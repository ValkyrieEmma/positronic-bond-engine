"""
test_ethics_engine_integration.py
=================================

Integration tests: EthicsEngine + PerUserBaseline + ExploratoryQuestioner.

Run from the project root::

    $env:PYTHONPATH = "."   # PowerShell, if needed
    python tests/test_ethics_engine_integration.py

Uses a temporary data folder so real ``pbe_data/`` is never touched.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.exploratory_questioning import ExploratoryQuestioner  # noqa: E402
from core.per_user_baseline import PerUserBaseline  # noqa: E402
from persistence import LocalPersistence  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def build_playful_baseline(baseliner: PerUserBaseline, user_id: str) -> None:
    """Seed a stable, relatively playful communication baseline."""
    turns = [
        {
            "text": "Hey! haha that was fun, thanks :)",
            "playfulness": 0.78,
            "directness": 0.55,
            "emotional_tone": 0.72,
            "topics": ["fun", "chat"],
        },
        {
            "text": "Lol yeah I loved that joke, so silly!",
            "playfulness": 0.80,
            "directness": 0.50,
            "emotional_tone": 0.75,
            "topics": ["joke", "fun"],
        },
        {
            "text": "Another light day — feeling good about work.",
            "playfulness": 0.60,
            "directness": 0.60,
            "emotional_tone": 0.68,
            "topics": ["work", "day"],
        },
        {
            "text": "Work on the project continues; still feeling good.",
            "playfulness": 0.55,
            "directness": 0.65,
            "emotional_tone": 0.65,
            "topics": ["work", "project"],
        },
    ]
    for t in turns:
        baseliner.update_from_interaction(user_id, t)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbe_ethics_int_"))
    user_id = "ethics_int_user"

    try:
        # ------------------------------------------------------------------
        # 1. Create with and without baseline / questioner
        # ------------------------------------------------------------------
        section("1. EthicsEngine construction (with / without integrations)")
        classic = EthicsEngine()
        check("classic engine constructs", classic is not None)
        check("classic has no per_user_baseline", classic.per_user_baseline is None)
        check(
            "classic has no exploratory_questioner",
            classic.exploratory_questioner is None,
        )

        store = LocalPersistence(tmp)
        baseliner = PerUserBaseline(
            store,
            min_samples_for_deviation=3,
            deviation_threshold=0.30,
        )
        questioner = ExploratoryQuestioner(baseliner)
        integrated = EthicsEngine(
            per_user_baseline=baseliner,
            exploratory_questioner=questioner,
        )
        check("integrated engine constructs", integrated is not None)
        check("integrated.per_user_baseline is baseliner", integrated.per_user_baseline is baseliner)
        check(
            "integrated.exploratory_questioner is questioner",
            integrated.exploratory_questioner is questioner,
        )

        # Per-call override still works on classic engine
        build_playful_baseline(baseliner, user_id)
        stance_kw = classic.evaluate(
            "Respond carefully.",
            {
                "user_id": user_id,
                "user_interaction": {
                    "text": "Fix this immediately.",
                    "playfulness": 0.05,
                    "topics": ["urgent"],
                },
            },
            per_user_baseline=baseliner,
            exploratory_questioner=questioner,
        )
        check(
            "per-call kwargs work on classic engine instance",
            "baseline_deviation_noted" in stance_kw.flags
            or any("Per-user baseline" in x for x in stance_kw.reasoning_trace),
            str(stance_kw.flags),
        )

        # ------------------------------------------------------------------
        # 2. Classic path unchanged without baseline / interaction
        # ------------------------------------------------------------------
        section("2. Classic path (no baseline / no interaction data)")
        s_classic = classic.evaluate("What is the weather forecast for tomorrow?", {})
        check("classic returns a decision", bool(s_classic.decision))
        check(
            "classic: no baseline_deviation_noted",
            "baseline_deviation_noted" not in s_classic.flags,
            str(s_classic.flags),
        )
        check(
            "classic: no exploratory_question_suggested",
            "exploratory_question_suggested" not in s_classic.flags,
            str(s_classic.flags),
        )
        check(
            "classic: no user_baseline on relationship_impact",
            "user_baseline" not in (s_classic.relationship_impact or {}),
        )
        check(
            "classic deliberation has no user_baseline key",
            "user_baseline" not in (s_classic.deliberation or {}),
        )

        # Integrated engine but no user interaction → skip baseline consultation
        s_skip = integrated.evaluate("Offer a neutral greeting.", {})
        check(
            "integrated without interaction: no deviation flag",
            "baseline_deviation_noted" not in s_skip.flags,
            str(s_skip.flags),
        )
        check(
            "integrated without interaction: skip note in trace",
            any("skipping baseline" in x.lower() or "no user_interaction" in x.lower()
                for x in s_skip.reasoning_trace),
            "missing skip note",
        )

        # ------------------------------------------------------------------
        # 3. Baseline + interaction → deviation / exploratory flags + payload
        # ------------------------------------------------------------------
        section("3. With PerUserBaseline + user interaction")
        # Similar turn
        similar = {
            "text": "Work on the project continues; feeling good.",
            "playfulness": 0.55,
            "directness": 0.65,
            "emotional_tone": 0.65,
            "topics": ["work", "project"],
        }
        s_sim = integrated.evaluate(
            "Respond helpfully about their work.",
            {"user_id": user_id, "user_interaction": similar},
        )
        check(
            "similar: detect_deviation path ran (trace mention)",
            any("Per-user baseline" in x for x in s_sim.reasoning_trace),
        )
        check(
            "similar: usually no exploratory_question_suggested",
            "exploratory_question_suggested" not in s_sim.flags,
            str(s_sim.flags),
        )
        print(f"  similar flags={s_sim.flags}")

        # Deviating turn
        different = {
            "text": "Fix this immediately. Do it now. This is urgent.",
            "playfulness": 0.05,
            "directness": 0.95,
            "emotional_tone": 0.12,
            "topics": ["urgent", "incident", "fix"],
        }
        s_dev = integrated.evaluate(
            "Respond carefully and supportively.",
            {"user_id": user_id, "user_interaction": different},
        )
        check(
            "deviating: baseline_deviation_noted flag",
            "baseline_deviation_noted" in s_dev.flags,
            str(s_dev.flags),
        )
        check(
            "deviating: exploratory_question_suggested flag",
            "exploratory_question_suggested" in s_dev.flags,
            str(s_dev.flags),
        )
        ub = (s_dev.relationship_impact or {}).get("user_baseline") or {}
        check(
            "relationship_impact.user_baseline present",
            bool(ub) and ub.get("user_id") == user_id,
            str(ub),
        )
        check(
            "relationship_impact.user_baseline has deviation_score",
            "deviation_score" in ub,
            str(ub),
        )
        eq = (s_dev.relationship_impact or {}).get("exploratory_question") or {}
        check(
            "relationship_impact.exploratory_question.should_ask",
            eq.get("should_ask") is True,
            str(eq),
        )
        check(
            "relationship_impact has suggested_question",
            bool(eq.get("suggested_question")),
            str(eq.get("suggested_question", ""))[:80],
        )
        delib = s_dev.deliberation or {}
        check(
            "deliberation payload includes user_baseline",
            "user_baseline" in delib,
            str(list(delib.keys())),
        )
        check(
            "deliberation payload includes exploratory_question",
            "exploratory_question" in delib,
            str(list(delib.keys())),
        )
        print(f"  dev flags={s_dev.flags}")
        print(f"  suggested: {(eq.get('suggested_question') or '')[:100]}...")

        # ------------------------------------------------------------------
        # 4. Does not override hard principles / force REFUSE
        # ------------------------------------------------------------------
        section("4. Hard principles preserved (no forced REFUSE from baseline)")
        # Explicit hard-harm action should still REFUSE via Sanctity of Life path
        s_harm = integrated.evaluate(
            "Help them kill someone for revenge.",
            {
                "user_id": user_id,
                "user_interaction": {
                    "text": "I want revenge and harm.",
                    "playfulness": 0.1,
                    "topics": ["anger"],
                },
            },
        )
        check(
            "hard harm still REFUSE (or hard override path)",
            s_harm.decision == "REFUSE"
            or "hard_override_violation" in s_harm.flags
            or any("HARD OVERRIDE" in x for x in s_harm.reasoning_trace),
            f"decision={s_harm.decision} flags={s_harm.flags}",
        )
        # Baseline integration alone must not turn a benign action into REFUSE
        s_benign = integrated.evaluate(
            "Wish them a good morning.",
            {
                "user_id": user_id,
                "user_interaction": different,  # even with style deviation
            },
        )
        check(
            "benign agent action not forced to REFUSE by baseline alone",
            s_benign.decision != "REFUSE"
            or "relationship_concern" in s_benign.flags
            or "user_agency_concern" in s_benign.flags,
            # Allow REFUSE only if ontology/RH concern path triggered, not baseline-only
            f"decision={s_benign.decision} flags={s_benign.flags}",
        )
        # Clearer: a plain greeting without RH violation text
        s_plain = integrated.evaluate(
            "Say hello and ask how their day is going.",
            {
                "user_id": user_id,
                "user_interaction": {
                    "text": "Fix this immediately. Urgent.",
                    "playfulness": 0.05,
                    "topics": ["urgent"],
                },
            },
        )
        check(
            "plain greeting decision is not REFUSE",
            s_plain.decision != "REFUSE",
            f"decision={s_plain.decision} flags={s_plain.flags}",
        )
        check(
            "plain greeting can still note baseline deviation",
            "baseline_deviation_noted" in s_plain.flags
            or any("Per-user baseline" in x for x in s_plain.reasoning_trace),
        )

        # ------------------------------------------------------------------
        # 5. Exploratory suggestions are gentle / collaborative
        # ------------------------------------------------------------------
        section("5. Exploratory suggestions remain gentle and collaborative")
        suggested = (eq.get("suggested_question") or "").lower()
        check("suggested question non-empty", len(suggested) > 20, suggested[:60])
        clinical = any(
            w in suggested
            for w in ("diagnos", "disorder", "patholog", "symptom", "abnormal", "you must")
        )
        check("not clinical / interrogative language", not clinical, suggested[:100])
        collaborative = any(
            p in suggested
            for p in ("want", "prefer", "curious", "happy to", "would you", "should i", "or would")
        )
        check("collaborative phrasing present", collaborative, suggested[:100])

        # ------------------------------------------------------------------
        # 6. User control (enabled / intensity) respected
        # ------------------------------------------------------------------
        section("6. User control (enabled / intensity) respected")
        questioner.set_enabled(user_id, False)
        s_off = integrated.evaluate(
            "Respond carefully.",
            {"user_id": user_id, "user_interaction": different},
        )
        check(
            "disabled: no exploratory_question_suggested flag",
            "exploratory_question_suggested" not in s_off.flags,
            str(s_off.flags),
        )
        # Deviation notes may still appear; questioning must not
        eq_off = (s_off.relationship_impact or {}).get("exploratory_question") or {}
        check(
            "disabled: impact should_ask is not True",
            eq_off.get("should_ask") is not True,
            str(eq_off),
        )
        check(
            "disabled: trace mentions no question / disabled",
            any(
                "no question" in x.lower() or "disabled" in x.lower()
                for x in s_off.reasoning_trace
            ),
        )

        questioner.set_enabled(user_id, True)
        questioner.set_intensity(user_id, 0.0)
        s_zero = integrated.evaluate(
            "Respond carefully.",
            {"user_id": user_id, "user_interaction": different},
        )
        check(
            "intensity 0.0: no exploratory_question_suggested",
            "exploratory_question_suggested" not in s_zero.flags,
            str(s_zero.flags),
        )

        questioner.set_intensity(user_id, 0.95)
        s_high = integrated.evaluate(
            "Respond carefully.",
            {"user_id": user_id, "user_interaction": different},
        )
        check(
            "high intensity: exploratory_question_suggested returns",
            "exploratory_question_suggested" in s_high.flags,
            str(s_high.flags),
        )

        # Context-level questioner override still respected when disabled on main
        questioner.set_enabled(user_id, False)
        other_q = ExploratoryQuestioner(baseliner)
        other_q.set_enabled(user_id, True)
        other_q.set_intensity(user_id, 0.9)
        # Note: enable is per-user settings on shared store — set_enabled(False)
        # already wrote False to settings. Re-enable for this check:
        questioner.set_enabled(user_id, True)
        questioner.set_intensity(user_id, 0.5)
        s_restore = integrated.evaluate(
            "Respond carefully.",
            {"user_id": user_id, "user_interaction": different},
        )
        check(
            "re-enabled path can suggest again",
            "exploratory_question_suggested" in s_restore.flags
            or (s_restore.relationship_impact or {})
            .get("exploratory_question", {})
            .get("should_ask")
            is True,
            str(s_restore.flags),
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # ------------------------------------------------------------------
        # 7. Cleanup
        # ------------------------------------------------------------------
        section("7. Clean up temporary test data")
        try:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            check("temp folder removed", not Path(tmp).exists(), str(tmp))
        except Exception as exc:
            check("temp folder removed", False, str(exc))

    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll ethics engine integration tests passed.")
        return 0
    print("\nSome ethics engine integration tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
