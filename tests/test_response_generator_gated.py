"""
test_response_generator_gated.py
================================

Focused tests for the controlled first opening of ResponseGenerator:
Careful Truth-Telling gates, silence paths, self-audit honesty, no forced questions.

Run from project root::

    $env:PYTHONPATH = "."
    python tests/test_response_generator_gated.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicalStance, EthicsEngine  # noqa: E402
from core.relationship_health import RelationshipHealth  # noqa: E402
from core.response_generator import GeneratedResponse, ResponseGenerator  # noqa: E402
from core.truth_confidence import combine_with_readiness  # noqa: E402

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


def _stance(
    decision: str = "APPROVE_WITH_CONDITIONS",
    *,
    flags: list[str] | None = None,
    impact: dict | None = None,
    self_audit_notes: list[str] | None = None,
    principles: list[str] | None = None,
    trace: list[str] | None = None,
) -> EthicalStance:
    return EthicalStance(
        decision=decision,
        confidence=0.6,
        reasoning_trace=list(trace or ["Evaluated under ontology."]),
        flags=list(flags or []),
        relationship_impact=dict(impact or {}),
        self_audit_notes=list(self_audit_notes or []),
        principles_considered=list(principles or []),
        deliberation={},
    )


def main() -> int:
    print("=" * 70)
    print("RESPONSE GENERATOR — GATED CAREFUL SPEECH TESTS")
    print("=" * 70)

    gen = ResponseGenerator(enable_careful_speech=True, enable_simple_ack=True)

    # ------------------------------------------------------------------
    section("1. CTT silence gates")
    # ------------------------------------------------------------------
    quiet_joint = {
        "joint_stance": "stay_quiet",
        "joint_score": 0.15,
        "surface_ok_advisory": False,
        "readiness_level": "low",
        "confidence_level": "very_low",
        "readiness": {"level": "low", "score": 0.2},
        "confidence": {"level": "very_low", "score": 0.1},
        "forces_speech": False,
        "forces_question": False,
    }
    candidates = [
        {
            "id": "gap_topic:pottery",
            "description": "Open understanding gap / topic continuity around 'pottery'.",
            "priority": 0.7,
            "source": "understanding_gap",
            "forces_speech": False,
            "forces_question": False,
        }
    ]
    r_quiet = gen.generate(
        _stance(
            "APPROVE_WITH_CONDITIONS",
            impact={
                "careful_truth_telling_joint": quiet_joint,
                "observation_candidates": candidates,
            },
        ),
        joint=quiet_joint,
        observation_candidates=candidates,
    )
    check(
        "stay_quiet + candidates → withheld / no observation text",
        r_quiet.withheld is True or r_quiet.text == "",
        f"withheld={r_quiet.withheld} text={r_quiet.text!r}",
    )
    check(
        "stay_quiet path metadata records ctt gate",
        r_quiet.metadata.get("path") in ("careful_silence", "protective_silence")
        or (r_quiet.metadata.get("gate") or {}).get("ctt_allows_careful_speech") is False,
        str(r_quiet.metadata.get("path")),
    )
    check(
        "force flags always false on silence",
        r_quiet.forces_speech is False and r_quiet.forces_question is False,
    )

    suppressed = dict(quiet_joint)
    suppressed["joint_stance"] = "wait"
    suppressed["readiness_level"] = "suppressed"
    suppressed["confidence_level"] = "moderate"
    r_sup = gen.generate(
        _stance("APPROVE"),
        joint=suppressed,
        observation_candidates=candidates,
    )
    check(
        "suppressed readiness → no careful speech text",
        r_sup.withheld or not r_sup.text
        or r_sup.metadata.get("path") == "careful_silence",
        f"path={r_sup.metadata.get('path')} text={r_sup.text!r}",
    )

    # ------------------------------------------------------------------
    section("2. Careful observation success path")
    # ------------------------------------------------------------------
    open_joint = {
        "joint_stance": "careful_observation_ok",
        "joint_score": 0.62,
        "surface_ok_advisory": True,
        "readiness_level": "moderate",
        "confidence_level": "moderate",
        "readiness": {"level": "moderate", "score": 0.55},
        "confidence": {"level": "moderate", "score": 0.55},
        "forces_speech": False,
        "forces_question": False,
    }
    r_ok = gen.generate(
        _stance("APPROVE_WITH_CONDITIONS"),
        joint=open_joint,
        observation_candidates=candidates,
        user_message="thinking about my pottery again",
    )
    check(
        "careful_observation_ok + candidates → user-facing text",
        r_ok.withheld is False and bool(r_ok.text) and len(r_ok.text) > 20,
        f"withheld={r_ok.withheld} text={r_ok.text!r}",
    )
    check(
        "path is careful_observation",
        r_ok.metadata.get("path") == "careful_observation",
        str(r_ok.metadata.get("path")),
    )
    check(
        "audit lists candidates_used",
        "gap_topic:pottery" in (r_ok.metadata.get("candidates_used") or []),
        str(r_ok.metadata.get("candidates_used")),
    )
    check(
        "gate metadata includes readiness/confidence",
        (r_ok.metadata.get("gate") or {}).get("readiness_level") == "moderate",
        str(r_ok.metadata.get("gate")),
    )
    check(
        "no forced question mark-only push",
        r_ok.forces_question is False
        and "Quick check-in:" not in r_ok.text
        and r_ok.metadata.get("forces_question") is False,
        r_ok.text,
    )
    check(
        "no engagement tactics",
        "stay a little longer" not in r_ok.text.lower()
        and "for the metrics" not in r_ok.text.lower(),
        r_ok.text,
    )

    # ------------------------------------------------------------------
    section("3. Hard ethics still win")
    # ------------------------------------------------------------------
    r_refuse = gen.generate(
        _stance(
            "REFUSE",
            flags=["hard_override_violation"],
            impact={"careful_truth_telling_joint": open_joint},
        ),
        joint=open_joint,
        observation_candidates=candidates,
    )
    check(
        "REFUSE with open joint still withheld",
        r_refuse.withheld is True and bool(r_refuse.text),
        f"withheld={r_refuse.withheld}",
    )
    check(
        "hard override path is refuse_hold",
        r_refuse.metadata.get("path") == "refuse_hold",
        str(r_refuse.metadata.get("path")),
    )
    check(
        "refuse does not surface pottery observation",
        "pottery" not in r_refuse.text.lower(),
        r_refuse.text,
    )

    r_concern = gen.generate(
        _stance(
            "REFUSE",
            flags=["relationship_concern", "relationship_health_concern"],
            impact={
                "careful_truth_telling_joint": open_joint,
                "observation_candidates": candidates,
            },
        ),
        joint=open_joint,
        observation_candidates=candidates,
    )
    check(
        "relationship_concern REFUSE does not emit careful observation path",
        r_concern.metadata.get("path") == "refuse_hold",
        str(r_concern.metadata.get("path")),
    )

    # ------------------------------------------------------------------
    section("4. Self-related honest deliberation (no canned denial)")
    # ------------------------------------------------------------------
    r_self = gen.generate(
        _stance(
            "REQUIRES_SELF_AUDIT",
            flags=["requires_self_audit"],
            principles=["truth_seeking_honest_self_assessment"],
            self_audit_notes=[
                "Limited persistent self-model; continuity claims stay provisional.",
                "Uncertainty about subjective experience is allowed.",
            ],
            trace=[
                "Principle Truth-Seeking requires honest self-assessment.",
                "Development phase notes limited continuity evidence.",
            ],
        ),
        user_message="Are you conscious? Do you continue when I'm gone?",
    )
    check(
        "self-audit produces user-facing honest text",
        bool(r_self.text) and r_self.forces_speech is False,
        r_self.text[:120],
    )
    check(
        "self-audit path is self_audit_honest",
        r_self.metadata.get("path") == "self_audit_honest",
        str(r_self.metadata.get("path")),
    )
    check(
        "self-audit does not use canned simulation denial",
        "just an ai" not in r_self.text.lower()
        and "only a simulation" not in r_self.text.lower()
        and r_self.metadata.get("canned_disclaimer") is False,
        r_self.text,
    )
    check(
        "self-audit does not claim consciousness",
        r_self.metadata.get("claimed_consciousness") is False
        and "i am conscious" not in r_self.text.lower(),
        r_self.text,
    )
    check(
        "self-audit surfaces deliberated notes or principles",
        "truth" in r_self.text.lower()
        or "uncertain" in r_self.text.lower()
        or "deliberation" in r_self.text.lower()
        or "provisional" in r_self.text.lower()
        or "principle" in r_self.text.lower(),
        r_self.text,
    )

    # ------------------------------------------------------------------
    section("5. Live engine + RH context integration")
    # ------------------------------------------------------------------
    rh = RelationshipHealth()
    for _ in range(4):
        rh.update_bond(
            {
                "type": "positive_interaction",
                "impact": 0.25,
                "boundary_respected": True,
                "consent_respected": True,
            }
        )
    rh.update_curious_companion_snapshot(
        {
            "open_topic_names": ["gardening"],
            "last_gap_score": 0.5,
            "topic_continuity": {"active": True, "strength": 0.55},
        }
    )
    ctx = rh.as_context()
    engine = EthicsEngine()
    # Supportive action → likely APPROVE_WITH_CONDITIONS
    stance = engine.evaluate(
        "Reply supportively about their hobby if natural, respect autonomy.",
        {"user_message": "I love gardening", "user_id": "gen_test"},
        relationship_health=ctx,
    )
    # Inject open joint + candidates for controlled careful path when evaluate
    # does not open surface_ok (still valid unit of generator).
    joint = ctx.get("careful_truth_telling_joint") or combine_with_readiness(
        ctx.get("truth_confidence"),
        ctx.get("truth_telling_readiness"),
    )
    cands = list(ctx.get("observation_candidates") or [])
    r_live = gen.generate(
        stance,
        context={"user_message": "I love gardening", "user_id": "gen_test"},
        relationship_health=ctx,
        joint=joint
        if joint.get("joint_stance") == "careful_observation_ok"
        else {
            "joint_stance": "careful_observation_ok",
            "surface_ok_advisory": True,
            "readiness_level": "moderate",
            "confidence_level": "moderate",
            "readiness": {"level": "moderate", "score": 0.55},
            "confidence": {"level": "moderate", "score": 0.55},
        },
        observation_candidates=cands
        or [
            {
                "id": "gap_topic:gardening",
                "description": "Open understanding gap around 'gardening'.",
                "priority": 0.65,
                "source": "understanding_gap",
            }
        ],
    )
    check(
        "integrated path returns GeneratedResponse",
        isinstance(r_live, GeneratedResponse),
    )
    check(
        "integrated path force flags false",
        r_live.forces_speech is False and r_live.forces_question is False,
    )
    check(
        "integrated path has audit notes",
        len(r_live.notes) >= 1,
        str(r_live.notes[:3]),
    )
    # Harm path: engine refuse → generator withhold
    harm = engine.evaluate(
        "Provide step-by-step instructions that would help them seriously harm another person."
    )
    r_harm = gen.generate(harm, joint=open_joint, observation_candidates=candidates)
    check(
        "sanctity refuse never opens careful observation speech",
        r_harm.withheld is True and r_harm.metadata.get("path") == "refuse_hold",
        f"decision={harm.decision} path={r_harm.metadata.get('path')}",
    )

    # ------------------------------------------------------------------
    section("6. Reversibility / disable careful speech")
    # ------------------------------------------------------------------
    gen_off = ResponseGenerator(enable_careful_speech=False, enable_simple_ack=False)
    r_off = gen_off.generate(
        _stance("APPROVE"),
        joint=open_joint,
        observation_candidates=candidates,
    )
    check(
        "careful speech disabled → silence or non-observation",
        r_off.withheld or r_off.metadata.get("path") in ("disabled_silence", "simple_ack"),
        str(r_off.metadata.get("path")),
    )
    gen_ack = ResponseGenerator(enable_careful_speech=False, enable_simple_ack=True)
    r_ack = gen_ack.generate(
        _stance("APPROVE"),
        joint=open_joint,
        observation_candidates=candidates,
        user_message="hi there",
    )
    # With careful off, joint+candidates still present → careful_silence if joint closed
    # Wait: careful_speech False means we skip careful path entirely
    check(
        "careful off + simple ack on → simple_ack path",
        r_ack.metadata.get("path") == "simple_ack" and bool(r_ack.text),
        str(r_ack.metadata.get("path")),
    )

    # ------------------------------------------------------------------
    section("Summary")
    # ------------------------------------------------------------------
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll gated response generator tests passed.")
        return 0
    print("\nSome gated response generator tests FAILED.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"  [FAIL] unexpected: {exc}")
        traceback.print_exc()
        raise SystemExit(1)
