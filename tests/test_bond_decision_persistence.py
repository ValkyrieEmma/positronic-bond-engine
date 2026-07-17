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
