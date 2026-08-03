"""
test_engagement_window.py
==========================

Per-user learned activity-window model (Phase 2 step 2): cold start never
guesses a wall-clock default, readiness needs both a known timezone and
history spread across enough distinct days, and once ready the model is
per-user, not a global heuristic.

Run::

    $env:PYTHONPATH = "."
    python tests/test_engagement_window.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.engagement_window import (  # noqa: E402
    MIN_DISTINCT_LOCAL_DAYS,
    MIN_TOUCHES_FOR_MODEL,
    EngagementWindowModel,
)
from core.session_time import set_timezone, touch_turn  # noqa: E402
from persistence import LocalPersistence  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kwargs: float) -> None:
        self.t = self.t + timedelta(**kwargs)


def _seed_touches(store, uid, *, base_day: datetime, hours: list[int], days: int) -> None:
    """Record ``len(hours)`` touches per day, for ``days`` distinct days,
    at the given UTC hours (used as UTC == local since these users are set
    to the "UTC" timezone — see module docstring on why that sidesteps DST
    entirely for a deterministic test). ``base_day`` must be midnight."""
    for d in range(days):
        for h in hours:
            clock = _Clock(base_day + timedelta(days=d, hours=h))
            touch_turn(store, uid, now_fn=clock)


def main() -> int:
    print("=" * 70)
    print("ENGAGEMENT WINDOW MODEL")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_engwin_"))
    try:
        store = LocalPersistence(tmp)
        model = EngagementWindowModel(store)
        base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # Scenarios 4 & 5 + 6: cold start
        # ------------------------------------------------------------
        cold_uid = "cold_start_user"
        # A couple of touches only — well under MIN_TOUCHES_FOR_MODEL.
        _seed_touches(store, cold_uid, base_day=base, hours=[19], days=2)
        now_evening = base + timedelta(days=10, hours=19, minutes=30)

        check(
            "cold start: mid_session=True opens regardless of wall clock",
            model.is_open_window(cold_uid, now_evening, mid_session=True) is True,
        )
        check(
            "cold start: mid_session=False closes regardless of wall clock",
            model.is_open_window(cold_uid, now_evening, mid_session=False) is False,
        )
        check(
            "cold start: never claims learned low-activity either",
            model.is_learned_low_activity(cold_uid, now_evening) is False,
        )
        cold_readiness = model.readiness(cold_uid)
        check(
            "cold start: readiness not ready with too little history",
            cold_readiness.ready is False,
            str(cold_readiness),
        )

        # Sufficient touch count but no stored timezone at all.
        no_tz_uid = "no_timezone_user"
        _seed_touches(store, no_tz_uid, base_day=base, hours=[19, 20, 21], days=10)
        no_tz_readiness = model.readiness(no_tz_uid)
        check(
            "30+ touches, no timezone: timezone_known False",
            no_tz_readiness.timezone_known is False,
            str(no_tz_readiness),
        )
        check(
            "30+ touches, no timezone: touch count alone does not unlock model",
            no_tz_readiness.ready is False,
            str(no_tz_readiness),
        )
        check(
            "30+ touches, no timezone: still cold-start is_open_window",
            model.is_open_window(no_tz_uid, base + timedelta(days=20, hours=19, minutes=30))
            is False,
        )
        check(
            "30+ touches, no timezone: mid_session still opens it",
            model.is_open_window(
                no_tz_uid,
                base + timedelta(days=20, hours=3),
                mid_session=True,
            )
            is True,
        )

        # Many touches, but all crammed into a single evening/day: count
        # alone (>= MIN_TOUCHES_FOR_MODEL) still isn't a daily rhythm.
        one_day_uid = "one_evening_user"
        set_timezone(store, one_day_uid, "UTC")
        for m in range(0, 20 * 3, 3):
            clock = _Clock(base + timedelta(minutes=m, hours=19))
            touch_turn(store, one_day_uid, now_fn=clock)
        one_day_readiness = model.readiness(one_day_uid)
        check(
            "20 touches in one evening: distinct_local_days below the gate",
            one_day_readiness.distinct_local_days < MIN_DISTINCT_LOCAL_DAYS,
            str(one_day_readiness),
        )
        check(
            "20 touches in one evening: not ready despite touch count",
            one_day_readiness.ready is False,
            str(one_day_readiness),
        )

        # ------------------------------------------------------------
        # Scenarios 1, 2, 7: full model once both gates are met
        # ------------------------------------------------------------
        evening_uid = "evening_user_a"
        set_timezone(store, evening_uid, "UTC")
        _seed_touches(store, evening_uid, base_day=base, hours=[19, 20], days=6)

        evening_readiness = model.readiness(evening_uid)
        check(
            "evening user: both gates satisfied",
            evening_readiness.ready is True,
            str(evening_readiness),
        )
        check(
            "evening user: at least MIN_TOUCHES_FOR_MODEL touches",
            evening_readiness.touch_count >= MIN_TOUCHES_FOR_MODEL,
            str(evening_readiness),
        )
        check(
            "evening user: at least MIN_DISTINCT_LOCAL_DAYS distinct days",
            evening_readiness.distinct_local_days >= MIN_DISTINCT_LOCAL_DAYS,
            str(evening_readiness),
        )

        open_check_time = base + timedelta(days=30, hours=19, minutes=45)
        check(
            "evening user: 7:45pm inside learned 7-9pm window -> open",
            model.is_open_window(evening_uid, open_check_time) is True,
        )

        low_activity_time = base + timedelta(days=30, hours=3)
        check(
            "evening user: 3am (zero historical touches) -> not open",
            model.is_open_window(evening_uid, low_activity_time) is False,
        )
        check(
            "evening user: 3am (zero historical touches) -> learned low activity",
            model.is_learned_low_activity(evening_uid, low_activity_time) is True,
        )
        check(
            "evening user: 7:45pm is not flagged learned-low-activity",
            model.is_learned_low_activity(evening_uid, open_check_time) is False,
        )

        # ------------------------------------------------------------
        # Scenario 3: per-user, not a global heuristic
        # ------------------------------------------------------------
        morning_uid = "morning_user_b"
        set_timezone(store, morning_uid, "UTC")
        _seed_touches(store, morning_uid, base_day=base, hours=[8, 9], days=6)
        check(
            "morning user: readiness satisfied",
            model.readiness(morning_uid).ready is True,
        )

        same_wall_clock = base + timedelta(days=40, hours=8, minutes=30)
        check(
            "morning user open at 8:30am (their learned window)",
            model.is_open_window(morning_uid, same_wall_clock) is True,
        )
        # Reuse evening_uid at the exact same wall-clock instant.
        check(
            "evening user closed at that same 8:30am instant",
            model.is_open_window(evening_uid, same_wall_clock) is False,
        )

        same_wall_clock_pm = base + timedelta(days=40, hours=19, minutes=30)
        check(
            "evening user open at 7:30pm (their learned window)",
            model.is_open_window(evening_uid, same_wall_clock_pm) is True,
        )
        check(
            "morning user closed at that same 7:30pm instant",
            model.is_open_window(morning_uid, same_wall_clock_pm) is False,
        )

    except Exception as e:
        check(f"suite raised: {e}", False)
        import traceback

        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
