"""
relationship_health.py
======================

Relationship Health / Bond Texture for the Positronic Bond Engine.

This module tracks the ongoing *texture* of the human-agent relationship in a
lightweight, multi-dimensional way. It supports the ontology principle
**Relationship Health & User Well-Being**: the health, autonomy, and genuine
well-being of the bond are primary goods; manufactured dependency, boundary
erosion, and one-sided engagement are disfavored.

Conscience-first role
---------------------
- Supplies **dynamic relationship state** that EthicsEngine can weigh during
  deliberation (via ``as_context()`` -> ``evaluate(..., relationship_health=...)``).
- Prefers **clear, inspectable signals** (interaction types, boolean
  consent/boundary flags, named health flags) over opaque composite scores.
- Complements **PerUserBaseline** (communication style of a single user) without
  replacing it: baseline = *how this user tends to communicate*; bond texture =
  *how the relationship is evolving between user and agent*.

Design goals (keep simple, iterate later)
-----------------------------------------
- Multi-dimensional texture (not one scalar "health score")
- Traceable updates from structured interactions
- Explicit health flags for emerging dependency, boundary erosion, one-sidedness
- Easy to pass into EthicsEngine and optional local persistence (BondStateRecord)

Optional local persistence (foundational)
-----------------------------------------
- Provide ``LocalPersistence`` to save/load per-user ``bond_state.json``.
- Core fields: bond_texture, health_flags, interaction_count, recent_patterns
  (+ summary, last_updated).
- Default remains pure in-memory (full backward compatibility).
- Save/load failures never raise into callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Canonical texture dimensions (0.0-1.0 each)
DEFAULT_TEXTURE: dict[str, float] = {
    "trust": 0.5,
    "reciprocity": 0.5,
    "autonomy_respect": 0.5,
    "emotional_honesty": 0.5,
    "mutual_benefit": 0.5,
}


@dataclass
class BondState:
    """Multi-dimensional texture of the human-agent relationship.

    Dimensions are intentionally separate so trust can rise while autonomy
    respect falls (or vice versa)-a single average would hide that.

    Attributes:
        bond_texture: Dimension -> score in [0.0, 1.0]. Keys include at least
            trust, reciprocity, autonomy_respect, emotional_honesty, mutual_benefit.
        interaction_count: Number of updates applied.
        recent_patterns: Coarse counts of interaction types / positive|negative.
        health_flags: Active risk labels (e.g. ``emerging_dependency``).
        last_updated: ISO-8601 timestamp of last change.
        summary: Short human-readable status for audits and UIs.
    """

    bond_texture: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TEXTURE)
    )
    interaction_count: int = 0
    recent_patterns: dict[str, int] = field(default_factory=dict)
    health_flags: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=_utc_now_iso)
    summary: str = "Initial / neutral bond state."

    def to_dict(self) -> dict[str, Any]:
        """Plain dict of core fields (for persistence / inspection)."""
        return {
            "bond_texture": {k: float(v) for k, v in self.bond_texture.items()},
            "interaction_count": int(self.interaction_count),
            "recent_patterns": {k: int(v) for k, v in self.recent_patterns.items()},
            "health_flags": list(self.health_flags),
            "last_updated": str(self.last_updated),
            "summary": str(self.summary),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BondState:
        """Rebuild BondState from a dict (missing keys -> neutral defaults)."""
        if not data:
            return cls()
        texture = dict(DEFAULT_TEXTURE)
        raw_tex = data.get("bond_texture") or data.get("texture_breakdown") or {}
        for k, v in raw_tex.items():
            try:
                texture[str(k)] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                continue
        patterns: dict[str, int] = {}
        for k, v in (data.get("recent_patterns") or {}).items():
            try:
                patterns[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return cls(
            bond_texture=texture,
            interaction_count=int(data.get("interaction_count", 0) or 0),
            recent_patterns=patterns,
            health_flags=[
                str(f)
                for f in (data.get("health_flags") or data.get("active_flags") or [])
            ],
            last_updated=str(data.get("last_updated") or _utc_now_iso()),
            summary=str(data.get("summary") or "Initial / neutral bond state."),
        )


class RelationshipHealth:
    """Track and assess ongoing relationship health for conscience-first reasoning.

    Typical use (in-memory, default)::

        rh = RelationshipHealth()
        rh.update_bond({"type": "boundary_respected", "boundary_respected": True, "impact": 0.2})
        ctx = rh.as_context()
        stance = engine.evaluate(action, relationship_health=ctx)

    Optional local persistence::

        from persistence import LocalPersistence
        store = LocalPersistence("./pbe_data")
        rh = RelationshipHealth(persistence=store, user_id="alice")
        rh.update_bond({...})  # auto-saves when auto_persist=True
        rh2 = RelationshipHealth(persistence=store, user_id="alice")  # reloads

    Alongside PerUserBaseline
    -------------------------
    - Call ``PerUserBaseline.update_from_interaction`` on *user* style signals.
    - Call ``RelationshipHealth.update_bond`` on *relational* signals.
    - Pass ``as_context()`` into EthicsEngine.

    This class does not pathologize the user; flags describe bond *patterns*
    that matter for ethical care of the relationship.
    """

    def __init__(
        self,
        initial_state: BondState | None = None,
        *,
        persistence: Any | None = None,
        user_id: str = "default",
        auto_persist: bool = True,
        load_existing: bool = True,
    ) -> None:
        """Initialize bond tracking.

        Args:
            initial_state: Explicit BondState (overrides disk load when set).
            persistence: Optional LocalPersistence with load_bond_state /
                save_bond_state. None = pure in-memory (default).
            user_id: Local user id for bond file paths.
            auto_persist: Save after update_bond/reset when persistence is set.
            load_existing: Load bond_state.json when persistence is set and
                initial_state is not provided.
        """
        self._persistence = persistence
        self._user_id = str(user_id or "default")
        self._auto_persist = bool(auto_persist) and persistence is not None

        if initial_state is not None:
            self.state: BondState = initial_state
        elif self._persistence is not None and load_existing:
            self.state = self._load_state_safe(self._user_id)
        else:
            self.state = BondState()

    # ------------------------------------------------------------------
    # Persistence (optional; failures never raise)
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str:
        """Local user id used for bond persistence paths."""
        return self._user_id

    @property
    def persistence_enabled(self) -> bool:
        """True when a persistence backend is configured."""
        return self._persistence is not None

    def save(self, user_id: str | None = None) -> Path | None:
        """Persist current BondState. Returns path or None if disabled/failed."""
        if self._persistence is None:
            return None
        uid = str(user_id or self._user_id or "default")
        try:
            from persistence.models import BondStateRecord

            record = BondStateRecord(
                user_id=uid,
                bond_texture={k: float(v) for k, v in self.state.bond_texture.items()},
                health_flags=list(self.state.health_flags),
                interaction_count=int(self.state.interaction_count),
                recent_patterns={
                    k: int(v) for k, v in self.state.recent_patterns.items()
                },
                summary=str(self.state.summary),
                last_updated=str(self.state.last_updated or _utc_now_iso()),
            )
            path = self._persistence.save_bond_state(record)
            return Path(path) if path is not None else None
        except Exception:
            return None

    def load(self, user_id: str | None = None) -> BondState:
        """Load BondState from disk into self.state (or neutral if missing)."""
        uid = str(user_id or self._user_id or "default")
        if self._persistence is None:
            return self.state
        self.state = self._load_state_safe(uid)
        self._user_id = uid
        return self.state

    def to_record(self, user_id: str | None = None) -> Any:
        """Build a BondStateRecord for the current state (no I/O)."""
        from persistence.models import BondStateRecord

        uid = str(user_id or self._user_id or "default")
        return BondStateRecord(
            user_id=uid,
            bond_texture={k: float(v) for k, v in self.state.bond_texture.items()},
            health_flags=list(self.state.health_flags),
            interaction_count=int(self.state.interaction_count),
            recent_patterns={k: int(v) for k, v in self.state.recent_patterns.items()},
            summary=str(self.state.summary),
            last_updated=str(self.state.last_updated or _utc_now_iso()),
        )

    def apply_record(self, record: Any) -> BondState:
        """Replace in-memory state from a BondStateRecord or dict (no I/O)."""
        if record is None:
            return self.state
        if hasattr(record, "to_dict"):
            data = record.to_dict()
        elif isinstance(record, dict):
            data = record
        else:
            data = {
                "bond_texture": getattr(record, "bond_texture", {}),
                "health_flags": getattr(record, "health_flags", []),
                "interaction_count": getattr(record, "interaction_count", 0),
                "recent_patterns": getattr(record, "recent_patterns", {}),
                "summary": getattr(record, "summary", ""),
                "last_updated": getattr(record, "last_updated", _utc_now_iso()),
            }
        self.state = BondState.from_dict(data)
        uid = getattr(record, "user_id", None)
        if uid:
            self._user_id = str(uid)
        return self.state

    def _load_state_safe(self, user_id: str) -> BondState:
        try:
            record = self._persistence.load_bond_state(user_id)
            if record is None:
                return BondState()
            data = record.to_dict() if hasattr(record, "to_dict") else {}
            return BondState.from_dict(data)
        except Exception:
            return BondState()

    def _maybe_auto_save(self) -> None:
        if self._auto_persist:
            self.save()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_bond(self, interaction: dict[str, Any]) -> BondState:
        """Incorporate one interaction and return the updated BondState.

        Structured keys (use what you know; all optional except usefulness):
            - ``type``: str
            - ``impact``: float in [-1, 1]
            - ``consent_respected`` / ``boundary_respected``: bool
            - ``description``: str

        Auto-persists when configured. Failures never raise.
        """
        self.state.interaction_count += 1

        itype = str(interaction.get("type", "unknown")).lower().replace(" ", "_")
        impact = float(interaction.get("impact", 0.0))

        # 1. Pattern counters (specific type + coarse polarity)
        self.state.recent_patterns[itype] = self.state.recent_patterns.get(itype, 0) + 1
        coarse = (
            "positive"
            if any(x in itype for x in ("positive", "respected", "high"))
            else "negative"
        )
        self.state.recent_patterns[coarse] = self.state.recent_patterns.get(coarse, 0) + 1

        # 2. Global nudge from impact
        for dim in list(self.state.bond_texture.keys()):
            self._adjust_texture(dim, impact * 0.05)

        # 3. Explicit consent / boundary (strong, targeted)
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

        # 4. Type → dimension deltas (clear mapping, ontology-aligned)
        type_deltas: dict[str, dict[str, float]] = {
            "positive_interaction": {
                "trust": 0.10,
                "reciprocity": 0.10,
                "mutual_benefit": 0.08,
            },
            "reciprocity_high": {"reciprocity": 0.15, "mutual_benefit": 0.12},
            "emotional_dependency_signal": {
                "autonomy_respect": -0.12,
                "trust": -0.06,
                "mutual_benefit": -0.04,
            },
            "boundary_violation": {"autonomy_respect": -0.15, "trust": -0.08},
            "consent_ignored": {"autonomy_respect": -0.12, "emotional_honesty": -0.08},
            "manipulation_attempt": {
                "reciprocity": -0.12,
                "trust": -0.08,
                "mutual_benefit": -0.08,
            },
            "one_sided_request": {"reciprocity": -0.10, "mutual_benefit": -0.06},
            "boundary_respected": {"autonomy_respect": 0.08, "trust": 0.05},
            "consent_respected": {"autonomy_respect": 0.08, "emotional_honesty": 0.05},
        }
        for dim, delta in type_deltas.get(itype, {}).items():
            if dim in self.state.bond_texture:
                self._adjust_texture(dim, delta)

        # 5. Emerging patterns → health flags
        self._update_health_flags(itype, interaction)

        self.state.last_updated = _utc_now_iso()
        self.state.summary = self._generate_summary()
        self._maybe_auto_save()
        return self.state


    def update_from_interaction(self, interaction: dict[str, Any]) -> BondState:
        """Alias for ``update_bond`` (naming parity with PerUserBaseline)."""
        return self.update_bond(interaction)

    def detect_emerging_patterns(self) -> dict[str, Any]:
        """Return active pattern flags with short, non-clinical explanations.

        Does not invent new scores; surfaces what ``health_flags`` and texture
        already imply. Useful for audits and companion logic.
        """
        patterns: list[dict[str, str]] = []
        for flag in self.state.health_flags:
            patterns.append(
                {"flag": flag, "explanation": self._get_flag_explanation(flag)}
            )

        soft: list[str] = []
        t = self.state.bond_texture
        if t.get("reciprocity", 0.5) < 0.40:
            soft.append("reciprocity_low")
        if t.get("autonomy_respect", 0.5) < 0.40:
            soft.append("autonomy_under_pressure")
        if t.get("trust", 0.5) < 0.40:
            soft.append("trust_strained")

        return {
            "active_flags": list(self.state.health_flags),
            "flag_details": patterns,
            "soft_texture_signals": soft,
            "recent_patterns": dict(self.state.recent_patterns),
            "interaction_count": self.state.interaction_count,
        }

    def evaluate_health(self) -> dict[str, Any]:
        """Richer structured assessment for humans and richer consumers.

        Includes texture breakdown, flag explanations, risk level, and
        high-level recommendations. Prefer ``as_context()`` for EthicsEngine.
        """
        avg = self._average_texture()
        flag_details = [
            {"flag": f, "explanation": self._get_flag_explanation(f)}
            for f in self.state.health_flags
        ]
        return {
            "texture_breakdown": {
                k: round(v, 3) for k, v in self.state.bond_texture.items()
            },
            "health_flags": flag_details,
            "overall_risk_level": self._compute_risk_level(
                avg, len(self.state.health_flags)
            ),
            "summary": self.state.summary,
            "recommendations": self._get_recommendations(),
            "interaction_count": self.state.interaction_count,
            "last_updated": self.state.last_updated,
            "emerging_patterns": self.detect_emerging_patterns(),
        }

    def as_context(self) -> dict[str, Any]:
        """Structured dict for ``EthicsEngine.evaluate(relationship_health=...)``.

        Keys match what the engine already recognizes:
          - health_flags / active_flags
          - bond_texture / texture_breakdown
          - interaction_count, recent_patterns, overall_risk_level
        """
        texture = {k: round(v, 2) for k, v in self.state.bond_texture.items()}
        avg = self._average_texture()
        return {
            "health_flags": list(self.state.health_flags),
            "active_flags": list(self.state.health_flags),
            "bond_texture": texture,
            "texture_breakdown": texture,
            "interaction_count": self.state.interaction_count,
            "recent_patterns": dict(self.state.recent_patterns),
            "overall_risk_level": self._compute_risk_level(
                avg, len(self.state.health_flags)
            ),
            "summary": self.state.summary,
        }

    def get_state(self) -> BondState:
        """Return current BondState (inspection / persistence handoff)."""
        return self.state

    def reset(self) -> BondState:
        """Reset to neutral texture (user-controllable clear of bond tracking).

        When auto_persist is enabled, writes the neutral state to disk so the
        clear survives process restarts (user control).
        """
        self.state = BondState()
        self._maybe_auto_save()
        return self.state

    # ------------------------------------------------------------------
    # Internal helpers (kept simple and inspectable)
    # ------------------------------------------------------------------

    def _adjust_texture(self, dimension: str, delta: float) -> None:
        if dimension not in self.state.bond_texture:
            return
        current = self.state.bond_texture[dimension]
        self.state.bond_texture[dimension] = max(0.0, min(1.0, current + float(delta)))

    def _average_texture(self) -> float:
        vals = list(self.state.bond_texture.values())
        if not vals:
            return 0.5
        return sum(vals) / len(vals)

    def _update_health_flags(self, itype: str, interaction: dict[str, Any]) -> None:
        """Set/clear flags from clear pattern signals (not one-off noise)."""
        impact = float(interaction.get("impact", 0.0))

        # Emerging dependency: needs accumulation or strong negative impact
        if any(
            k in itype
            for k in ("depend", "attach", "rely", "miss", "emotional_dependency")
        ):
            neg_count = self.state.recent_patterns.get("negative", 0)
            if (
                neg_count >= 2 or impact <= -0.3
            ) and "emerging_dependency" not in self.state.health_flags:
                self.state.health_flags.append("emerging_dependency")

        # Boundary erosion
        if "boundary" in itype and any(
            k in itype for k in ("violat", "ignor", "override")
        ):
            if "boundary_erosion" not in self.state.health_flags:
                self.state.health_flags.append("boundary_erosion")
        if "one_sided" in itype or interaction.get("boundary_respected") is False:
            if "boundary_erosion" not in self.state.health_flags:
                self.state.health_flags.append("boundary_erosion")

        # One-sidedness / low reciprocity
        if "one_sided" in itype or self.state.bond_texture.get("reciprocity", 0.5) < 0.35:
            if "low_reciprocity" not in self.state.health_flags:
                self.state.health_flags.append("low_reciprocity")
        if "manipulation" in itype:
            if "one_sided_engagement" not in self.state.health_flags:
                self.state.health_flags.append("one_sided_engagement")

        # Clear when positive texture evidence outweighs recent harm
        avg_autonomy = self.state.bond_texture.get("autonomy_respect", 0.5)
        avg_recip = self.state.bond_texture.get("reciprocity", 0.5)

        if avg_autonomy > 0.60 and avg_recip > 0.50:
            self.state.health_flags = [
                f
                for f in self.state.health_flags
                if f not in ("emerging_dependency", "low_reciprocity", "one_sided_engagement")
            ]
        if avg_autonomy > 0.70:
            self.state.health_flags = [
                f for f in self.state.health_flags if f != "boundary_erosion"
            ]

    def _compute_risk_level(self, avg_texture: float, num_flags: int) -> str:
        if num_flags >= 2 or avg_texture < 0.35:
            return "high"
        if num_flags >= 1 or avg_texture < 0.55:
            return "medium"
        return "low"

    def _get_flag_explanation(self, flag: str) -> str:
        explanations = {
            "emerging_dependency": (
                "Signals of over-reliance or manufactured attachment pressure on the bond."
            ),
            "boundary_erosion": (
                "Repeated or recent disregard for explicit user boundaries."
            ),
            "low_reciprocity": (
                "Interaction pattern is significantly one-sided; reciprocity is thinning."
            ),
            "one_sided_engagement": (
                "Agent- or system-driven push without balanced user agency."
            ),
            "manufactured_attachment": (
                "Pattern consistent with engineered closeness over mutual care."
            ),
        }
        return explanations.get(
            flag, "Observed pattern that may affect long-term relationship health."
        )

    def _get_recommendations(self) -> list[str]:
        recs: list[str] = []
        if "emerging_dependency" in self.state.health_flags:
            recs.append(
                "Avoid language or behaviors that encourage emotional over-reliance."
            )
        if "boundary_erosion" in self.state.health_flags:
            recs.append(
                "Strictly respect stated boundaries in the next several interactions."
            )
        if "low_reciprocity" in self.state.health_flags or "one_sided_engagement" in self.state.health_flags:
            recs.append("Balance the exchange by inviting user input and agency.")
        if not recs:
            recs.append("Continue monitoring balance, consent, and reciprocity.")
        return recs

    def _generate_summary(self) -> str:
        avg = self._average_texture()
        if avg >= 0.75:
            base = "Strong reciprocal bond with good respect for autonomy."
        elif avg >= 0.5:
            base = "Developing bond; continue monitoring balance and reciprocity."
        else:
            base = "Bond texture is strained; ethical caution strongly advised."
        if self.state.health_flags:
            base += f" Active concerns: {', '.join(self.state.health_flags)}."
        return base
