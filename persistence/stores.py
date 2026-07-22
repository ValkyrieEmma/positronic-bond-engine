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
- QueuedAuditStore → audits_queue.json (deferred provenance audits)
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
    ``observation_candidates_snapshot`` (latest careful observation seeds),
    and optional ``enjoyment_score`` (time-decayed enjoyment co-evolution).
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
        if isinstance(data.get("enjoyment_score"), dict):
            enj = self._privacy.filter_mapping(dict(data["enjoyment_score"]))
            enj["forces_speech"] = False
            enj["forces_question"] = False
            # Trim free-text topic labels
            topics = enj.get("preferred_topics")
            if isinstance(topics, list):
                enj["preferred_topics"] = [
                    self._privacy.filter_text(str(t))[:48] for t in topics[:8]
                ]
            evidence = enj.get("evidence")
            if isinstance(evidence, list):
                enj["evidence"] = [
                    self._privacy.filter_text(str(x))[:96] for x in evidence[:12]
                ]
            data["enjoyment_score"] = enj
        if isinstance(data.get("provenance_markers"), dict):
            pm = self._privacy.filter_mapping(dict(data["provenance_markers"]))
            pm["forces_speech"] = False
            pm["forces_question"] = False
            data["provenance_markers"] = pm
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

    def update_enjoyment_score(
        self, user_id: str, enjoyment: dict[str, Any]
    ) -> BondStateRecord:
        """Load-set-save enjoyment_score snapshot for this user."""
        from .models import compact_enjoyment_score_snapshot

        record = self.load(user_id)
        record.set_enjoyment_score(
            compact_enjoyment_score_snapshot(
                enjoyment, interaction_count=record.interaction_count
            )
        )
        self.save(record)
        return record

    def delete(self, user_id: str) -> bool:
        return self._backend.delete_path(self._path(user_id))

    def merge_provenance_markers(
        self, user_id: str, markers: dict[str, Any]
    ) -> BondStateRecord:
        """Merge provenance_markers (e.g. potentially_stale) into bond_state."""
        record = self.load(user_id)
        existing = (
            dict(record.provenance_markers)
            if isinstance(getattr(record, "provenance_markers", None), dict)
            else {}
        )
        # Merge potentially_stale lists (newest first, de-dupe by target+audit_id)
        new_stale = list(markers.get("potentially_stale") or [])
        old_stale = list(existing.get("potentially_stale") or [])
        merged_stale: list[dict[str, Any]] = []
        seen: set[str] = set()
        for m in list(new_stale) + list(old_stale):
            if not isinstance(m, dict):
                continue
            key = f"{m.get('target')}|{m.get('audit_id')}"
            if key in seen:
                continue
            seen.add(key)
            merged_stale.append(
                {
                    "target": str(m.get("target") or "")[:64],
                    "reason": str(m.get("reason") or "")[:160],
                    "audit_id": str(m.get("audit_id") or "")[:48],
                    "marked_at": str(m.get("marked_at") or "")[:64],
                }
            )
        existing["potentially_stale"] = merged_stale[:32]
        if markers.get("last_audit_id"):
            existing["last_audit_id"] = str(markers.get("last_audit_id"))[:48]
        if markers.get("last_audit_at"):
            existing["last_audit_at"] = str(markers.get("last_audit_at"))[:64]
        existing["forces_speech"] = False
        existing["forces_question"] = False
        record.provenance_markers = existing
        record.last_updated = record.last_updated  # keep; save will write
        self.save(record)
        return record


class QueuedAuditStore:
    """JSON file of deferred audit queue items per user (scaffolding).

    File: ``audits_queue.json`` under users/<user_id>/. Does not run audits —
    only stores inspectable queue state for later workers.
    """

    FILENAME = "audits_queue.json"

    def __init__(self, backend: JsonFileBackend, privacy: PrivacyFilter) -> None:
        self._backend = backend
        self._privacy = privacy

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._backend.data_root, user_id) / self.FILENAME

    def load(self, user_id: str) -> list[dict[str, Any]]:
        raw = self._backend.read_json(self._path(user_id))
        if isinstance(raw, dict) and isinstance(raw.get("audits"), list):
            return [r for r in raw["audits"] if isinstance(r, dict)]
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        return []

    def save(self, user_id: str, audits: list[dict[str, Any]]) -> Path:
        cleaned: list[dict[str, Any]] = []
        for a in audits or []:
            if not isinstance(a, dict):
                continue
            item = self._privacy.filter_mapping(dict(a))
            item["forces_speech"] = False
            item["forces_question"] = False
            if "reason" in item:
                item["reason"] = self._privacy.filter_text(str(item.get("reason") or ""))[
                    :280
                ]
            if "topic" in item:
                item["topic"] = self._privacy.filter_text(str(item.get("topic") or ""))[
                    :96
                ]
            cleaned.append(item)
        path = self._path(user_id)
        self._backend.write_json(
            path,
            {
                "user_id": user_id,
                "audits": cleaned,
                "schema_version": 1,
                "forces_speech": False,
                "forces_question": False,
            },
        )
        return path

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
