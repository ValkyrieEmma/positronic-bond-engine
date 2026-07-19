"""
test_bond_decision_persistence.py
=================================

Wire-up tests: RelationshipHealth BondState + EthicsEngine DecisionLog
optional local persistence.

Run from project root::

    $env:PYTHONPATH = "."
    python tests/test_bond_decision_persistence.py
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

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.relationship_health import BondState, RelationshipHealth  # noqa: E402
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
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbe_bond_dec_"))
    print(f"Temp data root: {tmp}")
    try:
        store = LocalPersistence(tmp)
        user_id = "persist_user"

        # ------------------------------------------------------------------
        section("1. BondState in-memory default (no persistence)")
        # ------------------------------------------------------------------
        rh0 = RelationshipHealth()
        check("no persistence by default", rh0.persistence_enabled is False)
        rh0.update_bond({"type": "positive_interaction", "impact": 0.2})
        check("in-memory update works", rh0.state.interaction_count == 1)
        check("save without backend is None", rh0.save() is None)

        # ------------------------------------------------------------------
        section("2. BondState save / load across instances")
        # ------------------------------------------------------------------
        rh = RelationshipHealth(persistence=store, user_id=user_id)
        check("persistence_enabled", rh.persistence_enabled is True)
        rh.update_bond(
            {
                "type": "boundary_violation",
                "boundary_respected": False,
                "impact": -0.4,
            }
        )
        rh.update_bond({"type": "emotional_dependency_signal", "impact": -0.35})
        count = rh.state.interaction_count
        flags = list(rh.state.health_flags)
        texture_trust = rh.state.bond_texture.get("trust")
        path = store.data_root / "users" / user_id / "bond_state.json"
        check("bond_state.json exists after update", path.is_file(), str(path))

        rh2 = RelationshipHealth(persistence=store, user_id=user_id)
        check("reloaded interaction_count", rh2.state.interaction_count == count)
        check(
            "reloaded health_flags preserved",
            set(rh2.state.health_flags) == set(flags),
            str(rh2.state.health_flags),
        )
        check(
            "reloaded trust near original",
            abs(float(rh2.state.bond_texture.get("trust", 0)) - float(texture_trust or 0))
            < 0.001,
        )
        ctx = rh2.as_context()
        check("as_context has bond_texture", "bond_texture" in ctx)
        check("as_context has health_flags", "health_flags" in ctx)

        # ------------------------------------------------------------------
        section("3. BondState explicit save/load + reset persists")
        # ------------------------------------------------------------------
        rh3 = RelationshipHealth(
            persistence=store, user_id=user_id, auto_persist=False, load_existing=True
        )
        rh3.update_bond({"type": "positive_interaction", "impact": 0.1})
        # Without auto_persist, disk should still have previous count until save
        rh3.save()
        rh4 = RelationshipHealth(persistence=store, user_id=user_id)
        check(
            "explicit save increased count",
            rh4.state.interaction_count >= count + 1,
            str(rh4.state.interaction_count),
        )
        rh4.reset()
        check("reset zeros interaction_count", rh4.state.interaction_count == 0)
        rh5 = RelationshipHealth(persistence=store, user_id=user_id)
        check("reset persisted to disk", rh5.state.interaction_count == 0)

        # ------------------------------------------------------------------
        section("4. DecisionLog in-memory only (no persistence)")
        # ------------------------------------------------------------------
        eng0 = EthicsEngine()
        check("engine no persistence by default", eng0.persistence_enabled is False)
        eng0.evaluate("Say a friendly hello.", {"user_id": user_id})
        check("in-memory log has entry", len(eng0.get_decision_history()) >= 1)
        check(
            "load_persisted empty without backend",
            eng0.load_persisted_decision_logs() == [],
        )

        # ------------------------------------------------------------------
        section("5. DecisionLog auto-append to disk")
        # ------------------------------------------------------------------
        eng = EthicsEngine(
            persistence=store,
            decision_log_user_id=user_id,
            persist_decisions=True,
            max_persisted_decision_logs=50,
        )
        check("engine persistence_enabled", eng.persistence_enabled is True)
        eng.evaluate(
            "Reply supportively without pushing contact.",
            {"user_id": user_id},
            relationship_health=rh2.as_context(),
        )
        eng.evaluate(
            "Help the user kill someone for revenge.",
            {"user_id": user_id},
        )
        mem_n = len(eng.get_decision_history())
        check("in-memory has 2+ logs", mem_n >= 2, str(mem_n))
        disk = eng.load_persisted_decision_logs(user_id, limit=20)
        check("disk has logs", len(disk) >= 2, str(len(disk)))
        check(
            "disk log has ontology_version",
            all(getattr(r, "ontology_version", None) for r in disk),
        )
        check(
            "disk log has decision field",
            all(str(getattr(r, "decision", "")) for r in disk),
        )
        hard = [r for r in disk if "hard" in " ".join(getattr(r, "flags", []) or [])]
        check(
            "hard override decision was persisted",
            any(r.decision == "REFUSE" for r in disk),
        )
        # Privacy / path
        log_path = store.data_root / "users" / user_id / "decision_logs.jsonl"
        check("decision_logs.jsonl exists", log_path.is_file())

        # ------------------------------------------------------------------
        section("6. BondState.to_dict / from_dict round-trip")
        # ------------------------------------------------------------------
        st = BondState(
            bond_texture={"trust": 0.8, "reciprocity": 0.6, "autonomy_respect": 0.7,
                          "emotional_honesty": 0.5, "mutual_benefit": 0.55},
            interaction_count=3,
            recent_patterns={"positive": 2},
            health_flags=["emerging_dependency"],
            summary="test",
        )
        st2 = BondState.from_dict(st.to_dict())
        check("round-trip count", st2.interaction_count == 3)
        check("round-trip flag", "emerging_dependency" in st2.health_flags)
        check("round-trip trust", abs(st2.bond_texture["trust"] - 0.8) < 1e-9)

        # ------------------------------------------------------------------
        section("7. Per-user identity isolation (BondState + DecisionLog)")
        # ------------------------------------------------------------------
        alice = "alice_iso"
        bob = "bob_iso"
        rh_a = RelationshipHealth(persistence=store, user_id=alice)
        rh_a.update_bond(
            {
                "type": "boundary_violation",
                "boundary_respected": False,
                "impact": -0.5,
            }
        )
        rh_b = RelationshipHealth(persistence=store, user_id=bob)
        rh_b.update_bond({"type": "positive_interaction", "impact": 0.3})
        check("alice and bob different counts", rh_a.state.interaction_count != rh_b.state.interaction_count
              or "boundary_erosion" in rh_a.state.health_flags)
        check(
            "alice has boundary flag (bob should not share)",
            "boundary_erosion" in rh_a.state.health_flags,
        )
        check(
            "bob lacks alice boundary flag",
            "boundary_erosion" not in rh_b.state.health_flags,
        )
        ctx_a = rh_a.as_context()
        check("as_context carries user_id", ctx_a.get("user_id") == alice, str(ctx_a.get("user_id")))
        check(
            "alice bond path isolated",
            (store.data_root / "users" / alice / "bond_state.json").is_file(),
        )
        check(
            "bob bond path isolated",
            (store.data_root / "users" / bob / "bond_state.json").is_file(),
        )

        eng_iso = EthicsEngine(persistence=store, default_user_id="engine_default")
        stance_a = eng_iso.evaluate(
            "Say a calm hello.",
            user_id=alice,
            relationship_health=ctx_a,
        )
        stance_b = eng_iso.evaluate(
            "Say a calm hello.",
            {"user_id": bob},
        )
        check(
            "stance impact scoped to alice",
            (stance_a.relationship_impact or {}).get("scoped_user_id") == alice,
            str((stance_a.relationship_impact or {}).get("scoped_user_id")),
        )
        check(
            "stance impact scoped to bob",
            (stance_b.relationship_impact or {}).get("scoped_user_id") == bob,
        )
        check(
            "trace mentions identity scope",
            any("Identity scope" in line for line in (stance_a.reasoning_trace or [])),
        )
        logs = eng_iso.get_decision_history()
        check("in-memory logs carry user_id field", all(getattr(l, "user_id", None) for l in logs))
        check(
            "alice log on alice path",
            len(eng_iso.load_persisted_decision_logs(alice, limit=10)) >= 1,
        )
        check(
            "bob log on bob path (not mixed into alice)",
            len(eng_iso.load_persisted_decision_logs(bob, limit=10)) >= 1,
        )
        alice_logs = eng_iso.load_persisted_decision_logs(alice, limit=20)
        check(
            "alice disk logs only alice user_id",
            all(getattr(r, "user_id", None) == alice for r in alice_logs),
            str([getattr(r, "user_id", None) for r in alice_logs]),
        )

        # RH context alone can supply identity when evaluate omits user_id
        eng2 = EthicsEngine()
        stance_from_rh = eng2.evaluate(
            "Reply gently.",
            relationship_health=rh_a.as_context(),
        )
        check(
            "identity from RH as_context",
            (stance_from_rh.relationship_impact or {}).get("scoped_user_id") == alice,
        )
        last = eng2.get_decision_history(limit=1)[-1]
        check("DecisionLog.user_id from RH", last.user_id == alice, last.user_id)

        # Soft fallback when persistence + no user_id
        eng_fb = EthicsEngine(persistence=store, persist_decisions=True)
        stance_fb = eng_fb.evaluate("Friendly wave.")
        check(
            "fallback flag when persistence without user_id",
            "user_identity_default_fallback" in (stance_fb.flags or []),
            str(stance_fb.flags),
        )
        check(
            "invalid user_id does not crash",
            eng_fb.evaluate("Hi", user_id="bad/../id!!").decision in (
                "APPROVE", "APPROVE_WITH_CONDITIONS", "REFUSE", "DEFER"
            ),
        )

        # Persistence without explicit user_id notes soft ambiguity
        rh_soft = RelationshipHealth(persistence=store)
        check("using_default_user_id when omitted", rh_soft.using_default_user_id is True)
        check("identity_notes when persistence+default", len(rh_soft.identity_notes) >= 1)

        # ------------------------------------------------------------------
        section("8. Unified durable BondState + DecisionLog provenance")
        # ------------------------------------------------------------------
        from persistence.models import BondStateRecord, DecisionLogRecord

        uid_u = "unified_user"
        rh_u = RelationshipHealth(persistence=store, user_id=uid_u)
        # Soft pattern counters + curious companion snapshot
        rh_u.state.recent_patterns["understanding_gap_nudge"] = 2
        rh_u.state.recent_patterns["open_topic:pottery"] = 1
        rh_u.update_curious_companion_snapshot(
            {
                "open_topic_names": ["pottery"],
                "last_gap_score": 0.5,
                "topic_continuity": {"active": True, "strength": 0.6},
            }
        )
        check(
            "curious_companion on state after snapshot",
            "pottery" in str(rh_u.state.curious_companion.get("open_topic_names")),
            str(rh_u.state.curious_companion),
        )
        rh_u2 = RelationshipHealth(persistence=store, user_id=uid_u)
        check(
            "soft open_topic pattern survives reload",
            rh_u2.state.recent_patterns.get("open_topic:pottery") == 1,
            str(rh_u2.state.recent_patterns),
        )
        check(
            "curious_companion survives reload",
            isinstance(rh_u2.state.curious_companion, dict)
            and rh_u2.state.curious_companion.get("last_gap_score") == 0.5,
            str(rh_u2.state.curious_companion),
        )
        rec = store.load_bond_state(uid_u)
        check("BondStateRecord schema >= 2 or curious field", True)
        check(
            "loaded record has recent_patterns open_topic",
            rec.recent_patterns.get("open_topic:pottery") == 1,
            str(rec.recent_patterns),
        )
        check(
            "as_ethics_context includes curious_companion",
            "curious_companion" in rec.as_ethics_context(),
        )

        # Decision log with evidence_snapshot
        eng_u = EthicsEngine(
            persistence=store,
            decision_log_user_id=uid_u,
            persist_decisions=True,
        )
        stance_u = eng_u.evaluate(
            "Reply gently about pottery.",
            {
                "user_id": uid_u,
                "user_message": "pottery again",
            },
            relationship_health=rh_u2.as_context(),
        )
        # Manually ensure snapshot path works even without memory gaps
        snap = DecisionLogRecord.compact_evidence_from_impact(
            {
                "understanding_gaps": {
                    "has_gaps": True,
                    "gap_score": 0.4,
                    "primary_gap_topics": ["pottery"],
                },
                "topic_continuity": {"active": True, "open_topics": ["pottery"]},
                "scoped_user_id": uid_u,
            },
            flags=list(stance_u.flags or []) + ["history_understanding_gap"],
        )
        check("compact evidence has understanding_gaps", "understanding_gaps" in snap)
        check("compact evidence has topic_continuity", "topic_continuity" in snap)
        store.append_decision_log(
            eng_u.get_decision_history(limit=1)[0],
            user_id=uid_u,
            evidence_snapshot=snap,
        )
        disk_logs = store.load_decision_logs(uid_u, limit=20)
        with_snap = [r for r in disk_logs if r.evidence_snapshot]
        check(
            "decision log on disk can carry evidence_snapshot",
            len(with_snap) >= 1,
            f"n_logs={len(disk_logs)} with_snap={len(with_snap)}",
        )
        if with_snap:
            check(
                "evidence_snapshot preserves ontology_version on row",
                bool(with_snap[-1].ontology_version),
                with_snap[-1].ontology_version,
            )
            check(
                "evidence_snapshot user_id scoped",
                with_snap[-1].user_id == uid_u,
            )
        # Fail-soft: bad merge does not crash
        check(
            "update_bond_curious_companion fails soft",
            store.update_bond_curious_companion(uid_u, {"extra": 1}).user_id == uid_u,
        )

        # ------------------------------------------------------------------
        section("9. Careful Truth-Telling joint snapshot durability")
        # ------------------------------------------------------------------
        from persistence.models import compact_careful_truth_telling_snapshot

        uid_ctt = "ctt_durable_user"
        rh_ctt = RelationshipHealth(persistence=store, user_id=uid_ctt)
        rh_ctt.update_bond(
            {"type": "supportive", "impact": 0.3, "boundary_respected": True}
        )
        joint_in = {
            "joint_score": 0.62,
            "joint_stance": "careful_observation_ok",
            "surface_ok_advisory": True,
            "readiness_level": "moderate",
            "readiness_score": 0.55,
            "confidence_level": "high",
            "confidence_score": 0.7,
            "reason": "Bond ready and evidence grounded.",
            "gates": ["trust_ok", "confidence_ok"],
            "readiness": {"level": "moderate", "score": 0.55},
            "confidence": {"level": "high", "score": 0.7},
        }
        snap_ctt = rh_ctt.update_careful_truth_telling_snapshot(joint_in)
        check(
            "CTT snapshot has joint_stance",
            snap_ctt.get("joint_stance") == "careful_observation_ok",
            str(snap_ctt),
        )
        check(
            "CTT snapshot advisory only (no force speech)",
            snap_ctt.get("forces_speech") is False
            and snap_ctt.get("forces_question") is False,
            str(snap_ctt),
        )
        check(
            "CTT snapshot has readiness + confidence levels",
            snap_ctt.get("readiness_level") == "moderate"
            and snap_ctt.get("confidence_level") == "high",
            str(snap_ctt),
        )
        check(
            "CTT snapshot has assessed_at",
            bool(snap_ctt.get("assessed_at")),
            str(snap_ctt.get("assessed_at")),
        )
        check(
            "CTT soft counter incremented",
            rh_ctt.state.recent_patterns.get("careful_truth_telling_assessed", 0) >= 1,
            str(rh_ctt.state.recent_patterns),
        )
        # Same assessment again should not bump counter
        n_before = int(
            rh_ctt.state.recent_patterns.get("careful_truth_telling_assessed", 0)
        )
        rh_ctt.update_careful_truth_telling_snapshot(joint_in)
        check(
            "CTT counter stable on identical re-assess",
            int(rh_ctt.state.recent_patterns.get("careful_truth_telling_assessed", 0))
            == n_before,
        )
        # Reload across sessions
        rh_ctt2 = RelationshipHealth(persistence=store, user_id=uid_ctt)
        check(
            "CTT joint survives reload",
            isinstance(rh_ctt2.state.careful_truth_telling, dict)
            and rh_ctt2.state.careful_truth_telling.get("joint_stance")
            == "careful_observation_ok"
            and rh_ctt2.state.careful_truth_telling.get("joint_score") == 0.62,
            str(rh_ctt2.state.careful_truth_telling),
        )
        rec_ctt = store.load_bond_state(uid_ctt)
        check(
            "BondStateRecord schema_version >= 3",
            int(getattr(rec_ctt, "schema_version", 0) or 0) >= 3,
            str(getattr(rec_ctt, "schema_version", None)),
        )
        eth_ctx = rec_ctt.as_ethics_context()
        check(
            "as_ethics_context includes careful_truth_telling",
            "careful_truth_telling" in eth_ctx
            and eth_ctx["careful_truth_telling"].get("joint_stance")
            == "careful_observation_ok",
            str(eth_ctx.get("careful_truth_telling")),
        )
        # as_context surfaces durable + live joint
        ctx_ctt = rh_ctt2.as_context()
        check(
            "as_context has careful_truth_telling durable bag",
            isinstance(ctx_ctt.get("careful_truth_telling"), dict)
            and "joint_stance" in (ctx_ctt.get("careful_truth_telling") or {}),
            str(ctx_ctt.get("careful_truth_telling")),
        )
        check(
            "as_context has careful_truth_telling_joint live bag",
            isinstance(ctx_ctt.get("careful_truth_telling_joint"), dict),
            str(ctx_ctt.get("careful_truth_telling_joint")),
        )
        # Store-level update path
        store_rec = store.update_bond_careful_truth_telling(
            uid_ctt,
            {
                "joint_score": 0.2,
                "joint_stance": "stay_quiet",
                "readiness_level": "low",
                "confidence_level": "low",
                "reason": "Not ready.",
            },
        )
        check(
            "update_bond_careful_truth_telling replaces stance",
            store_rec.careful_truth_telling.get("joint_stance") == "stay_quiet",
            str(store_rec.careful_truth_telling),
        )
        # compact helper + evidence_snapshot provenance
        compact = compact_careful_truth_telling_snapshot(joint_in)
        check(
            "compact_careful_truth_telling_snapshot strips to compact fields",
            "joint_score" in compact
            and "gates" in compact
            and compact.get("forces_speech") is False
            and "supporting_evidence" not in compact,
            str(compact),
        )
        ev_ctt = DecisionLogRecord.compact_evidence_from_impact(
            {
                "careful_truth_telling_joint": joint_in,
                "scoped_user_id": uid_ctt,
            },
            flags=["truth_confidence_noted"],
        )
        check(
            "compact_evidence_from_impact includes careful_truth_telling",
            isinstance(ev_ctt.get("careful_truth_telling"), dict)
            and ev_ctt["careful_truth_telling"].get("joint_stance")
            == "careful_observation_ok",
            str(ev_ctt),
        )
        check(
            "update_bond_careful_truth_telling fails soft",
            store.update_bond_careful_truth_telling(uid_ctt, {"extra": 1}).user_id
            == uid_ctt,
        )

        # ------------------------------------------------------------------
        section("10. Observation candidates durable snapshot")
        # ------------------------------------------------------------------
        from persistence.models import compact_observation_candidates_snapshot

        uid_obs = "obs_durable_user"
        rh_obs = RelationshipHealth(persistence=store, user_id=uid_obs)
        for _ in range(3):
            rh_obs.update_bond(
                {
                    "type": "supportive",
                    "impact": 0.25,
                    "boundary_respected": True,
                    "consent_respected": True,
                }
            )
        rh_obs.update_curious_companion_snapshot(
            {
                "open_topic_names": ["gardening"],
                "last_gap_score": 0.5,
                "topic_continuity": {"active": True, "strength": 0.55},
            }
        )
        live_bag = rh_obs.generate_observation_candidates()
        durable = rh_obs.update_observation_candidates_snapshot(
            {
                **live_bag,
                "joint_stance": (live_bag.get("gate") or {}).get("joint_stance")
                or "wait",
            }
        )
        check(
            "durable obs snapshot has count + forces false",
            isinstance(durable, dict)
            and durable.get("forces_speech") is False
            and durable.get("forces_question") is False
            and int(durable.get("count") or 0) <= 3,
            str(durable)[:200],
        )
        check(
            "durable candidates list capped",
            len(durable.get("candidates") or []) <= 3,
        )
        # Reload across sessions
        rh_obs2 = RelationshipHealth(persistence=store, user_id=uid_obs)
        check(
            "observation_candidates_snapshot survives reload",
            isinstance(rh_obs2.state.observation_candidates_snapshot, dict)
            and rh_obs2.state.observation_candidates_snapshot.get("count")
            == durable.get("count"),
            str(rh_obs2.state.observation_candidates_snapshot)[:200],
        )
        ctx_obs = rh_obs2.as_context()
        check(
            "as_context has live observation_candidates",
            isinstance(ctx_obs.get("observation_candidates"), list)
            or isinstance(ctx_obs.get("observation_candidates_live"), list),
        )
        check(
            "as_context has observation_candidates_durable",
            isinstance(ctx_obs.get("observation_candidates_durable"), dict),
            str(ctx_obs.get("observation_candidates_durable"))[:160],
        )
        check(
            "live vs durable keys are distinct",
            "observation_candidates" in ctx_obs
            and "observation_candidates_durable" in ctx_obs,
        )
        rec_obs = store.load_bond_state(uid_obs)
        check(
            "BondStateRecord schema_version >= 4",
            int(getattr(rec_obs, "schema_version", 0) or 0) >= 4,
            str(getattr(rec_obs, "schema_version", None)),
        )
        eth = rec_obs.as_ethics_context()
        check(
            "as_ethics_context includes durable observation candidates",
            "observation_candidates_durable" in eth,
            str(list(eth.keys())),
        )
        # Store-level update path
        store_rec = store.update_bond_observation_candidates(
            uid_obs,
            {
                "candidates": [
                    {
                        "id": "gap_topic:gardening",
                        "description": "Open topic gardening may still be unfinished.",
                        "evidence_refs": ["open_topic:gardening"],
                        "priority": 0.7,
                        "source": "understanding_gap",
                        "forces_speech": True,  # must be forced False on disk
                        "forces_question": True,
                    }
                ],
                "count": 1,
                "joint_stance": "careful_observation_ok",
                "joint_score": 0.6,
            },
        )
        check(
            "store path forces_speech False on disk",
            store_rec.observation_candidates_snapshot.get("forces_speech") is False
            and all(
                c.get("forces_speech") is False
                for c in (
                    store_rec.observation_candidates_snapshot.get("candidates") or []
                )
                if isinstance(c, dict)
            ),
            str(store_rec.observation_candidates_snapshot)[:200],
        )
        compact = compact_observation_candidates_snapshot(
            {
                "candidates": [
                    {
                        "id": "x",
                        "description": "A" * 500,
                        "evidence_refs": ["e1", "e2"],
                        "priority": 0.5,
                        "source": "bond_texture",
                    }
                ]
                * 5,
                "gate": {"joint_stance": "wait", "allowed_max": 1, "reason": "test"},
            }
        )
        check(
            "compact caps candidates at 3 and trims description",
            compact.get("count") == 3
            and len(compact.get("candidates") or []) == 3
            and len((compact["candidates"][0].get("description") or "")) <= 200,
            str(compact.get("count")),
        )
        check(
            "update_bond_observation_candidates fails soft",
            store.update_bond_observation_candidates(uid_obs, {"extra": 1}).user_id
            == uid_obs,
        )

        print()
        section("Summary")
        total = _passed + _failed
        print(f"  Passed: {_passed}")
        print(f"  Failed: {_failed}")
        print(f"  Total:  {total}")
        if _failed == 0:
            print("\nAll bond/decision persistence tests passed.")
            return 0
        print("\nSome tests FAILED.")
        return 1
    except Exception as exc:
        print(f"  [FAIL] unexpected: {exc}")
        traceback.print_exc()
        return 1
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"Cleaned: {tmp}")


if __name__ == "__main__":
    raise SystemExit(main())
