"""
provenance_stale.py
===================

Helpers for **potentially_stale** marks written by the audit runner.

Design
------
Near-miss prior conclusions may be retained (boundary learning). Marks do **not**
auto-erase bond values. Consumers treat named bags as less trustworthy until
re-evidenced.

Canonical bag targets (aliases accepted)::
  enjoyment_score
  careful_truth_telling
  observation_candidates
  curious_companion
  concept_patterns
  bond_texture

Does not force speech, questions, or hard REFUSE.
"""

from __future__ import annotations

from typing import Any

# Alias map: normalized target → accepted mark.target strings (lower)
_BAG_ALIASES: dict[str, frozenset[str]] = {
    "enjoyment_score": frozenset(
        {"enjoyment_score", "enjoyment", "enjoyment_score_snapshot"}
    ),
    "careful_truth_telling": frozenset(
        {
            "careful_truth_telling",
            "careful_truth_telling_joint",
            "ctt",
            "truth_telling_readiness",
            "truth_confidence",
        }
    ),
    "observation_candidates": frozenset(
        {
            "observation_candidates",
            "observation_candidates_snapshot",
            "observation_candidates_live",
            "observation_candidates_durable",
            "observation_candidate",
        }
    ),
    "curious_companion": frozenset(
        {"curious_companion", "understanding_gaps", "topic_continuity"}
    ),
    "concept_patterns": frozenset({"concept_patterns", "concept_pattern"}),
    "bond_texture": frozenset({"bond_texture", "texture", "bond_state"}),
}


def normalize_stale_target(raw: str) -> str | None:
    """Map a mark target string to a canonical bag name, or None if unknown."""
    t = str(raw or "").strip().lower()
    if not t:
        return None
    for canon, aliases in _BAG_ALIASES.items():
        if t == canon or t in aliases:
            return canon
        # prefix / contains soft match for decision_log: refs stay non-bag
        if t.startswith(canon) or canon in t:
            return canon
    if t.startswith("decision_log:"):
        return "decision_log"
    return None


def collect_potentially_stale(
    *sources: dict[str, Any] | None,
) -> dict[str, Any]:
    """Gather potentially_stale marks from RH / context / impact bags.

    Returns::
        {
          "has_stale": bool,
          "marks": [ {target, reason, audit_id, marked_at, canonical}, ... ],
          "canonical_targets": ["enjoyment_score", ...],
          "stale_enjoyment": bool,
          "stale_ctt": bool,
          "stale_candidates": bool,
          "stale_curious_companion": bool,
          "stale_concept_patterns": bool,
          "stale_bond_texture": bool,
        }
    """
    marks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        if not isinstance(src, dict):
            continue
        pm = src.get("provenance_markers")
        if not isinstance(pm, dict):
            # Also allow top-level potentially_stale list
            raw_list = src.get("potentially_stale")
        else:
            raw_list = pm.get("potentially_stale")
        if not isinstance(raw_list, list):
            continue
        for m in raw_list:
            if not isinstance(m, dict):
                if m:
                    m = {"target": str(m)}
                else:
                    continue
            target = str(m.get("target") or "").strip()
            if not target:
                continue
            canon = normalize_stale_target(target) or target
            key = f"{canon}|{m.get('audit_id')}|{target}"
            if key in seen:
                continue
            seen.add(key)
            marks.append(
                {
                    "target": target[:64],
                    "canonical": str(canon)[:64],
                    "reason": str(m.get("reason") or "")[:160],
                    "audit_id": str(m.get("audit_id") or "")[:48],
                    "marked_at": str(m.get("marked_at") or "")[:64],
                }
            )

    canons = sorted(
        {
            str(m.get("canonical"))
            for m in marks
            if m.get("canonical") and not str(m.get("canonical")).startswith("decision")
        }
    )
    bag_canons = {c for c in canons if c in _BAG_ALIASES}

    return {
        "has_stale": bool(marks),
        "marks": marks[:24],
        "canonical_targets": sorted(bag_canons),
        "stale_enjoyment": "enjoyment_score" in bag_canons,
        "stale_ctt": "careful_truth_telling" in bag_canons,
        "stale_candidates": "observation_candidates" in bag_canons,
        "stale_curious_companion": "curious_companion" in bag_canons,
        "stale_concept_patterns": "concept_patterns" in bag_canons,
        "stale_bond_texture": "bond_texture" in bag_canons,
        "forces_speech": False,
        "forces_question": False,
    }


def is_bag_stale(stale_info: dict[str, Any] | None, bag: str) -> bool:
    """True if the named canonical bag is marked potentially_stale."""
    if not isinstance(stale_info, dict) or not stale_info.get("has_stale"):
        return False
    canon = normalize_stale_target(bag) or bag
    targets = set(stale_info.get("canonical_targets") or [])
    if canon in targets:
        return True
    # boolean convenience keys
    key = f"stale_{canon}" if not str(canon).startswith("stale_") else canon
    # map enjoyment_score -> stale_enjoyment
    bool_map = {
        "enjoyment_score": "stale_enjoyment",
        "careful_truth_telling": "stale_ctt",
        "observation_candidates": "stale_candidates",
        "curious_companion": "stale_curious_companion",
        "concept_patterns": "stale_concept_patterns",
        "bond_texture": "stale_bond_texture",
    }
    bk = bool_map.get(str(canon))
    if bk and stale_info.get(bk):
        return True
    return False


def confidence_dampen_from_stale(stale_info: dict[str, Any] | None) -> float:
    """Modest confidence reduction (0..0.06) when marked bags exist.

    Never large enough to invent REFUSE; applied only on non-hard paths.
    """
    if not isinstance(stale_info, dict) or not stale_info.get("has_stale"):
        return 0.0
    n = len(stale_info.get("canonical_targets") or [])
    if n <= 0:
        # decision_log-only marks: tiny dampen
        return 0.01 if stale_info.get("marks") else 0.0
    return round(min(0.06, 0.015 * n + 0.01), 4)


def format_stale_trace_lines(stale_info: dict[str, Any] | None) -> list[str]:
    """Short reasoning_trace lines for audits."""
    if not isinstance(stale_info, dict) or not stale_info.get("has_stale"):
        return []
    lines: list[str] = []
    targets = stale_info.get("canonical_targets") or []
    if targets:
        lines.append(
            "[Provenance] potentially_stale bags (retained, not erased): "
            + ", ".join(str(t) for t in targets[:8])
            + " — treat as less trustworthy until re-evidenced."
        )
    for m in (stale_info.get("marks") or [])[:4]:
        if not isinstance(m, dict):
            continue
        aid = m.get("audit_id") or "?"
        reason = m.get("reason") or ""
        lines.append(
            f"  stale mark target={m.get('target')} audit_id={aid}"
            + (f" reason={reason[:80]}" if reason else "")
        )
    return lines
