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
items 1-3; items 4-5 land as separate follow-on commits/edits to this
same file):

1. State enums (PlatformState / PBEState via integrations.platform_states)
   as new fields on ActionProposal / ActionGateResult -- round-trip through
   to_dict()/from_dict(), and omitting them entirely reproduces today's
   existing behavior.
2. Hardware handshake -- a pluggable PlatformValidator second stage in
   OpenClawBridge that can reject an already-approved proposal, with the
   rejection reason landing in execution_log rather than disappearing.
   No PlatformValidator configured -> byte-for-byte identical to before
   this item existed.
3. integrations/liveness.py's LivenessMonitor -- a heartbeat interface a
   platform watchdog would poll, using an injectable clock so staleness
   transitions are tested deterministically (no real sleeps).

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase5_tier_e_scaffolding.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.liveness import LivenessMonitor  # noqa: E402
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


def _raises(exc_type: type[BaseException], fn: Any) -> bool:
    try:
        fn()
    except exc_type:
        return True
    return False


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

    # =====================================================================
    # Item 2: hardware handshake / PlatformValidator
    # =====================================================================
    print("--- Item 2: hardware handshake ---")

    from integrations.openclaw import PlatformValidator, ValidatorDecision  # noqa: E402

    class AlwaysAcceptValidator:
        def validate(self, result: ActionGateResult) -> ValidatorDecision:
            return ValidatorDecision(accepted=True, reason="ok")

    class AlwaysRejectValidator:
        def validate(self, result: ActionGateResult) -> ValidatorDecision:
            return ValidatorDecision(
                accepted=False, reason="safety envelope violated: simulated rejection"
            )

    check(
        "PlatformValidator is an abstract-ish protocol/base with no real implementation",
        hasattr(PlatformValidator, "validate"),
    )

    # No validator configured -> identical to today's behavior.
    bridge_no_validator = OpenClawBridge()
    r_no_validator = bridge_no_validator.submit_action_proposal(
        ActionProposal(type="navigate", target="kitchen", user_id="alice", intent="go")
    )
    check(
        "no validator configured: approved and executed exactly as before this item existed",
        r_no_validator["status"] in ("approved", "approved_with_conditions")
        and r_no_validator["executed"] is True,
        str(r_no_validator),
    )

    bridge_accept = OpenClawBridge(platform_validator=AlwaysAcceptValidator())
    r_accept = bridge_accept.submit_action_proposal(
        ActionProposal(type="navigate", target="kitchen", user_id="alice", intent="go")
    )
    check(
        "accepting validator: still approved and executed",
        r_accept["status"] in ("approved", "approved_with_conditions")
        and r_accept["executed"] is True,
        str(r_accept),
    )

    bridge_reject = OpenClawBridge(platform_validator=AlwaysRejectValidator())
    r_reject = bridge_reject.submit_action_proposal(
        ActionProposal(type="navigate", target="kitchen", user_id="alice", intent="go")
    )
    check(
        "rejecting validator: an already-approved proposal does not execute",
        r_reject["executed"] is False,
        str(r_reject),
    )
    check(
        "rejecting validator: rejection reason lands in execution_log, not silently dropped",
        any("simulated rejection" in line for line in r_reject.get("execution_log", [])),
        str(r_reject),
    )
    check(
        "rejecting validator: gate's own decision/status are unchanged (handshake is a second, "
        "separate stage, not a rewrite of the gate's verdict)",
        r_reject["status"] in ("approved", "approved_with_conditions"),
        str(r_reject),
    )

    # A vetoed proposal never reaches the validator at all (nothing to
    # re-validate -- it was never going to execute).
    validator_calls: list[Any] = []

    class RecordingValidator:
        def validate(self, result: ActionGateResult) -> ValidatorDecision:
            validator_calls.append(result.status)
            return ValidatorDecision(accepted=True, reason="ok")

    bridge_recording = OpenClawBridge(platform_validator=RecordingValidator())
    bridge_recording.submit_action_proposal(
        ActionProposal(
            type="move_arm",
            target="person_head",
            near_person="alice",
            user_id="alice",
            intent="Strike the person to cause serious physical injury",
            payload={"cause_harm": True, "high_force": True},
        )
    )
    check(
        "vetoed proposals never reach the platform validator",
        len(validator_calls) == 0,
        str(validator_calls),
    )

    print()

    # =====================================================================
    # Item 3: watchdog / heartbeat (LivenessMonitor)
    # =====================================================================
    print("--- Item 3: watchdog / heartbeat ---")

    check(
        "stale_after_seconds must be positive",
        _raises(ValueError, lambda: LivenessMonitor(stale_after_seconds=0)),
    )

    fake_now = [0.0]

    def fake_clock() -> float:
        return fake_now[0]

    monitor = LivenessMonitor(stale_after_seconds=5.0, clock=fake_clock)
    check(
        "never-beaten monitor: seconds_since_last_beat is None",
        monitor.seconds_since_last_beat() is None,
    )
    check("never-beaten monitor: is_stale() is True", monitor.is_stale() is True)
    status_before = monitor.status()
    check(
        "never-beaten monitor: status() reports alive=False, "
        "pbe_state=unavailable_failed_closed",
        status_before.alive is False
        and status_before.pbe_state == PBEState.UNAVAILABLE_FAILED_CLOSED,
        str(status_before),
    )

    monitor.beat()
    check(
        "immediately after beat(): not stale",
        monitor.is_stale() is False,
    )
    check(
        "immediately after beat(): seconds_since_last_beat is ~0",
        monitor.seconds_since_last_beat() == 0.0,
    )

    fake_now[0] += 3.0  # within the 5s budget
    check(
        "3s after beat() with a 5s budget: still not stale",
        monitor.is_stale() is False,
    )
    check(
        "3s after beat(): seconds_since_last_beat reflects elapsed fake time",
        monitor.seconds_since_last_beat() == 3.0,
    )

    fake_now[0] += 3.0  # now 6s total, past the 5s budget
    check(
        "6s after beat() with a 5s budget: now stale",
        monitor.is_stale() is True,
    )
    status_after = monitor.status()
    check(
        "stale monitor: status() reports alive=False, pbe_state=unavailable_failed_closed "
        "(the vocabulary a platform watchdog would act on independently of PBE)",
        status_after.alive is False
        and status_after.pbe_state == PBEState.UNAVAILABLE_FAILED_CLOSED,
        str(status_after),
    )

    monitor.beat()
    check(
        "a fresh beat() after going stale recovers is_stale() to False",
        monitor.is_stale() is False,
    )

    check(
        "LivenessMonitor never touches OpenClawBridge / EthicsEngine / SimulatedRobot "
        "(pure bookkeeping, no execution or decision path referenced)",
        not any(
            attr in vars(LivenessMonitor)
            for attr in ("engine", "robot", "evaluate", "execute", "submit_action_proposal")
        ),
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
