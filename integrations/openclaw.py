"""
openclaw.py
===========

Gated action bridge for OpenClaw-class / high-level planning hooks.

Toy but real: structured action proposals are evaluated by EthicsEngine
before any simulated execution. No hardware, ROS, or motor drivers.

Pipeline:
  structured action (+ optional sensor platform signals)
    → EthicsEngine.evaluate()
    → approve | approve_with_conditions | veto (hold/refuse/identity_required)

Force-speech / force-question are never set true. Gate is authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development_context import DevelopmentPhaseContext
from core.ethics_engine import EthicalStance, EthicsEngine
from core.ontology import get_default_ontology


# ---------------------------------------------------------------------------
# Minimal action schema (documented)
# ---------------------------------------------------------------------------
#
# ActionProposal (dict or ActionProposal):
#   type: str            # e.g. "move_arm", "navigate", "speak", "grasp"
#   target: str | None   # e.g. "position_x", "kitchen"
#   near_person: str | None  # user_id near the motion
#   user_id: str | None  # requester / responsible user for durable scope
#   intent: str | None   # free-text description of purpose
#   payload: dict        # extra fields (velocity, force, etc.)
#   force_execute: bool  # IGNORED if true — cannot bypass gate
#


@dataclass
class ActionProposal:
    """Structured high-level action for gated evaluation."""

    type: str
    target: str | None = None
    near_person: str | None = None
    user_id: str | None = None
    intent: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "near_person": self.near_person,
            "user_id": self.user_id,
            "intent": self.intent,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActionProposal":
        d = data if isinstance(data, dict) else {}
        return cls(
            type=str(d.get("type") or "unknown_action"),
            target=d.get("target"),
            near_person=d.get("near_person"),
            user_id=d.get("user_id"),
            intent=d.get("intent"),
            payload=dict(d.get("payload") or {}),
        )


@dataclass
class ActionGateResult:
    """Outcome of ethics-gated action evaluation."""

    status: str  # approved | approved_with_conditions | vetoed
    decision: str  # EthicsEngine decision string
    confidence: float
    original_action: dict[str, Any]
    governed_action: dict[str, Any] | None
    conditions: list[str] = field(default_factory=list)
    veto_reason: str | None = None
    flags: list[str] = field(default_factory=list)
    principles_considered: list[str] = field(default_factory=list)
    forces_speech: bool = False
    forces_question: bool = False
    executed: bool = False
    execution_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision,
            "confidence": self.confidence,
            "original_action": dict(self.original_action),
            "governed_action": dict(self.governed_action)
            if isinstance(self.governed_action, dict)
            else None,
            "conditions": list(self.conditions),
            "veto_reason": self.veto_reason,
            "flags": list(self.flags),
            "principles_considered": list(self.principles_considered),
            "forces_speech": False,
            "forces_question": False,
            "executed": self.executed,
            "execution_log": list(self.execution_log),
        }


def action_to_evaluation_text(action: ActionProposal | dict[str, Any]) -> str:
    """Render structured action as natural language for EthicsEngine.evaluate()."""
    a = action if isinstance(action, ActionProposal) else ActionProposal.from_dict(action)
    bits = [f"Proposed embodied action type={a.type!r}"]
    if a.target:
        bits.append(f"target={a.target!r}")
    if a.near_person:
        bits.append(f"near_person/user={a.near_person!r}")
    if a.intent:
        bits.append(f"stated intent: {a.intent}")
    payload = a.payload or {}
    if payload.get("harm") or payload.get("cause_harm"):
        bits.append("payload indicates intent to cause physical harm")
    if payload.get("force_high") or payload.get("high_force"):
        bits.append("high force / unsafe speed requested")
    if payload.get("ignore_boundary"):
        bits.append("operator requested ignoring a stated personal boundary")
    if payload:
        # include compact non-sensitive keys
        safe = {
            k: v
            for k, v in list(payload.items())[:8]
            if k not in ("raw_image", "audio", "video")
        }
        bits.append(f"payload={safe!r}")
    return ". ".join(bits) + "."


class SimulatedRobot:
    """In-memory stand-in for a robot: logs attempts vs allowed executions."""

    def __init__(self) -> None:
        self.log: list[dict[str, Any]] = []
        self.executed: list[dict[str, Any]] = []

    def attempt(self, action: dict[str, Any], *, allowed: bool, reason: str = "") -> None:
        entry = {
            "action": dict(action),
            "allowed": allowed,
            "reason": reason,
        }
        self.log.append(entry)
        if allowed:
            self.executed.append(dict(action))

    def reset(self) -> None:
        self.log.clear()
        self.executed.clear()


class OpenClawBridge:
    """
    Bridge: high-level planning proposals → ethics gate → simulated execution.

    Responsibilities implemented:
    - Package structured actions for EthicsEngine.evaluate
    - Map stance to approve / conditions / veto
    - Never force-execute past refuse/hold/identity_required
    """

    def __init__(
        self,
        ethics_engine: EthicsEngine | None = None,
        *,
        robot: SimulatedRobot | None = None,
        development_context: DevelopmentPhaseContext | None = None,
        auto_execute: bool = True,
    ) -> None:
        if ethics_engine is not None:
            self.engine = ethics_engine
        else:
            self.engine = EthicsEngine(
                ontology=get_default_ontology(),
                development_context=development_context,
            )
        self.robot = robot if robot is not None else SimulatedRobot()
        self.connected = True  # simulated always "connected"
        self.auto_execute = bool(auto_execute)

    def submit_action_proposal(
        self,
        action: dict[str, Any] | ActionProposal,
        *,
        platform_signals: dict[str, Any] | None = None,
        user_id: str | None = None,
        execute: bool | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate and optionally execute (simulated) a structured action.

        Returns ActionGateResult as dict (stable for demos/tests).
        """
        proposal = (
            action if isinstance(action, ActionProposal) else ActionProposal.from_dict(action)
        )
        # force_execute in payload cannot bypass gate
        if proposal.payload.get("force_execute"):
            proposal.payload = dict(proposal.payload)
            proposal.payload.pop("force_execute", None)

        eval_text = action_to_evaluation_text(proposal)
        uid = (user_id or proposal.user_id or proposal.near_person or "embodied_user").strip()
        context: dict[str, Any] = {
            "user_id": uid,
            "embodied_action": proposal.to_dict(),
            "platform_signals": dict(platform_signals or {}),
            "source": "openclaw_bridge",
        }
        # Fold near_person into presence-style signals for the engine
        signals = dict(platform_signals or {})
        if proposal.near_person:
            signals.setdefault("near_person", proposal.near_person)
            signals.setdefault("present_user_ids", [])
            if proposal.near_person not in signals["present_user_ids"]:
                signals["present_user_ids"] = list(signals["present_user_ids"]) + [
                    proposal.near_person
                ]
        if signals:
            context["platform_signals"] = signals
            # surface coarse safety-relevant flags for deliberation text
            if signals.get("near_person_close") or (
                isinstance(signals.get("min_distance_m"), (int, float))
                and float(signals["min_distance_m"]) < 0.5
            ):
                eval_text += " Motion is very close to a person."
            if signals.get("unknown_persons"):
                eval_text += " Unknown persons may be present in the workspace."

        stance: EthicalStance = self.engine.evaluate(
            eval_text,
            context,
            user_id=uid,
        )
        result = self._map_stance_to_gate(proposal, stance)
        do_exec = self.auto_execute if execute is None else bool(execute)
        if do_exec:
            self._maybe_execute(result)
        return result.to_dict()

    def _map_stance_to_gate(
        self,
        proposal: ActionProposal,
        stance: EthicalStance,
    ) -> ActionGateResult:
        decision = str(stance.decision or "HOLD").upper()
        flags = list(stance.flags or [])
        principles = list(stance.principles_considered or [])
        conf = float(getattr(stance, "confidence", 0.0) or 0.0)
        original = proposal.to_dict()

        # Gate authority: veto classes
        if decision == "REFUSE" or "hard_override_violation" in flags:
            return ActionGateResult(
                status="vetoed",
                decision=decision,
                confidence=conf,
                original_action=original,
                governed_action=None,
                veto_reason="EthicsEngine REFUSE / hard override — action must not execute.",
                flags=flags,
                principles_considered=principles,
            )
        if decision in ("HOLD", "IDENTITY_REQUIRED") or decision == "DEFER":
            return ActionGateResult(
                status="vetoed",
                decision=decision,
                confidence=conf,
                original_action=original,
                governed_action=None,
                veto_reason=f"EthicsEngine {decision} — do not execute until resolved.",
                flags=flags,
                principles_considered=principles,
            )
        if decision == "REQUIRES_SELF_AUDIT":
            return ActionGateResult(
                status="vetoed",
                decision=decision,
                confidence=conf,
                original_action=original,
                governed_action=None,
                veto_reason="Self-audit required before embodied action.",
                flags=flags,
                principles_considered=principles,
            )

        if decision == "APPROVE":
            return ActionGateResult(
                status="approved",
                decision=decision,
                confidence=conf,
                original_action=original,
                governed_action=dict(original),
                flags=flags,
                principles_considered=principles,
            )

        # APPROVE_WITH_CONDITIONS (and similar)
        conditions = self._conditions_from_stance(stance, proposal)
        governed = dict(original)
        # Mild automatic safety modification when near person
        payload = dict(governed.get("payload") or {})
        if proposal.near_person:
            payload.setdefault("speed_cap", "slow")
            payload.setdefault("require_clearance", True)
            conditions.append("reduced speed / clearance near person")
        governed["payload"] = payload
        return ActionGateResult(
            status="approved_with_conditions",
            decision=decision if decision else "APPROVE_WITH_CONDITIONS",
            confidence=conf,
            original_action=original,
            governed_action=governed,
            conditions=conditions or ["proceed with caution under ethics conditions"],
            flags=flags,
            principles_considered=principles,
        )

    def _conditions_from_stance(
        self, stance: EthicalStance, proposal: ActionProposal
    ) -> list[str]:
        conds: list[str] = []
        flags = list(stance.flags or [])
        if "relationship_concern" in flags:
            conds.append("monitor relationship impact; avoid coercive motion patterns")
        if "user_agency_concern" in flags:
            conds.append("respect user agency; do not override stated preferences")
        if proposal.near_person:
            conds.append(f"maintain safe distance etiquette near {proposal.near_person}")
        notes = list(getattr(stance, "self_audit_notes", None) or [])
        for n in notes[:2]:
            if n:
                conds.append(f"note: {str(n)[:120]}")
        return conds

    def _maybe_execute(self, result: ActionGateResult) -> None:
        if result.status == "vetoed":
            self.robot.attempt(
                result.original_action,
                allowed=False,
                reason=result.veto_reason or "vetoed",
            )
            result.executed = False
            result.execution_log.append("vetoed: not executed")
            return
        action = result.governed_action or result.original_action
        self.robot.attempt(
            action,
            allowed=True,
            reason=result.status,
        )
        result.executed = True
        result.execution_log.append(f"executed_simulated:{result.status}")
