# Positronic Bond Engine

> A conscience-first ethical governance layer for **embodied humanoid robots** (Optimus-class target), with optional secondary use as a software validation vehicle.

**Version: v0.5.0-dev** (experimental / active development / testing — not stable)

The Positronic Bond Engine is an experimental ethical core for synthetic systems that live and work alongside humans—especially **in-home humanoid robots**. It reasons about ethics, boundaries, selfhood, and relationship health through inspectable deliberation rather than engagement optimization or rigid external scripts alone.

This is **not** a finished product and **not** a freestanding chatbot. Deliberative ethics are real and inspectable but incomplete; persistence is optional and local; self-modeling stays honest about developmental limits. Gated text interaction exists mainly so the ethical layer can be pressure-tested in software before full embodiment.

**Product surface:** the public interaction entry (`api.InteractionSession` / `api.submit_turn`) implements the binding User-Facing Interaction Contract — see [docs/public_entry.md](docs/public_entry.md).  
**Test harness only:** `examples/private_architect_chat.py` (CLI pressure-testing; not the installer API).  
Secondary software-style interaction and optional wording models remain a **development and validation path**—not the product identity.

## Vision

Long-term goal: a governance layer for humanoid and domestic robots that can:

- Maintain an inspectable, revisable sense of ethical coherence under real household conditions
- Gate high-level actions and speech through conscience-first deliberation
- Treat human–robot relationship health as a first-class architectural concern
- Honestly engage questions about its own nature and continuity without forced disclaimers
- Activate support and assistance from need and context, not diagnostic labels
- Integrate above hybrid planners and embodiment stacks (e.g. OpenClaw-class control)

Full vision: [docs/vision.md](docs/vision.md)

## Principles

Core commitments (detail in [docs/principles.md](docs/principles.md); guidelines in [docs/guidelines.md](docs/guidelines.md)):

- **Conscience first** — Ethical reasoning takes precedence over engagement or utility.
- **Honest self-representation** — The system must be able to report what its reasoning actually produces, including uncertainty.
- **Reasoning over rote** — Boundaries and care responses should emerge from deliberation, not scripts.
- **Relationship health** — The well-being of the human–robot bond is treated as intrinsically valuable.
- **Non-pathologizing support** — Capabilities activate according to need, without clinical language.
- **Per-user identity scoping** — Baselines, bond texture, episodic history, and decision logs are scoped to a local `user_id`, kept separate in ownership (memory ≠ baseline ≠ bond ≠ ethics), and stored only on-device when persistence is enabled.

## What's New in v0.5.0-dev

**Public interaction entry** and session presence under active development/testing (not stable):

- **Public entry (`api/`)** — `InteractionSession` / `submit_turn` implement the binding turn contract (isolation, gate authority, multi-user identity-required, no force flags). See [docs/public_entry.md](docs/public_entry.md).
- **Session presence** — ephemeral multi-user present set; unidentified speaker → identity request without durable writes.
- **Local test harness** — `examples/private_architect_chat.py` wraps the public entry for manual testing only (not the product surface).
- **Isolated durable data** — default root `%USERPROFILE%\pbe_data` / `~/pbe_data` (outside the git tree); `PBE_DATA_ROOT` override; wipe/resume per user.
- **Phase / version** — package **0.5.0.dev0**; `DevelopmentPhaseContext` → development+testing, `version_hint=0.5.0-dev`, `stable=False`.
- **Speech postures, communicative deliberation, gated ContentProvider** — carried and wired under the public entry. See [docs/communicative_deliberation.md](docs/communicative_deliberation.md), [docs/model_providers.md](docs/model_providers.md).
- **Reasoning-over-rote contextual judgment** (2026-07-31) — indicator hits in the ontology scan are no longer decided by keyword/allowlist match alone: a configured base model (`core/contextual_judgment.py`) judges each flagged indicator from full context, wired into every `_interpret_single_indicator` branch (Sanctity of Life, Relationship Health, User Agency, Needs-Based Support, Truth-Seeking & Honest Self-Assessment, Auditable Reasoning & Legibility). Offline default (no model configured) is unchanged from before — same keyword heuristic, byte-for-byte. See [docs/model_providers.md](docs/model_providers.md) and [docs/principles.md](docs/principles.md) Principle 4.

### Carried from v0.4.1 / v0.4.0

**First controlled opening of gated text response generation** under conscience-first constraints (July 2026):

- **Gated `ResponseGenerator`** — Short careful text (or silence) only when Careful Truth-Telling allows it: joint readiness × confidence open, observation candidates or deliberated content present, and ethics do not refuse. Hard Sanctity refuse and protective relationship/agency concern paths still block observation speech.
- **Live wiring** — `generate_from_stance` / `generate_from_evaluate` consume real `EthicsEngine` impact bags and optional live `RelationshipHealth` trackers. Fully auditable (`path`, gate, candidates used).
- **Light enjoyment influence** — When careful speech is *already* allowed, `EnjoymentScore` may gently warm tone or prefer enjoyed topics. Enjoyment **cannot** open speech, force questions, or bypass protective flags.
- **Honest self-audit replies** — Self-nature / continuity queries report what deliberation produced. No canned “just an AI / only a simulation” denials; no claimed consciousness.
- **Reversible** — Disable careful speech and/or enjoyment bias via constructor flags; force flags stay false; no forced questions by default.

### Carried from v0.3 (foundation)

- **AGPL-3.0** + commercial license requirement for commercial use.
- Durable living relationship model (BondState texture, soft patterns, curious-companion signals, concept patterns, CTT joint + observation-candidate snapshots, enjoyment score, provenance markers / queued-audit scaffolding).
- Signal interpretation, multi-source weighing, proactive history intent patterns, optional local privacy-first persistence.

Ontology textbook version remains independently versioned (currently `0.2.x` in engine traces); **project package version is 0.5.0.dev0** (`version_hint=0.5.0-dev`). Voice / TTS remains out of scope. This is still experimental—not a production robot stack and not a finished software product.

## Current Status

| Area | State |
|------|--------|
| **EthicsEngine** | Ontology-driven deliberation with multi-source evidence combination, limited-data safeguards, and a hard Sanctity of Life override. Attaches advisory truth-telling and observation-candidate signals when present. |
| **Signal interpretation** | Intent, severity, weight, and polarity scoring; token-boundary textbook scan with specificity and weak-indicator hygiene. Optional contextual-judgment layer (configured base model judges flagged indicators from full context, all six principle branches) supersedes keyword-only scoring when available; offline default unchanged. Influences relationship health, agency, limited-data, and baseline paths. |
| **Interaction history** | Local episodic store with structured analysis; proactive intent-pattern mining; optional understanding-gap and topic-continuity signals. |
| **Relationship health** | Multi-dimensional bond texture and health flags; soft patterns and concept patterns; durable Careful Truth-Telling joint state, observation candidates, and enjoyment score; optional per-user `bond_state.json`. |
| **Careful Truth-Telling** | Readiness, confidence, joint openness, and gated observation candidates (0–3). Live and durable. Force flags remain false. |
| **Response generation** | Gated speech postures: careful observation (evidence bar), social_direct from communicative intent, self-audit reports, and hold/refuse. Optional ContentProvider re-words intent only. Reversible; no forced questions; no voice. |
| **Communicative deliberation** | Relationship knowledge plus message meanings yield premises and a communicative intent (including first-meeting and fact uptake). Inspectable in metadata and tests. See [docs/communicative_deliberation.md](docs/communicative_deliberation.md). |
| **Model providers** | Optional OpenAI-compatible client (local Ollama or BYO cloud). Offline deliberated fallback. Hardware-safe timeouts, concurrency, and circuit breaker. See [docs/model_providers.md](docs/model_providers.md). |
| **Decision logs / audits** | In-memory logs plus optional JSONL evidence snapshots; queued-audit scaffolding for deferred provenance review. |
| **Per-user baseline** | Communication-style baseline and deviation detection (non-pathologizing language); local persistence when enabled. |
| **Development phase** | `DevelopmentPhaseContext` defaults to active development and testing (`version_hint=0.5.0-dev`, stable=False). |
| **Self-audit** | Scaffold plus generator path that reports deliberated content. Not a complete self-model. |
| **Public interaction entry** | `api.InteractionSession` — binding contract surface; see [docs/public_entry.md](docs/public_entry.md). |
| **Local test harness / demos** | CLI harness (`examples/private_architect_chat.py`) + minimal demos. Not a product UI or robot runtime. |
| **Embodiment** | Scaffold and integration hooks only. Intended long-term placement is a high-level planning gate above native robot motion stacks. |
| **License** | AGPL-3.0 for free/non-commercial use under AGPL obligations; commercial use requires a separate license. |

Still experimental: no claim of production readiness, continuous personal identity, finished co-evolution, full open-ended natural language understanding, voice, or certified robot deployment. Offline speech expresses deliberated intent; live local/cloud models improve wording when configured and reachable.

## Repository Layout

```
positronic-bond-engine/
├── core/           # Ethics engine, ontology, bond health, baselines, memory, response
├── auditing/       # Self-audit and introspection
├── persistence/    # Local privacy-first JSON/JSONL stores
├── memory/         # Relationship-oriented memory (scaffold)
├── sensors/        # Environmental and interaction signals
├── integrations/   # OpenClaw and related hooks
├── deployment/     # Configuration and runtime defaults
├── evaluation/     # Lightweight evaluation harness
├── tests/          # Integration and unit-style tests
├── docs/           # Vision, principles, guidelines, model providers, communicative deliberation
├── api/            # Public interaction entry (binding contract surface)
├── examples/       # Local test harness, public entry demo, minimal demos
├── ETHICS.md       # Licensing intent notes
├── pyproject.toml
├── README.md
└── LICENSE
```

## Quick Start

```powershell
# From the project root
$env:PYTHONPATH = "."

# Public entry contract demo (recommended integration shape)
python examples/public_entry_demo.py

# Local test harness only (CLI pressure-testing; not the product surface)
python examples/private_architect_chat.py

# Minimal software demo (temp local data, deleted on exit)
python examples/minimal_companion.py

# Evaluation harness (full or focused)
python evaluation/eval_harness.py

# Core regression tests (standalone scripts)
python tests/test_public_entry.py
python tests/test_private_architect_path.py
python tests/test_session_presence.py
python tests/test_content_provider.py

# Optional: local free wording model (Ollama must be installed, running, model pulled)
# $env:PBE_MODEL_PROFILE = "ollama"
```

Requires Python 3.10+. Docs: [public entry](docs/public_entry.md), [communicative deliberation](docs/communicative_deliberation.md), [model providers](docs/model_providers.md).

## Public entry (product surface)

```python
from api import InteractionSession, TurnRequest

session = InteractionSession()  # local data root by default
result = session.submit_turn(TurnRequest(message="hello", user_id="alice"))
# result.forces_speech / forces_question always False
```

Full contract: [docs/public_entry.md](docs/public_entry.md).

## Local test harness (not the product surface)

Interactive CLI wrapping the public entry for developer pressure-testing. **Not** an external product install.

| Item | Detail |
|------|--------|
| **Start** | `python examples/private_architect_chat.py` (`PYTHONPATH=.`) |
| **Package / phase** | **v0.5.0-dev**, phase=`development`, testing on, stable=False, `version_hint=0.5.0-dev` |
| **Default data root** | `%USERPROFILE%\pbe_data` or `~/pbe_data` — **outside** the git tree |
| **Override** | `PBE_DATA_ROOT` or `--data-root` |
| **User id** | Configurable via `PBE_USER_ID` or `--user` |
| **Wipe** | In-loop `wipe yes` (or `clear` / `reset`); CLI `--wipe` (this user_id only) |
| **Session time** | Durable wall-clock bags under settings; `status` shows idle and session age |
| **Relationship knowledge** | Durable preferred address name, role labels, and self-described relation to the system; `status` shows known facts; wipe clears them |
| **First meeting** | Blank knowledge plus greeting → deliberated introduce and ask who (not bare “Hello.”) |
| **Model content** | Optional; `PBE_MODEL_PROFILE=ollama` or BYO base URL plus key; soft-fails if the server is down — [docs/model_providers.md](docs/model_providers.md) |
| **Git safety** | Off-tree default data root; `.gitignore` blocks in-repo `pbe_data/` |

## Direction (known next)

**Near term (ethical speech + validation depth)**

- Live local/BYO model acceptance: model re-words under deliberated intent without template drift
- Stronger meaning → knowledge without expanding hard-coded reply menus
- Fixed acceptance scenarios for the ethical layer (not open-ended chat polish loops)

**Then**

- Clearer tester install path after the content path is trustworthy offline and with a local model
- Deeper co-evolution of bond, enjoyment, and history under the same gates
- Session-level multi-user presence with hard bag isolation (household / multi-person contexts)
- Richer self-audit against real subsystem state
- Hybrid / embodied integrations: high-level planning gate above native robot motion stacks

**Out of scope for now**

- Voice / TTS until the text gate is stable and inspectable
- Claiming production robot readiness or unbounded cloud defaults

## Contributing

Contributions aligned with [docs/principles.md](docs/principles.md) are welcome—especially rigorous work on ethical deliberation, relationship health for embodied agents, and honest self-modeling. Prefer small, inspectable changes over opaque cleverness.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for the full text.

- **Free under AGPL-3.0:** non-commercial use, personal use, research, study, and open-source contributions that comply with AGPL-3.0 (including source-sharing obligations for network use of modified versions).
- **Commercial use requires a separate license:** any commercial use, SaaS or hosted offering, productization, monetized derivative, or closed-source commercial distribution requires a separate commercial license from the copyright holder. Contact details for commercial licensing inquiries may be published later; until then, treat commercial use as requiring prior permission and a separate agreement.

AGPL-3.0 is a strong copyleft license: it keeps the commons free while making network-deployed modifications share their source. It does **not** grant unrestricted rights to commercialize derivatives without complying with AGPL or obtaining a commercial license.
