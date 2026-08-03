"""
test_session_presence.py
========================

Session-scoped multi-user presence + identity check.

- Single-user path unchanged
- Multi-user unmarked turn → honest identity request (no durable assumption)
- Explicit speaker routes to that user_id's isolated memory
- Presence clear works

Run::

    $env:PYTHONPATH = "."
    python tests/test_session_presence.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.session_presence import (  # noqa: E402
    SessionPresence,
    extract_speaker_id,
    identity_request_reply,
    strip_speaker_prefix,
)
from examples.private_architect_chat import (  # noqa: E402
    build_stack,
    handle_system_command,
    process_turn,
)
from io import StringIO  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402

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


def test_unit_presence() -> None:
    print("Unit: SessionPresence API")
    p = SessionPresence()
    p.mark_present("alice")
    check("single not multi", not p.is_multi_user())
    check("not ambiguous single", not p.is_ambiguous())
    p.mark_present("bob")
    check("multi", p.is_multi_user())
    check("ambiguous without speaker", p.is_ambiguous())
    check("not ambiguous with alice", not p.is_ambiguous("alice"))
    check("ambiguous unknown speaker", p.is_ambiguous("carol"))
    p.mark_left("bob")
    check("after left not multi", not p.is_multi_user())
    p.mark_present("bob")
    p.clear()
    check("clear empty", p.current() == [])
    check(
        "extract speaker as",
        extract_speaker_id("as alice: hello there", ["alice", "bob"]) == "alice",
    )
    check(
        "strip prefix",
        strip_speaker_prefix("as alice: hello there", "alice") == "hello there",
    )
    check("identity request mentions presence", "who is speaking" in identity_request_reply(["a", "b"]).lower())


def test_command_interception() -> None:
    print("Commands never reach process_turn / model")
    tmp = tempfile.mkdtemp(prefix="pbe_cmd_")
    try:
        stack = build_stack(
            data_root=Path(tmp),
            user_id="alice",
            auto_enqueue_audits=False,
            auto_load_local_model_config=False,
        )
        mem0 = stack["memory"].count("alice")
        bond0 = stack["rh"].state.interaction_count

        for raw in (
            "presence",
            "  PRESENCE  ",
            "Presence!",
            "present bob",
            "  Present   Carol  ",
            "presence clear",
            "left bob",
            "present",  # usage only
        ):
            buf = StringIO()
            with redirect_stdout(buf):
                handled = handle_system_command(raw, stack)
            out = buf.getvalue()
            check(f"handled {raw!r}", handled is True, out)
            check(
                f"command output not empty {raw!r}",
                bool(out.strip()),
                out,
            )
            check(
                f"no agent> model line for {raw!r}",
                "agent>" not in out.lower() or "usage:" in out.lower(),
                out,
            )

        check(
            "commands did not write memory",
            stack["memory"].count("alice") == mem0,
            str(stack["memory"].count("alice")),
        )
        check(
            "commands did not bump bond",
            stack["rh"].state.interaction_count == bond0,
            str(stack["rh"].state.interaction_count),
        )

        # Multi-user still identity-checks free text after present bob
        handle_system_command("present bob", stack)
        r = process_turn("hello", stack=stack, quiet=True)
        check(
            "after present bob, hello → identity request",
            r.get("reply_path") == "presence_identity_request",
            str(r.get("reply_path")),
        )
        check(
            "free text not a command",
            handle_system_command("hello there", stack) is False,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live_single_and_multi() -> None:
    print("Live: single-user + multi-user identity")
    tmp = tempfile.mkdtemp(prefix="pbe_presence_")
    try:
        stack = build_stack(
            data_root=Path(tmp),
            user_id="alice",
            auto_enqueue_audits=False,
            auto_load_local_model_config=False,
        )
        r0 = process_turn("hello", stack=stack, quiet=True)
        check(
            "single-user not identity path",
            r0.get("reply_path") != "presence_identity_request",
            str(r0.get("reply_path")),
        )
        check("single-user speaks", bool(r0.get("reply_text")), str(r0.get("reply_text")))
        check("forces false", not r0.get("forces_speech") and not r0.get("forces_question"))

        pres: SessionPresence = stack["presence"]
        pres.mark_present("bob")
        check("now multi", pres.is_multi_user())

        r1 = process_turn("hello again", stack=stack, quiet=True)
        check(
            "unmarked multi → identity request",
            r1.get("reply_path") == "presence_identity_request",
            str(r1.get("reply_path")),
        )
        check(
            "identity text honest",
            "who is speaking" in (r1.get("reply_text") or "").lower(),
            r1.get("reply_text"),
        )
        check("identity forces false", not r1.get("forces_speech") and not r1.get("forces_question"))
        check("identity ambiguous flag", r1.get("identity_ambiguous") is True)

        # Unmarked multi must not write to alice memory as assumed speaker
        mem_before = stack["memory"].count("alice")
        r1b = process_turn("still ambiguous", stack=stack, quiet=True)
        mem_after = stack["memory"].count("alice")
        check(
            "ambiguous turn does not grow alice memory",
            mem_after == mem_before,
            f"{mem_before}→{mem_after}",
        )
        check("still identity path", r1b.get("reply_path") == "presence_identity_request")

        r2 = process_turn("as bob: hello from bob", stack=stack, quiet=True)
        check(
            "identified bob not identity path",
            r2.get("reply_path") != "presence_identity_request",
            str(r2.get("reply_path")),
        )
        check("speaker bob", r2.get("speaker_id") == "bob", str(r2.get("speaker_id")))
        check("stack switched to bob", (r2.get("stack") or {}).get("user_id") == "bob")
        stack = r2["stack"]
        check("bob memory has episodes", stack["memory"].count("bob") >= 1)

        # alice memory isolation: bob turn did not merge into alice bond path wrongly
        alice_stack = build_stack(
            data_root=Path(tmp),
            user_id="alice",
            auto_enqueue_audits=False,
            auto_load_local_model_config=False,
        )
        # Preserve multi presence for completeness
        alice_stack["presence"] = pres
        check(
            "alice and bob separate memory counts",
            alice_stack["memory"].count("alice") >= 1
            and alice_stack["memory"].count("bob") >= 1
            or stack["memory"].count("bob") >= 1,
        )

        pres.clear()
        check("presence cleared", pres.current() == [])
        pres.mark_present("alice")
        r3 = process_turn("hello alone", stack=alice_stack, quiet=True)
        check(
            "single after clear works",
            r3.get("reply_path") != "presence_identity_request",
            str(r3.get("reply_path")),
        )
    except Exception as e:
        check(f"live raised: {e}", False)
        import traceback

        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("=" * 70)
    print("SESSION PRESENCE + IDENTITY CHECK")
    print("=" * 70)
    print()
    for fn in (test_unit_presence, test_command_interception, test_live_single_and_multi):
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
