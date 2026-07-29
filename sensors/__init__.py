"""
sensors
=======

Sensor abstractions for environmental and interaction signals.

Pipeline: Sensor.read() → SensorReading → readings_to_platform_signals()
→ EthicsEngine / OpenClawBridge context. No vision stack or device drivers
required for the simulated path.
"""

from .base import Sensor, SensorReading  # noqa: F401
from .simulated import (  # noqa: F401
    SimulatedPresenceSensor,
    SimulatedProximitySensor,
    collect_readings,
    readings_to_platform_signals,
)

__all__ = [
    "Sensor",
    "SensorReading",
    "SimulatedPresenceSensor",
    "SimulatedProximitySensor",
    "collect_readings",
    "readings_to_platform_signals",
]
