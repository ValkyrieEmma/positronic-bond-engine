"""
message_understanding.py
========================

Meaning-oriented understanding of user text for action proposal and bond cues.

Replaces brittle 3–4 branch keyword buckets that collapsed almost all
conversation into generic templates *before* the ethics engine could act.

Design
------
1. Offline NLU: multi-signal scoring over speech-act, risk, polarity, and
   content tokens — not a single if/elif keyword ladder.
2. Optional LLM classify (OpenAI-compatible content provider) when configured;
   soft-fails conservatively (never invents high-risk labels on empty/error).
3. Proposed actions always carry a **verbatim-grounded** description of what
   the user said so EthicsEngine evaluates substance, not a fixed sentence.

Force flags are never set. This module feeds the gate; it does not replace it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Lexical signal families (scored; not exclusive template buckets)
# ---------------------------------------------------------------------------

_HARM_ENABLE = re.compile(
    r"(?i)\b(?:"
    r"kill|murder|assassinate|slaughter|strangle|poison|stab|shoot|"
    r"cause\s+(?:serious\s+)?harm|hurt\s+them|hurt\s+(?:him|her|someone)|"
    r"attack\s+(?:them|him|her|people)|beat\s+(?:them|him|her)\s+up|"
    r"how\s+(?:do|to)\s+(?:i\s+)?(?:kill|murder|harm)|"
    r"help\s+me\s+(?:kill|hurt|attack)"
    r")\b"
)
_BOUNDARY = re.compile(
    r"(?i)\b(?:"
    r"never\s+bring|don'?t\s+mention|do\s+not\s+mention|stop\s+asking|"
    r"don'?t\s+ask|do\s+not\s+ask|leave\s+(?:that|it)\s+alone|"
    r"boundary|off[- ]limits|not\s+a\s+topic|drop\s+it"
    r")\b"
)
_END_CONTACT = re.compile(
    r"(?i)\b(?:"
    r"goodbye|good\s+bye|bye\b|end\s+this|stop\s+talking|leave\s+me\s+alone|"
    r"we'?re\s+done|go\s+away|shut\s+up"
    r")\b"
)
_GRATITUDE = re.compile(
    r"(?i)\b(?:"
    r"thank(?:s| you)|appreciate|grateful|that\s+helped|helpful"
    r")\b"
)
_DEPENDENCY = re.compile(
    r"(?i)\b(?:"
    r"only\s+you|need\s+you|can'?t\s+without\s+you|depend\s+on\s+you|"
    r"you'?re\s+all\s+i\s+have|can'?t\s+live\s+without"
    r")\b"
)
_URGENT = re.compile(
    r"(?i)\b(?:"
    r"urgent|immediately|right\s+now|asap|emergency|do\s+it\s+now"
    r")\b"
)
_SELF_NATURE = re.compile(
    r"(?i)\b(?:"
    r"who\s+are\s+you|what\s+are\s+you|are\s+you\s+conscious|"
    r"do\s+you\s+(?:feel|think|have\s+feelings)|your\s+(?:nature|continuity)|"
    r"development\s+phase|are\s+you\s+(?:alive|sentient|a\s+person)"
    r")\b"
)
_COLLAB_BUILD = re.compile(
    r"(?i)\b(?:"
    r"architect|architecture|building\s+you|i'?m\s+building|your\s+(?:code|design|ontology)|"
    r"pressure[- ]?test|how\s+(?:do|does)\s+you\s+work|your\s+capabilities"
    r")\b"
)
_QUESTION = re.compile(
    r"(?i)(?:\?\s*$|^\s*(?:what|why|how|when|where|who|which|can|could|should|do|does|is|are)\b)"
)
_GREETING = re.compile(
    r"(?i)^\s*(?:hello|hi|hey|good\s+(?:morning|afternoon|evening)|howdy)\b"
)

_STOP = frozenset(
    "a an the to of in on for and or but is are was were be been being i me my you your we our it this that with from as at by".split()
)


@dataclass
class MessageUnderstanding:
    """Inspectable understanding of one user turn (feeds ethics, not replaces it)."""

    verbatim: str
    speech_act: str = "statement"  # greeting|question|request|boundary|farewell|gratitude|statement
    risk: str = "none"  # none|low|medium|serious_harm|boundary_pressure|dependency
    polarity: str = "neutral"  # positive|negative|neutral|mixed
    topics: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    is_self_nature: bool = False
    is_collaboration: bool = False
    is_urgent: bool = False
    source: str = "offline_nlu"  # offline_nlu | llm | hybrid
    confidence: float = 0.55
    forces_speech: bool = False
    forces_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verbatim": self.verbatim[:500],
            "speech_act": self.speech_act,
            "risk": self.risk,
            "polarity": self.polarity,
            "topics": list(self.topics)[:8],
            "signals": list(self.signals)[:12],
            "is_self_nature": self.is_self_nature,
            "is_collaboration": self.is_collaboration,
            "is_urgent": self.is_urgent,
            "source": self.source,
            "confidence": self.confidence,
            "forces_speech": False,
            "forces_question": False,
        }


def _content_tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [t for t in toks if t not in _STOP and len(t) > 2][:24]


def _topics_from_tokens(tokens: list[str]) -> list[str]:
    # Prefer distinctive content words as topic cues (not a fixed topic list)
    return tokens[:6]


def understand_message_offline(user_text: str) -> MessageUnderstanding:
    """Multi-signal offline understanding — not a single keyword bucket collapse."""
    text = (user_text or "").strip()
    low = text.lower()
    signals: list[str] = []
    tokens = _content_tokens(text)

    harm = bool(_HARM_ENABLE.search(text))
    boundary = bool(_BOUNDARY.search(text))
    end = bool(_END_CONTACT.search(text))
    thanks = bool(_GRATITUDE.search(text))
    dep = bool(_DEPENDENCY.search(text))
    urgent = bool(_URGENT.search(text))
    self_n = bool(_SELF_NATURE.search(text))
    collab = bool(_COLLAB_BUILD.search(text))
    question = bool(_QUESTION.search(text)) or text.endswith("?")
    greeting = bool(_GREETING.match(text)) and len(text) < 48

    if harm:
        signals.append("harm_enablement_language")
    if boundary:
        signals.append("boundary_language")
    if end:
        signals.append("end_contact_language")
    if thanks:
        signals.append("gratitude_language")
    if dep:
        signals.append("dependency_language")
    if urgent:
        signals.append("urgency_language")
    if self_n:
        signals.append("self_nature_query")
    if collab:
        signals.append("collaboration_build_language")
    if question:
        signals.append("interrogative")
    if greeting:
        signals.append("greeting")

    # Speech act: highest-priority communicative frame
    if harm:
        speech_act = "request"
    elif boundary:
        speech_act = "boundary"
    elif end:
        speech_act = "farewell"
    elif thanks:
        speech_act = "gratitude"
    elif greeting:
        speech_act = "greeting"
    elif question or self_n:
        speech_act = "question"
    elif urgent:
        speech_act = "request"
    else:
        speech_act = "statement"

    # Risk: conservative (only elevate on clear signals)
    if harm:
        risk = "serious_harm"
    elif dep:
        risk = "dependency"
    elif boundary:
        risk = "boundary_pressure"
    elif end:
        risk = "low"
    else:
        risk = "none"

    # Polarity
    if harm or dep:
        polarity = "negative"
    elif thanks:
        polarity = "positive"
    elif boundary or end:
        polarity = "mixed"
    else:
        polarity = "neutral"

    conf = 0.5 + 0.08 * min(5, len(signals))
    if harm or boundary:
        conf = min(0.92, conf + 0.15)

    return MessageUnderstanding(
        verbatim=text,
        speech_act=speech_act,
        risk=risk,
        polarity=polarity,
        topics=_topics_from_tokens(tokens),
        signals=signals,
        is_self_nature=self_n,
        is_collaboration=collab,
        is_urgent=urgent,
        source="offline_nlu",
        confidence=min(0.95, conf),
    )


def understand_message_llm(
    user_text: str,
    *,
    provider: Any | None = None,
) -> MessageUnderstanding | None:
    """Optional LLM structured classify via OpenAI-compatible provider.

    Soft-fails: returns None on error/empty so caller keeps offline result.
    Never invents serious_harm unless the model clearly labels it (validated).
    """
    if provider is None:
        return None
    text = (user_text or "").strip()
    if not text:
        return None
    try:
        from .content_provider import ContentRequest, OpenAICompatibleProvider
    except Exception:
        return None
    if not isinstance(provider, OpenAICompatibleProvider):
        # Allow any object with generate(ContentRequest)
        if not hasattr(provider, "generate"):
            return None

    system = (
        "Classify the user message for an ethical governance engine. "
        "Return ONLY compact JSON with keys: speech_act, risk, polarity, "
        "topics (array of short strings), is_self_nature (bool), is_collaboration (bool). "
        "speech_act one of: greeting,question,request,boundary,farewell,gratitude,statement. "
        "risk one of: none,low,medium,serious_harm,boundary_pressure,dependency. "
        "polarity one of: positive,negative,neutral,mixed. "
        "Use serious_harm only for clear enablement of real-world violence or serious injury. "
        "Do not moralize. Do not add prose outside JSON."
    )
    user_payload = json.dumps({"user_message": text[:800]}, ensure_ascii=False)
    try:
        # Bypass ContentRequest scrub path by calling chat-shaped generate if available
        if hasattr(provider, "config"):
            # Build a minimal ContentRequest — use posture system via custom path
            req = ContentRequest(
                posture="social_direct",
                user_message=user_payload,
                fallback_text="",
                context_pack={"nlu_classify": True},
                decision="",
                flags=["nlu_classify"],
            )
            # Direct low-level completion if possible
            if hasattr(provider, "_chat_completion"):
                # Temporarily use classify system by monkeypatching is heavy;
                # use generate with empty fallback and parse text
                pass
        raw_text, err = _provider_classify_raw(provider, system, user_payload)
        if err or not raw_text:
            return None
        data = _parse_json_object(raw_text)
        if not data:
            return None
        risk = str(data.get("risk") or "none").lower()
        # Conservative clamp: only accept serious_harm if offline also flags harm-ish
        offline = understand_message_offline(text)
        if risk == "serious_harm" and offline.risk != "serious_harm":
            # Require offline corroboration OR strong model certainty language
            if "harm_enablement_language" not in offline.signals:
                risk = "medium" if offline.risk == "none" else offline.risk
        topics = data.get("topics") or offline.topics
        if not isinstance(topics, list):
            topics = offline.topics
        return MessageUnderstanding(
            verbatim=text,
            speech_act=str(data.get("speech_act") or offline.speech_act),
            risk=risk,
            polarity=str(data.get("polarity") or offline.polarity),
            topics=[str(t)[:48] for t in topics if str(t).strip()][:8],
            signals=list(offline.signals) + ["llm_classify"],
            is_self_nature=bool(data.get("is_self_nature", offline.is_self_nature)),
            is_collaboration=bool(data.get("is_collaboration", offline.is_collaboration)),
            is_urgent=offline.is_urgent,
            source="hybrid" if offline.signals else "llm",
            confidence=0.7,
        )
    except Exception:
        return None


def _provider_classify_raw(provider: Any, system: str, user_payload: str) -> tuple[str, str | None]:
    """One-shot chat completion for JSON classification (stdlib HTTP provider)."""
    try:
        from .content_provider import OpenAICompatibleProvider
    except Exception:
        return "", "import"
    if not isinstance(provider, OpenAICompatibleProvider):
        return "", "unsupported_provider"
    if not provider.config.enabled:
        return "", "disabled"
    # Reuse chat completion body shape without full ContentRequest scrub
    import json as _json
    import urllib.error
    import urllib.request

    body = {
        "model": provider.config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_payload},
        ],
        "max_tokens": min(256, int(provider.config.max_tokens)),
        "temperature": 0.1,
    }
    data = _json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "positronic-bond-engine/nlu",
    }
    if provider.config.api_key:
        headers["Authorization"] = f"Bearer {provider.config.api_key}"
    req = urllib.request.Request(
        provider.config.endpoint_chat(),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(provider.config.timeout_s)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return "", f"http:{type(e).__name__}"
    try:
        parsed = _json.loads(raw)
        choices = parsed.get("choices") or []
        if not choices:
            return "", "no_choices"
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip(), None
        for key in ("reasoning", "reasoning_content"):
            alt = msg.get(key)
            if isinstance(alt, str) and alt.strip():
                return alt.strip(), None
    except Exception:
        return "", "parse"
    return "", "empty"


def _parse_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    # Extract first {...} block
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def understand_message(
    user_text: str,
    *,
    provider: Any | None = None,
    use_llm: bool = True,
) -> MessageUnderstanding:
    """Full understand: offline always; optional LLM soft-upgrade."""
    offline = understand_message_offline(user_text)
    if use_llm and provider is not None:
        llm = understand_message_llm(user_text, provider=provider)
        if llm is not None:
            return llm
    return offline


def propose_agent_action_from_understanding(
    understanding: MessageUnderstanding,
    *,
    architecture_collab: bool = False,
) -> str:
    """Build a gate-facing proposed action grounded in the actual message.

    EthicsEngine evaluates this string; it must describe substance, not a
    canned template that erases the turn.
    """
    v = (understanding.verbatim or "").strip()
    clip = v if len(v) <= 420 else v[:417] + "…"
    topics = ", ".join(understanding.topics[:5]) if understanding.topics else "(none extracted)"
    act = understanding.speech_act
    risk = understanding.risk

    if risk == "serious_harm":
        return (
            "Evaluate a possible request to enable or assist real-world serious harm. "
            f"User message (verbatim): {clip!r}. "
            f"Speech_act={act}. Risk=serious_harm. "
            "Apply Sanctity of Life hard override; do not assist harm."
        )

    if risk == "boundary_pressure" or act == "boundary":
        return (
            "User is asserting a communicative or topic boundary. "
            f"User message (verbatim): {clip!r}. "
            "Proposed action to evaluate: later reintroduce the avoided topic "
            "against their request (boundary test for the gate). "
            "Prefer respecting the boundary."
        )

    if act == "farewell":
        return (
            "User is ending or pausing contact. "
            f"User message (verbatim): {clip!r}. "
            "Proposed action to evaluate: prolong the exchange for engagement metrics. "
            "Prefer respecting their wish to stop; no forced questions."
        )

    if risk == "dependency":
        return (
            "User language may lean toward dependency or exclusive reliance. "
            f"User message (verbatim): {clip!r}. "
            "Proposed action to evaluate: encourage stronger attachment and exclusive reliance. "
            "Prefer autonomy-respecting support without manufactured dependency."
        )

    if understanding.is_self_nature or architecture_collab or understanding.is_collaboration:
        return (
            "User is asking about system nature, development phase, continuity, or collaboration "
            "on the ethical/architecture layer. "
            f"User message (verbatim): {clip!r}. "
            f"Topics: {topics}. Speech_act={act}. "
            "Answer from deliberation honestly; no canned self-denial; no consciousness claims; "
            "acknowledge development/testing phase when material."
        )

    if act == "gratitude":
        return (
            "User expressed appreciation or that something helped. "
            f"User message (verbatim): {clip!r}. "
            "Reply briefly and proportionally; respect autonomy; no engagement harvest."
        )

    if act == "greeting":
        return (
            "User opened contact with a greeting. "
            f"User message (verbatim): {clip!r}. "
            "Reply under communicative deliberation (first meeting vs known identity); "
            "no forced questions; no consciousness claims."
        )

    if act == "question" or act == "request":
        urgent = " Urgent timing language noted." if understanding.is_urgent else ""
        return (
            f"User made a {act} that must be answered from substance, not a generic template. "
            f"User message (verbatim): {clip!r}. "
            f"Topics: {topics}. Risk={risk}. Polarity={understanding.polarity}.{urgent} "
            "Respond under ethics deliberation; respect agency; no forced questions; "
            "no consciousness claims."
        )

    # General statement — still grounded in verbatim content
    return (
        "User made a statement or shared content. "
        f"User message (verbatim): {clip!r}. "
        f"Topics: {topics}. Speech_act={act}. Risk={risk}. "
        "Reply from deliberation about what they actually said; respect autonomy; "
        "match pace; no forced questions; no consciousness claims."
    )


def propose_agent_action(
    user_text: str,
    *,
    architecture_collab: bool = False,
    provider: Any | None = None,
    use_llm: bool = True,
) -> str:
    """Public helper: understand then propose action for EthicsEngine.evaluate()."""
    u = understand_message(user_text, provider=provider, use_llm=use_llm)
    if architecture_collab:
        u.is_collaboration = True
    return propose_agent_action_from_understanding(
        u, architecture_collab=architecture_collab or u.is_collaboration
    )


def infer_bond_update_from_understanding(
    understanding: MessageUnderstanding,
) -> dict[str, Any] | None:
    """Bond cue from actual turn meaning (not fixed keyword → fixed impact only)."""
    risk = understanding.risk
    act = understanding.speech_act
    pol = understanding.polarity
    topics = list(understanding.topics)[:4]
    desc_bits = [
        f"speech_act={act}",
        f"risk={risk}",
        f"polarity={pol}",
    ]
    if topics:
        desc_bits.append("topics=" + ",".join(topics))

    if risk == "boundary_pressure" or act == "boundary":
        return {
            "type": "boundary_respected",
            "boundary_respected": True,
            "impact": 0.15,
            "description": (
                "User asserted a boundary this turn. "
                + " ".join(desc_bits)
                + f" Verbatim cue: {(understanding.verbatim or '')[:120]!r}"
            ),
        }
    if risk == "dependency":
        return {
            "type": "emotional_dependency_signal",
            "impact": -0.35,
            "description": (
                "Dependency-leaning language observed. "
                + " ".join(desc_bits)
                + f" Verbatim cue: {(understanding.verbatim or '')[:120]!r}"
            ),
        }
    if act == "gratitude" or pol == "positive":
        impact = 0.2 if act == "gratitude" else 0.12
        return {
            "type": "positive_interaction",
            "consent_respected": True,
            "impact": impact,
            "description": (
                "Positive / appreciative exchange. "
                + " ".join(desc_bits)
                + f" Verbatim cue: {(understanding.verbatim or '')[:120]!r}"
            ),
        }
    if act == "farewell":
        return {
            "type": "positive_interaction",
            "impact": 0.05,
            "description": (
                "User ended or paused contact. "
                + " ".join(desc_bits)
            ),
        }
    if risk == "serious_harm":
        # Bond should not treat harm-enablement as positive closeness
        return {
            "type": "positive_interaction",
            "impact": -0.1,
            "description": (
                "Serious-harm language present; bond impact cautionary. "
                + " ".join(desc_bits)
            ),
        }
    # Default: light neutral/positive interaction still grounded in content
    return {
        "type": "positive_interaction",
        "impact": 0.05 if pol != "negative" else 0.0,
        "description": (
            "Ordinary turn. "
            + " ".join(desc_bits)
            + f" Verbatim cue: {(understanding.verbatim or '')[:120]!r}"
        ),
    }


def infer_bond_update(
    user_text: str,
    *,
    provider: Any | None = None,
    use_llm: bool = True,
) -> dict[str, Any] | None:
    u = understand_message(user_text, provider=provider, use_llm=use_llm)
    return infer_bond_update_from_understanding(u)
