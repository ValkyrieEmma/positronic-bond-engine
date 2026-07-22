"""
core
====

The heart of the Positronic Bond Engine.

This package contains the primary ethical reasoning systems, decision frameworks,
and governance logic. All other modules ultimately exist to support or be governed
by the conscience layer implemented here.

Design principles:
- Every major decision path must be traceable through ethical deliberation.
- The system must remain capable of honest self-reflection.
- Relationship health considerations are first-class inputs.
"""

from .development_context import (  # noqa: F401
    DevelopmentPhaseContext,
    get_default_development_context,
    resolve_development_context,
)
from .ethics_engine import DecisionLog, EthicalStance, EthicsEngine  # noqa: F401
from .exploratory_questioning import ExploratoryQuestioner, QuestionDecision  # noqa: F401
from .interaction_memory import (  # noqa: F401
    InteractionMemoryStore,
    InteractionRecord,
    MemoryStore,
)
from .ontology import (  # noqa: F401
    EthicalOntology,
    EthicalPrinciple,
    get_default_ontology,
    indicator_matches_text,
    prefer_specific_indicator_matches,
)
from .per_user_baseline import DeviationReport, PerUserBaseline  # noqa: F401
from .relationship_health import BondState, RelationshipHealth  # noqa: F401
from .response_generator import GeneratedResponse, ResponseGenerator  # noqa: F401
from .enjoyment_score import (  # noqa: F401
    EnjoymentScore,
    soft_texture_nudge_from_enjoyment,
    update_enjoyment_score,
)
from .observation_candidates import (  # noqa: F401
    ObservationCandidate,
    generate_observation_candidates,
    gate_allows_candidates,
)
from .truth_confidence import (  # noqa: F401
    TruthConfidence,
    assess_truth_confidence,
    combine_with_readiness,
)
from .truth_telling_readiness import (  # noqa: F401
    TruthTellingReadiness,
    assess_truth_telling_readiness,
)

__all__ = [
    "assess_truth_confidence",
    "assess_truth_telling_readiness",
    "BondState",
    "combine_with_readiness",
    "gate_allows_candidates",
    "generate_observation_candidates",
    "ObservationCandidate",
    "DecisionLog",
    "DevelopmentPhaseContext",
    "DeviationReport",
    "EnjoymentScore",
    "EthicalStance",
    "EthicsEngine",
    "EthicalOntology",
    "EthicalPrinciple",
    "ExploratoryQuestioner",
    "GeneratedResponse",
    "get_default_development_context",
    "get_default_ontology",
    "indicator_matches_text",
    "InteractionMemoryStore",
    "InteractionRecord",
    "MemoryStore",
    "PerUserBaseline",
    "prefer_specific_indicator_matches",
    "QuestionDecision",
    "RelationshipHealth",
    "resolve_development_context",
    "ResponseGenerator",
    "soft_texture_nudge_from_enjoyment",
    "TruthConfidence",
    "TruthTellingReadiness",
    "update_enjoyment_score",
]
