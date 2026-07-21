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

Key progress since the early modular skeleton (including foundation work through commits `e3d409f` / `8bad208`, July 2026):

- **Licensing** — Project is under **AGPL-3.0**; free for non-commercial / research use that complies with AGPL. **Commercial use requires a separate license** (see [License](#license) and [LICENSE](LICENSE)).
- **Durable living relationship model** — Per-user `BondState` / `BondStateRecord` can persist bond texture, health flags, soft pattern counters, understanding-gap / topic-continuity signals (`curious_companion`), multi-episode **concept patterns** (advisory trajectories only), and related co-evolution state via optional local JSON under `users/<user_id>/`. In-memory remains the default when persistence is not configured.
- **Careful Truth-Telling pipeline (non-speaking)** — Advisory-only stack: **TruthTellingReadiness** (timing), **TruthConfidence** (epistemic grounding), a **joint** readiness × confidence assessment (durable on bond state), and a **gated observation-candidate** layer (0–3 internal seeds, live + durable snapshot). Nothing here generates user-facing speech or forced questions; force flags stay false.
- **Signal-quality improvements (Tier 1)** — Ontology textbook scan uses token-boundary matching and specificity hygiene; weak / short indicators are down-weighted unless context co-factors or multi-channel evidence support them. High-severity intents and **Sanctity of Life** hard overrides remain strong and absolute.
- **Signal interpretation & multi-source weighing** — Matches still pass through intent / severity / weight / polarity; RH, agency, history, baseline, and concept-pattern channels combine with auditable `decision_basis` and confidence modulation.
- **Proactive history intent patterns** — Multi-episode history can elevate concern on moderate current signals when repeated problematic intent families appear, with explicit trace lines.
- **Decision-log provenance** — Optional local JSONL decision logs can carry compact `evidence_snapshot` bags (gaps, continuity, concept ids, careful-truth-telling / observation-candidate summaries) for later audit — not full episodic transcripts.
- **DevelopmentPhaseContext** — Lightweight maturity awareness for self-nature, continuity, and limitation reasoning without forced disclaimers on every reply.
- **Evaluation harness** — Full scenario suite remains **39/39**; focused runs for multi-channel weighing and multi-episode proactive history (`--weighing`, `--history-proactive`).

Ontology textbook version remains independently versioned (currently `0.2.x` in the engine traces); **project package version is 0.3.0**. Response generation stays intentionally paused.

## Current Status

| Area | State |
|------|--------|
| **EthicsEngine** | Ontology-driven deliberation with multi-source evidence combination, limited-data safeguards, hard Sanctity of Life override; attaches advisory truth-telling / observation-candidate signals when present |
| **Signal interpretation** | Intent / severity / weight / polarity; token-boundary textbook scan + specificity / weak-indicator hygiene; influences RH, agency, limited_data, and baseline paths |
| **Interaction history** | Local episodic store + structured analysis; proactive intent-pattern mining; understanding-gap / topic-continuity signals (optional) |
| **Relationship health** | Multi-dimensional bond texture + health flags; soft patterns; **concept patterns** (advisory); curious-companion gap/topic continuity; durable **careful_truth_telling** joint + **observation_candidates_snapshot**; optional per-user `bond_state.json` |
| **Careful Truth-Telling** | Readiness + confidence + joint assessment + gated observation candidates (0–3); live and durable; **fully advisory — no speech, no forced questions** |
| **Decision logs** | In-memory always; optional local JSONL append with compact **evidence_snapshot** provenance |
| **Per-user baseline** | Communication-style baseline + deviation (non-pathologizing); local persistence |
| **Development phase** | `DevelopmentPhaseContext` defaulting to active development / testing (`0.3-dev`) |
| **Self-audit** | Scaffold with development-phase honesty notes; not a complete self-model |
| **Response generation** | **Intentionally paused** — deliberative signals and candidates are inspectable only; no user-facing speech layer is open |
| **Companions / deployment** | Minimal demos and stubs; not a full companion product |
| **License** | AGPL-3.0; commercial use requires a separate license |

Still experimental: no claim of production readiness, continuous personal identity, finished relationship co-evolution, or that observation candidates will ever auto-surface as speech.

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

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for the full text.

- **Free under AGPL-3.0:** non-commercial use, personal use, research, study, and open-source contributions that comply with AGPL-3.0 (including source-sharing obligations for network use of modified versions).
- **Commercial use requires a separate license:** any commercial use, SaaS or hosted offering, productization, monetized derivative, or closed-source commercial distribution requires a separate commercial license from the copyright holder. Contact details for commercial licensing inquiries may be published later; until then, treat commercial use as requiring prior permission and a separate agreement.

AGPL-3.0 is a strong copyleft license: it keeps the commons free while making network-deployed modifications share their source. It does **not** grant unrestricted rights to commercialize derivatives without complying with AGPL or obtaining a commercial license.
