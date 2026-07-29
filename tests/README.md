# Tests

Integration and smoke tests for the Positronic Bond Engine. These are **standalone scripts** (not a full pytest suite). Run from the **project root** with `PYTHONPATH=.`.

```powershell
$env:PYTHONPATH = "."
```

## v0.5.0-dev — public entry, presence, harness, speech, providers

```powershell
python tests/test_public_entry.py
python tests/test_session_presence.py
python tests/test_private_architect_path.py
python tests/test_communicative_deliberation.py
python tests/test_speech_posture.py
python tests/test_social_direct_content.py
python tests/test_session_time.py
python tests/test_content_provider.py
```

| Script | Focus |
|--------|--------|
| `test_public_entry.py` | Public `api.InteractionSession` contract surface |
| `test_session_presence.py` | Session presence + command interception |
| `test_private_architect_path.py` | Local harness isolation, phase/version, wipe/resume |
| `test_communicative_deliberation.py` | Relationship knowledge, first meeting, role and name uptake |
| `test_speech_posture.py` | social_direct vs careful_observation evidence bar |
| `test_social_direct_content.py` | Intent-driven social speech, no soft-caution theater |
| `test_session_time.py` | Wall-clock / idle session bags |
| `test_content_provider.py` | Null/OpenAI-compatible safety (mocked HTTP; no live Ollama required) |

## Gated response generation (v0.4.0+)

```powershell
python tests/test_response_generator_gated.py
python tests/test_response_e2e_live.py
python tests/test_response_enjoyment_bias.py
```

## Ethics / bond foundation

```powershell
python tests/test_persistence.py
python tests/test_per_user_baseline.py
python tests/test_exploratory_questioning.py
python tests/test_deliberation_v2.py
python tests/test_dual_deliberation.py
python tests/test_limited_data.py
python tests/test_harm_prevention.py
python tests/test_ethics_engine_integration.py
python tests/test_bond_decision_persistence.py
python tests/test_interaction_memory_integration.py
python tests/test_relationship_health_integration.py
python tests/test_audit_runner.py
python tests/test_auto_enqueue_audits.py
python tests/test_provenance_stale_influence.py
```

## Evaluation harness

```powershell
python evaluation/eval_harness.py
python evaluation/eval_harness.py --weighing
python evaluation/eval_harness.py --history-proactive
python evaluation/eval_harness.py --co-evolution
```

Persistence-related scripts use temporary data folders and clean up after themselves. They do not write into the real home `pbe_data/` directory when run as designed.
