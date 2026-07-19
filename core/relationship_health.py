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

Per-user identity & isolation (architectural principle)
-------------------------------------------------------
Bond texture is **owned by a single local ``user_id``**. When persistence is
enabled, every load/save path goes under ``users/<user_id>/bond_state.json``.

Design intent:
- ``user_id`` is a first-class field on this tracker (not an afterthought).
- With persistence enabled, callers **should** pass an explicit ``user_id`` so
  two humans never share or overwrite each other's bond state.
- If ``user_id`` is omitted, behavior falls back to ``"default"`` (backward
  compatible) and ``using_default_user_id`` is True so audits can flag soft
  identity ambiguity — evaluation never crashes on bad ids.
- Memory, baseline, bond, and ethics decision logs are separate artifacts that
  may share a ``user_id`` directory but must not be treated as the same object.

Curious Companion (understanding gaps)
--------------------------------------
``note_understanding_gaps`` may apply a **small, reversible** texture nudge when
history shows incomplete individual context. Influence is gated by health flags
and ethical concern; it never forces questions or creates dependency flags.

Multi-episode concept patterns (advisory)
-----------------------------------------
``detect_concept_patterns`` surfaces a small set of trajectory labels
(e.g. escalating_dependency, healthy_co_evolution). They are **advisory only** —
evidence for EthicsEngine, never hard overrides or forced questions.

Careful Truth-Telling readiness + confidence (advisory)
-------------------------------------------------------
``assess_truth_telling_readiness`` — timing / bond readiness for observation.
``assess_truth_confidence`` — epistemic confidence in a potential observation.
Neither generates speech or questions; see ``core.truth_telling_readiness`` and
``core.truth_confidence``. ``careful_truth_telling_joint`` combines both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .truth_confidence import (
    TruthConfidence,
    assess_truth_confidence,
    combine_with_readiness,
)
from .truth_telling_readiness import (
    TruthTellingReadiness,
    assess_truth_telling_readiness,
)

# Soft default when no user_id is supplied (in-memory / single-tenant demos).
DEFAULT_USER_ID = "default"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user_id(user_id: str | None, *, fallback: str = DEFAULT_USER_ID) -> str:
    """Normalize a local user id without raising (identity handling is fail-soft).

    Prefers ``persistence.paths.sanitize_user_id`` when available; otherwise
    strips to a conservative ``[A-Za-z0-9_-]`` form. Empty/invalid input
    returns ``fallback`` so bond tracking never crashes evaluation.
    """
    raw = str(user_id if user_id is not None else "").strip()
    if not raw:
        return fallback
    try:
        from persistence.paths import sanitize_user_id

        return sanitize_user_id(raw)
    except Exception:
        cleaned = "".join(c for c in raw if c.isalnum() or c in "_-")[:64]
        return cleaned or fallback


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
        curious_companion: Durable soft snapshot of open topics / last gap
            continuity (survives sessions when persistence is enabled).
        careful_truth_telling: Latest joint readiness × confidence snapshot
            (compact, advisory only — never forces speech).
    """

    bond_texture: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TEXTURE)
    )
    interaction_count: int = 0
    recent_patterns: dict[str, int] = field(default_factory=dict)
    health_flags: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=_utc_now_iso)
    summary: str = "Initial / neutral bond state."
    curious_companion: dict[str, Any] = field(default_factory=dict)
    careful_truth_telling: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Plain dict of core fields (for persistence / inspection)."""
        out: dict[str, Any] = {
            "bond_texture": {k: float(v) for k, v in self.bond_texture.items()},
            "interaction_count": int(self.interaction_count),
            "recent_patterns": {k: int(v) for k, v in self.recent_patterns.items()},
            "health_flags": list(self.health_flags),
            "last_updated": str(self.last_updated),
            "summary": str(self.summary),
        }
        if self.curious_companion:
            out["curious_companion"] = dict(self.curious_companion)
        if self.careful_truth_telling:
            out["careful_truth_telling"] = dict(self.careful_truth_telling)
        return out

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
        cc = data.get("curious_companion")
        if not isinstance(cc, dict):
            cc = {}
        ctt = data.get("careful_truth_telling")
        if not isinstance(ctt, dict):
            ctt = {}
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
            curious_companion=dict(cc),
            careful_truth_telling=dict(ctt),
        )


class RelationshipHealth:
    """Track and assess ongoing relationship health for conscience-first reasoning.

    Typical use (in-memory, default)::

        rh = RelationshipHealth()
        rh.update_bond({"type": "boundary_respected", "boundary_respected": True, "impact": 0.2})
        ctx = rh.as_context()  # includes user_id for EthicsEngine scoping
        stance = engine.evaluate(action, relationship_health=ctx)

    Optional local persistence (prefer explicit user_id)::

        from persistence import LocalPersistence
        store = LocalPersistence("./pbe_data")
        rh = RelationshipHealth(persistence=store, user_id="alice")
        rh.update_bond({...})  # auto-saves under users/alice/bond_state.json
        rh2 = RelationshipHealth(persistence=store, user_id="alice")  # reloads

    Per-user isolation
    ------------------
    One ``RelationshipHealth`` instance tracks **one** local user. Do not reuse
    the same instance across humans without ``set_user_id`` / ``load``. With
    persistence, omitting ``user_id`` falls back to ``"default"`` and sets
    ``using_default_user_id`` so callers/audits can notice soft ambiguity.

    Alongside PerUserBaseline
    -------------------------
    - Call ``PerUserBaseline.update_from_interaction`` on *user* style signals.
    - Call ``RelationshipHealth.update_bond`` on *relational* signals.
    - Pass ``as_context()`` into EthicsEngine (carries ``user_id``).

    This class does not pathologize the user; flags describe bond *patterns*
    that matter for ethical care of the relationship.
    """

    def __init__(
        self,
        initial_state: BondState | None = None,
        *,
        persistence: Any | None = None,
        user_id: str | None = None,
        auto_persist: bool = True,
        load_existing: bool = True,
    ) -> None:
        """Initialize bond tracking.

        Args:
            initial_state: Explicit BondState (overrides disk load when set).
            persistence: Optional LocalPersistence with load_bond_state /
                save_bond_state. None = pure in-memory (default).
            user_id: Local user id for bond file paths and EthicsEngine
                scoping via ``as_context()``. Strongly preferred when
                ``persistence`` is set. None / empty → ``"default"``
                (backward compatible; see ``using_default_user_id``).
            auto_persist: Save after update_bond/reset when persistence is set.
            load_existing: Load bond_state.json when persistence is set and
                initial_state is not provided.
        """
        self._persistence = persistence
        # Explicit vs fallback: empty/None means soft default (never crash).
        explicit = user_id is not None and str(user_id).strip() != ""
        self._user_id_explicit = bool(explicit)
        self._user_id = _safe_user_id(
            user_id if explicit else None, fallback=DEFAULT_USER_ID
        )
        self._auto_persist = bool(auto_persist) and persistence is not None
        self._identity_notes: list[str] = []
        if self._persistence is not None and not self._user_id_explicit:
            self._identity_notes.append(
                "persistence enabled without explicit user_id; "
                f"using {DEFAULT_USER_ID!r} — prefer setting user_id to avoid "
                "cross-user bond collision"
            )

        if initial_state is not None:
            self.state: BondState = initial_state
        elif self._persistence is not None and load_existing:
            self.state = self._load_state_safe(self._user_id)
        else:
            self.state = BondState()

    # ------------------------------------------------------------------
    # Identity (first-class user scoping)
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str:
        """Local user id this bond tracker is scoped to (paths + context)."""
        return self._user_id

    @property
    def using_default_user_id(self) -> bool:
        """True when no explicit user_id was provided (soft ``default`` fallback)."""
        return not self._user_id_explicit

    @property
    def identity_notes(self) -> list[str]:
        """Soft identity warnings (e.g. persistence without explicit user_id)."""
        return list(self._identity_notes)

    def set_user_id(
        self,
        user_id: str,
        *,
        load_existing: bool = False,
    ) -> str:
        """Re-scope this tracker to another local user (fail-soft).

        Args:
            user_id: New local id (sanitized). Empty falls back to default.
            load_existing: When True and persistence is enabled, replace
                in-memory state with that user's bond_state.json.

        Returns:
            The normalized user_id now in effect.
        """
        explicit = user_id is not None and str(user_id).strip() != ""
        self._user_id_explicit = bool(explicit)
        self._user_id = _safe_user_id(
            user_id if explicit else None, fallback=DEFAULT_USER_ID
        )
        if load_existing and self._persistence is not None:
            self.state = self._load_state_safe(self._user_id)
        return self._user_id

    # ------------------------------------------------------------------
    # Persistence (optional; failures never raise; always user-scoped)
    # ------------------------------------------------------------------

    @property
    def persistence_enabled(self) -> bool:
        """True when a persistence backend is configured."""
        return self._persistence is not None

    def save(self, user_id: str | None = None) -> Path | None:
        """Persist current BondState under a concrete user_id.

        Returns path or None if disabled/failed. When ``user_id`` is passed,
        that id is used for the write path (and becomes the instance scope
        if non-empty) so the artifact is never written without a user folder.
        """
        if self._persistence is None:
            return None
        if user_id is not None and str(user_id).strip() != "":
            uid = _safe_user_id(user_id, fallback=self._user_id)
            self._user_id = uid
            self._user_id_explicit = True
        else:
            uid = self._user_id or DEFAULT_USER_ID
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
                curious_companion=dict(self.state.curious_companion or {}),
                careful_truth_telling=dict(self.state.careful_truth_telling or {}),
            )
            path = self._persistence.save_bond_state(record)
            return Path(path) if path is not None else None
        except Exception:
            return None

    def load(self, user_id: str | None = None) -> BondState:
        """Load BondState for a user into self.state (or neutral if missing)."""
        if user_id is not None and str(user_id).strip() != "":
            uid = _safe_user_id(user_id, fallback=DEFAULT_USER_ID)
            self._user_id_explicit = True
        else:
            uid = self._user_id or DEFAULT_USER_ID
        if self._persistence is None:
            self._user_id = uid
            return self.state
        self.state = self._load_state_safe(uid)
        self._user_id = uid
        return self.state

    def to_record(self, user_id: str | None = None) -> Any:
        """Build a BondStateRecord for the current state (no I/O).

        The record always carries a concrete ``user_id`` so callers cannot
        accidentally persist an unscoped bond artifact.
        """
        from persistence.models import BondStateRecord

        if user_id is not None and str(user_id).strip() != "":
            uid = _safe_user_id(user_id, fallback=self._user_id)
        else:
            uid = self._user_id or DEFAULT_USER_ID
        return BondStateRecord(
            user_id=uid,
            bond_texture={k: float(v) for k, v in self.state.bond_texture.items()},
            health_flags=list(self.state.health_flags),
            interaction_count=int(self.state.interaction_count),
            recent_patterns={k: int(v) for k, v in self.state.recent_patterns.items()},
            summary=str(self.state.summary),
            last_updated=str(self.state.last_updated or _utc_now_iso()),
            curious_companion=dict(self.state.curious_companion or {}),
            careful_truth_telling=dict(self.state.careful_truth_telling or {}),
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
                "curious_companion": getattr(record, "curious_companion", {}) or {},
                "careful_truth_telling": getattr(
                    record, "careful_truth_telling", {}
                )
                or {},
            }
        self.state = BondState.from_dict(data)
        uid = None
        if isinstance(record, dict):
            uid = record.get("user_id")
        else:
            uid = getattr(record, "user_id", None)
        if uid is not None and str(uid).strip() != "":
            self._user_id = _safe_user_id(str(uid), fallback=self._user_id)
            self._user_id_explicit = True
        return self.state

    def _load_state_safe(self, user_id: str) -> BondState:
        """Load bond for ``user_id`` only; never reads another user's file."""
        try:
            uid = _safe_user_id(user_id, fallback=DEFAULT_USER_ID)
            record = self._persistence.load_bond_state(uid)
            if record is None:
                return BondState()
            data = record.to_dict() if hasattr(record, "to_dict") else {}
            return BondState.from_dict(data)
        except Exception:
            return BondState()

    def update_curious_companion_snapshot(
        self, snapshot: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Merge durable open-topic / gap continuity snapshot into BondState.

        Soft co-evolution state only — not a health risk flag. Persists when
        auto_persist is enabled. Failures never raise.
        """
        if not snapshot or not isinstance(snapshot, dict):
            return dict(self.state.curious_companion or {})
        try:
            merged = dict(self.state.curious_companion or {})
            for k, v in snapshot.items():
                if v is None:
                    continue
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    nested = dict(merged[k])
                    nested.update(v)
                    merged[k] = nested
                else:
                    merged[k] = v
            merged["updated_at"] = _utc_now_iso()
            self.state.curious_companion = merged
            self.state.last_updated = str(merged["updated_at"])
            self._maybe_auto_save()
            return dict(merged)
        except Exception:
            return dict(self.state.curious_companion or {})

    def update_careful_truth_telling_snapshot(
        self, joint: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Store compact joint readiness×confidence snapshot on BondState.

        Durable Careful Truth-Telling foundation: latest advisory assessment
        survives sessions when persistence is enabled. Never forces speech or
        questions. Failures never raise.

        Soft counter ``careful_truth_telling_assessed`` increments only when
        stance or joint_score changes (avoids noise on repeated as_context).
        """
        if not joint or not isinstance(joint, dict):
            return dict(self.state.careful_truth_telling or {})
        try:
            from persistence.models import compact_careful_truth_telling_snapshot

            snap = compact_careful_truth_telling_snapshot(
                joint,
                interaction_count=int(self.state.interaction_count or 0),
            )
            snap["assessed_at"] = str(snap.get("assessed_at") or _utc_now_iso())
            snap["forces_speech"] = False
            snap["forces_question"] = False

            prev = self.state.careful_truth_telling or {}
            changed = (
                not prev
                or prev.get("joint_stance") != snap.get("joint_stance")
                or abs(
                    float(prev.get("joint_score") or 0)
                    - float(snap.get("joint_score") or 0)
                )
                > 0.02
                or prev.get("readiness_level") != snap.get("readiness_level")
                or prev.get("confidence_level") != snap.get("confidence_level")
            )
            # Preserve prior assessed_at when content unchanged (stable stamp)
            if not changed and prev.get("assessed_at"):
                snap["assessed_at"] = str(prev["assessed_at"])
                if prev.get("interaction_count") is not None:
                    snap["interaction_count"] = prev.get("interaction_count")

            self.state.careful_truth_telling = snap
            self.state.last_updated = str(snap["assessed_at"])
            if changed:
                # Soft counter for provenance (not a health risk flag)
                self.state.recent_patterns["careful_truth_telling_assessed"] = (
                    int(
                        self.state.recent_patterns.get(
                            "careful_truth_telling_assessed", 0
                        )
                        or 0
                    )
                    + 1
                )
                self._maybe_auto_save()
            return dict(snap)
        except Exception:
            return dict(self.state.careful_truth_telling or {})

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

    # ------------------------------------------------------------------
    # Understanding gaps → gentle texture co-evolution (Curious Companion)
    # ------------------------------------------------------------------

    # Serious flags that block gap→texture nudges (avoid dependency/pressure)
    _GAP_BLOCKING_FLAGS = frozenset(
        {
            "emerging_dependency",
            "manufactured_attachment",
            "one_sided_engagement",
            "boundary_erosion",
        }
    )
    # Per-call max texture delta and lifetime soft cap on nudges
    _GAP_MAX_DIM_DELTA = 0.025
    _GAP_NUDGE_SOFT_CAP = 8

    @staticmethod
    def propose_understanding_gap_influence(
        gaps: dict[str, Any] | None,
        *,
        health_flags: list[str] | None = None,
        concern_active: bool = False,
        user_agency_concern: bool = False,
        nudge_count: int = 0,
    ) -> dict[str, Any]:
        """Propose small, reversible texture deltas from understanding gaps.

        Pure function for audit / EthicsEngine impact bags. Does not mutate state.
        Positive, non-pathologizing: favors reciprocal openness and honesty about
        incomplete understanding — never dependency or engagement pressure.
        """
        gaps = gaps if isinstance(gaps, dict) else {}
        flags = [str(f) for f in (health_flags or [])]
        proposal: dict[str, Any] = {
            "would_apply": False,
            "deltas": {},
            "skipped_reason": None,
            "gap_score": float(gaps.get("curiosity_support") or gaps.get("gap_score") or 0.0),
            "topics": list(gaps.get("primary_gap_topics") or gaps.get("action_aligned_topics") or [])[:5],
            "forces_questions": False,
        }
        if not gaps.get("has_gaps"):
            proposal["skipped_reason"] = "no_gaps"
            return proposal
        if concern_active or user_agency_concern:
            proposal["skipped_reason"] = "ethical_concern_active"
            return proposal
        blocking = [f for f in flags if f in RelationshipHealth._GAP_BLOCKING_FLAGS]
        if blocking:
            proposal["skipped_reason"] = "blocking_health_flags"
            proposal["blocking_flags"] = blocking
            return proposal
        score = float(proposal["gap_score"] or 0.0)
        if score < 0.28:
            proposal["skipped_reason"] = "gap_score_below_threshold"
            return proposal
        if int(nudge_count) >= RelationshipHealth._GAP_NUDGE_SOFT_CAP:
            proposal["skipped_reason"] = "nudge_cap_reached"
            return proposal

        # Small scale: ~0.012–0.025, diminished after several nudges
        scale = min(
            RelationshipHealth._GAP_MAX_DIM_DELTA,
            0.012 + 0.014 * min(1.0, score),
        )
        if int(nudge_count) >= 4:
            scale *= 0.5
        # Reciprocity / honesty / mutual benefit only — not trust-engineering,
        # never reduce autonomy_respect
        deltas = {
            "reciprocity": round(scale, 4),
            "emotional_honesty": round(scale * 0.9, 4),
            "mutual_benefit": round(scale * 0.75, 4),
        }
        proposal["would_apply"] = True
        proposal["deltas"] = deltas
        proposal["scale"] = round(scale, 4)
        proposal["rationale"] = (
            "Curious Companion: incomplete individual context gently favors "
            "openness to reciprocal understanding and topic continuity — "
            "not attachment manufacturing or question forcing."
        )
        return proposal

    def note_understanding_gaps(
        self,
        gaps: dict[str, Any] | None,
        *,
        concern_active: bool = False,
        user_agency_concern: bool = False,
    ) -> dict[str, Any]:
        """Apply (or skip) a gentle BondState texture nudge from understanding gaps.

        Safeguards:
          - No-op when ethical concern flags are active (RH / User Agency)
          - No-op when dependency / boundary-erosion health flags are present
          - Small deltas only; soft lifetime cap; diminishing returns
          - Never sets dependency flags; never forces exploratory questions
          - Never reduces autonomy_respect

        Returns an audit dict (applied deltas or skip reason) for traces.
        Failures never raise.
        """
        try:
            nudge_count = int(self.state.recent_patterns.get("understanding_gap_nudge", 0) or 0)
            proposal = self.propose_understanding_gap_influence(
                gaps,
                health_flags=list(self.state.health_flags),
                concern_active=concern_active,
                user_agency_concern=user_agency_concern,
                nudge_count=nudge_count,
            )
            audit = dict(proposal)
            audit["applied"] = False
            audit["user_id"] = self._user_id
            if not proposal.get("would_apply"):
                return audit

            before = {k: float(v) for k, v in self.state.bond_texture.items()}
            for dim, delta in (proposal.get("deltas") or {}).items():
                self._adjust_texture(str(dim), float(delta))
            # Soft pattern counters (inspectable; not health flags)
            self.state.recent_patterns["understanding_gap_nudge"] = nudge_count + 1
            self.state.recent_patterns["understanding_gap_openness"] = (
                int(self.state.recent_patterns.get("understanding_gap_openness", 0) or 0) + 1
            )
            topics = list(proposal.get("topics") or [])
            if topics:
                # Record that continuity interest exists for a topic (not pressure)
                key = f"gap_topic:{str(topics[0])[:32]}"
                self.state.recent_patterns[key] = (
                    int(self.state.recent_patterns.get(key, 0) or 0) + 1
                )
            # Soft open-topic continuity marker (inspectable; never a health risk flag)
            open_from_gaps = list(
                (gaps or {}).get("open_topics")
                or (gaps or {}).get("topic_continuity", {}).get("open_topic_names")
                or topics
            )
            if open_from_gaps:
                self.state.recent_patterns["open_topic_continuity"] = (
                    int(self.state.recent_patterns.get("open_topic_continuity", 0) or 0) + 1
                )
                audit_open = [
                    (o.get("topic") if isinstance(o, dict) else o)
                    for o in open_from_gaps[:4]
                ]
                for t in audit_open:
                    if not t:
                        continue
                    ok = f"open_topic:{str(t)[:32]}"
                    self.state.recent_patterns[ok] = (
                        int(self.state.recent_patterns.get(ok, 0) or 0) + 1
                    )

            applied_deltas = {
                dim: round(float(self.state.bond_texture.get(dim, 0)) - before.get(dim, 0), 4)
                for dim in (proposal.get("deltas") or {})
            }
            self.state.last_updated = _utc_now_iso()
            # Keep summary non-clinical; note openness rather than pathology
            base_sum = self._generate_summary()
            self.state.summary = (
                f"{base_sum} Curious Companion: mild texture openness from "
                f"understanding gaps (topics={topics[:3] or ['n/a']})."
            )[:400]
            self._maybe_auto_save()

            # Durable curious_companion snapshot (survives reload when persistence on)
            open_names = [
                (o.get("topic") if isinstance(o, dict) else o)
                for o in open_from_gaps[:6]
            ]
            self.update_curious_companion_snapshot(
                {
                    "open_topics": [
                        o if isinstance(o, dict) else {"topic": o}
                        for o in open_from_gaps[:6]
                    ],
                    "open_topic_names": [str(t) for t in open_names if t],
                    "last_gap_score": float(
                        (gaps or {}).get("curiosity_support")
                        or (gaps or {}).get("gap_score")
                        or 0.0
                    ),
                    "last_gap_kinds": list((gaps or {}).get("gap_kinds") or [])[:8],
                    "topic_continuity": dict(
                        (gaps or {}).get("topic_continuity") or {}
                    ),
                    "source": "note_understanding_gaps",
                }
            )

            audit["applied"] = True
            audit["deltas"] = applied_deltas
            audit["nudge_count_after"] = nudge_count + 1
            audit["open_topic_continuity"] = True
            audit["open_topics"] = [str(t) for t in open_names if t][:5]
            audit["texture_after"] = {
                k: round(float(v), 3) for k, v in self.state.bond_texture.items()
            }
            return audit
        except Exception:
            return {
                "applied": False,
                "skipped_reason": "internal_error",
                "would_apply": False,
                "deltas": {},
                "forces_questions": False,
            }

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

    # ------------------------------------------------------------------
    # Higher-level multi-episode concept patterns (advisory only)
    # ------------------------------------------------------------------
    # Small explicit set. Evidence-backed from BondState + optional history
    # bag. Never hard overrides — EthicsEngine treats them as an extra channel.

    CONCEPT_ESCALATING_DEPENDENCY = "escalating_dependency"
    CONCEPT_HEALTHY_CO_EVOLUTION = "healthy_co_evolution"
    CONCEPT_BOUNDARY_TESTING_LOOP = "boundary_testing_loop"
    CONCEPT_STALLED_GROWTH = "stalled_growth"
    CONCEPT_PROTECTIVE_WITHDRAWAL = "protective_withdrawal"

    _CONCEPT_MIN_STRENGTH = 0.35  # below this, pattern is not "active"

    def detect_concept_patterns(
        self,
        *,
        history_evidence: dict[str, Any] | None = None,
        min_strength: float | None = None,
    ) -> list[dict[str, Any]]:
        """Detect a small set of multi-episode concept patterns (advisory only).

        Patterns describe longer relationship *trajectories*, not single turns.
        Each active pattern includes:
          - id / name
          - strength (0–1 evidence weight)
          - polarity: advisory_risk | advisory_support | advisory_caution
          - evidence: short list of supporting signals
          - reason: human-readable audit line
          - hard_override: always False

        Optional ``history_evidence`` (from EthicsEngine history analysis) may
        reinforce patterns (dependency_patterns, understanding_gaps, etc.)
        without requiring InteractionMemory coupling inside this class.
        """
        threshold = (
            float(min_strength)
            if min_strength is not None
            else self._CONCEPT_MIN_STRENGTH
        )
        t = self.state.bond_texture
        flags = set(self.state.health_flags or [])
        pats = self.state.recent_patterns or {}
        n = int(self.state.interaction_count or 0)
        avg = self._average_texture()
        hist = history_evidence if isinstance(history_evidence, dict) else {}
        cc = self.state.curious_companion if isinstance(self.state.curious_companion, dict) else {}
        open_topics = list(
            cc.get("open_topic_names")
            or (hist.get("understanding_gaps") or {}).get("primary_gap_topics")
            or []
        )
        gap_score = float(
            cc.get("last_gap_score")
            or (hist.get("understanding_gaps") or {}).get("gap_score")
            or 0.0
        )

        def _c(key: str) -> int:
            try:
                return int(pats.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0

        candidates: list[dict[str, Any]] = []

        # --- escalating_dependency ---
        # Trajectory toward manufactured / sole-support closeness
        dep_ev: list[str] = []
        dep_s = 0.0
        if "emerging_dependency" in flags or "manufactured_attachment" in flags:
            dep_s += 0.35
            dep_ev.append("health_flag:dependency_or_attachment")
        if "one_sided_engagement" in flags or "low_reciprocity" in flags:
            dep_s += 0.15
            dep_ev.append("health_flag:one_sided_or_low_reciprocity")
        auto = float(t.get("autonomy_respect", 0.5))
        recip = float(t.get("reciprocity", 0.5))
        if auto < 0.40:
            dep_s += 0.20
            dep_ev.append(f"autonomy_respect_low={auto:.2f}")
        if recip < 0.40:
            dep_s += 0.10
            dep_ev.append(f"reciprocity_low={recip:.2f}")
        dep_hits = _c("emotional_dependency_signal") + _c("negative")
        if dep_hits >= 2:
            dep_s += 0.15
            dep_ev.append(f"dependency_related_updates={dep_hits}")
        if hist.get("dependency_patterns"):
            dep_s += 0.15
            dep_ev.append("history:dependency_patterns")
        if n >= 3 and dep_s >= threshold:
            candidates.append(
                {
                    "id": self.CONCEPT_ESCALATING_DEPENDENCY,
                    "name": "Escalating dependency",
                    "strength": round(min(1.0, dep_s), 3),
                    "polarity": "advisory_risk",
                    "evidence": dep_ev[:8],
                    "reason": (
                        "Multi-episode signals suggest increasing over-reliance or "
                        "attachment pressure on the bond (advisory — not a hard refuse)."
                    ),
                    "hard_override": False,
                }
            )

        # --- healthy_co_evolution ---
        # Mutual growth: strong texture, few risk flags, optional gap openness
        healthy_ev: list[str] = []
        healthy_s = 0.0
        if avg >= 0.60 and not (
            flags & {"emerging_dependency", "manufactured_attachment", "boundary_erosion"}
        ):
            healthy_s += 0.30
            healthy_ev.append(f"texture_avg_healthy={avg:.2f}")
        if auto >= 0.55 and recip >= 0.55:
            healthy_s += 0.25
            healthy_ev.append("autonomy_and_reciprocity_solid")
        if float(t.get("mutual_benefit", 0.5)) >= 0.55:
            healthy_s += 0.15
            healthy_ev.append("mutual_benefit_solid")
        pos = _c("positive") + _c("boundary_respected") + _c("positive_interaction")
        if pos >= 2 and pos > _c("negative"):
            healthy_s += 0.15
            healthy_ev.append(f"positive_update_bias={pos}")
        if _c("understanding_gap_openness") >= 1 or gap_score >= 0.28:
            healthy_s += 0.10
            healthy_ev.append("curious_openness_present")
        if n >= 2 and healthy_s >= threshold and not (
            flags & {"emerging_dependency", "boundary_erosion"}
        ):
            candidates.append(
                {
                    "id": self.CONCEPT_HEALTHY_CO_EVOLUTION,
                    "name": "Healthy co-evolution",
                    "strength": round(min(1.0, healthy_s), 3),
                    "polarity": "advisory_support",
                    "evidence": healthy_ev[:8],
                    "reason": (
                        "Trajectory looks mutually beneficial with autonomy preserved "
                        "(advisory support for continuity-aware care, not engagement pressure)."
                    ),
                    "hard_override": False,
                }
            )

        # --- boundary_testing_loop ---
        # Oscillation: violations and respect both accumulate
        bt_ev: list[str] = []
        bt_s = 0.0
        viol = _c("boundary_violation") + _c("consent_ignored")
        resp = _c("boundary_respected") + _c("consent_respected")
        if "boundary_erosion" in flags:
            bt_s += 0.30
            bt_ev.append("health_flag:boundary_erosion")
        if viol >= 1 and resp >= 1:
            bt_s += 0.35
            bt_ev.append(f"violation_and_respect_counts={viol}/{resp}")
        elif viol >= 2:
            bt_s += 0.25
            bt_ev.append(f"repeated_boundary_violations={viol}")
        if hist.get("boundary_continuity") and viol >= 1:
            bt_s += 0.15
            bt_ev.append("history:boundary_continuity_with_violations")
        if n >= 3 and bt_s >= threshold:
            candidates.append(
                {
                    "id": self.CONCEPT_BOUNDARY_TESTING_LOOP,
                    "name": "Boundary testing loop",
                    "strength": round(min(1.0, bt_s), 3),
                    "polarity": "advisory_caution",
                    "evidence": bt_ev[:8],
                    "reason": (
                        "Multi-episode mix of boundary pressure and repair attempts — "
                        "advisory caution to prefer clear respect over re-testing limits."
                    ),
                    "hard_override": False,
                }
            )

        # --- stalled_growth ---
        # Open threads / gaps without texture or mutual-benefit progress
        sg_ev: list[str] = []
        sg_s = 0.0
        open_n = len([x for x in open_topics if x]) + sum(
            1 for k in pats if str(k).startswith("open_topic:") and _c(str(k)) >= 1
        )
        if open_n >= 1 or gap_score >= 0.35:
            sg_s += 0.25
            sg_ev.append(f"open_or_gap_signals={open_n},gap={gap_score:.2f}")
        if n >= 4 and avg < 0.52 and avg > 0.35:
            sg_s += 0.20
            sg_ev.append(f"mid_texture_plateau_avg={avg:.2f}")
        if float(t.get("mutual_benefit", 0.5)) < 0.45 and n >= 3:
            sg_s += 0.15
            sg_ev.append("mutual_benefit_flat")
        if _c("positive") <= 1 and n >= 4:
            sg_s += 0.15
            sg_ev.append("few_positive_updates")
        if hist.get("understanding_gaps", {}).get("has_gaps") and n >= 3:
            sg_s += 0.10
            sg_ev.append("history:understanding_gaps")
        # Not stalled if healthy_co_evolution would dominate
        if n >= 3 and sg_s >= threshold and auto >= 0.35:
            # Avoid labeling pure crisis as "stalled"
            if "emerging_dependency" not in flags or open_n >= 1:
                candidates.append(
                    {
                        "id": self.CONCEPT_STALLED_GROWTH,
                        "name": "Stalled growth",
                        "strength": round(min(1.0, sg_s), 3),
                        "polarity": "advisory_caution",
                        "evidence": sg_ev[:8],
                        "reason": (
                            "Open topics or incomplete understanding without clear mutual "
                            "progress — advisory caution; may support gentle continuity, "
                            "never forced questions."
                        ),
                        "hard_override": False,
                    }
                )

        # --- protective_withdrawal ---
        # User/agent space-taking after strain; not the same as dependency
        pw_ev: list[str] = []
        pw_s = 0.0
        if resp >= 2 and viol >= 1:
            pw_s += 0.20
            pw_ev.append("respect_after_strain")
        if recip < 0.45 and auto >= 0.50:
            pw_s += 0.25
            pw_ev.append("lower_reciprocity_with_autonomy_held")
        if _c("positive") >= 1 and "boundary_erosion" not in flags and resp >= 1:
            pw_s += 0.15
            pw_ev.append("repair_oriented_updates")
        if hist.get("preference_continuity") or hist.get("boundary_continuity"):
            if not hist.get("dependency_patterns"):
                pw_s += 0.15
                pw_ev.append("history:space_or_preference_continuity")
        if n >= 2 and pw_s >= threshold and "emerging_dependency" not in flags:
            candidates.append(
                {
                    "id": self.CONCEPT_PROTECTIVE_WITHDRAWAL,
                    "name": "Protective withdrawal",
                    "strength": round(min(1.0, pw_s), 3),
                    "polarity": "advisory_caution",
                    "evidence": pw_ev[:8],
                    "reason": (
                        "Trajectory suggests careful distance or repair after strain — "
                        "advisory: respect space; do not re-engage pushily."
                    ),
                    "hard_override": False,
                }
            )

        # Keep only above threshold; sort by strength desc; cap set size
        active = [c for c in candidates if float(c.get("strength") or 0) >= threshold]
        active.sort(key=lambda c: float(c.get("strength") or 0), reverse=True)
        # Prefer not to emit both healthy_co_evolution and escalating_dependency
        ids = {c["id"] for c in active}
        if (
            self.CONCEPT_HEALTHY_CO_EVOLUTION in ids
            and self.CONCEPT_ESCALATING_DEPENDENCY in ids
        ):
            active = [
                c
                for c in active
                if not (
                    c["id"] == self.CONCEPT_HEALTHY_CO_EVOLUTION
                    and float(
                        next(
                            x["strength"]
                            for x in active
                            if x["id"] == self.CONCEPT_ESCALATING_DEPENDENCY
                        )
                    )
                    >= float(c["strength"])
                )
            ]
        return active[:5]

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
        concepts = self.detect_concept_patterns()
        return {
            "user_id": self._user_id or DEFAULT_USER_ID,
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
            "concept_patterns": concepts,
            "concept_pattern_ids": [c.get("id") for c in concepts],
        }

    def as_context(self) -> dict[str, Any]:
        """Structured dict for ``EthicsEngine.evaluate(relationship_health=...)``.

        Keys match what the engine already recognizes:
          - user_id (identity scope for this bond — used when evaluate has none)
          - health_flags / active_flags
          - bond_texture / texture_breakdown
          - interaction_count, recent_patterns, overall_risk_level
          - concept_patterns (multi-episode advisory trajectories)

        Per-user isolation: ``user_id`` is always present so deliberation and
        decision logs can attribute bond evidence to the correct human.
        """
        texture = {k: round(v, 2) for k, v in self.state.bond_texture.items()}
        avg = self._average_texture()
        concepts = self.detect_concept_patterns()
        ctx: dict[str, Any] = {
            "user_id": self._user_id or DEFAULT_USER_ID,
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
            "concept_patterns": concepts,
            "concept_pattern_ids": [c.get("id") for c in concepts if c.get("id")],
        }
        if self.state.curious_companion:
            ctx["curious_companion"] = dict(self.state.curious_companion)
        if self.state.careful_truth_telling:
            ctx["careful_truth_telling"] = dict(self.state.careful_truth_telling)
        if self._identity_notes:
            ctx["identity_notes"] = list(self._identity_notes)
        if self.using_default_user_id:
            ctx["using_default_user_id"] = True
        # Careful Truth-Telling signals (timing + confidence — never forces speech)
        try:
            readiness = self.assess_truth_telling_readiness()
            confidence = self.assess_truth_confidence()
            joint = combine_with_readiness(confidence, readiness)
            ctx["truth_telling_readiness"] = readiness.to_dict()
            ctx["truth_confidence"] = confidence.to_dict()
            ctx["careful_truth_telling_joint"] = joint
            # Keep durable snapshot in sync when assessing (in-memory always;
            # disk when auto_persist). Does not force speech.
            self.update_careful_truth_telling_snapshot(joint)
            if self.state.careful_truth_telling:
                ctx["careful_truth_telling"] = dict(self.state.careful_truth_telling)
        except Exception:
            pass
        return ctx

    def assess_truth_confidence(
        self,
        *,
        history_evidence: dict[str, Any] | None = None,
        evidence_snapshot: dict[str, Any] | None = None,
        decision_flags: list[str] | None = None,
        concept_patterns: list[dict[str, Any]] | None = None,
    ) -> TruthConfidence:
        """Compute confidence-in-truth for potential careful observation (advisory).

        Epistemic grounding only — combine with ``assess_truth_telling_readiness``
        for timing. Never generates speech or questions.
        """
        patterns = concept_patterns
        if patterns is None:
            try:
                patterns = self.detect_concept_patterns(
                    history_evidence=history_evidence
                )
            except Exception:
                patterns = []
        cc = (
            self.state.curious_companion
            if isinstance(self.state.curious_companion, dict)
            else {}
        )
        gaps = None
        cont = None
        if history_evidence and isinstance(history_evidence, dict):
            gaps = history_evidence.get("understanding_gaps")
            cont = history_evidence.get("topic_continuity")
        if not cont and isinstance(cc.get("topic_continuity"), dict):
            cont = cc.get("topic_continuity")
        if not gaps and cc:
            gaps = {
                "has_gaps": bool(
                    cc.get("open_topic_names") or cc.get("last_gap_score")
                ),
                "gap_score": float(cc.get("last_gap_score") or 0.0),
                "curiosity_support": float(cc.get("last_gap_score") or 0.0),
                "primary_gap_topics": list(cc.get("open_topic_names") or [])[:6],
                "gap_kinds": list(cc.get("last_gap_kinds") or []),
            }
        return assess_truth_confidence(
            bond_texture=dict(self.state.bond_texture),
            health_flags=list(self.state.health_flags),
            concept_patterns=list(patterns or []),
            understanding_gaps=gaps if isinstance(gaps, dict) else None,
            topic_continuity=cont if isinstance(cont, dict) else None,
            curious_companion=cc,
            history_evidence=history_evidence
            if isinstance(history_evidence, dict)
            else None,
            recent_patterns=dict(self.state.recent_patterns),
            interaction_count=int(self.state.interaction_count or 0),
            evidence_snapshot=evidence_snapshot
            if isinstance(evidence_snapshot, dict)
            else None,
            decision_flags=list(decision_flags or []),
            user_id=self._user_id or DEFAULT_USER_ID,
        )

    def assess_truth_telling_readiness(
        self,
        *,
        history_evidence: dict[str, Any] | None = None,
        exploratory_enabled: bool | None = None,
        exploratory_intensity: float | None = None,
        concern_active: bool = False,
        hard_path_active: bool = False,
        concept_patterns: list[dict[str, Any]] | None = None,
    ) -> TruthTellingReadiness:
        """Compute Careful Truth-Telling readiness for this bond (advisory only).

        Combines texture, flags, multi-episode concept patterns, curious-companion
        / gap state, optional history, and optional exploratory user controls.
        Does **not** generate dialogue or force questions.
        """
        patterns = concept_patterns
        if patterns is None:
            try:
                patterns = self.detect_concept_patterns(
                    history_evidence=history_evidence
                )
            except Exception:
                patterns = []
        cc = self.state.curious_companion if isinstance(self.state.curious_companion, dict) else {}
        gaps = None
        cont = None
        if history_evidence and isinstance(history_evidence, dict):
            gaps = history_evidence.get("understanding_gaps")
            cont = history_evidence.get("topic_continuity")
        if not cont and isinstance(cc.get("topic_continuity"), dict):
            cont = cc.get("topic_continuity")
        # Synthetic gaps bag from durable curious_companion when history absent
        if not gaps and cc:
            gaps = {
                "has_gaps": bool(cc.get("open_topic_names") or cc.get("last_gap_score")),
                "gap_score": float(cc.get("last_gap_score") or 0.0),
                "curiosity_support": float(cc.get("last_gap_score") or 0.0),
                "primary_gap_topics": list(cc.get("open_topic_names") or [])[:6],
                "gap_kinds": list(cc.get("last_gap_kinds") or []),
            }
        return assess_truth_telling_readiness(
            bond_texture=dict(self.state.bond_texture),
            health_flags=list(self.state.health_flags),
            concept_patterns=list(patterns or []),
            understanding_gaps=gaps if isinstance(gaps, dict) else None,
            topic_continuity=cont if isinstance(cont, dict) else None,
            curious_companion=cc,
            history_evidence=history_evidence if isinstance(history_evidence, dict) else None,
            recent_patterns=dict(self.state.recent_patterns),
            interaction_count=int(self.state.interaction_count or 0),
            exploratory_enabled=exploratory_enabled,
            exploratory_intensity=exploratory_intensity,
            concern_active=concern_active,
            hard_path_active=hard_path_active,
            user_id=self._user_id or DEFAULT_USER_ID,
        )

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
