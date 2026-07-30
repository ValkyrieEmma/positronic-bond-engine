"""
test_zz_pytest_bridge.py
=========================

Makes every standalone check()-based script in this directory a real,
pytest-discoverable, pytest-*failing* test (Phase 1 roadmap item 3).

The problem this fixes: a bare ``pytest tests/`` previously collected only
23 tests across 3 files (test_communicative_deliberation.py,
test_content_provider.py, test_session_presence.py) — the only scripts that
happen to define module-level ``def test_*(...)`` functions pytest's default
collector recognizes — and silently skipped every other script's assertions
entirely. Worse, even those 23 "covered" functions call a local ``check()``
helper that only prints a ``[PASS]``/``[FAIL]`` line and increments a
counter; it never raises ``AssertionError``. Pytest only sees "the function
returned without raising," so all 23 were reported green regardless of
whether their internal checks actually passed — a false-confidence trap,
not real coverage.

Every script in this directory already exposes ``main() -> int`` (0 = every
check() in it passed, non-zero = at least one failed), used for its own
standalone invocation (``python tests/test_X.py``) via
``if __name__ == "__main__": raise SystemExit(main())``. This bridge does
not modify a single one of those scripts — it discovers every other
``test_*.py`` module in this directory at collection time, and generates one
real, assertion-backed pytest test per module that imports it fresh and
requires its existing ``main()`` to return 0. Standalone
``python tests/test_X.py`` usage for every script is completely unaffected;
this file only adds an additional way to run them, it does not change them.

Deliberately named with a ``zz`` prefix so it sorts and collects after the
scripts it wraps, and reads unambiguously as pytest-only infrastructure
rather than a 31st product test.

This is intentionally coarse — one pass/fail per file, not per individual
check() — but it is a *real* pass/fail: pytest now actually fails when any
script's check()s fail, and per-check detail is still fully visible in the
[PASS]/[FAIL] lines each script prints (pytest shows captured stdout on
failure).

Run (only meaningful under pytest; there is no standalone mode for this
bridge file itself)::

    $env:PYTHONPATH = "."
    pytest tests/
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_THIS_FILE = Path(__file__).resolve()


def _discover_script_modules() -> list[Path]:
    return sorted(
        p
        for p in _TESTS_DIR.glob("test_*.py")
        if p.resolve() != _THIS_FILE
    )


_SCRIPTS: list[Path] = _discover_script_modules()


def _load_main(script_path: Path) -> Callable[[], int] | None:
    """Import one standalone script as its own private module and return its main().

    Imported under a private module name (never the bare stem) so this never
    collides with pytest's own separate default collection of the same file
    (which imports it under its natural module name to find any module-level
    ``test_*`` functions it happens to define) — the two collection paths
    run the script's top-level code independently and do not interfere with
    each other or share global state.
    """
    mod_name = f"_pbe_standalone_script__{script_path.stem}"
    if mod_name in sys.modules:
        return getattr(sys.modules[mod_name], "main", None)
    spec = importlib.util.spec_from_file_location(mod_name, script_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return getattr(module, "main", None)


@pytest.mark.parametrize("script_path", _SCRIPTS, ids=lambda p: p.name)
def test_standalone_script_passes(script_path: Path) -> None:
    """Run one tests/test_*.py script's main() and require exit code 0.

    This is what makes ``pytest tests/`` actually exercise every check() in
    every script (not just the ones that happened to live in module-level
    test_-prefixed functions already) and actually fail the run when any of
    them reports a failing check().
    """
    main_fn = _load_main(script_path)
    assert main_fn is not None, f"{script_path.name} has no main() entry point"
    rc = main_fn()
    assert rc == 0, (
        f"{script_path.name} main() reported one or more failing check()s "
        f"(exit code {rc}) — see captured stdout above for the specific "
        "[FAIL] line(s)."
    )
