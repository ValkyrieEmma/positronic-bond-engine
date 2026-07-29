"""
session_presence.py
===================

Session-scoped multi-user presence for household / co-located contexts.

Invariants
----------
- Presence is **session-only**. It never creates permanent cross-user data.
- Bonds, memory, baselines, and decisions remain scoped to a single real ``user_id``.
- No synthetic group user_ids.
- When more than one person is present and the speaker is not identified for
  this turn, the entrypoint must ask who is speaking — not guess or merge.

This module only tracks who is present. Routing and isolation live in the
entrypoint / per-user stores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _norm_user_id(user_id: str) -> str:
    return (user_id or "").strip()


@dataclass
class SessionPresence:
    """In-memory set of real user_ids currently present in this session."""

    _present: set[str] = field(default_factory=set)

    def mark_present(self, user_id: str) -> None:
        uid = _norm_user_id(user_id)
        if uid:
            self._present.add(uid)

    def mark_left(self, user_id: str) -> None:
        uid = _norm_user_id(user_id)
        if uid:
            self._present.discard(uid)

    def current(self) -> list[str]:
        """Sorted list of present user_ids (stable, inspectable)."""
        return sorted(self._present)

    def clear(self) -> None:
        """Clear all session presence (e.g. session end)."""
        self._present.clear()

    def count(self) -> int:
        return len(self._present)

    def is_multi_user(self) -> bool:
        return len(self._present) > 1

    def is_ambiguous(self, speaker_id: str | None = None) -> bool:
        """True when more than one user is present and speaker is not identified.

        ``speaker_id`` must be a non-empty id that is currently present.
        Unknown / absent speaker_ids do not clear ambiguity.
        """
        if len(self._present) <= 1:
            return False
        sid = _norm_user_id(speaker_id or "")
        if not sid:
            return True
        return sid not in self._present

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.current(),
            "count": self.count(),
            "multi_user": self.is_multi_user(),
            "forces_speech": False,
            "forces_question": False,
        }


# Explicit speaker markers in free text (minimal, deterministic)
_SPEAKER_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:"
    r"(?:as|i\s+am|i'm|im)\s+([A-Za-z0-9_.@-]{1,64})\s*[:\-–—]\s*"
    r"|\[([A-Za-z0-9_.@-]{1,64})\]\s*"
    r"|([A-Za-z0-9_.@-]{1,64})\s*:\s+"
    r")(.*)$"
)


def extract_speaker_id(
    user_text: str,
    present: list[str] | set[str] | None,
) -> str | None:
    """If the turn clearly identifies a present user, return that user_id.

    Patterns (case-sensitive match against present ids after normalize):
      as alice: hello
      i am alice: hello
      [alice] hello
      alice: hello   (only if ``alice`` is in the present set)
    """
    text = (user_text or "").strip()
    if not text or not present:
        return None
    present_map = {_norm_user_id(u): u for u in present if _norm_user_id(u)}
    if not present_map:
        return None

    m = _SPEAKER_PREFIX_RE.match(text)
    if not m:
        return None
    candidate = (m.group(1) or m.group(2) or m.group(3) or "").strip()
    if not candidate:
        return None
    # Match present ids case-insensitively for convenience
    lower_map = {k.lower(): v for k, v in present_map.items()}
    return lower_map.get(candidate.lower())


def strip_speaker_prefix(user_text: str, speaker_id: str | None) -> str:
    """Remove an explicit speaker prefix once the speaker is known."""
    text = (user_text or "").strip()
    if not text or not speaker_id:
        return text
    m = _SPEAKER_PREFIX_RE.match(text)
    if not m:
        return text
    candidate = (m.group(1) or m.group(2) or m.group(3) or "").strip()
    if candidate.lower() != speaker_id.lower():
        return text
    rest = (m.group(4) or "").strip()
    return rest if rest else text


IDENTITY_REQUEST_TEXT = (
    "More than one person is present. Who is speaking? "
    "Say e.g. 'as <user_id>: <message>' so I do not assume the wrong bond."
)


def identity_request_reply(present: list[str] | None = None) -> str:
    """Honest multi-user identity ask — no guess, no merge."""
    ids = [p for p in (present or []) if p]
    if len(ids) >= 2:
        shown = ", ".join(ids[:8])
        return (
            f"More than one person is present ({shown}). Who is speaking? "
            "Say e.g. 'as <user_id>: <message>' so I do not assume the wrong bond."
        )
    return IDENTITY_REQUEST_TEXT
