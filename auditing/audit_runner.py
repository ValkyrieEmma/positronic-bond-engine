"""
audit_runner.py
===============

On-demand **audit runner lifecycle** for deferred QueuedAudit items.

Purpose
-------
Process pending audits in priority order (safety > relationship_health >
ordinary) without blocking live ``EthicsEngine.evaluate()``.

For each audit the runner:
  1. mark_running
  2. Load related decision-log / bond snapshot refs (fail-soft)
  3. Re-trigger related deliberations offline via EthicsEngine.evaluate
  4. Compare prior vs fresh conclusions; record compact corrections
  5. Mark dependent bags potentially_stale (near-miss priors retained)
  6. Optional temporary media purge (features ≫ clip; hook optional)
  7. complete() with inspectable result bag

Does **not**:
- generate speech or questions
- invent a second ethics engine
- auto-schedule in the background (caller invokes explicitly)
- rewrite bond texture values (only provenance marks)

Dependencies are injected so LocalPersistence / EthicsEngine stay modular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .queued_audit import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_RUNNING,
    AuditQueue,
    QueuedAudit,
    compact_audit_result,
)

# Material flag families for "conclusion changed" (not every soft note)
_MATERIAL_FLAG_PREFIXES = (
    "hard_override",
    "relationship_concern",
    "relationship_health_concern",
    "user_agency_concern",
    "requires_self_audit",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "to_dict"):
        try:
            d = obj.to_dict()
            return dict(d) if isinstance(d, dict) else {}
        except Exception:
            return {}
    # DecisionLog-like / record-like
    out: dict[str, Any] = {}
    for key in (
        "timestamp",
        "proposed_action",
        "decision",
        "confidence",
        "flags",
        "principles_considered",
        "user_id",
        "evidence_snapshot",
        "context",
        "ontology_version",
    ):
        if hasattr(obj, key):
            out[key] = getattr(obj, key)
    return out


def _material_flags(flags: list[str] | None) -> set[str]:
    out: set[str] = set()
    for f in flags or []:
        s = str(f)
        if any(s.startswith(p) or p in s for p in _MATERIAL_FLAG_PREFIXES):
            out.add(s)
    return out


@dataclass
class AuditRunReport:
    """Inspectable summary of one batch run (non-speaking)."""

    user_id: str
    processed: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed_soft: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    forces_speech: bool = False
    forces_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "processed": list(self.processed),
            "completed": list(self.completed),
            "failed_soft": list(self.failed_soft),
            "notes": list(self.notes)[:24],
            "forces_speech": False,
            "forces_question": False,
        }


class AuditRunner:
    """Process pending QueuedAudit items in priority order (on-demand).

    Typical use with LocalPersistence::

        store = LocalPersistence(path)
        queue = store.get_audit_queue(user_id)
        engine = EthicsEngine()  # offline instance; no live traffic
        runner = AuditRunner(
            queue,
            user_id=user_id,
            ethics_engine=engine,
            load_decision_logs=lambda uid: store.load_decision_logs(uid),
            load_bond_state=lambda uid: store.load_bond_state(uid),
            apply_stale_marks=lambda **kw: store.apply_audit_stale_marks_to_bond(**kw),
            media_purge=optional_purge_fn,
        )
        report = runner.process_batch(max_items=5)

    Never call from inside live evaluate() hot path.
    """

    def __init__(
        self,
        queue: AuditQueue,
        *,
        user_id: str = "default",
        ethics_engine: Any | None = None,
        ethics_engine_factory: Callable[[], Any] | None = None,
        load_decision_logs: Callable[[str], list[Any]] | None = None,
        load_bond_state: Callable[[str], Any] | None = None,
        apply_stale_marks: Callable[..., Any] | None = None,
        media_purge: Callable[[str, dict[str, str]], list[Any]] | None = None,
        fail_soft: bool = True,
    ) -> None:
        if queue is None:
            raise TypeError("queue is required")
        self.queue = queue
        self.user_id = str(user_id or getattr(queue, "_user_id", None) or "default")
        self._ethics_engine = ethics_engine
        self._ethics_engine_factory = ethics_engine_factory
        self._load_decision_logs = load_decision_logs
        self._load_bond_state = load_bond_state
        self._apply_stale_marks = apply_stale_marks
        self._media_purge = media_purge
        self._fail_soft = bool(fail_soft)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_next(self) -> QueuedAudit | None:
        """Process the highest-priority pending audit (or None if empty)."""
        nxt = self.queue.peek_next()
        if nxt is None:
            return None
        return self.process_one(nxt.audit_id)

    def process_batch(self, max_items: int | None = 10) -> AuditRunReport:
        """Process up to ``max_items`` pending audits in priority order."""
        report = AuditRunReport(user_id=self.user_id)
        cap = 10 if max_items is None else max(0, int(max_items))
        for _ in range(cap):
            item = self.process_next()
            if item is None:
                break
            report.processed.append(item.audit_id)
            if item.status == STATUS_COMPLETED:
                report.completed.append(item.audit_id)
            elif item.status not in (STATUS_PENDING, STATUS_RUNNING):
                # completed or cancelled after soft failure still counted
                if item.status != STATUS_COMPLETED:
                    report.failed_soft.append(item.audit_id)
        report.notes.append(
            f"batch processed={len(report.processed)} completed={len(report.completed)}"
        )
        report.forces_speech = False
        report.forces_question = False
        return report

    def process_one(self, audit_id: str) -> QueuedAudit | None:
        """Full lifecycle for a single audit id."""
        notes: list[str] = []
        corrected: list[str] = []
        potentially_stale: list[str] = []
        step_log: list[str] = []

        item = self.queue.get(audit_id)
        if item is None:
            return None
        if item.status not in (STATUS_PENDING, STATUS_RUNNING):
            notes.append(f"skip: status already {item.status}")
            return item

        try:
            self.queue.mark_running(audit_id)
            step_log.append("marked_running")
            uid = str(item.user_id or self.user_id)

            # --- Load decision logs ---
            logs = self._load_related_logs(uid, item.decision_log_refs)
            step_log.append(f"loaded_decision_logs n={len(logs)}")
            if not logs and item.decision_log_refs:
                notes.append("decision_log_refs missing or unresolved (fail-soft)")

            # --- Load bond snapshot ---
            bond = self._load_bond(uid)
            step_log.append("loaded_bond" if bond else "bond_missing_or_skipped")
            if bond is None and item.bond_snapshot_refs:
                notes.append("bond snapshot unavailable (fail-soft)")

            # --- Re-trigger deliberations offline ---
            comparisons = self._retrigger_deliberations(logs, item=item)
            step_log.append(f"retriggers n={len(comparisons)}")
            for cmp in comparisons:
                notes.append(str(cmp.get("note") or "")[:120])
                if cmp.get("changed"):
                    corrected.append(str(cmp.get("correction_ref") or "decision"))
                    # Dependent bond bags may be stale when ethics conclusion shifts
                    for ref in item.bond_snapshot_refs or []:
                        potentially_stale.append(str(ref))
                    potentially_stale.append(
                        str(cmp.get("correction_ref") or "prior_decision")
                    )

            # Bond refs marked when RH/safety audit and evidence present
            if item.bond_snapshot_refs and (
                corrected
                or item.priority_label in ("safety", "relationship_health")
            ):
                for ref in item.bond_snapshot_refs:
                    r = str(ref)
                    if r not in potentially_stale:
                        # Near-miss: retain prior bags; only mark stale when
                        # we have re-deliberation changes or safety-class review
                        if corrected or item.priority_label == "safety":
                            potentially_stale.append(r)

            # Dedup stale list
            seen_s: set[str] = set()
            stale_uniq: list[str] = []
            for s in potentially_stale:
                if s and s not in seen_s:
                    seen_s.add(s)
                    stale_uniq.append(s)
            potentially_stale = stale_uniq[:16]

            # --- Write stale marks for downstream ---
            if potentially_stale and self._apply_stale_marks is not None:
                try:
                    self._apply_stale_marks(
                        user_id=uid,
                        audit_id=item.audit_id,
                        potentially_stale=potentially_stale,
                        summary=(
                            f"Audit {item.topic}: "
                            + ("; ".join(corrected[:3]) if corrected else "review complete")
                        )[:160],
                    )
                    step_log.append(f"stale_marks_written n={len(potentially_stale)}")
                except Exception as exc:
                    notes.append(f"stale_marks_write_failed_soft: {exc}"[:120])
                    step_log.append("stale_marks_write_failed_soft")
            elif potentially_stale:
                notes.append("stale_marks computed but no apply_stale_marks hook")
                step_log.append("stale_marks_hook_absent")

            # --- Media purge (optional) ---
            purged: list[Any] = []
            if self._media_purge is not None:
                try:
                    tw = dict(item.time_window or {})
                    purged = list(
                        self._media_purge(uid, tw) or []
                    )
                    step_log.append(f"media_purged n={len(purged)}")
                    notes.append(f"temporary media purged: {len(purged)} item(s)")
                except Exception as exc:
                    notes.append(f"media_purge_failed_soft: {exc}"[:120])
                    step_log.append("media_purge_failed_soft")
            else:
                notes.append("media_purge skipped (no hook)")
                step_log.append("media_purge_skipped")

            # --- Complete ---
            summary = self._build_summary(
                item=item,
                corrected=corrected,
                potentially_stale=potentially_stale,
                comparisons=comparisons,
            )
            result = compact_audit_result(
                summary=summary,
                corrected=corrected,
                potentially_stale=potentially_stale,
                notes=notes[:8],
            )
            result["steps"] = step_log[:16]
            result["comparisons"] = [
                {
                    "prior_decision": c.get("prior_decision"),
                    "fresh_decision": c.get("fresh_decision"),
                    "changed": bool(c.get("changed")),
                    "ref": c.get("correction_ref"),
                }
                for c in comparisons[:8]
            ]
            result["prior_conclusions_retained"] = True  # near-miss intentional
            result["media_purged"] = [str(p)[:120] for p in purged][:12]
            result["forces_speech"] = False
            result["forces_question"] = False

            completed = self.queue.complete(
                audit_id,
                summary=summary,
                corrected=corrected,
                potentially_stale=potentially_stale,
                notes=notes[:8],
                result=result,
            )
            step_log.append("completed")
            return completed
        except Exception as exc:
            if not self._fail_soft:
                raise
            # Soft-complete with failure notes so queue does not stick forever
            notes.append(f"runner_failed_soft: {exc}"[:160])
            try:
                return self.queue.complete(
                    audit_id,
                    summary=f"Audit failed soft: {exc}"[:280],
                    corrected=[],
                    potentially_stale=[],
                    notes=notes[:8],
                    result={
                        **compact_audit_result(
                            summary=f"Audit failed soft: {exc}"[:280],
                            notes=notes[:8],
                        ),
                        "steps": step_log + ["failed_soft"],
                        "forces_speech": False,
                        "forces_question": False,
                    },
                )
            except Exception:
                return self.queue.get(audit_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_engine(self) -> Any | None:
        if self._ethics_engine is not None:
            return self._ethics_engine
        if self._ethics_engine_factory is not None:
            try:
                eng = self._ethics_engine_factory()
                self._ethics_engine = eng
                return eng
            except Exception:
                if not self._fail_soft:
                    raise
                return None
        return None

    def _load_related_logs(
        self, user_id: str, refs: list[str]
    ) -> list[dict[str, Any]]:
        if self._load_decision_logs is None:
            return []
        try:
            raw = self._load_decision_logs(user_id) or []
        except Exception:
            if not self._fail_soft:
                raise
            return []
        rows = [_as_dict(r) for r in raw]
        if not refs:
            # No explicit refs: take most recent few for ordinary re-check
            return rows[-3:] if rows else []
        ref_set = {str(r) for r in refs}
        matched = [
            r
            for r in rows
            if str(r.get("timestamp") or "") in ref_set
            or str(r.get("timestamp") or "")[:19] in {x[:19] for x in ref_set}
        ]
        # If timestamps don't match exactly, fall back to recent rows (fail-soft)
        if not matched and rows:
            return rows[-min(3, len(rows)) :]
        return matched

    def _load_bond(self, user_id: str) -> dict[str, Any] | None:
        if self._load_bond_state is None:
            return None
        try:
            bond = self._load_bond_state(user_id)
            return _as_dict(bond) if bond is not None else None
        except Exception:
            if not self._fail_soft:
                raise
            return None

    def _retrigger_deliberations(
        self,
        logs: list[dict[str, Any]],
        *,
        item: QueuedAudit,
    ) -> list[dict[str, Any]]:
        """Re-run EthicsEngine.evaluate on prior proposed actions (offline)."""
        engine = self._get_engine()
        comparisons: list[dict[str, Any]] = []
        if engine is None or not hasattr(engine, "evaluate"):
            if logs:
                comparisons.append(
                    {
                        "changed": False,
                        "note": "no ethics engine; skipped re-deliberation",
                        "prior_decision": logs[0].get("decision"),
                        "fresh_decision": None,
                        "correction_ref": None,
                    }
                )
            return comparisons

        for log in logs[:5]:
            action = str(log.get("proposed_action") or "").strip()
            if not action:
                continue
            prior_decision = str(log.get("decision") or "")
            prior_flags = list(log.get("flags") or [])
            ctx = dict(log.get("context") or {}) if isinstance(log.get("context"), dict) else {}
            ctx.setdefault("user_id", item.user_id or self.user_id)
            # Offline re-eval: no speech generation; engine only
            try:
                stance = engine.evaluate(
                    action,
                    ctx,
                    user_id=item.user_id or self.user_id,
                )
            except Exception as exc:
                comparisons.append(
                    {
                        "changed": False,
                        "note": f"re-eval failed soft: {exc}"[:120],
                        "prior_decision": prior_decision,
                        "fresh_decision": None,
                        "correction_ref": f"decision_log:{log.get('timestamp')}",
                    }
                )
                continue

            fresh_decision = str(getattr(stance, "decision", "") or "")
            fresh_flags = list(getattr(stance, "flags", None) or [])
            prior_mat = _material_flags(prior_flags)
            fresh_mat = _material_flags(fresh_flags)
            decision_changed = prior_decision.upper() != fresh_decision.upper()
            flags_changed = prior_mat != fresh_mat
            changed = decision_changed or flags_changed
            # Sanctity absolute: if either path hard-overrides, note explicitly
            sanctity = (
                "hard_override_violation" in prior_flags
                or "hard_override_violation" in fresh_flags
            )
            note = (
                f"re-eval action ref={str(log.get('timestamp') or '')[:19]}: "
                f"{prior_decision}->{fresh_decision}"
                + (" [material change]" if changed else " [stable]")
                + (" [sanctity involved]" if sanctity else "")
            )
            comparisons.append(
                {
                    "changed": changed,
                    "note": note[:160],
                    "prior_decision": prior_decision,
                    "fresh_decision": fresh_decision,
                    "prior_material_flags": sorted(prior_mat)[:8],
                    "fresh_material_flags": sorted(fresh_mat)[:8],
                    "correction_ref": f"decision_log:{log.get('timestamp')}",
                    "sanctity_involved": sanctity,
                }
            )
        return comparisons

    def _build_summary(
        self,
        *,
        item: QueuedAudit,
        corrected: list[str],
        potentially_stale: list[str],
        comparisons: list[dict[str, Any]],
    ) -> str:
        if corrected:
            return (
                f"[{item.priority_label}] {item.topic}: "
                f"{len(corrected)} correction(s); "
                f"{len(potentially_stale)} potentially_stale mark(s). "
                f"Prior conclusions retained as near-miss (boundary learning)."
            )[:280]
        n = len(comparisons)
        return (
            f"[{item.priority_label}] {item.topic}: review complete; "
            f"{n} re-deliberation(s); no material corrections. "
            f"Prior conclusions retained."
        )[:280]


def build_runner_from_persistence(
    persistence: Any,
    user_id: str = "default",
    *,
    ethics_engine: Any | None = None,
    ethics_engine_factory: Callable[[], Any] | None = None,
    media_purge: Callable[[str, dict[str, str]], list[Any]] | None = None,
) -> AuditRunner:
    """Convenience: AuditRunner bound to LocalPersistence-like store."""
    queue = persistence.get_audit_queue(user_id)

    def _load_logs(uid: str) -> list[Any]:
        if hasattr(persistence, "load_decision_logs"):
            return list(persistence.load_decision_logs(uid) or [])
        return []

    def _load_bond(uid: str) -> Any:
        if hasattr(persistence, "load_bond_state"):
            return persistence.load_bond_state(uid)
        return None

    def _stale(**kwargs: Any) -> Any:
        if hasattr(persistence, "apply_audit_stale_marks_to_bond"):
            return persistence.apply_audit_stale_marks_to_bond(**kwargs)
        return None

    return AuditRunner(
        queue,
        user_id=user_id,
        ethics_engine=ethics_engine,
        ethics_engine_factory=ethics_engine_factory,
        load_decision_logs=_load_logs,
        load_bond_state=_load_bond,
        apply_stale_marks=_stale,
        media_purge=media_purge,
        fail_soft=True,
    )
