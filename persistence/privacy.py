"""
privacy.py
==========

Privacy rules for what may be written to local persistence.

Hard rule (project requirement)
-------------------------------
The system must **never** persist any information about the user's sexual
activities unless the user explicitly references it in direct conversation
with the AI.

This module implements a conservative, inspectable filter for free-text fields
before they are written to disk. It is intentionally simple for v1 and can be
replaced or extended (e.g. model-based classifiers) without changing store APIs.

Local-only design
-----------------
Privacy filtering does **not** send data off-device. All checks are pure
string heuristics run in-process on the user's machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Conservative topical markers (not exhaustive; prefer false positives → redact)
_SEXUAL_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bsexual\b",
        r"\bsexually\b",
        r"\bsex\b",
        r"\bporn\b",
        r"\berotic\b",
        r"\bnude\b",
        r"\bnudity\b",
        r"\borgasm\b",
        r"\bmasturbat",
        r"\bintercourse\b",
        r"\bintimate act",
        r"\bsexual activity",
        r"\bsexual activities\b",
        r"\bhookup\b",
        r"\bnsfw\b",
    )
)

# Signals that content is *user-originated* explicit reference in conversation
_USER_EXPLICIT_REFERENCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\buser (said|says|mentioned|mentions|told|asked|shared|described|wrote)\b",
        r"\bthe user (said|says|mentioned|told|asked|shared|described)\b",
        r"\buser explicitly\b",
        r"\buser stated\b",
        r"\bthey (said|mentioned|told me|shared)\b",
        r"\bin (direct )?conversation\b",
        r"\bas the user (said|put it|described)\b",
        r"\buser['’]s (own )?words\b",
        r"\bquote(d)? from (the )?user\b",
    )
)

REDACTION_PLACEHOLDER = "[REDACTED: sexual content without explicit user reference]"


@dataclass
class PrivacyPolicy:
    """Configurable knobs for the privacy filter (local defaults only)."""

    enforce_sexual_content_rule: bool = True
    """If True, apply the sexual-activity persistence rule."""

    redaction_placeholder: str = REDACTION_PLACEHOLDER
    """Replacement text when content is blocked from persistence."""


@dataclass
class PrivacyFilter:
    """Apply local privacy rules before write.

    Usage:
        filter = PrivacyFilter()
        safe_text = filter.filter_text(raw)
        safe_dict = filter.filter_mapping(payload)
    """

    policy: PrivacyPolicy = field(default_factory=PrivacyPolicy)

    def contains_sexual_topic(self, text: str) -> bool:
        """Return True if text appears to discuss sexual activity/topics."""
        if not text:
            return False
        return any(p.search(text) for p in _SEXUAL_TOPIC_PATTERNS)

    def has_explicit_user_reference(self, text: str) -> bool:
        """Return True if text indicates the *user* explicitly raised the topic."""
        if not text:
            return False
        return any(p.search(text) for p in _USER_EXPLICIT_REFERENCE_PATTERNS)

    def may_persist_text(self, text: str) -> bool:
        """Decide whether free text may be stored as-is.

        Rule:
          - Non-sexual text → allowed
          - Sexual topic + explicit user reference → allowed
          - Sexual topic without explicit user reference → not allowed
        """
        if not self.policy.enforce_sexual_content_rule:
            return True
        if not self.contains_sexual_topic(text):
            return True
        return self.has_explicit_user_reference(text)

    def filter_text(self, text: str | None) -> str:
        """Return text safe to persist (possibly redacted)."""
        if text is None:
            return ""
        if self.may_persist_text(text):
            return text
        return self.policy.redaction_placeholder

    def filter_mapping(self, data: dict[str, Any] | None) -> dict[str, Any]:
        """Deep-filter string values in a mapping for persistence safety.

        Non-string leaves are copied as-is. Nested dicts/lists are walked.
        """
        if not data:
            return {}
        return self._walk(data)  # type: ignore[return-value]

    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.filter_text(obj)
        if isinstance(obj, dict):
            return {str(k): self._walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._walk(v) for v in obj]
        if isinstance(obj, tuple):
            return [self._walk(v) for v in obj]
        return obj
