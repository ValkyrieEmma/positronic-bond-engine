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

from .self_audit import AuditReport, SelfAuditor  # noqa: F401

__all__ = ["AuditReport", "SelfAuditor"]
