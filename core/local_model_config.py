"""
local_model_config.py
======================

Optional convenience loader for PBE_MODEL_* configuration from a local,
gitignored text file instead of requiring persistent OS environment
variables.

Why this exists: ``core/content_provider.py``'s ``config_from_env()`` (and
``core/contextual_judgment.py``'s default ``ContextualJudge()``) read the
base-model connection details purely from ``os.environ`` — that's the
documented mechanism (see ``docs/model_providers.md`` and AGENTS.md §2/§10).
On Windows, setting a *persistent* environment variable normally means
either editing System Properties, or running ``setx`` and then restarting
every terminal/IDE that should see it — annoying friction for something as
low-stakes as "point this at my local Ollama."

This module does NOT replace the env-var mechanism — it only offers an
additional, explicit, opt-in way to populate it from a plain file, using
``os.environ.setdefault`` so a real OS/shell environment variable always
wins if both are present. It is never imported or invoked automatically by
``content_provider.py`` or anywhere else — a caller (a script, a CLI entry
point) must explicitly call ``load_local_env_file()`` before constructing a
provider/judge. This is deliberate: importing content_provider.py must not
have the side effect of silently changing which model config wins, and the
existing test suite must keep seeing an unconfigured, inert default unless a
test explicitly opts in — see tests/test_local_model_config.py.

Usage (see examples/verify_local_model.py for the full flow)::

    from core.local_model_config import load_local_env_file
    load_local_env_file()  # applies .pbe_model.env, if present, before...
    from core.contextual_judgment import ContextualJudge
    judge = ContextualJudge()  # ...this reads the now-populated env vars
"""

from __future__ import annotations

import os

DEFAULT_FILENAME = ".pbe_model.env"


def _repo_root() -> str:
    # core/local_model_config.py -> core/ -> repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_local_env_file(
    filename: str = DEFAULT_FILENAME, *, path: str | None = None
) -> dict[str, str]:
    """Apply ``KEY=VALUE`` lines from a local config file to ``os.environ``.

    Args:
        filename: File name to look for at the repo root (default
            ``.pbe_model.env``, already gitignored — see .gitignore's
            "Local model connection config" section).
        path: Optional explicit path, overriding the repo-root lookup
            (mainly for tests).

    Returns:
        Dict of the keys actually applied this call (empty if the file is
        missing, empty, or every key was already set in the environment —
        real env vars always win, this never overwrites one). Never raises;
        any parse/IO problem is treated the same as "file not present."

    Format: one ``KEY=VALUE`` per line. Blank lines and lines starting with
    ``#`` are ignored. Values may be wrapped in matching single or double
    quotes (stripped). No interpolation, no multi-line values, no export
    keyword — deliberately minimal, not a full dotenv implementation.
    """
    target = path if path is not None else os.path.join(_repo_root(), filename)
    applied: dict[str, str] = {}
    try:
        if not os.path.isfile(target):
            return applied
        with open(target, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if not key:
                    continue
                if key not in os.environ:
                    os.environ[key] = value
                    applied[key] = value
    except OSError:
        return {}
    return applied
