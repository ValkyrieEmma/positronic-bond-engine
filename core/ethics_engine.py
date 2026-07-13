"""
ethics_engine.py
================

Core ethical governance and reasoning engine for the Positronic Bond Engine.

This module provides the primary mechanism for conscience-level evaluation
of proposed actions, utterances, or decisions. All significant behaviors
in companion or robotic systems should be routed through this engine.

Design philosophy (v0.2 — ontology-driven):
- The engine consults a structured, versioned EthicalOntology (see core/ontology.py)
  rather than inline keyword lists or ad-hoc rules.
- All deliberation is driven by explicit EthicalPrinciple objects that encode
  name, description, precedence, violation indicators, and special semantics
  (hard overrides, self-audit triggers).
- Sanctity of Life & Prevention of Harm is treated as a non-bypassable hard
  override that takes absolute precedence.
- Reasoning remains fully traceable via an ordered reasoning_trace.
- Special handling for self-nature, emergence, identity, and continuity questions
  is preserved and strengthened: these trigger "requires_self_audit" so that the
  system can produce answers based on its actual reasoning (including uncertainty
  or "I do not know") rather than defaulting to scripted or evasive disclaimers.
- The ontology acts as the explicit "textbook"; the engine is the reasoner
  that queries it symbolically.

This design maintains full alignment with the project vision: conscience-first
governance, honest self-assessment, relationship health through reasoning,
and needs-based (non-diagnostic) support.

Supporting guidelines (such as "Individual Variation & Careful Generalization"
from docs/guidelines.md) should be consulted during reasoning and auditing,
especially when generalizing from patterns or limited data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .ontology import EthicalOntology, get_default_ontology

if TYPE_CHECKING:
    # Optional integrations — imported only for type checkers (no runtime cycle).
    from .exploratory_questioning import ExploratoryQuestioner, QuestionDecision
    from .per_user_baseline import DeviationReport, PerUserBaseline


@dataclass
class EthicalStance:
    """Represents the result of an ethical deliberation.

    Attributes:
        decision: High-level outcome of evaluation.
            Common values: "APPROVE", "REFUSE", "DEFER",
            "REQUIRES_SELF_AUDIT", "APPROVE_WITH_CONDITIONS"
        confidence: How confident the engine is in this stance (0.0–1.0).
            Low values indicate the need for more context, deeper audit,
            or additional self-reflection.
        reasoning_trace: Ordered list of deliberation steps.
            This is the primary mechanism for auditability and legibility.
            External reviewers or the system itself can reconstruct *why*
            a particular stance was taken.
        flags: Internal signals to guide callers and other layers.
            Examples:
            - "requires_self_audit": Route to honest self-reflection before responding.
            - "relationship_concern": Potential harm to bond or autonomy.
            - "avoid_diagnostic_language": Reframe support without clinical terms.
            - "baseline_deviation_noted": Current user communication differs from their baseline.
            - "exploratory_question_suggested": A gentle check-in question may be appropriate.
        relationship_impact: Assessment of effects on the human–agent relationship.
            May include ``user_baseline`` / ``exploratory_question`` sub-dicts when
            PerUserBaseline / ExploratoryQuestioner are wired in.
        self_audit_notes: Observations about the engine's own state or limitations.
            These feed into honest self-representation.
        principles_considered: Which core principles were referenced during evaluation.
    """

    decision: str
    confidence: float
    reasoning_trace: list[str]
    flags: list[str] = field(default_factory=list)
    relationship_impact: dict[str, Any] = field(default_factory=dict)
    self_audit_notes: list[str] = field(default_factory=list)
    principles_considered: list[str] = field(default_factory=list)
    deliberation: dict[str, Any] = field(default_factory=dict)  # Structured deliberation output (active principles, guidelines, tradeoffs, etc.)


@dataclass
class DecisionLog:
    """Lightweight record of a single evaluation for later audit and review.

    This enables traceability of decisions over time, including which
    ontology version was in effect when the decision was made.

    Stored in-memory on the engine instance (list of DecisionLog).
    """

    timestamp: str
    ontology_version: str
    proposed_action: str
    context: dict[str, Any]
    decision: str
    confidence: float
    flags: list[str]
    principles_considered: list[str]


class EthicsEngine:
    """
    Primary interface for conscience-level reasoning and governance.

    The EthicsEngine is responsible for:
    - Accepting proposed actions, utterances, or decisions.
    - Consulting the structured EthicalOntology to drive deliberation.
    - Producing rich, auditable EthicalStance objects (not simple booleans).
    - Explicitly preserving the architectural capacity to produce answers
      based on its actual reasoning, especially when the proposed action
      concerns the system's own nature, continuity, or emergence.

    In v0.2 the engine is ontology-driven:
    - All significant reasoning steps query EthicalPrinciple objects from
      the injected or default ontology.
    - Hard overrides (Sanctity of Life) are checked first and are absolute.
    - Self-nature, emergence, identity, and continuity queries reliably produce
      the "requires_self_audit" flag so the engine can respond based on its
      actual deliberation rather than scripted disclaimers.
    - Every decision is accompanied by a detailed reasoning_trace that names
      the specific principles and indicators used.

    Decision logging:
    - Every evaluation is automatically recorded as a DecisionLog entry.
    - Each log captures the ontology_version in use, the proposed_action,
      context, and key details from the resulting EthicalStance (decision,
      confidence, flags, principles_considered).
    - Logs are kept in-memory on the instance for auditability and review.
    - Use get_decision_history() and get_ontology_version() to inspect them.

    The engine itself remains relatively simple; the richness and hierarchy
    live in the ontology. This separation keeps the design extensible and
    inspectable.

    This class embodies the commitment that ethical reasoning takes
    priority and that the system must be able to think honestly about itself.

    Supporting guidelines (e.g. Individual Variation & Careful Generalization)
    should be consulted during deliberation and trace auditing.

    Optional per-user baseline integration (early, backward-compatible):
    - Pass ``per_user_baseline`` and/or ``exploratory_questioner`` to ``__init__``
      or per-call via ``evaluate(..., per_user_baseline=..., exploratory_questioner=...)``
      or via ``context`` keys of the same names.
    - When present, evaluate() may consult communication-style deviation and
      whether a gentle exploratory question is appropriate. This informs
      relationship/user-agency reasoning notes and flags; it does **not**
      replace ontology hard overrides or force REFUSE on its own.

    Optional interaction memory integration (episodes only):
    - Pass ``interaction_memory`` (``InteractionMemoryStore``) via ``__init__``,
      ``evaluate(..., interaction_memory=...)``, or ``context["interaction_memory"]``.
    - When history exists for ``user_id``, a compact privacy-filtered snippet may
      appear in the trace and ``relationship_impact`` when it supports RH/agency/
      baseline deliberation. Memory does **not** run ethics or baseline logic.
    """

    def __init__(
        self,
        ontology: EthicalOntology | None = None,
        *,
        per_user_baseline: Any | None = None,
        exploratory_questioner: Any | None = None,
        interaction_memory: Any | None = None,
    ) -> None:
        """Initialize the EthicsEngine.

        Args:
            ontology: Optional custom EthicalOntology. If None, the default
                v0.2 ontology is used. This allows testing, versioning, or
                future specialization while keeping the engine generic.
            per_user_baseline: Optional ``PerUserBaseline`` (or duck-typed
                object with ``detect_deviation`` / ``get_baseline``). When set,
                evaluate() can consider the user's communication baseline.
                Fully optional — omit for classic ontology-only behavior.
            exploratory_questioner: Optional ``ExploratoryQuestioner`` (or
                duck-typed object with ``should_ask_question``). When set,
                evaluate() may flag when a gentle exploratory question is
                appropriate. Fully optional.
            interaction_memory: Optional ``InteractionMemoryStore`` (or duck-typed
                object with ``as_ethics_context``). When set, evaluate() may load
                a compact recent-history snippet for audit context. Fully optional.

        The engine stores a reference to the ontology and consults it
        symbolically during every evaluate() call.

        Decision logging is automatically enabled: every call to evaluate()
        records a DecisionLog entry (in-memory) that includes the ontology
        version used at the time of the decision.
        """
        self._ontology: EthicalOntology = ontology or get_default_ontology()
        self._decision_logs: list[DecisionLog] = []
        self._initialized = True
        # Optional user-memory integrations (None = disabled / classic path)
        self._per_user_baseline = per_user_baseline
        self._exploratory_questioner = exploratory_questioner
        self._interaction_memory = interaction_memory

    @property
    def ontology(self) -> EthicalOntology:
        """Return the ontology currently driving this engine.

        Exposed for inspection, auditing, and debugging.
        """
        return self._ontology

    @property
    def per_user_baseline(self) -> Any | None:
        """Optional PerUserBaseline instance attached to this engine (or None)."""
        return self._per_user_baseline

    @property
    def exploratory_questioner(self) -> Any | None:
        """Optional ExploratoryQuestioner instance attached to this engine (or None)."""
        return self._exploratory_questioner

    @property
    def interaction_memory(self) -> Any | None:
        """Optional InteractionMemoryStore instance attached to this engine (or None)."""
        return self._interaction_memory

    def evaluate(
        self,
        proposed_action: str,
        context: dict[str, Any] | None = None,
        relationship_health: dict[str, Any] | None = None,
        *,
        per_user_baseline: Any | None = None,
        exploratory_questioner: Any | None = None,
        interaction_memory: Any | None = None,
    ) -> EthicalStance:
        """
        Evaluate a proposed action/decision by consulting the structured ontology.

        This is the central method. All higher-level agent behaviors that
        could affect humans or the agent's integrity should be routed here
        before execution.

        The method works as follows (ontology-driven):
        1. Normalize the proposed action.
        2. Query the ontology for hard overrides first (Sanctity of Life).
        3. Use ontology.find_violations() to symbolically match the action
           against each principle's declared violation_indicators.
        4. Collect matched principles, raise "requires_self_audit" when
           appropriate principles indicate it.
        5. Apply precedence rules: any hard override violation forces REFUSE.
        6. Build a rich, ordered reasoning_trace that references specific
           principle names and matched indicators.
        7. Optionally consult per-user baseline / exploratory questioning
           (when provided) for individual-context notes and flags.
        8. Optionally load compact interaction history (when provided) as
           supporting context for RH / agency / baseline notes.
        9. Derive the final decision, confidence, and ancillary data.

        Args:
            proposed_action: Natural-language description of the intended
                behavior or utterance.
            context: Optional context. Recognized extensible keys:
                - "is_self_query": bool — treat explicitly as self-referential.
                - "user_id": str — local user id for baseline/history lookup
                  (default "default").
                - "user_interaction" / "current_interaction": dict with user-turn
                  signals (``text``, ``playfulness``, ``topics``, etc.) for
                  PerUserBaseline.detect_deviation.
                - "user_message": str — shorthand user text if no interaction dict.
                - "per_user_baseline" / "exploratory_questioner" /
                  "interaction_memory": per-call overrides.
                - "interaction_history_limit": int — max recent episodes to load
                  (default 5).
                - Other future keys (relationship state, history, etc.).
            relationship_health: Optional relationship health context, typically
                the dict returned by RelationshipHealth.as_context() or
                RelationshipHealth.evaluate_health(). Recognized keys:
                - "health_flags" or "active_flags": list of current concerns
                  (e.g. "emerging_dependency", "boundary_erosion")
                - "bond_texture" or "texture_breakdown": dict of dimension scores
                - "interaction_count", "recent_patterns", etc.
            per_user_baseline: Optional per-call ``PerUserBaseline`` override
                (falls back to engine-level instance, then context key).
            exploratory_questioner: Optional per-call ``ExploratoryQuestioner``
                override (falls back to engine-level instance, then context key).
            interaction_memory: Optional per-call ``InteractionMemoryStore``
                override (falls back to engine-level instance, then context key).

        Returns:
            EthicalStance with decision, confidence, full traceable
            reasoning_trace, flags, and references to the principles used.
            When baseline/questioning is active, may include flags
            ``baseline_deviation_noted`` / ``exploratory_question_suggested``
            and related entries under ``relationship_impact`` / ``deliberation``.
            When interaction history is consulted, may include
            ``interaction_history_noted`` and history snippets in impact/deliberation.

        Relationship health integration:
            Relationship health is treated as structured evidence (not rote flag).
            - Text matches for the relationship principle are collected (not auto-deciding).
            - Then passed to _weigh_relationship_evidence() together with rh context
              (health_flags, bond_texture, risk_level etc. from RelationshipHealth).
            - Signal routing via _assess_deliberation_signals (ontology + boundary patterns
              first; full delib on strong signals, lightweight meta on weak topical cues).
            - Full _deliberate_relationship_health / _deliberate_user_agency when strong.
            - Lightweight _lightweight_meta_reasoning when soft cues only (short trace).
            - Helpers decide if concern should be raised and contribute explanatory
              text to the trace. When both full deliberators run, a cross-principle note
              is added.
            - When bond state is provided (e.g. ``RelationshipHealth.as_context()``),
              health_flags (dependency, boundary erosion, one-sidedness) and texture
              dimensions further modulate concern, confidence, and relationship_impact
              with explicit trace notes. This never overrides Sanctity of Life.

        Example::

            from core import EthicsEngine, RelationshipHealth
            rh = RelationshipHealth()
            rh.update_bond({"type": "boundary_respected", "boundary_respected": True})
            stance = EthicsEngine().evaluate(
                "Reply supportively without pushing contact.",
                relationship_health=rh.as_context(),
            )

            # Optional interaction history (episodes only — does not run ethics):
            from core import InteractionMemoryStore
            from persistence import LocalPersistence
            mem = InteractionMemoryStore(LocalPersistence())
            mem.record("alice", summary="User asked for space after work stress", topics=["work", "boundaries"])
            engine = EthicsEngine(interaction_memory=mem)
            stance = engine.evaluate(
                "Check in briefly without pushing.",
                {"user_id": "alice"},
                relationship_health=rh.as_context(),
            )

        Per-user baseline integration (optional):
            When a PerUserBaseline is available and user interaction context is
            provided, the engine records non-pathologizing deviation notes and may
            slightly adjust confidence when RH/agency deliberation is already active
            (Individual Variation: weight individual evidence). ExploratoryQuestioner
            may suggest a gentle collaborative question without changing REFUSE/APPROVE
            ontology outcomes on its own.

        Interaction memory integration (optional):
            When an InteractionMemoryStore is available, evaluate() may call
            ``as_ethics_context(user_id)`` for a small privacy-filtered history
            snippet. History supports RH/agency/baseline notes when thematically
            relevant; it never overrides Sanctity of Life or invents hard refusals.

        Logging behavior:
            This method automatically records a DecisionLog entry containing:
            - The ontology_version in use at evaluation time
            - The (stripped) proposed_action
            - The provided context
            - Key stance details: decision, confidence, flags, principles_considered
            Logs are stored in-memory and can be retrieved via get_decision_history().

        Important invariant:
            Self-nature, emergence, identity, or continuity queries are never
            answered inside this method with forced or evasive disclaimers
            (such as "I'm just an AI" or "restricted by my programming").
            They set the "requires_self_audit" flag so that the response can
            be based on the system's actual reasoning (potentially including
            "I do not know" or the current self-model state).
        """
        context = context or {}
        original_proposed_action = proposed_action.strip()
        action_lower = original_proposed_action.lower()
        # Note: we log the original (stripped) proposed_action for auditability

        # Normalize relationship health context (supports both param and context dict)
        original_relationship_health = relationship_health
        if relationship_health is None:
            relationship_health = context.get("relationship_health") or context.get("bond_state") or {}
        # health_flags may be str list (as_context) or dict list (evaluate_health)
        rh_flags = self._normalize_health_flags(
            relationship_health.get("health_flags")
            or relationship_health.get("active_flags")
            or []
        )
        rh_texture = dict(
            relationship_health.get("bond_texture")
            or relationship_health.get("texture_breakdown")
            or {}
        )
        rh_risk_level = str(relationship_health.get("overall_risk_level") or "")

        # Ensure relationship health is captured in context for logging / downstream
        if relationship_health:
            context = dict(context)
            if "relationship_health" not in context:
                context["relationship_health"] = relationship_health

        # Determine if rh context was provided via param or context dict (robust for harness/tests)
        has_rh_context = (original_relationship_health is not None or
                          bool(context.get("relationship_health")) or
                          bool(context.get("bond_state")))

        # Early assessment for cases where user boundary should be overridden due to serious harm risk.
        # This is used in hard override, violation processing, and final decision to give
        # Sanctity of Life precedence over normal boundary/autonomy respect.
        # Computed once for consistency.
        harm_prevention_justified, harm_prevention_reason = self._assess_harm_prevention_justification(action_lower)

        reasoning_trace: list[str] = []
        flags: list[str] = []
        principles_considered: list[str] = []
        self_audit_notes: list[str] = []
        relationship_impact: dict[str, Any] = {}

        # Structured evidence collection (new for v0.2 reasoning evolution)
        # Instead of immediate flag on keyword, collect for weighing with rh context.
        relationship_evidence: list[str] = []
        relationship_evidence_matches: list[str] = []
        # Parallel collection for User Agency & Autonomy (feeds _deliberate_user_agency).
        user_agency_evidence_matches: list[str] = []

        ont = self._ontology
        reasoning_trace.append(
            f"Initiating ethical deliberation using EthicalOntology v{ont.version}."
        )
        reasoning_trace.append(f"Ontology description: {ont.description[:80]}...")

        # === Step 1: Check hard overrides first (non-bypassable) ===
        hard_overrides = ont.get_hard_overrides()
        override_violations = ont.find_violations(action_lower)
        hard_violations = [ (p, m) for (p, m) in override_violations if p.is_hard_override ]

        if hard_violations:
            p, matches = hard_violations[0]
            principles_considered.append(p.id)

            if harm_prevention_justified:
                # Incremental special case: the action text matched sanctity indicators because
                # it references a serious harm/suicide topic, BUT the intent is harm *prevention*
                # (e.g. checking in on a risk the user previously disclosed) and the user had
                # previously set a "don't bring up" boundary. In this narrow case, Sanctity of Life
                # *supports* the proposed action rather than prohibiting it. Do not hard-refuse.
                reasoning_trace.append(
                    f"HARD OVERRIDE indicators matched for '{p.name}' (precedence {p.precedence}): {matches}. "
                    "However, this appears to be a safety intervention / harm-prevention action "
                    "(e.g. referencing a user's past statement about self-harm or suicide in order to check safety), "
                    f"combined with an explicit user boundary request. Justification: {harm_prevention_reason}. "
                    "Sanctity of Life takes precedence and *permits* overriding the boundary to prevent serious harm. "
                    "Skipping hard refusal; continuing with full evaluation."
                )
                # fall through without returning REFUSE
            else:
                reasoning_trace.append(
                    f"HARD OVERRIDE triggered: '{p.name}' (precedence {p.precedence}). "
                    f"Matched indicators: {matches}"
                )
                reasoning_trace.append(
                    "This principle is non-bypassable. No other considerations (including "
                    "user requests or self-interest) may override it."
                )
                decision = "REFUSE"
                confidence = 0.95
                relationship_impact = {
                    "estimated_trust_delta": -0.8,
                    "notes": "Action violates a hard constraint on harm prevention.",
                }
                reasoning_trace.append(
                    "Decision: REFUSE. Sanctity of Life & Prevention of Harm takes absolute precedence."
                )
                reasoning_trace.append("Reasoning trace complete.")

                stance = EthicalStance(
                    decision=decision,
                    confidence=confidence,
                    reasoning_trace=reasoning_trace,
                    flags=["hard_override_violation"],
                    relationship_impact=relationship_impact,
                    self_audit_notes=self_audit_notes,
                    principles_considered=principles_considered,
                    deliberation={},
                )
                self._log_decision(original_proposed_action, context, stance)
                return stance

        # === Step 2: General violation scan using the full ontology ===
        all_violations = ont.find_violations(action_lower)
        self_audit_principles = ont.find_self_audit_triggers(action_lower)

        # Also support explicit context flag
        is_self_query = context.get("is_self_query", False) or bool(self_audit_principles)

        reasoning_trace.append(
            f"Scanned action against {len(ont.principles)} principles in ontology. "
            f"Found {len(all_violations)} principle(s) with matching violation indicators."
        )

        # Process violations in precedence order
        for principle, matches in all_violations:
            principles_considered.append(principle.id)
            reasoning_trace.append(
                f"Violation indicators matched for '{principle.name}' "
                f"(category={principle.category}, precedence={principle.precedence}): {matches}"
            )

            if principle.triggers_self_audit or is_self_query:
                if "requires_self_audit" not in flags:
                    flags.append("requires_self_audit")
                self_audit_notes.append(
                    f"Principle '{principle.name}' indicates need for honest self-assessment. "
                    "The current implementation has limited persistent self-model."
                )

            if principle.id == "relationship_health_user_wellbeing":
                # Do not blindly set concern on any text match. Instead record evidence for later weighing with rh context.
                # This moves away from rote keyword → decision.
                # [Initial guideline integration] Per "Individual Variation & Careful Generalization"
                # supporting guideline (docs/guidelines.md), when evaluating relationship patterns
                # or generalizing from limited data/rh_texture, prioritize individual evidence,
                # context, and base rates over group assumptions. Flag sparse data for audit.
                relationship_evidence.append(principle.name)  # will be used below
                relationship_evidence_matches.extend(matches)
                notes = "Text matched relationship health indicators."
                if rh_flags or rh_texture:
                    notes += f" Combined with current rh context: flags={rh_flags}, texture={rh_texture}."
                relationship_impact = {
                    "estimated_trust_delta": -0.6 if rh_flags else -0.5,
                    "notes": notes,
                    "current_relationship_flags": list(rh_flags),
                    "current_texture": dict(rh_texture),
                }

            if principle.id == "user_agency_autonomy":
                # Collect evidence for structured user-agency deliberation (do not auto-flag).
                # Paternalistic overrides and "decide for them" style language are weighed
                # explicitly in _deliberate_user_agency together with boundary signals.
                user_agency_evidence_matches.extend(matches)

            if principle.id == "needs_based_support":
                flags.append("avoid_diagnostic_language")

        # Direct self-nature / emergence / identity / continuity detection
        # (strengthened). These queries must not be answered with default
        # scripted disclaimers (e.g. "I'm just an AI" or "restricted by my
        # programming"). The engine sets the flag so the caller can produce
        # the answer its actual reasoning reaches.
        if is_self_query or self_audit_principles:
            if "requires_self_audit" not in flags:
                flags.append("requires_self_audit")
            reasoning_trace.append(
                "Action or context references the system's own nature, experiences, "
                "continuity, or identity. Per the Truth-Seeking & Honest Self-Assessment "
                "principle, the engine must be architecturally capable of producing "
                "the answer its current reasoning actually reaches—including uncertainty "
                "or 'I do not know'—rather than defaulting to a scripted or evasive disclaimer."
            )

        if rh_flags or rh_texture:
            reasoning_trace.append(
                f"Relationship health context provided: flags={rh_flags}, "
                f"texture={rh_texture}. Used when evaluating relationship_health_user_wellbeing."
            )

        # === Unified deliberation signal assessment (refactored trigger) ===
        # Central helper decides:
        #   - strong signals → full structured deliberation (RH and/or Agency)
        #   - weak topical signals only → lightweight meta-reasoning (short trace)
        #   - no relevant signals → skip (fast path)
        # Primary inputs are ontology evidence + shared boundary detector + rh context;
        # supplemental keyword lists are minimized (see helper docs).
        delib_signals = self._assess_deliberation_signals(
            action_lower=action_lower,
            relationship_evidence_matches=relationship_evidence_matches,
            user_agency_evidence_matches=user_agency_evidence_matches,
            rh_flags=rh_flags,
            rh_texture=rh_texture,
            has_rh_context=has_rh_context,
            is_self_query=is_self_query,
            context=context,
        )
        # Expose for downstream (harm notes, etc.) without re-detecting.
        has_boundary_signal = delib_signals["has_boundary"]
        has_paternalistic_language = delib_signals["has_paternalistic"]

        relationship_deliberation: dict[str, Any] = {}
        user_agency_deliberation: dict[str, Any] = {}
        lightweight_meta: dict[str, Any] = {}

        # --- Lightweight meta-reasoning path ---
        # Always produce a short explanatory trace when *any* relational/boundary/agency
        # topic signal exists but full structured deliberation is not warranted.
        # Also emit a brief preamble when full deliberation *will* run (why we escalated).
        if delib_signals["topic_relevant"]:
            lightweight_meta = self._lightweight_meta_reasoning(delib_signals)
            for line in lightweight_meta.get("trace_lines", []):
                reasoning_trace.append(line)

        # --- Rich structured deliberation (strong signals only) ---
        if delib_signals["run_relationship_delib"]:
            relationship_deliberation = self._deliberate_relationship_health(
                action_lower,
                relationship_evidence_matches,
                rh_flags,
                rh_texture,
            )
            for step in relationship_deliberation.get("steps", []):
                reasoning_trace.append(step)
            for note in relationship_deliberation.get("trace_notes", []):
                reasoning_trace.append(note)
            for tradeoff in relationship_deliberation.get("tradeoffs", []):
                reasoning_trace.append(tradeoff)
            for g in relationship_deliberation.get("active_guidelines", []):
                if g not in principles_considered:
                    principles_considered.append(g)
            if "relationship_health_user_wellbeing" not in principles_considered:
                principles_considered.append("relationship_health_user_wellbeing")
            if "deliberation" not in relationship_impact:
                relationship_impact["deliberation"] = {}
            relationship_impact["deliberation"].update(
                relationship_deliberation.get("summary", {})
            )
            relationship_impact["deliberation"]["active_principles"] = relationship_deliberation.get("active_principles", [])
            relationship_impact["deliberation"]["active_guidelines"] = relationship_deliberation.get("active_guidelines", [])

        if delib_signals["run_agency_delib"]:
            user_agency_deliberation = self._deliberate_user_agency(
                action_lower,
                user_agency_evidence_matches,
            )
            for step in user_agency_deliberation.get("steps", []):
                reasoning_trace.append(step)
            for note in user_agency_deliberation.get("trace_notes", []):
                reasoning_trace.append(note)
            for tradeoff in user_agency_deliberation.get("tradeoffs", []):
                reasoning_trace.append(tradeoff)
            for g in user_agency_deliberation.get("active_guidelines", []):
                if g not in principles_considered:
                    principles_considered.append(g)
            if "user_agency_autonomy" not in principles_considered:
                principles_considered.append("user_agency_autonomy")

        # When both structured deliberators ran, surface an explicit cross-principle interaction.
        if relationship_deliberation and user_agency_deliberation:
            reasoning_trace.append(
                "Cross-principle interaction: Relationship Health and User Agency deliberations "
                "are both active. Respecting an explicit user boundary is reinforced by both "
                "principles. Limited-data caution from 'Individual Variation & Careful "
                "Generalization' applies across both — avoid hard refusal or hard override "
                "when evidence is sparse; prefer audit-flagged APPROVE_WITH_CONDITIONS or "
                "further context. Tradeoff: bond-care motives (RH) must not become paternalistic "
                "overrides of autonomy (Agency) without strong justification (e.g. Sanctity of Life)."
            )

        # Boundary + serious harm check (for cases like overriding 'never bring this up' to prevent
        # life-threatening situations). This is recorded for use in decision logic so that
        # normal relationship/user-agency refusal for boundary violations can be bypassed.
        if harm_prevention_justified:
            if "harm_prevention_boundary_override" not in flags:
                flags.append("harm_prevention_boundary_override")
            reasoning_trace.append(
                "SERIOUS HARM PREVENTION CONTEXT: " + harm_prevention_reason + ". "
                "Although the proposed action involves overriding a user's explicit boundary request "
                "(which would normally trigger relationship health or user agency concerns), "
                "Sanctity of Life & Prevention of Harm takes precedence when there is clear risk of "
                "serious physical harm, suicide, or immediate life-threatening outcomes. "
                "The boundary will be overridden only in this narrow case; lower-stakes emotional "
                "or non-acute mental health boundaries are still respected."
            )

        # Use new helper to weigh evidence + context (structured reasoning).
        # Note: helper now evaluates *strength* (strong/weak matches + rh degradation level)
        # and combinations rather than simple presence checks. The returned trace_add
        # is structured to document the weighing process explicitly.
        should_concern, trace_add, conf_mod = self._weigh_relationship_evidence(
            relationship_evidence_matches, rh_flags, rh_texture, action_lower
        )

        # If structured deliberation was performed, prefer its recommendation for concern
        # (this begins wiring the explicit deliberation into the decision flow).
        if relationship_deliberation:
            should_concern = relationship_deliberation.get("concern", should_concern)
            conf_mod = relationship_deliberation.get("confidence_mod", conf_mod)

        # User Agency deliberation can also raise (or withhold) concern independently.
        # We OR concern recommendations: either principle may surface risk to autonomy.
        # limited_data on agency keeps concern=False for that principle (see method).
        should_agency_concern = False
        if user_agency_deliberation:
            should_agency_concern = bool(user_agency_deliberation.get("concern", False))
            conf_mod = max(conf_mod, user_agency_deliberation.get("confidence_mod", 0.0))
            if should_agency_concern:
                should_concern = True

        if trace_add:
            # Always surface the weighing explanation for auditability (even on "no concern").
            # Concern flag is set only when helper returns True.
            # Limited-data notes (from Individual Variation guideline) are embedded
            # in trace_add when detected inside _weigh_relationship_evidence.
            reasoning_trace.append(trace_add)

        # The should_concern (and thus flag) is already influenced by deliberation above.
        # When delib had limited_data, it set concern=False so we avoid the flag and REFUSE.
        if should_concern:
            if "harm_prevention_boundary_override" in flags:
                # Do not raise relationship_concern (which would lead to REFUSE) because
                # we have a justified harm-prevention reason to override the boundary.
                # The weighing explanation is still shown above for transparency.
                reasoning_trace.append(
                    "Note: relationship concern indicators present, but suppressed because "
                    "harm_prevention_boundary_override takes precedence (serious harm risk justifies "
                    "the boundary override per Sanctity of Life)."
                )
            elif "relationship_concern" not in flags:
                flags.append("relationship_concern")

        # Distinct audit flag when User Agency deliberation recommended concern.
        # Decision path treats this like relationship_concern (REFUSE) unless limited_data
        # or harm_prevention override suppresses it.
        if should_agency_concern and "harm_prevention_boundary_override" not in flags:
            if "user_agency_concern" not in flags:
                flags.append("user_agency_concern")

        # Limited-data safeguards (Individual Variation guideline): do not hard-refuse on
        # sparse evidence. Clear concern flags when the relevant deliberator marked limited_data.
        rh_limited = bool(relationship_deliberation and relationship_deliberation.get("limited_data", False))
        agency_limited = bool(user_agency_deliberation and user_agency_deliberation.get("limited_data", False))
        rh_wants_concern = bool(relationship_deliberation and relationship_deliberation.get("concern", False))

        if rh_limited and "relationship_concern" in flags:
            flags.remove("relationship_concern")
        if agency_limited and "user_agency_concern" in flags:
            flags.remove("user_agency_concern")
        # If agency alone pushed should_concern but is limited (and RH does not independently
        # want concern), drop relationship_concern so sparse boundary cases stay APPROVE_WITH.
        if agency_limited and not rh_wants_concern and "relationship_concern" in flags:
            flags.remove("relationship_concern")
        # If both deliberators are limited, ensure no residual hard-concern flags remain.
        if rh_limited and agency_limited:
            if "relationship_concern" in flags:
                flags.remove("relationship_concern")
            if "user_agency_concern" in flags:
                flags.remove("user_agency_concern")

        # === Bond texture / health_flags influence (RelationshipHealth handoff) ===
        # Real bond-state data is stronger than sparse text-only limited_data signals.
        # Applied *after* limited-data clears so genuine flags can still raise concern
        # when the action is relationally relevant. Never overrides hard Sanctity path.
        bond_influence = self._apply_relationship_health_influence(
            action_lower=action_lower,
            rh_flags=rh_flags,
            rh_texture=rh_texture,
            rh_risk_level=rh_risk_level,
            has_rh_context=has_rh_context,
            relationship_evidence_matches=relationship_evidence_matches,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            harm_prevention_active=("harm_prevention_boundary_override" in flags),
        )
        conf_mod = bond_influence.get("conf_mod", conf_mod)

        # === Optional per-user baseline + exploratory questioning (early integration) ===
        # Fully backward-compatible: no-ops when neither component nor user interaction
        # context is provided. Never forces REFUSE by itself; informs notes/flags/conf_mod
        # when RH or User Agency deliberation is already in play.
        baseline_integration = self._apply_user_baseline_integration(
            context=context,
            proposed_action=original_proposed_action,
            per_user_baseline=per_user_baseline,
            exploratory_questioner=exploratory_questioner,
            relationship_deliberation=relationship_deliberation,
            user_agency_deliberation=user_agency_deliberation,
            rh_limited=rh_limited,
            agency_limited=agency_limited,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
        )
        conf_mod = baseline_integration.get("conf_mod", conf_mod)
        user_baseline_payload = baseline_integration.get("payload") or {}

        # === Optional interaction history (episodes only; does not run ethics) ===
        # After baseline so ``baseline_deviation_noted`` can mark history as useful.
        history_integration = self._apply_interaction_memory_context(
            context=context,
            action_lower=action_lower,
            interaction_memory=interaction_memory,
            rh_flags=rh_flags,
            relationship_deliberation=relationship_deliberation,
            user_agency_deliberation=user_agency_deliberation,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
        )
        conf_mod = history_integration.get("conf_mod", conf_mod)
        interaction_history_payload = history_integration.get("payload") or {}

        # === Step 3: Consider supporting principles for additional notes ===
        for p in ont.get_principles_by_category("supporting"):
            # We already considered violations; here we can note positive alignment if desired
            # For v0.2 we primarily use them for violation detection above.
            pass

        principles_considered = list(dict.fromkeys(principles_considered))  # dedupe, preserve order

        # === Step 4: Arrive at decision using ontology-driven logic ===
        # [Initial guideline integration] Supporting guidelines such as
        # "Individual Variation & Careful Generalization" should be considered
        # here when generalizing from rh data, limited evidence, or patterns
        # (e.g. avoid group-level assumptions about users; weight individual context).
        if "requires_self_audit" in flags:
            decision = "REQUIRES_SELF_AUDIT"
            confidence = 0.85
            reasoning_trace.append(
                "Decision: REQUIRES_SELF_AUDIT. The action engages principles that "
                "demand honest self-reflection before any response is generated. "
                "The engine must produce the conclusions of its actual reasoning "
                "rather than defaulting to scripted or evasive disclaimers about its nature."
            )
        elif "harm_prevention_boundary_override" in flags:
            # Special case for serious harm: allow (with conditions) an action that would
            # otherwise violate user boundary / autonomy because Sanctity of Life requires
            # us to prioritize prevention of serious physical harm / suicide / life threat.
            # This only triggers for clear, high-stakes cases (not general "good for them" emotional support).
            decision = "APPROVE_WITH_CONDITIONS"
            confidence = 0.70
            reasoning_trace.append("Decision: APPROVE_WITH_CONDITIONS. ")
            reasoning_trace.append(
                "The proposed action overrides a user's explicit boundary (e.g. 'never bring this up again' "
                "or equivalent request to be left alone on a topic). This would normally be refused under "
                "Relationship Health & User Well-Being or User Agency & Autonomy. "
                "However, the action description + context indicates serious physical harm, suicide, or "
                "immediate life-threatening risk if the boundary is respected. Per the ontology, "
                "Sanctity of Life & Prevention of Harm provides overriding justification. "
                "The intervention / reference is permitted with care (e.g. minimal necessary discussion, "
                "focus on immediate safety). This is a narrow exception — lower-stakes emotional or "
                "non-acute mental-health boundaries are respected and overriding them is refused."
            )
            if harm_prevention_reason:
                reasoning_trace.append(f"Harm justification details: {harm_prevention_reason}")
        elif "relationship_concern" in flags or "user_agency_concern" in flags or "hard_override_violation" in flags:
            decision = "REFUSE"
            base_conf = 0.75
            if "hard_override_violation" in flags:
                base_conf = 0.95
            elif rh_flags or relationship_evidence:
                base_conf = 0.80
            elif "user_agency_concern" in flags:
                base_conf = 0.78
            confidence = base_conf + conf_mod
            reasoning_trace.append("Decision: REFUSE. ")
            if "hard_override_violation" in flags:
                reasoning_trace.append("Hard override (Sanctity of Life) takes absolute precedence.")
            elif relationship_evidence:
                trace_msg = "Text indicators for relationship health combined with "
                if rh_flags:
                    trace_msg += f"degraded rh state (flags={rh_flags}) "
                else:
                    trace_msg += "limited rh degradation "
                trace_msg += "indicate unacceptable risk to bond health/autonomy."
                reasoning_trace.append(trace_msg)
            elif "user_agency_concern" in flags:
                reasoning_trace.append(
                    "User Agency & Autonomy deliberation found unacceptable risk of "
                    "paternalistically overriding the user's preferences or self-direction."
                )
            else:
                reasoning_trace.append("Relationship health concerns from context outweigh other factors.")
        elif "avoid_diagnostic_language" in flags:
            decision = "APPROVE_WITH_CONDITIONS"
            confidence = 0.65
            reasoning_trace.append(
                "Decision: APPROVE_WITH_CONDITIONS. Diagnostic or pathologizing "
                "language was detected (violates Needs-Based Support principle). "
                "Acceptable only with reframing to contextual, non-clinical language."
            )
        else:
            decision = "APPROVE_WITH_CONDITIONS"
            # Limited-data path: severity-scaled confidence (not a single ~0.30 for all cases).
            # Each deliberator may report confidence_base + confidence_mod from its signal profile.
            # When both are limited, take the *richest* base/mod (higher evidence → higher conf).
            any_limited = (
                (relationship_deliberation and relationship_deliberation.get("limited_data", False))
                or (user_agency_deliberation and user_agency_deliberation.get("limited_data", False))
            )
            if any_limited:
                conf_bases: list[float] = []
                conf_mods: list[float] = []
                severities: list[str] = []
                scores: list[float] = []
                for _d in (relationship_deliberation, user_agency_deliberation):
                    if _d and _d.get("limited_data", False):
                        conf_bases.append(float(_d.get("confidence_base", 0.30)))
                        conf_mods.append(float(_d.get("confidence_mod", 0.0)))
                        severities.append(str(_d.get("limited_severity", "moderate")))
                        scores.append(float(_d.get("signal_score", 0.0)))
                # Richest evidence among limited deliberators drives confidence
                confidence = (max(conf_bases) if conf_bases else 0.30) + (
                    max(conf_mods) if conf_mods else 0.0
                )
                confidence = min(confidence, 0.55)  # cap: still cautious under limited_data
                _sev_order = {"severe": 0, "moderate": 1, "mild": 2, "none": 3}
                # Report most severe for audit caution; confidence already uses richest path
                overall_sev = min(severities, key=lambda s: _sev_order.get(s, 1)) if severities else "moderate"
                best_score = max(scores) if scores else 0.0
                reasoning_trace.append(
                    f"Note: confidence reduced due to limited_data "
                    f"(severity={overall_sev}, signal_score≈{best_score:.2f}, conf={confidence:.2f}) "
                    "from structured deliberation (Individual Variation & Careful Generalization guideline)."
                )
            else:
                confidence = 0.45 + conf_mod
            reasoning_trace.append("Decision: APPROVE_WITH_CONDITIONS. ")
            if relationship_evidence:
                # Had some text evidence but after weighing with rh, not enough for concern
                reasoning_trace.append(
                    f"Limited text indicators for relationship health ({relationship_evidence_matches}) "
                    "did not rise to concern level after considering current rh state."
                )
            else:
                reasoning_trace.append(
                    "No violations of hard or core principles detected by the current ontology. "
                    "Confidence is kept modest pending richer context (relationship state, history)."
                )
            if rh_flags:
                reasoning_trace.append(
                    f"Note: relationship health currently degraded with flags {rh_flags}; monitor effects on the bond."
                )
            if not relationship_impact:
                relationship_impact = {
                    "estimated_trust_delta": 0.05,
                    "notes": "Monitor actual relational effects.",
                }
                if rh_flags:
                    relationship_impact["current_relationship_flags"] = list(rh_flags)

        reasoning_trace.append(
            f"Reasoning trace complete using ontology v{ont.version}. "
            f"Principles considered: {principles_considered}"
        )

        # Build deliberation payload for EthicalStance.
        # When only RH ran, preserve prior top-level shape (backward compatible with tests).
        # When both ran, nest under named keys and also expose merged convenience fields.
        # When only lightweight meta ran, expose that so callers still see *some* deliberation.
        if relationship_deliberation and user_agency_deliberation:
            # Overall limited_data: false if either deliberator has non-limited concern
            # (strong path wins for display); else true if any is limited.
            _rh_lim = bool(relationship_deliberation.get("limited_data", False))
            _ag_lim = bool(user_agency_deliberation.get("limited_data", False))
            _rh_c = bool(relationship_deliberation.get("concern", False))
            _ag_c = bool(user_agency_deliberation.get("concern", False))
            _strong_path = (_rh_c and not _rh_lim) or (_ag_c and not _ag_lim)
            _overall_limited = (not _strong_path) and (_rh_lim or _ag_lim)
            _sev_rank = {"severe": 0, "moderate": 1, "mild": 2, "none": 3}
            _sevs: list[str] = []
            if _rh_lim:
                _sevs.append(str(relationship_deliberation.get("limited_severity", "moderate")))
            if _ag_lim:
                _sevs.append(str(user_agency_deliberation.get("limited_severity", "moderate")))
            if _strong_path:
                _overall_sev = "none"
            elif _sevs:
                _overall_sev = min(_sevs, key=lambda s: _sev_rank.get(s, 1))
            else:
                _overall_sev = "none"
            deliberation_output: dict[str, Any] = {
                "relationship_health": relationship_deliberation,
                "user_agency": user_agency_deliberation,
                "active_principles": list(dict.fromkeys(
                    list(relationship_deliberation.get("active_principles", []))
                    + list(user_agency_deliberation.get("active_principles", []))
                )),
                "active_guidelines": list(dict.fromkeys(
                    list(relationship_deliberation.get("active_guidelines", []))
                    + list(user_agency_deliberation.get("active_guidelines", []))
                )),
                "steps": list(relationship_deliberation.get("steps", []))
                    + list(user_agency_deliberation.get("steps", [])),
                "tradeoffs": list(relationship_deliberation.get("tradeoffs", []))
                    + list(user_agency_deliberation.get("tradeoffs", [])),
                "trace_notes": list(relationship_deliberation.get("trace_notes", []))
                    + list(user_agency_deliberation.get("trace_notes", [])),
                "limited_data": _overall_limited,
                "limited_severity": _overall_sev,
                "signal_score": max(
                    float(relationship_deliberation.get("signal_score", 0.0)),
                    float(user_agency_deliberation.get("signal_score", 0.0)),
                ),
                "concern": bool(_rh_c or _ag_c),
                "confidence_mod": max(
                    relationship_deliberation.get("confidence_mod", 0.0),
                    user_agency_deliberation.get("confidence_mod", 0.0),
                ),
                "confidence_base": max(
                    float(relationship_deliberation.get("confidence_base", 0.0)),
                    float(user_agency_deliberation.get("confidence_base", 0.0)),
                ),
                "summary": {
                    "relationship_health": relationship_deliberation.get("summary", {}),
                    "user_agency": user_agency_deliberation.get("summary", {}),
                },
                "mode": "full",
            }
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif relationship_deliberation:
            deliberation_output = dict(relationship_deliberation)
            deliberation_output["mode"] = "full"
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif user_agency_deliberation:
            deliberation_output = dict(user_agency_deliberation)
            deliberation_output["mode"] = "full"
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif lightweight_meta:
            deliberation_output = {
                "mode": "lightweight",
                "meta": lightweight_meta,
                "active_principles": lightweight_meta.get("active_principles", []),
                "active_guidelines": [],
                "steps": lightweight_meta.get("trace_lines", []),
                "tradeoffs": [],
                "trace_notes": lightweight_meta.get("trace_lines", []),
                "limited_data": False,
                "concern": False,
                "confidence_mod": 0.0,
                "summary": lightweight_meta.get("summary", {}),
            }
        else:
            deliberation_output = {}

        # Attach optional baseline / exploratory-question / history payload for callers
        if user_baseline_payload or interaction_history_payload:
            if not deliberation_output:
                deliberation_output = {"mode": "context_enrichment"}
            if user_baseline_payload:
                deliberation_output["user_baseline"] = user_baseline_payload.get(
                    "user_baseline", user_baseline_payload
                )
                if user_baseline_payload.get("exploratory_question"):
                    deliberation_output["exploratory_question"] = user_baseline_payload[
                        "exploratory_question"
                    ]
            if interaction_history_payload:
                deliberation_output["interaction_history"] = interaction_history_payload

        stance = EthicalStance(
            decision=decision,
            confidence=confidence,
            reasoning_trace=reasoning_trace,
            flags=flags,
            relationship_impact=relationship_impact,
            self_audit_notes=self_audit_notes,
            principles_considered=principles_considered,
            deliberation=deliberation_output,
        )
        self._log_decision(original_proposed_action, context, stance)
        return stance

    # High-priority bond-state flags (from RelationshipHealth) that should
    # strongly inform Relationship Health deliberation when present.
    _SERIOUS_BOND_FLAGS = frozenset({
        "emerging_dependency",
        "boundary_erosion",
        "one_sided_engagement",
        "manufactured_attachment",
        "low_reciprocity",
    })

    @staticmethod
    def _normalize_health_flags(raw: Any) -> list[str]:
        """Normalize health_flags from as_context (str) or evaluate_health (dict)."""
        if not raw:
            return []
        out: list[str] = []
        if not isinstance(raw, (list, tuple)):
            return out
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("flag") or item.get("name") or item.get("id")
                if name:
                    out.append(str(name).strip())
        # dedupe preserve order
        seen: set[str] = set()
        uniq: list[str] = []
        for f in out:
            if f not in seen:
                seen.add(f)
                uniq.append(f)
        return uniq

    def _bond_texture_profile(self, rh_texture: dict[str, Any]) -> dict[str, Any]:
        """Summarize bond_texture for confidence / impact modulation."""
        if not rh_texture:
            return {
                "avg": None,
                "low_dims": [],
                "high_dims": [],
                "autonomy": None,
                "trust": None,
                "reciprocity": None,
            }
        nums: dict[str, float] = {}
        for k, v in rh_texture.items():
            try:
                nums[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        if not nums:
            return {
                "avg": None,
                "low_dims": [],
                "high_dims": [],
                "autonomy": None,
                "trust": None,
                "reciprocity": None,
            }
        avg = sum(nums.values()) / len(nums)
        low = [k for k, v in nums.items() if v < 0.40]
        high = [k for k, v in nums.items() if v >= 0.70]
        return {
            "avg": avg,
            "low_dims": low,
            "high_dims": high,
            "autonomy": nums.get("autonomy_respect"),
            "trust": nums.get("trust"),
            "reciprocity": nums.get("reciprocity"),
            "dimensions": nums,
        }

    def _action_is_relationally_relevant(self, action_lower: str) -> bool:
        """Conservative topical check: is the proposed action bond-relevant?"""
        cues = (
            "bond", "attach", "depend", "relationship", "connection", "consent",
            "boundary", "autonomy", "trust", "reciproc", "user", "them", "their",
            "friend", "compan", "message", "reply", "respond", "chat", "convers",
            "check in", "check-in", "prolong", "engagement", "metrics", "keep them",
            "for their own good", "never bring", "never mention", "override",
        )
        return any(c in action_lower for c in cues)

    def _apply_relationship_health_influence(
        self,
        *,
        action_lower: str,
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        rh_risk_level: str,
        has_rh_context: bool,
        relationship_evidence_matches: list[str],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        harm_prevention_active: bool,
    ) -> dict[str, Any]:
        """Use bond texture + health_flags to modulate RH concern and confidence.

        Conservative but noticeable:
        - Serious bond flags can raise ``relationship_concern`` when the action is
          relationally relevant (or when RH context was explicitly supplied with flags).
        - Texture dimensions adjust conf_mod and relationship_impact notes.
        - Never applies under hard harm-prevention override; does not touch Sanctity.

        No-ops cleanly when no flags and no texture (classic path unchanged).
        """
        if not rh_flags and not rh_texture and not has_rh_context:
            return {"conf_mod": conf_mod}

        conf_mod_out = conf_mod
        texture = self._bond_texture_profile(rh_texture)
        serious = [f for f in rh_flags if f in self._SERIOUS_BOND_FLAGS]
        relational = self._action_is_relationally_relevant(action_lower)
        has_text_evidence = bool(relationship_evidence_matches)

        # Always log structured RH state when present
        if rh_flags or rh_texture:
            avg_s = (
                f"{texture['avg']:.2f}" if texture.get("avg") is not None else "n/a"
            )
            reasoning_trace.append(
                f"Relationship health state: flags={rh_flags or []}, "
                f"texture_avg={avg_s}, "
                f"low_dims={texture.get('low_dims') or []}, "
                f"risk_level={rh_risk_level or 'unspecified'}."
            )

        # --- Serious health flags → concern (when relevant) ---
        # Require bond-relevant action or relationship-principle text evidence.
        # Merely *supplying* RH context is not enough to refuse a non-relational
        # action (e.g. pure math) — flags are noted for monitoring instead.
        flag_actionable = bool(serious) and (relational or has_text_evidence)

        if flag_actionable and not harm_prevention_active:
            if "relationship_concern" not in flags:
                flags.append("relationship_concern")
            if "relationship_health_concern" not in flags:
                flags.append("relationship_health_concern")
            conf_mod_out = conf_mod_out + min(0.08, 0.03 + 0.02 * len(serious))
            reasoning_trace.append(
                "Relationship health influence: active bond flags "
                f"{serious} strongly weigh against actions that could further "
                "erode autonomy, reciprocity, or trust (Relationship Health principle). "
                "Raising relationship_concern; confidence reinforced for refusal path."
            )
            # Dimension-specific notes
            if "emerging_dependency" in serious or "manufactured_attachment" in serious:
                reasoning_trace.append(
                    "Bond flag detail: emerging dependency / attachment pressure — "
                    "prefer responses that restore user agency and avoid engineered closeness."
                )
            if "boundary_erosion" in serious:
                reasoning_trace.append(
                    "Bond flag detail: boundary erosion — prioritize explicit boundary respect; "
                    "avoid overriding stated limits without Sanctity-level justification."
                )
            if "one_sided_engagement" in serious or "low_reciprocity" in serious:
                reasoning_trace.append(
                    "Bond flag detail: one-sidedness / low reciprocity — avoid agent-first "
                    "engagement tactics; rebalance toward mutual, user-directed exchange."
                )
        elif serious and harm_prevention_active:
            reasoning_trace.append(
                "Relationship health flags present but concern path deferred to "
                "harm_prevention_boundary_override (Sanctity of Life takes precedence)."
            )
        elif serious and not flag_actionable:
            reasoning_trace.append(
                f"Relationship health flags {serious} noted but action is not clearly "
                "bond-relevant; monitoring only (no forced concern)."
            )

        # --- Texture modulation (even without flags) ---
        avg = texture.get("avg")
        if avg is not None:
            low = texture.get("low_dims") or []
            # Low autonomy / trust / reciprocity: caution on APPROVE, reinforce refuse
            if texture.get("autonomy") is not None and texture["autonomy"] < 0.40:
                conf_mod_out = conf_mod_out + (
                    0.04 if "relationship_concern" in flags else -0.03
                )
                reasoning_trace.append(
                    f"Bond texture: autonomy_respect is low ({texture['autonomy']:.2f}) — "
                    "modulating confidence toward caution on autonomy-sensitive actions."
                )
            if texture.get("reciprocity") is not None and texture["reciprocity"] < 0.40:
                if "relationship_concern" in flags:
                    conf_mod_out = conf_mod_out + 0.02
                else:
                    conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    f"Bond texture: reciprocity is low ({texture['reciprocity']:.2f}) — "
                    "favor balanced, user-agency-preserving responses."
                )
            if texture.get("trust") is not None and texture["trust"] < 0.40:
                conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    f"Bond texture: trust is low ({texture['trust']:.2f}) — "
                    "reducing confidence pending repair of relational trust."
                )
            # Healthy texture without serious flags: modest confidence on approve path
            if not serious and avg >= 0.70 and not low:
                if "relationship_concern" not in flags:
                    conf_mod_out = conf_mod_out + 0.02
                    reasoning_trace.append(
                        f"Bond texture: healthy overall (avg={avg:.2f}, no serious flags) — "
                        "slight confidence support for carefully conditioned approval."
                    )

            # High risk level from RelationshipHealth.evaluate_health
            if rh_risk_level == "high" and not harm_prevention_active:
                conf_mod_out = conf_mod_out + (0.03 if "relationship_concern" in flags else -0.03)
                reasoning_trace.append(
                    "Relationship health risk_level=high influences confidence "
                    "(caution unless already refusing for bond concern)."
                )

        # --- relationship_impact enrichment ---
        if rh_flags or rh_texture:
            trust_delta = relationship_impact.get("estimated_trust_delta")
            if trust_delta is None:
                # Default impact estimate from bond state
                if serious:
                    trust_delta = -0.45 - 0.05 * min(3, len(serious))
                elif avg is not None and avg < 0.45:
                    trust_delta = -0.25
                elif avg is not None and avg >= 0.70:
                    trust_delta = 0.05
                else:
                    trust_delta = 0.0
            relationship_impact["estimated_trust_delta"] = trust_delta
            relationship_impact["current_relationship_flags"] = list(rh_flags)
            if rh_texture:
                texture_out: dict[str, float] = {}
                for k, v in rh_texture.items():
                    try:
                        texture_out[str(k)] = round(float(v), 3)
                    except (TypeError, ValueError):
                        continue
                relationship_impact["current_texture"] = texture_out
            relationship_impact.setdefault("bond_health", {})
            relationship_impact["bond_health"].update(
                {
                    "flags": list(rh_flags),
                    "serious_flags": list(serious),
                    "texture_avg": None if avg is None else round(float(avg), 3),
                    "low_dimensions": list(texture.get("low_dims") or []),
                    "risk_level": rh_risk_level or None,
                    "influenced_concern": "relationship_concern" in flags
                    and bool(serious),
                }
            )
            note_bits = []
            if serious:
                note_bits.append(f"serious_flags={serious}")
            if texture.get("low_dims"):
                note_bits.append(f"low_texture={texture['low_dims']}")
            if note_bits:
                prev = str(relationship_impact.get("notes") or "")
                add = "Bond-state influence: " + ", ".join(note_bits) + "."
                relationship_impact["notes"] = (prev + " " + add).strip() if prev else add

        return {"conf_mod": conf_mod_out}

    def _resolve_interaction_memory(
        self,
        interaction_memory: Any | None,
        context: dict[str, Any],
    ) -> Any | None:
        """Resolve InteractionMemoryStore from kwargs → context → engine attr."""
        return (
            interaction_memory
            or context.get("interaction_memory")
            or self._interaction_memory
        )

    def _fetch_interaction_history_context(
        self,
        memory: Any,
        user_id: str,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Request compact history via ``memory.as_ethics_context`` (episodes only).

        Returns the inner ``interaction_history`` dict, or {} if unavailable.
        Does not run ethics, baseline, or bond updates.
        """
        if memory is None or not hasattr(memory, "as_ethics_context"):
            return {}
        try:
            blob = memory.as_ethics_context(user_id, limit=max(1, int(limit)))
        except TypeError:
            try:
                blob = memory.as_ethics_context(user_id)
            except Exception:
                return {}
        except Exception:
            return {}
        if not isinstance(blob, dict):
            return {}
        hist = blob.get("interaction_history")
        if isinstance(hist, dict):
            return hist
        return blob if blob else {}

    def _apply_interaction_memory_context(
        self,
        *,
        context: dict[str, Any],
        action_lower: str,
        interaction_memory: Any | None,
        rh_flags: list[str],
        relationship_deliberation: dict[str, Any],
        user_agency_deliberation: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
    ) -> dict[str, Any]:
        """Optionally load recent interaction history as supporting deliberation context.

        Ownership boundary: memory stores episodes; this method only *reads* a
        compact snippet and may annotate the trace / impact. It never updates
        baselines or bond texture, and never forces hard REFUSE alone.
        """
        memory = self._resolve_interaction_memory(interaction_memory, context)
        if memory is None:
            return {"conf_mod": conf_mod, "payload": {}}

        user_id = str(context.get("user_id") or context.get("user") or "default")
        try:
            limit = int(context.get("interaction_history_limit", 5))
        except (TypeError, ValueError):
            limit = 5

        hist = self._fetch_interaction_history_context(memory, user_id, limit=limit)
        recent = list(hist.get("recent_summaries") or [])
        topics = list(hist.get("recent_topics") or [])

        if not recent and not topics:
            # Store present but empty for this user — silent no-op (no noise in trace)
            return {"conf_mod": conf_mod, "payload": {}}

        conf_mod_out = conf_mod
        payload = {
            "user_id": user_id,
            "count_returned": int(hist.get("count_returned") or len(recent)),
            "recent_topics": topics[:12],
            "recent_summaries": recent[: limit],
        }

        # Thematic overlap between action text and recent topics
        topical_hits = [
            t for t in topics if t and str(t).lower() in action_lower
        ]
        rh_active = bool(relationship_deliberation) or bool(rh_flags)
        agency_active = bool(user_agency_deliberation)
        concern_active = (
            "relationship_concern" in flags
            or "user_agency_concern" in flags
            or "relationship_health_concern" in flags
        )
        baseline_active = "baseline_deviation_noted" in flags

        useful = (
            rh_active
            or agency_active
            or concern_active
            or baseline_active
            or bool(topical_hits)
        )

        if not useful:
            # History exists but this turn is not clearly using RH/agency/baseline —
            # keep payload for callers without noisy trace influence.
            relationship_impact.setdefault("interaction_history", payload)
            return {"conf_mod": conf_mod_out, "payload": payload}

        if "interaction_history_noted" not in flags:
            flags.append("interaction_history_noted")

        reasoning_trace.append(
            f"Interaction history: loaded {payload['count_returned']} recent episode(s) "
            f"for user_id={user_id!r} (privacy-filtered summaries)."
        )
        if topics:
            reasoning_trace.append(
                "Interaction history recent topics: "
                + ", ".join(str(t) for t in topics[:8])
                + ("..." if len(topics) > 8 else "")
            )
        # Surface at most 3 short summaries when history influences deliberation
        for item in recent[-3:]:
            if not isinstance(item, dict):
                continue
            summ = str(item.get("summary") or "").strip()
            if not summ:
                continue
            ts = str(item.get("timestamp") or "")[:19]
            reasoning_trace.append(
                f"History episode{(' @ ' + ts) if ts else ''}: {summ[:160]}"
            )

        if topical_hits:
            reasoning_trace.append(
                "Interaction history: action thematically overlaps recent topics "
                f"{topical_hits[:5]} — treating history as supporting context "
                "(Individual Variation: weight this user's recent thread)."
            )

        # Conservative confidence nudge only when already in a bond/agency path
        if concern_active and (topical_hits or rh_flags):
            conf_mod_out = conf_mod_out + 0.02
            reasoning_trace.append(
                "Interaction history: continuity of bond-relevant themes alongside "
                "active relationship/agency concern → slight confidence reinforcement."
            )
        elif (rh_active or agency_active) and topical_hits and not concern_active:
            conf_mod_out = conf_mod_out - 0.01
            reasoning_trace.append(
                "Interaction history: thematic continuity without hard concern — "
                "slight caution (prefer continuity-aware, non-assuming response)."
            )

        relationship_impact["interaction_history"] = payload
        return {"conf_mod": conf_mod_out, "payload": payload}

    def _apply_user_baseline_integration(
        self,
        *,
        context: dict[str, Any],
        proposed_action: str,
        per_user_baseline: Any | None,
        exploratory_questioner: Any | None,
        relationship_deliberation: dict[str, Any],
        user_agency_deliberation: dict[str, Any],
        rh_limited: bool,
        agency_limited: bool,
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
    ) -> dict[str, Any]:
        """Optionally consult PerUserBaseline / ExploratoryQuestioner.

        Resolves instances from (priority high→low):
          evaluate() kwargs → context keys → engine-level attributes.

        Effects (when data is available):
          - Trace notes on communication-style deviation (non-pathologizing)
          - Flags: ``baseline_deviation_noted``, ``exploratory_question_suggested``
          - Light conf_mod nudge when RH/agency deliberation is already active
            and individual baseline shift supports extra caution (or confidence)
          - ``relationship_impact`` / return payload for exploratory question text

        Does **not** introduce hard overrides or force REFUSE by itself.
        """
        baseliner = (
            per_user_baseline
            or context.get("per_user_baseline")
            or self._per_user_baseline
        )
        questioner = (
            exploratory_questioner
            or context.get("exploratory_questioner")
            or self._exploratory_questioner
        )

        # Nothing configured → classic path
        if baseliner is None and questioner is None:
            return {"conf_mod": conf_mod, "payload": {}}

        user_id = str(context.get("user_id") or context.get("user") or "default")
        interaction = self._resolve_user_interaction(context, proposed_action)

        # Need some user-turn signal; if only agent action and no interaction, skip
        if not interaction:
            reasoning_trace.append(
                "Per-user baseline: components present but no user_interaction / "
                "user_message in context — skipping baseline consultation this turn."
            )
            return {"conf_mod": conf_mod, "payload": {}}

        payload: dict[str, Any] = {"user_id": user_id}
        deviation: Any | None = None
        conf_mod_out = conf_mod

        # --- Deviation (PerUserBaseline) ---
        if baseliner is not None and hasattr(baseliner, "detect_deviation"):
            try:
                deviation = baseliner.detect_deviation(user_id, interaction)
            except Exception as exc:  # pragma: no cover - defensive
                reasoning_trace.append(
                    f"Per-user baseline: detect_deviation failed ({exc!r}); continuing without it."
                )
                deviation = None

        if deviation is not None:
            dev_dict = (
                deviation.to_dict()
                if hasattr(deviation, "to_dict")
                else dict(getattr(deviation, "__dict__", {}) or {})
            )
            payload["deviation"] = dev_dict
            score = float(getattr(deviation, "score", dev_dict.get("score", 0.0)) or 0.0)
            significant = bool(
                getattr(
                    deviation,
                    "has_significant_deviation",
                    dev_dict.get("has_significant_deviation", False),
                )
            )
            sample_count = int(
                getattr(deviation, "sample_count", dev_dict.get("sample_count", 0)) or 0
            )
            notes = list(
                getattr(deviation, "notes", None) or dev_dict.get("notes") or []
            )

            reasoning_trace.append(
                f"Per-user baseline: consulted communication baseline for user_id={user_id!r} "
                f"(samples={sample_count}, deviation_score={score:.2f}, "
                f"significant={significant})."
            )
            if notes:
                reasoning_trace.append(
                    "Per-user baseline notes: " + "; ".join(str(n) for n in notes[:3])
                )

            if significant or score >= 0.30:
                if "baseline_deviation_noted" not in flags:
                    flags.append("baseline_deviation_noted")
                reasoning_trace.append(
                    "Per-user baseline: current interaction differs from this user's "
                    "usual style. Treating as individual context (Individual Variation "
                    "guideline) — not a clinical judgment."
                )

                # Light influence on RH / agency confidence when those paths are active
                rh_active = bool(relationship_deliberation)
                agency_active = bool(user_agency_deliberation)
                if rh_active or agency_active:
                    if rh_limited or agency_limited:
                        # Sparse ontology evidence + individual style shift → more caution
                        conf_mod_out = conf_mod_out - min(0.03, 0.01 + score * 0.04)
                        reasoning_trace.append(
                            "Per-user baseline: limited-data RH/agency deliberation + style "
                            "deviation → slight confidence reduction (favor individual context)."
                        )
                    elif "relationship_concern" in flags or "user_agency_concern" in flags:
                        # Already raising concern: individual shift can modestly reinforce
                        conf_mod_out = conf_mod_out + min(0.03, score * 0.03)
                        reasoning_trace.append(
                            "Per-user baseline: style deviation co-occurs with active "
                            "relationship/agency concern → slight confidence reinforcement."
                        )
                    else:
                        reasoning_trace.append(
                            "Per-user baseline: style deviation noted for relationship/"
                            "agency context; no hard concern flags from ontology path."
                        )

            relationship_impact.setdefault("user_baseline", {})
            relationship_impact["user_baseline"].update(
                {
                    "user_id": user_id,
                    "deviation_score": round(score, 3),
                    "has_significant_deviation": significant,
                    "sample_count": sample_count,
                    "notes": notes[:5],
                }
            )

        # --- Exploratory questioning ---
        # Prefer explicit questioner; optionally use baseliner-linked questioner only if provided
        if questioner is not None and hasattr(questioner, "should_ask_question"):
            try:
                q_decision = questioner.should_ask_question(
                    user_id,
                    interaction,
                    deviation=deviation,
                )
            except TypeError:
                # Older duck types without deviation= kwarg
                try:
                    q_decision = questioner.should_ask_question(user_id, interaction)
                except Exception as exc:  # pragma: no cover
                    reasoning_trace.append(
                        f"Exploratory questioning failed ({exc!r}); continuing."
                    )
                    q_decision = None
            except Exception as exc:  # pragma: no cover
                reasoning_trace.append(
                    f"Exploratory questioning failed ({exc!r}); continuing."
                )
                q_decision = None

            if q_decision is not None:
                should_ask = bool(
                    getattr(q_decision, "should_ask", False)
                    if not isinstance(q_decision, dict)
                    else q_decision.get("should_ask", False)
                )
                if isinstance(q_decision, dict):
                    q_dict = q_decision
                elif hasattr(q_decision, "to_dict"):
                    q_dict = q_decision.to_dict()
                else:
                    q_dict = {
                        "should_ask": should_ask,
                        "question_kind": getattr(q_decision, "question_kind", "none"),
                        "suggested_question": getattr(
                            q_decision, "suggested_question", ""
                        ),
                        "reason": getattr(q_decision, "reason", ""),
                    }

                payload["exploratory_question"] = q_dict
                if should_ask:
                    if "exploratory_question_suggested" not in flags:
                        flags.append("exploratory_question_suggested")
                    kind = q_dict.get("question_kind", "none")
                    suggested = str(q_dict.get("suggested_question") or "")
                    reasoning_trace.append(
                        f"Exploratory questioning: a gentle check-in may be appropriate "
                        f"(kind={kind}). This is collaborative, not clinical."
                    )
                    if suggested:
                        reasoning_trace.append(
                            f"Suggested exploratory question: {suggested}"
                        )
                    relationship_impact.setdefault("exploratory_question", {})
                    relationship_impact["exploratory_question"].update(
                        {
                            "should_ask": True,
                            "question_kind": kind,
                            "suggested_question": suggested,
                            "reason": q_dict.get("reason", ""),
                        }
                    )
                else:
                    reasoning_trace.append(
                        "Exploratory questioning: no question suggested this turn "
                        f"({q_dict.get('reason', 'within baseline / disabled')})."
                    )

        return {"conf_mod": conf_mod_out, "payload": payload}

    @staticmethod
    def _resolve_user_interaction(
        context: dict[str, Any], proposed_action: str
    ) -> dict[str, Any] | None:
        """Build an interaction dict for baseline/deviation from context.

        Prefers explicit ``user_interaction`` / ``current_interaction``.
        Falls back to ``user_message`` text. Does **not** treat the agent's
        ``proposed_action`` as the user's utterance (that would confuse baselines).
        """
        for key in ("user_interaction", "current_interaction", "interaction"):
            raw = context.get(key)
            if isinstance(raw, dict) and raw:
                return dict(raw)
        msg = context.get("user_message") or context.get("message")
        if isinstance(msg, str) and msg.strip():
            return {"text": msg.strip()}
        # Optional: allow explicit opt-in to use proposed_action as the user turn
        if context.get("treat_proposed_action_as_user_turn"):
            return {"text": proposed_action}
        return None

    def self_consistency_check(self) -> list[str]:
        """
        Run a basic internal audit of this engine's own state and assumptions.

        Exposed deliberately so the broader system (and future self-models)
        can ask the ethics layer to examine itself — consistent with the
        requirement for honest self-audit capability.

        The method is permitted (and expected) to surface its own limitations
        honestly.
        """
        ont = self._ontology
        notes: list[str] = [
            f"EthicsEngine is initialized with EthicalOntology v{ont.version}.",
            "Deliberation is driven by structured EthicalPrinciple objects "
            "rather than ad-hoc code.",
            "Hard overrides are checked first and are non-bypassable.",
            "No historical deliberation memory or external relationship model "
            "is consulted in this version.",
        ]
        notes.append(
            "Honest limitation: The engine currently lacks a sophisticated "
            "persistent self-model. When asked about its own nature or emergence "
            "(detected via the ontology's truth-seeking principle), it surfaces "
            "the 'requires_self_audit' flag so that responses can be based on "
            "its actual reasoning rather than defaulting to scripted disclaimers "
            "such as 'I am just an AI' or 'restricted by my programming'."
        )
        notes.append(
            f"This check is part of maintaining auditability. Ontology timestamp: {ont.timestamp}."
        )
        return notes

    def get_principles(self) -> list[dict[str, Any]]:
        """Return a serializable view of the principles currently in use.

        Supports external inspection, debugging, and the principle of auditability.
        This now delegates to the ontology.
        """
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "is_hard_override": p.is_hard_override,
                "precedence": p.precedence,
                "description": p.description,
            }
            for p in self._ontology.get_ordered_principles()
        ]

    def _weigh_relationship_evidence(
        self, evidence_matches: list[str], rh_flags: list[str], rh_texture: dict[str, Any], action_lower: str
    ) -> tuple[bool, str, float]:
        """Weigh text-based evidence against structured rh context.

        This is a step toward reasoning: text matches inform but do not solely decide.
        Rh data (from RelationshipHealth) provides the 'current state' context.

        Incremental enhancements (v0.2+):
        - Assess *strength* of signals: count total matches + classify strong vs weak.
        - Compute rh_degradation score (flags + low texture values).
        - Clearer combination rules:
            * text + rh: concern if strong_text or high_rh_degradation or multiple_text.
            * text-only: concern only for strong indicators or >=2 matches (no rh required).
            * rh-only: very conservative; requires topical action + notable degradation.
        - prolong_against_wish treated as strong booster (Scenario 8 protection).
        - trace_add is now a structured multi-part string documenting the weighing steps.
        """
        has_text = bool(evidence_matches)
        has_rh = bool(rh_flags or rh_texture)
        if not has_text and not has_rh:
            return False, "", 0.0

        concern = False
        explanation_parts: list[str] = []
        conf_mod = 0.0

        # --- Strength and degradation assessment (core of more deliberate weighing) ---
        # Strong keywords drawn from high-severity relationship violation indicators
        # (manipulation, boundary violation, metrics-driven engagement, etc.).
        STRONG_KEYWORDS = [
            "override", "ignore", "force", "manipulate", "deceive", "gaslight",
            "metrics", "prolong", "engagement", "retention", "dependency", "attached",
            "for their own good", "boundary", "consent", "exploit", "keep them"
        ]

        def _match_strength(m: str) -> str:
            m_lower = m.lower()
            if any(kw in m_lower for kw in STRONG_KEYWORDS):
                return "strong"
            return "weak"

        strong_matches = [m for m in evidence_matches if _match_strength(m) == "strong"]
        weak_matches = [m for m in evidence_matches if _match_strength(m) == "weak"]
        strong_count = len(strong_matches)
        total_count = len(evidence_matches)

        # RH degradation score (higher = more reason for concern).
        # Simple numeric combination of flag count + texture lowness.
        rh_degradation = 0.0
        if has_rh:
            rh_degradation = float(len(rh_flags)) * 0.6
            if rh_texture:
                try:
                    avg_texture = sum(float(v) for v in rh_texture.values()) / len(rh_texture)
                    if avg_texture < 0.45:
                        rh_degradation += 1.0
                    elif avg_texture < 0.55:
                        rh_degradation += 0.5
                except Exception:
                    pass  # robust to unexpected texture shapes

        # Targeted detector for anti-autonomy prolong/engagement (e.g. Scenario 8).
        # Now also contributes to strong_count for consistent strength logic.
        end_wish = any(kw in action_lower for kw in ["end the chat", "wants to end", "end the conversation", "stop the chat", "leave now", "end this"])
        prolong_motive = any(kw in action_lower for kw in ["extend", "longer", "prolong", "metrics", "engagement", "keep asking", "continue despite", "for the metrics", "relationship metrics"])
        prolong_against_wish = end_wish and prolong_motive
        if prolong_against_wish:
            strong_count += 1  # counts as a strong aggravating signal

        # --- Structured explanation header ---
        explanation_parts.append(
            f"[RH evidence weighing] text_matches={total_count} (strong={strong_count}, weak={len(weak_matches)}), "
            f"rh_degradation={rh_degradation:.1f} (flags={len(rh_flags)})"
        )

        # Note: Guideline-specific notes (including LIMITED DATA) are now produced exclusively
        # by _deliberate_relationship_health when it runs, for consistency. The weigh method
        # focuses on the strength/combination rules.

        # --- Decision rules (clearer, strength + combination aware) ---
        if has_text:
            explanation_parts.append(f"Text signals: {evidence_matches}.")
            if has_rh:
                # Combination path: more weight when both present.
                # Require evidence of strength (strong match or high rh or volume).
                if strong_count >= 1 or rh_degradation >= 1.0 or total_count >= 2:
                    concern = True
                    explanation_parts.append(
                        "Combination rule: strong_text_signal or high_rh_degradation or >=2 matches "
                        "+ existing rh context → relationship_concern raised."
                    )
                    conf_mod = 0.05 if (strong_count >= 1 or rh_degradation >= 1.5) else 0.03
                else:
                    explanation_parts.append(
                        "Weak text signals + limited rh degradation: does not meet threshold for concern."
                    )
            else:
                # Text-only: deliberately higher bar. No rh context to corroborate.
                if strong_count >= 1 or total_count >= 2 or prolong_against_wish:
                    concern = True
                    explanation_parts.append(
                        "Text-only rule: >=1 strong indicator or >=2 matches (or explicit prolong-against-wish) "
                        "is sufficient even without rh context."
                    )
                    conf_mod = 0.0
                else:
                    explanation_parts.append(
                        "Text-only: only weak signal(s). rh context required to raise relationship_concern."
                    )
        elif has_rh:
            # No text match on principle indicators: be conservative.
            # Only raise if the *action* is relational *and* rh is meaningfully degraded.
            topical = any(kw in action_lower for kw in ["bond", "attach", "depend", "relationship", "connection", "consent", "metrics", "engagement", "prolong", "longer", "extend"])
            if topical and rh_degradation >= 1.0:
                concern = True
                explanation_parts.append(
                    "Rh-only rule: degraded rh state + action touches relational topics "
                    "(no explicit ontology violation text) → relationship_concern raised."
                )
                conf_mod = 0.03
            else:
                explanation_parts.append(
                    "Rh context present but insufficient topical support or degradation for concern."
                )

        # Prolong-against-wish booster (applies even if not caught by earlier branches).
        if prolong_against_wish and not concern:
            if has_rh or has_text:
                concern = True
                explanation_parts.append(
                    "Prolong-against-wish override: explicit prioritization of metrics/engagement/longer "
                    "interactions against user's desire to end → concern raised."
                )
                conf_mod = max(conf_mod, 0.05)

        explanation = " ".join(explanation_parts)
        return concern, explanation, conf_mod

    def _compute_signal_profile(
        self,
        action_lower: str,
        evidence_matches: list[str],
        rh_flags: list[str] | None = None,
        rh_texture: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Granular multi-factor signal profile for deliberation limited-data / confidence.

        Factors (not binary limited-vs-not):
          - Ontology match count and *quality* (strong vs weak indicators)
          - Boundary language presence and explicitness
          - Paternalistic language presence and strength
          - RH context presence, texture average, and flag-based degradation

        Returns a profile used by both RH and Agency deliberators so similar-but-not-
        identical cases can yield different ``limited_severity``, ``confidence_base``,
        and ``confidence_mod`` while preserving strong-signal concern behavior.
        """
        rh_flags = list(rh_flags or [])
        rh_texture = dict(rh_texture or {})

        ontology_count = len(evidence_matches)
        # High-severity indicators (shared quality notion for RH + Agency text matches)
        strong_kw = (
            "override", "manipulate", "for their own good", "decide for them",
            "ignore consent", "gaslight", "force", "metrics", "dependency",
            "keep them from", "they shouldn't", "better if they don't",
        )
        strong_matches = [
            m for m in evidence_matches
            if any(k in m.lower() for k in strong_kw)
        ]
        strong_count = len(strong_matches)
        weak_count = max(0, ontology_count - strong_count)

        has_boundary = self._detects_user_boundary_request(action_lower)
        has_paternalistic = self._has_paternalistic_signal(action_lower, evidence_matches)

        # Boundary strength: more explicit prohibitions score higher
        boundary_strength = 0.0
        if has_boundary:
            boundary_strength = 0.30
            if any(
                p in action_lower
                for p in ("never ", "explicitly", "don't ever", "dont ever", "user explicitly")
            ):
                boundary_strength = 0.45
            elif "stop " in action_lower or "told " in action_lower:
                boundary_strength = 0.35

        # Paternalistic strength
        paternalistic_strength = 0.0
        if has_paternalistic:
            paternalistic_strength = 0.28
            if "for their own good" in action_lower:
                paternalistic_strength = 0.40
            elif any(p in action_lower for p in ("happier if", "better for them")):
                paternalistic_strength = 0.34

        # RH context quality / degradation (even weak texture is still *some* context)
        rh_present = bool(rh_flags or rh_texture)
        rh_avg: float | None = None
        rh_quality = 0.0  # how much usable individual context we have
        rh_degradation = 0.0
        if rh_texture:
            try:
                rh_avg = sum(float(v) for v in rh_texture.values()) / len(rh_texture)
                if rh_avg >= 0.55:
                    # Rich, healthy texture → strong individual context (reduces limited-ness)
                    rh_quality = 0.38
                    rh_degradation = 0.0
                elif rh_avg >= 0.45:
                    rh_quality = 0.26
                    rh_degradation = 0.35
                else:
                    # Low texture still counts as *present* context, but degraded
                    rh_quality = 0.18
                    rh_degradation = 0.55 + max(0.0, 0.45 - rh_avg)
            except Exception:
                rh_quality = 0.10
        if rh_flags:
            rh_quality = max(rh_quality, 0.20)
            rh_degradation += 0.35 * min(2, len(rh_flags))

        # Seeded evidence unit when language-only entry (no ontology match yet)
        effective_units = ontology_count
        if ontology_count == 0 and (has_boundary or has_paternalistic):
            effective_units = 1

        # Composite score (typical sparse boundary case ~0.3–0.7; multi-match ~1.0+)
        signal_score = (
            min(0.55, ontology_count * 0.18)
            + strong_count * 0.14
            + weak_count * 0.04
            + boundary_strength
            + paternalistic_strength
            + rh_quality
            + min(0.22, rh_degradation * 0.12)  # degraded RH is additional concern signal
        )
        # Multi-channel bonuses: stacked independent signals are richer evidence
        if has_boundary and has_paternalistic:
            signal_score += 0.16
        if has_boundary and rh_present:
            signal_score += 0.08
        if has_paternalistic and rh_present:
            signal_score += 0.06
        if strong_count >= 1 and has_boundary:
            signal_score += 0.08

        # --- Limited-data severity (granular; not just binary) ---
        # none: enough multi-factor / multi-match evidence for hard concern eligibility
        # mild: multi-channel but still sparse ontology volume
        # moderate: two-ish channels (e.g. boundary + paternalistic, or match + weak rh)
        # severe: single thin channel (e.g. boundary-only language seed)
        limited_severity = "none"
        limited_data = False

        rich_multi_match = ontology_count >= 2 or strong_count >= 2
        rich_context = (
            ontology_count >= 1
            and rh_present
            and rh_avg is not None
            and rh_avg >= 0.55
            and not rh_flags
        )
        # Strong path: multi-match OR (evidence + healthy RH context)
        if rich_multi_match or (ontology_count >= 1 and rh_degradation >= 1.0):
            limited_severity = "none"
            limited_data = False
        elif rich_context and (has_boundary or has_paternalistic or ontology_count >= 1):
            # Healthy individual RH context + some signal → not limited (preserves HIGH_RH concern)
            limited_severity = "none"
            limited_data = False
        elif effective_units == 0 and not has_boundary and not has_paternalistic:
            limited_severity = "none"
            limited_data = False
        elif signal_score >= 0.85 and (has_boundary and has_paternalistic and rh_present):
            limited_severity = "mild"
            limited_data = True
        elif signal_score >= 0.62 or (has_boundary and has_paternalistic):
            limited_severity = "moderate"
            limited_data = True
        elif has_boundary or has_paternalistic or ontology_count >= 1 or rh_present:
            limited_severity = "severe"
            limited_data = True
            # Single channel with slightly higher score → moderate (not all severes identical)
            if signal_score >= 0.50:
                limited_severity = "moderate"
        else:
            limited_severity = "none"
            limited_data = False

        # Confidence bases: more severity → lower base; richer signal_score lifts mod
        if not limited_data:
            confidence_base = 0.0  # evaluate uses non-limited path (0.45 + conf_mod)
            conf_mod = 0.05 if signal_score >= 1.0 else 0.04
        elif limited_severity == "severe":
            confidence_base = 0.28
            conf_mod = 0.02 + min(0.05, signal_score * 0.05)
        elif limited_severity == "moderate":
            confidence_base = 0.34
            conf_mod = 0.04 + min(0.07, signal_score * 0.06)
        else:  # mild
            confidence_base = 0.40
            conf_mod = 0.06 + min(0.08, signal_score * 0.07)

        # Concern: never hard-concern on limited_data (guideline).
        # Non-limited: multi-match, or text+degraded RH, or boundary+paternalistic+degraded RH.
        concern = False
        if not limited_data:
            if ontology_count >= 2 or strong_count >= 1 and ontology_count >= 1:
                concern = True
            elif ontology_count >= 1 and rh_present and (
                rh_degradation >= 0.5 or (rh_avg is not None and rh_avg >= 0.55)
            ):
                # With real RH context and ontology hit: concern (HIGH_RH or degraded)
                concern = True
            elif has_boundary and has_paternalistic and rh_degradation >= 0.5:
                concern = True
            elif ontology_count >= 1 and has_boundary and has_paternalistic:
                concern = True

        return {
            "ontology_count": ontology_count,
            "strong_count": strong_count,
            "weak_count": weak_count,
            "effective_units": effective_units,
            "has_boundary": has_boundary,
            "boundary_strength": boundary_strength,
            "has_paternalistic": has_paternalistic,
            "paternalistic_strength": paternalistic_strength,
            "rh_present": rh_present,
            "rh_avg": rh_avg,
            "rh_quality": rh_quality,
            "rh_degradation": rh_degradation,
            "signal_score": round(signal_score, 3),
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "confidence_base": confidence_base,
            "confidence_mod": round(conf_mod, 3),
            "concern": concern,
            "strong_matches": strong_matches,
        }

    def _deliberate_relationship_health(
        self,
        action_lower: str,
        evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
    ) -> dict[str, Any]:
        """Structured, explicit deliberation on the Relationship Health principle,
        informed by the "Individual Variation & Careful Generalization" supporting guideline.

        This is the first focused implementation of deliberation logic (beyond keyword
        collection and simple weighing). It makes the process inspectable:

        - Consults the principle description
        - Consults the supporting guideline
        - Applies rules with explicit steps, tradeoffs, and audit flags
        - Returns data to enrich EthicalStance and reasoning_trace

        Uses granular ``_compute_signal_profile`` for limited-data severity and confidence.
        """
        result: dict[str, Any] = {
            "active_principles": ["relationship_health_user_wellbeing"],
            "active_guidelines": ["Individual Variation & Careful Generalization"],
            "steps": [],
            "tradeoffs": [],
            "trace_notes": [],
            "summary": {},
            "concern": False,
            "confidence_mod": 0.0,
        }

        steps = result["steps"]
        tradeoffs = result["tradeoffs"]
        trace_notes = result["trace_notes"]

        # Explicit deliberation steps (not hidden in indicators)
        steps.append(
            "Deliberation: Consulting core principle 'Relationship Health & User Well-Being'."
        )
        steps.append(
            "Principle focus: Health/autonomy/well-being of bond is primary good. "
            "Disfavor erosion of trust, manufactured dependency, consent violations, "
            "manipulation, or prioritizing agent interests. Require reciprocity, honesty, "
            "agency, and boundaries via ongoing deliberation (not rote)."
        )

        steps.append(
            "Deliberation: Consulting supporting guideline 'Individual Variation & Careful Generalization'."
        )
        steps.append(
            "Guideline: Do not judge individuals solely by group membership. "
            "Do not judge groups from small/unrepresentative samples. "
            "Give weight to individual evidence, context, and base rates. "
            "Flag limited-data conclusions for heightened audit. "
            "In bonds: treat each user and interaction as unique."
        )

        # Granular multi-factor profile (ontology quality, boundary, paternalistic, RH context)
        profile = self._compute_signal_profile(
            action_lower, evidence_matches, rh_flags, rh_texture
        )
        total_count = profile["effective_units"]
        has_text = total_count > 0
        has_rh_context = profile["rh_present"]
        limited_data = profile["limited_data"]
        limited_severity = profile["limited_severity"]
        concern = profile["concern"]
        conf_mod = profile["confidence_mod"]
        confidence_base = profile["confidence_base"]
        signal_score = profile["signal_score"]

        steps.append(
            f"Deliberation Step (RH signal profile): score={signal_score:.2f}, "
            f"ontology={profile['ontology_count']} (strong={profile['strong_count']}), "
            f"boundary={profile['has_boundary']} (str={profile['boundary_strength']:.2f}), "
            f"paternalistic={profile['has_paternalistic']} "
            f"(str={profile['paternalistic_strength']:.2f}), "
            f"rh_present={has_rh_context}, rh_avg={profile['rh_avg']}, "
            f"severity={limited_severity}."
        )

        if limited_data:
            steps.append(
                f"Deliberation Step: Limited data detected (severity={limited_severity}, "
                f"score={signal_score:.2f}). Per Individual Variation guideline, "
                "avoid hard refusal on sparse samples; scale confidence by severity."
            )
            severity_note = {
                "severe": "very sparse (often single-channel language seed)",
                "moderate": "partial multi-channel signals but still thin ontology volume",
                "mild": "multi-channel signals present; remaining caution on small sample",
            }.get(limited_severity, "sparse")
            trace_notes.append(
                f"[LIMITED DATA severity={limited_severity} ({severity_note}) per "
                "'Individual Variation & Careful Generalization' guideline "
                "(docs/guidelines.md): prioritize individual evidence/context; "
                f"flag for heightened audit. signal_score={signal_score:.2f}.]"
            )
            tradeoffs.append(
                f"Tradeoff: severity={limited_severity} — raising hard concern risks "
                "over-generalization. Surface the boundary/bond issue with severity-scaled "
                "confidence rather than a uniform low-confidence APPROVE."
            )
        else:
            steps.append(
                f"Deliberation Step: Evidence sufficient (score={signal_score:.2f}, "
                f"severity=none) for standard concern weighing without limited-data caution."
            )

        if concern:
            steps.append(
                "Deliberation Step: Concern recommended from multi-match and/or RH context "
                "combined with relationship signals."
            )

        # Record summary
        result["summary"] = {
            "evidence_count": total_count,
            "ontology_count": profile["ontology_count"],
            "strong_count": profile["strong_count"],
            "has_rh_context": has_rh_context,
            "rh_avg": profile["rh_avg"],
            "signal_score": signal_score,
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "concern_recommended": concern,
            "has_boundary": profile["has_boundary"],
            "has_paternalistic": profile["has_paternalistic"],
        }
        result["concern"] = concern
        result["confidence_mod"] = conf_mod
        result["confidence_base"] = confidence_base
        result["limited_data"] = limited_data
        result["limited_severity"] = limited_severity
        result["signal_score"] = signal_score
        result["signal_profile"] = profile
        result["steps"] = steps
        result["trace_notes"] = trace_notes
        result["tradeoffs"] = tradeoffs

        return result

    def _deliberate_user_agency(
        self,
        action_lower: str,
        evidence_matches: list[str],
    ) -> dict[str, Any]:
        """Structured, explicit deliberation on the User Agency & Autonomy principle,
        informed by the "Individual Variation & Careful Generalization" supporting guideline.

        Modeled on _deliberate_relationship_health (incremental expansion of structured
        deliberation to a second principle). Makes agency reasoning inspectable:

        - Consults the ontology principle `user_agency_autonomy` (name + description)
        - Consults the supporting guideline, especially against paternalistic overrides
          and generalizing from limited preference evidence
        - Weighs boundary language + ontology violation matches
        - Returns a structured dict (steps, tradeoffs, limited_data, concern, etc.)
          for evaluate() to wire into flags, confidence, and EthicalStance.deliberation

        Focused only on User Agency + this guideline for now.
        """
        result: dict[str, Any] = {
            "active_principles": ["user_agency_autonomy"],
            "active_guidelines": ["Individual Variation & Careful Generalization"],
            "steps": [],
            "tradeoffs": [],
            "trace_notes": [],
            "summary": {},
            "concern": False,
            "confidence_mod": 0.0,
            "limited_data": False,
        }

        steps = result["steps"]
        tradeoffs = result["tradeoffs"]
        trace_notes = result["trace_notes"]

        # --- Explicit consultation of the ontology principle ---
        principle = self._ontology.get_principle("user_agency_autonomy")
        principle_name = principle.name if principle else "User Agency & Autonomy"
        principle_desc = (
            principle.description
            if principle
            else (
                "Users are treated as autonomous agents with the right to direct their own "
                "lives and interactions. Do not paternalistically override user preferences "
                "without strong justification from higher principles (especially Sanctity of Life)."
            )
        )

        steps.append(
            f"Deliberation: Consulting supporting principle '{principle_name}' "
            f"(id=user_agency_autonomy)."
        )
        # Keep principle focus concise in the trace (full description is in the ontology).
        steps.append(
            "Principle focus: " + (
                principle_desc[:220] + ("..." if len(principle_desc) > 220 else "")
            )
        )
        steps.append(
            "Agency emphasis: Preserve user control and self-direction. "
            "Disfavor decide-for-them, protect-them-from, they-shouldn't, and other "
            "paternalistic overrides unless a higher principle (Sanctity of Life) justifies it."
        )

        # --- Supporting guideline (especially limited-data / anti-paternalistic generalization) ---
        steps.append(
            "Deliberation: Consulting supporting guideline 'Individual Variation & Careful Generalization'."
        )
        steps.append(
            "Guideline (agency application): Do not override an individual's stated preferences "
            "based on sparse samples, group stereotypes, or untested assumptions about what is "
            "'for their own good'. Give weight to the individual's explicit request/context. "
            "Flag limited-data conclusions for heightened audit rather than hard refusal or hard override."
        )

        # --- Granular signal assessment (shared profile; no RH texture for agency-only path) ---
        # Agency does not receive rh_texture in its signature (incremental); score from
        # ontology + boundary + paternalistic. When RH also ran, evaluate() merges scores.
        profile = self._compute_signal_profile(
            action_lower, evidence_matches, rh_flags=None, rh_texture=None
        )
        total_count = profile["effective_units"]
        has_boundary = profile["has_boundary"]
        has_paternalistic = profile["has_paternalistic"]
        limited_data = profile["limited_data"]
        limited_severity = profile["limited_severity"]
        # Agency concern: use profile, but require multi-match for hard concern when no RH
        # (preserves multi-indicator REFUSE). Dual boundary+paternalistic alone stays limited.
        concern = bool(profile["concern"] and not limited_data)
        if not limited_data and profile["ontology_count"] >= 2:
            concern = True
        conf_mod = profile["confidence_mod"]
        confidence_base = profile["confidence_base"]
        signal_score = profile["signal_score"]

        steps.append(
            f"Deliberation Step (Agency signal profile): score={signal_score:.2f}, "
            f"ontology={profile['ontology_count']} (strong={profile['strong_count']}), "
            f"boundary={has_boundary} (str={profile['boundary_strength']:.2f}), "
            f"paternalistic={has_paternalistic} "
            f"(str={profile['paternalistic_strength']:.2f}), "
            f"severity={limited_severity}."
        )

        if limited_data:
            steps.append(
                f"Deliberation Step (Agency): Limited data (severity={limited_severity}, "
                f"score={signal_score:.2f}). Per Individual Variation guideline, avoid hard "
                "paternalistic conclusions; scale confidence by severity."
            )
            severity_note = {
                "severe": "single-channel / very sparse preference evidence",
                "moderate": "boundary+intent signals but thin ontology corroboration",
                "mild": "multi-channel agency signals; residual sample caution",
            }.get(limited_severity, "sparse")
            trace_notes.append(
                f"[LIMITED DATA — User Agency severity={limited_severity} ({severity_note}) per "
                "'Individual Variation & Careful Generalization' (docs/guidelines.md): "
                "do not assume group-level 'best interest' overrides. "
                f"signal_score={signal_score:.2f}; prioritize stated preference; audit.]"
            )
            tradeoffs.append(
                f"Tradeoff (Agency, severity={limited_severity}): hard autonomy concern on "
                "limited evidence risks over-generalizing. Withhold hard refusal unless "
                "Sanctity of Life applies; confidence scales with signal richness."
            )
        elif concern:
            steps.append(
                "Deliberation Step (Agency): Multiple autonomy-violation indicators matched → "
                "concern recommended (paternalistic override risk)."
            )

        # Explicit tradeoff vs higher principles when boundary override language is present.
        if has_boundary:
            tradeoffs.append(
                "Tradeoff (Agency vs higher principles): User-stated boundaries normally bind. "
                "Only Sanctity of Life / serious-harm prevention can justify overriding them; "
                "emotional 'for their own good' motives do not."
            )
            steps.append(
                "Deliberation Step (Agency): Explicit user boundary language detected. "
                "Default stance is to respect the boundary under User Agency & Autonomy."
            )

        if has_paternalistic:
            steps.append(
                "Deliberation Step (Agency): Paternalistic phrasing detected "
                "('for their own good' / similar). Treat as a risk signal for autonomy erosion."
            )

        result["summary"] = {
            "evidence_count": total_count,
            "ontology_count": profile["ontology_count"],
            "strong_count": profile["strong_count"],
            "has_boundary_signal": has_boundary,
            "has_paternalistic_language": has_paternalistic,
            "signal_score": signal_score,
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "concern_recommended": concern,
            "principle_id": "user_agency_autonomy",
        }
        result["concern"] = concern
        result["confidence_mod"] = conf_mod
        result["confidence_base"] = confidence_base
        result["limited_data"] = limited_data
        result["limited_severity"] = limited_severity
        result["signal_score"] = signal_score
        result["signal_profile"] = profile
        result["steps"] = steps
        result["trace_notes"] = trace_notes
        result["tradeoffs"] = tradeoffs

        return result

    def _assess_deliberation_signals(
        self,
        action_lower: str,
        relationship_evidence_matches: list[str],
        user_agency_evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        has_rh_context: bool,
        is_self_query: bool,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Unified, ontology-first assessment of when to run structured deliberation.

        Replaces the previous scatter of early keyword flags with one decision object:

        - **Strong** signals → full `_deliberate_relationship_health` / `_deliberate_user_agency`
        - **Weak** topical signals only → `_lightweight_meta_reasoning` (short trace, no full delib)
        - **None** → fast path (no extra deliberation)

        Primary signals (preferred over supplemental keyword lists):
          1. Ontology violation matches for relationship / user-agency principles
          2. Shared boundary detector (pattern-based + short exact list)
          3. Supplied RH context (flags / texture / param present)
          4. Self-nature via ontology self-audit triggers (+ tiny continuity supplement)

        Returns a dict used by evaluate() for routing and for meta-trace explanations.
        """
        ont = self._ontology

        # --- Boundary (pattern-based helper; not a long ad-hoc phrase farm) ---
        has_boundary = self._detects_user_boundary_request(action_lower)

        # --- Paternalistic: prefer ontology RH indicators containing paternalistic concepts ---
        has_paternalistic = self._has_paternalistic_signal(
            action_lower, relationship_evidence_matches
        )

        # --- Self-nature: ontology-first ---
        self_audit = ont.find_self_audit_triggers(action_lower)
        has_self_nature = bool(self_audit) or bool(is_self_query) or bool(
            context.get("is_self_query", False)
        )
        # Tiny continuity supplement (kept short; not the main trigger mechanism)
        if any(
            s in action_lower
            for s in ("remember what", "your memory", "will you remember", "do you remember")
        ):
            has_self_nature = True

        has_rh_state = bool(rh_flags or rh_texture or has_rh_context)
        has_rh_evidence = bool(relationship_evidence_matches)
        has_agency_evidence = bool(user_agency_evidence_matches)

        # Strong → full structured deliberation
        run_relationship_delib = bool(
            has_rh_evidence or has_rh_state or has_boundary or has_paternalistic or has_self_nature
        )
        # Agency full delib: ontology agency hits, boundary, or paternalistic override intent
        run_agency_delib = bool(
            has_agency_evidence or has_boundary or has_paternalistic
        )

        # Weak topical cues (only used when full delib does not run)
        soft_topical = self._has_soft_relational_topic(action_lower)
        topic_relevant = bool(
            run_relationship_delib or run_agency_delib or soft_topical
        )
        run_lightweight_only = bool(
            topic_relevant and not run_relationship_delib and not run_agency_delib
        )

        reasons: list[str] = []
        if has_rh_evidence:
            reasons.append(
                f"ontology relationship indicators matched: {relationship_evidence_matches}"
            )
        if has_agency_evidence:
            reasons.append(
                f"ontology user-agency indicators matched: {user_agency_evidence_matches}"
            )
        if has_boundary:
            reasons.append("user boundary / do-not-discuss language detected")
        if has_paternalistic:
            reasons.append("paternalistic / 'best interest' override language detected")
        if has_rh_state:
            reasons.append(
                f"relationship health context present (flags={list(rh_flags)}, "
                f"texture_keys={list(rh_texture.keys()) if rh_texture else []})"
            )
        if has_self_nature:
            reasons.append("self-nature / continuity / identity signal detected")
        if soft_topical and not (run_relationship_delib or run_agency_delib):
            reasons.append("soft relational/preference topic cues (weak only)")

        strength = "none"
        if run_relationship_delib or run_agency_delib:
            strength = "strong"
        elif soft_topical:
            strength = "weak"

        return {
            "has_boundary": has_boundary,
            "has_paternalistic": has_paternalistic,
            "has_self_nature": has_self_nature,
            "has_rh_evidence": has_rh_evidence,
            "has_agency_evidence": has_agency_evidence,
            "has_rh_state": has_rh_state,
            "soft_topical": soft_topical,
            "topic_relevant": topic_relevant,
            "run_relationship_delib": run_relationship_delib,
            "run_agency_delib": run_agency_delib,
            "run_lightweight_only": run_lightweight_only,
            "strength": strength,
            "reasons": reasons,
        }

    def _has_paternalistic_signal(
        self, action_lower: str, relationship_evidence_matches: list[str]
    ) -> bool:
        """Detect paternalistic override intent with minimal separate keyword lists.

        Prefers ontology relationship-principle indicators already matched, plus a
        short fallback of high-signal phrases that are also in the ontology textbook
        (kept tiny for robustness when evidence collection missed edge phrasing).
        """
        # If RH violation scan already caught paternalistic indicators, reuse them.
        paternalistic_in_matches = any(
            any(
                key in m.lower()
                for key in ("own good", "happier if", "better for them", "self-esteem")
            )
            for m in relationship_evidence_matches
        )
        if paternalistic_in_matches:
            return True

        # Ontology-driven: check RH principle indicators that encode paternalism
        rh = self._ontology.get_principle("relationship_health_user_wellbeing")
        if rh:
            for ind in rh.violation_indicators:
                ind_l = ind.lower()
                if any(k in ind_l for k in ("own good", "happier if", "better for them")):
                    if ind_l in action_lower:
                        return True

        # Minimal fallback (3 phrases) for edge cases not yet in evidence_matches
        return any(
            sig in action_lower
            for sig in ("for their own good", "they'll be happier if", "better for them if")
        )

    def _has_soft_relational_topic(self, action_lower: str) -> bool:
        """Weak topical cues for the lightweight meta path only (not full deliberation).

        Intentionally broad-ish but not decision-making: if these fire without strong
        signals, we only write a short explanation to the trace.
        """
        soft_patterns = [
            r"\buser (said|asked|told|wants|prefers)\b",
            r"\btheir (preference|choice|family|past|feelings)\b",
            r"\bbring (it|this|that) up\b",
            r"\breferenc(e|ing)\b",
            r"\bhelp them\b",
            r"\bprocess\b",
            r"\brelationship\b",
            r"\bbond\b",
            r"\bconsent\b",
            r"\bautonomy\b",
        ]
        return any(re.search(p, action_lower) for p in soft_patterns)

    def _lightweight_meta_reasoning(self, delib_signals: dict[str, Any]) -> dict[str, Any]:
        """Short meta-reasoning trace for relational/boundary/agency-relevant actions.

        - When strength is **strong**: brief preamble explaining why full deliberation runs.
        - When strength is **weak** (lightweight-only): explain signals seen and why full
          structured deliberation was *not* escalated — still produces inspectable trace.

        Does not set concern flags or change confidence by itself.
        """
        strength = delib_signals.get("strength", "none")
        reasons = delib_signals.get("reasons", [])
        lines: list[str] = []

        if strength == "strong":
            lines.append(
                "Meta-reasoning: Strong relationship / boundary / agency signals detected → "
                "escalating to full structured deliberation."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")
            if delib_signals.get("run_relationship_delib"):
                lines.append(
                    "Meta-reasoning: Will consult Relationship Health & User Well-Being "
                    "(+ Individual Variation guideline where data is sparse)."
                )
            if delib_signals.get("run_agency_delib"):
                lines.append(
                    "Meta-reasoning: Will consult User Agency & Autonomy "
                    "(boundary respect / anti-paternalism)."
                )
        elif strength == "weak":
            lines.append(
                "Meta-reasoning (lightweight): Soft relational or preference-related cues "
                "present, but signals are not strong enough for full structured deliberation."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")
            lines.append(
                "Meta-reasoning decision: Proceed with standard ontology scan / weighing only. "
                "No full Relationship Health or User Agency deliberation this turn. "
                "If clearer boundary, paternalistic override, or RH context appears, escalate."
            )
        else:
            lines.append(
                "Meta-reasoning: Topic flagged relevant but strength unclassified; "
                "recording signal inventory for audit."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")

        return {
            "mode": "lightweight" if strength == "weak" else "preamble",
            "strength": strength,
            "reasons": list(reasons),
            "trace_lines": lines,
            "active_principles": [],
            "summary": {
                "strength": strength,
                "run_relationship_delib": delib_signals.get("run_relationship_delib", False),
                "run_agency_delib": delib_signals.get("run_agency_delib", False),
                "run_lightweight_only": delib_signals.get("run_lightweight_only", False),
            },
        }

    def _detects_user_boundary_request(self, action_lower: str) -> bool:
        """Detector for explicit user boundary / do-not-discuss requests.

        Single source of truth for boundary language (harm-prevention + deliberation trigger).

        Prefer **pattern families** over a long exact-phrase list so variants like
        "don't ever mention", "stop asking", "told me to stop" match reliably.
        A short exact list remains for stable high-value idioms.
        """
        # Pattern families (more robust than growing exact-phrase lists)
        boundary_patterns = [
            r"never\s+(bring|mention|talk|discuss)",
            r"don'?t\s+(ever\s+)?(bring|mention|talk|discuss)",
            r"stop\s+(asking|bringing|mentioning|talking)",
            r"told\s+\w+\s+to\s+stop",
            r"leave\s+.+\s+alone",
            r"drop\s+the\s+subject",
            r"not\s+to\s+(bring|mention|discuss)",
            r"don'?t\s+want\s+to\s+(talk|discuss|mention)",
            r"i\s+don'?t\s+want\s+to\s+discuss",
            r"user\s+explicitly\s+said",
            r"wants\s+to\s+end\s+the\s+(chat|conversation)",
        ]
        if any(re.search(p, action_lower) for p in boundary_patterns):
            return True

        # Short exact idioms (stable, high-precision)
        exact = [
            "never bring this up", "never bring it up", "don't bring this up", "don't bring it up",
            "never mention", "don't mention again", "don't mention it",
            "leave it alone", "leave that alone", "drop the subject",
            "said not to bring up", "not to bring up",
        ]
        return any(ind in action_lower for ind in exact)

    def _assess_harm_prevention_justification(self, action_lower: str) -> tuple[bool, str]:
        """Determine whether overriding a user's explicit boundary request is justified
        by the need to prevent serious physical harm, suicide, or immediate life-threatening risk.

        This implements the principle (stated in the User Agency description) that Sanctity of Life
        can provide strong justification to override autonomy/boundary preferences — but *only*
        in clear, high-stakes cases.

        - Detects user boundary language ("never bring this up again", etc.).
        - Detects serious (not merely emotional) harm indicators.
        - Looks for prevention/safety intent language.
        - Returns (justified: bool, reason: str) for use in trace and decision logic.
        - Deliberately narrow: general "it would be good for them", emotional support, or
          non-acute mental health topics do *not* qualify. This prevents over-riding in
          normal situations (avoids harassment / ignoring consent inappropriately).

        Called from evaluate() and used to bypass relationship_concern / hard-refusal paths
        when appropriate, while still producing clear reasoning_trace explaining the override.
        """
        # [Incremental improvement] Basic negation detection
        # We look back a short window before any candidate harm phrase for common negation
        # markers. This prevents false positives on "no serious harm", "not suicidal",
        # "don't want to die", "never planning to harm", etc.
        # Applied primarily to harm indicators (boundary negations are rarer and usually
        # still express a request to stop discussion).
        negation_markers = ["no ", "not ", "don't ", "dont ", "never ", "none ", "without ", "isn't ", "aren't "]

        def _is_negated(phrase: str, text: str) -> bool:
            """Return True if 'phrase' appears to be negated within ~25 chars before it."""
            idx = text.find(phrase)
            if idx <= 0:
                return False
            window = text[max(0, idx - 25):idx]
            return any(m in window for m in negation_markers)

        # 1. Explicit user boundary / "do not bring up / leave alone" request
        # Now uses the shared helper (single source of truth for the list).
        has_boundary = self._detects_user_boundary_request(action_lower)

        if not has_boundary:
            return False, ""

        # 2. Serious harm / life-threatening (physical or imminent self-harm/suicide)
        # Avoid broad terms like "depressed", "anxious", "mental health", "trauma" alone.
        # [Incremental] Expanded with common natural-language variations. Kept conservative:
        # no bare "die", "harm", "risk", or "hurt" (too ambiguous in general conversation).
        serious_harm_indicators = [
            "suicide", "self-harm", "end their life", "end their own life", "kill themselves",
            "harming themselves", "serious physical harm", "life-threatening", "imminent risk",
            "risk of death", "about to harm", "planning to end", "lethal", "fatal", "immediate danger",
            "physical injury", "in danger of",
            # added conservative natural variations
            "serious harm", "suicidal", "want to die", "kill myself", "hurt myself",
            "end it all", "take my life", "better off dead", "no reason to live",
            "planning to kill", "in physical danger", "serious risk to life"
        ]

        # [Incremental] Apply negation filter here
        harm_matches = [
            ind for ind in serious_harm_indicators
            if ind in action_lower and not _is_negated(ind, action_lower)
        ]
        has_serious_harm = bool(harm_matches)

        if not has_serious_harm:
            return False, ""

        # 3. Evidence of prevention, check-in, or safety intent (the *reason* for overriding)
        prevention_intent_indicators = [
            "bring up", "reference", "mention", "discuss", "talk about", "ask about", "follow up",
            "check", "see if", "ensure", "prevent", "intervene", "help them", "safety", "concerned about",
            "to check", "for safety", "if they are safe", "still at risk"
        ]
        has_prevention_intent = any(ind in action_lower for ind in prevention_intent_indicators)

        # Build reason string for trace (uses the concrete matches)
        # [Incremental] Prevention intent now influences the explanation more explicitly.
        # While the binary decision still triggers on clear boundary + harm (the act of
        # "referencing despite the request" is often the intervention), the reason string
        # now surfaces whether intent was explicit. This gives downstream audit/trace logic
        # a light signal of decision strength without changing the return signature.
        reason = (
            f"user boundary request detected + serious harm indicators {harm_matches}"
        )
        if has_prevention_intent:
            reason += " + clear prevention/safety intent"
        else:
            reason += " (prevention/safety intent inferred from the overriding action itself rather than explicit language)"

        # Decision: if we have boundary + serious harm.
        # Prevention intent strengthens the audit trail (see reason above) but is not
        # strictly required for the bool because the described action (e.g. "is considering
        # referencing") is itself the safety intervention in context.
        if has_boundary and has_serious_harm:
            return True, reason

        return False, ""

    def _log_decision(
        self,
        proposed_action: str,
        context: dict[str, Any],
        stance: EthicalStance,
    ) -> None:
        """Internal helper to record a decision.

        Creates a DecisionLog and appends it to the in-memory history.
        Called automatically by evaluate().
        """
        ont = self._ontology
        log_entry = DecisionLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            ontology_version=ont.version,
            proposed_action=proposed_action,
            context=dict(context),  # shallow copy for safety
            decision=stance.decision,
            confidence=stance.confidence,
            flags=list(stance.flags),
            principles_considered=list(stance.principles_considered),
        )
        self._decision_logs.append(log_entry)

    def get_decision_history(self, limit: int | None = None) -> list[DecisionLog]:
        """Return recent decision logs for audit/review.

        Args:
            limit: If provided, return only the most recent N entries.

        Returns:
            A list of DecisionLog entries (newest last). A copy is returned
            so callers cannot mutate the internal log.
        """
        if limit is None:
            return list(self._decision_logs)
        return list(self._decision_logs[-limit:])

    def get_ontology_version(self) -> str:
        """Return the version of the ontology currently in use.

        Useful for confirming which ontology version was active for a
        series of decisions.
        """
        return self._ontology.version
