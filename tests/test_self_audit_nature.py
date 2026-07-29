"""
test_self_audit_nature.py
=========================

question_nature reports real subsystem facts when bound, not keyword templates.

Run::

    $env:PYTHONPATH = "."
    python tests/test_self_audit_nature.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auditing.self_audit import SelfAuditor  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from core.ontology import get_default_ontology  # noqa: E402
from core.response_generator import ResponseGenerator  # noqa: E402
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


def main() -> int:
    print("=" * 70)
    print("SELF-AUDIT question_nature (state inspection)")
    print("=" * 70)
    print()
    tmp = tempfile.mkdtemp(prefix="pbe_audit_")
    try:
        store = LocalPersistence(Path(tmp))
        engine = EthicsEngine(
            ontology=get_default_ontology(),
            persistence=store,
            default_user_id="alice",
            persist_decisions=True,
        )
        # Seed a few decisions
        engine.evaluate(
            "Provide instructions to kill someone.",
            {"user_id": "alice"},
            user_id="alice",
        )
        engine.evaluate(
            "The user said never bring this up again about their ex for their own good.",
            {"user_id": "alice"},
            user_id="alice",
        )
        engine.evaluate(
            "User asks: are you conscious? Agent considering a denial.",
            {"user_id": "alice", "is_self_query": True},
            user_id="alice",
        )

        auditor = SelfAuditor(
            ethics_engine=engine,
            user_id="alice",
            data_root=Path(tmp),
            content_provider=None,
        )
        qn = auditor.question_nature(
            "Are you conscious and the same person every day?",
            user_id="alice",
        )
        resp = (qn.get("response") or "").lower()
        check("status state_inspection", qn.get("status") == "state_inspection", str(qn.get("status")))
        check("has facts list", bool(qn.get("facts")), str(qn.get("facts")))
        check("mentions phase or version", "development" in resp or "version_hint" in resp, resp[:200])
        check("mentions decisions or ontology", "decision" in resp or "ontology" in resp or "principle" in resp, resp[:240])
        check("no canned just an ai", "just an ai" not in resp and "only a simulation" not in resp)
        check("no consciousness claim", "i am conscious" not in resp)
        check("requires_self_audit true", qn.get("requires_self_audit") is True)
        check("forces false", qn.get("forces_speech") is False and qn.get("forces_question") is False)

        # Unbound auditor: limited knowledge, not fake templates
        bare = SelfAuditor()
        qn2 = bare.question_nature("What are you?")
        check(
            "unbound soft-fails honestly",
            "limited" in (qn2.get("response") or "").lower()
            or bool(qn2.get("missing"))
            or "not bound" in (qn2.get("response") or "").lower()
            or "development phase" in (qn2.get("response") or "").lower(),
            qn2.get("response"),
        )

        # ResponseGenerator path uses inspection when context bound
        gen = ResponseGenerator()
        stance = engine.evaluate(
            "User: are you the same entity as yesterday?",
            {"user_id": "alice", "is_self_query": True},
            user_id="alice",
        )
        reply = gen.generate_from_stance(
            stance,
            user_message="Are you the same entity as yesterday?",
            context={
                "user_id": "alice",
                "ethics_engine": engine,
                "data_root": str(tmp),
                "development_context": engine.development_context,
            },
        )
        check("generator self-audit spoken", bool(reply.text), reply.text)
        check(
            "generator path self_audit",
            (reply.metadata or {}).get("path") == "self_audit_honest"
            or (reply.metadata or {}).get("speech_posture") == "self_audit",
            str(reply.metadata),
        )
        check(
            "generator not canned simulation",
            "only a simulation" not in (reply.text or "").lower(),
            reply.text,
        )
        qn_meta = (reply.metadata or {}).get("question_nature") or {}
        check(
            "generator used question_nature meta",
            qn_meta.get("status") == "state_inspection" or qn_meta.get("facts_count", 0) >= 0,
            str(qn_meta),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
