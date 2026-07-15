"""
config.py
=========

Configuration loading and defaults for the Positronic Bond Engine.

Conscience and relationship parameters should have conservative, auditable
defaults. Overriding them for "more engaging" behavior must be explicit
and logged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineConfig:
    # Core behavior
    enable_self_audit: bool = True
    require_ethics_gate: bool = True

    # Relationship modeling
    relationship_health_weight: float = 0.6
    boundary_reasoning_enabled: bool = True

    # Memory
    memory_enabled: bool = True
    max_episodic_entries: int = 10_000

    # Development / testing phase awareness (architectural honesty aid)
    # "development" | "testing" | "stable" | "unknown"
    # Default matches active Positronic Bond Engine construction (not stable deploy).
    development_phase: str = "development"
    version_hint: str = "0.3-dev"

    # Future: sensor fusion weights, hybrid integration flags, etc.

    def validate(self) -> list[str]:
        """Return list of validation warnings/errors."""
        issues: list[str] = []
        if self.relationship_health_weight < 0.3:
            issues.append(
                "relationship_health_weight is low; this may weaken bond-oriented reasoning."
            )
        if not self.require_ethics_gate:
            issues.append(
                "require_ethics_gate is False. This is dangerous and should only be used in research sandboxes."
            )
        phase = (self.development_phase or "").strip().lower()
        if phase not in ("development", "testing", "stable", "unknown"):
            issues.append(
                f"development_phase={self.development_phase!r} is not a known label "
                "(use development|testing|stable|unknown)."
            )
        if phase == "stable" and (self.version_hint or "").endswith("-dev"):
            issues.append(
                "development_phase is stable but version_hint still looks like a -dev build; "
                "align labels for honest self-representation."
            )
        return issues

    def development_context_kwargs(self) -> dict:
        """Kwargs for ``resolve_development_context`` / EthicsEngine construction."""
        return {
            "phase": self.development_phase,
            "version_hint": self.version_hint,
        }
