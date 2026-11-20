"""Laya typed-decision backend with explicit priority and safe rule fallback.

Laya is a non-generative typed-decision router: one forward pass returns
intent, recall needs and a response posture.  It is used for both quick and
deep StoryRole turns; the rule backend is reached only when Laya is disabled
or raises.  The router is process-global, lazy-built and serialized because
the CPU torch backend is not safe to call concurrently.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from .rule_backend import RuleDecisionBackend

logger = logging.getLogger(__name__)

_DEFAULT_REPO = "convaiinnovations/laya-multilingual"

# One typed-decision pass answers planning and the quick response posture.
_QUESTIONS: dict[str, dict[str, Any]] = {
    "intent": {
        "type": "choice",
        "instructions": "判断用户本轮主要意图",
        "criteria": {
            "daily_chat": "日常闲聊",
            "emotional_support": "情绪陪伴",
            "relationship_reflection": "关系和态度",
            "plot_or_fact": "小说事实",
            "value_reflection": "价值和选择",
            "future_probe": "未来或结局",
        },
    },
    "needs_novel_search": {
        "type": "noul",
        "instructions": "是否需要检索小说原文",
    },
    "needs_memory": {
        "type": "noul",
        "instructions": "是否需要用户历史记忆",
    },
    "needs_relationship": {
        "type": "noul",
        "instructions": "是否需要关系状态",
    },
    "needs_timeline_check": {
        "type": "noul",
        "instructions": "是否需要知识边界检查",
    },
    "auto_deep": {
        "type": "noul",
        "instructions": "这个问题是否需要深度分析而不是快速回应",
    },
    "response_action": {
        "type": "choice",
        "instructions": "角色现在最合适的回应动作",
        "criteria": {
            "自然回应": "保持自然，直接回应对方",
            "安慰": "先承接对方的情绪，给一点陪伴",
            "追问": "请对方说明具体指的是哪一段",
            "设边界": "温和但明确地保留角色自己的立场",
            "承认不知道": "没有足够回忆确认，承认不确定",
        },
    },
}

_ROUTER_BUILD_LOCK = threading.Lock()
_ROUTER_PREDICT_LOCK = threading.Lock()
_ROUTER: Any | None = None


def get_laya_router() -> Any:
    """Build the process-global Laya Router once, without downloading eagerly."""
    global _ROUTER
    if _ROUTER is not None:
        return _ROUTER
    with _ROUTER_BUILD_LOCK:
        if _ROUTER is None:
            from laya import Router

            device = os.getenv("STORYROLE_LAYA_DEVICE", "auto").strip() or "auto"
            kwargs: dict[str, Any] = {
                "max_loaded": max(1, int(os.getenv("STORYROLE_LAYA_MAX_LOADED", "1"))),
            }
            if device != "auto":
                kwargs["device"] = device
            repo = os.getenv("STORYROLE_LAYA_MODEL", "").strip()
            if repo and repo != _DEFAULT_REPO:
                kwargs["models"] = {"multilingual": repo}
                kwargs["default"] = "multilingual"
            _ROUTER = Router(**kwargs)
            logger.info("Laya Router created (device=%s, repo=%s)", device, repo or "default")
    return _ROUTER


def warmup_laya() -> dict[str, Any]:
    """Preload the multilingual checkpoint so the first quick turn is warm.

    The application calls this from a daemon thread at startup.  Failure is
    reported but never prevents the API from serving: the safe rule fallback
    remains available.
    """
    if os.getenv("STORYROLE_LAYA_WARMUP", "1").lower() in {"0", "false", "off", "no"}:
        return {"status": "disabled"}
    try:
        router = get_laya_router()
        names = [
            item.strip()
            for item in os.getenv("STORYROLE_LAYA_PRELOAD", "multilingual").split(",")
            if item.strip()
        ]
        with _ROUTER_PREDICT_LOCK:
            router.preload(names)
        logger.info("Laya warmup completed: %s", names)
        return {"status": "ready", "preloaded": names}
    except Exception as error:
        logger.warning("Laya warmup failed; rule fallback remains active: %s: %s", type(error).__name__, error)
        return {"status": "unavailable", "error": f"{type(error).__name__}: {error}"}


def _answer(answers: dict[str, Any], key: str) -> dict[str, Any]:
    value = answers.get(key)
    return value if isinstance(value, dict) else {}


def _choice(answers: dict[str, Any], key: str, default: str) -> str:
    value = _answer(answers, key).get("choice")
    return str(value) if value is not None else default


def _probability(answers: dict[str, Any], key: str, default: float = 0.0) -> float:
    answer = _answer(answers, key)
    value = answer.get("noul")
    if value is None:
        value = answer.get("probability")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _confidence(answers: dict[str, Any], key: str, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(_answer(answers, key).get("confidence"))))
    except (TypeError, ValueError):
        return default


class LayaDecisionBackend:
    """Typed decisions from Laya's multilingual checkpoint."""

    name = "laya"

    def __init__(self, router: Any | None = None) -> None:
        self.model_name = os.getenv("STORYROLE_LAYA_MODEL", _DEFAULT_REPO)
        self.device = os.getenv("STORYROLE_LAYA_DEVICE", "auto")
        self._router = router

    def _get_router(self) -> Any:
        return self._router if self._router is not None else get_laya_router()

    def plan(self, message: str) -> dict[str, Any]:
        message = str(message or "").strip()
        started = time.perf_counter()
        router = self._get_router()
        with _ROUTER_PREDICT_LOCK:
            result = router.predict({"body": message}, _QUESTIONS)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        if not isinstance(result, dict):
            raise ValueError("unsupported Laya result")
        answers = result.get("answers") or {}
        if not isinstance(answers, dict):
            raise ValueError("Laya result has no answers")

        intent = _choice(answers, "intent", "daily_chat")
        allowed = {
            "daily_chat", "emotional_support", "relationship_reflection",
            "plot_or_fact", "value_reflection", "future_probe",
        }
        if intent not in allowed:
            intent = "daily_chat"

        needs_novel_search = _probability(answers, "needs_novel_search") >= 0.5
        needs_memory = _probability(answers, "needs_memory") >= 0.5
        needs_relationship = _probability(answers, "needs_relationship") >= 0.5
        needs_timeline_check = _probability(answers, "needs_timeline_check") >= 0.5
        auto_deep = _probability(answers, "auto_deep") >= 0.5

        # Deterministic guards around typed decisions: a factual question
        # still recalls the novel, a relationship question still recalls the
        # relationship state, and a future/ending probe still checks the cut.
        if intent == "plot_or_fact":
            needs_novel_search = True
        if intent == "relationship_reflection":
            needs_relationship = True
            needs_memory = True
        if intent == "future_probe":
            needs_timeline_check = True
        if intent in {"value_reflection", "future_probe"}:
            auto_deep = True
        if len(message) > 120:
            auto_deep = True

        routing = result.get("routing") if isinstance(result.get("routing"), dict) else {}
        routing_model = str(routing.get("model") or result.get("model") or "multilingual")
        response_action = _choice(answers, "response_action", "自然回应")

        return {
            "intent": intent,
            "confidence": _confidence(answers, "intent"),
            "needs_novel_search": needs_novel_search,
            "needs_memory": needs_memory,
            "needs_relationship": needs_relationship,
            "needs_timeline_check": needs_timeline_check,
            "auto_deep": auto_deep,
            "answer_mode": "in_character_chat",
            "search_queries": [message],
            "future_probe": intent == "future_probe",
            "response_action": response_action,
            "planner_notes": f"Laya Router（{routing_model}）",
            "decision_backend": "laya",
            "laya_model": routing_model,
            "laya_routing": routing,
            "laya_elapsed_ms": elapsed_ms,
        }


class SafeLayaDecisionBackend:
    """Prefer Laya; use the deterministic rule plan only on failure."""

    def __init__(self, router: Any | None = None) -> None:
        self.laya = LayaDecisionBackend(router=router)
        self.rule = RuleDecisionBackend()

    def plan(self, message: str) -> dict[str, Any]:
        try:
            laya = self.laya.plan(message)
        except Exception as error:
            logger.warning("Laya unavailable, using rule fallback: %s: %s", type(error).__name__, error)
            rule = self.rule.plan(message)
            return {
                **rule,
                "decision_backend": "rule_fallback",
                "laya_error": f"{type(error).__name__}: {error}",
            }
        if os.getenv("STORYROLE_DECISION_BACKEND", "laya").lower() == "laya_shadow":
            rule = self.rule.plan(message)
            return {**rule, "decision_backend": "rule_shadow_laya", "laya_shadow": laya}
        return laya
