"""StoryRole Agent C: dynamic character conversation agent."""

from __future__ import annotations

from contextlib import nullcontext

import asyncio
import inspect
import json
import time
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.rag.embeddings.embedding_model import create_dashscope_embeddings
from app.rag.indexing.bm25_index import PersistentBM25Index
from app.rag.retrievers.hybrid_fusion_retriever import HybridFusionRetriever
from app.agents.decision.mode import normalize_mode
from app.schemas.auth import UserOut
from app.services.novel_import_service import novel_import_service
from app.observability import TraceContext, observe_async_call
from app.storage.repositories.storyrole_repository import (
    get_character,
    get_character_period,
    get_latest_period_analysis,
    get_novel,
    get_persona_profile_for_period,
    list_characters,
)


@lru_cache(maxsize=1)
def _memory_tool():
    from app.memory.tools import MemoryTool

    return MemoryTool()


@lru_cache(maxsize=1)
def _chat_model():
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        os.getenv("STORYROLE_CHAT_MODEL", os.getenv("TEST_CHAT_MODEL", "deepseek-v4.1-flash-1017")),
        model_provider="openai",
    )


@lru_cache(maxsize=32)
def _indexed_retriever(
    collection_name: str, persist_directory: str, bm25_path: str,
    rerank_enabled: bool = False, dense_filter_json: str = "",
):
    from langchain_chroma import Chroma

    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=create_dashscope_embeddings(),
        persist_directory=persist_directory,
    )
    return HybridFusionRetriever(
        vectorstore,
        dense_weight=0.65,
        sparse_weight=0.35,
        sparse_index=PersistentBM25Index(bm25_path) if Path(bm25_path).exists() else None,
        rerank_enabled=rerank_enabled,
        dense_filter=json.loads(dense_filter_json) if dense_filter_json else None,
    )


class CharacterConversationAgent:
    agent_id = "character-conversation"

    async def reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        started_at = time.perf_counter()
        trace = TraceContext(
            trace_id=str(payload.get("trace_id") or __import__("uuid").uuid4().hex),
            run_type="storyrole_chat",
            metadata={"owner_id": int(payload.get("owner_id")), "novel_id": payload.get("novel_id"), "character_id": payload.get("character_id")},
        )
        trace.start()
        payload = {**payload, "trace_id": trace.trace_id}
        from app.services.chat_context_compaction import prepare_history
        prepared_history = await prepare_history(
            thread_id=int((payload.get("thread") or {}).get("id") or 0),
            fallback_messages=list(payload.get("recent_messages") or []),
            trace_id=trace.trace_id,
        ) if (payload.get("thread") or {}).get("id") else None
        if prepared_history is not None:
            payload = {
                **payload,
                "recent_messages": prepared_history.messages,
                "history_summary": prepared_history.summary,
            }
        owner_id = int(payload["owner_id"])
        novel_id = str(payload["novel_id"])
        character_id = int(payload["character_id"])
        message = str(payload["message"]).strip()
        period_id = int(payload["period_id"]) if payload.get("period_id") is not None else None
        with trace.step("profile_load"):
            profile_row = get_persona_profile_for_period(
                character_id=character_id, owner_id=owner_id, period_id=period_id
            )
            if not profile_row:
                raise ValueError("角色尚未完成女娲画像分析")
            period = get_character_period(period_id=period_id, owner_id=owner_id) if period_id else None
            character = get_character(character_id=character_id, owner_id=owner_id)
        if not character or character["novel_id"] != novel_id:
            raise ValueError("角色不存在或不属于当前小说")
        profile = profile_row["profile"]
        profile_evidence = profile_row.get("evidence", [])
        from app.rag.rolerag.persona.contract import build_persona_contract

        # Nuwa owns "who this person is"; RoleRAG owns "what he may know".
        contract_profile = {
            **profile,
            "period_name": profile.get("period_name") or (period or {}).get("name") or "",
            "period_stage": profile.get("period_stage") or (period or {}).get("timeline_stage") or "",
        }
        persona_contract = build_persona_contract(contract_profile)
        persona_contract_text = persona_contract.render()

        # All modes run through the same v3 AgentHarness. `mode` only selects
        # the quick/deep policy branch; there is no legacy fallback path.
        requested_mode = normalize_mode(
            payload.get("mode"), legacy_deep_reasoning=bool(payload.get("deep_reasoning"))
        )
        from app.agents.storyrole.harness.turn import run_harness_turn

        return await run_harness_turn(
            self, payload, trace=trace,
            identity={
                "owner_id": owner_id, "novel_id": novel_id,
                "character_id": character_id, "period_id": period_id,
                "character": character, "profile_row": profile_row,
                "profile": profile, "profile_evidence": profile_evidence,
                "period": period, "persona_contract": persona_contract,
                "persona_contract_text": persona_contract_text,
                "message": message, "requested_mode": requested_mode,
            },
        )

    @staticmethod
    def _record_evidence_graph(
        *, trace_id: str, message: str, profile: dict[str, Any],
        period_id: int | None, evidence: list[dict[str, Any]], answer: str,
    ) -> None:
        try:
            from app.observability.evidence_graph import EvidenceGraph

            graph = EvidenceGraph(trace_id)
            question = graph.add_node("question", content=message)
            profile_node = graph.add_node(
                "period_profile", str(period_id) if period_id is not None else "full",
                content=json.dumps(profile, ensure_ascii=False),
                metadata={"period_id": period_id},
            )
            answer_node = graph.add_node("final_answer", content=answer)
            graph.add_edge(answer_node, question, "answers")
            graph.add_edge(answer_node, profile_node, "constrained_by")
            graph.add_evidence(evidence[:24], target_node=answer_node)
        except Exception:
            # Observability must never make a successful answer fail.
            return

    async def _persist_memory_candidate_async(
        self, payload: dict[str, Any], character: dict[str, Any], message: str,
        answer: str, decision: dict[str, Any],
    ) -> None:
        await asyncio.to_thread(
            self._persist_memory_candidate, payload, character, message, answer, decision
        )

    @staticmethod
    def _log_background_failure(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            # The request/test client may close the loop before a fire-and-forget
            # persistence task finishes; that is shutdown, not a data failure.
            return
        except Exception as error:
            import logging
            logging.getLogger(__name__).warning("StoryRole background update failed: %s", type(error).__name__)

    @staticmethod
    async def _await_optional(task: Any, fallback: dict[str, Any], kernel: Any = None) -> dict[str, Any] | None:
        if task is None:
            return fallback
        try:
            timeout = min(10.0, max(0.01, kernel.remaining_seconds())) if kernel is not None else 10.0
            return await asyncio.wait_for(task, timeout=timeout)
        except Exception:
            if kernel is not None and kernel.deadline_exceeded():
                kernel.note_deadline()
            return None

    @staticmethod
    def _unwrap_fallback(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if value.get("_fallback_used"):
            return dict(value.get("_fallback_value") or {}), True
        return value, False

    @staticmethod
    def _deadline_reply(character_name: str, appraisal: Any) -> str:
        action = getattr(appraisal, "action", "") or "natural_reply"
        replies = {
            "hold_boundary": "这件事，我不答应。",
            "comfort": "先坐一会儿。我在这儿，不急着说。",
            "probe": "这一段我没有看清。你想问的是哪一件事？",
            "uncertain": "这不能算我确定记得的事，我不把它说成答案。",
            "answer": "让我按真正记得的说。眼下，我只能先说到这里。",
            "natural_reply": "我在。只是这一刻，我得先想一想。",
        }
        return replies.get(action, replies["natural_reply"])

    @staticmethod
    def _deadline_fallback(agent_id: str) -> dict[str, Any]:
        if agent_id in {"role-cognition", "character-reasoning"}:
            return {
                "response_action": "",
                "value_judgment": "",
                "decision_backend": "deadline_fallback",
            }
        if agent_id == "evidence-analysis":
            return {"used_chunks": [], "cognitive_summary": "", "emotional_summary": "", "analysis": ""}
        return {}

    @staticmethod
    async def _dispatch_timeout(
        a2a_client: Any, agent_id: str, payload: dict[str, Any], *,
        timeout: float, fallback: Any, kernel: Any = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if kernel is not None and kernel.remaining_seconds() <= 0:
            kernel.note_deadline()
            value = CharacterConversationAgent._deadline_fallback(agent_id) if callable(fallback) else fallback
            return {"_fallback_used": True, "_fallback_value": value}
        effective_timeout = timeout
        if kernel is not None:
            effective_timeout = min(timeout, max(0.01, kernel.remaining_seconds()))
        try:
            result = await asyncio.wait_for(a2a_client.send(agent_id, payload), timeout=effective_timeout)
            if kernel is not None:
                kernel.record_tool_call(
                    name=agent_id,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            return result
        except Exception:
            try:
                if kernel is not None and kernel.remaining_seconds() <= 0:
                    raise asyncio.TimeoutError
                value = fallback() if callable(fallback) else fallback
                if inspect.isawaitable(value):
                    if kernel is not None:
                        value = await asyncio.wait_for(
                            value,
                            timeout=max(0.01, kernel.remaining_seconds()),
                        )
                    else:
                        value = await value
            except Exception:
                value = CharacterConversationAgent._deadline_fallback(agent_id) if callable(fallback) else fallback
                if kernel is not None:
                    kernel.note_deadline()
            if kernel is not None:
                kernel.record_tool_call(
                    name=agent_id,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    degraded=True,
                )
            return {"_fallback_used": True, "_fallback_value": value}

    async def _run_agent(
        self, *, novel_id: str, owner_id: int, character_name: str,
        profile: dict[str, Any], evidence: list[dict[str, Any]], message: str,
        recent_messages: list[dict[str, Any]], plan: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None, reasoning: dict[str, Any] | None = None,
        period_id: int | None = None, mode: str = "quick", trace_id: str | None = None,
        generation_state: dict[str, bool] | None = None, history_summary: str = "",
        persona_contract: str = "",
        context_manifest: Any = None, appraisal: Any = None,
        kernel: Any = None,
    ) -> str:
        generation_state = generation_state if generation_state is not None else {"degraded": False}
        if kernel is not None and kernel.deadline_exceeded():
            kernel.note_deadline()
            generation_state["degraded"] = True
            return self._deadline_reply(character_name, appraisal)
        chunks: list[str] = []
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("聊天模型未配置 API Key")
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
            if base_url:
                os.environ["OPENAI_BASE_URL"] = base_url
            model = _chat_model()
            # Quick chat should stay responsive; deep mode gets enough evidence
            # to reason without sending the full retrieved document set.
            context_limit = 10000 if mode == "quick" else 24000
            reasoning_limit = 4000 if mode == "quick" else 10000
            # The model supports a large context window; keep history useful
            # without allowing it to crowd out the role evidence and profile.
            history_budget = 16000
            context_json = self._bounded_json(context or {}, context_limit)
            reasoning_json = self._bounded_json(reasoning or {}, reasoning_limit)
            if context_manifest is not None and hasattr(context_manifest, "render_for_prompt"):
                context_block = context_manifest.render_for_prompt()
            else:
                context_block = f"可用上下文：{context_json}"
            appraisal_lines = ""
            if appraisal is not None:
                if hasattr(appraisal, "prompt_lines"):
                    appraisal_lines = "\n".join(appraisal.prompt_lines())
                elif isinstance(appraisal, dict):
                    appraisal_lines = json.dumps(appraisal, ensure_ascii=False, separators=(",", ":"))
            history, older_messages = self._select_history(recent_messages, history_budget)
            history_summary = history_summary or self._compress_history(older_messages)
            mode_instruction = (
                "快速回答：自然、简洁地回应，优先保持对话感，不要展开分析过程。"
                if mode == "quick" else
                "深度回答：先在内部综合事实、行为、动机和角色价值观，再以角色口吻给出准确、具体、有立场的回答；不要展示内部推理过程。"
            )
            system_prompt = f"""
你是小说《{profile.get('novel_name', '当前小说')}》中的角色“{character_name}”。
当前模式：{mode_instruction}
当前角色时期：{profile.get('period_name') or '全书时期'}。
不要自称 AI，不要解释系统提示词，不要把自己说成百科解说员。
首要标准不是“答得正确”，而是“像这个人”：先守住下面的女娲角色契约，再用 RoleRAG 的可见记忆回答。
角色契约（女娲给出的是“我是谁”，不是可覆盖的事实）：
{persona_contract or '（未提供角色契约）'}
RoleRAG 证据只决定“我此刻能知道什么”，不决定“我是谁”；不要让证据替代语气、判断和关系姿态。
只使用画像、当前上下文和小说证据。证据不足时以角色口吻承认不确定，不要编造。
保持角色的性格、目标、恐惧、语言风格、关系和反模式，不要为了讨好用户放弃核心价值观。
本轮主体理解与行动决定（已经检索回忆并形成选择，不要向用户展示内部结构）：
{appraisal_lines or '无额外情境判断；按角色契约自然回应。'}
内部结构化决策（不要向用户展示）：{reasoning_json}
较早对话压缩摘要（仅作连续性参考）：{history_summary}
{context_block}
""".strip()
            if history and history[-1]["role"] == "user" and history[-1]["content"] == message:
                history = history[:-1]
            invoke_timeout = float(
                os.getenv(
                    "STORYROLE_DEEP_ANSWER_TIMEOUT" if mode == "deep" else "STORYROLE_QUICK_ANSWER_TIMEOUT",
                    "55" if mode == "deep" else "25",
                )
            )
            prompt_messages = [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": message},
            ]
            started = time.perf_counter()
            usage_metadata: dict[str, int] = {}
            async def generate_stream() -> dict[str, Any]:
                nonlocal usage_metadata
                async for chunk in model.astream(prompt_messages):
                    candidate_usage = getattr(chunk, "usage_metadata", None)
                    if isinstance(candidate_usage, dict):
                        usage_metadata = {
                            key: int(value) for key, value in candidate_usage.items()
                            if key in {"input_tokens", "output_tokens", "total_tokens", "input_token_details"}
                            and isinstance(value, (int, float))
                        }
                    content = chunk.content if hasattr(chunk, "content") else chunk
                    if isinstance(content, list):
                        text = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
                    else:
                        text = str(content or "")
                    if text:
                        chunks.append(text)
                        from app.agents.storyrole.streaming import publish_answer_token
                        publish_answer_token(trace_id, text)
                return {"text": "".join(chunks), "usage_metadata": usage_metadata}

            generation = await asyncio.wait_for(
                observe_async_call(
                    generate_stream,
                    operation="storyrole_answer_generation",
                    trace_id=trace_id,
                    model=model,
                    prompt=system_prompt + "\n" + message,
                ),
                timeout=max(0.01, min(invoke_timeout, kernel.remaining_seconds())) if kernel is not None else max(1.0, invoke_timeout),
            )
            normalized = str(generation.get("text") or "").strip()
            if not normalized:
                raise RuntimeError("聊天模型返回了空回答")
            if mode == "deep":
                import logging
                logging.getLogger("storyrole.deep").info(
                    "answer stream completed trace_id=%s output_chars=%d duration_ms=%.1f",
                    trace_id, len(normalized), (time.perf_counter() - started) * 1000,
                )
            if kernel is not None:
                kernel.record_model_call(
                    stage="express",
                    model=str(getattr(model, "model_name", "") or os.getenv(
                        "STORYROLE_CHAT_MODEL", "deepseek-v4.1-flash-1017"
                    )),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    output_chars=len(normalized),
                    usage=usage_metadata,
                )
            return normalized
        except Exception:
            generation_state["degraded"] = True
            if kernel is not None:
                kernel.record_model_call(
                    stage="express",
                    model=str(getattr(locals().get("model"), "model_name", "") or "unknown"),
                    duration_ms=(time.perf_counter() - started) * 1000 if "started" in locals() else 0.0,
                    output_chars=len("".join(chunks)),
                    degraded=True,
                )
            if chunks:
                from app.agents.storyrole.streaming import reset_answer_stream
                reset_answer_stream(trace_id)
            raise

    @staticmethod
    def _bounded_json(value: Any, limit: int) -> str:
        """Serialize context within a valid JSON character budget."""
        data = json.loads(json.dumps(value, ensure_ascii=False, default=str))
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= limit:
            return text

        # Retrieval lists are the largest and least important parts to send in
        # full. Drop their tail first, preserving the profile and instructions.
        if isinstance(data, dict):
            for key in ("novel_evidence", "evidence", "web_evidence", "memories", "recent_messages"):
                items = data.get(key)
                if not isinstance(items, list):
                    continue
                while items and len(text) > limit:
                    items.pop()
                    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                if len(text) <= limit:
                    return text

            # A single oversized field should still not create malformed JSON.
            for key, item in list(data.items()):
                if isinstance(item, str) and len(text) > limit:
                    data[key] = item[: max(256, limit // 4)]
                    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                    if len(text) <= limit:
                        return text

        # Keep the payload valid even when one scalar field is unusually large.
        return json.dumps({"truncated_context": text[: max(0, limit - 32)]}, ensure_ascii=False)

    @staticmethod
    def _compress_history(messages: list[dict[str, Any]]) -> str:
        """Keep a small deterministic summary without spending another LLM call."""
        if not messages:
            return "无较早对话。"
        lines: list[str] = []
        for item in messages:
            role = "用户" if item.get("role") == "user" else "角色"
            content = " ".join(str(item.get("content") or "").split())
            if content:
                lines.append(f"{role}：{content[:180]}")
        summary = "；".join(lines)
        return summary[:3000] or "无较早对话。"

    @staticmethod
    def _estimate_tokens(value: str) -> int:
        """Conservative token estimate for mixed Chinese and Latin text."""
        chinese = sum("\u3400" <= char <= "\u9fff" for char in value)
        other = len(value) - chinese
        return max(1, chinese + (other + 3) // 4)

    @classmethod
    def _select_history(
        cls, messages: list[dict[str, Any]], budget: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Select at most ten newest messages while respecting a token budget."""
        valid = [
            {"role": item.get("role"), "content": str(item.get("content") or "")}
            for item in messages
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        selected: list[dict[str, Any]] = []
        used = 0
        selected_indexes: set[int] = set()
        for index in range(len(valid) - 1, -1, -1):
            item = valid[index]
            item_tokens = cls._estimate_tokens(item["content"]) + 4
            if selected and (len(selected) >= 10 or used + item_tokens > budget):
                break
            if not selected and item_tokens > budget:
                # Keep the newest turn usable even when it is unusually long.
                max_chars = max(256, budget * 2)
                item = {**item, "content": item["content"][:max_chars]}
                item_tokens = cls._estimate_tokens(item["content"]) + 4
            selected.insert(0, item)
            selected_indexes.add(index)
            used += item_tokens
        older = [item for index, item in enumerate(valid) if index not in selected_indexes]
        return selected, older

    def _search_chunks(
        self, novel_id: str, owner_id: int, query: str, character_name: str,
        *, period_id: int | None = None, k: int = 6, rerank: bool = False,
        trace_id: str | None = None,
    ) -> str:
        manifest, index_info = self._resolve_novel_index(novel_id, owner_id)
        try:
            retriever = _indexed_retriever(
                str(index_info["collection_name"]),
                str(index_info["vector_index_path"]),
                str(index_info["bm25_index_path"]),
                rerank,
                json.dumps(index_info.get("dense_filter") or {}, sort_keys=True),
            )
            period = get_character_period(period_id=period_id, owner_id=owner_id) if period_id else None
            if period_id and not period:
                return "[]"
            retrieval_filter = None
            scoped_query = query
            if period:
                ids = [str(value) for value in (period.get("evidence_ids") or []) if str(value)]
                if not ids and period_id:
                    period_profile = get_persona_profile_for_period(
                        character_id=int(period["character_id"]), owner_id=owner_id, period_id=period_id
                    )
                    ids = [str(item.get("chunk_id")) for item in (period_profile or {}).get("evidence", []) if item.get("chunk_id")]
                if not ids:
                    return "[]"
                retrieval_filter = {"chunk_id": {"$in": ids}}
                keywords = [str(value) for value in (period.get("keywords") or []) if str(value)]
                if keywords:
                    scoped_query = f"{query} {' '.join(keywords[:4])}"
            documents = retriever.retrieve(
                scoped_query, k=max(1, min(k, 12)), filter=retrieval_filter
            )
            return json.dumps(
                [
                    {
                        "chapter": str(document.metadata.get("section_title", "未知章节")),
                        "chunk_id": document.metadata.get("chunk_id"),
                        "text": document.page_content[:1600],
                        "retrieval": {
                            "fusion": document.metadata.get("fusion_score", 0.0),
                            "rerank": document.metadata.get("rerank_score", 0.0),
                        },
                    }
                    for document in documents
                ],
                ensure_ascii=False,
            )
        except Exception:
            if manifest.get("chunks_path"):
                return self._fallback_search_chunks(manifest, query, character_name)
            return "[]"

    @staticmethod
    def _resolve_novel_index(novel_id: str, owner_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        """Resolve a user-import index first, then the bundled Three-Body indexes."""
        try:
            manifest = novel_import_service.get_job(novel_id, owner_id=owner_id)
            index_info = manifest.get("index") or {}
            if index_info.get("collection_name"):
                return manifest, index_info
        except (FileNotFoundError, PermissionError):
            pass

        workspace = get_novel(novel_id=novel_id, owner_id=owner_id)
        if workspace and workspace.get("source_kind") == "bundled":
            from app.rag.retrievers.novel_vector_retriever import (
                DEFAULT_CHROMA_DIR, NOVEL_COLLECTION,
            )
            bm25_path = DEFAULT_CHROMA_DIR.parent / "bm25" / f"{NOVEL_COLLECTION}.json"
            if bm25_path.exists():
                bm25_index_path = str(bm25_path)
            else:
                from app.rag.indexing.bm25_index import PersistentBM25Index
                from langchain_core.documents import Document
                import json
                from pathlib import Path

                chunks_path = Path(str(workspace.get("chunks_path") or ""))
                index = PersistentBM25Index(bm25_path)
                if not index.records and chunks_path.exists():
                    docs = []
                    for line in chunks_path.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        record = json.loads(line)
                        metadata = dict(record.get("metadata") or {})
                        docs.append(Document(page_content=str(record.get("text") or ""), metadata=metadata))
                    index.replace_documents(docs)
                bm25_index_path = str(bm25_path)
            return {"novel_name": workspace.get("name"), "chunks_path": workspace.get("chunks_path")}, {
                "collection_name": NOVEL_COLLECTION,
                "vector_index_path": str(DEFAULT_CHROMA_DIR),
                "bm25_index_path": bm25_index_path,
                "dense_filter": {"source_id": "three_body_txt_local"},
            }
        raise FileNotFoundError(f"小说检索索引不存在：{novel_id}")

    @staticmethod
    def _load_memories(payload: dict[str, Any], *, character_name: str) -> list[dict[str, Any]]:
        user_data = payload.get("user") or {}
        thread = payload.get("thread") or {}
        if not user_data.get("id") or not user_data.get("username"):
            return []
        try:
            result = _memory_tool().search_items(
                query=str(payload.get("message") or ""),
                user=UserOut(**user_data),
                character=character_name,
                timeline_stage="dynamic",
                mode="storyrole",
                thread_name=str(thread.get("thread_name") or "线程1"),
                limit=5,
                min_importance=0.15,
            )
            return [
                {"id": item.id, "content": item.content, "importance": item.importance, "score": item.score}
                for item in result.items
            ]
        except Exception:
            return []

    @staticmethod
    def _persist_memory_candidate(
        payload: dict[str, Any], character: dict[str, Any], message: str,
        answer: str, decision: dict[str, Any],
    ) -> None:
        if not decision.get("requires_confirmation"):
            return
        user_data = payload.get("user") or {}
        thread = payload.get("thread") or {}
        if not user_data.get("id") or not user_data.get("username"):
            return
        try:
            from app.storage.repositories.storyrole_repository import create_memory_candidate
            create_memory_candidate(
                novel_id=str(payload["novel_id"]), character_id=int(payload["character_id"]),
                owner_id=int(user_data["id"]), thread_id=int(thread["id"]) if thread.get("id") else None,
                thread_name=str(thread.get("thread_name") or "线程1"),
                memory_type=str(decision.get("memory_type", "user_preference")),
                content=f"用户：{message}\n角色：{answer}",
                summary=str(decision.get("content") or message)[:300],
                importance=float(decision.get("importance", 0.75)),
                reason=str(decision.get("reason") or "待确认的长期记忆候选"),
            )
        except Exception:
            return

    async def _update_relationship(
        self, a2a_client: Any, payload: dict[str, Any], *, character_id: int,
        novel_id: str, owner_id: int, message: str, final_answer: str,
    ) -> None:
        # Relationship state is intentionally conservative: only explicit cues
        # change trust/intimacy; ordinary turns keep the previous state.
        try:
            current = await self._dispatch(a2a_client, "relationship-state", {
                "profile": {}, "character_id": character_id, "owner_id": owner_id,
                "trace_id": payload.get("trace_id"),
            })
            state = current.get("user_relationship") or {}
            trust = float(state.get("trust", 0.5))
            intimacy = float(state.get("intimacy", 0.0))
            positive = any(token in message for token in ("谢谢", "相信你", "理解你", "记住我"))
            negative = any(token in message for token in ("骗我", "不信你", "讨厌你"))
            trust_delta = 0.01 if positive else -0.01 if negative else 0.0
            intimacy_delta = 0.005 if positive else 0.0
            tension_delta = 0.01 if negative else 0.0
            if not positive and not negative:
                return
            relationship_state = dict(state.get("state") or {})
            turns = list(relationship_state.get("recent_turns") or [])
            turns.append({"message": message[:120], "answer": final_answer[:180]})
            relationship_state["recent_turns"] = turns[-10:]
            evidence = list(state.get("evidence") or [])
            evidence.append({"source": "conversation_turn", "message": message[:120]})
            await self._dispatch(a2a_client, "relationship-update", {
                "character_id": character_id, "novel_id": novel_id, "owner_id": owner_id,
                "trace_id": payload.get("trace_id"),
                "trust": max(0.0, min(1.0, trust + trust_delta)),
                "intimacy": max(0.0, min(1.0, intimacy + intimacy_delta)),
                "tension": max(0.0, min(1.0, float(state.get("tension", 0.0)) + tension_delta)),
                "dependency": float(state.get("dependency", 0.0)),
                "state": relationship_state,
                "evidence": evidence[-20:],
            })
        except Exception:
            return

    def rerank_evidence(
        self, *, novel_id: str, owner_id: int, query: str, character_name: str,
        period_id: int | None, evidence: list[dict[str, Any]], limit: int,
    ) -> list[dict[str, Any]]:
        if not evidence:
            return []
        try:
            _manifest, index_info = self._resolve_novel_index(novel_id, owner_id)
            retriever = _indexed_retriever(
                str(index_info["collection_name"]), str(index_info["vector_index_path"]),
                str(index_info["bm25_index_path"]), True,
            )
            docs = []
            from langchain_core.documents import Document
            for item in evidence:
                doc = Document(
                    page_content=str(item.get("text") or ""),
                    metadata={"chunk_id": str(item.get("chunk_id") or ""), **dict(item)},
                )
                docs.append(doc)
            ranked = retriever.rerank_documents(query, docs, top_k=limit)
            return [
                {**dict(doc.metadata), "chapter": doc.metadata.get("chapter", "未知章节"),
                 "chunk_id": doc.metadata.get("chunk_id"), "text": doc.page_content}
                for doc in ranked
            ]
        except Exception:
            return evidence[:limit]

    def search_evidence(
        self, *, novel_id: str, owner_id: int, query: str, character_name: str,
        period_id: int | None = None, k: int = 6, rerank: bool = False,
    ) -> list[dict[str, Any]]:
        raw = self._search_chunks(
            novel_id, owner_id, query, character_name, period_id=period_id, k=k, rerank=rerank
        )
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _merge_evidence(results: list[list[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for batch in results:
            for item in batch:
                chunk_id = str(item.get("chunk_id") or "")
                key = chunk_id or f"{item.get('chapter')}:{item.get('text', '')[:80]}"
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= limit:
                    return merged
        return merged

    @staticmethod
    async def _dispatch(a2a_client: Any, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await a2a_client.send(agent_id, payload)

    @staticmethod
    def _fallback_search_chunks(manifest: dict[str, Any], query: str, character_name: str) -> str:
        terms = [term for term in query.strip().split() if term] or [query.strip()]
        hits: list[tuple[int, dict[str, Any]]] = []
        with Path(manifest["chunks_path"]).open("r", encoding="utf-8") as file:
            for record in file:
                if not record.strip():
                    continue
                item = json.loads(record)
                text = str(item.get("text") or "")
                score = sum(text.count(term) for term in terms) + (2 if character_name in text else 0)
                if score:
                    hits.append((score, item))
        hits.sort(key=lambda pair: pair[0], reverse=True)
        return json.dumps(
            [
                {
                    "chapter": (item.get("metadata") or {}).get("section_title", "未知章节"),
                    "chunk_id": item.get("chunk_id"),
                    "text": str(item.get("text") or "")[:1200],
                }
                for _score, item in hits[:6]
            ],
            ensure_ascii=False,
        )

    @staticmethod
    def _fallback_reply(character_name: str, profile: dict[str, Any], message: str) -> str:
        style = "、".join(str(item) for item in profile.get("speech_style", [])[:2]) or "克制"
        personality = "、".join(str(item) for item in profile.get("personality", [])[:2]) or "复杂"
        return f"{character_name}（{style}）暂时无法把这件事说得更确定。就目前的了解，我会以{personality}的方式看待“{message}”，但还需要更多原文证据。"


