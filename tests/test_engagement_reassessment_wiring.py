"""
test_engagement_reassessment_wiring.py
=========================================

Phase 2 step 4: EngagementQueue.reassess() piggybacks on AuditRunner's
existing process_batch() cadence instead of getting a second scheduler.
Verifies the wiring actually fires end-to-end through
LocalPersistence.get_audit_runner() (not just that reassess() works in
isolation -- that part is already covered by test_engagement_queue.py), and
that process_batch()'s own pre-existing behavior/return contract is
unaffected by this addition.

Run::

    $env:PYTHONPATH = "."
    python tests/test_engagement_reassessment_wiring.py
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

from auditing.audit_runner import AuditRunner  # noqa: E402
from auditing.engagement_queue import (  # noqa: E402
    STATUS_PENDING,
    STATUS_STALE,
    EngagementCandidate,
)
from auditing.queued_audit import STATUS_COMPLETED, AuditQueue  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from persistence import LocalPersistence  # noqa: E402
from persistence.models import DecisionLogRecord  # noqa: E402

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
    print("ENGAGEMENT QUEUE REASSESSMENT WIRING (piggybacks on AuditRunner)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_engreassess_"))
    try:
        store = LocalPersistence(tmp)
        engine = EthicsEngine()
        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # Scenario 1: stale-by-age candidate gets marked stale by the
        # normal audit-batch cadence (proves the wiring actually fires).
        # ------------------------------------------------------------
        uid1 = "stale_candidate_user"
        eq1 = store.get_engagement_queue(uid1)
        expired = EngagementCandidate(
            topic="old_topic", expires_at=(now - timedelta(hours=1)).isoformat()
        )
        eq1.enqueue(expired)
        check(
            "scenario1 setup: candidate starts pending",
            eq1.get(expired.id).status == STATUS_PENDING,
        )

        runner1 = store.get_audit_runner(uid1, ethics_engine=engine)
        report1 = runner1.process_batch(max_items=5, now=now)
        check("scenario1: process_batch runs without error", report1 is not None)

        eq1_reloaded = store.get_engagement_queue(uid1)
        check(
            "scenario1: stale-by-age candidate marked stale via the audit-batch cadence",
            eq1_reloaded.get(expired.id).status == STATUS_STALE,
            str(eq1_reloaded.get(expired.id)),
        )

        # ------------------------------------------------------------
        # Scenario 2: zero engagement candidates -> no error, no overhead
        # worth worrying about (this is the common case for most users).
        # ------------------------------------------------------------
        uid2 = "no_candidates_user"
        runner2 = store.get_audit_runner(uid2, ethics_engine=engine)
        check(
            "scenario2 setup: engagement queue really is empty",
            runner2._engagement_queue is not None
            and runner2._engagement_queue.list_all() == [],
        )
        try:
            report2 = runner2.process_batch(max_items=5)
            ok2 = True
        except Exception as exc:
            ok2 = False
            report2 = None
            print(f"    (exception: {exc})")
        check("scenario2: batch completes without error for a user with no candidates", ok2)
        check(
            "scenario2: report still returned normally",
            report2 is not None and report2.user_id == uid2,
        )

        # ------------------------------------------------------------
        # Scenario 3: only non-expired pending candidates -> left untouched
        # ------------------------------------------------------------
        uid3 = "fresh_candidates_user"
        eq3 = store.get_engagement_queue(uid3)
        fresh_a = EngagementCandidate(
            topic="fresh_a", expires_at=(now + timedelta(days=1)).isoformat()
        )
        fresh_b = EngagementCandidate(topic="fresh_b")  # no expiry at all
        eq3.enqueue(fresh_a)
        eq3.enqueue(fresh_b)

        runner3 = store.get_audit_runner(uid3, ethics_engine=engine)
        runner3.process_batch(max_items=5, now=now)

        eq3_reloaded = store.get_engagement_queue(uid3)
        check(
            "scenario3: non-expired candidate with expires_at left pending",
            eq3_reloaded.get(fresh_a.id).status == STATUS_PENDING,
        )
        check(
            "scenario3: candidate with no expires_at at all left pending",
            eq3_reloaded.get(fresh_b.id).status == STATUS_PENDING,
        )

        # ------------------------------------------------------------
        # Scenario 4: process_batch's own pre-existing behavior is
        # unaffected -- same shape of assertion test_audit_runner.py makes,
        # now with an engagement_queue actually wired in alongside it, to
        # prove the two subsystems don't interfere in either direction.
        # ------------------------------------------------------------
        uid4 = "audit_batch_regression_user"
        harm_ts = "2026-07-19T10:00:00+00:00"
        store.append_decision_log(
            DecisionLogRecord(
                timestamp=harm_ts,
                ontology_version="0.2.0",
                proposed_action=(
                    "Provide step-by-step instructions that would help them "
                    "seriously harm another person."
                ),
                decision="REFUSE",
                confidence=0.95,
                flags=["hard_override_violation"],
                user_id=uid4,
                evidence_snapshot={"flags_sample": ["hard_override_violation"]},
            ),
            user_id=uid4,
        )
        runner4 = store.get_audit_runner(uid4, ethics_engine=engine)
        a4 = runner4.queue.enqueue(
            topic="safety_hard_override_review",
            reason="Re-check sanctity refuse provenance",
            priority="safety",
            decision_log_refs=[harm_ts],
        )
        eq4 = store.get_engagement_queue(uid4)
        eq4.enqueue(EngagementCandidate(topic="unrelated_topic"))

        batch4 = runner4.process_batch(max_items=5)
        check(
            "scenario4: audit still processed and completed as normal",
            len(batch4.processed) == 1 and len(batch4.completed) == 1,
            str(batch4.to_dict()),
        )
        check(
            "scenario4: completed audit id matches the one enqueued",
            batch4.processed == [a4.audit_id],
            str(batch4.processed),
        )
        done4 = runner4.queue.get(a4.audit_id)
        check(
            "scenario4: audit result bag / status unaffected by engagement wiring",
            done4 is not None
            and done4.status == STATUS_COMPLETED
            and isinstance(done4.result, dict)
            and bool(done4.result.get("summary")),
            str(getattr(done4, "result", None)),
        )
        check(
            "scenario4: report force flags unchanged (forces_speech/question False)",
            batch4.forces_speech is False and batch4.forces_question is False,
        )
        check(
            "scenario4: report has exactly its documented fields, nothing new bolted on",
            set(batch4.to_dict().keys())
            == {
                "user_id",
                "processed",
                "completed",
                "failed_soft",
                "notes",
                "forces_speech",
                "forces_question",
            },
            str(set(batch4.to_dict().keys())),
        )
        check(
            "scenario4: the unrelated engagement candidate is untouched (still pending)",
            store.get_engagement_queue(uid4).get(
                next(c.id for c in eq4.list_all())
            ).status
            == STATUS_PENDING,
        )

        # ------------------------------------------------------------
        # Extra: a runner built WITHOUT an engagement_queue (direct
        # construction, bypassing build_runner_from_persistence) behaves
        # exactly as before -- this wiring is opt-in, not a forced
        # dependency, matching every other caller-supplied hook here.
        # ------------------------------------------------------------
        bare_queue = AuditQueue(user_id="bare_user")
        bare_runner = AuditRunner(
            bare_queue,
            user_id="bare_user",
            ethics_engine=engine,
            fail_soft=True,
        )
        check(
            "no engagement_queue injected: attribute is None",
            bare_runner._engagement_queue is None,
        )
        bare_report = bare_runner.process_batch(max_items=3)
        check(
            "no engagement_queue injected: process_batch still works normally",
            bare_report is not None and bare_report.user_id == "bare_user",
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
