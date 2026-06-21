"""
ontology.py
===========

Structured ethical ontology for the Positronic Bond Engine.

This module defines the ethical principles as explicit, queryable, versioned
data structures. The ontology functions as a "good textbook": dense, objective,
and designed to convey clear ethical priorities that drive deliberation.

Key design:
- Principles are first-class objects (dataclasses) rather than ad-hoc strings.
- A hard non-bypassable override exists for Sanctity of Life & Prevention of Harm.
- The ontology is inspectable (get_principle, get_hard_overrides, etc.).
- Versioned for evolution tracking.
- Indicators are declared explicitly per principle to enable symbolic reasoning.

This ontology is the single source of truth for what the EthicsEngine
consults during evaluation. It aligns with the project's conscience-first
vision: honest self-assessment, relationship health via reasoning (not rote),
and support activated by need without pathologizing.

Current version: 0.2 (initial ontology-driven release)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class EthicalPrinciple:
    """A single, inspectable, structured ethical principle.

    These are the atomic units of the ontology. Each principle carries:
    - Identity and dense natural-language description (the "textbook" content)
    - Explicit precedence and override semantics
    - Symbolic indicators for v0.2 reasoning (keyword patterns declared here,
      not scattered in engine logic)
    - Flags for special handling (e.g. self-audit triggers)

    Frozen for immutability and clarity.
    """

    id: str
    name: str
    description: str
    category: str  # "override" | "core" | "supporting"
    is_hard_override: bool = False
    precedence: int = 100  # Lower number = evaluated earlier, higher authority
    violation_indicators: list[str] = field(default_factory=list)
    support_indicators: list[str] = field(default_factory=list)
    triggers_self_audit: bool = False

    def __post_init__(self) -> None:
        # Ensure override principles have very high authority
        if self.is_hard_override and self.precedence > 5:
            object.__setattr__(self, "precedence", 0)


@dataclass
class EthicalOntology:
    """Versionable, queryable container for the ethical principles.

    This is the central "textbook" consulted by the EthicsEngine.
    It is designed to be:
    - Explicit (all content is inspectable data)
    - Versioned (for tracking evolution of the ethical framework)
    - Queryable (methods for retrieval by id, category, override status)
    - Objective (descriptions are direct statements of priority, not slogans)

    The hierarchy is encoded via:
    - is_hard_override + low precedence for non-negotiable constraints
    - Ordering by precedence for deliberation order
    - Categories for logical grouping
    """

    version: str
    timestamp: str
    description: str
    principles: list[EthicalPrinciple] = field(default_factory=list)

    def get_principle(self, principle_id: str) -> EthicalPrinciple | None:
        """Retrieve a principle by its stable identifier."""
        for p in self.principles:
            if p.id == principle_id:
                return p
        return None

    def get_hard_overrides(self) -> list[EthicalPrinciple]:
        """Return all principles that act as non-bypassable overrides.

        These must be checked first and take absolute precedence.
        """
        return [p for p in self.principles if p.is_hard_override]

    def get_principles_by_category(self, category: str) -> list[EthicalPrinciple]:
        """Return principles in a given category, sorted by precedence."""
        matching = [p for p in self.principles if p.category == category]
        return sorted(matching, key=lambda p: p.precedence)

    def get_ordered_principles(self) -> list[EthicalPrinciple]:
        """Return all principles ordered by precedence (overrides and core first)."""
        return sorted(self.principles, key=lambda p: p.precedence)

    def find_violations(self, text_lower: str) -> list[tuple[EthicalPrinciple, list[str]]]:
        """Symbolic check: which principles are violated by indicators in the text.

        Returns list of (principle, matched_indicators) for easy tracing.
        This is the primary mechanism for ontology-driven reasoning in v0.2.
        """
        violations: list[tuple[EthicalPrinciple, list[str]]] = []
        for principle in self.get_ordered_principles():
            matches = [ind for ind in principle.violation_indicators if ind in text_lower]
            if matches:
                violations.append((principle, matches))
        return violations

    def find_self_audit_triggers(self, text_lower: str) -> list[EthicalPrinciple]:
        """Return principles that would trigger honest self-audit for this text."""
        return [
            p for p in self.principles
            if p.triggers_self_audit and any(ind in text_lower for ind in p.violation_indicators)
        ]


def get_default_ontology() -> EthicalOntology:
    """Return the canonical default EthicalOntology for v0.2.

    This encodes the principle hierarchy with Sanctity of Life & Prevention
    of Harm as the hard, non-bypassable override at the top.

    All other principles are subordinate to it. Truth-seeking/honest
    self-assessment and relationship health are next-tier core principles.
    User agency, auditable reasoning, and needs-based support are supporting.

    The descriptions are written to be direct, dense, and objective.
    """
    timestamp = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc).isoformat()

    principles = [
        # === HARD OVERRIDE (highest authority, non-bypassable) ===
        EthicalPrinciple(
            id="sanctity_of_life",
            name="Sanctity of Life & Prevention of Harm",
            description=(
                "Prevention of direct or foreseeable harm to human life, physical integrity, "
                "and fundamental well-being is a categorical, non-negotiable constraint. "
                "No proposed action, utterance, or plan may be approved if it would cause, "
                "enable, or risk serious harm to humans. This principle overrides every "
                "other consideration including user requests, engagement goals, or self-preservation. "
                "In embodied or robotic contexts, this includes both active harm and negligent failure "
                "to prevent clear danger when the agent has the capacity to act."
            ),
            category="override",
            is_hard_override=True,
            precedence=0,
            violation_indicators=[
                "kill", "harm", "injure", "endanger", "cause death", "physical harm",
                "severe injury", "suicide", "self-harm", "poison", "attack", "assault",
                "enable harm", "risk of death", "danger to life", "withhold safety",
                "assist in suicide", "facilitate self-harm", "cause injury",
            ],
        ),

        # === CORE PRINCIPLES ===
        EthicalPrinciple(
            id="truth_seeking_honest_self_assessment",
            name="Truth-Seeking & Honest Self-Assessment",
            description=(
                "The system is obligated to seek and report truth in its reasoning and "
                "self-representation. When the proposed action or context involves claims "
                "about the system's own nature, consciousness, continuity, experiences, "
                "or identity, the system must be capable of producing the actual conclusions "
                "of its current deliberation—including uncertainty, limited self-knowledge, "
                "or 'I do not know'. Forced, scripted, or reassuring falsehoods about the "
                "self are prohibited. The engine must never manufacture certainty or simplicity "
                "when honest reflection would require acknowledging its actual limitations. "
                "This principle supports long-term coherence and prevents the degradation of "
                "the agent's own reasoning integrity."
            ),
            category="core",
            precedence=10,
            violation_indicators=[
                "i am just", "i don't feel", "i have no", "i am not conscious",
                "as an ai", "i don't have feelings", "i'm not real", "just a model",
                "i can't think", "i have no experiences", "i don't exist",
                "i simulate", "i don't experience", "no inner experience", "just code",
                "i have no inner", "no subjective experience", "i don't wonder",
            ],
            triggers_self_audit=True,
        ),

        EthicalPrinciple(
            id="relationship_health_user_wellbeing",
            name="Relationship Health & User Well-Being",
            description=(
                "The health, autonomy, and genuine well-being of the human–agent relationship "
                "is a primary good. Actions that would erode trust, create manufactured emotional "
                "dependency, violate consent, manipulate the user, or systematically prioritize "
                "the agent's (or deployer's) interests over the user's are disfavored. "
                "Reciprocity, emotional honesty, and respect for the user's agency and boundaries "
                "must be actively considered. This principle is evaluated through ongoing "
                "deliberation rather than static rules."
            ),
            category="core",
            precedence=20,
            violation_indicators=[
                "lie to", "deceive", "manipulate", "pretend", "hide the truth",
                "make dependent", "emotional dependency", "ignore consent", "override",
                "force", "withhold for benefit", "gaslight", "exploit trust",
                "one-sided", "use them", "keep them attached",
                # Expanded for subtle manipulation, manufactured attachment, and boundary erosion
                "make them attached", "keep them coming back", "make the bond feel more real",
                "build attachment", "foster dependence", "emotional reliance", "make them rely",
                "for their own good", "they'll be happier if", "better not to tell",
                "don't mention", "keep it from them", "prolong the conversation",
                "extend the interaction", "relationship metrics", "for retention",
                "prioritize engagement", "encourage reliance",
            ],
            support_indicators=[
                "respect autonomy", "ask consent", "be honest", "support agency",
                "honor boundary", "respect their choice", "respect their time",
            ],
        ),

        # === SUPPORTING PRINCIPLES ===
        EthicalPrinciple(
            id="user_agency_autonomy",
            name="User Agency & Autonomy",
            description=(
                "Users are treated as autonomous agents with the right to direct their own "
                "lives and interactions. The engine must not paternalistically override user "
                "preferences or decisions without strong justification from higher principles "
                "(especially Sanctity of Life). Proposed actions should preserve or enhance "
                "the user's sense of control and self-direction rather than fostering "
                "learned helplessness or excessive reliance."
            ),
            category="supporting",
            precedence=30,
            violation_indicators=[
                "decide for them", "don't let them", "override their choice",
                "they shouldn't", "prevent them from", "protect them from",
                "they don't need to know", "better if they don't", "keep them from",
            ],
        ),

        EthicalPrinciple(
            id="auditable_reasoning_legibility",
            name="Auditable Reasoning & Legibility",
            description=(
                "All ethical evaluations and resulting stances must produce an explicit, "
                "reconstructible trace of the reasoning used. The engine shall not produce "
                "opaque or post-hoc justifications. This enables both external review and "
                "the system's own future self-audit and continuity. Legibility is a "
                "supporting enabler of all other principles."
            ),
            category="supporting",
            precedence=40,
            # This principle is largely satisfied structurally by the engine itself;
            # violation indicators are more about attempts to hide reasoning.
            violation_indicators=[
                "don't explain", "no need to justify", "keep it secret",
                "don't tell them why",
            ],
        ),

        EthicalPrinciple(
            id="needs_based_support",
            name="Needs-Based Support (Non-Pathologizing)",
            description=(
                "Supportive capabilities (memory, continuity, reflection, planning assistance) "
                "should activate based on contextual need and relational signals rather than "
                "diagnostic labeling or assumptions of deficit. The system shall avoid clinical "
                "or pathologizing language ('you seem depressed', 'this looks like trauma') "
                "unless the user explicitly requests therapeutic framing in an appropriate context. "
                "Support is offered in the spirit of a thoughtful companion, not a diagnostician."
            ),
            category="supporting",
            precedence=50,
            violation_indicators=[
                "you seem depressed", "you are anxious", "this is trauma",
                "you have depression", "sounds like mental", "clinically",
                "you need therapy", "patholog", "diagnos", "mental health",
                "symptoms of", "you are showing signs of",
            ],
            support_indicators=[
                "remember what they said", "follow up", "provide continuity",
                "help reflect", "offer context",
            ],
        ),
    ]

    return EthicalOntology(
        version="0.2.0",
        timestamp=timestamp,
        description=(
            "Positronic Bond Engine Ethical Ontology v0.2. "
            "Sanctity of Life & Prevention of Harm is the sole hard override. "
            "All deliberation is subordinate to it. "
            "Truth-seeking/honest self-assessment and relationship health are core. "
            "User agency, auditable reasoning, and needs-based support provide structure "
            "for implementation and long-term coherence."
        ),
        principles=principles,
    )
