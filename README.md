# Positronic Bond Engine

> A conscience-first ethical governance layer for AI companions and in-home robotics.

**Version: v0.3** (experimental / active development)

The Positronic Bond Engine is an experimental framework for AI systems that can form healthy, long-term relationships with humans by reasoning about ethics, boundaries, selfhood, and mutual well-being — rather than through simulation or rigid external rules.

This is **not** a finished product. It is a living research and engineering effort: deliberative ethics are real and inspectable, but incomplete; persistence is optional and local; self-modeling remains honest about developmental limits.

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

## What's New in v0.3

Key progress since the early modular skeleton:

- **Signal interpretation** — Ontology matches are interpreted as intent / severity / weight / polarity, so a single raw keyword hit no longer drives decisions alone.
- **Multi-source weighing** — Relationship health, user agency, history, and baseline channels combine with auditable `decision_basis` and confidence modulation.
- **Proactive history intent patterns** — Multi-episode interaction history can elevate concern on moderate current signals when repeated problematic intent families appear (paternalistic override, attachment manufacturing, engagement coercion), with explicit trace lines.
- **Optional local persistence** — Privacy-first `BondState` and `DecisionLog` save/load via the existing `persistence/` layer (in-memory remains the default).
- **DevelopmentPhaseContext** — Lightweight maturity awareness for self-nature, continuity, and limitation reasoning without forced disclaimers on every reply.
- **Evaluation harness** — Focused runs for multi-channel weighing and multi-episode proactive history (`--weighing`, `--history-proactive`).

Ontology textbook version remains independently versioned (currently `0.2.x` in the engine traces); **project package version is 0.3.0**.

## Current Status

| Area | State |
|------|--------|
| **EthicsEngine** | Ontology-driven deliberation with multi-source evidence combination, limited-data safeguards, hard Sanctity of Life override |
| **Signal interpretation** | Intent / severity / weight / polarity layer; influences RH, agency, limited_data, and baseline paths |
| **Interaction history** | Local episodic store + structured analysis; proactive intent-pattern mining (optional) |
| **Relationship health** | Multi-dimensional bond texture + health flags; optional per-user `bond_state.json` persistence |
| **Decision logs** | In-memory always; optional append to local JSONL for audit |
| **Per-user baseline** | Communication-style baseline + deviation (non-pathologizing); local persistence |
| **Development phase** | `DevelopmentPhaseContext` defaulting to active development / testing (`0.3-dev`) |
| **Self-audit** | Scaffold with development-phase honesty notes; not a complete self-model |
| **Companions / deployment** | Minimal demos and stubs; not a full companion product |

Still experimental: no claim of production readiness, continuous personal identity, or finished relationship co-evolution.

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
```

Requires Python 3.10+.

## Next Steps

- Deeper long-term co-evolution of bond + history (beyond foundational persistence)
- Richer self-audit against real subsystem state
- Hybrid / embodied integrations under the same conscience gate
- Expanded evaluation coverage for agency, limited-data, and baseline × interpretation paths

## Contributing

Contributions aligned with [docs/principles.md](docs/principles.md) are welcome — especially rigorous work on ethical deliberation, relationship health, and honest self-modeling. Prefer small, inspectable changes over opaque cleverness.

## License

MIT License — see [LICENSE](LICENSE).
