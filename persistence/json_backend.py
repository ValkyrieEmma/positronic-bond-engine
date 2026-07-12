"""
json_backend.py
===============

Minimal file I/O helpers for JSON and JSONL on the local filesystem.

- Atomic-ish writes (write temp file then replace) to reduce corruption risk
- No network, no encryption layer in v1 (may be added later without API break)
- Easy for users to open files in any text editor
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonFileBackend:
    """Read/write JSON objects and append-only JSONL logs under a root path."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)

    def read_json(self, path: Path) -> dict[str, Any] | None:
        """Load a JSON object file; return None if missing or empty."""
        path = Path(path)
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                return None
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return {"_value": data}
        except (OSError, json.JSONDecodeError):
            return None

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write a JSON object atomically (best-effort on Windows)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        self._atomic_write_text(path, payload)

    def append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        """Append one JSON object as a single line (JSONL)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def read_jsonl(self, path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Read JSONL records (oldest first). If limit set, return the last N."""
        path = Path(path)
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            rows.append(obj)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        if limit is not None and limit >= 0:
            return rows[-limit:]
        return rows

    def rewrite_jsonl(self, path: Path, records: list[dict[str, Any]]) -> None:
        """Replace a JSONL file with the given records (e.g. after trimming)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records
        )
        self._atomic_write_text(path, body)

    def delete_path(self, path: Path) -> bool:
        """Delete a file if it exists. Returns True if something was removed."""
        path = Path(path)
        if path.is_file():
            path.unlink()
            return True
        return False

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(text)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
