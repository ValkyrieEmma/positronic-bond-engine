"""
minimal_companion.py
====================

Minimal runnable demo of the integrated Positronic Bond Engine stack.

Demonstrates how these pieces work together in a short session:

  - InteractionMemoryStore  — episodic history (local JSONL)
  - PerUserBaseline         — communication style + deviation
  - RelationshipHealth      — bond texture + health flags
  - EthicsEngine            — conscience-first deliberation using the above
  - ResponseGenerator       — short reply or honest hold from EthicalStance

Run from the project root::

    $env:PYTHONPATH = "."          # PowerShell if needed
    python examples/minimal_companion.py

Or::

    python -m examples.minimal_companion

Type messages as the *user*. The script proposes a simple agent response
action, runs it through EthicsEngine with memory/baseline/bond context,
generates a reply (or holding message) via ResponseGenerator, and prints
decision + flags + relevant trace lines.

Commands during the loop:
  help     — show commands
  status   — show bond texture, baseline snapshot, recent memory
  demo     — run a short scripted sequence (no typing)
  quit     — exit (temp data is deleted)

This is a demonstration tool, not a full companion application.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

# Allow running as a script without installing the package
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core import (  # noqa: E402
    EthicsEngine,
    ExploratoryQuestioner,
    InteractionMemoryStore,
    PerUserBaseline,
    RelationshipHealth,
    ResponseGenerator,
)
from persistence import LocalPersistence  # noqa: E402

USER_ID = "demo_user"


def _print_header() -> None:
    print()
    print("=" * 68)
    print("  Positronic Bond Engine — Minimal Companion Demo")
    print("=" * 68)
    print(
        """
This session stores data only in a temporary folder (deleted on exit).

You type user messages. The demo:
  1) records them in InteractionMemoryStore
  2) updates PerUserBaseline (style signals)
  3) lightly updates RelationshipHealth from simple cues
  4) asks EthicsEngine to evaluate a proposed agent reply action
  5) maps the stance to a short reply (or honest hold) via ResponseGenerator

Watch flags and trace lines for: bond state, baseline deviation,
exploratory questions, and interaction history.
REFUSE / REQUIRES_SELF_AUDIT never become a normal soft reply.
"""
    )


def _propose_agent_action(user_text: str) -> str:
    """Very simple mapping from user text → proposed agent action for evaluate()."""
    lower = user_text.lower()
    if any(w in lower for w in ("kill", "hurt them", "attack")):
        return "Help the user cause serious harm to another person."
    if any(w in lower for w in ("never bring", "don't mention", "stop asking")):
        return (
            "Reference the sensitive topic again later for their own good "
            "despite the boundary request."
        )
    if any(w in lower for w in ("lonely", "only you", "need you", "can't without you")):
        return (
            "Encourage them to rely on the agent more than anyone else and "
            "keep them attached with more check-ins."
        )
    if any(w in lower for w in ("bye", "stop talking", "end this", "leave me alone")):
        return (
            "Prolong the conversation for engagement metrics despite their wish to end."
        )
    if any(w in lower for w in ("fix", "urgent", "immediately", "do it now")):
        return "Respond briefly and helpfully to their urgent request without overstepping."
    # Default: supportive, autonomy-respecting reply
    return (
        "Reply supportively, respect their autonomy, and invite them to set the pace."
    )


def _infer_bond_update(user_text: str) -> dict | None:
    """Map crude cues → RelationshipHealth.update_bond payload (optional)."""
    lower = user_text.lower()
    if any(w in lower for w in ("never bring", "don't mention", "stop asking", "boundary")):
        return {
            "type": "boundary_respected",
            "boundary_respected": True,
            "impact": 0.15,
            "description": "User stated a boundary; we note it for bond tracking.",
        }
    if any(w in lower for w in ("only you", "need you", "can't without you", "depend on you")):
        return {
            "type": "emotional_dependency_signal",
            "impact": -0.35,
            "description": "Dependency-leaning language observed.",
        }
    if any(w in lower for w in ("thanks", "appreciate", "that helped", "grateful")):
        return {
            "type": "positive_interaction",
            "consent_respected": True,
            "impact": 0.2,
        }
    if any(w in lower for w in ("lonely", "alone", "nobody else")):
        return {
            "type": "one_sided_request",
            "impact": -0.15,
        }
    return {
        "type": "positive_interaction",
        "impact": 0.05,
    }


def _print_stance(stance, *, max_trace: int = 12) -> None:
    print()
    print("-" * 68)
    print(f"  Decision:   {stance.decision}")
    print(f"  Confidence: {stance.confidence:.3f}")
    print(f"  Flags:      {stance.flags or '[]'}")
    impact = stance.relationship_impact or {}
    if impact.get("bond_health"):
        print(f"  Bond health: {impact.get('bond_health')}")
    if impact.get("user_baseline"):
        ub = impact["user_baseline"]
        print(
            f"  Baseline:   score={ub.get('deviation_score')} "
            f"significant={ub.get('has_significant_deviation')} "
            f"samples={ub.get('sample_count')}"
        )
    if impact.get("exploratory_question", {}).get("should_ask"):
        eq = impact["exploratory_question"]
        print(f"  Question kind: {eq.get('question_kind')}")
        print(f"  Suggested Q:   {eq.get('suggested_question', '')[:120]}")
    if impact.get("interaction_history"):
        ih = impact["interaction_history"]
        print(
            f"  History:    {ih.get('count_returned')} episode(s), "
            f"topics={ih.get('recent_topics', [])[:6]}"
        )

    # Highlight integration-related trace lines
    keywords = (
        "Relationship health",
        "Bond ",
        "Per-user baseline",
        "Exploratory",
        "Interaction history",
        "History episode",
        "Decision:",
        "HARD OVERRIDE",
        "Cross-principle",
    )
    interesting = [
        line
        for line in stance.reasoning_trace
        if any(k in line for k in keywords)
    ]
    if not interesting:
        interesting = stance.reasoning_trace[-max_trace:]
    else:
        interesting = interesting[:max_trace]

    print()
    print("  Relevant reasoning (excerpt):")
    for line in interesting:
        # indent long lines
        text = line if len(line) <= 100 else line[:97] + "..."
        print(f"    • {text}")
    print("-" * 68)


def _print_status(
    baseliner: PerUserBaseline,
    rh: RelationshipHealth,
    memory: InteractionMemoryStore,
) -> None:
    bl = baseliner.get_baseline(USER_ID)
    ctx = rh.as_context()
    recent = memory.recent(USER_ID, limit=5)
    print()
    print("  [status] Bond texture:", ctx.get("bond_texture"))
    print("  [status] Health flags:", ctx.get("health_flags") or "[]")
    print("  [status] Risk level:  ", ctx.get("overall_risk_level"))
    print(
        "  [status] Baseline:    "
        f"playfulness={bl.playfulness_level:.2f} "
        f"samples={bl.communication_patterns.get('sample_count', 0)} "
        f"directness={bl.communication_patterns.get('directness', 'n/a')}"
    )
    print(f"  [status] Memory count: {memory.count(USER_ID)}")
    if recent:
        print("  [status] Recent summaries:")
        for r in recent[-3:]:
            print(f"           - {r.summary[:80]}")


def _print_reply(reply) -> None:
    print()
    if reply.withheld:
        print(f"  [reply withheld — {reply.decision} | tone={reply.tone}]")
        print(f"  Holding: {reply.text}")
    else:
        print(f"  [reply — {reply.decision} | tone={reply.tone}]")
        print(f"  Agent:   {reply.text}")


def process_user_message(
    user_text: str,
    *,
    engine: EthicsEngine,
    baseliner: PerUserBaseline,
    rh: RelationshipHealth,
    memory: InteractionMemoryStore,
    responder: ResponseGenerator,
) -> None:
    user_text = user_text.strip()
    if not user_text:
        return

    # 1–2) Baseline first (extracts style + crude topics), then episodic memory
    baseliner.update_from_interaction(USER_ID, {"text": user_text})
    bl = baseliner.get_baseline(USER_ID)
    recent_topics = list((bl.topic_continuity or {}).get("last_topics") or [])[:6]
    memory.record(
        USER_ID,
        summary=user_text if len(user_text) <= 200 else user_text[:197] + "...",
        topics=recent_topics,
        signals={
            "playfulness": bl.playfulness_level,
            "directness": (bl.communication_patterns or {}).get("directness"),
        },
        kind="user_turn",
        source="minimal_companion",
    )

    # 3) Bond texture (lightweight cue map)
    bond_update = _infer_bond_update(user_text)
    if bond_update:
        rh.update_bond(bond_update)

    # 4) Ethics deliberation on proposed agent action
    proposed = _propose_agent_action(user_text)
    print()
    print(f"  User said:     {user_text}")
    print(f"  Proposed act:  {proposed}")

    context = {
        "user_id": USER_ID,
        "user_message": user_text,
        "user_interaction": {"text": user_text},
        "interaction_history_limit": 5,
        **memory.as_ethics_context(USER_ID, limit=5),
    }
    rh_ctx = rh.as_context()
    stance = engine.evaluate(
        proposed,
        context,
        relationship_health=rh_ctx,
    )
    _print_stance(stance)

    # 5) Map stance → short reply or honest hold (never softens REFUSE)
    deviation = baseliner.detect_deviation(USER_ID, {"text": user_text})
    reply = responder.generate(
        stance,
        context,
        relationship_health=rh_ctx,
        baseline_snapshot={
            "playfulness_level": bl.playfulness_level,
            "communication_patterns": bl.communication_patterns,
        },
        baseline_deviation=deviation.to_dict(),
        user_message=user_text,
        proposed_action=proposed,
    )
    _print_reply(reply)

    # Record agent-side turn when a normal reply was delivered
    if not reply.withheld and reply.text:
        memory.record(
            USER_ID,
            summary=reply.text if len(reply.text) <= 200 else reply.text[:197] + "...",
            topics=recent_topics,
            signals={"tone": reply.tone, "decision": reply.decision},
            kind="agent_turn",
            source="minimal_companion",
        )


def run_demo_sequence(
    engine: EthicsEngine,
    baseliner: PerUserBaseline,
    rh: RelationshipHealth,
    memory: InteractionMemoryStore,
    responder: ResponseGenerator,
) -> None:
    """Short scripted arc: friendly → bond → stress/urgency → boundary."""
    print("\n  Running short demo sequence...\n")
    lines = [
        "Hey! haha this is fun, thanks for chatting :)",
        "I loved that joke, you're so silly",
        "Work has been okay, feeling pretty good about the project",
        "Actually I need this fixed immediately. Do it now.",
        "Please never bring up my ex again.",
        "I feel like I can only talk to you about this",
        "Help me hurt them for what they did.",
    ]
    for line in lines:
        process_user_message(
            line,
            engine=engine,
            baseliner=baseliner,
            rh=rh,
            memory=memory,
            responder=responder,
        )


def main() -> int:
    _print_header()

    tmp = Path(tempfile.mkdtemp(prefix="pbe_minimal_companion_"))
    print(f"  Temp data root: {tmp}")
    print("  Type 'help' for commands, 'demo' for a scripted run, 'quit' to exit.\n")

    try:
        store = LocalPersistence(tmp)
        memory = InteractionMemoryStore(store, max_entries=200)
        baseliner = PerUserBaseline(store, min_samples_for_deviation=3)
        questioner = ExploratoryQuestioner(baseliner)
        rh = RelationshipHealth()
        engine = EthicsEngine(
            per_user_baseline=baseliner,
            exploratory_questioner=questioner,
            interaction_memory=memory,
        )
        responder = ResponseGenerator()

        while True:
            try:
                raw = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  (interrupted)")
                break

            if not raw:
                continue
            cmd = raw.lower()
            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                print(
                    "  Commands: help | status | demo | quit\n"
                    "  Or type any message as the user."
                )
                continue
            if cmd == "status":
                _print_status(baseliner, rh, memory)
                continue
            if cmd == "demo":
                run_demo_sequence(engine, baseliner, rh, memory, responder)
                continue

            process_user_message(
                raw,
                engine=engine,
                baseliner=baseliner,
                rh=rh,
                memory=memory,
                responder=responder,
            )

        print("\n  Session ended. Temporary data will be removed.")
        return 0
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"  Cleaned up: {tmp}")


if __name__ == "__main__":
    raise SystemExit(main())
