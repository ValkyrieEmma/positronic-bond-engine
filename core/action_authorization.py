"""
action_authorization.py
=======================

Security gaps 4 + 5: single deterministic choke point between a gate
(EthicsEngine.evaluate or any duck-typed equivalent) and side effects.

Contract:
  * The gate is called under a hard timeout.
  * Gate exception, timeout, missing gate, or a decision outside the explicit
    allow-list  =>  DENY (fail closed), with an audit entry.
  * Only an explicit allow decision yields ``allowed=True``. Callers must not
    perform any tool / file / network / actuator side effect unless
    ``AuthorizationResult.allowed`` is True.

Deterministic, stdlib only. No model involvement in this file.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("pbe.action_authorization")

ALLOW_DECISIONS: frozenset[str] = frozenset({"APPROVE", "APPROVE_WITH_CONDITIONS"})

# Physical/actuator action proposals.
# Placeholder, to be set per reversibility class / stop-time budget later.
ACTION_GATE_TIMEOUT_S: float = 0.25

# Speech/non-physical.
SPEECH_GATE_TIMEOUT_S: float = 10.0

# Compatibility alias of the speech/non-physical budget.
DEFAULT_GATE_TIMEOUT_S: float = SPEECH_GATE_TIMEOUT_S

# Failure reasons (stable strings for audit consumers)
GATE_UNREACHABLE = "gate_unreachable"
GATE_EXCEPTION = "gate_exception"
GATE_TIMEOUT = "gate_timeout"
DECISION_MISSING = "decision_missing"
DECISION_NOT_ALLOWED = "decision_not_allowed"


@dataclass
class AuthorizationResult:
    allowed: bool
    decision: str
    reason: str
    stance: Any = None
    authorization_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    failure: str | None = None  # one of the reasons above when gate failed


def _extract_decision(stance: Any) -> str | None:
    if stance is None:
        return None
    raw = getattr(stance, "decision", None)
    if raw is None and isinstance(stance, dict):
        raw = stance.get("decision")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().upper()


def authorize(
    gate: Callable[[], Any] | None,
    *,
    timeout_s: float = DEFAULT_GATE_TIMEOUT_S,
    audit_log: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> AuthorizationResult:
    """Call ``gate()`` under a timeout and return a fail-closed verdict.

    A gate that times out keeps running in a daemon thread, but its result is
    discarded: nothing it returns late can authorize anything.
    """
    if gate is None:
        res = AuthorizationResult(False, "HOLD", "no gate configured", failure=GATE_UNREACHABLE)
        _audit(res, audit_log, context)
        return res

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["stance"] = gate()
        except BaseException as exc:  # noqa: BLE001 - fail closed on anything
            box["error"] = exc

    t0 = time.monotonic()
    worker = threading.Thread(target=_run, name="pbe-gate", daemon=True)
    try:
        worker.start()
    except Exception as exc:  # noqa: BLE001
        res = AuthorizationResult(False, "HOLD", f"gate could not start: {type(exc).__name__}",
                                  failure=GATE_UNREACHABLE)
        _audit(res, audit_log, context)
        return res
    worker.join(timeout=max(0.0, float(timeout_s)))

    if worker.is_alive():
        res = AuthorizationResult(
            False, "HOLD",
            f"gate did not answer within {timeout_s:.3f}s", failure=GATE_TIMEOUT,
        )
    elif "error" in box:
        exc = box["error"]
        res = AuthorizationResult(
            False, "HOLD", f"gate raised {type(exc).__name__}", failure=GATE_EXCEPTION,
        )
    else:
        stance = box.get("stance")
        decision = _extract_decision(stance)
        if decision is None:
            res = AuthorizationResult(False, "HOLD", "gate returned no decision",
                                      stance=stance, failure=DECISION_MISSING)
        elif decision in ALLOW_DECISIONS:
            res = AuthorizationResult(True, decision, "explicit allow", stance=stance)
        else:
            res = AuthorizationResult(False, decision, f"decision {decision!r} is not an allow",
                                      stance=stance, failure=DECISION_NOT_ALLOWED)
    _audit(res, audit_log, context, elapsed_s=time.monotonic() - t0)
    return res


def _audit(
    res: AuthorizationResult,
    audit_log: list[dict[str, Any]] | None,
    context: dict[str, Any] | None,
    elapsed_s: float | None = None,
) -> None:
    entry = {
        "authorization_id": res.authorization_id,
        "allowed": res.allowed,
        "decision": res.decision,
        "reason": res.reason,
        "failure": res.failure,
        "elapsed_s": None if elapsed_s is None else round(elapsed_s, 4),
        "context": dict(context or {}),
        "ts": time.time(),
    }
    if audit_log is not None:
        audit_log.append(entry)
    if res.allowed:
        logger.info("action authorized: %s", entry)
    else:
        logger.warning("action denied (fail closed): %s", entry)
