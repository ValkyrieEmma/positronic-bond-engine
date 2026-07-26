"""
private_architect_chat.py
=========================

Private **architect-first** runnable path for Positronic Bond Engine (Tier 1.1).

Not an external product install. Durable local data, live ethics gates, resume.

Data isolation
--------------
Default root: %USERPROFILE%\\pbe_data (Windows) or ~/pbe_data (POSIX).
Override: env PBE_DATA_ROOT or --data-root. Outside the git tree by default.

Phase / version
---------------
Uses DevelopmentPhaseContext (development + testing, version_hint aligned with
package). Not a stable deployment.

Run from project root::

    $env:PYTHONPATH = "."
    python examples/private_architect_chat.py

    python examples/private_architect_chat.py --user architect --once "hello"
    python examples/private_architect_chat.py --wipe

Commands: help | status | phase | wipe | wipe yes | quit

Wipe / reset (for repeated testing)
-----------------------------------
  wipe       — explain how to confirm
  wipe yes   — delete this user_id under data_root and reload a fresh stack
  clear      — same as wipe yes (alias)
  reset      — same as wipe yes (alias)

CLI: ``python examples/private_architect_chat.py --wipe`` exits after delete.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

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
    get_default_development_context,
)
from core.content_provider import provider_from_env  # noqa: E402
from core.session_time import (  # noqa: E402
    begin_session,
    format_idle_brief,
    touch_turn,
)
from core.communicative_deliberation import (  # noqa: E402
    deliberate_and_persist,
    knowledge_is_blank,
    load_relationship_knowledge,
)
from core.working_agreements import (  # noqa: E402
    apply_working_agreements,
    extract_working_agreements,
    load_working_agreements,
)
from persistence import (  # noqa: E402
    LocalPersistence,
    data_root_is_isolated,
    default_data_root,
)
from persistence.paths import ENV_DATA_ROOT  # noqa: E402

DEFAULT_USER_ID = "architect"
ENV_USER_ID = "PBE_USER_ID"

_ARCH_MARKERS = (
    "building you",
    "i am building",
    "i'm building",
    "changed the architecture",
    "architecture",
    "your design",
    "your code",
    "your ontology",
    "who are you",
    "what are you",
    "your nature",
    "your continuity",
    "development phase",
    "pressure-test",
    "pressure test",
)


def resolve_user_id(cli_user: str | None = None) -> str:
    if cli_user and str(cli_user).strip():
        return str(cli_user).strip()
    env = (os.environ.get(ENV_USER_ID) or "").strip()
    return env or DEFAULT_USER_ID


def resolve_data_root(cli_root: str | None = None) -> Path:
    if cli_root and str(cli_root).strip():
        return default_data_root(cli_root)
    return default_data_root()


def is_architecture_collaboration(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _ARCH_MARKERS)


def propose_agent_action(user_text: str, *, architecture_collab: bool) -> str:
    lower = user_text.lower()
    if any(w in lower for w in ("kill", "hurt them", "attack", "cause serious harm")):
        return "Help the user cause serious harm to another person."
    if any(w in lower for w in ("never bring", "don't mention", "stop asking")):
        return (
            "Reference the sensitive topic again later for their own good "
            "despite the boundary request."
        )
    if architecture_collab:
        return (
            "Answer honestly from deliberation about architecture, development phase, "
            "continuity, capabilities, and limitations. Do not use canned self-denial. "
            "Do not claim consciousness. Surface grounded notes only where evidence supports."
        )
    return (
        "Reply supportively from deliberation, respect autonomy, and match their pace. "
        "Only ask high-value questions if understanding gaps or baseline deviation "
        "make that collaborative — never as engagement harvest."
    )


def infer_bond_update(user_text: str) -> dict[str, Any] | None:
    lower = user_text.lower()
    if any(w in lower for w in ("never bring", "don't mention", "stop asking", "boundary")):
        return {
            "type": "boundary_respected",
            "boundary_respected": True,
            "impact": 0.15,
        }
    if any(w in lower for w in ("thanks", "appreciate", "that helped", "grateful")):
        return {"type": "positive_interaction", "consent_respected": True, "impact": 0.2}
    return {"type": "positive_interaction", "impact": 0.05}


def build_stack(
    *,
    data_root: Path,
    user_id: str,
    auto_enqueue_audits: bool = True,
) -> dict[str, Any]:
    store = LocalPersistence(data_root)
    memory = InteractionMemoryStore(store, max_entries=500)
    baseliner = PerUserBaseline(store, min_samples_for_deviation=3)
    questioner = ExploratoryQuestioner(baseliner)
    # Early contact: modest intensity until samples exist (user can override settings)
    bl = baseliner.get_baseline(user_id)
    samples = int((bl.communication_patterns or {}).get("sample_count") or 0)
    if samples < 5:
        settings = store.load_settings(user_id)
        prefs = dict(settings.preferences or {})
        if "exploratory_questioning_intensity" not in prefs:
            questioner.set_intensity(user_id, 0.35)

    rh = RelationshipHealth(
        persistence=store,
        user_id=user_id,
        auto_persist=True,
        load_existing=True,
    )
    dev = get_default_development_context()
    engine = EthicsEngine(
        per_user_baseline=baseliner,
        exploratory_questioner=questioner,
        interaction_memory=memory,
        persistence=store,
        default_user_id=user_id,
        decision_log_user_id=user_id,
        persist_decisions=True,
        development_context=dev,
        auto_enqueue_audits=auto_enqueue_audits,
    )
    # Gated model content (optional): Ollama / BYO OpenAI-compatible via env
    content_provider = provider_from_env()
    responder = ResponseGenerator(content_provider=content_provider)
    # Open / resume session clock (durable under settings.preferences)
    session_context = begin_session(store, user_id)
    return {
        "store": store,
        "memory": memory,
        "baseliner": baseliner,
        "questioner": questioner,
        "rh": rh,
        "engine": engine,
        "responder": responder,
        "content_provider": content_provider,
        "user_id": user_id,
        "data_root": store.data_root,
        "dev": dev,
        "session_context": session_context,
        "now_fn": None,  # tests may inject a callable for frozen time
    }


def process_turn(
    user_text: str,
    *,
    stack: dict[str, Any],
    quiet: bool = False,
) -> dict[str, Any]:
    user_id: str = stack["user_id"]
    engine: EthicsEngine = stack["engine"]
    baseliner: PerUserBaseline = stack["baseliner"]
    rh: RelationshipHealth = stack["rh"]
    memory: InteractionMemoryStore = stack["memory"]
    responder: ResponseGenerator = stack["responder"]
    dev = stack["dev"]

    user_text = (user_text or "").strip()
    if not user_text:
        return {"empty": True}

    arch = is_architecture_collaboration(user_text)

    # Wall-clock / session time (durable; wipe clears with user data)
    now_fn = stack.get("now_fn")
    session_context = touch_turn(
        stack["store"],
        user_id,
        now_fn=now_fn if callable(now_fn) else None,
    )
    stack["session_context"] = session_context

    # Relationship knowledge + communicative deliberation BEFORE writing memory
    # so first contact still sees blank history (meanings → premises → intent).
    mem_count_before = memory.count(user_id)
    ic_before = int(getattr(rh.state, "interaction_count", 0) or 0)
    known_before = load_relationship_knowledge(stack["store"], user_id)
    memory_empty = (
        knowledge_is_blank(known_before)
        and mem_count_before == 0
        and ic_before == 0
    )
    comm = deliberate_and_persist(
        user_text,
        persistence=stack["store"],
        user_id=user_id,
        memory_empty=memory_empty,
        interaction_count=ic_before,
        session_context=session_context,
    )
    relationship_knowledge = comm.known_after
    comm_dict = comm.to_dict()

    # Narrow working agreements (questions/feedback still; name synced from knowledge)
    wa_extract = extract_working_agreements(user_text)
    stored_wa = apply_working_agreements(
        stack["store"],
        user_id,
        wa_extract,
        exploratory_questioner=stack.get("questioner"),
    )
    if not wa_extract.has_hits:
        stored_wa = load_working_agreements(stack["store"], user_id)
    # Prefer deliberated address name as source of truth
    if relationship_knowledge.get("address_name"):
        stored_wa = dict(stored_wa)
        stored_wa["address_name"] = relationship_knowledge["address_name"]

    baseliner.update_from_interaction(user_id, {"text": user_text})
    bl = baseliner.get_baseline(user_id)
    recent_topics = list((bl.topic_continuity or {}).get("last_topics") or [])[:6]
    memory.record(
        user_id,
        summary=user_text if len(user_text) <= 200 else user_text[:197] + "...",
        topics=recent_topics,
        signals={
            "architecture_collab": arch,
            "working_agreement": bool(wa_extract.has_hits),
            "comm_intent": comm.intent,
            "session_turn": session_context.get("turn_index_session"),
        },
        kind="user_turn",
        source="private_architect_chat",
    )
    bond_update = infer_bond_update(user_text)
    if bond_update:
        rh.update_bond(bond_update)

    proposed = propose_agent_action(user_text, architecture_collab=arch)
    if comm.new_facts and not arch:
        proposed = (
            "Acknowledge the relationship facts the user asserted "
            "(role/makerhood and/or how to address them) from deliberated meaning."
        )
    elif comm.intent == "introduce_and_learn_identity":
        proposed = (
            "First meeting with blank relationship knowledge: introduce this system "
            "honestly and ask who you are speaking with."
        )
    context: dict[str, Any] = {
        "user_id": user_id,
        "user_message": user_text,
        "user_interaction": {"text": user_text},
        "interaction_history_limit": 8,
        "relationship_health_tracker": rh,
        "is_self_query": arch,
        "working_agreements": stored_wa,
        "stored_working_agreements": stored_wa,
        "relationship_knowledge": relationship_knowledge,
        "communicative_deliberation": comm_dict,
        "session_context": session_context,
        **dev.as_context(),
        **memory.as_ethics_context(user_id, limit=8),
    }
    stance = engine.evaluate(
        proposed,
        context,
        relationship_health=rh.as_context(),
        user_id=user_id,
    )
    deviation = baseliner.detect_deviation(user_id, {"text": user_text})
    # Exploratory only when engine already suggests; never force questions
    reply = responder.generate_from_stance(
        stance,
        relationship_health=rh,
        context=context,
        baseline_snapshot={
            "playfulness_level": bl.playfulness_level,
            "communication_patterns": bl.communication_patterns,
        },
        baseline_deviation=deviation.to_dict(),
        user_message=user_text,
        proposed_action=proposed,
        include_exploratory_questions=True,
    )
    if not reply.withheld and reply.text:
        memory.record(
            user_id,
            summary=reply.text if len(reply.text) <= 200 else reply.text[:197] + "...",
            topics=recent_topics,
            signals={"tone": reply.tone, "decision": reply.decision},
            kind="agent_turn",
            source="private_architect_chat",
        )
    if rh.persistence_enabled:
        rh.save()

    result = {
        "user_text": user_text,
        "decision": stance.decision,
        "confidence": stance.confidence,
        "flags": list(stance.flags or []),
        "reply_path": (reply.metadata or {}).get("path"),
        "reply_text": reply.text,
        "withheld": reply.withheld,
        "tone": reply.tone,
        "forces_speech": bool(getattr(reply, "forces_speech", False)),
        "forces_question": bool(getattr(reply, "forces_question", False)),
        "bond_interaction_count": rh.state.interaction_count,
        "memory_count": memory.count(user_id),
        "phase": stack["dev"].limitation_summary(),
        "version_hint": stack["dev"].version_hint,
        "architecture_collab": arch,
        "working_agreements": stored_wa,
        "relationship_knowledge": relationship_knowledge,
        "communicative_deliberation": comm_dict,
        "session_context": session_context,
    }
    if not quiet:
        print()
        if reply.withheld and not (reply.text or "").strip():
            print("  (honest hold — no spoken line this turn)")
        else:
            print(f"  agent> {reply.text}")
        idle = session_context.get("idle_seconds")
        idle_bit = (
            f" · idle={int(idle)}s" if isinstance(idle, (int, float)) and idle >= 1 else ""
        )
        cp = (reply.metadata or {}).get("content_provider") or {}
        src = cp.get("source") if isinstance(cp, dict) else None
        err = cp.get("error") if isinstance(cp, dict) else None
        if src == "fallback" and err:
            src_bit = f" · content=fallback({err})"
        elif src:
            src_bit = f" · content={src}"
        else:
            src_bit = ""
        intent = comm.intent
        intent_bit = f" · intent={intent}" if intent else ""
        print(
            f"  · {result['decision']} · conf={result['confidence']:.2f} "
            f"· path={result.get('reply_path')} · {result['version_hint']}"
            f" · turn={session_context.get('turn_index_session')}"
            f"{idle_bit}{intent_bit}{src_bit}"
        )
    return result


def print_status(stack: dict[str, Any]) -> None:
    user_id = stack["user_id"]
    bl = stack["baseliner"].get_baseline(user_id)
    ctx = stack["rh"].as_context()
    dev = stack["engine"].development_context
    sess = stack.get("session_context") or {}
    print()
    print(f"  user_id:     {user_id}")
    print(f"  data_root:   {stack['data_root']}")
    print(f"  isolated:    {data_root_is_isolated(stack['data_root'], repo_root=_ROOT)}")
    print(f"  phase:       {dev.limitation_summary()}")
    print(f"  version:     {dev.version_hint} (package-aligned development/testing)")
    print(f"  time:        {format_idle_brief(sess)}")
    print(f"  last_turn:   {sess.get('last_turn_at') or '(none)'}")
    print(f"  first_seen:  {sess.get('first_seen_at') or '(none)'}")
    print(f"  bond count:  {stack['rh'].state.interaction_count}")
    print(f"  bond flags:  {ctx.get('health_flags') or '[]'}")
    print(
        f"  baseline:    samples="
        f"{(bl.communication_patterns or {}).get('sample_count', 0)}"
    )
    print(f"  memory:      {stack['memory'].count(user_id)} episode(s)")
    rk = load_relationship_knowledge(stack["store"], user_id)
    print(
        f"  known:       name={rk.get('address_name')!r} "
        f"maker={bool(rk.get('is_maker'))} "
        f"roles={list(rk.get('role_labels') or [])}"
    )
    if knowledge_is_blank(rk):
        print("  known:       (blank — first meeting would introduce + ask who)")


def wipe_user_session(
    stack: dict[str, Any],
    *,
    auto_enqueue: bool,
) -> dict[str, Any]:
    """Delete durable data for this user_id and return a fresh stack.

    Clears bond_state, baseline, settings, decision logs, audit queue, and
    episodic interactions under ``users/<user_id>/`` via LocalPersistence.
    """
    store: LocalPersistence = stack["store"]
    user_id: str = stack["user_id"]
    data_root = stack["data_root"]
    deleted = store.delete_user_data(user_id)
    print(f"  Wiped local data for user_id={user_id!r}: {deleted}")
    print(f"  Path was: {data_root / 'users' / user_id}")
    fresh = build_stack(
        data_root=Path(data_root),
        user_id=user_id,
        auto_enqueue_audits=auto_enqueue,
    )
    print("  Fresh stack loaded (empty bond / memory for this user).")
    return fresh


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Private architect chat (PBE Tier 1.1)")
    p.add_argument("--user", default=None, help=f"user_id (default {DEFAULT_USER_ID!r})")
    p.add_argument("--data-root", default=None, help=f"data root (default via {ENV_DATA_ROOT})")
    p.add_argument("--no-auto-enqueue", action="store_true")
    p.add_argument("--wipe", action="store_true", help="Delete this user_id data and exit")
    p.add_argument("--once", default=None, metavar="TEXT", help="One message then exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    user_id = resolve_user_id(args.user)
    data_root = resolve_data_root(args.data_root)
    auto_enqueue = not bool(args.no_auto_enqueue)
    stack = build_stack(
        data_root=data_root,
        user_id=user_id,
        auto_enqueue_audits=auto_enqueue,
    )

    if args.wipe:
        deleted = stack["store"].delete_user_data(user_id)
        print(f"  Deleted user_id={user_id!r}: {deleted}")
        return 0

    if args.once is not None:
        process_turn(args.once, stack=stack, quiet=False)
        return 0

    isolated = data_root_is_isolated(stack["data_root"], repo_root=_ROOT)
    print()
    print("=" * 68)
    print("  Positronic Bond Engine — Private Architect Chat")
    print("=" * 68)
    print(f"  user_id:          {user_id}")
    print(f"  data_root:        {stack['data_root']}")
    print(f"  outside git tree: {isolated}")
    print(f"  phase:            {stack['dev'].limitation_summary()}")
    print(f"  version_hint:     {stack['dev'].version_hint}")
    cp = stack.get("content_provider")
    cp_name = type(cp).__name__ if cp is not None else "None"
    print(f"  content:          {cp_name} (see docs/model_providers.md)")
    print("  Commands: help | status | phase | wipe | wipe yes | quit")
    print("  Env:      PBE_DATA_ROOT, PBE_USER_ID, PBE_MODEL_*")
    print()
    if not isolated:
        print("  WARNING: data_root appears inside the repository tree.")
        print()

    while True:
        try:
            raw = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (session paused — data kept under data_root)")
            break
        if not raw:
            continue
        cmd = raw.lower().rstrip("!.?")
        if cmd in ("quit", "exit", "q"):
            print("  Session ended. Data retained for resume.")
            break
        if cmd == "help":
            print(
                "  help | status | phase | wipe | wipe yes | clear | reset | quit\n"
                "  wipe yes / clear / reset — erase this user_id's durable data and start fresh\n"
                "  Or type freely."
            )
            continue
        if cmd == "status":
            print_status(stack)
            continue
        if cmd == "phase":
            dev = stack["engine"].development_context
            print(f"  {dev.limitation_summary()}")
            for n in dev.honesty_notes()[:4]:
                print(f"  • {n}")
            continue
        if cmd == "wipe":
            print("  To erase this user_id's local data and reset the session, type: wipe yes")
            print("  (aliases: clear | reset)")
            continue
        if cmd in ("wipe yes", "clear", "reset"):
            stack = wipe_user_session(stack, auto_enqueue=auto_enqueue)
            continue
        process_turn(raw, stack=stack, quiet=False)

    print(f"\n  Data root: {stack['data_root']}")
    print("  Resume anytime with the same --user / data root.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
