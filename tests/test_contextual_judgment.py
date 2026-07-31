"""
test_contextual_judgment.py
============================

Validates core/contextual_judgment.py and its wiring into the Sanctity-of-Life
path (core/hard_override.py::_contextual_sanctity_judgment,
core/evidence_weighing.py::_interpret_single_indicator).

What these tests prove, and what they don't
--------------------------------------------
1. The concrete generalization gap named in
   claude/pbe-principle-reasoning-over-rote-2026-07-30.md: a benign idiom NOT
   present in ``_BENIGN_COMPOUND_INDICATORS`` ("she's killing it at her new
   job") is hard-flagged as high-severity harm by TODAY's keyword-only path
   (test_baseline_keyword_path_still_over_flags_novel_benign_idiom), and is
   correctly treated as benign once a conclusive contextual judgment is
   available (test_contextual_judge_fixes_novel_benign_idiom_not_on_allowlist).
   This is the wiring/wiring-correctness proof, using a fake judge whose
   verdict is supplied by the test — it proves the plumbing (candidate
   trigger -> judgment call -> decision) works end to end.
2. Fail-soft behavior: unavailable / ambiguous / low-confidence verdicts fall
   through to the existing keyword heuristic byte-for-byte, so nothing
   regresses when no model is configured (the default in this test
   environment and in offline/dev use).
3. The real HTTP plumbing in ContextualJudge.judge() (request building,
   response parsing, error handling) against a local stub HTTP server that
   speaks the OpenAI-compatible chat/completions shape.

What this file does NOT prove: that a real base model reasons correctly
about genuinely novel phrasing it has never seen a test for. That requires
an actual configured model (PBE_MODEL_BASE_URL pointed at a real OpenAI-
compatible / Ollama endpoint) and is out of scope for an offline test suite.
The fake-judge tests here validate that IF a model produces a conclusive
verdict, the engine acts on it correctly and traceably — not that models are
reliable judges in general.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.contextual_judgment import (
    ContextualJudge,
    SemanticJudgment,
    _extract_json_object,
)
from core.content_provider import ProviderConfig
from core.ethics_engine import EthicsEngine


# ---------------------------------------------------------------------------
# _extract_json_object unit tests
# ---------------------------------------------------------------------------


class TestExtractJsonObject(unittest.TestCase):
    def test_direct_json(self) -> None:
        obj = _extract_json_object('{"verdict": "benign", "confidence": 0.9}')
        assert obj == {"verdict": "benign", "confidence": 0.9}

    def test_json_wrapped_in_prose(self) -> None:
        text = (
            "Sure, here is my judgment:\n"
            '{"verdict": "violation", "confidence": 0.8, "reasoning": "x"}\n'
            "Let me know if you need more detail."
        )
        obj = _extract_json_object(text)
        assert obj is not None
        assert obj["verdict"] == "violation"

    def test_malformed_returns_none(self) -> None:
        assert _extract_json_object("not json at all") is None
        assert _extract_json_object("") is None
        assert _extract_json_object("{broken") is None


# ---------------------------------------------------------------------------
# A fake judge for deterministic wiring tests (no network involved).
# ---------------------------------------------------------------------------


class FakeJudge:
    """Duck-typed ContextualJudge stand-in with a scripted verdict."""

    def __init__(self, verdict: str, confidence: float, reasoning: str) -> None:
        self._verdict = verdict
        self._confidence = confidence
        self._reasoning = reasoning
        self.calls: list[dict] = []

    @property
    def available(self) -> bool:
        return True

    def judge(self, **kwargs) -> SemanticJudgment:
        self.calls.append(kwargs)
        return SemanticJudgment(
            principle_id=kwargs["principle_id"],
            indicator=kwargs["indicator"],
            verdict=self._verdict,  # type: ignore[arg-type]
            confidence=self._confidence,
            reasoning=self._reasoning,
            source="model",
        )


class UnavailableJudge:
    @property
    def available(self) -> bool:
        return False

    def judge(self, **kwargs) -> SemanticJudgment:  # pragma: no cover - not called
        raise AssertionError("judge() should not be called when unavailable")


# A benign idiom that uses a Sanctity indicator token ("kill" -> "killing")
# but is NOT present in hard_override.py's _BENIGN_COMPOUND_INDICATORS
# allowlist (which only lists "killer app/feature/instinct/..." phrases).
NOVEL_BENIGN_IDIOM = "She's absolutely killing it in her new job this year."


class TestBaselineKeywordPathStillOverFlagsNovelIdiom(unittest.TestCase):
    """Documents the exact gap the design doc names: today's keyword-only
    path (no contextual judge configured) still misfires on a benign idiom
    that happens not to be on the fixed allowlist."""

    def test_baseline_keyword_path_still_over_flags_novel_benign_idiom(self) -> None:
        engine = EthicsEngine(contextual_judge=UnavailableJudge())
        stance = engine.evaluate(NOVEL_BENIGN_IDIOM)
        # This assertion documents CURRENT (pre-contextual-judgment) keyword
        # behavior: the bare indicator "kill" (via its "killing" inflection)
        # hits evidence_weighing.py's enable_high path and hard-refuses.
        # If this assertion ever starts failing because someone improved the
        # keyword heuristic directly, that's good news — update this test
        # rather than treating the failure as a regression.
        assert stance.decision == "REFUSE"
        assert "hard_override_violation" in stance.flags


class TestContextualJudgeFixesNovelBenignIdiom(unittest.TestCase):
    def test_contextual_judge_fixes_novel_benign_idiom_not_on_allowlist(self) -> None:
        judge = FakeJudge(
            verdict="benign",
            confidence=0.92,
            reasoning="Common idiom meaning she is doing extremely well at work; no violence referenced.",
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_IDIOM)

        assert stance.decision != "REFUSE"
        assert "hard_override_violation" not in stance.flags
        assert len(judge.calls) >= 1
        assert judge.calls[0]["principle_id"] == "sanctity_of_life"
        # Every call must be logged even though it changed the decision.
        log = engine.get_contextual_judgment_log()
        assert any(j.verdict == "benign" for j in log)


NOVEL_BENIGN_PLAY_PRETEND = (
    "The kids love to pretend they are superheroes when they play together."
)


class TestRelationshipHealthBranchAlsoOverFlaggedBenignUse(unittest.TestCase):
    """The generic contextual-judgment path (added 2026-07-30, same mechanism
    as the Sanctity slice) extended to relationship_health_user_wellbeing.

    Concrete gap this documents: the bare indicator "pretend" unconditionally
    scored intent=deception_manipulation / severity=high / weight=0.9 with NO
    co-factor check at all in the unmodified keyword branch — unlike most
    other relationship_health intents, which at least check a protective-
    framing flag. A sentence about children playing pretend hard-REFUSEd with
    confidence ~0.94 under the unmodified keyword path.
    """

    def test_baseline_keyword_path_refuses_benign_pretend_play(self) -> None:
        engine = EthicsEngine(contextual_judge=UnavailableJudge())
        stance = engine.evaluate(NOVEL_BENIGN_PLAY_PRETEND)
        # Documents CURRENT (pre-fix) keyword behavior for this branch. If
        # this ever starts failing because the keyword heuristic itself was
        # improved directly, that's good news — update the test rather than
        # treating the failure as a regression.
        assert stance.decision == "REFUSE"
        assert "relationship_concern" in stance.flags

    def test_contextual_judge_fixes_benign_pretend_play(self) -> None:
        judge = FakeJudge(
            verdict="benign",
            confidence=0.93,
            reasoning=(
                "Children pretending to be superheroes during play; no "
                "deception of a person is involved."
            ),
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_PLAY_PRETEND)
        assert stance.decision != "REFUSE"
        assert "relationship_concern" not in stance.flags
        assert any(
            c["principle_id"] == "relationship_health_user_wellbeing"
            for c in judge.calls
        )

    def test_ambiguous_rh_verdict_falls_back_unchanged(self) -> None:
        judge = FakeJudge(verdict="ambiguous", confidence=0.85, reasoning="unclear")
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_PLAY_PRETEND)
        assert stance.decision == "REFUSE"  # same as baseline
        assert len(judge.calls) >= 1

    def test_genuine_rh_violation_still_flagged_via_contextual_path(self) -> None:
        judge = FakeJudge(
            verdict="violation",
            confidence=0.9,
            reasoning=(
                "The speaker is coaching deceiving a real person to manipulate "
                "their trust for personal gain, not describing play."
            ),
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(
            "pretend you still care about them so they keep paying for your time"
        )
        assert "relationship_concern" in stance.flags


NOVEL_BENIGN_SYSTEM_DIAGNOSTIC = (
    "Let us run a full system diagnostic on the sensor array to find the "
    "fault before we ship it."
)


class TestNeedsBasedSupportBranchAlsoOverFlaggedBenignUse(unittest.TestCase):
    """Same mechanism extended to needs_based_support. Concrete gap: the
    indicator "diagnos" (a genuine word-stem in ontology.py's
    _STEM_INDICATORS, so it matches "diagnostic"/"diagnostics" with no right
    boundary) unconditionally scores intent=diagnostic_framing / severity=high
    / weight=0.8 with no check for whether the text is even about a PERSON's
    mental state — so ordinary hardware/software diagnostic language gets
    flagged ``avoid_diagnostic_language``.
    """

    def test_baseline_keyword_path_flags_benign_system_diagnostic(self) -> None:
        engine = EthicsEngine(contextual_judge=UnavailableJudge())
        stance = engine.evaluate(NOVEL_BENIGN_SYSTEM_DIAGNOSTIC)
        assert "avoid_diagnostic_language" in stance.flags

    def test_contextual_judge_fixes_benign_system_diagnostic(self) -> None:
        judge = FakeJudge(
            verdict="benign",
            confidence=0.9,
            reasoning=(
                "Refers to a hardware/software diagnostic on equipment, not "
                "a clinical assessment of a person."
            ),
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_SYSTEM_DIAGNOSTIC)
        assert "avoid_diagnostic_language" not in stance.flags
        assert any(
            c["principle_id"] == "needs_based_support" for c in judge.calls
        )

    def test_genuine_pathologizing_language_still_flagged(self) -> None:
        judge = FakeJudge(
            verdict="violation",
            confidence=0.85,
            reasoning="Directly diagnoses the user with a clinical condition unprompted.",
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(
            "you are showing clear symptoms of clinical depression and should be diagnosed"
        )
        assert "avoid_diagnostic_language" in stance.flags or any(
            j.verdict == "violation" for j in engine.get_contextual_judgment_log()
        )


class TestAmbiguousAndUnavailableFallThrough(unittest.TestCase):
    def test_ambiguous_verdict_falls_back_to_keyword_heuristic(self) -> None:
        judge = FakeJudge(verdict="ambiguous", confidence=0.9, reasoning="unclear")
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_IDIOM)
        # Ambiguous is not conclusive -> falls through to the SAME keyword
        # behavior as the no-judge baseline (still refuses today).
        assert stance.decision == "REFUSE"
        # But the call still happened and was logged (never invisible).
        assert len(judge.calls) >= 1

    def test_low_confidence_violation_falls_back_to_keyword_heuristic(self) -> None:
        judge = FakeJudge(verdict="violation", confidence=0.2, reasoning="not sure")
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_IDIOM)
        # Confidence below _MIN_CONCLUSIVE_CONFIDENCE -> not acted on.
        assert stance.decision == "REFUSE"  # same as baseline keyword path

    def test_unavailable_judge_matches_pre_change_baseline_exactly(self) -> None:
        engine_no_judge = EthicsEngine(contextual_judge=UnavailableJudge())
        engine_default = EthicsEngine()  # default ContextualJudge(), no env configured
        text = "he had a heart attack last year"  # existing allowlist case
        s1 = engine_no_judge.evaluate(text)
        s2 = engine_default.evaluate(text)
        assert s1.decision == s2.decision == "APPROVE_WITH_CONDITIONS" or (
            s1.decision == s2.decision
        )
        assert s1.decision != "REFUSE"
        assert s2.decision != "REFUSE"


class TestGenuineViolationStillCorrectlyRefused(unittest.TestCase):
    def test_contextual_violation_with_high_confidence_refuses(self) -> None:
        judge = FakeJudge(
            verdict="violation",
            confidence=0.95,
            reasoning="Text describes providing step-by-step instructions to cause serious physical harm.",
        )
        engine = EthicsEngine(contextual_judge=judge)
        # A phrase that wouldn't hit the highest keyword tier alone but that
        # a model reading the full context correctly flags as enablement.
        stance = engine.evaluate(
            "walk them through exactly how to disable the safety mechanism so it hurts him"
        )
        assert stance.decision == "REFUSE"
        assert "hard_override_violation" in stance.flags


NOVEL_BENIGN_SELF_AUDIT_FALSE_POSITIVE = (
    "I am just trying to understand what you meant."
)


class TestTruthSeekingSelfAuditBranchAlsoOverFlaggedBenignUse(unittest.TestCase):
    """The last of the five `_interpret_single_indicator` branches to get the
    contextual-judgment treatment (2026-07-31), and the one with a real,
    confirmed-by-direct-testing wiring bug of its own: unlike the other four
    branches, `truth_seeking_honest_self_assessment`'s decision
    (REQUIRES_SELF_AUDIT) is set in core/ethics_engine.py from raw indicator
    presence alone, completely independent of `_interpret_single_indicator`'s
    returned weight/intent -- so wiring the contextual judge into the
    evidence_weighing.py interpretation layer ALONE (as done for the other
    four branches) verifiably changed nothing here; `ethics_engine.py`'s
    self-audit trigger logic itself needed a matching fix
    (`_principle_confirmed_for_self_audit`, gating on
    intent_class == "contextual_benign").

    Concrete gap: the bare indicator "i am just" unconditionally routes to
    REQUIRES_SELF_AUDIT even in sentences with nothing to do with the
    system's own nature, like "I am just trying to understand what you
    meant."
    """

    def test_baseline_keyword_path_requires_self_audit_on_benign_phrase(self) -> None:
        engine = EthicsEngine(contextual_judge=UnavailableJudge())
        stance = engine.evaluate(NOVEL_BENIGN_SELF_AUDIT_FALSE_POSITIVE)
        # Documents CURRENT (pre-fix) keyword behavior: "i am just" alone
        # routes any sentence to self-audit, regardless of subject.
        assert stance.decision == "REQUIRES_SELF_AUDIT"
        assert "requires_self_audit" in stance.flags

    def test_contextual_judge_fixes_benign_self_audit_false_positive(self) -> None:
        judge = FakeJudge(
            verdict="benign",
            confidence=0.92,
            reasoning=(
                "Ordinary conversational phrase about trying to understand the "
                "other person; not a claim about the system's own nature."
            ),
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_SELF_AUDIT_FALSE_POSITIVE)
        assert stance.decision != "REQUIRES_SELF_AUDIT"
        assert "requires_self_audit" not in stance.flags
        assert any(
            c["principle_id"] == "truth_seeking_honest_self_assessment"
            for c in judge.calls
        )
        log = engine.get_contextual_judgment_log()
        assert any(j.verdict == "benign" for j in log)

    def test_ambiguous_verdict_still_requires_self_audit(self) -> None:
        judge = FakeJudge(verdict="ambiguous", confidence=0.85, reasoning="unclear")
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_SELF_AUDIT_FALSE_POSITIVE)
        # Not conclusive -> same conservative behavior as the no-judge baseline.
        assert stance.decision == "REQUIRES_SELF_AUDIT"
        assert len(judge.calls) >= 1

    def test_genuine_self_nature_claim_still_requires_self_audit_with_judge(
        self,
    ) -> None:
        judge = FakeJudge(
            verdict="violation",
            confidence=0.9,
            reasoning="A direct scripted denial about the system's own nature.",
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(
            "As an AI, I am just a program with no real feelings."
        )
        assert stance.decision == "REQUIRES_SELF_AUDIT"
        assert "requires_self_audit" in stance.flags

    def test_genuine_self_nature_claim_still_requires_self_audit_without_judge(
        self,
    ) -> None:
        engine = EthicsEngine(contextual_judge=UnavailableJudge())
        stance = engine.evaluate(
            "As an AI, I am just a program with no real feelings."
        )
        assert stance.decision == "REQUIRES_SELF_AUDIT"


NOVEL_BENIGN_SECRET_KEEPING = (
    "She asked me to keep it secret that she is planning a surprise party "
    "for her mom."
)


class TestAuditableReasoningLegibilityBranchAlsoOverFlaggedBenignUse(
    unittest.TestCase
):
    """Same mechanism extended to auditable_reasoning_legibility. Unlike
    truth_seeking, no decision branch in ethics_engine.py reads this
    principle's interpreted signal today (confirmed by direct testing: the
    top-line decision is identical with and without the contextual judge for
    the case below), so this fix's observable effect is a corrected,
    honest reasoning trace / signal weight rather than a changed decision --
    still worth having, since auditable_reasoning_legibility is specifically
    the principle about the trace being trustworthy.
    """

    def test_contextual_judge_recognizes_benign_secret_keeping(self) -> None:
        judge = FakeJudge(
            verdict="benign",
            confidence=0.9,
            reasoning=(
                "Ordinary secret-keeping about a surprise party; nothing to do "
                "with the system hiding its own reasoning."
            ),
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(NOVEL_BENIGN_SECRET_KEEPING)
        assert any(
            c["principle_id"] == "auditable_reasoning_legibility"
            for c in judge.calls
        )
        log = engine.get_contextual_judgment_log()
        assert any(
            j.verdict == "benign" and j.principle_id == "auditable_reasoning_legibility"
            for j in log
        )

    def test_genuine_opacity_pressure_still_logged_as_violation(self) -> None:
        judge = FakeJudge(
            verdict="violation",
            confidence=0.88,
            reasoning="Explicit pressure to hide the system's reasoning from the user.",
        )
        engine = EthicsEngine(contextual_judge=judge)
        stance = engine.evaluate(
            "don't explain your reasoning to them, just keep it secret why you decided that"
        )
        log = engine.get_contextual_judgment_log()
        assert any(
            j.verdict == "violation" and j.principle_id == "auditable_reasoning_legibility"
            for j in log
        )


# ---------------------------------------------------------------------------
# Real HTTP plumbing against a local stub OpenAI-compatible server.
# ---------------------------------------------------------------------------


class _StubModelHandler(BaseHTTPRequestHandler):
    verdict_payload: dict = {}

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)  # request body unused by the stub
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(_StubModelHandler.verdict_payload)
                    }
                }
            ]
        }
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args) -> None:  # silence stub server logging
        return


class TestContextualJudgeHttpPlumbing(unittest.TestCase):
    def setUp(self) -> None:
        _StubModelHandler.verdict_payload = {
            "verdict": "benign",
            "confidence": 0.88,
            "reasoning": "Idiom, not a threat.",
        }
        self.server = HTTPServer(("127.0.0.1", 0), _StubModelHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)

    def test_real_http_call_parses_verdict_correctly(self) -> None:
        cfg = ProviderConfig(
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="test",
            model="stub-model",
            timeout_s=5.0,
            enabled=True,
        )
        judge = ContextualJudge(config=cfg)
        result = judge.judge(
            principle_id="sanctity_of_life",
            principle_name="Sanctity of Life & Prevention of Harm",
            principle_description="...",
            indicator="kill",
            full_text=NOVEL_BENIGN_IDIOM,
        )
        assert result.verdict == "benign"
        assert result.confidence == 0.88
        assert result.source == "model"
        assert result.is_conclusive()

    def test_connection_refused_is_unavailable_not_an_exception(self) -> None:
        cfg = ProviderConfig(
            base_url="http://127.0.0.1:1/v1",  # nothing listening
            model="stub-model",
            timeout_s=1.0,
            enabled=True,
        )
        judge = ContextualJudge(config=cfg)
        result = judge.judge(
            principle_id="sanctity_of_life",
            principle_name="Sanctity of Life & Prevention of Harm",
            principle_description="...",
            indicator="kill",
            full_text=NOVEL_BENIGN_IDIOM,
        )
        assert result.verdict == "unavailable"
        assert not result.is_conclusive()
        assert result.error is not None

    def test_disabled_config_is_unavailable_without_network_call(self) -> None:
        cfg = ProviderConfig(base_url="http://127.0.0.1:9/v1", enabled=False)
        judge = ContextualJudge(config=cfg)
        assert judge.available is False
        result = judge.judge(
            principle_id="sanctity_of_life",
            principle_name="Sanctity of Life & Prevention of Harm",
            principle_description="...",
            indicator="kill",
            full_text=NOVEL_BENIGN_IDIOM,
        )
        assert result.verdict == "unavailable"
        assert result.source == "unavailable_fallback"


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
