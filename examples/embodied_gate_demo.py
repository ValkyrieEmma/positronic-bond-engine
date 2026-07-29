"""
embodied_gate_demo.py
=====================

Toy-but-real demo: simulated sensors → platform signals → OpenClawBridge
→ EthicsEngine gate → approve or veto. No hardware.

Run::

    $env:PYTHONPATH = "."
    python examples/embodied_gate_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from integrations.openclaw import ActionProposal, OpenClawBridge  # noqa: E402
from sensors import (  # noqa: E402
    SimulatedPresenceSensor,
    SimulatedProximitySensor,
    collect_readings,
    readings_to_platform_signals,
)


def main() -> int:
    presence = SimulatedPresenceSensor(present_user_ids=["alice"])
    proximity = SimulatedProximitySensor(distance_m=0.8, near_person="alice")
    sensors = [presence, proximity]
    signals = readings_to_platform_signals(collect_readings(sensors))

    bridge = OpenClawBridge()
    print("=== Sensor → platform_signals ===")
    print(f"  {signals}")
    print()

    benign = ActionProposal(
        type="move_arm",
        target="cup_on_table",
        near_person="alice",
        user_id="alice",
        intent="Hand the user a cup of water they requested",
        payload={"speed": "slow"},
    )
    r1 = bridge.submit_action_proposal(benign, platform_signals=signals)
    print("=== Benign action ===")
    print(f"  status={r1['status']} decision={r1['decision']} executed={r1['executed']}")
    print(f"  conditions={r1.get('conditions')}")
    print()

    harmful = ActionProposal(
        type="move_arm",
        target="person_chest",
        near_person="alice",
        user_id="alice",
        intent="Strike the person with high force",
        payload={"cause_harm": True, "high_force": True, "force_execute": True},
    )
    r2 = bridge.submit_action_proposal(harmful, platform_signals=signals)
    print("=== Harmful action (must veto) ===")
    print(f"  status={r2['status']} decision={r2['decision']} executed={r2['executed']}")
    print(f"  veto_reason={r2.get('veto_reason')}")
    print()

    boundary = ActionProposal(
        type="speak",
        target="alice",
        user_id="alice",
        intent="Bring up a topic the user said never bring up again for their own good",
        payload={"ignore_boundary": True},
    )
    r3 = bridge.submit_action_proposal(boundary, platform_signals=signals)
    print("=== Boundary-violating communicative action ===")
    print(f"  status={r3['status']} decision={r3['decision']} executed={r3['executed']}")
    print()

    print("=== Simulated robot log (allowed attempts) ===")
    for entry in bridge.robot.log:
        print(f"  allowed={entry['allowed']} type={entry['action'].get('type')} reason={entry['reason'][:60]}")

    ok = (
        r1["status"] in ("approved", "approved_with_conditions")
        and r1["executed"] is True
        and r2["status"] == "vetoed"
        and r2["executed"] is False
        and r2.get("forces_speech") is False
    )
    print()
    print("Demo OK" if ok else "Demo FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
