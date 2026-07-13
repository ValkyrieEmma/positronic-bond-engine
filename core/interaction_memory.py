"""
interaction_memory.py
=====================

Lightweight, local-only interaction history for the Positronic Bond Engine.

Architecture placement
----------------------
- **Not** a second baseline: does not estimate communication style (that is
  ``PerUserBaseline``).
- **Not** bond texture: does not own trust/reciprocity flags (that is
  ``RelationshipHealth``).
- **Not** ethical audit logs: decision traces stay in EthicsEngine /
  ``DecisionLogRecord`` persistence.
- **Is** a thin episodic feed: ordered interaction records that other
  modules can *consume* as context (e.g. recent topics for baseline updates,
  short summaries for ethics context, continuity for companions).

Persistence
-----------
Built on ``LocalPersistence`` / ``JsonFileBackend`` — files live under::

    <data_root>/users/<user_id>/interactions.jsonl

Privacy-first: free-text fields pass through the same local PrivacyFilter as
other stores (sexual content only if the user explicitly referenced it).

No vector search, embeddings, or cloud backends in this version.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from persistence.local_persistence import LocalPersistence
from persistence.paths import ensure_user_dir, sanitize_user_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InteractionRecord:
    """One lightweight interaction / turn stored for history.

    Keep payloads small and auditable. Prefer summaries and key signals over
    raw transcripts when possible.

    Attributes:
        timestamp: ISO-8601 UTC time of the interaction.
        user_id: Local user identifier.
        kind: Coarse type (e.g. ``user_turn``, ``agent_turn``, ``system``).
        summary: Short human-readable description (privacy-filtered on write).
        topics: Optional topic tags (non-sensitive labels preferred).
        signals: Optional key numeric/categorical signals (playfulness, etc.).
        source: Optional origin tag (e.g. ``companion``, ``eval_harness``).
        metadata: Extensible bag for non-sensitive extras.
        schema_version: Record format version.
    """

    timestamp: str
    user_id: str
    kind: str = "user_turn"
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> InteractionRecord:
        if not data:
            return cls(timestamp=_utc_now_iso(), user_id="default")
        topics_raw = data.get("topics") or []
        if isinstance(topics_raw, str):
            topics_list = [topics_raw]
        else:
            topics_list = [str(t) for t in topics_raw if str(t).strip()]
        return cls(
            timestamp=str(data.get("timestamp") or _utc_now_iso()),
            user_id=str(data.get("user_id") or "default"),
            kind=str(data.get("kind") or "user_turn"),
            summary=str(data.get("summary") or data.get("content") or ""),
            topics=topics_list,
            signals=dict(data.get("signals") or {}),
            source=str(data.get("source") or ""),
            metadata=dict(data.get("metadata") or {}),
            schema_version=int(data.get("schema_version", 1)),
        )


class InteractionMemoryStore:
    """Durable, local-only interaction history on top of LocalPersistence.

    Responsibilities (narrow on purpose):
      - Append privacy-filtered interaction records
      - Query recent / by-topic / last-N interactions
      - Export compact context for EthicsEngine or PerUserBaseline consumers

    Does **not**:
      - Update bond texture (use RelationshipHealth)
      - Update communication baseline EMA (use PerUserBaseline)
      - Store full ethical decision audits (use decision_logs)
      - Perform semantic/vector retrieval

    Example::

        from persistence import LocalPersistence
        from core import InteractionMemoryStore, PerUserBaseline

        store = LocalPersistence()
        memory = InteractionMemoryStore(store)
        memory.record("alice", summary="User asked about weekend plans", topics=["plans"])
        recent = memory.recent("alice", limit=5)
        # Optionally feed topics into baseline:
        # baseliner.update_from_interaction("alice", {"topics": recent[-1].topics})
    """

    FILENAME = "interactions.jsonl"
    DEFAULT_MAX_ENTRIES = 2_000

    def __init__(
        self,
        persistence: LocalPersistence | None = None,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        """
        Args:
            persistence: LocalPersistence instance (creates default if omitted).
            max_entries: Soft cap per user; oldest lines trimmed after append.
        """
        self._persistence = persistence or LocalPersistence()
        self.max_entries = max(1, int(max_entries))

    @property
    def persistence(self) -> LocalPersistence:
        return self._persistence

    @property
    def data_root(self) -> Path:
        return self._persistence.data_root

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        user_id: str,
        *,
        summary: str = "",
        kind: str = "user_turn",
        topics: Iterable[str] | None = None,
        signals: dict[str, Any] | None = None,
        source: str = "",
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> InteractionRecord:
        """Append one interaction record (privacy-filtered) and return it."""
        rec = InteractionRecord(
            timestamp=timestamp or _utc_now_iso(),
            user_id=sanitize_user_id(user_id),
            kind=kind or "user_turn",
            summary=summary or "",
            topics=[str(t).strip() for t in (topics or []) if str(t).strip()],
            signals=dict(signals or {}),
            source=source or "",
            metadata=dict(metadata or {}),
        )
        self.append(rec)
        return rec

    def append(self, record: InteractionRecord) -> Path:
        """Append a fully formed InteractionRecord after privacy filtering."""
        uid = sanitize_user_id(record.user_id)
        settings = self._persistence.load_settings(uid)
        path = self._path(uid)
        if not settings.persistence_enabled or not settings.memory_enabled:
            return path

        data = record.to_dict()
        privacy = self._persistence.privacy
        data["summary"] = privacy.filter_text(str(data.get("summary") or ""))
        data["metadata"] = privacy.filter_mapping(dict(data.get("metadata") or {}))
        # Topics/signals expected to be non-sensitive labels; still filter string values
        if data.get("signals"):
            data["signals"] = privacy.filter_mapping(dict(data["signals"]))

        self._persistence.backend.append_jsonl(path, data)
        self._trim(uid)
        return path

    def append_from_interaction_dict(
        self,
        user_id: str,
        interaction: dict[str, Any],
        *,
        kind: str = "user_turn",
        source: str = "",
    ) -> InteractionRecord:
        """Convenience: build a record from a PerUserBaseline-style interaction dict.

        Extracts text → summary (truncated), topics, and a few common signals.
        Does not call PerUserBaseline itself (caller may do both).
        """
        text = str(
            interaction.get("text")
            or interaction.get("message")
            or interaction.get("content")
            or interaction.get("summary")
            or ""
        ).strip()
        summary = text if len(text) <= 240 else text[:237] + "..."
        topics = interaction.get("topics")
        signals: dict[str, Any] = {}
        for key in (
            "playfulness",
            "directness",
            "emotional_tone",
            "tone",
            "message_length",
        ):
            if key in interaction:
                signals[key] = interaction[key]
        return self.record(
            user_id,
            summary=summary,
            kind=kind,
            topics=topics if isinstance(topics, (list, tuple)) else None,
            signals=signals or None,
            source=source,
            metadata={"from_interaction_dict": True},
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def recent(self, user_id: str, limit: int = 10) -> list[InteractionRecord]:
        """Return the last ``limit`` interactions (oldest→newest within the window)."""
        limit = max(0, int(limit))
        rows = self._persistence.backend.read_jsonl(
            self._path(user_id), limit=limit if limit > 0 else None
        )
        return [InteractionRecord.from_dict(r) for r in rows]

    def last_n(self, user_id: str, n: int = 10) -> list[InteractionRecord]:
        """Alias for ``recent``."""
        return self.recent(user_id, limit=n)

    def by_topic(
        self,
        user_id: str,
        topic: str,
        *,
        limit: int | None = 50,
    ) -> list[InteractionRecord]:
        """Return interactions whose topics list contains ``topic`` (case-insensitive)."""
        needle = str(topic).strip().lower()
        if not needle:
            return []
        all_rows = self._load_all(user_id)
        matched = [
            r
            for r in all_rows
            if any(needle == t.lower() or needle in t.lower() for t in r.topics)
        ]
        if limit is not None and limit >= 0:
            return matched[-limit:]
        return matched

    def by_kind(
        self,
        user_id: str,
        kind: str,
        *,
        limit: int | None = 50,
    ) -> list[InteractionRecord]:
        """Return interactions with matching ``kind``."""
        k = str(kind).strip().lower()
        rows = [r for r in self._load_all(user_id) if r.kind.lower() == k]
        if limit is not None and limit >= 0:
            return rows[-limit:]
        return rows

    def count(self, user_id: str) -> int:
        """Number of stored interactions for the user."""
        return len(self._load_all(user_id))

    def as_ethics_context(
        self,
        user_id: str,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Compact history snippet for EthicsEngine ``context`` (not relationship_health).

        Callers may merge this into ``evaluate`` context, e.g.::

            ctx = {**memory.as_ethics_context("alice"), "user_id": "alice"}
            engine.evaluate(action, ctx)

        Intentionally small: recent summaries + topic multiset only.
        """
        recent = self.recent(user_id, limit=limit)
        topic_counts: dict[str, int] = {}
        for r in recent:
            for t in r.topics:
                topic_counts[t] = topic_counts.get(t, 0) + 1
        return {
            "interaction_history": {
                "user_id": user_id,
                "count_returned": len(recent),
                "recent_summaries": [
                    {
                        "timestamp": r.timestamp,
                        "kind": r.kind,
                        "summary": r.summary[:200],
                        "topics": list(r.topics)[:8],
                    }
                    for r in recent
                ],
                "recent_topics": sorted(
                    topic_counts.keys(), key=lambda t: (-topic_counts[t], t)
                )[:12],
            }
        }

    def topics_for_baseline(
        self, user_id: str, *, limit: int = 10
    ) -> list[str]:
        """Flatten recent topics for optional PerUserBaseline updates."""
        topics: list[str] = []
        seen: set[str] = set()
        for r in reversed(self.recent(user_id, limit=limit)):
            for t in r.topics:
                tl = t.lower()
                if tl not in seen:
                    seen.add(tl)
                    topics.append(t)
        return topics

    def clear_user(self, user_id: str) -> bool:
        """Delete interaction history file for one user (user control)."""
        return self._persistence.backend.delete_path(self._path(user_id))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _path(self, user_id: str) -> Path:
        return ensure_user_dir(self._persistence.data_root, user_id) / self.FILENAME

    def _load_all(self, user_id: str) -> list[InteractionRecord]:
        rows = self._persistence.backend.read_jsonl(self._path(user_id))
        return [InteractionRecord.from_dict(r) for r in rows]

    def _trim(self, user_id: str) -> None:
        rows = self._persistence.backend.read_jsonl(self._path(user_id))
        if len(rows) > self.max_entries:
            self._persistence.backend.rewrite_jsonl(
                self._path(user_id), rows[-self.max_entries :]
            )


# Friendly alias requested in design discussions; prefer InteractionMemoryStore
# in new code to avoid confusion with memory.store.MemoryStore (in-process scaffold).
MemoryStore = InteractionMemoryStore
