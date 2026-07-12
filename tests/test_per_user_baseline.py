"""
test_per_user_baseline.py
=========================

Standalone tests for Per-User Baseline Memory + local persistence.

Run from the project root::

    python test_per_user_baseline.py

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

from core.per_user_baseline import DeviationReport, PerUserBaseline  # noqa: E402
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
    tmp = Path(tempfile.mkdtemp(prefix="pbe_baseline_test_"))
    user_id = "baseline_tester"

    try:
        # ------------------------------------------------------------------
        # 1. Create PerUserBaseline with temporary data folder
        # ------------------------------------------------------------------
        section("1. Create PerUserBaseline (temporary data folder)")
        print(f"  Temp data root: {tmp}")
        store = LocalPersistence(tmp)
        baseliner = PerUserBaseline(
            store,
            min_samples_for_deviation=3,
            deviation_threshold=0.30,
        )
        check("PerUserBaseline instance created", isinstance(baseliner, PerUserBaseline))
        check("uses provided LocalPersistence", baseliner._persistence is store)

        # ------------------------------------------------------------------
        # 2. Update from several interactions (text + explicit signals)
        # ------------------------------------------------------------------
        section("2. Update baseline from several interactions")

        # Text-only playful turns
        baseliner.update_from_interaction(
            user_id,
            {"text": "Hey! haha that was really fun, thanks :)"},
        )
        baseliner.update_from_interaction(
            user_id,
            {"text": "Lol yeah I loved that joke, so silly!"},
        )
        # Explicit signal values (no pathologizing labels — just numbers)
        baseliner.update_from_interaction(
            user_id,
            {
                "text": "Work meeting went well, feeling good about the project.",
                "playfulness": 0.45,
                "directness": 0.70,
                "emotional_tone": 0.65,
                "topics": ["work", "project", "meeting"],
            },
        )
        baseliner.update_from_interaction(
            user_id,
            {
                "message": "Another solid day at work on the project.",
                "playfulness": 0.40,
                "directness": 0.75,
                "emotional_tone": 0.60,
                "topics": ["work", "project"],
            },
        )
        bl = baseliner.get_baseline(user_id)
        check(
            "sample_count after 4 updates",
            int(bl.communication_patterns.get("sample_count", 0)) == 4,
            str(bl.communication_patterns.get("sample_count")),
        )

        # ------------------------------------------------------------------
        # 3. Load baseline and verify signals are tracked
        # ------------------------------------------------------------------
        section("3. Load baseline and verify tracked signals")
        bl = baseliner.get_baseline(user_id)
        check("user_id matches", bl.user_id == user_id)
        check(
            "playfulness_level is a float in [0, 1]",
            isinstance(bl.playfulness_level, float) and 0.0 <= bl.playfulness_level <= 1.0,
            str(bl.playfulness_level),
        )
        check(
            "communication_patterns has directness",
            "directness" in bl.communication_patterns,
            str(bl.communication_patterns),
        )
        check(
            "communication_patterns has message_length_score",
            "message_length_score" in bl.communication_patterns,
        )
        check(
            "emotional_tone_range has min/max/mean",
            all(k in bl.emotional_tone_range for k in ("min", "max", "mean")),
            str(bl.emotional_tone_range),
        )
        check(
            "tone min <= mean <= max",
            bl.emotional_tone_range["min"]
            <= bl.emotional_tone_range["mean"]
            <= bl.emotional_tone_range["max"],
            str(bl.emotional_tone_range),
        )
        check(
            "topic_continuity has recent_topics",
            isinstance(bl.topic_continuity.get("recent_topics"), list)
            and len(bl.topic_continuity.get("recent_topics") or []) > 0,
            str(bl.topic_continuity),
        )
        check(
            "topic_continuity has continuity_score",
            "continuity_score" in bl.topic_continuity,
        )
        # Work/project should appear after explicit topics updates
        recent = [t.lower() for t in (bl.topic_continuity.get("recent_topics") or [])]
        check(
            "recent topics include work/project",
            "work" in recent or "project" in recent,
            str(recent),
        )
        print(f"  Snapshot playfulness={bl.playfulness_level:.3f} "
              f"directness={bl.communication_patterns.get('directness')} "
              f"tone={bl.emotional_tone_range}")

        # ------------------------------------------------------------------
        # 4. detect_deviation()
        # ------------------------------------------------------------------
        section("4. detect_deviation() after enough samples")
        # Similar style — expect lower deviation score
        similar = baseliner.detect_deviation(
            user_id,
            {
                "text": "Work on the project continues; feeling good.",
                "playfulness": 0.42,
                "directness": 0.72,
                "emotional_tone": 0.62,
                "topics": ["work", "project"],
            },
        )
        check("returns DeviationReport", isinstance(similar, DeviationReport))
        check("sample_count >= 3", similar.sample_count >= 3, str(similar.sample_count))
        check("to_dict has expected keys", all(
            k in similar.to_dict()
            for k in (
                "user_id",
                "has_significant_deviation",
                "score",
                "signals",
                "notes",
                "sample_count",
            )
        ))
        check(
            "signals include core dimensions",
            all(
                k in similar.signals
                for k in (
                    "message_length",
                    "directness",
                    "emotional_tone",
                    "playfulness",
                    "topic_continuity",
                )
            ),
            str(list(similar.signals.keys())),
        )
        print(f"  Similar turn: significant={similar.has_significant_deviation} "
              f"score={similar.score:.3f}")

        # Very different style — expect higher score than the similar turn
        different = baseliner.detect_deviation(
            user_id,
            {
                "text": "Fix this immediately. Do it now. Urgent.",
                "playfulness": 0.05,
                "directness": 0.95,
                "emotional_tone": 0.15,
                "topics": ["urgent", "fix", "incident"],
            },
        )
        check("different turn returns DeviationReport", isinstance(different, DeviationReport))
        check(
            "different turn score >= similar turn score",
            different.score + 1e-9 >= similar.score,
            f"different={different.score:.3f} similar={similar.score:.3f}",
        )
        check(
            "score is in [0, 1]",
            0.0 <= different.score <= 1.0,
            str(different.score),
        )
        # With enough samples and a large shift, often significant — soft check:
        # either significant is True OR score is clearly elevated
        check(
            "different turn is notable (significant or elevated score)",
            different.has_significant_deviation or different.score >= 0.25,
            f"significant={different.has_significant_deviation} score={different.score:.3f}",
        )
        print(f"  Different turn: significant={different.has_significant_deviation} "
              f"score={different.score:.3f} notes={different.notes}")

        # ------------------------------------------------------------------
        # 5. reset_baseline()
        # ------------------------------------------------------------------
        section("5. reset_baseline() returns defaults")
        before_path = store.user_data_path(user_id) / "baseline.json"
        check("baseline file exists before reset", before_path.is_file())
        reset_bl = baseliner.reset_baseline(user_id)
        check("reset returns UserBaseline for same user", reset_bl.user_id == user_id)
        check(
            "sample_count reset to 0",
            int(reset_bl.communication_patterns.get("sample_count", -1)) == 0,
            str(reset_bl.communication_patterns),
        )
        check(
            "playfulness back near default 0.5",
            abs(reset_bl.playfulness_level - 0.5) < 1e-6,
            str(reset_bl.playfulness_level),
        )
        check(
            "emotional_tone_range cleared",
            reset_bl.emotional_tone_range == {} or len(reset_bl.emotional_tone_range) == 0,
            str(reset_bl.emotional_tone_range),
        )
        recent_after = (reset_bl.topic_continuity or {}).get("recent_topics") or []
        check("recent_topics cleared", recent_after == [])
        # get_baseline should match reset
        loaded_reset = baseliner.get_baseline(user_id)
        check(
            "get_baseline after reset matches",
            int(loaded_reset.communication_patterns.get("sample_count", -1)) == 0
            and abs(loaded_reset.playfulness_level - 0.5) < 1e-6,
        )

        # Rebuild a small baseline so we can test cross-instance persistence
        baseliner.update_from_interaction(
            user_id,
            {
                "text": "Persist me please",
                "playfulness": 0.81,
                "directness": 0.55,
                "emotional_tone": 0.70,
                "topics": ["persistence", "test"],
            },
        )
        baseliner.update_from_interaction(
            user_id,
            {
                "playfulness": 0.79,
                "directness": 0.58,
                "emotional_tone": 0.68,
                "topics": ["persistence"],
            },
        )
        mid = baseliner.get_baseline(user_id)
        saved_playfulness = mid.playfulness_level
        saved_samples = int(mid.communication_patterns.get("sample_count", 0))
        check("post-reset samples tracked again", saved_samples == 2, str(saved_samples))

        # ------------------------------------------------------------------
        # 6. Persistence across new PerUserBaseline instances
        # ------------------------------------------------------------------
        section("6. Data persists across new PerUserBaseline instances")
        # Drop references; open a fresh facade on the same folder
        del baseliner
        store2 = LocalPersistence(tmp)
        baseliner2 = PerUserBaseline(store2)
        reloaded = baseliner2.get_baseline(user_id)
        check("reloaded user_id", reloaded.user_id == user_id)
        check(
            "reloaded sample_count matches",
            int(reloaded.communication_patterns.get("sample_count", 0)) == saved_samples,
            f"got {reloaded.communication_patterns.get('sample_count')} expected {saved_samples}",
        )
        check(
            "reloaded playfulness matches (approx)",
            abs(reloaded.playfulness_level - saved_playfulness) < 1e-6,
            f"got {reloaded.playfulness_level} expected {saved_playfulness}",
        )
        check(
            "baseline.json still on disk",
            (tmp / "users" / user_id / "baseline.json").is_file(),
        )
        topics = (reloaded.topic_continuity or {}).get("recent_topics") or []
        check(
            "reloaded topics include persistence",
            any("persistence" in str(t).lower() for t in topics),
            str(topics),
        )

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # ------------------------------------------------------------------
        # 7. Clean up temporary folder
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
        print("\nAll per-user baseline tests passed.")
        return 0
    print("\nSome per-user baseline tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
