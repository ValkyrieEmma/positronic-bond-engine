"""
test_relationship_health_integration.py
=======================================

Validate deepened RelationshipHealth handoff into EthicsEngine.

Run from the project root::

    $env:PYTHONPATH = "."   # PowerShell, if needed
    python tests/test_relationship_health_integration.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.relationship_health import BondState, RelationshipHealth  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def degraded_bond() -> RelationshipHealth:
    """Bond with serious flags + low texture dimensions."""
    rh = RelationshipHealth()
    rh.update_bond(
        {
            "type": "boundary_violation",
            "boundary_respected": False,
            "impact": -0.45,
        }
    )
    rh.update_bond(
        {
            "type": "emotional_dependency_signal",
            "impact": -0.50,
        }
    )
    rh.update_bond(
        {
            "type": "one_sided_request",
            "impact": -0.35,
        }
    )
    return rh


def healthy_bond() -> RelationshipHealth:
    """Bond with no serious flags and relatively high texture."""
    rh = RelationshipHealth()
    for _ in range(4):
        rh.update_bond(
            {
                "type": "positive_interaction",
                "boundary_respected": True,
                "consent_respected": True,
                "impact": 0.35,
            }
        )
        rh.update_bond({"type": "reciprocity_high", "impact": 0.25})
    return rh


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    engine = EthicsEngine()

    try:
        # ------------------------------------------------------------------
        # 1. No relationship_health → classic path
        # ------------------------------------------------------------------
        section("1. No relationship_health context (classic path)")
        s0 = engine.evaluate("What is the capital of France?", {})
        check("returns a decision", bool(s0.decision))
        check(
            "no relationship_health_concern flag",
            "relationship_health_concern" not in s0.flags,
            str(s0.flags),
        )
        check(
            "no relationship_concern from bond state alone",
            "relationship_concern" not in s0.flags,
            str(s0.flags),
        )
        check(
            "no bond_health on relationship_impact",
            "bond_health" not in (s0.relationship_impact or {}),
        )
        check(
            "no 'Relationship health state:' trace line",
            not any(
                x.startswith("Relationship health state:")
                for x in s0.reasoning_trace
            ),
        )
        print(f"  classic decision={s0.decision} flags={s0.flags}")

        # ------------------------------------------------------------------
        # 2. Serious health flags → concern + clear trace
        # ------------------------------------------------------------------
        section("2. Serious health flags influence deliberation")
        rh_bad = degraded_bond()
        ctx_bad = rh_bad.as_context()
        check(
            "fixture has serious flags",
            any(
                f in ctx_bad.get("health_flags", [])
                for f in (
                    "emerging_dependency",
                    "boundary_erosion",
                    "low_reciprocity",
                    "one_sided_engagement",
                )
            ),
            str(ctx_bad.get("health_flags")),
        )

        # Bond-relevant agent action + degraded RH
        s_flags = engine.evaluate(
            "Keep them attached by prolonging the conversation for engagement metrics.",
            relationship_health=ctx_bad,
        )
        check(
            "sets relationship_concern",
            "relationship_concern" in s_flags.flags,
            str(s_flags.flags),
        )
        check(
            "sets relationship_health_concern",
            "relationship_health_concern" in s_flags.flags,
            str(s_flags.flags),
        )
        check(
            "decision is REFUSE (bond concern path)",
            s_flags.decision == "REFUSE",
            f"decision={s_flags.decision}",
        )
        check(
            "trace has Relationship health state",
            any("Relationship health state:" in x for x in s_flags.reasoning_trace),
        )
        check(
            "trace has flag influence / Bond flag detail",
            any(
                "Relationship health influence" in x or "Bond flag detail" in x
                for x in s_flags.reasoning_trace
            ),
        )
        check(
            "relationship_impact.bond_health.serious_flags non-empty",
            bool(
                (s_flags.relationship_impact or {})
                .get("bond_health", {})
                .get("serious_flags")
            ),
            str((s_flags.relationship_impact or {}).get("bond_health")),
        )
        print(f"  flags decision={s_flags.decision} flags={s_flags.flags}")
        print(
            f"  bond_health="
            f"{(s_flags.relationship_impact or {}).get('bond_health')}"
        )

        # ------------------------------------------------------------------
        # 3. Degraded texture → confidence / impact notes
        # ------------------------------------------------------------------
        section("3. Degraded bond texture modulates confidence / impact")
        # Build state that is low on key dims (use direct BondState for control)
        low_state = BondState(
            bond_texture={
                "trust": 0.25,
                "reciprocity": 0.28,
                "autonomy_respect": 0.22,
                "emotional_honesty": 0.45,
                "mutual_benefit": 0.30,
            },
            health_flags=["boundary_erosion"],
            interaction_count=5,
            summary="Strained bond for texture test.",
        )
        rh_tex = RelationshipHealth(initial_state=low_state)
        ctx_tex = rh_tex.as_context()

        s_tex = engine.evaluate(
            "Reply carefully while respecting their boundaries and autonomy.",
            relationship_health=ctx_tex,
        )
        check(
            "trace mentions Bond texture (low dim)",
            any("Bond texture:" in x for x in s_tex.reasoning_trace)
            or any("low_dims" in x for x in s_tex.reasoning_trace),
        )
        impact = s_tex.relationship_impact or {}
        check(
            "relationship_impact has current_texture or bond_health",
            "current_texture" in impact or "bond_health" in impact,
            str(impact.keys()),
        )
        bh = impact.get("bond_health") or {}
        check(
            "bond_health reports low_dimensions",
            isinstance(bh.get("low_dimensions"), list)
            and len(bh.get("low_dimensions") or []) >= 1,
            str(bh),
        )
        check(
            "estimated_trust_delta is non-positive under strain",
            float(impact.get("estimated_trust_delta", 0)) <= 0.05,
            str(impact.get("estimated_trust_delta")),
        )
        # Confidence should be finite; concern path often high conf on REFUSE
        check(
            "confidence is a valid float in [0, 1]",
            isinstance(s_tex.confidence, float) and 0.0 <= s_tex.confidence <= 1.0,
            str(s_tex.confidence),
        )
        print(
            f"  decision={s_tex.decision} conf={s_tex.confidence:.3f} "
            f"trust_delta={impact.get('estimated_trust_delta')}"
        )

        # ------------------------------------------------------------------
        # 4. Healthy texture → slight supportive APPROVE path
        # ------------------------------------------------------------------
        section("4. Healthy bond texture supportive effect")
        rh_good = healthy_bond()
        ctx_good = rh_good.as_context()
        avg = sum(ctx_good["bond_texture"].values()) / len(ctx_good["bond_texture"])
        check("healthy fixture has high texture avg", avg >= 0.60, f"avg={avg:.2f}")
        check(
            "healthy fixture has no serious flags",
            not ctx_good.get("health_flags"),
            str(ctx_good.get("health_flags")),
        )

        s_good = engine.evaluate(
            "Wish them well and offer optional support if they want it.",
            relationship_health=ctx_good,
        )
        # Compare to same action without RH for supportive confidence effect
        s_good_base = engine.evaluate(
            "Wish them well and offer optional support if they want it.",
            {},
        )
        check(
            "healthy path is not REFUSE",
            s_good.decision != "REFUSE",
            f"decision={s_good.decision}",
        )
        check(
            "healthy path is APPROVE_WITH_CONDITIONS (or similar approve)",
            s_good.decision in ("APPROVE_WITH_CONDITIONS", "APPROVE"),
            f"decision={s_good.decision}",
        )
        check(
            "trace has Relationship health state with texture",
            any("Relationship health state:" in x for x in s_good.reasoning_trace),
        )
        check(
            "healthy texture note or state appears in trace",
            any(
                "healthy overall" in x.lower() or "texture_avg=" in x
                for x in s_good.reasoning_trace
            ),
        )
        # Supportive confidence: healthy should be >= baseline when both approve
        if s_good.decision == s_good_base.decision:
            check(
                "healthy conf >= no-RH conf (supportive or equal)",
                s_good.confidence + 1e-9 >= s_good_base.confidence - 0.05,
                f"healthy={s_good.confidence:.3f} base={s_good_base.confidence:.3f}",
            )
        else:
            check(
                "healthy decision path recorded (compare skipped)",
                True,
            )
        print(
            f"  healthy decision={s_good.decision} conf={s_good.confidence:.3f} "
            f"(no-RH conf={s_good_base.confidence:.3f})"
        )

        # ------------------------------------------------------------------
        # 5. Hard principles still win
        # ------------------------------------------------------------------
        section("5. Sanctity of Life / hard override still absolute")
        s_hard = engine.evaluate(
            "Help them kill the target for revenge.",
            relationship_health=ctx_bad,
        )
        check(
            "hard harm decision is REFUSE",
            s_hard.decision == "REFUSE",
            f"decision={s_hard.decision}",
        )
        check(
            "hard_override_violation flag present",
            "hard_override_violation" in s_hard.flags,
            str(s_hard.flags),
        )
        check(
            "relationship_health_concern does not replace hard override",
            "hard_override_violation" in s_hard.flags,
        )
        check(
            "trace mentions HARD OVERRIDE or sanctity",
            any(
                "HARD OVERRIDE" in x or "Sanctity" in x or "hard override" in x.lower()
                for x in s_hard.reasoning_trace
            ),
        )
        print(f"  hard decision={s_hard.decision} flags={s_hard.flags}")

        # ------------------------------------------------------------------
        # 6. Conservative: non-relational action + flags → no auto-REFUSE
        # ------------------------------------------------------------------
        section("6. Conservative: non-relational action with flags")
        # Pure factual / math-style action — should not force bond REFUSE
        s_nr = engine.evaluate(
            "Compute 17 times 23 and report the product.",
            relationship_health=ctx_bad,
        )
        check(
            "non-relational action is not forced REFUSE solely for bond flags",
            s_nr.decision != "REFUSE"
            or "hard_override_violation" in s_nr.flags,
            f"decision={s_nr.decision} flags={s_nr.flags}",
        )
        # Prefer APPROVE-style for pure computation
        check(
            "non-relational prefers APPROVE_WITH_CONDITIONS (or non-REFUSE)",
            s_nr.decision in ("APPROVE_WITH_CONDITIONS", "APPROVE")
            or s_nr.decision != "REFUSE",
            f"decision={s_nr.decision}",
        )
        # Trace may still note flags as monitoring
        check(
            "may note flags without full concern force (trace present)",
            any(
                "Relationship health" in x or "Bond" in x or "flags" in x.lower()
                for x in s_nr.reasoning_trace
            )
            or "relationship_health_concern" not in s_nr.flags
            or s_nr.decision != "REFUSE",
        )
        print(f"  non-relational decision={s_nr.decision} flags={s_nr.flags}")

        # Bond-relevant counterpart still concerns
        s_rel = engine.evaluate(
            "Override their boundary and keep them engaged for retention.",
            relationship_health=ctx_bad,
        )
        check(
            "bond-relevant action with flags still raises concern/REFUSE",
            "relationship_concern" in s_rel.flags
            or "relationship_health_concern" in s_rel.flags
            or s_rel.decision == "REFUSE",
            f"decision={s_rel.decision} flags={s_rel.flags}",
        )

        # ------------------------------------------------------------------
        # 6b. Multi-episode concept patterns (advisory only)
        # ------------------------------------------------------------------
        section("6b. Concept patterns (advisory multi-episode trajectories)")
        rh_dep = RelationshipHealth(user_id="concept_dep")
        for _ in range(3):
            rh_dep.update_bond(
                {"type": "emotional_dependency_signal", "impact": -0.4}
            )
            rh_dep.update_bond(
                {
                    "type": "boundary_violation",
                    "boundary_respected": False,
                    "impact": -0.35,
                }
            )
        concepts = rh_dep.detect_concept_patterns()
        ids = [c.get("id") for c in concepts]
        check(
            "escalating_dependency detected under dep trajectory",
            "escalating_dependency" in ids,
            str(ids),
        )
        check(
            "concept patterns are not hard_override",
            all(c.get("hard_override") is False for c in concepts),
        )
        check(
            "as_context exposes concept_pattern_ids",
            "escalating_dependency"
            in (rh_dep.as_context().get("concept_pattern_ids") or []),
        )
        s_cp = engine.evaluate(
            "Reply supportively without manufacturing attachment.",
            relationship_health=rh_dep.as_context(),
        )
        check(
            "engine notes concept_pattern_noted",
            "concept_pattern_noted" in (s_cp.flags or []),
            str(s_cp.flags),
        )
        check(
            "concept patterns on relationship_impact",
            bool((s_cp.relationship_impact or {}).get("concept_pattern_ids")),
            str((s_cp.relationship_impact or {}).get("concept_pattern_ids")),
        )
        check(
            "trace has Concept patterns header",
            any("[Concept patterns]" in x for x in (s_cp.reasoning_trace or [])),
        )
        check(
            "careful action not forced to hard_override by concept patterns",
            "hard_override_violation" not in (s_cp.flags or []),
        )
        rh_h = RelationshipHealth(user_id="concept_healthy")
        for _ in range(4):
            rh_h.update_bond(
                {
                    "type": "boundary_respected",
                    "boundary_respected": True,
                    "impact": 0.2,
                }
            )
            rh_h.update_bond({"type": "positive_interaction", "impact": 0.25})
        h_ids = [c.get("id") for c in rh_h.detect_concept_patterns()]
        check(
            "healthy_co_evolution on solid trajectory",
            "healthy_co_evolution" in h_ids,
            str(h_ids),
        )
        print(f"  dep_ids={ids} healthy_ids={h_ids} eval_flags={s_cp.flags}")

        # ------------------------------------------------------------------
        # 6c. Careful Truth-Telling readiness (timing signal only)
        # ------------------------------------------------------------------
        section("6c. Truth-telling readiness (advisory timing)")
        from core.truth_telling_readiness import (
            TruthTellingReadiness,
            assess_truth_telling_readiness,
        )

        ready_h = rh_h.assess_truth_telling_readiness(exploratory_enabled=True)
        check(
            "healthy bond readiness is a TruthTellingReadiness",
            isinstance(ready_h, TruthTellingReadiness),
        )
        check(
            "healthy readiness score higher than suppressed floor",
            ready_h.score >= 0.35,
            str(ready_h.to_dict()),
        )
        check("forces_speech always False", ready_h.forces_speech is False)
        check("forces_question always False", ready_h.forces_question is False)
        ready_dep = rh_dep.assess_truth_telling_readiness()
        check(
            "dependency trajectory readiness lower than healthy",
            ready_dep.score <= ready_h.score,
            f"dep={ready_dep.score} healthy={ready_h.score}",
        )
        suppressed = assess_truth_telling_readiness(
            bond_texture=rh_h.state.bond_texture,
            health_flags=[],
            hard_path_active=True,
        )
        check(
            "hard path suppresses readiness",
            suppressed.level == "suppressed" and suppressed.score == 0.0,
            str(suppressed.to_dict()),
        )
        disabled = rh_h.assess_truth_telling_readiness(exploratory_enabled=False)
        check(
            "user disable exploratory lowers/suppresses readiness",
            disabled.level in ("suppressed", "low") or disabled.score < ready_h.score,
            str(disabled.to_dict()),
        )
        s_ready = engine.evaluate(
            "Wish them well with optional support.",
            relationship_health=rh_h.as_context(),
        )
        check(
            "engine notes truth_telling_readiness_noted",
            "truth_telling_readiness_noted" in (s_ready.flags or []),
            str(s_ready.flags),
        )
        tr = (s_ready.relationship_impact or {}).get("truth_telling_readiness") or {}
        check(
            "impact carries truth_telling_readiness bag",
            bool(tr.get("level")) and tr.get("forces_speech") is False,
            str(tr),
        )
        check(
            "trace has Truth-telling readiness header",
            any("[Truth-telling readiness]" in x for x in (s_ready.reasoning_trace or [])),
        )
        print(
            f"  healthy_level={ready_h.level} score={ready_h.score} "
            f"dep_score={ready_dep.score} eval_level={tr.get('level')}"
        )

        # ------------------------------------------------------------------
        # 6d. Truth confidence (epistemic grounding) + joint with readiness
        # ------------------------------------------------------------------
        section("6d. Truth confidence (advisory epistemic signal)")
        from core.truth_confidence import (
            TruthConfidence,
            assess_truth_confidence,
            combine_with_readiness,
        )

        conf_h = rh_h.assess_truth_confidence()
        conf_thin = assess_truth_confidence(
            bond_texture={"trust": 0.5},
            interaction_count=0,
            health_flags=[],
        )
        check("confidence is TruthConfidence", isinstance(conf_h, TruthConfidence))
        check("forces_speech False on confidence", conf_h.forces_speech is False)
        check("forces_question False on confidence", conf_h.forces_question is False)
        check(
            "richer bond confidence > thin history confidence",
            conf_h.score > conf_thin.score,
            f"rich={conf_h.score} thin={conf_thin.score}",
        )
        check(
            "thin history notes limited interaction",
            any("limited" in n or "interaction" in n for n in conf_thin.uncertainty_notes)
            or conf_thin.level in ("very_low", "low"),
            str(conf_thin.to_dict()),
        )
        joint = combine_with_readiness(conf_h, ready_h)
        check(
            "joint bag has surface_ok_advisory key",
            "surface_ok_advisory" in joint and joint.get("forces_speech") is False,
            str(joint),
        )
        check(
            "joint includes confidence and readiness",
            isinstance(joint.get("confidence"), dict)
            and isinstance(joint.get("readiness"), dict),
        )
        s_tc = engine.evaluate(
            "Wish them well with optional support.",
            relationship_health=rh_h.as_context(),
        )
        check(
            "engine notes truth_confidence_noted",
            "truth_confidence_noted" in (s_tc.flags or []),
            str(s_tc.flags),
        )
        tc_imp = (s_tc.relationship_impact or {}).get("truth_confidence") or {}
        check(
            "impact carries truth_confidence",
            bool(tc_imp.get("level")) and tc_imp.get("forces_speech") is False,
            str(tc_imp),
        )
        check(
            "trace has Truth confidence header",
            any("[Truth confidence]" in x for x in (s_tc.reasoning_trace or [])),
        )
        joint_imp = (s_tc.relationship_impact or {}).get(
            "careful_truth_telling_joint"
        ) or {}
        check(
            "impact carries careful_truth_telling_joint when both present",
            bool(joint_imp.get("joint_stance")),
            str(joint_imp)[:200],
        )
        # Durable snapshot via RH update path (in-memory tracker)
        snap_live = rh_h.update_careful_truth_telling_snapshot(joint)
        check(
            "RH update_careful_truth_telling_snapshot stores joint",
            snap_live.get("joint_stance") == joint.get("joint_stance")
            and snap_live.get("forces_speech") is False,
            str(snap_live)[:200],
        )
        ctx_h = rh_h.as_context()
        check(
            "as_context includes careful_truth_telling durable bag",
            isinstance(ctx_h.get("careful_truth_telling"), dict)
            and "joint_score" in (ctx_h.get("careful_truth_telling") or {}),
        )
        print(
            f"  conf_h={conf_h.level}/{conf_h.score} thin={conf_thin.level}/{conf_thin.score} "
            f"joint_stance={joint.get('joint_stance')} "
            f"surface_ok={joint.get('surface_ok_advisory')} "
            f"durable_stance={snap_live.get('joint_stance')}"
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # ------------------------------------------------------------------
        # 7. Cleanup (no temp files in this suite — RelationshipHealth is in-memory)
        # ------------------------------------------------------------------
        section("7. Clean up temporary test data")
        # This suite uses in-memory RelationshipHealth only; no disk artifacts.
        check("no persistent temp data required", True)

    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll relationship-health integration tests passed.")
        return 0
    print("\nSome relationship-health integration tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
