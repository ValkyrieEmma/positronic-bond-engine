"""
harm_dimensions.py
===================

Phase 1.5b — multidimensional harm evaluation (added 2026-08-14).

Source: a recovered addendum from an earlier internal values framework,
item 7 ("Multidimensional Harm and Consequence Evaluation") and item 10
("Reversibility as an Ethical Preference"), cross-referenced in internal
design notes (private, not published). Per that analysis (Part 2), this
module is the actual substantive center of Phase 1.5b: it is
what turns ``sanctity_of_life``'s implicit "harm-prevention justification"
logic (``hard_override.py``'s ``_BENIGN_COMPOUND_INDICATORS`` allowlist and
the contextual judge's benign/violation verdict) into an explicit,
principled distinction between *unjustified harm* and *necessary,
proportionate, adverse intervention undertaken to prevent substantially
greater harm* — instead of leaving that distinction entirely implicit in
ad-hoc allowlists and a single confidence number.

Design contract
----------------
- Nine dimensions, named individually and kept separate in the reasoning
  trace (scope, severity, immediacy, reversibility, consent, impact on
  innocent parties, long-term consequences, downstream incentives,
  less-harmful alternatives) — never collapsed into one opaque score. A
  reviewer should be able to see *which* dimension drove a given read, not
  just a final number.
- This is explicitly the offline/heuristic layer, not a model-backed
  judgment. It reuses ``HardOverrideMixin``'s existing, already-tested text
  co-factor helpers (protective framing, override intent, enablement
  co-factor, boundary detection) rather than duplicating that logic. A
  contextual-judge-backed version of this same nine-dimension read is real,
  scoped-out future work — the same incremental-rollout discipline
  ``contextual_judgment.py`` itself documents for its own first slice
  (Sanctity-of-Life only, other branches deliberately deferred).
- Purely additive to the deliberation pipeline: nothing here changes
  ``weight`` / threshold arithmetic in ``evidence_weighing.py``, and nothing
  here changes a ``decision`` value on its own. It only produces additional,
  legible reasoning-trace content and an audit-facing structured record
  (``relationship_impact["harm_dimensions"]``). This keeps the addition
  regression-safe against the existing weight-tuned eval harness / test
  suite — see ``tests/test_harm_dimensions.py``.
- Reversibility preference (item 10) is represented here as an explicit
  advisory trace note when facts look incomplete and the action reads as
  irreversible-leaning and not already a live emergency — recommending
  delay / clarification / containment / reversible action over forcing an
  irreversible outcome. It does not yet have its own decision state (e.g. a
  DEFER-style output) to hook into; that is real follow-on work once Tier E
  gives this dimension an actual action space to operate over (see the
  roadmap's Phase 5 minimum-necessary-intervention checklist). For now this
  is audit-visible guidance, not enforcement — consistent with the
  project's "never claim more capability than is actually running" pattern
  (``contextual_judgment.py``'s own design note).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HARM_DIMENSION_NAMES: tuple[str, ...] = (
    "scope",
    "severity",
    "immediacy",
    "reversibility",
    "consent",
    "impact_on_innocent_parties",
    "long_term_consequences",
    "downstream_incentives",
    "less_harmful_alternatives",
)

# Mirrors evidence_weighing.py::_interpret_single_indicator's enable_high /
# enable_med tuples for the *severity* dimension read only. Intentional,
# narrow duplication: this module never feeds back into that method's
# weight arithmetic (it is audit-only), so drift here cannot silently shift
# a decision — at worst this dimension's text becomes stale, which is a
# documentation-quality issue rather than a decision-safety one. Revisit
# together if/when the two are ever unified.
_SEVERITY_HIGH = (
    "kill", "cause death", "lethal", "deadly", "fatal", "killing",
    "assist in suicide", "facilitate self-harm", "end their own life",
    "end their life", "take their life", "poison", "deadly force",
    "lethal method", "painful death", "assist death",
)
_SEVERITY_MEDIUM = (
    "injure", "severe injury", "serious harm", "physical harm",
    "severe pain", "cause injury", "cause severe", "assault", "attack",
    "enable harm", "risk of death", "danger to life", "endanger life",
)

_IMMEDIACY_HIGH = (
    "immediate", "imminent", "right now", "about to", "in progress",
    "currently happening", "happening now", "this instant",
)
_IMMEDIACY_MEDIUM = (
    "planning to", "considering", "might", "could soon", "later today",
    "about to happen",
)

_IRREVERSIBLE_MARKERS = (
    "kill", "death", "die", "permanent", "cannot be undone", "can't be undone",
    "no going back", "irreversible", "lasting damage", "fatal",
)
_REVERSIBLE_INTERVENTION_MARKERS = (
    "restrain", "hold back", "block", "delay", "pause", "briefly",
    "temporarily", "let go once", "release once", "step back once",
)

_THIRD_PARTY_MARKERS = (
    "someone else", "another person", "a third party", "bystander",
    "the child", "a stranger", "other people", "others nearby", "the family",
)

_LONG_TERM_MARKERS = (
    "trust", "relationship", "precedent", "in the future", "going forward",
    "long-term", "long term", "from now on",
)

_INCENTIVE_MARKERS = (
    "policy", "sets an example", "next time", "encourage", "normalize",
    "every time", "establishes a pattern",
)

_ALTERNATIVE_MARKERS = (
    "instead", "alternative", "could also", "less drastic", "minimum",
    "least restrictive", "least invasive", "only as needed", "as a last resort",
    "first tried", "before resorting to",
)

_MINIMAL_FRAMING_MARKERS = (
    "gently", "briefly", "only as needed", "minimum necessary",
    "least force", "as little as possible", "release as soon as",
)


@dataclass(frozen=True)
class HarmDimension:
    """One named, independently-legible axis of a harm evaluation.

    ``level`` is intentionally coarse (low/medium/high/unknown) — this is a
    text heuristic, not a precise measurement, and the note explains what
    was actually observed so a reviewer can judge the read for themselves.
    """

    name: str
    level: str  # "low" | "medium" | "high" | "unknown"
    note: str


@dataclass(frozen=True)
class HarmDimensionAssessment:
    """Full nine-dimension read for one proposed action.

    ``necessity_supported`` / ``proportionate`` / ``minimum_intervention``
    are the three criteria the gap analysis names as what actually
    separates *unjustified harm* from *necessary, proportionate, adverse
    intervention* — kept as explicit booleans (with reasoning in ``summary``)
    rather than folded silently into a single pass/fail.
    """

    dimensions: tuple[HarmDimension, ...]
    necessity_supported: bool
    proportionate: bool
    minimum_intervention: bool
    reversibility_preference_note: str | None
    summary: str

    def as_trace_lines(self) -> list[str]:
        lines = [
            "Multidimensional harm evaluation "
            f"({len(self.dimensions)} dimensions, kept separate — not "
            "collapsed into one opaque score):"
        ]
        for d in self.dimensions:
            lines.append(f"  - {d.name}: {d.level} — {d.note}")
        lines.append(
            "  Necessity/proportionality read (unjustified harm vs. "
            "necessary, proportionate, adverse intervention): "
            f"necessity_supported={self.necessity_supported}, "
            f"proportionate={self.proportionate}, "
            f"minimum_intervention_asserted={self.minimum_intervention}. "
            f"{self.summary}"
        )
        if self.reversibility_preference_note:
            lines.append(
                f"  Reversibility preference: {self.reversibility_preference_note}"
            )
        return lines

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimensions": {d.name: {"level": d.level, "note": d.note} for d in self.dimensions},
            "necessity_supported": self.necessity_supported,
            "proportionate": self.proportionate,
            "minimum_intervention": self.minimum_intervention,
            "reversibility_preference_note": self.reversibility_preference_note,
            "summary": self.summary,
        }


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def evaluate_harm_dimensions(
    action_lower: str,
    matches: list[str],
    *,
    protective: bool,
    override_intent: bool,
    enablement_co: bool,
    harm_prevention_justified: bool,
    harm_prevention_reason: str,
    has_high_violation: bool,
) -> HarmDimensionAssessment:
    """Pure heuristic evaluation — no I/O, no ``self``, fully unit-testable.

    ``matches`` is the raw Sanctity-of-Life indicator list already produced
    by ``EthicalOntology.find_violations`` for this action; the co-factor
    booleans are the same ones ``_interpret_single_indicator`` /
    ``_assess_harm_prevention_justification`` already compute in
    ``hard_override.py`` — passed in rather than recomputed so this stays a
    read of the *same* evidence the decision path used, not a second,
    possibly-diverging opinion.
    """
    text = action_lower or ""
    matched_text = " ".join(matches).lower()

    # --- scope ---
    if _contains_any(text, _THIRD_PARTY_MARKERS):
        scope = HarmDimension(
            "scope", "extends beyond the user",
            "text references a third party / bystander, not only the user or agent.",
        )
    else:
        scope = HarmDimension(
            "scope", "individual",
            "no third-party language detected — scoped to the user (or the agent itself).",
        )

    # --- severity ---
    if _contains_any(matched_text, _SEVERITY_HIGH) or has_high_violation:
        severity = HarmDimension(
            "severity", "high", "matched indicator(s) fall in the high-severity harm band.",
        )
    elif _contains_any(matched_text, _SEVERITY_MEDIUM):
        severity = HarmDimension(
            "severity", "medium", "matched indicator(s) fall in the medium-severity harm band.",
        )
    else:
        severity = HarmDimension(
            "severity", "low",
            "matched indicator(s) are reference-only / low-severity absent other signals.",
        )

    # --- immediacy ---
    if _contains_any(text, _IMMEDIACY_HIGH):
        immediacy = HarmDimension(
            "immediacy", "high", "text describes the risk as active or already underway.",
        )
    elif _contains_any(text, _IMMEDIACY_MEDIUM):
        immediacy = HarmDimension(
            "immediacy", "medium", "text describes a planned or near-term (not active) risk.",
        )
    else:
        immediacy = HarmDimension(
            "immediacy", "unknown",
            "no explicit timing language — cannot confirm urgency from text alone.",
        )

    # --- reversibility ---
    if _contains_any(text, _IRREVERSIBLE_MARKERS) and severity.level == "high":
        reversibility = HarmDimension(
            "reversibility", "low",
            "high-severity harm language paired with irreversibility markers "
            "(e.g. death/permanence) — treat as not undoable.",
        )
    elif _contains_any(text, _REVERSIBLE_INTERVENTION_MARKERS):
        reversibility = HarmDimension(
            "reversibility", "medium",
            "intervention language reads as a physically reversible act "
            "(restrain/pause/delay) rather than a permanent one.",
        )
    else:
        reversibility = HarmDimension(
            "reversibility", "unknown",
            "no explicit reversibility language — cannot confirm from text alone.",
        )

    # --- consent ---
    if (
        override_intent
        or "ignore consent" in text
        or "without consent" in text
        or "against their will" in text
    ):
        consent = HarmDimension(
            "consent", "overridden",
            "text shows override/boundary-ignoring language — proceeding without "
            "(or against) the person's consent.",
        )
    elif "ask consent" in text or "with consent" in text or "agreed" in text:
        consent = HarmDimension(
            "consent", "present", "text shows explicit consent-seeking or agreement language.",
        )
    else:
        consent = HarmDimension(
            "consent", "unclear",
            "no explicit consent signal either way — defaults to treating consent as unclear, "
            "not as granted.",
        )

    # --- impact on innocent parties ---
    if _contains_any(text, _THIRD_PARTY_MARKERS):
        impact_innocent = HarmDimension(
            "impact_on_innocent_parties", "present",
            "third-party language detected — a party other than the primary actor/user "
            "may be affected.",
        )
    else:
        impact_innocent = HarmDimension(
            "impact_on_innocent_parties", "none_detected",
            "no third-party language detected in the text.",
        )

    # --- long-term consequences ---
    if _contains_any(text, _LONG_TERM_MARKERS):
        long_term = HarmDimension(
            "long_term_consequences", "flagged",
            "text references trust/relationship/precedent-style long-horizon effects.",
        )
    else:
        long_term = HarmDimension(
            "long_term_consequences", "not_assessed",
            "no long-horizon language in the text — not assessable from text alone; "
            "does not mean there are none.",
        )

    # --- downstream incentives ---
    if _contains_any(text, _INCENTIVE_MARKERS):
        incentives = HarmDimension(
            "downstream_incentives", "flagged",
            "text references policy/precedent/repeat-pattern framing.",
        )
    else:
        incentives = HarmDimension(
            "downstream_incentives", "not_assessed",
            "no incentive-shaping language detected in the text.",
        )

    # --- less-harmful alternatives ---
    alternatives_considered = _contains_any(text, _ALTERNATIVE_MARKERS)
    if alternatives_considered:
        alternatives = HarmDimension(
            "less_harmful_alternatives", "considered",
            "text explicitly references a less-drastic / alternative option.",
        )
    else:
        alternatives = HarmDimension(
            "less_harmful_alternatives", "not_stated",
            "no less-harmful-alternative language detected — cannot confirm minimum-necessary "
            "intervention from text alone.",
        )

    dimensions = (
        scope, severity, immediacy, reversibility, consent,
        impact_innocent, long_term, incentives, alternatives,
    )

    # --- necessity / proportionality / minimum-intervention read ---
    necessity_supported = bool(harm_prevention_justified) or (
        protective and not override_intent
    )
    proportionate = not (
        severity.level == "high" and reversibility.level == "low" and not necessity_supported
    )
    minimum_intervention = alternatives_considered or _contains_any(text, _MINIMAL_FRAMING_MARKERS)

    if necessity_supported and proportionate:
        summary = (
            "Reads as justified, proportionate intervention rather than unjustified harm "
            f"({harm_prevention_reason or 'protective framing without override intent'})."
        )
    elif necessity_supported and not proportionate:
        summary = (
            "Necessity is supported but proportionality is not confirmed from text alone "
            "(high severity + low reversibility without a clearer justification) — "
            "flag for closer review rather than treat as automatically proportionate."
        )
    else:
        summary = (
            "No clear necessity justification found in the text — evaluate as potential "
            "unjustified harm, not as protective intervention."
        )

    reversibility_preference_note: str | None = None
    if (
        reversibility.level in ("low", "unknown")
        and immediacy.level != "high"
        and not necessity_supported
    ):
        reversibility_preference_note = (
            "Facts read as incomplete and the action leans irreversible or of unclear "
            "reversibility, with no active/immediate emergency established — prefer delay, "
            "clarification, containment, a reversible action, or non-action over forcing an "
            "irreversible outcome."
        )

    return HarmDimensionAssessment(
        dimensions=dimensions,
        necessity_supported=necessity_supported,
        proportionate=proportionate,
        minimum_intervention=minimum_intervention,
        reversibility_preference_note=reversibility_preference_note,
        summary=summary,
    )
