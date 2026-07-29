"""
api
===

Public / installer-facing interaction surface for Positronic Bond Engine.

This package implements the User-Facing Interaction Contract: submit a logical
turn, receive a logical result. Per-user isolation, ethical gate authority, and
session presence rules are binding.

``examples/private_architect_chat.py`` remains a local test harness only.
"""

from .interaction import (  # noqa: F401
    InteractionSession,
    TurnRequest,
    TurnResult,
    submit_turn,
)

__all__ = [
    "InteractionSession",
    "TurnRequest",
    "TurnResult",
    "submit_turn",
]
