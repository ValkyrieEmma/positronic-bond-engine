"""
integrations
============

External hooks. All action paths must respect the conscience layer.
"""

from .openclaw import (  # noqa: F401
    ActionGateResult,
    ActionProposal,
    OpenClawBridge,
    SimulatedRobot,
    action_to_evaluation_text,
)

__all__ = [
    "ActionGateResult",
    "ActionProposal",
    "OpenClawBridge",
    "SimulatedRobot",
    "action_to_evaluation_text",
]
