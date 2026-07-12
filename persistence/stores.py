"""
stores.py
=========

Domain-specific local stores (one concern each).

Each store knows only its file names and model types. The ``LocalPersistence``
facade composes them; they do not call each other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_backend import JsonFileBackend
from .models import BondStateRecord, DecisionLogRecord, UserBaseline, UserSettings
from .paths import ensure_user_dir
from .privacy import PrivacyFilter


class BaselineStore:
    """Per-user baseline JSON (communication style foundation)."""

    FILENAME = "baseline.json"

    def __init__(self, backend: JsonFileBackend, privacy: PrivacyFilter) -> None:
        self._backend = backend
        self._privacy = privacy

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._backend.data_root, user_id) / self.FILENAME

    def load(self, user_id: str) -> UserBaseline:
        raw = self._backend.read_json(self._path(user_id))
        return UserBaseline.from_dict(raw, user_id=user_id)

    def save(self, baseline: UserBaseline) -> Path:
        data = baseline.to_dict()
        # Free-text notes only; structured dims are non-sensitive summaries by design
        data["notes"] = self._privacy.filter_text(str(data.get("notes") or ""))
        path = self._path(baseline.user_id)
        self._backend.write_json(path, data)
        return path

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))


class BondStateStore:
    """Relationship health / bond texture JSON."""

    FILENAME = "bond_state.json"

    def __init__(self, backend: JsonFileBackend, privacy: PrivacyFilter) -> None:
        self._backend = backend
        self._privacy = privacy

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._backend.data_root, user_id) / self.FILENAME

    def load(self, user_id: str) -> BondStateRecord:
        raw = self._backend.read_json(self._path(user_id))
        return BondStateRecord.from_dict(raw, user_id=user_id)

    def save(self, record: BondStateRecord) -> Path:
        data = record.to_dict()
        data["summary"] = self._privacy.filter_text(str(data.get("summary") or ""))
        path = self._path(record.user_id)
        self._backend.write_json(path, data)
        return path

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))


class DecisionLogStore:
    """Append-only decision log (JSONL) for auditability."""

    FILENAME = "decision_logs.jsonl"

    def __init__(self, backend: JsonFileBackend, privacy: PrivacyFilter) -> None:
        self._backend = backend
        self._privacy = privacy

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._backend.data_root, user_id) / self.FILENAME

    def append(self, record: DecisionLogRecord, *, max_entries: int | None = None) -> Path:
        """Append one log after privacy filtering free-text fields."""
        data = record.to_dict()
        data["proposed_action"] = self._privacy.filter_text(
            str(data.get("proposed_action") or "")
        )
        data["context"] = self._privacy.filter_mapping(dict(data.get("context") or {}))
        path = self._path(record.user_id)
        self._backend.append_jsonl(path, data)
        if max_entries is not None and max_entries > 0:
            self._trim(record.user_id, max_entries)
        return path

    def load(self, user_id: str, *, limit: int | None = None) -> list[DecisionLogRecord]:
        rows = self._backend.read_jsonl(self._path(user_id), limit=limit)
        return [DecisionLogRecord.from_dict(r) for r in rows]

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))

    def _trim(self, user_id: str, max_entries: int) -> None:
        rows = self._backend.read_jsonl(self._path(user_id))
        if len(rows) > max_entries:
            self._backend.rewrite_jsonl(self._path(user_id), rows[-max_entries:])


class SettingsStore:
    """User settings and controls JSON."""

    FILENAME = "settings.json"

    def __init__(self, backend: JsonFileBackend, privacy: PrivacyFilter) -> None:
        self._backend = backend
        self._privacy = privacy

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._backend.data_root, user_id) / self.FILENAME

    def load(self, user_id: str) -> UserSettings:
        raw = self._backend.read_json(self._path(user_id))
        return UserSettings.from_dict(raw, user_id=user_id)

    def save(self, settings: UserSettings) -> Path:
        data = settings.to_dict()
        # Preferences bag may contain free text — filter defensively
        data["preferences"] = self._privacy.filter_mapping(
            dict(data.get("preferences") or {})
        )
        path = self._path(settings.user_id)
        self._backend.write_json(path, data)
        return path

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))
