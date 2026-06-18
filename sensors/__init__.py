"""
sensors
=======

Sensor abstractions for environmental, interaction, and physiological signals.

The sensors layer feeds the rest of the system with grounded data about the
current situation. Ethical use of this data (especially anything that could
be considered personal or biometric) is the responsibility of the ethics
engine and auditing layers.
"""

from .base import Sensor, SensorReading  # noqa: F401

__all__ = ["Sensor", "SensorReading"]
