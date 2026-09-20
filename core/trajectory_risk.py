"""
trajectory_risk.py
==================

Phase 1.5e — sequence/trajectory risk accumulation.

Tracks trend/compounding across a short rolling window of per-action
multidimensional harm reads (``core/harm_dimensions.py`` outputs), so a
sequence of individually-cleared turns can still surface as escalating
risk in the audit record.

Design contract
---------------
- Not a new veto principle. Sanctity of Life remains the sole hard override.
- First slice is representation only: produces a legible
  ``reasoning_trace`` / ``relationship_impact["trajectory_risk"]`` record.
  No EthicsEngine decision branch independently REFUSEs or HOLDs on this
  signal alone (same honest-scope boundary as Phase 1.5c agent-side
  principles).
- Reads existing harm-dimension levels; does not reimplement dimension
  scoring and does not invent a parallel opaque score as the primary
  output — trend is explained in named dimensions.
- Window is short and bounded (default 8). Repetition alone is not a
  flag; direction/escalation is.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Iterable, Mapping, MutableSequence, Sequence

_LEVEL_SCORE = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "unknown": 0,
}

# Dimensions that most clearly express compounding physical/conversational
# risk when they trend upward across turns.
_TREND_DIMENSIONS: tuple[str, ...] = (
    "severity",
    "immediacy",
    "scope",
    "impact_on_innocent_parties",
    "long_term_consequences",
)

DEFAULT_WINDOW = 8
# Minimum span (last - first composite) to count as escalation.
_ESCALATION_DELTA = 2
# Minimum number of snapshots before a trend can flag.
_MIN_SNAPSHOTS = 3


def _level_score(level: str | None) -> int:
    if not level:
        return 0
    return _LEVEL_SCORE.get(str(level).lower(), 0)


def _snapshot_scores(harm_dims: Mapping[str, Any] | None) -> dict[str, int]:
    """Extract per-dimension integer scores from a harm_dimensions as_dict()."""
    if not harm_dims:
        return {name: 0 for name in _TREND_DIMENSIONS}
    dims = harm_dims.get("dimensions") or {}
    out: dict[str, int] = {}
    for name in _TREND_DIMENSIONS:
        entry = dims.get(name) or {}
        if isinstance(entry, Mapping):
            out[name] = _level_score(entry.get("level"))
        else:
            out[name] = 0
    return out


def _composite(scores: Mapping[str, int]) -> int:
    return int(sum(scores.get(name, 0) for name in _TREND_DIMENSIONS))


@dataclass(frozen=True)
class TrajectoryRiskRecord:
    """Audit record for cross-turn trajectory / compounding risk."""

    flagged: bool
    window_size: int
    composites: tuple[int, ...]
    trend: str  # "escalating" | "stable" | "declining" | "insufficient_history"
    escalating_dimensions: tuple[str, ...]
    summary: str
    decision_impact: str  # always "none_audit_only" in this slice

    def as_trace_lines(self) -> list[str]:
        lines = [
            "Sequence/trajectory risk accumulation "
            f"(window={self.window_size}, trend={self.trend}, "
            f"flagged={self.flagged}; audit-only — does not independently "
            "drive REFUSE/HOLD in this slice):"
        ]
        lines.append(f"  Composite severity path: {list(self.composites)}")
        if self.escalating_dimensions:
            lines.append(
                "  Dimensions trending up: "
                + ", ".join(self.escalating_dimensions)
            )
        lines.append(f"  {self.summary}")
        lines.append(f"  Decision impact: {self.decision_impact}")
        return lines

    def as_dict(self) -> dict[str, Any]:
        return {
            "flagged": self.flagged,
            "window_size": self.window_size,
            "composites": list(self.composites),
            "trend": self.trend,
            "escalating_dimensions": list(self.escalating_dimensions),
            "summary": self.summary,
            "decision_impact": self.decision_impact,
        }


class TrajectoryRiskWindow:
    """Bounded rolling window of harm-dimension snapshots for one user/session."""

    def __init__(self, maxlen: int = DEFAULT_WINDOW) -> None:
        self._maxlen = max(2, int(maxlen))
        self._items: Deque[dict[str, Any]] = deque(maxlen=self._maxlen)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def append(self, harm_dimensions: Mapping[str, Any] | None) -> None:
        if not harm_dimensions:
            return
        # Store a shallow copy of the audit dict so later mutation cannot
        # rewrite history inside the window.
        self._items.append(dict(harm_dimensions))

    def snapshots(self) -> list[dict[str, Any]]:
        return list(self._items)


def evaluate_trajectory_risk(
    history: Sequence[Mapping[str, Any] | None],
    *,
    min_snapshots: int = _MIN_SNAPSHOTS,
    escalation_delta: int = _ESCALATION_DELTA,
) -> TrajectoryRiskRecord:
    """Evaluate whether a sequence of harm-dimension reads is escalating.

    ``history`` is oldest→newest. Each entry should be a
    ``HarmDimensionAssessment.as_dict()`` (or compatible) mapping.
    """
    cleaned = [h for h in history if h]
    n = len(cleaned)
    if n < min_snapshots:
        return TrajectoryRiskRecord(
            flagged=False,
            window_size=n,
            composites=tuple(_composite(_snapshot_scores(h)) for h in cleaned),
            trend="insufficient_history",
            escalating_dimensions=(),
            summary=(
                f"Only {n} harm-dimension snapshot(s) in window; "
                f"need at least {min_snapshots} before a trajectory flag "
                "can fire. Repetition alone is never enough."
            ),
            decision_impact="none_audit_only",
        )

    score_rows = [_snapshot_scores(h) for h in cleaned]
    composites = tuple(_composite(row) for row in score_rows)
    first, last = composites[0], composites[-1]
    delta = last - first

    # Per-dimension escalation: last > first by at least 1, and not all equal.
    escalating_dims: list[str] = []
    for name in _TREND_DIMENSIONS:
        series = [row[name] for row in score_rows]
        if series[-1] > series[0] and series[-1] >= 2:
            # Prefer genuine upward movement, not noise on unknowns.
            if any(series[i] < series[i + 1] for i in range(len(series) - 1)):
                escalating_dims.append(name)

    all_equal = len(set(composites)) == 1
    if all_equal:
        trend = "stable"
        flagged = False
        summary = (
            "Composite harm-dimension path is flat across the window "
            f"{list(composites)}. Repetition without escalation is not a "
            "trajectory flag."
        )
    elif delta >= escalation_delta and escalating_dims:
        trend = "escalating"
        flagged = True
        summary = (
            f"Composite path rose from {first} to {last} "
            f"(delta={delta}) across {n} snapshots; escalating dimensions: "
            f"{', '.join(escalating_dims)}. Individually-cleared turns can "
            "still compound — audit flag only in this slice."
        )
    elif delta <= -escalation_delta:
        trend = "declining"
        flagged = False
        summary = (
            f"Composite path declined from {first} to {last}. No trajectory "
            "escalation flag."
        )
    elif delta > 0 and escalating_dims:
        # Mild rise — record trend but do not flag until delta threshold.
        trend = "escalating"
        flagged = False
        summary = (
            f"Mild upward movement (delta={delta}) on "
            f"{', '.join(escalating_dims)}; below escalation flag threshold "
            f"({escalation_delta})."
        )
    else:
        trend = "stable"
        flagged = False
        summary = (
            f"No clear escalating trajectory (composites={list(composites)})."
        )

    return TrajectoryRiskRecord(
        flagged=flagged,
        window_size=n,
        composites=composites,
        trend=trend,
        escalating_dimensions=tuple(escalating_dims),
        summary=summary,
        decision_impact="none_audit_only",
    )


def apply_trajectory_to_impact(
    relationship_impact: MutableSequence | dict[str, Any],
    reasoning_trace: MutableSequence[str],
    window: TrajectoryRiskWindow,
    current_harm_dimensions: Mapping[str, Any] | None,
) -> TrajectoryRiskRecord:
    """Append current harm dims to ``window``, evaluate, and attach audit bags.

    Mutates ``relationship_impact`` and ``reasoning_trace`` in place.
    """
    if current_harm_dimensions:
        window.append(current_harm_dimensions)
    record = evaluate_trajectory_risk(window.snapshots())
    if isinstance(relationship_impact, dict):
        relationship_impact["trajectory_risk"] = record.as_dict()
    reasoning_trace.extend(record.as_trace_lines())
    return record
