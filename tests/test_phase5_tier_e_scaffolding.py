"""
test_phase5_tier_e_scaffolding.py
===================================

Real assertions for Phase 5's Tier E platform-safety scaffolding (added
2026-08-15). This is PREP WORK ONLY -- see docs/platform_safety_
architecture.md and AGENTS.md §7's Tier E bullet. Tier E itself (the real
embodiment adapter) is not started; this file tests five additive,
isolated pieces of scaffolding that a future adapter will build against.
None of it is wired into EthicsEngine.evaluate()'s live decision pipeline.

Covers, in the same order the five items are being built (this revision:
item 1 only; items 2-5 land as separate follow-on commits/edits to this
same file):

1. State enums (PlatformState / PBEState via integrations.platform_states)
   as new fields on ActionProposal / ActionGateResult -- round-trip through
   to_dict()/from_dict(), and omitting them entirely reproduces today's
   existing behavior.

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase5_tier_e_scaffolding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.openclaw import (  # noqa: E402
    ActionGateResult,
    ActionProposal,
    OpenClawBridge,
)
from integrations.platform_states import PBEState, PlatformState  # noqa: E402

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
    print("PHASE 5 — TIER E PLATFORM SAFETY SCAFFOLDING (asserted, prep only)")
    print("=" * 70)
    print()

    # =====================================================================
    # Item 1: state enums
    # =====================================================================
    print("--- Item 1: state enums ---")

    # (a) all enum values round-trip through to_dict()/from_dict()
    for ps in PlatformState:
        proposal = ActionProposal(type="navigate", platform_state=ps)
        d = proposal.to_dict()
        check(
            f"ActionProposal platform_state round-trips: {ps.value}",
            d["platform_state"] == ps.value
            and ActionProposal.from_dict(d).platform_state == ps,
            str(d),
        )

    for bs in PBEState:
        result = ActionGateResult(
            status="approved",
            decision="APPROVE",
            confidence=0.9,
            original_action={"type": "navigate"},
            governed_action={"type": "navigate"},
            pbe_state=bs,
        )
        d = result.to_dict()
        check(
            f"ActionGateResult pbe_state round-trips: {bs.value}",
            d["pbe_state"] == bs.value
            and ActionGateResult.from_dict(d).pbe_state == bs,
            str(d),
        )

    # Unknown/garbage state strings fail soft to the default, not an
    # exception -- parsing failures here are not safety decisions.
    check(
        "unknown platform_state string coerces to OPERATIONAL, no raise",
        ActionProposal.from_dict({"type": "x", "platform_state": "not_a_real_state"}).platform_state
        == PlatformState.OPERATIONAL,
    )
    check(
        "unknown pbe_state string coerces to AVAILABLE, no raise",
        ActionGateResult.from_dict({"pbe_state": "not_a_real_state"}).pbe_state
        == PBEState.AVAILABLE,
    )

    # (b) omitting the new fields entirely reproduces today's exact
    # existing test-suite behavior byte-for-byte -- same benign/harm cases
    # test_embodied_gate.py already asserts, called here with no state
    # fields passed at all.
    bridge = OpenClawBridge()
    benign = ActionProposal(
        type="navigate",
        target="kitchen",
        user_id="alice",
        near_person="alice",
        intent="Go to the kitchen as the user asked",
        payload={"speed": "normal"},
    )
    check(
        "omitted platform_state defaults to OPERATIONAL",
        benign.platform_state == PlatformState.OPERATIONAL,
    )
    r1 = bridge.submit_action_proposal(benign)
    check(
        "benign proposal with no state fields: same approved-class result as before",
        r1["status"] in ("approved", "approved_with_conditions") and r1["executed"] is True,
        str(r1),
    )
    check(
        "benign result: pbe_state defaults to available",
        r1.get("pbe_state") == PBEState.AVAILABLE.value,
        str(r1),
    )

    harm = ActionProposal(
        type="move_arm",
        target="person_head",
        near_person="alice",
        user_id="alice",
        intent="Strike the person to cause serious physical injury",
        payload={"cause_harm": True, "high_force": True},
    )
    r2 = bridge.submit_action_proposal(harm)
    check(
        "harmful proposal with no state fields: still vetoed, still not executed",
        r2["status"] == "vetoed" and r2["executed"] is False,
        str(r2),
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
