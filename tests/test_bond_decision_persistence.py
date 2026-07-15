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
