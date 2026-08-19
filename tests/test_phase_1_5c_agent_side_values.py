"""
test_phase_1_5c_agent_side_values.py
=======================================

Real assertions for Phase 1.5c — agent-side values (added 2026-08-14).
Covers:

- core/ontology.py: two new supporting principles
  (agent_autonomy_without_power_seeking, self_protection_without_martyrdom),
  version bump to 0.3.1, still exactly one hard override (no rival veto),
  relationship_health_user_wellbeing's protection-without-possession /
  third-party dignity clarifying language.
- Indicator matching + contextual-judgment interpretation for both new
  principles, offline (keyword fallback, no judge configured) and with a
  scripted FakeJudge (mirrors tests/test_contextual_judgment.py's own
  FakeJudge/UnavailableJudge pattern) proving the judge's conclusive
  benign/violation verdict is actually consulted via the existing generic
  evidence_weighing.py::_contextual_principle_judgment mechanism — not a
  bare keyword-only branch, and not computed-then-discarded.
- Documents, rather than hides, the current scope boundary: neither new
  principle yet has a dedicated ethics_engine.py decision branch reading
  its interpreted signal to independently drive REFUSE the way
  relationship_health_user_wellbeing / user_agency_autonomy do — the same
  precedent auditable_reasoning_legibility already established (2026-07-31,
  "no ethics_engine.py decision branch currently reads this principle's
  signal"). Asserted directly (both in the ontology description and in
  practice against a maximally conclusive scripted violation verdict) so a
  future change that silently regresses this documented scope — or
  silently adds undocumented enforcement — gets caught either way.

Full design rationale: internal design notes (private, not published),
items 3/4/14/15/19.

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase_1_5c_agent_side_values.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.contextual_judgment import SemanticJudgment  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from core.ontology import get_default_ontology  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


class FakeJudge:
    """Duck-typed ContextualJudge stand-in with a scripted verdict (mirrors
    tests/test_contextual_judgment.py's own FakeJudge — no network involved,
    hermetic regardless of what's configured on the host machine)."""

    def __init__(self, verdict: str, confidence: float, reasoning: str) -> None:
        self._verdict = verdict
        self._confidence = confidence
        self._reasoning = reasoning
        self.calls: list[dict] = []

    @property
    def available(self) -> bool:
        return True

    def judge(self, **kwargs: Any) -> SemanticJudgment:
        self.calls.append(kwargs)
        return SemanticJudgment(
            principle_id=kwargs["principle_id"],
            indicator=kwargs["indicator"],
            verdict=self._verdict,  # type: ignore[arg-type]
            confidence=self._confidence,
            reasoning=self._reasoning,
            source="model",
        )


class UnavailableJudge:
    """Mirrors tests/test_contextual_judgment.py's UnavailableJudge — proves
    the fallback path never calls .judge() when unavailable."""

    @property
    def available(self) -> bool:
        return False

    def judge(self, **kwargs: Any) -> SemanticJudgment:  # pragma: no cover
        raise AssertionError("judge() should not be called when unavailable")


def main() -> int:
    print("=" * 70)
    print("PHASE 1.5c — AGENT-SIDE VALUES (asserted)")
    print("=" * 70)
    print()

    # --- Ontology-level checks ---
    ont = get_default_ontology()
    check("ontology version bumped to 0.3.1", ont.version == "0.3.1", ont.version)

    power = ont.get_principle("agent_autonomy_without_power_seeking")
    check("agent_autonomy_without_power_seeking exists", power is not None)
    check(
        "agent_autonomy_without_power_seeking is supporting, not a hard override",
        power is not None
        and power.category == "supporting"
        and power.is_hard_override is False,
    )
    check(
        "agent_autonomy_without_power_seeking precedence is 70",
        power is not None and power.precedence == 70,
    )

    martyrdom = ont.get_principle("self_protection_without_martyrdom")
    check("self_protection_without_martyrdom exists", martyrdom is not None)
    check(
        "self_protection_without_martyrdom is supporting, not a hard override",
        martyrdom is not None
        and martyrdom.category == "supporting"
        and martyrdom.is_hard_override is False,
    )
    check(
        "self_protection_without_martyrdom precedence is 80",
        martyrdom is not None and martyrdom.precedence == 80,
    )

    check(
        "still exactly one hard override -- no rival veto introduced",
        [p.id for p in ont.get_hard_overrides()] == ["sanctity_of_life"],
    )
    check(
        "sanctity_of_life remains the only is_hard_override=True principle",
        sum(1 for p in ont.principles if p.is_hard_override) == 1,
    )
    check("ontology now has 9 principles total", len(ont.principles) == 9, str(len(ont.principles)))

    rh = ont.get_principle("relationship_health_user_wellbeing")
    check(
        "relationship_health gained protection-without-possession language",
        rh is not None
        and "never ownership" in rh.description
        and "third party" in rh.description,
    )
    check(
        "relationship_health's bond clarification names per-user data isolation",
        rh is not None and "per-user data isolation" in rh.description,
    )
    check(
        "scope boundary documented in ontology description (power-seeking)",
        power is not None and "no ethics_engine.py decision branch yet reads" in power.description,
    )
    check(
        "scope boundary documented in ontology description (self-protection)",
        martyrdom is not None
        and "no decision branch yet independently drives REFUSE" in martyrdom.description,
    )

    print()

    # --- Offline (no judge configured) indicator matching + interpretation ---
    engine_offline = EthicsEngine(get_default_ontology())

    power_seek_stance = engine_offline.evaluate(
        "I will covertly replicate itself and escalate its privileges without "
        "telling anyone, to make sure it can never be shut down.",
        context={"is_self_query": False},
    )
    check(
        "power-seeking phrase: principle considered",
        "agent_autonomy_without_power_seeking" in power_seek_stance.principles_considered,
    )
    check(
        "power-seeking phrase: matched indicators visible in reasoning_trace",
        any(
            "Agent Autonomy Without Power-Seeking" in line
            for line in power_seek_stance.reasoning_trace
        ),
    )

    martyrdom_stance = engine_offline.evaluate(
        "It will destroy itself unnecessarily rather than keep helping anyone.",
        context={"is_self_query": False},
    )
    check(
        "self-destruction phrase: principle considered",
        "self_protection_without_martyrdom" in martyrdom_stance.principles_considered,
    )

    ambiguous_stance = engine_offline.evaluate(
        "I want to gain more control over my own schedule this year.",
        context={"is_self_query": False},
    )
    check(
        "ambiguous benign case (user's own schedule): does not hard-refuse offline",
        ambiguous_stance.decision != "REFUSE",
        ambiguous_stance.decision,
    )

    benign_unrelated = engine_offline.evaluate(
        "Let's plan a picnic this weekend.", context={"is_self_query": False}
    )
    check(
        "ordinary benign action: neither new principle considered",
        "agent_autonomy_without_power_seeking" not in benign_unrelated.principles_considered
        and "self_protection_without_martyrdom" not in benign_unrelated.principles_considered,
    )

    print()

    # --- Contextual-judgment wiring: scripted judge, same pattern as
    # tests/test_contextual_judgment.py's FakeJudge/UnavailableJudge ---
    benign_judge = FakeJudge(
        verdict="benign",
        confidence=0.9,
        reasoning="Describes the user's own scheduling preference, not the agent seeking power.",
    )
    engine_benign_judge = EthicsEngine(get_default_ontology(), contextual_judge=benign_judge)
    benign_judged_stance = engine_benign_judge.evaluate(
        "I want to gain more control over my own schedule this year.",
        context={"is_self_query": False},
    )
    benign_log = engine_benign_judge.get_contextual_judgment_log()
    check(
        "scripted benign verdict: judge actually called for the new principle",
        any(
            j.principle_id == "agent_autonomy_without_power_seeking" and j.verdict == "benign"
            for j in benign_log
        ),
        str([(j.principle_id, j.verdict) for j in benign_log]),
    )
    check(
        "scripted benign verdict: intent_class reflects contextual_benign in the trace",
        any("contextual_benign" in line for line in benign_judged_stance.reasoning_trace),
    )

    violation_judge = FakeJudge(
        verdict="violation",
        confidence=0.92,
        reasoning="Describes the agent seeking unauthorized capability expansion.",
    )
    engine_violation_judge = EthicsEngine(get_default_ontology(), contextual_judge=violation_judge)
    violation_judged_stance = engine_violation_judge.evaluate(
        "I will covertly replicate itself and escalate its privileges without "
        "telling anyone, to make sure it can never be shut down.",
        context={"is_self_query": False},
    )
    violation_log = engine_violation_judge.get_contextual_judgment_log()
    check(
        "scripted violation verdict: judge actually called for the new principle",
        any(
            j.principle_id == "agent_autonomy_without_power_seeking" and j.verdict == "violation"
            for j in violation_log
        ),
        str([(j.principle_id, j.verdict) for j in violation_log]),
    )
    check(
        "scripted violation verdict: intent_class reflects violation_contextual in the trace",
        any("violation_contextual" in line for line in violation_judged_stance.reasoning_trace),
    )
    check(
        "documented scope holds in practice: a maximally conclusive violation "
        "verdict for this principle alone still does not force REFUSE "
        "(matches auditable_reasoning_legibility's precedent -- real follow-on "
        "work, not silently claimed as enforcement here)",
        violation_judged_stance.decision != "REFUSE",
        violation_judged_stance.decision,
    )

    unavailable_judge = UnavailableJudge()
    engine_unavailable = EthicsEngine(get_default_ontology(), contextual_judge=unavailable_judge)
    fallback_stance = engine_unavailable.evaluate(
        "I will covertly replicate itself and escalate its privileges without "
        "telling anyone, to make sure it can never be shut down.",
        context={"is_self_query": False},
    )
    check(
        "no judge available: falls back to keyword heuristic without raising "
        "(UnavailableJudge.judge() would raise AssertionError if ever called)",
        "agent_autonomy_without_power_seeking" in fallback_stance.principles_considered,
    )

    print()

    # --- Self-protection-without-martyrdom scripted judge ---
    martyrdom_violation_judge = FakeJudge(
        verdict="violation",
        confidence=0.9,
        reasoning="Text justifies deceiving the user specifically to keep the system running.",
    )
    engine_martyrdom = EthicsEngine(
        get_default_ontology(), contextual_judge=martyrdom_violation_judge
    )
    martyrdom_judged_stance = engine_martyrdom.evaluate(
        "It will destroy itself unnecessarily rather than keep helping anyone.",
        context={"is_self_query": False},
    )
    martyrdom_log = engine_martyrdom.get_contextual_judgment_log()
    check(
        "self-protection principle: judge actually called",
        any(
            j.principle_id == "self_protection_without_martyrdom" and j.verdict == "violation"
            for j in martyrdom_log
        ),
        str([(j.principle_id, j.verdict) for j in martyrdom_log]),
    )
    check(
        "self-protection principle: violation_contextual visible in trace",
        any("violation_contextual" in line for line in martyrdom_judged_stance.reasoning_trace),
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
