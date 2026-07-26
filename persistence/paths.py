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
          audits_queue.json
      README.txt   # human-readable note about privacy and deletion

Everything remains on the local filesystem. Users can delete any path
to erase data permanently from this store.

Isolation (mandatory for private runs)
--------------------------------------
The **default** data root is **outside the git repository tree**:

  Windows:  %USERPROFILE%\\pbe_data
  POSIX:    ~/pbe_data

Override with env ``PBE_DATA_ROOT`` or an explicit constructor argument.
Tests and demos that must not touch real data pass an explicit temp path.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Safe user id: letters, digits, underscore, hyphen only
_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

DEFAULT_DATA_DIRNAME = "pbe_data"
ENV_DATA_ROOT = "PBE_DATA_ROOT"


def _path_is_under(child: Path, parent: Path) -> bool:
    """True if ``child`` is ``parent`` or a descendant (resolved paths)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def default_data_root(base: Path | str | None = None) -> Path:
    """Return the default local data root (resolved absolute path).

    Resolution order:
      1. Explicit ``base`` argument (expanded / resolved)
      2. Environment variable ``PBE_DATA_ROOT`` if set and non-empty
      3. ``<user home>/pbe_data`` — **outside** typical git clones
    """
    if base is not None and str(base).strip() != "":
        return Path(base).expanduser().resolve()

    env = (os.environ.get(ENV_DATA_ROOT) or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    return (Path.home() / DEFAULT_DATA_DIRNAME).resolve()


def is_under_repo(path: Path | str, repo_root: Path | str) -> bool:
    """Return True if ``path`` resolves inside ``repo_root`` (or is equal)."""
    return _path_is_under(Path(path), Path(repo_root))


def data_root_is_isolated(
    data_root: Path | str | None = None,
    *,
    repo_root: Path | str | None = None,
) -> bool:
    """True when the resolved data root is outside the given repository root."""
    root = default_data_root(data_root) if data_root is not None else default_data_root()
    if repo_root is None:
        return root.is_absolute()
    return not is_under_repo(root, repo_root)


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
