"""
store.py
========

Basic memory substrate interface.

Future implementations will likely distinguish between:
- Episodic memory (specific interactions)
- Semantic memory (generalized knowledge about the human)
- Procedural / preference memory
- Self-memory (the agent's record of its own past states and commitments)

All memory access should be auditable and subject to ethical review
(especially when retrieving sensitive relational details).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    timestamp: datetime
    kind: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    # relationship_context will carry consent, sensitivity, and bond-state info
    relationship_context: dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    """
    Abstract interface for memory operations.

    Concrete implementations (in-memory, vector, graph, encrypted local, etc.)
    will be added in later phases.
    """

    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def store(
        self,
        kind: str,
        content: Any,
        *,
        metadata: dict[str, Any] | None = None,
        relationship_context: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            timestamp=datetime.utcnow(),
            kind=kind,
            content=content,
            metadata=metadata or {},
            relationship_context=relationship_context or {},
        )
        self._entries.append(entry)
        return entry

    def recall(self, query: dict[str, Any] | None = None) -> list[MemoryEntry]:
        """
        Retrieve memories matching the query.

        The query language is intentionally left open for now. Future versions
        should support both semantic and structured retrieval while routing
        sensitive recalls through the ethics engine.
        """
        if not query:
            return list(self._entries)
        # Very naive filter for scaffold
        return [
            e
            for e in self._entries
            if all(str(v).lower() in str(e.content).lower() for v in query.values())
        ]

    def clear(self) -> None:
        """Dangerous operation — should itself be subject to audit."""
        self._entries.clear()
