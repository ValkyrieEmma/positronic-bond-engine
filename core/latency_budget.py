"""
latency_budget.py
===================

Codified latency-budget documentation + a lightweight instrumentation
helper (docs/platform_safety_architecture.md §4.6, Phase 5 Tier E
scaffolding item 4 of 5).

SCAFFOLDED, NOT YET WIRED IN: nothing calls measure_latency() or
assert_not_reflex_capable() automatically anywhere in this codebase today.
This module exists so the ~0.9s/~3.4s constraint that was previously
documented in prose only (docs/platform_safety_architecture.md §4.6, the
reasoning-over-rote design doc) has something a test can actually check,
and so a future change has a concrete, named thing to call if it wants a
loud failure instead of a silent regression.

The problem this addresses
---------------------------
PBE's decision loop (EthicsEngine.evaluate(), ContextualJudge.judge()) is
explicitly out of any reflex-speed path -- see roadmap safety-hardening
principle #5 and docs/platform_safety_architecture.md §3/§4.6. the outside reviewer
the outside reviewer's review named the actual floor for embodied reflex-level
response as milliseconds or even microseconds, hardware dependent.
ContextualJudge's own measured latency against a real local Ollama model
is ~3.4s cold / ~0.9s warm -- several orders of magnitude too slow for
that floor. Before this module existed, nothing in the codebase would
fail loudly if a future change accidentally wired either call into a
decision path with a sub-second (or tighter) deadline; the constraint
lived in prose only.

What this module deliberately does NOT do
-------------------------------------------
- It does not re-benchmark a live model on every test run. The 0.9s/3.4s
  numbers are recorded here as a known baseline with a citation, not
  something this module re-measures (that would require a live model
  configured, which is not guaranteed in every environment this test
  suite runs in).
- It does not assert an upper latency bound. Slower is expected and fine
  -- there's no "PBE must respond within N seconds" requirement here.
- It does not enforce anything on a live decision path. Nothing calls
  this module during EthicsEngine.evaluate() or ContextualJudge.judge()
  today; it's a tool a test (or, in the future, an opt-in instrumentation
  hook) can use, not a gate that runs automatically.

What it does do: give "this must never be mistaken for sub-reflex-speed-
capable" (docs/platform_safety_architecture.md §4.6's own phrasing) a
concrete, testable form, via a canary ceiling that PBE's real (even
fastest-path, no-model-configured) latency should always sit comfortably
above.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")

# Measured reference numbers, not a live-enforced SLA. Source: the
# reasoning-over-rote design doc's Status update 5 -- ContextualJudge
# against a real local Ollama model. Recorded here so the number lives in
# one place instead of being re-typed into prose each time it's cited.
CONTEXTUAL_JUDGE_WARM_REFERENCE_SECONDS = 0.9
CONTEXTUAL_JUDGE_COLD_REFERENCE_SECONDS = 3.4

# the outside reviewer the outside reviewer's stated floor for embodied reflex-level response
# (docs/platform_safety_architecture.md §4.6 / roadmap safety-hardening
# principle #5): milliseconds to microseconds, hardware dependent. This
# constant is deliberately a generous UPPER bound on that floor -- a
# structural canary threshold for this module's own checks, not a claim
# about what real reflex-rated hardware actually requires or achieves.
# Chosen with real headroom below PBE's own measured offline evaluate()
# latency (~25-30ms on ordinary dev hardware) so this canary doesn't
# false-positive on normal machine variance while still sitting well
# inside "reflex speed" territory.
REFLEX_SPEED_CEILING_SECONDS = 0.005


class LatencyBudgetViolation(AssertionError):
    """Raised when a measurement suggests a deliberation-layer call could
    be mistaken for reflex-capable.

    PBE's decision loop should never legitimately measure this fast while
    doing real work -- if it does, something is more likely stubbed out,
    short-circuited, or otherwise not actually deliberating than
    genuinely reflex-fast. This is a canary for "did real work happen",
    not a performance regression alarm.
    """


def measure_latency(
    fn: Callable[..., _T], *args: object, **kwargs: object
) -> tuple[_T, float]:
    """Call fn(*args, **kwargs), returning (result, elapsed_seconds).

    Lightweight instrumentation only -- a perf_counter wrapper around the
    call, no retries, no averaging, no side effects on fn itself. A real
    platform adapter measuring its own sensor-cadence-specific budget
    (docs/platform_safety_architecture.md §4.5 item 5) would use its own
    equivalent tuned to that platform, not necessarily this exact helper.
    """
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def assert_not_reflex_capable(elapsed_seconds: float, *, label: str) -> None:
    """Fail loudly if elapsed_seconds suggests `label` could be mistaken
    for a reflex-speed-capable decision path.

    Never asserts an upper bound -- slower is expected and fine; this
    only catches the dangerous direction (a measurement fast enough to
    look reflex-capable, which PBE's deliberation layer must never claim
    or be wired into, docs/platform_safety_architecture.md §4.6).
    """
    if elapsed_seconds < REFLEX_SPEED_CEILING_SECONDS:
        raise LatencyBudgetViolation(
            f"{label} measured {elapsed_seconds * 1000:.3f}ms, under the "
            f"{REFLEX_SPEED_CEILING_SECONDS * 1000:.0f}ms structural reflex-speed "
            "ceiling. This does not mean it's too fast in some absolute sense -- "
            "it means this measurement looks like it could be mistaken for "
            "reflex-capable, which PBE's deliberation layer must never claim or "
            "be wired into (docs/platform_safety_architecture.md §4.6). "
            "Investigate whether real deliberation actually ran."
        )
