"""StoryRole turn state and action-scoped context building.

The turn object is a passive data carrier. It does not execute actions and it
does not choose the next step; `services` writes its artifacts, `actions` reads
them, and `policy` only inspects observable flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agents.storyrole.harness.context_manifest import ContextManifest, build_context_manifest
from app.harness.context_pipeline import ContextPipeline, ContextView


@dataclass
class StoryRoleTurn:
    agent: Any
    payload: dict[str, Any]
    identity: dict[str, Any]
    trace: Any
    scope: Any
    mode: str = "quick"

    message: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    understanding: Any = None
    execution_plan: Any = None
    deep_plan: dict[str, Any] = field(default_factory=dict)
    role_retrieval: dict[str, Any] = field(default_factory=dict)
    role_evidence: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    web_evidence: list[dict[str, Any]] = field(default_factory=list)
    relationship: dict[str, Any] = field(default_factory=dict)
    timeline: dict[str, Any] = field(
        default_factory=lambda: {
            "allowed": True,
            "future_probe": False,
            "notes": "未触发时间线检查",
        }
    )
    evidence_analysis: dict[str, Any] = field(default_factory=dict)
    cognition: dict[str, Any] = field(default_factory=dict)
    curated_context: dict[str, Any] = field(default_factory=dict)
    appraisal: Any = None
    pre_manifest: ContextManifest | None = None
    full_manifest: ContextManifest | None = None
    draft: str = ""
    final_answer: str = ""
    review: dict[str, Any] = field(default_factory=dict)
    review_packet: Any = None
    local_fidelity: Any = None
    memory_decision: dict[str, Any] = field(default_factory=dict)
    generation_state: dict[str, Any] = field(default_factory=lambda: {"degraded": False})
    attempted: set[str] = field(default_factory=set)
    degradations: list[str] = field(default_factory=list)
    graph_trace_id: str = ""
    answer: str = ""
    runtime_error: str = ""

    def __post_init__(self) -> None:
        self.message = str(self.identity.get("message") or self.payload.get("message") or "").strip()
        self.mode = str(self.identity.get("requested_mode") or self.payload.get("mode") or "quick")
        if self.mode not in {"quick", "deep"}:
            self.mode = "quick"
        self.identity = {
            **self.identity,
            "owner_id": int(self.identity["owner_id"]),
            "novel_id": str(self.identity["novel_id"]),
            "character_id": int(self.identity["character_id"]),
            "period_id": self.identity.get("period_id"),
            "character": self.identity.get("character") or {},
            "profile_row": self.identity.get("profile_row") or {},
            "profile": self.identity.get("profile") or {},
            "profile_evidence": list(self.identity.get("profile_evidence") or []),
            "persona_contract": self.identity.get("persona_contract"),
            "persona_contract_text": str(self.identity.get("persona_contract_text") or ""),
            "period": self.identity.get("period"),
        }

    @property
    def owner_id(self) -> int:
        return int(self.identity["owner_id"])

    @property
    def novel_id(self) -> str:
        return str(self.identity["novel_id"])

    @property
    def character_id(self) -> int:
        return int(self.identity["character_id"])

    @property
    def period_id(self) -> int | None:
        value = self.identity.get("period_id")
        return int(value) if value is not None else None

    @property
    def character_name(self) -> str:
        return str((self.identity.get("character") or {}).get("canonical_name") or "")

    @property
    def profile(self) -> dict[str, Any]:
        return dict(self.identity.get("profile") or {})

    @property
    def profile_evidence(self) -> list[dict[str, Any]]:
        return list(self.identity.get("profile_evidence") or [])

    @property
    def persona_contract(self) -> Any:
        return self.identity.get("persona_contract")

    @property
    def persona_contract_text(self) -> str:
        return str(self.identity.get("persona_contract_text") or "")

    @property
    def period(self) -> dict[str, Any] | None:
        return self.identity.get("period")

    def subject_state(self, execution: Any = None) -> Any:
        if execution is not None:
            return execution.subject_state
        return self.identity.get("_subject_state")

    def role_context(self) -> dict[str, Any]:
        return {
            "evidence": self.role_evidence,
            "ego_summary": self.role_retrieval.get("ego_summary", ""),
            "profile_overlay": self.role_retrieval.get("profile_overlay", {}),
            "route": self.role_retrieval.get("route", ""),
            "route_reason": self.role_retrieval.get("route_reason", ""),
            "cutoff": self.role_retrieval.get("cutoff"),
            "multi_hop": self.role_retrieval.get("multi_hop", False),
        }

    def evidence_ids(self) -> list[str]:
        ids = [
            str(item.get("chunk_id") or item.get("id") or "")
            for item in self.role_evidence
            if item.get("chunk_id") or item.get("id")
        ]
        return ids[:16]

    def set_pre_manifest(self, manifest: ContextManifest) -> None:
        self.pre_manifest = manifest

    def set_full_manifest(self, manifest: ContextManifest) -> None:
        self.full_manifest = manifest

    def degraded(self) -> bool:
        return bool(self.degradations) or bool(self.generation_state.get("degraded"))


class StoryRoleContextBuilder:
    """Builds at most two manifests: pre-recall and post-decision.

    Earlier actions get a small pointer view; recall actions get the pre-recall
    manifest; assemble/express/review get the post-decision manifest. The
    review view is filtered again by `ContextPipeline`.
    """

    def __init__(self, turn: StoryRoleTurn, *, max_tokens: int = 3200) -> None:
        self.turn = turn
        self.max_tokens = max(0, int(max_tokens))

    def _minimal_view(self, action: str) -> ContextView:
        identity_lines = [
            f"角色：{self.turn.character_name}",
            f"时期：{self.turn.profile.get('period_name') or '全书时期'}",
        ]
        contract = self.turn.persona_contract_text
        if contract:
            identity_lines.append(contract[:220])
        situation = f"用户这一句：{self.turn.message[:280]}"
        sections = {"identity": identity_lines, "situation": [situation]}
        return ContextView(
            action=action, sections=sections,
            withheld=["self_state", "decision", "memory", "history", "constraints"],
            estimated_tokens=max(1, sum(len(line) for line in identity_lines + [situation]) // 2),
            rendered="\n".join(identity_lines + [situation]),
            level="summary",
        )

    def build(self, action: Any, execution: Any = None) -> ContextView | None:
        action_name = action.name if hasattr(action, "name") else str(action)
        if action_name in {"plan_turn", "understand_event"} and self.turn.pre_manifest is None:
            return self._minimal_view(action_name)
        manifest = self.turn.full_manifest or self.turn.pre_manifest
        if manifest is None:
            return self._minimal_view(action_name)
        pipeline = ContextPipeline(manifest, max_tokens=self.max_tokens)
        return pipeline.view(action_name)

    def build_pre_manifest(self) -> ContextManifest:
        state = self.turn.identity.get("_subject_state")
        state_payload = state.as_dict() if hasattr(state, "as_dict") else state or {}
        manifest = build_context_manifest(
            persona_contract=self.turn.persona_contract_text,
            profile=self.turn.profile,
            role_context={"cutoff": None},
            evidence=[],
            interaction_state=state_payload,
            appraisal={
                "understanding": self.turn.understanding.as_dict() if self.turn.understanding is not None else {},
                "user_move": getattr(self.turn.understanding, "user_move", ""),
                "stakes": getattr(self.turn.understanding, "stakes", ""),
            },
            recent_messages=list(self.turn.payload.get("recent_messages") or []),
            timeline=self.turn.timeline,
            budget_tokens=self.max_tokens,
        )
        self.turn.set_pre_manifest(manifest)
        return manifest

    def build_full_manifest(self) -> ContextManifest:
        state = self.turn.identity.get("_subject_state")
        state_payload = state.as_dict() if hasattr(state, "as_dict") else state or {}
        manifest = build_context_manifest(
            persona_contract=self.turn.persona_contract_text,
            profile=self.turn.profile,
            role_context=self.turn.role_context(),
            evidence=self.turn.profile_evidence + self.turn.role_evidence,
            interaction_state=state_payload,
            appraisal=self.turn.appraisal.as_dict() if self.turn.appraisal is not None else {},
            recent_messages=list(self.turn.payload.get("recent_messages") or []),
            timeline=self.turn.timeline,
            budget_tokens=self.max_tokens,
        )
        self.turn.set_full_manifest(manifest)
        return manifest
