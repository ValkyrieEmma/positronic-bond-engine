# Communicative deliberation & relationship knowledge

Public architecture note for **v0.4.1-dev**. Pairs with [model_providers.md](model_providers.md).

Speech and interaction under the ethical gate should emerge from **reasoning about meaning and relationship**, not from a catalog of chat templates. This supports the Optimus-class target (humanoid robots that must introduce themselves, learn who they are with, and know when to stand down) and is exercised today through the **local development / validation harness**.

## Intent

1. Words have meanings; introductions can assert durable facts (for example, a preferred name, or how the user identifies in relation to the system).
2. Those facts are stored as **relationship knowledge** and used as premises later.
3. When knowledge and memory for a user are **blank**, a greeting is reasoned as **first meeting**: introduce honestly and ask who you are speaking with (as two people would upon meeting).
4. The system also reasons about when to **stop** (leave alone / goodbye) or respect boundaries.
5. Optional models only **re-word** a deliberated communicative intent; they never open speech past the ethics gate or set force flags.

## Pipeline

```
user message
  → interpret meanings (propositions / glosses)
  → load relationship knowledge
  → premises → situation → communicative intent
  → persist new facts if any
  → EthicsEngine.evaluate (gate)
  → speech posture
  → express intent (offline fallback)
  → optional ContentProvider re-word under same intent
  → scrub force flags / soft theater
```

Implementation:

| Piece | Module |
|-------|--------|
| Meanings, knowledge, intent | `core/communicative_deliberation.py` |
| Working agreements (name, questions, feedback) | `core/working_agreements.py` (name kept aligned with knowledge) |
| Social expression | `core/response_generator.py` (`social_direct`) |
| Optional wording model | `core/content_provider.py` |
| Local interactive harness | `examples/private_architect_chat.py` (script path; local validation only) |

## Durable relationship knowledge

Stored under user settings preferences (`relationship_knowledge`), wiped with the user:

| Field | Meaning |
|-------|---------|
| `address_name` | Preferred form of address |
| `is_maker` | Whether the user self-described a builder/designer relation to the system (implementation flag; treated as role evidence) |
| `role_labels` | Self-described role labels (for example designer, builder) |
| `role_summary` | Short self-description evidence |

Harness `status` can show known address name, role labels, and related flags.

## Communicative intents (examples)

| Intent | Typical premises |
|--------|------------------|
| `introduce_and_learn_identity` | Blank knowledge + contact opening |
| `acknowledge_relationship_facts` | Role self-description and/or address directive this turn |
| `greet_with_known_identity` | Greeting + stored name/role knowledge |
| `stop_engaging` | Leave-alone / goodbye meanings |
| `continue_collaboration` | Ongoing exchange; topics as aids |

Telemetry may show `intent=…` on each harness turn. Premises are inspectable in metadata / tests.

## Honest limits (current)

- Meaning extraction is **linguistic + deliberative**, not open-ended human understanding.
- Offline fallback **expresses** the deliberated intent in plain words; a live local/cloud model can improve naturalness under the **same** intent.
- Full Optimus-class bond fluency, multi-person household presence, and embodiment remain later direction (see README).

## Tests

```powershell
$env:PYTHONPATH = "."
python tests/test_communicative_deliberation.py
python tests/test_speech_posture.py
python tests/test_social_direct_content.py
python tests/test_private_architect_path.py
```
