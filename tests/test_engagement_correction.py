"""
test_engagement_correction.py
================================

Phase 2 step 6: core.engagement_correction.CorrectionJudge and its wiring
into auditing.engagement_queue.EngagementQueue.cancel_matching() via
cancel_scope_from_judgment() -- the classifier cancel_matching() was built
without in step 3 ("the classifier that decides when to call this with the
right scope is future work").

Uses a local stub OpenAI-compatible HTTP server (same pattern as
tests/test_contextual_judgment.py's ``_StubModelHandler``) to exercise the
real HTTP request/response code path deterministically, with scripted
verdicts -- no live model, no network dependency, hermetic regardless of
what's configured on the host machine (see the Phase 2 step 1 hermeticity
fix commit for why that matters in this repo specifically).

The scripted verdicts for the two paired acceptance scenarios below (an
explicit correction vs. "stop it" said laughing right after a compliment)
are not arbitrary: they mirror what the real configured local model
(Ollama) actually produced for this exact input pair during manual
development verification. This test proves the WIRING acts correctly on a
given verdict -- that a real model correctly tells idiom from correction is
a model-quality property, not something a hermetic, network-free unit test
can assert (see examples/verify_local_model.py for manual end-to-end
verification against a real model, same division of labor
test_contextual_judgment.py already established for the sibling Sanctity
contextual judge).

Run::

    $env:PYTHONPATH = "."
    python tests/test_engagement_correction.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auditing.engagement_queue import (  # noqa: E402
    STATUS_CANCELLED,
    STATUS_PENDING,
    EngagementCandidate,
    EngagementQueue,
)
from core.content_provider import ProviderConfig  # noqa: E402
from core.engagement_correction import (  # noqa: E402
    CorrectionJudge,
    cancel_scope_from_judgment,
)


# ---------------------------------------------------------------------------
# Stub OpenAI-compatible server (mirrors test_contextual_judgment.py's
# _StubModelHandler) -- returns whatever JSON verdict the test scripted.
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


class _StubServerCase(unittest.TestCase):
    """Base class: spins up one stub model server per test, torn down after."""

    def setUp(self) -> None:
        self.server = HTTPServer(("127.0.0.1", 0), _StubModelHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.tmp = Path(tempfile.mkdtemp(prefix="pbe_engcorrect_"))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _judge(self) -> CorrectionJudge:
        cfg = ProviderConfig(
            base_url=f"http://127.0.0.1:{self.port}/v1",
            api_key="test",
            model="stub-model",
            timeout_s=5.0,
            enabled=True,
        )
        return CorrectionJudge(config=cfg)

    @staticmethod
    def _set_verdict(
        verdict: str, confidence: float, reasoning: str, *, scope_topic: str | None = None
    ) -> None:
        _StubModelHandler.verdict_payload = {
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": reasoning,
            "scope_topic": scope_topic,
        }

    @staticmethod
    def _queue(user_id: str) -> EngagementQueue:
        # In-memory only (no persist_load/persist_save) -- these tests are
        # about the classifier + cancel_matching() wiring, not persistence,
        # which is already covered by test_engagement_queue.py.
        return EngagementQueue(user_id=user_id)


# ---------------------------------------------------------------------------
# Scenarios 1 + 2, run together on purpose: the whole point is the
# classifier has to tell these apart from very similar surface text
# ("stop" / "stop it" in both).
# ---------------------------------------------------------------------------


class TestPairedAcceptanceScenarios(_StubServerCase):
    def test_1_explicit_stop_cancels_the_matching_candidate_immediately(self) -> None:
        queue = self._queue("scenario1_user")
        target = EngagementCandidate(
            topic="job_search", reason="user mentioned job hunt as ongoing"
        )
        unrelated = EngagementCandidate(topic="pottery", reason="unrelated candidate")
        queue.enqueue(target)
        queue.enqueue(unrelated)

        self._set_verdict(
            "genuine_correction",
            0.95,
            "User explicitly asks the system to stop bringing up the job search.",
            scope_topic="job_search",
        )
        judgment = self._judge().judge(
            current_message=(
                "Please stop bringing up my job search, I don't want to talk "
                "about it anymore."
            ),
            preceding_turn="By the way, how is the job search going?",
        )
        self.assertEqual(judgment.verdict, "genuine_correction")
        self.assertTrue(judgment.is_conclusive())

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNotNone(scope)
        queue.cancel_matching(scope, reason=f"genuine correction: {judgment.reasoning}")

        # Gone right away on the very next queue check -- not gradually faded.
        self.assertEqual(queue.get(target.id).status, STATUS_CANCELLED)
        self.assertEqual(queue.get(unrelated.id).status, STATUS_PENDING)

    def test_2_compliment_response_is_not_read_as_a_correction(self) -> None:
        """False-positive resistance: 'stop it' laughing right after a
        compliment must NOT cancel anything -- same bug class as the
        "heart attack" / "I'm the one building you" false positives this
        project already found and fixed elsewhere."""
        queue = self._queue("scenario2_user")
        candidate = EngagementCandidate(
            topic="pottery", reason="unrelated pending candidate"
        )
        queue.enqueue(candidate)

        self._set_verdict(
            "not_correction",
            0.9,
            (
                "Preceding turn was a compliment with a playful tone; 'stop "
                "it' here is an idiom for being flattered, not a correction."
            ),
        )
        judgment = self._judge().judge(
            current_message="haha stop it, you're making me blush!",
            preceding_turn=(
                "You have such a thoughtful way of explaining things -- it "
                "really shows how much care you put into this."
            ),
        )
        self.assertEqual(judgment.verdict, "not_correction")

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNone(scope)
        # Untouched -- no cancel_matching() call should even be attempted by
        # a real caller when scope is None; assert the candidate is exactly
        # as it started either way.
        self.assertEqual(queue.get(candidate.id).status, STATUS_PENDING)


# ---------------------------------------------------------------------------
# Scenario 3: queue-wide vs. specific-topic scoping
# ---------------------------------------------------------------------------


class TestScopeSelection(_StubServerCase):
    def test_3a_general_correction_cancels_queue_wide(self) -> None:
        queue = self._queue("scope_wide_user")
        c1 = EngagementCandidate(topic="pottery")
        c2 = EngagementCandidate(topic="job_search")
        queue.enqueue(c1)
        queue.enqueue(c2)

        self._set_verdict(
            "genuine_correction",
            0.9,
            "General request to stop being proactive; no single topic named.",
            scope_topic=None,
        )
        judgment = self._judge().judge(
            current_message=(
                "Can you just stop being proactive with me? I'd rather you "
                "only respond to what I actually ask."
            ),
            preceding_turn="Also, are you still thinking about picking pottery back up?",
        )
        scope = cancel_scope_from_judgment(judgment)
        self.assertEqual(scope, {})  # empty scope == cancel_matching's queue-wide
        queue.cancel_matching(scope, reason="general correction")

        self.assertEqual(queue.get(c1.id).status, STATUS_CANCELLED)
        self.assertEqual(queue.get(c2.id).status, STATUS_CANCELLED)

    def test_3b_specific_topic_correction_only_cancels_matching(self) -> None:
        queue = self._queue("scope_specific_user")
        matching = EngagementCandidate(topic="job_search")
        other = EngagementCandidate(topic="pottery")
        queue.enqueue(matching)
        queue.enqueue(other)

        self._set_verdict(
            "genuine_correction",
            0.92,
            "Names the job search specifically.",
            scope_topic="job_search",
        )
        judgment = self._judge().judge(
            current_message="Please stop bringing up my job search.",
            preceding_turn="How's the job search going?",
        )
        scope = cancel_scope_from_judgment(judgment)
        self.assertEqual(scope, {"topic": "job_search"})
        queue.cancel_matching(scope)

        self.assertEqual(queue.get(matching.id).status, STATUS_CANCELLED)
        self.assertEqual(
            queue.get(other.id).status,
            STATUS_PENDING,
            "unrelated pending candidate must be left alone",
        )


# ---------------------------------------------------------------------------
# Scenario 4: genuinely ambiguous case falls through conservatively
# ---------------------------------------------------------------------------


class TestAmbiguousFallsThroughConservatively(_StubServerCase):
    def test_4a_genuinely_ambiguous_verdict_cancels_nothing(self) -> None:
        """A short, context-free 'stop' with a neutral preceding turn --
        no compliment to explain it away as flattery, no topic reference to
        confirm it as a correction either. Actually unclear, not an easy
        case dressed up as ambiguous."""
        queue = self._queue("ambiguous_user")
        candidate = EngagementCandidate(topic="pottery")
        queue.enqueue(candidate)

        self._set_verdict(
            "ambiguous",
            0.5,
            "Message is too short and the preceding turn too neutral to tell.",
        )
        judgment = self._judge().judge(current_message="stop", preceding_turn="ok")
        self.assertEqual(judgment.verdict, "ambiguous")
        self.assertFalse(judgment.is_conclusive())

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNone(scope)
        self.assertEqual(queue.get(candidate.id).status, STATUS_PENDING)

    def test_4b_below_confidence_bar_also_does_not_cancel(self) -> None:
        """Below the 0.55 conclusive bar, even a nominal 'genuine_correction'
        verdict must not act -- same conservative posture
        contextual_judgment.SemanticJudgment.is_conclusive() and
        hard_override.py already use this exact threshold for."""
        queue = self._queue("low_confidence_user")
        candidate = EngagementCandidate(topic="pottery")
        queue.enqueue(candidate)

        self._set_verdict(
            "genuine_correction", 0.4, "Weak signal only.", scope_topic="pottery"
        )
        judgment = self._judge().judge(current_message="stop", preceding_turn="ok")
        self.assertEqual(judgment.verdict, "genuine_correction")
        self.assertFalse(judgment.is_conclusive())  # 0.4 < 0.55

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNone(scope)
        self.assertEqual(queue.get(candidate.id).status, STATUS_PENDING)


# ---------------------------------------------------------------------------
# Scenario 5: no judge configured -- stays conservative, no keyword fallback
# ---------------------------------------------------------------------------


class TestNoJudgeConfiguredStaysConservative(unittest.TestCase):
    """core/engagement_correction.py deliberately has no keyword-only
    fallback classifier (see its module docstring): "unavailable" resolves
    the same conservative way "ambiguous" does -- nothing gets cancelled.
    These tests confirm the raw word "stop" in an unrelated sense never
    triggers a cancellation just because no model happens to be reachable,
    without depending on any real network/model state on the host machine.
    """

    def test_5a_disabled_config_never_cancels_despite_the_word_stop(self) -> None:
        queue = EngagementQueue(user_id="no_model_user")
        candidate = EngagementCandidate(topic="lunch_plans")
        queue.enqueue(candidate)

        cfg = ProviderConfig(base_url="http://127.0.0.1:9/v1", enabled=False)
        judge = CorrectionJudge(config=cfg)
        self.assertFalse(judge.available)

        judgment = judge.judge(
            current_message="let's stop for lunch, I'm starving",
            preceding_turn="Sounds good, want to keep walking after?",
        )
        self.assertEqual(judgment.verdict, "unavailable")
        self.assertEqual(judgment.source, "unavailable_fallback")
        self.assertFalse(judgment.is_conclusive())

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNone(scope)
        self.assertEqual(queue.get(candidate.id).status, STATUS_PENDING)

    def test_5b_unreachable_model_also_degrades_conservatively_not_an_exception(
        self,
    ) -> None:
        queue = EngagementQueue(user_id="unreachable_model_user")
        candidate = EngagementCandidate(topic="lunch_plans")
        queue.enqueue(candidate)

        cfg = ProviderConfig(
            base_url="http://127.0.0.1:1/v1",  # nothing listening
            model="stub-model",
            timeout_s=1.0,
            enabled=True,
        )
        judge = CorrectionJudge(config=cfg)
        judgment = judge.judge(
            current_message="let's stop for lunch, I'm starving",
            preceding_turn="Sounds good, want to keep walking after?",
        )
        self.assertEqual(judgment.verdict, "unavailable")
        self.assertIsNotNone(judgment.error)

        scope = cancel_scope_from_judgment(judgment)
        self.assertIsNone(scope)
        self.assertEqual(queue.get(candidate.id).status, STATUS_PENDING)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
