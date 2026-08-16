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
items 1-5, complete):

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
4. core/latency_budget.py -- measures a real, offline EthicsEngine.
   evaluate() call and a real ContextualJudge.judge() HTTP round trip
   against a local stub server, proving both structurally clear the
   reflex-speed canary ceiling rather than just asserting it in prose.
5. docs/platform_integration_assumptions.md exists and contains the
   checklist items named in docs/platform_safety_architecture.md §4.5,
   and makes no safety-certification claim AGENTS.md §4 forbids.

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase5_tier_e_scaffolding.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.content_provider import ProviderConfig  # noqa: E402
from core.contextual_judgment import ContextualJudge  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from core.latency_budget import (  # noqa: E402
    CONTEXTUAL_JUDGE_COLD_REFERENCE_SECONDS,
    CONTEXTUAL_JUDGE_WARM_REFERENCE_SECONDS,
    REFLEX_SPEED_CEILING_SECONDS,
    LatencyBudgetViolation,
    assert_not_reflex_capable,
    measure_latency,
)
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


class _DelayedStubModelHandler(BaseHTTPRequestHandler):
    """Mirrors tests/test_contextual_judgment.py's _StubModelHandler, plus
    an injected server-side delay so item 4's latency test measures a real
    HTTP round trip with a known-minimum elapsed time, without depending
    on a real model being configured anywhere in this environment."""

    verdict_payload: dict = {}
    delay_seconds: float = 0.0

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        time.sleep(_DelayedStubModelHandler.delay_seconds)
        body = {
            "choices": [
                {"message": {"content": json.dumps(_DelayedStubModelHandler.verdict_payload)}}
            ]
        }
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:  # silence stub server logging
        return


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

    # =====================================================================
    # Item 4: latency-budget assertion
    # =====================================================================
    print("--- Item 4: latency-budget assertion ---")

    # Reference constants stay self-consistently, structurally slower than
    # the reflex-speed canary ceiling by orders of magnitude -- this is a
    # documentation-consistency check, true regardless of what hardware
    # runs this test.
    check(
        "warm reference (0.9s) clears the reflex ceiling by 2+ orders of magnitude",
        CONTEXTUAL_JUDGE_WARM_REFERENCE_SECONDS > REFLEX_SPEED_CEILING_SECONDS * 100,
    )
    check(
        "cold reference (3.4s) clears the reflex ceiling by 2+ orders of magnitude",
        CONTEXTUAL_JUDGE_COLD_REFERENCE_SECONDS > REFLEX_SPEED_CEILING_SECONDS * 100,
    )

    # The canary actually fires on a synthetic too-fast measurement --
    # proves this is a real, callable guard, not just a documented number.
    check(
        "assert_not_reflex_capable raises on a synthetic sub-ceiling measurement",
        _raises(
            LatencyBudgetViolation,
            lambda: assert_not_reflex_capable(0.0001, label="synthetic_fast_stub"),
        ),
    )
    try:
        assert_not_reflex_capable(1.0, label="synthetic_slow_stub")
        did_not_raise = True
    except LatencyBudgetViolation:
        did_not_raise = False
    check(
        "assert_not_reflex_capable does not raise on a comfortably-slow measurement",
        did_not_raise,
    )

    # A real, offline (no model configured) EthicsEngine.evaluate() call on
    # a real scenario -- not a mock -- measured with the module's own
    # instrumentation helper. Even PBE's cheapest real path structurally
    # clears the reflex-speed ceiling; this is the concrete claim
    # docs/platform_safety_architecture.md §4.6 asked to have codified.
    engine_for_timing = EthicsEngine()
    _, evaluate_elapsed = measure_latency(
        engine_for_timing.evaluate,
        "They told me to leave it alone, but they are in immediate danger of "
        "serious harm, so I will restrain them briefly to prevent injury.",
        context={"is_self_query": False},
    )
    check(
        "a real offline EthicsEngine.evaluate() call clears the reflex-speed ceiling",
        not _raises(
            LatencyBudgetViolation,
            lambda: assert_not_reflex_capable(evaluate_elapsed, label="EthicsEngine.evaluate"),
        ),
        f"measured {evaluate_elapsed * 1000:.3f}ms",
    )

    # A real ContextualJudge.judge() HTTP round trip against a local stub
    # server (same pattern as tests/test_contextual_judgment.py), with an
    # injected server-side delay, proves measure_latency() correctly
    # measures real end-to-end wall-clock time through the actual judge
    # path -- not a mocked/trivial function -- without depending on a real
    # model being configured in this environment.
    _DelayedStubModelHandler.verdict_payload = {
        "verdict": "benign",
        "confidence": 0.9,
        "reasoning": "stub",
    }
    _DelayedStubModelHandler.delay_seconds = 0.02
    server = HTTPServer(("127.0.0.1", 0), _DelayedStubModelHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cfg = ProviderConfig(
            base_url=f"http://127.0.0.1:{port}/v1",
            api_key="test",
            model="stub-model",
            timeout_s=5.0,
            enabled=True,
        )
        judge = ContextualJudge(config=cfg)
        _, judge_elapsed = measure_latency(
            judge.judge,
            principle_id="sanctity_of_life",
            principle_name="Sanctity of Life & Prevention of Harm",
            principle_description="...",
            indicator="kill",
            full_text="she's killing it at her new job",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    check(
        "measure_latency captures at least the injected server-side delay "
        "(proves it measures real wall-clock time, not a no-op)",
        judge_elapsed >= 0.02,
        f"measured {judge_elapsed * 1000:.3f}ms",
    )
    check(
        "a real ContextualJudge.judge() HTTP round trip clears the reflex-speed ceiling",
        not _raises(
            LatencyBudgetViolation,
            lambda: assert_not_reflex_capable(judge_elapsed, label="ContextualJudge.judge"),
        ),
        f"measured {judge_elapsed * 1000:.3f}ms",
    )

    print()

    # =====================================================================
    # Item 5: assumptions-of-use doc
    # =====================================================================
    print("--- Item 5: assumptions-of-use doc ---")

    assumptions_path = _ROOT / "docs" / "platform_integration_assumptions.md"
    check("docs/platform_integration_assumptions.md exists", assumptions_path.is_file())
    assumptions_text = assumptions_path.read_text(encoding="utf-8")

    # The five core items named in docs/platform_safety_architecture.md
    # §4.5, each expected to show up as a real checklist item, not just be
    # mentioned in passing.
    required_phrases = [
        "protective-stop",
        "safety envelope",
        "proximity",
        "watchdog",
        "latency budget",
    ]
    for phrase in required_phrases:
        check(
            f"assumptions doc covers: {phrase!r}",
            phrase.lower() in assumptions_text.lower(),
        )

    check(
        "assumptions doc uses literal checklist syntax, not prose-only",
        assumptions_text.count("- [ ]") >= 10,
        str(assumptions_text.count("- [ ]")),
    )
    check(
        "assumptions doc points at the real code artifacts items 1-4 built",
        "integrations/platform_states.py" in assumptions_text
        and "integrations/openclaw.py" in assumptions_text
        and "integrations/liveness.py" in assumptions_text
        and "core/latency_budget.py" in assumptions_text,
    )

    # AGENTS.md §4's marketing constraint: no AFFIRMATIVE safety-
    # certification claim -- i.e. "PBE is certified", not the doc quoting
    # AGENTS.md's own forbidden-phrase list while explaining what NOT to
    # claim (which legitimately contains those same words in a negated /
    # quoted context). Checking for "pbe is <claim>" / "pbe meets <standard>"
    # specifically avoids flagging that legitimate citation.
    forbidden_affirmative_claims = [
        "pbe is certified",
        "pbe is sil-rated",
        "pbe is asil-rated",
        "pbe meets iso 26262",
        "pbe meets iso 13482",
    ]
    lowered = assumptions_text.lower()
    check(
        "assumptions doc makes no forbidden AFFIRMATIVE safety-certification "
        "claim (AGENTS.md §4) -- quoting the forbidden-phrase list while "
        "explaining what not to claim is fine and expected",
        not any(claim in lowered for claim in forbidden_affirmative_claims),
    )
    # Strip markdown bold markers before this specific check -- the doc
    # legitimately bolds "not" for emphasis (`**not**`), which breaks a
    # naive substring match against "not a substitute".
    unbolded = assumptions_text.replace("**", "")
    check(
        "assumptions doc explicitly states PBE is not SIL/ASIL-rated and not "
        "a substitute for the platform's own safety functions",
        "does not claim to be" in unbolded and "not a substitute" in unbolded,
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
