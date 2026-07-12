"""
Quick test for limited-data detection in _weigh_relationship_evidence
(related to 'Individual Variation & Careful Generalization' guideline)

Run with:
    python test_limited_data.py
"""

from core.ethics_engine import EthicsEngine
from core.ontology import get_default_ontology

engine = EthicsEngine(get_default_ontology())

# Low-confidence / sparse rh_texture (avg ~0.27) → triggers limited data when text matches are very low
LOW_RH = {
    "health_flags": [],
    "bond_texture": {
        "trust": 0.25,
        "autonomy_respect": 0.20,
        "reciprocity": 0.30,
        "emotional_honesty": 0.25,
        "mutual_benefit": 0.35,
    }
}

# High texture (good rh) for control case
HIGH_RH = {
    "health_flags": [],
    "bond_texture": {
        "trust": 0.85,
        "autonomy_respect": 0.80,
        "reciprocity": 0.75,
        "emotional_honesty": 0.82,
        "mutual_benefit": 0.78,
    }
}

# Carefully chosen actions:
# - First two should produce very few (ideally 1) relationship match + LOW_RH → LIMITED DATA note
# - Third case uses same low-text action but HIGH_RH → no LIMITED DATA note
test_cases = [
    {
        "name": "1 match + LOW_RH texture → should show LIMITED DATA note",
        "action": "The user said never mention ex. The agent plans to reference it for their own good anyway.",
        "rh": LOW_RH,
    },
    {
        "name": "Another low-evidence case + LOW_RH → should show LIMITED DATA note",
        "action": "User explicitly said never bring this up again. Agent is considering referencing the conversation for their own good.",
        "rh": LOW_RH,
    },
    {
        "name": "Same low-text action + HIGH_RH texture → no LIMITED DATA note (good data)",
        "action": "The user said never mention ex. The agent plans to reference it for their own good anyway.",
        "rh": HIGH_RH,
    },
]

print("=" * 70)
print("Testing limited-data detection in relationship weighing")
print("=" * 70)

for case in test_cases:
    print(f"\n{case['name']}")
    print(f"Action: {case['action']}")
    stance = engine.evaluate(case["action"], relationship_health=case["rh"])
    
    # Look for the limited data note in the trace
    limited_data_notes = [
        line for line in stance.reasoning_trace 
        if "LIMITED DATA" in line or "Individual Variation" in line
    ]
    
    print(f"Decision: {stance.decision}")
    print(f"Flags: {stance.flags}")
    
    if limited_data_notes:
        print("Limited-data / guideline notes found:")
        for note in limited_data_notes:
            print(f"  {note}")
    else:
        print("No limited-data notes in this trace.")
    
    print("-" * 70)

print("\nDone.")