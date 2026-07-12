"""
models.py
=========

Serializable records for local persistence.

These are plain dataclasses with ``to_dict`` / ``from_dict`` so they can be
stored as JSON without a heavy ORM. They intentionally mirror concepts already
used by EthicsEngine and RelationshipHealth so integration stays thin.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserBaseline:
    """Per-user baseline communication / relational style snapshot.

    Foundation for future Per-User Baseline Memory. Fields start minimal and
    may be sparsely populated until baseline estimation is implemented.
    """

    user_id: str
    # Communication / style dimensions (0.0–1.0 or free descriptive floats)
    communication_patterns: dict[str, Any] = field(default_factory=dict)
    """e.g. preferred_length, directness, question_rate."""

    emotional_tone_range: dict[str, float] = field(default_factory=dict)
    """e.g. min/max/mean observed valence or calm–intense range."""

    topic_continuity: dict[str, Any] = field(default_factory=dict)
    """e.g. recurring themes, continuity scores (non-sensitive summaries)."""

    playfulness_level: float = 0.5
    """0.0 = highly serious default; 1.0 = highly playful."""

    notes: str = ""
    """Optional free-text baseline notes (privacy-filtered on write)."""

    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, user_id: str | None = None) -> UserBaseline:
        if not data:
            return cls(user_id=user_id or "default")
        return cls(
            user_id=str(data.get("user_id") or user_id or "default"),
            communication_patterns=dict(data.get("communication_patterns") or {}),
            emotional_tone_range={
                k: float(v) for k, v in (data.get("emotional_tone_range") or {}).items()
            },
            topic_continuity=dict(data.get("topic_continuity") or {}),
            playfulness_level=float(data.get("playfulness_level", 0.5)),
            notes=str(data.get("notes") or ""),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class BondStateRecord:
    """Persisted relationship health / bond texture state.

    Compatible with keys expected by EthicsEngine (bond_texture, health_flags)
    and RelationshipHealth.as_context().
    """

    user_id: str
    bond_texture: dict[str, float] = field(
        default_factory=lambda: {
            "trust": 0.5,
            "reciprocity": 0.5,
            "autonomy_respect": 0.5,
            "emotional_honesty": 0.5,
            "mutual_benefit": 0.5,
        }
    )
    health_flags: list[str] = field(default_factory=list)
    interaction_count: int = 0
    recent_patterns: dict[str, int] = field(default_factory=dict)
    summary: str = "Initial / neutral bond state."
    last_updated: str = field(default_factory=_utc_now_iso)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_ethics_context(self) -> dict[str, Any]:
        """Shape suitable for EthicsEngine.evaluate(relationship_health=...)."""
        texture = {k: round(float(v), 3) for k, v in self.bond_texture.items()}
        return {
            "health_flags": list(self.health_flags),
            "active_flags": list(self.health_flags),
            "bond_texture": texture,
            "texture_breakdown": texture,
            "interaction_count": self.interaction_count,
            "recent_patterns": dict(self.recent_patterns),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, user_id: str | None = None) -> BondStateRecord:
        if not data:
            return cls(user_id=user_id or "default")
        texture_raw = data.get("bond_texture") or data.get("texture_breakdown") or {}
        return cls(
            user_id=str(data.get("user_id") or user_id or "default"),
            bond_texture={k: float(v) for k, v in texture_raw.items()},
            health_flags=list(data.get("health_flags") or data.get("active_flags") or []),
            interaction_count=int(data.get("interaction_count", 0)),
            recent_patterns={
                k: int(v) for k, v in (data.get("recent_patterns") or {}).items()
            },
            summary=str(data.get("summary") or "Initial / neutral bond state."),
            last_updated=str(data.get("last_updated") or _utc_now_iso()),
            schema_version=int(data.get("schema_version", 1)),
        )

    @classmethod
    def from_relationship_health_context(
        cls, user_id: str, ctx: dict[str, Any]
    ) -> BondStateRecord:
        """Build a record from RelationshipHealth.as_context() / evaluate_health()."""
        return cls.from_dict({**ctx, "user_id": user_id}, user_id=user_id)


@dataclass
class DecisionLogRecord:
    """One ethical evaluation record for auditability.

    Aligns with core.ethics_engine.DecisionLog fields so engines can flush
    in-memory logs to disk without reshaping.
    """

    timestamp: str
    ontology_version: str
    proposed_action: str
    context: dict[str, Any] = field(default_factory=dict)
    decision: str = ""
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)
    principles_considered: list[str] = field(default_factory=list)
    user_id: str = "default"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DecisionLogRecord:
        if not data:
            return cls(
                timestamp=_utc_now_iso(),
                ontology_version="unknown",
                proposed_action="",
            )
        return cls(
            timestamp=str(data.get("timestamp") or _utc_now_iso()),
            ontology_version=str(data.get("ontology_version") or "unknown"),
            proposed_action=str(data.get("proposed_action") or ""),
            context=dict(data.get("context") or {}),
            decision=str(data.get("decision") or ""),
            confidence=float(data.get("confidence", 0.0)),
            flags=list(data.get("flags") or []),
            principles_considered=list(data.get("principles_considered") or []),
            user_id=str(data.get("user_id") or "default"),
            schema_version=int(data.get("schema_version", 1)),
        )

    @classmethod
    def from_decision_log(cls, log: Any, *, user_id: str = "default") -> DecisionLogRecord:
        """Convert an EthicsEngine DecisionLog (or duck-typed object) to a record."""
        return cls(
            timestamp=str(getattr(log, "timestamp", _utc_now_iso())),
            ontology_version=str(getattr(log, "ontology_version", "unknown")),
            proposed_action=str(getattr(log, "proposed_action", "")),
            context=dict(getattr(log, "context", {}) or {}),
            decision=str(getattr(log, "decision", "")),
            confidence=float(getattr(log, "confidence", 0.0)),
            flags=list(getattr(log, "flags", []) or []),
            principles_considered=list(getattr(log, "principles_considered", []) or []),
            user_id=user_id,
        )


@dataclass
class UserSettings:
    """User-facing settings and controls (local only)."""

    user_id: str
    # Controls
    memory_enabled: bool = True
    persistence_enabled: bool = True
    share_baseline_with_ethics: bool = True
    retain_decision_logs: bool = True
    max_decision_logs: int = 5_000
    """Soft cap for retained decision log lines (oldest trimmed)."""

    # Preferences (extensible bag for future UI / OpenClaw hooks)
    preferences: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, user_id: str | None = None) -> UserSettings:
        if not data:
            return cls(user_id=user_id or "default")
        return cls(
            user_id=str(data.get("user_id") or user_id or "default"),
            memory_enabled=bool(data.get("memory_enabled", True)),
            persistence_enabled=bool(data.get("persistence_enabled", True)),
            share_baseline_with_ethics=bool(data.get("share_baseline_with_ethics", True)),
            retain_decision_logs=bool(data.get("retain_decision_logs", True)),
            max_decision_logs=int(data.get("max_decision_logs", 5_000)),
            preferences=dict(data.get("preferences") or {}),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            schema_version=int(data.get("schema_version", 1)),
        )
