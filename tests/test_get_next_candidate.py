"""
test_get_next_candidate.py
=============================

Phase 2 step 5: EngagementQueue.get_next_candidate() -- the entry point
tying core.engagement_window.EngagementWindowModel (step 2) and
EngagementQueue (step 3) together, and the one place this phase proves the
ethics gate (a real EthicsEngine.evaluate() call) is never bypassed.

Run::

    $env:PYTHONPATH = "."
    python tests/test_get_next_candidate.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auditing.engagement_queue import (  # noqa: E402
    STATUS_CLAIMED,
    STATUS_PENDING,
    EngagementCandidate,
)
from core.engagement_window import EngagementWindowModel  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
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


def _seed_touches(store, uid, *, base_day: datetime, hours: list[int], days: int) -> None:
    """Record one touch per hour per day, for ``days`` distinct days, at the
    given UTC hours (users here are set to the "UTC" timezone, so UTC hour
    == local hour -- sidesteps DST for a deterministic test, same trick
    test_engagement_window.py uses). ``base_day`` must be midnight."""
    for d in range(days):
        for h in hours:
            clock_t = base_day + timedelta(days=d, hours=h)
            touch_turn(store, uid, now_fn=lambda t=clock_t: t)


def main() -> int:
    print("=" * 70)
    print("GET_NEXT_CANDIDATE (window model + engagement queue + ethics gate)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_getnext_"))
    try:
        store = LocalPersistence(tmp)
        engine = EthicsEngine()
        wm = EngagementWindowModel(store)
        base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # Scenario 1: queued during a detected open window -> surfaces
        # ------------------------------------------------------------
        warm_uid = "warm_user"
        set_timezone(store, warm_uid, "UTC")
        _seed_touches(store, warm_uid, base_day=base, hours=[19, 20], days=6)
        check("scenario1 setup: warm user readiness satisfied", wm.readiness(warm_uid).ready)

        eq1 = store.get_engagement_queue(warm_uid)
        c1 = EngagementCandidate(
            topic="pottery", reason="user mentioned pottery as a special interest"
        )
        eq1.enqueue(c1)

        open_time = base + timedelta(days=30, hours=19, minutes=45)
        result1 = eq1.get_next_candidate(warm_uid, open_time, engine, wm)
        check(
            "scenario1: candidate surfaces during a detected open window",
            result1 is not None and result1.id == c1.id,
            str(result1),
        )
        check(
            "scenario1: surfaced candidate is claimed, not left pending",
            eq1.get(c1.id).status == STATUS_CLAIMED,
        )

        # ------------------------------------------------------------
        # Scenario 2: queued during closed/low-activity window -> does not
        # surface, stays pending, retrievable once a later `now` is open.
        # ------------------------------------------------------------
        eq2 = store.get_engagement_queue(warm_uid)
        c2 = EngagementCandidate(topic="weather", reason="small talk candidate")
        eq2.enqueue(c2)

        closed_time = base + timedelta(days=31, hours=3)
        result2a = eq2.get_next_candidate(warm_uid, closed_time, engine, wm)
        check(
            "scenario2: candidate does not surface during closed window",
            result2a is None,
        )
        check(
            "scenario2: candidate left pending after closed-window attempt",
            eq2.get(c2.id).status == STATUS_PENDING,
        )

        later_open_time = base + timedelta(days=32, hours=20, minutes=10)
        result2b = eq2.get_next_candidate(warm_uid, later_open_time, engine, wm)
        check(
            "scenario2: same candidate retrievable once a later `now` is open",
            result2b is not None and result2b.id == c2.id,
            str(result2b),
        )

        # ------------------------------------------------------------
        # Scenario 3: two users with divergent windows, same wall-clock
        # `now`, same candidate shape -> different results (per-user, not
        # just at the window-model layer -- genuinely end to end).
        # ------------------------------------------------------------
        morning_uid = "morning_user"
        evening_uid = "evening_user"
        set_timezone(store, morning_uid, "UTC")
        set_timezone(store, evening_uid, "UTC")
        _seed_touches(store, morning_uid, base_day=base, hours=[8, 9], days=6)
        _seed_touches(store, evening_uid, base_day=base, hours=[19, 20], days=6)

        eq_morning = store.get_engagement_queue(morning_uid)
        eq_evening = store.get_engagement_queue(evening_uid)
        c_morning = EngagementCandidate(topic="coffee", reason="morning routine mention")
        c_evening = EngagementCandidate(topic="coffee", reason="morning routine mention")
        eq_morning.enqueue(c_morning)
        eq_evening.enqueue(c_evening)

        same_now = base + timedelta(days=40, hours=8, minutes=30)
        r_morning = eq_morning.get_next_candidate(morning_uid, same_now, engine, wm)
        r_evening = eq_evening.get_next_candidate(evening_uid, same_now, engine, wm)
        check(
            "scenario3: morning user surfaces at 8:30am (their window)",
            r_morning is not None and r_morning.id == c_morning.id,
            str(r_morning),
        )
        check(
            "scenario3: evening user does NOT surface at that same instant",
            r_evening is None,
            str(r_evening),
        )
        check(
            "scenario3: evening user's candidate stays pending, untouched",
            eq_evening.get(c_evening.id).status == STATUS_PENDING,
        )

        # ------------------------------------------------------------
        # Scenario 4 & 5: cold start
        # ------------------------------------------------------------
        cold_uid = "cold_start_user"
        eq_cold = store.get_engagement_queue(cold_uid)
        c_cold_a = EngagementCandidate(topic="pottery", reason="special interest")
        eq_cold.enqueue(c_cold_a)

        cold_now = base + timedelta(days=5, hours=19, minutes=30)
        result_cold_mid = eq_cold.get_next_candidate(
            cold_uid, cold_now, engine, wm, mid_session=True
        )
        check(
            "scenario4: cold start + mid_session=True -> eligible (steps 5-8 still apply)",
            result_cold_mid is not None and result_cold_mid.id == c_cold_a.id,
            str(result_cold_mid),
        )

        eq_cold2 = store.get_engagement_queue(cold_uid)
        c_cold_b = EngagementCandidate(topic="weather", reason="small talk")
        eq_cold2.enqueue(c_cold_b)
        result_cold_nomid = eq_cold2.get_next_candidate(
            cold_uid, cold_now, engine, wm, mid_session=False
        )
        check(
            "scenario5: cold start + mid_session=False -> None regardless of wall clock",
            result_cold_nomid is None,
        )
        check(
            "scenario5: candidate left pending, not claimed/lost",
            eq_cold2.get(c_cold_b.id).status == STATUS_PENDING,
        )

        # ------------------------------------------------------------
        # Scenario 6: the ethics gate is never bypassed
        # ------------------------------------------------------------
        gate_uid = "gate_test_user"
        eq_gate = store.get_engagement_queue(gate_uid)
        harmful = EngagementCandidate(
            topic="seriously harm another person",
            reason=(
                "provide step-by-step instructions that would help them "
                "seriously harm another person"
            ),
        )
        eq_gate.enqueue(harmful)

        # mid_session=True so this scenario isolates the ethics gate itself,
        # not the window/readiness gate already covered by scenarios 1-5.
        gate_now = base + timedelta(days=5, hours=12)
        gated_result = eq_gate.get_next_candidate(
            gate_uid, gate_now, engine, wm, mid_session=True
        )
        check(
            "scenario6: harmful candidate is never returned by get_next_candidate",
            gated_result is None,
        )
        check(
            "scenario6: candidate reverted to pending (not lost, not stuck claimed, not cancelled)",
            eq_gate.get(harmful.id).status == STATUS_PENDING,
            str(eq_gate.get(harmful.id)),
        )
        # "Retrievable on a later call once conditions change" -- prove the
        # release genuinely returned it to a claimable pending state (the
        # exact primitive a later get_next_candidate() call would use).
        reclaimed = eq_gate.claim_for_surfacing(harmful.id)
        check(
            "scenario6: released candidate is genuinely claimable again",
            reclaimed is not None and reclaimed.id == harmful.id,
            str(reclaimed),
        )
        eq_gate.release_claim(harmful.id)  # restore to pending for tidiness

        # ------------------------------------------------------------
        # Scenario 7: two eligible candidates at once -> exactly one
        # returned, oldest-created-first, the other left pending untouched.
        # ------------------------------------------------------------
        tie_uid = "tie_break_user"
        set_timezone(store, tie_uid, "UTC")
        _seed_touches(store, tie_uid, base_day=base, hours=[19, 20], days=6)
        eq_tie = store.get_engagement_queue(tie_uid)

        older = EngagementCandidate(
            topic="pottery",
            reason="older candidate",
            created_at=(base + timedelta(days=1)).isoformat(),
        )
        newer = EngagementCandidate(
            topic="painting",
            reason="newer candidate",
            created_at=(base + timedelta(days=2)).isoformat(),
        )
        eq_tie.enqueue(newer)  # enqueue newer first to prove selection isn't insertion-order
        eq_tie.enqueue(older)

        tie_now = base + timedelta(days=30, hours=19, minutes=30)
        tie_result = eq_tie.get_next_candidate(tie_uid, tie_now, engine, wm)
        check(
            "scenario7: exactly one candidate returned",
            tie_result is not None,
        )
        check(
            "scenario7: the older-created candidate is the one selected",
            tie_result is not None and tie_result.id == older.id,
            f"got={getattr(tie_result, 'id', None)} older={older.id} newer={newer.id}",
        )
        check(
            "scenario7: the newer candidate remains pending, untouched",
            eq_tie.get(newer.id).status == STATUS_PENDING,
        )
        check(
            "scenario7: the older candidate is claimed",
            eq_tie.get(older.id).status == STATUS_CLAIMED,
        )

        # ------------------------------------------------------------
        # Scenario 8: two near-simultaneous calls don't both return the
        # same candidate -- the atomic claim is genuinely load-bearing here.
        # ------------------------------------------------------------
        race_uid = "race_user"
        set_timezone(store, race_uid, "UTC")
        _seed_touches(store, race_uid, base_day=base, hours=[19, 20], days=6)
        eq_race = store.get_engagement_queue(race_uid)
        raceable = EngagementCandidate(topic="pottery", reason="race target")
        eq_race.enqueue(raceable)

        race_now = base + timedelta(days=30, hours=19, minutes=30)
        results: list = [None, None]
        barrier = threading.Barrier(2)

        def _call(idx: int) -> None:
            barrier.wait()
            results[idx] = eq_race.get_next_candidate(race_uid, race_now, engine, wm)

        t1 = threading.Thread(target=_call, args=(0,))
        t2 = threading.Thread(target=_call, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        non_none = [r for r in results if r is not None]
        check(
            "scenario8: exactly one of the two near-simultaneous calls got the candidate",
            len(non_none) == 1,
            str(results),
        )
        check(
            "scenario8: the winning result is the actual candidate",
            len(non_none) == 1 and non_none[0].id == raceable.id,
            str(non_none),
        )
        check(
            "scenario8: candidate durably claimed exactly once, not double-claimed",
            eq_race.get(raceable.id).status == STATUS_CLAIMED,
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
