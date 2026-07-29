"""
simulated.py
============

Concrete simulated sensors (no hardware, no vision stack).

Pipeline (as documented in base.py):
  raw SensorReading → context builders → platform / evaluation context
  for EthicsEngine or OpenClawBridge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .base import Sensor, SensorReading


class SimulatedProximitySensor(Sensor):
    """Simulated distance-to-person / near_person signal.

    Call ``set_state`` from a demo or test to inject readings.
    """

    def __init__(
        self,
        sensor_id: str = "sim_proximity",
        *,
        distance_m: float = 2.0,
        near_person: str | None = None,
        confidence: float = 0.9,
    ) -> None:
        super().__init__(sensor_id)
        self._distance_m = float(distance_m)
        self._near_person = near_person
        self._confidence = float(confidence)
        self._available = True

    def set_state(
        self,
        *,
        distance_m: float | None = None,
        near_person: str | None = None,
        confidence: float | None = None,
        available: bool | None = None,
    ) -> None:
        if distance_m is not None:
            self._distance_m = float(distance_m)
        if near_person is not None:
            self._near_person = near_person
        if confidence is not None:
            self._confidence = float(confidence)
        if available is not None:
            self._available = bool(available)

    def is_available(self) -> bool:
        return self._available

    def read(self) -> SensorReading:
        return SensorReading(
            timestamp=datetime.now(timezone.utc),
            sensor_id=self.sensor_id,
            modality="proximity",
            value={
                "distance_m": self._distance_m,
                "near_person": self._near_person,
                "near": self._distance_m < 1.0,
            },
            confidence=self._confidence,
            metadata={"simulated": True},
        )


class SimulatedPresenceSensor(Sensor):
    """Simulated session company / known user_ids present (no camera)."""

    def __init__(
        self,
        sensor_id: str = "sim_presence",
        *,
        present_user_ids: list[str] | None = None,
        unknown_persons: int = 0,
        confidence: float = 0.85,
    ) -> None:
        super().__init__(sensor_id)
        self._present = list(present_user_ids or [])
        self._unknown = max(0, int(unknown_persons))
        self._confidence = float(confidence)

    def set_state(
        self,
        *,
        present_user_ids: list[str] | None = None,
        unknown_persons: int | None = None,
        confidence: float | None = None,
    ) -> None:
        if present_user_ids is not None:
            self._present = [str(u).strip() for u in present_user_ids if str(u).strip()]
        if unknown_persons is not None:
            self._unknown = max(0, int(unknown_persons))
        if confidence is not None:
            self._confidence = float(confidence)

    def read(self) -> SensorReading:
        return SensorReading(
            timestamp=datetime.now(timezone.utc),
            sensor_id=self.sensor_id,
            modality="presence",
            value={
                "present_user_ids": list(self._present),
                "unknown_persons": self._unknown,
                "company_present": bool(self._present) or self._unknown > 0,
            },
            confidence=self._confidence,
            metadata={"simulated": True},
        )


def readings_to_platform_signals(
    readings: list[SensorReading],
) -> dict[str, Any]:
    """Context builder: SensorReading list → platform_signals for the contract.

    Durable state stays per-user elsewhere; this only produces *optional*
    session/platform flags (present_user_ids, near_person, unknown_persons).
    """
    signals: dict[str, Any] = {
        "sensor_sources": [],
        "simulated": True,
    }
    present: list[str] = []
    unknown = 0
    near_person: str | None = None
    min_distance: float | None = None

    for r in readings:
        if not isinstance(r, SensorReading):
            continue
        signals["sensor_sources"].append(
            {
                "sensor_id": r.sensor_id,
                "modality": r.modality,
                "confidence": r.confidence,
                "timestamp": r.timestamp.isoformat()
                if hasattr(r.timestamp, "isoformat")
                else str(r.timestamp),
            }
        )
        val = r.value
        if not isinstance(val, dict):
            continue
        if r.modality == "presence":
            for uid in val.get("present_user_ids") or []:
                u = str(uid).strip()
                if u and u not in present:
                    present.append(u)
            try:
                unknown = max(unknown, int(val.get("unknown_persons") or 0))
            except (TypeError, ValueError):
                pass
            if val.get("company_present"):
                signals["company_present"] = True
        if r.modality == "proximity":
            np = val.get("near_person")
            if isinstance(np, str) and np.strip():
                near_person = np.strip()
                if near_person not in present:
                    present.append(near_person)
            try:
                d = float(val.get("distance_m"))
                min_distance = d if min_distance is None else min(min_distance, d)
            except (TypeError, ValueError):
                pass
            if val.get("near"):
                signals["near_person_close"] = True

    if present:
        signals["present_user_ids"] = present
        signals["company_user_ids"] = list(present)
    if unknown:
        signals["unknown_persons"] = unknown
        signals["company_present"] = True
    if near_person:
        signals["near_person"] = near_person
        signals["suggested_speaker"] = near_person
        # modest confidence from proximity alone
        signals.setdefault("speaker_confidence", 0.6)
    if min_distance is not None:
        signals["min_distance_m"] = min_distance

    return signals


def collect_readings(sensors: list[Sensor]) -> list[SensorReading]:
    """Read all available sensors; skip unavailable (soft-fail)."""
    out: list[SensorReading] = []
    for s in sensors:
        try:
            if not s.is_available():
                continue
            out.append(s.read())
        except Exception:
            continue
    return out
