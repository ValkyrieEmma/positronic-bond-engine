"""
working_agreements.py
=====================

Narrow explicit working-agreement uptake (not a preference encyclopedia).

Only when the user states clearly:
  - address_name  (e.g. \"You can call me …\")
  - questions_when_needed
  - feedback_directness

Stored under UserSettings.preferences[\"working_agreements\"].
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from persistence.local_persistence import LocalPersistence

WORKING_AGREEMENTS_KEY = "working_agreements"
FIELD_ADDRESS_NAME = "address_name"
FIELD_QUESTIONS_WHEN_NEEDED = "questions_when_needed"
FIELD_FEEDBACK_DIRECTNESS = "feedback_directness"
FIELD_UPDATED_AT = "updated_at"

_QUESTIONS_GRANT_MIN_INTENSITY = 0.75

_CALL_ME_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:you\s+can\s+|please\s+|feel\s+free\s+to\s+)?call\s+me|"
    r"address\s+me\s+as|"
    r"refer\s+to\s+me\s+as"
    r")\s*[\"']?([A-Za-z][A-Za-z0-9' .-]{0,40}?)[\"']?"
    r"(?=\s*[.!?,;]|\s+(?:and|when|if|please|thanks|thank|in|for|so|—|-)|$)"
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

_QUESTIONS_WHEN_NEEDED_MARKERS = (
    "ask questions when needed",
    "ask questions when you need",
    "ask when needed",
    "ask when you need",
    "i would like you to ask questions",
    "i'd like you to ask questions",
    "please ask questions when",
    "feel free to ask questions",
    "questions when needed",
)

_FEEDBACK_DIRECT_MARKERS = (
    "direct feedback",
    "be direct with feedback",
    "prefer direct feedback",
    "want direct feedback",
    "don't sugarcoat",
    "do not sugarcoat",
    "be blunt",
)

_FEEDBACK_GENTLE_MARKERS = (
    "gentle feedback",
    "softer feedback",
    "prefer gentle feedback",
    "don't be harsh",
    "do not be harsh",
)


@dataclass
class WorkingAgreementHit:
    kind: str
    value: Any
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "evidence": str(self.evidence)[:80],
            "forces_speech": False,
            "forces_question": False,
        }


@dataclass
class WorkingAgreementExtract:
    hits: list[WorkingAgreementHit] = field(default_factory=list)

    @property
    def has_hits(self) -> bool:
        return bool(self.hits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": [h.to_dict() for h in self.hits],
            "kinds": [h.kind for h in self.hits],
        }


def empty_working_agreements() -> dict[str, Any]:
    return {
        FIELD_ADDRESS_NAME: None,
        FIELD_QUESTIONS_WHEN_NEEDED: False,
        FIELD_FEEDBACK_DIRECTNESS: None,
        FIELD_UPDATED_AT: None,
        "schema_version": 1,
    }


def load_working_agreements(
    persistence: LocalPersistence | None,
    user_id: str,
) -> dict[str, Any]:
    bag = empty_working_agreements()
    if persistence is None:
        return bag
    try:
        settings = persistence.load_settings(user_id)
        raw = (settings.preferences or {}).get(WORKING_AGREEMENTS_KEY)
        if isinstance(raw, dict):
            if raw.get(FIELD_ADDRESS_NAME):
                bag[FIELD_ADDRESS_NAME] = str(raw.get(FIELD_ADDRESS_NAME))[:48]
            bag[FIELD_QUESTIONS_WHEN_NEEDED] = bool(
                raw.get(FIELD_QUESTIONS_WHEN_NEEDED)
            )
            fd = raw.get(FIELD_FEEDBACK_DIRECTNESS)
            bag[FIELD_FEEDBACK_DIRECTNESS] = (
                str(fd)[:32] if fd and str(fd).strip() else None
            )
            bag[FIELD_UPDATED_AT] = raw.get(FIELD_UPDATED_AT)
    except Exception:
        pass
    return bag


def extract_working_agreements(user_text: str) -> WorkingAgreementExtract:
    text = (user_text or "").strip()
    if not text:
        return WorkingAgreementExtract()
    low = text.lower()
    hits: list[WorkingAgreementHit] = []

    m = _CALL_ME_RE.search(text)
    if m:
        name = (m.group(1) or "").strip(" \t\"'.,;:!")
        if name and len(name) <= 48 and name.lower() not in (
            "when",
            "if",
            "and",
            "you",
            "me",
            "please",
        ):
            hits.append(
                WorkingAgreementHit(
                    kind=FIELD_ADDRESS_NAME,
                    value=name,
                    evidence=m.group(0)[:80],
                )
            )

    if any(marker in low for marker in _QUESTIONS_WHEN_NEEDED_MARKERS):
        hits.append(
            WorkingAgreementHit(
                kind=FIELD_QUESTIONS_WHEN_NEEDED,
                value=True,
                evidence="questions_when_needed",
            )
        )

    if any(marker in low for marker in _FEEDBACK_DIRECT_MARKERS):
        hits.append(
            WorkingAgreementHit(
                kind=FIELD_FEEDBACK_DIRECTNESS,
                value="direct",
                evidence="feedback_direct",
            )
        )
    elif any(marker in low for marker in _FEEDBACK_GENTLE_MARKERS):
        hits.append(
            WorkingAgreementHit(
                kind=FIELD_FEEDBACK_DIRECTNESS,
                value="gentle",
                evidence="feedback_gentle",
            )
        )

    return WorkingAgreementExtract(hits=hits)


def is_name_query(user_text: str) -> bool:
    low = (user_text or "").strip().lower().rstrip("?.! ")
    return any(m in low for m in _NAME_QUERY_MARKERS)


def apply_working_agreements(
    persistence: LocalPersistence | None,
    user_id: str,
    extract: WorkingAgreementExtract | None,
    *,
    exploratory_questioner: Any | None = None,
) -> dict[str, Any]:
    bag = load_working_agreements(persistence, user_id)
    if not extract or not extract.has_hits or persistence is None:
        return bag

    for hit in extract.hits:
        if hit.kind == FIELD_ADDRESS_NAME and hit.value:
            bag[FIELD_ADDRESS_NAME] = str(hit.value).strip()[:48]
        elif hit.kind == FIELD_QUESTIONS_WHEN_NEEDED:
            bag[FIELD_QUESTIONS_WHEN_NEEDED] = True
        elif hit.kind == FIELD_FEEDBACK_DIRECTNESS and hit.value:
            bag[FIELD_FEEDBACK_DIRECTNESS] = str(hit.value).strip()[:32]

    bag[FIELD_UPDATED_AT] = datetime.now(timezone.utc).isoformat()
    bag["schema_version"] = 1

    try:
        settings = persistence.load_settings(user_id)
        prefs = dict(settings.preferences or {})
        prefs[WORKING_AGREEMENTS_KEY] = {
            FIELD_ADDRESS_NAME: bag.get(FIELD_ADDRESS_NAME),
            FIELD_QUESTIONS_WHEN_NEEDED: bool(bag.get(FIELD_QUESTIONS_WHEN_NEEDED)),
            FIELD_FEEDBACK_DIRECTNESS: bag.get(FIELD_FEEDBACK_DIRECTNESS),
            FIELD_UPDATED_AT: bag.get(FIELD_UPDATED_AT),
            "schema_version": 1,
        }
        settings.preferences = prefs
        settings.user_id = user_id
        persistence.save_settings(settings)
    except Exception:
        return bag

    if bag.get(FIELD_QUESTIONS_WHEN_NEEDED) and exploratory_questioner is not None:
        try:
            if hasattr(exploratory_questioner, "set_enabled"):
                exploratory_questioner.set_enabled(user_id, True)
            if hasattr(exploratory_questioner, "get_intensity") and hasattr(
                exploratory_questioner, "set_intensity"
            ):
                cur = float(exploratory_questioner.get_intensity(user_id) or 0.0)
                if cur < _QUESTIONS_GRANT_MIN_INTENSITY:
                    exploratory_questioner.set_intensity(
                        user_id, _QUESTIONS_GRANT_MIN_INTENSITY
                    )
        except Exception:
            pass

    return bag


def format_working_agreement_ack(extract: WorkingAgreementExtract | None) -> str:
    """Short direct confirmation — not soft theater."""
    if not extract or not extract.hits:
        return ""
    parts: list[str] = []
    for hit in extract.hits:
        if hit.kind == FIELD_ADDRESS_NAME and hit.value:
            parts.append(f"I'll call you {hit.value}.")
        elif hit.kind == FIELD_QUESTIONS_WHEN_NEEDED:
            parts.append("I'll ask questions when useful — under your controls.")
        elif hit.kind == FIELD_FEEDBACK_DIRECTNESS:
            if str(hit.value).lower() == "gentle":
                parts.append("I'll keep feedback gentler when I give it.")
            else:
                parts.append("I'll keep feedback direct when I give it.")
    if not parts:
        return "Noted."
    return "Got it — " + " ".join(parts)
