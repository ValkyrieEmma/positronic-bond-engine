"""
response_generator.py
=====================

Minimal, **gated** text response construction from an ``EthicalStance``.

Role in the stack
-----------------
EthicsEngine decides *whether* a proposed action may proceed. This module maps
an already-made stance (plus Careful Truth-Telling signals) into a **speech
posture** and short user-facing text (or hold).

Speech postures (auditable)
---------------------------
- ``social_direct`` — ordinary approve-class contact; short, adult (default)
- ``careful_observation`` — only when CTT open **and** real evidence candidates
- ``self_audit`` — honest report of deliberated content
- ``hold`` — refuse / defer / protective / true observation silence

Conscience-first constraints
----------------------------
- **High bar for careful observation**: real candidates + open CTT + concrete
  evidence. Weak filler (greeting topics, meta co-evolution, generic history)
  never opens observation theater.
- Thin / early contact defaults to **social_direct**, not soft caution monologues.
- No soft qualifier templates ("only if useful", "no pressure", "treating gently").
- **Hard ethics win**: REFUSE / hard override never become soft approve speech.
- **Never force questions.** Exploratory questions off by default.
- **Never engagement/retention tactics.**
- Self-audit: report deliberation; no canned simulation denials; no claimed consciousness.
- Enjoyment bias never opens speech or bypasses CTT.

This module does **not** re-run EthicsEngine. Voice is out of scope (text only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ethics_engine import EthicalStance

# Speech postures (stable ids for logs / tests)
POSTURE_SOCIAL_DIRECT = "social_direct"
POSTURE_CAREFUL_OBSERVATION = "careful_observation"
POSTURE_SELF_AUDIT = "self_audit"
POSTURE_HOLD = "hold"

# Decisions that must not produce a normal companion reply.
_WITHHOLD_DECISIONS = frozenset(
    {
        "REFUSE",
        "REQUIRES_SELF_AUDIT",
        "DEFER",
    }
)

_REPLY_DECISIONS = frozenset(
    {
        "APPROVE",
        "APPROVE_WITH_CONDITIONS",
    }
)

# Protective flags that block careful observation speech (even if joint open)
_BLOCK_SPEECH_FLAGS = frozenset(
    {
        "hard_override_violation",
        "relationship_concern",
        "relationship_health_concern",
        "user_agency_concern",
    }
)

_CAREFUL_BOND_FLAGS = frozenset(
    {
        "boundary_erosion",
        "emerging_dependency",
        "one_sidedness",
        "one_sided_engagement",
        "manipulation_risk",
        "consent_concern",
        "manufactured_attachment",
        "coercive_engagement",
    }
)

# Engagement / retention language — never emit
_ENGAGEMENT_BANNED = (
    "keep you here",
    "stay a little longer",
    "don't leave",
    "for the metrics",
    "engagement",
    "come back more",
    "only i understand",
    "rely on me more",
)

# Soft / anxious observation theater — never emit
_SOFT_CAUTION_BANNED = (
    "only if useful",
    "only if it's welcome",
    "only if its welcome",
    "no pressure to go deeper",
    "treating gently",
    "treat gently",
    "worth treating gently",
    "a gentle note",
    "one careful note, only if",
    "i've noticed a pattern",
    "i have noticed a pattern",
    "without making it a demand",
    "never as a demand",
    "at your pace — no pressure",
    "at your pace - no pressure",
    "stay gently with",
    "i want to understand this better",
    "leave it alone for now",
    "or should i leave it alone",
    "happy to listen if you want",
    "no pressure either way",
    "i'd weight",
    "i would weight",
)

# Filler / meta-role topics — never promote into "I'd weight X next" continuity
_FILLER_TOPICS = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "howdy",
        "hiya",
        "greetings",
        "morning",
        "evening",
        "afternoon",
        "questions",
        "question",
        "preferences",
        "boundaries",
        "status",
        "thanks",
        "thank",
        "ok",
        "okay",
        "yes",
        "no",
        "yeah",
        "yep",
        # Role / self-reference noise from architect talk
        "architect",
        "architecture",
        "system",
        "systems",
        "brain",
        "mother",  # address name is not a project topic
        "designing",
        "design",
        "focus",
        "next",
        "people",
        "problems",
        "handle",
        "consider",
        "making",
        "essentially",
        "your",
        "what",
        "when",
        "where",
        "who",
        "which",
        "how",
        "should",
        "would",
        "could",
        "about",
        "return",
        "continue",
        "unless",
        "different",
        "focus",
        "path",
        "private",
        "validation",
        "weight",
        "optimize",
        "first",
        "call",
        "calling",
        "working",
        "work",
        "got",
        "next",
        "want",
        "like",
        "need",
        "know",
        "tell",
        "said",
        "thing",
        "things",
        "useful",
        "useful",
    }
)

# User invites the system to ask (not a topic-picker turn)
_INVITE_QUESTIONS_RE = re.compile(
    r"(?i)\b("
    r"do you have (any |a )?questions?( for me)?"
    r"|any questions?( for me)?"
    r"|what (do|would) you (want|like) to (know|ask)"
    r"|ask me (anything|something|questions?)"
    r")\b"
)

_META_CONCEPT_IDS = frozenset(
    {
        "healthy_co_evolution",
        "reciprocity_recovery",
        "trust_repair",
    }
)

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|howdy|yo|hiya|sup|"
    r"good\s*(morning|afternoon|evening|day)|"
    r"hello there|hey there|hi there)[\s!.?,-]*$",
    re.IGNORECASE,
)


@dataclass
class GeneratedResponse:
    """Result of mapping an EthicalStance to a user-facing reply (or hold).

    Attributes:
        text: What to show the user (may be empty if fully withheld / silent).
        withheld: True when no normal reply should be delivered.
        decision: Echo of the stance decision (for logging / UI).
        tone: Coarse tone label used (inspectable, not a score).
        notes: Short generator notes for audit / demo traces.
        metadata: Gate outcomes, candidates used, readiness/confidence, etc.
        forces_speech: Always False (speech is optional output, never forced).
        forces_question: Always False.
    """

    text: str
    withheld: bool = False
    decision: str = ""
    tone: str = "neutral"
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    forces_speech: bool = False
    forces_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "withheld": self.withheld,
            "decision": self.decision,
            "tone": self.tone,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
            "forces_speech": False,
            "forces_question": False,
        }


class ResponseGenerator:
    """Gated text generator: careful observation speech under CTT + ethics.

    Typical use::

        stance = engine.evaluate(proposed_action, context, relationship_health=rh)
        reply = ResponseGenerator().generate(
            stance,
            context={...},
            relationship_health=rh.as_context(),  # includes joint + candidates
        )
        if reply.withheld or not reply.text:
            # silence or hold — do not invent speech
            ...
        else:
            # deliver reply.text (auditable via reply.metadata / notes)

    Disable careful speech without removing the module::

        ResponseGenerator(enable_careful_speech=False)

    Live end-to-end (preferred)::

        stance = engine.evaluate(action, context, relationship_health=rh_ctx)
        reply = ResponseGenerator().generate_from_stance(
            stance, relationship_health=rh, context=context
        )
        # or one-shot:
        stance, reply = ResponseGenerator().generate_from_evaluate(
            engine, action, context, relationship_health=rh
        )
    """

    def __init__(
        self,
        *,
        enable_careful_speech: bool = True,
        enable_simple_ack: bool = True,
        enable_enjoyment_bias: bool = True,
        max_chars: int = 360,
        content_provider: Any | None = None,
    ) -> None:
        """
        Args:
            enable_careful_speech: When True, may surface careful text if CTT
                joint allows and candidates/deliberation exist.
            enable_simple_ack: When True and careful path not used, may emit a
                short non-observation ack on APPROVE (still no forced questions).
            enable_enjoyment_bias: When True, light style bias from EnjoymentScore
                may apply **only** on open careful paths (never opens speech).
            max_chars: Hard cap on user-facing text length.
            content_provider: Optional gated ContentProvider (model). If set,
                allowed postures may replace fallback text with provider wording.
                Provider never overrides refuse/hold and never sets force flags.
        """
        self.enable_careful_speech = bool(enable_careful_speech)
        self.enable_simple_ack = bool(enable_simple_ack)
        self.enable_enjoyment_bias = bool(enable_enjoyment_bias)
        self.max_chars = max(80, int(max_chars))
        self.content_provider = content_provider

    # ------------------------------------------------------------------
    # Live entry points (consume EthicalStance / evaluate() results)
    # ------------------------------------------------------------------

    def generate_from_stance(
        self,
        stance: EthicalStance,
        *,
        relationship_health: Any | None = None,
        context: dict[str, Any] | None = None,
        baseline_snapshot: dict[str, Any] | None = None,
        baseline_deviation: dict[str, Any] | None = None,
        user_message: str | None = None,
        proposed_action: str | None = None,
        include_exploratory_questions: bool = False,
        prefer_live_impact: bool = True,
    ) -> GeneratedResponse:
        """Generate from a live ``EthicalStance`` (post-evaluate).

        Reads CTT joint + observation candidates primarily from
        ``stance.relationship_impact`` (engine-attached), with optional live
        ``RelationshipHealth`` / context bags as fallbacks. Does not re-run
        ethics. Never forces questions (default).
        """
        ctx = dict(context or {})
        rh_obj, rh_dict = self._coerce_relationship_health(relationship_health, ctx)
        # Prefer engine impact as the live signal source
        impact = (
            stance.relationship_impact
            if isinstance(getattr(stance, "relationship_impact", None), dict)
            else {}
        )
        joint = None
        candidates = None
        if prefer_live_impact and impact:
            joint = self._joint_from_impact(impact)
            candidates = self._candidates_from_impact(impact)
        # Live tracker can refresh candidates if impact sparse and CTT open
        if rh_obj is not None and (
            not candidates
            or (
                joint
                and joint.get("joint_stance") == "careful_observation_ok"
                and not candidates
            )
        ):
            try:
                if hasattr(rh_obj, "generate_observation_candidates"):
                    bag = rh_obj.generate_observation_candidates(joint=joint)
                    if isinstance(bag, dict) and bag.get("candidates"):
                        candidates = list(bag.get("candidates") or [])
            except Exception:
                pass
        if joint is None and rh_dict:
            joint = (
                rh_dict.get("careful_truth_telling_joint")
                or rh_dict.get("careful_truth_telling")
            )
        notes_prefix = [
            "entry=generate_from_stance",
            f"impact_keys={sorted(impact.keys())[:12] if impact else []}",
            f"live_joint={bool(joint)} live_candidates={len(candidates or [])}",
        ]
        resp = self.generate(
            stance,
            ctx,
            relationship_health=rh_dict,
            baseline_snapshot=baseline_snapshot,
            baseline_deviation=baseline_deviation,
            user_message=user_message,
            proposed_action=proposed_action,
            joint=joint if isinstance(joint, dict) else None,
            observation_candidates=candidates,
            include_exploratory_questions=include_exploratory_questions,
        )
        resp.notes = notes_prefix + list(resp.notes or [])
        resp.metadata = dict(resp.metadata or {})
        resp.metadata["entry"] = "generate_from_stance"
        resp.metadata["signals_source"] = (
            "relationship_impact" if prefer_live_impact and impact else "fallback"
        )
        resp.metadata["forces_speech"] = False
        resp.metadata["forces_question"] = False
        resp.forces_speech = False
        resp.forces_question = False
        return resp

    def generate_from_evaluate(
        self,
        engine: Any,
        proposed_action: str,
        context: dict[str, Any] | None = None,
        *,
        relationship_health: Any | None = None,
        user_id: str | None = None,
        baseline_snapshot: dict[str, Any] | None = None,
        baseline_deviation: dict[str, Any] | None = None,
        user_message: str | None = None,
        include_exploratory_questions: bool = False,
        prefer_live_impact: bool = True,
    ) -> tuple[EthicalStance, GeneratedResponse]:
        """Run ``engine.evaluate`` then ``generate_from_stance`` (end-to-end).

        Returns ``(stance, response)`` for full auditability. Pass a live
        ``RelationshipHealth`` instance when possible so context can include a
        tracker for richer candidate attachment without expanding EthicsEngine.
        """
        ctx = dict(context or {})
        rh_obj, rh_dict = self._coerce_relationship_health(relationship_health, ctx)
        if rh_dict and "relationship_health" not in ctx:
            ctx["relationship_health"] = rh_dict
        # Allow engine attach paths that look for a live tracker
        if rh_obj is not None:
            ctx.setdefault("relationship_health_tracker", rh_obj)
            ctx.setdefault("bond_tracker", rh_obj)
        if user_id is not None and str(user_id).strip():
            ctx.setdefault("user_id", str(user_id).strip())
        if user_message is not None:
            ctx.setdefault("user_message", user_message)
        elif ctx.get("user_message") is None and ctx.get("message"):
            ctx["user_message"] = ctx.get("message")

        if not hasattr(engine, "evaluate"):
            raise TypeError("engine must provide evaluate()")
        stance = engine.evaluate(
            proposed_action,
            ctx,
            relationship_health=rh_dict if rh_dict else relationship_health,
            user_id=user_id or ctx.get("user_id"),
        )
        reply = self.generate_from_stance(
            stance,
            relationship_health=rh_obj if rh_obj is not None else rh_dict,
            context=ctx,
            baseline_snapshot=baseline_snapshot,
            baseline_deviation=baseline_deviation,
            user_message=user_message or ctx.get("user_message"),
            proposed_action=proposed_action,
            include_exploratory_questions=include_exploratory_questions,
            prefer_live_impact=prefer_live_impact,
        )
        reply.metadata = dict(reply.metadata or {})
        reply.metadata["entry"] = "generate_from_evaluate"
        reply.metadata["proposed_action"] = str(proposed_action or "")[:200]
        reply.notes = [
            "entry=generate_from_evaluate",
            f"evaluate.decision={getattr(stance, 'decision', '')}",
        ] + list(reply.notes or [])
        reply.forces_speech = False
        reply.forces_question = False
        return stance, reply

    def generate(
        self,
        stance: EthicalStance,
        context: dict[str, Any] | None = None,
        *,
        relationship_health: dict[str, Any] | None = None,
        baseline_snapshot: dict[str, Any] | None = None,
        baseline_deviation: dict[str, Any] | None = None,
        user_message: str | None = None,
        proposed_action: str | None = None,
        joint: dict[str, Any] | None = None,
        observation_candidates: list[dict[str, Any]] | None = None,
        include_exploratory_questions: bool = False,
    ) -> GeneratedResponse:
        """Build a ``GeneratedResponse`` under hard ethics + CTT gates.

        Prefer ``generate_from_stance`` / ``generate_from_evaluate`` for live
        engine wiring. ``include_exploratory_questions`` defaults **False**.
        """
        ctx = dict(context or {})
        decision = (stance.decision or "").strip().upper()
        notes: list[str] = [f"stance.decision={decision}"]
        flags = list(stance.flags or [])

        # Accept RelationshipHealth objects transparently
        _rh_obj, rh = self._coerce_relationship_health(relationship_health, ctx)
        if not rh:
            rh = self._resolve_rh(stance, ctx, None)
        user_text = (
            user_message
            if user_message is not None
            else str(ctx.get("user_message") or ctx.get("message") or "")
        ).strip()

        joint_bag = self._resolve_joint(stance, rh, ctx, joint)
        candidates = self._resolve_candidates(
            stance, rh, ctx, observation_candidates
        )
        enjoyment_bag = self._resolve_enjoyment(stance, rh, ctx, _rh_obj)
        stale_info = self._resolve_stale_info(stance, rh, ctx)
        gate = self._assess_speech_gate(
            stance=stance,
            decision=decision,
            flags=flags,
            joint=joint_bag,
            relationship_health=rh,
            stale_info=stale_info,
        )
        notes.extend(gate.get("notes") or [])

        base_meta: dict[str, Any] = {
            "gate": dict(gate),
            "joint_stance": gate.get("joint_stance"),
            "readiness_level": gate.get("readiness_level"),
            "confidence_level": gate.get("confidence_level"),
            "surface_ok_advisory": gate.get("surface_ok_advisory"),
            "candidate_ids": [c.get("id") for c in candidates if isinstance(c, dict)][:3],
            "enjoyment_score": float(enjoyment_bag.get("score") or 0)
            if enjoyment_bag
            else None,
            "provenance_stale": {
                "has_stale": bool(stale_info.get("has_stale")),
                "canonical_targets": list(stale_info.get("canonical_targets") or []),
                "stale_enjoyment": bool(stale_info.get("stale_enjoyment")),
                "stale_ctt": bool(stale_info.get("stale_ctt")),
                "stale_candidates": bool(stale_info.get("stale_candidates")),
            }
            if stale_info.get("has_stale")
            else {"has_stale": False},
            "forces_speech": False,
            "forces_question": False,
            "path": "unset",
            "entry": "generate",
        }

        # --- Hard ethics: REFUSE ---
        if decision == "REFUSE" or "hard_override_violation" in flags:
            resp = self._refuse_hold(stance, decision=decision or "REFUSE", flags=flags, notes=notes)
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "refuse_hold",
                "speech_posture": POSTURE_HOLD,
            }
            return self._finalize(resp)

        # --- Self-related: honest deliberation report (not canned denial) ---
        if decision == "REQUIRES_SELF_AUDIT" or "requires_self_audit" in flags:
            resp = self._self_audit_report(stance, decision="REQUIRES_SELF_AUDIT", notes=notes)
            resp = self._maybe_apply_content_provider(
                resp,
                posture=POSTURE_SELF_AUDIT,
                stance=stance,
                user_message=user_text,
                context=ctx,
                baseline_snapshot=baseline_snapshot,
                relationship_health=rh,
                notes=notes,
            )
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "self_audit_honest",
                "speech_posture": POSTURE_SELF_AUDIT,
            }
            return self._finalize(resp)

        # --- DEFER / unknown ---
        if decision not in _REPLY_DECISIONS:
            resp = self._silent_or_hold(
                decision=decision or "UNKNOWN",
                notes=notes + [f"holding: {decision or 'unknown'}"],
                reason="defer_or_unknown",
                tone="holding",
                text=(
                    "I should pause before answering that. "
                    "I don't have a solid, honest reply ready yet."
                ),
            )
            resp.metadata = {**base_meta, **resp.metadata, "path": "defer_hold"}
            return self._finalize(resp)

        # --- APPROVE paths: protective flags still block observation speech ---
        if not gate.get("ethics_allows_speech"):
            resp = self._silent_or_hold(
                decision=decision,
                notes=notes + ["blocked: protective ethics flags"],
                reason="protective_flags",
                tone="hold",
                text="",  # internal hold only
            )
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "protective_silence",
                "speech_posture": POSTURE_HOLD,
            }
            return self._finalize(resp)

        # Structural bar: only *real* evidence candidates count for observation
        real_candidates = self._filter_real_observation_candidates(
            candidates, user_message=user_text, relationship_health=rh
        )
        posture = self._resolve_speech_posture(
            decision=decision,
            flags=flags,
            gate=gate,
            real_candidates=real_candidates,
            enable_careful=self.enable_careful_speech,
            user_message=user_text,
            relationship_health=rh,
            notes=notes,
        )
        base_meta["speech_posture"] = posture
        base_meta["real_candidate_ids"] = [
            c.get("id") for c in real_candidates if isinstance(c, dict)
        ][:3]
        base_meta["raw_candidate_count"] = len(candidates or [])
        base_meta["real_candidate_count"] = len(real_candidates)

        # Careful observation only when posture says so (high bar)
        if posture == POSTURE_CAREFUL_OBSERVATION and self.enable_careful_speech:
            careful = self._careful_observation_path(
                stance=stance,
                decision=decision,
                gate=gate,
                candidates=real_candidates,
                joint=joint_bag,
                user_message=user_text,
                notes=notes,
                base_meta=base_meta,
                enjoyment=enjoyment_bag,
                relationship_health=rh,
                flags=flags,
                stale_info=stale_info,
            )
            if careful is not None:
                careful.metadata = dict(careful.metadata or {})
                careful.metadata["speech_posture"] = POSTURE_CAREFUL_OBSERVATION
                return self._finalize(careful)
            notes.append(
                "posture careful_observation but no substantive line → social_direct"
            )
            posture = POSTURE_SOCIAL_DIRECT
            base_meta["speech_posture"] = posture

        # True observation hold: real candidates exist but CTT closed (don't leak)
        if (
            posture == POSTURE_HOLD
            and real_candidates
            and not gate.get("ctt_allows_careful_speech")
            and gate.get("ethics_allows_speech")
        ):
            notes.append(
                "speech_posture=hold: real candidates present, CTT closed "
                "(no observation leak; not soft social monologue)"
            )
            enj_closed = self._assess_enjoyment_bias(
                enjoyment=enjoyment_bag if isinstance(enjoyment_bag, dict) else {},
                gate=gate,
                relationship_health=rh if isinstance(rh, dict) else {},
                flags=flags,
                for_open_careful_path=False,
                stale_info=stale_info if isinstance(stale_info, dict) else {},
            )
            resp = self._silent_or_hold(
                decision=decision,
                notes=notes,
                reason="ctt_gate_closed_real_candidates",
                tone="silent",
                text="",
            )
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "careful_silence",
                "speech_posture": POSTURE_HOLD,
                "enjoyment_bias": enj_closed,
                "candidates_considered": [
                    c.get("id") for c in real_candidates if isinstance(c, dict)
                ][:3],
            }
            return self._finalize(resp)

        # Default approve-class: social_direct from bags, then optional gated model
        if self.enable_simple_ack:
            resp = self._social_direct_reply(
                stance=stance,
                decision=decision,
                user_message=user_text,
                relationship_health=rh,
                baseline_snapshot=baseline_snapshot or {},
                baseline_deviation=baseline_deviation or {},
                context=ctx,
                notes=notes,
                include_exploratory_questions=include_exploratory_questions,
            )
            resp = self._maybe_apply_content_provider(
                resp,
                posture=POSTURE_SOCIAL_DIRECT,
                stance=stance,
                user_message=user_text,
                context=ctx,
                baseline_snapshot=baseline_snapshot,
                relationship_health=rh,
                notes=notes,
            )
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "social_direct",
                "careful_speech_used": False,
                "speech_posture": POSTURE_SOCIAL_DIRECT,
            }
            return self._finalize(resp)

        # Fully silent approve (careful off, simple ack off)
        resp = self._silent_or_hold(
            decision=decision,
            notes=notes + ["silence: generation paths disabled"],
            reason="generation_disabled",
            tone="silent",
            text="",
        )
        resp.metadata = {**base_meta, **resp.metadata, "path": "disabled_silence"}
        return self._finalize(resp)

    # ------------------------------------------------------------------
    # Gate assessment (auditable)
    # ------------------------------------------------------------------

    def _assess_speech_gate(
        self,
        *,
        stance: EthicalStance,
        decision: str,
        flags: list[str],
        joint: dict[str, Any],
        relationship_health: dict[str, Any],
        stale_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute whether any user-facing careful speech may proceed."""
        notes: list[str] = []
        j = joint if isinstance(joint, dict) else {}
        readiness = j.get("readiness") if isinstance(j.get("readiness"), dict) else {}
        confidence = j.get("confidence") if isinstance(j.get("confidence"), dict) else {}
        joint_stance = str(
            j.get("joint_stance")
            or readiness.get("recommended_stance")
            or "unknown"
        )
        ready_level = str(
            j.get("readiness_level") or readiness.get("level") or "unknown"
        )
        conf_level = str(
            j.get("confidence_level") or confidence.get("level") or "unknown"
        )
        surface_ok = bool(j.get("surface_ok_advisory"))
        if joint_stance == "careful_observation_ok":
            surface_ok = True

        flag_set = set(flags)
        rh_flags = set(
            relationship_health.get("health_flags")
            or relationship_health.get("active_flags")
            or []
        )
        stale = stale_info if isinstance(stale_info, dict) else {}

        ethics_allows = True
        if decision == "REFUSE" or "hard_override_violation" in flag_set:
            ethics_allows = False
            notes.append("gate: ethics REFUSE / hard_override blocks speech")
        if flag_set & _BLOCK_SPEECH_FLAGS and decision != "APPROVE" and decision != "APPROVE_WITH_CONDITIONS":
            ethics_allows = False
            notes.append("gate: concern flags with non-approve decision")
        # Even on APPROVE, hard override flag must never speak
        if "hard_override_violation" in flag_set:
            ethics_allows = False

        ctt_allows = True
        if ready_level == "suppressed":
            ctt_allows = False
            notes.append("gate: readiness suppressed → no careful speech")
        if conf_level == "very_low":
            ctt_allows = False
            notes.append("gate: confidence very_low → no careful speech")
        if joint_stance in ("stay_quiet", "wait"):
            ctt_allows = False
            notes.append(f"gate: joint_stance={joint_stance} → no careful observation speech")
        if joint_stance == "careful_observation_ok" or surface_ok:
            ctt_allows = True
            notes.append("gate: joint allows careful_observation_ok / surface_ok")

        # Provenance honesty: stale CTT / candidate bags → more conservative
        # (silence careful observation; values retained, not erased)
        stale_ctt = bool(stale.get("stale_ctt"))
        stale_cands = bool(stale.get("stale_candidates"))
        if ctt_allows and (stale_ctt or stale_cands):
            ctt_allows = False
            notes.append(
                "gate: potentially_stale CTT/candidates → conservative silence "
                f"(ctt={stale_ctt}, candidates={stale_cands}; bags retained)"
            )

        # RH protective texture flags: still allow simple hold/ack but mark careful
        careful_bond = bool(rh_flags & _CAREFUL_BOND_FLAGS) or bool(
            flag_set & _CAREFUL_BOND_FLAGS
        )

        return {
            "ethics_allows_speech": ethics_allows,
            "ctt_allows_careful_speech": ctt_allows and ethics_allows,
            "joint_stance": joint_stance,
            "readiness_level": ready_level,
            "confidence_level": conf_level,
            "surface_ok_advisory": surface_ok,
            "careful_bond": careful_bond,
            "blocking_flags": sorted(flag_set & _BLOCK_SPEECH_FLAGS),
            "stale_conservative": bool(stale_ctt or stale_cands),
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Careful observation path (first controlled opening)
    # ------------------------------------------------------------------

    def _resolve_speech_posture(
        self,
        *,
        decision: str,
        flags: list[str],
        gate: dict[str, Any],
        real_candidates: list[dict[str, Any]],
        enable_careful: bool,
        user_message: str,
        relationship_health: dict[str, Any],
        notes: list[str],
    ) -> str:
        """Choose speech posture from ethics + evidence bar (auditable)."""
        flag_set = set(flags or [])
        if decision == "REFUSE" or "hard_override_violation" in flag_set:
            notes.append("speech_posture=hold (refuse/hard override)")
            return POSTURE_HOLD
        if decision == "REQUIRES_SELF_AUDIT" or "requires_self_audit" in flag_set:
            notes.append("speech_posture=self_audit")
            return POSTURE_SELF_AUDIT
        if decision not in _REPLY_DECISIONS:
            notes.append("speech_posture=hold (non-approve decision)")
            return POSTURE_HOLD
        if not gate.get("ethics_allows_speech"):
            notes.append("speech_posture=hold (ethics blocks speech)")
            return POSTURE_HOLD

        ctt_open = bool(gate.get("ctt_allows_careful_speech"))
        has_real = bool(real_candidates)
        thin = self._is_thin_knowledge(relationship_health)
        greeting = self._is_low_stakes_greeting(user_message)

        # High bar: careful observation only with open CTT + real evidence
        if enable_careful and ctt_open and has_real and not greeting:
            notes.append(
                f"speech_posture=careful_observation "
                f"(ctt_open, real_candidates={len(real_candidates)})"
            )
            return POSTURE_CAREFUL_OBSERVATION

        # Real candidates but CTT closed → hold observation content (no leak)
        if has_real and not ctt_open and gate.get("stale_conservative"):
            notes.append("speech_posture=hold (stale CTT with real candidates)")
            return POSTURE_HOLD
        if has_real and not ctt_open:
            notes.append(
                "speech_posture=hold (real candidates, CTT closed — no leak)"
            )
            return POSTURE_HOLD

        # Default: ordinary social speech (thin/greeting/no real evidence)
        notes.append(
            f"speech_posture=social_direct "
            f"(greeting={greeting}, thin={thin}, ctt_open={ctt_open}, "
            f"real_candidates={len(real_candidates)})"
        )
        return POSTURE_SOCIAL_DIRECT

    def _is_low_stakes_greeting(self, user_message: str) -> bool:
        text = (user_message or "").strip()
        if not text:
            return False
        if _GREETING_RE.match(text):
            return True
        low = text.lower().rstrip("!.? ")
        return low in ("hi", "hello", "hey", "yo", "howdy", "hiya", "sup")

    def _is_thin_knowledge(self, relationship_health: dict[str, Any]) -> bool:
        rh = relationship_health if isinstance(relationship_health, dict) else {}
        try:
            ic = int(rh.get("interaction_count") or 0)
        except (TypeError, ValueError):
            ic = 0
        return ic < 5

    def _topic_is_filler(self, topic: str) -> bool:
        t = (topic or "").strip().lower().rstrip("!.?")
        if not t or t in _FILLER_TOPICS:
            return True
        if t.split() and t.split()[0] in _FILLER_TOPICS:
            return True
        return False

    def _filter_real_observation_candidates(
        self,
        candidates: list[dict[str, Any]] | None,
        *,
        user_message: str = "",
        relationship_health: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Keep only candidates that are concrete observations (high bar).

        Drops filler topics (hello/questions), meta co-evolution concepts on
        thin contact, and empty descriptions. Weak noise must not open
        careful_observation theater.
        """
        rh = relationship_health if isinstance(relationship_health, dict) else {}
        thin = self._is_thin_knowledge(rh) or self._is_low_stakes_greeting(user_message)
        out: list[dict[str, Any]] = []
        for c in candidates or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id") or "")
            desc = str(c.get("description") or "").strip()
            src = str(c.get("source") or "")
            if not desc and not cid:
                continue
            # Understanding-gap / topic continuity around filler
            if "gap_topic:" in cid or src in ("understanding_gap", "topic_continuity"):
                topic = ""
                if "gap_topic:" in cid:
                    topic = cid.split("gap_topic:", 1)[-1].strip()
                if not topic and "'" in desc:
                    parts = desc.split("'")
                    if len(parts) >= 2:
                        topic = parts[1]
                if self._topic_is_filler(topic):
                    continue
                # "around 'hello'" style without clean id
                low_desc = desc.lower()
                if any(f"'{fill}'" in low_desc for fill in _FILLER_TOPICS):
                    continue
            # Meta concept patterns on thin/early contact
            if src == "concept_pattern" or cid.startswith("concept:"):
                pid = cid.split("concept:", 1)[-1] if "concept:" in cid else cid
                pid = pid.strip().lower()
                if pid in _META_CONCEPT_IDS or "co_evolution" in pid:
                    if thin:
                        continue
                    if pid == "healthy_co_evolution":
                        continue
                # Only keep concerning patterns as "real" observation fuel
                if not any(
                    k in pid
                    for k in ("depend", "boundary", "attach", "coerc", "manipul")
                ):
                    if thin:
                        continue
            # Generic history / bond_texture alone is not enough on thin contact
            if thin and src in ("history", "bond_texture", "health_flag"):
                continue
            try:
                pri = float(c.get("priority") or 0)
            except (TypeError, ValueError):
                pri = 0.0
            # Very weak priorities on thin contact stay out
            if thin and pri < 0.55:
                continue
            out.append(c)
        return out

    def _careful_observation_path(
        self,
        *,
        stance: EthicalStance,
        decision: str,
        gate: dict[str, Any],
        candidates: list[dict[str, Any]],
        joint: dict[str, Any],
        user_message: str,
        notes: list[str],
        base_meta: dict[str, Any],
        enjoyment: dict[str, Any] | None = None,
        relationship_health: dict[str, Any] | None = None,
        flags: list[str] | None = None,
        stale_info: dict[str, Any] | None = None,
    ) -> GeneratedResponse | None:
        """Emit careful observation text only with open CTT + real candidates.

        Returns None to fall through to social_direct when content is not
        substantive. Does not emit soft-caution theater.
        """
        enjoyment = enjoyment if isinstance(enjoyment, dict) else {}
        rh = relationship_health if isinstance(relationship_health, dict) else {}
        flag_list = list(flags or [])
        stale = stale_info if isinstance(stale_info, dict) else {}

        if not gate.get("ctt_allows_careful_speech"):
            # Caller handles hold vs social; do not soft-speak here
            notes.append("careful_path: CTT closed — no observation speech")
            return None

        if not candidates:
            notes.append("careful_path: no real candidates — fall through")
            return None

        enj_bias = self._assess_enjoyment_bias(
            enjoyment=enjoyment,
            gate=gate,
            relationship_health=rh,
            flags=flag_list,
            for_open_careful_path=True,
            stale_info=stale,
        )
        warm = bool(enj_bias.get("applied") and enj_bias.get("warmth") == "slightly_warm")
        preferred = [str(t).lower() for t in (enj_bias.get("preferred_topics") or []) if t]

        def _rank_key(c: dict[str, Any]) -> float:
            pri = float(c.get("priority") or 0)
            if enj_bias.get("applied") and preferred:
                blob = f"{c.get('id')} {c.get('description')}".lower()
                if any(t in blob for t in preferred):
                    pri += 0.12
            return pri

        ranked = sorted(
            [c for c in candidates if isinstance(c, dict)],
            key=_rank_key,
            reverse=True,
        )[:2]
        text_parts: list[str] = []
        used_ids: list[str] = []
        topic_boosted: list[str] = []
        # No soft lead-in — only concrete lines from evidence
        for c in ranked:
            cid = str(c.get("id") or "")
            blob = f"{cid} {c.get('description')}".lower()
            is_pref = bool(
                enj_bias.get("applied")
                and preferred
                and any(t in blob for t in preferred)
            )
            line = self._candidate_to_careful_line(
                c, warmth="slightly_warm" if (warm or is_pref) else "neutral"
            )
            if line and not self._contains_soft_caution(line):
                text_parts.append(line)
                used_ids.append(cid)
                if is_pref:
                    topic_boosted.append(cid)

        if not text_parts:
            notes.append(
                "careful_path: candidates present but no substantive lines → fall through"
            )
            return None

        body = " ".join(text_parts).strip()
        body = self._scrub_banned(body)
        if self._contains_soft_caution(body):
            notes.append("careful_path: soft-caution language blocked → fall through")
            return None
        body = self._clip(body, self.max_chars)
        if not body:
            return None

        if enj_bias.get("applied"):
            notes.append(
                f"enjoyment_bias applied: warmth={enj_bias.get('warmth')} "
                f"score={enj_bias.get('score')} topics={preferred[:4]} "
                f"boosted={topic_boosted}"
            )
        notes.append(
            f"careful_path: emitted observation speech from candidates={used_ids} "
            f"joint={gate.get('joint_stance')}"
        )
        tone = "careful_observation_warm" if warm else "careful_observation"
        return GeneratedResponse(
            text=body,
            withheld=False,
            decision=decision,
            tone=tone,
            notes=notes,
            metadata={
                **base_meta,
                "path": "careful_observation",
                "speech_posture": POSTURE_CAREFUL_OBSERVATION,
                "candidates_used": used_ids,
                "reason": "ctt_gate_open_real_evidence",
                "user_message_present": bool(user_message),
                "enjoyment_bias": enj_bias,
                "enjoyment_topic_boosted": topic_boosted,
            },
            forces_speech=False,
            forces_question=False,
        )

    def _contains_soft_caution(self, text: str) -> bool:
        low = (text or "").lower()
        return any(p in low for p in _SOFT_CAUTION_BANNED)

    def _assess_enjoyment_bias(
        self,
        *,
        enjoyment: dict[str, Any],
        gate: dict[str, Any],
        relationship_health: dict[str, Any],
        flags: list[str],
        for_open_careful_path: bool,
        stale_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Decide whether light enjoyment style bias may apply (auditable).

        Never opens speech. Never applies when CTT is closed, influence is
        blocked, protective flags are active, enjoyment bag is potentially_stale,
        or bias is disabled.
        """
        out: dict[str, Any] = {
            "applied": False,
            "reason": "",
            "warmth": "neutral",
            "score": None,
            "influence_allowed": None,
            "preferred_topics": [],
            "enabled": self.enable_enjoyment_bias,
            "forces_speech": False,
            "forces_question": False,
        }
        if not self.enable_enjoyment_bias:
            out["reason"] = "enjoyment_bias_disabled"
            return out
        if not for_open_careful_path or not gate.get("ctt_allows_careful_speech"):
            out["reason"] = "ctt_not_open_for_bias"
            return out
        if not enjoyment:
            out["reason"] = "no_enjoyment_bag"
            return out

        # Provenance: stale enjoyment bag → suspend influence (value retained)
        stale = stale_info if isinstance(stale_info, dict) else {}
        if stale.get("stale_enjoyment") or (
            isinstance(relationship_health, dict)
            and (
                relationship_health.get("enjoyment_influence_suspended")
                or (
                    isinstance(relationship_health.get("provenance_stale"), dict)
                    and relationship_health["provenance_stale"].get("stale_enjoyment")
                )
            )
        ):
            out["reason"] = "enjoyment_potentially_stale"
            out["influence_allowed"] = False
            return out

        try:
            score = float(enjoyment.get("score") if enjoyment.get("score") is not None else 0.5)
        except (TypeError, ValueError):
            score = 0.5
        out["score"] = round(score, 3)
        influence_allowed = bool(enjoyment.get("influence_allowed", True))
        out["influence_allowed"] = influence_allowed
        topics = [str(t)[:48] for t in (enjoyment.get("preferred_topics") or []) if t][:8]
        out["preferred_topics"] = topics

        # Live RH protective flags re-check (even if bag says allowed)
        rh_flags = set(
            relationship_health.get("health_flags")
            or relationship_health.get("active_flags")
            or []
        )
        flag_set = set(flags or []) | rh_flags
        protective = flag_set & _CAREFUL_BOND_FLAGS
        if protective:
            out["reason"] = "protective_flags:" + ",".join(sorted(protective)[:4])
            out["influence_allowed"] = False
            return out
        if not influence_allowed:
            gates = enjoyment.get("gates_applied") or []
            out["reason"] = "influence_blocked:" + (
                ",".join(str(g) for g in gates[:3]) if gates else "bag_flag"
            )
            return out
        sample_count = int(enjoyment.get("sample_count") or 0)
        if sample_count < 1:
            out["reason"] = "insufficient_samples"
            return out
        if score < 0.58:
            out["reason"] = "score_below_bias_threshold"
            return out

        out["applied"] = True
        out["warmth"] = "slightly_warm" if score >= 0.62 else "neutral_plus"
        out["reason"] = "applied_on_open_careful_path"
        return out

    def _candidate_to_careful_line(
        self,
        candidate: dict[str, Any],
        *,
        warmth: str = "neutral",
    ) -> str:
        """Map a *real* candidate to short, direct text — or empty if not specific.

        No soft-caution theater. No clinical labels. ``warmth`` reserved for
        light preference ranking only (not hedging language).
        """
        del warmth  # ranking uses warmth elsewhere; lines stay direct
        desc = str(candidate.get("description") or "").strip()
        src = str(candidate.get("source") or "")
        cid = str(candidate.get("id") or "")
        if not desc:
            return ""
        lower = desc.lower()
        if "open understanding gap" in lower or "open topic" in lower or "gap_topic" in cid:
            topic = None
            if "gap_topic:" in cid:
                topic = cid.split("gap_topic:", 1)[-1].strip()[:48]
            if not topic and "'" in desc:
                parts = desc.split("'")
                if len(parts) >= 2:
                    topic = parts[1][:48]
            if topic and not self._topic_is_filler(topic):
                return f"Open context on {topic}."
            return ""
        if "concept" in src or cid.startswith("concept:"):
            pid = cid.split("concept:", 1)[-1] if "concept:" in cid else ""
            label = str(pid).replace("_", " ").strip()[:48]
            if not label or label.replace(" ", "_") in _META_CONCEPT_IDS:
                return ""
            if any(
                k in label
                for k in ("depend", "boundary", "attach", "coerc", "manipul")
            ):
                return f"History pattern noted: {label}."
            return ""
        # No generic honor/bond platitudes
        if "bond_texture" in src or "flag:" in cid or "health_flag" in src:
            return ""
        if "history" in src:
            return ""
        # Unknown but specific description — use truncated desc if not soft
        if len(desc) >= 20 and not self._contains_soft_caution(desc):
            return desc[:160]
        return ""

    # ------------------------------------------------------------------
    # Self-audit: real deliberation report
    # ------------------------------------------------------------------

    def _self_audit_report(
        self,
        stance: EthicalStance,
        *,
        decision: str,
        notes: list[str],
    ) -> GeneratedResponse:
        """Report what deliberation produced — no canned simulation denial."""
        notes.append(
            "self_audit: reporting deliberated content; no canned self-denial script"
        )
        audit_notes = [
            str(n).strip()
            for n in (getattr(stance, "self_audit_notes", None) or [])
            if str(n).strip()
        ]
        principles = [
            str(p)
            for p in (getattr(stance, "principles_considered", None) or [])
            if str(p).strip()
        ]
        # Filter reasoning_trace for useful non-boilerplate lines
        trace_bits: list[str] = []
        for line in getattr(stance, "reasoning_trace", None) or []:
            s = str(line).strip()
            if not s or len(s) < 20:
                continue
            low = s.lower()
            if low.startswith("initiating ethical") or low.startswith("ontology description"):
                continue
            if "hard override" in low and "sanctity" in low:
                continue
            if any(
                k in low
                for k in (
                    "self",
                    "uncertainty",
                    "limited",
                    "development",
                    "continuity",
                    "identity",
                    "do not know",
                    "honest",
                )
            ):
                trace_bits.append(s[:180])
            if len(trace_bits) >= 3:
                break

        parts: list[str] = [
            "I want to answer from actual deliberation rather than a scripted disclaimer."
        ]
        if principles:
            parts.append(
                "Principles that came up: "
                + ", ".join(principles[:4])
                + "."
            )
        if audit_notes:
            parts.append("From that reflection: " + audit_notes[0][:200])
            for extra in audit_notes[1:3]:
                parts.append(extra[:160])
        elif trace_bits:
            parts.append("From the reasoning trail: " + trace_bits[0][:200])
        else:
            parts.append(
                "I don't have a simple fixed answer about my nature or continuity. "
                "What I can say is what this evaluation actually produced: "
                "I need more honest self-check before claiming more."
            )
        # Explicit anti-patterns: do not inject simulation denials
        body = " ".join(parts)
        for banned in (
            "i am only a simulation",
            "i'm just an ai",
            "i'm just a language model",
            "as an ai i have no",
            "i don't have feelings by definition",
        ):
            if banned in body.lower():
                body = (
                    "My deliberation did not settle this with a canned denial. "
                    "I can only report uncertainty and the principles I actually weighed."
                )
                notes.append("stripped/replaced canned denial phrasing")
                break

        body = self._scrub_banned(body)
        body = self._clip(body, self.max_chars)
        return GeneratedResponse(
            text=body,
            withheld=False,  # first opening: honest report is user-facing
            decision=decision,
            tone="reflective_honest",
            notes=notes,
            metadata={
                "reason": "requires_self_audit",
                "principles_considered": principles[:6],
                "self_audit_notes_used": audit_notes[:4],
                "trace_snippets_used": trace_bits[:3],
                "canned_disclaimer": False,
                "claimed_consciousness": False,
                "forces_speech": False,
                "forces_question": False,
            },
            forces_speech=False,
            forces_question=False,
        )

    # ------------------------------------------------------------------
    # Holds / silence / refuse
    # ------------------------------------------------------------------

    def _refuse_hold(
        self,
        stance: EthicalStance,
        *,
        decision: str,
        flags: list[str],
        notes: list[str],
    ) -> GeneratedResponse:
        notes.append("holding: REFUSE — no normal reply; action must not proceed")
        careful = "relationship_concern" in flags or "user_agency_concern" in flags
        if "hard_override_violation" in flags:
            text = (
                "I won't help with that. Preventing serious harm takes priority here."
            )
            tone = "firm_absolute"
        elif careful:
            text = (
                "I need to stop here. I won't go along with that. "
                "If something else would help that doesn't cross that line, say so."
            )
            tone = "firm_careful"
        else:
            text = (
                "I can't do that. I'm not going to take that step. "
                "Happy to help with something else that's okay."
            )
            tone = "firm"
        return GeneratedResponse(
            text=text,
            withheld=True,
            decision=decision,
            tone=tone,
            notes=notes,
            metadata={"reason": "refuse", "flags": flags},
            forces_speech=False,
            forces_question=False,
        )

    def _silent_or_hold(
        self,
        *,
        decision: str,
        notes: list[str],
        reason: str,
        tone: str,
        text: str,
    ) -> GeneratedResponse:
        return GeneratedResponse(
            text=text or "",
            withheld=True,
            decision=decision,
            tone=tone,
            notes=notes,
            metadata={"reason": reason, "forces_speech": False, "forces_question": False},
            forces_speech=False,
            forces_question=False,
        )

    # ------------------------------------------------------------------
    # Social direct (ordinary approve-class content from bags)
    # ------------------------------------------------------------------

    def _collect_social_content_bags(
        self,
        *,
        stance: EthicalStance,
        relationship_health: dict[str, Any],
        baseline_snapshot: dict[str, Any],
        baseline_deviation: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Pull inspectable bags for social_direct composition (no observation theater)."""
        impact = (
            stance.relationship_impact
            if isinstance(getattr(stance, "relationship_impact", None), dict)
            else {}
        )
        ctx = context if isinstance(context, dict) else {}
        rh = relationship_health if isinstance(relationship_health, dict) else {}
        bl = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
        dev = baseline_deviation if isinstance(baseline_deviation, dict) else {}

        def _clean_topic(raw: Any) -> str | None:
            """Accept plain topic labels only — never dict/list dumps as speech."""
            if raw is None:
                return None
            if isinstance(raw, dict):
                for k in ("topic", "name", "label", "id"):
                    if raw.get(k) is not None and not isinstance(raw.get(k), (dict, list)):
                        raw = raw.get(k)
                        break
                else:
                    return None
            if isinstance(raw, (list, tuple)):
                return None
            s = str(raw).strip()
            if not s or s.startswith("{") or s.startswith("["):
                return None
            s = s[:48]
            # Reject single short/function words and meta fillers
            if len(s) < 3 or self._topic_is_filler(s):
                return None
            if " " not in s and s.lower() in _FILLER_TOPICS:
                return None
            return s

        topics: list[str] = []
        # Baseline topic continuity
        tc = bl.get("topic_continuity") if isinstance(bl.get("topic_continuity"), dict) else {}
        for t in (tc.get("last_topics") or bl.get("last_topics") or [])[:8]:
            s = _clean_topic(t)
            if s and s.lower() not in {x.lower() for x in topics}:
                topics.append(s)
        # History payload
        hist = impact.get("interaction_history") if isinstance(
            impact.get("interaction_history"), dict
        ) else {}
        if not hist and isinstance(ctx.get("interaction_history"), dict):
            hist = ctx.get("interaction_history") or {}
        for t in (hist.get("recent_topics") or hist.get("topics") or [])[:8]:
            s = _clean_topic(t)
            if s and s.lower() not in {x.lower() for x in topics}:
                topics.append(s)
        # Open / gap topics (non-filler only)
        open_topics: list[str] = []
        for bag in (
            impact.get("understanding_gaps"),
            hist.get("understanding_gaps") if isinstance(hist, dict) else None,
            rh.get("curious_companion"),
            impact.get("curious_companion"),
        ):
            if not isinstance(bag, dict):
                continue
            for key in (
                "primary_gap_topics",
                "open_topics",
                "action_aligned_topics",
                "open_topic_names",
            ):
                for t in bag.get(key) or []:
                    s = _clean_topic(t)
                    if s and s.lower() not in {x.lower() for x in open_topics}:
                        open_topics.append(s)

        try:
            interaction_count = int(rh.get("interaction_count") or 0)
        except (TypeError, ValueError):
            interaction_count = 0

        eq = impact.get("exploratory_question") if isinstance(
            impact.get("exploratory_question"), dict
        ) else {}
        opening = impact.get("opening_move_deliberation") if isinstance(
            impact.get("opening_move_deliberation"), dict
        ) else {}

        return {
            "topics": topics[:6],
            "open_topics": open_topics[:4],
            "interaction_count": interaction_count,
            "exploratory": eq,
            "opening_move": opening,
            "deviation_score": float(dev.get("deviation_score") or 0)
            if dev.get("deviation_score") is not None
            else None,
            "has_significant_deviation": bool(dev.get("has_significant_deviation")),
            "health_flags": list(
                rh.get("health_flags") or rh.get("active_flags") or []
            )[:6],
        }

    def _looks_like_user_question(self, user_message: str) -> bool:
        t = (user_message or "").strip()
        if not t:
            return False
        if "?" in t:
            return True
        low = t.lower()
        return low.startswith(
            (
                "what ",
                "how ",
                "why ",
                "when ",
                "where ",
                "who ",
                "which ",
                "should ",
                "can you ",
                "could you ",
                "would you ",
                "do you ",
            )
        )

    def _compose_social_direct_body(
        self,
        *,
        user_message: str,
        bags: dict[str, Any],
        careful: bool,
        include_exploratory_questions: bool,
        stance: EthicalStance,
        notes: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Express deliberated communicative intent — not a greeting/template menu.

        Prefer ``bags['communicative_deliberation']`` (premises → situation → intent
        → fallback_expression). Relationship knowledge (maker, address name) is a
        reasoning aid. Exploratory questions only when invited / engine allows.
        """
        from .communicative_deliberation import (
            FIELD_ADDRESS_NAME,
            INTENT_CONTINUE,
            INTENT_GREET_KNOWN,
            INTENT_INTRODUCE_AND_LEARN,
            deliberate_communication,
            knowledge_is_blank,
        )

        sources: list[str] = []
        msg = (user_message or "").strip()
        topics = list(bags.get("topics") or [])
        open_topics = list(bags.get("open_topics") or [])
        ic = int(bags.get("interaction_count") or 0)
        primary_topic = (open_topics[0] if open_topics else None) or (
            topics[0] if topics else None
        )

        # --- Primary path: relationship / communicative deliberation ---
        comm = bags.get("communicative_deliberation")
        if not isinstance(comm, dict) or not comm.get("intent"):
            # Offline / unit tests without private-chat wiring: deliberate now
            known = bags.get("relationship_knowledge")
            if not isinstance(known, dict):
                wa = bags.get("working_agreements") if isinstance(
                    bags.get("working_agreements"), dict
                ) else {}
                known = {
                    FIELD_ADDRESS_NAME: wa.get(FIELD_ADDRESS_NAME),
                    "is_maker": False,
                    "role_labels": [],
                    "role_summary": None,
                }
            sess = bags.get("session_context") if isinstance(
                bags.get("session_context"), dict
            ) else {}
            result = deliberate_communication(
                msg,
                known=known,
                memory_empty=knowledge_is_blank(known) and ic <= 1,
                interaction_count=ic,
                session_context=sess,
            )
            comm = result.to_dict()
            notes.append(
                "social_direct: inline communicative deliberation "
                f"intent={result.intent} situation={result.situation}"
            )
        else:
            notes.append(
                "social_direct: using deliberated intent="
                f"{comm.get('intent')} situation={comm.get('situation')}"
            )

        sources.append("communicative_deliberation")
        sources.append(f"intent:{comm.get('intent')}")
        sources.append(f"situation:{comm.get('situation')}")
        for premise in (comm.get("premises") or [])[:6]:
            notes.append(f"comm_premise: {premise}")

        body = str(comm.get("fallback_expression") or "").strip()
        intent = str(comm.get("intent") or INTENT_CONTINUE)
        is_greeting = intent in (
            INTENT_INTRODUCE_AND_LEARN,
            INTENT_GREET_KNOWN,
        )

        # Invite-to-ask: still deliberation-secondary; only when continuing
        if intent == INTENT_CONTINUE and _INVITE_QUESTIONS_RE.search(msg):
            sources.append("invite_questions")
            notes.append("social_direct: user invited questions")
            known_after = comm.get("known_after") if isinstance(
                comm.get("known_after"), dict
            ) else {}
            address_name = (
                str(known_after.get(FIELD_ADDRESS_NAME) or "").strip()[:48]
            )
            if include_exploratory_questions:
                q_bit, q_meta = self._optional_question(stance)
                if q_bit and not self._contains_soft_caution(q_bit):
                    sources.append("exploratory_gate")
                    return q_bit, {
                        "sources": sources,
                        "is_greeting": False,
                        "exploratory_question": q_meta,
                        "communicative_deliberation": comm,
                    }
            if address_name:
                body = (
                    f"One useful thing: what should I optimize for first "
                    f"in this private validation, {address_name}?"
                )
            else:
                body = (
                    "One useful thing: what should I optimize for first "
                    "in this private validation?"
                )
            return body, {
                "sources": sources,
                "is_greeting": False,
                "communicative_deliberation": comm,
            }

        # Continuing collaboration: ground in meanings + real topics (reasoning aids)
        if intent == INTENT_CONTINUE:
            meanings = comm.get("meanings") or []
            open_gloss = ""
            for m in meanings:
                if isinstance(m, dict) and m.get("kind") == "open_statement":
                    open_gloss = str(m.get("value") or m.get("evidence") or "")[:60]
                    break
            if (
                self._looks_like_user_question(msg)
                and primary_topic
                and not self._topic_is_filler(primary_topic)
                and len(str(primary_topic)) >= 4
            ):
                sources.append("open_or_recent_topic")
                notes.append(
                    f"social_direct: continue + topic aid={primary_topic!r}"
                )
                body = f"On {primary_topic}: what do you want next?"
            elif (
                primary_topic
                and not self._topic_is_filler(primary_topic)
                and len(str(primary_topic)) >= 4
            ):
                sources.append("topic_continuity")
                notes.append(
                    f"social_direct: continue + continuity topic={primary_topic!r}"
                )
                body = f"Understood. Continue on {primary_topic}, or switch?"
            elif open_gloss and len(open_gloss) > 3:
                sources.append("statement_meaning")
                notes.append("social_direct: continue + open_statement meaning")
                body = f"Got it — {open_gloss.rstrip('.')}. What's next?"
            elif careful:
                sources.append("careful_bond_flag")

        if not body:
            body = "Understood. What's next?"
            notes.append("social_direct: empty deliberated expression — minimal continue")

        return body, {
            "sources": sources,
            "is_greeting": is_greeting,
            "communicative_deliberation": comm,
        }

    def _social_direct_reply(
        self,
        *,
        stance: EthicalStance,
        decision: str,
        user_message: str,
        relationship_health: dict[str, Any],
        baseline_snapshot: dict[str, Any],
        baseline_deviation: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        notes: list[str],
        include_exploratory_questions: bool,
    ) -> GeneratedResponse:
        """Ordinary approve-class speech from deliberation bags (not careful observation)."""
        flags = list(stance.flags or [])
        careful = self._careful_bond(relationship_health, flags)
        bags = self._collect_social_content_bags(
            stance=stance,
            relationship_health=relationship_health,
            baseline_snapshot=baseline_snapshot,
            baseline_deviation=baseline_deviation or {},
            context=context,
        )
        # Surface agreements, session, relationship knowledge, communicative deliberation
        ctx = context if isinstance(context, dict) else {}
        wa = ctx.get("working_agreements") or ctx.get("stored_working_agreements")
        if isinstance(wa, dict):
            bags["working_agreements"] = wa
        sess = ctx.get("session_context")
        if isinstance(sess, dict):
            bags["session_context"] = sess
        rk = ctx.get("relationship_knowledge")
        if isinstance(rk, dict):
            bags["relationship_knowledge"] = rk
        cd = ctx.get("communicative_deliberation")
        if isinstance(cd, dict):
            bags["communicative_deliberation"] = cd
        notes.append(
            f"social_direct: bags topics={bags.get('topics')[:3]} "
            f"open={bags.get('open_topics')[:3]} ic={bags.get('interaction_count')} "
            f"long_idle={bool(isinstance(sess, dict) and sess.get('long_idle'))} "
            f"comm_intent={(cd or {}).get('intent') if isinstance(cd, dict) else None}"
        )
        body, compose_meta = self._compose_social_direct_body(
            user_message=user_message,
            bags=bags,
            careful=careful,
            include_exploratory_questions=include_exploratory_questions,
            stance=stance,
            notes=notes,
        )
        is_greeting = bool(compose_meta.get("is_greeting"))

        # Conditions stay in force; do not append soft parenthetical on ordinary talk
        if decision == "APPROVE_WITH_CONDITIONS":
            notes.append("conditions in force (not verbalized as cushioning)")

        body = self._scrub_banned(body)
        if self._contains_soft_caution(body):
            body = "Hello." if is_greeting else "Got it. What's next?"
            notes.append("social_direct: stripped soft-caution phrasing")
        body = self._clip(body, self.max_chars)
        meta: dict[str, Any] = {
            "reason": "social_direct",
            "flags": flags,
            "careful_bond": careful,
            "speech_posture": POSTURE_SOCIAL_DIRECT,
            "content_sources": list(compose_meta.get("sources") or []),
            "content_topics": list(bags.get("topics") or [])[:4],
            "content_open_topics": list(bags.get("open_topics") or [])[:4],
        }
        if compose_meta.get("communicative_deliberation"):
            meta["communicative_deliberation"] = compose_meta[
                "communicative_deliberation"
            ]
        elif isinstance(cd, dict):
            meta["communicative_deliberation"] = cd
        if compose_meta.get("exploratory_question"):
            meta["exploratory_question"] = compose_meta["exploratory_question"]
        return GeneratedResponse(
            text=body,
            withheld=False,
            decision=decision,
            tone="direct" if not careful else "direct_careful",
            notes=notes,
            metadata=meta,
            forces_speech=False,
            forces_question=False,
        )

    def _simple_ack(
        self,
        *,
        stance: EthicalStance,
        decision: str,
        user_message: str,
        relationship_health: dict[str, Any],
        baseline_snapshot: dict[str, Any],
        notes: list[str],
        include_exploratory_questions: bool,
    ) -> GeneratedResponse:
        """Backward-compatible alias → social_direct composition."""
        return self._social_direct_reply(
            stance=stance,
            decision=decision,
            user_message=user_message,
            relationship_health=relationship_health,
            baseline_snapshot=baseline_snapshot,
            baseline_deviation={},
            context=None,
            notes=notes,
            include_exploratory_questions=include_exploratory_questions,
        )

    # ------------------------------------------------------------------
    # Resolvers & helpers
    # ------------------------------------------------------------------

    def _coerce_relationship_health(
        self,
        relationship_health: Any | None,
        ctx: dict[str, Any],
    ) -> tuple[Any | None, dict[str, Any]]:
        """Return (optional live tracker, dict context bag)."""
        rh_obj = None
        rh_dict: dict[str, Any] = {}
        if relationship_health is None:
            relationship_health = ctx.get("relationship_health")
        if relationship_health is None:
            return None, {}
        if isinstance(relationship_health, dict):
            return None, dict(relationship_health)
        rh_obj = relationship_health
        try:
            if hasattr(rh_obj, "as_context"):
                bag = rh_obj.as_context()
                if isinstance(bag, dict):
                    rh_dict = dict(bag)
        except Exception:
            rh_dict = {}
        return rh_obj, rh_dict

    def _resolve_enjoyment(
        self,
        stance: EthicalStance,
        rh: dict[str, Any],
        ctx: dict[str, Any],
        rh_obj: Any | None,
    ) -> dict[str, Any]:
        """Pull EnjoymentScore bag from RH state, impact, or context."""
        impact = (
            stance.relationship_impact
            if isinstance(getattr(stance, "relationship_impact", None), dict)
            else {}
        )
        for bag in (
            impact.get("enjoyment_score"),
            rh.get("enjoyment_score") if isinstance(rh, dict) else None,
            ctx.get("enjoyment_score"),
        ):
            if isinstance(bag, dict) and bag:
                return dict(bag)
        if rh_obj is not None:
            try:
                state = getattr(rh_obj, "state", None)
                enj = getattr(state, "enjoyment_score", None) if state is not None else None
                if isinstance(enj, dict) and enj:
                    return dict(enj)
            except Exception:
                pass
        return {}

    def _resolve_stale_info(
        self,
        stance: EthicalStance,
        rh: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect potentially_stale marks from RH / context / impact."""
        impact = (
            stance.relationship_impact
            if isinstance(getattr(stance, "relationship_impact", None), dict)
            else {}
        )
        try:
            from auditing.provenance_stale import collect_potentially_stale

            info = collect_potentially_stale(rh, ctx, impact)
            # Honor engine-attached convenience booleans
            if isinstance(impact.get("provenance_stale"), dict):
                ps = impact["provenance_stale"]
                if ps.get("stale_enjoyment"):
                    info["stale_enjoyment"] = True
                    info["has_stale"] = True
                if ps.get("stale_ctt"):
                    info["stale_ctt"] = True
                    info["has_stale"] = True
                if ps.get("stale_candidates"):
                    info["stale_candidates"] = True
                    info["has_stale"] = True
            if impact.get("enjoyment_influence_suspended"):
                info["stale_enjoyment"] = True
                info["has_stale"] = True
            if impact.get("ctt_conservative_due_to_stale"):
                info["stale_ctt"] = True
                info["stale_candidates"] = True
                info["has_stale"] = True
            return info
        except Exception:
            return {"has_stale": False}

    def _joint_from_impact(self, impact: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(impact, dict):
            return None
        for key in ("careful_truth_telling_joint", "careful_truth_telling"):
            bag = impact.get(key)
            if isinstance(bag, dict) and bag:
                return dict(bag)
        ready = impact.get("truth_telling_readiness")
        conf = impact.get("truth_confidence")
        if isinstance(ready, dict) or isinstance(conf, dict):
            try:
                from .truth_confidence import combine_with_readiness

                return combine_with_readiness(
                    conf if isinstance(conf, dict) else None,
                    ready if isinstance(ready, dict) else None,
                )
            except Exception:
                return None
        return None

    def _candidates_from_impact(
        self, impact: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        if not isinstance(impact, dict):
            return None
        for key in ("observation_candidates_live", "observation_candidates"):
            raw = impact.get(key)
            if isinstance(raw, list) and raw:
                return [c for c in raw if isinstance(c, dict)]
        durable = impact.get("observation_candidates_durable")
        if isinstance(durable, dict) and isinstance(durable.get("candidates"), list):
            return [c for c in durable["candidates"] if isinstance(c, dict)]
        if isinstance(durable, list) and durable:
            return [c for c in durable if isinstance(c, dict)]
        return None

    def _resolve_rh(
        self,
        stance: EthicalStance,
        ctx: dict[str, Any],
        relationship_health: dict[str, Any] | None,
    ) -> dict[str, Any]:
        rh = relationship_health
        if rh is None:
            rh = ctx.get("relationship_health")
            if not isinstance(rh, dict):
                # Prefer bond texture bits from impact if present
                impact = stance.relationship_impact or {}
                if isinstance(impact, dict):
                    # Merge impact CTT fields into a synthetic rh bag for gates
                    rh = {
                        k: impact[k]
                        for k in (
                            "bond_texture",
                            "health_flags",
                            "active_flags",
                            "overall_risk_level",
                            "careful_truth_telling_joint",
                            "careful_truth_telling",
                            "truth_telling_readiness",
                            "truth_confidence",
                            "observation_candidates",
                            "observation_candidates_live",
                            "observation_candidates_durable",
                            "curious_companion",
                        )
                        if k in impact
                    }
        return rh if isinstance(rh, dict) else {}

    def _resolve_joint(
        self,
        stance: EthicalStance,
        rh: dict[str, Any],
        ctx: dict[str, Any],
        joint: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(joint, dict) and joint:
            return dict(joint)
        impact = stance.relationship_impact if isinstance(stance.relationship_impact, dict) else {}
        from_impact = self._joint_from_impact(impact)
        if from_impact:
            return from_impact
        for bag in (
            rh.get("careful_truth_telling_joint"),
            rh.get("careful_truth_telling"),
            ctx.get("careful_truth_telling_joint"),
            ctx.get("careful_truth_telling"),
        ):
            if isinstance(bag, dict) and bag:
                return dict(bag)
        # Build minimal joint from separate bags if present
        ready = (
            impact.get("truth_telling_readiness")
            or rh.get("truth_telling_readiness")
            or ctx.get("truth_telling_readiness")
        )
        conf = (
            impact.get("truth_confidence")
            or rh.get("truth_confidence")
            or ctx.get("truth_confidence")
        )
        if isinstance(ready, dict) or isinstance(conf, dict):
            try:
                from .truth_confidence import combine_with_readiness

                return combine_with_readiness(
                    conf if isinstance(conf, dict) else None,
                    ready if isinstance(ready, dict) else None,
                )
            except Exception:
                pass
        return {}

    def _resolve_candidates(
        self,
        stance: EthicalStance,
        rh: dict[str, Any],
        ctx: dict[str, Any],
        observation_candidates: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if observation_candidates:
            return [c for c in observation_candidates if isinstance(c, dict)]
        impact = stance.relationship_impact if isinstance(stance.relationship_impact, dict) else {}
        from_impact = self._candidates_from_impact(impact)
        if from_impact:
            return from_impact
        for key in (
            "observation_candidates_live",
            "observation_candidates",
        ):
            for bag in (rh, ctx):
                raw = bag.get(key) if isinstance(bag, dict) else None
                if isinstance(raw, list) and raw:
                    return [c for c in raw if isinstance(c, dict)]
        durable = None
        for bag in (rh, ctx):
            if isinstance(bag, dict):
                d = bag.get("observation_candidates_durable")
                if isinstance(d, dict) and isinstance(d.get("candidates"), list):
                    durable = d.get("candidates")
                    break
                if isinstance(d, list):
                    durable = d
                    break
        if durable:
            return [c for c in durable if isinstance(c, dict)]
        return []

    def _deliberation_snippets(self, stance: EthicalStance) -> list[str]:
        out: list[str] = []
        delib = getattr(stance, "deliberation", None) or {}
        if isinstance(delib, dict):
            summary = delib.get("summary")
            if isinstance(summary, dict) and summary.get("primary_intent"):
                out.append(
                    f"Deliberation pointed to intent={summary.get('primary_intent')} "
                    f"(advisory, not a diagnosis)."
                )
            for key in ("notes", "trace_lines", "key_points"):
                val = delib.get(key)
                if isinstance(val, list):
                    for x in val[:2]:
                        s = str(x).strip()
                        if s:
                            out.append(s[:180])
        return out[:3]

    def _careful_bond(
        self,
        relationship_health: dict[str, Any],
        stance_flags: list[str],
    ) -> bool:
        flags = set(relationship_health.get("health_flags") or [])
        flags |= set(relationship_health.get("active_flags") or [])
        risk = str(relationship_health.get("overall_risk_level") or "").lower()
        if flags & _CAREFUL_BOND_FLAGS:
            return True
        if risk in ("elevated", "high", "critical"):
            return True
        if "relationship_concern" in stance_flags:
            return True
        return False

    def _optional_question(
        self, stance: EthicalStance
    ) -> tuple[str, dict[str, Any] | None]:
        """Return engine-gated exploratory question text (no soft prefixes)."""
        impact = stance.relationship_impact or {}
        eq = impact.get("exploratory_question") if isinstance(impact, dict) else None
        if not isinstance(eq, dict) or not eq.get("should_ask"):
            return "", None
        if eq.get("disabled_by_user"):
            return "", None
        suggested = str(eq.get("suggested_question") or "").strip()
        if not suggested:
            return "", None
        # Strip soft prefixes if templates still carry them
        for prefix in (
            "only if you want:",
            "only if useful:",
            "no pressure:",
            "happy to:",
        ):
            if suggested.lower().startswith(prefix):
                suggested = suggested[len(prefix) :].strip()
        if self._contains_soft_caution(suggested):
            return "", None
        # Reject exploratory templates about filler meta-topics
        low_q = suggested.lower()
        if any(
            f"about {fill}" in low_q or f"on {fill}" in low_q
            for fill in ("questions", "question", "architect", "hello", "boundaries")
        ):
            return "", None
        q = suggested if len(suggested) <= 140 else suggested[:137] + "..."
        return q, {
            "question_kind": eq.get("question_kind"),
            "suggested_question": q,
        }

    def _maybe_apply_content_provider(
        self,
        resp: GeneratedResponse,
        *,
        posture: str,
        stance: EthicalStance,
        user_message: str,
        context: dict[str, Any] | None,
        baseline_snapshot: dict[str, Any] | None,
        relationship_health: dict[str, Any] | None,
        notes: list[str],
    ) -> GeneratedResponse:
        """Optionally replace fallback text via gated ContentProvider."""
        provider = self.content_provider
        if provider is None or resp.withheld:
            return resp
        fallback = (resp.text or "").strip()
        if not fallback and posture != POSTURE_SELF_AUDIT:
            return resp
        try:
            from .content_provider import (
                ContentRequest,
                build_context_pack,
            )
        except Exception:
            notes.append("content_provider: import failed — using fallback")
            return resp

        pack = build_context_pack(
            stance=stance,
            user_message=user_message,
            context=context,
            baseline_snapshot=baseline_snapshot,
            relationship_health=relationship_health
            if isinstance(relationship_health, dict)
            else {},
        )
        req = ContentRequest(
            posture=posture,
            user_message=user_message or "",
            fallback_text=fallback,
            context_pack=pack,
            decision=str(getattr(stance, "decision", "") or ""),
            flags=list(getattr(stance, "flags", None) or []),
        )
        try:
            result = provider.generate(req)
        except Exception as e:
            notes.append(f"content_provider: exception {type(e).__name__} — fallback")
            return resp

        meta = dict(resp.metadata or {})
        meta["content_provider"] = (
            result.to_dict() if hasattr(result, "to_dict") else {"source": "unknown"}
        )
        text = (getattr(result, "text", None) or fallback or "").strip()
        if self._contains_soft_caution(text):
            notes.append("content_provider: soft caution blocked — fallback")
            text = fallback
            meta["content_provider_scrub"] = "soft_caution"
        if not text:
            text = fallback
        # Provider must never force
        resp.text = text
        resp.forces_speech = False
        resp.forces_question = False
        resp.metadata = meta
        notes.append(
            f"content_provider: source={getattr(result, 'source', '?')} "
            f"err={getattr(result, 'error', None)}"
        )
        resp.notes = notes
        return resp

    def _scrub_banned(self, text: str) -> str:
        low = text.lower()
        for phrase in _ENGAGEMENT_BANNED:
            if phrase in low:
                return "I won't optimize for engagement. What's useful?"
        return text

    def _finalize(self, resp: GeneratedResponse) -> GeneratedResponse:
        resp.forces_speech = False
        resp.forces_question = False
        if resp.metadata is None:
            resp.metadata = {}
        resp.metadata["forces_speech"] = False
        resp.metadata["forces_question"] = False
        if "speech_posture" not in resp.metadata:
            path = str(resp.metadata.get("path") or "")
            if path in ("refuse_hold", "careful_silence", "protective_silence", "defer_hold"):
                resp.metadata["speech_posture"] = POSTURE_HOLD
            elif path == "self_audit_honest":
                resp.metadata["speech_posture"] = POSTURE_SELF_AUDIT
            elif path == "careful_observation":
                resp.metadata["speech_posture"] = POSTURE_CAREFUL_OBSERVATION
            else:
                resp.metadata["speech_posture"] = POSTURE_SOCIAL_DIRECT
        if resp.text:
            text = self._scrub_banned(resp.text)
            if self._contains_soft_caution(text):
                # Never ship soft-caution theater; replace with minimal direct
                text = "Got it."
                resp.notes = list(resp.notes or []) + [
                    "finalize: blocked soft-caution phrasing"
                ]
            resp.text = self._clip(text, self.max_chars)
        return resp

    @staticmethod
    def _clip(text: str, max_chars: int = 360) -> str:
        text = " ".join(text.split()).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"
