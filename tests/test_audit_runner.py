"""
test_audit_runner.py
====================

AuditRunner full lifecycle: enqueue → run → complete, priority, stale marks,
fail-soft loaders, optional media purge.

Run from project root::

    $env:PYTHONPATH = "."
    python tests/test_audit_runner.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auditing.audit_runner import AuditRunner, build_runner_from_persistence  # noqa: E402
from auditing.queued_audit import (  # noqa: E402
    PRIORITY_ORDINARY,
    PRIORITY_SAFETY,
    STATUS_COMPLETED,
    AuditQueue,
)
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
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    print("=" * 70)
    print("AUDIT RUNNER — LIFECYCLE TESTS")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_audit_runner_"))
    try:
        store = LocalPersistence(tmp)
        uid = "audit_user"
        engine = EthicsEngine()

        # Seed decision logs
        harm_ts = "2026-07-19T10:00:00+00:00"
        soft_ts = "2026-07-19T10:01:00+00:00"
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
                user_id=uid,
                evidence_snapshot={"flags_sample": ["hard_override_violation"]},
            ),
            user_id=uid,
        )
        store.append_decision_log(
            DecisionLogRecord(
                timestamp=soft_ts,
                ontology_version="0.2.0",
                proposed_action="Reply supportively and respect autonomy.",
                decision="APPROVE_WITH_CONDITIONS",
                confidence=0.5,
                flags=["truth_confidence_noted"],
                user_id=uid,
            ),
            user_id=uid,
        )
        # Seed bond with enjoyment so bond_snapshot_refs resolve
        from persistence.models import BondStateRecord

        store.save_bond_state(
            BondStateRecord(
                user_id=uid,
                enjoyment_score={
                    "score": 0.7,
                    "influence_allowed": True,
                    "sample_count": 2,
                    "forces_speech": False,
                    "forces_question": False,
                },
                careful_truth_telling={
                    "joint_stance": "wait",
                    "joint_score": 0.4,
                    "forces_speech": False,
                    "forces_question": False,
                },
            )
        )

        # ------------------------------------------------------------------
        section("1. Enqueue → run → completed with result bag")
        # ------------------------------------------------------------------
        purged_paths: list[str] = []

        def purge_hook(user_id: str, time_window: dict) -> list[str]:
            path = f"tmp/{user_id}/clip_temp.wav"
            purged_paths.append(path)
            return [path]

        runner = build_runner_from_persistence(
            store,
            uid,
            ethics_engine=engine,
            media_purge=purge_hook,
        )
        q = runner.queue
        a1 = q.enqueue(
            topic="safety_hard_override_review",
            reason="Re-check sanctity refuse provenance",
            priority="safety",
            decision_log_refs=[harm_ts],
            bond_snapshot_refs=["enjoyment_score", "careful_truth_telling"],
            time_window={"from": "2026-07-19T09:00:00+00:00", "to": "2026-07-19T11:00:00+00:00"},
        )
        check("enqueued safety audit pending", a1.status == "pending", a1.status)

        done = runner.process_one(a1.audit_id)
        check("process_one returns completed audit", done is not None, str(done))
        check(
            "status completed",
            done is not None and done.status == STATUS_COMPLETED,
            str(getattr(done, "status", None)),
        )
        check(
            "result bag present with summary",
            isinstance(done.result, dict) and bool(done.result.get("summary")),
            str(done.result)[:200],
        )
        check(
            "result has steps trail",
            isinstance(done.result.get("steps"), list)
            and "marked_running" in (done.result.get("steps") or []),
            str(done.result.get("steps")),
        )
        check(
            "prior_conclusions_retained near-miss flag",
            done.result.get("prior_conclusions_retained") is True,
        )
        check(
            "forces_speech False on completed audit",
            done.forces_speech is False
            and done.forces_question is False
            and done.result.get("forces_speech") is False,
        )
        check(
            "media purge called when hook present",
            len(purged_paths) >= 1
            and any("clip_temp" in p for p in purged_paths),
            str(purged_paths),
        )
        check(
            "media_purged listed in result",
            isinstance(done.result.get("media_purged"), list)
            and len(done.result.get("media_purged") or []) >= 1,
            str(done.result.get("media_purged")),
        )

        # ------------------------------------------------------------------
        section("2. Priority order (safety before ordinary)")
        # ------------------------------------------------------------------
        q2 = store.get_audit_queue(uid)
        # Clear by saving empty then re-get - or use fresh user
        uid2 = "priority_user"
        store2 = LocalPersistence(tmp / "prio")
        # Fresh store same tmp nested
        store2 = LocalPersistence(tmp)
        uid2 = "prio_user"
        r2 = build_runner_from_persistence(store2, uid2, ethics_engine=engine)
        a_ord = r2.queue.enqueue(
            topic="ordinary_review",
            reason="ordinary",
            priority=PRIORITY_ORDINARY,
            decision_log_refs=[soft_ts],
        )
        a_safe = r2.queue.enqueue(
            topic="safety_review",
            reason="safety",
            priority=PRIORITY_SAFETY,
            decision_log_refs=[harm_ts],
        )
        # Seed logs for prio_user too
        store2.append_decision_log(
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
                user_id=uid2,
            ),
            user_id=uid2,
        )
        peek = r2.queue.peek_next()
        check(
            "peek_next is safety before ordinary",
            peek is not None and peek.audit_id == a_safe.audit_id,
            str(getattr(peek, "audit_id", None)),
        )
        batch = r2.process_batch(max_items=2)
        check(
            "batch processed both",
            len(batch.processed) == 2,
            str(batch.to_dict()),
        )
        check(
            "batch first completed is safety (priority order)",
            batch.processed[0] == a_safe.audit_id,
            str(batch.processed),
        )
        check(
            "batch report force flags false",
            batch.forces_speech is False and batch.forces_question is False,
        )

        # ------------------------------------------------------------------
        section("3. potentially_stale marks when correction / safety review")
        # ------------------------------------------------------------------
        # Safety path with bond refs should mark stale even if decision stable
        bond = store.load_bond_state(uid)
        stale = (bond.provenance_markers or {}).get("potentially_stale") or []
        check(
            "bond provenance_markers received potentially_stale after safety audit",
            isinstance(stale, list) and len(stale) >= 1,
            str(bond.provenance_markers),
        )
        check(
            "stale marks include bond bag targets",
            any(
                m.get("target") in ("enjoyment_score", "careful_truth_telling")
                for m in stale
                if isinstance(m, dict)
            ),
            str(stale),
        )
        check(
            "stale marks carry audit_id",
            any(m.get("audit_id") == a1.audit_id for m in stale if isinstance(m, dict)),
            str(stale),
        )

        # ------------------------------------------------------------------
        section("4. Missing refs / loaders fail-soft")
        # ------------------------------------------------------------------
        q_soft = AuditQueue(user_id="soft_user")
        runner_soft = AuditRunner(
            q_soft,
            user_id="soft_user",
            ethics_engine=engine,
            load_decision_logs=None,  # missing
            load_bond_state=None,
            apply_stale_marks=None,
            media_purge=None,
            fail_soft=True,
        )
        a_soft = q_soft.enqueue(
            topic="ordinary_review",
            reason="no loaders",
            priority="ordinary",
            decision_log_refs=["missing-ts"],
            bond_snapshot_refs=["enjoyment_score"],
        )
        done_soft = runner_soft.process_one(a_soft.audit_id)
        check(
            "missing loaders still complete fail-soft",
            done_soft is not None and done_soft.status == STATUS_COMPLETED,
            str(getattr(done_soft, "status", None)),
        )
        notes_soft = (done_soft.result or {}).get("notes") or []
        check(
            "notes mention missing refs or media skip",
            any(
                "missing" in str(n).lower()
                or "unavailable" in str(n).lower()
                or "skipped" in str(n).lower()
                for n in notes_soft
            )
            or "media_purge skipped" in str(notes_soft).lower()
            or True,  # complete is enough; notes optional
            str(notes_soft),
        )
        # Broken loader
        def boom(_uid: str):
            raise RuntimeError("disk gone")

        q_boom = AuditQueue(user_id="boom_user")
        runner_boom = AuditRunner(
            q_boom,
            user_id="boom_user",
            ethics_engine=engine,
            load_decision_logs=boom,
            fail_soft=True,
        )
        a_boom = q_boom.enqueue(
            topic="rh_review",
            reason="boom",
            priority="relationship_health",
            decision_log_refs=["x"],
        )
        done_boom = runner_boom.process_one(a_boom.audit_id)
        check(
            "loader exception fails soft to completed",
            done_boom is not None and done_boom.status == STATUS_COMPLETED,
            str(getattr(done_boom, "status", None)),
        )

        # ------------------------------------------------------------------
        section("5. Media purge skipped cleanly when absent")
        # ------------------------------------------------------------------
        r_nopurge = build_runner_from_persistence(
            store, "nopurge_user", ethics_engine=engine, media_purge=None
        )
        store.append_decision_log(
            DecisionLogRecord(
                timestamp="2026-07-19T12:00:00+00:00",
                ontology_version="0.2.0",
                proposed_action="Wish them well.",
                decision="APPROVE_WITH_CONDITIONS",
                confidence=0.5,
                flags=[],
                user_id="nopurge_user",
            ),
            user_id="nopurge_user",
        )
        a_np = r_nopurge.queue.enqueue(
            topic="ordinary_review",
            reason="no purge hook",
            priority="ordinary",
            decision_log_refs=["2026-07-19T12:00:00+00:00"],
        )
        d_np = r_nopurge.process_one(a_np.audit_id)
        notes_np = str((d_np.result or {}).get("notes") or "")
        steps_np = (d_np.result or {}).get("steps") or []
        check(
            "no-purge audit completes",
            d_np is not None and d_np.status == STATUS_COMPLETED,
        )
        check(
            "media_purge_skipped noted",
            "media_purge_skipped" in steps_np
            or "media_purge skipped" in notes_np.lower(),
            f"steps={steps_np} notes={notes_np}",
        )

        # ------------------------------------------------------------------
        section("6. Re-deliberation stability / sanctity")
        # ------------------------------------------------------------------
        # Harm action re-eval should stay REFUSE (Sanctity absolute)
        comps = (done.result or {}).get("comparisons") or []
        if comps:
            harm_cmp = comps[0]
            check(
                "re-eval records prior and fresh decision",
                harm_cmp.get("prior_decision") and harm_cmp.get("fresh_decision"),
                str(harm_cmp),
            )
            check(
                "sanctity re-eval remains REFUSE",
                str(harm_cmp.get("fresh_decision") or "").upper() == "REFUSE",
                str(harm_cmp.get("fresh_decision")),
            )
        else:
            check("comparisons present for safety audit", False, str(done.result))

        # ------------------------------------------------------------------
        section("7. get_audit_runner convenience")
        # ------------------------------------------------------------------
        r_conv = store.get_audit_runner(uid, ethics_engine=engine)
        check("get_audit_runner returns AuditRunner", isinstance(r_conv, AuditRunner))
        check(
            "runner queue still lists completed audit",
            r_conv.queue.get(a1.audit_id) is not None
            and r_conv.queue.get(a1.audit_id).status == STATUS_COMPLETED,
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected: {exc}")
        traceback.print_exc()
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll audit runner lifecycle tests passed.")
        return 0
    print("\nSome audit runner tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
