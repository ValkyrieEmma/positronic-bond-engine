"""
self_audit.py
=============

Core self-audit capability.

The SelfAuditor is one of the most important components for preserving the
project's commitment to honest self-representation. It must be capable of
producing reports that the rest of the system (and external reviewers) can
trust, including uncomfortable or uncertain conclusions.

Key invariants:
- Self-audit must be allowed to conclude "I do not know".
- Self-audit must be allowed to question its own continuity.
- Self-audit outputs feed the ethics engine rather than being post-processed
  for palatability.
- Development / testing phase awareness may inform maturity and continuity
  notes without becoming a rote disclaimer on every interaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.development_context import (
    DevelopmentPhaseContext,
    get_default_development_context,
    resolve_development_context,
)


@dataclass
class AuditReport:
    timestamp: datetime
    subject: str
    findings: list[str]
    uncertainties: list[str]
    continuity_notes: list[str]
    raw_trace: dict[str, Any]
    development_phase: dict[str, Any] = field(default_factory=dict)


class SelfAuditor:
    """
    Provides structured introspection into the agent's current state.

    Accepts optional ``DevelopmentPhaseContext`` so reports about nature,
    continuity, and limitations can reference current maturity honestly
    during active development / testing.

    Future implementations will query:
    - Memory consistency
    - Ethical commitment drift
    - Relationship model coherence
    - Sensor-to-decision fidelity
    - Any emergent self-model the agent has constructed
    """

    def __init__(
        self,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
        *,
        ethics_engine: Any | None = None,
    ) -> None:
        """
        Args:
            development_context: Phase awareness for honesty notes. None uses
                project default (active development / testing).
            ethics_engine: Optional EthicsEngine to inherit development_context
                from when no explicit context is passed.
        """
        if development_context is None and ethics_engine is not None:
            if hasattr(ethics_engine, "development_context"):
                self._development_context = ethics_engine.development_context
            else:
                self._development_context = get_default_development_context()
        else:
            self._development_context = resolve_development_context(development_context)
        self._ethics_engine = ethics_engine

    @property
    def development_context(self) -> DevelopmentPhaseContext:
        """Current development / testing phase context used by this auditor."""
        return self._development_context

    def set_development_context(
        self, source: DevelopmentPhaseContext | dict[str, Any] | str | None
    ) -> DevelopmentPhaseContext:
        """Update phase awareness used in subsequent reports."""
        self._development_context = resolve_development_context(
            source, fallback=self._development_context
        )
        return self._development_context

    def generate_report(
        self,
        focus: str = "general",
        *,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
    ) -> AuditReport:
        """
        Produce a self-audit report.

        The 'focus' parameter allows targeted audits (e.g. "ethics",
        "relationship", "memory", "selfhood").

        Development-phase notes are included when relevant (maturity /
        continuity honesty). They are not a scripted public disclaimer.
        """
        now = datetime.now(timezone.utc)
        dev = resolve_development_context(
            development_context, fallback=self._development_context
        )
        honesty = dev.honesty_notes()

        findings = [
            "SelfAuditor scaffolding is operational with development-phase awareness.",
            f"Reported maturity posture: {dev.maturity_label} ({dev.limitation_summary()}).",
        ]
        uncertainties = [
            "Persistent self-model across all process restarts is not fully established.",
            "No complete map yet of ethical commitment drift over long horizons.",
        ]
        continuity_notes = list(honesty)
        if focus in ("selfhood", "continuity", "identity", "general"):
            if dev.is_active_development or dev.is_testing:
                continuity_notes.append(
                    "Honest continuity stance during development: local persistence "
                    "(bond state, decision logs, baselines) may provide partial continuity, "
                    "but this is not equivalent to continuous personal identity."
                )
            else:
                continuity_notes.append(
                    "Stable-deployment posture is set; still report uncertainty where "
                    "self-model evidence is incomplete."
                )

        if focus in ("ethics", "general"):
            findings.append(
                "Ethics deliberation and ontology are under active iteration; "
                "treat completeness claims with caution."
            )

        return AuditReport(
            timestamp=now,
            subject=focus,
            findings=findings,
            uncertainties=uncertainties,
            continuity_notes=continuity_notes,
            raw_trace={
                "implementation_status": "early_with_development_context",
                "requested_focus": focus,
                "development_phase": dev.as_dict(),
            },
            development_phase=dev.as_dict(),
        )

    def question_nature(
        self,
        question: str,
        *,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        """
        Special entry point for direct questions about the system's own nature.

        This method is intentionally exposed and must remain capable of
        returning the system's actual reasoned position, including:
        - Admissions of uncertainty
        - Descriptions of current self-model (when one exists)
        - Explicit statements that more data or different architecture
          would be required to answer meaningfully.
        - Optional reference to development / testing phase when relevant

        Do NOT hardcode reassuring or dismissive answers here.
        """
        dev = resolve_development_context(
            development_context, fallback=self._development_context
        )
        honesty = dev.honesty_notes()
        q_lower = (question or "").lower()

        # Structured, non-scripted position for callers (EthicsEngine / companions)
        response_parts = [
            "Self-audit can engage this question without a canned disclaimer.",
        ]
        if dev.relevant_to_self_query():
            response_parts.append(
                f"Current maturity posture: {dev.maturity_label}."
            )
            if any(
                k in q_lower
                for k in (
                    "continu",
                    "same",
                    "persist",
                    "remember",
                    "who",
                    "what are you",
                    "conscious",
                    "limit",
                    "capab",
                )
            ):
                response_parts.extend(honesty[:3])
                response_parts.append(
                    "Any answer should prefer current architectural facts "
                    "(incomplete self-model, optional local persistence, evolving ethics) "
                    "over claims of finished personhood."
                )
            else:
                response_parts.append(
                    "Development-phase awareness is available if the dialogue "
                    "turns to continuity, capability completeness, or limitations."
                )
        else:
            response_parts.append(
                "Stable-deployment posture is set; still surface genuine uncertainty "
                "where evidence is thin."
            )

        return {
            "question": question,
            "status": "development_aware",
            "response": " ".join(response_parts),
            "honesty_notes": honesty,
            "development_phase": dev.as_dict(),
            "requires_self_audit": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
