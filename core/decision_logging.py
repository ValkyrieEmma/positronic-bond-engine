"""
decision_logging.py
========

Extracted from ethics_engine.py for reviewability (move-then-wire).
Behavior is unchanged: methods remain on EthicsEngine via mixin composition.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from dataclasses import dataclass, field

@dataclass
class DecisionLog:
    """Lightweight record of a single evaluation for later audit and review.

    This enables traceability of decisions over time, including which
    ontology version was in effect when the decision was made.

    Stored in-memory on the engine instance (list of DecisionLog).

    Per-user isolation: ``user_id`` scopes this log to one local human so
    audit trails and optional disk appends never mix users by accident.

    ``evidence_snapshot`` holds compact understanding-gap / topic-continuity /
    flag provenance for durable DecisionLogStore lines (schema v2).
    """

    timestamp: str
    ontology_version: str
    proposed_action: str
    context: dict[str, Any]
    decision: str
    confidence: float
    flags: list[str]
    principles_considered: list[str]
    user_id: str = "default"
    evidence_snapshot: dict[str, Any] = field(default_factory=dict)




class DecisionLoggingMixin:
    """Decision log + optional persistence + deferred audit enqueue."""

    def _log_decision(
        self,
        proposed_action: str,
        context: dict[str, Any],
        stance: EthicalStance,
    ) -> None:
        """Internal helper to record a decision.

        Creates a DecisionLog and appends it to the in-memory history.
        Called automatically by evaluate(). When optional LocalPersistence is
        configured, also appends a privacy-filtered DecisionLogRecord to disk
        under the resolved user_id (failures never raise — evaluation must not
        depend on I/O).

        Per-user isolation: the log's ``user_id`` is taken from the evaluate()
        working context (already identity-scoped) so disk paths never mix users.
        """
        ont = self._ontology
        ctx = dict(context or {})
        # Context was identity-scoped at evaluate() entry; keep fail-soft resolve
        user_id = self._safe_user_id(
            ctx.get("user_id") or ctx.get("user") or self._decision_log_user_id,
            fallback="default",
        )
        ctx["user_id"] = user_id
        # Compact provenance for durable DecisionLogStore (gaps / continuity / flags)
        evidence_snapshot: dict[str, Any] = {}
        try:
            from persistence.models import DecisionLogRecord

            evidence_snapshot = DecisionLogRecord.compact_evidence_from_impact(
                getattr(stance, "relationship_impact", None),
                flags=list(stance.flags or []),
            )
        except Exception:
            evidence_snapshot = {}

        log_entry = DecisionLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            ontology_version=ont.version,
            proposed_action=proposed_action,
            context=ctx,  # shallow copy for safety
            decision=stance.decision,
            confidence=stance.confidence,
            flags=list(stance.flags),
            principles_considered=list(stance.principles_considered),
            user_id=user_id,
            evidence_snapshot=evidence_snapshot,
        )
        self._decision_logs.append(log_entry)
        self._maybe_persist_decision_log(log_entry, user_id=user_id)
        self._maybe_enqueue_deferred_audit(
            log_entry, stance=stance, user_id=user_id, context=ctx
        )

    def _maybe_persist_decision_log(
        self, log_entry: DecisionLog, *, user_id: str
    ) -> None:
        """Best-effort append of one DecisionLog under users/<user_id>/ only."""
        if not self._persist_decisions or self._persistence is None:
            return
        try:
            uid = self._safe_user_id(
                user_id or getattr(log_entry, "user_id", None),
                fallback=self._decision_log_user_id or "default",
            )
            snap = getattr(log_entry, "evidence_snapshot", None)
            self._persistence.append_decision_log(
                log_entry,
                user_id=uid,
                max_entries=self._max_persisted_decision_logs,
                evidence_snapshot=snap if isinstance(snap, dict) else None,
            )
        except Exception:
            # Optional persistence: never interrupt deliberation
            return

    def _auto_enqueue_enabled(self, context: dict[str, Any] | None) -> bool:
        """Resolve opt-in for deferred audit enqueue (constructor + per-call)."""
        enabled = bool(self._auto_enqueue_audits)
        if isinstance(context, dict):
            if "auto_enqueue_audits" in context:
                enabled = bool(context.get("auto_enqueue_audits"))
            elif "queue_audits" in context:
                enabled = bool(context.get("queue_audits"))
        return enabled

    def _resolve_audit_queue(self, user_id: str) -> Any | None:
        """Return an AuditQueue-like object or None (fail-soft)."""
        if self._audit_queue is not None and hasattr(self._audit_queue, "enqueue"):
            return self._audit_queue
        if self._persistence is not None and hasattr(
            self._persistence, "get_audit_queue"
        ):
            try:
                return self._persistence.get_audit_queue(user_id)
            except Exception:
                return None
        return None

    def _maybe_enqueue_deferred_audit(
        self,
        log_entry: DecisionLog,
        *,
        stance: EthicalStance,
        user_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Fail-soft auto-enqueue of a deferred provenance audit (enqueue only).

        Never blocks evaluate(). Never runs AuditRunner. Decision outcomes are
        unchanged. forces_speech / forces_question stay False.
        """
        if not self._auto_enqueue_enabled(context):
            return
        try:
            from auditing.queued_audit import suggest_audit_from_decision

            uid = self._safe_user_id(
                user_id or getattr(log_entry, "user_id", None),
                fallback=self._decision_log_user_id or "default",
            )
            snap = getattr(log_entry, "evidence_snapshot", None)
            if not isinstance(snap, dict):
                snap = None
            suggestion = suggest_audit_from_decision(
                decision=str(getattr(stance, "decision", "") or ""),
                flags=list(getattr(stance, "flags", None) or []),
                user_id=uid,
                decision_log_ref=str(getattr(log_entry, "timestamp", "") or ""),
                evidence_snapshot=snap,
            )
            if not suggestion:
                return

            # Enrich bond snapshot refs from live impact (when present)
            impact = getattr(stance, "relationship_impact", None)
            if isinstance(impact, dict):
                refs = list(suggestion.get("bond_snapshot_refs") or [])
                for key in (
                    "careful_truth_telling",
                    "careful_truth_telling_joint",
                    "enjoyment_score",
                    "observation_candidates",
                    "observation_candidates_durable",
                    "curious_companion",
                    "concept_patterns",
                    "provenance_markers",
                ):
                    if impact.get(key) and key not in refs:
                        # Normalize joint → careful_truth_telling bag name
                        bag = (
                            "careful_truth_telling"
                            if key == "careful_truth_telling_joint"
                            else (
                                "observation_candidates_snapshot"
                                if key
                                in (
                                    "observation_candidates",
                                    "observation_candidates_durable",
                                )
                                else key
                            )
                        )
                        if bag not in refs:
                            refs.append(bag)
                suggestion["bond_snapshot_refs"] = refs[:12]
                # Keep a compact evidence pointer
                ev = dict(suggestion.get("evidence_snapshot_ref") or {})
                if snap:
                    ev["has_evidence_snapshot"] = True
                suggestion["evidence_snapshot_ref"] = ev

            queue = self._resolve_audit_queue(uid)
            if queue is None or not hasattr(queue, "enqueue"):
                return

            item = queue.enqueue(**suggestion)
            if item is None:
                return

            # Inspectable impact + soft trace note (no decision change)
            if isinstance(impact, dict):
                impact["audit_enqueued"] = True
                impact["queued_audit_ref"] = {
                    "audit_id": str(getattr(item, "audit_id", "") or ""),
                    "priority_label": str(
                        getattr(item, "priority_label", "") or ""
                    ),
                    "priority": getattr(item, "priority", None),
                    "topic": str(getattr(item, "topic", "") or "")[:96],
                    "status": str(getattr(item, "status", "pending") or "pending"),
                    "auto_enqueued": True,
                    "forces_speech": False,
                    "forces_question": False,
                }
            trace = getattr(stance, "reasoning_trace", None)
            if isinstance(trace, list):
                trace.append(
                    "[Audit queue] deferred audit enqueued "
                    f"id={getattr(item, 'audit_id', '')} "
                    f"priority={getattr(item, 'priority_label', '')} "
                    f"topic={getattr(item, 'topic', '')} "
                    "(enqueue only; AuditRunner not run on hot path)."
                )
        except Exception:
            # Fail-soft: never interrupt evaluate
            return

    def get_decision_history(self, limit: int | None = None) -> list[DecisionLog]:
        """Return recent in-memory decision logs for audit/review.

        Args:
            limit: If provided, return only the most recent N entries.

        Returns:
            A list of DecisionLog entries (newest last). A copy is returned
            so callers cannot mutate the internal log.
        """
        if limit is None:
            return list(self._decision_logs)
        return list(self._decision_logs[-limit:])

    def load_persisted_decision_logs(
        self,
        user_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[Any]:
        """Load DecisionLogRecord entries from disk (empty list if disabled).

        Does not replace the in-memory log; use for audit / pattern mining
        across sessions.
        """
        if self._persistence is None:
            return []
        uid = self._safe_user_id(
            user_id if user_id is not None else self._decision_log_user_id,
            fallback="default",
        )
        try:
            return list(self._persistence.load_decision_logs(uid, limit=limit))
        except Exception:
            return []

    def flush_decision_logs_to_persistence(
        self,
        user_id: str | None = None,
        *,
        only_unpersisted: bool = False,
    ) -> int:
        """Write current in-memory DecisionLog entries to disk.

        Useful after a session of pure in-memory evaluates when persistence
        was attached late. Returns count of append attempts (0 if disabled).

        When ``user_id`` is None, each log is written under its own
        ``DecisionLog.user_id`` (per-entry isolation). When ``user_id`` is set,
        all flushed entries use that id (explicit re-scope).

        Note: ``only_unpersisted`` is reserved for a future cursor; currently
        all in-memory logs are appended (callers should flush once).
        """
        if self._persistence is None:
            return 0
        force_uid = (
            self._safe_user_id(user_id, fallback="default")
            if user_id is not None and str(user_id).strip() != ""
            else None
        )
        n = 0
        for log in self._decision_logs:
            try:
                uid = force_uid or self._safe_user_id(
                    getattr(log, "user_id", None) or self._decision_log_user_id,
                    fallback="default",
                )
                self._persistence.append_decision_log(
                    log,
                    user_id=uid,
                    max_entries=self._max_persisted_decision_logs,
                )
                n += 1
            except Exception:
                continue
        return n

    @property
    def persistence_enabled(self) -> bool:
        """True when LocalPersistence is configured for decision logs."""
        return self._persistence is not None

