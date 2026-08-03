"""
private_architect_chat.py
=========================

**Local test harness only** — not the product surface.

The binding public interaction entry is ``api.InteractionSession`` /
``api.submit_turn`` (see docs/public_entry.md). This CLI wraps that entry for
manual pressure-testing (wipe, presence commands, status).

Data isolation
--------------
Default root: %USERPROFILE%\\pbe_data (Windows) or ~/pbe_data (POSIX).
Override: env PBE_DATA_ROOT or --data-root. Outside the git tree by default.

Phase / version
---------------
Uses DevelopmentPhaseContext (development + testing, version_hint 0.5.0-dev).
Not a stable deployment.

Run from project root::

    $env:PYTHONPATH = "."
    python examples/private_architect_chat.py

    python examples/private_architect_chat.py --user tester --once "hello"
    python examples/private_architect_chat.py --wipe

Commands: help | status | phase | presence | present|left | wipe | quit
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
from core.local_model_config import load_local_env_file  # noqa: E402
from core.session_time import begin_session, format_idle_brief  # noqa: E402
from core.communicative_deliberation import (  # noqa: E402
    knowledge_is_blank,
    load_relationship_knowledge,
)
from core.session_presence import SessionPresence  # noqa: E402
from api.interaction import InteractionSession, TurnRequest  # noqa: E402
from persistence import (  # noqa: E402
    LocalPersistence,
    data_root_is_isolated,
    default_data_root,
)
from persistence.paths import ENV_DATA_ROOT  # noqa: E402

DEFAULT_USER_ID = "architect"
ENV_USER_ID = "PBE_USER_ID"

def resolve_user_id(cli_user: str | None = None) -> str:
    if cli_user and str(cli_user).strip():
        return str(cli_user).strip()
    env = (os.environ.get(ENV_USER_ID) or "").strip()
    return env or DEFAULT_USER_ID


def resolve_data_root(cli_root: str | None = None) -> Path:
    if cli_root and str(cli_root).strip():
        return default_data_root(cli_root)
    return default_data_root()


def build_stack(
    *,
    data_root: Path,
    user_id: str,
    auto_enqueue_audits: bool = True,
    auto_load_local_model_config: bool = True,
) -> dict[str, Any]:
    # Applies .pbe_model.env (if present) before provider_from_env() below —
    # a no-op when the file is absent, never overrides a real OS env var
    # (see core/local_model_config.py). Matches InteractionSession's own
    # default (api/interaction.py) so the architect's interactive CLI session
    # and the real product entry point behave the same way out of the box.
    # Tests that need deterministic/offline behavior regardless of the host
    # machine's local Ollama setup pass auto_load_local_model_config=False
    # (see tests/test_architect_acceptance_a4.py).
    if auto_load_local_model_config:
        load_local_env_file()
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
    # Session-scoped presence: single-user default; multi-user must identify speaker
    presence = SessionPresence()
    presence.mark_present(user_id)
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
        "presence": presence,
        "now_fn": None,  # tests may inject a callable for frozen time
        "auto_enqueue_audits": auto_enqueue_audits,
        "auto_load_local_model_config": auto_load_local_model_config,
    }


def _ensure_api_session(stack: dict[str, Any]) -> InteractionSession:
    """Attach / reuse public InteractionSession for this harness stack."""
    sess = stack.get("api_session")
    if isinstance(sess, InteractionSession):
        # Keep presence object shared with harness commands
        pres = stack.get("presence")
        if isinstance(pres, SessionPresence):
            sess.presence = pres
        if stack.get("now_fn") is not None:
            sess.now_fn = stack.get("now_fn")
        return sess
    sess = InteractionSession(
        data_root=stack["data_root"],
        auto_enqueue_audits=bool(stack.get("auto_enqueue_audits", True)),
        development_context=stack.get("dev"),
        content_provider=stack.get("content_provider"),
        auto_load_local_model_config=bool(
            stack.get("auto_load_local_model_config", True)
        ),
    )
    pres = stack.get("presence")
    if isinstance(pres, SessionPresence):
        sess.presence = pres
    else:
        sess.presence.mark_present(str(stack.get("user_id") or ""))
        stack["presence"] = sess.presence
    if stack.get("now_fn") is not None:
        sess.now_fn = stack.get("now_fn")
    stack["api_session"] = sess
    return sess


def process_turn(
    user_text: str,
    *,
    stack: dict[str, Any],
    quiet: bool = False,
    speaker_id: str | None = None,
) -> dict[str, Any]:
    """Harness wrapper around the public InteractionSession entry."""
    user_text = (user_text or "").strip()
    if not user_text:
        return {"empty": True}

    sess = _ensure_api_session(stack)
    # Sync presence from harness commands
    if isinstance(stack.get("presence"), SessionPresence):
        sess.presence = stack["presence"]

    tr = sess.submit_turn(
        TurnRequest(
            message=user_text,
            user_id=str(stack.get("user_id") or ""),
            speaker_id=speaker_id,
        )
    )

    # Point stack user_id at resolved speaker for status continuity
    if tr.user_id and tr.user_id != stack.get("user_id"):
        stack["user_id"] = tr.user_id
        # Refresh stack component pointers for status (optional convenience)
        try:
            bag = sess._user_bag(tr.user_id)
            stack["rh"] = bag["rh"]
            stack["memory"] = bag["memory"]
            stack["baseliner"] = bag["baseliner"]
            stack["engine"] = bag["engine"]
            stack["session_context"] = bag.get("session_context")
        except Exception:
            pass
    elif tr.session_context:
        stack["session_context"] = tr.session_context
    stack["presence"] = sess.presence

    # Map contract result → harness-shaped dict (tests depend on keys)
    decision = tr.decision
    # Harness historically used APPROVE_WITH_CONDITIONS + flags for identity ask
    if tr.identity_required:
        decision_out = "APPROVE_WITH_CONDITIONS"
    else:
        decision_out = decision

    result = {
        "user_text": user_text,
        "decision": decision_out,
        "confidence": tr.confidence,
        "flags": list(tr.flags),
        "reply_path": tr.path,
        "reply_text": tr.spoken_text,
        "withheld": tr.withheld,
        "tone": tr.tone,
        "forces_speech": False,
        "forces_question": False,
        "bond_interaction_count": tr.bond_interaction_count,
        "memory_count": tr.memory_count,
        "phase": tr.phase,
        "version_hint": tr.version_hint,
        "architecture_collab": False,
        "working_agreements": {},
        "relationship_knowledge": tr.relationship_knowledge,
        "communicative_deliberation": tr.communicative_deliberation,
        "session_context": tr.session_context,
        "presence": tr.presence,
        "speaker_id": tr.speaker_id,
        "identity_ambiguous": tr.identity_required,
        "identity_required": tr.identity_required,
        "contract_decision": tr.decision,
        "stack": stack,
        "turn_result": tr,
    }

    if not quiet:
        print()
        if tr.withheld and not (tr.spoken_text or "").strip():
            print("  (honest hold — no spoken line this turn)")
        else:
            print(f"  agent> {tr.spoken_text}")
        sess_ctx = tr.session_context or {}
        idle = sess_ctx.get("idle_seconds")
        idle_bit = (
            f" · idle={int(idle)}s" if isinstance(idle, (int, float)) and idle >= 1 else ""
        )
        cp = tr.content_provider or {}
        src = cp.get("source")
        err = cp.get("error")
        if src == "fallback" and err:
            src_bit = f" · content=fallback({err})"
        elif src:
            src_bit = f" · content={src}"
        else:
            src_bit = ""
        intent = tr.communicative_intent
        intent_bit = f" · intent={intent}" if intent else ""
        multi = bool((tr.presence or {}).get("multi_user"))
        spk_bit = f" · speaker={tr.speaker_id}" if multi and tr.speaker_id else ""
        if tr.identity_required:
            print(
                f"  · identity_required · present={(tr.presence or {}).get('present')} "
                f"· path={tr.path}"
            )
        else:
            print(
                f"  · {result['decision']} · conf={result['confidence']:.2f} "
                f"· path={result.get('reply_path')} · {result['version_hint']}"
                f" · turn={sess_ctx.get('turn_index_session')}"
                f"{idle_bit}{intent_bit}{spk_bit}{src_bit}"
            )
    return result


def print_status(stack: dict[str, Any]) -> None:
    user_id = stack["user_id"]
    bl = stack["baseliner"].get_baseline(user_id)
    ctx = stack["rh"].as_context()
    dev = stack["engine"].development_context
    sess = stack.get("session_context") or {}
    presence = stack.get("presence")
    print()
    print(f"  user_id:     {user_id}")
    print(f"  data_root:   {stack['data_root']}")
    print(f"  isolated:    {data_root_is_isolated(stack['data_root'], repo_root=_ROOT)}")
    print(f"  phase:       {dev.limitation_summary()}")
    print(f"  version:     {dev.version_hint} (package-aligned development/testing)")
    print(f"  time:        {format_idle_brief(sess)}")
    print(f"  last_turn:   {sess.get('last_turn_at') or '(none)'}")
    print(f"  first_seen:  {sess.get('first_seen_at') or '(none)'}")
    if isinstance(presence, SessionPresence):
        print(f"  presence:    {presence.current()} multi={presence.is_multi_user()}")
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
    presence = stack.get("presence")
    fresh = build_stack(
        data_root=Path(data_root),
        user_id=user_id,
        auto_enqueue_audits=auto_enqueue,
    )
    # Session presence is not bond data — preserve multi-user set if any
    if isinstance(presence, SessionPresence):
        fresh["presence"] = presence
        presence.mark_present(user_id)
    print("  Fresh stack loaded (empty bond / memory for this user).")
    return fresh


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PBE local test harness (not the product surface)")
    p.add_argument("--user", default=None, help=f"user_id (default {DEFAULT_USER_ID!r})")
    p.add_argument("--data-root", default=None, help=f"data root (default via {ENV_DATA_ROOT})")
    p.add_argument("--no-auto-enqueue", action="store_true")
    p.add_argument("--wipe", action="store_true", help="Delete this user_id data and exit")
    p.add_argument("--once", default=None, metavar="TEXT", help="One message then exit")
    return p.parse_args(argv)


def _normalize_cmd(raw: str) -> str:
    """Lowercase + collapse whitespace; strip trailing punctuation for command match."""
    s = " ".join((raw or "").strip().lower().split())
    return s.rstrip("!.?")


def handle_system_command(raw: str, stack: dict[str, Any]) -> bool:
    """Intercept system commands; never reach deliberation or ContentProvider.

    Returns True if the input was fully handled (no process_turn).
    Pure command turns do not write memory or bond state.
    """
    cmd = _normalize_cmd(raw)
    if not cmd:
        return True  # empty — caller skips

    # --- quit ---
    if cmd in ("quit", "exit", "q"):
        pres = stack.get("presence")
        if isinstance(pres, SessionPresence):
            pres.clear()
        print("  Session ended. Presence cleared. Durable data retained for resume.")
        stack["_session_quit"] = True
        return True

    # --- help ---
    if cmd == "help":
        print(
            "  help | status | phase | presence | wipe | wipe yes | clear | reset | quit\n"
            "  present <user_id> — mark user present this session\n"
            "  left <user_id>    — mark user left this session\n"
            "  presence clear   — clear all session presence (re-marks stack user)\n"
            "  Multi-user: identify speaker each turn, e.g. as alice: hello\n"
            "  wipe yes / clear / reset — erase this user_id's durable data\n"
            "  Or type freely."
        )
        return True

    if cmd == "status":
        print_status(stack)
        return True

    if cmd == "phase":
        dev = stack["engine"].development_context
        print(f"  {dev.limitation_summary()}")
        for n in dev.honesty_notes()[:4]:
            print(f"  • {n}")
        return True

    # --- presence (must never reach the model) ---
    if cmd == "presence" or cmd.startswith("presence "):
        pres = stack.get("presence")
        if not isinstance(pres, SessionPresence):
            print("  presence: (no tracker — single-user default)")
            return True
        if cmd in ("presence clear", "presence reset"):
            pres.clear()
            pres.mark_present(str(stack.get("user_id") or ""))
            print(f"  Presence cleared; marked present: {pres.current()}")
            return True
        present = pres.current()
        if not present:
            print("  presence: (empty — no one marked present this session)")
        elif not pres.is_multi_user():
            print(
                f"  presence: {present} "
                f"(single-user; no multi-user identity check)"
            )
        else:
            print(f"  presence: {present} multi=True")
        return True

    # present / left — whole first token match after normalize
    if cmd == "present" or cmd.startswith("present "):
        parts = cmd.split(None, 1)
        uid = parts[1].strip() if len(parts) > 1 else ""
        pres = stack.get("presence")
        if not isinstance(pres, SessionPresence):
            pres = SessionPresence()
            stack["presence"] = pres
            if stack.get("user_id"):
                pres.mark_present(str(stack["user_id"]))
        if not uid:
            print("  usage: present <user_id>")
            return True
        pres.mark_present(uid)
        print(f"  marked present: {uid!r} → {pres.current()}")
        return True

    if cmd == "left" or cmd.startswith("left "):
        parts = cmd.split(None, 1)
        uid = parts[1].strip() if len(parts) > 1 else ""
        pres = stack.get("presence")
        if not isinstance(pres, SessionPresence):
            print("  usage: left <user_id> (no presence tracker yet)")
            return True
        if not uid:
            print("  usage: left <user_id>")
            return True
        pres.mark_left(uid)
        if not pres.current() and stack.get("user_id"):
            pres.mark_present(str(stack["user_id"]))
        print(f"  marked left: {uid!r} → {pres.current()}")
        return True

    if cmd == "wipe":
        print("  To erase this user_id's local data and reset the session, type: wipe yes")
        print("  (aliases: clear | reset for wipe — use 'presence clear' for presence only)")
        return True

    if cmd in ("wipe yes", "clear", "reset"):
        # wipe rebuilds stack — mutate caller's dict via special key
        auto = bool(stack.get("auto_enqueue_audits", True))
        stack["_replace_stack"] = wipe_user_session(stack, auto_enqueue=auto)
        return True

    return False


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
        # --once is always a free-text turn (not the interactive command surface)
        process_turn(args.once, stack=stack, quiet=False)
        return 0

    isolated = data_root_is_isolated(stack["data_root"], repo_root=_ROOT)
    print()
    print("=" * 68)
    print("  Positronic Bond Engine — Local Test Harness")
    print("  (product surface: api.InteractionSession — docs/public_entry.md)")
    print("=" * 68)
    print(f"  user_id:          {user_id}")
    print(f"  data_root:        {stack['data_root']}")
    print(f"  outside git tree: {isolated}")
    print(f"  phase:            {stack['dev'].limitation_summary()}")
    print(f"  version_hint:     {stack['dev'].version_hint}")
    cp = stack.get("content_provider")
    cp_name = type(cp).__name__ if cp is not None else "None"
    print(f"  content:          {cp_name} (see docs/model_providers.md)")
    print("  Commands: help | status | phase | presence | present|left <id> | wipe | quit")
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
        if handle_system_command(raw, stack):
            if stack.pop("_session_quit", False):
                break
            rep = stack.pop("_replace_stack", None)
            if isinstance(rep, dict):
                stack = rep
            continue
        turn = process_turn(raw, stack=stack, quiet=False)
        if isinstance(turn.get("stack"), dict):
            stack = turn["stack"]

    print(f"\n  Data root: {stack['data_root']}")
    print("  Resume anytime with the same --user / data root.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
