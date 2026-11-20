"""Bounded Harness runtime for one character turn.

Ownership is explicit:

- `AgentHarness` owns the loop, guardrails, context handoff, budget, trace,
  checkpoints and final stop reason;
- `Policy` only proposes the next action;
- `ActionRegistry` owns one isolated handler per action;
- handlers return `Observation`; they never call the loop or mutate the policy.

The old model where policy both planned and executed every domain step is
deliberately gone.
"""

from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .actions import (
    ActionRegistry,
    ActionSpec,
    AgentAction,
    Observation,
)
from .budget import BudgetExceeded, BudgetLedger
from .checkpoint import TurnCheckpoint
from .context_pipeline import ContextView
from .guardrails import (
    ActionLimitGuard,
    BudgetGuard,
    DependencyGuard,
    GuardrailPipeline,
    TerminalGuard,
)
from .policy import PolicyView
from .recovery import DefaultRecoveryPolicy, RecoveryDecision, RecoveryPolicy
from .tool_runtime import ToolResult, ToolRuntime
from .trace import HarnessTrace
from .types import SubjectState, TurnBudget, TurnScope, now_iso


# Kept as the built-in catalog for callers that only need names. StoryRole
# supplies richer specs and real handlers through its own registry.
DEFAULT_ACTION_SPECS: dict[str, ActionSpec] = {
    "plan_turn": ActionSpec("plan_turn", "判断本轮需要哪些能力", category="state", max_per_turn=1, context_sections=("identity", "situation", "constraints")),
    "understand_event": ActionSpec("understand_event", "理解用户这句话对角色意味着什么", ("plan_turn",), "state", 1, ("identity", "self_state", "situation", "history", "constraints")),
    "recall_role": ActionSpec("recall_role", "检索角色可见的小说证据", ("understand_event",), "tool", 1, ("identity", "self_state", "situation", "constraints")),
    "recall_user_memory": ActionSpec("recall_user_memory", "检索当前用户相关长期记忆", ("understand_event",), "tool", 1, ("identity", "self_state", "situation", "constraints")),
    "recall_web": ActionSpec("recall_web", "显式联网时检索外部信息", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
    "relation_state": ActionSpec("relation_state", "读取角色与来客的关系状态", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
    "timeline_guard": ActionSpec("timeline_guard", "检查是否越过角色可见时期", ("understand_event",), "tool", 1, ("identity", "situation", "constraints")),
    "cognition": ActionSpec("cognition", "形成角色认知", ("understand_event",), "model", 1, ("identity", "self_state", "situation", "memory", "constraints")),
    "decide": ActionSpec("decide", "形成本轮行动决定", ("cognition",), "state", 1, ("identity", "self_state", "situation", "memory", "constraints")),
    "assemble_context": ActionSpec("assemble_context", "按本轮决定组装最终上下文", ("decide",), "state", 1, ("identity", "self_state", "situation", "memory", "decision", "history", "constraints")),
    "express": ActionSpec("express", "按角色口吻生成回答", ("assemble_context",), "model", 1, ("identity", "self_state", "situation", "memory", "decision", "history", "constraints"), critical=True),
    "review": ActionSpec("review", "独立评审草稿是否像角色", ("express",), "model", 1, ("identity", "decision", "memory", "constraints"), critical=True),
    "learn": ActionSpec("learn", "把本轮实际经历写回主体状态", ("review",), "state", 1, ("identity", "self_state", "decision", "constraints")),
    "stop": ActionSpec("stop", "结束本轮", ("learn",), "control", 1, (), terminal=True),
}

ACTION_SPECS = DEFAULT_ACTION_SPECS


@dataclass
class ExecutionState:
    scope: TurnScope
    mode: str
    step: int
    max_steps: int
    state: dict[str, Any]
    subject_state: SubjectState
    handoff: dict[str, Any]
    observations: list[Observation]
    completed_actions: list[str]
    action_counts: dict[str, int]
    checkpoint: TurnCheckpoint
    action: AgentAction | None = None
    context: ContextView | None = None
    attempt: int = 0
    tool_runtime: ToolRuntime | None = None
    ledger: BudgetLedger | None = None
    trace: HarnessTrace | None = None

    async def call_tool(
        self, name: str, args: dict[str, Any] | None = None, *, actor: str = "action",
    ) -> ToolResult:
        if self.tool_runtime is None:
            return ToolResult(name=name, status="error", error="tool_runtime_missing")
        if self.ledger is not None:
            self.ledger.charge_tool()
        result = await self.tool_runtime.call(
            name, args or {}, scope=self.scope, actor=actor,
            trace_id=self.checkpoint.turn_id,
        )
        if self.trace is not None:
            self.trace.record(
                "tool", name=name, status=result.status, duration_ms=result.duration_ms,
                provenance=result.provenance, degraded=result.degraded,
            )
        return result

    def charge_model(self, *, stage: str, tokens: int = 0) -> None:
        if self.ledger is not None:
            self.ledger.charge_model(stage=stage, tokens=tokens)
        if self.trace is not None:
            self.trace.record(
                "budget", stage=stage,
                model_calls=self.ledger.model_calls if self.ledger is not None else 0,
                tokens=self.ledger.tokens if self.ledger is not None else 0,
            )

    @property
    def action_history(self) -> list[dict[str, Any]]:
        return list(self.checkpoint.action_history)


@dataclass
class AgentView(PolicyView):
    """Backward-compatible name for the policy-facing view."""


@dataclass
class HarnessResult:
    answer: str
    stop_reason: str
    actions: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    trace: dict[str, Any]
    budget: dict[str, Any]
    state: dict[str, Any]
    checkpoint: dict[str, Any]
    degraded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "stop_reason": self.stop_reason,
            "actions": list(self.actions),
            "observations": list(self.observations),
            "trace": dict(self.trace),
            "budget": dict(self.budget),
            "state": dict(self.state),
            "checkpoint": dict(self.checkpoint),
            "degraded": bool(self.degraded),
        }


class AgentHarness:
    """One bounded turn. Domain identity, prompts and tools live outside this class."""

    def __init__(
        self,
        *,
        scope: TurnScope,
        mode: str = "quick",
        budget: TurnBudget | None = None,
        state_store: Any = None,
        context_pipeline: Any = None,
        context_provider: Callable[[AgentAction, ExecutionState], ContextView | None] | None = None,
        tool_runtime: ToolRuntime | None = None,
        trace: HarnessTrace | None = None,
        registry: ActionRegistry | None = None,
        guardrails: GuardrailPipeline | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        handoff_builder: Callable[[SubjectState], dict[str, Any]] | None = None,
        max_steps: int = 16,
        checkpoint: TurnCheckpoint | None = None,
    ) -> None:
        self.scope = scope
        self.mode = mode
        self.budget = budget or TurnBudget.for_mode(mode)
        self.ledger = BudgetLedger(self.budget)
        self.state_store = state_store
        self.context_pipeline = context_pipeline
        self.context_provider = context_provider
        self.tool_runtime = tool_runtime or ToolRuntime()
        self.registry = registry or ActionRegistry()
        self.trace = trace or HarnessTrace(
            turn_id=f"{scope.state_key}:{int(time.time() * 1000)}",
            scope_key=scope.state_key,
        )
        self.max_steps = max(1, int(max_steps))
        self.guardrails = guardrails or GuardrailPipeline([
            DependencyGuard(),
            ActionLimitGuard(),
            BudgetGuard(self.ledger, max_steps=self.max_steps),
            TerminalGuard(),
        ])
        self.recovery_policy = recovery_policy or DefaultRecoveryPolicy()
        self.handoff_builder = handoff_builder
        self.checkpoint = checkpoint or TurnCheckpoint(
            turn_id=self.trace.turn_id,
            scope_key=scope.state_key,
            mode=mode,
        )
        self.execution: ExecutionState | None = None
        self.turn_state: dict[str, Any] = {}
        self._seen: dict[str, int] = {}
        self._stop_reason = ""
        self._actions: list[AgentAction] = []
        self._observations: list[Observation] = []
        self._completed: list[str] = []

    def action_spec(self, name: str) -> ActionSpec | None:
        return self.registry.spec(name)

    def charge_model(self, *, stage: str, tokens: int = 0) -> None:
        self.ledger.charge_model(stage=stage, tokens=tokens)
        self.trace.record(
            "budget", stage=stage,
            model_calls=self.ledger.model_calls, tokens=self.ledger.tokens,
        )

    async def call_tool(
        self, name: str, args: dict[str, Any] | None = None, *, actor: str = "policy",
    ) -> ToolResult:
        self.ledger.charge_tool()
        result = await self.tool_runtime.call(
            name, args, scope=self.scope, actor=actor, trace_id=self.trace.turn_id,
        )
        self.trace.record(
            "tool", name=name, status=result.status, duration_ms=result.duration_ms,
            provenance=result.provenance, degraded=result.degraded,
        )
        return result

    def _load_state(self, subject_state: SubjectState | None) -> SubjectState:
        if subject_state is not None:
            return subject_state
        if self.state_store is not None:
            try:
                loaded = self.state_store.load(self.scope)
                return loaded if isinstance(loaded, SubjectState) else SubjectState.from_dict(loaded)
            except Exception as error:
                self.trace.record("state_load_failed", error=type(error).__name__)
        return SubjectState.empty()

    def _context_for(self, action: AgentAction, execution: ExecutionState) -> ContextView | None:
        if self.context_provider is not None:
            return self.context_provider(action, execution)
        if self.context_pipeline is not None:
            return self.context_pipeline.view(action.name)
        return None

    def _guardrail_context(self, execution: ExecutionState) -> Any:
        return execution

    async def _execute_once(
        self, action: AgentAction, context: ContextView | None, execution: ExecutionState,
    ) -> Observation:
        handler = self.registry.handler(action.name)
        if handler is None:
            return Observation(action.name, status="error", error=f"missing_handler:{action.name}")
        try:
            result = handler(action, context, execution)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, ToolResult):
                result = Observation(
                    action.name, status=result.status, data=result.data,
                    error=result.error, provenance=result.provenance,
                )
            if not isinstance(result, Observation):
                result = Observation(action.name, data=result)
            return result
        except Exception as error:
            return Observation(
                action.name, status="error", error=f"{type(error).__name__}: {error}",
            )

    async def _execute_with_recovery(
        self, action: AgentAction, context: ContextView | None, execution: ExecutionState,
    ) -> Observation:
        observation = await self._execute_once(action, context, execution)
        attempt = 0
        while observation.status == "timeout" or observation.status == "error":
            spec = self.registry.spec(action.name)
            if spec is None:
                return observation
            decision = self.recovery_policy.decide(action, spec, observation, attempt)
            if decision is None:
                break
            observation.recovery = decision.as_dict()
            self.trace.record(
                "recovery", action=action.name, decision=decision.action, reason=decision.reason,
            )
            if decision.action == "retry" and attempt < decision.max_attempts:
                attempt += 1
                execution.attempt = attempt
                observation = await self._execute_once(action, context, execution)
                continue
            if decision.action == "degrade":
                observation.status = "degraded"
                observation.error = observation.error or decision.reason
                break
            if decision.action == "replan":
                observation.status = "denied"
                observation.error = decision.reason
                break
            if decision.action == "stop":
                self._stop_reason = decision.reason
                break
        return observation

    def _apply_observation(
        self, action: AgentAction, observation: Observation, execution: ExecutionState,
    ) -> None:
        if observation.state_patch:
            execution.state.update(observation.state_patch)
        if observation.artifacts:
            execution.state.setdefault("artifacts", {}).update(observation.artifacts)
        self.ledger.charge_observation(observation)
        self.ledger.steps += 1
        if observation.ok:
            if action.name not in self._completed:
                self._completed.append(action.name)
        self._observations.append(observation)
        execution.completed_actions = list(self._completed)
        execution.observations = list(self._observations)
        self.checkpoint.mark(
            action=action.name,
            status=observation.status,
            reason=action.reason or observation.error,
            step=execution.step,
            budget=self.ledger.as_dict(),
            subject_state=execution.subject_state.as_dict(),
            artifacts_digest=self._artifacts_digest(execution.state),
        )
        self.trace.observation(
            action.name, observation.status,
            error=observation.error, provenance=observation.provenance,
        )
        self.trace.record(
            "checkpoint", action=action.name, completed=list(self._completed),
            step=execution.step,
        )

    @staticmethod
    def _artifacts_digest(state: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in state.items():
            if key in {"subject_state", "handoff", "artifacts"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value if not isinstance(value, str) else value[:180]
            elif isinstance(value, list):
                result[key] = {"type": "list", "count": len(value)}
            elif isinstance(value, dict):
                result[key] = {"type": "dict", "keys": sorted(value)[:20]}
        artifacts = state.get("artifacts")
        if isinstance(artifacts, dict):
            result["artifact_keys"] = sorted(artifacts)[:30]
        return result

    def _save_checkpoint(self, execution: ExecutionState, *, status: str, stop_reason: str) -> None:
        self.checkpoint.status = status
        self.checkpoint.stop_reason = stop_reason
        self.checkpoint.step = execution.step
        self.checkpoint.budget_snapshot = self.ledger.as_dict()
        self.checkpoint.subject_state = execution.subject_state.as_dict()
        self.checkpoint.updated_at = now_iso()
        if self.state_store is not None:
            try:
                self.state_store.save(
                    self.scope, execution.subject_state, checkpoint=self.checkpoint.as_dict(),
                )
                self.trace.record("state_saved", turn=execution.subject_state.turn_count)
            except Exception as error:
                self.trace.record("state_save_failed", error=type(error).__name__)

    async def run(
        self,
        policy: Any,
        *,
        state: dict[str, Any] | None = None,
        subject_state: SubjectState | None = None,
        persist: bool = True,
        resume: bool = False,
    ) -> HarnessResult:
        state = dict(state or {})
        self.turn_state = state
        if resume and self.checkpoint.completed_actions:
            subject = self.checkpoint.subject()
            self._completed = list(self.checkpoint.completed_actions)
            if not state.get("action_history"):
                state["action_history"] = list(self.checkpoint.action_history)
            self.trace.record(
                "resume", turn_id=self.checkpoint.turn_id,
                completed=list(self._completed), step=self.checkpoint.step,
            )
        else:
            subject = self._load_state(subject_state)
        state["subject_state"] = subject
        handoff = self._handoff(subject)
        state["handoff"] = handoff
        state.setdefault("mode", self.mode)
        state.setdefault("action_history", [])
        self.trace.record(
            "turn_start", mode=self.mode, scope=self.scope.state_key,
            handoff_turn=handoff.get("turn_count"), resumed=bool(resume),
        )

        execution = ExecutionState(
            scope=self.scope, mode=self.mode, step=int(self.checkpoint.step),
            max_steps=self.max_steps, state=state, subject_state=subject,
            handoff=handoff, observations=list(self._observations),
            completed_actions=list(self._completed),
            action_counts={},
            checkpoint=self.checkpoint,
            tool_runtime=self.tool_runtime,
            ledger=self.ledger,
            trace=self.trace,
        )
        self.execution = execution

        while execution.step < self.max_steps:
            if self.ledger.deadline_exceeded():
                self._stop_reason = "deadline_exceeded"
                break
            view = AgentView(
                action="", mode=self.mode, subject_state=subject, handoff=handoff,
                state=state, observations=list(self._observations),
                completed_actions=list(self._completed), step=execution.step,
                available_actions=self.registry.names(),
            )
            try:
                action = policy.next_action(view, state)
            except Exception as error:
                self._stop_reason = "policy_error"
                self._observations.append(Observation(
                    action="policy", status="error", error=f"{type(error).__name__}: {error}",
                ))
                self.trace.observation("policy", "error", error=type(error).__name__)
                break
            if action is None:
                self._stop_reason = "completed"
                break
            if isinstance(action, str):
                action = AgentAction(name=action)
            if not isinstance(action, AgentAction):
                self._stop_reason = "policy_error"
                self.trace.record("policy_error", error="next_action must return AgentAction|None")
                break

            self._actions.append(action)
            execution.action = action
            self.trace.action(action.name, reason=action.reason, args=action.args)
            spec = self.registry.spec(action.name)
            if spec is None:
                observation = Observation(action.name, status="error", error=f"unknown_action:{action.name}")
                self._apply_observation(action, observation, execution)
                self._stop_reason = f"unknown_action:{action.name}"
                break
            execution.action_counts[action.name] = execution.action_counts.get(action.name, 0)
            decision = self.guardrails.check(action, spec, execution)
            if not decision.allowed:
                observation = Observation(
                    action.name, status=decision.status, error=decision.reason,
                )
                self._apply_observation(action, observation, execution)
                key = action.fingerprint()
                self._seen[key] = self._seen.get(key, 0) + 1
                if decision.reason.startswith("max_") or decision.reason == "deadline_exceeded":
                    self._stop_reason = decision.reason
                    break
                if self._seen[key] >= 3:
                    self._stop_reason = "no_progress"
                    break
                execution.step += 1
                continue
            if action.name == "stop":
                self._stop_reason = str(state.get("stop_reason") or "completed")
                self.trace.stop(self._stop_reason, reason=action.reason)
                break

            execution.action_counts[action.name] = execution.action_counts.get(action.name, 0) + 1
            context = self._context_for(action, execution)
            execution.context = context
            if context is not None:
                self.trace.record(
                    "context_view", action=action.name, withheld=context.withheld,
                    estimated_tokens=context.estimated_tokens,
                )
            observation = await self._execute_with_recovery(action, context, execution)
            self._apply_observation(action, observation, execution)
            if observation.status == "denied":
                execution.step += 1
                continue
            if observation.status == "error" and spec.critical:
                self._stop_reason = f"{action.name}_failed"
                break
            if self._stop_reason.startswith(("critical_action_failed",)):
                break
            key = action.fingerprint()
            if observation.ok:
                self._seen[key] = 0
            else:
                self._seen[key] = self._seen.get(key, 0) + 1
                if self._seen[key] >= 3:
                    self._stop_reason = "no_progress"
                    break
            subject = state.get("subject_state")
            if isinstance(subject, SubjectState):
                execution.subject_state = subject
                handoff = self._handoff(subject)
                state["handoff"] = handoff
                execution.handoff = handoff
            if spec.terminal:
                self._stop_reason = str(state.get("stop_reason") or "completed")
                break
            execution.step += 1

        if not self._stop_reason:
            self._stop_reason = "max_steps"
        finalized: dict[str, Any] | None = None
        if hasattr(policy, "finalize"):
            try:
                finalized = policy.finalize(state, self)
            except Exception as error:
                self.trace.record("finalize_failed", error=type(error).__name__)
        if isinstance(finalized, dict):
            state.update(finalized)
        answer = str(state.get("final_answer") or state.get("answer") or "")
        subject_payload = execution.subject_state.as_dict() if hasattr(execution.subject_state, "as_dict") else execution.subject_state
        state_payload = {
            key: value.as_dict() if isinstance(value, SubjectState) else value
            for key, value in state.items()
            if key not in {"subject_state"}
        }
        state_payload["subject"] = subject_payload
        result_payload = {
            "answer": answer,
            "stop_reason": self._stop_reason or "completed",
            "actions": [action.as_dict() for action in self._actions],
            "observations": [observation.as_dict() for observation in self._observations],
            "trace": self.trace.as_dict(),
            "budget": self.ledger.as_dict(),
            "state": state_payload,
            "checkpoint": self.checkpoint.as_dict(),
            "degraded": bool(self.ledger.degraded) or any(
                item.status not in {"ok", "denied"} for item in self._observations
            ),
        }
        self.trace.stop(self._stop_reason or "completed", step=execution.step)
        if persist:
            self._save_checkpoint(execution, status="completed", stop_reason=self._stop_reason)
        return HarnessResult(**result_payload)

    def _handoff(self, subject: SubjectState) -> dict[str, Any]:
        if self.handoff_builder is None:
            return {}
        try:
            return dict(self.handoff_builder(subject) or {})
        except Exception:
            return {}
