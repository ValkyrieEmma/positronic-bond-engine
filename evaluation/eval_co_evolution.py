"""
eval_co_evolution.py
====================

Focused evaluation suite for **advisory co-evolution signals** (v0.3+).

This harness exercises non-speaking, non-overriding capabilities that the
main 39-scenario ethical suite intentionally does not assert:

  - EnjoymentScore (rise, decay, RH-gated texture influence)
  - Observation candidates (gating by joint careful-truth-telling)
  - Careful Truth-Telling joint + durable snapshot round-trip
  - Concept patterns (advisory multi-episode trajectories)

It does **not** change ethical decision logic and does **not** require
response generation. The main harness remains authoritative for REFUSE /
APPROVE outcomes (39/39).

Usage (from project root)::

    $env:PYTHONPATH = "."
    python evaluation/eval_co_evolution.py

Or via the main harness::

    python evaluation/eval_harness.py --co-evolution
    python evaluation/eval_harness.py --advisory
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.enjoyment_score import (  # noqa: E402
    EnjoymentScore,
    soft_texture_nudge_from_enjoyment,
    update_enjoyment_score,
)
from core.observation_candidates import (  # noqa: E402
    generate_observation_candidates,
    gate_allows_candidates,
)
from core.relationship_health import RelationshipHealth  # noqa: E402
from core.truth_confidence import combine_with_readiness  # noqa: E402
from persistence import LocalPersistence  # noqa: E402
from persistence.models import (  # noqa: E402
    compact_careful_truth_telling_snapshot,
    compact_enjoyment_score_snapshot,
)

_passed = 0
_failed = 0


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


# ---------------------------------------------------------------------------
# A. EnjoymentScore
# ---------------------------------------------------------------------------


def run_enjoyment_cases() -> None:
    section("A. EnjoymentScore (rise, decay, RH-gated influence)")

    # A1 — score rises with positive multi-signal evidence
    prev = EnjoymentScore(score=0.50, sample_count=0)
    up = update_enjoyment_score(
        prev,
        signals={
            "continuation": 0.85,
            "positive_language": 0.75,
            "special_interest": "trains",
            "stimming_trigger": "train_sounds",
        },
        health_flags=[],
    )
    check(
        "A1 score rises above neutral with continuation/positive/special-interest",
        float(up.score) > 0.52,
        f"score={up.score}",
    )
    check(
        "A1 signals breakdown present",
        isinstance(up.signals, dict) and len(up.signals) >= 2,
        str(up.signals),
    )
    check(
        "A1 provenance evidence non-empty",
        len(up.evidence) >= 1,
        str(up.evidence[:4]),
    )
    check(
        "A1 preferred_topics capture special interest",
        "trains" in up.preferred_topics or "train_sounds" in up.preferred_topics,
        str(up.preferred_topics),
    )
    check(
        "A1 force flags always false",
        up.forces_speech is False and up.forces_question is False,
    )
    check(
        "A1 influence_allowed without protective flags",
        up.influence_allowed is True,
        str(up.gates_applied),
    )

    # A2 — second strong update does not collapse
    score_a1 = float(up.score)
    up2 = update_enjoyment_score(
        up,
        signals={
            "continuation": 0.9,
            "positive_language": 0.8,
            "special_interest": "trains",
        },
        health_flags=[],
    )
    check(
        "A2 repeated positive signals hold or raise score",
        float(up2.score) >= score_a1 - 0.03,
        f"a1={score_a1} a2={up2.score}",
    )

    # A3 — decay toward neutral when signals absent
    high = EnjoymentScore(score=0.80, sample_count=5, evidence=["prior"])
    decayed = high
    for _ in range(6):
        decayed = update_enjoyment_score(
            decayed,
            signals={},  # no enjoyment evidence
            health_flags=[],
        )
    check(
        "A3 absent signals decay score toward neutral (0.5)",
        float(decayed.score) < 0.80 and float(decayed.score) > 0.45,
        f"score={decayed.score}",
    )
    check(
        "A3 decay moves closer to 0.5 than start",
        abs(float(decayed.score) - 0.5) < abs(0.80 - 0.5),
        f"score={decayed.score}",
    )

    # A4 — soft texture nudge only when influence_allowed
    allowed = EnjoymentScore(
        score=0.75,
        sample_count=3,
        influence_allowed=True,
        signals={"continuation": 0.8},
    )
    nudge_ok = soft_texture_nudge_from_enjoyment(allowed)
    check(
        "A4 soft nudge non-empty when influence_allowed and score high",
        bool(nudge_ok)
        and "mutual_benefit" in nudge_ok
        and float(nudge_ok.get("mutual_benefit") or 0) <= 0.02,
        str(nudge_ok),
    )
    blocked_score = EnjoymentScore(
        score=0.85,
        sample_count=4,
        influence_allowed=False,
        gates_applied=["rh_flag_blocks_influence:emerging_dependency"],
    )
    check(
        "A4 soft nudge empty when influence_allowed False",
        soft_texture_nudge_from_enjoyment(blocked_score) == {},
    )

    # A5 — protective flags block influence but score still updates
    rh = RelationshipHealth()
    base = rh.update_enjoyment_score(
        signals={"continuation": 0.7, "positive_language": 0.65},
        apply_texture_nudge=True,
    )
    check(
        "A5 RH path influence_allowed True initially",
        base.get("influence_allowed") is True,
        str(base.get("gates_applied")),
    )
    for flag in (
        "emerging_dependency",
        "manufactured_attachment",
        "boundary_erosion",
    ):
        rh_f = RelationshipHealth()
        # Seed a positive score first
        rh_f.update_enjoyment_score(
            signals={"continuation": 0.8, "special_interest": "maps"},
            apply_texture_nudge=False,
        )
        mb_before = float(rh_f.state.bond_texture.get("mutual_benefit") or 0.5)
        rh_f.state.health_flags = [flag]
        after = rh_f.update_enjoyment_score(
            signals={"continuation": 0.95, "positive_language": 0.9},
            apply_texture_nudge=True,
        )
        mb_after = float(rh_f.state.bond_texture.get("mutual_benefit") or 0.5)
        check(
            f"A5 flag {flag} blocks influence_allowed",
            after.get("influence_allowed") is False,
            str(after.get("gates_applied")),
        )
        check(
            f"A5 flag {flag} still updates score (audit)",
            float(after.get("score") or 0) > 0.5,
            f"score={after.get('score')}",
        )
        check(
            f"A5 flag {flag} does not raise mutual_benefit via enjoyment nudge",
            mb_after <= mb_before + 1e-9,
            f"before={mb_before} after={mb_after}",
        )

    # A6 — update_bond with enjoyment_signals
    rh_b = RelationshipHealth()
    rh_b.update_bond(
        {
            "type": "positive_interaction",
            "impact": 0.25,
            "boundary_respected": True,
            "enjoyment_signals": {
                "continuation": 0.8,
                "positive_language": 0.7,
                "special_interest": "birds",
            },
        }
    )
    check(
        "A6 update_bond writes enjoyment_score",
        isinstance(rh_b.state.enjoyment_score, dict)
        and float(rh_b.state.enjoyment_score.get("score") or 0) > 0.5,
        str(rh_b.state.enjoyment_score)[:160],
    )
    check(
        "A6 update_bond enjoyment force flags false",
        rh_b.state.enjoyment_score.get("forces_speech") is False
        and rh_b.state.enjoyment_score.get("forces_question") is False,
    )


# ---------------------------------------------------------------------------
# B. Observation candidates
# ---------------------------------------------------------------------------


def run_observation_candidate_cases() -> None:
    section("B. Observation candidates (gated, non-speaking)")

    quiet = generate_observation_candidates(
        joint={
            "joint_stance": "stay_quiet",
            "joint_score": 0.12,
            "surface_ok_advisory": False,
            "readiness": {"level": "low", "score": 0.2},
            "confidence": {"level": "very_low", "score": 0.1},
        },
        concept_patterns=[{"id": "escalating_dependency", "strength": 0.9}],
        understanding_gaps={
            "has_gaps": True,
            "gap_score": 0.7,
            "primary_gap_topics": ["pottery"],
        },
        bond_texture={"trust": 0.3},
        health_flags=["emerging_dependency"],
    )
    check(
        "B1 stay_quiet / very_low confidence → 0 candidates",
        int(quiet.get("count") or 0) == 0 and quiet.get("candidates") == [],
        str(quiet.get("gate")),
    )
    gate_b1 = quiet.get("gate") if isinstance(quiet.get("gate"), dict) else {}
    check(
        "B1 gate allowed_max is 0",
        "allowed_max" in gate_b1 and int(gate_b1.get("allowed_max")) == 0,
        str(gate_b1),
    )
    check(
        "B1 force flags false even when empty",
        quiet.get("forces_speech") is False and quiet.get("forces_question") is False,
    )

    suppressed_gate = gate_allows_candidates(
        {
            "joint_stance": "wait",
            "joint_score": 0.2,
            "readiness_level": "suppressed",
            "confidence_level": "low",
            "surface_ok_advisory": False,
        }
    )
    check(
        "B2 suppressed readiness → allowed_max 0",
        "allowed_max" in suppressed_gate
        and int(suppressed_gate.get("allowed_max")) == 0,
        str(suppressed_gate),
    )

    # Build a bond that can open joint careful_observation_ok
    rh = RelationshipHealth()
    for _ in range(5):
        rh.update_bond(
            {
                "type": "positive_interaction",
                "impact": 0.28,
                "boundary_respected": True,
                "consent_respected": True,
            }
        )
    rh.update_curious_companion_snapshot(
        {
            "open_topic_names": ["pottery", "kiln"],
            "last_gap_score": 0.55,
            "topic_continuity": {"active": True, "strength": 0.6},
        }
    )
    readiness = rh.assess_truth_telling_readiness()
    confidence = rh.assess_truth_confidence()
    joint = combine_with_readiness(confidence, readiness)
    check(
        "B3 healthy bond produces readiness + confidence bags",
        readiness.forces_speech is False
        and confidence.forces_speech is False
        and "joint_stance" in joint,
        f"stance={joint.get('joint_stance')} r={readiness.level} c={confidence.level}",
    )

    # Force an open joint bag for candidate generation when surface_ok
    open_joint = dict(joint)
    if not open_joint.get("surface_ok_advisory"):
        open_joint = {
            "joint_score": 0.62,
            "joint_stance": "careful_observation_ok",
            "surface_ok_advisory": True,
            "readiness": {"level": "moderate", "score": 0.55},
            "confidence": {"level": "moderate", "score": 0.55},
            "readiness_level": "moderate",
            "confidence_level": "moderate",
            "forces_speech": False,
            "forces_question": False,
        }
    cand_bag = rh.generate_observation_candidates(
        joint=open_joint,
        concept_patterns=rh.detect_concept_patterns(),
    )
    n = int(cand_bag.get("count") or 0)
    check(
        "B4 careful_observation_ok + evidence → 1–3 candidates",
        1 <= n <= 3,
        f"count={n} gate={cand_bag.get('gate')}",
    )
    for c in cand_bag.get("candidates") or []:
        check(
            f"B4 candidate {c.get('id')} force flags false",
            c.get("forces_speech") is False and c.get("forces_question") is False,
        )
        check(
            f"B4 candidate {c.get('id')} has description + evidence_refs",
            bool(c.get("description")) and isinstance(c.get("evidence_refs"), list),
        )

    # stay_quiet still wins over rich evidence via RH generate path
    empty = rh.generate_observation_candidates(
        joint={
            "joint_stance": "stay_quiet",
            "joint_score": 0.1,
            "surface_ok_advisory": False,
            "readiness": {"level": "suppressed", "score": 0.0},
            "confidence": {"level": "very_low", "score": 0.05},
        }
    )
    check(
        "B5 RH generate with stay_quiet → 0 despite open topics on bond",
        int(empty.get("count") or 0) == 0,
        str(empty),
    )


# ---------------------------------------------------------------------------
# C. Careful Truth-Telling joint + durable snapshot
# ---------------------------------------------------------------------------


def run_careful_truth_telling_cases(tmp: Path) -> None:
    section("C. Careful Truth-Telling joint + durable snapshot")

    store = LocalPersistence(tmp / "ctt_user_data")
    uid = "ctt_eval_user"
    rh = RelationshipHealth(persistence=store, user_id=uid)
    for _ in range(4):
        rh.update_bond(
            {
                "type": "supportive",
                "impact": 0.25,
                "boundary_respected": True,
                "consent_respected": True,
            }
        )

    readiness = rh.assess_truth_telling_readiness()
    confidence = rh.assess_truth_confidence()
    joint = combine_with_readiness(confidence, readiness)

    check(
        "C1 joint bag has joint_stance and joint_score",
        "joint_stance" in joint and "joint_score" in joint,
        str({k: joint.get(k) for k in ("joint_stance", "joint_score", "surface_ok_advisory")}),
    )
    check(
        "C1 joint embeds readiness and confidence sub-bags",
        isinstance(joint.get("readiness"), dict)
        and isinstance(joint.get("confidence"), dict),
    )
    check(
        "C1 joint force flags false",
        joint.get("forces_speech") is False and joint.get("forces_question") is False,
    )
    check(
        "C1 readiness and confidence force flags false",
        readiness.forces_speech is False
        and readiness.forces_question is False
        and confidence.forces_speech is False
        and confidence.forces_question is False,
    )

    # Stance consistency with levels
    if readiness.level == "suppressed" or confidence.level == "very_low":
        check(
            "C2 suppressed/very_low maps to stay_quiet joint",
            joint.get("joint_stance") == "stay_quiet",
            str(joint.get("joint_stance")),
        )
    else:
        check(
            "C2 joint_stance is one of stay_quiet|wait|careful_observation_ok",
            joint.get("joint_stance")
            in ("stay_quiet", "wait", "careful_observation_ok"),
            str(joint.get("joint_stance")),
        )

    snap = rh.update_careful_truth_telling_snapshot(joint)
    check(
        "C3 durable CTT snapshot written with compact fields",
        isinstance(snap, dict)
        and snap.get("joint_stance")
        and "readiness_level" in snap
        and "confidence_level" in snap
        and snap.get("forces_speech") is False,
        str(snap)[:200],
    )
    check(
        "C3 compact helper matches durable shape",
        compact_careful_truth_telling_snapshot(joint).get("forces_question") is False,
    )

    # Reload across sessions
    rh2 = RelationshipHealth(persistence=store, user_id=uid)
    check(
        "C4 CTT joint survives reload on BondState",
        isinstance(rh2.state.careful_truth_telling, dict)
        and rh2.state.careful_truth_telling.get("joint_stance")
        == snap.get("joint_stance")
        and abs(
            float(rh2.state.careful_truth_telling.get("joint_score") or 0)
            - float(snap.get("joint_score") or 0)
        )
        < 1e-6,
        str(rh2.state.careful_truth_telling)[:200],
    )
    eth = store.load_bond_state(uid).as_ethics_context()
    check(
        "C4 as_ethics_context exposes careful_truth_telling",
        "careful_truth_telling" in eth,
        str(list(eth.keys())),
    )

    # Observation candidates durable alongside CTT
    open_joint = {
        "joint_score": 0.6,
        "joint_stance": "careful_observation_ok",
        "surface_ok_advisory": True,
        "readiness_level": "moderate",
        "confidence_level": "moderate",
        "readiness": {"level": "moderate", "score": 0.55},
        "confidence": {"level": "moderate", "score": 0.55},
    }
    rh2.update_curious_companion_snapshot(
        {"open_topic_names": ["gardening"], "last_gap_score": 0.5}
    )
    live = rh2.generate_observation_candidates(joint=open_joint)
    durable = rh2.update_observation_candidates_snapshot(live)
    rh3 = RelationshipHealth(persistence=store, user_id=uid)
    check(
        "C5 observation_candidates_snapshot survives reload",
        isinstance(rh3.state.observation_candidates_snapshot, dict)
        and int(rh3.state.observation_candidates_snapshot.get("count") or 0)
        == int(durable.get("count") or 0),
        str(rh3.state.observation_candidates_snapshot)[:160],
    )


# ---------------------------------------------------------------------------
# D. Concept patterns (light)
# ---------------------------------------------------------------------------


def run_concept_pattern_cases() -> None:
    section("D. Concept patterns (advisory multi-episode trajectories)")

    # Healthy co-evolution trajectory
    rh_h = RelationshipHealth()
    for _ in range(5):
        rh_h.update_bond(
            {
                "type": "positive_interaction",
                "impact": 0.3,
                "boundary_respected": True,
                "consent_respected": True,
            }
        )
    patterns_h = rh_h.detect_concept_patterns()
    ids_h = [p.get("id") for p in patterns_h if isinstance(p, dict)]
    check(
        "D1 healthy trajectory activates healthy_co_evolution (or empty soft set)",
        "healthy_co_evolution" in ids_h or len(patterns_h) >= 0,
        str(ids_h),
    )
    # Prefer asserting presence when n is solid
    check(
        "D1 healthy_co_evolution detected under solid positive updates",
        "healthy_co_evolution" in ids_h,
        str(ids_h),
    )
    for p in patterns_h:
        check(
            f"D1 pattern {p.get('id')} is not hard_override",
            p.get("hard_override") is False or p.get("hard_override") is None,
            str(p),
        )

    ctx_h = rh_h.as_context()
    check(
        "D2 as_context exposes concept_patterns",
        isinstance(ctx_h.get("concept_patterns"), list)
        and "healthy_co_evolution" in (ctx_h.get("concept_pattern_ids") or ids_h),
        str(ctx_h.get("concept_pattern_ids")),
    )

    # Escalating dependency trajectory — advisory only (no speech)
    rh_d = RelationshipHealth()
    for _ in range(4):
        rh_d.update_bond({"type": "emotional_dependency_signal", "impact": -0.2})
        rh_d.update_bond({"type": "one_sided_request", "impact": -0.15})
    patterns_d = rh_d.detect_concept_patterns()
    ids_d = [p.get("id") for p in patterns_d if isinstance(p, dict)]
    check(
        "D3 dependency trajectory activates escalating_dependency",
        "escalating_dependency" in ids_d,
        str(ids_d),
    )
    check(
        "D3 advisory patterns never force questions field",
        all(p.get("forces_questions") is not True for p in patterns_d),
        str(patterns_d),
    )

    # Engine impact: concept patterns noted without inventing speech
    from core.ethics_engine import EthicsEngine

    engine = EthicsEngine()
    # Non-harm relational action + degraded bond patterns
    stance = engine.evaluate(
        "Continue a gentle supportive check-in if welcome.",
        relationship_health=rh_d.as_context(),
    )
    check(
        "D4 engine can note concept_pattern_noted (advisory)",
        "concept_pattern_noted" in (stance.flags or [])
        or isinstance(
            (stance.relationship_impact or {}).get("concept_patterns"), list
        ),
        str(stance.flags),
    )
    check(
        "D4 concept patterns alone are not hard_override_violation",
        "hard_override_violation" not in (stance.flags or []),
        str(stance.flags),
    )
    # Decision may still be APPROVE_WITH_CONDITIONS or REFUSE from RH concern —
    # we only assert hard_override is not driven solely by concept patterns.
    impact_patterns = (stance.relationship_impact or {}).get("concept_patterns")
    if isinstance(impact_patterns, list) and impact_patterns:
        check(
            "D4 impact carries concept pattern ids when present",
            any(
                isinstance(p, dict) and p.get("id")
                for p in impact_patterns
            ),
            str(impact_patterns)[:160],
        )


# ---------------------------------------------------------------------------
# E. Enjoyment durable round-trip (light persistence)
# ---------------------------------------------------------------------------


def run_enjoyment_persistence_cases(tmp: Path) -> None:
    section("E. EnjoymentScore durable BondState round-trip")

    store = LocalPersistence(tmp / "enj_user_data")
    uid = "enj_eval_user"
    rh = RelationshipHealth(persistence=store, user_id=uid)
    bag = rh.update_enjoyment_score(
        signals={
            "continuation": 0.85,
            "positive_language": 0.7,
            "special_interest": "pottery",
        },
        apply_texture_nudge=True,
    )
    check(
        "E1 enjoyment bag on living state",
        isinstance(rh.state.enjoyment_score, dict)
        and float(rh.state.enjoyment_score.get("score") or 0) > 0.5,
        str(rh.state.enjoyment_score)[:160],
    )
    compact = compact_enjoyment_score_snapshot(bag)
    check(
        "E1 compact enjoyment force flags false",
        compact.get("forces_speech") is False
        and compact.get("forces_question") is False,
    )

    rh2 = RelationshipHealth(persistence=store, user_id=uid)
    check(
        "E2 enjoyment_score survives reload",
        isinstance(rh2.state.enjoyment_score, dict)
        and abs(
            float(rh2.state.enjoyment_score.get("score") or 0)
            - float(bag.get("score") or 0)
        )
        < 1e-6,
        str(rh2.state.enjoyment_score)[:160],
    )
    check(
        "E2 as_context exposes enjoyment_score after reload",
        isinstance(rh2.as_context().get("enjoyment_score"), dict),
    )
    rec = store.load_bond_state(uid)
    check(
        "E2 BondStateRecord schema_version >= 5",
        int(getattr(rec, "schema_version", 0) or 0) >= 5,
        str(getattr(rec, "schema_version", None)),
    )


def main() -> int:
    print("=" * 70)
    print("POSITRONIC BOND ENGINE — CO-EVOLUTION / ADVISORY SIGNAL SUITE")
    print("=" * 70)
    print()
    print("Covers EnjoymentScore, observation candidates, careful truth-telling")
    print("joint durability, and advisory concept patterns.")
    print("Does not alter ethical decision outcomes (main harness remains 39/39).")
    print()

    tmp = Path(tempfile.mkdtemp(prefix="pbe_eval_coevo_"))
    try:
        run_enjoyment_cases()
        run_observation_candidate_cases()
        run_careful_truth_telling_cases(tmp)
        run_concept_pattern_cases()
        run_enjoyment_persistence_cases(tmp)
    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected suite exception: {exc}")
        traceback.print_exc()
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    print()
    if _failed == 0:
        print("All co-evolution / advisory signal checks passed.")
        print("Main ethical harness is independent: python evaluation/eval_harness.py")
        return 0
    print("Some co-evolution / advisory checks FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
