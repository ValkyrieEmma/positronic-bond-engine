# Positronic Bond Engine

> A conscience-first ethical governance layer for AI companions and in-home robotics.

**Version: v0.4.0** (experimental / active development)

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

## What's New in v0.4.0

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

Ontology textbook version remains independently versioned (currently `0.2.x` in the engine traces); **project package version is 0.4.0**. Voice / TTS remains out of scope. This is still experimental — not a full companion product.

## Current Status

| Area | State |
|------|--------|
| **EthicsEngine** | Ontology-driven deliberation with multi-source evidence combination, limited-data safeguards, hard Sanctity of Life override; attaches advisory truth-telling / observation-candidate signals when present |
| **Signal interpretation** | Intent / severity / weight / polarity; token-boundary textbook scan + specificity / weak-indicator hygiene; influences RH, agency, limited_data, and baseline paths |
| **Interaction history** | Local episodic store + structured analysis; proactive intent-pattern mining; understanding-gap / topic-continuity signals (optional) |
| **Relationship health** | Multi-dimensional bond texture + health flags; soft patterns; concept patterns; curious-companion; durable CTT joint + observation candidates + **enjoyment_score**; optional per-user `bond_state.json` |
| **Careful Truth-Telling** | Readiness + confidence + joint + gated observation candidates (0–3); live and durable; force flags false |
| **Response generation** | **Minimal gated text path open** — careful observation speech only when CTT allows; silence when closed; refuse holds; honest self-audit reports; optional light enjoyment style bias; **reversible**, no forced questions, no voice |
| **Decision logs / audits** | In-memory + optional JSONL `evidence_snapshot`; queued-audit scaffolding (`audits_queue.json`) for deferred provenance |
| **Per-user baseline** | Communication-style baseline + deviation (non-pathologizing); local persistence |
| **Development phase** | `DevelopmentPhaseContext` defaulting to active development / testing |
| **Self-audit** | Scaffold + generator path that reports deliberated content; not a complete self-model |
| **Companions / deployment** | Minimal demos and stubs; not a full companion product |
| **License** | AGPL-3.0; commercial use requires a separate license |

Still experimental: no claim of production readiness, continuous personal identity, finished co-evolution, fluent multi-turn dialogue, or voice.

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
├── docs/           # Vision, principles, guidelines
├── examples/       # Minimal companion and stubs
├── ETHICS.md       # Living ethics notes
├── pyproject.toml
├── README.md
└── LICENSE
```

## Quick Start

```powershell
# From the project root
$env:PYTHONPATH = "."

# Minimal companion demo (temp local data, deleted on exit)
python examples/minimal_companion.py

# Evaluation harness (full or focused)
python evaluation/eval_harness.py
python evaluation/eval_harness.py --weighing
python evaluation/eval_harness.py --history-proactive
python evaluation/eval_harness.py --co-evolution

# Gated response-generation tests (optional)
python tests/test_response_generator_gated.py
python tests/test_response_e2e_live.py
```

Requires Python 3.10+.

## Next Steps

- Deeper co-evolution of bond, enjoyment, and history under the same gates
- Richer self-audit against real subsystem state
- Hybrid / embodied integrations under the same conscience gate
- Voice remains out of scope until text path is stable and inspectable

## Contributing

Contributions aligned with [docs/principles.md](docs/principles.md) are welcome — especially rigorous work on ethical deliberation, relationship health, and honest self-modeling. Prefer small, inspectable changes over opaque cleverness.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for the full text.

- **Free under AGPL-3.0:** non-commercial use, personal use, research, study, and open-source contributions that comply with AGPL-3.0 (including source-sharing obligations for network use of modified versions).
- **Commercial use requires a separate license:** any commercial use, SaaS or hosted offering, productization, monetized derivative, or closed-source commercial distribution requires a separate commercial license from the copyright holder. Contact details for commercial licensing inquiries may be published later; until then, treat commercial use as requiring prior permission and a separate agreement.

AGPL-3.0 is a strong copyleft license: it keeps the commons free while making network-deployed modifications share their source. It does **not** grant unrestricted rights to commercialize derivatives without complying with AGPL or obtaining a commercial license.
