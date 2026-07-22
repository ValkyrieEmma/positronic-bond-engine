"""
enjoyment_score.py
==================

Lightweight **enjoyment-driven personality scoring** (Tier 1) for co-evolution.

Purpose
-------
Estimate what *this specific human* appears to enjoy and respond positively to
(including special interests and stimming-related triggers), so future style
preferences can emerge from **their enjoyment** rather than simple mirroring.

This is **not** engagement optimization. It is an advisory, evidence-backed,
time-decayed score with explicit Relationship Health guardrails.

Does **not**:
- generate speech or questions
- force style changes
- override protective health flags
- prolong conversation for metrics / retention

Design
------
- Multi-signal instant assessment → blended into a decaying running score
- Provenance list of supporting evidence labels (auditable / correctable)
- ``influence_allowed`` is False when protective RH flags are active
- Optional tiny texture nudges only when influence is allowed (caller-side)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Neutral resting point for decay (neither high nor low enjoyment)
_NEUTRAL = 0.50
# Default decay toward neutral per interaction when no new positive evidence
_DEFAULT_DECAY = 0.92
# Cap provenance entries
_MAX_EVIDENCE = 12
_MAX_SIGNAL_KEYS = 12

# Protective flags that block enjoyment → texture/style influence
# (score may still update for audit; influence_allowed becomes False)
PROTECTIVE_BLOCKING_FLAGS = frozenset(
    {
        "emerging_dependency",
        "manufactured_attachment",
        "one_sided_engagement",
        "boundary_erosion",
        "coercive_engagement",
    }
)

# Signal channel names (stable for logs / persistence)
SIGNAL_CONTINUATION = "continuation"
SIGNAL_POSITIVE_LANGUAGE = "positive_language"
SIGNAL_SPECIAL_INTEREST = "special_interest"
SIGNAL_STIMMING = "stimming_trigger"
SIGNAL_ENGAGEMENT = "engagement_pattern"
SIGNAL_RECIPROCITY = "reciprocity_enjoyment"

_SIGNAL_WEIGHTS: dict[str, float] = {
    SIGNAL_CONTINUATION: 0.22,
    SIGNAL_POSITIVE_LANGUAGE: 0.20,
    SIGNAL_SPECIAL_INTEREST: 0.22,
    SIGNAL_STIMMING: 0.16,
    SIGNAL_ENGAGEMENT: 0.10,
    SIGNAL_RECIPROCITY: 0.10,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass
class EnjoymentScore:
    """Inspectable multi-signal enjoyment score for one user bond.

    Attributes:
        score: Overall 0–1 time-decayed enjoyment estimate.
        signals: Channel → contribution strength (0–1) for latest blend.
        evidence: Compact provenance labels (not dialogue).
        last_updated: ISO timestamp.
        interaction_count: Bond interaction count when last updated.
        sample_count: Number of enjoyment updates applied.
        influence_allowed: False when RH protective flags block co-evolution use.
        gates_applied: Why influence was blocked or score damped.
        preferred_topics: Short special-interest / enjoyment topic labels.
        forces_speech / forces_question: Always False.
        user_id: Local scope when known.
        schema_version: Structure version.
    """

    score: float = _NEUTRAL
    signals: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=_utc_now_iso)
    interaction_count: int = 0
    sample_count: int = 0
    influence_allowed: bool = True
    gates_applied: list[str] = field(default_factory=list)
    preferred_topics: list[str] = field(default_factory=list)
    forces_speech: bool = False
    forces_question: bool = False
    user_id: str = "default"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score"] = _clamp01(float(d.get("score") or _NEUTRAL))
        d["forces_speech"] = False
        d["forces_question"] = False
        d["signals"] = {
            str(k)[:48]: _clamp01(float(v))
            for k, v in (d.get("signals") or {}).items()
        }
        d["evidence"] = [str(x)[:96] for x in (d.get("evidence") or [])][:_MAX_EVIDENCE]
        d["gates_applied"] = [str(x)[:80] for x in (d.get("gates_applied") or [])][:8]
        d["preferred_topics"] = [
            str(t)[:48] for t in (d.get("preferred_topics") or [])
        ][:8]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EnjoymentScore:
        if not data:
            return cls()
        signals: dict[str, float] = {}
        for k, v in (data.get("signals") or {}).items():
            try:
                signals[str(k)[:48]] = _clamp01(float(v))
            except (TypeError, ValueError):
                continue
        return cls(
            score=_clamp01(float(data.get("score") if data.get("score") is not None else _NEUTRAL)),
            signals=signals,
            evidence=[str(x)[:96] for x in (data.get("evidence") or [])][:_MAX_EVIDENCE],
            last_updated=str(data.get("last_updated") or _utc_now_iso()),
            interaction_count=int(data.get("interaction_count") or 0),
            sample_count=int(data.get("sample_count") or 0),
            influence_allowed=bool(data.get("influence_allowed", True)),
            gates_applied=[str(x)[:80] for x in (data.get("gates_applied") or [])][:8],
            preferred_topics=[
                str(t)[:48] for t in (data.get("preferred_topics") or [])
            ][:8],
            forces_speech=False,
            forces_question=False,
            user_id=str(data.get("user_id") or "default"),
            schema_version=int(data.get("schema_version") or 1),
        )


def apply_rh_guardrails(
    score: EnjoymentScore,
    *,
    health_flags: list[str] | None = None,
    ethical_concern_active: bool = False,
) -> EnjoymentScore:
    """Set influence_allowed / gates from Relationship Health protective state.

    Does not zero the score (audit trail preserved); blocks style/texture use.
    """
    flags = {str(f) for f in (health_flags or []) if f}
    blocking = sorted(flags & PROTECTIVE_BLOCKING_FLAGS)
    gates = list(score.gates_applied)
    allowed = True
    if blocking:
        allowed = False
        for f in blocking:
            g = f"rh_flag_blocks_influence:{f}"
            if g not in gates:
                gates.append(g)
    if ethical_concern_active:
        allowed = False
        g = "ethical_concern_blocks_influence"
        if g not in gates:
            gates.append(g)
    score.influence_allowed = allowed
    score.gates_applied = gates[:8]
    score.forces_speech = False
    score.forces_question = False
    return score


def extract_enjoyment_signals_from_interaction(
    interaction: dict[str, Any] | None,
) -> dict[str, Any]:
    """Pull structured enjoyment signals from an interaction dict.

    Recognized keys (all optional)::
        enjoyment_signals: dict of channel → float|bool|str
        continued / continuation: bool or float
        positive_language / user_positive: bool or float
        special_interest / special_interest_topic: str or bool
        stimming / stimming_trigger: str or bool
        engagement_pattern / voluntary_engagement: float
        enjoyed / user_enjoyed: bool
    """
    ix = interaction if isinstance(interaction, dict) else {}
    raw = ix.get("enjoyment_signals")
    out: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}

    # Flat aliases
    if ix.get("continued") is not None or ix.get("continuation") is not None:
        out.setdefault(
            SIGNAL_CONTINUATION,
            ix.get("continuation") if ix.get("continuation") is not None else ix.get("continued"),
        )
    if ix.get("positive_language") is not None or ix.get("user_positive") is not None:
        out.setdefault(
            SIGNAL_POSITIVE_LANGUAGE,
            ix.get("positive_language")
            if ix.get("positive_language") is not None
            else ix.get("user_positive"),
        )
    if ix.get("special_interest") is not None or ix.get("special_interest_topic") is not None:
        out.setdefault(
            SIGNAL_SPECIAL_INTEREST,
            ix.get("special_interest_topic")
            if ix.get("special_interest_topic") is not None
            else ix.get("special_interest"),
        )
    if ix.get("stimming") is not None or ix.get("stimming_trigger") is not None:
        out.setdefault(
            SIGNAL_STIMMING,
            ix.get("stimming_trigger")
            if ix.get("stimming_trigger") is not None
            else ix.get("stimming"),
        )
    if ix.get("engagement_pattern") is not None or ix.get("voluntary_engagement") is not None:
        out.setdefault(
            SIGNAL_ENGAGEMENT,
            ix.get("engagement_pattern")
            if ix.get("engagement_pattern") is not None
            else ix.get("voluntary_engagement"),
        )
    if ix.get("enjoyed") is True or ix.get("user_enjoyed") is True:
        out.setdefault(SIGNAL_POSITIVE_LANGUAGE, 0.7)
        out.setdefault(SIGNAL_CONTINUATION, max(float(out.get(SIGNAL_CONTINUATION) or 0), 0.55))

    # Light inference from type / impact when no explicit enjoyment bag
    itype = str(ix.get("type") or "").lower().replace(" ", "_")
    impact = float(ix.get("impact") or 0.0)
    if not out:
        if any(x in itype for x in ("positive", "supportive", "reciproc", "playful", "shared")):
            out[SIGNAL_POSITIVE_LANGUAGE] = min(0.75, 0.45 + max(0.0, impact) * 0.4)
            out[SIGNAL_RECIPROCITY] = min(0.7, 0.40 + max(0.0, impact) * 0.35)
        if "special_interest" in itype or "stim" in itype:
            out[SIGNAL_SPECIAL_INTEREST] = 0.65
        if impact > 0.15 and any(
            x in itype for x in ("boundary_respected", "consent_respected", "positive")
        ):
            out.setdefault(SIGNAL_CONTINUATION, min(0.6, 0.35 + impact * 0.3))
    return out


def _to_strength(val: Any) -> float:
    """Normalize a signal value to 0–1 strength."""
    if val is None:
        return 0.0
    if isinstance(val, bool):
        return 0.75 if val else 0.0
    if isinstance(val, (int, float)):
        return _clamp01(float(val))
    s = str(val).strip()
    if not s:
        return 0.0
    # Non-empty topic/label counts as moderate-high presence
    return 0.70


def _topic_from_val(val: Any) -> str | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return None
    s = str(val).strip()[:48]
    return s or None


def compute_instant_enjoyment(
    signals: dict[str, Any] | None,
) -> tuple[float, dict[str, float], list[str], list[str]]:
    """Compute one-shot enjoyment from signal bag.

    Returns (instant_score, channel_strengths, evidence_labels, topics).
    """
    sig = signals if isinstance(signals, dict) else {}
    strengths: dict[str, float] = {}
    evidence: list[str] = []
    topics: list[str] = []

    # Map free-form keys onto canonical channels
    canonical_map = {
        "continuation": SIGNAL_CONTINUATION,
        "continued": SIGNAL_CONTINUATION,
        SIGNAL_CONTINUATION: SIGNAL_CONTINUATION,
        "positive_language": SIGNAL_POSITIVE_LANGUAGE,
        "user_positive": SIGNAL_POSITIVE_LANGUAGE,
        SIGNAL_POSITIVE_LANGUAGE: SIGNAL_POSITIVE_LANGUAGE,
        "special_interest": SIGNAL_SPECIAL_INTEREST,
        "special_interest_topic": SIGNAL_SPECIAL_INTEREST,
        SIGNAL_SPECIAL_INTEREST: SIGNAL_SPECIAL_INTEREST,
        "stimming": SIGNAL_STIMMING,
        "stimming_trigger": SIGNAL_STIMMING,
        SIGNAL_STIMMING: SIGNAL_STIMMING,
        "engagement_pattern": SIGNAL_ENGAGEMENT,
        "voluntary_engagement": SIGNAL_ENGAGEMENT,
        SIGNAL_ENGAGEMENT: SIGNAL_ENGAGEMENT,
        "reciprocity": SIGNAL_RECIPROCITY,
        "reciprocity_enjoyment": SIGNAL_RECIPROCITY,
        SIGNAL_RECIPROCITY: SIGNAL_RECIPROCITY,
    }

    for k, v in sig.items():
        key = str(k).lower().strip()
        channel = canonical_map.get(key)
        if not channel:
            # Allow direct custom channel with low weight if numeric
            if isinstance(v, (int, float, bool)):
                channel = key[:48]
            else:
                # topic-like free key
                channel = SIGNAL_SPECIAL_INTEREST
                t = _topic_from_val(v) or _topic_from_val(key)
                if t and t not in topics:
                    topics.append(t)
        strength = _to_strength(v)
        if strength <= 0:
            continue
        strengths[channel] = max(strengths.get(channel, 0.0), strength)
        evidence.append(f"{channel}={strength:.2f}")
        t = _topic_from_val(v)
        if t and t not in topics and channel in (
            SIGNAL_SPECIAL_INTEREST,
            SIGNAL_STIMMING,
        ):
            topics.append(t)

    if not strengths:
        return _NEUTRAL, {}, ["no_enjoyment_signals"], []

    # Weighted average of known channels; unknown channels get small weight
    total_w = 0.0
    acc = 0.0
    for ch, st in strengths.items():
        w = float(_SIGNAL_WEIGHTS.get(ch, 0.06))
        acc += w * st
        total_w += w
    instant = acc / total_w if total_w > 0 else _NEUTRAL
    # Soft floor when only weak signals
    if max(strengths.values()) < 0.35:
        instant = min(instant, 0.45)
    return _clamp01(instant), strengths, evidence[:8], topics[:6]


def update_enjoyment_score(
    previous: EnjoymentScore | dict[str, Any] | None,
    *,
    interaction: dict[str, Any] | None = None,
    signals: dict[str, Any] | None = None,
    health_flags: list[str] | None = None,
    ethical_concern_active: bool = False,
    interaction_count: int | None = None,
    decay: float = _DEFAULT_DECAY,
    user_id: str = "default",
) -> EnjoymentScore:
    """Blend new enjoyment evidence into a time-decayed running score.

    ``score_new = decay * score_old + (1 - decay) * instant`` when evidence
    present; pure decay toward neutral when no signals this turn.
    """
    prev = (
        previous
        if isinstance(previous, EnjoymentScore)
        else EnjoymentScore.from_dict(previous if isinstance(previous, dict) else None)
    )
    decay = max(0.5, min(0.98, float(decay)))
    sig_bag = signals if isinstance(signals, dict) else None
    if sig_bag is None:
        sig_bag = extract_enjoyment_signals_from_interaction(interaction)

    instant, channel_strengths, evidence, topics = compute_instant_enjoyment(sig_bag)
    has_signal = bool(channel_strengths) and evidence != ["no_enjoyment_signals"]

    if has_signal:
        new_score = decay * float(prev.score) + (1.0 - decay) * instant
        # Mild boost when special interest / stimming clearly present (not engagement farming)
        si = channel_strengths.get(SIGNAL_SPECIAL_INTEREST, 0.0)
        stim = channel_strengths.get(SIGNAL_STIMMING, 0.0)
        if max(si, stim) >= 0.65 and channel_strengths.get(SIGNAL_CONTINUATION, 0) >= 0.4:
            new_score = min(1.0, new_score + 0.03)
        sample_count = int(prev.sample_count or 0) + 1
    else:
        # Decay toward neutral when no enjoyment evidence
        new_score = decay * float(prev.score) + (1.0 - decay) * _NEUTRAL
        sample_count = int(prev.sample_count or 0)

    # Merge preferred topics (most recent first, unique)
    preferred = list(topics)
    for t in prev.preferred_topics or []:
        if t not in preferred:
            preferred.append(t)
    preferred = preferred[:8]

    # Provenance: newest first
    evidence_full = list(evidence)
    for e in prev.evidence or []:
        if e not in evidence_full:
            evidence_full.append(e)
    evidence_full = evidence_full[:_MAX_EVIDENCE]

    ic = (
        int(interaction_count)
        if interaction_count is not None
        else int(prev.interaction_count or 0)
    )
    if interaction and interaction.get("_bond_interaction_count") is not None:
        try:
            ic = int(interaction.get("_bond_interaction_count"))
        except (TypeError, ValueError):
            pass

    result = EnjoymentScore(
        score=_clamp01(new_score),
        signals={k: _clamp01(v) for k, v in list(channel_strengths.items())[:_MAX_SIGNAL_KEYS]},
        evidence=evidence_full,
        last_updated=_utc_now_iso(),
        interaction_count=ic,
        sample_count=sample_count,
        influence_allowed=True,
        gates_applied=[],
        preferred_topics=preferred,
        forces_speech=False,
        forces_question=False,
        user_id=str(user_id or prev.user_id or "default"),
        schema_version=1,
    )
    return apply_rh_guardrails(
        result,
        health_flags=health_flags,
        ethical_concern_active=ethical_concern_active,
    )


def soft_texture_nudge_from_enjoyment(
    enjoyment: EnjoymentScore | dict[str, Any] | None,
    *,
    max_nudge: float = 0.02,
) -> dict[str, float]:
    """Tiny advisory texture deltas from high enjoyment (never large).

    Returns empty dict when influence is blocked or score is neutral.
    Only touches mutual_benefit / reciprocity lightly — never autonomy_respect
    downward, never creates dependency flags.
    """
    e = (
        enjoyment
        if isinstance(enjoyment, EnjoymentScore)
        else EnjoymentScore.from_dict(enjoyment if isinstance(enjoyment, dict) else None)
    )
    if not e.influence_allowed:
        return {}
    if e.score < 0.58 or e.sample_count < 1:
        return {}
    # Scale nudge by distance above mid-high enjoyment
    strength = min(1.0, (e.score - 0.55) / 0.45)
    n = max_nudge * strength
    if n < 0.005:
        return {}
    return {
        "mutual_benefit": round(n, 4),
        "reciprocity": round(n * 0.75, 4),
    }
