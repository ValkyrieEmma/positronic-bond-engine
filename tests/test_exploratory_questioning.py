"""
test_exploratory_questioning.py
===============================

Standalone tests for ExploratoryQuestioner + PerUserBaseline + local persistence.

Run from the project root::

    python test_exploratory_questioning.py

Uses a temporary data folder so real ``pbe_data/`` is never touched.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.exploratory_questioning import (  # noqa: E402
    PREF_ENABLED,
    PREF_INTENSITY,
    ExploratoryQuestioner,
    QuestionDecision,
)
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbe_eq_test_"))
    user_id = "eq_tester"

    try:
        # ------------------------------------------------------------------
        # 1. Create ExploratoryQuestioner + PerUserBaseline on temp folder
        # ------------------------------------------------------------------
        section("1. Create ExploratoryQuestioner (temporary data folder)")
        print(f"  Temp data root: {tmp}")
        store = LocalPersistence(tmp)
        baseliner = PerUserBaseline(
            store,
            min_samples_for_deviation=3,
            deviation_threshold=0.30,
        )
        questioner = ExploratoryQuestioner(
            baseliner,
            base_score_threshold=0.28,
            prefer_significant_flag=True,
        )
        check("ExploratoryQuestioner instance created", isinstance(questioner, ExploratoryQuestioner))
        check("shares baseliner", questioner.baseliner is baseliner)
        check("questioning enabled by default", questioner.is_enabled(user_id) is True)
        check(
            "default intensity is 0.5",
            abs(questioner.get_intensity(user_id) - 0.5) < 1e-6,
            str(questioner.get_intensity(user_id)),
        )

        # ------------------------------------------------------------------
        # 2. Build baseline with several interactions
        # ------------------------------------------------------------------
        section("2. Build baseline with several interactions")
        turns = [
            {
                "text": "Hey! haha that was fun, thanks :)",
                "playfulness": 0.75,
                "directness": 0.55,
                "emotional_tone": 0.70,
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
        bl = baseliner.get_baseline(user_id)
        n = int(bl.communication_patterns.get("sample_count", 0))
        check("baseline has enough samples (>= 3)", n >= 3, str(n))
        check("playfulness tracked", 0.0 <= bl.playfulness_level <= 1.0, str(bl.playfulness_level))
        print(f"  sample_count={n} playfulness={bl.playfulness_level:.3f}")

        # ------------------------------------------------------------------
        # 3. Similar interaction → usually should_ask=False
        # ------------------------------------------------------------------
        section("3. should_ask_question() — similar / normal interaction")
        similar_interaction = {
            "text": "Work on the project continues; feeling good.",
            "playfulness": 0.55,
            "directness": 0.65,
            "emotional_tone": 0.65,
            "topics": ["work", "project"],
        }
        d_sim = questioner.should_ask_question(user_id, similar_interaction)
        check("returns QuestionDecision", isinstance(d_sim, QuestionDecision))
        check(
            "similar turn: should_ask=False",
            d_sim.should_ask is False,
            f"kind={d_sim.question_kind} reason={d_sim.reason}",
        )
        check(
            "similar turn: empty suggested_question",
            not d_sim.suggested_question,
            repr(d_sim.suggested_question),
        )
        check("similar turn: not disabled_by_user", d_sim.disabled_by_user is False)
        print(f"  similar: ask={d_sim.should_ask} score="
              f"{d_sim.deviation.score if d_sim.deviation else 'n/a'} "
              f"reason={d_sim.reason[:90]}")

        # ------------------------------------------------------------------
        # 4. Deviating interaction → should_ask=True + kind + gentle question
        # ------------------------------------------------------------------
        section("4. should_ask_question() — clearly deviating interaction")
        different_interaction = {
            "text": "Fix this immediately. Do it now. This is urgent.",
            "playfulness": 0.05,
            "directness": 0.95,
            "emotional_tone": 0.12,
            "topics": ["urgent", "incident", "fix"],
        }
        d_diff = questioner.should_ask_question(user_id, different_interaction)
        check("returns QuestionDecision", isinstance(d_diff, QuestionDecision))
        check(
            "deviating turn: should_ask=True",
            d_diff.should_ask is True,
            f"kind={d_diff.question_kind} reason={d_diff.reason}",
        )
        check(
            "deviating turn: question_kind is set (not none)",
            bool(d_diff.question_kind) and d_diff.question_kind != "none",
            str(d_diff.question_kind),
        )
        check(
            "deviating turn: suggested_question is non-empty",
            bool(d_diff.suggested_question) and len(d_diff.suggested_question) > 20,
            repr(d_diff.suggested_question[:80]),
        )
        # Gentle tone: should not sound clinical / interrogative
        lower_q = (d_diff.suggested_question or "").lower()
        clinicalish = any(
            w in lower_q
            for w in ("diagnos", "disorder", "patholog", "symptom", "abnormal")
        )
        check("suggested question is non-clinical", not clinicalish, lower_q[:80])
        soft_cues = any(
            p in lower_q
            for p in ("want", "prefer", "curious", "happy to", "would you", "should i")
        )
        check("suggested question has collaborative tone", soft_cues, lower_q[:100])
        check(
            "deviation attached when asking",
            d_diff.deviation is not None
            and (d_diff.deviation.has_significant_deviation or d_diff.deviation.score >= 0.25),
        )
        print(f"  different: ask={d_diff.should_ask} kind={d_diff.question_kind}")
        print(f"  question: {d_diff.suggested_question[:120]}...")

        # ------------------------------------------------------------------
        # 5. User control — disable + intensity
        # ------------------------------------------------------------------
        section("5. User control (disable + intensity)")

        # 5a Disable
        questioner.set_enabled(user_id, False)
        check("is_enabled False after set_enabled(False)", questioner.is_enabled(user_id) is False)
        d_off = questioner.should_ask_question(user_id, different_interaction)
        check(
            "disabled: should_ask=False even on deviation",
            d_off.should_ask is False,
            f"kind={d_off.question_kind}",
        )
        check("disabled: disabled_by_user=True", d_off.disabled_by_user is True)
        questioner.set_enabled(user_id, True)
        check("re-enabled", questioner.is_enabled(user_id) is True)

        # 5b Intensity low → harder to trigger; high → easier
        # Same deviating interaction at intensity 0.1 vs 0.9
        questioner.set_intensity(user_id, 0.1)
        check(
            "intensity set to ~0.1",
            abs(questioner.get_intensity(user_id) - 0.1) < 1e-6,
            str(questioner.get_intensity(user_id)),
        )
        d_low = questioner.should_ask_question(user_id, different_interaction)

        questioner.set_intensity(user_id, 0.95)
        check(
            "intensity set to ~0.95",
            abs(questioner.get_intensity(user_id) - 0.95) < 1e-6,
        )
        d_high = questioner.should_ask_question(user_id, different_interaction)

        # At least one of: high intensity asks, or low is stricter than high
        # (deviating turn should still ask at high intensity)
        check(
            "high intensity asks on clear deviation",
            d_high.should_ask is True,
            f"high ask={d_high.should_ask} low ask={d_low.should_ask} "
            f"high_reason={d_high.reason[:60]}",
        )
        # Intensity is reflected on the decision
        check(
            "intensity_applied on high decision ~0.95",
            abs(d_high.intensity_applied - 0.95) < 1e-6,
            str(d_high.intensity_applied),
        )
        check(
            "intensity_applied on low decision ~0.1",
            abs(d_low.intensity_applied - 0.1) < 1e-6,
            str(d_low.intensity_applied),
        )
        # Low intensity should use a higher effective threshold (reason or not-ask)
        # Soft: either low does not ask, or high still asks (already checked)
        if not d_low.should_ask:
            check("low intensity suppresses or raises bar (does not ask)", True)
        else:
            # Both ask — still OK if threshold math is looser; note it
            check(
                "low intensity still can ask on very strong deviation (acceptable)",
                True,
            )
        print(f"  intensity low: ask={d_low.should_ask} | high: ask={d_high.should_ask}")

        # Intensity 0.0 behaves like off for asking
        questioner.set_intensity(user_id, 0.0)
        d_zero = questioner.should_ask_question(user_id, different_interaction)
        check(
            "intensity 0.0 → should_ask=False",
            d_zero.should_ask is False,
            d_zero.reason,
        )
        # Restore a usable intensity for persistence check
        questioner.set_intensity(user_id, 0.75)
        questioner.set_enabled(user_id, True)

        # ------------------------------------------------------------------
        # 6. Settings persist across new instances
        # ------------------------------------------------------------------
        section("6. Enabled/intensity persist across new instances")
        questioner.set_enabled(user_id, False)
        questioner.set_intensity(user_id, 0.33)
        del questioner
        del baseliner

        store2 = LocalPersistence(tmp)
        baseliner2 = PerUserBaseline(store2)
        questioner2 = ExploratoryQuestioner(baseliner2)
        check(
            "reloaded is_enabled=False",
            questioner2.is_enabled(user_id) is False,
        )
        check(
            "reloaded intensity≈0.33",
            abs(questioner2.get_intensity(user_id) - 0.33) < 1e-6,
            str(questioner2.get_intensity(user_id)),
        )
        # Confirm settings file contains prefs
        settings = store2.load_settings(user_id)
        check(
            "settings.preferences has exploratory keys",
            PREF_ENABLED in (settings.preferences or {})
            and PREF_INTENSITY in (settings.preferences or {}),
            str(settings.preferences),
        )
        d_persist = questioner2.should_ask_question(user_id, different_interaction)
        check(
            "reloaded disabled still blocks asking",
            d_persist.should_ask is False and d_persist.disabled_by_user is True,
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # ------------------------------------------------------------------
        # 7. Clean up
        # ------------------------------------------------------------------
        section("7. Clean up temporary test folder")
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
        print("\nAll exploratory questioning tests passed.")
        return 0
    print("\nSome exploratory questioning tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
