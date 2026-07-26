"""
test_session_time.py
====================

Wall-clock / session time awareness: durable bags, inject clock, wipe clears,
greeting may note long idle without soft theater.

Run::

    $env:PYTHONPATH = "."
    python tests/test_session_time.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.session_time import (  # noqa: E402
    LONG_IDLE_SECONDS,
    SESSION_STALE_SECONDS,
    begin_session,
    load_session_time,
    touch_turn,
)
from examples.private_architect_chat import (  # noqa: E402
    build_stack,
    process_turn,
    wipe_user_session,
)
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


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kwargs: float) -> None:
        self.t = self.t + timedelta(**kwargs)


def main() -> int:
    print("=" * 70)
    print("SESSION TIME AWARENESS")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_sess_"))
    uid = "time_user"
    try:
        store = LocalPersistence(tmp)
        clock = _Clock(datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc))

        ctx0 = begin_session(store, uid, now_fn=clock, force_new=True)
        check("begin_session has session_id", bool(ctx0.get("session_id")))
        check("turn_index starts 0", ctx0.get("turn_index_session") == 0)
        check("first_seen set", bool(ctx0.get("first_seen_at")))
        sid0 = ctx0.get("session_id")

        ctx1 = touch_turn(store, uid, now_fn=clock)
        check("first touch turn_index=1", ctx1.get("turn_index_session") == 1)
        check("same session_id after touch", ctx1.get("session_id") == sid0)

        clock.advance(seconds=30)
        ctx2 = touch_turn(store, uid, now_fn=clock)
        check("second touch turn_index=2", ctx2.get("turn_index_session") == 2)
        check(
            "idle_before ~30s",
            ctx2.get("idle_seconds") is not None
            and abs(float(ctx2.get("idle_seconds")) - 30) < 1,
            str(ctx2.get("idle_seconds")),
        )
        check("not long_idle yet", ctx2.get("long_idle") is False)

        # Long idle → new session on next touch
        clock.advance(seconds=SESSION_STALE_SECONDS + 10)
        ctx3 = touch_turn(store, uid, now_fn=clock)
        check(
            "long gap rolls session_id",
            ctx3.get("session_id") != sid0,
            f"{ctx3.get('session_id')} vs {sid0}",
        )
        check("turn_index reset after roll", ctx3.get("turn_index_session") == 1)

        # Durable load
        loaded = load_session_time(store, uid)
        check("persisted last_turn_at", bool(loaded.last_turn_at))
        check("persisted first_seen survives", bool(loaded.first_seen_at))

        # Long idle greeting via private chat
        clock2 = _Clock(datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc))
        stack = build_stack(data_root=tmp, user_id="greet_user", auto_enqueue_audits=False)
        stack["now_fn"] = clock2
        # seed name + a turn
        process_turn(
            "You can call me mother.",
            stack=stack,
            quiet=True,
        )
        # simulate long idle
        clock2.advance(seconds=LONG_IDLE_SECONDS + 60)
        # new process-like begin then greeting
        stack["session_context"] = begin_session(
            stack["store"], "greet_user", now_fn=clock2, force_new=False
        )
        r = process_turn("hello", stack=stack, quiet=True)
        text = (r.get("reply_text") or "").lower()
        check(
            "greeting after long idle may say hello again",
            "hello" in text
            and ("again" in text or "mother" in text),
            r.get("reply_text"),
        )
        check(
            "session_context on result",
            isinstance(r.get("session_context"), dict)
            and r["session_context"].get("turn_index_session") is not None,
            str(r.get("session_context")),
        )
        check(
            "no soft caution on time greeting",
            "no pressure" not in text and "only if useful" not in text,
            r.get("reply_text"),
        )

        # Wipe clears session_time
        stack2 = wipe_user_session(stack, auto_enqueue=False)
        cleared = load_session_time(stack2["store"], "greet_user")
        # After wipe + rebuild, begin_session creates fresh — first_seen may be set again
        # but old long history gone: turn index from new begin is 0 until touch
        check(
            "wipe + rebuild has fresh session bag or empty pre-touch",
            cleared.turn_index_session == 0
            or cleared.session_id != (r.get("session_context") or {}).get("session_id"),
            cleared.to_dict(),
        )

    except Exception as e:
        check(f"suite raised: {e}", False)
        import traceback

        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
