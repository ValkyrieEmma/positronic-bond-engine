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
        return issues
