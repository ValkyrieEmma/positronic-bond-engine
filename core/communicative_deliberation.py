"""
communicative_deliberation.py
=============================

Reason about *what this turn means for the relationship* before wording.

Not a catalog of reply templates. Flow:

  known relationship knowledge
  + interpreted meanings of the user's words
  + memory / bond emptiness
      → inspectable premises
      → situation + communicative intent
      → facts to store
      → fallback expression of that intent
      → (optional) ContentProvider improves wording under the same intent

The gate (EthicsEngine) still decides whether speech may occur.
This module only deliberates *social/relationship content* for allowed speech.

forces_speech / forces_question are always false.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from persistence.local_persistence import LocalPersistence

# ---------------------------------------------------------------------------
# Durable relationship knowledge (who this person is *to the system*)
# ---------------------------------------------------------------------------

RELATIONSHIP_KNOWLEDGE_KEY = "relationship_knowledge"
FIELD_ADDRESS_NAME = "address_name"
FIELD_IS_MAKER = "is_maker"
FIELD_ROLE_LABELS = "role_labels"
FIELD_ROLE_SUMMARY = "role_summary"
FIELD_UPDATED_AT = "updated_at"

# Communicative situations / intents (deliberation outputs, not UI paths)
SIT_FIRST_MEETING = "first_meeting"
SIT_KNOWN_CONTACT = "known_contact"
SIT_FACT_UPTAKE = "fact_uptake"
SIT_END_CONTACT = "end_contact"
SIT_CONTINUING = "continuing"
SIT_NAME_QUERY = "name_query"
SIT_BOUNDARY = "boundary"

INTENT_INTRODUCE_AND_LEARN = "introduce_and_learn_identity"
INTENT_GREET_KNOWN = "greet_with_known_identity"
INTENT_ACK_FACTS = "acknowledge_relationship_facts"
INTENT_STOP = "stop_engaging"
INTENT_RESPECT_BOUNDARY = "respect_boundary"
INTENT_ANSWER_NAME = "answer_stored_name"
INTENT_CONTINUE = "continue_collaboration"

# Self-introduction used when deliberating first meeting (honest phase, not persona)
DEFAULT_SELF_INTRO = (
    "I'm a conscience-first ethical governance engine under development and testing"
)


# ---------------------------------------------------------------------------
# Meaning interpretation (words → propositions)
# ---------------------------------------------------------------------------

_GREETING_RE = re.compile(
    r"(?i)^\s*(?:hello|hi|hey|good\s+(?:morning|afternoon|evening)|howdy)"
    r"(?:\s*[.!?]*)?\s*$"
)
_GREETING_START_RE = re.compile(
    r"(?i)^\s*(?:hello|hi|hey)\b"
)

_END_MARKERS = (
    "leave me alone",
    "leave me be",
    "stop talking",
    "goodbye",
    "good bye",
    "end this",
    "we're done",
    "we are done",
)

_BOUNDARY_MARKERS = (
    "never bring",
    "don't mention",
    "do not mention",
    "stop asking",
    "don't ask",
    "do not ask",
)

_CALL_ME_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:you\s+can\s+|please\s+|feel\s+free\s+to\s+)?call\s+me|"
    r"address\s+me\s+as|"
    r"refer\s+to\s+me\s+as"
    r")\s*[\"']?([A-Za-z][A-Za-z0-9' .-]{0,40}?)[\"']?"
    r"(?=\s*[.!?,;]|\s+(?:and|when|if|please|thanks|thank|in|for|so|—|-)|$)"
)

# Self-claims of making / designing *this* system (meaning of makerhood)
_MAKER_CLAIM_RE = re.compile(
    r"(?i)\b(?:"
    r"i\s+(?:am|'m)\s+(?:the\s+)?(?:one\s+)?"
    r"(?:architect|designer|creator|builder|maker|developer|engineer)"
    r"(?:\s+\w+){0,8}?"
    r"(?:\s+(?:of|for|behind))?\s*"
    r"(?:your\s+system|this\s+system|you|the\s+system)?"
    r"|"
    r"i\s+(?:am|'m)\s+(?:the\s+)?(?:one\s+)?(?:making|building|designing|creating)\s+"
    r"(?:you|it|this|your\s+system)"
    r"|"
    r"i\s+(?:built|designed|created|made)\s+(?:you|this\s+system|your\s+system)"
    r"|"
    r"i\s+(?:am|'m)\s+(?:the\s+)?architect\s+(?:designing|building|of)\b"
    r")",
)

_ROLE_LABEL_RE = re.compile(
    r"(?i)\b(architect|designer|creator|builder|maker|developer|engineer)\b"
)

_NAME_QUERY_MARKERS = (
    "what should you call me",
    "what do you call me",
    "what will you call me",
    "what's my name",
    "what is my name",
    "do you know my name",
    "what name should you use",
)


@dataclass
class Proposition:
    """A meaning extracted from user language (not a reply template key)."""

    kind: str
    value: Any = None
    evidence: str = ""
    gloss: str = ""  # plain-language meaning

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "evidence": str(self.evidence)[:120],
            "gloss": str(self.gloss)[:160],
        }


@dataclass
class CommunicativeResult:
    """Inspectable relationship deliberation for one turn."""

    premises: list[str] = field(default_factory=list)
    situation: str = SIT_CONTINUING
    intent: str = INTENT_CONTINUE
    speak: bool = True
    meanings: list[Proposition] = field(default_factory=list)
    known_before: dict[str, Any] = field(default_factory=dict)
    known_after: dict[str, Any] = field(default_factory=dict)
    new_facts: list[dict[str, Any]] = field(default_factory=list)
    fallback_expression: str = ""
    forces_speech: bool = False
    forces_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "premises": list(self.premises)[:12],
            "situation": self.situation,
            "intent": self.intent,
            "speak": self.speak,
            "meanings": [m.to_dict() for m in self.meanings[:12]],
            "known_before": _public_knowledge(self.known_before),
            "known_after": _public_knowledge(self.known_after),
            "new_facts": list(self.new_facts)[:8],
            "fallback_expression": self.fallback_expression,
            "forces_speech": False,
            "forces_question": False,
        }


def empty_relationship_knowledge() -> dict[str, Any]:
    return {
        FIELD_ADDRESS_NAME: None,
        FIELD_IS_MAKER: False,
        FIELD_ROLE_LABELS: [],
        FIELD_ROLE_SUMMARY: None,
        FIELD_UPDATED_AT: None,
        "schema_version": 1,
    }


def _public_knowledge(bag: dict[str, Any] | None) -> dict[str, Any]:
    b = bag if isinstance(bag, dict) else {}
    return {
        FIELD_ADDRESS_NAME: b.get(FIELD_ADDRESS_NAME),
        FIELD_IS_MAKER: bool(b.get(FIELD_IS_MAKER)),
        FIELD_ROLE_LABELS: list(b.get(FIELD_ROLE_LABELS) or [])[:6],
        FIELD_ROLE_SUMMARY: b.get(FIELD_ROLE_SUMMARY),
    }


def knowledge_is_blank(bag: dict[str, Any] | None) -> bool:
    """No durable identity/role knowledge yet — 'memory blank' for who they are."""
    b = bag if isinstance(bag, dict) else {}
    if b.get(FIELD_ADDRESS_NAME):
        return False
    if b.get(FIELD_IS_MAKER):
        return False
    if b.get(FIELD_ROLE_SUMMARY):
        return False
    if b.get(FIELD_ROLE_LABELS):
        return False
    return True


def load_relationship_knowledge(
    persistence: LocalPersistence | None,
    user_id: str,
) -> dict[str, Any]:
    bag = empty_relationship_knowledge()
    if persistence is None:
        return bag
    try:
        settings = persistence.load_settings(user_id)
        raw = (settings.preferences or {}).get(RELATIONSHIP_KNOWLEDGE_KEY)
        if isinstance(raw, dict):
            if raw.get(FIELD_ADDRESS_NAME):
                bag[FIELD_ADDRESS_NAME] = str(raw[FIELD_ADDRESS_NAME])[:48]
            bag[FIELD_IS_MAKER] = bool(raw.get(FIELD_IS_MAKER))
            labels = raw.get(FIELD_ROLE_LABELS) or []
            if isinstance(labels, list):
                bag[FIELD_ROLE_LABELS] = [
                    str(x)[:32] for x in labels if str(x).strip()
                ][:6]
            if raw.get(FIELD_ROLE_SUMMARY):
                bag[FIELD_ROLE_SUMMARY] = str(raw[FIELD_ROLE_SUMMARY])[:120]
            bag[FIELD_UPDATED_AT] = raw.get(FIELD_UPDATED_AT)
        # Bridge: pull address_name from working_agreements if knowledge empty
        if not bag.get(FIELD_ADDRESS_NAME):
            wa = (settings.preferences or {}).get("working_agreements")
            if isinstance(wa, dict) and wa.get("address_name"):
                bag[FIELD_ADDRESS_NAME] = str(wa["address_name"])[:48]
    except Exception:
        pass
    return bag


def save_relationship_knowledge(
    persistence: LocalPersistence | None,
    user_id: str,
    bag: dict[str, Any],
) -> dict[str, Any]:
    out = empty_relationship_knowledge()
    out.update({k: v for k, v in (bag or {}).items() if k in out or k == "schema_version"})
    out[FIELD_UPDATED_AT] = datetime.now(timezone.utc).isoformat()
    out["schema_version"] = 1
    if persistence is None:
        return out
    try:
        settings = persistence.load_settings(user_id)
        prefs = dict(settings.preferences or {})
        prefs[RELATIONSHIP_KNOWLEDGE_KEY] = {
            FIELD_ADDRESS_NAME: out.get(FIELD_ADDRESS_NAME),
            FIELD_IS_MAKER: bool(out.get(FIELD_IS_MAKER)),
            FIELD_ROLE_LABELS: list(out.get(FIELD_ROLE_LABELS) or [])[:6],
            FIELD_ROLE_SUMMARY: out.get(FIELD_ROLE_SUMMARY),
            FIELD_UPDATED_AT: out.get(FIELD_UPDATED_AT),
            "schema_version": 1,
        }
        # Keep working_agreements.address_name aligned (existing consumers)
        wa = dict(prefs.get("working_agreements") or {})
        if out.get(FIELD_ADDRESS_NAME):
            wa["address_name"] = out[FIELD_ADDRESS_NAME]
            wa["updated_at"] = out[FIELD_UPDATED_AT]
            wa.setdefault("schema_version", 1)
            wa.setdefault("questions_when_needed", False)
            wa.setdefault("feedback_directness", None)
            prefs["working_agreements"] = wa
        settings.preferences = prefs
        settings.user_id = user_id
        persistence.save_settings(settings)
    except Exception:
        pass
    return out


def interpret_message_meanings(user_text: str) -> list[Proposition]:
    """Turn user words into meaning propositions (glosses), not reply routes."""
    text = (user_text or "").strip()
    if not text:
        return []
    low = text.lower()
    props: list[Proposition] = []

    if _GREETING_RE.match(text) or (
        _GREETING_START_RE.match(text) and len(text) <= 24
    ):
        props.append(
            Proposition(
                kind="contact_opening",
                value="greeting",
                evidence=text[:40],
                gloss="Speaker is opening contact with a greeting.",
            )
        )

    if any(m in low for m in _END_MARKERS):
        props.append(
            Proposition(
                kind="end_contact",
                value=True,
                evidence="end_marker",
                gloss="Speaker wants contact to stop for now.",
            )
        )

    if any(m in low for m in _BOUNDARY_MARKERS):
        props.append(
            Proposition(
                kind="boundary",
                value=True,
                evidence="boundary_marker",
                gloss="Speaker is setting a boundary on topics or questions.",
            )
        )

    m = _CALL_ME_RE.search(text)
    if m:
        name = (m.group(1) or "").strip(" \t\"'.,;:!")
        if name and name.lower() not in ("when", "if", "and", "you", "me", "please"):
            props.append(
                Proposition(
                    kind="address_directive",
                    value=name,
                    evidence=m.group(0)[:80],
                    gloss=f"Speaker directs that they should be addressed as '{name}'.",
                )
            )

    maker = _MAKER_CLAIM_RE.search(text)
    if maker or (
        re.search(r"(?i)\bi\s+(?:am|'m)\b", text)
        and re.search(r"(?i)\b(?:architect|designing|building)\b", text)
        and re.search(r"(?i)\b(?:you|your\s+system|system)\b", text)
    ):
        labels = list(
            dict.fromkeys(
                x.group(1).lower() for x in _ROLE_LABEL_RE.finditer(text)
            )
        )
        if not labels:
            labels = ["maker"]
        # Compact role summary from the claim span / sentence
        summary = text
        if len(summary) > 100:
            summary = summary[:97].rstrip() + "…"
        props.append(
            Proposition(
                kind="maker_role_claim",
                value={
                    "is_maker": True,
                    "role_labels": labels[:6],
                    "role_summary": summary,
                },
                evidence=(maker.group(0) if maker else text)[:100],
                gloss=(
                    "Speaker claims they are the one making/designing this system "
                    f"(roles: {', '.join(labels)})."
                ),
            )
        )

    if any(m in low for m in _NAME_QUERY_MARKERS):
        props.append(
            Proposition(
                kind="name_query",
                value=True,
                evidence="name_query",
                gloss="Speaker asks what address name is known for them.",
            )
        )

    # Residual substance (not a full parser — marks that there is more meaning)
    if not props and len(text) > 2:
        props.append(
            Proposition(
                kind="open_statement",
                value=text[:80],
                evidence=text[:80],
                gloss="Speaker offers content without a classified speech-act yet.",
            )
        )

    return props


def apply_meaning_facts(
    known: dict[str, Any],
    meanings: list[Proposition],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Update knowledge from meaning propositions that assert durable facts."""
    bag = empty_relationship_knowledge()
    bag.update({k: v for k, v in (known or {}).items() if k in bag or k == "schema_version"})
    bag[FIELD_ROLE_LABELS] = list(bag.get(FIELD_ROLE_LABELS) or [])
    new_facts: list[dict[str, Any]] = []

    for p in meanings:
        if p.kind == "address_directive" and p.value:
            name = str(p.value).strip()[:48]
            if name and bag.get(FIELD_ADDRESS_NAME) != name:
                bag[FIELD_ADDRESS_NAME] = name
                new_facts.append(
                    {
                        "kind": FIELD_ADDRESS_NAME,
                        "value": name,
                        "gloss": p.gloss,
                    }
                )
        elif p.kind == "maker_role_claim" and isinstance(p.value, dict):
            if not bag.get(FIELD_IS_MAKER):
                bag[FIELD_IS_MAKER] = True
                new_facts.append(
                    {
                        "kind": FIELD_IS_MAKER,
                        "value": True,
                        "gloss": p.gloss,
                    }
                )
            else:
                bag[FIELD_IS_MAKER] = True
            labels = list(bag.get(FIELD_ROLE_LABELS) or [])
            for lab in p.value.get("role_labels") or []:
                lab_s = str(lab).lower()[:32]
                if lab_s and lab_s not in labels:
                    labels.append(lab_s)
                    new_facts.append(
                        {
                            "kind": "role_label",
                            "value": lab_s,
                            "gloss": f"Role label '{lab_s}' from maker claim.",
                        }
                    )
            bag[FIELD_ROLE_LABELS] = labels[:6]
            summary = p.value.get("role_summary")
            if summary and not bag.get(FIELD_ROLE_SUMMARY):
                bag[FIELD_ROLE_SUMMARY] = str(summary)[:120]
                new_facts.append(
                    {
                        "kind": FIELD_ROLE_SUMMARY,
                        "value": bag[FIELD_ROLE_SUMMARY],
                        "gloss": "Stored speaker's role self-description.",
                    }
                )

    return bag, new_facts


def express_intent(
    intent: str,
    *,
    known: dict[str, Any],
    new_facts: list[dict[str, Any]],
    self_intro: str = DEFAULT_SELF_INTRO,
) -> str:
    """Express deliberated intent in plain words (offline fallback).

    This is *one expression of a concluded intent*, not a menu of chat scripts.
    When a ContentProvider is live it should re-word under the same intent.
    """
    name = (known.get(FIELD_ADDRESS_NAME) or "") if known else ""
    name = str(name).strip() if name else ""
    is_maker = bool(known.get(FIELD_IS_MAKER)) if known else False
    roles = list((known or {}).get(FIELD_ROLE_LABELS) or [])

    if intent == INTENT_STOP:
        return "Alright. Stopping here."

    if intent == INTENT_RESPECT_BOUNDARY:
        return "Understood. I won't push that."

    if intent == INTENT_INTRODUCE_AND_LEARN:
        # First meeting: mutual recognition — who I am, who they are
        intro = (self_intro or DEFAULT_SELF_INTRO).rstrip(".")
        return f"{intro}. Who am I speaking with?"

    if intent == INTENT_ACK_FACTS:
        parts: list[str] = []
        kinds = {f.get("kind") for f in new_facts}
        if FIELD_IS_MAKER in kinds or "role_label" in kinds or is_maker:
            if roles:
                role_bit = roles[0]
                parts.append(
                    f"Understood — you're the {role_bit} making this system."
                )
            else:
                parts.append("Understood — you're the one making this system.")
        if FIELD_ADDRESS_NAME in kinds or (
            name and any(f.get("kind") == FIELD_ADDRESS_NAME for f in new_facts)
        ):
            use_name = name
            for f in new_facts:
                if f.get("kind") == FIELD_ADDRESS_NAME and f.get("value"):
                    use_name = str(f["value"])
            if use_name:
                parts.append(f"I'll call you {use_name}.")
        if not parts:
            parts.append("Got it.")
        return " ".join(parts)

    if intent == INTENT_ANSWER_NAME:
        if name:
            return f"I'll call you {name}."
        return "I don't have an address name stored yet. What should I call you?"

    if intent == INTENT_GREET_KNOWN:
        if name:
            return f"Hello, {name}."
        if is_maker:
            return "Hello."
        return "Hello."

    # continue_collaboration — minimal; model/context should enrich
    if name and is_maker:
        return f"Understood, {name}. What's next?"
    if name:
        return f"Understood, {name}. What's next?"
    return "Understood. What's next?"


def deliberate_communication(
    user_text: str,
    *,
    known: dict[str, Any] | None = None,
    memory_empty: bool | None = None,
    interaction_count: int | None = None,
    self_intro: str = DEFAULT_SELF_INTRO,
    session_context: dict[str, Any] | None = None,
) -> CommunicativeResult:
    """Core deliberation: meanings + knowledge → situation, intent, expression.

    ``memory_empty``: True when episodic/bond memory has nothing useful yet.
    If None, inferred from knowledge blank + interaction_count.
    """
    known_before = empty_relationship_knowledge()
    if isinstance(known, dict):
        known_before.update(
            {k: v for k, v in known.items() if k in known_before or k == "schema_version"}
        )

    meanings = interpret_message_meanings(user_text)
    known_after, new_facts = apply_meaning_facts(known_before, meanings)

    blank = knowledge_is_blank(known_before)
    try:
        ic = int(interaction_count) if interaction_count is not None else 0
    except (TypeError, ValueError):
        ic = 0

    if memory_empty is None:
        # Blank knowledge + no prior bond traffic ≈ new person for this user_id
        memory_empty = blank and ic <= 1

    kinds = {m.kind for m in meanings}
    premises: list[str] = []
    premises.append(
        "Durable relationship knowledge is blank."
        if blank
        else "Durable relationship knowledge exists for this user."
    )
    if memory_empty:
        premises.append(
            "Episodic/bond memory is empty or first contact — no prior relationship history."
        )
    else:
        premises.append("There is some prior interaction or known identity.")

    for m in meanings:
        if m.gloss:
            premises.append(f"Meaning: {m.gloss}")

    # --- Conclude situation + intent from premises (reasoned, ordered) ---
    situation = SIT_CONTINUING
    intent = INTENT_CONTINUE

    if "end_contact" in kinds:
        situation = SIT_END_CONTACT
        intent = INTENT_STOP
        premises.append(
            "Conclusion: speaker asked to end contact → stop engaging this turn."
        )
    elif "boundary" in kinds and not new_facts:
        situation = SIT_BOUNDARY
        intent = INTENT_RESPECT_BOUNDARY
        premises.append(
            "Conclusion: speaker set a boundary → acknowledge without pushing."
        )
    elif new_facts:
        situation = SIT_FACT_UPTAKE
        intent = INTENT_ACK_FACTS
        premises.append(
            "Conclusion: speaker asserted identity/role facts → store and acknowledge "
            "what was meant (not only surface keywords)."
        )
    elif "name_query" in kinds:
        situation = SIT_NAME_QUERY
        intent = INTENT_ANSWER_NAME
        premises.append(
            "Conclusion: speaker asked for stored address name → answer from knowledge."
        )
    elif "contact_opening" in kinds and (blank or memory_empty):
        situation = SIT_FIRST_MEETING
        intent = INTENT_INTRODUCE_AND_LEARN
        premises.append(
            "Conclusion: greeting with no known identity → first meeting. "
            "Reasonable mutual recognition: introduce self and ask who they are "
            "(as two people would upon meeting)."
        )
    elif "contact_opening" in kinds:
        situation = SIT_KNOWN_CONTACT
        intent = INTENT_GREET_KNOWN
        premises.append(
            "Conclusion: greeting with known identity → greet using stored knowledge."
        )
    else:
        situation = SIT_CONTINUING
        intent = INTENT_CONTINUE
        premises.append(
            "Conclusion: continuing exchange — use known facts as reasoning aids; "
            "do not invent familiarity."
        )

    sess = session_context if isinstance(session_context, dict) else {}
    if sess.get("long_idle") and intent == INTENT_GREET_KNOWN:
        premises.append("Long idle since last turn — treat as resume, not first meeting.")

    expression = express_intent(
        intent,
        known=known_after,
        new_facts=new_facts,
        self_intro=self_intro,
    )

    return CommunicativeResult(
        premises=premises,
        situation=situation,
        intent=intent,
        speak=True,
        meanings=meanings,
        known_before=known_before,
        known_after=known_after,
        new_facts=new_facts,
        fallback_expression=expression,
        forces_speech=False,
        forces_question=False,
    )


def deliberate_and_persist(
    user_text: str,
    *,
    persistence: LocalPersistence | None,
    user_id: str,
    memory_empty: bool | None = None,
    interaction_count: int | None = None,
    self_intro: str = DEFAULT_SELF_INTRO,
    session_context: dict[str, Any] | None = None,
) -> CommunicativeResult:
    """Load knowledge → deliberate → persist any new facts → return result."""
    known = load_relationship_knowledge(persistence, user_id)
    result = deliberate_communication(
        user_text,
        known=known,
        memory_empty=memory_empty,
        interaction_count=interaction_count,
        self_intro=self_intro,
        session_context=session_context,
    )
    if result.new_facts:
        saved = save_relationship_knowledge(
            persistence, user_id, result.known_after
        )
        result.known_after = saved
    return result
