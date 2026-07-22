"""
local_persistence.py
====================

Thin facade over domain stores for local-only persistence.

This is **not** a god object: it does not implement I/O or privacy rules itself.
It wires ``JsonFileBackend``, ``PrivacyFilter``, and the domain stores, and
exposes a small, stable API for the rest of the engine.

Privacy (enforced on write via PrivacyFilter)
---------------------------------------------
Never persist information about the user's sexual activities unless the user
explicitly references that topic in direct conversation with the AI.

Local-only
----------
All files live under ``data_root`` (default: ``./pbe_data``). No cloud, no
remote APIs. Users may delete the entire folder or any per-user subdirectory.

Extensibility
-------------
- Per-user baseline memory can grow inside ``UserBaseline`` + ``BaselineStore``
- Long-term / episodic memory can add new stores beside existing ones
- OpenClaw (or other integrations) can inject a custom ``data_root`` or later
  a different backend implementing the same store methods
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterable

from .json_backend import JsonFileBackend
from .models import BondStateRecord, DecisionLogRecord, UserBaseline, UserSettings
from .paths import default_data_root, sanitize_user_id, user_dir
from .privacy import PrivacyFilter, PrivacyPolicy
from .stores import (
    BaselineStore,
    BondStateStore,
    DecisionLogStore,
    QueuedAuditStore,
    SettingsStore,
)

_README_TEXT = """Positronic Bond Engine — local data directory
================================================

This folder stores persistence data for the Positronic Bond Engine.

Privacy
-------
- Data is local only (on this machine). Nothing is uploaded by this layer.
- Sexual activity content is not stored unless the user explicitly references
  it in direct conversation with the AI (see persistence/privacy.py).

Layout (all paths scoped to users/<user_id>/)
--------------------------------------------
  baseline.json          — PerUserBaseline (communication style)
  bond_state.json        — RelationshipHealth living bond model
                           (texture, health_flags, soft pattern counters,
                            curious_companion, careful_truth_telling joint,
                            observation_candidates_snapshot, enjoyment_score,
                            provenance_markers)
  settings.json          — user controls (memory, exploratory prefs, …)
  decision_logs.jsonl    — EthicsEngine audit lines + evidence_snapshot
  audits_queue.json      — deferred QueuedAudit scaffolding (non-blocking)
  interactions.jsonl     — InteractionMemoryStore episodic feed
                           (owned by core.interaction_memory; same folder)

Ownership
---------
  Bond / decisions / baseline / settings  → this package (stores above)
  Episodes (summaries, topics)            → InteractionMemoryStore
  They share user_id only; they do not write each other's files.

Deletion
--------
- Delete a user folder to erase that user's data.
- Delete this entire directory to erase all engine persistence data.
"""


class LocalPersistence:
    """Main entry point for local file-based persistence (v1 JSON foundation)."""

    def __init__(
        self,
        data_root: Path | str | None = None,
        *,
        privacy: PrivacyFilter | None = None,
        privacy_policy: PrivacyPolicy | None = None,
    ) -> None:
        root = default_data_root(Path(data_root) if data_root else None)
        self.data_root = root
        self.backend = JsonFileBackend(root)
        if privacy is not None:
            self.privacy = privacy
        else:
            self.privacy = PrivacyFilter(policy=privacy_policy or PrivacyPolicy())

        self.baselines = BaselineStore(self.backend, self.privacy)
        self.bonds = BondStateStore(self.backend, self.privacy)
        self.decision_logs = DecisionLogStore(self.backend, self.privacy)
        self.audits = QueuedAuditStore(self.backend, self.privacy)
        self.settings = SettingsStore(self.backend, self.privacy)

        self._ensure_readme()

    # ------------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------------

    def load_baseline(self, user_id: str = "default") -> UserBaseline:
        return self.baselines.load(user_id)

    def save_baseline(self, baseline: UserBaseline) -> Path:
        return self.baselines.save(baseline)

    # ------------------------------------------------------------------
    # Bond / relationship health (RelationshipHealth ownership)
    # ------------------------------------------------------------------

    def load_bond_state(self, user_id: str = "default") -> BondStateRecord:
        return self.bonds.load(user_id)

    def save_bond_state(self, record: BondStateRecord) -> Path:
        return self.bonds.save(record)

    def save_bond_from_context(self, user_id: str, context: dict[str, Any]) -> Path:
        """Persist bond state from RelationshipHealth.as_context()-like dict."""
        record = BondStateRecord.from_relationship_health_context(user_id, context)
        return self.save_bond_state(record)

    def update_bond_curious_companion(
        self, user_id: str, snapshot: dict[str, Any]
    ) -> BondStateRecord:
        """Merge gap/continuity snapshot into bond_state.json for this user.

        Used so open topics / last gap evidence survive sessions without
        coupling BondStateStore to InteractionMemoryStore.
        """
        return self.bonds.update_curious_companion(user_id, snapshot)

    def update_bond_careful_truth_telling(
        self, user_id: str, snapshot: dict[str, Any]
    ) -> BondStateRecord:
        """Persist compact joint readiness×confidence on bond_state.json."""
        return self.bonds.update_careful_truth_telling(user_id, snapshot)

    def update_bond_observation_candidates(
        self, user_id: str, cand_bag: dict[str, Any]
    ) -> BondStateRecord:
        """Persist compact observation-candidate snapshot on bond_state.json."""
        return self.bonds.update_observation_candidates(user_id, cand_bag)

    def update_bond_enjoyment_score(
        self, user_id: str, enjoyment: dict[str, Any]
    ) -> BondStateRecord:
        """Persist compact enjoyment score on bond_state.json."""
        return self.bonds.update_enjoyment_score(user_id, enjoyment)

    def merge_bond_provenance_markers(
        self, user_id: str, markers: dict[str, Any]
    ) -> BondStateRecord:
        """Merge potentially_stale / last_audit markers into bond_state.json."""
        return self.bonds.merge_provenance_markers(user_id, markers)

    # ------------------------------------------------------------------
    # Queued audits (deferred provenance; never blocks evaluate)
    # ------------------------------------------------------------------

    def load_audit_queue(self, user_id: str = "default") -> list[dict[str, Any]]:
        return self.audits.load(user_id)

    def save_audit_queue(
        self, user_id: str, audits: list[dict[str, Any]]
    ) -> Path:
        return self.audits.save(user_id, audits)

    def get_audit_queue(
        self, user_id: str = "default", *, max_entries: int = 200
    ) -> Any:
        """Return an ``AuditQueue`` bound to this user's durable queue file.

        Enqueue / complete are local and fail-soft; they never block evaluate().
        """
        from auditing.queued_audit import AuditQueue

        return AuditQueue(
            user_id=user_id,
            persist_load=lambda uid: self.load_audit_queue(uid),
            persist_save=lambda uid, rows: self.save_audit_queue(uid, rows),
            fail_soft=True,
            max_entries=max_entries,
        )

    def apply_audit_stale_marks_to_bond(
        self,
        user_id: str,
        *,
        audit_id: str,
        potentially_stale: list[str] | None = None,
        summary: str = "",
    ) -> BondStateRecord:
        """Write potentially_stale markers from a completed audit onto BondState.

        Scaffolding only — does not rewrite enjoyment/CTT values.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        marks = [
            {
                "target": str(t)[:64],
                "reason": str(summary or "")[:160],
                "audit_id": str(audit_id)[:48],
                "marked_at": now,
            }
            for t in (potentially_stale or [])
            if t
        ]
        return self.merge_bond_provenance_markers(
            user_id,
            {
                "potentially_stale": marks,
                "last_audit_id": audit_id,
                "last_audit_at": now,
            },
        )

    # ------------------------------------------------------------------
    # Decision logs (EthicsEngine ownership)
    # ------------------------------------------------------------------

    def append_decision_log(
        self,
        record: DecisionLogRecord | Any,
        *,
        user_id: str | None = None,
        max_entries: int | None = None,
        evidence_snapshot: dict[str, Any] | None = None,
    ) -> Path:
        """Append a DecisionLogRecord or EthicsEngine DecisionLog-like object.

        Optional ``evidence_snapshot`` attaches compact gap/continuity/flag
        provenance for later retrospective correction (privacy-filtered on write).
        """
        if not isinstance(record, DecisionLogRecord):
            uid = user_id or "default"
            record = DecisionLogRecord.from_decision_log(
                record, user_id=uid, evidence_snapshot=evidence_snapshot
            )
        else:
            if user_id:
                record.user_id = user_id
            if evidence_snapshot and not record.evidence_snapshot:
                record.evidence_snapshot = dict(evidence_snapshot)

        settings = self.load_settings(record.user_id)
        if not settings.retain_decision_logs or not settings.persistence_enabled:
            # Respect user control: no-op path (still return intended path)
            return user_dir(self.data_root, record.user_id) / DecisionLogStore.FILENAME

        cap = max_entries if max_entries is not None else settings.max_decision_logs
        return self.decision_logs.append(record, max_entries=cap)

    def append_decision_from_stance(
        self,
        log: Any,
        stance: Any,
        *,
        user_id: str | None = None,
        max_entries: int | None = None,
    ) -> Path:
        """Append a decision log with evidence_snapshot taken from EthicalStance."""
        impact = getattr(stance, "relationship_impact", None) or {}
        flags = list(getattr(stance, "flags", None) or getattr(log, "flags", None) or [])
        snap = DecisionLogRecord.compact_evidence_from_impact(impact, flags=flags)
        return self.append_decision_log(
            log, user_id=user_id, max_entries=max_entries, evidence_snapshot=snap
        )

    def append_decision_logs(
        self,
        logs: Iterable[Any],
        *,
        user_id: str = "default",
    ) -> int:
        """Append many logs (e.g. flush EthicsEngine.get_decision_history())."""
        n = 0
        for log in logs:
            self.append_decision_log(log, user_id=user_id)
            n += 1
        return n

    def load_decision_logs(
        self, user_id: str = "default", *, limit: int | None = None
    ) -> list[DecisionLogRecord]:
        return self.decision_logs.load(user_id, limit=limit)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def load_settings(self, user_id: str = "default") -> UserSettings:
        return self.settings.load(user_id)

    def save_settings(self, settings: UserSettings) -> Path:
        return self.settings.save(settings)

    # ------------------------------------------------------------------
    # User lifecycle / deletion (user-owned data)
    # ------------------------------------------------------------------

    def list_user_ids(self) -> list[str]:
        """List user ids that have a directory under the data root."""
        users_root = self.data_root / "users"
        if not users_root.is_dir():
            return []
        ids: list[str] = []
        for p in sorted(users_root.iterdir()):
            if p.is_dir():
                try:
                    ids.append(sanitize_user_id(p.name))
                except ValueError:
                    continue
        return ids

    def delete_user_data(self, user_id: str) -> bool:
        """Delete all persisted data for one user. Returns True if a dir existed."""
        path = user_dir(self.data_root, user_id)
        if path.is_dir():
            shutil.rmtree(path)
            return True
        return False

    def delete_all_data(self) -> None:
        """Delete the entire data root (all users). Irreversible for this store."""
        if self.data_root.is_dir():
            shutil.rmtree(self.data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._ensure_readme()

    def user_data_path(self, user_id: str = "default") -> Path:
        """Return the on-disk folder for a user (for backup / inspection)."""
        return user_dir(self.data_root, user_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_readme(self) -> None:
        readme = self.data_root / "README.txt"
        if not readme.is_file():
            self.data_root.mkdir(parents=True, exist_ok=True)
            readme.write_text(_README_TEXT, encoding="utf-8")
