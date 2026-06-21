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

from .ethics_engine import DecisionLog, EthicsEngine  # noqa: F401
from .ontology import (
    EthicalOntology,
    EthicalPrinciple,
    get_default_ontology,
)
from .relationship_health import BondState, RelationshipHealth  # noqa: F401

__all__ = [
    "BondState",
    "DecisionLog",
    "EthicsEngine",
    "EthicalOntology",
    "EthicalPrinciple",
    "get_default_ontology",
    "RelationshipHealth",
]
