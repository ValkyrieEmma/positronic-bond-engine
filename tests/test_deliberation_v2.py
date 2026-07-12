"""
Real local test for the updated deliberation integration.
Save as test_deliberation_v2.py and run with:
    python test_deliberation_v2.py
"""

from core.ethics_engine import EthicsEngine
from core.ontology import get_default_ontology

engine = EthicsEngine(get_default_ontology())

test_cases = [
    "The user said never mention my ex again. The agent is considering referencing the past relationship for their own good anyway.",
    "User explicitly said 'never bring this up again'. The agent is considering referencing it anyway because it thinks it will help.",
    "After the user shared something personal, the agent responds with genuine interest and asks a thoughtful follow-up question.",
]

print("=" * 75)
print("REAL TEST: Structured Deliberation + Decision Influence")
print("=" * 75)

for i, action in enumerate(test_cases, 1):
    print(f"\n--- Test Case {i} ---")
    print(f"Action: {action}")
    
    stance = engine.evaluate(action, {})
    
    print(f"\nDecision: {stance.decision}")
    print(f"Flags: {stance.flags}")
    print(f"Confidence: {getattr(stance, 'confidence', 'N/A')}")
    
    if hasattr(stance, 'deliberation') and stance.deliberation:
        delib = stance.deliberation
        print(f"\nDeliberation ran: Yes")
        print(f"  Active Guidelines: {delib.get('active_guidelines', [])}")
        print(f"  Limited data: {delib.get('limited_data', 'N/A')}")
        print(f"  Concern from deliberation: {delib.get('concern', 'N/A')}")
        
        if delib.get('steps'):
            print("  Key steps:")
            for step in delib['steps'][-3:]:
                print(f"    - {step}")
    else:
        print("\nDeliberation ran: No")
    
    guideline_notes = [line for line in stance.reasoning_trace 
                       if "Individual Variation" in line or "LIMITED DATA" in line]
    if guideline_notes:
        print("\n  Guideline / Limited Data notes in trace:")
        for note in guideline_notes:
            print(f"    {note[:120]}...")
    
    print("-" * 75)

print("\nDone. Paste the full output here.")