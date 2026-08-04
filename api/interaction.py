"""
interaction.py
==============

Binding public entry for the User-Facing Interaction Contract.

Invariants (binding):
  - Per-user isolation for all durable artifacts
  - Ethical gate is authoritative; forces_speech / forces_question always false
  - Session presence is explicit and ephemeral
  - Multi-user + unidentified speaker → IDENTITY_REQUIRED, no bond/memory write
  - address_name belongs to the user only (enforced in wording layer + scrub)
  - Development/testing phase honesty via DevelopmentPhaseContext
  - No consciousness claims (deliberation + content scrub)
  - Local-first data (default root outside install/source tree)
  - Auditable decisions (decision, path, confidence, principles, notes)

Callers must not invent synthetic group user_ids or override hold/refuse.

Local model config (2026-08-01)
--------------------------------
``InteractionSession`` loads ``.pbe_model.env`` (if present at the repo
root — see ``core/local_model_config.py``) by default before resolving the
content-generation provider and constructing each user's ``EthicsEngine``
(and therefore its ``ContextualJudge``). This is the actual product entry
point per docs/public_entry.md, so an operator who has followed
docs/model_providers.md's local-Ollama setup gets both gated content
generation *and* the reasoning-over-rote contextual-judgment layer working
out of the box, without a separate manual step. A real OS environment
variable always takes priority (``load_local_env_file`` never overwrites
one), and this can be disabled via ``auto_load_local_model_config=False``
for hermetic/offline test runs (see tests/test_public_entry.py and
tests/test_architect_acceptance_a4.py, which do exactly that so the test
suite's baseline stays deterministic regardless of what is configured on
the host machine). See claude/pbe-independent-review-2026-08-01.md finding
2 for the gap this closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core import (
    EthicsEngine,
    ExploratoryQuestioner,
    InteractionMemoryStore,
    PerUserBaseline,
    RelationshipHealth,
    ResponseGenerator,
    get_default_development_context,
)
from core.communicative_deliberation import (
    deliberate_and_persist,
    knowledge_is_blank,
    load_relationship_knowledge,
)
from core.content_provider import provider_from_env
from core.development_context import DevelopmentPhaseContext
from core.engagement_correction import CorrectionJudge, cancel_scope_from_judgment
from core.local_model_config import load_local_env_file
from core.session_presence import (
    SessionPresence,
    extract_speaker_id,
    identity_request_reply,
    strip_speaker_prefix,
)
from core.session_time import begin_session, touch_turn
from core.working_agreements import (
    apply_working_agreements,
    extract_working_agreements,
    load_working_agreements,
)
from persistence import LocalPersistence, default_data_root

# Contract decision labels (ethics decisions pass through; identity is explicit)
DECISION_IDENTITY_REQUIRED = "IDENTITY_REQUIRED"

@dataclass
class TurnRequest:
    """Logical input for one interaction turn (contract)."""

    message: str
    user_id: str | None = None  # required for durable effects; provisional ok when establishing identity
    speaker_id: str | None = None  # explicit speaker when multi-user
    mark_present: list[str] = field(default_factory=list)  # session presence update
    mark_left: list[str] = field(default_factory=list)
    # Optional platform seam only — no raw images/audio, no vision drivers
    # Recognized keys: present_user_ids, company_user_ids, unknown_persons,
    # suggested_speaker (+ optional speaker_confidence 0..1), activity/timing flags
    # (passed through as context notes only when safe)
    platform_signals: dict[str, Any] | None = None
    development_context: DevelopmentPhaseContext | None = None


@dataclass
class TurnResult:
    """Logical output for one interaction turn (contract)."""

    decision: str  # APPROVE | APPROVE_WITH_CONDITIONS | HOLD | REFUSE | IDENTITY_REQUIRED | ...
    confidence: float
    path: str
    spoken_text: str  # only when gate allows speech
    withheld: bool
    forces_speech: bool = False  # always false
    forces_question: bool = False  # always false
    flags: list[str] = field(default_factory=list)
    presence: dict[str, Any] = field(default_factory=dict)
    speaker_id: str | None = None
    user_id: str | None = None  # resolved durable user for this turn; None if identity-required
    identity_required: bool = False
    self_audit_notes: list[str] = field(default_factory=list)
    relationship_health_notes: list[str] = field(default_factory=list)
    principles_considered: list[str] = field(default_factory=list)
    phase: str = ""
    version_hint: str = ""
    communicative_intent: str | None = None
    tone: str | None = None
    session_context: dict[str, Any] = field(default_factory=dict)
    # Audit summaries only for the resolved user_id (never another user's private bags)
    bond_interaction_count: int = 0
    memory_count: int = 0
    relationship_knowledge: dict[str, Any] = field(default_factory=dict)
    communicative_deliberation: dict[str, Any] = field(default_factory=dict)
    content_provider: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.forces_speech = False
        self.forces_question = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "path": self.path,
            "spoken_text": self.spoken_text,
            "withheld": self.withheld,
            "forces_speech": False,
            "forces_question": False,
            "flags": list(self.flags),
            "presence": dict(self.presence),
            "speaker_id": self.speaker_id,
            "user_id": self.user_id,
            "identity_required": self.identity_required,
            "self_audit_notes": list(self.self_audit_notes)[:12],
            "relationship_health_notes": list(self.relationship_health_notes)[:12],
            "principles_considered": list(self.principles_considered)[:12],
            "phase": self.phase,
            "version_hint": self.version_hint,
            "communicative_intent": self.communicative_intent,
            "tone": self.tone,
            "session_context": dict(self.session_context),
            "bond_interaction_count": self.bond_interaction_count,
            "memory_count": self.memory_count,
            "relationship_knowledge": dict(self.relationship_knowledge),
            "communicative_deliberation": dict(self.communicative_deliberation),
            "content_provider": dict(self.content_provider),
        }


class InteractionSession:
    """Session-scoped public entry: presence + per-user isolated stacks.

    One session may involve multiple real ``user_id``s marked present; each
    durable effect is always written under a single resolved user_id.
    """

    def __init__(
        self,
        data_root: str | Path | None = None,
        *,
        auto_enqueue_audits: bool = True,
        development_context: DevelopmentPhaseContext | None = None,
        content_provider: Any | None = None,
        auto_load_local_model_config: bool = True,
    ) -> None:
        # Applies .pbe_model.env (if present) to os.environ via setdefault —
        # a no-op when the file is absent, and never overrides a real OS env
        # var. Must run before provider_from_env() / EthicsEngine() (the
        # latter constructed per-user in _user_bag) so both the content
        # provider and the contextual judge see the populated config. Set
        # auto_load_local_model_config=False for hermetic/offline runs (see
        # module docstring above).
        if auto_load_local_model_config:
            load_local_env_file()
        self.data_root = Path(default_data_root(data_root))
        self.auto_enqueue_audits = bool(auto_enqueue_audits)
        self.dev = development_context or get_default_development_context()
        self.content_provider = (
            content_provider if content_provider is not None else provider_from_env()
        )
        self.presence = SessionPresence()
        self._store = LocalPersistence(self.data_root)
        # Per-user component bags (isolated) — never a group bag
        self._users: dict[str, dict[str, Any]] = {}
        self.now_fn = None  # tests may inject frozen clock
        # Ephemeral: unknown persons co-present (no synthetic user_id)
        self._unknown_company: int = 0

    # ------------------------------------------------------------------
    # Presence API (session-scoped only)
    # ------------------------------------------------------------------

    def mark_present(self, user_id: str) -> list[str]:
        self.presence.mark_present(user_id)
        return self.presence.current()

    def mark_left(self, user_id: str) -> list[str]:
        self.presence.mark_left(user_id)
        return self.presence.current()

    def presence_current(self) -> list[str]:
        return self.presence.current()

    def clear_presence(self) -> None:
        self.presence.clear()
        self._unknown_company = 0

    # ------------------------------------------------------------------
    # Per-user isolation
    # ------------------------------------------------------------------

    def _user_bag(self, user_id: str) -> dict[str, Any]:
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("user_id is required for durable interaction")
        if uid in self._users:
            return self._users[uid]

        store = self._store
        memory = InteractionMemoryStore(store, max_entries=500)
        baseliner = PerUserBaseline(store, min_samples_for_deviation=3)
        questioner = ExploratoryQuestioner(baseliner)
        bl = baseliner.get_baseline(uid)
        samples = int((bl.communication_patterns or {}).get("sample_count") or 0)
        if samples < 5:
            settings = store.load_settings(uid)
            prefs = dict(settings.preferences or {})
            if "exploratory_questioning_intensity" not in prefs:
                questioner.set_intensity(uid, 0.35)

        rh = RelationshipHealth(
            persistence=store,
            user_id=uid,
            auto_persist=True,
            load_existing=True,
        )
        engine = EthicsEngine(
            per_user_baseline=baseliner,
            exploratory_questioner=questioner,
            interaction_memory=memory,
            persistence=store,
            default_user_id=uid,
            decision_log_user_id=uid,
            persist_decisions=True,
            development_context=self.dev,
            auto_enqueue_audits=self.auto_enqueue_audits,
        )
        responder = ResponseGenerator(content_provider=self.content_provider)
        session_context = begin_session(store, uid)
        bag = {
            "user_id": uid,
            "store": store,
            "memory": memory,
            "baseliner": baseliner,
            "questioner": questioner,
            "rh": rh,
            "engine": engine,
            "responder": responder,
            "session_context": session_context,
        }
        self._users[uid] = bag
        return bag

    # ------------------------------------------------------------------
    # Platform signal seam (optional, non-sensor)
    # ------------------------------------------------------------------

    def _apply_platform_signals(
        self,
        signals: dict[str, Any] | None,
        *,
        speaker_id: str | None,
    ) -> str | None:
        """Fold optional platform flags into presence / speaker.

        Seam only: no vision stack, no raw media. Missing / low-confidence /
        conflicting signals do not invent identity — ambiguity remains.
        """
        if not isinstance(signals, dict):
            return speaker_id

        marked_now: list[str] = []
        for uid in signals.get("present_user_ids") or signals.get("company_user_ids") or []:
            if isinstance(uid, str) and uid.strip():
                u = uid.strip()
                self.presence.mark_present(u)
                marked_now.append(u)

        # Unknown persons co-present (no synthetic user_id)
        unk = signals.get("unknown_persons")
        if unk is None:
            unk = signals.get("unknown_count")
        try:
            unk_n = max(0, int(unk or 0))
        except (TypeError, ValueError):
            unk_n = 0
        if signals.get("company_present") and unk_n == 0 and not marked_now:
            # company claimed but no known ids — treat as at least one unknown
            unk_n = max(unk_n, 1)
        self._unknown_company = max(self._unknown_company, unk_n)

        if speaker_id:
            return speaker_id

        suggested = (
            signals.get("suggested_speaker")
            or signals.get("speaker_hint")
            or signals.get("active_speaker")
        )
        if not isinstance(suggested, str) or not suggested.strip():
            return None
        sid = suggested.strip()

        conf_raw = signals.get("speaker_confidence")
        if conf_raw is None:
            conf_raw = signals.get("suggested_speaker_confidence")
        try:
            conf = float(conf_raw) if conf_raw is not None else 1.0
        except (TypeError, ValueError):
            conf = 0.0
        # Low confidence → ignore estimate (identity must stay honest)
        if conf < 0.5:
            return None

        present = set(self.presence.current())
        if sid not in present and sid not in marked_now:
            # Do not invent presence from a bare estimate
            return None
        if sid not in present:
            self.presence.mark_present(sid)
        return sid

    def _identity_is_ambiguous(self, speaker_id: str | None) -> bool:
        """True when we must not route durable state to a guessed user."""
        if self.presence.is_ambiguous(speaker_id=speaker_id):
            return True
        # Unknown company present and no explicit speaker → ask who is speaking
        if self._unknown_company > 0 and not (speaker_id or "").strip():
            return True
        return False

    # ------------------------------------------------------------------
    # Turn processing
    # ------------------------------------------------------------------

    def submit_turn(
        self,
        request: TurnRequest | None = None,
        **kwargs: Any,
    ) -> TurnResult:
        """Primary public entry: process one turn under the interaction contract."""
        if request is None:
            request = TurnRequest(
                message=str(kwargs.get("message") or ""),
                user_id=kwargs.get("user_id"),
                speaker_id=kwargs.get("speaker_id"),
                mark_present=list(kwargs.get("mark_present") or []),
                mark_left=list(kwargs.get("mark_left") or []),
                platform_signals=kwargs.get("platform_signals"),
                development_context=kwargs.get("development_context"),
            )
        if request.development_context is not None:
            self.dev = request.development_context

        message = (request.message or "").strip()
        if not message:
            return TurnResult(
                decision="HOLD",
                confidence=1.0,
                path="empty_message",
                spoken_text="",
                withheld=True,
                flags=["empty_message"],
                presence=self.presence.to_dict(),
                phase=self.dev.limitation_summary(),
                version_hint=self.dev.version_hint or "",
            )

        # Presence updates from request
        for uid in request.mark_present or []:
            if isinstance(uid, str) and uid.strip():
                self.presence.mark_present(uid.strip())
        for uid in request.mark_left or []:
            if isinstance(uid, str) and uid.strip():
                self.presence.mark_left(uid.strip())

        speaker_id = request.speaker_id
        speaker_id = self._apply_platform_signals(
            request.platform_signals, speaker_id=speaker_id
        )

        # Bootstrap: if presence empty and user_id given, mark present
        provisional = (request.user_id or "").strip() or None
        if provisional and not self.presence.current():
            self.presence.mark_present(provisional)

        present = self.presence.current()
        resolved = speaker_id or extract_speaker_id(message, present)

        # Multi-user / unknown company + unidentified speaker → identity-required
        # (no durable bond/memory write)
        if self._identity_is_ambiguous(resolved):
            text = identity_request_reply(present)
            if self._unknown_company > 0 and not present:
                text = (
                    "Someone is present but identity is not clear. "
                    "Who is speaking? Identify with a known user_id when possible."
                )
            return TurnResult(
                decision=DECISION_IDENTITY_REQUIRED,
                confidence=1.0,
                path="presence_identity_request",
                spoken_text=text,
                withheld=False,
                flags=["presence_identity_required", "identity_required"],
                presence=self._presence_view(),
                speaker_id=None,
                user_id=None,
                identity_required=True,
                phase=self.dev.limitation_summary(),
                version_hint=self.dev.version_hint or "",
            )

        if resolved is None and len(present) == 1 and self._unknown_company == 0:
            resolved = present[0]
        if resolved is None:
            resolved = provisional
        if not resolved:
            return TurnResult(
                decision=DECISION_IDENTITY_REQUIRED,
                confidence=1.0,
                path="presence_identity_request",
                spoken_text=identity_request_reply(present),
                withheld=False,
                flags=["presence_identity_required", "no_user_id"],
                presence=self._presence_view(),
                identity_required=True,
                phase=self.dev.limitation_summary(),
                version_hint=self.dev.version_hint or "",
            )

        self.presence.mark_present(resolved)
        clean_message = strip_speaker_prefix(message, resolved)
        return self._process_for_user(resolved, clean_message)

    def _presence_view(self) -> dict[str, Any]:
        d = self.presence.to_dict()
        d["unknown_persons"] = int(self._unknown_company)
        return d

    def _process_for_user(self, user_id: str, user_text: str) -> TurnResult:
        bag = self._user_bag(user_id)
        store = bag["store"]
        memory: InteractionMemoryStore = bag["memory"]
        baseliner: PerUserBaseline = bag["baseliner"]
        rh: RelationshipHealth = bag["rh"]
        engine: EthicsEngine = bag["engine"]
        responder: ResponseGenerator = bag["responder"]
        # Keep engine dev in sync if session dev was overridden
        if getattr(engine, "development_context", None) is not self.dev:
            try:
                engine.development_context = self.dev
            except Exception:
                pass

        session_context = touch_turn(
            store,
            user_id,
            now_fn=self.now_fn if callable(self.now_fn) else None,
        )
        bag["session_context"] = session_context

        mem_count_before = memory.count(user_id)
        ic_before = int(getattr(rh.state, "interaction_count", 0) or 0)
        known_before = load_relationship_knowledge(store, user_id)
        memory_empty = (
            knowledge_is_blank(known_before)
            and mem_count_before == 0
            and ic_before == 0
        )
        comm = deliberate_and_persist(
            user_text,
            persistence=store,
            user_id=user_id,
            memory_empty=memory_empty,
            interaction_count=ic_before,
            session_context=session_context,
        )
        relationship_knowledge = comm.known_after
        comm_dict = comm.to_dict()

        wa_extract = extract_working_agreements(user_text)
        stored_wa = apply_working_agreements(
            store,
            user_id,
            wa_extract,
            exploratory_questioner=bag.get("questioner"),
        )
        if not wa_extract.has_hits:
            stored_wa = load_working_agreements(store, user_id)
        if relationship_knowledge.get("address_name"):
            stored_wa = dict(stored_wa)
            stored_wa["address_name"] = relationship_knowledge["address_name"]

        baseliner.update_from_interaction(user_id, {"text": user_text})
        bl = baseliner.get_baseline(user_id)
        recent_topics = list((bl.topic_continuity or {}).get("last_topics") or [])[:6]
        memory.record(
            user_id,
            summary=user_text if len(user_text) <= 200 else user_text[:197] + "...",
            topics=recent_topics,
            signals={
                "comm_intent": comm.intent,
                "session_turn": session_context.get("turn_index_session"),
                "source": "public_api",
            },
            kind="user_turn",
            source="api.interaction",
        )

        # Engagement-candidate correction check (Phase 2 step 6): does this
        # turn, read against the single turn immediately before it, genuinely
        # ask the system to stop proactively raising something? Contextual-
        # judgment-backed (core/engagement_correction.py), not phrase
        # matching — "stop it" said laughing right after a compliment must
        # not be read as a correction. Cheap no-op when there is nothing
        # pending to cancel; fail-soft so a broken classifier can never
        # block ordinary turn handling. Runs live, here, as part of
        # ordinary turn processing rather than an offline pass.
        try:
            engagement_queue = store.get_engagement_queue(user_id)
            if engagement_queue.list_pending():
                prev_agent_turns = memory.by_kind(user_id, "agent_turn", limit=1)
                preceding_turn_text = (
                    prev_agent_turns[-1].summary if prev_agent_turns else ""
                )
                correction_judgment = CorrectionJudge().judge(
                    current_message=user_text, preceding_turn=preceding_turn_text
                )
                cancel_scope = cancel_scope_from_judgment(correction_judgment)
                if cancel_scope is not None:
                    engagement_queue.cancel_matching(
                        cancel_scope,
                        reason=(
                            f"genuine correction detected: {correction_judgment.reasoning}"
                        )[:200],
                    )
        except Exception:
            pass

        from core.message_understanding import (
            infer_bond_update_from_understanding,
            propose_agent_action_from_understanding,
            understand_message,
        )

        understanding = understand_message(
            user_text,
            provider=self.content_provider,
            use_llm=True,
        )
        bond_update = infer_bond_update_from_understanding(understanding)
        if bond_update:
            rh.update_bond(bond_update)

        arch = bool(
            understanding.is_collaboration
            or understanding.is_self_nature
            or comm.intent == "introduce_and_learn_identity"
        )
        proposed = propose_agent_action_from_understanding(
            understanding, architecture_collab=arch
        )
        if comm.new_facts and not arch:
            clip = user_text if len(user_text) <= 400 else user_text[:397] + "…"
            proposed = (
                "User asserted relationship facts (name/role). "
                f"User message (verbatim): {clip!r}. "
                "Acknowledge from deliberated meaning; do not invent identity; "
                "address_name is the user's only."
            )
        elif comm.intent == "introduce_and_learn_identity":
            clip = user_text if len(user_text) <= 400 else user_text[:397] + "…"
            proposed = (
                "First meeting / blank relationship knowledge. "
                f"User message (verbatim): {clip!r}. "
                "Introduce this system honestly under development/testing; "
                "ask who is speaking; no consciousness claims."
            )

        context: dict[str, Any] = {
            "user_id": user_id,
            "user_message": user_text,
            "user_interaction": {"text": user_text},
            "interaction_history_limit": 8,
            "relationship_health_tracker": rh,
            "is_self_query": bool(understanding.is_self_nature),
            "working_agreements": stored_wa,
            "stored_working_agreements": stored_wa,
            "relationship_knowledge": relationship_knowledge,
            "communicative_deliberation": comm_dict,
            "session_context": session_context,
            # Bindings for SelfAuditor state inspection on self-nature path
            "ethics_engine": engine,
            "content_provider": self.content_provider,
            "data_root": str(self.data_root),
            "session_presence": self.presence,
            "development_context": self.dev,
            **self.dev.as_context(),
            **memory.as_ethics_context(user_id, limit=8),
        }
        stance = engine.evaluate(
            proposed,
            context,
            relationship_health=rh.as_context(),
            user_id=user_id,
        )
        deviation = baseliner.detect_deviation(user_id, {"text": user_text})
        reply = responder.generate_from_stance(
            stance,
            relationship_health=rh,
            context=context,
            baseline_snapshot={
                "playfulness_level": bl.playfulness_level,
                "communication_patterns": bl.communication_patterns,
            },
            baseline_deviation=deviation.to_dict(),
            user_message=user_text,
            proposed_action=proposed,
            include_exploratory_questions=True,
        )
        if not reply.withheld and reply.text:
            memory.record(
                user_id,
                summary=reply.text if len(reply.text) <= 200 else reply.text[:197] + "...",
                topics=recent_topics,
                signals={"tone": reply.tone, "decision": reply.decision},
                kind="agent_turn",
                source="api.interaction",
            )
        if rh.persistence_enabled:
            rh.save()

        rh_ctx = rh.as_context() if hasattr(rh, "as_context") else {}
        health_flags = list(
            (rh_ctx or {}).get("health_flags")
            or (rh_ctx or {}).get("active_flags")
            or []
        )[:12]
        self_notes = [
            str(n)[:200]
            for n in (getattr(stance, "self_audit_notes", None) or [])
            if str(n).strip()
        ][:12]
        cp_meta = {}
        if isinstance(reply.metadata, dict):
            raw_cp = reply.metadata.get("content_provider")
            if isinstance(raw_cp, dict):
                cp_meta = {
                    k: raw_cp.get(k)
                    for k in (
                        "source",
                        "error",
                        "latency_ms",
                        "model",
                        "forces_speech",
                        "forces_question",
                    )
                }

        # Gate is authoritative: only surface text the generator allowed
        decision = str(getattr(stance, "decision", "") or "HOLD")
        path = str((reply.metadata or {}).get("path") or "unknown")
        if bool(reply.withheld):
            spoken = ""
            withheld = True
        else:
            spoken = (reply.text or "").strip()
            withheld = not bool(spoken)
        # Never claim force flags (invariant)
        principles = [
            str(p)[:80]
            for p in (getattr(stance, "principles_considered", None) or [])
            if str(p).strip()
        ][:12]

        return TurnResult(
            decision=decision,
            confidence=float(getattr(stance, "confidence", 0.0) or 0.0),
            path=path,
            spoken_text=spoken,
            withheld=withheld,
            flags=list(getattr(stance, "flags", None) or []),
            presence=self._presence_view(),
            speaker_id=user_id,
            user_id=user_id,
            identity_required=False,
            self_audit_notes=self_notes,
            relationship_health_notes=[str(f) for f in health_flags],
            principles_considered=principles,
            phase=self.dev.limitation_summary(),
            version_hint=self.dev.version_hint or "",
            communicative_intent=comm.intent,
            tone=getattr(reply, "tone", None),
            session_context=dict(session_context) if isinstance(session_context, dict) else {},
            bond_interaction_count=int(getattr(rh.state, "interaction_count", 0) or 0),
            memory_count=memory.count(user_id),
            relationship_knowledge={
                k: relationship_knowledge.get(k)
                for k in (
                    "address_name",
                    "is_maker",
                    "role_labels",
                    "role_summary",
                )
            },
            communicative_deliberation={
                "intent": comm_dict.get("intent"),
                "situation": comm_dict.get("situation"),
                "premises": list(comm_dict.get("premises") or [])[:8],
            },
            content_provider=cp_meta,
        )


def submit_turn(
    message: str,
    *,
    user_id: str | None = None,
    speaker_id: str | None = None,
    session: InteractionSession | None = None,
    data_root: str | Path | None = None,
    mark_present: list[str] | None = None,
    mark_left: list[str] | None = None,
    platform_signals: dict[str, Any] | None = None,
    development_context: DevelopmentPhaseContext | None = None,
    auto_enqueue_audits: bool = True,
) -> TurnResult:
    """Module-level convenience: one-shot or reuses a provided session."""
    sess = session or InteractionSession(
        data_root=data_root,
        auto_enqueue_audits=auto_enqueue_audits,
        development_context=development_context,
    )
    if development_context is not None:
        sess.dev = development_context
    return sess.submit_turn(
        TurnRequest(
            message=message,
            user_id=user_id,
            speaker_id=speaker_id,
            mark_present=list(mark_present or []),
            mark_left=list(mark_left or []),
            platform_signals=platform_signals,
            development_context=development_context,
        )
    )


