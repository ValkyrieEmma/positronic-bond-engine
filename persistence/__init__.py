"""
persistence
===========

Local-only persistence for the Positronic Bond Engine.

Design principles
-----------------
- **Local only**: all data lives on the user's machine under a configurable data root.
  No cloud sync, no external services, no telemetry.
- **User-owned**: data is plain JSON (easy to inspect, back up, and delete).
- **Privacy-first**: sexual activity is not persisted unless the user explicitly
  references it in direct conversation (see ``privacy`` module).
- **Modular**: separate models, backend, privacy filter, and domain stores — no
  central "god object". A thin ``LocalPersistence`` facade wires them for callers.

This package is the foundation for per-user baseline memory and later long-term
memory / OpenClaw integration without requiring a redesign of storage layout.
"""

from .local_persistence import LocalPersistence
from .models import (
    BondStateRecord,
    DecisionLogRecord,
    UserBaseline,
    UserSettings,
)
from .paths import default_data_root
from .privacy import PrivacyFilter, PrivacyPolicy

__all__ = [
    "LocalPersistence",
    "UserBaseline",
    "BondStateRecord",
    "DecisionLogRecord",
    "UserSettings",
    "PrivacyFilter",
    "PrivacyPolicy",
    "default_data_root",
]
