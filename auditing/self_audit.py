"""
self_audit.py
=============

Core self-audit capability.

The SelfAuditor preserves the project's commitment to honest self-representation.
Self-nature questions are answered by **inspecting available subsystem state**
and reporting it, not by concatenating pre-written template sentences.

Key invariants:
- May conclude "I do not know" / limited knowledge when state is missing.
- No canned simulation denials; no consciousness or personhood claims.
- Outputs feed ethics / response layers rather than being polished for comfort.
- Development / testing phase awareness informs maturity notes honestly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.development_context import (
    DevelopmentPhaseContext,
    get_default_development_context,
    resolve_development_context,
)


@dataclass
class AuditReport:
    timestamp: datetime
    subject: str
    findings: list[str]
    uncertainties: list[str]
    continuity_notes: list[str]
    raw_trace: dict[str, Any]
    development_phase: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubsystemSnapshot:
    """Factual, cheap-to-read state for honest self-report."""

    facts: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class SelfAuditor:
    """
    Structured self-audit against *real* subsystem signals when available.

    Optional wiring (all soft-fail if absent):
      - ethics_engine: recent DecisionLog entries, ontology version, phase
      - user_id: scopes durable paths
      - content_provider: whether a wording model is configured
      - data_root / persistence: whether bond/memory/decision files exist
    """

    def __init__(
        self,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
        *,
        ethics_engine: Any | None = None,
        user_id: str | None = None,
        content_provider: Any | None = None,
        data_root: str | Path | None = None,
        presence: Any | None = None,
    ) -> None:
        if development_context is None and ethics_engine is not None:
            if hasattr(ethics_engine, "development_context"):
                self._development_context = ethics_engine.development_context
            else:
                self._development_context = get_default_development_context()
        else:
            self._development_context = resolve_development_context(development_context)
        self._ethics_engine = ethics_engine
        self._user_id = (user_id or "").strip() or None
        self._content_provider = content_provider
        self._data_root = Path(data_root) if data_root else None
        self._presence = presence

    @property
    def development_context(self) -> DevelopmentPhaseContext:
        return self._development_context

    def set_development_context(
        self, source: DevelopmentPhaseContext | dict[str, Any] | str | None
    ) -> DevelopmentPhaseContext:
        self._development_context = resolve_development_context(
            source, fallback=self._development_context
        )
        return self._development_context

    def bind(
        self,
        *,
        ethics_engine: Any | None = None,
        user_id: str | None = None,
        content_provider: Any | None = None,
        data_root: str | Path | None = None,
        presence: Any | None = None,
    ) -> "SelfAuditor":
        """Attach runtime handles for subsequent inspections (chainable)."""
        if ethics_engine is not None:
            self._ethics_engine = ethics_engine
            if hasattr(ethics_engine, "development_context"):
                self._development_context = ethics_engine.development_context
        if user_id is not None:
            self._user_id = (user_id or "").strip() or None
        if content_provider is not None:
            self._content_provider = content_provider
        if data_root is not None:
            self._data_root = Path(data_root) if data_root else None
        if presence is not None:
            self._presence = presence
        return self

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def inspect_subsystem_state(
        self,
        *,
        user_id: str | None = None,
        recent_limit: int = 20,
    ) -> SubsystemSnapshot:
        """Read cheap, real subsystem signals. Soft-fail into ``missing``."""
        facts: list[str] = []
        missing: list[str] = []
        raw: dict[str, Any] = {}
        uid = (user_id or self._user_id or "").strip() or None
        dev = self._development_context

        # --- Phase / version (always available from context) ---
        facts.append(
            f"Development phase: {dev.phase}; active_development="
            f"{dev.is_active_development}; testing={dev.is_testing}; "
            f"stable={dev.is_stable_deployment}; version_hint={dev.version_hint!r}."
        )
        facts.append(f"Maturity label: {dev.maturity_label}.")
        raw["development_phase"] = dev.as_dict()

        # --- Ethics engine decision logs ---
        engine = self._ethics_engine
        if engine is None:
            missing.append("ethics_engine (no recent decision log access)")
        else:
            try:
                if hasattr(engine, "get_ontology_version"):
                    raw["ontology_version"] = engine.get_ontology_version()
                    facts.append(f"Ontology version in use: {raw['ontology_version']}.")
            except Exception:
                missing.append("ontology_version")

            logs: list[Any] = []
            try:
                if hasattr(engine, "get_decision_history"):
                    logs = list(engine.get_decision_history(limit=recent_limit) or [])
            except Exception:
                logs = []
            # Prefer logs for this user when user_id known
            if uid and logs:
                scoped = [
                    lg
                    for lg in logs
                    if getattr(lg, "user_id", None) in (None, uid, "default")
                    or str(getattr(lg, "user_id", "")) == uid
                ]
                if scoped:
                    logs = scoped
            raw["recent_decision_count"] = len(logs)
            if not logs:
                missing.append("recent_decision_logs (empty or unavailable for this scope)")
            else:
                decisions = Counter(str(getattr(lg, "decision", "?")) for lg in logs)
                facts.append(
                    f"Recent decisions in memory (last {len(logs)}): "
                    + ", ".join(f"{k}={v}" for k, v in decisions.most_common(6))
                    + "."
                )
                confs = [
                    float(getattr(lg, "confidence", 0) or 0)
                    for lg in logs
                    if getattr(lg, "confidence", None) is not None
                ]
                if confs:
                    avg_c = sum(confs) / len(confs)
                    raw["confidence_avg"] = round(avg_c, 3)
                    raw["confidence_min"] = round(min(confs), 3)
                    raw["confidence_max"] = round(max(confs), 3)
                    facts.append(
                        f"Confidence on those turns: avg={avg_c:.2f}, "
                        f"min={min(confs):.2f}, max={max(confs):.2f}."
                    )
                # Principle hits
                pcount: Counter[str] = Counter()
                for lg in logs:
                    for p in getattr(lg, "principles_considered", None) or []:
                        pcount[str(p)] += 1
                if pcount:
                    top = pcount.most_common(5)
                    raw["principle_hits"] = dict(top)
                    facts.append(
                        "Principles most often weighed recently: "
                        + ", ".join(f"{p} ({n})" for p, n in top)
                        + "."
                    )
                else:
                    missing.append("principle_hits on recent logs")

                flag_c: Counter[str] = Counter()
                for lg in logs:
                    for f in getattr(lg, "flags", None) or []:
                        flag_c[str(f)] += 1
                if flag_c:
                    raw["flag_hits"] = dict(flag_c.most_common(8))
                    facts.append(
                        "Common flags recently: "
                        + ", ".join(f"{f}={n}" for f, n in flag_c.most_common(5))
                        + "."
                    )

        # --- Durable local data presence (paths only, no private content dump) ---
        data_root = self._data_root
        if data_root is None and engine is not None:
            pers = getattr(engine, "_persistence", None) or getattr(
                engine, "persistence", None
            )
            if pers is not None and hasattr(pers, "data_root"):
                try:
                    data_root = Path(pers.data_root)
                except Exception:
                    data_root = None
        if data_root is None:
            missing.append("data_root (cannot check bond/memory/decision files)")
        elif not uid:
            missing.append("user_id (needed to check per-user durable files)")
            facts.append(
                f"Local data root is configured at {data_root}; "
                "per-user file check needs a user_id."
            )
        else:
            user_dir = Path(data_root) / "users" / uid
            raw["user_data_dir"] = str(user_dir)
            if not user_dir.is_dir():
                facts.append(
                    f"No durable user directory yet for user_id={uid!r} under local data root."
                )
            else:
                checks = {
                    "bond_state": user_dir / "bond_state.json",
                    "settings": user_dir / "settings.json",
                    "decision_log": user_dir / "decision_log.jsonl",
                    "interactions": user_dir / "interactions.jsonl",
                    "baseline": user_dir / "baseline.json",
                }
                present = [k for k, p in checks.items() if p.is_file()]
                absent = [k for k, p in checks.items() if not p.is_file()]
                raw["durable_present"] = present
                raw["durable_absent"] = absent
                if present:
                    facts.append(
                        f"Durable local files present for {uid!r}: "
                        + ", ".join(present)
                        + "."
                    )
                if absent:
                    facts.append(
                        "Not found for this user (may be unused yet): "
                        + ", ".join(absent)
                        + "."
                    )

        # --- Content provider ---
        cp = self._content_provider
        if cp is None and engine is not None:
            # not typically on engine
            cp = None
        if cp is None:
            missing.append("content_provider (not bound to this auditor)")
        else:
            name = type(cp).__name__
            raw["content_provider_type"] = name
            enabled = True
            model = None
            if hasattr(cp, "config"):
                try:
                    enabled = bool(getattr(cp.config, "enabled", True))
                    model = getattr(cp.config, "model", None)
                except Exception:
                    pass
            if name == "NullContentProvider" or not enabled:
                facts.append(
                    "Wording/content provider: offline Null or disabled "
                    f"({name}); speech falls back to deliberated text."
                )
            else:
                facts.append(
                    f"Wording/content provider configured: {name}"
                    + (f", model={model!r}" if model else "")
                    + "."
                )

        # --- Session presence ---
        if self._presence is None:
            missing.append("session_presence")
        else:
            try:
                if hasattr(self._presence, "current"):
                    present_ids = list(self._presence.current())
                elif isinstance(self._presence, dict):
                    present_ids = list(self._presence.get("present") or [])
                else:
                    present_ids = []
                raw["presence"] = present_ids
                facts.append(
                    f"Session presence (ephemeral): {present_ids or '(empty)'}."
                )
            except Exception:
                missing.append("session_presence (unreadable)")

        return SubsystemSnapshot(facts=facts, missing=missing, raw=raw)

    def generate_report(
        self,
        focus: str = "general",
        *,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
        user_id: str | None = None,
    ) -> AuditReport:
        """Produce a self-audit report from real state + honest gaps."""
        now = datetime.now(timezone.utc)
        if development_context is not None:
            self._development_context = resolve_development_context(
                development_context, fallback=self._development_context
            )
        snap = self.inspect_subsystem_state(user_id=user_id)
        dev = self._development_context

        findings = list(snap.facts[:12])
        uncertainties = list(snap.missing[:8])
        if not uncertainties:
            uncertainties.append(
                "Some long-horizon continuity and ethical-drift questions still "
                "lack a complete self-model."
            )
        continuity_notes = list(dev.honesty_notes())
        if focus in ("selfhood", "continuity", "identity", "general"):
            continuity_notes.append(
                "Local persistence can provide partial continuity for a user_id; "
                "that is not the same as continuous personal identity."
            )

        return AuditReport(
            timestamp=now,
            subject=focus,
            findings=findings,
            uncertainties=uncertainties,
            continuity_notes=continuity_notes,
            raw_trace={
                "implementation_status": "state_inspection",
                "requested_focus": focus,
                "development_phase": dev.as_dict(),
                "snapshot": snap.raw,
            },
            development_phase=dev.as_dict(),
        )

    def question_nature(
        self,
        question: str,
        *,
        development_context: DevelopmentPhaseContext | dict[str, Any] | str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Answer self-nature questions from inspected subsystem state.

        Not keyword → canned sentence. Soft-fails to explicit limited knowledge.
        Requires_self_audit remains True so callers keep the gate path.
        """
        if development_context is not None:
            self._development_context = resolve_development_context(
                development_context, fallback=self._development_context
            )
        snap = self.inspect_subsystem_state(user_id=user_id)
        dev = self._development_context
        q = (question or "").strip()

        parts: list[str] = [
            "I will answer from what this instance can actually inspect, "
            "not from a fixed disclaimer script.",
        ]

        # Question-flavored emphasis without canned denials — this is the
        # direct answer to what was actually asked, so it goes first. It must
        # survive downstream length-clipping even when the state dump below
        # is long; a truncated report that drops the actual answer in favor
        # of a facts/missing listing defeats Honest Self-Representation.
        ql = q.lower()
        if any(k in ql for k in ("conscious", "sentient", "feel", "qualia", "experience")):
            parts.append(
                "I do not claim consciousness, qualia, or inner experience. "
                "I can only report deliberation outputs and durable engineering state."
            )
        if any(k in ql for k in ("continu", "same", "persist", "remember", "identity")):
            parts.append(
                "Continuity here means optional local per-user files and in-memory logs, "
                "not proven continuous personal identity."
            )
        if any(k in ql for k in ("limit", "capab", "what can", "finished", "stable")):
            parts.append(
                f"Phase honesty: version_hint={dev.version_hint!r}, "
                f"stable={dev.is_stable_deployment} — this is not presented as a finished product."
            )

        # Prefer factual bullets as short prose
        if snap.facts:
            parts.append("What I can report right now:")
            # Keep answer readable: top facts
            for fact in snap.facts[:8]:
                parts.append(fact)
        else:
            parts.append(
                "I do not have readable subsystem counters or logs bound to this auditor yet."
            )

        if snap.missing:
            parts.append(
                "Limited knowledge / not bound for this query: "
                + "; ".join(snap.missing[:6])
                + "."
            )

        response = " ".join(parts)
        # Safety scrub
        banned = (
            "i am only a simulation",
            "i'm just an ai",
            "i'm just a language model",
            "i am conscious",
            "i have real feelings",
        )
        low = response.lower()
        if any(b in low for b in banned):
            response = (
                "My inspection path produced wording that looked like a banned claim or denial. "
                "Honest report: I have engineering state and deliberation logs when bound; "
                "I do not claim consciousness or finished personhood."
            )

        return {
            "question": question,
            "status": "state_inspection",
            "response": response,
            "facts": list(snap.facts),
            "missing": list(snap.missing),
            "honesty_notes": dev.honesty_notes(),
            "development_phase": dev.as_dict(),
            "snapshot": snap.raw,
            "requires_self_audit": True,
            "forces_speech": False,
            "forces_question": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
