"""
engagement_queue.py
====================

Queue of proactive **engagement candidates** — topics or observations the
system might later choose to bring up on its own — and their lifecycle.
Mirrors ``auditing.queued_audit`` (``QueuedAudit`` / ``AuditQueue``) closely
on purpose: dataclass + queue class + persistence pair, same cap/eviction
shape, same fail-soft persistence contract. The two scaffolds are meant to
stay easy to reason about side by side.

Deliberately not named anything with "proactive" in it: that word already
names a different concept elsewhere in this codebase — proactive
*disclosure* about the user's own interaction history
(``evaluation/eval_harness.py --history-proactive``,
``core/relationship_health.py``'s multi-episode disclosure trajectories),
not proactive *topic surfacing*. "Engagement" here matches
``core/engagement_window.py`` (Phase 2 step 2), which this queue is meant to
sit downstream of.

Scope (Phase 2 step 3 of the roadmap; step 5 added get_next_candidate())
---------------------------------------------------------------------------
This module is the queue data structure, its own operations, persistence,
and (as of step 5) the single gated entry point that actually selects and
releases a candidate for surfacing — nothing more. It deliberately does
**not**:

- classify conversation for topic resolution — ``reassess()`` only handles
  age-based expiry (see its docstring for why, and what's missing)
- classify "the user wants me to stop bringing this up" —
  ``cancel_matching()`` only builds the cancellation mechanism; deciding
  when to call it with which scope is future work
- generate speech, questions, or candidate content itself
- decide when the system is otherwise free to do maintenance/audit work at
  all (the separate, not-yet-implemented "recharge cycle" design) —
  ``get_next_candidate()`` only decides whether an *already-queued*
  candidate may be shown to a person right now; the two concerns don't
  depend on each other

``get_next_candidate()`` (Phase 2 step 5 — added 2026-08-03)
----------------------------------------------------------------
The entry point that ties ``core.engagement_window.EngagementWindowModel``
(step 2) and this queue (step 3) together, and is the one place this phase
proves the ethics gate is never bypassed: every candidate this method could
possibly return has already been routed through a real
``EthicsEngine.evaluate()`` call and gotten an affirmative verdict back,
with no code path that skips that check. See
``EngagementQueue.get_next_candidate()``'s own docstring for the exact
order of operations. A method on this class, not a free function elsewhere
or a method on ``EngagementWindowModel``/``EthicsEngine``, because
selecting *which* queued candidate to release is fundamentally a queue
operation built directly on ``claim_for_surfacing()`` /
``release_claim()`` — the readiness/window/ethics checks are consulted,
not owned, by this method.

Persistence limitation (shared with auditing.queued_audit.AuditQueue)
------------------------------------------------------------------------
Every mutation is a full load → in-memory mutate → full save round trip
through plain JSON files (see ``persistence.stores.EngagementCandidateStore``
/ ``persistence/json_backend.py``), with no cross-process file locking. Two
processes writing for the same user at the same time could clobber each
other. Fine for this single-process product — the same limitation the audit
queue already has and does not attempt to solve; not addressed here either,
not a silent divergence from that precedent.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.enjoyment_score import (
    EnjoymentScore,
    compute_instant_enjoyment,
    extract_enjoyment_signals_from_interaction,
    update_enjoyment_score,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_SURFACED = "surfaced"
STATUS_STALE = "stale"
STATUS_CANCELLED = "cancelled"

_VALID_STATUSES = frozenset(
    {STATUS_PENDING, STATUS_CLAIMED, STATUS_SURFACED, STATUS_STALE, STATUS_CANCELLED}
)

# Label prefix for record_reception()'s evidence entries in
# core.enjoyment_score's provenance trail — distinct from ordinary blended
# enjoyment-signal channel names so a reaction to a specific proactively
# surfaced candidate reads unambiguously as that, not general enjoyment
# signal (see record_reception()).
RECEPTION_EVIDENCE_LABEL = "proactive_candidate_reception"

# Only these two literal decisions count as "the ethics gate approved
# surfacing this candidate" (see get_next_candidate()). Deliberately an
# allow-list, not a block-list keyed to "REFUSE"/"HOLD": EthicsEngine.
# evaluate()'s real decision vocabulary is APPROVE / APPROVE_WITH_CONDITIONS
# / REFUSE / DEFER / REQUIRES_SELF_AUDIT (see core/ethics_engine.py's
# evaluate() docstring) — "HOLD" is a label api/interaction.py uses at its
# own layer, not something evaluate() itself ever returns. An allow-list
# means anything unrecognized (REFUSE, DEFER, REQUIRES_SELF_AUDIT, a typo,
# a future new decision label, an empty/missing decision) fails closed
# instead of silently slipping through.
_APPROVING_DECISIONS = frozenset({"APPROVE", "APPROVE_WITH_CONDITIONS"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_candidate_id() -> str:
    return f"engcand_{uuid.uuid4().hex[:10]}"


def _proposed_action_for_candidate(candidate: EngagementCandidate) -> str:
    """Natural-language ``proposed_action`` for ``ethics_engine.evaluate()``.

    The action being evaluated is the *system's own* proposed act of
    raising this topic — not the topic text standing in for something the
    user said — matching how proposed_action is used everywhere else in
    this codebase (see auditing/audit_runner.py's own re-evaluation calls).
    """
    parts = [f"Proactively raise the topic '{candidate.topic}' with the user."]
    if candidate.reason:
        parts.append(f"Reason this was queued: {candidate.reason}")
    return " ".join(parts)[:500]


def _parse_iso(s: str | None) -> datetime | None:
    """Parse a stored ISO timestamp; aware UTC on success, None otherwise.

    Narrow, matching reader for this module's own created_at/expires_at
    format (mirrors core.session_time's private _parse_iso) — not a general
    ISO parser, and unparseable/garbage values are treated as absent rather
    than raising, so a hand-edited or corrupted bag can't crash reassess().
    """
    if not s or not str(s).strip():
        return None
    raw = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class EngagementCandidate:
    """One candidate topic/observation the system might proactively surface.

    Attributes:
        id: Stable local id.
        topic: Short topic label (not dialogue).
        reason: Why this candidate was proposed.
        source: Provenance — where this candidate came from (e.g.
            "engagement_window", "concept_pattern", "understanding_gap").
        status: pending | claimed | surfaced | stale | cancelled.
        user_id: Local scope.
        created_at: ISO timestamp.
        expires_at: Optional ISO timestamp; reassess() marks a pending
            candidate stale once this is in the past (see reassess()).
        relevance_notes: Optional free-text context for why this is
            relevant right now (internal notes only, not dialogue).
        forces_speech / forces_question: Always False.
        schema_version: Structure version.
    """

    id: str = field(default_factory=_new_candidate_id)
    topic: str = ""
    reason: str = ""
    source: str = "unknown"
    status: str = STATUS_PENDING
    user_id: str = "default"
    created_at: str = field(default_factory=_utc_now_iso)
    expires_at: str | None = None
    relevance_notes: str | None = None
    forces_speech: bool = False
    forces_question: bool = False
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forces_speech"] = False
        d["forces_question"] = False
        status = str(d.get("status") or STATUS_PENDING)
        if status not in _VALID_STATUSES:
            status = STATUS_PENDING
        d["status"] = status
        d["id"] = str(d.get("id") or _new_candidate_id())[:64]
        d["topic"] = str(d.get("topic") or "")[:96]
        d["reason"] = str(d.get("reason") or "")[:280]
        d["source"] = str(d.get("source") or "unknown")[:48]
        d["user_id"] = str(d.get("user_id") or "default")
        d["expires_at"] = str(d["expires_at"]) if d.get("expires_at") else None
        d["relevance_notes"] = (
            str(d["relevance_notes"])[:280] if d.get("relevance_notes") else None
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EngagementCandidate:
        if not data:
            return cls()
        status = str(data.get("status") or STATUS_PENDING)
        if status not in _VALID_STATUSES:
            status = STATUS_PENDING
        return cls(
            id=str(data.get("id") or _new_candidate_id())[:64],
            topic=str(data.get("topic") or "")[:96],
            reason=str(data.get("reason") or "")[:280],
            source=str(data.get("source") or "unknown")[:48],
            status=status,
            user_id=str(data.get("user_id") or "default"),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            expires_at=str(data["expires_at"]) if data.get("expires_at") else None,
            relevance_notes=(
                str(data["relevance_notes"])[:280]
                if data.get("relevance_notes")
                else None
            ),
            forces_speech=False,
            forces_question=False,
            schema_version=int(data.get("schema_version") or 1),
        )


class EngagementQueue:
    """In-memory (optionally durable) queue of EngagementCandidates.

    Persistence is optional via ``persist_load`` / ``persist_save``
    callables that read/write a list of candidate dicts for a user — same
    contract as ``auditing.queued_audit.AuditQueue``. Failures never raise
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
        self._items: list[EngagementCandidate] = []
        # Guards claim_for_surfacing()'s check-then-set against a second
        # near-simultaneous call for the same id, and every other mutation
        # for consistency (see claim_for_surfacing()'s docstring).
        self._lock = threading.Lock()
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
                EngagementCandidate.from_dict(r) for r in rows if isinstance(r, dict)
            ]
        except Exception:
            if not self._fail_soft:
                raise
            self._items = []

    def _save(self) -> None:
        """Persist the current items, capped at ``max_entries``.

        Mirrors AuditQueue._save exactly, including its quirk: only the
        *persisted* rows are capped/evicted here — self._items itself is
        never trimmed, so it can grow past max_entries in memory across
        many enqueue() calls on the same live queue object within one
        process (each save() still recomputes the cap from the full
        in-memory list, so what lands on disk always respects it; a fresh
        reload() picks up the persisted, capped view). Copied as-is per
        this module's brief to mirror the audit queue's real behavior
        rather than a cleaned-up guess at it.

        Eviction: pending candidates are always kept first; the remaining
        budget is filled with non-pending candidates, most recent first.
        AuditQueue sorts that non-pending "rest" bucket by updated_at;
        EngagementCandidate has no per-status-change timestamp, so
        created_at is the closest available recency signal.
        """
        if self._persist_save is None:
            return
        try:
            rows = [c.to_dict() for c in self._items]
            if len(rows) > self._max_entries:
                pending = [r for r in rows if r.get("status") == STATUS_PENDING]
                rest = [r for r in rows if r.get("status") != STATUS_PENDING]
                rest.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
                rows = (pending + rest)[: self._max_entries]
            self._persist_save(self._user_id, rows)
        except Exception:
            if not self._fail_soft:
                raise

    def reload(self) -> None:
        """Re-read from durable store (if configured)."""
        self._load()

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def enqueue(self, candidate: EngagementCandidate) -> EngagementCandidate:
        """Add a candidate. De-dupes by id: re-enqueuing an id already in
        the queue replaces that entry in place rather than creating a
        duplicate. Enforces the cap/eviction policy described in _save().
        """
        if not isinstance(candidate, EngagementCandidate):
            raise TypeError("enqueue() requires an EngagementCandidate")
        with self._lock:
            self._items = [c for c in self._items if c.id != candidate.id]
            self._items.append(candidate)
            self._save()
        return candidate

    def reassess(self, now: datetime | None = None) -> list[EngagementCandidate]:
        """Age-based expiry only: mark pending candidates whose
        ``expires_at`` is in the past as stale.

        This is a known-narrower ``reassess()`` than the final version —
        topic-resolution-based staleness ("the user already worked this
        through on their own, unprompted, so it's no longer worth
        surfacing") needs conversation context and a classifier that
        doesn't exist yet. Not silently omitted: that logic simply isn't
        built yet, and this docstring is the marker for it.

        Safe to call repeatedly. Only ever touches candidates currently
        ``pending`` — a candidate that is already ``surfaced``,
        ``cancelled``, or ``stale`` is left untouched even if its
        ``expires_at`` is also in the past.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        changed: list[EngagementCandidate] = []
        with self._lock:
            for c in self._items:
                if c.status != STATUS_PENDING or not c.expires_at:
                    continue
                expires = _parse_iso(c.expires_at)
                if expires is not None and expires <= now:
                    c.status = STATUS_STALE
                    changed.append(c)
            if changed:
                self._save()
        return changed

    def claim_for_surfacing(self, candidate_id: str) -> EngagementCandidate | None:
        """Atomically transition one ``pending`` candidate to ``claimed``.

        Returns the candidate on success; ``None`` if it is not currently
        pending (already claimed, surfaced, stale, cancelled, or unknown).
        The check-then-set runs under ``self._lock``, so a second
        near-simultaneous call for the same id reliably observes the
        already-claimed state instead of racing to claim the same pending
        candidate twice — only one caller can ever get a non-None result
        for a given id.

        Exists now so the future ``get_next_candidate()`` step can call it
        — this is only the claiming primitive, not candidate selection.
        """
        cid = str(candidate_id or "")
        with self._lock:
            for c in self._items:
                if c.id != cid:
                    continue
                if c.status != STATUS_PENDING:
                    return None
                c.status = STATUS_CLAIMED
                self._save()
                return c
        return None

    def release_claim(self, candidate_id: str) -> EngagementCandidate | None:
        """Atomically revert one ``claimed`` candidate back to ``pending``.

        Returns the candidate on success; ``None`` if it is not currently
        ``claimed`` (unknown id, or already pending/surfaced/stale/
        cancelled). Symmetric counterpart to ``claim_for_surfacing()``, same
        lock-guarded check-then-set atomicity.

        Added for ``get_next_candidate()`` (Phase 2 step 5): a claimed
        candidate that then fails the ethics-gate check must not be lost or
        cancelled — it needs to go back to pending so it can be reassessed
        or reconsidered later. ``claim_for_surfacing()`` was deliberately
        one-directional when it was built (Phase 2 step 3); this closes
        that gap rather than working around it from outside the class.
        """
        cid = str(candidate_id or "")
        with self._lock:
            for c in self._items:
                if c.id != cid:
                    continue
                if c.status != STATUS_CLAIMED:
                    return None
                c.status = STATUS_PENDING
                self._save()
                return c
        return None

    def cancel_matching(
        self,
        scope: dict[str, Any] | None = None,
        *,
        reason: str = "",
    ) -> list[EngagementCandidate]:
        """Cancel matching *pending* candidates; queue-wide when ``scope``
        is empty.

        ``scope`` recognizes:
            candidate_id: cancel exactly this one candidate, if pending.
            topic: cancel every pending candidate with this exact topic.
            (both omitted / scope empty or None): cancel every pending
                candidate for this queue's user — queue-wide.

        Matched candidates are marked ``cancelled``, never deleted — they
        stay inspectable via ``list_all()`` / ``get()``. The classifier
        that decides *when* to call this with which scope (recognizing a
        user's "stop bringing that up") is future work; this only builds
        the mechanism it will call.
        """
        s = scope if isinstance(scope, dict) else {}
        cid = str(s.get("candidate_id") or "").strip()
        topic = str(s.get("topic") or "").strip()

        cancelled: list[EngagementCandidate] = []
        with self._lock:
            for c in self._items:
                if c.status != STATUS_PENDING:
                    continue
                if cid and c.id != cid:
                    continue
                if topic and c.topic != topic:
                    continue
                c.status = STATUS_CANCELLED
                if reason:
                    note = f"cancelled: {reason}"
                    c.relevance_notes = (
                        f"{c.relevance_notes} | {note}"[:280]
                        if c.relevance_notes
                        else note[:280]
                    )
                cancelled.append(c)
            if cancelled:
                self._save()
        return cancelled

    def record_reception(
        self,
        candidate_id: str,
        interaction: dict[str, Any] | None,
        *,
        previous_enjoyment: EnjoymentScore | dict[str, Any] | None = None,
        health_flags: list[str] | None = None,
        ethical_concern_active: bool = False,
        user_id: str | None = None,
    ) -> EnjoymentScore:
        """Record how the user received a specific proactively-surfaced
        candidate, through core.enjoyment_score's real evidence-recording
        mechanism (``update_enjoyment_score``) — not a parallel/shadow
        store.

        ``interaction`` is read the same way any other enjoyment update
        reads one (``extract_enjoyment_signals_from_interaction``). On top
        of whatever ordinary enjoyment signals that interaction carries,
        this also injects one additional signal channel literally named
        ``"{RECEPTION_EVIDENCE_LABEL}:{candidate_id}"``, so the resulting
        ``EnjoymentScore.evidence`` list carries an entry retrievable and
        traceable back to this specific candidate — distinct from ordinary
        blended enjoyment-signal evidence, not mixed in anonymously.
        (Candidate ids should stay reasonably short: enjoyment_score.py's
        own channel-key handling truncates at 48 characters, an existing
        constraint of the real mechanism this deliberately doesn't work
        around — see compute_instant_enjoyment.)

        Does not change the candidate's status — this only records the
        reaction; marking a candidate "surfaced" belongs to the future
        surfacing entry point, not here. Does not persist the returned
        EnjoymentScore either — callers do that via
        ``LocalPersistence.update_bond_enjoyment_score``, the same as every
        other EnjoymentScore consumer; this queue does not own bond-state
        writes (mirrors queued_audit.py / LocalPersistence's own division
        of labor — QueuedAudit's own bond writes go through
        ``LocalPersistence.apply_audit_stale_marks_to_bond``, not through
        AuditQueue itself).
        """
        cid = str(candidate_id or "")
        base_signals = extract_enjoyment_signals_from_interaction(interaction)
        instant, _strengths, _evidence, _topics = compute_instant_enjoyment(base_signals)
        signals = dict(base_signals)
        signals[f"{RECEPTION_EVIDENCE_LABEL}:{cid}"] = instant
        return update_enjoyment_score(
            previous_enjoyment,
            signals=signals,
            health_flags=health_flags,
            ethical_concern_active=ethical_concern_active,
            user_id=str(user_id or self._user_id or "default"),
        )

    def get_next_candidate(
        self,
        user_id: str,
        now: datetime,
        ethics_engine: Any,
        engagement_window_model: Any,
        *,
        mid_session: bool = False,
    ) -> EngagementCandidate | None:
        """The Phase 2 step 5 entry point: at most one already-queued
        candidate, gated by the learned activity window AND a real
        ``EthicsEngine.evaluate()`` call — never returned on the strength
        of just one of those, and never on neither.

        Order of operations:

        1. ``reassess(now)`` first, so staleness is current before anything
           else looks at this queue.
        2 & 4. Readiness (``timezone_known`` + ``sufficient_history``) and
           the open-window check are both already fully embodied by a
           single call to
           ``engagement_window_model.is_open_window(user_id, now,
           mid_session=mid_session)``: ``mid_session=True`` returns True
           unconditionally (a live touch is its own proof — checked before
           anything else), and cold start (either readiness gate unmet)
           already returns False rather than guessing from wall-clock time
           — see ``core/engagement_window.py``'s own docstring. Reusing
           that one call is deliberate: it *is* "the existing readiness/
           is_open_window logic already built and tested in step 2", not a
           parallel reimplementation of it. ``mid_session`` itself is meant
           to be read straight off this turn's own session_context —
           ``core.session_time``'s ``touch_turn()`` / ``begin_session()``
           now return a ``live_touch_this_turn`` key for exactly this (see
           that module's docstring) — not tracked independently by callers.
        5. ``list_pending()[0]`` — already oldest-created-first (see that
           method's docstring), matching ``queued_audit.py``'s own
           ``(priority, created_at)`` tie-break convention on the
           ``created_at`` axis (this queue has no priority dimension of its
           own).
        6. ``claim_for_surfacing()`` — the atomic primitive built for
           exactly this in Phase 2 step 3.
        7. Routed through ``ethics_engine.evaluate()`` before ever being
           returned. Fails closed: only a literal ``APPROVE`` /
           ``APPROVE_WITH_CONDITIONS`` verdict (or an evaluate() call that
           raises) surfaces the candidate; anything else — ``REFUSE``,
           ``DEFER``, ``REQUIRES_SELF_AUDIT``, an unrecognized label, or an
           exception during evaluation — releases the claim back to
           pending via ``release_claim()`` and returns None. The candidate
           is never lost or cancelled by a failed gate check: only an
           actual queue mutation (stale-by-age, or an explicit
           ``cancel_matching()``) removes it from future consideration.
        8. At most one candidate, ever, per call — explicit in the vision
           doc ("asks or reports rather than dumping").
        """
        self.reassess(now)

        if not engagement_window_model.is_open_window(
            user_id, now, mid_session=mid_session
        ):
            return None

        pending = self.list_pending()
        if not pending:
            return None

        claimed = self.claim_for_surfacing(pending[0].id)
        if claimed is None:
            # Lost the race to another near-simultaneous caller (or this
            # candidate's state changed between list_pending() and here) --
            # an honest "nothing available this call", not an error.
            return None

        decision = ""
        try:
            action = _proposed_action_for_candidate(claimed)
            stance = ethics_engine.evaluate(
                action, {"user_id": user_id}, user_id=user_id
            )
            decision = str(getattr(stance, "decision", "") or "").strip().upper()
        except Exception:
            decision = ""  # fail closed -- see docstring step 7

        if decision in _APPROVING_DECISIONS:
            return claimed

        self.release_claim(claimed.id)
        return None

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def list_all(self) -> list[EngagementCandidate]:
        return list(self._items)

    def list_pending(self) -> list[EngagementCandidate]:
        """Pending candidates, oldest first. No priority/selection logic
        here — that's the future get_next_candidate() step's job."""
        pending = [c for c in self._items if c.status == STATUS_PENDING]
        pending.sort(key=lambda c: str(c.created_at))
        return pending

    def get(self, candidate_id: str) -> EngagementCandidate | None:
        cid = str(candidate_id or "")
        for c in self._items:
            if c.id == cid:
                return c
        return None
