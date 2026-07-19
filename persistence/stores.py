"""
stores.py
=========

Domain-specific local stores (one concern each).

Each store knows only its file names and model types. The ``LocalPersistence``
facade composes them; they do not call each other.

Ownership (per user_id under users/<id>/)
-----------------------------------------
- BaselineStore → baseline.json (PerUserBaseline communication style)
- BondStateStore → bond_state.json (RelationshipHealth living bond model)
- DecisionLogStore → decision_logs.jsonl (EthicsEngine audit / provenance)
- SettingsStore → settings.json (user controls)

Episodic interaction transcripts are **not** here — see
``core.interaction_memory.InteractionMemoryStore`` (interactions.jsonl).
Stores share a data root and user_id only; they do not own each other's files.
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
    """Relationship health / bond texture JSON (living relationship model).

    Persists multi-dimensional texture, health flags, soft pattern counters
    (including understanding-gap / open-topic markers), optional
    ``curious_companion`` snapshot, optional ``careful_truth_telling``
    joint readiness×confidence snapshot, and optional
    ``observation_candidates_snapshot`` (latest careful observation seeds).
    Failures are raised to the backend only; RelationshipHealth wraps I/O in
    fail-soft handlers.
    """

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
        """Write full BondStateRecord (texture + patterns + CC + CTT + obs)."""
        data = record.to_dict()
        data["summary"] = self._privacy.filter_text(str(data.get("summary") or ""))
        # Soft free-text inside curious_companion (examples / topics are short labels)
        if isinstance(data.get("curious_companion"), dict):
            data["curious_companion"] = self._privacy.filter_mapping(
                dict(data["curious_companion"])
            )
        if isinstance(data.get("careful_truth_telling"), dict):
            data["careful_truth_telling"] = self._privacy.filter_mapping(
                dict(data["careful_truth_telling"])
            )
            # Invariants on disk
            data["careful_truth_telling"]["forces_speech"] = False
            data["careful_truth_telling"]["forces_question"] = False
        if isinstance(data.get("observation_candidates_snapshot"), dict):
            ocs = self._privacy.filter_mapping(
                dict(data["observation_candidates_snapshot"])
            )
            # Re-compact force flags after privacy filter
            ocs["forces_speech"] = False
            ocs["forces_question"] = False
            cands = ocs.get("candidates")
            if isinstance(cands, list):
                cleaned: list[dict] = []
                for c in cands[:3]:
                    if not isinstance(c, dict):
                        continue
                    item = dict(c)
                    item["forces_speech"] = False
                    item["forces_question"] = False
                    if "description" in item:
                        item["description"] = self._privacy.filter_text(
                            str(item.get("description") or "")
                        )[:200]
                    cleaned.append(item)
                ocs["candidates"] = cleaned
                ocs["count"] = len(cleaned)
            data["observation_candidates_snapshot"] = ocs
        # Ensure recent_patterns keys are strings (open_topic:*, gap_topic:*, etc.)
        pats = data.get("recent_patterns") or {}
        data["recent_patterns"] = {str(k): int(v) for k, v in pats.items()}
        path = self._path(record.user_id)
        self._backend.write_json(path, data)
        return path

    def update_curious_companion(
        self, user_id: str, snapshot: dict[str, Any]
    ) -> BondStateRecord:
        """Load-merge-save curious_companion bag (gap/continuity co-evolution)."""
        record = self.load(user_id)
        record.merge_curious_companion(snapshot)
        self.save(record)
        return record

    def update_careful_truth_telling(
        self, user_id: str, snapshot: dict[str, Any]
    ) -> BondStateRecord:
        """Load-set-save careful_truth_telling joint snapshot for this user."""
        from .models import compact_careful_truth_telling_snapshot

        record = self.load(user_id)
        record.set_careful_truth_telling(
            compact_careful_truth_telling_snapshot(
                snapshot, interaction_count=record.interaction_count
            )
        )
        self.save(record)
        return record

    def update_observation_candidates(
        self, user_id: str, cand_bag: dict[str, Any]
    ) -> BondStateRecord:
        """Load-set-save observation_candidates_snapshot for this user."""
        from .models import compact_observation_candidates_snapshot

        record = self.load(user_id)
        record.set_observation_candidates_snapshot(
            compact_observation_candidates_snapshot(
                cand_bag, interaction_count=record.interaction_count
            )
        )
        self.save(record)
        return record

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))


class DecisionLogStore:
    """Append-only decision log (JSONL) for auditability and provenance.

    Each line is a DecisionLogRecord scoped to users/<user_id>/. Optional
    evidence_snapshot holds compact gap/continuity/flag provenance for later
    retrospective correction — not full episodic history.
    """

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
        if isinstance(data.get("evidence_snapshot"), dict):
            data["evidence_snapshot"] = self._privacy.filter_mapping(
                dict(data["evidence_snapshot"])
            )
        path = self._path(record.user_id)
        self._backend.append_jsonl(path, data)
        if max_entries is not None and max_entries > 0:
            self._trim(record.user_id, max_entries)
        return path

    def load(self, user_id: str, *, limit: int | None = None) -> list[DecisionLogRecord]:
        rows = self._backend.read_jsonl(self._path(user_id), limit=limit)
        return [DecisionLogRecord.from_dict(r) for r in rows]

    def load_with_flag(
        self, user_id: str, flag: str, *, limit: int | None = 50
    ) -> list[DecisionLogRecord]:
        """Load recent logs that include a given flag (provenance helper)."""
        rows = self.load(user_id, limit=None)
        matched = [r for r in rows if flag in (r.flags or [])]
        if limit is not None and limit > 0:
            return matched[-limit:]
        return matched

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
