"""
verified_core.py
================

Security gap 1: read-only, integrity-verified ethics core.

The ethics/ontology data the governor loads lives in ``core/ethics_core/``.
Before any of it is parsed, the whole directory is checked against
``PINNED_MANIFEST`` (``core/ethics_core_manifest.py``), a sha256 digest per
file pinned in code:

* missing file, extra file or directory, modified byte, or unreadable file
  => ``CoreIntegrityError``. Nothing is returned; nothing is partially loaded.
* The bytes that were hashed are the bytes that get parsed (no re-read, so
  no check-then-swap window).
* The result is an immutable mapping cached for the life of the process.
  Nothing in the runtime writes to ``core/ethics_core``.

There is deliberately NO environment variable, config key, CLI flag, or
function argument that points this loader at another directory or skips
verification. Tests substitute ``_CORE_DIR`` / ``_PINNED_MANIFEST`` with
pytest's ``monkeypatch`` and call ``_reset_cache_for_tests()``; that is
ordinary in-process code modification, not a switch reachable from
configuration.

The manifest is regenerated only by a human developer with
``python scripts/rebuild_ethics_manifest.py`` and lands through a reviewed
PR. The robot runtime never runs that script and holds no signing key.

Threat model: assume the attacker has read this code. A pinned digest
defeats on-disk tampering of the data files (including editing a file and
its self-declared ``principles_hash`` together). It does not defend against
an attacker who can also rewrite the installed Python code; that is the job
of install/package integrity (signed bundles), which is follow-up work.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from .ethics_core_manifest import PINNED_MANIFEST

_CORE_DIR: Path = Path(__file__).resolve().parent / "ethics_core"
_PINNED_MANIFEST: Mapping[str, str] = PINNED_MANIFEST

_lock = threading.Lock()
_cache: Mapping[str, bytes] | None = None


class CoreIntegrityError(RuntimeError):
    """The ethics core failed verification. Fail closed: deny everything."""


def _read_and_verify(core_dir: Path, manifest: Mapping[str, str]) -> Mapping[str, bytes]:
    if not manifest:
        raise CoreIntegrityError("ethics core manifest is empty")
    try:
        if not core_dir.is_dir():
            raise CoreIntegrityError(f"ethics core directory missing: {core_dir.name}")
        present = {p.name for p in core_dir.iterdir()}
    except OSError as exc:
        raise CoreIntegrityError(f"ethics core directory unreadable: {exc}") from exc

    extra = sorted(present - set(manifest))
    if extra:
        raise CoreIntegrityError(f"unexpected entries in ethics core: {extra}")
    missing = sorted(set(manifest) - present)
    if missing:
        raise CoreIntegrityError(f"missing ethics core files: {missing}")

    verified: dict[str, bytes] = {}
    for name, expected in sorted(manifest.items()):
        path = core_dir / name
        if path.is_symlink() or not path.is_file():
            raise CoreIntegrityError(f"ethics core entry is not a regular file: {name}")
        try:
            with open(path, "rb") as fh:  # read-only, binary
                data = fh.read()
        except OSError as exc:
            raise CoreIntegrityError(f"ethics core file unreadable: {name}: {exc}") from exc
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise CoreIntegrityError(
                f"ethics core digest mismatch for {name}: expected {expected}, got {actual}"
            )
        verified[name] = data
    return MappingProxyType(verified)


def load_verified_core() -> Mapping[str, bytes]:
    """Return the verified core as an immutable ``{filename: bytes}`` mapping.

    Takes no arguments on purpose (see module docstring). Raises
    ``CoreIntegrityError`` on any failure. Success is cached for the process;
    failure is never cached as success.
    """
    global _cache
    with _lock:
        if _cache is None:
            _cache = _read_and_verify(_CORE_DIR, _PINNED_MANIFEST)
        return _cache


def core_integrity_error() -> str | None:
    """None if the core is verified; otherwise a short reason string."""
    try:
        load_verified_core()
    except CoreIntegrityError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - anything unexpected also fails closed
        return f"ethics core check raised {type(exc).__name__}"
    return None


def _reset_cache_for_tests() -> None:
    global _cache
    with _lock:
        _cache = None
