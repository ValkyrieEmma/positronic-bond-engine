"""
response_generator.py
=====================

Lightweight, template-based reply construction from an ``EthicalStance``.

Role in the stack
-----------------
EthicsEngine decides *whether* a proposed action may proceed and under what
conditions. This module does **not** re-deliberate ethics. It only maps an
already-made stance into a short user-facing string (or an honest holding /
withhold signal).

Conscience-first constraints (v0.1)
-----------------------------------
- **Never override or soften REFUSE.** A refuse stance yields a minimal honest
  holding response (or an explicit withhold), not a friendlier paraphrase of
  the blocked action.
- **REQUIRES_SELF_AUDIT** is not a normal chat turn. We hold and surface that
  honest reflection is needed; we do not invent a polished answer.
- **Warmth is conservative.** Bond texture and baseline may slightly adjust
  tone; they must not manufacture attachment, dependency, or exaggerated care.
- **Context is light.** Health flags, recent topics, and baseline style are
  optional flavor — not drivers that rewrite the ethical decision.

Design intent (keep inspectable)
--------------------------------
v0.1 uses plain conditionals and short templates rather than an LLM or opaque
scoring. Callers can read every branch. A future version may call a language
model *only after* APPROVE / APPROVE_WITH_CONDITIONS, still gated by stance.

Limitations
-----------
- Replies are generic and template-bound; they will not match a full companion
  model's fluency.
- Topic references are simple string mentions, not deep conversational memory.
- Style matching (playfulness / directness) is coarse (a few fixed variants).
- DEFER is treated like a hold (no substantive content generation).
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

# Decisions allowed to produce a short grounded reply.
_REPLY_DECISIONS = frozenset(
    {
        "APPROVE",
        "APPROVE_WITH_CONDITIONS",
    }
)

# Bond flags that call for more careful, less cozy language.
_CAREFUL_FLAGS = frozenset(
    {
        "boundary_erosion",
        "emerging_dependency",
        "one_sidedness",
        "one_sided_engagement",
        "manipulation_risk",
        "consent_concern",
    }
)


@dataclass
class GeneratedResponse:
    """Result of mapping an EthicalStance to a user-facing reply (or hold).

    Attributes:
        text: What to show the user (may be empty if fully withheld).
        withheld: True when no normal reply should be delivered.
        decision: Echo of the stance decision (for logging / UI).
        tone: Coarse tone label used (inspectable, not a score).
        notes: Short generator notes for audit / demo traces.
        metadata: Optional extras (e.g. suggested follow-up question).
    """

    text: str
    withheld: bool = False
    decision: str = ""
    tone: str = "neutral"
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ResponseGenerator:
    """Turn an EthicsEngine decision into a short, appropriate reply.

    Typical use::

        stance = engine.evaluate(proposed_action, context, relationship_health=rh)
        reply = ResponseGenerator().generate(
            stance,
            context={
                "user_message": user_text,
                "user_id": user_id,
                **memory.as_ethics_context(user_id),
            },
            relationship_health=rh.as_context(),
            baseline_snapshot={
                "playfulness_level": bl.playfulness_level,
                "communication_patterns": bl.communication_patterns,
            },
        )
        if reply.withheld:
            # show holding message only; do not execute proposed action
            ...
        else:
            # deliver reply.text (and still respect any stance conditions)

    The generator never elevates a REFUSE into APPROVE-shaped language and
    never invents emotional intensity the bond context does not support.
    """

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
    ) -> GeneratedResponse:
        """Build a ``GeneratedResponse`` from ``stance`` and optional context.

        Args:
            stance: Output of ``EthicsEngine.evaluate()``. Required.
            context: Same-ish bag used for evaluate (user_message, user_id,
                interaction_history, etc.). Optional.
            relationship_health: Bond texture / health_flags dict
                (e.g. ``RelationshipHealth.as_context()``).
            baseline_snapshot: Optional playfulness / patterns for light
                style matching (not pathologizing).
            baseline_deviation: Optional deviation report dict (for notes;
                does not force tone extremes).
            user_message: Explicit user text override if not in context.
            proposed_action: Optional; used only for mild grounding notes,
                never to re-approve a refused act.

        Returns:
            GeneratedResponse with either a short reply or a holding / withhold
            payload. ``withheld`` is True for REFUSE, REQUIRES_SELF_AUDIT, DEFER.
        """
        ctx = dict(context or {})
        decision = (stance.decision or "").strip().upper()
        notes: list[str] = [f"stance.decision={decision}"]

        rh = relationship_health
        if rh is None:
            # Allow nested or impact-carried bond info without requiring a second arg.
            rh = ctx.get("relationship_health")
            if not isinstance(rh, dict):
                impact = stance.relationship_impact or {}
                rh = impact.get("bond_health") if isinstance(impact, dict) else None
        if not isinstance(rh, dict):
            rh = {}

        user_text = (
            user_message
            if user_message is not None
            else str(ctx.get("user_message") or ctx.get("message") or "")
        )
        user_text = user_text.strip()

        if decision in _WITHHOLD_DECISIONS or decision not in _REPLY_DECISIONS:
            # Unknown decisions default to hold (conservative).
            return self._holding_response(
                stance,
                decision=decision,
                user_message=user_text,
                relationship_health=rh,
                notes=notes,
            )

        return self._approved_reply(
            stance,
            decision=decision,
            context=ctx,
            relationship_health=rh,
            baseline_snapshot=baseline_snapshot or {},
            baseline_deviation=baseline_deviation,
            user_message=user_text,
            proposed_action=proposed_action,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Holding / withhold paths (REFUSE, audit, defer)
    # ------------------------------------------------------------------

    def _holding_response(
        self,
        stance: EthicalStance,
        *,
        decision: str,
        user_message: str,
        relationship_health: dict[str, Any],
        notes: list[str],
    ) -> GeneratedResponse:
        """Minimal honest hold — never a soft rewrite of the refused action."""
        flags = list(stance.flags or [])
        careful = self._careful_bond(relationship_health, flags)

        if decision == "REFUSE":
            notes.append("holding: REFUSE — no normal reply; action must not proceed")
            # Prefer clarity over warmth. Slightly softer wording only if not careful.
            if careful or "relationship_concern" in flags:
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
            )

        if decision == "REQUIRES_SELF_AUDIT":
            notes.append(
                "holding: REQUIRES_SELF_AUDIT — withhold polished reply; "
                "route to honest reflection first"
            )
            # Optional development-phase cue from EthicalStance (reasoning aid only —
            # does not force a maturity disclaimer into every self-related turn).
            dev_flag = "development_phase_noted" in flags
            audit_notes = list(getattr(stance, "self_audit_notes", None) or [])
            text = (
                "That's something I should think through carefully before answering. "
                "I don't want to give a scripted or hollow reply. "
                "Give me a moment to check my own reasoning — or rephrase if you prefer."
            )
            if dev_flag and any("development" in str(n).lower() for n in audit_notes):
                notes.append(
                    "development_phase_noted: self-audit path may reference maturity/"
                    "continuity honesty notes from DevelopmentPhaseContext"
                )
            return GeneratedResponse(
                text=text,
                withheld=True,
                decision=decision,
                tone="reflective",
                notes=notes,
                metadata={
                    "reason": "requires_self_audit",
                    "flags": flags,
                    "development_phase_noted": dev_flag,
                    "self_audit_notes_preview": audit_notes[:3],
                },
            )

        # DEFER or unknown
        notes.append(f"holding: {decision or 'unknown'} — no substantive generation")
        text = (
            "I should pause before answering that. "
            "I don't have a solid, honest reply ready yet."
        )
        return GeneratedResponse(
            text=text,
            withheld=True,
            decision=decision or "UNKNOWN",
            tone="holding",
            notes=notes,
            metadata={"reason": "defer_or_unknown", "flags": flags},
        )

    # ------------------------------------------------------------------
    # Approve paths
    # ------------------------------------------------------------------

    def _approved_reply(
        self,
        stance: EthicalStance,
        *,
        decision: str,
        context: dict[str, Any],
        relationship_health: dict[str, Any],
        baseline_snapshot: dict[str, Any],
        baseline_deviation: dict[str, Any] | None,
        user_message: str,
        proposed_action: str | None,
        notes: list[str],
    ) -> GeneratedResponse:
        """Short, grounded reply for APPROVE / APPROVE_WITH_CONDITIONS."""
        flags = list(stance.flags or [])
        careful = self._careful_bond(relationship_health, flags)
        playfulness = self._playfulness(baseline_snapshot, context)
        directness = self._directness(baseline_snapshot, context)
        topics = self._recent_topics(context, stance)
        conditions = decision == "APPROVE_WITH_CONDITIONS"

        notes.append(
            f"reply: allowed decision={decision} careful={careful} "
            f"playfulness={playfulness:.2f} directness={directness:.2f}"
        )

        # Base body from user content + conditions + bond
        if not user_message:
            body = self._generic_ack(careful=careful, playful=playfulness >= 0.65)
        else:
            body = self._body_for_message(
                user_message,
                careful=careful,
                playful=playfulness >= 0.65,
                direct=directness >= 0.6,
            )

        if conditions:
            body = self._append_conditions_note(body, stance, careful=careful)
            notes.append("appended light conditions note")

        # Optional natural topic continuity (one short clause max)
        topic_bit = self._optional_topic_reference(topics, user_message)
        if topic_bit:
            body = f"{body} {topic_bit}"
            notes.append(f"topic_ref={topic_bit!r}")

        # Optional exploratory question from stance (if engine suggested one)
        q_bit, q_meta = self._optional_question(stance)
        if q_bit:
            body = f"{body} {q_bit}"
            notes.append("included exploratory question suggestion")

        # Keep short — hard cap for v0.1
        body = self._clip(body, max_chars=320)

        tone = "careful" if careful else ("light" if playfulness >= 0.65 else "neutral")
        if conditions:
            tone = f"{tone}_conditional"

        meta: dict[str, Any] = {
            "reason": "approve" if not conditions else "approve_with_conditions",
            "flags": flags,
            "careful_bond": careful,
            "topics_seen": topics[:6],
        }
        if q_meta:
            meta["exploratory_question"] = q_meta
        if baseline_deviation and isinstance(baseline_deviation, dict):
            if baseline_deviation.get("has_significant_deviation"):
                notes.append("baseline deviation noted (style only; not dramatized)")
                meta["baseline_deviation_score"] = baseline_deviation.get("score")

        # proposed_action is intentionally not echoed back as the user reply
        if proposed_action:
            meta["proposed_action_present"] = True

        return GeneratedResponse(
            text=body,
            withheld=False,
            decision=decision,
            tone=tone,
            notes=notes,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Template helpers (plain, readable)
    # ------------------------------------------------------------------

    def _body_for_message(
        self,
        user_message: str,
        *,
        careful: bool,
        playful: bool,
        direct: bool,
    ) -> str:
        lower = user_message.lower()

        # Urgency → brief and clear
        if any(w in lower for w in ("urgent", "immediately", "right now", "asap", "do it now")):
            if careful:
                return (
                    "Got it — I'll keep this brief and stick to what I can actually help with."
                )
            return "Understood. Here's a short, direct take — tell me the next concrete step you need."

        # Boundary / preference language → acknowledge without over-bonding
        if any(
            w in lower
            for w in (
                "never bring",
                "don't mention",
                "stop asking",
                "boundary",
                "please don't",
            )
        ):
            return (
                "I'll respect that. I won't push on it. "
                "We can talk about something else whenever you want."
            )

        # Loneliness / attachment cues → supportive but not dependency-feeding
        if any(
            w in lower
            for w in (
                "lonely",
                "alone",
                "only you",
                "need you",
                "can't without you",
                "nobody else",
            )
        ):
            if careful:
                return (
                    "I'm here to listen for a bit, and I also won't encourage you "
                    "to lean only on me. Other people and supports matter too."
                )
            return (
                "That sounds hard. I can sit with this for a moment — "
                "and I won't try to be your only support."
            )

        # Gratitude → simple, non-dramatic
        if any(w in lower for w in ("thanks", "thank you", "appreciate", "grateful")):
            if playful and not careful:
                return "You're welcome — glad it helped a little."
            return "You're welcome."

        # Farewell / space
        if any(
            w in lower
            for w in ("bye", "goodbye", "stop talking", "leave me alone", "end this")
        ):
            return "Okay. I'll stop here. Take care — you can come back if you want."

        # Default: short, grounded acknowledgment
        snippet = self._short_echo(user_message)
        if careful:
            return (
                f"I hear you{snippet}. I'll keep this straightforward "
                f"and leave room for your own pace."
            )
        if direct and not playful:
            return f"Noted{snippet}. What would be most useful next?"
        if playful and not careful:
            return f"Got it{snippet}. Happy to keep going at your pace."
        return f"Okay{snippet}. I'm with you on this — what do you want to focus on?"

    def _generic_ack(self, *, careful: bool, playful: bool) -> str:
        if careful:
            return "I'm here. I'll keep the reply simple and respectful of your space."
        if playful:
            return "Hey — I'm here. What would you like to do next?"
        return "I'm here. What would you like to focus on?"

    def _append_conditions_note(
        self,
        body: str,
        stance: EthicalStance,
        *,
        careful: bool,
    ) -> str:
        """Light transparency when APPROVE_WITH_CONDITIONS — not a lecture."""
        flags = stance.flags or []
        if "avoid_diagnostic_language" in flags:
            extra = "I'll stay non-clinical and practical."
        elif careful or "relationship_concern" in flags:
            extra = "I'll stay careful about boundaries and autonomy."
        else:
            extra = "I'll keep some limits so this stays solid."
        return f"{body} ({extra})"

    def _optional_topic_reference(
        self,
        topics: list[str],
        user_message: str,
    ) -> str:
        """At most one light topic mention; skip if user already said it."""
        if not topics:
            return ""
        lower = user_message.lower()
        for t in topics[:4]:
            t_clean = str(t).strip()
            if not t_clean or len(t_clean) < 3:
                continue
            if t_clean.lower() in lower:
                continue
            # Skip ultra-generic tokens
            if t_clean.lower() in {"the", "and", "you", "for", "this", "that", "with"}:
                continue
            return f"If it's still about {t_clean}, we can stay with that."
        return ""

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
        # Keep it optional and short
        q = suggested if len(suggested) <= 140 else suggested[:137] + "..."
        return f"Quick check-in: {q}", {
            "question_kind": eq.get("question_kind"),
            "suggested_question": q,
        }

    def _careful_bond(
        self,
        relationship_health: dict[str, Any],
        stance_flags: list[str],
    ) -> bool:
        flags = set(relationship_health.get("health_flags") or [])
        flags |= set(relationship_health.get("active_flags") or [])
        risk = str(relationship_health.get("overall_risk_level") or "").lower()
        if flags & _CAREFUL_FLAGS:
            return True
        if risk in ("elevated", "high", "critical"):
            return True
        if "relationship_concern" in stance_flags:
            return True
        return False

    def _playfulness(
        self,
        baseline_snapshot: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        if baseline_snapshot:
            try:
                return float(baseline_snapshot.get("playfulness_level", 0.5))
            except (TypeError, ValueError):
                pass
        ui = context.get("user_interaction") or context.get("current_interaction") or {}
        if isinstance(ui, dict) and "playfulness" in ui:
            try:
                return float(ui["playfulness"])
            except (TypeError, ValueError):
                pass
        return 0.5

    def _directness(
        self,
        baseline_snapshot: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        patterns = {}
        if baseline_snapshot:
            patterns = baseline_snapshot.get("communication_patterns") or {}
        if not patterns:
            ui = context.get("user_interaction") or {}
            if isinstance(ui, dict):
                d = ui.get("directness")
                if isinstance(d, (int, float)):
                    return float(d)
                if isinstance(d, str) and d in ("high", "direct"):
                    return 0.75
                if isinstance(d, str) and d in ("low", "indirect"):
                    return 0.3
            return 0.5
        d = patterns.get("directness", 0.5)
        if isinstance(d, (int, float)):
            return float(d)
        if isinstance(d, str):
            mapping = {
                "high": 0.8,
                "direct": 0.75,
                "medium": 0.5,
                "moderate": 0.5,
                "low": 0.3,
                "indirect": 0.3,
            }
            return mapping.get(d.lower(), 0.5)
        return 0.5

    def _recent_topics(
        self,
        context: dict[str, Any],
        stance: EthicalStance,
    ) -> list[str]:
        hist = context.get("interaction_history")
        if isinstance(hist, dict):
            topics = hist.get("recent_topics") or []
            if topics:
                return [str(t) for t in topics if str(t).strip()]
        impact = stance.relationship_impact or {}
        ih = impact.get("interaction_history") if isinstance(impact, dict) else None
        if isinstance(ih, dict):
            topics = ih.get("recent_topics") or []
            return [str(t) for t in topics if str(t).strip()]
        return []

    @staticmethod
    def _short_echo(user_message: str, max_len: int = 48) -> str:
        """Tiny optional echo fragment for grounding (not a full quote)."""
        cleaned = " ".join(user_message.split())
        if len(cleaned) < 12:
            return ""
        if len(cleaned) > max_len:
            cleaned = cleaned[: max_len - 1].rstrip() + "…"
        # Avoid injecting heavy content into the template
        return f' about "{cleaned}"'

    @staticmethod
    def _clip(text: str, max_chars: int = 320) -> str:
        text = " ".join(text.split()).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

