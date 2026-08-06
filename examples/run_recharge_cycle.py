"""
run_recharge_cycle.py
=======================

Small, dedicated script that is today's trigger source for the automatic
recharge cycle (core/recharge_cycle.py's own docstring calls this out as
one of two interchangeable callers of ``is_recharge_window_open()`` — the
other being an in-process check; tomorrow's embodied caller is a
charging-dock sensor event asking the same question). Meant to be invoked
once a day by an OS-level scheduler, not run continuously.

For every known user (``LocalPersistence.list_user_ids()``): checks
``is_recharge_window_open(store, user_id, now)``. If all three gates hold,
runs ``AuditRunner.process_batch()`` (which also drives
``EngagementQueue.reassess()`` as of Phase 2 step 4) for that user. If any
gate fails, the cycle is skipped for that user and the reason is durably
recorded via ``record_cycle_result()`` — never silently retried more
aggressively, never forced through. Either way, the outcome is logged to
stdout and to the user's durable recharge state.

Registering with Windows Task Scheduler (not done automatically by this
script — run this yourself once, adjusting the path and time to taste)::

    schtasks /Create /SC DAILY /ST 05:15 ^
        /TN "PositronicBondEngine_RechargeCycle" ^
        /TR "python C:\\path\\to\\positronic-bond-engine\\examples\\run_recharge_cycle.py"

Pick a start time inside (or a little before) the configured recharge
window so the daily run actually lands inside it — the window itself is
configurable per user via ``core.recharge_cycle.set_recharge_window()``,
default ~5am for 3 hours (see that module for why it's a window, not a
single instant: a run that fires a few minutes early or late should not
miss the day entirely).

Run directly::

    $env:PYTHONPATH = "."
    python examples/run_recharge_cycle.py [--data-root PATH]

Exit code 0 always (a skipped cycle is not a failure) unless something
raises outside the per-user fail-soft boundary already built into
AuditRunner / EngagementQueue.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.local_model_config import load_local_env_file  # noqa: E402
from core.recharge_cycle import is_recharge_window_open, record_cycle_result  # noqa: E402
from persistence import LocalPersistence  # noqa: E402


def run_cycle_for_user(store: LocalPersistence, user_id: str, now: datetime) -> dict:
    """Check the gate for one user; run the batch and return a summary dict
    if it opens, otherwise record and return the skip reasons."""
    gate = is_recharge_window_open(store, user_id, now)
    if not gate.should_run:
        record_cycle_result(store, user_id, gate, ran=False)
        return {"user_id": user_id, "ran": False, "gate": gate.to_dict()}

    # Offline EthicsEngine instance for the runner's re-deliberation step —
    # matches AuditRunner's own class docstring example and
    # build_runner_from_persistence()'s intended usage; never the live
    # per-turn engine.
    runner = store.get_audit_runner(user_id, ethics_engine=EthicsEngine())
    report = runner.process_batch()
    record_cycle_result(store, user_id, gate, ran=True)
    return {"user_id": user_id, "ran": True, "gate": gate.to_dict(), "report": report.to_dict()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override the local data root (defaults to the standard PBE data dir).",
    )
    args = parser.parse_args()

    load_local_env_file()  # .pbe_model.env, if present -- see that module
    store = LocalPersistence(args.data_root)
    now = datetime.now(timezone.utc)

    user_ids = store.list_user_ids()
    print(f"Recharge cycle check at {now.isoformat()} — {len(user_ids)} known user(s).")
    if not user_ids:
        print("No users known yet; nothing to do.")
        return 0

    ran_count = 0
    for user_id in user_ids:
        try:
            result = run_cycle_for_user(store, user_id, now)
        except Exception as exc:  # noqa: BLE001 - a scheduled script must not crash the whole run over one user
            print(f"  [{user_id}] cycle raised (skipped, not retried): {exc}")
            continue
        if result["ran"]:
            ran_count += 1
            report = result["report"]
            print(
                f"  [{user_id}] RAN — processed={len(report['processed'])} "
                f"completed={len(report['completed'])}"
            )
        else:
            reasons = "; ".join(result["gate"]["reasons"]) or "unknown"
            print(f"  [{user_id}] skipped — {reasons}")

    print(f"Done. {ran_count}/{len(user_ids)} user(s) ran this cycle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
