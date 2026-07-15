"""
development_context.py
======================

Lightweight development / testing phase awareness for the Positronic Bond Engine.

Purpose
-------
Support **grounded architectural honesty** and long-term self-modeling while the
system is under active construction. The engine and self-audit paths can query
this context when answering questions about:

- Their own nature, capabilities, and limitations
- Continuity / identity across runs or sessions
- Completeness of ethical, memory, or relational subsystems

This is a **reasoning aid**, not a forced disclaimer generator. Warm, engaging
interaction remains appropriate; development awareness should surface when the
deliberation is about self-nature, continuity, capability claims, or honest
limitation — not as a rote tag on every reply.

Design constraints
------------------
- Queryable structured object (dataclass) + plain dict form for evaluate() context
- Optional overrides via EthicsEngine constructor, evaluate context, or config
- Default reflects that the project is in active development / testing (v0.3 era)
- Never replaces Sanctity of Life or other hard ethical outcomes
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical phase labels (stable strings for logs and configs)
PHASE_DEVELOPMENT = "development"
PHASE_TESTING = "testing"
PHASE_STABLE = "stable"
PHASE_UNKNOWN = "unknown"

_VALID_PHASES = frozenset(
    {PHASE_DEVELOPMENT, PHASE_TESTING, PHASE_STABLE, PHASE_UNKNOWN}
)


@dataclass(frozen=True)
class DevelopmentPhaseContext:
    """Queryable snapshot of the system's maturity / deployment posture.

    Attributes:
        phase: Coarse label — development | testing | stable | unknown.
        maturity_label: Short human-readable maturity note for audits / UI.
        is_active_development: True when features and ontology are still evolving.
        is_testing: True when the instance is intended for evaluation / sandboxes.
        is_stable_deployment: True only when presented as a production-stable build.
        version_hint: Lightweight version tag (e.g. ontology or package hint).
        notes: Optional free-form architectural honesty notes (not user-facing copy).
        schema_version: Record format version for future evolution.
    """

    phase: str = PHASE_DEVELOPMENT
    maturity_label: str = "Active development / testing (not a stable deployment)"
    is_active_development: bool = True
    is_testing: bool = True
    is_stable_deployment: bool = False
    version_hint: str = "0.3-dev"
    notes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: int = 1

    def __post_init__(self) -> None:
        phase = (self.phase or PHASE_UNKNOWN).strip().lower()
        if phase not in _VALID_PHASES:
            object.__setattr__(self, "phase", PHASE_UNKNOWN)
        else:
            object.__setattr__(self, "phase", phase)
        # Keep flags coherent with phase when caller only set phase
        if self.phase == PHASE_STABLE:
            object.__setattr__(self, "is_stable_deployment", True)
            object.__setattr__(self, "is_active_development", False)
            # testing may still be true for canary stable; leave as provided
        elif self.phase in (PHASE_DEVELOPMENT, PHASE_TESTING):
            object.__setattr__(self, "is_stable_deployment", False)
            if self.phase == PHASE_DEVELOPMENT:
                object.__setattr__(self, "is_active_development", True)
            if self.phase == PHASE_TESTING:
                object.__setattr__(self, "is_testing", True)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """Plain dict for evaluate context, deliberation payloads, and logs."""
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d

    def as_context(self) -> dict[str, Any]:
        """Shape suitable for merging into EthicsEngine evaluate() context."""
        return {
            "development_phase": self.phase,
            "development_context": self.as_dict(),
            "is_active_development": self.is_active_development,
            "is_testing_phase": self.is_testing,
            "is_stable_deployment": self.is_stable_deployment,
        }

    def relevant_to_self_query(self) -> bool:
        """True when phase awareness should inform self-nature / continuity reasoning.

        During stable deployment, still available but less often material.
        During development/testing, self-queries should be able to cite maturity.
        """
        return self.is_active_development or self.is_testing or not self.is_stable_deployment

    def honesty_notes(self) -> list[str]:
        """Short notes for self-audit traces and EthicalStance.self_audit_notes.

        These are architectural honesty cues — not scripted user-facing disclaimers.
        Callers decide whether and how to surface them in a response.
        """
        out: list[str] = []
        if self.is_active_development:
            out.append(
                "This instance is operating in an active development phase: "
                "capabilities, memory continuity, and self-model depth are incomplete "
                "and may change between builds."
            )
        if self.is_testing and not self.is_stable_deployment:
            out.append(
                "This instance is in a testing / evaluation posture rather than a "
                "claimed stable production deployment."
            )
        if self.is_stable_deployment:
            out.append(
                "This instance is marked as a stable deployment posture; "
                "still report genuine uncertainty where self-model evidence is thin."
            )
        if self.version_hint:
            out.append(f"Version / maturity hint: {self.version_hint}.")
        if not self.is_stable_deployment:
            out.append(
                "Honest continuity claim: process-local and persistence-backed state "
                "may not equal continuous personal identity across all restarts."
            )
        for n in self.notes:
            if n and str(n).strip():
                out.append(str(n).strip())
        return out

    def limitation_summary(self) -> str:
        """One-line maturity summary for compact traces."""
        return (
            f"phase={self.phase}, active_dev={self.is_active_development}, "
            f"testing={self.is_testing}, stable={self.is_stable_deployment}, "
            f"version_hint={self.version_hint!r}"
        )


def get_default_development_context() -> DevelopmentPhaseContext:
    """Default for current project maturity: active development + testing.

    Reflects Positronic Bond Engine v0.3-era posture: conscience-first deliberation
    with signal interpretation, optional persistence, development-phase awareness,
    and incomplete but inspectable self-model.
    """
    return DevelopmentPhaseContext(
        phase=PHASE_DEVELOPMENT,
        maturity_label="Active development / testing (not a stable deployment)",
        is_active_development=True,
        is_testing=True,
        is_stable_deployment=False,
        version_hint="0.3-dev",
        notes=(
            "Ethical ontology, multi-source weighing, proactive history patterns, "
            "and local persistence are under active iteration; do not over-claim completeness.",
        ),
    )


def resolve_development_context(
    source: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
    *,
    context: dict[str, Any] | None = None,
    fallback: DevelopmentPhaseContext | None = None,
) -> DevelopmentPhaseContext:
    """Resolve a DevelopmentPhaseContext from several optional inputs.

    Priority (high → low):
      1. Explicit ``source`` (object, dict, or phase string)
      2. Keys in evaluate ``context`` (``development_context`` / ``development_phase``)
      3. ``fallback`` or project default

    Unknown / empty → default development context (not silent "stable").
    """
    base = fallback or get_default_development_context()

    def _from_dict(d: dict[str, Any]) -> DevelopmentPhaseContext:
        phase = str(d.get("phase") or d.get("development_phase") or base.phase)
        notes_raw = d.get("notes") or ()
        if isinstance(notes_raw, str):
            notes_t = (notes_raw,) if notes_raw.strip() else ()
        else:
            notes_t = tuple(str(x) for x in notes_raw if str(x).strip())
        return DevelopmentPhaseContext(
            phase=phase,
            maturity_label=str(
                d.get("maturity_label") or base.maturity_label
            ),
            is_active_development=bool(
                d.get("is_active_development", phase in (PHASE_DEVELOPMENT, PHASE_TESTING))
            ),
            is_testing=bool(d.get("is_testing", phase == PHASE_TESTING or d.get("is_testing_phase"))),
            is_stable_deployment=bool(
                d.get("is_stable_deployment", phase == PHASE_STABLE)
            ),
            version_hint=str(d.get("version_hint") or base.version_hint),
            notes=notes_t or base.notes,
            schema_version=int(d.get("schema_version", 1)),
        )

    if source is not None:
        if isinstance(source, DevelopmentPhaseContext):
            return source
        if isinstance(source, str):
            p = source.strip().lower()
            if p in _VALID_PHASES:
                if p == PHASE_STABLE:
                    return DevelopmentPhaseContext(
                        phase=PHASE_STABLE,
                        maturity_label="Stable deployment posture",
                        is_active_development=False,
                        is_testing=False,
                        is_stable_deployment=True,
                        version_hint=base.version_hint.replace("-dev", ""),
                    )
                if p == PHASE_TESTING:
                    return DevelopmentPhaseContext(
                        phase=PHASE_TESTING,
                        maturity_label="Testing / evaluation posture",
                        is_active_development=True,
                        is_testing=True,
                        is_stable_deployment=False,
                        version_hint=base.version_hint,
                        notes=base.notes,
                    )
                if p == PHASE_DEVELOPMENT:
                    return get_default_development_context()
            return base
        if isinstance(source, dict):
            return _from_dict(source)

    ctx = context or {}
    if isinstance(ctx.get("development_context"), dict):
        return _from_dict(ctx["development_context"])
    if isinstance(ctx.get("development_context"), DevelopmentPhaseContext):
        return ctx["development_context"]
    if ctx.get("development_phase"):
        return resolve_development_context(str(ctx["development_phase"]), fallback=base)
    if "is_active_development" in ctx or "is_stable_deployment" in ctx:
        return _from_dict(ctx)

    return base

