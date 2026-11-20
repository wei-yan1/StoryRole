"""StoryRole domain services used by action handlers.

Services are capabilities, not controllers. They may call domain models,
RoleRAG, memory, Nuwa and persistence, but they never decide the next action.
The `StoryRoleTurn` object is the only shared mutable artifact.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.agents.runtime.compiler import PlanCompiler
from app.agents.storyrole.harness.appraisal import choose_action, interpret_event, recall_plan
from app.agents.storyrole.harness.context_manifest import ContextManifest
from app.agents.storyrole.harness.review import ReviewPolicy, build_review_packet, run_review_loop
from app.agents.storyrole.harness.update import update_interaction_state


def _manifest_context(manifest: ContextManifest | None) -> dict[str, Any]:
    if manifest is None:
        return {}
    return {section.name: list(section.lines) for section in manifest.sections if section.lines}


class PlanningService:
    def __init__(self, turn: Any) -> None:
        self.turn = turn

    async def plan_turn(self, execution: Any) -> dict[str, Any]:
        from app.agents.decision.mode import resolve_mode
        from app.agents.storyrole.query_planner import QueryPlannerAgent
        from app.agents.a2a.registry import client as a2a_client

        backend = os.getenv("STORYROLE_DECISION_BACKEND", "laya").lower()
        with self.turn.trace.step("query_planning", metadata={"backend": backend}):
            if backend == "rule":
                plan = await asyncio.to_thread(
                    QueryPlannerAgent().plan, {"message": self.turn.message},
                )
            else:
                result = await self.turn.agent._dispatch_timeout(
                    a2a_client, "query-planner",
                    {"message": self.turn.message, "trace_id": self.turn.trace.trace_id},
                    timeout=float(os.getenv("STORYROLE_QUERY_PLANNER_TIMEOUT", "20")),
                    fallback=QueryPlannerAgent().plan({"message": self.turn.message}),
                )
                plan, degraded = self.turn.agent._unwrap_fallback(result)
                if degraded:
                    self.turn.degradations.append("query_planner_fallback")
        mode = resolve_mode(str(self.turn.identity.get("requested_mode") or "quick"), plan)
        self.turn.mode = mode
        plan = {**plan, "mode": mode}
        if mode == "deep":
            plan["needs_novel_search"] = True
            plan["needs_memory"] = True
            plan["needs_timeline_check"] = True
        self.turn.plan = plan
        return {"intent": plan.get("intent", ""), "mode": mode}

    async def understand_event(self, execution: Any) -> dict[str, Any]:
        from app.agents.storyrole.harness.context import StoryRoleContextBuilder

        self.turn.identity["_subject_state"] = execution.subject_state
        with self.turn.trace.step("interpret", metadata={"planner_intent": self.turn.plan.get("intent", "")}):
            understanding = interpret_event(
                self.turn.message,
                persona_contract=self.turn.persona_contract,
                interaction_state=execution.subject_state,
                plan=self.turn.plan,
            )
            self.turn.plan = recall_plan(
                understanding, self.turn.plan, mode=self.turn.mode,
            )
            self.turn.understanding = understanding
            self.turn.execution_plan = PlanCompiler().compile(self.turn.plan, mode=self.turn.mode)
        # A recall action will rebuild the pre-recall manifest with evidence.
        # For turns that need no world recall, build it once here so cognition
        # does not see a contextless role.
        needs_recall = bool(
            self.turn.plan.get("needs_novel_search")
            or self.turn.plan.get("needs_relationship")
            or self.turn.plan.get("needs_timeline_check")
            or self.turn.plan.get("needs_memory")
            or str(self.turn.payload.get("web_mode") or "off") == "on"
        )
        if not needs_recall:
            StoryRoleContextBuilder(
                self.turn, max_tokens=self.turn.identity.get("max_context_tokens", 3200),
            ).build_pre_manifest()
        return {
            "user_move": understanding.user_move,
            "stakes": understanding.stakes,
            "needs": list(understanding.memory_needs),
        }


class RecallService:
    def __init__(self, turn: Any) -> None:
        self.turn = turn

    async def recall_role(self, execution: Any) -> dict[str, Any]:
        from app.agents.storyrole.harness.context import StoryRoleContextBuilder

        result = await execution.call_tool("rolerag.evidence", {})
        if not result.ok:
            return {"status": result.status, "error": result.error, "provenance": result.provenance}
        data = dict(result.data or {})
        self.turn.role_retrieval = data
        self.turn.role_evidence = list(data.get("evidence") or [])
        self.turn.identity["_subject_state"] = execution.subject_state
        StoryRoleContextBuilder(
            self.turn, max_tokens=self.turn.identity.get("max_context_tokens", 3200),
        ).build_pre_manifest()
        return {
            "evidence_count": len(self.turn.role_evidence),
            "cutoff": data.get("cutoff"),
            "route": data.get("route"),
            "provenance": result.provenance,
        }

    async def recall_memory(self, execution: Any) -> dict[str, Any]:
        result = await execution.call_tool(
            "memory.search", {"query": self.turn.message, "limit": 5},
        )
        if not result.ok:
            return {"status": result.status, "error": result.error}
        self.turn.memories = list(result.data or [])
        return {"memory_count": len(self.turn.memories)}

    async def recall_web(self, execution: Any) -> dict[str, Any]:
        result = await execution.call_tool(
            "web.search", {"query": self.turn.message, "max_results": 4},
        )
        if not result.ok:
            return {"status": result.status, "error": result.error}
        self.turn.web_evidence = list(result.data or [])
        return {"web_count": len(self.turn.web_evidence)}

    async def relation_state(self, execution: Any) -> dict[str, Any]:
        result = await execution.call_tool(
            "relationship.state", {"character_id": self.turn.character_id},
        )
        if not result.ok:
            return {"status": result.status, "error": result.error}
        self.turn.relationship = dict(result.data or {})
        return dict(self.turn.relationship)

    async def timeline_guard(self, execution: Any) -> dict[str, Any]:
        result = await execution.call_tool(
            "timeline.guard", {"message": self.turn.message},
        )
        if not result.ok:
            return {"status": result.status, "error": result.error}
        self.turn.timeline = dict(result.data or self.turn.timeline)
        return {"allowed": self.turn.timeline.get("allowed")}


class CognitionService:
    def __init__(self, turn: Any) -> None:
        self.turn = turn

    async def cognition(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client
        from app.agents.storyrole.harness.context import StoryRoleContextBuilder

        if self.turn.pre_manifest is None:
            StoryRoleContextBuilder(
                self.turn, max_tokens=self.turn.identity.get("max_context_tokens", 3200),
            ).build_pre_manifest()
        execution.charge_model(stage="cognition")
        result = await self.turn.agent._dispatch_timeout(
            a2a_client, "character-reasoning",
            {
                "message": self.turn.message,
                "plan": self.turn.plan,
                "context": _manifest_context(self.turn.pre_manifest),
                "role_context": self.turn.role_context(),
                "subject_state": execution.subject_state.as_dict(),
                "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
                "deep_reasoning": False,
                "trace_id": self.turn.trace.trace_id,
            },
            timeout=8.0,
            fallback={"response_action": "自然回应并保留角色立场"},
        )
        value, degraded = self.turn.agent._unwrap_fallback(result)
        self.turn.cognition = dict(value or {})
        if degraded:
            self.turn.degradations.append("character_reasoning_fallback")
        return {
            "decision_backend": self.turn.cognition.get("decision_backend") or "deterministic_quick",
            "degraded": degraded,
        }

    async def deep_plan(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client
        from app.agents.storyrole.deep_planner import DeepQuestionPlannerAgent

        with self.turn.trace.step("deep_question_planning"):
            result = await self.turn.agent._dispatch_timeout(
                a2a_client, "deep-question-planner",
                {
                    "message": self.turn.message, "profile": self.turn.profile,
                    "period_id": self.turn.period_id, "classification": self.turn.plan,
                    "trace_id": self.turn.trace.trace_id,
                },
                timeout=20.0,
                fallback=DeepQuestionPlannerAgent._fallback(self.turn.message),
            )
        self.turn.deep_plan, degraded = self.turn.agent._unwrap_fallback(result)
        if degraded:
            self.turn.degradations.append("deep_planner_fallback")
        return {"queries": len(self.turn.deep_plan.get("search_queries") or [])}

    async def deep_retrieval(self, execution: Any) -> dict[str, Any]:
        queries = self.turn.deep_plan.get("search_queries") or [self.turn.message]
        results = await asyncio.gather(*(
            asyncio.to_thread(
                self.turn.agent.search_evidence,
                novel_id=self.turn.novel_id, owner_id=self.turn.owner_id,
                query=str(query), character_name=self.turn.character_name,
                period_id=self.turn.period_id, k=8, rerank=False,
            )
            for query in queries[:3]
        ), return_exceptions=True)
        lists = [item for item in results if isinstance(item, list)]
        if not lists:
            self.turn.degradations.append("novel_evidence_unavailable")
        evidence = self.turn.agent._merge_evidence(lists, limit=18)
        self.turn.role_evidence = evidence
        self.turn.role_retrieval = {
            **self.turn.role_retrieval,
            "evidence": evidence,
            "cutoff": self.turn.role_retrieval.get("cutoff"),
        }
        return {"evidence_count": len(evidence)}

    async def context_curate(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client

        self.turn.identity["_subject_state"] = execution.subject_state
        pre = self.turn.pre_manifest
        payload = {
            "novel_id": self.turn.novel_id, "owner_id": self.turn.owner_id,
            "character_name": self.turn.character_name, "message": self.turn.message,
            "plan": self.turn.plan, "profile": self.turn.profile,
            "persona_contract": self.turn.persona_contract.as_dict() if self.turn.persona_contract else {},
            "period_id": self.turn.period_id, "evidence": self.turn.profile_evidence,
            "retrieved_evidence": self.turn.role_evidence,
            "web_evidence": self.turn.web_evidence,
            "recent_messages": list(self.turn.payload.get("recent_messages") or []),
            "memories": self.turn.memories, "relationship": self.turn.relationship,
            "timeline": self.turn.timeline, "role_context": self.turn.role_context(),
            "interaction_state": execution.subject_state.as_dict(),
            "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
            "situated_appraisal": {
                "user_move": getattr(self.turn.understanding, "user_move", ""),
                "stakes": getattr(self.turn.understanding, "stakes", ""),
                "understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
            },
            "trace_id": self.turn.trace.trace_id,
        }
        fallback = {"context": {
            "profile": self.turn.profile,
            "recent_messages": list(self.turn.payload.get("recent_messages") or [])[-12:],
            "memories": self.turn.memories,
            "relationship": self.turn.relationship,
            "timeline": self.turn.timeline,
            "evidence": self.turn.profile_evidence[:8],
            "novel_evidence": self.turn.role_evidence,
            "web_evidence": self.turn.web_evidence,
            "role_context": self.turn.role_context(),
            "persona_contract": self.turn.persona_contract.as_dict() if self.turn.persona_contract else {},
            "interaction_state": execution.subject_state.as_dict(),
            "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
            "situated_appraisal": payload["situated_appraisal"],
        }}
        result = await self.turn.agent._dispatch_timeout(
            a2a_client, "context-curator", payload, timeout=15.0, fallback=fallback,
        )
        value, degraded = self.turn.agent._unwrap_fallback(result)
        if degraded:
            self.turn.degradations.append("context_curator_fallback")
        self.turn.curated_context = dict((value or {}).get("context") or {})
        turn_context = dict(self.turn.curated_context)
        if pre is not None and not turn_context:
            turn_context = _manifest_context(pre)
        return {"context_keys": sorted(turn_context)[:12]}

    async def deep_evidence(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client
        from app.agents.storyrole.evidence_analyst import EvidenceAnalysisAgent

        pre = self.turn.pre_manifest
        analysis_context = dict(self.turn.curated_context or _manifest_context(pre))
        analysis_context["novel_evidence"] = list(analysis_context.get("novel_evidence") or self.turn.role_evidence)[:6]
        result = await self.turn.agent._dispatch_timeout(
            a2a_client, "evidence-analysis",
            {
                "message": self.turn.message, "deep_plan": self.turn.deep_plan,
                "context": analysis_context, "trace_id": self.turn.trace.trace_id,
            },
            timeout=90.0,
            fallback=lambda: EvidenceAnalysisAgent().analyze({"context": analysis_context}),
        )
        self.turn.evidence_analysis, degraded = self.turn.agent._unwrap_fallback(result)
        if degraded:
            self.turn.degradations.append("evidence_analysis_fallback")
        return {"evidence_analysis": bool(self.turn.evidence_analysis)}

    async def deep_cognition(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client
        from app.agents.storyrole.role_cognition_agent import RoleCognitionAgent

        execution.charge_model(stage="cognition")
        result = await self.turn.agent._dispatch_timeout(
            a2a_client, "role-cognition",
            {
                "message": self.turn.message, "profile": self.turn.profile,
                "period_id": self.turn.period_id, "relationship": self.turn.relationship,
                "evidence_analysis": self.turn.evidence_analysis,
                "analysis_type": self.turn.deep_plan.get("analysis_type", self.turn.plan.get("intent", "mixed")),
                "role_context": self.turn.role_context(),
                "subject_state": execution.subject_state.as_dict(),
                "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
                "persona_contract": self.turn.persona_contract.as_dict() if self.turn.persona_contract else {},
                "recent_messages": list(self.turn.payload.get("recent_messages") or [])[-8:],
                "history_summary": str(self.turn.payload.get("history_summary") or ""),
                "trace_id": self.turn.trace.trace_id,
                "deep_plan": self.turn.deep_plan,
            },
            timeout=45.0,
            fallback=lambda: RoleCognitionAgent().decide({
                "message": self.turn.message, "profile": self.turn.profile,
                "evidence_analysis": self.turn.evidence_analysis,
                "role_context": self.turn.role_context(),
                "subject_state": execution.subject_state.as_dict(),
                "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
                "persona_contract": self.turn.persona_contract.as_dict() if self.turn.persona_contract else {},
            }),
        )
        value, degraded = self.turn.agent._unwrap_fallback(result)
        self.turn.cognition = {**dict(value or {}), "evidence_analysis": self.turn.evidence_analysis}
        if degraded:
            self.turn.degradations.append("role_cognition_fallback")
        return {"decision_backend": self.turn.cognition.get("decision_backend") or "role_cognition"}


class GenerationService:
    def __init__(self, turn: Any) -> None:
        self.turn = turn

    def decide(self, execution: Any) -> dict[str, Any]:
        from app.agents.storyrole.harness.context import StoryRoleContextBuilder

        self.turn.appraisal = choose_action(
            self.turn.understanding,
            persona_contract=self.turn.persona_contract,
            interaction_state=execution.subject_state,
            role_context=self.turn.role_context(),
            evidence=self.turn.role_evidence,
            relationship=self.turn.relationship,
            cognition=self.turn.cognition,
        )
        StoryRoleContextBuilder(
            self.turn, max_tokens=self.turn.identity.get("max_context_tokens", 3200),
        ).build_full_manifest()
        return {
            "action": self.turn.appraisal.action,
            "change_from_previous": self.turn.appraisal.decision.change_from_previous,
        }

    def assemble_context(self, execution: Any) -> dict[str, Any]:
        from app.agents.storyrole.harness.context import StoryRoleContextBuilder

        manifest = StoryRoleContextBuilder(
            self.turn, max_tokens=self.turn.identity.get("max_context_tokens", 3200),
        ).build_full_manifest()
        return {
            "estimated_tokens": manifest.estimated_tokens,
            "trimmed": manifest.trimmed,
            "budget_trimmed": manifest.budget_trimmed,
        }

    async def express(self, execution: Any) -> dict[str, Any]:
        execution.charge_model(stage="express")
        context = {
            **dict(self.turn.curated_context or {}),
            "role_context": self.turn.role_context(),
            "interaction_state": execution.subject_state.as_dict(),
            "subject_understanding": self.turn.understanding.as_dict() if self.turn.understanding else {},
            "action_decision": self.turn.appraisal.decision.as_dict() if self.turn.appraisal else {},
            "situated_appraisal": self.turn.appraisal.as_dict() if self.turn.appraisal else {},
            "memories": self.turn.memories,
        }
        timeout = max(0.01, execution.ledger.remaining_ms() / 1000) if execution.ledger else 30.0
        try:
            answer = await asyncio.wait_for(
                self.turn.agent._run_agent(
                    novel_id=self.turn.novel_id, owner_id=self.turn.owner_id,
                    character_name=self.turn.character_name, profile=self.turn.profile,
                    evidence=self.turn.profile_evidence, message=self.turn.message,
                    recent_messages=list(self.turn.payload.get("recent_messages") or []),
                    plan=self.turn.plan, context=context, reasoning=self.turn.cognition,
                    period_id=self.turn.period_id, mode=self.turn.mode,
                    trace_id=self.turn.trace.trace_id,
                    generation_state=self.turn.generation_state,
                    history_summary=str(self.turn.payload.get("history_summary") or ""),
                    persona_contract=self.turn.persona_contract_text,
                    context_manifest=self.turn.full_manifest,
                    appraisal=self.turn.appraisal, kernel=None,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"status": "timeout", "error": "回答生成超时"}
        self.turn.draft = str(answer or "")
        if not self.turn.draft:
            return {"status": "error", "error": "回答为空"}
        self.turn.final_answer = self.turn.draft
        return {"chars": len(self.turn.draft)}

    async def review(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client
        from app.rag.rolerag.persona.contract import check_persona

        self.turn.local_fidelity = check_persona(
            self.turn.persona_contract,
            self.turn.draft,
            unknown_terms=tuple((self.turn.role_retrieval.get("scope") or {}).get("external_terms") or ()),
        )
        self.turn.review_packet = build_review_packet(
            message=self.turn.message, draft=self.turn.draft,
            persona_contract=self.turn.persona_contract,
            role_context=self.turn.role_context(),
            relationship=self.turn.relationship,
            period=self.turn.period,
        )
        needs_semantic = self.turn.mode == "deep" or not self.turn.local_fidelity.ok

        async def review_once(packet: Any, draft: str, attempt: int) -> dict[str, Any]:
            packet.draft = draft
            packet.attempt = attempt
            if not needs_semantic:
                return {
                    "pass": self.turn.local_fidelity.ok,
                    "score": self.turn.local_fidelity.score,
                    "persona_score": self.turn.local_fidelity.score,
                    "violations": list(self.turn.local_fidelity.violations),
                    "rewrite_instruction": self.turn.local_fidelity.instruction,
                    "final_answer": draft,
                    "review_skipped": True,
                }
            execution.charge_model(stage="review")
            result = await self.turn.agent._dispatch_timeout(
                a2a_client, "consistency-guard",
                {
                    "message": self.turn.message, "draft_answer": draft,
                    "persona_contract": self.turn.persona_contract.as_dict() if self.turn.persona_contract else {},
                    "persona_fidelity": self.turn.local_fidelity.as_dict(),
                    "review_packet": packet.as_dict(),
                    "timeline": self.turn.timeline, "trace_id": self.turn.trace.trace_id,
                },
                timeout=45.0 if self.turn.mode == "deep" else 12.0,
                fallback={
                    "pass": self.turn.local_fidelity.ok,
                    "score": self.turn.local_fidelity.score,
                    "persona_score": self.turn.local_fidelity.score,
                    "violations": list(self.turn.local_fidelity.violations),
                    "rewrite_instruction": self.turn.local_fidelity.instruction,
                    "final_answer": draft,
                },
            )
            value, degraded = self.turn.agent._unwrap_fallback(result)
            if degraded:
                self.turn.degradations.append("persona_fidelity_guard_fallback")
            return value

        loop = await run_review_loop(
            draft=self.turn.draft, packet=self.turn.review_packet,
            review_fn=review_once,
            policy=ReviewPolicy(accept_score=float(os.getenv("STORYROLE_HARNESS_ACCEPT_SCORE", "0.65"))),
            max_attempts=int(self.turn.identity.get("max_review_attempts", 1)),
        )
        last = dict(loop.reviews[-1]) if loop.reviews else {}
        self.turn.review = {
            **last, "pass": loop.accepted, "persona_score": loop.best_score,
            "final_answer": loop.final_answer, "review_loop": loop.as_dict(),
        }
        self.turn.final_answer = loop.final_answer
        return {
            "accepted": loop.accepted,
            "score": loop.best_score,
            "attempts": loop.attempts,
        }

    async def memory_decision(self, execution: Any) -> dict[str, Any]:
        from app.agents.a2a.registry import client as a2a_client

        result = await self.turn.agent._dispatch_timeout(
            a2a_client, "memory-decision",
            {"message": self.turn.message, "profile": self.turn.profile,
             "trace_id": self.turn.trace.trace_id},
            timeout=5.0,
            fallback={"requires_confirmation": False, "should_save": False},
        )
        value, degraded = self.turn.agent._unwrap_fallback(result)
        if degraded:
            self.turn.degradations.append("memory_decision_fallback")
        self.turn.memory_decision = dict(value or {})
        return {"should_save": self.turn.memory_decision.get("should_save")}


class PersistenceService:
    def __init__(self, turn: Any) -> None:
        self.turn = turn

    def learn(self, execution: Any) -> dict[str, Any]:
        state = update_interaction_state(
            execution.subject_state,
            user_message=self.turn.message,
            answer=self.turn.final_answer,
            appraisal=self.turn.appraisal.as_dict() if self.turn.appraisal else {},
            accepted=bool(self.turn.review.get("pass")),
            score=float(self.turn.review.get("persona_score") or (
                self.turn.local_fidelity.score if self.turn.local_fidelity else 0.0
            )),
            attempts=int((self.turn.review.get("review_loop") or {}).get("attempts") or 1),
            evidence_ids=self.turn.evidence_ids(),
        )
        if self.turn.full_manifest is not None:
            state.context_snapshot = dict(self.turn.full_manifest.snapshot.as_dict())
        execution.state["subject_state"] = state
        execution.state["final_answer"] = self.turn.final_answer
        self.turn.answer = self.turn.final_answer
        try:
            self.turn.agent._record_evidence_graph(
                trace_id=self.turn.trace.trace_id, message=self.turn.message,
                profile=self.turn.profile, period_id=self.turn.period_id,
                evidence=self.turn.profile_evidence + self.turn.role_evidence + self.turn.web_evidence,
                answer=self.turn.final_answer,
            )
        except Exception:
            pass
        # Background writes stay out of the critical turn; failures are logged,
        # not allowed to rewrite the answer.
        try:
            from app.agents.a2a.registry import client as a2a_client

            tasks = [
                asyncio.create_task(self.turn.agent._persist_memory_candidate_async(
                    self.turn.payload, self.turn.identity["character"],
                    self.turn.message, self.turn.final_answer, self.turn.memory_decision,
                )),
                asyncio.create_task(self.turn.agent._update_relationship(
                    a2a_client,
                    self.turn.payload, character_id=self.turn.character_id,
                    novel_id=self.turn.novel_id, owner_id=self.turn.owner_id,
                    message=self.turn.message, final_answer=self.turn.final_answer,
                )),
            ]
            for task in tasks:
                task.add_done_callback(self.turn.agent._log_background_failure)
        except Exception:
            pass
        return {"turn": state.turn_count, "episodes": len(state.episodes)}
