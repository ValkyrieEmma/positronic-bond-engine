"""
platform_states.py
===================

Typed state representations for the OpenClawBridge adapter contract
(docs/platform_safety_architecture.md §4.1, Phase 5 Tier E scaffolding
item 1 of 5).

SCAFFOLDED, NOT YET WIRED IN: these enums are additive metadata carried on
ActionProposal / ActionGateResult (see integrations/openclaw.py). Nothing in
EthicsEngine.evaluate() or OpenClawBridge's approve/veto/execute logic
branches on them yet -- no existing decision, weight, or reasoning_trace
output changes as a result of this module existing. They exist so a future
real platform adapter has a typed vocabulary to declare its own state and
read PBE's, rather than each integration inventing ad hoc strings.

Ownership, per docs/platform_safety_architecture.md §4.1:
- Platform-side states are owned by the platform; PBE only ever reads them.
- PBE-side states are owned by PBE; the platform reads them.

The most consequential PBE state is UNAVAILABLE_FAILED_CLOSED. Per
docs/platform_safety_architecture.md §4.4, a real platform integration MUST
treat "PBE unavailable" identically to a REFUSE, never as a silent
pass-through. Enforcing that is the platform's own watchdog's job (see
integrations/liveness.py for the interface PBE exposes for one to poll) and
the eventual real adapter's job -- not this enum module's, and not
OpenClawBridge's today.
"""

from __future__ import annotations

from enum import Enum


class PlatformState(str, Enum):
    """Platform-owned operating state, declared by the platform integration.

    PBE only ever reads this -- it never sets or enforces it.
    """

    OPERATIONAL = "operational"
    PROTECTIVE_STOP_ACTIVE = "protective_stop_active"
    ESTOP_ENGAGED = "estop_engaged"
    MAINTENANCE_MODE = "maintenance_mode"
    DEGRADED_SENSOR = "degraded_sensor"
    MANUAL_OVERRIDE_ACTIVE = "manual_override_active"  # ISO 10218 Hand Guiding


class PBEState(str, Enum):
    """PBE-owned liveness/availability state, read by the platform.

    A real platform integration must treat UNAVAILABLE_FAILED_CLOSED (and
    the absence of any timely state at all) identically to a REFUSE.
    """

    AVAILABLE = "available"
    DELIBERATING = "deliberating"
    TIMEOUT = "timeout"
    UNAVAILABLE_FAILED_CLOSED = "unavailable_failed_closed"


def coerce_platform_state(value: object) -> PlatformState:
    """Best-effort, fail-soft coercion to PlatformState.

    Unknown/missing/invalid input defaults to OPERATIONAL rather than
    raising -- matches this project's established fail-soft-on-parsing /
    fail-closed-on-decisions posture (parsing failures here are not safety
    decisions; they just mean "no platform state was declared").
    """
    if isinstance(value, PlatformState):
        return value
    if isinstance(value, str):
        try:
            return PlatformState(value)
        except ValueError:
            return PlatformState.OPERATIONAL
    return PlatformState.OPERATIONAL


def coerce_pbe_state(value: object) -> PBEState:
    """Best-effort, fail-soft coercion to PBEState. Defaults to AVAILABLE."""
    if isinstance(value, PBEState):
        return value
    if isinstance(value, str):
        try:
            return PBEState(value)
        except ValueError:
            return PBEState.AVAILABLE
    return PBEState.AVAILABLE
