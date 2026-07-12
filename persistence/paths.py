"""
paths.py
========

Resolve and manage local data directories for persistence.

Default layout (under the data root)::

    <data_root>/
      users/
        <user_id>/
          baseline.json
          bond_state.json
          settings.json
          decision_logs.jsonl
      README.txt   # human-readable note about privacy and deletion

Everything remains on the local filesystem. Users can delete any path
to erase data permanently from this store.
"""

from __future__ import annotations

import re
from pathlib import Path

# Safe user id: letters, digits, underscore, hyphen only
_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

DEFAULT_DATA_DIRNAME = "pbe_data"


def default_data_root(base: Path | None = None) -> Path:
    """Return the default local data root.

    Prefer an explicit ``base``; otherwise use ``./pbe_data`` relative to
    the current working directory (simple, visible, easy to delete).

    Later deployment configs may override this (e.g. platform app-data dirs)
    without changing store APIs.
    """
    if base is not None:
        return Path(base).expanduser().resolve()
    return (Path.cwd() / DEFAULT_DATA_DIRNAME).resolve()


def sanitize_user_id(user_id: str) -> str:
    """Validate user_id for use as a directory name.

    Raises:
        ValueError: if the id is empty or contains unsafe characters.
    """
    uid = (user_id or "").strip()
    if not uid or not _USER_ID_RE.match(uid):
        raise ValueError(
            "user_id must be 1–64 chars of [a-zA-Z0-9_-] only "
            f"(got {user_id!r}). This keeps paths local and safe."
        )
    return uid


def user_dir(data_root: Path, user_id: str) -> Path:
    """Return ``<data_root>/users/<user_id>/`` (not necessarily created)."""
    return Path(data_root) / "users" / sanitize_user_id(user_id)


def ensure_user_dir(data_root: Path, user_id: str) -> Path:
    """Create and return the per-user directory."""
    path = user_dir(data_root, user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
