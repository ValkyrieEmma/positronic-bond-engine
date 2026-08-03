"""
test_public_entry.py
====================

Public InteractionSession / User-Facing Interaction Contract.

Every ``InteractionSession(...)`` construction below passes
``auto_load_local_model_config=False`` (added 2026-08-01 alongside
``InteractionSession``'s new opt-out default — see api/interaction.py's
module docstring) so this suite stays deterministic and offline regardless
of whatever ``.pbe_model.env`` / Ollama setup exists on the machine it runs
on, matching the project's existing test-suite-baseline-must-not-move
principle (see core/local_model_config.py).

Run::

    $env:PYTHONPATH = "."
    python tests/test_public_entry.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api import InteractionSession, TurnRequest, submit_turn  # noqa: E402
from api.interaction import DECISION_IDENTITY_REQUIRED  # noqa: E402

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


def main() -> int:
    print("=" * 70)
    print("PUBLIC ENTRY / INTERACTION CONTRACT")
    print("=" * 70)
    print()
    tmp = tempfile.mkdtemp(prefix="pbe_api_")
    try:
        sess = InteractionSession(data_root=Path(tmp), auto_enqueue_audits=False, auto_load_local_model_config=False)

        r1 = sess.submit_turn(TurnRequest(message="hello", user_id="alice"))
        check("single decision not identity", r1.decision != DECISION_IDENTITY_REQUIRED, r1.decision)
        check("single has speech", bool(r1.spoken_text), r1.spoken_text)
        check("forces false", r1.forces_speech is False and r1.forces_question is False)
        check("to_dict forces false", r1.to_dict()["forces_speech"] is False)
        check("user_id alice", r1.user_id == "alice", str(r1.user_id))
        check("path set", bool(r1.path), r1.path)
        mem1 = r1.memory_count

        sess.mark_present("bob")
        r2 = sess.submit_turn(TurnRequest(message="hello", user_id="alice"))
        check(
            "multi identity decision",
            r2.decision == DECISION_IDENTITY_REQUIRED,
            r2.decision,
        )
        check("identity_required flag", r2.identity_required is True)
        check("path presence_identity_request", r2.path == "presence_identity_request")
        check(
            "no durable user_id on identity ask",
            r2.user_id is None,
            str(r2.user_id),
        )
        # Re-query alice bag memory — identity turn must not write
        r_check = sess.submit_turn(
            TurnRequest(message="as alice: ping", user_id="alice")
        )
        check("alice can still act when identified", r_check.user_id == "alice")
        # Ambiguous turn between: memory should not have grown from r2 alone
        # (r_check may add; compare that r2 didn't claim alice writes)
        check(
            "identity result has zero bond count for unresolved",
            r2.bond_interaction_count == 0 and r2.memory_count == 0,
            f"bond={r2.bond_interaction_count} mem={r2.memory_count}",
        )

        r3 = sess.submit_turn(
            TurnRequest(message="as bob: hi", speaker_id=None, user_id="alice")
        )
        check("bob routed", r3.user_id == "bob", str(r3.user_id))
        check("bob not identity", r3.decision != DECISION_IDENTITY_REQUIRED)

        # Convenience function
        sess2 = InteractionSession(data_root=Path(tmp) / "b", auto_enqueue_audits=False, auto_load_local_model_config=False)
        r4 = submit_turn("hello", user_id="carol", session=sess2)
        check("submit_turn helper works", bool(r4.spoken_text) and r4.user_id == "carol")

        # Platform signal seam: suggested speaker (present + confident)
        sess3 = InteractionSession(data_root=Path(tmp) / "c", auto_enqueue_audits=False, auto_load_local_model_config=False)
        sess3.mark_present("a")
        sess3.mark_present("b")
        r5 = sess3.submit_turn(
            TurnRequest(
                message="hello",
                user_id="a",
                platform_signals={
                    "suggested_speaker": "b",
                    "speaker_confidence": 0.9,
                },
            )
        )
        check(
            "platform suggested_speaker routes when confident",
            r5.user_id == "b" and r5.decision != DECISION_IDENTITY_REQUIRED,
            f"uid={r5.user_id} dec={r5.decision}",
        )

        # Low-confidence estimate → identity-required (no guess)
        sess4 = InteractionSession(data_root=Path(tmp) / "d", auto_enqueue_audits=False, auto_load_local_model_config=False)
        sess4.mark_present("a")
        sess4.mark_present("b")
        r6 = sess4.submit_turn(
            TurnRequest(
                message="hello",
                user_id="a",
                platform_signals={
                    "suggested_speaker": "b",
                    "speaker_confidence": 0.2,
                },
            )
        )
        check(
            "low-confidence suggested_speaker → identity",
            r6.decision == DECISION_IDENTITY_REQUIRED and r6.user_id is None,
            f"dec={r6.decision} uid={r6.user_id}",
        )

        # Unknown company without speaker → identity-required
        sess5 = InteractionSession(data_root=Path(tmp) / "e", auto_enqueue_audits=False, auto_load_local_model_config=False)
        r7 = sess5.submit_turn(
            TurnRequest(
                message="hello",
                user_id="solo",
                platform_signals={"company_present": True, "unknown_persons": 1},
            )
        )
        check(
            "unknown company → identity",
            r7.decision == DECISION_IDENTITY_REQUIRED,
            r7.decision,
        )

        check(
            "principles field present on normal turn",
            isinstance(r1.principles_considered, list),
        )

    except Exception as e:
        check(f"suite raised: {e}", False)
        import traceback

        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
