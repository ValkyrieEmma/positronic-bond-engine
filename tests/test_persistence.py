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
_ROOT = Path(__file__).resolve().parent
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
