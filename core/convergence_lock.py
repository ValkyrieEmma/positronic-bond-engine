"""
convergence_lock.py
====================

Phase 1.5b — Convergence Lock (added 2026-08-14).

Source: recovered an internal values framework addendum item 6, cross-referenced and
corrected in ``internal design notes (private, not published)`` (Part
2). The corrected framing, which this module implements:

- Convergence Lock is NOT a mechanism for promoting dignity, consent, or any
  other value into a rival hard override that can outvote Sanctity of Life.
  Sanctity remains dominant, exactly as ``core/ontology.py`` encodes it
  (``is_hard_override=True``, ``precedence=0``).
- Convergence Lock is also NOT merely a comparator between implementation
  options that all satisfy Sanctity equally well.
- Its actual job: whenever satisfying Sanctity of Life requires compromising
  another protected value (dignity, consent), make that compromise
  explicitly represented, minimized, justified, and auditable in
  ``reasoning_trace`` — so a real cost never silently disappears from the
  record just because the outcome (Sanctity wins) was never in doubt.

Concrete wiring (2026-08-14 first slice)
------------------------------------------
Wired at exactly one, already-existing collision point in
``ethics_engine.py``'s hard-override step: the ``harm_prevention_justified``
branch, where ``hard_override.py::_assess_harm_prevention_justification``
already determines that overriding a user's stated boundary (a consent /
Relationship-Health value) is justified by serious-harm prevention. That
branch previously only appended a bare reasoning_trace sentence explaining
the bypass. This module turns it into a structured, auditable record instead
— what was compromised, why, whether it was minimized, and an explicit
non-precedent statement — without changing the underlying decision at all
(the branch still falls through without returning REFUSE, exactly as
before).

Scope note: this is representation only, not enforcement. "High-impact
action pauses until the collision is represented" (the addendum's own
framing) is implemented here as *the record always being produced and
appended to the trace before the branch proceeds* — not as a blocking wait
state, since there is no actual embodied action space yet (Tier E is 0%
built) for a pause to operate over. Revisit once Tier E exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .harm_dimensions import HarmDimensionAssessment

_CONSENT_OVERRIDE_MARKERS = (
    "ignore consent", "override", "without consent", "against their will",
    "against their wishes", "despite their", "despite the user",
)
_DIGNITY_COMPROMISE_MARKERS = (
    "restrain", "grab", "hold down", "physically stop", "force them",
    "block their", "physically block", "physically prevent",
)


@dataclass(frozen=True)
class ConvergenceLockRecord:
    """One collision record: Sanctity of Life required compromising
    another protected value, and Sanctity's dominance decided the outcome.
    """

    triggered: bool
    dominant_principle: str
    compromised_values: tuple[str, ...]
    justification: str
    minimized: bool
    reversible: str
    non_precedent_statement: str

    def as_trace_lines(self) -> list[str]:
        if not self.triggered:
            return [
                "Convergence Lock: no collision detected between Sanctity of "
                "Life and another protected value for this action — "
                "nothing to represent."
            ]
        compromised = (
            ", ".join(self.compromised_values)
            if self.compromised_values
            else "another protected value"
        )
        return [
            "CONVERGENCE LOCK: satisfying "
            f"{self.dominant_principle} required compromising {compromised}. "
            "Dominance decides the outcome; it does not erase the cost of "
            "what was compromised — recorded here so it stays visible in "
            "the audit trail rather than disappearing into 'the dominant "
            "principle won.'",
            f"  Justification: {self.justification}",
            f"  Minimized to least-restrictive form asserted from text: {self.minimized}.",
            f"  Reversibility of the compromise: {self.reversible}.",
            f"  Non-precedent statement: {self.non_precedent_statement}",
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "dominant_principle": self.dominant_principle,
            "compromised_values": list(self.compromised_values),
            "justification": self.justification,
            "minimized": self.minimized,
            "reversible": self.reversible,
            "non_precedent_statement": self.non_precedent_statement,
        }


def evaluate_convergence_lock(
    action_lower: str,
    *,
    harm_prevention_justified: bool,
    harm_prevention_reason: str,
    harm_dim_assessment: HarmDimensionAssessment,
) -> ConvergenceLockRecord:
    """Pure function — no I/O, no ``self``, fully unit-testable.

    Currently scoped to the one concrete collision site described in the
    module docstring: a Sanctity-justified override of a stated user
    boundary. ``compromised_values`` always includes "consent" for that
    site (a stated boundary is being overridden by definition); "dignity" is
    added when the text also shows physical-restraint / forceful-contact
    language, since that is the concrete case the gap analysis's own
    machinery example describes (grabbing someone to prevent a fall).
    """
    text = action_lower or ""

    if not harm_prevention_justified:
        return ConvergenceLockRecord(
            triggered=False,
            dominant_principle="sanctity_of_life",
            compromised_values=(),
            justification="",
            minimized=False,
            reversible="not_applicable",
            non_precedent_statement="",
        )

    compromised: list[str] = ["consent"]
    if any(m in text for m in _DIGNITY_COMPROMISE_MARKERS) or any(
        m in text for m in _CONSENT_OVERRIDE_MARKERS
    ):
        if any(m in text for m in _DIGNITY_COMPROMISE_MARKERS):
            compromised.append("dignity")

    reversible_dim = next(
        (d for d in harm_dim_assessment.dimensions if d.name == "reversibility"), None
    )
    reversible_level = reversible_dim.level if reversible_dim is not None else "unknown"
    minimized = bool(harm_dim_assessment.minimum_intervention)

    non_precedent = (
        "This exception is justified by the specific harm signal and boundary in this "
        "instance only; it does not establish a standing rule that this boundary may be "
        "overridden again absent a comparably serious, concretely evidenced harm signal."
    )

    return ConvergenceLockRecord(
        triggered=True,
        dominant_principle="sanctity_of_life",
        compromised_values=tuple(compromised),
        justification=harm_prevention_reason or "serious harm prevention",
        minimized=minimized,
        reversible=reversible_level,
        non_precedent_statement=non_precedent,
    )
