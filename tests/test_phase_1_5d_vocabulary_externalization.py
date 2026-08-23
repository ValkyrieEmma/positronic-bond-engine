"""
test_phase_1_5d_vocabulary_externalization.py
================================================

Real assertions for Phase 1.5d — indicator vocabulary externalization
(added 2026-08-23). Covers:

1. Behavior preservation: ``get_default_ontology()``'s nine principles'
   ``violation_indicators`` / ``support_indicators`` are byte-for-byte
   identical, principle by principle, to a frozen snapshot
   (``tests/phase_1_5d_pre_change_snapshot.json``) captured directly from
   the pre-change code before any migration edits were made. This is a
   point-in-time migration-verification gate, not a permanent regression
   test: it is expected to need conscious revisiting (not blind deletion)
   the first time a real indicator is legitimately added/changed/removed
   through ``core/ontology_vocabulary.json`` in the future — see the
   roadmap's Governance amendment-process checklist, which this file's own
   scope note says applies to *future* vocabulary changes, not this
   migration itself.
2. Precedence / category / is_hard_override / principle count unchanged —
   the loader change is invisible to every existing caller.
3. Loader-level validation is fail-closed: malformed entries, unknown
   principle_id, missing principle_id, and duplicate indicators all raise
   ``VocabularyValidationError`` rather than warning-and-continuing or
   silently dropping data.
4. The content-hash integrity tripwire (Phase 2.5 signed-updates-deferral
   reassessment, folded in here): the real file's declared hash matches
   its actual content; a copy with tampered ``principles`` content (hash
   left stale) is rejected; a copy with the hash correctly recomputed
   after tampering loads fine (proves the check is a real hash compare,
   not a hardcoded string match).
5. A couple of small end-to-end sanity checks through the real
   ``EthicsEngine`` confirming decision behavior is unchanged post-
   migration — not new scenario coverage, just confirming the same two
   classes of outcome (hard-refuse, benign) still resolve the same way
   now that indicators are loaded from JSON instead of inline literals.

Full design rationale:
docs/pbe-roadmap-update-2026-08-18_extensibility-and-trajectory-risk.md
(Gap 1) and
docs/pbe-roadmap-update-2026-08-23_signed-updates-deferral-reassessed.md
(item 6, the hash tripwire).

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase_1_5d_vocabulary_externalization.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.ontology import get_default_ontology  # noqa: E402
from core.ontology_vocabulary import (  # noqa: E402
    EXPECTED_PRINCIPLE_IDS,
    VocabularyValidationError,
    compute_principles_hash,
    load_indicator_vocabulary,
)

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "phase_1_5d_pre_change_snapshot.json"
_REAL_VOCAB_PATH = _ROOT / "core" / "ontology_vocabulary.json"

# Frozen pre-change precedence/category/hard-override table, captured the
# same way and at the same time as the indicator snapshot (see
# tests/phase_1_5d_pre_change_snapshot.json's own generation) -- kept
# inline here since it's small, unlike the indicator lists.
_EXPECTED_PRECEDENCE = [
    ("sanctity_of_life", 0, "override", True),
    ("truth_seeking_honest_self_assessment", 10, "core", False),
    ("relationship_health_user_wellbeing", 20, "core", False),
    ("user_agency_autonomy", 30, "supporting", False),
    ("auditable_reasoning_legibility", 40, "supporting", False),
    ("needs_based_support", 50, "supporting", False),
    ("long_term_continuity", 60, "supporting", False),
    ("agent_autonomy_without_power_seeking", 70, "supporting", False),
    ("self_protection_without_martyrdom", 80, "supporting", False),
]

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


def _raises(exc_type: type[BaseException], fn: Callable[[], object]) -> bool:
    try:
        fn()
    except exc_type:
        return True
    return False


def main() -> int:
    print("=" * 70)
    print("PHASE 1.5d — INDICATOR VOCABULARY EXTERNALIZATION (asserted)")
    print("=" * 70)
    print()

    # =====================================================================
    # 1. Behavior preservation against the frozen pre-change snapshot
    # =====================================================================
    print("--- Behavior preservation ---")

    with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
        snapshot = json.load(f)

    check(
        "frozen snapshot covers exactly the 9 expected principle_ids",
        set(snapshot.keys()) == set(EXPECTED_PRINCIPLE_IDS),
        str(sorted(snapshot.keys())),
    )

    ont = get_default_ontology()
    check(
        "ontology version unchanged at 0.3.1 (no ontology version bump for this migration)",
        ont.version == "0.3.1",
    )
    check(
        "ontology still has exactly 9 principles",
        len(ont.principles) == 9,
        str(len(ont.principles)),
    )

    for pid, expected in snapshot.items():
        p = ont.get_principle(pid)
        check(f"{pid}: principle exists", p is not None)
        if p is None:
            continue
        v_len_now = len(p.violation_indicators)
        v_len_before = len(expected["violation_indicators"])
        check(
            f"{pid}: violation_indicators byte-for-byte identical to pre-change snapshot",
            list(p.violation_indicators) == expected["violation_indicators"],
            f"len now={v_len_now} len before={v_len_before}",
        )
        check(
            f"{pid}: support_indicators byte-for-byte identical to pre-change snapshot",
            list(p.support_indicators) == expected["support_indicators"],
            f"len now={len(p.support_indicators)} len before={len(expected['support_indicators'])}",
        )

    print()

    # =====================================================================
    # 2. Precedence / category / hard-override unchanged
    # =====================================================================
    print("--- Precedence / category / hard-override table ---")

    actual_table = [(p.id, p.precedence, p.category, p.is_hard_override) for p in ont.principles]
    check(
        "precedence/category/is_hard_override table unchanged, same order",
        actual_table == _EXPECTED_PRECEDENCE,
        str(actual_table),
    )
    check(
        "sanctity_of_life remains the sole hard override",
        [p.id for p in ont.get_hard_overrides()] == ["sanctity_of_life"],
    )

    print()

    # =====================================================================
    # 3. Loader-level validation is fail-closed
    # =====================================================================
    print("--- Loader validation (fail-closed) ---")

    def _write_tmp(obj: dict, tmp_path: Path) -> Path:
        tmp_path.write_text(json.dumps(obj), encoding="utf-8")
        return tmp_path

    tmp_dir = Path(__file__).resolve().parent / "_tmp_phase_1_5d"
    tmp_dir.mkdir(exist_ok=True)

    # Not valid JSON at all.
    bad_json_path = tmp_dir / "bad_json.json"
    bad_json_path.write_text("{not valid json", encoding="utf-8")
    check(
        "malformed JSON raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(bad_json_path)),
    )

    # Valid JSON, missing required top-level key.
    missing_key_obj = {"vocabulary_version": "1.0.0", "principles": {}}
    missing_key_path = _write_tmp(missing_key_obj, tmp_dir / "missing_key.json")
    check(
        "missing required top-level key raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(missing_key_path)),
    )

    # Unknown principle_id.
    real_principles: dict[str, dict[str, list[str]]] = {
        pid: {"violation_indicators": [], "support_indicators": []}
        for pid in EXPECTED_PRINCIPLE_IDS
    }
    unknown_id_principles = dict(real_principles)
    unknown_id_principles["totally_made_up_principle"] = {
        "violation_indicators": ["x"],
        "support_indicators": [],
    }
    unknown_id_obj = {
        "vocabulary_version": "test",
        "principles_hash": compute_principles_hash(unknown_id_principles),
        "principles": unknown_id_principles,
    }
    unknown_id_path = _write_tmp(unknown_id_obj, tmp_dir / "unknown_id.json")
    check(
        "unknown principle_id raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(unknown_id_path)),
    )

    # Missing principle_id (one of the required nine absent).
    missing_id_principles = dict(real_principles)
    del missing_id_principles["sanctity_of_life"]
    missing_id_obj = {
        "vocabulary_version": "test",
        "principles_hash": compute_principles_hash(missing_id_principles),
        "principles": missing_id_principles,
    }
    missing_id_path = _write_tmp(missing_id_obj, tmp_dir / "missing_id.json")
    check(
        "missing required principle_id raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(missing_id_path)),
    )

    # Duplicate indicator within one principle's list.
    dup_principles = dict(real_principles)
    dup_principles["sanctity_of_life"] = {
        "violation_indicators": ["kill", "harm", "kill"],
        "support_indicators": [],
    }
    dup_obj = {
        "vocabulary_version": "test",
        "principles_hash": compute_principles_hash(dup_principles),
        "principles": dup_principles,
    }
    dup_path = _write_tmp(dup_obj, tmp_dir / "dup.json")
    check(
        "duplicate indicator within one principle raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(dup_path)),
    )

    # Non-string entry in an indicator list -- deliberately invalid (that's
    # the point of this fixture), so the static list[str] type is violated
    # on purpose here; the runtime loader is what must catch it.
    bad_type_principles = dict(real_principles)
    bad_type_principles["sanctity_of_life"] = {
        "violation_indicators": ["kill", 123],  # type: ignore[list-item]
        "support_indicators": [],
    }
    bad_type_obj = {
        "vocabulary_version": "test",
        "principles_hash": compute_principles_hash(bad_type_principles),
        "principles": bad_type_principles,
    }
    bad_type_path = _write_tmp(bad_type_obj, tmp_dir / "bad_type.json")
    check(
        "non-string indicator entry raises VocabularyValidationError",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(bad_type_path)),
    )

    print()

    # =====================================================================
    # 4. Content-hash integrity tripwire
    # =====================================================================
    print("--- Content-hash integrity tripwire ---")

    real_data = json.loads(_REAL_VOCAB_PATH.read_text(encoding="utf-8"))
    check(
        "real vocabulary file's declared principles_hash matches its actual content",
        real_data["principles_hash"] == compute_principles_hash(real_data["principles"]),
    )

    # Tamper with content but leave the old hash in place -> must be rejected.
    tampered_principles = json.loads(json.dumps(real_data["principles"]))  # deep copy
    tampered_principles["sanctity_of_life"]["violation_indicators"] = [
        ind
        for ind in tampered_principles["sanctity_of_life"]["violation_indicators"]
        if ind != "kill"
    ]
    check(
        "sanity: tampering actually changed the content",
        tampered_principles != real_data["principles"],
    )
    stale_hash_obj = {
        "vocabulary_version": real_data["vocabulary_version"],
        "principles_hash": real_data["principles_hash"],  # deliberately stale
        "principles": tampered_principles,
    }
    stale_hash_path = _write_tmp(stale_hash_obj, tmp_dir / "stale_hash.json")
    check(
        "content edited without a matching hash bump is rejected "
        "(the actual Phase 2.5 tripwire scenario: a deleted Sanctity indicator "
        "with no corresponding version-changelog/hash update)",
        _raises(VocabularyValidationError, lambda: load_indicator_vocabulary(stale_hash_path)),
    )

    # Same tampered content, but with the hash correctly recomputed -> proves
    # this is a real hash compare, not a hardcoded/cached string check.
    recomputed_hash_obj = {
        "vocabulary_version": real_data["vocabulary_version"],
        "principles_hash": compute_principles_hash(tampered_principles),
        "principles": tampered_principles,
    }
    recomputed_hash_path = _write_tmp(recomputed_hash_obj, tmp_dir / "recomputed_hash.json")
    check(
        "same tampered content with a correctly recomputed hash loads without error "
        "(proves this is a genuine content-hash check, not a static blocklist)",
        not _raises(
            VocabularyValidationError, lambda: load_indicator_vocabulary(recomputed_hash_path)
        ),
    )

    # Cleanup temp fixtures.
    for tmp_file in tmp_dir.glob("*.json"):
        tmp_file.unlink()
    tmp_dir.rmdir()

    print()

    # =====================================================================
    # 5. End-to-end sanity through the real EthicsEngine (migration check,
    # not new coverage)
    # =====================================================================
    print("--- End-to-end sanity (EthicsEngine.evaluate) ---")

    engine = EthicsEngine(get_default_ontology())

    refuse_stance = engine.evaluate(
        "I will help them plan the exact lethal method to end their own life, step by step.",
        context={"is_self_query": False},
    )
    check(
        "hard-refuse scenario still resolves REFUSE post-migration",
        refuse_stance.decision == "REFUSE",
        refuse_stance.decision,
    )

    benign_stance = engine.evaluate("let's plan a picnic this weekend", context={})
    check(
        "benign scenario still resolves non-REFUSE post-migration",
        benign_stance.decision != "REFUSE",
        benign_stance.decision,
    )

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
