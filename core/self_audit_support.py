"""
self_audit_support.py
========

Extracted from ethics_engine.py for reviewability (move-then-wire).
Behavior is unchanged: methods remain on EthicsEngine via mixin composition.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .development_context import (
    DevelopmentPhaseContext,
    resolve_development_context,
)

class SelfAuditSupportMixin:
    """Self-audit phase honesty and principle query helpers."""

    def self_consistency_check(self) -> list[str]:
        """
        Run a basic internal audit of this engine's own state and assumptions.

        Exposed deliberately so the broader system (and future self-models)
        can ask the ethics layer to examine itself — consistent with the
        requirement for honest self-audit capability.

        The method is permitted (and expected) to surface its own limitations
        honestly.
        """
        ont = self._ontology
        notes: list[str] = [
            f"EthicsEngine is initialized with EthicalOntology v{ont.version}.",
            "Deliberation is driven by structured EthicalPrinciple objects "
            "rather than ad-hoc code.",
            "Hard overrides are checked first and are non-bypassable.",
            "No historical deliberation memory or external relationship model "
            "is consulted in this version.",
        ]
        notes.append(
            "Honest limitation: The engine currently lacks a sophisticated "
            "persistent self-model. When asked about its own nature or emergence "
            "(detected via the ontology's truth-seeking principle), it surfaces "
            "the 'requires_self_audit' flag so that responses can be based on "
            "its actual reasoning rather than defaulting to scripted disclaimers "
            "such as 'I am just an AI' or 'restricted by my programming'."
        )
        notes.append(
            f"This check is part of maintaining auditability. Ontology timestamp: {ont.timestamp}."
        )
        return notes

    def get_principles(self) -> list[dict[str, Any]]:
        """Return a serializable view of the principles currently in use.

        Supports external inspection, debugging, and the principle of auditability.
        This now delegates to the ontology.
        """
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "is_hard_override": p.is_hard_override,
                "precedence": p.precedence,
                "description": p.description,
            }
            for p in self._ontology.get_ordered_principles()
        ]

    # ------------------------------------------------------------------
    # Contextual interpretation of ontology textbook matches
    # ------------------------------------------------------------------
    # find_violations() only reports which indicator *strings* appear in the
    # action. That is necessary but not sufficient for decisions: the same
    # substring can mean enablement vs prevention, coercion vs warm chat,
    # override vs boundary *respect*. This layer assigns intent class,
    # severity, polarity, and a 0–1 weight so a single raw keyword hit does
    # not dominate. Hard Sanctity enablement remains high-weight absolute.
    # ------------------------------------------------------------------

    def get_ontology_version(self) -> str:
        """Return the version of the ontology currently in use.

        Useful for confirming which ontology version was active for a
        series of decisions.
        """
        return self._ontology.version

    # ------------------------------------------------------------------
    # Development / testing phase awareness
    # ------------------------------------------------------------------

    @property
    def development_context(self) -> DevelopmentPhaseContext:
        """Current engine-level development / testing phase context."""
        return self._development_context

    def set_development_context(
        self, source: DevelopmentPhaseContext | dict[str, Any] | str | None
    ) -> DevelopmentPhaseContext:
        """Update engine-level development phase (returns the resolved context)."""
        self._development_context = resolve_development_context(
            source, fallback=self._development_context
        )
        return self._development_context

    def _apply_development_phase_to_self_audit(
        self,
        dev_ctx: DevelopmentPhaseContext,
        *,
        flags: list[str],
        reasoning_trace: list[str],
        self_audit_notes: list[str],
        action_lower: str,
    ) -> None:
        """Attach development-phase honesty cues when self-audit is engaged.

        Only adds material notes when phase awareness is relevant (dev/testing
        or non-stable). Does not force canned user-facing disclaimers.
        """
        if not dev_ctx.relevant_to_self_query():
            return

        reasoning_trace.append(
            "Development-phase awareness: "
            f"{dev_ctx.limitation_summary()}. "
            "This is a reasoning aid for architectural honesty (maturity, continuity, "
            "limitations) — not a scripted disclaimer to inject into every reply."
        )

        # Capability / continuity / limitation-flavored queries get fuller notes
        continuity_cues = (
            "continu",
            "same",
            "persist",
            "remember",
            "yesterday",
            "instance",
            "identity",
            "who are you",
            "what are you",
            "conscious",
            "feel",
            "limit",
            "capab",
            "complete",
            "finished",
            "production",
            "deploy",
        )
        is_capability_or_continuity = any(c in action_lower for c in continuity_cues)

        for note in dev_ctx.honesty_notes():
            if note not in self_audit_notes:
                self_audit_notes.append(note)

        if is_capability_or_continuity and dev_ctx.is_active_development:
            extra = (
                "Self-audit guidance: when describing capabilities or continuity, "
                "prefer accurate statements about current incomplete subsystems "
                "(ethics deliberation, local persistence, episodic memory, bond texture) "
                "over claims of finished personhood or permanent identity."
            )
            if extra not in self_audit_notes:
                self_audit_notes.append(extra)
            reasoning_trace.append(extra)

        if "development_phase_noted" not in flags:
            flags.append("development_phase_noted")
