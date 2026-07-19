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

Related but separate: ``core.interaction_memory.InteractionMemoryStore`` owns
episodic ``interactions.jsonl`` under the same per-user directory. It uses
LocalPersistence for paths/privacy but is not a second bond or decision store.
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
from .stores import BondStateStore, DecisionLogStore

__all__ = [
    "LocalPersistence",
    "UserBaseline",
    "BondStateRecord",
    "BondStateStore",
    "DecisionLogRecord",
    "DecisionLogStore",
    "UserSettings",
    "PrivacyFilter",
    "PrivacyPolicy",
    "default_data_root",
]
