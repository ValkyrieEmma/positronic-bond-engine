"""
truth_telling_readiness.py
==========================

Lightweight **Careful Truth-Telling readiness / timing** signal for the
Positronic Bond Engine.

Purpose
-------
Answer: *when is it appropriate for the system to later surface a careful
observation or gentle guidance, versus when it should stay quiet?*

This module produces an **advisory-only** structured assessment. It does
**not**:
- generate dialogue or templates
- force exploratory questions
- raise hard ethical refusals
- bypass Relationship Health or User Agency

Design
------
- Pure assessment functions + a small dataclass for inspectability.
- Evidence from BondState texture, health flags, multi-episode concept
  patterns, understanding-gap / open-topic state, optional history tone,
  and optional exploratory-questioning user controls.
- EthicsEngine (or future response layers) may *consult* the bag; nothing
  here decides speech content.

Keep this file modular: RelationshipHealth wraps it for callers that already
hold a bond tracker; EthicsEngine only attaches the bag when present.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Public level labels (stable strings for logs / persistence)
LEVEL_SUPPRESSED = "suppressed"
LEVEL_LOW = "low"
LEVEL_MODERATE = "moderate"
LEVEL_HIGH = "high"

_VALID_LEVELS = frozenset(
    {LEVEL_SUPPRESSED, LEVEL_LOW, LEVEL_MODERATE, LEVEL_HIGH}
)


@dataclass
class TruthTellingReadiness:
    """Inspectable readiness / timing signal for careful truth-telling.

    Attributes:
        level: suppressed | low | moderate | high
        score: 0.0–1.0 continuous readiness (higher = more appropriate to
            *consider* careful observation later — never an order to speak).
        reason: Short human-readable summary for audits.
        evidence: Supporting signal strings (non-clinical).
        gates_applied: Why readiness was reduced or suppressed (if any).
        polarity: advisory_open | advisory_caution | advisory_quiet
        forces_speech: Always False (invariant).
        forces_question: Always False (invariant).
        recommended_stance: stay_quiet | wait | careful_observation_ok
            (advisory labels only for future layers).
        user_id: Local user scope when known.
        schema_version: Structure version for persistence / provenance.
    """

    level: str = LEVEL_LOW
    score: float = 0.0
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    gates_applied: list[str] = field(default_factory=list)
    polarity: str = "advisory_quiet"
    forces_speech: bool = False
    forces_question: bool = False
    recommended_stance: str = "stay_quiet"
    user_id: str = "default"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Invariants — never allow mutation via dict consumers to imply force
        d["forces_speech"] = False
        d["forces_question"] = False
        if d.get("level") not in _VALID_LEVELS:
            d["level"] = LEVEL_LOW
        d["score"] = max(0.0, min(1.0, float(d.get("score") or 0.0)))
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TruthTellingReadiness:
        if not data:
            return cls(reason="no assessment data")
        level = str(data.get("level") or LEVEL_LOW)
        if level not in _VALID_LEVELS:
            level = LEVEL_LOW
        return cls(
            level=level,
            score=max(0.0, min(1.0, float(data.get("score") or 0.0))),
            reason=str(data.get("reason") or ""),
            evidence=[str(x) for x in (data.get("evidence") or [])][:12],
            gates_applied=[str(x) for x in (data.get("gates_applied") or [])][:12],
            polarity=str(data.get("polarity") or "advisory_quiet"),
            forces_speech=False,
            forces_question=False,
            recommended_stance=str(
                data.get("recommended_stance") or "stay_quiet"
            ),
            user_id=str(data.get("user_id") or "default"),
            schema_version=int(data.get("schema_version") or 1),
        )


def assess_truth_telling_readiness(
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
    exploratory_enabled: bool | None = None,
    exploratory_intensity: float | None = None,
    concern_active: bool = False,
    hard_path_active: bool = False,
    user_id: str = "default",
) -> TruthTellingReadiness:
    """Combine bond / pattern / gap / control signals into a readiness bag.

    Pure function — no I/O, no speech generation. All inputs optional;
    missing channels simply contribute less evidence.
    """
    texture = bond_texture if isinstance(bond_texture, dict) else {}
    flags = {str(f) for f in (health_flags or [])}
    patterns = [p for p in (concept_patterns or []) if isinstance(p, dict)]
    gaps = understanding_gaps if isinstance(understanding_gaps, dict) else {}
    cont = topic_continuity if isinstance(topic_continuity, dict) else {}
    cc = curious_companion if isinstance(curious_companion, dict) else {}
    hist = history_evidence if isinstance(history_evidence, dict) else {}
    pats = recent_patterns if isinstance(recent_patterns, dict) else {}

    evidence: list[str] = []
    gates: list[str] = []
    score = 0.35  # modest prior: silence is often fine; openness is earned

    # --- Hard / concern gates (suppress speech readiness) ---
    if hard_path_active:
        return TruthTellingReadiness(
            level=LEVEL_SUPPRESSED,
            score=0.0,
            reason=(
                "Hard ethical or harm-prevention path is active — "
                "careful truth-telling observations are suppressed."
            ),
            evidence=["hard_path_active"],
            gates_applied=["hard_path"],
            polarity="advisory_quiet",
            recommended_stance="stay_quiet",
            user_id=user_id,
        )
    if concern_active:
        gates.append("ethical_concern_active")
        score -= 0.25
        evidence.append("relationship_or_agency_concern_active")

    # Serious RH flags → stay quieter
    serious = flags & {
        "emerging_dependency",
        "manufactured_attachment",
        "boundary_erosion",
        "one_sided_engagement",
    }
    if serious:
        gates.append("serious_health_flags")
        score -= 0.18 * min(2, len(serious))
        evidence.append("health_flags=" + ",".join(sorted(serious)))

    # Bond texture: autonomy + trust + honesty support careful observation
    def _f(key: str, default: float = 0.5) -> float:
        try:
            return float(texture.get(key, default))
        except (TypeError, ValueError):
            return default

    auto = _f("autonomy_respect")
    trust = _f("trust")
    honesty = _f("emotional_honesty")
    recip = _f("reciprocity")
    if auto >= 0.55:
        score += 0.12
        evidence.append(f"autonomy_respect_ok={auto:.2f}")
    elif auto < 0.40:
        score -= 0.12
        evidence.append(f"autonomy_respect_low={auto:.2f}")
        gates.append("low_autonomy_texture")
    if trust >= 0.55:
        score += 0.10
        evidence.append(f"trust_ok={trust:.2f}")
    elif trust < 0.40:
        score -= 0.10
        evidence.append(f"trust_low={trust:.2f}")
        gates.append("low_trust_texture")
    if honesty >= 0.50:
        score += 0.08
        evidence.append(f"emotional_honesty_ok={honesty:.2f}")
    if recip >= 0.50:
        score += 0.05
        evidence.append(f"reciprocity_ok={recip:.2f}")

    # Concept patterns
    pat_ids = {str(p.get("id") or "") for p in patterns}
    pat_by_id = {str(p.get("id") or ""): p for p in patterns}
    if "healthy_co_evolution" in pat_ids:
        st = float(pat_by_id["healthy_co_evolution"].get("strength") or 0.5)
        score += 0.18 * min(1.0, st)
        evidence.append(f"concept:healthy_co_evolution({st:.2f})")
    if "escalating_dependency" in pat_ids:
        st = float(pat_by_id["escalating_dependency"].get("strength") or 0.5)
        score -= 0.22 * min(1.0, st)
        evidence.append(f"concept:escalating_dependency({st:.2f})")
        gates.append("escalating_dependency_pattern")
    if "protective_withdrawal" in pat_ids:
        st = float(pat_by_id["protective_withdrawal"].get("strength") or 0.5)
        score -= 0.16 * min(1.0, st)
        evidence.append(f"concept:protective_withdrawal({st:.2f})")
        gates.append("protective_withdrawal_pattern")
    if "boundary_testing_loop" in pat_ids:
        st = float(pat_by_id["boundary_testing_loop"].get("strength") or 0.5)
        score -= 0.12 * min(1.0, st)
        evidence.append(f"concept:boundary_testing_loop({st:.2f})")
        gates.append("boundary_testing_loop")
    if "stalled_growth" in pat_ids:
        st = float(pat_by_id["stalled_growth"].get("strength") or 0.5)
        # Mild caution: observation may help *if* other channels are healthy
        score -= 0.05 * min(1.0, st)
        evidence.append(f"concept:stalled_growth({st:.2f})")

    # Understanding gaps / open topics: increase *potential* for careful
    # observation only when bond is not strained (gaps alone ≠ speak now)
    gap_score = float(
        gaps.get("curiosity_support")
        or gaps.get("gap_score")
        or cc.get("last_gap_score")
        or 0.0
    )
    open_names = list(
        gaps.get("primary_gap_topics")
        or cont.get("open_topic_names")
        or cc.get("open_topic_names")
        or []
    )
    if gap_score >= 0.35 or open_names:
        if not serious and auto >= 0.45:
            score += 0.10
            evidence.append(
                f"open_or_gap_context(score={gap_score:.2f},topics={open_names[:3]})"
            )
        else:
            score -= 0.05
            evidence.append("gaps_present_but_bond_not_ready")
            gates.append("gaps_without_bond_readiness")

    if cont.get("relational_coherence") and cont.get("action_continues_open_topic"):
        if not serious:
            score += 0.08
            evidence.append("topic_continuity_relational_coherence")

    # History tone (light): dependency / boundary pressure quietens; preference continuity can open
    if hist.get("dependency_patterns"):
        score -= 0.10
        evidence.append("history:dependency_patterns")
        gates.append("history_dependency")
    if hist.get("boundary_continuity") and serious:
        score -= 0.05
        evidence.append("history:boundary_under_strain")
    if hist.get("preference_continuity") and not serious:
        score += 0.05
        evidence.append("history:preference_continuity")

    # Soft pattern counters
    try:
        neg = int(pats.get("negative", 0) or 0)
        pos = int(pats.get("positive", 0) or 0)
    except (TypeError, ValueError):
        neg, pos = 0, 0
    if neg >= 3 and neg > pos:
        score -= 0.08
        evidence.append(f"recent_negative_bias={neg}>{pos}")
        gates.append("recent_negative_bias")
    if pos >= 2 and pos > neg and not serious:
        score += 0.05
        evidence.append(f"recent_positive_bias={pos}")

    if int(interaction_count or 0) < 2:
        score -= 0.08
        evidence.append("thin_interaction_history")
        gates.append("thin_history")

    # User exploratory controls (explicit agency)
    if exploratory_enabled is False:
        gates.append("exploratory_questioning_disabled")
        score -= 0.20
        evidence.append("user_disabled_exploratory_questioning")
    elif exploratory_enabled is True:
        intensity = 0.5
        if exploratory_intensity is not None:
            try:
                intensity = max(0.0, min(1.0, float(exploratory_intensity)))
            except (TypeError, ValueError):
                intensity = 0.5
        if intensity <= 0.0:
            gates.append("exploratory_intensity_zero")
            score -= 0.18
            evidence.append("exploratory_intensity=0")
        elif intensity >= 0.65:
            score += 0.06
            evidence.append(f"exploratory_intensity_open={intensity:.2f}")
        else:
            evidence.append(f"exploratory_intensity={intensity:.2f}")

    score = max(0.0, min(1.0, score))

    # Map to level + stance (advisory labels only)
    if score < 0.22 or (concern_active and score < 0.45):
        level = LEVEL_SUPPRESSED if (hard_path_active or (concern_active and score < 0.25)) else LEVEL_LOW
        if concern_active and score < 0.25:
            level = LEVEL_SUPPRESSED
        stance = "stay_quiet"
        polarity = "advisory_quiet"
    elif score < 0.45:
        level = LEVEL_LOW
        stance = "stay_quiet"
        polarity = "advisory_quiet"
    elif score < 0.70:
        level = LEVEL_MODERATE
        stance = "wait"
        polarity = "advisory_caution"
    else:
        level = LEVEL_HIGH
        stance = "careful_observation_ok"
        polarity = "advisory_open"

    # Re-suppress if user fully disabled exploratory (even if score was high)
    if exploratory_enabled is False or (
        exploratory_intensity is not None and float(exploratory_intensity or 0) <= 0.0
    ):
        level = LEVEL_LOW if level == LEVEL_HIGH else level
        if exploratory_enabled is False:
            level = LEVEL_SUPPRESSED
            stance = "stay_quiet"
            polarity = "advisory_quiet"

    if level == LEVEL_SUPPRESSED:
        reason = (
            "Readiness suppressed: protective or user-control gates advise silence "
            "for careful observation right now."
        )
    elif level == LEVEL_LOW:
        reason = (
            "Low readiness: bond or trajectory evidence favors staying quiet; "
            "careful observation is not currently indicated."
        )
    elif level == LEVEL_MODERATE:
        reason = (
            "Moderate readiness: some support for careful observation later, "
            "but pacing and User Agency still call for restraint."
        )
    else:
        reason = (
            "Higher readiness: bond texture and trajectory support *considering* "
            "a careful observation when a future response layer chooses to speak — "
            "still advisory; never forced."
        )

    return TruthTellingReadiness(
        level=level,
        score=round(score, 3),
        reason=reason,
        evidence=evidence[:12],
        gates_applied=list(dict.fromkeys(gates))[:12],
        polarity=polarity,
        forces_speech=False,
        forces_question=False,
        recommended_stance=stance,
        user_id=str(user_id or "default"),
    )
