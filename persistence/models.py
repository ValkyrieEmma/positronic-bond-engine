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


def compact_observation_candidates_snapshot(
    cand_bag: dict[str, Any] | None,
    *,
    interaction_count: int | None = None,
    max_candidates: int = 3,
) -> dict[str, Any]:
    """Build a compact, privacy-safe durable observation-candidate snapshot.

    Stores at most ``max_candidates`` short seeds (id, description, evidence_refs,
    priority, source, linked levels). Always forces_speech/question False.
    Never stores dialogue templates or forced questions.
    """
    bag = cand_bag if isinstance(cand_bag, dict) else {}
    raw_list = bag.get("candidates")
    if raw_list is None and isinstance(bag.get("observation_candidates"), list):
        raw_list = bag.get("observation_candidates")
    if not isinstance(raw_list, list):
        raw_list = []
    gate = bag.get("gate") if isinstance(bag.get("gate"), dict) else {}
    compact_cands: list[dict[str, Any]] = []
    for c in raw_list[: max(0, int(max_candidates))]:
        if not isinstance(c, dict):
            continue
        compact_cands.append(
            {
                "id": str(c.get("id") or "unknown")[:64],
                "description": str(c.get("description") or "")[:200],
                "evidence_refs": [
                    str(x)[:80] for x in (c.get("evidence_refs") or [])
                ][:6],
                "priority": max(0.0, min(1.0, float(c.get("priority") or 0.0))),
                "source": str(c.get("source") or "unknown")[:48],
                "readiness_level": str(c.get("readiness_level") or "low")[:32],
                "confidence_level": str(c.get("confidence_level") or "low")[:32],
                "joint_stance": str(c.get("joint_stance") or "")[:64],
                "forces_speech": False,
                "forces_question": False,
            }
        )
    joint_stance = str(
        bag.get("joint_stance")
        or gate.get("joint_stance")
        or (compact_cands[0].get("joint_stance") if compact_cands else "stay_quiet")
        or "stay_quiet"
    )[:64]
    out: dict[str, Any] = {
        "candidates": compact_cands,
        "count": len(compact_cands),
        "joint_stance": joint_stance,
        "joint_score": float(
            bag.get("joint_score")
            if bag.get("joint_score") is not None
            else gate.get("joint_score") or 0.0
        ),
        "gate_reason": str(gate.get("reason") or bag.get("gate_reason") or "")[:200],
        "allowed_max": int(
            gate.get("allowed_max")
            if gate.get("allowed_max") is not None
            else bag.get("allowed_max")
            if bag.get("allowed_max") is not None
            else len(compact_cands)
        ),
        "assessed_at": str(bag.get("assessed_at") or _utc_now_iso()),
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }
    if interaction_count is not None:
        out["interaction_count"] = int(interaction_count)
    elif bag.get("interaction_count") is not None:
        try:
            out["interaction_count"] = int(bag.get("interaction_count"))
        except (TypeError, ValueError):
            pass
    return out


def compact_careful_truth_telling_snapshot(
    joint: dict[str, Any] | None,
    *,
    interaction_count: int | None = None,
) -> dict[str, Any]:
    """Build a compact, privacy-safe durable joint readiness×confidence bag.

    Stores only levels, scores, stance, short reasons/gates — not full evidence
    lists or free-form dialogue. Always marks forces_speech/question False.
    """
    j = joint if isinstance(joint, dict) else {}
    readiness = j.get("readiness") if isinstance(j.get("readiness"), dict) else {}
    confidence = j.get("confidence") if isinstance(j.get("confidence"), dict) else {}
    # Accept flat or nested joint forms
    out: dict[str, Any] = {
        "joint_score": float(j.get("joint_score") or 0.0),
        "joint_stance": str(j.get("joint_stance") or "stay_quiet")[:64],
        "surface_ok_advisory": bool(j.get("surface_ok_advisory")),
        "readiness_level": str(
            j.get("readiness_level") or readiness.get("level") or "low"
        )[:32],
        "readiness_score": float(
            j.get("readiness_score")
            if j.get("readiness_score") is not None
            else readiness.get("score") or 0.0
        ),
        "confidence_level": str(
            j.get("confidence_level") or confidence.get("level") or "low"
        )[:32],
        "confidence_score": float(
            j.get("confidence_score")
            if j.get("confidence_score") is not None
            else confidence.get("score") or 0.0
        ),
        "reason": str(j.get("reason") or "")[:280],
        "gates": [
            str(g)[:64]
            for g in (
                j.get("gates")
                or readiness.get("gates_applied")
                or []
            )
        ][:8],
        "assessed_at": str(j.get("assessed_at") or _utc_now_iso()),
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }
    if interaction_count is not None:
        out["interaction_count"] = int(interaction_count)
    elif j.get("interaction_count") is not None:
        try:
            out["interaction_count"] = int(j.get("interaction_count"))
        except (TypeError, ValueError):
            pass
    return out


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

    Ownership
    ---------
    Owned by ``BondStateStore`` / RelationshipHealth. Episodic transcripts live
    in ``InteractionMemoryStore`` (interactions.jsonl); this record holds the
    living *relationship model* for one ``user_id``, including soft pattern
    counters (e.g. understanding-gap nudges, open_topic:*).

    ``curious_companion`` is a small durable snapshot of open topics / gap
    continuity so co-evolution survives sessions without storing full episode
    text here (episodes remain InteractionMemory's concern).

    ``careful_truth_telling`` is the latest joint readiness × confidence
    snapshot (advisory only — never forces speech). Compact fields only.

    ``observation_candidates_snapshot`` is the latest compact set of careful
    observation seeds (0–3) the system has already considered — durable across
    sessions, never forces speech/questions.
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
    # Curious Companion durable soft state (open topics / last gap continuity)
    curious_companion: dict[str, Any] = field(default_factory=dict)
    # Careful Truth-Telling joint snapshot (readiness × confidence)
    careful_truth_telling: dict[str, Any] = field(default_factory=dict)
    # Latest observation-candidate seeds (compact, advisory, non-speaking)
    observation_candidates_snapshot: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_ethics_context(self) -> dict[str, Any]:
        """Shape suitable for EthicsEngine.evaluate(relationship_health=...)."""
        texture = {k: round(float(v), 3) for k, v in self.bond_texture.items()}
        ctx: dict[str, Any] = {
            "user_id": self.user_id,
            "health_flags": list(self.health_flags),
            "active_flags": list(self.health_flags),
            "bond_texture": texture,
            "texture_breakdown": texture,
            "interaction_count": self.interaction_count,
            "recent_patterns": dict(self.recent_patterns),
            "summary": self.summary,
        }
        if self.curious_companion:
            ctx["curious_companion"] = dict(self.curious_companion)
        if self.careful_truth_telling:
            ctx["careful_truth_telling"] = dict(self.careful_truth_telling)
            # Convenience mirrors for consumers
            if self.careful_truth_telling.get("readiness_level"):
                ctx.setdefault(
                    "truth_telling_readiness",
                    {
                        "level": self.careful_truth_telling.get("readiness_level"),
                        "score": self.careful_truth_telling.get("readiness_score"),
                    },
                )
            if self.careful_truth_telling.get("confidence_level"):
                ctx.setdefault(
                    "truth_confidence",
                    {
                        "level": self.careful_truth_telling.get("confidence_level"),
                        "score": self.careful_truth_telling.get("confidence_score"),
                    },
                )
        if self.observation_candidates_snapshot:
            ctx["observation_candidates_durable"] = dict(
                self.observation_candidates_snapshot
            )
            # Convenience: candidate list only (clearly durable, not live)
            cands = self.observation_candidates_snapshot.get("candidates")
            if isinstance(cands, list):
                ctx["observation_candidates_durable_list"] = list(cands)
        return ctx

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, user_id: str | None = None) -> BondStateRecord:
        if not data:
            return cls(user_id=user_id or "default")
        texture_raw = data.get("bond_texture") or data.get("texture_breakdown") or {}
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
        ocs = data.get("observation_candidates_snapshot")
        if not isinstance(ocs, dict):
            ocs = {}
        return cls(
            user_id=str(data.get("user_id") or user_id or "default"),
            bond_texture={k: float(v) for k, v in texture_raw.items()},
            health_flags=list(data.get("health_flags") or data.get("active_flags") or []),
            interaction_count=int(data.get("interaction_count", 0)),
            recent_patterns=patterns,
            summary=str(data.get("summary") or "Initial / neutral bond state."),
            last_updated=str(data.get("last_updated") or _utc_now_iso()),
            curious_companion=dict(cc),
            careful_truth_telling=dict(ctt),
            observation_candidates_snapshot=dict(ocs),
            schema_version=int(data.get("schema_version", 4)),
        )

    def set_careful_truth_telling(
        self, snapshot: dict[str, Any] | None
    ) -> "BondStateRecord":
        """Replace durable careful-truth-telling joint snapshot (compact)."""
        if not snapshot or not isinstance(snapshot, dict):
            return self
        self.careful_truth_telling = compact_careful_truth_telling_snapshot(snapshot)
        self.last_updated = str(
            self.careful_truth_telling.get("assessed_at") or _utc_now_iso()
        )
        return self

    def set_observation_candidates_snapshot(
        self, cand_bag: dict[str, Any] | None
    ) -> "BondStateRecord":
        """Replace durable observation-candidate snapshot (compact, non-speaking)."""
        if not cand_bag or not isinstance(cand_bag, dict):
            return self
        self.observation_candidates_snapshot = compact_observation_candidates_snapshot(
            cand_bag, interaction_count=self.interaction_count
        )
        self.last_updated = str(
            self.observation_candidates_snapshot.get("assessed_at") or _utc_now_iso()
        )
        return self

    @classmethod
    def from_relationship_health_context(
        cls, user_id: str, ctx: dict[str, Any]
    ) -> BondStateRecord:
        """Build a record from RelationshipHealth.as_context() / evaluate_health()."""
        return cls.from_dict({**ctx, "user_id": user_id}, user_id=user_id)

    def merge_curious_companion(self, snapshot: dict[str, Any] | None) -> "BondStateRecord":
        """Merge a gap/continuity snapshot (non-destructive; later fields win)."""
        if not snapshot or not isinstance(snapshot, dict):
            return self
        merged = dict(self.curious_companion or {})
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
        self.curious_companion = merged
        self.last_updated = str(merged["updated_at"])
        return self


@dataclass
class DecisionLogRecord:
    """One ethical evaluation record for auditability and later provenance.

    Aligns with core.ethics_engine.DecisionLog fields so engines can flush
    in-memory logs to disk without reshaping.

    Ownership
    ---------
    Owned by ``DecisionLogStore``. Does not store full episodic memory (that is
    InteractionMemoryStore). Optional ``evidence_snapshot`` holds compact
    understanding-gap / topic-continuity / flag provenance so retrospective
    correction is feasible without replaying full context bags.
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
    # Compact provenance for future queued audits / retrospective correction
    evidence_snapshot: dict[str, Any] = field(default_factory=dict)
    """e.g. understanding_gaps, topic_continuity, scoped_user_id, decision hints."""
    schema_version: int = 2

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
        snap = data.get("evidence_snapshot")
        if not isinstance(snap, dict):
            # Backward-compatible: lift nested keys from legacy rows if present
            snap = {}
            for k in ("understanding_gaps", "topic_continuity", "gap_texture_influence"):
                if isinstance(data.get(k), dict):
                    snap[k] = data[k]
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
            evidence_snapshot=dict(snap),
            schema_version=int(data.get("schema_version", 2)),
        )

    @classmethod
    def from_decision_log(
        cls,
        log: Any,
        *,
        user_id: str = "default",
        evidence_snapshot: dict[str, Any] | None = None,
    ) -> DecisionLogRecord:
        """Convert an EthicsEngine DecisionLog (or duck-typed object) to a record.

        Prefers ``log.user_id`` (then context user_id) so in-memory identity
        scope is preserved on disk (per-user isolation). The ``user_id`` kwarg
        is the fallback when the log carries no identity.
        """
        log_uid = getattr(log, "user_id", None)
        if not log_uid:
            ctx = getattr(log, "context", None)
            if isinstance(ctx, dict):
                log_uid = ctx.get("user_id") or ctx.get("user")
        resolved = str(log_uid or user_id or "default")
        snap = evidence_snapshot
        if snap is None:
            snap = getattr(log, "evidence_snapshot", None)
        if not isinstance(snap, dict):
            snap = {}
        return cls(
            timestamp=str(getattr(log, "timestamp", _utc_now_iso())),
            ontology_version=str(getattr(log, "ontology_version", "unknown")),
            proposed_action=str(getattr(log, "proposed_action", "")),
            context=dict(getattr(log, "context", {}) or {}),
            decision=str(getattr(log, "decision", "")),
            confidence=float(getattr(log, "confidence", 0.0)),
            flags=list(getattr(log, "flags", []) or []),
            principles_considered=list(getattr(log, "principles_considered", []) or []),
            user_id=resolved,
            evidence_snapshot=dict(snap),
        )

    @staticmethod
    def compact_evidence_from_impact(
        relationship_impact: dict[str, Any] | None,
        *,
        flags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a small provenance bag from EthicalStance.relationship_impact.

        Designed for DecisionLog persistence — enough structure for later
        retrospective correction, not a full deliberation dump.
        """
        impact = relationship_impact if isinstance(relationship_impact, dict) else {}
        snap: dict[str, Any] = {
            "captured_at": _utc_now_iso(),
            "scoped_user_id": impact.get("scoped_user_id"),
            "flags_sample": list(flags or [])[:24],
        }
        for key in (
            "understanding_gaps",
            "topic_continuity",
            "gap_texture_influence",
            "action_bond_polarity",
        ):
            val = impact.get(key)
            if isinstance(val, dict) and val:
                # Shallow copy; privacy filter will scrub free text on write
                snap[key] = dict(val)
        # Drop oversized nested lists of examples (keep structure, trim text later)
        ug = snap.get("understanding_gaps")
        if isinstance(ug, dict):
            for ek in ("uncertainty_examples", "disclosure_examples"):
                if isinstance(ug.get(ek), list):
                    ug[ek] = [str(x)[:120] for x in ug[ek][:3]]
        # Compact concept patterns (ids + strength only for provenance)
        cps = impact.get("concept_patterns")
        if isinstance(cps, list) and cps:
            snap["concept_pattern_ids"] = [
                str(p.get("id"))
                for p in cps
                if isinstance(p, dict) and p.get("id")
            ][:8]
        # Careful Truth-Telling joint (advisory readiness × confidence)
        ctt = impact.get("careful_truth_telling")
        if not isinstance(ctt, dict) or not ctt:
            joint = impact.get("careful_truth_telling_joint")
            if isinstance(joint, dict) and joint:
                ctt = compact_careful_truth_telling_snapshot(joint)
        if isinstance(ctt, dict) and ctt:
            snap["careful_truth_telling"] = compact_careful_truth_telling_snapshot(ctt)
        # Observation candidates (prefer durable snapshot; else live list bag)
        ocs = impact.get("observation_candidates_durable")
        if not isinstance(ocs, dict) or not ocs:
            live = impact.get("observation_candidates")
            meta = impact.get("observation_candidates_meta")
            if isinstance(live, list) and live:
                ocs = compact_observation_candidates_snapshot(
                    {
                        "candidates": live,
                        "gate": meta.get("gate")
                        if isinstance(meta, dict)
                        else {},
                        "count": len(live),
                    }
                )
        if isinstance(ocs, dict) and ocs:
            snap["observation_candidates"] = compact_observation_candidates_snapshot(
                ocs
            )
        return {k: v for k, v in snap.items() if v is not None and v != {} and v != []}


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
