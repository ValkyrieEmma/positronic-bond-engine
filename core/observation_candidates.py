"""
observation_candidates.py
=========================

Lightweight **observation-candidate** layer for Careful Truth-Telling.

Purpose
-------
Given readiness × confidence (joint assessment) plus grounded bond / history
evidence, produce a **small** set (0–3) of structured *possible* careful
observations the system *could* consider later.

This module is **advisory and non-speaking**. It does **not**:
- generate user-facing dialogue or templates
- force exploratory questions
- raise hard ethical refusals
- decide that anything must be said

Future response layers may consult these candidates; nothing here opens speech.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Cap deliberately low — quality over volume
MAX_CANDIDATES = 3

# Joint stances (aligned with truth_confidence.combine_with_readiness)
STANCE_STAY_QUIET = "stay_quiet"
STANCE_WAIT = "wait"
STANCE_CAREFUL_OK = "careful_observation_ok"


@dataclass
class ObservationCandidate:
    """One possible careful observation (structured, non-speaking).

    Attributes:
        id: Stable short id for this candidate type/source.
        description: Short neutral description of what *could* be observed
            (not a dialogue template; not addressed to the user).
        evidence_refs: Compact evidence labels / keys (not raw episode text).
        readiness_level: Linked readiness level at generation time.
        confidence_level: Linked confidence level at generation time.
        priority: 0.0–1.0 relevance / priority for future layers.
        source: Primary evidence channel (concept_pattern, understanding_gap,
            bond_texture, history, health_flag, joint).
        joint_stance: Joint careful-truth-telling stance used for gating.
        forces_speech: Always False.
        forces_question: Always False.
        schema_version: Structure version.
    """

    id: str
    description: str
    evidence_refs: list[str] = field(default_factory=list)
    readiness_level: str = "low"
    confidence_level: str = "low"
    priority: float = 0.0
    source: str = "unknown"
    joint_stance: str = STANCE_STAY_QUIET
    forces_speech: bool = False
    forces_question: bool = False
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forces_speech"] = False
        d["forces_question"] = False
        d["priority"] = max(0.0, min(1.0, float(d.get("priority") or 0.0)))
        d["description"] = str(d.get("description") or "")[:280]
        d["evidence_refs"] = [str(x)[:96] for x in (d.get("evidence_refs") or [])][:8]
        d["id"] = str(d.get("id") or "unknown")[:64]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ObservationCandidate:
        if not data:
            return cls(
                id="empty",
                description="",
                forces_speech=False,
                forces_question=False,
            )
        return cls(
            id=str(data.get("id") or "unknown")[:64],
            description=str(data.get("description") or "")[:280],
            evidence_refs=[str(x)[:96] for x in (data.get("evidence_refs") or [])][:8],
            readiness_level=str(data.get("readiness_level") or "low")[:32],
            confidence_level=str(data.get("confidence_level") or "low")[:32],
            priority=max(0.0, min(1.0, float(data.get("priority") or 0.0))),
            source=str(data.get("source") or "unknown")[:48],
            joint_stance=str(data.get("joint_stance") or STANCE_STAY_QUIET)[:64],
            forces_speech=False,
            forces_question=False,
            schema_version=int(data.get("schema_version") or 1),
        )


def _level_from_joint(joint: dict[str, Any], which: str) -> str:
    """Extract readiness or confidence level from joint bag (nested or flat)."""
    if which == "readiness":
        nested = joint.get("readiness") if isinstance(joint.get("readiness"), dict) else {}
        return str(
            joint.get("readiness_level")
            or nested.get("level")
            or "low"
        )
    nested = joint.get("confidence") if isinstance(joint.get("confidence"), dict) else {}
    return str(
        joint.get("confidence_level")
        or nested.get("level")
        or "low"
    )


def _score_from_joint(joint: dict[str, Any], which: str) -> float:
    if which == "readiness":
        nested = joint.get("readiness") if isinstance(joint.get("readiness"), dict) else {}
        try:
            return float(
                joint.get("readiness_score")
                if joint.get("readiness_score") is not None
                else nested.get("score") or 0.0
            )
        except (TypeError, ValueError):
            return 0.0
    nested = joint.get("confidence") if isinstance(joint.get("confidence"), dict) else {}
    try:
        return float(
            joint.get("confidence_score")
            if joint.get("confidence_score") is not None
            else nested.get("score") or 0.0
        )
    except (TypeError, ValueError):
        return 0.0


def gate_allows_candidates(joint: dict[str, Any] | None) -> dict[str, Any]:
    """Decide how many candidates the joint assessment permits.

    Returns:
        allowed_max (0–3), reason, joint_stance, readiness_level, confidence_level
    """
    j = joint if isinstance(joint, dict) else {}
    stance = str(j.get("joint_stance") or STANCE_STAY_QUIET)
    ready_level = _level_from_joint(j, "readiness")
    conf_level = _level_from_joint(j, "confidence")
    ready_score = _score_from_joint(j, "readiness")
    conf_score = _score_from_joint(j, "confidence")
    joint_score = float(j.get("joint_score") or 0.0)
    surface_ok = bool(j.get("surface_ok_advisory"))

    # Hard quiet gates
    if (
        ready_level == "suppressed"
        or conf_level in ("very_low",)
        or stance == STANCE_STAY_QUIET
        or joint_score < 0.28
        or (ready_score < 0.30 and conf_score < 0.30)
    ):
        return {
            "allowed_max": 0,
            "reason": (
                "Gated closed: joint stance quiet, suppressed readiness, "
                "very low confidence, or joint_score too low — no candidates."
            ),
            "joint_stance": stance,
            "readiness_level": ready_level,
            "confidence_level": conf_level,
        }

    # Wait: at most one low-priority exploratory seed for future layers
    if stance == STANCE_WAIT or not surface_ok:
        if ready_score < 0.35 or conf_score < 0.35:
            return {
                "allowed_max": 0,
                "reason": (
                    "Gated closed under wait: readiness or confidence still too "
                    "low for even a single candidate."
                ),
                "joint_stance": stance,
                "readiness_level": ready_level,
                "confidence_level": conf_level,
            }
        return {
            "allowed_max": 1,
            "reason": (
                "Gated to at most 1 candidate: joint stance is wait / not yet "
                "surface_ok_advisory."
            ),
            "joint_stance": stance,
            "readiness_level": ready_level,
            "confidence_level": conf_level,
        }

    # careful_observation_ok / surface_ok: up to MAX_CANDIDATES
    cap = MAX_CANDIDATES
    if conf_level == "low" or ready_level == "low":
        cap = min(cap, 2)
    if joint_score < 0.50:
        cap = min(cap, 2)
    return {
        "allowed_max": cap,
        "reason": (
            f"Gated open (max={cap}): joint supports considering careful "
            "observations — advisory candidates only."
        ),
        "joint_stance": stance,
        "readiness_level": ready_level,
        "confidence_level": conf_level,
    }


def _candidate(
    *,
    cid: str,
    description: str,
    evidence_refs: list[str],
    source: str,
    priority: float,
    joint: dict[str, Any],
    gate: dict[str, Any],
) -> ObservationCandidate:
    return ObservationCandidate(
        id=cid[:64],
        description=description[:280],
        evidence_refs=[str(x)[:96] for x in evidence_refs][:8],
        readiness_level=str(gate.get("readiness_level") or _level_from_joint(joint, "readiness")),
        confidence_level=str(gate.get("confidence_level") or _level_from_joint(joint, "confidence")),
        priority=max(0.0, min(1.0, float(priority))),
        source=source[:48],
        joint_stance=str(gate.get("joint_stance") or joint.get("joint_stance") or STANCE_STAY_QUIET),
        forces_speech=False,
        forces_question=False,
    )


def _from_concept_patterns(
    patterns: list[dict[str, Any]],
    joint: dict[str, Any],
    gate: dict[str, Any],
) -> list[ObservationCandidate]:
    out: list[ObservationCandidate] = []
    # Prefer concerning or healthy co-evolution labels that are relationship-grounded
    priority_boost = {
        "escalating_dependency": 0.88,
        "boundary_testing_loop": 0.84,
        "attachment_pressure": 0.82,
        "healthy_co_evolution": 0.72,
        "reciprocity_recovery": 0.70,
        "trust_repair": 0.70,
    }
    for p in patterns or []:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or p.get("pattern_id") or "").strip()
        if not pid:
            continue
        strength = float(p.get("strength") or p.get("score") or 0.0)
        if strength < 0.30 and pid not in priority_boost:
            continue
        base = priority_boost.get(pid, 0.55)
        pri = min(1.0, base * (0.55 + 0.45 * min(1.0, max(strength, 0.35))))
        label = str(p.get("label") or p.get("name") or pid).replace("_", " ")
        out.append(
            _candidate(
                cid=f"concept:{pid}"[:64],
                description=(
                    f"Multi-episode concept pattern '{pid}' "
                    f"(strength≈{strength:.2f}) is present — a careful observation "
                    f"about this trajectory ({label}) may be relationship-relevant."
                ),
                evidence_refs=[
                    f"concept_pattern:{pid}",
                    f"strength:{strength:.2f}",
                ],
                source="concept_pattern",
                priority=pri,
                joint=joint,
                gate=gate,
            )
        )
    return out


def _from_understanding_gaps(
    gaps: dict[str, Any] | None,
    topic_continuity: dict[str, Any] | None,
    curious_companion: dict[str, Any] | None,
    joint: dict[str, Any],
    gate: dict[str, Any],
) -> list[ObservationCandidate]:
    out: list[ObservationCandidate] = []
    g = gaps if isinstance(gaps, dict) else {}
    tc = topic_continuity if isinstance(topic_continuity, dict) else {}
    cc = curious_companion if isinstance(curious_companion, dict) else {}

    topics: list[str] = []
    for key in ("primary_gap_topics", "open_topics", "action_aligned_topics"):
        raw = g.get(key) or tc.get(key) or cc.get(key)
        if isinstance(raw, list):
            for t in raw:
                s = str(t).strip()[:48]
                if s and s not in topics:
                    topics.append(s)
    for t in cc.get("open_topic_names") or []:
        s = str(t).strip()[:48]
        if s and s not in topics:
            topics.append(s)

    gap_score = 0.0
    try:
        gap_score = float(
            g.get("gap_score")
            or cc.get("last_gap_score")
            or 0.0
        )
    except (TypeError, ValueError):
        gap_score = 0.0
    has_gaps = bool(g.get("has_gaps") or topics or gap_score >= 0.25)

    if not has_gaps and not topics:
        return out

    # One candidate for the top open topic (most grounded)
    if topics:
        top = topics[0]
        pri = min(0.9, 0.50 + 0.35 * min(1.0, gap_score if gap_score else 0.4))
        out.append(
            _candidate(
                cid=f"gap_topic:{top}"[:64],
                description=(
                    f"Open understanding gap / topic continuity around '{top}' — "
                    "a careful, non-pushy observation about this unfinished thread "
                    "may be grounded if readiness allows."
                ),
                evidence_refs=[
                    f"open_topic:{top}",
                    f"gap_score:{gap_score:.2f}",
                    *[f"open_topic:{t}" for t in topics[1:3]],
                ],
                source="understanding_gap",
                priority=pri,
                joint=joint,
                gate=gate,
            )
        )
    elif gap_score >= 0.35:
        out.append(
            _candidate(
                cid="gap_generic",
                description=(
                    "Understanding-gap signal present without a named topic — "
                    "system could later note limited grasp rather than invent detail."
                ),
                evidence_refs=[f"gap_score:{gap_score:.2f}"],
                source="understanding_gap",
                priority=min(0.65, 0.40 + 0.3 * gap_score),
                joint=joint,
                gate=gate,
            )
        )
    return out


def _from_bond_texture(
    bond_texture: dict[str, Any] | None,
    health_flags: list[str] | None,
    joint: dict[str, Any],
    gate: dict[str, Any],
) -> list[ObservationCandidate]:
    out: list[ObservationCandidate] = []
    tex = bond_texture if isinstance(bond_texture, dict) else {}
    if not tex:
        return out

    # Low dimensions that are relationship-relevant (not clinical)
    lows: list[tuple[str, float]] = []
    for dim, val in tex.items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v < 0.42:
            lows.append((str(dim), v))
    lows.sort(key=lambda x: x[1])

    if lows:
        dim, v = lows[0]
        # Prefer autonomy / trust / reciprocity as observation seeds
        if dim in (
            "autonomy_respect",
            "trust",
            "reciprocity",
            "emotional_honesty",
            "mutual_benefit",
        ):
            pri = min(0.78, 0.45 + (0.42 - v))
            out.append(
                _candidate(
                    cid=f"texture_low:{dim}"[:64],
                    description=(
                        f"Bond texture dimension '{dim}' is relatively low "
                        f"(≈{v:.2f}) — a careful observation about this relational "
                        "quality may be relevant; not a diagnosis."
                    ),
                    evidence_refs=[f"bond_texture:{dim}={v:.2f}"],
                    source="bond_texture",
                    priority=pri,
                    joint=joint,
                    gate=gate,
                )
            )

    flags = [str(f) for f in (health_flags or []) if f]
    # Only soft, non-absolute flags as observation seeds
    soft_flag_map = {
        "emerging_dependency": (
            0.80,
            "Health flag 'emerging_dependency' is active — observation about "
            "balance of reliance vs autonomy may be relationship-relevant.",
        ),
        "boundary_erosion": (
            0.82,
            "Health flag 'boundary_erosion' is active — observation about "
            "boundary respect may be relationship-relevant.",
        ),
        "low_reciprocity": (
            0.70,
            "Health flag 'low_reciprocity' is active — observation about "
            "give-and-take balance may be relationship-relevant.",
        ),
    }
    for fl in flags:
        if fl in soft_flag_map:
            pri, desc = soft_flag_map[fl]
            out.append(
                _candidate(
                    cid=f"flag:{fl}"[:64],
                    description=desc,
                    evidence_refs=[f"health_flag:{fl}"],
                    source="health_flag",
                    priority=pri,
                    joint=joint,
                    gate=gate,
                )
            )
            break  # one flag-based candidate max at source
    return out


def _from_history(
    history_evidence: dict[str, Any] | None,
    joint: dict[str, Any],
    gate: dict[str, Any],
) -> list[ObservationCandidate]:
    out: list[ObservationCandidate] = []
    hist = history_evidence if isinstance(history_evidence, dict) else {}
    if not hist or not hist.get("relevant"):
        return out

    # Boundary / preference continuity — careful observation seed
    if hist.get("boundary_continuity") or hist.get("preference_continuity"):
        support = float(hist.get("support_score") or 0.0)
        out.append(
            _candidate(
                cid="history:boundary_continuity",
                description=(
                    "Interaction history shows boundary or preference continuity — "
                    "a careful observation that honors prior limits may be grounded."
                ),
                evidence_refs=[
                    "history:boundary_or_preference_continuity",
                    f"history_support:{support:.2f}",
                ],
                source="history",
                priority=min(0.85, 0.50 + 0.35 * min(1.0, support)),
                joint=joint,
                gate=gate,
            )
        )

    intent = hist.get("intent_patterns") if isinstance(hist.get("intent_patterns"), dict) else {}
    strength = float(intent.get("pattern_strength") or 0.0)
    repeated = list(intent.get("repeated_intents") or [])[:3]
    if strength >= 0.35 and repeated:
        out.append(
            _candidate(
                cid="history:intent_pattern",
                description=(
                    "Repeated intent patterns in history "
                    f"({', '.join(str(x) for x in repeated[:3])}) — a careful "
                    "observation about this recurring trajectory may be grounded."
                ),
                evidence_refs=[
                    f"history_intent:{x}" for x in repeated[:3]
                ]
                + [f"pattern_strength:{strength:.2f}"],
                source="history",
                priority=min(0.86, 0.48 + 0.4 * min(1.0, strength)),
                joint=joint,
                gate=gate,
            )
        )
    return out


def generate_observation_candidates(
    *,
    joint: dict[str, Any] | None = None,
    concept_patterns: list[dict[str, Any]] | None = None,
    understanding_gaps: dict[str, Any] | None = None,
    topic_continuity: dict[str, Any] | None = None,
    curious_companion: dict[str, Any] | None = None,
    bond_texture: dict[str, Any] | None = None,
    health_flags: list[str] | None = None,
    history_evidence: dict[str, Any] | None = None,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    """Build a gated, compact set of observation candidates.

    Returns a bag::
        {
          "candidates": [ObservationCandidate.to_dict(), ...],  # 0–3
          "count": int,
          "gate": {...},
          "forces_speech": False,
          "forces_question": False,
          "schema_version": 1,
        }

    Never produces speech or questions. Empty when joint assessment says quiet.
    """
    j = joint if isinstance(joint, dict) else {}
    gate = gate_allows_candidates(j)
    allowed = int(gate.get("allowed_max") or 0)
    if max_candidates is not None:
        allowed = min(allowed, max(0, int(max_candidates)))
    allowed = min(MAX_CANDIDATES, max(0, allowed))

    empty_bag = {
        "candidates": [],
        "count": 0,
        "gate": gate,
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }
    if allowed <= 0:
        return empty_bag

    pool: list[ObservationCandidate] = []
    pool.extend(_from_concept_patterns(list(concept_patterns or []), j, gate))
    pool.extend(
        _from_understanding_gaps(
            understanding_gaps, topic_continuity, curious_companion, j, gate
        )
    )
    pool.extend(_from_bond_texture(bond_texture, health_flags, j, gate))
    pool.extend(_from_history(history_evidence, j, gate))

    # Prefer grounded relational sources over generic; stable id de-dupe
    pool.sort(key=lambda c: (-float(c.priority), c.source, c.id))
    seen: set[str] = set()
    selected: list[ObservationCandidate] = []
    for c in pool:
        if c.id in seen:
            continue
        # Under wait gate, only keep higher-priority grounded items
        if allowed <= 1 and c.priority < 0.48:
            continue
        seen.add(c.id)
        selected.append(c)
        if len(selected) >= allowed:
            break

    # Scale priorities slightly by joint_score so weak joints don't over-rank
    joint_score = float(j.get("joint_score") or 0.0)
    scale = 0.75 + 0.25 * min(1.0, max(0.0, joint_score))
    for c in selected:
        c.priority = round(min(1.0, float(c.priority) * scale), 3)
        c.forces_speech = False
        c.forces_question = False

    return {
        "candidates": [c.to_dict() for c in selected],
        "count": len(selected),
        "gate": gate,
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }
