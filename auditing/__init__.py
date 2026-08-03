"""
auditing
========

Self-audit and integrity verification systems.

This package provides mechanisms for the Positronic Bond Engine to examine
its own deliberation outputs and bound subsystem state (decision logs,
phase, durable file presence) — not canned template scripts.

Critical requirement:
The auditing layer must never be used to force comforting or liability-reducing
narratives. It exists to enable honest self-knowledge.
"""

from .audit_runner import (  # noqa: F401
    AuditRunner,
    AuditRunReport,
    build_runner_from_persistence,
)
from .engagement_queue import (  # noqa: F401
    EngagementCandidate,
    EngagementQueue,
)
from .provenance_stale import (  # noqa: F401
    collect_potentially_stale,
    confidence_dampen_from_stale,
    format_stale_trace_lines,
    is_bag_stale,
    normalize_stale_target,
)
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
    "AuditRunReport",
    "AuditRunner",
    # EngagementCandidate/EngagementQueue's own STATUS_* constants are not
    # re-exported here — they'd collide by name (though not by meaning)
    # with QueuedAudit's STATUS_PENDING / STATUS_CANCELLED above. Import
    # them from auditing.engagement_queue directly instead.
    "EngagementCandidate",
    "EngagementQueue",
    "PRIORITY_ORDINARY",
    "PRIORITY_RELATIONSHIP_HEALTH",
    "PRIORITY_SAFETY",
    "QueuedAudit",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_PENDING",
    "STATUS_RUNNING",
    "SelfAuditor",
    "build_runner_from_persistence",
    "collect_potentially_stale",
    "compact_audit_result",
    "confidence_dampen_from_stale",
    "format_stale_trace_lines",
    "is_bag_stale",
    "normalize_stale_target",
    "suggest_audit_from_decision",
]
