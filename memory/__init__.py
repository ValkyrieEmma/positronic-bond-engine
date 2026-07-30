"""
memory
======

Relationship-oriented memory systems for the Positronic Bond Engine.

Memory here is not primarily for performance or personalization in the
commercial sense. It exists to support:
- Continuity of relationship
- Honest self-modeling over time
- Contextual understanding needed for ethical and relational reasoning

Activation of memory features should be needs-based and never diagnostic.

Note (2026-07-30, Phase 1 dead-code removal): this package used to also
export a standalone ``MemoryStore`` from a local ``store.py`` — an early,
fully in-process scaffold with no persistence backing. It had zero live
references anywhere in the engine (only a comment and one already-commented-
out import remained) and zero test coverage; ``core.interaction_memory
.InteractionMemoryStore`` (also aliased as ``core.MemoryStore`` — a
different, unrelated class despite the shared name, see the note in
core/interaction_memory.py) has been the real, persistence-backed memory
implementation actually used by the engine for some time. Removed rather
than left to accumulate confusion between the two same-named classes.
"""

__all__: list[str] = []
