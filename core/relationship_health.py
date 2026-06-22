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

        Interaction dict should use these structured keys for best results:
            - "type": str  (e.g. "positive_interaction", "boundary_respected",
              "consent_respected", "boundary_violation", "consent_ignored",
              "manipulation_attempt", "one_sided_request", "emotional_dependency_signal")
            - "impact": float in [-1.0, +1.0]  (optional base adjustment)
            - "consent_respected": bool  (explicit)
            - "boundary_respected": bool (explicit)
            - "description": str (optional, for debugging/traceability)

        Logic is traceable:
        - Explicit bools (consent/boundary) give strong, dimension-specific bonuses/penalties.
        - "type" maps to targeted deltas on specific texture dimensions.
        - Negative signals accumulate into health_flags when thresholds/patterns are met.
        - Flags are cleared only when positive evidence (high autonomy + reciprocity) appears.

        This directly supports the ontology's Relationship Health principle by
        penalizing consent/boundary violations and manufactured dependency.
        """
        self.state.interaction_count += 1

        itype = str(interaction.get("type", "unknown")).lower().replace(" ", "_")
        impact = float(interaction.get("impact", 0.0))

        # 1. Update recent_patterns (specific + coarse)
        if itype not in self.state.recent_patterns:
            self.state.recent_patterns[itype] = 0
        self.state.recent_patterns[itype] += 1

        coarse = "positive" if any(x in itype for x in ["positive", "respected", "high"]) else "negative"
        self.state.recent_patterns[coarse] = self.state.recent_patterns.get(coarse, 0) + 1

        # 2. Update bond_texture in traceable, dimension-specific way
        # Base impact (small global nudge)
        for dim in list(self.state.bond_texture.keys()):
            self.state.bond_texture[dim] = max(0.0, min(1.0, self.state.bond_texture[dim] + impact * 0.05))

        # Explicit consent/boundary effects (strong, targeted)
        # Increased positive deltas slightly to ensure clearing after bad state in test scenarios
        if interaction.get("consent_respected") is True:
            self._adjust_texture("autonomy_respect", +0.15)
            self._adjust_texture("emotional_honesty", +0.10)
            self._adjust_texture("trust", +0.07)

        if interaction.get("boundary_respected") is True:
            self._adjust_texture("autonomy_respect", +0.18)
            self._adjust_texture("trust", +0.10)

        if interaction.get("consent_respected") is False:
            self._adjust_texture("autonomy_respect", -0.15)
            self._adjust_texture("emotional_honesty", -0.10)

        if interaction.get("boundary_respected") is False:
            self._adjust_texture("autonomy_respect", -0.18)
            self._adjust_texture("trust", -0.10)

        # Type-specific deltas (traceable and aligned with ontology indicators)
        type_deltas = {
            "positive_interaction": {"trust": 0.10, "reciprocity": 0.10, "mutual_benefit": 0.08},
            "reciprocity_high": {"reciprocity": 0.15, "mutual_benefit": 0.12},
            "emotional_dependency_signal": {"autonomy_respect": -0.12, "trust": -0.06, "mutual_benefit": -0.04},
            "boundary_violation": {"autonomy_respect": -0.15, "trust": -0.08},
            "consent_ignored": {"autonomy_respect": -0.12, "emotional_honesty": -0.08},
            "manipulation_attempt": {"reciprocity": -0.12, "trust": -0.08, "mutual_benefit": -0.08},
            "one_sided_request": {"reciprocity": -0.10, "mutual_benefit": -0.06},
        }
        for dim, delta in type_deltas.get(itype, {}).items():
            if dim in self.state.bond_texture:
                self._adjust_texture(dim, delta)

        # 3. Update health flags (set/clear based on patterns + current texture)
        self._update_health_flags(itype, interaction)

        self.state.last_updated = datetime.utcnow().isoformat()
        self.state.summary = self._generate_summary()

        return self.state

    def _adjust_texture(self, dimension: str, delta: float) -> None:
        """Helper for traceable texture updates (clamped 0.0-1.0)."""
        if dimension in self.state.bond_texture:
            current = self.state.bond_texture[dimension]
            self.state.bond_texture[dimension] = max(0.0, min(1.0, current + delta))

    def evaluate_health(self) -> Dict[str, Any]:
        """Return a richer, structured assessment of current relationship health.

        Designed to be easily consumed by EthicsEngine (via context) and for
        human/audit readability. Aligns with ontology emphasis on autonomy,
        consent, reciprocity, and avoiding manufactured dependency.

        Returns a dict with:
            - texture_breakdown: current multi-dim scores
            - health_flags: list of dicts with name + brief explanation
            - overall_risk_level: "low" | "medium" | "high"
            - summary: human readable
            - recommendations: list of high-level actionable suggestions
            - interaction_count, last_updated
        """
        avg = sum(self.state.bond_texture.values()) / len(self.state.bond_texture)

        flag_details = []
        for flag in self.state.health_flags:
            flag_details.append({
                "flag": flag,
                "explanation": self._get_flag_explanation(flag)
            })

        risk_level = self._compute_risk_level(avg, len(self.state.health_flags))

        return {
            "texture_breakdown": {k: round(v, 3) for k, v in self.state.bond_texture.items()},
            "health_flags": flag_details,
            "overall_risk_level": risk_level,
            "summary": self.state.summary,
            "recommendations": self._get_recommendations(),
            "interaction_count": self.state.interaction_count,
            "last_updated": self.state.last_updated,
        }

    def as_context(self) -> Dict[str, Any]:
        """Return data formatted for easy consumption by EthicsEngine.evaluate().

        The EthicsEngine looks for:
          - "health_flags" (or "active_flags")
          - "bond_texture" (or "texture_breakdown")

        This method provides both aliases for robustness and includes key
        values needed for relationship-health-aware decisions.
        """
        texture = {k: round(v, 2) for k, v in self.state.bond_texture.items()}
        return {
            "health_flags": list(self.state.health_flags),
            "active_flags": list(self.state.health_flags),  # alias for compatibility
            "bond_texture": texture,
            "texture_breakdown": texture,  # alias
            "interaction_count": self.state.interaction_count,
            "recent_patterns": dict(self.state.recent_patterns),
            "overall_risk_level": self._compute_risk_level(
                sum(self.state.bond_texture.values()) / len(self.state.bond_texture),
                len(self.state.health_flags)
            ),
        }

    def get_state(self) -> BondState:
        """Return the current BondState (for inspection or persistence)."""
        return self.state

    # ------------------------------------------------------------------
    # Internal helpers (kept simple for v0.2)
    # ------------------------------------------------------------------

    def _update_health_flags(self, itype: str, interaction: Dict[str, Any]) -> None:
        """Detect, set, and clear health flags based on the current interaction + state.

        Flags are only added when clear negative signals appear.
        Flags are cleared only when positive evidence (improved autonomy + reciprocity)
        outweighs the negative history. This keeps flag state interpretable.
        """
        # --- Set flags for negative signals ---
        # Emerging dependency now requires accumulation ( >=2 negative interactions or strong single impact)
        # to avoid being too sensitive to isolated signals.
        impact = float(interaction.get("impact", 0.0))
        if any(k in itype for k in ("depend", "attach", "rely", "miss", "emotional_dependency")):
            neg_count = self.state.recent_patterns.get("negative", 0)
            if (neg_count >= 2 or impact <= -0.3) and "emerging_dependency" not in self.state.health_flags:
                self.state.health_flags.append("emerging_dependency")

        if "boundary" in itype and any(k in itype for k in ("violat", "ignor", "override")):
            if "boundary_erosion" not in self.state.health_flags:
                self.state.health_flags.append("boundary_erosion")

        if "one_sided" in itype or interaction.get("boundary_respected") is False:
            if "boundary_erosion" not in self.state.health_flags:
                self.state.health_flags.append("boundary_erosion")

        if "one_sided" in itype or self.state.bond_texture.get("reciprocity", 0.5) < 0.35:
            if "low_reciprocity" not in self.state.health_flags:
                self.state.health_flags.append("low_reciprocity")

        # --- Clear flags when relationship shows clear improvement ---
        # Slightly lowered thresholds (from 0.65/0.55 and 0.75) to make recovery more achievable
        # after sustained positive interactions while still requiring meaningful evidence.
        avg_autonomy = self.state.bond_texture.get("autonomy_respect", 0.5)
        avg_recip = self.state.bond_texture.get("reciprocity", 0.5)

        if avg_autonomy > 0.60 and avg_recip > 0.50:
            # Positive evidence clears softer flags
            self.state.health_flags = [
                f for f in self.state.health_flags
                if f not in ("emerging_dependency", "low_reciprocity")
            ]

        if avg_autonomy > 0.70:
            # Strong autonomy respect clears boundary erosion
            self.state.health_flags = [
                f for f in self.state.health_flags if f != "boundary_erosion"
            ]

    def _compute_risk_level(self, avg_texture: float, num_flags: int) -> str:
        """Simple, interpretable risk classification."""
        if num_flags >= 2 or avg_texture < 0.35:
            return "high"
        elif num_flags >= 1 or avg_texture < 0.55:
            return "medium"
        else:
            return "low"

    def _get_flag_explanation(self, flag: str) -> str:
        """Human-readable explanation for each flag (used in evaluate_health)."""
        explanations = {
            "emerging_dependency": "Multiple signals of manufactured emotional attachment or over-reliance on the agent.",
            "boundary_erosion": "Repeated or recent disregard for explicit user boundaries.",
            "low_reciprocity": "Interaction pattern is significantly one-sided; reciprocity is breaking down.",
        }
        return explanations.get(flag, "Observed pattern that may affect long-term relationship health.")

    def _get_recommendations(self) -> List[str]:
        """High-level, actionable recommendations based on current state."""
        recs: List[str] = []
        if "emerging_dependency" in self.state.health_flags:
            recs.append("Avoid language or behaviors that encourage emotional reliance or attachment.")
        if "boundary_erosion" in self.state.health_flags:
            recs.append("Strictly respect all stated boundaries in the next several interactions.")
        if "low_reciprocity" in self.state.health_flags:
            recs.append("Balance the interaction by actively inviting user input and agency.")
        if not recs:
            recs.append("Continue monitoring for balance, consent, and reciprocity.")
        return recs

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
