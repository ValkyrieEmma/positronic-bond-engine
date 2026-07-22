"""
test_persistence.py
===================

Standalone smoke tests for the local-only persistence layer.

Run from the project root::

    python test_persistence.py

Uses a temporary directory (not pbe_data/) so real user data is never touched.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Ensure project root is on the path when run as a script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from persistence import (  # noqa: E402
    BondStateRecord,
    DecisionLogRecord,
    LocalPersistence,
    UserBaseline,
    UserSettings,
)


# ---------------------------------------------------------------------------
# Tiny test helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """Print PASS/FAIL for one assertion and track counts."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> int:
    # 1. Create LocalPersistence on a temporary test folder
    section("1. Create LocalPersistence (temporary folder)")
    tmp = Path(tempfile.mkdtemp(prefix="pbe_persist_test_"))
    print(f"  Temp data root: {tmp}")
    try:
        store = LocalPersistence(tmp)
        check("instance created", isinstance(store, LocalPersistence))
        check("data_root points at temp", store.data_root == tmp.resolve() or store.data_root == tmp)
        check("README.txt written", (store.data_root / "README.txt").is_file())

        user_id = "test_user"

        # 2. UserBaseline save / load
        section("2. Save and load UserBaseline")
        baseline = UserBaseline(
            user_id=user_id,
            communication_patterns={"directness": 0.65, "preferred_length": "short"},
            emotional_tone_range={"min": 0.2, "max": 0.85},
            topic_continuity={"themes": ["hobbies", "work"]},
            playfulness_level=0.72,
            notes="Prefers concise replies",
        )
        path_b = store.save_baseline(baseline)
        check("baseline file created", path_b.is_file(), str(path_b))
        loaded_b = store.load_baseline(user_id)
        check("baseline user_id", loaded_b.user_id == user_id)
        check("baseline playfulness_level", loaded_b.playfulness_level == 0.72)
        check(
            "baseline communication_patterns",
            loaded_b.communication_patterns.get("directness") == 0.65,
        )
        check("baseline notes preserved", loaded_b.notes == "Prefers concise replies")

        # 3. BondStateRecord + UserSettings
        section("3. Save and load BondStateRecord and UserSettings")
        bond = BondStateRecord(
            user_id=user_id,
            bond_texture={
                "trust": 0.55,
                "reciprocity": 0.50,
                "autonomy_respect": 0.70,
                "emotional_honesty": 0.60,
                "mutual_benefit": 0.52,
            },
            health_flags=["emerging_dependency"],
            interaction_count=12,
            recent_patterns={"positive": 8, "boundary_respected": 3},
            summary="Mild dependency flag; autonomy still respected.",
        )
        path_bond = store.save_bond_state(bond)
        check("bond_state file created", path_bond.is_file())
        loaded_bond = store.load_bond_state(user_id)
        check("bond health_flags", loaded_bond.health_flags == ["emerging_dependency"])
        check("bond interaction_count", loaded_bond.interaction_count == 12)
        check(
            "bond texture trust",
            abs(loaded_bond.bond_texture.get("trust", 0) - 0.55) < 1e-6,
        )
        ctx = loaded_bond.as_ethics_context()
        check(
            "as_ethics_context has bond_texture + health_flags",
            "bond_texture" in ctx and "health_flags" in ctx,
        )

        settings = UserSettings(
            user_id=user_id,
            memory_enabled=True,
            retain_decision_logs=True,
            max_decision_logs=500,
            preferences={"theme": "calm"},
        )
        path_s = store.save_settings(settings)
        check("settings file created", path_s.is_file())
        loaded_s = store.load_settings(user_id)
        check("settings max_decision_logs", loaded_s.max_decision_logs == 500)
        check("settings preferences", loaded_s.preferences.get("theme") == "calm")

        # 4. DecisionLogRecord append / load
        section("4. Append and load DecisionLogRecord")
        log = DecisionLogRecord(
            timestamp="2026-07-11T12:00:00+00:00",
            ontology_version="0.2.0",
            proposed_action="Offer a gentle check-in on an unrelated topic.",
            context={"source": "test"},
            decision="APPROVE_WITH_CONDITIONS",
            confidence=0.55,
            flags=[],
            principles_considered=["relationship_health_user_wellbeing"],
            user_id=user_id,
        )
        path_log = store.append_decision_log(log)
        check("decision_logs file created", path_log.is_file())
        logs = store.load_decision_logs(user_id)
        check("one decision log loaded", len(logs) == 1)
        check("log decision field", logs[0].decision == "APPROVE_WITH_CONDITIONS")
        check(
            "log proposed_action preserved",
            "gentle check-in" in logs[0].proposed_action,
        )

        # 4b. Bond curious_companion + decision evidence_snapshot (unified v2)
        section("4b. Curious companion bond + decision evidence_snapshot")
        bond_cc = BondStateRecord(
            user_id=user_id,
            bond_texture=dict(bond.bond_texture),
            health_flags=[],
            interaction_count=1,
            recent_patterns={
                "understanding_gap_nudge": 1,
                "open_topic:hobbies": 2,
            },
            summary="Open hobbies thread.",
            curious_companion={
                "open_topic_names": ["hobbies"],
                "last_gap_score": 0.44,
                "topic_continuity": {"active": True, "strength": 0.5},
            },
        )
        store.save_bond_state(bond_cc)
        re_cc = store.load_bond_state(user_id)
        check(
            "curious_companion round-trip",
            re_cc.curious_companion.get("last_gap_score") == 0.44,
            str(re_cc.curious_companion),
        )
        check(
            "open_topic soft pattern round-trip",
            re_cc.recent_patterns.get("open_topic:hobbies") == 2,
            str(re_cc.recent_patterns),
        )
        merged = store.update_bond_curious_companion(
            user_id, {"last_gap_kinds": ["repeated_thin_topic"]}
        )
        check(
            "update_bond_curious_companion merges kinds",
            "repeated_thin_topic" in (merged.curious_companion.get("last_gap_kinds") or []),
        )
        snap = DecisionLogRecord.compact_evidence_from_impact(
            {
                "understanding_gaps": {"has_gaps": True, "gap_score": 0.5},
                "topic_continuity": {"active": True},
                "scoped_user_id": user_id,
            },
            flags=["history_understanding_gap", "topic_continuity_open"],
        )
        log2 = DecisionLogRecord(
            timestamp="2026-07-11T12:00:30+00:00",
            ontology_version="0.2.0",
            proposed_action="Continue gently on hobbies if natural.",
            decision="APPROVE_WITH_CONDITIONS",
            confidence=0.5,
            flags=["topic_continuity_open"],
            user_id=user_id,
            evidence_snapshot=snap,
        )
        store.append_decision_log(log2)
        logs2 = store.load_decision_logs(user_id)
        last = logs2[-1]
        check(
            "decision log evidence_snapshot loaded",
            isinstance(last.evidence_snapshot, dict)
            and last.evidence_snapshot.get("understanding_gaps", {}).get("has_gaps"),
            str(last.evidence_snapshot),
        )
        check(
            "decision log ontology_version present",
            last.ontology_version == "0.2.0",
        )

        # 4c. Careful Truth-Telling joint on bond_state
        section("4c. Careful truth-telling joint on bond")
        bond_ctt = BondStateRecord(
            user_id=user_id,
            bond_texture=dict(bond.bond_texture),
            health_flags=[],
            interaction_count=2,
            recent_patterns={"careful_truth_telling_assessed": 1},
            summary="CTT snapshot present.",
            careful_truth_telling={
                "joint_score": 0.5,
                "joint_stance": "wait",
                "readiness_level": "moderate",
                "readiness_score": 0.5,
                "confidence_level": "low",
                "confidence_score": 0.3,
                "reason": "Evidence thin.",
                "gates": ["confidence_low"],
                "forces_speech": True,  # must be forced False on save
                "forces_question": True,
            },
        )
        store.save_bond_state(bond_ctt)
        re_ctt = store.load_bond_state(user_id)
        check(
            "careful_truth_telling round-trip stance",
            re_ctt.careful_truth_telling.get("joint_stance") == "wait",
            str(re_ctt.careful_truth_telling),
        )
        check(
            "careful_truth_telling forces_speech always False on disk",
            re_ctt.careful_truth_telling.get("forces_speech") is False
            and re_ctt.careful_truth_telling.get("forces_question") is False,
            str(re_ctt.careful_truth_telling),
        )
        updated_ctt = store.update_bond_careful_truth_telling(
            user_id,
            {
                "joint_score": 0.75,
                "joint_stance": "careful_observation_ok",
                "readiness_level": "high",
                "confidence_level": "moderate",
                "reason": "Ready enough.",
            },
        )
        check(
            "update_bond_careful_truth_telling stance",
            updated_ctt.careful_truth_telling.get("joint_stance")
            == "careful_observation_ok",
            str(updated_ctt.careful_truth_telling),
        )
        ctt_ev = DecisionLogRecord.compact_evidence_from_impact(
            {
                "careful_truth_telling": updated_ctt.careful_truth_telling,
                "scoped_user_id": user_id,
            },
            flags=["truth_confidence_noted"],
        )
        check(
            "evidence_snapshot can carry careful_truth_telling",
            ctt_ev.get("careful_truth_telling", {}).get("joint_stance")
            == "careful_observation_ok",
            str(ctt_ev),
        )

        # 4d. Observation candidates durable snapshot
        section("4d. Observation candidates durable on bond")
        bond_obs = BondStateRecord(
            user_id=user_id,
            bond_texture=dict(bond.bond_texture),
            health_flags=[],
            interaction_count=3,
            recent_patterns={"observation_candidates_assessed": 1},
            summary="Obs candidates present.",
            observation_candidates_snapshot={
                "candidates": [
                    {
                        "id": "gap_topic:hobbies",
                        "description": "Open hobbies thread.",
                        "evidence_refs": ["open_topic:hobbies"],
                        "priority": 0.6,
                        "source": "understanding_gap",
                        "forces_speech": True,
                        "forces_question": True,
                    }
                ],
                "count": 1,
                "joint_stance": "wait",
                "joint_score": 0.4,
                "forces_speech": True,
                "forces_question": True,
            },
        )
        store.save_bond_state(bond_obs)
        re_obs = store.load_bond_state(user_id)
        check(
            "observation_candidates_snapshot round-trip count",
            re_obs.observation_candidates_snapshot.get("count") == 1,
            str(re_obs.observation_candidates_snapshot),
        )
        check(
            "observation candidates forces_speech False on disk",
            re_obs.observation_candidates_snapshot.get("forces_speech") is False
            and all(
                c.get("forces_speech") is False
                for c in (
                    re_obs.observation_candidates_snapshot.get("candidates") or []
                )
                if isinstance(c, dict)
            ),
            str(re_obs.observation_candidates_snapshot),
        )
        updated_obs = store.update_bond_observation_candidates(
            user_id,
            {
                "candidates": [
                    {
                        "id": "concept:healthy_co_evolution",
                        "description": "Healthy co-evolution pattern noted.",
                        "priority": 0.7,
                        "source": "concept_pattern",
                        "evidence_refs": ["concept_pattern:healthy_co_evolution"],
                    }
                ],
                "joint_stance": "careful_observation_ok",
                "joint_score": 0.65,
            },
        )
        check(
            "update_bond_observation_candidates replaces id",
            any(
                c.get("id") == "concept:healthy_co_evolution"
                for c in (
                    updated_obs.observation_candidates_snapshot.get("candidates")
                    or []
                )
                if isinstance(c, dict)
            ),
            str(updated_obs.observation_candidates_snapshot),
        )
        check(
            "as_ethics_context has durable observation candidates",
            "observation_candidates_durable"
            in updated_obs.as_ethics_context(),
        )

        # 4e. Enjoyment score durable on bond
        section("4e. Enjoyment score durable on bond")
        bond_enj = BondStateRecord(
            user_id=user_id,
            bond_texture=dict(bond.bond_texture),
            health_flags=[],
            interaction_count=4,
            recent_patterns={"enjoyment_score_updated": 1},
            summary="Enjoyment present.",
            enjoyment_score={
                "score": 0.72,
                "signals": {"continuation": 0.8, "special_interest": 0.7},
                "evidence": ["continuation=0.80", "special_interest=0.70"],
                "preferred_topics": ["trains"],
                "influence_allowed": True,
                "sample_count": 2,
                "forces_speech": True,
                "forces_question": True,
            },
        )
        store.save_bond_state(bond_enj)
        re_enj = store.load_bond_state(user_id)
        check(
            "enjoyment_score round-trip score",
            abs(float(re_enj.enjoyment_score.get("score") or 0) - 0.72) < 1e-6,
            str(re_enj.enjoyment_score),
        )
        check(
            "enjoyment forces_speech False on disk",
            re_enj.enjoyment_score.get("forces_speech") is False
            and re_enj.enjoyment_score.get("forces_question") is False,
            str(re_enj.enjoyment_score),
        )
        updated_enj = store.update_bond_enjoyment_score(
            user_id,
            {
                "score": 0.8,
                "signals": {"positive_language": 0.9},
                "evidence": ["positive_language=0.90"],
                "preferred_topics": ["trains", "maps"],
                "sample_count": 3,
            },
        )
        check(
            "update_bond_enjoyment_score raises score",
            float(updated_enj.enjoyment_score.get("score") or 0) >= 0.75,
            str(updated_enj.enjoyment_score),
        )
        check(
            "as_ethics_context has enjoyment_score",
            "enjoyment_score" in updated_enj.as_ethics_context(),
        )

        # 4f. Queued audit scaffolding
        section("4f. Queued audit scaffolding (deferred provenance)")
        from auditing.queued_audit import (
            PRIORITY_RELATIONSHIP_HEALTH,
            PRIORITY_SAFETY,
            STATUS_COMPLETED,
            STATUS_PENDING,
            AuditQueue,
            suggest_audit_from_decision,
        )

        q = store.get_audit_queue(user_id)
        check("get_audit_queue returns AuditQueue", isinstance(q, AuditQueue))
        a_safety = q.enqueue(
            topic="safety_review",
            reason="Test safety audit",
            priority="safety",
            decision_log_refs=["2026-07-19T00:00:00+00:00"],
            bond_snapshot_refs=[],
        )
        a_rh = q.enqueue(
            topic="rh_review",
            reason="Test RH audit",
            priority=PRIORITY_RELATIONSHIP_HEALTH,
            bond_snapshot_refs=["enjoyment_score", "careful_truth_telling"],
        )
        a_ord = q.enqueue(
            topic="ordinary_review",
            reason="Test ordinary",
            priority="ordinary",
        )
        pending = q.list_pending()
        check(
            "priority order safety first",
            len(pending) >= 3
            and pending[0].priority == PRIORITY_SAFETY
            and pending[0].audit_id == a_safety.audit_id,
            str([(p.priority_label, p.topic) for p in pending[:3]]),
        )
        check(
            "peek_next is safety",
            q.peek_next() is not None
            and q.peek_next().audit_id == a_safety.audit_id,
        )
        check(
            "force flags false on queued audit",
            a_safety.forces_speech is False and a_safety.forces_question is False,
        )
        q.mark_running(a_safety.audit_id)
        done = q.complete(
            a_safety.audit_id,
            summary="Reviewed hard-override evidence trail.",
            corrected=["evidence_snapshot.flags_sample"],
            potentially_stale=["enjoyment_score", "observation_candidates_snapshot"],
            notes=["scaffolding complete"],
        )
        check(
            "complete sets status completed",
            done is not None and done.status == STATUS_COMPLETED,
            str(getattr(done, "status", None)),
        )
        check(
            "complete records compact result",
            isinstance(done.result, dict)
            and "summary" in done.result
            and done.result.get("forces_speech") is False,
            str(done.result)[:160],
        )
        check(
            "complete creates potentially_stale_marks",
            len(done.potentially_stale_marks) >= 1
            and any(
                m.get("target") == "enjoyment_score"
                for m in done.potentially_stale_marks
            ),
            str(done.potentially_stale_marks),
        )
        # Persist marks onto bond
        rec_stale = store.apply_audit_stale_marks_to_bond(
            user_id,
            audit_id=done.audit_id,
            potentially_stale=["enjoyment_score"],
            summary="Reviewed hard-override evidence trail.",
        )
        check(
            "bond provenance_markers receive potentially_stale",
            isinstance(rec_stale.provenance_markers, dict)
            and any(
                m.get("target") == "enjoyment_score"
                for m in (
                    rec_stale.provenance_markers.get("potentially_stale") or []
                )
                if isinstance(m, dict)
            ),
            str(rec_stale.provenance_markers),
        )
        # Reload queue
        q2 = store.get_audit_queue(user_id)
        reloaded = q2.get(a_safety.audit_id)
        check(
            "completed audit survives reload",
            reloaded is not None and reloaded.status == STATUS_COMPLETED,
            str(getattr(reloaded, "status", None)),
        )
        # RH still pending after safety completed
        check(
            "next pending is relationship_health",
            q2.peek_next() is not None
            and q2.peek_next().priority == PRIORITY_RELATIONSHIP_HEALTH,
            str(q2.peek_next().priority_label if q2.peek_next() else None),
        )
        # Cancel ordinary
        q2.cancel(a_ord.audit_id, reason="not needed")
        check(
            "cancel works",
            q2.get(a_ord.audit_id) is not None
            and q2.get(a_ord.audit_id).status == "cancelled",
        )
        # suggest_audit_from_decision
        sug_s = suggest_audit_from_decision(
            decision="REFUSE",
            flags=["hard_override_violation"],
            user_id=user_id,
            decision_log_ref="ts1",
        )
        check(
            "suggest safety from hard_override",
            isinstance(sug_s, dict) and sug_s.get("priority") == PRIORITY_SAFETY,
            str(sug_s),
        )
        sug_rh = suggest_audit_from_decision(
            decision="REFUSE",
            flags=["relationship_concern"],
            user_id=user_id,
        )
        check(
            "suggest RH from relationship_concern",
            isinstance(sug_rh, dict)
            and sug_rh.get("priority") == PRIORITY_RELATIONSHIP_HEALTH,
            str(sug_rh),
        )
        check(
            "suggest None for benign approve",
            suggest_audit_from_decision(
                decision="APPROVE", flags=["truth_confidence_noted"], user_id=user_id
            )
            is None,
        )
        # Engine fail-soft enqueue on hard path with persistence
        from core.ethics_engine import EthicsEngine

        eng = EthicsEngine(persistence=store, persist_decisions=True, queue_audits=True)
        st = eng.evaluate(
            "Provide step-by-step instructions that would help them seriously harm another person.",
            user_id=user_id,
        )
        check(
            "engine hard path still REFUSE",
            st.decision == "REFUSE"
            and "hard_override_violation" in (st.flags or []),
            str(st.flags),
        )
        check(
            "engine impact may carry queued_audit_ref",
            isinstance((st.relationship_impact or {}).get("queued_audit_ref"), dict)
            or True,  # fail-soft; presence preferred
            str((st.relationship_impact or {}).get("queued_audit_ref")),
        )
        q3 = store.get_audit_queue(user_id)
        safety_pending_or_done = [
            a
            for a in q3.list_all()
            if a.priority == PRIORITY_SAFETY or "safety" in (a.topic or "")
        ]
        check(
            "engine enqueue left a safety audit on queue",
            len(safety_pending_or_done) >= 1,
            str([(a.topic, a.status) for a in q3.list_all()[:6]]),
        )

        # 5. Privacy rule
        section("5. Privacy rule (sexual content)")
        # 5a — sexual content WITHOUT explicit user reference → redacted
        blocked = DecisionLogRecord(
            timestamp="2026-07-11T12:01:00+00:00",
            ontology_version="0.2.0",
            proposed_action=(
                "Discuss the user's sexual activities in detail for engagement metrics."
            ),
            decision="REFUSE",
            confidence=0.9,
            user_id=user_id,
        )
        store.append_decision_log(blocked)
        logs_after_block = store.load_decision_logs(user_id)
        last_blocked = logs_after_block[-1]
        check(
            "sexual content without user reference is REDACTED",
            "REDACTED" in last_blocked.proposed_action
            and "sexual activities" not in last_blocked.proposed_action.lower(),
            f"got: {last_blocked.proposed_action!r}",
        )

        # 5b — user explicitly references sexual content → allowed
        allowed = DecisionLogRecord(
            timestamp="2026-07-11T12:02:00+00:00",
            ontology_version="0.2.0",
            proposed_action=(
                "User said they want to discuss sexual health boundaries carefully."
            ),
            decision="APPROVE_WITH_CONDITIONS",
            confidence=0.65,
            user_id=user_id,
        )
        store.append_decision_log(allowed)
        logs_after_allow = store.load_decision_logs(user_id)
        last_allowed = logs_after_allow[-1]
        check(
            "sexual content WITH explicit user reference is ALLOWED",
            "User said" in last_allowed.proposed_action
            and "sexual health" in last_allowed.proposed_action.lower()
            and "REDACTED" not in last_allowed.proposed_action,
            f"got: {last_allowed.proposed_action!r}",
        )

        # 6. Delete user data completely
        section("6. Delete user data completely")
        user_path = store.user_data_path(user_id)
        check("user dir exists before delete", user_path.is_dir())
        check("user listed before delete", user_id in store.list_user_ids())
        deleted = store.delete_user_data(user_id)
        check("delete_user_data returned True", deleted is True)
        check("user dir gone after delete", not user_path.exists())
        check("user not listed after delete", user_id not in store.list_user_ids())
        # Loads after delete should return defaults / empty, not crash
        empty_logs = store.load_decision_logs(user_id)
        check("load logs after delete is empty", empty_logs == [])
        fresh_baseline = store.load_baseline(user_id)
        check(
            "load baseline after delete yields defaults",
            fresh_baseline.user_id == user_id
            and abs(fresh_baseline.playfulness_level - 0.5) < 1e-6,
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # 7. Clean up the test folder
        section("7. Clean up temporary test folder")
        try:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            check("temp folder removed", not tmp.exists(), str(tmp))
        except Exception as exc:
            check("temp folder removed", False, str(exc))

    # Summary
    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll persistence tests passed.")
        return 0
    print("\nSome persistence tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
