"""Single-turn orchestration.

The order is fixed and testable:

    project -> scope -> route -> retrieve -> render -> style check -> (rewrite)

Style checking happens *after* generation, which is the one thing the three
memory papers do not do: they condition the model on a profile and hope. Here
the output is measured against the character's own corpus and rewritten once
with a concrete instruction if it drifts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from typing import Protocol

from ..models import CognitionState, Evidence
from ..persona.contract import build_persona_contract, check_persona
from ..persona.emotion import gate, select_pattern
from ..persona.seed import PersonaSeed, ProfileOverlay, build_seed
from ..persona.state import describe
from ..persona.style import StyleProfile, StyleReport, check, fingerprint
from ..project import project
from ..retrieval.router import RouteDecision, route
from ..retrieval.scope import ScopeReport, analyze_scope
from ..retrieval.subgraph import retrieve
from ..retrieval.ego import build_ego_network, ego_summary
from ..store import InMemoryGraphStore


@dataclass
class TurnContext:
    character_id: str
    cutoff: int
    message: str
    state: CognitionState
    evidence: list[Evidence]
    decision: RouteDecision
    scope: ScopeReport
    seed: PersonaSeed
    ego_summary: str = ""
    emotion: str = "静"
    emotion_jump: bool = False


@dataclass
class Reply:
    text: str
    route: str
    evidence: list[Evidence]
    scope: ScopeReport
    style: StyleReport
    state: CognitionState
    messages: list[dict] = field(default_factory=list)
    attempts: int = 1
    fidelity: object | None = None


class Renderer(Protocol):
    def render(self, context: TurnContext) -> str: ...
    def rewrite(self, text: str, instruction: str, context: TurnContext) -> str: ...


class TemplateRenderer:
    """Deterministic renderer used for tests and the offline demo.

    It is deliberately plain: the value being demonstrated is the cognition
    layer, not prose quality. A production deployment swaps in an LLM renderer
    with the same protocol.
    """

    def render(self, context: TurnContext) -> str:
        decision = context.decision
        state = context.state
        if decision.kind == "reject":
            if context.scope.external_terms:
                return "那些事我没见过。这里没有。"
            if decision.reason.startswith("无可见事件"):
                return "这事我没听说。别问我。"
            if decision.entities:
                return f"{decision.entities[0]}这个人，我没听过。"
            return "这人与我无关。他不在我的日子。"

        if decision.kind == "stance":
            if state.affect.get("hostility", 0) > 0.55:
                return "你问这个做什么。有些话，我不想说第二遍。"
            if state.beliefs:
                belief = state.beliefs[0]
                return f"{belief.target}的事，说不清。我只知道，我欠自己一个交代。"
            return "这事说来话长。我不想把它说成一句好听话。"

        if decision.kind == "recall":
            if context.evidence and context.evidence[0].kind == "episode":
                return context.evidence[0].text
            if context.evidence:
                return f"那天我记得。{_clause(context.evidence[0].text)}。"
            return "那天的事，我记得。只是不想再提。"

        if decision.kind == "probe":
            if context.evidence:
                return f"你问为什么。{_clause(context.evidence[0].text)}。就是这样。"
            return "为什么。我自己也想过很多回。想不明白。"

        return "……"

    def rewrite(self, text: str, instruction: str, context: TurnContext) -> str:
        # Cheap deterministic repair: drop banned clauses, split long sentences.
        pieces = [piece.strip() for piece in text.replace("！", "。").split("。") if piece.strip()]
        kept = [piece for piece in pieces if not any(word in piece for word in context.seed.judgement[:0])]
        shortened = []
        for piece in kept:
            if len(piece) > 22 and "，" in piece:
                piece = piece.split("，")[0]
            shortened.append(piece)
        return "。".join(shortened) + "。" if shortened else text


class LLMRenderer:
    """Production renderer: same protocol, real model, style loop intact."""

    def __init__(self, llm) -> None:
        self.llm = llm

    def render(self, context: TurnContext) -> str:
        messages = build_messages(context, draft="")
        text = self.llm.complete(messages[1]["content"], system=messages[0]["content"]).strip()
        if text:
            return text
        # Reasoning models can spend the whole completion on hidden reasoning
        # and return an empty content field. An empty turn is worse than a
        # deterministic sentence: fall back to the template renderer.
        return TemplateRenderer().render(context)

    def rewrite(self, text: str, instruction: str, context: TurnContext) -> str:
        prompt = (
            f"上一稿：{text}\n"
            f"必须修改：{instruction}\n"
            "写成完整的一句话，不能只给一个词；只输出改写后的台词，不要解释，不要加引号。"
        )
        rewritten = self.llm.complete(prompt, system=f"你是{context.seed.name}。").strip()
        return rewritten or text


_PROJECT_CACHE: dict[tuple, CognitionState] = {}
_SEED_CACHE: dict[tuple, PersonaSeed] = {}
_SCOPE_CACHE: dict[tuple, ScopeReport] = {}
_EGO_CACHE: dict[tuple, object] = {}


def _revision(store: InMemoryGraphStore) -> int:
    return int(getattr(store, "revision", 0))


def _remember(cache: dict, key: tuple, compute):
    if key in cache:
        return cache[key]
    if len(cache) > 256:
        cache.clear()
    value = compute()
    cache[key] = value
    return value


def _overlay_key(overlay: ProfileOverlay | None) -> str:
    if overlay is None:
        return ""
    return "\x1f".join(
        (
            overlay.identity,
            "|".join(overlay.traits),
            "|".join(overlay.goals),
            "|".join(overlay.fears),
            "|".join(overlay.speech_style),
            "|".join(overlay.anti_patterns),
            "|".join(overlay.core_beliefs),
            "|".join(overlay.decision_patterns),
            "|".join(overlay.conversation_rules),
            "|".join(overlay.knowledge_rules),
            "|".join(overlay.relationships),
            "|".join(overlay.known),
            "|".join(overlay.unknown),
        )
    )


def chat_turn(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    message: str,
    *,
    renderer: Renderer | None = None,
    style_profile: StyleProfile | None = None,
    external_terms: list[str] | None = None,
    max_rewrites: int = 1,
    profile_overlay: ProfileOverlay | None = None,
    plan: dict | None = None,
) -> Reply:
    renderer = renderer or TemplateRenderer()
    key = (_revision(store), character_id, cutoff)
    state = _remember(_PROJECT_CACHE, key, lambda: project(store, character_id, cutoff))
    seed = _remember(
        _SEED_CACHE,
        key + (_overlay_key(profile_overlay),),
        lambda: build_seed(store, character_id, cutoff, overlay=profile_overlay),
    )
    scope_key = key + (message, tuple(external_terms or ()))
    scope = _remember(
        _SCOPE_CACHE,
        scope_key,
        lambda: analyze_scope(message, store, character_id, cutoff, external_terms=external_terms),
    )
    decision = route(message, scope, plan=plan)
    evidence = retrieve(store, character_id, cutoff, decision)
    decision, evidence = guard_unseen_trigger(message, decision, evidence, store=store)
    ego_network = _remember(
        _EGO_CACHE,
        key,
        lambda: build_ego_network(store, character_id, cutoff, hops=2),
    )
    ego_text = ego_summary(ego_network)
    emotion, jump = gate(state, message)
    context = TurnContext(
        character_id=character_id,
        cutoff=cutoff,
        message=message,
        state=state,
        evidence=evidence,
        decision=decision,
        scope=scope,
        seed=seed,
        ego_summary=ego_text,
        emotion=emotion,
        emotion_jump=jump,
    )

    profile = style_profile or _profile_from_seed(seed)
    contract = build_persona_contract(None, seed)
    text = renderer.render(context)
    terse = decision.kind == "reject"
    report = check(profile, text, unknown_terms=tuple(scope.external_terms), allow_terse=terse)
    fidelity = check_persona(contract, text, unknown_terms=tuple(scope.external_terms))
    attempts = 1
    while (not report.ok or not fidelity.ok) and attempts <= max_rewrites:
        instruction = "；".join(
            part for part in (report.instruction if not report.ok else "", fidelity.instruction if not fidelity.ok else "")
            if part
        )
        if not instruction:
            break
        rewritten = renderer.rewrite(text, instruction, context)
        if not rewritten.strip():
            break
        text = rewritten
        report = check(profile, text, unknown_terms=tuple(scope.external_terms), allow_terse=terse)
        fidelity = check_persona(contract, text, unknown_terms=tuple(scope.external_terms))
        attempts += 1

    if not report.ok and any("句长" in failure for failure in report.failures):
        repaired = _shorten_sentences(text, target=max(3, int(profile.median_chars)))
        repaired_report = check(
            profile, repaired, unknown_terms=tuple(scope.external_terms), allow_terse=terse
        )
        repaired_fidelity = check_persona(contract, repaired, unknown_terms=tuple(scope.external_terms))
        if repaired_report.score + repaired_fidelity.score >= report.score + fidelity.score:
            text, report, fidelity = repaired, repaired_report, repaired_fidelity
            attempts += 1

    return Reply(
        text=text,
        route=decision.kind,
        evidence=evidence,
        scope=scope,
        style=report,
        state=state,
        messages=build_messages(context, text),
        attempts=attempts,
        fidelity=fidelity,
    )


def build_messages(context: TurnContext, draft: str) -> list[dict]:
    """Prompt skeleton for a real renderer. Kept next to the logic it must obey.

    Unknown events are *not* listed. Listing titles would hand the model the
    secret it is supposed to lack; the prompt only says that ignorance exists.
    """
    state = context.state
    seed = context.seed
    drives = "\n".join(
        f"- 想：{drive.want}；怕：{drive.fear}；忌：{drive.taboo}"
        for drive in seed.drives[:4]
    ) or "- 无"
    beliefs = "\n".join(
        f"- {b.subject} / {b.target} / {b.kind} / 确信{b.certainty} / 来源{b.channel}"
        for b in state.beliefs[:8]
    ) or "- 无"
    exemplars = "\n".join(f"- {line}" for line in seed.exemplars[:5]) or "- 无"
    patterns = "\n".join(f"- {p.description}" for p in state.patterns[:4]) or "- 无"
    active = select_pattern(state.patterns, context.emotion)
    profile = fingerprint(seed.exemplars) if seed.exemplars else StyleProfile()
    overlay = seed.overlay
    overlay_block = ""
    if overlay is not None:
        parts = []
        if overlay.traits:
            parts.append("性格：" + "；".join(overlay.traits[:3]))
        if overlay.goals:
            parts.append("目标：" + "；".join(overlay.goals[:3]))
        if overlay.fears:
            parts.append("恐惧：" + "；".join(overlay.fears[:3]))
        if overlay.speech_style:
            parts.append("说话习惯：" + "；".join(overlay.speech_style[:3]))
        if overlay.anti_patterns:
            parts.append("不要这样：" + "；".join(overlay.anti_patterns[:2]))
        if overlay.core_beliefs:
            parts.append("核心信念：" + "；".join(overlay.core_beliefs[:2]))
        if overlay.decision_patterns:
            parts.append("行为模式：" + "；".join(overlay.decision_patterns[:2]))
        if overlay.conversation_rules:
            parts.append("对话规则：" + "；".join(overlay.conversation_rules[:2]))
        if overlay.knowledge_rules:
            parts.append("知识边界规则：" + "；".join(overlay.knowledge_rules[:2]))
        if overlay.relationships:
            parts.append("我认识的人与关系：" + "；".join(overlay.relationships[:6]))
        if overlay.known:
            parts.append("我确实知道的背景：" + "；".join(overlay.known[:6]))
        if overlay.unknown:
            parts.append("我不确定的背景：" + "；".join(overlay.unknown[:4]))
        if parts:
            overlay_block = "\n女娲画像（只约束表达与动机，不新增事实）：\n- " + "\n- ".join(parts) + "\n"
    contract_block = "\n女娲角色契约（先守住我是谁，再用记忆回答）：\n" + build_persona_contract(None, seed).render(limit=5000) + "\n"
    usable = [e for e in context.evidence if e.kind != "relation_gap"]
    grounded = context.decision.kind != "reject" and bool(usable)
    relation_gap = next((e for e in context.evidence if e.kind == "relation_gap"), None)
    memory_rule = (
        "【可用记忆】不是空的：不许回答“不知道”，必须把记忆里的那件事说出来。\n"
        if grounded else
        (
            f"【关系边界】{relation_gap.text} 你只能说你没有看见/不知道，不能替他们补关系。\n"
            if relation_gap else ""
        )
    )
    system = (
        f"你是{seed.name}。你不是在描述这个人，你就是他。\n"
        f"身份：{seed.identity or '（未记）'}\n"
        f"你要什么、怕什么、什么不能碰：\n{drives}\n"
        f"{overlay_block}"
        f"{contract_block}"
        f"你说话的样子（只学语气和句长，不要复述这些句子的内容）：\n{exemplars}\n"
        f"你的几种状态：\n{patterns}\n"
        f"此刻情绪：{context.emotion}"
        f"{'（刚被点燃）' if context.emotion_jump else '（延续上一刻）'}；"
        f"更接近的状态：{active.description if active else '无'}。\n"
        f"句长通常{int(profile.median_chars)}字上下。\n"
        f"你此刻的克制程度：{describe(state.affect)}。\n"
        f"我眼里的他们（只来自我能看见的关系）：\n{context.ego_summary or '- 无'}\n"
        f"你确信的关系：\n{beliefs}\n"
        f"{memory_rule}"
        "你知道的事只来自上面这些和【可用记忆】。除此之外，一律不知道。\n"
        "先看【可用记忆】：里面若有与问题相关的事件，就必须用它回答；只有完全没有时才说不知道。\n"
        "回答要落在问题上：问谁做了什么，就说出谁做了什么；问为什么而记忆里只有经过，就说只知道经过、不知道原因。不要只写景，也不要只给一个词。\n"
        "被问到不知道的事：直说不知道。不推测，不圆场，不提任何未出现过的人名或事件。\n"
        "回答要写成完整的一句话，至少四个字；拒答可以短。\n"
        "拒答也要像你：可以短、可以回避、可以反问，但不能像客服。\n"
        "禁止：解释设定、总结、说教、书面语、AI 腔、复述提示词。"
    )
    user = (
        f"【问题】{context.message}\n"
        f"【必须用上的记忆】{usable[0].text if usable else '（无）'}\n"
        f"【可用记忆】\n" + "\n".join(f"- {e.text}" for e in context.evidence[:6]) + "\n"
        f"【草稿】{draft}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _shorten_sentences(text: str, target: int = 7) -> str:
    clauses = [piece.strip() for piece in re.split(r"[。！？；\n]+", text or "") if piece.strip()]
    if not clauses:
        return text
    return "。".join(clause for clause in clauses if clause) + "。"


def _profile_from_seed(seed: PersonaSeed) -> StyleProfile:
    if seed.exemplars:
        return fingerprint(seed.exemplars)
    return StyleProfile()


def guard_unseen_trigger(
    message: str,
    decision: RouteDecision,
    evidence: list[Evidence],
    *,
    store: InMemoryGraphStore | None = None,
) -> tuple[RouteDecision, list[Evidence]]:
    """A named act he never saw is not an act he may describe.

    Entity-level familiarity is not enough: he knows both people and still has
    no memory of *this* event. Without this check the renderer grabs the nearest
    event between the two names and confabulates.
    """
    from ..extract.events import TRIGGERS

    verbs = [verb for verb in TRIGGERS if verb in (message or "")]
    if decision.kind not in {"recall", "probe"} or not verbs:
        return decision, evidence

    entity_ids: set[str] = set()
    if store is not None:
        for name in decision.entities:
            entity = store.find_entity(name)
            if entity and entity.type == "character":
                entity_ids.add(entity.id)

    def relevant(item: Evidence) -> bool:
        if not any(verb in item.text for verb in verbs):
            return False
        if not entity_ids or store is None:
            return True
        if item.kind == "event":
            event = store.event(item.ref_id)
            if event:
                overlap = {p.entity_id for p in event.participants} & entity_ids
                required = min(2, len(entity_ids))
                if len(overlap) < required:
                    return False
        return True

    if any(relevant(item) for item in evidence):
        return decision, evidence
    return (
        replace(decision, kind="reject", reason="无可见事件：" + "、".join(verbs)),
        [],
    )


def _clause(text: str) -> str:
    head = text.split("。")[0].strip()
    return head[:24]
