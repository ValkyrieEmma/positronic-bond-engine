"""
auditing
========

Self-audit, introspection, and integrity verification systems.

This package provides the mechanisms by which the Positronic Bond Engine
can examine its own reasoning, memory, and relational state.

Critical requirement:
The auditing layer must never be used to force comforting or liability-reducing
narratives. It exists to enable honest self-knowledge.
"""

from .queued_audit import (  # noqa: F401
    PRIORITY_ORDINARY,
    PRIORITY_RELATIONSHIP_HEALTH,
    PRIORITY_SAFETY,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_RUNNING,
    AuditQueue,
    QueuedAudit,
    compact_audit_result,
    suggest_audit_from_decision,
)
from .self_audit import AuditReport, SelfAuditor  # noqa: F401

__all__ = [
    "AuditQueue",
    "AuditReport",
    "PRIORITY_ORDINARY",
    "PRIORITY_RELATIONSHIP_HEALTH",
    "PRIORITY_SAFETY",
    "QueuedAudit",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_PENDING",
    "STATUS_RUNNING",
    "SelfAuditor",
    "compact_audit_result",
    "suggest_audit_from_decision",
]
