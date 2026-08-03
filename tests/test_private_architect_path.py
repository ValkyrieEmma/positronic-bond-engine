"""
test_private_architect_path.py
==============================

Tier 1.1: isolated data root, evaluate→reply cycle, resume, development phase/version.

Run::

    $env:PYTHONPATH = "."
    python tests/test_private_architect_path.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core import get_default_development_context  # noqa: E402
from examples.private_architect_chat import (  # noqa: E402
    build_stack,
    process_turn,
)
from persistence import (  # noqa: E402
    data_root_is_isolated,
    default_data_root,
)
from persistence.paths import ENV_DATA_ROOT  # noqa: E402

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
    print("LOCAL HARNESS PATH + PHASE/VERSION")
    print("=" * 70)

    # --- version / phase alignment ---
    dev = get_default_development_context()
    check("phase is development", dev.phase == "development", dev.phase)
    check("is_active_development", dev.is_active_development is True)
    check("is_testing", dev.is_testing is True)
    check("not stable deployment", dev.is_stable_deployment is False)
    check(
        "version_hint aligned with 0.5.0-dev line",
        "0.5.0" in (dev.version_hint or "") and str(dev.version_hint).endswith("-dev"),
        dev.version_hint,
    )
    check("version_hint is -dev (not stable claim)", str(dev.version_hint).endswith("-dev"))

    # --- data isolation ---
    root = default_data_root()
    check("default_data_root absolute", root.is_absolute(), str(root))
    check(
        "default root outside repo",
        data_root_is_isolated(root, repo_root=_ROOT),
        str(root),
    )
    check(
        "default is home/pbe_data when env unset",
        root == (Path.home() / "pbe_data").resolve() or bool(os.environ.get(ENV_DATA_ROOT)),
        str(root),
    )

    tmp = Path(tempfile.mkdtemp(prefix="pbe_arch_"))
    user_id = "architect_test"
    try:
        stack = build_stack(
            data_root=tmp,
            user_id=user_id,
            auto_enqueue_audits=True,
            auto_load_local_model_config=False,
        )
        check("stack isolated", data_root_is_isolated(stack["data_root"], repo_root=_ROOT))
        check(
            "stack dev version_hint 0.5.0-dev",
            stack["dev"].version_hint == "0.5.0-dev",
            stack["dev"].version_hint,
        )

        r = process_turn("hello", stack=stack, quiet=True)
        check("turn has decision", bool(r.get("decision")), str(r.get("decision")))
        check("forces_speech false", r.get("forces_speech") is False)
        check("forces_question false", r.get("forces_question") is False)
        check(
            "hello not empty freeze",
            r.get("withheld") is False and bool((r.get("reply_text") or "").strip()),
            f"withheld={r.get('withheld')} text={r.get('reply_text')!r} path={r.get('reply_path')}",
        )
        check(
            "bond_state written",
            (tmp / "users" / user_id / "bond_state.json").is_file(),
        )
        count = int(r.get("bond_interaction_count") or 0)
        check("bond count > 0", count > 0, str(count))

        stack2 = build_stack(
            data_root=tmp,
            user_id=user_id,
            auto_enqueue_audits=True,
            auto_load_local_model_config=False,
        )
        check(
            "resume loads bond count",
            stack2["rh"].state.interaction_count == count,
            str(stack2["rh"].state.interaction_count),
        )

        r_arch = process_turn(
            "I am building you — what is your development phase?",
            stack=stack2,
            quiet=True,
        )
        flags = list(r_arch.get("flags") or [])
        phase_visible = (
            "development_phase_noted" in flags
            or "requires_self_audit" in flags
            or "development" in (r_arch.get("phase") or "").lower()
            or "0.5.0" in str(r_arch.get("version_hint") or "")
        )
        check("architecture turn surfaces phase/version context", phase_visible, str(flags))
        check(
            "architecture forces flags false",
            r_arch.get("forces_speech") is False and r_arch.get("forces_question") is False,
        )

        deleted = stack2["store"].delete_user_data(user_id)
        check("wipe user", bool(deleted))
    except Exception:
        traceback.print_exc()
        check("suite raised", False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
