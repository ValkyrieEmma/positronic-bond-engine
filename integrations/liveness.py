"""
liveness.py
============

Watchdog / heartbeat interface (docs/platform_safety_architecture.md §4.7,
Phase 5 Tier E scaffolding item 3 of 5).

SCAFFOLDED, NOT YET WIRED IN: nothing in EthicsEngine.evaluate() or
OpenClawBridge calls LivenessMonitor.beat() today. This module exists so a
future real platform adapter has a clean, tested interface to poll instead
of inventing its own ad hoc liveness contract per integration.

Borrowed directly from the ROS-Safety Working Group's own watchdog library
pattern (DDS QoS + lifecycle-node based): a supervisor independent of the
main reasoning loop that detects a hang and forces a safe state.

Critical scope boundary, stated here because getting it backwards would be
a real safety regression, not just a documentation nitpick: this class
NEVER enforces anything. It has no ability to stop a robot, and nothing in
this file tries. Per docs/platform_safety_architecture.md §4.4 / §4.7,
that control logic belongs entirely to the PLATFORM's own watchdog,
running independently of PBE:

    The platform polls this heartbeat (or an equivalent interface a real
    adapter builds against). If it goes stale, the platform must
    independently default to `PlatformState.PROTECTIVE_STOP_ACTIVE`
    (integrations/platform_states.py) on its own -- it must never wait for
    PBE to tell it to stop, because a hung or crashed PBE is exactly the
    failure mode this watchdog exists to catch. Per §4.4: "the platform
    must treat 'PBE unavailable' identically to a REFUSE, never as a
    silent pass-through."

A real integration calls `beat()` around its own decision loop (e.g. after
each `EthicsEngine.evaluate()` / `OpenClawBridge.submit_action_proposal()`
call) -- exactly where is left to whatever is driving that loop, since
this module has no opinion about it and isn't wired into either call today.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from integrations.platform_states import PBEState


@dataclass(frozen=True)
class HeartbeatStatus:
    """A snapshot of liveness at the moment status() was called."""

    alive: bool
    seconds_since_last_beat: float | None
    pbe_state: PBEState


class LivenessMonitor:
    """PBE-side heartbeat source for a platform watchdog to poll.

    Records when PBE last confirmed it was alive (`beat()`) and answers
    "has PBE answered within its expected budget recently" (`is_stale()`).
    Carries no reference to any EthicsEngine, robot, or execution path --
    it is pure bookkeeping, deliberately decoupled from decision logic.
    """

    def __init__(
        self,
        *,
        stale_after_seconds: float = 5.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self._stale_after_seconds = float(stale_after_seconds)
        # Injectable clock (defaults to a monotonic clock, immune to
        # wall-clock adjustments) so tests can advance time deterministically
        # without real sleeps.
        self._clock: Callable[[], float] = clock or time.monotonic
        self._last_beat: float | None = None

    def beat(self) -> None:
        """Record that PBE is alive right now."""
        self._last_beat = self._clock()

    def seconds_since_last_beat(self) -> float | None:
        """None if beat() has never been called."""
        if self._last_beat is None:
            return None
        return max(0.0, self._clock() - self._last_beat)

    def is_stale(self) -> bool:
        """True if beat() was never called, or the last beat is older than
        stale_after_seconds. A platform watchdog should treat True
        identically to PBEState.UNAVAILABLE_FAILED_CLOSED -- i.e. force
        its own protective stop, never wait for PBE to confirm anything
        further."""
        elapsed = self.seconds_since_last_beat()
        return elapsed is None or elapsed > self._stale_after_seconds

    def status(self) -> HeartbeatStatus:
        """Convenience snapshot pairing staleness with the PBEState
        vocabulary (integrations/platform_states.py) a platform adapter
        would want to log or expose alongside this. Still read-only --
        computing this snapshot never stops anything."""
        elapsed = self.seconds_since_last_beat()
        stale = self.is_stale()
        pbe_state = PBEState.UNAVAILABLE_FAILED_CLOSED if stale else PBEState.AVAILABLE
        return HeartbeatStatus(
            alive=not stale,
            seconds_since_last_beat=elapsed,
            pbe_state=pbe_state,
        )
