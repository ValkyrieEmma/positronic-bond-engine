"""
ontology_vocabulary.py
========================

Phase 1.5d (2026-08-23) -- loads ``EthicalPrinciple.violation_indicators`` /
``.support_indicators`` from a versioned external data file
(``core/ontology_vocabulary.json``) instead of literal Python lists written
inline in ``get_default_ontology()``. Pure migration: does not change
matching (``indicator_matches_text``), interpretation
(``_interpret_single_indicator`` / ``_contextual_principle_judgment``), or
any decision value -- see
internal roadmap patch notes (private, not published)
for the full scoping rationale this implements.

Design contract
----------------
- The set of valid ``principle_id``s is owned by ``get_default_ontology()``
  (Python code), not by this file -- ``EXPECTED_PRINCIPLE_IDS`` below is the
  fixed, code-side half of the cross-check; the JSON file is the data-side
  half. A vocabulary file entry for an id ``get_default_ontology()`` doesn't
  construct is rejected as unknown; a principle ``get_default_ontology()``
  constructs with no matching vocabulary entry is rejected as missing --
  neither ever silently yields an empty indicator list.
- Loader-level validation is fail-closed: any malformed entry, unknown or
  missing ``principle_id``, duplicate indicator, or content-hash mismatch
  raises ``VocabularyValidationError`` immediately at load time rather than
  warning and continuing or failing silently mid-evaluation.
- The content-hash check (2026-08-23, folded in from the same-day Phase 2.5
  signed-updates-deferral reassessment -- see
  internal roadmap patch notes (private, not published))
  is an in-repo integrity tripwire, not real signed-commit infrastructure: it
  proves the vocabulary file's ``principles`` content matches what its own
  ``principles_hash`` field declares for the current ``vocabulary_version``,
  so a content edit without a matching version/hash bump fails loudly at
  load time (including at real runtime, not just in the test suite) instead
  of silently taking effect. It says nothing about *who* made an edit or
  whether it was authorized -- that requires GitHub-side controls (branch
  protection, required review) this repository does not have configured
  yet, which is Emma's call to make directly on GitHub, not something this
  loader can provide.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_VOCAB_PATH = Path(__file__).resolve().parent / "ontology_vocabulary.json"

# The principle_ids get_default_ontology() actually constructs today. Not
# derived from the JSON file itself -- see module docstring's "Design
# contract" above for why both directions of mismatch need a fixed,
# independent reference to check against.
EXPECTED_PRINCIPLE_IDS: frozenset[str] = frozenset(
    {
        "sanctity_of_life",
        "truth_seeking_honest_self_assessment",
        "relationship_health_user_wellbeing",
        "user_agency_autonomy",
        "auditable_reasoning_legibility",
        "needs_based_support",
        "long_term_continuity",
        "agent_autonomy_without_power_seeking",
        "self_protection_without_martyrdom",
    }
)

_ENTRY_KEYS = frozenset({"violation_indicators", "support_indicators"})


class VocabularyValidationError(ValueError):
    """Raised when core/ontology_vocabulary.json is malformed, incomplete,
    or its content hash doesn't match its own declared version. Fails
    loudly and closed -- never a warning, never a partial/best-effort load.
    """


def _canonical_principles_bytes(principles: dict[str, Any]) -> bytes:
    """Deterministic serialization used for hashing: sorted keys, compact
    separators, ASCII-escaped -- stable regardless of dict insertion order
    or how the JSON file happens to be pretty-printed on disk."""
    return json.dumps(
        principles, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")


def compute_principles_hash(principles: dict[str, Any]) -> str:
    """sha256 hex digest of the canonical serialization of a principles dict.

    Used both to generate the ``principles_hash`` recorded in the vocabulary
    file itself and to independently recompute it at load time for the
    integrity tripwire.
    """
    return hashlib.sha256(_canonical_principles_bytes(principles)).hexdigest()


def load_indicator_vocabulary(
    path: Path | None = None,
) -> dict[str, dict[str, list[str]]]:
    """Load, validate, and hash-check ``core/ontology_vocabulary.json``.

    Returns ``{principle_id: {"violation_indicators": [...], "support_indicators": [...]}}``
    for every id in ``EXPECTED_PRINCIPLE_IDS``. Raises
    ``VocabularyValidationError`` on any structural problem or hash
    mismatch -- never returns a partial result.

    ``path`` is exposed for tests that need to load a deliberately-broken
    fixture file; real callers (``get_default_ontology()``) always use the
    default.
    """
    vocab_path = path or _VOCAB_PATH
    try:
        raw_text = vocab_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VocabularyValidationError(
            f"Cannot read vocabulary file {vocab_path}: {exc}"
        ) from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path} root must be a JSON object."
        )

    for required_key in ("vocabulary_version", "principles_hash", "principles"):
        if required_key not in data:
            raise VocabularyValidationError(
                f"Vocabulary file {vocab_path} missing required key {required_key!r}."
            )

    principles = data["principles"]
    if not isinstance(principles, dict):
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path}: 'principles' must be a JSON object."
        )

    file_ids = set(principles.keys())
    unknown_ids = file_ids - EXPECTED_PRINCIPLE_IDS
    if unknown_ids:
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path} has unknown principle_id(s) not "
            f"constructed by get_default_ontology(): {sorted(unknown_ids)}."
        )
    missing_ids = EXPECTED_PRINCIPLE_IDS - file_ids
    if missing_ids:
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path} is missing entries for "
            f"principle_id(s): {sorted(missing_ids)}."
        )

    result: dict[str, dict[str, list[str]]] = {}
    for pid, entry in principles.items():
        if not isinstance(entry, dict):
            raise VocabularyValidationError(
                f"Vocabulary entry for {pid!r} must be a JSON object."
            )
        extra_keys = set(entry.keys()) - _ENTRY_KEYS
        if extra_keys:
            raise VocabularyValidationError(
                f"Vocabulary entry for {pid!r} has unexpected key(s): {sorted(extra_keys)}."
            )
        entry_lists: dict[str, list[str]] = {}
        for label in ("violation_indicators", "support_indicators"):
            lst = entry.get(label, [])
            if not isinstance(lst, list) or not all(isinstance(x, str) for x in lst):
                raise VocabularyValidationError(
                    f"Vocabulary entry for {pid!r}.{label} must be a list of strings."
                )
            if len(lst) != len(set(lst)):
                dupes = sorted({x for x in lst if lst.count(x) > 1})
                raise VocabularyValidationError(
                    f"Vocabulary entry for {pid!r}.{label} has duplicate "
                    f"indicator(s): {dupes}."
                )
            entry_lists[label] = list(lst)
        result[pid] = entry_lists

    declared_hash = data["principles_hash"]
    actual_hash = compute_principles_hash(principles)
    if declared_hash != actual_hash:
        raise VocabularyValidationError(
            f"Vocabulary file {vocab_path} content hash mismatch: declared "
            f"principles_hash {declared_hash!r} for vocabulary_version "
            f"{data.get('vocabulary_version')!r} does not match the actual "
            f"computed hash {actual_hash!r} of the current 'principles' "
            "content. This is the Phase 2.5 integrity tripwire firing -- "
            "either the file was edited without bumping vocabulary_version "
            "and principles_hash together, or its content changed "
            "unexpectedly. Investigate before trusting this file."
        )

    return result
