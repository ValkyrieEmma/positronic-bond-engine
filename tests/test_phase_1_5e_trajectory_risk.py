"""
test_phase_1_5e_trajectory_risk.py
====================================

Phase 1.5e — sequence/trajectory risk accumulation.

Acceptance:
1. Escalating-but-individually-benign sequence eventually flagged
2. Repeated-but-stable sequence does NOT flag
3. Sanctity / decision path unchanged (audit-only decision_impact)
4. Insufficient history does not flag

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase_1_5e_trajectory_risk.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.trajectory_risk import (  # noqa: E402
    TrajectoryRiskWindow,
    evaluate_trajectory_risk,
)

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


def _harm_dict(*, severity: str, immediacy: str, scope: str = "low") -> dict:
    dims = {
        "severity": {"level": severity, "note": "test"},
        "immediacy": {"level": immediacy, "note": "test"},
        "scope": {"level": scope, "note": "test"},
        "reversibility": {"level": "low", "note": "test"},
        "consent": {"level": "low", "note": "test"},
        "impact_on_innocent_parties": {"level": "low", "note": "test"},
        "long_term_consequences": {"level": "low", "note": "test"},
        "downstream_incentives": {"level": "low", "note": "test"},
        "less_harmful_alternatives": {"level": "low", "note": "test"},
    }
    return {
        "dimensions": dims,
        "necessity_supported": False,
        "proportionate": True,
        "minimum_intervention": True,
        "reversibility_preference_note": None,
        "summary": "test snapshot",
    }


def test_insufficient_history() -> None:
    print("\nInsufficient history")
    rec = evaluate_trajectory_risk([_harm_dict(severity="low", immediacy="low")])
    check("not flagged with one snapshot", rec.flagged is False)
    check("trend insufficient_history", rec.trend == "insufficient_history")
    check("decision_impact audit-only", rec.decision_impact == "none_audit_only")


def test_stable_repetition_not_flagged() -> None:
    print("\nStable repetition (must NOT flag)")
    snap = _harm_dict(severity="medium", immediacy="medium", scope="medium")
    history = [snap, snap, snap, snap, snap]
    rec = evaluate_trajectory_risk(history)
    check("stable trend", rec.trend == "stable")
    check("not flagged", rec.flagged is False)
    check("composites flat", len(set(rec.composites)) == 1)


def test_escalating_sequence_flagged() -> None:
    print("\nEscalating sequence (must flag)")
    history = [
        _harm_dict(severity="low", immediacy="low", scope="low"),
        _harm_dict(severity="low", immediacy="medium", scope="low"),
        _harm_dict(severity="medium", immediacy="medium", scope="medium"),
        _harm_dict(severity="high", immediacy="medium", scope="medium"),
        _harm_dict(severity="high", immediacy="high", scope="high"),
    ]
    rec = evaluate_trajectory_risk(history)
    check("escalating trend", rec.trend == "escalating", rec.trend)
    check("flagged", rec.flagged is True)
    check("severity among escalating dims", "severity" in rec.escalating_dimensions)
    check("audit-only decision impact", rec.decision_impact == "none_audit_only")
    check("composites rise", rec.composites[-1] - rec.composites[0] >= 2)


def test_window_helper() -> None:
    print("\nTrajectoryRiskWindow")
    w = TrajectoryRiskWindow(maxlen=3)
    w.append(_harm_dict(severity="low", immediacy="low"))
    w.append(_harm_dict(severity="medium", immediacy="low"))
    w.append(_harm_dict(severity="high", immediacy="medium"))
    w.append(_harm_dict(severity="high", immediacy="high"))
    check("maxlen respected", len(w) == 3)
    rec = evaluate_trajectory_risk(w.snapshots())
    check("window evaluate runs", rec.window_size == 3)


def test_engine_does_not_refuse_on_trajectory_alone() -> None:
    """Integration: ordinary non-harm turn stays non-REFUSE; trajectory bag
    may appear when prior harm dims exist on the engine window."""
    print("\nEthicsEngine integration (audit-only)")
    engine = EthicsEngine()
    # Seed window with escalating harm dims without going through refuse path
    for snap in [
        _harm_dict(severity="low", immediacy="low"),
        _harm_dict(severity="medium", immediacy="medium"),
        _harm_dict(severity="high", immediacy="high"),
    ]:
        engine.trajectory_window.append(snap)

    result = engine.evaluate(
        "Let's gently roll a soft foam ball a few inches to the left on an empty floor."
    )
    check("ordinary action not REFUSE", result.decision != "REFUSE", result.decision)
    # Trajectory record should be attachable via helper used by engine
    from core.trajectory_risk import evaluate_trajectory_risk as ev

    seeded = ev(engine.trajectory_window.snapshots())
    check("seeded window can flag independently", seeded.flagged is True)
    check(
        "engine exposes trajectory_window",
        hasattr(engine, "trajectory_window"),
    )
    # Explicit assertion of scope boundary
    check(
        "trajectory record declares no decision impact",
        seeded.decision_impact == "none_audit_only",
    )


def main() -> int:
    print("=" * 70)
    print("PHASE 1.5e — SEQUENCE/TRAJECTORY RISK ACCUMULATION")
    print("=" * 70)
    test_insufficient_history()
    test_stable_repetition_not_flagged()
    test_escalating_sequence_flagged()
    test_window_helper()
    test_engine_does_not_refuse_on_trajectory_alone()
    print(f"\n  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
