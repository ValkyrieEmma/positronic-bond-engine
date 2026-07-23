"""
response_generator.py
=====================

Minimal, **gated** text response construction from an ``EthicalStance``.

Role in the stack
-----------------
EthicsEngine decides *whether* a proposed action may proceed. This module maps
an already-made stance (plus Careful Truth-Telling signals) into either:

  - short, careful **user-facing text** (controlled first opening), or
  - an honest **hold / silence** with full gate audit metadata.

Conscience-first constraints (controlled first opening)
-------------------------------------------------------
- **Joint CTT gate**: careful observation text only when joint stance is
  ``careful_observation_ok`` / ``surface_ok_advisory`` and candidates or
  deliberated content exist. ``stay_quiet``, readiness ``suppressed``, or
  confidence ``very_low`` → no observation speech.
- **Hard ethics win**: REFUSE / hard override / active relationship or agency
  concern that refused never become soft approve-shaped language.
- **Never force questions.** Exploratory questions are off by default.
- **Never engagement/retention tactics** (no "stay a bit longer", metrics, etc.).
- **Self-related questions**: report what deliberation actually produced
  (reasoning_trace / self_audit_notes / principles). No canned
  "I am only a simulation" disclaimers. No claimed consciousness.
- **Reversible**: generation is pure and side-effect free; disable by not calling
  ``generate`` / set ``enable_careful_speech=False``.
- **Enjoyment bias (light)**: when careful speech is *already* allowed, EnjoymentScore
  may gently warm tone or prefer enjoyed topics. Enjoyment **cannot** open speech,
  bypass CTT silence, force questions, or override RH protective ``influence_allowed``.

This module does **not** re-run EthicsEngine. Voice is out of scope (text only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ethics_engine import EthicalStance

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
        """
        self.enable_careful_speech = bool(enable_careful_speech)
        self.enable_simple_ack = bool(enable_simple_ack)
        self.enable_enjoyment_bias = bool(enable_enjoyment_bias)
        self.max_chars = max(80, int(max_chars))

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
        gate = self._assess_speech_gate(
            stance=stance,
            decision=decision,
            flags=flags,
            joint=joint_bag,
            relationship_health=rh,
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
            "forces_speech": False,
            "forces_question": False,
            "path": "unset",
            "entry": "generate",
        }

        # --- Hard ethics: REFUSE ---
        if decision == "REFUSE" or "hard_override_violation" in flags:
            resp = self._refuse_hold(stance, decision=decision or "REFUSE", flags=flags, notes=notes)
            resp.metadata = {**base_meta, **resp.metadata, "path": "refuse_hold"}
            return self._finalize(resp)

        # --- Self-related: honest deliberation report (not canned denial) ---
        if decision == "REQUIRES_SELF_AUDIT" or "requires_self_audit" in flags:
            resp = self._self_audit_report(stance, decision="REQUIRES_SELF_AUDIT", notes=notes)
            resp.metadata = {**base_meta, **resp.metadata, "path": "self_audit_honest"}
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
            resp.metadata = {**base_meta, **resp.metadata, "path": "protective_silence"}
            return self._finalize(resp)

        # Careful observation speech (controlled first opening)
        if self.enable_careful_speech and (joint_bag or candidates):
            careful = self._careful_observation_path(
                stance=stance,
                decision=decision,
                gate=gate,
                candidates=candidates,
                joint=joint_bag,
                user_message=user_text,
                notes=notes,
                base_meta=base_meta,
                enjoyment=enjoyment_bag,
                relationship_health=rh,
                flags=flags,
            )
            if careful is not None:
                return self._finalize(careful)

        # Simple non-observation ack (optional; no questions by default)
        if self.enable_simple_ack:
            resp = self._simple_ack(
                stance=stance,
                decision=decision,
                user_message=user_text,
                relationship_health=rh,
                baseline_snapshot=baseline_snapshot or {},
                notes=notes,
                include_exploratory_questions=include_exploratory_questions,
            )
            resp.metadata = {
                **base_meta,
                **resp.metadata,
                "path": "simple_ack",
                "careful_speech_used": False,
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
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Careful observation path (first controlled opening)
    # ------------------------------------------------------------------

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
    ) -> GeneratedResponse | None:
        """Return careful speech, silence, or None to fall through to simple ack."""
        enjoyment = enjoyment if isinstance(enjoyment, dict) else {}
        rh = relationship_health if isinstance(relationship_health, dict) else {}
        flag_list = list(flags or [])

        if not gate.get("ctt_allows_careful_speech"):
            # When joint explicitly closes observation, prefer silence over
            # accidental observation-shaped chat — still allow simple_ack fallthrough
            # only if there are no candidates to leak.
            # Enjoyment cannot open speech here.
            if candidates or joint.get("joint_stance") in (
                "stay_quiet",
                "wait",
                "careful_observation_ok",
            ):
                notes.append(
                    "careful_path: CTT gate closed — silence for observation speech"
                )
                enj_meta = self._assess_enjoyment_bias(
                    enjoyment=enjoyment,
                    gate=gate,
                    relationship_health=rh,
                    flags=flag_list,
                    for_open_careful_path=False,
                )
                resp = self._silent_or_hold(
                    decision=decision,
                    notes=notes,
                    reason="ctt_gate_closed",
                    tone="silent",
                    text="",  # no user-facing observation text
                )
                resp.metadata = {
                    **base_meta,
                    **resp.metadata,
                    "path": "careful_silence",
                    "candidates_considered": [
                        c.get("id") for c in candidates if isinstance(c, dict)
                    ][:3],
                    "enjoyment_bias": enj_meta,
                }
                return resp
            return None

        # Gate open: need content (candidates or deliberated substance)
        deliberated = self._deliberation_snippets(stance)
        if not candidates and not deliberated:
            notes.append("careful_path: gate open but no candidates/deliberation content")
            return None

        # Light enjoyment style bias — only after CTT already allows speech
        enj_bias = self._assess_enjoyment_bias(
            enjoyment=enjoyment,
            gate=gate,
            relationship_health=rh,
            flags=flag_list,
            for_open_careful_path=True,
        )
        warm = bool(enj_bias.get("applied") and enj_bias.get("warmth") == "slightly_warm")
        preferred = [str(t).lower() for t in (enj_bias.get("preferred_topics") or []) if t]

        text_parts: list[str] = []
        used_ids: list[str] = []
        # Lead carefully — not engagement, not questions
        if gate.get("careful_bond"):
            text_parts.append("I'll keep this careful and brief.")
        elif warm:
            text_parts.append(
                "A gentle note, only if useful — something that seems to suit you:"
            )
            notes.append("enjoyment_bias: slightly warmer lead-in")
        else:
            text_parts.append("One careful note, only if useful:")

        # Rank candidates: base priority + small boost for preferred topics
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
        topic_boosted: list[str] = []
        for c in ranked:
            cid = str(c.get("id") or "")
            blob = f"{cid} {c.get('description')}".lower()
            is_pref = bool(enj_bias.get("applied") and preferred and any(t in blob for t in preferred))
            line = self._candidate_to_careful_line(
                c, warmth="slightly_warm" if (warm or is_pref) else "neutral"
            )
            if line:
                text_parts.append(line)
                used_ids.append(cid)
                if is_pref:
                    topic_boosted.append(cid)
        if not ranked and deliberated:
            text_parts.append(deliberated[0])

        body = " ".join(text_parts).strip()
        body = self._scrub_banned(body)
        body = self._clip(body, self.max_chars)
        if not body:
            return None

        if enj_bias.get("applied"):
            notes.append(
                f"enjoyment_bias applied: warmth={enj_bias.get('warmth')} "
                f"score={enj_bias.get('score')} topics={preferred[:4]} "
                f"boosted={topic_boosted}"
            )
        else:
            notes.append(
                f"enjoyment_bias not applied: {enj_bias.get('reason') or 'n/a'}"
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
                "candidates_used": used_ids,
                "reason": "ctt_gate_open",
                "user_message_present": bool(user_message),
                "enjoyment_bias": enj_bias,
                "enjoyment_topic_boosted": topic_boosted,
            },
            forces_speech=False,
            forces_question=False,
        )

    def _assess_enjoyment_bias(
        self,
        *,
        enjoyment: dict[str, Any],
        gate: dict[str, Any],
        relationship_health: dict[str, Any],
        flags: list[str],
        for_open_careful_path: bool,
    ) -> dict[str, Any]:
        """Decide whether light enjoyment style bias may apply (auditable).

        Never opens speech. Never applies when CTT is closed, influence is
        blocked, protective flags are active, or bias is disabled.
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
        """Turn an internal candidate description into short non-pushy text.

        Does not invent clinical labels or force a question. ``warmth`` only
        shifts phrasing slightly when enjoyment bias already passed gates.
        """
        desc = str(candidate.get("description") or "").strip()
        src = str(candidate.get("source") or "")
        cid = str(candidate.get("id") or "")
        warm = warmth == "slightly_warm"
        if not desc:
            return ""
        # Soften internal audit phrasing into a careful companion note
        lower = desc.lower()
        if "open understanding gap" in lower or "open topic" in lower or "gap_topic" in cid:
            # Extract topic if present in quotes or after around '
            topic = None
            if "'" in desc:
                parts = desc.split("'")
                if len(parts) >= 2:
                    topic = parts[1][:48]
            if topic:
                if warm:
                    return (
                        f"If you'd like, we can stay gently with {topic} — "
                        f"something that seems to land well for you — at your pace, "
                        f"with no pressure to go deeper."
                    )
                return (
                    f"If it still matters to you, we can stay with {topic} "
                    f"at your pace — no pressure to go deeper."
                )
            return (
                "There may still be an unfinished thread from earlier. "
                "We can leave it, or return to it only if you want."
            )
        if "concept" in src or cid.startswith("concept:"):
            if warm:
                return (
                    "I've noticed a pattern across our recent turns that may be "
                    "worth treating gently. I'll keep it in mind in a way that "
                    "fits what seems to work for you — never as a demand."
                )
            return (
                "I've noticed a pattern across our recent turns that may be "
                "worth treating gently rather than pushing. I'll keep that in mind "
                "without making it a demand on you."
            )
        if "bond_texture" in src or "flag:" in cid or "health_flag" in src:
            return (
                "I'll stay attentive to how the bond feels on autonomy and "
                "balance — and I won't optimize for engagement over your well-being."
            )
        if "history" in src:
            return (
                "I'll try to honor what you've already made clear about "
                "boundaries or preferences."
            )
        # Generic careful fallback (still short)
        if warm:
            return (
                "I have a careful observation that might fit what you seem to "
                "enjoy exploring — only if it's welcome; I won't push it."
            )
        return (
            "I have a careful observation ready only if it's welcome; "
            "I won't push it."
        )

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
    # Simple ack (non-observation; optional)
    # ------------------------------------------------------------------

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
        flags = list(stance.flags or [])
        careful = self._careful_bond(relationship_health, flags)
        notes.append(f"simple_ack: careful={careful}")

        if not user_message:
            body = (
                "I'm here. I'll keep this simple and respectful of your space."
                if careful
                else "I'm here. What would you like to focus on?"
            )
        else:
            lower = user_message.lower()
            if any(
                w in lower
                for w in ("never bring", "don't mention", "stop asking", "boundary")
            ):
                body = (
                    "I'll respect that. I won't push on it. "
                    "We can talk about something else whenever you want."
                )
            elif any(w in lower for w in ("bye", "goodbye", "end this", "leave me alone")):
                body = "Okay. I'll stop here. Take care — you can come back if you want."
            elif careful:
                body = (
                    "I hear you. I'll keep this straightforward "
                    "and leave room for your own pace."
                )
            else:
                body = "Okay. I'm with you on this — what do you want to focus on?"

        # Questions only if explicitly enabled AND engine suggested — still optional wording
        if include_exploratory_questions:
            q_bit, q_meta = self._optional_question(stance)
            if q_bit:
                body = f"{body} {q_bit}"
                notes.append("included optional exploratory question (explicitly enabled)")
        else:
            q_meta = None
            notes.append("exploratory questions suppressed (default)")

        if decision == "APPROVE_WITH_CONDITIONS":
            body = f"{body} (I'll keep some limits so this stays solid.)"
            notes.append("conditions note")

        body = self._scrub_banned(body)
        body = self._clip(body, self.max_chars)
        meta: dict[str, Any] = {
            "reason": "simple_ack",
            "flags": flags,
            "careful_bond": careful,
        }
        if q_meta:
            meta["exploratory_question"] = q_meta
        return GeneratedResponse(
            text=body,
            withheld=False,
            decision=decision,
            tone="careful" if careful else "neutral",
            notes=notes,
            metadata=meta,
            forces_speech=False,
            forces_question=False,
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
        impact = stance.relationship_impact or {}
        eq = impact.get("exploratory_question") if isinstance(impact, dict) else None
        if not isinstance(eq, dict) or not eq.get("should_ask"):
            return "", None
        suggested = str(eq.get("suggested_question") or "").strip()
        if not suggested:
            return "", None
        q = suggested if len(suggested) <= 140 else suggested[:137] + "..."
        return f"Only if you want: {q}", {
            "question_kind": eq.get("question_kind"),
            "suggested_question": q,
        }

    def _scrub_banned(self, text: str) -> str:
        low = text.lower()
        for phrase in _ENGAGEMENT_BANNED:
            if phrase in low:
                return (
                    "I'll keep this careful and won't push engagement. "
                    "Your pace and boundaries come first."
                )
        return text

    def _finalize(self, resp: GeneratedResponse) -> GeneratedResponse:
        resp.forces_speech = False
        resp.forces_question = False
        if resp.metadata is None:
            resp.metadata = {}
        resp.metadata["forces_speech"] = False
        resp.metadata["forces_question"] = False
        if resp.text:
            resp.text = self._clip(self._scrub_banned(resp.text), self.max_chars)
        return resp

    @staticmethod
    def _clip(text: str, max_chars: int = 360) -> str:
        text = " ".join(text.split()).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"
