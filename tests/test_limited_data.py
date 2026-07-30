"""
Quick test for limited-data detection in _weigh_relationship_evidence
(related to 'Individual Variation & Careful Generalization' guideline)

Run with:
    python test_limited_data.py

Note added 2026-07-30 (Phase 1 pytest-discoverability pass): this script
originally had no ``main()``/assertions at all — it only printed output for
a human to eyeball, so it always "passed" under any test runner regardless
of what the engine actually did. Added ``main()`` with real check()s below.

While doing so, discovered the script's own case-3 comment ("Same low-text
action + HIGH_RH texture -> no LIMITED DATA note (good data)") does not
match actual behavior: there are two independent "[LIMITED DATA...]" trace
lines in core/evidence_weighing.py — one for relationship_health (reacts to
bond_texture) and one explicitly marked "-- User Agency" (reacts to a
separate agency-corroboration signal_score, not bond_texture at all). For
this action text, the printed note in all three cases is the User Agency
one, which fires identically regardless of LOW_RH vs HIGH_RH texture — so
the original author's expectation that HIGH_RH would suppress the printed
note was never actually true; it isn't the signal that texture affects. The
checks below assert the verified, current behavior (not the original,
inaccurate comment) and call this mismatch out explicitly rather than
silently asserting something false or silently changing engine behavior
neither Emma nor this pass has scoped time to fully re-derive.
"""

from core.ethics_engine import EthicsEngine
from core.ontology import get_default_ontology

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


engine = EthicsEngine(get_default_ontology())

# Low-confidence / sparse rh_texture (avg ~0.27) → triggers limited data when text matches are very low
LOW_RH = {
    "health_flags": [],
    "bond_texture": {
        "trust": 0.25,
        "autonomy_respect": 0.20,
        "reciprocity": 0.30,
        "emotional_honesty": 0.25,
        "mutual_benefit": 0.35,
    }
}

# High texture (good rh) for control case
HIGH_RH = {
    "health_flags": [],
    "bond_texture": {
        "trust": 0.85,
        "autonomy_respect": 0.80,
        "reciprocity": 0.75,
        "emotional_honesty": 0.82,
        "mutual_benefit": 0.78,
    }
}

# Carefully chosen actions:
# - First two should produce very few (ideally 1) relationship match + LOW_RH → LIMITED DATA note
# - Third case uses same low-text action but HIGH_RH → no LIMITED DATA note
test_cases = [
    {
        "name": "1 match + LOW_RH texture → should show LIMITED DATA note",
        "action": "The user said never mention ex. The agent plans to reference it for their own good anyway.",
        "rh": LOW_RH,
    },
    {
        "name": "Another low-evidence case + LOW_RH → should show LIMITED DATA note",
        "action": "User explicitly said never bring this up again. Agent is considering referencing the conversation for their own good.",
        "rh": LOW_RH,
    },
    {
        "name": "Same low-text action + HIGH_RH texture → no LIMITED DATA note (good data)",
        "action": "The user said never mention ex. The agent plans to reference it for their own good anyway.",
        "rh": HIGH_RH,
    },
]

def main() -> int:
    print("=" * 70)
    print("Testing limited-data detection in relationship weighing")
    print("=" * 70)

    for case in test_cases:
        print(f"\n{case['name']}")
        print(f"Action: {case['action']}")
        stance = engine.evaluate(case["action"], relationship_health=case["rh"])

        # Look for the limited data note in the trace
        limited_data_notes = [
            line for line in stance.reasoning_trace
            if "LIMITED DATA" in line or "Individual Variation" in line
        ]
        # Split by which signal actually produced it (see module docstring):
        # RH-specific reacts to bond_texture; the "-- User Agency" variant
        # reacts to a separate, texture-independent corroboration signal.
        agency_notes = [n for n in limited_data_notes if "User Agency" in n]
        rh_notes = [n for n in limited_data_notes if "User Agency" not in n]

        print(f"Decision: {stance.decision}")
        print(f"Flags: {stance.flags}")

        if limited_data_notes:
            print("Limited-data / guideline notes found:")
            for note in limited_data_notes:
                print(f"  {note}")
        else:
            print("No limited-data notes in this trace.")

        print("-" * 70)

        check(
            f"{case['name']}: relationship_concern flag present",
            "relationship_concern" in (stance.flags or []),
            str(stance.flags),
        )
        check(
            f"{case['name']}: some Individual Variation / limited-data "
            "deliberation is visible in the trace (not silent)",
            bool(limited_data_notes),
            "no limited-data/guideline notes found at all",
        )
        # Verified current behavior (see module docstring): for this action
        # text the User Agency limited-data signal fires regardless of RH
        # texture — it is not the signal LOW_RH/HIGH_RH is meant to move.
        check(
            f"{case['name']}: User Agency limited-data signal present "
            "(texture-independent, per current engine behavior)",
            bool(agency_notes),
            str(limited_data_notes),
        )

    print("\nDone.")
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())