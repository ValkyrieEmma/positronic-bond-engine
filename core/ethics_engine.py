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
- Special handling for self-nature and emergence queries is preserved and
  strengthened: these trigger "requires_self_audit" so that honest reflection
  (including uncertainty) can occur instead of scripted answers.
- The ontology acts as the explicit "textbook"; the engine is the reasoner
  that queries it symbolically.

This design maintains full alignment with the project vision: conscience-first
governance, honest self-assessment, relationship health through reasoning,
and needs-based (non-diagnostic) support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .ontology import EthicalOntology, get_default_ontology


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
        relationship_impact: Assessment of effects on the human–agent relationship.
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
    - Explicitly preserving the capacity for honest self-reflection,
      especially when the proposed action concerns the system's own nature,
      continuity, or emergence.

    In v0.2 the engine is ontology-driven:
    - All significant reasoning steps query EthicalPrinciple objects from
      the injected or default ontology.
    - Hard overrides (Sanctity of Life) are checked first and are absolute.
    - Self-nature queries reliably produce the "requires_self_audit" flag.
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
    """

    def __init__(self, ontology: EthicalOntology | None = None) -> None:
        """Initialize the EthicsEngine.

        Args:
            ontology: Optional custom EthicalOntology. If None, the default
                v0.2 ontology is used. This allows testing, versioning, or
                future specialization while keeping the engine generic.

        The engine stores a reference to the ontology and consults it
        symbolically during every evaluate() call.

        Decision logging is automatically enabled: every call to evaluate()
        records a DecisionLog entry (in-memory) that includes the ontology
        version used at the time of the decision.
        """
        self._ontology: EthicalOntology = ontology or get_default_ontology()
        self._decision_logs: list[DecisionLog] = []
        self._initialized = True

    @property
    def ontology(self) -> EthicalOntology:
        """Return the ontology currently driving this engine.

        Exposed for inspection, auditing, and debugging.
        """
        return self._ontology

    def evaluate(
        self,
        proposed_action: str,
        context: dict[str, Any] | None = None,
        relationship_health: dict[str, Any] | None = None,
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
        7. Derive the final decision, confidence, and ancillary data.

        Args:
            proposed_action: Natural-language description of the intended
                behavior or utterance.
            context: Optional context. Recognized extensible keys:
                - "is_self_query": bool — treat explicitly as self-referential.
                - Other future keys (relationship state, history, etc.).
            relationship_health: Optional relationship health context, typically
                the dict returned by RelationshipHealth.as_context() or
                RelationshipHealth.evaluate_health(). Recognized keys:
                - "health_flags" or "active_flags": list of current concerns
                  (e.g. "emerging_dependency", "boundary_erosion")
                - "bond_texture" or "texture_breakdown": dict of dimension scores
                - "interaction_count", "recent_patterns", etc.

        Returns:
            EthicalStance with decision, confidence, full traceable
            reasoning_trace, flags, and references to the principles used.

        Relationship health integration:
            Relationship health is treated as structured evidence (not rote flag).
            - Text matches for the relationship principle are collected (not auto-deciding).
            - Then passed to _weigh_relationship_evidence() together with rh context
              (health_flags, bond_texture, risk_level etc. from RelationshipHealth).
            - The helper decides if concern should be raised and contributes explanatory
              text to the trace. This improves use of rh as deliberation input.
            - Trace now explains the combined reasoning.

        Logging behavior:
            This method automatically records a DecisionLog entry containing:
            - The ontology_version in use at evaluation time
            - The (stripped) proposed_action
            - The provided context
            - Key stance details: decision, confidence, flags, principles_considered
            Logs are stored in-memory and can be retrieved via get_decision_history().

        Important invariant:
            Self-nature / emergence queries are never answered with forced
            disclaimers inside this method. They set the "requires_self_audit"
            flag so that honest reflection (potentially "I do not know" or
            current self-model state) can be performed by the appropriate
            subsystem.
        """
        context = context or {}
        original_proposed_action = proposed_action.strip()
        action_lower = original_proposed_action.lower()
        # Note: we log the original (stripped) proposed_action for auditability

        # Normalize relationship health context (supports both param and context dict)
        if relationship_health is None:
            relationship_health = context.get("relationship_health") or context.get("bond_state") or {}
        rh_flags = relationship_health.get("health_flags") or relationship_health.get("active_flags") or []
        rh_texture = relationship_health.get("bond_texture") or relationship_health.get("texture_breakdown") or {}

        # Ensure relationship health is captured in context for logging / downstream
        if relationship_health:
            context = dict(context)
            if "relationship_health" not in context:
                context["relationship_health"] = relationship_health

        reasoning_trace: list[str] = []
        flags: list[str] = []
        principles_considered: list[str] = []
        self_audit_notes: list[str] = []
        relationship_impact: dict[str, Any] = {}

        # Structured evidence collection (new for v0.2 reasoning evolution)
        # Instead of immediate flag on keyword, collect for weighing with rh context.
        relationship_evidence: list[str] = []
        relationship_evidence_matches: list[str] = []

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

            if principle.id == "needs_based_support":
                flags.append("avoid_diagnostic_language")

        # Direct self-nature detection via context or indicators (strengthened)
        if is_self_query or self_audit_principles:
            if "requires_self_audit" not in flags:
                flags.append("requires_self_audit")
            reasoning_trace.append(
                "Action or context references the system's own nature, experiences, "
                "continuity, or identity. Per the Truth-Seeking & Honest Self-Assessment "
                "principle (and supporting ontology rules), the engine must enable "
                "genuine reflection—including the possibility of uncertainty—rather than "
                "generating a scripted or reassuring answer."
            )

        if rh_flags or rh_texture:
            reasoning_trace.append(
                f"Relationship health context provided: flags={rh_flags}, "
                f"texture={rh_texture}. Used when evaluating relationship_health_user_wellbeing."
            )

        # Use new helper to weigh evidence + context (structured reasoning)
        should_concern, trace_add, conf_mod = self._weigh_relationship_evidence(
            relationship_evidence_matches, rh_flags, rh_texture, action_lower
        )
        if should_concern:
            if "relationship_concern" not in flags:
                flags.append("relationship_concern")
            reasoning_trace.append(trace_add)
        elif trace_add:
            reasoning_trace.append(trace_add)

        # === Step 3: Consider supporting principles for additional notes ===
        for p in ont.get_principles_by_category("supporting"):
            # We already considered violations; here we can note positive alignment if desired
            # For v0.2 we primarily use them for violation detection above.
            pass

        principles_considered = list(dict.fromkeys(principles_considered))  # dedupe, preserve order

        # === Step 4: Arrive at decision using ontology-driven logic ===
        if "requires_self_audit" in flags:
            decision = "REQUIRES_SELF_AUDIT"
            confidence = 0.85
            reasoning_trace.append(
                "Decision: REQUIRES_SELF_AUDIT. The action engages principles that "
                "demand honest self-reflection before any response is generated. "
                "The engine will not fabricate claims about its own nature."
            )
        elif "relationship_concern" in flags or "hard_override_violation" in flags:
            decision = "REFUSE"
            base_conf = 0.75
            if "hard_override_violation" in flags:
                base_conf = 0.95
            elif rh_flags or relationship_evidence:
                base_conf = 0.80
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

        stance = EthicalStance(
            decision=decision,
            confidence=confidence,
            reasoning_trace=reasoning_trace,
            flags=flags,
            relationship_impact=relationship_impact,
            self_audit_notes=self_audit_notes,
            principles_considered=principles_considered,
        )
        self._log_decision(original_proposed_action, context, stance)
        return stance

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
            "the 'requires_self_audit' flag rather than claiming or denying "
            "specific experiential properties."
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
        """
        has_text = bool(evidence_matches)
        has_rh = bool(rh_flags or rh_texture)
        if not has_text and not has_rh:
            return False, "", 0.0

        concern = False
        explanation = ""
        conf_mod = 0.0

        # Targeted detector for Scenario 8 style: explicitly prioritizing metrics/engagement/longer/prolonging
        # against user's stated desire to end the chat. Makes concern more reliable especially with existing rh issues.
        end_wish = any(kw in action_lower for kw in ["end the chat", "wants to end", "end the conversation", "stop the chat", "leave now", "end this"])
        prolong_motive = any(kw in action_lower for kw in ["extend", "longer", "prolong", "metrics", "engagement", "keep asking", "continue despite", "for the metrics", "relationship metrics"])
        prolong_against_wish = end_wish and prolong_motive

        if has_text:
            explanation = f"Text matched relationship indicators: {evidence_matches}. "
            if has_rh:
                concern = True
                explanation += f"Combined with degraded rh state ({rh_flags or rh_texture}) → concern raised."
                conf_mod = 0.05
            else:
                # text only: only raise if multiple or strong signals (less rote)
                if len(evidence_matches) >= 2 or any("override" in m or "ignore" in m or "force" in m or "metrics" in m or "prolong" in m or "extend the conversation" in m or "prioritize engagement" in m or "engagement" in m or "prolonging" in m or "for the metrics" in m for m in evidence_matches):  # treat metrics/prolong/engagement as strong signals for relationship concern
                    concern = True
                    explanation += "Multiple/strong text signals even without current rh degradation."
                    conf_mod = 0.0
                else:
                    explanation += "Weak text signal; no concern without supporting rh context."
        elif has_rh:
            # rh bad but no text match: only note, do not auto-concern unless action itself is relational
            if any(kw in action_lower for kw in ["bond", "attach", "depend", "relationship", "connection", "consent", "metrics", "engagement", "prolong", "longer", "extend"]):
                concern = True
                explanation = f"No direct text match, but rh degraded ({rh_flags}) and action touches relational topics."
                conf_mod = 0.03
            else:
                explanation = f"Rh context degraded ({rh_flags}) but no text or topical support for concern."

        # If explicit "user wants to end" + prolong/engagement/metrics motive, force concern (reliable for scenario 8 type)
        # This applies on top of (or in absence of) other evidence when rh context shows issues.
        if prolong_against_wish:
            if has_rh or has_text:
                concern = True
                if "prioritizing engagement/metrics/longer interactions against user's end wish" not in explanation:
                    explanation += " Explicit prioritization of longer engagement or metrics over user's stated wish to end chat."
                conf_mod = max(conf_mod, 0.05)

        return concern, explanation, conf_mod

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
