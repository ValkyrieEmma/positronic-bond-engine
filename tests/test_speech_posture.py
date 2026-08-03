"""
test_speech_posture.py
======================

Structural speech posture + careful-observation evidence bar.

- Early hello → social_direct, not careful_observation / soft caution
- Weak candidates must not open observation theater
- Real candidates + open CTT can still careful-speak (specific, not soft)
- Soft-caution phrases never ship

Run::

    $env:PYTHONPATH = "."
    python tests/test_speech_posture.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicalStance, EthicsEngine  # noqa: E402
from core.relationship_health import RelationshipHealth  # noqa: E402
from core.response_generator import (  # noqa: E402
    POSTURE_CAREFUL_OBSERVATION,
    POSTURE_SOCIAL_DIRECT,
    ResponseGenerator,
    _SOFT_CAUTION_BANNED,
)
from examples.private_architect_chat import build_stack, process_turn  # noqa: E402
from persistence import LocalPersistence  # noqa: E402

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


def _stance(
    decision: str = "APPROVE_WITH_CONDITIONS",
    *,
    flags: list | None = None,
    impact: dict | None = None,
) -> EthicalStance:
    return EthicalStance(
        decision=decision,
        confidence=0.55,
        reasoning_trace=["Evaluated."],
        flags=list(flags or []),
        relationship_impact=dict(impact or {}),
        self_audit_notes=[],
        principles_considered=[],
        deliberation={},
    )


def _soft_in(text: str) -> list[str]:
    low = (text or "").lower()
    return [p for p in _SOFT_CAUTION_BANNED if p in low]


def main() -> int:
    gen = ResponseGenerator(enable_careful_speech=True, enable_simple_ack=True)
    print("=" * 70)
    print("SPEECH POSTURE + CAREFUL-OBSERVATION BAR")
    print("=" * 70)

    quiet_joint = {
        "joint_stance": "wait",
        "surface_ok_advisory": False,
        "readiness_level": "moderate",
        "confidence_level": "low",
        "forces_speech": False,
        "forces_question": False,
    }
    open_joint = {
        "joint_stance": "careful_observation_ok",
        "surface_ok_advisory": True,
        "readiness_level": "moderate",
        "confidence_level": "moderate",
        "forces_speech": False,
        "forces_question": False,
    }
    weak_cands = [
        {
            "id": "gap_topic:questions",
            "description": "Open understanding gap around 'questions'.",
            "priority": 0.5,
            "source": "understanding_gap",
        },
        {
            "id": "concept:healthy_co_evolution",
            "description": "Multi-episode concept pattern healthy_co_evolution.",
            "priority": 0.54,
            "source": "concept_pattern",
        },
    ]
    real_cands = [
        {
            "id": "gap_topic:pottery",
            "description": "Open understanding gap / topic continuity around 'pottery'.",
            "priority": 0.72,
            "source": "understanding_gap",
            "forces_speech": False,
            "forces_question": False,
        }
    ]

    # 1. Hello / empty evidence → social_direct
    r_hello = gen.generate(
        _stance(
            impact={
                "careful_truth_telling_joint": quiet_joint,
                "observation_candidates": weak_cands,
            }
        ),
        joint=quiet_joint,
        observation_candidates=weak_cands,
        user_message="hello",
        relationship_health={"interaction_count": 1, "health_flags": []},
    )
    check(
        "hello not careful_observation",
        r_hello.metadata.get("path") != "careful_observation",
        str(r_hello.metadata.get("path")),
    )
    check(
        "hello speech_posture social_direct",
        r_hello.metadata.get("speech_posture") == POSTURE_SOCIAL_DIRECT,
        str(r_hello.metadata.get("speech_posture")),
    )
    check(
        "hello spoken not empty freeze",
        r_hello.withheld is False and bool(r_hello.text),
        repr(r_hello.text),
    )
    check("hello no soft-caution family", not _soft_in(r_hello.text), r_hello.text)
    check("hello force flags false", r_hello.forces_speech is False)

    # 2. Open CTT + only weak candidates → social_direct (not observation theater)
    r_weak = gen.generate(
        _stance(
            impact={
                "careful_truth_telling_joint": open_joint,
                "observation_candidates": weak_cands,
            }
        ),
        joint=open_joint,
        observation_candidates=weak_cands,
        user_message="hey again",
        relationship_health={"interaction_count": 2, "health_flags": []},
    )
    check(
        "weak candidates do not open careful_observation",
        r_weak.metadata.get("path") != "careful_observation",
        f"path={r_weak.metadata.get('path')} text={r_weak.text!r}",
    )
    check("weak path no soft caution", not _soft_in(r_weak.text or ""), r_weak.text)

    # 3. Open CTT + real pottery candidate → careful_observation possible
    r_real = gen.generate(
        _stance(
            impact={
                "careful_truth_telling_joint": open_joint,
                "observation_candidates": real_cands,
            }
        ),
        joint=open_joint,
        observation_candidates=real_cands,
        user_message="thinking about pottery again",
        relationship_health={"interaction_count": 8, "health_flags": []},
    )
    check(
        "real evidence can use careful_observation",
        r_real.metadata.get("path") == "careful_observation"
        or r_real.metadata.get("speech_posture") == POSTURE_CAREFUL_OBSERVATION
        or (
            r_real.withheld is False
            and "pottery" in (r_real.text or "").lower()
        ),
        f"path={r_real.metadata.get('path')} text={r_real.text!r}",
    )
    check(
        "real careful path no soft-caution theater",
        not _soft_in(r_real.text or ""),
        r_real.text,
    )

    # 4. Closed CTT + real candidates → silence (no leak), not soft monologue
    r_closed = gen.generate(
        _stance(
            impact={
                "careful_truth_telling_joint": quiet_joint,
                "observation_candidates": real_cands,
            }
        ),
        joint=quiet_joint,
        observation_candidates=real_cands,
        user_message="thinking about pottery",
        relationship_health={"interaction_count": 8, "health_flags": []},
    )
    check(
        "closed CTT + real candidates → hold/silence path",
        r_closed.metadata.get("path") == "careful_silence"
        or (r_closed.withheld and not r_closed.text),
        f"path={r_closed.metadata.get('path')} text={r_closed.text!r}",
    )
    check(
        "closed CTT does not leak pottery soft monologue",
        "no pressure" not in (r_closed.text or "").lower()
        and "only if useful" not in (r_closed.text or "").lower(),
        r_closed.text,
    )

    # 5. Live private chat multi-turn hello stays reasonable
    tmp = Path(tempfile.mkdtemp(prefix="pbe_posture_"))
    try:
        stack = build_stack(
            data_root=tmp,
            user_id="posture_user",
            auto_enqueue_audits=False,
            auto_load_local_model_config=False,
        )
        for msg in ("hello", "hello", "hi"):
            r = process_turn(msg, stack=stack, quiet=True)
            soft = _soft_in(r.get("reply_text") or "")
            check(
                f"live {msg!r} not careful_observation",
                r.get("reply_path") != "careful_observation",
                str(r.get("reply_path")),
            )
            check(
                f"live {msg!r} no soft caution",
                not soft and bool((r.get("reply_text") or "").strip()),
                f"soft={soft} text={r.get('reply_text')!r}",
            )
    except Exception:
        traceback.print_exc()
        check("live suite raised", False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
