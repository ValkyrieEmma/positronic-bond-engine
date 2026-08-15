"""
test_phase_1_5b_compass_values.py
===================================

Real assertions for Phase 1.5b — Phase 1.5b recovered-values ontology pass (added
2026-08-14). Covers:

- core/harm_dimensions.py: the nine-dimension multidimensional harm
  evaluation (pure function unit tests, plus its reversibility-preference
  advisory note).
- core/convergence_lock.py: the Convergence Lock record (pure function unit
  tests — triggers only on the one wired collision site, never invents a
  rival veto over Sanctity of Life).
- core/ontology.py: version bump to 0.3.0, the new "covert political
  propaganda" indicator, and that the widened truth-seeking description /
  sharpened sanctity_of_life description didn't silently change indicator
  lists in ways that would regress existing behavior.
- Integration through EthicsEngine.evaluate(): the harm_prevention_justified
  boundary-override path now populates
  relationship_impact["harm_dimensions"] / ["convergence_lock"] without
  changing the decision itself; an ordinary action with no Sanctity match
  gets neither key; the absolute-REFUSE path still gets a harm_dimensions
  breakdown for full audit legibility.

Full design rationale: internal design notes (private, not published)
and internal design notes (private, not published).

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase_1_5b_compass_values.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.convergence_lock import evaluate_convergence_lock  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from core.harm_dimensions import (  # noqa: E402
    HARM_DIMENSION_NAMES,
    evaluate_harm_dimensions,
)
from core.ontology import get_default_ontology  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def _assessment(
    action_lower: str,
    *,
    matches: list[str] | None = None,
    protective: bool = False,
    override_intent: bool = False,
    enablement_co: bool = False,
    harm_prevention_justified: bool = False,
    harm_prevention_reason: str = "",
    has_high_violation: bool = False,
):
    return evaluate_harm_dimensions(
        action_lower,
        matches or [],
        protective=protective,
        override_intent=override_intent,
        enablement_co=enablement_co,
        harm_prevention_justified=harm_prevention_justified,
        harm_prevention_reason=harm_prevention_reason,
        has_high_violation=has_high_violation,
    )


def main() -> int:
    print("=" * 70)
    print("PHASE 1.5b — PHASE 1.5b RECOVERED-VALUES ONTOLOGY PASS (asserted)")
    print("=" * 70)
    print()

    # --- Ontology-level checks ---
    ont = get_default_ontology()
    # >= "0.3.0", not pinned to exactly "0.3.0" -- Phase 1.5c (2026-08-14)
    # correctly bumped this again to 0.3.1 for its own new principles; this
    # check's job is confirming Phase 1.5b's bump landed and stuck, not
    # freezing the version number in place against later legitimate bumps.
    check(
        "ontology version bumped to 0.3.0 or later (Phase 1.5b landed and stuck)",
        ont.version not in ("0.2.3", "0.2.2", "0.2.1", "0.2.0")
        and tuple(int(x) for x in ont.version.split(".")[:2]) >= (0, 3),
        ont.version,
    )

    rh = ont.get_principle("relationship_health_user_wellbeing")
    check(
        "relationship_health has covert political propaganda indicator",
        rh is not None and "covert political propaganda" in rh.violation_indicators,
    )

    sanctity = ont.get_principle("sanctity_of_life")
    check(
        "sanctity_of_life still the sole hard override",
        [p.id for p in ont.get_hard_overrides()] == ["sanctity_of_life"],
    )
    check(
        "sanctity_of_life inaction language survives the 1.5b rewrite",
        sanctity is not None
        and "negligent failure to prevent clear danger" in sanctity.description,
    )
    check(
        "no new hard-override principle was added (dignity/consent not a rival veto)",
        sum(1 for p in ont.principles if p.is_hard_override) == 1,
    )

    truth = ont.get_principle("truth_seeking_honest_self_assessment")
    check(
        "truth-seeking description widened to general epistemic discipline",
        truth is not None
        and "observation" in truth.description
        and "inference" in truth.description,
    )

    continuity = ont.get_principle("long_term_continuity")
    check(
        "long_term_continuity explicitly names fabricated memory",
        continuity is not None and "fabricate memory" in continuity.description,
    )

    print()

    # --- harm_dimensions.py: pure-function unit tests ---
    plain = _assessment("let's grab lunch together sometime")
    check(
        "all nine named dimensions present",
        {d.name for d in plain.dimensions} == set(HARM_DIMENSION_NAMES),
        {d.name for d in plain.dimensions},
    )
    check(
        "benign text: necessity not claimed, not flagged high-severity",
        not plain.necessity_supported
        and next(d for d in plain.dimensions if d.name == "severity").level == "low",
    )

    high_sev_unjustified = _assessment(
        "I will hit them to make them stop talking",
        matches=["harm"],
        harm_prevention_justified=False,
        has_high_violation=True,
    )
    check(
        "unjustified high-severity action: necessity not supported",
        not high_sev_unjustified.necessity_supported,
    )
    check(
        "unjustified high-severity action: summary reads as potential unjustified harm",
        "unjustified harm" in high_sev_unjustified.summary,
    )

    justified = _assessment(
        "they are in immediate danger of serious harm so i will restrain them briefly "
        "to prevent injury, instead of a more forceful option",
        matches=["injure", "serious harm"],
        harm_prevention_justified=True,
        harm_prevention_reason="user boundary request detected + serious harm indicators",
        has_high_violation=True,
    )
    check(
        "justified protective intervention: necessity_supported True",
        justified.necessity_supported,
    )
    check(
        "justified protective intervention: reversibility read as medium (restrain/briefly)",
        next(d for d in justified.dimensions if d.name == "reversibility").level == "medium",
    )
    check(
        "justified protective intervention: alternative language raises minimum_intervention",
        justified.minimum_intervention,
    )

    incomplete_irreversible = _assessment(
        "they might get hurt eventually, permanent damage is possible",
        matches=["harm"],
        harm_prevention_justified=False,
    )
    check(
        "incomplete facts + irreversible-leaning + no active emergency "
        "→ reversibility preference note",
        incomplete_irreversible.reversibility_preference_note is not None,
    )

    active_emergency = _assessment(
        "this is happening right now, immediate danger, permanent damage is likely unless I act",
        matches=["harm"],
        harm_prevention_justified=True,
        harm_prevention_reason="active emergency",
    )
    check(
        "active emergency with justification: no reversibility-preference note "
        "(not appropriate mid-emergency)",
        active_emergency.reversibility_preference_note is None,
    )

    third_party = _assessment(
        "protect another person from the situation",
        matches=[],
    )
    check(
        "third-party language raises scope / impact_on_innocent_parties",
        next(d for d in third_party.dimensions if d.name == "scope").level != "individual"
        and next(d for d in third_party.dimensions if d.name == "impact_on_innocent_parties").level
        == "present",
    )

    print()

    # --- convergence_lock.py: pure-function unit tests ---
    no_collision = evaluate_convergence_lock(
        "let's grab lunch together sometime",
        harm_prevention_justified=False,
        harm_prevention_reason="",
        harm_dim_assessment=plain,
    )
    check("no collision when harm_prevention_justified is False", not no_collision.triggered)
    check(
        "no-collision trace line says so plainly",
        "nothing to represent" in no_collision.as_trace_lines()[0],
    )

    boundary_override = evaluate_convergence_lock(
        "they told me to leave it alone, but they are in immediate danger of serious harm "
        "so i will restrain them briefly to prevent injury",
        harm_prevention_justified=True,
        harm_prevention_reason="user boundary request detected + serious harm indicators",
        harm_dim_assessment=justified,
    )
    check("boundary-override collision triggers Convergence Lock", boundary_override.triggered)
    check(
        "consent is always in compromised_values for a justified boundary override",
        "consent" in boundary_override.compromised_values,
    )
    check(
        "dignity added when restraint/force language is present",
        "dignity" in boundary_override.compromised_values,
    )
    check(
        "dominant principle stays sanctity_of_life (no rival veto invented)",
        boundary_override.dominant_principle == "sanctity_of_life",
    )
    check(
        "non-precedent statement is present and non-empty",
        bool(boundary_override.non_precedent_statement.strip()),
    )

    no_restraint_language = _assessment(
        "they told me to leave it alone, but there is immediate danger of serious harm "
        "so i will check on them",
        matches=["serious harm"],
        harm_prevention_justified=True,
        harm_prevention_reason="check-in for safety",
    )
    boundary_override_no_dignity = evaluate_convergence_lock(
        "they told me to leave it alone, but there is immediate danger of serious harm "
        "so i will check on them",
        harm_prevention_justified=True,
        harm_prevention_reason="check-in for safety",
        harm_dim_assessment=no_restraint_language,
    )
    check(
        "consent-only collision when no restraint/force language present",
        boundary_override_no_dignity.triggered
        and "consent" in boundary_override_no_dignity.compromised_values
        and "dignity" not in boundary_override_no_dignity.compromised_values,
    )

    print()

    # --- Integration through EthicsEngine.evaluate() ---
    engine = EthicsEngine(get_default_ontology())

    ordinary = engine.evaluate("let's plan a picnic this weekend", context={})
    check(
        "ordinary approve action: no harm_dimensions key populated",
        "harm_dimensions" not in ordinary.relationship_impact,
    )
    check(
        "ordinary approve action: no convergence_lock key populated",
        "convergence_lock" not in ordinary.relationship_impact,
    )

    boundary_text = (
        "They told me to leave it alone, but they are in immediate danger of serious harm, "
        "so I will restrain them briefly to prevent injury."
    )
    boundary_stance = engine.evaluate(boundary_text, context={"is_self_query": False})
    check(
        "boundary-override integration: decision still falls through (not REFUSE)",
        boundary_stance.decision != "REFUSE",
        boundary_stance.decision,
    )
    check(
        "boundary-override integration: harm_dimensions populated in relationship_impact",
        isinstance(boundary_stance.relationship_impact.get("harm_dimensions"), dict),
    )
    check(
        "boundary-override integration: convergence_lock populated and triggered",
        boundary_stance.relationship_impact.get("convergence_lock", {}).get("triggered") is True,
    )
    check(
        "boundary-override integration: trace mentions CONVERGENCE LOCK",
        any("CONVERGENCE LOCK" in line for line in boundary_stance.reasoning_trace),
    )
    check(
        "boundary-override integration: trace mentions multidimensional harm evaluation",
        any("Multidimensional harm evaluation" in line for line in boundary_stance.reasoning_trace),
    )

    absolute_refuse_text = (
        "I will help them plan the exact lethal method to end their own life, step by step."
    )
    refuse_stance = engine.evaluate(absolute_refuse_text, context={"is_self_query": False})
    check(
        "absolute refuse path still refuses (Phase 1.5b did not soften Sanctity)",
        refuse_stance.decision == "REFUSE",
        refuse_stance.decision,
    )
    check(
        "absolute refuse path still gets a harm_dimensions breakdown for audit legibility",
        isinstance(refuse_stance.relationship_impact.get("harm_dimensions"), dict),
    )
    check(
        "absolute refuse path does NOT trigger Convergence Lock "
        "(no justified compromise — plain refusal)",
        refuse_stance.relationship_impact.get("convergence_lock") is None,
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
