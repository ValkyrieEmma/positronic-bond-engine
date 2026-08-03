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

Touch history & timezone (added for Phase 2 — engagement window model)
------------------------------------------------------------------------
``touch_history`` is a bounded, pruned-on-save list of ISO timestamps for
real user turns (recorded in ``touch_turn``, not ``begin_session`` — opening
a session with nobody saying anything yet is not evidence of an activity
pattern). It exists so a later per-user "when does this person usually talk
to me" model (``core/engagement_window.py``, not built yet) has raw history
to learn from, without this module knowing anything about windows, recharge
cycles, or proactive candidates itself — this module only records and prunes.

``timezone`` is a per-user IANA name (e.g. ``"America/Los_Angeles"``), the
single source of truth for localizing that history — "hour of day" is
meaningless without it, and a fixed UTC-offset integer would silently drift
across DST. Set via ``set_timezone``; best-effort validated against the
system's IANA database when one is available (see ``set_timezone`` docstring
for what happens when it isn't, e.g. a bare Windows Python without the
``tzdata`` package).

Both fields default to empty/None so old ``session_time`` bags on disk load
correctly (``from_dict`` never requires either key).

``live_touch_this_turn`` (added for Phase 2 step 5 — get_next_candidate)
--------------------------------------------------------------------------
``session_context`` (the dict returned by ``touch_turn`` / ``begin_session``
/ ``build_session_context``) gained one new boolean key,
``live_touch_this_turn``: True only on the context returned by an actual
``touch_turn()`` call (a real user turn happened just now), False from a
bare ``begin_session()`` (opening a session with nobody having said
anything yet, same distinction ``touch_history`` itself already draws — see
above). This is the existing, narrowly-scoped signal
``auditing.engagement_queue.EngagementQueue.get_next_candidate()``'s
``mid_session`` parameter is meant to be derived from: a caller sitting in
the same turn-processing path as a live ``touch_turn()`` call already has
this turn's ``session_context`` in hand and can read the key straight off
it, rather than tracking a second, parallel "are we mid-session" flag of
its own. Not exposed anywhere before this — this module had no way to tell
a live-touch context from a session-open-only context from the outside
until now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from persistence.local_persistence import LocalPersistence

SESSION_TIME_KEY = "session_time"

# Idle gap (seconds) before a greeting may note "back after a while"
LONG_IDLE_SECONDS = 6 * 3600  # 6 hours
# Idle gap that starts a *new* process-session id on next touch if process died
# (also used when begin_session is called explicitly)
SESSION_STALE_SECONDS = 30 * 60  # 30 minutes

# Touch-history retention: whichever cap binds first, checked on every save.
TOUCH_HISTORY_MAX_ENTRIES = 500
TOUCH_HISTORY_MAX_AGE_DAYS = 90


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


def _prune_touch_history(history: list[str], now: datetime) -> list[str]:
    """Drop entries older than the age cap, then cap total count.

    Unparseable entries are dropped rather than kept (defensive — should not
    happen from our own writes, but a hand-edited or corrupted bag should not
    poison the model with a garbage timestamp).
    """
    cutoff = now - timedelta(days=TOUCH_HISTORY_MAX_AGE_DAYS)
    kept: list[str] = []
    for ts in history:
        dt = _parse_iso(ts)
        if dt is not None and dt >= cutoff:
            kept.append(ts)
    if len(kept) > TOUCH_HISTORY_MAX_ENTRIES:
        kept = kept[-TOUCH_HISTORY_MAX_ENTRIES:]
    return kept


@dataclass
class SessionTimeState:
    """In-memory + durable session time snapshot."""

    first_seen_at: str | None = None
    last_session_start: str | None = None
    last_turn_at: str | None = None
    session_id: str | None = None
    turn_index_session: int = 0
    # Per-user IANA timezone name (e.g. "America/Los_Angeles"); None until set.
    timezone: str | None = None
    # Bounded, pruned-on-save list of ISO turn timestamps (see module docstring).
    touch_history: list[str] = field(default_factory=list)
    schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_seen_at": self.first_seen_at,
            "last_session_start": self.last_session_start,
            "last_turn_at": self.last_turn_at,
            "session_id": self.session_id,
            "turn_index_session": int(self.turn_index_session),
            "timezone": self.timezone,
            "touch_history": list(self.touch_history),
            "schema_version": int(self.schema_version),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionTimeState:
        if not isinstance(data, dict):
            return cls()
        raw_history = data.get("touch_history")
        history = (
            [str(t) for t in raw_history if t]
            if isinstance(raw_history, list)
            else []
        )
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
            timezone=str(data["timezone"]) if data.get("timezone") else None,
            touch_history=history,
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


def _record_touch(
    persistence: LocalPersistence | None,
    user_id: str,
    now: datetime,
) -> None:
    """Append+prune touch_history for a real turn. Fail-soft, local only."""
    if persistence is None:
        return
    try:
        state = load_session_time(persistence, user_id)
        state.touch_history = _prune_touch_history(
            list(state.touch_history) + [_fmt(now)], now
        )
        _save_session_time(persistence, user_id, state)
    except Exception:
        pass


def set_timezone(
    persistence: LocalPersistence | None,
    user_id: str,
    tz_name: str,
) -> dict[str, Any]:
    """Set this user's IANA timezone (e.g. ``"America/Los_Angeles"``).

    Best-effort validated against the system's tz database via ``zoneinfo``.
    Three distinct outcomes, reported honestly rather than collapsed into a
    single boolean:

    - The name is a real IANA zone: stored, ``validated=True``.
    - The name is checked against a known-good canary ("UTC") to confirm a tz
      database is actually available, and it isn't a real zone: rejected,
      ``ok=False``, nothing is stored.
    - No tz database is available at all (the canary itself fails — common on
      a bare Windows Python install without the ``tzdata`` PyPI package, since
      Windows ships no system IANA data): the name is stored as given
      (best-effort, matching this module's fail-soft persistence elsewhere)
      but ``validated=False``, so callers can surface that honestly instead of
      claiming a check that never actually ran.

    Returns a dict: ``{"ok", "timezone", "validated", "error"}``.
    """
    name = str(tz_name or "").strip()
    result: dict[str, Any] = {
        "ok": False,
        "timezone": None,
        "validated": False,
        "error": None,
    }
    if not name:
        result["error"] = "empty timezone name"
        return result

    validated = False
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(name)
            validated = True
        except ZoneInfoNotFoundError:
            try:
                ZoneInfo("UTC")  # canary: is a tz database available at all?
            except Exception:
                pass  # no database available — fall through, store best-effort
            else:
                result["error"] = f"unknown IANA timezone: {name}"
                return result
    except ImportError:
        pass  # zoneinfo unavailable (pre-3.9) — store best-effort

    state = load_session_time(persistence, user_id)
    state.timezone = name
    if persistence is not None:
        try:
            _save_session_time(persistence, user_id, state)
        except Exception:
            result["error"] = "failed to persist"
            return result

    result.update({"ok": True, "timezone": name, "validated": validated})
    return result


def get_timezone(
    persistence: LocalPersistence | None,
    user_id: str,
) -> str | None:
    """Convenience accessor — this user's stored IANA timezone, if any set."""
    return load_session_time(persistence, user_id).timezone


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

    Does not touch ``touch_history`` — a session opening with nobody having
    said anything yet is not evidence of an activity pattern; ``touch_turn``
    is where real touches are recorded.
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
        # begin_session was not called — open one, but this call is still a
        # real touch, so record it in touch_history too before returning.
        ctx = begin_session(persistence, user_id, now_fn=lambda: now, force_new=True)
        _record_touch(persistence, user_id, now)
        ctx["live_touch_this_turn"] = True
        return ctx

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
    state.touch_history = _prune_touch_history(
        list(state.touch_history) + [_fmt(now)], now
    )

    if persistence is not None:
        try:
            _save_session_time(persistence, user_id, state)
        except Exception:
            pass

    return build_session_context(
        state, now=now, idle_before_turn=idle_before, just_began=False, live_touch=True
    )


def build_session_context(
    state: SessionTimeState,
    *,
    now: datetime | None = None,
    idle_before_turn: float | None = None,
    just_began: bool = False,
    live_touch: bool = False,
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
        "timezone": state.timezone,
        "touch_history_count": len(state.touch_history),
        "live_touch_this_turn": bool(live_touch),
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
