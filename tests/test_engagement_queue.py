"""
test_engagement_queue.py
=========================

EngagementCandidate / EngagementQueue (Phase 2 step 3): enqueue + dedupe,
cap/eviction (mirrors auditing.queued_audit.AuditQueue's real policy),
age-based reassess(), atomic claim_for_surfacing(), cancel_matching()
scoping, and record_reception() writing into core.enjoyment_score's real
evidence trail.

Run::

    $env:PYTHONPATH = "."
    python tests/test_engagement_queue.py
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

from auditing.engagement_queue import (  # noqa: E402
    RECEPTION_EVIDENCE_LABEL,
    STATUS_CANCELLED,
    STATUS_CLAIMED,
    STATUS_PENDING,
    STATUS_STALE,
    STATUS_SURFACED,
    EngagementCandidate,
)
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


def main() -> int:
    print("=" * 70)
    print("ENGAGEMENT QUEUE")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_engqueue_"))
    try:
        store = LocalPersistence(tmp)
        base_t = datetime(2026, 7, 1, tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # Scenario 1: enqueue -> persisted round-trip
        # ------------------------------------------------------------
        uid1 = "roundtrip_user"
        q1 = store.get_engagement_queue(uid1)
        c1 = EngagementCandidate(
            topic="pottery",
            reason="user mentioned pottery as a special interest last session",
            source="observation_candidates",
            relevance_notes="raised unprompted twice",
        )
        q1.enqueue(c1)

        q1_reloaded = store.get_engagement_queue(uid1)
        found = q1_reloaded.get(c1.id)
        check("round-trip: candidate persisted", found is not None)
        check(
            "round-trip: fields survive reload",
            found is not None
            and found.topic == "pottery"
            and found.source == "observation_candidates"
            and found.status == STATUS_PENDING
            and found.relevance_notes == "raised unprompted twice",
            str(found),
        )

        # ------------------------------------------------------------
        # Scenario 2: re-enqueue same id -> no duplicate
        # ------------------------------------------------------------
        c1_updated = EngagementCandidate(
            id=c1.id,
            topic="pottery",
            reason="updated reason after a second mention",
            source="observation_candidates",
        )
        q1.enqueue(c1_updated)
        check(
            "re-enqueue same id: no duplicate entry",
            len(q1.list_all()) == 1,
            str(len(q1.list_all())),
        )
        check(
            "re-enqueue same id: fields updated in place",
            q1.get(c1.id).reason == "updated reason after a second mention",
        )

        # ------------------------------------------------------------
        # Scenario 3: cap / eviction mirrors AuditQueue's real policy
        # ------------------------------------------------------------
        # max_entries has a real floor of 10 (mirrors AuditQueue's own
        # `max(10, int(max_entries))`) -- requesting less still yields a
        # cap of 10, so these fixtures deliberately exceed 10, not 5.
        cap_uid = "cap_test_user"
        cap_q = store.get_engagement_queue(cap_uid, max_entries=10)

        # 3a: pending is always fully kept when it doesn't itself exceed the
        # cap; remaining budget goes to non-pending, most-recently-created
        # first (mirrors AuditQueue._save's updated_at-recency rule, using
        # created_at since EngagementCandidate has no per-status timestamp).
        pending_items = [
            EngagementCandidate(
                topic=f"pending_{i}",
                created_at=(base_t + timedelta(minutes=i)).isoformat(),
            )
            for i in range(4)
        ]
        nonpending_items = []
        statuses_cycle = [STATUS_STALE, STATUS_CANCELLED, STATUS_SURFACED, STATUS_STALE]
        for i in range(8):
            c = EngagementCandidate(
                topic=f"nonpending_{i}",
                created_at=(base_t + timedelta(hours=1, minutes=i)).isoformat(),
            )
            c.status = statuses_cycle[i % len(statuses_cycle)]
            nonpending_items.append(c)

        for c in pending_items + nonpending_items:
            cap_q.enqueue(c)

        check(
            "cap: in-memory items not trimmed on the live object"
            " (AuditQueue's own quirk, copied as-is)",
            len(cap_q.list_all()) == 12,
            str(len(cap_q.list_all())),
        )

        cap_reloaded = store.get_engagement_queue(cap_uid, max_entries=10)
        persisted_ids = {c.id for c in cap_reloaded.list_all()}
        check(
            "cap: persisted/reloaded view capped at max_entries (floor 10)",
            len(persisted_ids) == 10,
            str(len(persisted_ids)),
        )
        check(
            "cap: all 4 pending candidates survive (pending kept first)",
            all(c.id in persisted_ids for c in pending_items),
            str(persisted_ids),
        )
        # Remaining 6 of 10 slots go to the 6 most-recently-created non-pending.
        expected_survivors = {c.id for c in nonpending_items[-6:]}
        actual_nonpending_survivors = persisted_ids - {c.id for c in pending_items}
        check(
            "cap: remaining budget goes to most-recently-created non-pending",
            actual_nonpending_survivors == expected_survivors,
            f"expected={expected_survivors} actual={actual_nonpending_survivors}",
        )

        # 3b: when pending alone exceeds the cap, only the cap survives, kept
        # in insertion order -- no non-pending item gets in at all.
        overflow_uid = "cap_overflow_user"
        overflow_q = store.get_engagement_queue(overflow_uid, max_entries=10)
        overflow_pending = [
            EngagementCandidate(
                topic=f"overflow_{i}",
                created_at=(base_t + timedelta(minutes=i)).isoformat(),
            )
            for i in range(15)
        ]
        for c in overflow_pending:
            overflow_q.enqueue(c)
        overflow_reloaded = store.get_engagement_queue(overflow_uid, max_entries=10)
        overflow_ids = [c.id for c in overflow_reloaded.list_all()]
        check(
            "cap overflow: capped at max_entries even when all pending",
            len(overflow_ids) == 10,
            str(len(overflow_ids)),
        )
        check(
            "cap overflow: survivors are the first 10 inserted, in order",
            overflow_ids == [c.id for c in overflow_pending[:10]],
            str(overflow_ids),
        )

        # ------------------------------------------------------------
        # Scenario 4: reassess() age-based expiry only
        # ------------------------------------------------------------
        reassess_uid = "reassess_user"
        rq = store.get_engagement_queue(reassess_uid)
        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

        expired_pending = EngagementCandidate(
            topic="expired", expires_at=(now - timedelta(hours=1)).isoformat()
        )
        fresh_pending = EngagementCandidate(
            topic="fresh", expires_at=(now + timedelta(hours=1)).isoformat()
        )
        no_expiry_pending = EngagementCandidate(topic="no_expiry")
        already_cancelled = EngagementCandidate(
            topic="already_cancelled",
            expires_at=(now - timedelta(hours=1)).isoformat(),
        )
        already_cancelled.status = STATUS_CANCELLED
        already_surfaced = EngagementCandidate(
            topic="already_surfaced",
            expires_at=(now - timedelta(hours=1)).isoformat(),
        )
        already_surfaced.status = STATUS_SURFACED

        for c in (
            expired_pending,
            fresh_pending,
            no_expiry_pending,
            already_cancelled,
            already_surfaced,
        ):
            rq.enqueue(c)

        changed = rq.reassess(now)
        check(
            "reassess: past-expiry pending -> stale",
            rq.get(expired_pending.id).status == STATUS_STALE,
        )
        check(
            "reassess: not-yet-expired pending left alone",
            rq.get(fresh_pending.id).status == STATUS_PENDING,
        )
        check(
            "reassess: no expires_at at all left alone",
            rq.get(no_expiry_pending.id).status == STATUS_PENDING,
        )
        check(
            "reassess: already-cancelled with past expiry untouched",
            rq.get(already_cancelled.id).status == STATUS_CANCELLED,
        )
        check(
            "reassess: already-surfaced with past expiry untouched",
            rq.get(already_surfaced.id).status == STATUS_SURFACED,
        )
        check(
            "reassess: returns only the candidate it actually changed",
            [c.id for c in changed] == [expired_pending.id],
            str([c.id for c in changed]),
        )

        changed_again = rq.reassess(now)
        check(
            "reassess: safe to call repeatedly, no-op once nothing is eligible",
            changed_again == [],
        )

        # ------------------------------------------------------------
        # Scenario 5: claim_for_surfacing atomic transition
        # ------------------------------------------------------------
        claim_uid = "claim_user"
        clq = store.get_engagement_queue(claim_uid)
        claimable = EngagementCandidate(topic="claim_me")
        clq.enqueue(claimable)

        claimed = clq.claim_for_surfacing(claimable.id)
        check(
            "claim: first call transitions pending -> claimed and returns it",
            claimed is not None and claimed.status == STATUS_CLAIMED,
            str(claimed),
        )
        second = clq.claim_for_surfacing(claimable.id)
        check("claim: second call on the same id returns None", second is None)
        check(
            "claim: candidate is durably claimed (not just the returned copy)",
            clq.get(claimable.id).status == STATUS_CLAIMED,
        )
        check(
            "claim: unknown id returns None",
            clq.claim_for_surfacing("nonexistent_id") is None,
        )

        # ------------------------------------------------------------
        # Scenario 6: cancel_matching scoping
        # ------------------------------------------------------------
        cancel_uid = "cancel_user"
        cq = store.get_engagement_queue(cancel_uid)
        pottery = EngagementCandidate(topic="pottery")
        weather = EngagementCandidate(topic="weather")
        pottery2 = EngagementCandidate(topic="pottery")
        for c in (pottery, weather, pottery2):
            cq.enqueue(c)

        cancelled_topic = cq.cancel_matching({"topic": "pottery"}, reason="user asked to stop")
        check(
            "cancel_matching topic scope: only matching-topic candidates cancelled",
            {c.id for c in cancelled_topic} == {pottery.id, pottery2.id},
            str([c.id for c in cancelled_topic]),
        )
        check(
            "cancel_matching topic scope: unrelated pending candidate untouched",
            cq.get(weather.id).status == STATUS_PENDING,
        )
        check(
            "cancel_matching topic scope: matched candidates cancelled, not deleted",
            cq.get(pottery.id) is not None and cq.get(pottery.id).status == STATUS_CANCELLED,
        )

        wide_uid = "cancel_wide_user"
        wq = store.get_engagement_queue(wide_uid)
        a = EngagementCandidate(topic="a")
        b = EngagementCandidate(topic="b")
        for c in (a, b):
            wq.enqueue(c)
        cancelled_wide = wq.cancel_matching(None)
        check(
            "cancel_matching queue-wide (no scope): every pending candidate cancelled",
            {c.id for c in cancelled_wide} == {a.id, b.id},
            str([c.id for c in cancelled_wide]),
        )
        check(
            "cancel_matching queue-wide: statuses durably updated",
            wq.get(a.id).status == STATUS_CANCELLED and wq.get(b.id).status == STATUS_CANCELLED,
        )

        # ------------------------------------------------------------
        # Scenario 7: record_reception -> real enjoyment_score evidence trail
        # ------------------------------------------------------------
        recv_uid = "reception_user"
        rcq = store.get_engagement_queue(recv_uid)
        seed_topic = EngagementCandidate(topic="pottery", source="observation_candidates")
        rcq.enqueue(seed_topic)

        result = rcq.record_reception(
            seed_topic.id,
            {"positive_language": True, "continued": True},
        )
        label = f"{RECEPTION_EVIDENCE_LABEL}:{seed_topic.id}"
        check(
            "record_reception: evidence trail carries the labeled entry",
            any(e.startswith(label) for e in result.evidence),
            str(result.evidence),
        )
        check(
            "record_reception: traceable back to this exact candidate id",
            any(seed_topic.id in e for e in result.evidence),
            str(result.evidence),
        )
        check(
            "record_reception: candidate status untouched by reception",
            rcq.get(seed_topic.id).status == STATUS_PENDING,
        )
        check(
            "record_reception: went through the real update path (score moved, sampled)",
            result.sample_count == 1 and result.score != 0.5,
            f"sample_count={result.sample_count} score={result.score}",
        )

        # A second, different candidate's reception must not collide.
        other_topic = EngagementCandidate(topic="weather", source="observation_candidates")
        rcq.enqueue(other_topic)
        result2 = rcq.record_reception(
            other_topic.id,
            {"positive_language": True},
            previous_enjoyment=result,
        )
        label2 = f"{RECEPTION_EVIDENCE_LABEL}:{other_topic.id}"
        check(
            "record_reception: distinct candidates get distinct traceable entries",
            any(e.startswith(label) for e in result2.evidence)
            and any(e.startswith(label2) for e in result2.evidence),
            str(result2.evidence),
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
