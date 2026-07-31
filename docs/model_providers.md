# Model content providers (gated)

The EthicsEngine decides **whether** speech may occur and under which **speech posture**.  
**Communicative deliberation** decides **situation + intent** and durable relationship facts (see [communicative_deliberation.md](communicative_deliberation.md)).  
A **ContentProvider** only **re-words** already-allowed turns under that intent (`social_direct`, `self_audit`). It must never:

- override `REFUSE` / hold / withheld silence
- set `forces_speech` or `forces_question` true
- claim consciousness or emit canned self-denials
- invent relationship facts not in the context pack
- run unbounded background jobs

Offline default: **no model** — deliberated fallback expression only (`NullContentProvider`).

This supports the ethical core for humanoid robots: models are optional wording layers, not the conscience. Callers use the **public entry** (`api/`); the local CLI harness exercises the same pipeline for testing.

## Architecture

```
user message
  → communicative deliberation (meanings → knowledge → intent)
  → EthicsEngine.evaluate → speech posture
  → ResponseGenerator expresses intent (fallback text)
  → optional ContentProvider.generate(context_pack)   # same intent
  → scrub + soft-fail → user-facing text
```

| Piece | Location |
|-------|----------|
| Deliberation + knowledge | `core/communicative_deliberation.py` |
| HTTP provider (wording) | `core/content_provider.py` |
| Contextual judgment (reasoning-over-rote) | `core/contextual_judgment.py` — same `PBE_MODEL_*` config, different job: judges whether an ontology-flagged indicator hit is a genuine principle violation from full context, used by `EthicsEngine`'s `contextual_judge=` (see `claude/pbe-principle-reasoning-over-rote-2026-07-30.md`) |
| Optional local config file | `core/local_model_config.py` — explicit opt-in `.pbe_model.env` loader, see below |
| Wiring | `ResponseGenerator`; public entry and local test harness via `provider_from_env()` |

Context pack includes intent, premises, relationship knowledge (preferred address name, role labels, self-described relation to the system), phase/version, short topics — not arbitrary private dumps.

## Local free path (Ollama)

Ollama must be **running** (e.g. desktop app or `ollama serve`) and a model pulled. If nothing listens on the API port, the harness still works with `content=fallback(...)` and surfaces the error in telemetry.

1. Install [Ollama](https://ollama.com/) and pull a small model, e.g. `ollama pull llama3.2`.
2. Ensure the OpenAI-compatible API is on loopback (default `http://127.0.0.1:11434/v1`).
3. From the project root:

```powershell
$env:PYTHONPATH = "."
$env:PBE_MODEL_PROFILE = "ollama"
# optional overrides:
# $env:PBE_MODEL_NAME = "llama3.2"
# $env:PBE_MODEL_BASE_URL = "http://127.0.0.1:11434/v1"
# $env:PBE_MODEL_TIMEOUT_S = "45"
# $env:PBE_MODEL_MAX_TOKENS = "256"
python examples/private_architect_chat.py
```

Or in code:

```python
from core.content_provider import ollama_provider
from core.response_generator import ResponseGenerator

responder = ResponseGenerator(content_provider=ollama_provider(model="llama3.2"))
```

### Convenience: `.pbe_model.env` instead of shell env vars (2026-07-30)

Setting *persistent* OS environment variables on Windows normally means
editing System Properties or running `setx` and restarting every terminal —
friction for something this low-stakes. `core/local_model_config.py`
provides an optional, explicit, opt-in alternative: a plain
`.pbe_model.env` file at the repo root (gitignored — see `.gitignore`'s
"Local model connection config" section), loaded with:

```python
from core.local_model_config import load_local_env_file
load_local_env_file()  # applies .pbe_model.env via os.environ.setdefault
```

before constructing any provider. A real environment variable with the same
name always wins over the file. **This is never loaded automatically** —
importing `content_provider.py` has no side effect on your environment,
so the test suite's "no model configured" baseline is unaffected whether or
not `.pbe_model.env` exists. Run `python examples/verify_local_model.py`
(after `$env:PYTHONPATH = "."`) for a one-command check that both the
content-generation path *and* the contextual-judgment path (see
`core/contextual_judgment.py` and
`claude/pbe-principle-reasoning-over-rote-2026-07-30.md`) can actually reach
your configured model — it prints clear pass/fail plus troubleshooting for
each.

## BYO cloud (OpenAI-compatible)

Any HTTP Chat Completions endpoint works (OpenAI, proxies, LM Studio, etc.):

```powershell
$env:PBE_MODEL_BASE_URL = "https://api.openai.com/v1"
$env:PBE_MODEL_API_KEY = "sk-..."
$env:PBE_MODEL_NAME = "gpt-4o-mini"
$env:PBE_MODEL_ENABLED = "1"
# omit PBE_MODEL_PROFILE or set openai_compatible
```

Keys stay in your environment — the engine does not ship credentials.

## Environment variables

| Variable | Meaning | Default |
|----------|---------|---------|
| `PBE_MODEL_ENABLED` | `0` / `false` / `off` disables | `1` |
| `PBE_MODEL_PROFILE` | `ollama` \| `openai_compatible` \| `off` | empty |
| `PBE_MODEL_BASE_URL` | API root (…`/v1` or full chat URL) | none (offline) |
| `PBE_MODEL_API_KEY` | Bearer token | empty |
| `PBE_MODEL_NAME` | Model id | `llama3.2` when Ollama profile |
| `PBE_MODEL_TIMEOUT_S` | Request timeout | `45` |
| `PBE_MODEL_MAX_TOKENS` | Max completion tokens (capped 1024) | `256` |
| `PBE_MODEL_MAX_CONTEXT_CHARS` | Max user payload chars | `4000` |

**Offline default:** no `PBE_MODEL_BASE_URL` and profile not `ollama` → `NullContentProvider` (safe for tests and machines without a local server).

**Ollama profile:** `PBE_MODEL_PROFILE=ollama` fills loopback URL + default model even if base URL is unset. Soft-fails if the server is not running.

## Hardware / usage safety

Conservative caps for local free models and shared machines:

| Control | Behavior |
|---------|----------|
| Timeout | Default 45s; soft-fail to deliberated fallback on hang |
| Concurrency | Max **1** in-flight generation (semaphore) |
| Tokens / context | `max_tokens` + `max_context_chars` caps |
| Circuit breaker | After 3 consecutive failures, open ~60s |
| Soft-fail | Errors → deliberated fallback text; interaction continues |
| Scrub | Drop consciousness claims, soft-caution theater, engagement bait |

## Telemetry

Local harness status lines may include:

```text
· intent=introduce_and_learn_identity · content=fallback
· content=fallback(url_error:...)     # local/cloud model unreachable
· content=provider                    # model wording used
```

Metadata shape:

```json
"content_provider": {
  "source": "provider" | "fallback",
  "error": null | "timeout" | "circuit_open" | "url_error:...",
  "latency_ms": 120.5,
  "model": "llama3.2",
  "forces_speech": false,
  "forces_question": false
}
```

## Tests

```powershell
$env:PYTHONPATH = "."
python tests/test_content_provider.py
```

Uses mocked HTTP — no live Ollama/cloud required.

## Out of scope (later)

- Desktop UI / packaged exe
- Streaming tokens in a product TUI
- Multi-model routing / embedding providers
- Auto-download of weights
