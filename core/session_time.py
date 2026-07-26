"""
session_time.py
===============

Wall-clock and session time awareness for private / durable runs.

Stores compact timestamps under ``UserSettings.preferences["session_time"]``
so resume after process restart can report idle gap and session age without
a second store type.

Design
------
- Local only (same isolation as other per-user settings).
- Inject ``now_fn`` for tests (no freezes on real wall clock required).
- Social use is light: greetings may note a long gap; never soft theater.
- Wipe via ``delete_user_data`` clears this bag with the user folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from persistence.local_persistence import LocalPersistence

SESSION_TIME_KEY = "session_time"

# Idle gap (seconds) before a greeting may note "back after a while"
LONG_IDLE_SECONDS = 6 * 3600  # 6 hours
# Idle gap that starts a *new* process-session id on next touch if process died
# (also used when begin_session is called explicitly)
SESSION_STALE_SECONDS = 30 * 60  # 30 minutes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class SessionTimeState:
    """In-memory + durable session time snapshot."""

    first_seen_at: str | None = None
    last_session_start: str | None = None
    last_turn_at: str | None = None
    session_id: str | None = None
    turn_index_session: int = 0
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_seen_at": self.first_seen_at,
            "last_session_start": self.last_session_start,
            "last_turn_at": self.last_turn_at,
            "session_id": self.session_id,
            "turn_index_session": int(self.turn_index_session),
            "schema_version": int(self.schema_version),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionTimeState:
        if not isinstance(data, dict):
            return cls()
        return cls(
            first_seen_at=str(data["first_seen_at"])
            if data.get("first_seen_at")
            else None,
            last_session_start=str(data["last_session_start"])
            if data.get("last_session_start")
            else None,
            last_turn_at=str(data["last_turn_at"]) if data.get("last_turn_at") else None,
            session_id=str(data["session_id"]) if data.get("session_id") else None,
            turn_index_session=int(data.get("turn_index_session") or 0),
            schema_version=int(data.get("schema_version") or 1),
        )


def load_session_time(
    persistence: LocalPersistence | None,
    user_id: str,
) -> SessionTimeState:
    if persistence is None:
        return SessionTimeState()
    try:
        settings = persistence.load_settings(user_id)
        raw = (settings.preferences or {}).get(SESSION_TIME_KEY)
        return SessionTimeState.from_dict(raw if isinstance(raw, dict) else None)
    except Exception:
        return SessionTimeState()


def _save_session_time(
    persistence: LocalPersistence,
    user_id: str,
    state: SessionTimeState,
) -> None:
    settings = persistence.load_settings(user_id)
    prefs = dict(settings.preferences or {})
    prefs[SESSION_TIME_KEY] = state.to_dict()
    settings.preferences = prefs
    settings.user_id = user_id
    persistence.save_settings(settings)


def begin_session(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    now_fn: Callable[[], datetime] | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    """Mark a process/session start; returns session_context for evaluate/status.

    If the last turn was recent and ``force_new`` is False, keeps the same
    ``session_id`` (process restart mid-session). Long idle or first run
    creates a new session id.
    """
    now = (now_fn or _utc_now)()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    state = load_session_time(persistence, user_id)
    last_turn = _parse_iso(state.last_turn_at)
    idle = (now - last_turn).total_seconds() if last_turn else None

    new_session = (
        force_new
        or not state.session_id
        or idle is None
        or idle >= SESSION_STALE_SECONDS
    )
    if new_session:
        state.session_id = uuid4().hex[:12]
        state.last_session_start = _fmt(now)
        state.turn_index_session = 0
    if not state.first_seen_at:
        state.first_seen_at = _fmt(now)

    if persistence is not None:
        try:
            _save_session_time(persistence, user_id, state)
        except Exception:
            pass

    return build_session_context(state, now=now, just_began=True)


def touch_turn(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Record a user turn; increments session turn index. Returns session_context."""
    now = (now_fn or _utc_now)()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    state = load_session_time(persistence, user_id)
    if not state.session_id:
        # begin_session was not called — open one
        return begin_session(persistence, user_id, now_fn=lambda: now, force_new=True)

    last_turn = _parse_iso(state.last_turn_at)
    idle_before = (now - last_turn).total_seconds() if last_turn else None
    # Very long gap mid-process still rolls session id
    if idle_before is not None and idle_before >= SESSION_STALE_SECONDS:
        state.session_id = uuid4().hex[:12]
        state.last_session_start = _fmt(now)
        state.turn_index_session = 0

    state.turn_index_session = int(state.turn_index_session or 0) + 1
    state.last_turn_at = _fmt(now)
    if not state.first_seen_at:
        state.first_seen_at = _fmt(now)
    if not state.last_session_start:
        state.last_session_start = _fmt(now)

    if persistence is not None:
        try:
            _save_session_time(persistence, user_id, state)
        except Exception:
            pass

    return build_session_context(
        state, now=now, idle_before_turn=idle_before, just_began=False
    )


def build_session_context(
    state: SessionTimeState,
    *,
    now: datetime | None = None,
    idle_before_turn: float | None = None,
    just_began: bool = False,
) -> dict[str, Any]:
    """Plain dict for evaluate context, status, and social_direct."""
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    last_turn = _parse_iso(state.last_turn_at)
    session_start = _parse_iso(state.last_session_start)
    first_seen = _parse_iso(state.first_seen_at)

    idle_s = idle_before_turn
    if idle_s is None and last_turn is not None:
        idle_s = max(0.0, (now - last_turn).total_seconds())
    session_age_s = (
        max(0.0, (now - session_start).total_seconds()) if session_start else 0.0
    )
    lifetime_s = max(0.0, (now - first_seen).total_seconds()) if first_seen else 0.0

    long_idle = bool(idle_s is not None and idle_s >= LONG_IDLE_SECONDS)
    new_session = bool(just_began and state.turn_index_session == 0)

    return {
        "session_id": state.session_id,
        "first_seen_at": state.first_seen_at,
        "last_session_start": state.last_session_start,
        "last_turn_at": state.last_turn_at,
        "turn_index_session": int(state.turn_index_session or 0),
        "now_utc": _fmt(now),
        "idle_seconds": round(idle_s, 1) if idle_s is not None else None,
        "session_age_seconds": round(session_age_s, 1),
        "lifetime_seconds": round(lifetime_s, 1),
        "long_idle": long_idle,
        "new_session": new_session,
        "long_idle_threshold_seconds": LONG_IDLE_SECONDS,
        "session_stale_threshold_seconds": SESSION_STALE_SECONDS,
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }


def format_idle_brief(session_context: dict[str, Any] | None) -> str:
    """Human-readable idle / session line for status (not chat theater)."""
    if not isinstance(session_context, dict):
        return "session: (none)"
    idle = session_context.get("idle_seconds")
    age = session_context.get("session_age_seconds")
    turns = session_context.get("turn_index_session")
    sid = session_context.get("session_id") or "?"
    parts = [f"session_id={sid}", f"turns={turns}"]
    if age is not None:
        parts.append(f"session_age={_human_duration(float(age))}")
    if idle is not None:
        parts.append(f"idle_before_last={_human_duration(float(idle))}")
    if session_context.get("long_idle"):
        parts.append("long_idle=yes")
    return "  ".join(parts)


def _human_duration(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h{m}m" if m else f"{h}h"
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d}d{h}h" if h else f"{d}d"
