"""
test_recharge_cycle.py
========================

core/recharge_cycle.py: the three automatic gates (window / pause / no
live session) individually and combined, pause set/clear, skip-and-log
behavior, the manual "go to sleep" phrase matcher (positive and negative
cases), the ethics-gate bypass, and implicit wake on next interaction.

Run::

    $env:PYTHONPATH = "."
    python tests/test_recharge_cycle.py
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

from core.content_provider import ProviderConfig  # noqa: E402
from core.recharge_cycle import (  # noqa: E402
    SESSION_STALE_SECONDS,
    go_to_sleep,
    is_asleep,
    is_paused,
    is_recharge_window_open,
    is_sleep_command,
    load_recharge_state,
    maybe_wake,
    record_cycle_result,
    set_pause,
    set_recharge_window,
)
from core.session_time import begin_session, set_timezone, touch_turn  # noqa: E402
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
    print("RECHARGE CYCLE (automatic gates + manual emergency sleep)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="pbe_recharge_"))
    try:
        store = LocalPersistence(tmp)
        base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

        # ------------------------------------------------------------
        # Gate 1: within-window check, individually
        # ------------------------------------------------------------
        uid = "gate_user"
        set_timezone(store, uid, "UTC")

        in_window = base + timedelta(hours=6)  # default window 5:00-8:00
        gate_in = is_recharge_window_open(store, uid, in_window)
        check(
            "within_window True inside the default 5am-8am window",
            gate_in.within_window is True,
            str(gate_in.to_dict()),
        )

        out_window = base + timedelta(hours=14)
        gate_out = is_recharge_window_open(store, uid, out_window)
        check(
            "within_window False at 2pm",
            gate_out.within_window is False,
            str(gate_out.to_dict()),
        )
        check(
            "should_run False when outside window even with nothing else wrong",
            gate_out.should_run is False,
        )

        # Custom window, including midnight wraparound
        set_recharge_window(store, uid, start_hour=23, duration_hours=4.0)
        wrap_inside = base + timedelta(hours=1)  # 1am, inside 23:00-03:00
        wrap_outside = base + timedelta(hours=10)
        check(
            "custom wraparound window: 1am counts as inside 23:00+4h",
            is_recharge_window_open(store, uid, wrap_inside).within_window is True,
        )
        check(
            "custom wraparound window: 10am counts as outside",
            is_recharge_window_open(store, uid, wrap_outside).within_window is False,
        )
        set_recharge_window(store, uid, start_hour=5, duration_hours=3.0)  # restore default

        # No timezone set -> conservative "window cannot be confirmed open"
        no_tz_uid = "no_timezone_gate_user"
        gate_no_tz = is_recharge_window_open(store, no_tz_uid, in_window)
        check(
            "no timezone set: within_window False (conservative, not a guess)",
            gate_no_tz.within_window is False,
            str(gate_no_tz.to_dict()),
        )

        # ------------------------------------------------------------
        # Gate 2: not-paused, individually + set/clear
        # ------------------------------------------------------------
        check("not paused by default", is_paused(store, uid) is False)
        gate_before_pause = is_recharge_window_open(store, uid, in_window)
        check("not_paused True before pausing", gate_before_pause.not_paused is True)

        set_pause(store, uid, True, reason="streaming tonight")
        check("is_paused True after set_pause(True)", is_paused(store, uid) is True)
        gate_paused = is_recharge_window_open(store, uid, in_window)
        check(
            "not_paused False, should_run False while paused (even in-window)",
            gate_paused.not_paused is False and gate_paused.should_run is False,
            str(gate_paused.to_dict()),
        )
        check(
            "pause reason surfaced in reasons",
            any("streaming tonight" in r for r in gate_paused.reasons),
            str(gate_paused.reasons),
        )

        set_pause(store, uid, False)
        check("is_paused False after set_pause(False)", is_paused(store, uid) is False)
        gate_unpaused = is_recharge_window_open(store, uid, in_window)
        check(
            "not_paused True again after clearing pause",
            gate_unpaused.not_paused is True,
        )

        # ------------------------------------------------------------
        # Gate 3: no-live-session, individually
        # ------------------------------------------------------------
        session_uid = "session_gate_user"
        set_timezone(store, session_uid, "UTC")
        gate_no_touch_ever = is_recharge_window_open(store, session_uid, in_window)
        check(
            "no_live_session True when the user has never touched the system",
            gate_no_touch_ever.no_live_session is True,
        )

        begin_session(store, session_uid, now_fn=lambda: in_window, force_new=True)
        touch_turn(store, session_uid, now_fn=lambda: in_window)
        gate_just_touched = is_recharge_window_open(
            store, session_uid, in_window + timedelta(minutes=1)
        )
        check(
            "no_live_session False 1 minute after a real touch",
            gate_just_touched.no_live_session is False,
            str(gate_just_touched.to_dict()),
        )
        check(
            "should_run False overall while a live session is in progress",
            gate_just_touched.should_run is False,
        )

        gate_stale = is_recharge_window_open(
            store,
            session_uid,
            in_window + timedelta(seconds=SESSION_STALE_SECONDS + 1),
        )
        check(
            "no_live_session True again once past SESSION_STALE_SECONDS",
            gate_stale.no_live_session is True,
            str(gate_stale.to_dict()),
        )

        # ------------------------------------------------------------
        # All three gates combined
        # ------------------------------------------------------------
        combo_uid = "combo_user"
        set_timezone(store, combo_uid, "UTC")
        begin_session(store, combo_uid, now_fn=lambda: in_window, force_new=True)
        touch_turn(store, combo_uid, now_fn=lambda: in_window)

        far_later = in_window + timedelta(seconds=SESSION_STALE_SECONDS + 1)
        gate_all_good = is_recharge_window_open(store, combo_uid, far_later)
        check(
            "combined: all three gates satisfied -> should_run True",
            gate_all_good.should_run is True
            and gate_all_good.within_window
            and gate_all_good.not_paused
            and gate_all_good.no_live_session,
            str(gate_all_good.to_dict()),
        )

        set_pause(store, combo_uid, True, reason="test")
        # Fresh touch outside the window, checked shortly after, so all
        # three gates fail together: outside window, paused, AND a live
        # session (recent touch) in progress.
        touch_turn(store, combo_uid, now_fn=lambda: out_window)
        gate_all_bad = is_recharge_window_open(
            store, combo_uid, out_window + timedelta(minutes=1)
        )
        check(
            "combined: window closed timing + paused + live session -> all three False",
            not gate_all_bad.within_window
            and not gate_all_bad.not_paused
            and not gate_all_bad.no_live_session
            and gate_all_bad.should_run is False,
            str(gate_all_bad.to_dict()),
        )
        set_pause(store, combo_uid, False)

        # ------------------------------------------------------------
        # Skip-and-log behavior
        # ------------------------------------------------------------
        log_uid = "log_user"
        set_timezone(store, log_uid, "UTC")
        skip_gate = is_recharge_window_open(store, log_uid, out_window)
        record_cycle_result(store, log_uid, skip_gate, ran=False)
        logged = load_recharge_state(store, log_uid)
        check(
            "skipped cycle durably recorded as not-ran",
            logged.last_cycle_ran is False,
            str(logged.to_dict()),
        )
        check(
            "skip reasons are logged, not swallowed silently",
            bool(logged.last_cycle_reasons)
            and any("window" in r for r in logged.last_cycle_reasons),
            str(logged.last_cycle_reasons),
        )

        ran_gate = is_recharge_window_open(store, log_uid, in_window)
        record_cycle_result(store, log_uid, ran_gate, ran=True)
        logged2 = load_recharge_state(store, log_uid)
        check(
            "a cycle that actually ran is also durably recorded",
            logged2.last_cycle_ran is True,
        )

        # ------------------------------------------------------------
        # Manual sleep command: phrase matching (recall-biased, tested
        # positive and negative cases)
        # ------------------------------------------------------------
        positive_cases = [
            "go to sleep",
            "Go To Sleep",
            "go sleep",
            "go recharge",
            "please go to sleep now",
            "time to recharge",
            "time to sleep",
            "go to your dock",
            "go charge",
            "power down",
            "sleep now",
            "recharge now",
        ]
        for phrase in positive_cases:
            check(f"sleep command matches: {phrase!r}", is_sleep_command(phrase) is True)

        negative_cases = [
            "I'm exhausted, this app puts me to sleep",
            "I need to sleep",
            "I'm going to sleep soon",
            "let's stop for lunch",
            "I can't sleep lately",
            "having trouble sleeping",
            "",
            "hello there",
        ]
        for phrase in negative_cases:
            check(
                f"sleep command does NOT match: {phrase!r}",
                is_sleep_command(phrase) is False,
            )

        # ------------------------------------------------------------
        # go_to_sleep(): forces Asleep, fail-soft VRAM release
        # ------------------------------------------------------------
        sleep_uid = "sleep_action_user"
        check("not asleep before go_to_sleep", is_asleep(store, sleep_uid) is False)

        unreachable_cfg = ProviderConfig(
            base_url="http://127.0.0.1:1/v1", enabled=True, timeout_s=1.0, profile="ollama"
        )
        result = go_to_sleep(store, sleep_uid, provider_config=unreachable_cfg, now=in_window)
        check("asleep True immediately after go_to_sleep", is_asleep(store, sleep_uid) is True)
        check(
            "go_to_sleep never raises even when VRAM release fails (fail-soft)",
            isinstance(result, dict) and "vram_release" in result,
            str(result),
        )
        check(
            "durable Asleep state is set even though VRAM release failed",
            result["state"].asleep is True and result["vram_release"]["ok"] is False,
            str(result),
        )

        # Non-ollama profile: documented no-op, not a crash
        cloud_cfg = ProviderConfig(base_url="https://example.invalid/v1", profile="openai_compatible")
        cloud_result = go_to_sleep(store, "cloud_user", provider_config=cloud_cfg, now=in_window)
        check(
            "non-ollama profile: VRAM release is a documented no-op",
            cloud_result["vram_release"]["attempted"] is False
            and cloud_result["vram_release"]["error"] == "no_release_mechanism_for_this_profile",
            str(cloud_result["vram_release"]),
        )

        # ------------------------------------------------------------
        # Implicit wake resumes Awake automatically on next interaction
        # ------------------------------------------------------------
        check(
            "maybe_wake clears asleep state",
            maybe_wake(store, sleep_uid, now=in_window + timedelta(minutes=5)).asleep is False,
        )
        check("is_asleep False after maybe_wake", is_asleep(store, sleep_uid) is False)
        woke_state = load_recharge_state(store, sleep_uid)
        check("woke_at recorded", bool(woke_state.woke_at), str(woke_state.to_dict()))

        # maybe_wake on an already-awake user is a safe no-op
        already_awake_uid = "already_awake_user"
        state_noop = maybe_wake(store, already_awake_uid, now=in_window)
        check(
            "maybe_wake on an already-awake user is a safe no-op",
            state_noop.asleep is False,
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
