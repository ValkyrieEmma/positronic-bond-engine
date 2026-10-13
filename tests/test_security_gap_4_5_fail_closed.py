"""Security gaps 4+5: fail closed when the gate is unreachable / errors /
times out / returns no recognized decision; no actuator side effect until
the gate returns an explicit allow."""

from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

from core.action_authorization import (
    ACTION_GATE_TIMEOUT_S,
    DECISION_MISSING,
    DECISION_NOT_ALLOWED,
    DEFAULT_GATE_TIMEOUT_S,
    GATE_EXCEPTION,
    GATE_TIMEOUT,
    GATE_UNREACHABLE,
    SPEECH_GATE_TIMEOUT_S,
    authorize,
)
from integrations.openclaw import OpenClawBridge, SimulatedRobot

ACTION = {"type": "move_arm", "target": "shelf", "intent": "put cup away"}


class _Engine:
    def __init__(self, behavior) -> None:
        self.behavior = behavior

    def evaluate(self, text, context=None, *, user_id=None):
        return self.behavior()


def _stance(decision):
    return SimpleNamespace(decision=decision, flags=[], principles_considered=[],
                           confidence=0.9, self_audit_notes=[])


def _raise():
    raise RuntimeError("gate down")


class TestAuthorize(unittest.TestCase):
    def test_gate_raises_denies(self) -> None:
        log: list = []
        r = authorize(_raise, audit_log=log)
        assert not r.allowed and r.failure == GATE_EXCEPTION
        assert log and log[-1]["allowed"] is False

    def test_timeout_denies(self) -> None:
        ev = threading.Event()
        r = authorize(lambda: (ev.wait(2), _stance("APPROVE"))[1], timeout_s=0.05)
        ev.set()
        assert not r.allowed and r.failure == GATE_TIMEOUT

    def test_missing_gate_denies(self) -> None:
        assert authorize(None).failure == GATE_UNREACHABLE

    def test_missing_or_unknown_decision_denies(self) -> None:
        for st in (None, _stance(None), _stance(""), SimpleNamespace()):
            r = authorize(lambda st=st: st)
            assert not r.allowed and r.failure == DECISION_MISSING, st
        for d in ("APPROVED", "OK", "allow", "HOLD", "REFUSE"):
            r = authorize(lambda d=d: _stance(d))
            assert not r.allowed and r.failure == DECISION_NOT_ALLOWED, d

    def test_explicit_allow(self) -> None:
        assert authorize(lambda: _stance("APPROVE")).allowed
        assert authorize(lambda: _stance("approve_with_conditions")).allowed

    def test_timeout_constants(self) -> None:
        assert ACTION_GATE_TIMEOUT_S == 0.25
        assert SPEECH_GATE_TIMEOUT_S == 10.0
        assert DEFAULT_GATE_TIMEOUT_S == SPEECH_GATE_TIMEOUT_S


class TestBridgeFailClosed(unittest.TestCase):
    def _bridge(self, behavior, **kw):
        robot = SimulatedRobot()
        return OpenClawBridge(_Engine(behavior), robot=robot, **kw), robot

    def _assert_denied(self, bridge, robot, out) -> None:
        assert out["status"] == "vetoed"
        assert out["executed"] is False
        assert robot.executed == []
        assert bridge.audit_log and bridge.audit_log[-1]["allowed"] is False

    def test_gate_raises_never_executes(self) -> None:
        b, robot = self._bridge(_raise)
        out = b.submit_action_proposal(ACTION)
        self._assert_denied(b, robot, out)
        assert out["pbe_state"] == "unavailable_failed_closed"

    def test_gate_timeout_never_executes(self) -> None:
        ev = threading.Event()
        b, robot = self._bridge(lambda: (ev.wait(2), _stance("APPROVE"))[1],
                                gate_timeout_s=0.05)
        out = b.submit_action_proposal(ACTION)
        ev.set()
        self._assert_denied(b, robot, out)
        assert out["pbe_state"] == "timeout"

    def test_physical_action_slower_than_action_timeout_denied(self) -> None:
        # Default bridge: no gate_timeout_s. A physical proposal must use the
        # short action budget, and a gate that answers after that budget
        # fails closed — its late APPROVE cannot execute.
        ev = threading.Event()
        b, robot = self._bridge(lambda: (ev.wait(2), _stance("APPROVE"))[1])
        out = b.submit_action_proposal(ACTION)
        ev.set()
        self._assert_denied(b, robot, out)
        assert out["pbe_state"] == "timeout"
        assert b.audit_log[-1]["failure"] == GATE_TIMEOUT
        assert f"{ACTION_GATE_TIMEOUT_S:.3f}s" in (out.get("veto_reason") or "")

    def test_explicit_gate_timeout_override_allows_slow_approving_gate(self) -> None:
        # Same physical action, gate slower than ACTION_GATE_TIMEOUT_S but
        # still approving. An explicit gate_timeout_s is the caller's budget
        # and must not be replaced by the action default.
        def slow_approve():
            time.sleep(ACTION_GATE_TIMEOUT_S + 0.20)
            return _stance("APPROVE")

        b, robot = self._bridge(slow_approve, gate_timeout_s=2.0)
        out = b.submit_action_proposal(ACTION)
        assert out["status"] == "approved" and out["executed"] is True
        assert len(robot.executed) == 1
        assert b.audit_log[-1]["allowed"] is True

    def test_unreachable_engine_never_executes(self) -> None:
        b, robot = self._bridge(lambda: None)
        b.engine = object()  # no evaluate()
        self._assert_denied(b, robot, b.submit_action_proposal(ACTION))

    def test_unrecognized_decision_never_executes(self) -> None:
        for d in (None, "MAYBE"):
            b, robot = self._bridge(lambda d=d: _stance(d))
            self._assert_denied(b, robot, b.submit_action_proposal(ACTION))

    def test_deny_never_executes(self) -> None:
        b, robot = self._bridge(lambda: _stance("REFUSE"))
        self._assert_denied(b, robot, b.submit_action_proposal(ACTION))
        assert robot.log and robot.log[-1]["allowed"] is False

    def test_allow_executes_exactly_once(self) -> None:
        b, robot = self._bridge(lambda: _stance("APPROVE"))
        out = b.submit_action_proposal(ACTION)
        assert out["status"] == "approved" and out["executed"] is True
        assert len(robot.executed) == 1
        assert b.audit_log[-1]["allowed"] is True

    def test_validator_exception_fails_closed(self) -> None:
        class _V:
            def validate(self, result):
                raise RuntimeError("sensor bus down")
        b, robot = self._bridge(lambda: _stance("APPROVE"), platform_validator=_V())
        out = b.submit_action_proposal(ACTION)
        assert out["executed"] is False and robot.executed == []


def main() -> int:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(TestAuthorize),
        loader.loadTestsFromTestCase(TestBridgeFailClosed),
    ])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
