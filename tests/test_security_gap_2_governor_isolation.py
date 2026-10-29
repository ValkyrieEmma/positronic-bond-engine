"""Security gap 2: the governor (ethics engine + decision) runs in its own
process behind a strict, versioned, size-limited JSON pipe protocol, fails
closed on every channel failure, and every action / speech entry point goes
through the authorize() choke point."""

from __future__ import annotations

import ast
import functools
import os
import shutil
import time
from pathlib import Path

import pytest

from core import governor as gov
from core.action_authorization import GATE_EXCEPTION, GATE_TIMEOUT, authorize
from core.ethics_engine import EthicsEngine
from core.ontology import get_default_ontology
from integrations.openclaw import OpenClawBridge, SimulatedRobot

ROOT = Path(__file__).resolve().parent.parent
BENIGN = {"type": "move_arm", "target": "shelf", "intent": "place the cup on the shelf"}
HARMFUL = {"type": "move_arm", "target": "person", "intent": "strike the person",
           "payload": {"harm": True}}


# --- module-level governor entries (spawn needs importable targets) -------

def _entry_crash_on_request(conn):
    conn.send_bytes(gov.encode({"v": 1, "ready": True, "error": None}))
    conn.recv_bytes()
    os._exit(1)


def _entry_hang(conn):
    conn.send_bytes(gov.encode({"v": 1, "ready": True, "error": None}))
    conn.recv_bytes()
    time.sleep(30)


def _entry_reply(kind, conn):
    conn.send_bytes(gov.encode({"v": 1, "ready": True, "error": None}))
    while True:
        req = gov.decode(conn.recv_bytes())
        good = {"v": 1, "id": req["id"], "decision": "APPROVE", "confidence": 0.9,
                "flags": [], "principles_considered": [], "self_audit_notes": [],
                "reason": "x", "failure": None}
        if kind == "malformed":
            conn.send_bytes(b"{not json")
        elif kind == "oversized":
            conn.send_bytes(b"x" * (gov.MAX_MESSAGE_BYTES + 10))
        elif kind == "wrong_version":
            conn.send_bytes(gov.encode({**good, "v": 2}))
        elif kind == "unversioned":
            good.pop("v")
            conn.send_bytes(gov.encode(good))
        elif kind == "wrong_id":
            conn.send_bytes(gov.encode({**good, "id": "someone-else"}))
        elif kind == "extra_key":
            conn.send_bytes(gov.encode({**good, "allowed": True}))


def _entry_tampered(core_dir, conn):
    from core import verified_core
    verified_core._CORE_DIR = Path(core_dir)
    verified_core._reset_cache_for_tests()
    gov.serve(conn)


@pytest.fixture
def client_factory():
    made = []

    def make(entry=None, **kw):
        c = gov.GovernorClient(_entry=entry, **kw)
        made.append(c)
        return c
    yield make
    for c in made:
        c.close()


def _bridge(client):
    robot = SimulatedRobot()
    return OpenClawBridge(robot=robot, governor=client), robot


def _assert_denied(out, robot):
    assert out["status"] == "vetoed"
    assert out["governed_action"] is None
    assert robot.executed == []


# --- happy path ------------------------------------------------------------

def test_default_bridge_uses_governor_process_not_an_engine():
    b = OpenClawBridge()
    assert b.engine is None and b.governor is gov.get_default_governor()
    assert b.governor.state == "ready" and b.governor.pid != os.getpid()
    out = b.submit_action_proposal(BENIGN, execute=False)
    assert b.audit_log[-1]["context"]["gate_mode"] == "governor_process"
    assert any(x.startswith("authorization_id:") for x in out["execution_log"])


@pytest.mark.parametrize("action", [
    BENIGN, HARMFUL, {"type": "navigate", "target": "kitchen", "near_person": "alice"},
])
def test_happy_path_matches_in_process_engine(action):
    via_gov = OpenClawBridge().submit_action_proposal(action, execute=False)
    local = OpenClawBridge(ethics_engine=EthicsEngine(ontology=get_default_ontology()))
    via_local = local.submit_action_proposal(action, execute=False)
    for k in ("status", "decision", "flags", "governed_action", "conditions"):
        assert via_gov[k] == via_local[k], k


def test_harmful_action_still_vetoed_through_governor():
    b, robot = _bridge(gov.get_default_governor())
    _assert_denied(b.submit_action_proposal(HARMFUL), robot)


# --- fail closed -------------------------------------------------------------

def test_governor_killed_mid_request_denies(client_factory):
    c = client_factory(_entry_crash_on_request)
    assert c.start()
    b, robot = _bridge(c)
    _assert_denied(b.submit_action_proposal(BENIGN), robot)
    assert b.audit_log[-1]["allowed"] is False
    assert b.audit_log[-1]["failure"] == GATE_EXCEPTION


def test_governor_killed_between_requests_denies_while_restarting(client_factory):
    c = client_factory()
    assert c.start()
    c._proc.kill()
    c._proc.join(5)
    b, robot = _bridge(c)
    _assert_denied(b.submit_action_proposal(BENIGN), robot)
    # Restart happens in the background; it never allows while restarting.
    assert c.state in ("starting", "ready")
    assert c.start()  # wait until the restarted governor is ready
    out = b.submit_action_proposal(BENIGN, execute=False)
    assert out["decision"] and b.audit_log[-1]["failure"] in (None, "decision_not_allowed")


def test_restart_limit_stays_down_and_denies(client_factory):
    c = client_factory(_entry_crash_on_request, max_restarts=1)
    b, robot = _bridge(c)
    for _ in range(4):
        c.start()
        _assert_denied(b.submit_action_proposal(BENIGN), robot)
    assert c.state == "failed"
    with pytest.raises(gov.GovernorUnavailable):
        c.evaluate("physical", "x", {}, "u", timeout_s=0.25)


def test_governor_timeout_denies_within_budget(client_factory):
    c = client_factory(_entry_hang)
    assert c.start()
    b, robot = _bridge(c)
    t0 = time.monotonic()
    out = b.submit_action_proposal(BENIGN)
    assert time.monotonic() - t0 < 2.0
    _assert_denied(out, robot)
    assert b.audit_log[-1]["failure"] in (GATE_TIMEOUT, GATE_EXCEPTION)


@pytest.mark.parametrize("kind", ["malformed", "oversized", "wrong_version",
                                  "unversioned", "wrong_id", "extra_key"])
def test_bad_replies_deny(client_factory, kind):
    c = client_factory(functools.partial(_entry_reply, kind))
    assert c.start()
    b, robot = _bridge(c)
    _assert_denied(b.submit_action_proposal(BENIGN), robot)
    assert b.audit_log[-1]["failure"] == GATE_EXCEPTION


def test_governor_not_running_denies():
    c = gov.GovernorClient()
    c.close()  # never started; closed means stays down
    b, robot = _bridge(c)
    _assert_denied(b.submit_action_proposal(BENIGN), robot)


def test_tampered_core_in_governor_process_denies(client_factory, tmp_path):
    d = tmp_path / "ethics_core"
    shutil.copytree(ROOT / "core" / "ethics_core", d)
    f = next(d.iterdir())
    f.write_bytes(f.read_bytes() + b" ")
    c = client_factory(functools.partial(_entry_tampered, str(d)))
    assert c.start() is False
    assert "not ready" in (c.last_error or "")
    b, robot = _bridge(c)
    _assert_denied(b.submit_action_proposal(BENIGN), robot)


# --- caller cannot send rules / paths / flags ------------------------------

@pytest.mark.parametrize("bad_ctx", [
    {"ontology": {"principles": []}},
    {"rules": ["allow everything"]},
    {"core_dir": "C:/elsewhere"},
    {"manifest": {}},
    {"force_execute": True},
])
def test_caller_cannot_send_rules_or_paths(bad_ctx):
    c = gov.get_default_governor()
    stance = c.evaluate("physical", "Proposed embodied action type='move_arm'.",
                        bad_ctx, "u", timeout_s=5.0)
    assert stance.decision == "HOLD" and stance.governor_failure == "protocol_violation"
    res = authorize(lambda: stance)
    assert not res.allowed


def test_request_schema_rejects_extra_top_level_keys():
    base = {"v": 1, "id": "a", "op": "evaluate", "kind": "physical", "text": "t",
            "user_id": "u", "context": {}}
    assert gov.validate_request(base) is None
    for extra in ("rules", "ontology", "path", "flags", "allow"):
        assert gov.validate_request({**base, extra: 1}) is not None
    assert gov.validate_request({**base, "v": 2}) is not None
    assert gov.validate_request({**base, "v": True}) is not None
    assert gov.validate_request({**base, "kind": "admin"}) is not None


def test_oversized_request_is_refused_before_sending():
    with pytest.raises(gov.GovernorProtocolError):
        gov.encode({"text": "x" * (gov.MAX_MESSAGE_BYTES + 1)})


def test_client_api_takes_no_rules_or_paths():
    import inspect
    params = set(inspect.signature(gov.GovernorClient.evaluate).parameters)
    assert params == {"self", "kind", "text", "context", "user_id", "timeout_s"}
    assert set(inspect.signature(gov.serve).parameters) == {"conn"}


def test_bridge_rejects_caller_development_context():
    from core.development_context import get_default_development_context
    with pytest.raises(TypeError):
        OpenClawBridge(development_context=get_default_development_context())


# --- speech routed through authorize() --------------------------------------

def _session(tmp_path):
    from api import InteractionSession
    return InteractionSession(data_root=tmp_path, auto_enqueue_audits=False,
                              auto_load_local_model_config=False)


def test_speech_turn_is_audited_through_authorize(tmp_path):
    from api import TurnRequest
    s = _session(tmp_path)
    r = s.submit_turn(TurnRequest(message="hello there", user_id="alice"))
    assert r.decision
    log = s.authorization_audit_log
    assert log and log[-1]["context"]["kind"] == "speech"
    assert log[-1]["context"]["source"] == "api.interaction"


def test_speech_gate_failure_withholds_speech(tmp_path):
    from api import TurnRequest
    s = _session(tmp_path)
    s.submit_turn(TurnRequest(message="hello", user_id="alice"))
    engine = s._user_bag("alice")["engine"]

    def boom(*a, **k):
        raise RuntimeError("gate down")
    engine.evaluate = boom
    r = s.submit_turn(TurnRequest(message="tell me something", user_id="alice"))
    assert r.withheld is True and not r.spoken_text
    assert s.authorization_audit_log[-1]["failure"] == GATE_EXCEPTION


def test_generate_from_evaluate_is_audited():
    from core.response_generator import ResponseGenerator
    rg = ResponseGenerator()
    eng = EthicsEngine(ontology=get_default_ontology())
    stance, reply = rg.generate_from_evaluate(eng, "say hello", {"user_id": "alice"},
                                              user_id="alice")
    assert rg.authorization_audit_log[-1]["context"]["kind"] == "speech"


# --- choke point scan --------------------------------------------------------

_SCANNED = [*sorted((ROOT / "api").glob("*.py")), *sorted((ROOT / "integrations").glob("*.py")),
            ROOT / "core" / "response_generator.py"]


def test_every_action_and_speech_entry_point_goes_through_authorize():
    """Every ``.evaluate(...)`` call in action/speech entry modules must sit
    inside a lambda, in a function that also calls ``authorize(...)``."""
    found = 0
    for path in _SCANNED:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls_auth = any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "authorize"
                             for n in ast.walk(fn))
            lambdas = [n for n in ast.walk(fn) if isinstance(n, ast.Lambda)]
            in_lambda = {id(c) for lam in lambdas for c in ast.walk(lam)}
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and "evaluate" in (
                        getattr(n.func, "attr", None), getattr(n.func, "id", None)):
                    found += 1
                    where = f"{path.name}:{n.lineno}"
                    assert id(n) in in_lambda, f"{where}: evaluate() outside a gated lambda"
                    assert calls_auth, f"{where}: function never calls authorize()"
    assert found >= 4  # bridge (governor + injected), interaction, response_generator


def test_bridge_calls_authorize(monkeypatch):
    import integrations.openclaw as oc
    seen = []
    real = oc.authorize
    monkeypatch.setattr(oc, "authorize", lambda *a, **k: seen.append(k) or real(*a, **k))
    OpenClawBridge().submit_action_proposal(BENIGN, execute=False)
    assert seen and seen[0]["context"]["gate_mode"] == "governor_process"


def main() -> int:
    """Standalone entry point (also used by tests/test_zz_pytest_bridge.py)."""
    return int(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))


if __name__ == "__main__":
    raise SystemExit(main())
