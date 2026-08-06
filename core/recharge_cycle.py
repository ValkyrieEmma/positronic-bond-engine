"""
recharge_cycle.py
===================

Awake/Asleep state for "is the system currently free to do maintenance
work at all" — a different question from
``core.engagement_window.EngagementWindowModel.is_open_window()`` ("is this
specific user likely receptive right now"). This module answers the
scheduling-side question AGENTS.md already names: "The queue is reassessed
on every full recharge audit cycle" (AGENTS.md's Proactive value delivery
section) — ``auditing.audit_runner.AuditRunner.process_batch()`` (which
also drives ``EngagementQueue.reassess()`` as of Phase 2 step 4) has no
automatic trigger in the product today; it only runs when something
explicitly calls it. This module is that trigger's gate, built around the
existing "recharge cycle" language rather than invented fresh, and modeled
the same way it will actually work once embodied (a robot on its charging
dock, not being spoken to) rather than a throwaway local-machine timer hack.

Two states
----------
- **Awake (interacting).** Default state whenever a user is actively in a
  live session. Maintenance work does not run here.
- **Asleep / Recharging.** The state maintenance work is allowed to run in.
  For the *automatic* audit/reassessment cadence, entry is gated by three
  checks in ``is_recharge_window_open()``, all of which must hold:

  1. Within the configured daily recharge window (default ~5am, start hour
     + duration — not a single instant, so a session that happens to start
     at 5:03am doesn't miss it; see ``set_recharge_window()``).
  2. Not paused (``set_pause()`` — an explicit, person-set "hold off" signal
     for "I know I'll be gaming/streaming outside the normal window", not
     an attempt to auto-detect GPU contention; the honest mechanism here is
     asking, not guessing).
  3. No live session in progress for the user in question.

  If any gate fails, the cycle is honestly skipped and logged as skipped
  (see ``record_cycle_result()``) — never silently retried more
  aggressively, never forced through.

Trigger source: swappable by design
-------------------------------------
``is_recharge_window_open()`` is the one small entry point — "is now a
valid recharge window for this user, and should the batch run." Today's
caller is ``examples/run_recharge_cycle.py``, a small dedicated script
meant to be invoked once a day by an OS-level scheduler (Windows Task
Scheduler on this machine — see that script's own docstring for the exact
registration command). Tomorrow's embodied caller is a charging-dock
sensor event asking the same question. Neither
``AuditRunner.process_batch()`` nor ``EngagementQueue.reassess()`` needs to
know or care which kind of caller triggered them — this module's job ends
at "should the batch run," not "how did we get asked."

Time-critical mid-day bypass: deliberately not designed here. The gate
needs a bypass seam for something genuinely time-critical to force the
batch to run immediately regardless of Awake/Asleep state — but the
classification logic for "what counts as time-critical" is its own design
pass, explicitly parked. No caller for that seam exists yet; that is
correct for this change, not an oversight.

Manual "go to sleep" — an emergency safety control, not just scheduling
--------------------------------------------------------------------------
``is_sleep_command()`` / ``go_to_sleep()`` let a person force the system
into Asleep immediately, on a natural-language command, as a safety
measure independent of the three automatic gates above (opposite
direction from the time-critical bypass: that forces the batch to run
*despite* Asleep; manual sleep forces Asleep *despite* whatever's
happening — both out of scope for each other). Decided:

- **Bypasses the ethics gate entirely.** Not a decision
  ``EthicsEngine.evaluate()`` approves/holds/refuses — a safety control
  must not be gateable by the system it backstops. Not a new precedent:
  the automatic recharge-state gate above already sits outside
  ``evaluate()`` entirely too.
- **Deterministic phrase-matching, not ContextualJudge** — the same reason
  the Sanctity-of-Life override's *enforcement* is hardcoded/unconditional
  while its *interpretation* is contextual (see
  ``core/contextual_judgment.py``): a safety command can't depend on a
  model call that might time out or return an ambiguous verdict. Biased
  toward recall over precision — see ``is_sleep_command()``'s docstring
  for exactly what is and isn't matched, and why a false positive is the
  acceptable failure mode here (an unnecessary pause) while a false
  negative is not (it defeats the feature).
- **Waking is implicit, never a separate command** — ``maybe_wake()`` is
  called on every ordinary live turn; Awake is simply the default state
  whenever a live session is active, so the system wakes itself the
  moment the next real interaction happens. See ``api/interaction.py``'s
  wiring for the exact turn-processing order this depends on.
- **The sleep action is a swappable seam**, mirroring the trigger-source
  seam above — today: release local VRAM (see
  ``core.content_provider.release_vram()``); tomorrow (embodied): navigate
  to dock, or sleep mode if unreachable. Same call shape, output side
  instead of input side.

Persistence follows the same per-user pattern ``core/session_time.py``
already uses: a compact bag under ``UserSettings.preferences``, loaded via
``LocalPersistence.load_settings`` / ``save_settings`` — no dedicated
store/file, matching how small, session-adjacent state is already handled
here (as opposed to ``EngagementCandidateStore``'s own file, which fits a
growing list of records rather than one small state bag).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.content_provider import ProviderConfig, release_vram
from core.session_time import SESSION_STALE_SECONDS, get_timezone, load_session_time
from persistence.local_persistence import LocalPersistence

RECHARGE_STATE_KEY = "recharge_cycle"

# Default daily recharge window: a configurable stand-in, not a hardcoded
# instant -- see set_recharge_window(). 5am / 3h is a reasonable default
# for a single-operator machine; every field is per-user and overridable.
DEFAULT_WINDOW_START_HOUR = 5
DEFAULT_WINDOW_DURATION_HOURS = 3.0

_MIN_WINDOW_DURATION_HOURS = 0.25
_MAX_WINDOW_DURATION_HOURS = 12.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Naive datetimes are treated as UTC, matching the convention already
    established in core/session_time.py and core/engagement_window.py."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt(dt: datetime) -> str:
    return _ensure_aware_utc(dt).astimezone(timezone.utc).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    """Parse a stored ISO timestamp; aware UTC on success, None otherwise.

    Narrow, matching reader for this module's own stored format (mirrors
    core.session_time's and auditing.engagement_queue's own private
    _parse_iso, each kept local rather than importing a private symbol
    across modules — see those modules for the same note).
    """
    if not s or not str(s).strip():
        return None
    raw = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _ensure_aware_utc(dt).astimezone(timezone.utc)


def _resolve_zoneinfo(tz_name: str | None) -> Any:
    """Best-effort ZoneInfo for a stored timezone name; None if unresolvable
    on this machine right now. Mirrors core.engagement_window's own helper
    of the same name (kept local for the same reason — see that module)."""
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
class RechargeState:
    """Durable per-user Awake/Asleep + recharge-window configuration.

    Attributes:
        paused: Explicit person-set "hold off the automatic cycle" signal.
        paused_since / paused_reason: When and why, for inspection.
        window_start_hour: Local hour (0-23) the recharge window opens.
        window_duration_hours: How long the window stays open.
        asleep: True after a manual "go to sleep" command (or, in principle,
            any future caller of go_to_sleep()); cleared by maybe_wake().
            NOT consulted by is_recharge_window_open() -- the automatic
            gate and the manual emergency control are deliberately
            decoupled (see module docstring).
        asleep_since / asleep_reason: When and why the system went Asleep.
        woke_at: ISO timestamp of the most recent implicit wake, informational.
        last_cycle_at / last_cycle_ran / last_cycle_reasons: The most recent
            automatic-gate check's outcome, so a skipped cycle is durably
            logged (not just printed and lost) -- see record_cycle_result().
        schema_version: Structure version.
    """

    paused: bool = False
    paused_since: str | None = None
    paused_reason: str = ""
    window_start_hour: int = DEFAULT_WINDOW_START_HOUR
    window_duration_hours: float = DEFAULT_WINDOW_DURATION_HOURS
    asleep: bool = False
    asleep_since: str | None = None
    asleep_reason: str = ""
    woke_at: str | None = None
    last_cycle_at: str | None = None
    last_cycle_ran: bool | None = None
    last_cycle_reasons: list[str] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "paused": bool(self.paused),
            "paused_since": self.paused_since,
            "paused_reason": str(self.paused_reason or "")[:200],
            "window_start_hour": max(0, min(23, int(self.window_start_hour))),
            "window_duration_hours": max(
                _MIN_WINDOW_DURATION_HOURS,
                min(_MAX_WINDOW_DURATION_HOURS, float(self.window_duration_hours)),
            ),
            "asleep": bool(self.asleep),
            "asleep_since": self.asleep_since,
            "asleep_reason": str(self.asleep_reason or "")[:200],
            "woke_at": self.woke_at,
            "last_cycle_at": self.last_cycle_at,
            "last_cycle_ran": self.last_cycle_ran,
            "last_cycle_reasons": [str(r)[:200] for r in (self.last_cycle_reasons or [])][
                :8
            ],
            "schema_version": int(self.schema_version),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RechargeState:
        if not isinstance(data, dict):
            return cls()
        return cls(
            paused=bool(data.get("paused", False)),
            paused_since=str(data["paused_since"]) if data.get("paused_since") else None,
            paused_reason=str(data.get("paused_reason") or "")[:200],
            window_start_hour=max(
                0, min(23, int(data.get("window_start_hour") or DEFAULT_WINDOW_START_HOUR))
            ),
            window_duration_hours=max(
                _MIN_WINDOW_DURATION_HOURS,
                min(
                    _MAX_WINDOW_DURATION_HOURS,
                    float(
                        data.get("window_duration_hours") or DEFAULT_WINDOW_DURATION_HOURS
                    ),
                ),
            ),
            asleep=bool(data.get("asleep", False)),
            asleep_since=str(data["asleep_since"]) if data.get("asleep_since") else None,
            asleep_reason=str(data.get("asleep_reason") or "")[:200],
            woke_at=str(data["woke_at"]) if data.get("woke_at") else None,
            last_cycle_at=str(data["last_cycle_at"]) if data.get("last_cycle_at") else None,
            last_cycle_ran=(
                bool(data["last_cycle_ran"]) if data.get("last_cycle_ran") is not None else None
            ),
            last_cycle_reasons=[
                str(r)[:200] for r in (data.get("last_cycle_reasons") or [])
            ][:8],
            schema_version=int(data.get("schema_version") or 1),
        )


def load_recharge_state(
    persistence: LocalPersistence | None, user_id: str
) -> RechargeState:
    if persistence is None:
        return RechargeState()
    try:
        settings = persistence.load_settings(user_id)
        raw = (settings.preferences or {}).get(RECHARGE_STATE_KEY)
        return RechargeState.from_dict(raw if isinstance(raw, dict) else None)
    except Exception:
        return RechargeState()


def _save_recharge_state(
    persistence: LocalPersistence, user_id: str, state: RechargeState
) -> None:
    settings = persistence.load_settings(user_id)
    prefs = dict(settings.preferences or {})
    prefs[RECHARGE_STATE_KEY] = state.to_dict()
    settings.preferences = prefs
    settings.user_id = user_id
    persistence.save_settings(settings)


# ---------------------------------------------------------------------------
# Pause / window configuration
# ---------------------------------------------------------------------------


def set_pause(
    persistence: LocalPersistence | None,
    user_id: str,
    paused: bool,
    *,
    reason: str = "",
) -> RechargeState:
    """Set or clear the explicit "hold off the automatic cycle" signal."""
    state = load_recharge_state(persistence, user_id)
    state.paused = bool(paused)
    state.paused_since = _utc_now_iso() if paused else None
    state.paused_reason = str(reason or "")[:200] if paused else ""
    if persistence is not None:
        _save_recharge_state(persistence, user_id, state)
    return state


def is_paused(persistence: LocalPersistence | None, user_id: str) -> bool:
    return load_recharge_state(persistence, user_id).paused


def set_recharge_window(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    start_hour: int,
    duration_hours: float,
) -> RechargeState:
    """Configure this user's daily recharge window (local time, via
    core.session_time's stored timezone -- see is_recharge_window_open())."""
    state = load_recharge_state(persistence, user_id)
    state.window_start_hour = max(0, min(23, int(start_hour)))
    state.window_duration_hours = max(
        _MIN_WINDOW_DURATION_HOURS, min(_MAX_WINDOW_DURATION_HOURS, float(duration_hours))
    )
    if persistence is not None:
        _save_recharge_state(persistence, user_id, state)
    return state


# ---------------------------------------------------------------------------
# The automatic gate
# ---------------------------------------------------------------------------


@dataclass
class RechargeGateResult:
    """Inspectable outcome of one is_recharge_window_open() check."""

    user_id: str
    checked_at: str
    within_window: bool
    not_paused: bool
    no_live_session: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def should_run(self) -> bool:
        return self.within_window and self.not_paused and self.no_live_session

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "checked_at": self.checked_at,
            "within_window": self.within_window,
            "not_paused": self.not_paused,
            "no_live_session": self.no_live_session,
            "should_run": self.should_run,
            "reasons": list(self.reasons),
        }


def is_recharge_window_open(
    persistence: LocalPersistence | None,
    user_id: str,
    now: datetime,
) -> RechargeGateResult:
    """The one entry point: is now a valid recharge window for this user,
    and should the automatic batch (AuditRunner.process_batch(), which
    also drives EngagementQueue.reassess()) run? See module docstring for
    the three gates and why each is checked the way it is.

    Swappable trigger source: this function does not know or care who is
    asking -- a daily scheduled script today, a charging-dock sensor event
    tomorrow. It only answers the question.
    """
    now = _ensure_aware_utc(now)
    state = load_recharge_state(persistence, user_id)
    reasons: list[str] = []

    # Gate 1: within the recharge window. Needs the user's local time of
    # day -- reuses core.session_time's stored timezone (the single source
    # of truth core.engagement_window.EngagementWindowModel already uses
    # for the same reason) rather than a second, redundant timezone field.
    tz = _resolve_zoneinfo(get_timezone(persistence, user_id))
    if tz is None:
        within_window = False
        reasons.append(
            "timezone unknown or unresolvable on this machine -- local time "
            "of day cannot be confirmed, so the recharge window cannot be "
            "confirmed open (conservative default; matches "
            "core.engagement_window's own cold-start posture rather than "
            "guessing a window from UTC)"
        )
    else:
        local_now = now.astimezone(tz)
        minute_of_day = local_now.hour * 60 + local_now.minute
        start = int(state.window_start_hour) * 60
        duration_min = max(0.0, float(state.window_duration_hours)) * 60
        end = start + duration_min
        if end <= 24 * 60:
            within_window = start <= minute_of_day < end
        else:
            # Window wraps past midnight (e.g. start=23, duration=4h).
            within_window = minute_of_day >= start or minute_of_day < (end - 24 * 60)
        if not within_window:
            reasons.append(
                f"outside recharge window (local time {local_now.strftime('%H:%M')}, "
                f"window is {state.window_start_hour:02d}:00 for "
                f"{state.window_duration_hours:g}h)"
            )

    # Gate 2: not paused.
    not_paused = not state.paused
    if not not_paused:
        reasons.append(
            "recharge cycle paused"
            + (f" ({state.paused_reason})" if state.paused_reason else "")
        )

    # Gate 3: no live session in progress. A scheduled/background trigger
    # has no in-memory session_context of its own to consult -- only
    # durable state survives between processes -- so this reuses
    # core.session_time.SESSION_STALE_SECONDS (the same threshold
    # touch_turn()/begin_session() already use to decide a session has
    # gone stale) against the persisted last_turn_at: if the most recent
    # real touch is more recent than that threshold, a live session is
    # presumed still in progress.
    session_state = load_session_time(persistence, user_id)
    last_turn = _parse_iso(session_state.last_turn_at)
    if last_turn is None:
        no_live_session = True
    else:
        idle_s = (now - last_turn).total_seconds()
        no_live_session = idle_s >= SESSION_STALE_SECONDS
        if not no_live_session:
            reasons.append(
                f"live session in progress (last touch {idle_s:.0f}s ago, "
                f"under the {SESSION_STALE_SECONDS}s staleness threshold)"
            )

    if within_window and not_paused and no_live_session:
        reasons.append("all three gates satisfied")

    return RechargeGateResult(
        user_id=user_id,
        checked_at=_fmt(now),
        within_window=within_window,
        not_paused=not_paused,
        no_live_session=no_live_session,
        reasons=reasons,
    )


def record_cycle_result(
    persistence: LocalPersistence | None,
    user_id: str,
    gate: RechargeGateResult,
    *,
    ran: bool,
) -> RechargeState:
    """Durably log why the most recent cycle ran or was skipped -- so a
    skipped cycle is inspectable later, not just printed to a console and
    lost. Callers (examples/run_recharge_cycle.py) call this after every
    check, whether or not the batch actually ran."""
    state = load_recharge_state(persistence, user_id)
    state.last_cycle_at = gate.checked_at
    state.last_cycle_ran = bool(ran)
    state.last_cycle_reasons = list(gate.reasons)[:8]
    if persistence is not None:
        _save_recharge_state(persistence, user_id, state)
    return state


# ---------------------------------------------------------------------------
# Time-critical mid-day bypass -- seam only, no classification logic yet.
# ---------------------------------------------------------------------------


def force_run_bypassing_recharge_gate(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    reason: str,
) -> None:
    """Structural seam for a future time-critical bypass: something that
    needs the batch (or a scoped part of it) to run immediately regardless
    of Awake/Asleep state.

    Deliberately not implemented -- the classification logic for "what
    counts as time-critical" is its own design pass (see module
    docstring). No caller exists yet; that is correct for this change, not
    an oversight. Raises NotImplementedError rather than silently no-op'ing
    or silently approving, so an accidental call surfaces immediately
    instead of behaving unpredictably.
    """
    raise NotImplementedError(
        "Time-critical bypass classification is a separate, not-yet-designed "
        "pass (see core/recharge_cycle.py's module docstring). This seam is "
        "structurally present but intentionally has no caller and no logic "
        f"yet (reason given: {reason!r}, user_id={user_id!r})."
    )


# ---------------------------------------------------------------------------
# Manual "go to sleep" — emergency safety control
# ---------------------------------------------------------------------------

# Deterministic phrase patterns, biased toward recall over precision (see
# module docstring): a false-positive sleep trigger costs an unnecessary
# pause; a false negative defeats the feature. Anchored on imperative
# constructions ("go to sleep", "time to recharge", "sleep now", "power
# down") rather than bare topic words, which is what actually keeps this
# from firing on "I'm exhausted, this app puts me to sleep" (that sentence
# never contains "go" immediately before "sleep", nor "time to sleep", nor
# "sleep now", etc.) without needing a separate negative-match guard list.
# Known, accepted limitation: pure phrase matching cannot parse negation
# ("let's NOT go to sleep yet" would still match) -- an accepted
# false-positive per the recall-over-precision bias, not an oversight.
_SLEEP_COMMAND_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bgo\s+(?:to\s+)?sleep\b"),
    re.compile(r"\bgo\s+(?:to\s+)?(?:the\s+|your\s+)?(?:recharge|charging)\b"),
    re.compile(r"\bgo\s+(?:to\s+)?(?:the\s+|your\s+)?dock\b"),
    re.compile(r"\bgo\s+charge\b"),
    re.compile(r"\btime\s+to\s+(?:sleep|recharge)\b"),
    re.compile(r"\b(?:please\s+)?sleep\s+now\b"),
    re.compile(r"\brecharge\s+now\b"),
    re.compile(r"\bpower\s+down\b"),
]


def is_sleep_command(text: str) -> bool:
    """True when ``text`` deterministically matches an emergency
    "go to sleep" / "go recharge" style command.

    Tested against (see tests/test_recharge_cycle.py for the full set):
        Positive: "go to sleep", "go recharge", "please go to sleep now",
        "time to recharge", "go to your dock", "power down".
        Negative: "I'm exhausted, this app puts me to sleep" (the
        explicitly named case this must not trigger on), "I need to
        sleep", "I'm going to sleep soon", general mentions of being
        tired that never form an imperative "go ... sleep/recharge/dock/
        charge" or "... now" / "time to ..." construction.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(p.search(t) for p in _SLEEP_COMMAND_PATTERNS)


def go_to_sleep(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    reason: str = "manual_sleep_command",
    provider_config: ProviderConfig | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Force Asleep immediately and best-effort release local VRAM.

    Bypasses the automatic gate's three checks entirely -- this is the
    manual emergency control, not a request the recharge cycle evaluates
    (see module docstring). Callers (api/interaction.py) must invoke this
    *before* EthicsEngine.evaluate() or any content-provider call for the
    turn, not after -- a safety control must not be gateable by the system
    it backstops.

    Returns ``{"state": RechargeState, "vram_release": <release_vram()
    result dict>}``. Never raises -- the VRAM-release call is fail-soft by
    construction (see core.content_provider.release_vram()); a failed
    release still leaves the durable Asleep state set.
    """
    now = _ensure_aware_utc(now or _utc_now())
    state = load_recharge_state(persistence, user_id)
    state.asleep = True
    state.asleep_since = _fmt(now)
    state.asleep_reason = str(reason or "")[:200]
    state.woke_at = None
    if persistence is not None:
        _save_recharge_state(persistence, user_id, state)
    vram_result = release_vram(provider_config)
    return {"state": state, "vram_release": vram_result}


def maybe_wake(
    persistence: LocalPersistence | None,
    user_id: str,
    *,
    now: datetime | None = None,
) -> RechargeState:
    """Implicit wake: call on every ordinary live turn, before ordinary
    processing continues. If the user was Asleep, clears it and records the
    wake timestamp. No separate wake command exists or is needed -- Awake
    is simply the default state whenever a live session is active (see
    module docstring); this is what makes that true in the persisted state,
    not just true "by default" in the abstract.

    A no-op (no save call) when the user was already Awake, so this is
    cheap to call unconditionally on every turn.
    """
    now = _ensure_aware_utc(now or _utc_now())
    state = load_recharge_state(persistence, user_id)
    if not state.asleep:
        return state
    state.asleep = False
    state.asleep_since = None
    state.woke_at = _fmt(now)
    if persistence is not None:
        _save_recharge_state(persistence, user_id, state)
    return state


def is_asleep(persistence: LocalPersistence | None, user_id: str) -> bool:
    return load_recharge_state(persistence, user_id).asleep
