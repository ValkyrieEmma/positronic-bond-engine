"""
base.py
=======

Sensor interface definitions.

Sensors are intentionally abstract. A "sensor" can be:
- Physical hardware (camera, microphone, environmental)
- Digital (chat logs, API events, system state)
- Inferred (relationship tension derived from interaction patterns)

The key contract is that raw readings flow through context builders
that then feed the ethics and relationship reasoning systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SensorReading:
    timestamp: datetime
    sensor_id: str
    modality: str
    value: Any
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class Sensor:
    """
    Base class for all sensors.

    Implementations should be lightweight and focus on reliable signal
    acquisition. Interpretation and ethical weighting belong elsewhere.
    """

    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id

    def read(self) -> SensorReading:
        """Return the current reading. Must be overridden."""
        raise NotImplementedError

    def is_available(self) -> bool:
        return True
