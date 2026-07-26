"""
test_communicative_deliberation.py
==================================

Relationship knowledge + communicative deliberation:

- Blank memory + greeting → first-meeting intent (introduce + learn identity)
- Intro stores maker role AND address name (two facts)
- Later greeting uses stored knowledge
- Premises are inspectable (reasoning trail, not silent template switch)
- Leave-alone → stop intent

Run::

    $env:PYTHONPATH = "."
    python tests/test_communicative_deliberation.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.communicative_deliberation import (  # noqa: E402
    FIELD_ADDRESS_NAME,
    FIELD_IS_MAKER,
    INTENT_ACK_FACTS,
    INTENT_GREET_KNOWN,
    INTENT_INTRODUCE_AND_LEARN,
    INTENT_STOP,
    SIT_FIRST_MEETING,
    deliberate_and_persist,
    deliberate_communication,
    knowledge_is_blank,
    load_relationship_knowledge,
)
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


def test_unit_first_meeting() -> None:
    print("Unit: blank knowledge + hello → first meeting")
    r = deliberate_communication(
        "hello",
        known={},
        memory_empty=True,
        interaction_count=0,
    )
    check("situation first_meeting", r.situation == SIT_FIRST_MEETING, r.situation)
    check("intent introduce_and_learn", r.intent == INTENT_INTRODUCE_AND_LEARN, r.intent)
    check(
        "expression introduces and asks identity",
        "who" in r.fallback_expression.lower()
        or "speaking" in r.fallback_expression.lower()
        or "name" in r.fallback_expression.lower(),
        r.fallback_expression,
    )
    check(
        "not bare Hello only",
        r.fallback_expression.strip().lower() not in ("hello.", "hello"),
        r.fallback_expression,
    )
    check(
        "premises mention blank knowledge",
        any("blank" in p.lower() for p in r.premises),
        str(r.premises),
    )
    check(
        "premises mention first meeting / mutual recognition",
        any(
            "first meeting" in p.lower() or "mutual recognition" in p.lower()
            for p in r.premises
        ),
        str(r.premises),
    )
    check("forces false", r.forces_speech is False and r.forces_question is False)


def test_unit_intro_two_facts() -> None:
    print("Unit: intro asserts maker + address name")
    text = (
        "I am the architect designing your system. You can call me mother."
    )
    r = deliberate_communication(text, known={}, memory_empty=False, interaction_count=1)
    check("intent ack facts", r.intent == INTENT_ACK_FACTS, r.intent)
    check("stores is_maker", bool(r.known_after.get(FIELD_IS_MAKER)), str(r.known_after))
    check(
        "stores address_name mother",
        str(r.known_after.get(FIELD_ADDRESS_NAME) or "").lower() == "mother",
        str(r.known_after),
    )
    kinds = {f.get("kind") for f in r.new_facts}
    check("new_facts has maker", FIELD_IS_MAKER in kinds or "role_label" in kinds, str(kinds))
    check("new_facts has address_name", FIELD_ADDRESS_NAME in kinds, str(kinds))
    low = r.fallback_expression.lower()
    check(
        "ack mentions makerhood",
        "making" in low or "architect" in low or "maker" in low,
        r.fallback_expression,
    )
    check("ack mentions mother", "mother" in low, r.fallback_expression)
    check(
        "meaning gloss for maker",
        any(m.kind == "maker_role_claim" for m in r.meanings),
        [m.kind for m in r.meanings],
    )
    check(
        "meaning gloss for address",
        any(m.kind == "address_directive" for m in r.meanings),
        [m.kind for m in r.meanings],
    )


def test_unit_known_greeting() -> None:
    print("Unit: known mother + hello")
    r = deliberate_communication(
        "hello",
        known={
            FIELD_ADDRESS_NAME: "mother",
            FIELD_IS_MAKER: True,
            "role_labels": ["architect"],
        },
        memory_empty=False,
        interaction_count=5,
    )
    check("intent greet known", r.intent == INTENT_GREET_KNOWN, r.intent)
    check("uses mother", "mother" in r.fallback_expression.lower(), r.fallback_expression)


def test_unit_stop() -> None:
    print("Unit: leave me alone")
    r = deliberate_communication(
        "leave me alone",
        known={FIELD_ADDRESS_NAME: "mother"},
        memory_empty=False,
        interaction_count=3,
    )
    check("intent stop", r.intent == INTENT_STOP, r.intent)
    check("stop expression", "stop" in r.fallback_expression.lower(), r.fallback_expression)


def test_live_stack() -> None:
    print("Live stack: wipe-like blank → hello → intro → hello")
    tmp = tempfile.mkdtemp(prefix="pbe_comm_")
    try:
        stack = build_stack(
            user_id="comm_user",
            data_root=Path(tmp),
            auto_enqueue_audits=False,
        )
        r1 = process_turn("Hello", stack=stack, quiet=True)
        text1 = (r1.get("reply_text") or "").lower()
        comm1 = r1.get("communicative_deliberation") or {}
        check(
            "live first hello intent introduce",
            comm1.get("intent") == INTENT_INTRODUCE_AND_LEARN,
            str(comm1.get("intent")),
        )
        check(
            "live first hello not bare hello",
            text1.strip() not in ("hello.", "hello")
            and (
                "who" in text1
                or "speaking" in text1
                or "name" in text1
                or "engine" in text1
                or "governance" in text1
            ),
            r1.get("reply_text"),
        )
        check("forces false turn1", not r1.get("forces_speech") and not r1.get("forces_question"))

        r2 = process_turn(
            "I am the architect designing your system. You can call me mother.",
            stack=stack,
            quiet=True,
        )
        rk = r2.get("relationship_knowledge") or {}
        check("live stores mother", str(rk.get("address_name") or "").lower() == "mother", str(rk))
        check("live stores is_maker", bool(rk.get("is_maker")), str(rk))
        text2 = (r2.get("reply_text") or "").lower()
        check("live ack maker", "making" in text2 or "architect" in text2, r2.get("reply_text"))
        check("live ack mother", "mother" in text2, r2.get("reply_text"))

        # Persist load
        loaded = load_relationship_knowledge(stack["store"], "comm_user")
        check(
            "persisted both facts",
            loaded.get("address_name") == "mother" and bool(loaded.get("is_maker")),
            str(loaded),
        )
        check("knowledge not blank", not knowledge_is_blank(loaded))

        r3 = process_turn("hello", stack=stack, quiet=True)
        text3 = (r3.get("reply_text") or "").lower()
        check("live known hello uses mother", "mother" in text3, r3.get("reply_text"))
        check(
            "live known hello intent greet",
            (r3.get("communicative_deliberation") or {}).get("intent")
            == INTENT_GREET_KNOWN,
            str((r3.get("communicative_deliberation") or {}).get("intent")),
        )
    except Exception as e:
        check(f"live suite raised: {e}", False)
        import traceback

        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_persist_helper() -> None:
    print("Persist helper")
    tmp = tempfile.mkdtemp(prefix="pbe_comm_p_")
    try:
        from persistence import LocalPersistence

        store = LocalPersistence(data_root=Path(tmp))
        r = deliberate_and_persist(
            "I am the one making it. Call me mother.",
            persistence=store,
            user_id="u1",
            memory_empty=False,
            interaction_count=1,
        )
        check("persist intent ack", r.intent == INTENT_ACK_FACTS, r.intent)
        loaded = load_relationship_knowledge(store, "u1")
        check("persist mother", loaded.get("address_name") == "mother", str(loaded))
        check("persist maker", bool(loaded.get("is_maker")), str(loaded))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("=" * 70)
    print("COMMUNICATIVE DELIBERATION + RELATIONSHIP KNOWLEDGE")
    print("=" * 70)
    print()
    for fn in (
        test_unit_first_meeting,
        test_unit_intro_two_facts,
        test_unit_known_greeting,
        test_unit_stop,
        test_persist_helper,
        test_live_stack,
    ):
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} raised: {e}", False)
            import traceback

            traceback.print_exc()
        print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
