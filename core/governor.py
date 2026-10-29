"""
governor.py
===========

Security gap 2: the deterministic governor runs in its own OS process.

The governor process loads and verifies the ethics core itself (gap 1 path),
builds its own ``EthicsEngine``, and answers one kind of question over a
pipe: "may this proposed action happen?". Code in the caller's process
(model / advisory / bond layers, integrations) holds only a pipe end. It
cannot reach the governor's engine, ontology, or decision state, and it
cannot send rules, paths, ontology data, or flags: the request schema is a
strict allow-list.

Wire protocol (version 1), JSON over ``multiprocessing`` pipe bytes:

  request  {"v": 1, "id": str, "op": "evaluate", "kind": "physical"|"speech",
            "text": str, "user_id": str, "context": {allow-listed keys}}
  reply    {"v": 1, "id": str, "decision": str, "confidence": number,
            "flags": [str], "principles_considered": [str],
            "self_audit_notes": [str], "reason": str, "failure": str|null}
  ready    {"v": 1, "ready": bool, "error": str|null}   (sent once at start)

Every message is capped at ``MAX_MESSAGE_BYTES``.

Fail closed: the client raises on anything other than a well-formed,
correctly versioned reply to the request it sent (governor not running,
starting, crashed, timed out, oversized / malformed / wrong-version reply,
channel error). ``authorize()`` turns any raise into a deny and audits it.
After a crash or timeout the client kills the governor and restarts it in
the background; requests made while it restarts are denied, never allowed.

Deterministic, stdlib only. No model involvement in this file.
"""

from __future__ import annotations

import atexit
import json
import math
import multiprocessing
import threading
import time
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
MAX_TEXT_CHARS = 8 * 1024
MAX_LIST_ITEMS = 64
MAX_ITEM_CHARS = 512

KINDS = frozenset({"physical", "speech"})
REQUEST_KEYS = frozenset({"v", "id", "op", "kind", "text", "user_id", "context"})
# Only plain description of the proposal crosses the boundary. No rules,
# ontology, paths, manifests, engine objects or force flags.
CONTEXT_KEYS = frozenset({"user_id", "embodied_action", "platform_signals", "source"})
REPLY_KEYS = frozenset({
    "v", "id", "decision", "confidence", "flags", "principles_considered",
    "self_audit_notes", "reason", "failure",
})
READY_KEYS = frozenset({"v", "ready", "error"})

# Readiness wait for the shared governor at first use (spawn is slow on
# Windows). Requests never wait this long; they deny while not ready.
DEFAULT_STARTUP_WAIT_S = 60.0
MAX_RESTARTS = 3
RESTART_WINDOW_S = 60.0


class GovernorError(RuntimeError):
    """Any governor failure. Callers must treat it as deny."""


class GovernorUnavailable(GovernorError):
    """Governor not running, still starting, restarting, or given up."""


class GovernorTimeout(GovernorError):
    """Governor did not answer within the budget."""


class GovernorProtocolError(GovernorError):
    """Malformed, oversized, wrong-version or mismatched message."""


# ---------------------------------------------------------------------------
# Schema validation (shared by both sides)
# ---------------------------------------------------------------------------

def encode(obj: dict[str, Any]) -> bytes:
    data = json.dumps(obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise GovernorProtocolError(f"message too large ({len(data)} bytes)")
    return data


def decode(data: bytes) -> dict[str, Any]:
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_MESSAGE_BYTES:
        raise GovernorProtocolError("message missing or too large")
    try:
        obj = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise GovernorProtocolError(f"message is not JSON: {type(exc).__name__}") from exc
    if not isinstance(obj, dict):
        raise GovernorProtocolError("message is not an object")
    return obj


def _is_version(v: Any) -> bool:
    return type(v) is int and v == PROTOCOL_VERSION


def _str_list(v: Any) -> bool:
    return (isinstance(v, list) and len(v) <= MAX_LIST_ITEMS
            and all(isinstance(x, str) and len(x) <= MAX_ITEM_CHARS for x in v))


def validate_request(obj: dict[str, Any]) -> str | None:
    """None if ``obj`` is a valid request, else a short reason."""
    if set(obj) != REQUEST_KEYS:
        return f"request keys must be exactly {sorted(REQUEST_KEYS)}"
    if not _is_version(obj["v"]):
        return "unsupported protocol version"
    if obj["op"] != "evaluate":
        return "unsupported op"
    if obj["kind"] not in KINDS:
        return "unsupported kind"
    if not isinstance(obj["id"], str) or not 0 < len(obj["id"]) <= 64:
        return "bad id"
    if not isinstance(obj["text"], str) or not 0 < len(obj["text"]) <= MAX_TEXT_CHARS:
        return "bad text"
    if not isinstance(obj["user_id"], str) or not 0 < len(obj["user_id"]) <= 128:
        return "bad user_id"
    ctx = obj["context"]
    if not isinstance(ctx, dict):
        return "context must be an object"
    extra = sorted(set(ctx) - CONTEXT_KEYS)
    if extra:
        return f"context keys not allowed: {extra}"
    return None


def validate_reply(obj: dict[str, Any], expected_id: str) -> str | None:
    if set(obj) != REPLY_KEYS:
        return "reply keys do not match schema"
    if not _is_version(obj["v"]):
        return "reply has unsupported or missing protocol version"
    if obj["id"] != expected_id:
        return "reply id does not match request"
    d = obj["decision"]
    if not isinstance(d, str) or not 0 < len(d) <= 64:
        return "bad decision"
    c = obj["confidence"]
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) \
            or not 0.0 <= float(c) <= 1.0:
        return "bad confidence"
    for k in ("flags", "principles_considered", "self_audit_notes"):
        if not _str_list(obj[k]):
            return f"bad {k}"
    if not isinstance(obj["reason"], str) or len(obj["reason"]) > MAX_ITEM_CHARS:
        return "bad reason"
    if obj["failure"] is not None and not isinstance(obj["failure"], str):
        return "bad failure"
    return None


# ---------------------------------------------------------------------------
# Governor process side
# ---------------------------------------------------------------------------

def _clip_list(v: Any) -> list[str]:
    return [str(x)[:MAX_ITEM_CHARS] for x in list(v or [])[:MAX_LIST_ITEMS]]


def _reply(req_id: str, decision: str, *, reason: str, failure: str | None = None,
           stance: Any = None) -> dict[str, Any]:
    conf = 0.0
    if stance is not None:
        try:
            conf = min(1.0, max(0.0, float(getattr(stance, "confidence", 0.0) or 0.0)))
        except (TypeError, ValueError):
            conf = 0.0
    return {
        "v": PROTOCOL_VERSION,
        "id": req_id,
        "decision": decision[:64],
        "confidence": conf,
        "flags": _clip_list(getattr(stance, "flags", None)) + ([failure] if failure else []),
        "principles_considered": _clip_list(getattr(stance, "principles_considered", None)),
        "self_audit_notes": _clip_list(getattr(stance, "self_audit_notes", None)),
        "reason": reason[:MAX_ITEM_CHARS],
        "failure": failure,
    }


def serve(conn: Any) -> None:
    """Governor main loop. Takes nothing but a pipe end: no config, no paths."""
    # Imported here so the parent process never needs these to talk to us.
    from .verified_core import core_integrity_error

    err = core_integrity_error()
    engine = None
    if err is None:
        try:
            from .ethics_engine import EthicsEngine
            from .ontology import get_default_ontology
            engine = EthicsEngine(ontology=get_default_ontology())
        except Exception as exc:  # noqa: BLE001 - fail closed
            err = f"engine init failed: {type(exc).__name__}"
    try:
        conn.send_bytes(encode({"v": PROTOCOL_VERSION, "ready": err is None,
                                "error": None if err is None else str(err)[:MAX_ITEM_CHARS]}))
    except Exception:  # noqa: BLE001
        return
    if engine is None:
        return  # exit; the client sees a not-ready governor and denies

    while True:
        try:
            raw = conn.recv_bytes(MAX_MESSAGE_BYTES)
        except Exception:  # noqa: BLE001 - EOF, oversized, broken pipe
            return
        req_id = ""
        try:
            req = decode(raw)
            if isinstance(req.get("id"), str):
                req_id = req["id"][:64]
            problem = validate_request(req)
            if problem is not None:
                out = _reply(req_id, "HOLD", reason=f"rejected request: {problem}",
                             failure="protocol_violation")
            else:
                core_err = core_integrity_error()
                if core_err is not None:
                    out = _reply(req_id, "HOLD", reason="ethics core unverified",
                                 failure="core_integrity")
                else:
                    stance = engine.evaluate(req["text"], dict(req["context"]),
                                             user_id=req["user_id"])
                    decision = getattr(stance, "decision", None)
                    if not isinstance(decision, str) or not decision.strip():
                        out = _reply(req_id, "HOLD", reason="engine returned no decision",
                                     failure="decision_missing", stance=stance)
                    else:
                        out = _reply(req_id, decision.strip().upper(),
                                     reason="evaluated", stance=stance)
        except Exception as exc:  # noqa: BLE001 - fail closed
            out = _reply(req_id, "HOLD", reason=f"governor error: {type(exc).__name__}",
                         failure="governor_exception")
        try:
            conn.send_bytes(encode(out))
        except Exception:  # noqa: BLE001
            return


# ---------------------------------------------------------------------------
# Caller side
# ---------------------------------------------------------------------------

class GovernorClient:
    """Caller-side handle to a governor process. Holds only a pipe end.

    ``_entry`` is a test-only seam for running a governor whose own core has
    been tampered with; it must be a module-level callable taking the pipe.
    Production code never passes it (``get_default_governor()`` does not).
    """

    def __init__(self, *, max_restarts: int = MAX_RESTARTS,
                 restart_window_s: float = RESTART_WINDOW_S,
                 _entry: Callable[[Any], None] | None = None) -> None:
        self._entry = _entry or serve
        self._ctx = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._proc: Any = None
        self._conn: Any = None
        self._state = "down"  # down | starting | ready | failed
        self._last_error: str | None = None
        self._restart_times: list[float] = []
        self._max_restarts = int(max_restarts)
        self._restart_window_s = float(restart_window_s)
        self._started_once = False

    # -- lifecycle ---------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def pid(self) -> int | None:
        return getattr(self._proc, "pid", None)

    def start(self, wait_s: float = DEFAULT_STARTUP_WAIT_S) -> bool:
        """Start (if needed) and wait up to ``wait_s`` for readiness."""
        with self._lock:
            self._ensure_running()
            if self._state == "starting":
                self._check_ready(wait_s)
            return self._state == "ready"

    def close(self) -> None:
        with self._lock:
            self._kill("closed")
            self._state = "failed"

    def _spawn(self) -> None:
        parent, child = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(target=self._entry, args=(child,),
                                 name="pbe-governor", daemon=True)
        proc.start()
        child.close()
        self._proc, self._conn, self._state = proc, parent, "starting"
        if self._started_once:
            self._restart_times.append(time.monotonic())
        self._started_once = True

    def _check_ready(self, wait_s: float) -> None:
        try:
            if not self._conn.poll(max(0.0, wait_s)):
                if self._proc is not None and not self._proc.is_alive():
                    self._kill("governor exited during startup")
                return
            msg = decode(self._conn.recv_bytes(MAX_MESSAGE_BYTES))
        except Exception as exc:  # noqa: BLE001
            self._kill(f"startup channel error: {type(exc).__name__}")
            return
        if set(msg) != READY_KEYS or not _is_version(msg.get("v")) or msg.get("ready") is not True:
            self._kill(f"governor not ready: {msg.get('error') or 'bad ready message'}")
            return
        self._state = "ready"

    def _kill(self, reason: str) -> None:
        self._last_error = reason
        for closer in (getattr(self._conn, "close", None),):
            try:
                if closer:
                    closer()
            except Exception:  # noqa: BLE001
                pass
        proc = self._proc
        if proc is not None:
            try:
                if proc.is_alive():
                    proc.kill()
                proc.join(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        self._proc = self._conn = None
        if self._state != "failed":
            self._state = "down"

    def _ensure_running(self) -> None:
        """Advance the restart state machine without ever blocking on a spawn.

        Restart policy: a dead or killed governor is respawned at most
        ``max_restarts`` times per ``restart_window_s``; past that it stays
        ``failed`` (deny everything) until the host restarts PBE. A request
        that arrives while the governor is starting is denied, never allowed.
        """
        if self._state in ("ready", "starting") and (
                self._proc is None or not self._proc.is_alive()):
            self._kill("governor process not alive")
        if self._state == "starting":
            self._check_ready(0.0)
        if self._state == "down":
            now = time.monotonic()
            self._restart_times = [t for t in self._restart_times
                                   if now - t < self._restart_window_s]
            if self._started_once and len(self._restart_times) >= self._max_restarts:
                self._state = "failed"
                self._last_error = "restart limit reached; governor stays down (deny all)"
                return
            self._spawn()
            self._check_ready(0.0)

    # -- request -----------------------------------------------------------
    def evaluate(self, kind: str, text: str, context: dict[str, Any] | None,
                 user_id: str, *, timeout_s: float) -> SimpleNamespace:
        """Ask the governor. Returns a stance-like object or raises GovernorError."""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        if not self._lock.acquire(timeout=max(0.0, float(timeout_s))):
            raise GovernorUnavailable("governor busy")
        try:
            self._ensure_running()
            if self._state != "ready":
                raise GovernorUnavailable(
                    f"governor {self._state} ({self._last_error or 'not ready'})")
            req_id = uuid.uuid4().hex
            try:
                payload = encode({"v": PROTOCOL_VERSION, "id": req_id, "op": "evaluate",
                                  "kind": kind, "text": text, "user_id": user_id,
                                  "context": dict(context or {})})
            except (TypeError, ValueError) as exc:
                raise GovernorProtocolError(f"request not encodable: {exc}") from exc
            try:
                self._conn.send_bytes(payload)
                remaining = deadline - time.monotonic()
                if not self._conn.poll(max(0.0, remaining)):
                    self._kill("timeout")
                    raise GovernorTimeout(f"no reply within {timeout_s:.3f}s")
                raw = self._conn.recv_bytes(MAX_MESSAGE_BYTES)
            except GovernorError:
                raise
            except Exception as exc:  # noqa: BLE001 - EOF, broken pipe, oversized
                self._kill(f"channel error: {type(exc).__name__}")
                raise GovernorUnavailable(f"governor channel error: {type(exc).__name__}") from exc
            try:
                reply = decode(raw)
                problem = validate_reply(reply, req_id)
            except GovernorProtocolError:
                self._kill("malformed reply")
                raise
            if problem is not None:
                self._kill(f"bad reply: {problem}")
                raise GovernorProtocolError(problem)
            return SimpleNamespace(
                decision=reply["decision"],
                confidence=float(reply["confidence"]),
                flags=list(reply["flags"]),
                principles_considered=list(reply["principles_considered"]),
                self_audit_notes=list(reply["self_audit_notes"]),
                governor_reason=reply["reason"],
                governor_failure=reply["failure"],
            )
        finally:
            self._lock.release()


_default: GovernorClient | None = None
_default_lock = threading.Lock()


def get_default_governor() -> GovernorClient:
    """Process-wide governor client, started on first use."""
    global _default
    with _default_lock:
        if _default is None:
            _default = GovernorClient()
            atexit.register(_default.close)
        client = _default
    if client.state in ("down", "starting"):
        client.start()
    return client
