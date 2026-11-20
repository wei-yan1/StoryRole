"""Executable tool layer for the bounded agent harness.

The old `CapabilityRegistry` only listed capabilities. This module adds the
missing execution contract: a small schema, an explicit permission check, a
timeout, result distillation and provenance. It deliberately does not become a
general-purpose tool platform; the harness keeps a small allow-list.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ToolHandler = Callable[..., Any]
Distiller = Callable[[Any, dict[str, Any]], Any]
PermissionFn = Callable[[Any, dict[str, Any]], bool]


def _type_ok(value: Any, expected: str) -> bool:
    if expected in {"any", "object"}:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True


def validate_args(spec: "ToolSpec", args: dict[str, Any] | None) -> tuple[bool, str]:
    value = args or {}
    if not isinstance(value, dict):
        return False, "工具参数必须是对象"
    schema = spec.schema or {}
    if schema.get("type") not in {None, "object"}:
        return False, "工具 schema 顶层必须是 object"
    properties = schema.get("properties") or {}
    required = list(schema.get("required") or [])
    for key in required:
        if key not in value:
            return False, f"缺少参数：{key}"
        expected = str((properties.get(key) or {}).get("type") or "any")
        if not _type_ok(value[key], expected):
            return False, f"参数 {key} 类型应为 {expected}"
    for key, item in properties.items():
        if key not in value:
            continue
        expected = str((item or {}).get("type") or "any")
        if not _type_ok(value[key], expected):
            return False, f"参数 {key} 类型应为 {expected}"
    return True, ""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    purpose: str
    schema: dict[str, Any]
    handler: ToolHandler
    source: str = ""
    timeout_ms: int = 12000
    distiller: Distiller | None = None
    permission: PermissionFn | None = None
    permission_reason: str = "工具未授权"
    idempotent: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "source": self.source,
            "schema": self.schema,
            "timeout_ms": self.timeout_ms,
            "idempotent": bool(self.idempotent),
        }


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    actor: str = "policy"
    trace_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "args": dict(self.args),
            "actor": self.actor,
            "trace_id": self.trace_id,
        }


@dataclass
class ToolResult:
    name: str
    status: str
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    provenance: list[str] = field(default_factory=list)
    degraded: bool = False
    distilled: bool = False
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "duration_ms": round(float(self.duration_ms), 2),
            "provenance": list(self.provenance),
            "degraded": bool(self.degraded),
            "distilled": bool(self.distilled),
            "cached": bool(self.cached),
        }


class ToolRuntime:
    """Small allow-list executor; it owns validation, permission and timeout."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._idempotency: dict[str, ToolResult] = {}

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if spec.name in self._specs and not replace:
            raise ValueError(f"工具已注册：{spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def describe(self) -> list[dict[str, Any]]:
        return [self._specs[name].as_dict() for name in self.names()]

    async def call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        scope: Any = None,
        actor: str = "policy",
        trace_id: str = "",
        idempotency_key: str = "",
    ) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult(name=name, status="error", error="工具不存在")
        cache_key = ""
        if spec.idempotent:
            material = idempotency_key or json.dumps(
                args or {}, ensure_ascii=False, sort_keys=True, default=str,
            )
            digest = hashlib.sha1(f"{name}:{material}".encode("utf-8")).hexdigest()
            cache_key = f"{name}:{digest}"
        if cache_key and spec.idempotent and cache_key in self._idempotency:
            cached = self._idempotency[cache_key]
            return ToolResult(
                name=cached.name, status=cached.status, data=cached.data,
                error=cached.error, duration_ms=cached.duration_ms,
                provenance=list(cached.provenance), degraded=cached.degraded,
                distilled=cached.distilled, cached=True,
            )
        ok, reason = validate_args(spec, args)
        if not ok:
            return ToolResult(name=name, status="error", error=reason)
        if spec.permission is not None:
            try:
                allowed = bool(spec.permission(scope, args or {}))
            except Exception as error:
                return ToolResult(
                    name=name, status="denied",
                    error=f"权限检查失败：{type(error).__name__}",
                )
            if not allowed:
                return ToolResult(
                    name=name, status="denied", error=spec.permission_reason,
                )
        started = time.perf_counter()
        try:
            if inspect.iscoroutinefunction(spec.handler):
                raw = await asyncio.wait_for(
                    spec.handler(**(args or {})),
                    timeout=max(0.001, spec.timeout_ms / 1000),
                )
            else:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(spec.handler, **(args or {})),
                    timeout=max(0.001, spec.timeout_ms / 1000),
                )
        except asyncio.TimeoutError:
            return ToolResult(
                name=name, status="timeout",
                error=f"工具超时（{spec.timeout_ms}ms）",
                duration_ms=(time.perf_counter() - started) * 1000,
                degraded=True,
            )
        except Exception as error:
            return ToolResult(
                name=name, status="error",
                error=f"{type(error).__name__}: {error}",
                duration_ms=(time.perf_counter() - started) * 1000,
                degraded=True,
            )
        duration = (time.perf_counter() - started) * 1000
        data = raw
        distilled = False
        if spec.distiller is not None:
            try:
                data = spec.distiller(raw, args or {})
                distilled = True
            except Exception as error:
                return ToolResult(
                    name=name, status="error",
                    error=f"结果蒸馏失败：{type(error).__name__}: {error}",
                    duration_ms=duration, degraded=True,
                )
        provenance = [spec.source] if spec.source else []
        if isinstance(raw, dict):
            provenance.extend(str(item) for item in (raw.get("provenance") or []) if str(item))
        result = ToolResult(
            name=name, status="ok", data=data, duration_ms=duration,
            provenance=list(dict.fromkeys(provenance)), distilled=distilled,
        )
        if cache_key and spec.idempotent:
            self._idempotency[cache_key] = result
        return result

    async def call_many(
        self,
        calls: list[ToolCall],
        *,
        scope: Any = None,
    ) -> list[ToolResult]:
        """Run independent reads concurrently; a failure stays a local failure."""
        if not calls:
            return []
        return list(await asyncio.gather(*(
            self.call(call.name, call.args, scope=scope, actor=call.actor, trace_id=call.trace_id)
            for call in calls
        )))
