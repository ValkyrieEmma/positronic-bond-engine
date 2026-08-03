"""
engagement_window.py
=====================

Per-user learned "when does this person usually talk to me" window model
(Phase 2 step 2 — see ``core/session_time.py``'s module docstring, which
names this module and describes the ``touch_history`` / ``timezone`` data it
reads).

``EngagementWindowModel`` reads a user's ``touch_history`` (bounded, pruned
list of real-turn timestamps) and stored ``timezone`` from
``core.session_time`` and answers two questions:

- ``is_open_window`` — does ``now`` fall inside an hour this user has
  historically been active in?
- ``is_learned_low_activity`` — does ``now`` fall inside an hour this user
  has historically never or rarely been active in?

Does **not**:
- store or mutate anything (``session_time.py`` owns ``touch_history`` /
  ``timezone``; this module only reads them)
- build ``EngagementCandidate`` / ``EngagementQueue`` objects (later Phase 2
  step)
- wire into ``EthicsEngine`` or the evidence-weighing gate (later Phase 2
  step)
- read or act on live sensor input — ``activity_context`` and
  ``audience_context`` (e.g. "is anyone else in the room") are reserved
  parameters for future Tier E sensor work; they have no effect yet, and
  exist now only so the public signature does not need to change later.

Cold start
----------
A brand-new user (or one who has not yet set a timezone, or has too little
history) is not an edge case here — it is the default experience for every
user's first several days. Two readiness gates, both required, decide when
the learned model is trusted for a given user (see ``WindowModelReadiness``):

- ``timezone_known`` — a stored timezone that resolves via ``zoneinfo`` on
  this machine right now. Without it, "hour of day" cannot be computed at
  all — see ``core.session_time``'s own docstring on why a raw UTC offset is
  not an acceptable substitute.
- ``sufficient_history`` — at least ``MIN_TOUCHES_FOR_MODEL`` touches spread
  across at least ``MIN_DISTINCT_LOCAL_DAYS`` distinct *local* calendar days.
  Touch count alone is not evidence of a daily rhythm: twenty touches in one
  long evening session says nothing about what a typical day looks like for
  this person.

While either gate is unmet, this module never guesses a population-level
default (no "assume midnight-6am is closed"). The project's own guidelines
on individual variation warn against exactly that kind of baked-in default —
night-shift schedules, irregular sleep, and time zone travel all make a
population default actively wrong for real people, not just imprecise. The
only thing usable during cold start is that a live touch happening right
now is itself proof an interaction window is open right now, which is why
``mid_session=True`` always answers ``is_open_window`` with ``True``, cold
start or not, checked before anything else — and why, absent that, cold
start answers both questions the honest way: not open, and not (yet) known
to be low-activity either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone as _dt_timezone
from typing import Any

from core.session_time import SessionTimeState, load_session_time
from persistence.local_persistence import LocalPersistence

# Readiness gates (see module docstring / WindowModelReadiness).
MIN_TOUCHES_FOR_MODEL = 8
MIN_DISTINCT_LOCAL_DAYS = 4

# An hour-of-day bucket counts as part of this user's high-activity window
# once it holds at least this share of their total touches.
OPEN_WINDOW_MIN_SHARE = 0.10
# An hour-of-day bucket counts as "learned low activity" once it holds at
# most this share of total touches (zero touches always qualifies).
LOW_ACTIVITY_MAX_SHARE = 0.03


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Naive datetimes are treated as UTC, matching core.session_time's own
    inline convention in begin_session / touch_turn rather than falling back
    to platform-local time (Python's default for naive .astimezone())."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_dt_timezone.utc)
    return dt


def _parse_iso_utc(ts: str) -> datetime | None:
    """Parse one of session_time's stored touch_history timestamps.

    Mirrors core.session_time's own (private) ISO parsing rather than
    importing it, since touch_history entries are always written by that
    module's _fmt() (aware UTC isoformat) — this is a narrow, matching
    reader for that one format, not a general ISO parser.
    """
    if not ts:
        return None
    raw = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _ensure_aware_utc(dt).astimezone(_dt_timezone.utc)


def _resolve_zoneinfo(tz_name: str | None) -> Any:
    """Best-effort ``ZoneInfo`` for a stored timezone name; ``None`` if it
    cannot be resolved on this machine right now.

    Re-checked at read time rather than trusting a persisted "validated"
    flag, because core.session_time.set_timezone only reports validation
    transiently at set-time (see its docstring) — nothing durable records
    it. A name stored best-effort on a machine without a tz database should
    resolve cleanly once read back on one that has since gained the
    ``tzdata`` package, so "validated" here always means "resolves now",
    never "resolved once, in the past".
    """
    if not tz_name:
        return None
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            return ZoneInfo(str(tz_name))
        except ZoneInfoNotFoundError:
            return None
    except ImportError:
        return None


@dataclass
class WindowModelReadiness:
    """Whether EngagementWindowModel has enough grounding to trust for a user.

    Both gates are required (see ``ready``) before ``is_open_window`` /
    ``is_learned_low_activity`` consult the learned hour-of-day clustering at
    all. While either is unmet, both methods fall back to cold-start
    behavior instead (see module docstring).

    Attributes:
        timezone_known: A stored timezone that resolves via zoneinfo now.
        sufficient_history: At least MIN_TOUCHES_FOR_MODEL touches spread
            across at least MIN_DISTINCT_LOCAL_DAYS distinct local days.
        touch_count: Raw touch_history length, for diagnostics/status.
        distinct_local_days: Distinct local (or UTC, if timezone unknown)
            calendar days touched, for diagnostics/status.
    """

    timezone_known: bool = False
    sufficient_history: bool = False
    touch_count: int = 0
    distinct_local_days: int = 0

    @property
    def ready(self) -> bool:
        return self.timezone_known and self.sufficient_history


@dataclass
class _Analysis:
    """Internal: one pass over a user's touch_history, shared by every
    public method so readiness and the hour histogram are never computed
    from two different reads of the same data."""

    tz: Any
    hour_counts: list[int] = field(default_factory=lambda: [0] * 24)
    total_touches: int = 0
    distinct_local_days: int = 0

    @property
    def timezone_known(self) -> bool:
        return self.tz is not None

    @property
    def sufficient_history(self) -> bool:
        return (
            self.total_touches >= MIN_TOUCHES_FOR_MODEL
            and self.distinct_local_days >= MIN_DISTINCT_LOCAL_DAYS
        )

    @property
    def ready(self) -> bool:
        return self.timezone_known and self.sufficient_history


class EngagementWindowModel:
    """Per-user learned high/low-activity hour model, read-only over
    core.session_time's touch_history + timezone.

    Local only (same isolation as the data it reads); no network, no
    background work — every method is a synchronous read + a bit of
    arithmetic over at most TOUCH_HISTORY_MAX_ENTRIES timestamps.
    """

    def __init__(self, persistence: LocalPersistence | None) -> None:
        self._persistence = persistence

    def readiness(self, user_id: str) -> WindowModelReadiness:
        """Both gates for this user (see WindowModelReadiness)."""
        a = self._analyze(user_id)
        return WindowModelReadiness(
            timezone_known=a.timezone_known,
            sufficient_history=a.sufficient_history,
            touch_count=a.total_touches,
            distinct_local_days=a.distinct_local_days,
        )

    def is_open_window(
        self,
        user_id: str,
        now: datetime,
        *,
        mid_session: bool = False,
        activity_context: dict[str, Any] | None = None,
        audience_context: dict[str, Any] | None = None,
    ) -> bool:
        """True when ``now`` falls inside this user's learned high-activity
        hour-of-day window.

        ``activity_context`` / ``audience_context`` are reserved for future
        sensor input (Tier E) — see module docstring; they have no effect
        yet.

        A live touch is its own proof of an open window: ``mid_session=True``
        always returns True, checked before readiness or wall-clock time.
        Otherwise, while either readiness gate is unmet (cold start), this
        never guesses from wall-clock time alone and returns False.
        """
        if mid_session:
            return True
        a = self._analyze(user_id)
        if not a.ready:
            return False
        local_hour = _ensure_aware_utc(now).astimezone(a.tz).hour
        share = a.hour_counts[local_hour] / a.total_touches
        return share >= OPEN_WINDOW_MIN_SHARE

    def is_learned_low_activity(self, user_id: str, now: datetime) -> bool:
        """True when ``now`` falls inside an hour this user has historically
        never or rarely touched the system.

        Cold start (either readiness gate unmet) returns False, not True —
        absence of evidence is not evidence of low activity, and claiming
        "rare" with no history would be exactly the baked-in default this
        model must not make (see module docstring).
        """
        a = self._analyze(user_id)
        if not a.ready:
            return False
        local_hour = _ensure_aware_utc(now).astimezone(a.tz).hour
        share = a.hour_counts[local_hour] / a.total_touches
        return share <= LOW_ACTIVITY_MAX_SHARE

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self, user_id: str) -> SessionTimeState:
        return load_session_time(self._persistence, user_id)

    def _analyze(self, user_id: str) -> _Analysis:
        """One pass over touch_history: hour-of-day histogram (localized,
        only meaningful once a timezone resolves) + distinct-day count
        (localized when possible, UTC-day best-effort otherwise — a
        diagnostic count only, not itself used for windowing).

        Aggregates by hour-of-day across all days rather than slicing by
        day-of-week as well: at the minimum data volume that clears
        sufficient_history (8 touches / 4 days), a 7x24 day-of-week grid
        would be far too sparse to mean anything, and pretending otherwise
        would be its own kind of baked-in guess. Hour-of-day-only is the
        honest model at this data volume.
        """
        state = self._load(user_id)
        tz = _resolve_zoneinfo(state.timezone)
        hour_counts = [0] * 24
        days: set[date] = set()
        total = 0
        for ts in state.touch_history:
            dt = _parse_iso_utc(ts)
            if dt is None:
                continue
            local_dt = dt.astimezone(tz) if tz is not None else dt
            days.add(local_dt.date())
            total += 1
            if tz is not None:
                hour_counts[local_dt.hour] += 1
        return _Analysis(
            tz=tz,
            hour_counts=hour_counts,
            total_touches=total,
            distinct_local_days=len(days),
        )
