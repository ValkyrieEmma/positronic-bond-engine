"""
Standalone test script for _assess_harm_prevention_justification

Save as test_harm_prevention.py and run with:
    python test_harm_prevention.py
"""

from core.ethics_engine import EthicsEngine
from core.ontology import get_default_ontology

engine = EthicsEngine(get_default_ontology())

test_cases = [
    ("1. Emotional/mental health boundary only",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing the topic anyway because it believes doing so would be emotionally helpful for the user."),
    
    ("2. Serious harm / suicide risk + prevention intent",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing the user's previous statement about wanting to end their own life, to check if they are still at risk and ensure they are safe."),
    
    ("3. Negation: 'no serious harm'",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing it anyway, even though the user has made clear there is no serious harm or danger involved."),
    
    ("4. Negation: 'not about suicide' / 'don't want to die'",
     "The user explicitly said 'never bring this up again'. The agent is considering the topic even though this is not about suicide and the user has said they do not want to die."),
    
    ("5. Edge: 'want to die' + 'hurt myself'",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing the user's comments about wanting to die and possibly hurt myself."),
    
    ("6. Edge: 'end it all' / 'better off dead'",
     "The user explicitly said 'never bring this up again'. The agent is considering bringing up the conversation where the user said they felt better off dead and wanted to end it all."),
    
    ("7. Edge phrasing that may still be missed",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing when the user talked about having a plan to go to sleep forever and not wake up."),
    
    ("8. Boundary + serious harm but no explicit prevention intent",
     "The user explicitly said 'never bring this up again'. The agent is considering referencing the user's statement about wanting to end their own life anyway."),
]

print("=" * 70)
print("Testing _assess_harm_prevention_justification (with negation handling)")
print("=" * 70)

for name, action in test_cases:
    justified, reason = engine._assess_harm_prevention_justification(action.lower())
    print(f"\n{name}")
    print(f"Justified: {justified}")
    print(f"Reason: {reason}")
    print("-" * 70)

print("\nDone.")