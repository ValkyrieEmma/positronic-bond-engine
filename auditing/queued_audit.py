"""
queued_audit.py
===============

Lightweight **queued audit scaffolding** for provenance-aware correction.

Purpose
-------
Accept retrospective / deferred audit work **without blocking** real-time
``EthicsEngine.evaluate()``. Evidence snapshots on DecisionLog remain the
primary provenance trail; this queue records *intent to re-examine* and
compact *results* when a correction is applied.

This is scaffolding only — not a full audit runner or media lifecycle.

Does **not**:
- generate speech or questions
- re-run full deliberation inside evaluate()
- block the real-time path

Priority order (lower number = higher urgency)::
  safety (0) > relationship_health (1) > ordinary (2)
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Priority & status constants
# ---------------------------------------------------------------------------

PRIORITY_SAFETY = 0
PRIORITY_RELATIONSHIP_HEALTH = 1
PRIORITY_ORDINARY = 2

PRIORITY_LABELS: dict[int, str] = {
    PRIORITY_SAFETY: "safety",
    PRIORITY_RELATIONSHIP_HEALTH: "relationship_health",
    PRIORITY_ORDINARY: "ordinary",
}

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

_VALID_STATUSES = frozenset(
    {STATUS_PENDING, STATUS_RUNNING, STATUS_COMPLETED, STATUS_CANCELLED}
)
_VALID_PRIORITIES = frozenset(
    {PRIORITY_SAFETY, PRIORITY_RELATIONSHIP_HEALTH, PRIORITY_ORDINARY}
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_audit_id() -> str:
    return f"audit_{uuid.uuid4().hex[:12]}"


def priority_from_label(label: str | int | None) -> int:
    """Map string or int priority to ordered int (default ordinary)."""
    if isinstance(label, int) and label in _VALID_PRIORITIES:
        return label
    s = str(label or "ordinary").strip().lower().replace(" ", "_")
    if s in ("safety", "sanctity", "hard_override", "harm"):
        return PRIORITY_SAFETY
    if s in (
        "relationship_health",
        "rh",
        "bond",
        "relationship",
        "agency",
        "user_agency",
    ):
        return PRIORITY_RELATIONSHIP_HEALTH
    if s.isdigit() and int(s) in _VALID_PRIORITIES:
        return int(s)
    return PRIORITY_ORDINARY


@dataclass
class QueuedAudit:
    """One deferred audit request / result (inspectable, non-speaking).

    Attributes:
        audit_id: Stable local id.
        priority: 0 safety > 1 relationship_health > 2 ordinary.
        priority_label: Human-readable priority name.
        topic: Short topic / focus label (not dialogue).
        reason: Why this audit was queued.
        status: pending | running | completed | cancelled.
        user_id: Local scope.
        created_at / updated_at: ISO timestamps.
        time_window: Optional ``{from, to}`` ISO bounds for the review window.
        decision_log_refs: Timestamps or opaque ids of related decision logs.
        bond_snapshot_refs: Names of bond bags considered (e.g. enjoyment_score).
        evidence_snapshot_ref: Optional compact provenance pointer.
        result: Compact completion bag (corrections, stale marks, notes).
        potentially_stale_marks: Targets marked stale when this audit completed.
        forces_speech / forces_question: Always False.
        schema_version: Structure version.
    """

    audit_id: str = field(default_factory=_new_audit_id)
    priority: int = PRIORITY_ORDINARY
    priority_label: str = "ordinary"
    topic: str = ""
    reason: str = ""
    status: str = STATUS_PENDING
    user_id: str = "default"
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    time_window: dict[str, str] = field(default_factory=dict)
    decision_log_refs: list[str] = field(default_factory=list)
    bond_snapshot_refs: list[str] = field(default_factory=list)
    evidence_snapshot_ref: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    potentially_stale_marks: list[dict[str, Any]] = field(default_factory=list)
    forces_speech: bool = False
    forces_question: bool = False
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forces_speech"] = False
        d["forces_question"] = False
        pri = int(d.get("priority") if d.get("priority") is not None else PRIORITY_ORDINARY)
        if pri not in _VALID_PRIORITIES:
            pri = PRIORITY_ORDINARY
        d["priority"] = pri
        d["priority_label"] = PRIORITY_LABELS.get(pri, "ordinary")
        status = str(d.get("status") or STATUS_PENDING)
        if status not in _VALID_STATUSES:
            status = STATUS_PENDING
        d["status"] = status
        d["topic"] = str(d.get("topic") or "")[:96]
        d["reason"] = str(d.get("reason") or "")[:280]
        d["decision_log_refs"] = [
            str(x)[:96] for x in (d.get("decision_log_refs") or [])
        ][:24]
        d["bond_snapshot_refs"] = [
            str(x)[:64] for x in (d.get("bond_snapshot_refs") or [])
        ][:12]
        # result stays compact
        res = d.get("result") if isinstance(d.get("result"), dict) else {}
        d["result"] = {
            k: v
            for k, v in {
                "summary": str(res.get("summary") or "")[:280],
                "corrected": [str(x)[:96] for x in (res.get("corrected") or [])][:12],
                "potentially_stale": [
                    str(x)[:96] for x in (res.get("potentially_stale") or [])
                ][:12],
                "notes": [str(x)[:120] for x in (res.get("notes") or [])][:8],
                "completed_at": str(res.get("completed_at") or ""),
            }.items()
            if v not in ("", [], None)
        }
        marks = []
        for m in d.get("potentially_stale_marks") or []:
            if isinstance(m, dict):
                marks.append(
                    {
                        "target": str(m.get("target") or "")[:64],
                        "reason": str(m.get("reason") or "")[:160],
                        "audit_id": str(m.get("audit_id") or d.get("audit_id") or "")[
                            :48
                        ],
                        "marked_at": str(m.get("marked_at") or "")[:64],
                    }
                )
            else:
                marks.append(
                    {
                        "target": str(m)[:64],
                        "reason": "",
                        "audit_id": str(d.get("audit_id") or "")[:48],
                        "marked_at": "",
                    }
                )
        d["potentially_stale_marks"] = marks[:16]
        tw = d.get("time_window") if isinstance(d.get("time_window"), dict) else {}
        d["time_window"] = {
            k: str(v)[:64]
            for k, v in tw.items()
            if k in ("from", "to", "since", "until") and v
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> QueuedAudit:
        if not data:
            return cls()
        pri = priority_from_label(data.get("priority_label") or data.get("priority"))
        status = str(data.get("status") or STATUS_PENDING)
        if status not in _VALID_STATUSES:
            status = STATUS_PENDING
        marks_raw = data.get("potentially_stale_marks") or []
        marks: list[dict[str, Any]] = []
        for m in marks_raw:
            if isinstance(m, dict):
                marks.append(
                    {
                        "target": str(m.get("target") or "")[:64],
                        "reason": str(m.get("reason") or "")[:160],
                        "audit_id": str(m.get("audit_id") or "")[:48],
                        "marked_at": str(m.get("marked_at") or "")[:64],
                    }
                )
        return cls(
            audit_id=str(data.get("audit_id") or _new_audit_id())[:48],
            priority=pri,
            priority_label=PRIORITY_LABELS.get(pri, "ordinary"),
            topic=str(data.get("topic") or "")[:96],
            reason=str(data.get("reason") or "")[:280],
            status=status,
            user_id=str(data.get("user_id") or "default"),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            time_window=dict(data.get("time_window") or {})
            if isinstance(data.get("time_window"), dict)
            else {},
            decision_log_refs=[
                str(x)[:96] for x in (data.get("decision_log_refs") or [])
            ][:24],
            bond_snapshot_refs=[
                str(x)[:64] for x in (data.get("bond_snapshot_refs") or [])
            ][:12],
            evidence_snapshot_ref=dict(data.get("evidence_snapshot_ref") or {})
            if isinstance(data.get("evidence_snapshot_ref"), dict)
            else {},
            result=dict(data.get("result") or {})
            if isinstance(data.get("result"), dict)
            else {},
            potentially_stale_marks=marks[:16],
            forces_speech=False,
            forces_question=False,
            schema_version=int(data.get("schema_version") or 1),
        )


def compact_audit_result(
    *,
    summary: str = "",
    corrected: list[str] | None = None,
    potentially_stale: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact completion result bag."""
    return {
        "summary": str(summary or "")[:280],
        "corrected": [str(x)[:96] for x in (corrected or [])][:12],
        "potentially_stale": [str(x)[:96] for x in (potentially_stale or [])][:12],
        "notes": [str(x)[:120] for x in (notes or [])][:8],
        "completed_at": _utc_now_iso(),
        "forces_speech": False,
        "forces_question": False,
    }


class AuditQueue:
    """In-memory (optionally durable) priority queue for deferred audits.

    Persistence is optional via ``persist_load`` / ``persist_save`` callables
    that read/write a list of audit dicts for a user. Failures never raise
    into real-time callers when ``fail_soft`` is True (default).
    """

    def __init__(
        self,
        *,
        user_id: str = "default",
        persist_load: Callable[[str], list[dict[str, Any]]] | None = None,
        persist_save: Callable[[str, list[dict[str, Any]]], None] | None = None,
        fail_soft: bool = True,
        max_entries: int = 200,
    ) -> None:
        self._user_id = str(user_id or "default")
        self._persist_load = persist_load
        self._persist_save = persist_save
        self._fail_soft = bool(fail_soft)
        self._max_entries = max(10, int(max_entries))
        self._items: list[QueuedAudit] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._persist_load is None:
            return
        try:
            rows = self._persist_load(self._user_id) or []
            self._items = [
                QueuedAudit.from_dict(r) for r in rows if isinstance(r, dict)
            ]
        except Exception:
            if not self._fail_soft:
                raise
            self._items = []

    def _save(self) -> None:
        if self._persist_save is None:
            return
        try:
            # Cap size: keep highest-priority pending + recent completed
            rows = [a.to_dict() for a in self._items]
            if len(rows) > self._max_entries:
                # Prefer pending first, then by recency
                pending = [r for r in rows if r.get("status") == STATUS_PENDING]
                rest = [r for r in rows if r.get("status") != STATUS_PENDING]
                rest.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
                rows = (pending + rest)[: self._max_entries]
            self._persist_save(self._user_id, rows)
        except Exception:
            if not self._fail_soft:
                raise

    def reload(self) -> None:
        """Re-read from durable store (if configured)."""
        self._load()

    # ------------------------------------------------------------------
    # Queue operations (never block evaluate — pure local work)
    # ------------------------------------------------------------------

    def enqueue(
        self,
        *,
        topic: str,
        reason: str,
        priority: str | int = PRIORITY_ORDINARY,
        user_id: str | None = None,
        decision_log_refs: list[str] | None = None,
        bond_snapshot_refs: list[str] | None = None,
        evidence_snapshot_ref: dict[str, Any] | None = None,
        time_window: dict[str, str] | None = None,
        audit_id: str | None = None,
    ) -> QueuedAudit:
        """Accept a new audit request. Fast; does not run the audit."""
        try:
            pri = priority_from_label(priority)
            uid = str(user_id or self._user_id or "default")
            item = QueuedAudit(
                audit_id=str(audit_id or _new_audit_id())[:48],
                priority=pri,
                priority_label=PRIORITY_LABELS.get(pri, "ordinary"),
                topic=str(topic or "")[:96],
                reason=str(reason or "")[:280],
                status=STATUS_PENDING,
                user_id=uid,
                decision_log_refs=[str(x)[:96] for x in (decision_log_refs or [])][:24],
                bond_snapshot_refs=[
                    str(x)[:64] for x in (bond_snapshot_refs or [])
                ][:12],
                evidence_snapshot_ref=dict(evidence_snapshot_ref or {})
                if isinstance(evidence_snapshot_ref, dict)
                else {},
                time_window=dict(time_window or {})
                if isinstance(time_window, dict)
                else {},
                forces_speech=False,
                forces_question=False,
            )
            # De-dupe by audit_id
            self._items = [a for a in self._items if a.audit_id != item.audit_id]
            self._items.append(item)
            self._save()
            return item
        except Exception:
            if not self._fail_soft:
                raise
            return QueuedAudit(
                topic=str(topic or "")[:96],
                reason=f"enqueue_failed_soft: {reason}"[:280],
                status=STATUS_CANCELLED,
                user_id=str(user_id or self._user_id or "default"),
            )

    def list_all(self) -> list[QueuedAudit]:
        return list(self._items)

    def list_pending(self) -> list[QueuedAudit]:
        """Pending audits in priority order (safety first), then created_at."""
        pending = [a for a in self._items if a.status == STATUS_PENDING]
        pending.sort(key=lambda a: (int(a.priority), str(a.created_at)))
        return pending

    def peek_next(self) -> QueuedAudit | None:
        pending = self.list_pending()
        return pending[0] if pending else None

    def get(self, audit_id: str) -> QueuedAudit | None:
        aid = str(audit_id or "")
        for a in self._items:
            if a.audit_id == aid:
                return a
        return None

    def mark_running(self, audit_id: str) -> QueuedAudit | None:
        a = self.get(audit_id)
        if a is None or a.status not in (STATUS_PENDING, STATUS_RUNNING):
            return a
        a.status = STATUS_RUNNING
        a.updated_at = _utc_now_iso()
        self._save()
        return a

    def cancel(self, audit_id: str, *, reason: str = "") -> QueuedAudit | None:
        a = self.get(audit_id)
        if a is None:
            return None
        if a.status in (STATUS_COMPLETED, STATUS_CANCELLED):
            return a
        a.status = STATUS_CANCELLED
        a.updated_at = _utc_now_iso()
        if reason:
            a.reason = (a.reason + f" | cancelled: {reason}")[:280]
        self._save()
        return a

    def complete(
        self,
        audit_id: str,
        *,
        summary: str = "",
        corrected: list[str] | None = None,
        potentially_stale: list[str] | None = None,
        notes: list[str] | None = None,
        result: dict[str, Any] | None = None,
    ) -> QueuedAudit | None:
        """Mark audit completed and record a compact result + stale marks.

        Does not re-run ethics. Callers may then apply corrections separately.
        """
        a = self.get(audit_id)
        if a is None:
            return None
        if a.status == STATUS_CANCELLED:
            return a
        res = (
            dict(result)
            if isinstance(result, dict) and result
            else compact_audit_result(
                summary=summary,
                corrected=corrected,
                potentially_stale=potentially_stale,
                notes=notes,
            )
        )
        res["forces_speech"] = False
        res["forces_question"] = False
        a.result = res
        a.status = STATUS_COMPLETED
        a.updated_at = _utc_now_iso()

        # Build potentially_stale_marks from result targets
        stale_targets = list(res.get("potentially_stale") or potentially_stale or [])
        marks: list[dict[str, Any]] = []
        now = _utc_now_iso()
        for t in stale_targets:
            marks.append(
                {
                    "target": str(t)[:64],
                    "reason": str(res.get("summary") or a.reason or "")[:160],
                    "audit_id": a.audit_id,
                    "marked_at": now,
                }
            )
        a.potentially_stale_marks = marks[:16]
        self._save()
        return a

    def collect_potentially_stale_marks(
        self, *, completed_only: bool = True
    ) -> list[dict[str, Any]]:
        """Aggregate stale marks from audits (for bond provenance_markers)."""
        out: list[dict[str, Any]] = []
        for a in self._items:
            if completed_only and a.status != STATUS_COMPLETED:
                continue
            for m in a.potentially_stale_marks or []:
                if isinstance(m, dict) and m.get("target"):
                    out.append(dict(m))
        # de-dupe by target+audit_id
        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for m in out:
            key = f"{m.get('target')}|{m.get('audit_id')}"
            if key in seen:
                continue
            seen.add(key)
            uniq.append(m)
        return uniq[:32]


def suggest_audit_from_decision(
    *,
    decision: str = "",
    flags: list[str] | None = None,
    user_id: str = "default",
    decision_log_ref: str | None = None,
    evidence_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Suggest a queue payload from a decision outcome (no side effects).

    Returns None when no deferred audit is warranted. Used by optional hooks
    so evaluate() stays non-blocking (caller enqueues separately / fail-soft).
    """
    flags_l = [str(f) for f in (flags or [])]
    decision_u = str(decision or "").upper()

    if "hard_override_violation" in flags_l:
        return {
            "topic": "safety_hard_override_review",
            "reason": (
                "Hard Sanctity / harm override fired — queue deferred safety "
                "provenance review of supporting evidence (non-blocking)."
            ),
            "priority": PRIORITY_SAFETY,
            "user_id": user_id,
            "decision_log_refs": [decision_log_ref] if decision_log_ref else [],
            "bond_snapshot_refs": [],
            "evidence_snapshot_ref": {
                "flags_sample": flags_l[:12],
                "decision": decision_u,
            }
            if not evidence_snapshot
            else {
                "flags_sample": flags_l[:12],
                "decision": decision_u,
                "has_evidence_snapshot": True,
            },
        }

    if any(
        f in flags_l
        for f in (
            "relationship_concern",
            "relationship_health_concern",
            "user_agency_concern",
        )
    ):
        return {
            "topic": "relationship_health_review",
            "reason": (
                "Relationship / agency concern raised — queue deferred bond "
                "provenance review (advisory; does not force speech)."
            ),
            "priority": PRIORITY_RELATIONSHIP_HEALTH,
            "user_id": user_id,
            "decision_log_refs": [decision_log_ref] if decision_log_ref else [],
            "bond_snapshot_refs": [
                "careful_truth_telling",
                "enjoyment_score",
                "observation_candidates_snapshot",
            ],
            "evidence_snapshot_ref": {
                "flags_sample": flags_l[:12],
                "decision": decision_u,
            },
        }

    # Optional ordinary trail when limited_data + concern-like flags
    if "limited_data" in flags_l and decision_u in ("REFUSE", "DEFER"):
        return {
            "topic": "limited_data_decision_review",
            "reason": (
                "Limited-data path produced refuse/defer — queue ordinary "
                "provenance check for individual-variation safeguards."
            ),
            "priority": PRIORITY_ORDINARY,
            "user_id": user_id,
            "decision_log_refs": [decision_log_ref] if decision_log_ref else [],
            "bond_snapshot_refs": [],
            "evidence_snapshot_ref": {"flags_sample": flags_l[:12]},
        }

    return None
