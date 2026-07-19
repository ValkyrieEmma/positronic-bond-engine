"""
truth_confidence.py
===================

Lightweight **confidence-in-truth** assessment for Careful Truth-Telling.

Purpose
-------
Answer: *how confident is the system that a potential observation or piece of
guidance is well-supported by available evidence — vs weakly grounded or
conflicted?*

Pairs with ``TruthTellingReadiness`` (timing / relationship readiness):
  - Readiness → is the *bond* ready for careful observation?
  - Confidence → is the *content* well-evidenced enough to consider?

This module is **advisory only**. It does **not**:
- generate dialogue or templates
- force exploratory questions
- raise hard ethical refusals
- decide that speech must occur

Design
------
- Pure assessment + inspectable dataclass
- Evidence from bond texture consistency, concept patterns, understanding
  gaps / open topics, history signals, optional DecisionLog provenance
- ``combine_with_readiness`` produces a joint bag for future response layers
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Levels (aligned vocabulary with readiness for easy combination)
LEVEL_VERY_LOW = "very_low"
LEVEL_LOW = "low"
LEVEL_MODERATE = "moderate"
LEVEL_HIGH = "high"

_VALID_LEVELS = frozenset(
    {LEVEL_VERY_LOW, LEVEL_LOW, LEVEL_MODERATE, LEVEL_HIGH}
)


@dataclass
class TruthConfidence:
    """Inspectable confidence-in-truth signal for careful observation.

    Attributes:
        level: very_low | low | moderate | high
        score: 0.0–1.0 (higher = better-supported by evidence)
        reason: Short audit summary
        supporting_evidence: Signals that increase confidence
        conflicting_evidence: Signals that decrease confidence
        uncertainty_notes: Explicit limited-data / gap / conflict notes
        forces_speech: Always False
        forces_question: Always False
        user_id: Local scope when known
        schema_version: Structure version
    """

    level: str = LEVEL_LOW
    score: float = 0.0
    reason: str = ""
    supporting_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    forces_speech: bool = False
    forces_question: bool = False
    user_id: str = "default"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forces_speech"] = False
        d["forces_question"] = False
        if d.get("level") not in _VALID_LEVELS:
            d["level"] = LEVEL_LOW
        d["score"] = max(0.0, min(1.0, float(d.get("score") or 0.0)))
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TruthConfidence:
        if not data:
            return cls(reason="no assessment data")
        level = str(data.get("level") or LEVEL_LOW)
        if level not in _VALID_LEVELS:
            level = LEVEL_LOW
        return cls(
            level=level,
            score=max(0.0, min(1.0, float(data.get("score") or 0.0))),
            reason=str(data.get("reason") or ""),
            supporting_evidence=[
                str(x) for x in (data.get("supporting_evidence") or [])
            ][:12],
            conflicting_evidence=[
                str(x) for x in (data.get("conflicting_evidence") or [])
            ][:12],
            uncertainty_notes=[
                str(x) for x in (data.get("uncertainty_notes") or [])
            ][:12],
            forces_speech=False,
            forces_question=False,
            user_id=str(data.get("user_id") or "default"),
            schema_version=int(data.get("schema_version") or 1),
        )


def assess_truth_confidence(
    *,
    bond_texture: dict[str, Any] | None = None,
    health_flags: list[str] | None = None,
    concept_patterns: list[dict[str, Any]] | None = None,
    understanding_gaps: dict[str, Any] | None = None,
    topic_continuity: dict[str, Any] | None = None,
    curious_companion: dict[str, Any] | None = None,
    history_evidence: dict[str, Any] | None = None,
    recent_patterns: dict[str, Any] | None = None,
    interaction_count: int = 0,
    evidence_snapshot: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    decision_flags: list[str] | None = None,
    user_id: str = "default",
) -> TruthConfidence:
    """Weigh available evidence into a confidence-in-truth assessment.

    Pure function — no I/O, no speech. Missing channels reduce confidence
    (limited-data caution) rather than inventing certainty.
    """
    texture = bond_texture if isinstance(bond_texture, dict) else {}
    flags = {str(f) for f in (health_flags or [])}
    patterns = [p for p in (concept_patterns or []) if isinstance(p, dict)]
    gaps = understanding_gaps if isinstance(understanding_gaps, dict) else {}
    cont = topic_continuity if isinstance(topic_continuity, dict) else {}
    cc = curious_companion if isinstance(curious_companion, dict) else {}
    hist = history_evidence if isinstance(history_evidence, dict) else {}
    pats = recent_patterns if isinstance(recent_patterns, dict) else {}
    snap = evidence_snapshot if isinstance(evidence_snapshot, dict) else {}
    prov = provenance if isinstance(provenance, dict) else {}
    dflags = {str(f) for f in (decision_flags or [])}

    supporting: list[str] = []
    conflicting: list[str] = []
    uncertainty: list[str] = []
    # Prior: modest — do not claim high confidence without multi-channel support
    score = 0.40

    def _f(key: str, default: float = 0.5) -> float:
        try:
            return float(texture.get(key, default))
        except (TypeError, ValueError):
            return default

    # --- Limited interaction history ---
    n = int(interaction_count or 0)
    if n < 2:
        score -= 0.18
        uncertainty.append("limited_interaction_count")
        conflicting.append(f"interaction_count={n}<2")
    elif n < 4:
        score -= 0.08
        uncertainty.append("thin_but_forming_history")
        supporting.append(f"interaction_count={n}")
    else:
        score += 0.08
        supporting.append(f"interaction_count={n}")

    # --- Texture consistency (coherent dims support confidence) ---
    dims = [
        _f("trust"),
        _f("reciprocity"),
        _f("autonomy_respect"),
        _f("emotional_honesty"),
        _f("mutual_benefit"),
    ]
    if dims:
        avg = sum(dims) / len(dims)
        spread = max(dims) - min(dims)
        if spread <= 0.25 and avg >= 0.45:
            score += 0.12
            supporting.append(f"texture_coherent_avg={avg:.2f}_spread={spread:.2f}")
        elif spread >= 0.45:
            score -= 0.12
            conflicting.append(f"texture_incoherent_spread={spread:.2f}")
            uncertainty.append("conflicting_bond_dimensions")
        else:
            supporting.append(f"texture_avg={avg:.2f}")

    # --- Health flags (risk flags reduce confidence in "all is well" observations) ---
    serious = flags & {
        "emerging_dependency",
        "manufactured_attachment",
        "boundary_erosion",
        "one_sided_engagement",
    }
    if serious:
        # Confidence in a *risk-aware* observation can still be moderate if
        # flags are clear; we treat clear flags as supporting evidence of risk
        # but conflicting for rosy claims. Net: slight support for grounded
        # caution, conflict for naive certainty.
        score += 0.05
        supporting.append("clear_health_flags=" + ",".join(sorted(serious)))
        conflicting.append("risk_flags_present_for_positive_claims")
        uncertainty.append("bond_strain_complicates_claims")
    elif flags:
        supporting.append("minor_or_monitor_flags=" + ",".join(sorted(flags)[:4]))
    else:
        score += 0.04
        supporting.append("no_active_health_flags")

    # --- Concept patterns (consistent trajectory increases confidence) ---
    pat_ids = {str(p.get("id") or "") for p in patterns}
    if len(patterns) == 1:
        p0 = patterns[0]
        st = float(p0.get("strength") or 0.0)
        score += 0.12 * min(1.0, st)
        supporting.append(
            f"single_clear_concept={p0.get('id')}({st:.2f})"
        )
    elif len(patterns) >= 2:
        # Multiple patterns: check polarity conflict
        pols = {str(p.get("polarity") or "") for p in patterns}
        if "advisory_risk" in pols and "advisory_support" in pols:
            score -= 0.15
            conflicting.append("concept_polarity_conflict_risk_vs_support")
            uncertainty.append("mixed_trajectory_patterns")
        else:
            score += 0.08
            supporting.append(
                "aligned_concepts=" + ",".join(sorted(pat_ids)[:4])
            )
    else:
        if n >= 3:
            score -= 0.05
            uncertainty.append("no_multi_episode_concept_pattern")
        else:
            uncertainty.append("concepts_not_yet_formed")

    # --- Understanding gaps: explicit uncertainty about the user ---
    gap_score = float(
        gaps.get("curiosity_support")
        or gaps.get("gap_score")
        or cc.get("last_gap_score")
        or 0.0
    )
    gap_kinds = list(gaps.get("gap_kinds") or cc.get("last_gap_kinds") or [])
    if gaps.get("has_gaps") or gap_score >= 0.28:
        # Gaps lower confidence in *complete* claims; raise confidence that
        # "we don't fully know" is itself well-founded
        score -= 0.10
        uncertainty.append(
            f"understanding_gaps(score={gap_score:.2f},kinds={gap_kinds[:4]})"
        )
        conflicting.append("incomplete_individual_context")
        # Evidence that gaps are structured supports meta-confidence
        if gap_score >= 0.4:
            supporting.append("gaps_well_characterized")
            score += 0.04
    if cont.get("active") and cont.get("relational_coherence"):
        supporting.append("topic_continuity_coherent")
        score += 0.05
    elif cont.get("active") and cont.get("suppressed"):
        conflicting.append("topic_continuity_suppressed_by_concern")
        score -= 0.04

    # --- History evidence strength / conflict ---
    if hist:
        if hist.get("relevant"):
            sup = float(hist.get("support_score") or 0.0)
            if sup >= 0.45:
                score += 0.10
                supporting.append(f"history_support={sup:.2f}")
            elif sup > 0:
                score += 0.03
                supporting.append(f"history_support_weak={sup:.2f}")
            if hist.get("dependency_patterns") and hist.get("preference_continuity"):
                # Not always conflict, but mixed personal history
                uncertainty.append("history_mixed_dependency_and_preference")
        else:
            uncertainty.append("history_not_relevant_this_turn")
    else:
        if n >= 2:
            uncertainty.append("no_history_evidence_bag")
            score -= 0.04

    # Soft pattern balance
    try:
        pos = int(pats.get("positive", 0) or 0)
        neg = int(pats.get("negative", 0) or 0)
    except (TypeError, ValueError):
        pos, neg = 0, 0
    if pos + neg >= 3:
        if abs(pos - neg) <= 1:
            conflicting.append(f"mixed_update_polarity_pos={pos}_neg={neg}")
            score -= 0.06
            uncertainty.append("mixed_recent_pattern_polarity")
        elif pos > neg:
            supporting.append(f"positive_pattern_bias={pos}>{neg}")
            score += 0.04
        else:
            supporting.append(f"negative_pattern_bias={neg}>{pos}")
            score += 0.03  # clear direction still informative

    # --- Provenance / decision snapshot (if provided) ---
    if snap or prov:
        src = snap or prov
        supporting.append("provenance_or_evidence_snapshot_present")
        score += 0.06
        if src.get("understanding_gaps") or src.get("topic_continuity"):
            supporting.append("snapshot_includes_gap_or_continuity")
            score += 0.03
        if src.get("concept_pattern_ids"):
            supporting.append(
                "snapshot_concept_ids="
                + ",".join(str(x) for x in (src.get("concept_pattern_ids") or [])[:4])
            )
    # Decision flags that already encode uncertainty
    if "limited_data" in dflags or any("limited" in f for f in dflags):
        score -= 0.10
        uncertainty.append("decision_flags_limited_data")
        conflicting.append("limited_data_flag")
    if "history_understanding_gap" in dflags:
        uncertainty.append("flag:history_understanding_gap")
        score -= 0.03

    score = max(0.0, min(1.0, score))

    # Level mapping
    if score < 0.28:
        level = LEVEL_VERY_LOW
        reason = (
            "Very low confidence: limited or conflicting evidence; "
            "any careful observation would be poorly grounded."
        )
    elif score < 0.48:
        level = LEVEL_LOW
        reason = (
            "Low confidence: some signals present but thin, mixed, or "
            "incomplete individual context reduces epistemic support."
        )
    elif score < 0.72:
        level = LEVEL_MODERATE
        reason = (
            "Moderate confidence: multi-channel evidence is reasonably "
            "aligned, with residual uncertainty — suitable only for careful, "
            "hedged observation if readiness also allows."
        )
    else:
        level = LEVEL_HIGH
        reason = (
            "Higher confidence: consistent multi-episode and texture evidence "
            "supports the grounding of a careful observation — still advisory; "
            "never forces speech (combine with TruthTellingReadiness)."
        )

    return TruthConfidence(
        level=level,
        score=round(score, 3),
        reason=reason,
        supporting_evidence=supporting[:12],
        conflicting_evidence=conflicting[:12],
        uncertainty_notes=uncertainty[:12],
        forces_speech=False,
        forces_question=False,
        user_id=str(user_id or "default"),
    )


def combine_with_readiness(
    confidence: TruthConfidence | dict[str, Any] | None,
    readiness: Any | None,
) -> dict[str, Any]:
    """Combine TruthConfidence with TruthTellingReadiness into a joint bag.

    Future response layers can use:
      - surface_ok_advisory: both moderately high (still never forced)
      - reason: short joint summary
      - confidence / readiness sub-bags

    Does not generate speech. forces_speech / forces_question always False.
    """
    conf = (
        confidence
        if isinstance(confidence, TruthConfidence)
        else TruthConfidence.from_dict(
            confidence if isinstance(confidence, dict) else None
        )
    )
    # readiness may be TruthTellingReadiness or dict
    if readiness is None:
        ready_dict: dict[str, Any] = {}
        ready_score = 0.0
        ready_level = "low"
        ready_stance = "stay_quiet"
    elif hasattr(readiness, "to_dict"):
        ready_dict = readiness.to_dict()
        ready_score = float(ready_dict.get("score") or 0.0)
        ready_level = str(ready_dict.get("level") or "low")
        ready_stance = str(ready_dict.get("recommended_stance") or "stay_quiet")
    elif isinstance(readiness, dict):
        ready_dict = dict(readiness)
        ready_score = float(ready_dict.get("score") or 0.0)
        ready_level = str(ready_dict.get("level") or "low")
        ready_stance = str(ready_dict.get("recommended_stance") or "stay_quiet")
    else:
        ready_dict = {}
        ready_score = 0.0
        ready_level = "low"
        ready_stance = "stay_quiet"

    conf_score = float(conf.score)
    # Joint: geometric-ish balance — both need to be decent
    joint = (conf_score * 0.55) + (ready_score * 0.45)
    surface_ok = (
        conf_score >= 0.48
        and ready_score >= 0.45
        and ready_level not in ("suppressed",)
        and ready_stance != "stay_quiet"
        and conf.level in (LEVEL_MODERATE, LEVEL_HIGH)
    )
    # Even when surface_ok, still advisory
    if ready_level == "suppressed" or conf.level == LEVEL_VERY_LOW:
        joint_stance = "stay_quiet"
        joint_reason = (
            "Joint assessment: stay quiet — readiness suppressed or "
            "confidence very low."
        )
    elif surface_ok:
        joint_stance = "careful_observation_ok"
        joint_reason = (
            "Joint assessment: evidence confidence and relationship readiness "
            "both support *considering* a careful observation later — "
            "advisory only; never forced."
        )
    elif conf_score >= 0.48 and ready_score < 0.45:
        joint_stance = "wait"
        joint_reason = (
            "Joint assessment: content may be grounded enough, but relationship "
            "readiness is low — wait; do not surface now."
        )
    elif ready_score >= 0.45 and conf_score < 0.48:
        joint_stance = "wait"
        joint_reason = (
            "Joint assessment: relationship may be ready, but confidence in "
            "the observation is weak or conflicted — wait or seek more context."
        )
    else:
        joint_stance = "stay_quiet"
        joint_reason = (
            "Joint assessment: neither confidence nor readiness supports "
            "surfacing a careful observation now."
        )

    return {
        "joint_score": round(max(0.0, min(1.0, joint)), 3),
        "joint_stance": joint_stance,
        "surface_ok_advisory": bool(surface_ok),
        "reason": joint_reason,
        "confidence": conf.to_dict(),
        "readiness": ready_dict,
        "forces_speech": False,
        "forces_question": False,
        "schema_version": 1,
    }
