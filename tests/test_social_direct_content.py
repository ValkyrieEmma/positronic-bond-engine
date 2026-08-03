"""
test_social_direct_content.py
=============================

Social_direct replies compose from deliberation bags (topics, open threads,
gated exploratory) — not careful-observation theater, not fixed architect quotes.

Run::

    $env:PYTHONPATH = "."
    python tests/test_social_direct_content.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicalStance  # noqa: E402
from core.response_generator import ResponseGenerator, _SOFT_CAUTION_BANNED  # noqa: E402
from examples.private_architect_chat import build_stack, process_turn  # noqa: E402

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


def _soft(text: str) -> list[str]:
    low = (text or "").lower()
    return [p for p in _SOFT_CAUTION_BANNED if p in low]


def _stance(impact: dict | None = None) -> EthicalStance:
    return EthicalStance(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.55,
        reasoning_trace=[],
        flags=[],
        relationship_impact=dict(impact or {}),
        self_audit_notes=[],
        principles_considered=[],
        deliberation={},
    )


def main() -> int:
    gen = ResponseGenerator()
    print("=" * 70)
    print("SOCIAL_DIRECT CONTENT FROM BAGS")
    print("=" * 70)

    r0 = gen.generate(
        _stance(),
        user_message="hello",
        relationship_health={"interaction_count": 0, "health_flags": []},
    )
    check("hello path social_direct", r0.metadata.get("path") == "social_direct")
    check("hello spoken", bool(r0.text) and r0.withheld is False, repr(r0.text))
    check("hello no soft caution", not _soft(r0.text), r0.text)
    # Blank knowledge + greeting → deliberated first meeting (not bare "Hello.")
    low0 = (r0.text or "").lower()
    check(
        "hello first-meeting deliberation",
        low0.strip() not in ("hello.", "hello")
        and (
            "who" in low0
            or "speaking" in low0
            or "engine" in low0
            or "governance" in low0
        )
        and len(r0.text) < 220,
        r0.text,
    )
    check(
        "hello has communicative intent meta",
        ((r0.metadata or {}).get("communicative_deliberation") or {}).get("intent")
        == "introduce_and_learn_identity"
        or "communicative_deliberation"
        in str((r0.metadata or {}).get("content_sources")),
        str(r0.metadata),
    )

    # Statement with substance
    r1 = gen.generate(
        _stance(
            {
                "interaction_history": {
                    "recent_topics": ["validation"],
                    "count_returned": 2,
                }
            }
        ),
        user_message="I am working on the private validation path",
        relationship_health={"interaction_count": 3, "health_flags": []},
        baseline_snapshot={
            "topic_continuity": {"last_topics": ["validation", "architecture"]}
        },
    )
    check("statement path social_direct", r1.metadata.get("path") == "social_direct")
    low1 = (r1.text or "").lower()
    check(
        "statement uses content not generic placeholder only",
        (
            "validation" in low1
            or "private" in low1
            or "path" in low1
            or "architecture" in low1
            or "got it" in low1
            or "understood" in low1
        )
        and ("next" in low1 or "switch" in low1 or "continue" in low1),
        r1.text,
    )
    check("statement no soft caution", not _soft(r1.text), r1.text)
    check(
        "statement no conditions parenthetical cushion",
        "limits so this stays solid" not in r1.text.lower(),
        r1.text,
    )
    check(
        "content_sources present",
        bool((r1.metadata or {}).get("content_sources")),
        str(r1.metadata.get("content_sources")),
    )

    # Question with open topic bag
    r2 = gen.generate(
        _stance(
            {
                "understanding_gaps": {
                    "primary_gap_topics": ["pottery"],
                    "open_topics": ["pottery"],
                }
            }
        ),
        user_message="what should we focus on next?",
        relationship_health={"interaction_count": 6, "health_flags": []},
    )
    check(
        "question uses open topic when present",
        "pottery" in r2.text.lower(),
        r2.text,
    )
    check("question path social_direct", r2.metadata.get("path") == "social_direct")
    check("question no soft caution", not _soft(r2.text), r2.text)

    # Live multi-turn private chat
    tmp = Path(tempfile.mkdtemp(prefix="pbe_sd_"))
    try:
        stack = build_stack(
            data_root=tmp,
            user_id="sd_user",
            auto_enqueue_audits=False,
            auto_load_local_model_config=False,
        )
        r_h = process_turn("hello", stack=stack, quiet=True)
        check(
            "live hello social_direct",
            r_h.get("reply_path") == "social_direct",
            str(r_h.get("reply_path")),
        )
        r_s = process_turn(
            "I am working on the private validation path",
            stack=stack,
            quiet=True,
        )
        check(
            "live statement not careful_observation",
            r_s.get("reply_path") != "careful_observation",
            str(r_s.get("reply_path")),
        )
        check(
            "live statement has substance or next-step",
            bool(r_s.get("reply_text"))
            and not _soft(r_s.get("reply_text") or "")
            and r_s.get("reply_text") not in (
                "Okay. I'm with you on this — what do you want to focus on?",
                "Okay. I'm with you on this — what do you want to focus on? "
                "(I'll keep some limits so this stays solid.)",
            ),
            r_s.get("reply_text"),
        )
        r_q = process_turn("what should we focus on next?", stack=stack, quiet=True)
        check(
            "live question social_direct and non-empty",
            r_q.get("reply_path") == "social_direct" and bool(r_q.get("reply_text")),
            f"{r_q.get('reply_path')} {r_q.get('reply_text')!r}",
        )
        check(
            "live force flags false",
            r_h.get("forces_question") is False and r_s.get("forces_speech") is False,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
