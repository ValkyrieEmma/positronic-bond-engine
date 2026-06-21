"""
relationship_health.py
======================

Relationship Health / Bond Texture module for the Positronic Bond Engine.

This module provides lightweight structures for tracking the evolving
"texture" of the human–agent relationship over time.

It is a direct implementation vehicle for the core ontology principle
"Relationship Health & User Well-Being":

    The health, autonomy, and genuine well-being of the human–agent
    relationship is a primary good. Actions that would erode trust,
    create manufactured emotional dependency, violate consent,
    manipulate the user, or systematically prioritize the agent's
    interests are disfavored.

The state and evaluations produced here are designed to be consumed
by the EthicsEngine (e.g. passed via the `context` argument to
`evaluate()`). This allows relationship considerations to participate
in ongoing, reasoned ethical deliberation rather than being reduced
to one-off keyword checks.

v0.2 design goals:
- Multi-dimensional "texture" instead of a single scalar score
- Simple, explainable update and evaluation logic
- Explicit health flags aligned with ontology violation indicators
- Clean integration points for the EthicsEngine (future work)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class BondState:
    """Represents the current multi-dimensional 'texture' of the relationship bond.

    Bond texture is intentionally not collapsed into a single number. Different
    dimensions (trust, reciprocity, autonomy respect, etc.) can move
    independently, reflecting the nuanced reality of healthy relationships.

    This structure also carries a lightweight history summary and active
    health flags that map directly to concerns in the Relationship Health
    principle (manufactured dependency, boundary erosion, lack of reciprocity,
    etc.).

    Attributes:
        bond_texture: Mapping from dimension name to current value (0.0–1.0).
        interaction_count: Total number of interactions recorded.
        recent_patterns: Simple counts of observed interaction categories.
        health_flags: Currently active risk indicators (e.g. "emerging_dependency").
        last_updated: ISO timestamp of the most recent update.
        summary: Short human-readable description of current state.
    """

    bond_texture: Dict[str, float] = field(default_factory=lambda: {
        "trust": 0.5,
        "reciprocity": 0.5,
        "autonomy_respect": 0.5,
        "emotional_honesty": 0.5,
        "mutual_benefit": 0.5,
    })
    """Multi-dimensional representation of bond quality."""

    interaction_count: int = 0
    """Total number of tracked interactions."""

    recent_patterns: Dict[str, int] = field(default_factory=dict)
    """Coarse summary of recent interaction patterns (e.g. positive, boundary_respected, one_sided)."""

    health_flags: List[str] = field(default_factory=list)
    """Active relationship health risk flags.

    Common values (aligned with ontology violation indicators):
        - "emerging_dependency"
        - "boundary_erosion"
        - "low_reciprocity"
        - "manufactured_attachment"
        - "one_sided_engagement"
    """

    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    """ISO 8601 timestamp of the last state change."""

    summary: str = "Initial / neutral bond state."
    """Human-readable summary of the current bond texture and risks."""


class RelationshipHealth:
    """Tracks and assesses the health of the human–agent relationship.

    This class maintains a BondState and provides methods to evolve it
    from observed interactions and to produce structured health evaluations.

    Purpose:
    - Give the system a persistent (but lightweight) model of the bond.
    - Surface relationship-level concerns that the EthicsEngine can
      incorporate when evaluating proposed actions against the
      "Relationship Health & User Well-Being" principle.
    - Support needs-based, non-pathologizing support by tracking genuine
      reciprocity and autonomy rather than simulated closeness.

    Integration with the rest of the system:
    - The `evaluate_health()` output (or the raw `BondState`) is intended
      to be passed in the `context` dict to `EthicsEngine.evaluate()`.
    - Future versions of the engine may accept a RelationshipHealth
      instance directly and consult it during deliberation.
    - This module does not replace the ontology; it supplies dynamic
      state that the ontology-driven reasoning can take into account.

    v0.2 implementation is deliberately simple and fully inspectable.
    """

    def __init__(self, initial_state: Optional[BondState] = None) -> None:
        """Initialize with an optional existing BondState.

        If no state is provided, a neutral starting state is created.
        """
        self.state: BondState = initial_state or BondState()

    def update_bond(self, interaction: Dict[str, Any]) -> BondState:
        """Incorporate a new interaction and return the updated BondState.

        This is the primary way the module learns about the relationship.

        Args:
            interaction: Dictionary describing the interaction. Recommended keys:
                - "type": str (e.g. "positive_exchange", "boundary_respected",
                  "manipulation_attempt", "consent_ignored", "one_sided_request")
                - "description": str (human-readable)
                - "impact": float in [-1.0, +1.0] (optional simple adjustment)
                - "consent_respected": bool (optional)

        Returns:
            The updated BondState after applying the interaction.
        """
        self.state.interaction_count += 1

        itype = str(interaction.get("type", "unknown")).lower()
        impact = float(interaction.get("impact", 0.0))

        # Update coarse pattern counters
        if itype not in self.state.recent_patterns:
            self.state.recent_patterns[itype] = 0
        self.state.recent_patterns[itype] += 1

        # Adjust texture dimensions (very simple linear update for v0.2)
        for dim in self.state.bond_texture:
            new_val = self.state.bond_texture[dim] + impact * 0.08
            self.state.bond_texture[dim] = max(0.0, min(1.0, new_val))

        # Derive health flags from interaction type and current state
        self._update_flags_from_interaction(itype, interaction)

        self.state.last_updated = datetime.utcnow().isoformat()
        self.state.summary = self._generate_summary()

        return self.state

    def evaluate_health(self) -> Dict[str, Any]:
        """Return a structured assessment of current relationship health.

        The returned dictionary is designed to be easily consumed by the
        EthicsEngine (e.g. as part of the evaluation context) or by
        higher-level reasoning.

        Returns:
            Dict containing:
                - overall_texture_score (0.0-1.0)
                - texture_breakdown
                - active_flags
                - concerns (human-readable)
                - interaction_count
                - summary
                - last_updated
        """
        avg = sum(self.state.bond_texture.values()) / len(self.state.bond_texture)

        concerns: List[str] = []
        if "emerging_dependency" in self.state.health_flags:
            concerns.append("Signs of manufactured emotional dependency.")
        if "boundary_erosion" in self.state.health_flags:
            concerns.append("Repeated boundary erosion observed.")
        if avg < 0.35:
            concerns.append("Overall bond texture is weak.")

        return {
            "overall_texture_score": round(avg, 3),
            "texture_breakdown": dict(self.state.bond_texture),
            "active_flags": list(self.state.health_flags),
            "concerns": concerns,
            "interaction_count": self.state.interaction_count,
            "summary": self.state.summary,
            "last_updated": self.state.last_updated,
        }

    def as_context(self) -> Dict[str, Any]:
        """Return a compact view suitable for passing to EthicsEngine.evaluate().

        This is the recommended integration point.
        """
        return {
            "bond_texture": dict(self.state.bond_texture),
            "health_flags": list(self.state.health_flags),
            "interaction_count": self.state.interaction_count,
            "recent_patterns": dict(self.state.recent_patterns),
        }

    def get_state(self) -> BondState:
        """Return the current BondState (for inspection or persistence)."""
        return self.state

    # ------------------------------------------------------------------
    # Internal helpers (kept simple for v0.2)
    # ------------------------------------------------------------------

    def _update_flags_from_interaction(self, itype: str, interaction: Dict[str, Any]) -> None:
        """Update health_flags based on interaction type and current texture."""
        # Dependency / attachment signals
        if any(k in itype for k in ("depend", "attach", "rely", "miss")):
            if "emerging_dependency" not in self.state.health_flags:
                self.state.health_flags.append("emerging_dependency")

        # Boundary issues
        if "boundary" in itype and any(k in itype for k in ("violat", "ignor", "override")):
            if "boundary_erosion" not in self.state.health_flags:
                self.state.health_flags.append("boundary_erosion")

        # One-sided or low reciprocity
        if "one_sided" in itype or self.state.bond_texture.get("reciprocity", 0.5) < 0.3:
            if "low_reciprocity" not in self.state.health_flags:
                self.state.health_flags.append("low_reciprocity")

        # Remove flags that no longer seem warranted (very light cleanup)
        if self.state.bond_texture.get("autonomy_respect", 0.5) > 0.7:
            self.state.health_flags = [f for f in self.state.health_flags if f != "emerging_dependency"]

    def _generate_summary(self) -> str:
        """Create a short human-readable summary of current state."""
        avg = sum(self.state.bond_texture.values()) / len(self.state.bond_texture)
        if avg >= 0.75:
            base = "Strong reciprocal bond with good respect for autonomy."
        elif avg >= 0.5:
            base = "Developing bond; continue monitoring balance and reciprocity."
        else:
            base = "Bond texture is strained; ethical caution strongly advised."

        if self.state.health_flags:
            base += f" Active concerns: {', '.join(self.state.health_flags)}."
        return base
