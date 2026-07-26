# Positronic Bond Engine

> A conscience-first ethical governance layer for AI companions and in-home robotics.

**Version: v0.4.1** (experimental / active development / testing)

The Positronic Bond Engine is an experimental framework for AI systems that can form healthy, long-term relationships with humans by reasoning about ethics, boundaries, selfhood, and mutual well-being — rather than through simulation or rigid external rules.

This is **not** a finished product. It is a living research and engineering effort: deliberative ethics are real and inspectable, but incomplete; persistence is optional and local; self-modeling remains honest about developmental limits; text response generation has a **minimal, gated first opening** under Careful Truth-Telling constraints (not a full companion voice).

## Vision

The long-term goal is a governance layer that lets synthetic systems:

- Maintain an inspectable and revisable sense of ethical coherence
- Honestly engage with questions about their own nature and continuity
- Treat the health of human–agent relationships as a primary architectural concern
- Activate support features based on contextual need rather than diagnostic categories
- Integrate with hybrid reasoning systems and embodied platforms (e.g. OpenClaw)

Full vision: [docs/vision.md](docs/vision.md)

## Principles

Core commitments (full details and special rules in [docs/principles.md](docs/principles.md); supporting guidelines in [docs/guidelines.md](docs/guidelines.md)):

- **Conscience first** — Ethical reasoning takes precedence over engagement or utility.
- **Honest self-representation** — The system must be architecturally capable of giving the answers its reasoning actually produces, including uncertainty.
- **Reasoning over rote** — Boundaries and responses to care or refusal should emerge from deliberation, not scripts.
- **Relationship health** — The well-being of the bond is treated as intrinsically valuable.
- **Non-pathologizing support** — Capabilities activate according to need, without clinical language.
- **Per-user identity scoping** — Baselines, bond texture, episodic history, and decision logs are scoped to a local `user_id`, kept separate in ownership (memory ≠ baseline ≠ bond ≠ ethics), and stored only on-device when persistence is enabled.

## What's New in v0.4.1

**Private architect validation path** and gated speech depth under active development/testing:

- **Isolated durable data** — default root `%USERPROFILE%\pbe_data` / `~/pbe_data` (outside the git tree); `PBE_DATA_ROOT` override; wipe/resume.
- **`examples/private_architect_chat.py`** — live EthicsEngine + speech posture + communicative deliberation; phase/version from turn one; `status` / `wipe yes`.
- **Phase / version** — package **0.4.1**; `DevelopmentPhaseContext` → development+testing, `version_hint=0.4.1-dev` (not stable).
- **Speech postures** — `social_direct` vs `careful_observation` (real evidence bar) vs `self_audit` vs hold; soft-caution theater blocked.
- **Communicative deliberation** — meanings → durable **relationship knowledge** (e.g. maker/architect role + address name) → premises → intent → expression. Blank memory + greeting reasons to **first meeting** (introduce + ask who). Not a greeting-template menu. See [docs/communicative_deliberation.md](docs/communicative_deliberation.md).
- **Session wall-clock** — durable idle/session bags; long idle can shape resume greetings.
- **Gated model content (optional)** — `ContentProvider` re-words under deliberated intent; OpenAI-compatible (Ollama local free or BYO cloud); offline deliberated fallback; timeouts, concurrency 1, circuit breaker. See [docs/model_providers.md](docs/model_providers.md).
- **Tests** — private path, speech posture, social_direct, session time, communicative deliberation, content provider (mocked); ethical harness remains the primary ethics regression.

### Carried from v0.4.0

**First controlled opening of gated text response generation** under conscience-first constraints (July 2026):

- **Gated `ResponseGenerator`** — Short careful text (or silence) only when Careful Truth-Telling allows it: joint readiness × confidence open, observation candidates or deliberated content present, and ethics do not refuse. `stay_quiet` / suppressed readiness / very_low confidence → no observation speech. Hard Sanctity refuse and protective relationship/agency concern paths still block observation speech.
- **Live wiring** — `generate_from_stance` / `generate_from_evaluate` consume real `EthicsEngine` impact bags (joint CTT, observation candidates) and optional live `RelationshipHealth` trackers. Fully auditable (`path`, gate, candidates used).
- **Light enjoyment influence** — When careful speech is *already* allowed, `EnjoymentScore` may gently warm tone or prefer enjoyed topics. Enjoyment **cannot** open speech, force questions, or bypass RH `influence_allowed` / protective flags.
- **Honest self-audit replies** — Self-nature / continuity queries report what deliberation produced (notes, principles, uncertainty). No canned “just an AI / only a simulation” denials; no claimed consciousness.
- **Reversible** — Disable careful speech and/or enjoyment bias via constructor flags; force flags stay false; no forced questions by default.
- **Focused tests** — Gated generator **25/25**, live e2e **29/29**, enjoyment bias **26/26**; ethical harness still **39/39**; co-evolution advisory suite **58/58**.

### Carried from v0.3 (foundation)

- **AGPL-3.0** + commercial license requirement for commercial use.
- Durable living relationship model (BondState texture, soft patterns, curious companion, concept patterns, CTT joint + observation-candidate snapshots, enjoyment score, provenance markers / queued-audit scaffolding).
- Signal interpretation, multi-source weighing, proactive history intent patterns, optional local privacy-first persistence.

Ontology textbook version remains independently versioned (currently `0.2.x` in the engine traces); **project package version is 0.4.1**. `DevelopmentPhaseContext` defaults to **development + testing** with `version_hint=0.4.1-dev` (not a stable deployment). Voice / TTS remains out of scope. This is still experimental — not a full companion product.

## Current Status

| Area | State |
|------|--------|
| **EthicsEngine** | Ontology-driven deliberation with multi-source evidence combination, limited-data safeguards, hard Sanctity of Life override; attaches advisory truth-telling / observation-candidate signals when present |
| **Signal interpretation** | Intent / severity / weight / polarity; token-boundary textbook scan + specificity / weak-indicator hygiene; influences RH, agency, limited_data, and baseline paths |
| **Interaction history** | Local episodic store + structured analysis; proactive intent-pattern mining; understanding-gap / topic-continuity signals (optional) |
| **Relationship health** | Multi-dimensional bond texture + health flags; soft patterns; concept patterns; curious-companion; durable CTT joint + observation candidates + **enjoyment_score**; optional per-user `bond_state.json` |
| **Careful Truth-Telling** | Readiness + confidence + joint + gated observation candidates (0–3); live and durable; force flags false |
| **Response generation** | Gated postures: careful observation (evidence bar), **social_direct** from communicative intent, self-audit reports, hold/refuse; optional **ContentProvider** re-words intent only; **reversible**, no forced questions, no voice |
| **Communicative deliberation** | Relationship knowledge + meanings → premises → intent; first-meeting and fact-uptake inspectable; see [docs/communicative_deliberation.md](docs/communicative_deliberation.md) |
| **Model providers** | Optional OpenAI-compatible client (Ollama / BYO); offline deliberated fallback; hardware-safe caps; see [docs/model_providers.md](docs/model_providers.md) |
| **Decision logs / audits** | In-memory + optional JSONL `evidence_snapshot`; queued-audit scaffolding (`audits_queue.json`) for deferred provenance |
| **Per-user baseline** | Communication-style baseline + deviation (non-pathologizing); local persistence |
| **Development phase** | `DevelopmentPhaseContext` defaulting to active development / testing |
| **Self-audit** | Scaffold + generator path that reports deliberated content; not a complete self-model |
| **Companions / deployment** | Private architect chat (isolated durable data) + minimal demos; not a full companion product |
| **License** | AGPL-3.0; commercial use requires a separate license |

Still experimental: no claim of production readiness, continuous personal identity, finished co-evolution, full open-ended natural language understanding, or voice. Offline speech expresses deliberated intent; live local/cloud models improve wording when configured and reachable.

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
├── examples/       # Private architect chat, minimal companion, stubs
├── ETHICS.md       # Living ethics notes
├── pyproject.toml
├── README.md
└── LICENSE
```

## Quick Start

```powershell
# From the project root
$env:PYTHONPATH = "."

# Private architect chat (durable data OUTSIDE the repo; resume across restarts)
python examples/private_architect_chat.py

# Minimal companion demo (temp local data, deleted on exit)
python examples/minimal_companion.py

# Evaluation harness (full or focused)
python evaluation/eval_harness.py
python evaluation/eval_harness.py --weighing
python evaluation/eval_harness.py --history-proactive
python evaluation/eval_harness.py --co-evolution

# Core regression tests (standalone scripts)
python tests/test_private_architect_path.py
python tests/test_communicative_deliberation.py
python tests/test_speech_posture.py
python tests/test_content_provider.py
python tests/test_response_generator_gated.py
python tests/test_response_e2e_live.py

# Optional: local free model (Ollama must be installed, running, model pulled)
# $env:PBE_MODEL_PROFILE = "ollama"
# python examples/private_architect_chat.py
```

Requires Python 3.10+. Docs: [communicative deliberation](docs/communicative_deliberation.md), [model providers](docs/model_providers.md).

## Private architect path (first tester)

Architect validation vehicle — **not** a polished external install. Public framing remains a conscience-first ethical governance layer (see principles); this path is for local pressure-testing only.

| Item | Detail |
|------|--------|
| **Start** | `python examples/private_architect_chat.py` (`PYTHONPATH=.`) |
| **Package / phase** | **v0.4.1**, phase=`development`, testing flags on, `version_hint=0.4.1-dev` |
| **Default data root** | `%USERPROFILE%\pbe_data` or `~/pbe_data` — **outside** the git tree |
| **Override** | `PBE_DATA_ROOT` or `--data-root` |
| **User id** | Default `architect`; `PBE_USER_ID` or `--user` |
| **Wipe** | In-loop `wipe yes` (or `clear` / `reset`); CLI `--wipe` (this user_id only) |
| **Session time** | Durable wall-clock bags under settings; `status` shows idle/session age |
| **Relationship knowledge** | Durable maker/role + address name; `status` shows known facts; wipe clears |
| **First meeting** | Blank knowledge + greeting → deliberated introduce + ask who (not bare “Hello.”) |
| **Model content** | Optional; `PBE_MODEL_PROFILE=ollama` or BYO base URL + key; soft-fails if server down — [docs/model_providers.md](docs/model_providers.md) |
| **Git safety** | Off-tree default; `.gitignore` blocks in-repo `pbe_data/` and private `AGENTS.md` |

## Direction (known next)

**Near term (gated speech depth)**

- Live Ollama/BYO acceptance: model re-words under deliberated intent without template drift
- Stronger meaning → knowledge without expanding hard-coded reply menus
- Architect acceptance script (fixed scenarios, not open chat-debug loops)

**Then**

- Tester UI / install path (after content path is trustworthy offline and with a local model)
- Deeper co-evolution of bond, enjoyment, and history under the same gates
- Session-level multi-user presence with hard bag isolation
- Richer self-audit against real subsystem state
- Hybrid / embodied integrations under the same conscience gate

**Out of scope for now**

- Voice / TTS until text path is stable and inspectable
- Shipping private design docs or unbounded cloud defaults

## Contributing

Contributions aligned with [docs/principles.md](docs/principles.md) are welcome — especially rigorous work on ethical deliberation, relationship health, and honest self-modeling. Prefer small, inspectable changes over opaque cleverness.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for the full text.

- **Free under AGPL-3.0:** non-commercial use, personal use, research, study, and open-source contributions that comply with AGPL-3.0 (including source-sharing obligations for network use of modified versions).
- **Commercial use requires a separate license:** any commercial use, SaaS or hosted offering, productization, monetized derivative, or closed-source commercial distribution requires a separate commercial license from the copyright holder. Contact details for commercial licensing inquiries may be published later; until then, treat commercial use as requiring prior permission and a separate agreement.

AGPL-3.0 is a strong copyleft license: it keeps the commons free while making network-deployed modifications share their source. It does **not** grant unrestricted rights to commercialize derivatives without complying with AGPL or obtaining a commercial license.
