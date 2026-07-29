"""
public_entry_demo.py
====================

Minimal verification of the public InteractionSession contract.

Not a product UI. Shows single-user speech and multi-user identity-required.

Run from project root::

    $env:PYTHONPATH = "."
    python examples/public_entry_demo.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api import InteractionSession, TurnRequest  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbe_public_demo_"))
    try:
        session = InteractionSession(data_root=tmp, auto_enqueue_audits=False)

        print("=== Single-user turn ===")
        r1 = session.submit_turn(
            TurnRequest(message="hello", user_id="alice")
        )
        print(f"  decision: {r1.decision}")
        print(f"  path:     {r1.path}")
        print(f"  spoken:   {r1.spoken_text!r}")
        print(f"  forces:   speech={r1.forces_speech} question={r1.forces_question}")
        print(f"  presence: {r1.presence}")
        assert r1.forces_speech is False and r1.forces_question is False
        assert r1.decision != "IDENTITY_REQUIRED"
        assert r1.spoken_text

        print()
        print("=== Multi-user + unidentified speaker ===")
        session.mark_present("bob")
        r2 = session.submit_turn(
            TurnRequest(message="hello again", user_id="alice")
        )
        print(f"  decision: {r2.decision}")
        print(f"  path:     {r2.path}")
        print(f"  spoken:   {r2.spoken_text!r}")
        print(f"  identity_required: {r2.identity_required}")
        print(f"  presence: {r2.presence}")
        assert r2.decision == "IDENTITY_REQUIRED"
        assert r2.identity_required is True
        assert r2.path == "presence_identity_request"
        assert "who is speaking" in r2.spoken_text.lower()

        print()
        print("=== Identified speaker (bob) ===")
        r3 = session.submit_turn(
            TurnRequest(message="as bob: hello from bob", user_id="alice")
        )
        print(f"  decision: {r3.decision}")
        print(f"  path:     {r3.path}")
        print(f"  user_id:  {r3.user_id}")
        print(f"  spoken:   {r3.spoken_text!r}")
        assert r3.user_id == "bob"
        assert r3.decision != "IDENTITY_REQUIRED"
        assert r3.forces_speech is False

        print()
        print("Demo OK — contract-shaped results only (no CLI product UI).")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
