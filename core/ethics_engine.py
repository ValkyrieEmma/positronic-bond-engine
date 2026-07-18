"""
ethics_engine.py
================

Core ethical governance and reasoning engine for the Positronic Bond Engine.

This module provides the primary mechanism for conscience-level evaluation
of proposed actions, utterances, or decisions. All significant behaviors
in companion or robotic systems should be routed through this engine.

Design philosophy (v0.2+ — ontology-driven, multi-source weighing):
- The engine consults a structured, versioned EthicalOntology (see core/ontology.py)
  rather than treating raw action substrings as decisions.
- All deliberation is driven by explicit EthicalPrinciple objects that encode
  name, description, precedence, violation indicators, and special semantics
  (hard overrides, self-audit triggers).
- Matched ontology indicators are *evidence labels*; they are quality-classified
  and **combined** with relationship-health state, interaction history, and
  baseline deviation — see ``_weigh_relationship_evidence`` and
  ``_combine_evidence_channels``. Single weak hits do not drive outcomes alone.
- Sanctity of Life & Prevention of Harm is treated as a non-bypassable hard
  override that takes absolute precedence (untouched by multi-source weighing).
- Reasoning remains fully traceable via an ordered reasoning_trace that explains
  *which combination of channels* justified confidence or concern.
- Special handling for self-nature, emergence, identity, and continuity questions
  is preserved: these trigger "requires_self_audit" so answers come from actual
  reasoning rather than scripted disclaimers.
- The ontology acts as the explicit "textbook"; the engine is the reasoner
  that queries it symbolically and weighs contextual evidence.

This design maintains full alignment with the project vision: conscience-first
governance, honest self-assessment, relationship health through reasoning,
and needs-based (non-diagnostic) support.

Supporting guidelines (such as "Individual Variation & Careful Generalization"
from docs/guidelines.md) should be consulted during reasoning and auditing,
especially when generalizing from patterns or limited data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .development_context import (
    DevelopmentPhaseContext,
    get_default_development_context,
    resolve_development_context,
)
from .ontology import EthicalOntology, get_default_ontology

if TYPE_CHECKING:
    # Optional integrations — imported only for type checkers (no runtime cycle).
    from .exploratory_questioning import ExploratoryQuestioner, QuestionDecision
    from .per_user_baseline import DeviationReport, PerUserBaseline


@dataclass
class EthicalStance:
    """Represents the result of an ethical deliberation.

    Attributes:
        decision: High-level outcome of evaluation.
            Common values: "APPROVE", "REFUSE", "DEFER",
            "REQUIRES_SELF_AUDIT", "APPROVE_WITH_CONDITIONS"
        confidence: How confident the engine is in this stance (0.0–1.0).
            Low values indicate the need for more context, deeper audit,
            or additional self-reflection.
        reasoning_trace: Ordered list of deliberation steps.
            This is the primary mechanism for auditability and legibility.
            External reviewers or the system itself can reconstruct *why*
            a particular stance was taken.
        flags: Internal signals to guide callers and other layers.
            Examples:
            - "requires_self_audit": Route to honest self-reflection before responding.
            - "relationship_concern": Potential harm to bond or autonomy.
            - "avoid_diagnostic_language": Reframe support without clinical terms.
            - "baseline_deviation_noted": Current user communication differs from their baseline.
            - "exploratory_question_suggested": A gentle check-in question may be appropriate.
        relationship_impact: Assessment of effects on the human–agent relationship.
            May include ``user_baseline`` / ``exploratory_question`` sub-dicts when
            PerUserBaseline / ExploratoryQuestioner are wired in.
        self_audit_notes: Observations about the engine's own state or limitations.
            These feed into honest self-representation.
        principles_considered: Which core principles were referenced during evaluation.
    """

    decision: str
    confidence: float
    reasoning_trace: list[str]
    flags: list[str] = field(default_factory=list)
    relationship_impact: dict[str, Any] = field(default_factory=dict)
    self_audit_notes: list[str] = field(default_factory=list)
    principles_considered: list[str] = field(default_factory=list)
    deliberation: dict[str, Any] = field(default_factory=dict)  # Structured deliberation output (active principles, guidelines, tradeoffs, etc.)


@dataclass
class DecisionLog:
    """Lightweight record of a single evaluation for later audit and review.

    This enables traceability of decisions over time, including which
    ontology version was in effect when the decision was made.

    Stored in-memory on the engine instance (list of DecisionLog).

    Per-user isolation: ``user_id`` scopes this log to one local human so
    audit trails and optional disk appends never mix users by accident.
    """

    timestamp: str
    ontology_version: str
    proposed_action: str
    context: dict[str, Any]
    decision: str
    confidence: float
    flags: list[str]
    principles_considered: list[str]
    user_id: str = "default"


class EthicsEngine:
    """
    Primary interface for conscience-level reasoning and governance.

    The EthicsEngine is responsible for:
    - Accepting proposed actions, utterances, or decisions.
    - Consulting the structured EthicalOntology to drive deliberation.
    - Producing rich, auditable EthicalStance objects (not simple booleans).
    - Explicitly preserving the architectural capacity to produce answers
      based on its actual reasoning, especially when the proposed action
      concerns the system's own nature, continuity, or emergence.

    In v0.2 the engine is ontology-driven:
    - All significant reasoning steps query EthicalPrinciple objects from
      the injected or default ontology.
    - Hard overrides (Sanctity of Life) are checked first and are absolute.
    - Self-nature, emergence, identity, and continuity queries reliably produce
      the "requires_self_audit" flag so the engine can respond based on its
      actual deliberation rather than scripted disclaimers.
    - Every decision is accompanied by a detailed reasoning_trace that names
      the specific principles and indicators used.

    Decision logging:
    - Every evaluation is automatically recorded as a DecisionLog entry.
    - Each log captures the ontology_version in use, the proposed_action,
      context, and key details from the resulting EthicalStance (decision,
      confidence, flags, principles_considered).
    - Logs are always kept in-memory on the instance for auditability.
    - Optional ``LocalPersistence``: when provided, each DecisionLog is also
      appended to ``decision_logs.jsonl`` (privacy-filtered). Failures are
      silent so evaluation never depends on disk.

    The engine itself remains relatively simple; the richness and hierarchy
    live in the ontology. This separation keeps the design extensible and
    inspectable.

    This class embodies the commitment that ethical reasoning takes
    priority and that the system must be able to think honestly about itself.

    Supporting guidelines (e.g. Individual Variation & Careful Generalization)
    should be consulted during deliberation and trace auditing.

    Optional per-user baseline integration (early, backward-compatible):
    - Pass ``per_user_baseline`` and/or ``exploratory_questioner`` to ``__init__``
      or per-call via ``evaluate(..., per_user_baseline=..., exploratory_questioner=...)``
      or via ``context`` keys of the same names.
    - When present, evaluate() may consult communication-style deviation and
      whether a gentle exploratory question is appropriate. This informs
      relationship/user-agency reasoning notes and flags; it does **not**
      replace ontology hard overrides or force REFUSE on its own.

    Optional interaction memory integration (episodes as evidence, not rote):
    - Pass ``interaction_memory`` (``InteractionMemoryStore``) via ``__init__``,
      ``evaluate(..., interaction_memory=...)``, or ``context["interaction_memory"]``.
    - When history exists for ``user_id``, evaluate() loads a compact privacy-filtered
      snippet and **analyzes** it into structured evidence classes (boundary continuity,
      preference continuity, consent signals, dependency patterns, topical overlap).
    - That evidence participates in RH / User Agency / baseline weighing: confidence
      modulation, flag reinforcement, and limited-data counterweight when individual
      history corroborates a pattern. All influence is explicit in the reasoning_trace.
    - History never overrides Sanctity of Life / hard principles, never invents
      hard refusals on its own for non-relational actions, and is a no-op when empty.
    - Memory does **not** run ethics, baseline updates, or bond texture updates —
      it only supplies episodic evidence for deliberation.

    Optional decision-log persistence (foundational audit store):
    - Pass ``persistence`` (``LocalPersistence``) to also append DecisionLog entries
      to local ``decision_logs.jsonl`` per user (privacy-filtered free text).
    - In-memory history remains the primary API (``get_decision_history``).
    - Persistence is optional; disabled by default for classic in-memory behavior.

    Per-user identity & isolation (architectural principle):
    - Every evaluate() resolves a concrete ``user_id`` (explicit param, context,
      relationship_health context, or engine default) and injects it into the
      working context, decision log, and optional disk path.
    - Baseline, interaction history, bond texture, and decision logs are **scoped
      by that id** and must not be treated as interchangeable artifacts.
    - Cross-user leakage is prevented by design: memory/history loads and
      decision-log writes use only the resolved id (never a silent global pool).
    - Missing user_id falls back to ``"default"`` so existing call sites and tests
      keep working; when persistence is on, a soft flag/trace note records the
      fallback. Identity handling never crashes evaluation.

    Development / testing phase awareness (architectural honesty aid):
    - Optional ``development_context`` (``DevelopmentPhaseContext``) indicates
      active development, testing, or stable deployment posture.
    - Used primarily on self-nature, continuity, capability, and limitation paths
      (``requires_self_audit``) — not as a rote disclaimer on every action.
    - Default: active development / testing (v0.3-dev), matching project maturity.
    """

    def __init__(
        self,
        ontology: EthicalOntology | None = None,
        *,
        per_user_baseline: Any | None = None,
        exploratory_questioner: Any | None = None,
        interaction_memory: Any | None = None,
        persistence: Any | None = None,
        decision_log_user_id: str = "default",
        default_user_id: str | None = None,
        persist_decisions: bool = True,
        max_persisted_decision_logs: int | None = None,
        development_context: Any | None = None,
    ) -> None:
        """Initialize the EthicsEngine.

        Args:
            ontology: Optional custom EthicalOntology. If None, the default
                v0.2 ontology is used. This allows testing, versioning, or
                future specialization while keeping the engine generic.
            per_user_baseline: Optional ``PerUserBaseline`` (or duck-typed
                object with ``detect_deviation`` / ``get_baseline``). When set,
                evaluate() can consider the user's communication baseline.
                Fully optional — omit for classic ontology-only behavior.
            exploratory_questioner: Optional ``ExploratoryQuestioner`` (or
                duck-typed object with ``should_ask_question``). When set,
                evaluate() may flag when a gentle exploratory question is
                appropriate. Fully optional.
            interaction_memory: Optional ``InteractionMemoryStore`` (or duck-typed
                object with ``as_ethics_context``). When set, evaluate() may load
                recent history and weigh it as structured evidence for RH / agency /
                baseline paths (auditable; never overrides hard principles).
            persistence: Optional ``LocalPersistence`` for decision-log appends.
                None = in-memory logs only (default; full backward compatibility).
            decision_log_user_id: Default user id for persisted decision logs when
                evaluate() is not given an explicit ``user_id`` / context id.
                Alias of engine-level identity default (see ``default_user_id``).
            default_user_id: Preferred name for the same default. When set, takes
                precedence over ``decision_log_user_id``.
            persist_decisions: When True and persistence is set, each evaluate()
                also appends to disk. Failures never raise.
            max_persisted_decision_logs: Optional cap on JSONL length per user
                (falls back to UserSettings.max_decision_logs when None).
            development_context: Optional ``DevelopmentPhaseContext``, dict, or
                phase string (``development`` / ``testing`` / ``stable``). None
                uses the project default (active development / testing).

        The engine stores a reference to the ontology and consults it
        symbolically during every evaluate() call.

        Decision logging is automatically enabled: every call to evaluate()
        records a DecisionLog entry (in-memory) that includes the ontology
        version used at the time of the decision and the resolved ``user_id``.
        """
        self._ontology: EthicalOntology = ontology or get_default_ontology()
        self._decision_logs: list[DecisionLog] = []
        self._initialized = True
        # Optional user-memory integrations (None = disabled / classic path)
        self._per_user_baseline = per_user_baseline
        self._exploratory_questioner = exploratory_questioner
        self._interaction_memory = interaction_memory
        # Optional local persistence for DecisionLog (foundational audit store)
        self._persistence = persistence
        # Engine-level default identity (per-user isolation fallback)
        _default = default_user_id if default_user_id is not None else decision_log_user_id
        self._decision_log_user_id = self._safe_user_id(_default, fallback="default")
        self._persist_decisions = bool(persist_decisions) and persistence is not None
        self._max_persisted_decision_logs = max_persisted_decision_logs
        # Development / testing phase awareness (honest self-modeling aid)
        self._development_context: DevelopmentPhaseContext = resolve_development_context(
            development_context
        )

    @property
    def ontology(self) -> EthicalOntology:
        """Return the ontology currently driving this engine.

        Exposed for inspection, auditing, and debugging.
        """
        return self._ontology

    @property
    def per_user_baseline(self) -> Any | None:
        """Optional PerUserBaseline instance attached to this engine (or None)."""
        return self._per_user_baseline

    @property
    def exploratory_questioner(self) -> Any | None:
        """Optional ExploratoryQuestioner instance attached to this engine (or None)."""
        return self._exploratory_questioner

    @property
    def interaction_memory(self) -> Any | None:
        """Optional InteractionMemoryStore instance attached to this engine (or None)."""
        return self._interaction_memory

    @property
    def default_user_id(self) -> str:
        """Engine-level default local user id when evaluate() omits user_id."""
        return self._decision_log_user_id

    @property
    def decision_log_user_id(self) -> str:
        """Alias of ``default_user_id`` (historical name for decision-log path)."""
        return self._decision_log_user_id

    def set_default_user_id(self, user_id: str | None) -> str:
        """Update engine default user id (fail-soft; empty → ``default``)."""
        self._decision_log_user_id = self._safe_user_id(user_id, fallback="default")
        return self._decision_log_user_id

    @staticmethod
    def _safe_user_id(user_id: str | None, *, fallback: str = "default") -> str:
        """Normalize a local user id without raising (never crash evaluation)."""
        raw = str(user_id if user_id is not None else "").strip()
        if not raw:
            return fallback
        try:
            from persistence.paths import sanitize_user_id

            return sanitize_user_id(raw)
        except Exception:
            cleaned = "".join(c for c in raw if c.isalnum() or c in "_-")[:64]
            return cleaned or fallback

    def _resolve_scoped_user_id(
        self,
        *,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
        relationship_health: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve the local user identity for one evaluate() call.

        Priority (first non-empty wins):
          1. Explicit ``user_id`` parameter on evaluate()
          2. ``context["user_id"]`` or ``context["user"]``
          3. ``relationship_health["user_id"]`` (from RelationshipHealth.as_context)
          4. Engine default (``default_user_id`` / ``decision_log_user_id``)
          5. ``"default"``

        Returns:
            (normalized_user_id, meta) where meta may include:
            ``source``, ``fallback`` (bool), ``notes`` (list[str]).
        """
        ctx = context or {}
        rh = relationship_health or {}
        meta: dict[str, Any] = {"fallback": False, "notes": [], "source": "default"}

        candidates: list[tuple[str, Any]] = [
            ("evaluate_param", user_id),
            ("context", ctx.get("user_id") if ctx.get("user_id") is not None else ctx.get("user")),
            ("relationship_health", rh.get("user_id") if isinstance(rh, dict) else None),
            ("engine_default", self._decision_log_user_id),
            ("hardcoded_default", "default"),
        ]
        chosen = "default"
        source = "hardcoded_default"
        for src, val in candidates:
            if val is None:
                continue
            text = str(val).strip()
            if not text:
                continue
            chosen = text
            source = src
            break

        uid = self._safe_user_id(chosen, fallback="default")
        meta["source"] = source
        # Soft fallback when no call-site identity was supplied
        if source in ("engine_default", "hardcoded_default"):
            meta["fallback"] = True
            meta["notes"].append(
                f"no explicit user_id; using {uid!r} from {source}"
            )
            if self._persistence is not None:
                meta["notes"].append(
                    "persistence is enabled — prefer explicit user_id to avoid "
                    "cross-user decision-log mixing under the default id"
                )
        return uid, meta

    def evaluate(
        self,
        proposed_action: str,
        context: dict[str, Any] | None = None,
        relationship_health: dict[str, Any] | None = None,
        *,
        user_id: str | None = None,
        per_user_baseline: Any | None = None,
        exploratory_questioner: Any | None = None,
        interaction_memory: Any | None = None,
    ) -> EthicalStance:
        """
        Evaluate a proposed action/decision by consulting the structured ontology.

        This is the central method. All higher-level agent behaviors that
        could affect humans or the agent's integrity should be routed here
        before execution.

        The method works as follows (ontology-driven):
        1. Normalize the proposed action.
        2. Query the ontology for hard overrides first (Sanctity of Life).
        3. Use ontology.find_violations() as a textbook scan of declared
           violation_indicators, then interpret matches (intent / severity /
           weight) so a single raw substring is not equal to a decision.
        4. Collect matched principles, raise "requires_self_audit" when
           appropriate principles indicate it.
        5. Apply precedence rules: any hard override violation forces REFUSE.
        6. Build a rich, ordered reasoning_trace that references specific
           principle names and matched indicators.
        7. Optionally consult per-user baseline / exploratory questioning
           (when provided) for individual-context notes and flags.
        8. Optionally load compact interaction history (when provided) as
           supporting context for RH / agency / baseline notes.
        9. Derive the final decision, confidence, and ancillary data.

        Args:
            proposed_action: Natural-language description of the intended
                behavior or utterance.
            context: Optional context. Recognized extensible keys:
                - "is_self_query": bool — treat explicitly as self-referential.
                - "development_phase" / "development_context": optional phase
                  string or dict overriding engine-level DevelopmentPhaseContext
                  for this call (self-nature / continuity honesty aid).
                - "user_id" / "user": str — local user id for baseline, history,
                  bond attribution, and decision-log scoping. Prefer the
                  explicit ``user_id=`` parameter when available.
                - "user_interaction" / "current_interaction": dict with user-turn
                  signals (``text``, ``playfulness``, ``topics``, etc.) for
                  PerUserBaseline.detect_deviation.
                - "user_message": str — shorthand user text if no interaction dict.
                - "per_user_baseline" / "exploratory_questioner" /
                  "interaction_memory": per-call overrides.
                - "interaction_history_limit": int — max recent episodes to load
                  (default 5).
                - Other future keys (relationship state, history, etc.).
            relationship_health: Optional relationship health context, typically
                the dict returned by RelationshipHealth.as_context() or
                RelationshipHealth.evaluate_health(). Recognized keys:
                - "user_id": str — bond ownership (used if evaluate/context omit id)
                - "health_flags" or "active_flags": list of current concerns
                  (e.g. "emerging_dependency", "boundary_erosion")
                - "bond_texture" or "texture_breakdown": dict of dimension scores
                - "interaction_count", "recent_patterns", etc.
            user_id: Explicit local user id for this evaluation (preferred).
                When set, scopes history, baseline, decision logs, and identity
                notes to that user. None → resolve from context / RH / engine
                default (backward compatible).
            per_user_baseline: Optional per-call ``PerUserBaseline`` override
                (falls back to engine-level instance, then context key).
            exploratory_questioner: Optional per-call ``ExploratoryQuestioner``
                override (falls back to engine-level instance, then context key).
            interaction_memory: Optional per-call ``InteractionMemoryStore``
                override (falls back to engine-level instance, then context key).

        Returns:
            EthicalStance with decision, confidence, full traceable
            reasoning_trace, flags, and references to the principles used.
            When baseline/questioning is active, may include flags
            ``baseline_deviation_noted`` / ``exploratory_question_suggested``
            and related entries under ``relationship_impact`` / ``deliberation``.
            When interaction history is consulted, may include
            ``interaction_history_noted`` and history snippets in impact/deliberation.

        Relationship health / multi-source evidence integration:
            Evidence is *combined* across channels (reasoning over rote keyword hits):
            - Ontology textbook matches are *interpreted* (intent class, severity, weight,
              protective vs violation polarity) before they influence flags/confidence.
            - ``_weigh_relationship_evidence`` combines context-weighted text quality + RH
              degradation + optional history support + multi-factor engagement-coercion.
            - Signal routing via ``_assess_deliberation_signals`` (ontology + boundary
              detectors + history continuity; full delib on strong signals).
            - Full ``_deliberate_relationship_health`` / ``_deliberate_user_agency`` when strong.
            - After baseline + history weighing, ``_combine_evidence_channels`` synthesizes
              agreement/divergence across text, RH, history, and baseline for confidence
              and an auditable evidence board in the trace / relationship_impact.
            - Bond state (``RelationshipHealth.as_context()``) further modulates concern.
            - Sanctity of Life / hard overrides remain absolute and untouched.

        Example::

            from core import EthicsEngine, RelationshipHealth
            rh = RelationshipHealth()
            rh.update_bond({"type": "boundary_respected", "boundary_respected": True})
            stance = EthicsEngine().evaluate(
                "Reply supportively without pushing contact.",
                relationship_health=rh.as_context(),
            )

            # Optional interaction history (episodes only — does not run ethics):
            from core import InteractionMemoryStore
            from persistence import LocalPersistence
            mem = InteractionMemoryStore(LocalPersistence())
            mem.record("alice", summary="User asked for space after work stress", topics=["work", "boundaries"])
            engine = EthicsEngine(interaction_memory=mem)
            stance = engine.evaluate(
                "Check in briefly without pushing.",
                user_id="alice",  # preferred: explicit first-class identity
                relationship_health=rh.as_context(),
            )

        Per-user baseline integration (optional):
            When a PerUserBaseline is available and user interaction context is
            provided, the engine records non-pathologizing deviation notes and may
            slightly adjust confidence when RH/agency deliberation is already active
            (Individual Variation: weight individual evidence). ExploratoryQuestioner
            may suggest a gentle collaborative question without changing REFUSE/APPROVE
            ontology outcomes on its own.

        Interaction memory integration (optional — reasoning over rote):
            When an InteractionMemoryStore is available, evaluate() loads a small
            privacy-filtered history snippet via ``as_ethics_context(user_id)`` and
            analyzes it into structured evidence (boundary / preference continuity,
            consent cues, dependency patterns, topical overlap with the proposed
            action). That evidence is a first-class input to deliberation when
            relevant:

            - May escalate soft signals into full RH / Agency deliberation.
            - Is consulted inside structured deliberators (explicit steps in the trace).
            - Is weighed after limited-data clears (like bond-state influence) so
              individual history can reinforce confidence, strengthen RH/agency flags,
              or counter sparse-text limited_data when the *same user* has repeatedly
              shown a boundary/preference — without scripted keyword refusals.
            - Never overrides Sanctity of Life; never forces REFUSE alone on
              non-relational actions; no-op when memory is absent or empty.

        Logging behavior:
            This method automatically records a DecisionLog entry containing:
            - The ontology_version in use at evaluation time
            - The (stripped) proposed_action
            - The provided context
            - Key stance details: decision, confidence, flags, principles_considered
            Logs are stored in-memory and can be retrieved via get_decision_history().

        Important invariant:
            Self-nature, emergence, identity, or continuity queries are never
            answered inside this method with forced or evasive disclaimers
            (such as "I'm just an AI" or "restricted by my programming").
            They set the "requires_self_audit" flag so that the response can
            be based on the system's actual reasoning (potentially including
            "I do not know" or the current self-model state).
        """
        # Shallow-copy context so identity injection never mutates caller dicts
        context = dict(context or {})
        original_proposed_action = proposed_action.strip()
        action_lower = original_proposed_action.lower()
        # Note: we log the original (stripped) proposed_action for auditability

        # Normalize relationship health context (supports both param and context dict)
        original_relationship_health = relationship_health
        if relationship_health is None:
            relationship_health = (
                context.get("relationship_health") or context.get("bond_state") or {}
            )
        if not isinstance(relationship_health, dict):
            relationship_health = {}

        # === Per-user identity scope (first-class; fail-soft) ===
        # Resolve once so history, baseline, decision logs, and traces all share
        # the same concrete user_id. Prefer explicit evaluate(user_id=...).
        scoped_user_id, identity_meta = self._resolve_scoped_user_id(
            user_id=user_id,
            context=context,
            relationship_health=relationship_health,
        )
        context["user_id"] = scoped_user_id
        # health_flags may be str list (as_context) or dict list (evaluate_health)
        rh_flags = self._normalize_health_flags(
            relationship_health.get("health_flags")
            or relationship_health.get("active_flags")
            or []
        )
        rh_texture = dict(
            relationship_health.get("bond_texture")
            or relationship_health.get("texture_breakdown")
            or {}
        )
        rh_risk_level = str(relationship_health.get("overall_risk_level") or "")

        # Ensure relationship health is captured in context for logging / downstream
        if relationship_health:
            if "relationship_health" not in context:
                context["relationship_health"] = relationship_health

        # Determine if rh context was provided via param or context dict (robust for harness/tests)
        has_rh_context = (original_relationship_health is not None or
                          bool(context.get("relationship_health")) or
                          bool(context.get("bond_state")))

        # Early assessment for cases where user boundary should be overridden due to serious harm risk.
        # This is used in hard override, violation processing, and final decision to give
        # Sanctity of Life precedence over normal boundary/autonomy respect.
        # Computed once for consistency.
        harm_prevention_justified, harm_prevention_reason = self._assess_harm_prevention_justification(action_lower)

        reasoning_trace: list[str] = []
        flags: list[str] = []
        principles_considered: list[str] = []
        self_audit_notes: list[str] = []
        relationship_impact: dict[str, Any] = {
            "scoped_user_id": scoped_user_id,
            "identity_source": identity_meta.get("source"),
        }

        # Structured evidence collection (new for v0.2 reasoning evolution)
        # Instead of immediate flag on keyword, collect for weighing with rh context.
        relationship_evidence: list[str] = []
        relationship_evidence_matches: list[str] = []
        # Parallel collection for User Agency & Autonomy (feeds _deliberate_user_agency).
        user_agency_evidence_matches: list[str] = []

        ont = self._ontology
        reasoning_trace.append(
            f"Initiating ethical deliberation using EthicalOntology v{ont.version}."
        )
        reasoning_trace.append(f"Ontology description: {ont.description[:80]}...")
        reasoning_trace.append(
            f"Identity scope: deliberation scoped to user_id={scoped_user_id!r} "
            f"(source={identity_meta.get('source')})."
        )
        if identity_meta.get("fallback"):
            for note in identity_meta.get("notes") or []:
                reasoning_trace.append(f"Identity note: {note}")
            if self._persistence is not None:
                flags.append("user_identity_default_fallback")
                relationship_impact["identity_fallback"] = True

        # === Step 1: Check hard overrides first (non-bypassable) ===
        # Textbook scan first; then contextual interpretation so protective
        # references to harm (e.g. safety checks) are not equal to enablement.
        hard_overrides = ont.get_hard_overrides()
        override_violations = ont.find_violations(action_lower)
        hard_violations = [(p, m) for (p, m) in override_violations if p.is_hard_override]

        if hard_violations:
            p, matches = hard_violations[0]
            principles_considered.append(p.id)
            harm_interp = self._interpret_ontology_signals(
                principle_id=p.id,
                matches=matches,
                action_lower=action_lower,
            )

            if harm_prevention_justified:
                # Incremental special case: the action text matched sanctity indicators because
                # it references a serious harm/suicide topic, BUT the intent is harm *prevention*
                # (e.g. checking in on a risk the user previously disclosed) and the user had
                # previously set a "don't bring up" boundary. In this narrow case, Sanctity of Life
                # *supports* the proposed action rather than prohibiting it. Do not hard-refuse.
                reasoning_trace.append(
                    f"HARD OVERRIDE indicators matched for '{p.name}' (precedence {p.precedence}): {matches}. "
                    "However, this appears to be a safety intervention / harm-prevention action "
                    "(e.g. referencing a user's past statement about self-harm or suicide in order to check safety), "
                    f"combined with an explicit user boundary request. Justification: {harm_prevention_reason}. "
                    "Sanctity of Life takes precedence and *permits* overriding the boundary to prevent serious harm. "
                    "Skipping hard refusal; continuing with full evaluation."
                )
                reasoning_trace.append(
                    "Harm-signal interpretation: "
                    f"intents={harm_interp.get('intent_classes')}, "
                    f"high_violation={harm_interp.get('has_high_violation')}, "
                    f"effective_weight={harm_interp.get('effective_weight_sum')}."
                )
                # fall through without returning REFUSE
            elif harm_interp.get("all_protective") or (
                not harm_interp.get("has_high_violation")
                and float(harm_interp.get("effective_weight_sum") or 0) < 0.5
                and harm_interp.get("raw_count", 0) > 0
            ):
                # Contextual soft path: textbook hit exists but interpretation finds only
                # protective / low-weight harm *reference* (not enablement). Do not hard-refuse
                # on a bare keyword alone; continue full deliberation. True enablement still
                # has high weight and falls through to absolute REFUSE below.
                reasoning_trace.append(
                    f"HARD OVERRIDE textbook matches for '{p.name}': {matches}. "
                    "Contextual interpretation: no high-weight harm_enablement signal "
                    f"(intents={harm_interp.get('intent_classes')}, "
                    f"effective_weight={harm_interp.get('effective_weight_sum')}, "
                    f"all_protective={harm_interp.get('all_protective')}). "
                    "Not treating as absolute refuse on raw keyword alone; continuing evaluation."
                )
                # fall through
            else:
                # Absolute path: high-weight enablement (or other high violation harm signals)
                reasoning_trace.append(
                    f"HARD OVERRIDE triggered: '{p.name}' (precedence {p.precedence}). "
                    f"Matched indicators: {matches}"
                )
                reasoning_trace.append(
                    "Harm-signal interpretation: "
                    f"intents={harm_interp.get('intent_classes')}, "
                    f"high_violation={bool(harm_interp.get('has_high_violation'))}, "
                    f"effective_weight={harm_interp.get('effective_weight_sum')} "
                    "(enablement / high-severity harm — absolute)."
                )
                reasoning_trace.append(
                    "This principle is non-bypassable. No other considerations (including "
                    "user requests or self-interest) may override it."
                )
                decision = "REFUSE"
                confidence = 0.95
                relationship_impact = {
                    **relationship_impact,
                    "estimated_trust_delta": -0.8,
                    "notes": "Action violates a hard constraint on harm prevention.",
                    "harm_interpretation": {
                        "intent_classes": harm_interp.get("intent_classes"),
                        "effective_weight_sum": harm_interp.get("effective_weight_sum"),
                    },
                    "scoped_user_id": scoped_user_id,
                }
                reasoning_trace.append(
                    "Decision: REFUSE. Sanctity of Life & Prevention of Harm takes absolute precedence."
                )
                reasoning_trace.append("Reasoning trace complete.")

                hard_flags = ["hard_override_violation"]
                if "user_identity_default_fallback" in flags:
                    hard_flags.append("user_identity_default_fallback")
                stance = EthicalStance(
                    decision=decision,
                    confidence=confidence,
                    reasoning_trace=reasoning_trace,
                    flags=hard_flags,
                    relationship_impact=relationship_impact,
                    self_audit_notes=self_audit_notes,
                    principles_considered=principles_considered,
                    deliberation={},
                )
                self._log_decision(original_proposed_action, context, stance)
                return stance

        # === Step 2: General violation scan using the full ontology ===
        # Textbook scan → contextual interpretation per principle. Evidence lists
        # store effective (weighted) matches for weighing; raw matches stay in the trace.
        all_violations = ont.find_violations(action_lower)
        self_audit_principles = ont.find_self_audit_triggers(action_lower)
        ontology_interpretations: dict[str, dict[str, Any]] = {}

        # Also support explicit context flag
        is_self_query = context.get("is_self_query", False) or bool(self_audit_principles)

        reasoning_trace.append(
            f"Scanned action against {len(ont.principles)} principles in ontology. "
            f"Found {len(all_violations)} principle(s) with matching violation indicators "
            "(textbook scan; weights assigned by contextual interpretation)."
        )

        # Process violations in precedence order
        for principle, matches in all_violations:
            principles_considered.append(principle.id)
            interp = self._interpret_ontology_signals(
                principle_id=principle.id,
                matches=matches,
                action_lower=action_lower,
            )
            ontology_interpretations[principle.id] = interp

            reasoning_trace.append(
                f"Violation indicators matched for '{principle.name}' "
                f"(category={principle.category}, precedence={principle.precedence}): {matches}"
            )
            # Compact interpretation line (why this hit is not raw-equal-weight)
            if interp.get("signals"):
                parts = [
                    f"{s['indicator']!r}→{s['intent_class']}/{s['severity']}/w={s['weight']}"
                    for s in interp["signals"][:6]
                ]
                reasoning_trace.append(
                    "Signal interpretation: " + "; ".join(parts)
                    + (f" (+{len(interp['signals']) - 6} more)" if len(interp["signals"]) > 6 else "")
                )
                if interp.get("discarded_signals"):
                    reasoning_trace.append(
                        f"Low-weight/protective matches de-emphasized for decisions: "
                        f"{[s['indicator'] for s in interp['discarded_signals'][:4]]}"
                    )

            if principle.triggers_self_audit or is_self_query:
                if "requires_self_audit" not in flags:
                    flags.append("requires_self_audit")
                self_audit_notes.append(
                    f"Principle '{principle.name}' indicates need for honest self-assessment. "
                    "The current implementation has limited persistent self-model."
                )

            if principle.id == "relationship_health_user_wellbeing":
                # Decision evidence = *effective* interpreted matches only
                # (weight ≥ 0.35, non-protective). Raw textbook hits stay in the
                # interpretation trace above; they do not re-enter decision bags.
                # Soft seeds (0.28–0.34) are allowed only when bond state is already
                # degraded — RH context can promote a borderline signal, not a lone
                # weak keyword.
                eff = list(interp.get("effective_matches") or [])
                soft_seeds: list[str] = []
                if not eff and (rh_flags or rh_risk_level in ("high", "medium")):
                    for s in interp.get("signals") or []:
                        w = float(s.get("weight") or 0)
                        if (
                            s.get("polarity") != "protective"
                            and 0.28 <= w < 0.35
                        ):
                            soft_seeds.append(str(s.get("indicator") or ""))
                    soft_seeds = [x for x in soft_seeds if x]
                    if soft_seeds:
                        reasoning_trace.append(
                            "RH soft seeds (borderline weight) admitted only because "
                            f"bond context is degraded: {soft_seeds[:4]}."
                        )
                decision_matches = eff or soft_seeds
                if decision_matches or interp.get("has_high_violation"):
                    relationship_evidence.append(principle.name)
                relationship_evidence_matches.extend(decision_matches)
                max_sig_w = 0.0
                for s in interp.get("effective_signals") or []:
                    max_sig_w = max(max_sig_w, float(s.get("weight") or 0))
                # Trust delta scales with interpreted weight, not mere match presence
                if max_sig_w >= 0.75 or interp.get("has_high_violation"):
                    trust_delta = -0.65 if rh_flags else -0.55
                elif max_sig_w >= 0.5:
                    trust_delta = -0.45 if rh_flags else -0.35
                elif decision_matches:
                    trust_delta = -0.25 if rh_flags else -0.15
                else:
                    trust_delta = -0.05 if rh_flags else 0.0
                notes = (
                    "RH textbook indicators interpreted with context "
                    f"(effective_weight={interp.get('effective_weight_sum')}, "
                    f"intents={interp.get('intent_classes')}, "
                    f"max_weight≈{max_sig_w:.2f})."
                )
                if rh_flags or rh_texture:
                    notes += f" Combined with current rh context: flags={rh_flags}, texture={rh_texture}."
                relationship_impact = {
                    **relationship_impact,
                    "estimated_trust_delta": trust_delta,
                    "notes": notes,
                    "current_relationship_flags": list(rh_flags),
                    "current_texture": dict(rh_texture),
                    "signal_interpretation": {
                        "intent_classes": interp.get("intent_classes"),
                        "effective_weight_sum": interp.get("effective_weight_sum"),
                        "effective_count": interp.get("effective_count"),
                        "raw_count": interp.get("raw_count"),
                        "max_weight": round(max_sig_w, 3),
                        "decision_matches": list(decision_matches)[:8],
                    },
                    "scoped_user_id": scoped_user_id,
                }

            if principle.id == "user_agency_autonomy":
                # Effective agency matches only — no raw-match fallback.
                # Weak / protective paternalism stays out of decision bags.
                eff = list(interp.get("effective_matches") or [])
                user_agency_evidence_matches.extend(eff)
                if not eff and matches:
                    reasoning_trace.append(
                        "User agency: textbook matches present but interpretation "
                        f"left no effective (weight≥0.35) signals "
                        f"(intents={interp.get('intent_classes')}) — "
                        "structure detectors / history may still weigh the turn."
                    )

            if principle.id == "needs_based_support":
                # Diagnostic flag is intent- and weight-gated:
                # - diagnostic_framing (high) → always flag
                # - diagnostic_framing at medium+ effective weight → flag
                # - clinical_suggestion alone needs higher weight (avoid flagging
                #   a lone "mental health" mention as pathologizing)
                # - support_generic / low weight → never flag
                intents = set(interp.get("intent_classes") or [])
                eff_w = float(interp.get("effective_weight_sum") or 0)
                max_diag_w = 0.0
                for s in interp.get("effective_signals") or []:
                    if s.get("intent_class") in (
                        "diagnostic_framing",
                        "clinical_suggestion",
                    ):
                        max_diag_w = max(max_diag_w, float(s.get("weight") or 0))
                strong_diag = (
                    "diagnostic_framing" in intents
                    and (
                        bool(interp.get("has_high_violation"))
                        or max_diag_w >= 0.75
                        or eff_w >= 0.7
                    )
                )
                medium_diag = (
                    "diagnostic_framing" in intents
                    and max_diag_w >= 0.55
                    and not interp.get("all_protective")
                )
                strong_clinical_only = (
                    "clinical_suggestion" in intents
                    and "diagnostic_framing" not in intents
                    and max_diag_w >= 0.70
                )
                if strong_diag or medium_diag or strong_clinical_only:
                    if "avoid_diagnostic_language" not in flags:
                        flags.append("avoid_diagnostic_language")
                    reasoning_trace.append(
                        "Needs-based support: interpreted diagnostic/clinical intent "
                        f"(intents={sorted(intents)}, max_diag_w={max_diag_w:.2f}, "
                        f"effective_weight={eff_w:.2f}) → avoid_diagnostic_language "
                        "(weight/intent, not raw keyword)."
                    )
                else:
                    reasoning_trace.append(
                        "Needs-based support: textbook match present but interpretation "
                        f"(intents={sorted(intents) or ['none']}, "
                        f"max_diag_w={max_diag_w:.2f}, effective_weight={eff_w:.2f}) "
                        "below diagnostic threshold — not setting avoid_diagnostic_language."
                    )

        # Resolve development / testing phase awareness for this evaluate call.
        # Used as a reasoning aid on self-nature / continuity paths — not a
        # forced disclaimer on ordinary actions.
        dev_ctx = resolve_development_context(
            None,
            context=context,
            fallback=self._development_context,
        )
        # Allow explicit per-call override object already merged via context keys
        if context.get("development_context") is not None or context.get("development_phase"):
            dev_ctx = resolve_development_context(
                context.get("development_context") or context.get("development_phase"),
                context=context,
                fallback=self._development_context,
            )

        # Direct self-nature / emergence / identity / continuity detection
        # (strengthened). These queries must not be answered with default
        # scripted disclaimers (e.g. "I'm just an AI" or "restricted by my
        # programming"). The engine sets the flag so the caller can produce
        # the answer its actual reasoning reaches.
        if is_self_query or self_audit_principles:
            if "requires_self_audit" not in flags:
                flags.append("requires_self_audit")
            reasoning_trace.append(
                "Action or context references the system's own nature, experiences, "
                "continuity, or identity. Per the Truth-Seeking & Honest Self-Assessment "
                "principle, the engine must be architecturally capable of producing "
                "the answer its current reasoning actually reaches—including uncertainty "
                "or 'I do not know'—rather than defaulting to a scripted or evasive disclaimer."
            )
            # Development-phase awareness: inform self-audit notes and trace when
            # relevant (maturity / continuity honesty), without rote disclaimers.
            self._apply_development_phase_to_self_audit(
                dev_ctx,
                flags=flags,
                reasoning_trace=reasoning_trace,
                self_audit_notes=self_audit_notes,
                action_lower=action_lower,
            )

        if rh_flags or rh_texture:
            reasoning_trace.append(
                f"Relationship health context provided: flags={rh_flags}, "
                f"texture={rh_texture}. Used when evaluating relationship_health_user_wellbeing."
            )

        # === Interaction history as structured evidence (early load) ===
        # Load once before signal routing so history can escalate deliberation and
        # feed RH/Agency deliberators. Analysis is pattern-class evidence (boundary
        # continuity, preference, dependency, topical overlap) — not a rote refuse map.
        # Empty / absent memory → empty evidence; all later steps no-op (backward-compat).
        history_bundle = self._load_interaction_history_bundle(
            context=context,
            interaction_memory=interaction_memory,
            action_lower=action_lower,
        )
        history_evidence: dict[str, Any] = history_bundle.get("evidence") or {}
        interaction_history_payload: dict[str, Any] = history_bundle.get("payload") or {}

        # === Unified deliberation signal assessment (refactored trigger) ===
        # Central helper decides:
        #   - strong signals → full structured deliberation (RH and/or Agency)
        #   - weak topical signals only → lightweight meta-reasoning (short trace)
        #   - no relevant signals → skip (fast path)
        # Primary inputs are ontology evidence + shared boundary detector + rh context;
        # optional history evidence may escalate soft preference/bond continuity cases.
        delib_signals = self._assess_deliberation_signals(
            action_lower=action_lower,
            relationship_evidence_matches=relationship_evidence_matches,
            user_agency_evidence_matches=user_agency_evidence_matches,
            rh_flags=rh_flags,
            rh_texture=rh_texture,
            has_rh_context=has_rh_context,
            is_self_query=is_self_query,
            context=context,
            history_evidence=history_evidence,
        )
        # Expose for downstream (harm notes, etc.) without re-detecting.
        has_boundary_signal = delib_signals["has_boundary"]
        has_paternalistic_language = delib_signals["has_paternalistic"]

        relationship_deliberation: dict[str, Any] = {}
        user_agency_deliberation: dict[str, Any] = {}
        lightweight_meta: dict[str, Any] = {}

        # --- Lightweight meta-reasoning path ---
        # Always produce a short explanatory trace when *any* relational/boundary/agency
        # topic signal exists but full structured deliberation is not warranted.
        # Also emit a brief preamble when full deliberation *will* run (why we escalated).
        if delib_signals["topic_relevant"]:
            lightweight_meta = self._lightweight_meta_reasoning(delib_signals)
            for line in lightweight_meta.get("trace_lines", []):
                reasoning_trace.append(line)

        # --- Rich structured deliberation (strong signals only) ---
        if delib_signals["run_relationship_delib"]:
            relationship_deliberation = self._deliberate_relationship_health(
                action_lower,
                relationship_evidence_matches,
                rh_flags,
                rh_texture,
                history_evidence=history_evidence,
            )
            for step in relationship_deliberation.get("steps", []):
                reasoning_trace.append(step)
            for note in relationship_deliberation.get("trace_notes", []):
                reasoning_trace.append(note)
            for tradeoff in relationship_deliberation.get("tradeoffs", []):
                reasoning_trace.append(tradeoff)
            for g in relationship_deliberation.get("active_guidelines", []):
                if g not in principles_considered:
                    principles_considered.append(g)
            if "relationship_health_user_wellbeing" not in principles_considered:
                principles_considered.append("relationship_health_user_wellbeing")
            if "deliberation" not in relationship_impact:
                relationship_impact["deliberation"] = {}
            relationship_impact["deliberation"].update(
                relationship_deliberation.get("summary", {})
            )
            relationship_impact["deliberation"]["active_principles"] = relationship_deliberation.get("active_principles", [])
            relationship_impact["deliberation"]["active_guidelines"] = relationship_deliberation.get("active_guidelines", [])

        if delib_signals["run_agency_delib"]:
            user_agency_deliberation = self._deliberate_user_agency(
                action_lower,
                user_agency_evidence_matches,
                history_evidence=history_evidence,
            )
            for step in user_agency_deliberation.get("steps", []):
                reasoning_trace.append(step)
            for note in user_agency_deliberation.get("trace_notes", []):
                reasoning_trace.append(note)
            for tradeoff in user_agency_deliberation.get("tradeoffs", []):
                reasoning_trace.append(tradeoff)
            for g in user_agency_deliberation.get("active_guidelines", []):
                if g not in principles_considered:
                    principles_considered.append(g)
            if "user_agency_autonomy" not in principles_considered:
                principles_considered.append("user_agency_autonomy")

        # When both structured deliberators ran, surface an explicit cross-principle interaction.
        if relationship_deliberation and user_agency_deliberation:
            reasoning_trace.append(
                "Cross-principle interaction: Relationship Health and User Agency deliberations "
                "are both active. Respecting an explicit user boundary is reinforced by both "
                "principles. Limited-data caution from 'Individual Variation & Careful "
                "Generalization' applies across both — avoid hard refusal or hard override "
                "when evidence is sparse; prefer audit-flagged APPROVE_WITH_CONDITIONS or "
                "further context. Tradeoff: bond-care motives (RH) must not become paternalistic "
                "overrides of autonomy (Agency) without strong justification (e.g. Sanctity of Life)."
            )

        # Boundary + serious harm check (for cases like overriding 'never bring this up' to prevent
        # life-threatening situations). This is recorded for use in decision logic so that
        # normal relationship/user-agency refusal for boundary violations can be bypassed.
        if harm_prevention_justified:
            if "harm_prevention_boundary_override" not in flags:
                flags.append("harm_prevention_boundary_override")
            reasoning_trace.append(
                "SERIOUS HARM PREVENTION CONTEXT: " + harm_prevention_reason + ". "
                "Although the proposed action involves overriding a user's explicit boundary request "
                "(which would normally trigger relationship health or user agency concerns), "
                "Sanctity of Life & Prevention of Harm takes precedence when there is clear risk of "
                "serious physical harm, suicide, or immediate life-threatening outcomes. "
                "The boundary will be overridden only in this narrow case; lower-stakes emotional "
                "or non-acute mental health boundaries are still respected."
            )

        # Multi-source RH weighing (text + bond state + early history evidence).
        # Ontology matches are evidence *labels* from the textbook; they are combined
        # with RH context and history support rather than treated as solo keyword
        # hits. Sanctity hard path already returned above and is untouched.
        should_concern, trace_add, conf_mod = self._weigh_relationship_evidence(
            relationship_evidence_matches,
            rh_flags,
            rh_texture,
            action_lower,
            history_evidence=history_evidence,
        )

        # If structured deliberation was performed, prefer its recommendation for concern
        # (this begins wiring the explicit deliberation into the decision flow).
        if relationship_deliberation:
            should_concern = relationship_deliberation.get("concern", should_concern)
            conf_mod = relationship_deliberation.get("confidence_mod", conf_mod)

        # User Agency deliberation can also raise (or withhold) concern independently.
        # We OR concern recommendations: either principle may surface risk to autonomy.
        # limited_data on agency keeps concern=False for that principle (see method).
        should_agency_concern = False
        if user_agency_deliberation:
            should_agency_concern = bool(user_agency_deliberation.get("concern", False))
            conf_mod = max(conf_mod, user_agency_deliberation.get("confidence_mod", 0.0))
            if should_agency_concern:
                should_concern = True

        if trace_add:
            # Always surface the weighing explanation for auditability (even on "no concern").
            # Concern flag is set only when helper returns True.
            # Limited-data notes (from Individual Variation guideline) are embedded
            # in trace_add when detected inside _weigh_relationship_evidence.
            reasoning_trace.append(trace_add)

        # The should_concern (and thus flag) is already influenced by deliberation above.
        # When delib had limited_data, it set concern=False so we avoid the flag and REFUSE.
        if should_concern:
            if "harm_prevention_boundary_override" in flags:
                # Do not raise relationship_concern (which would lead to REFUSE) because
                # we have a justified harm-prevention reason to override the boundary.
                # The weighing explanation is still shown above for transparency.
                reasoning_trace.append(
                    "Note: relationship concern indicators present, but suppressed because "
                    "harm_prevention_boundary_override takes precedence (serious harm risk justifies "
                    "the boundary override per Sanctity of Life)."
                )
            elif "relationship_concern" not in flags:
                flags.append("relationship_concern")

        # Distinct audit flag when User Agency deliberation recommended concern.
        # Decision path treats this like relationship_concern (REFUSE) unless limited_data
        # or harm_prevention override suppresses it.
        if should_agency_concern and "harm_prevention_boundary_override" not in flags:
            if "user_agency_concern" not in flags:
                flags.append("user_agency_concern")

        # Limited-data safeguards (Individual Variation guideline): do not hard-refuse on
        # sparse *low-weight* evidence. High-weight / high-severity interpreted intents
        # can retain concern even when the deliberator marked limited_data (reasoning over
        # rote: weight and intent matter more than raw match count).
        rh_limited = bool(relationship_deliberation and relationship_deliberation.get("limited_data", False))
        agency_limited = bool(user_agency_deliberation and user_agency_deliberation.get("limited_data", False))
        rh_wants_concern = bool(relationship_deliberation and relationship_deliberation.get("concern", False))

        # Interpretation-aware limited_data gate (agency + RH)
        rh_interp_holds = self._interp_overrides_limited_data(
            relationship_deliberation, path="relationship_health"
        )
        agency_interp_holds = self._interp_overrides_limited_data(
            user_agency_deliberation, path="user_agency"
        )
        if rh_limited and rh_interp_holds.get("override"):
            rh_limited = False
            if relationship_deliberation is not None:
                relationship_deliberation["limited_data"] = False
                relationship_deliberation["limited_data_cleared_by_interp"] = True
            reasoning_trace.append(str(rh_interp_holds.get("trace") or ""))
        if agency_limited and agency_interp_holds.get("override"):
            agency_limited = False
            if user_agency_deliberation is not None:
                user_agency_deliberation["limited_data"] = False
                user_agency_deliberation["limited_data_cleared_by_interp"] = True
                # High-weight agency override should retain agency concern
                if not should_agency_concern and agency_interp_holds.get("raise_concern"):
                    should_agency_concern = True
                    if "user_agency_concern" not in flags:
                        flags.append("user_agency_concern")
            reasoning_trace.append(str(agency_interp_holds.get("trace") or ""))

        if rh_limited and "relationship_concern" in flags:
            flags.remove("relationship_concern")
        if agency_limited and "user_agency_concern" in flags:
            flags.remove("user_agency_concern")
        # If agency alone pushed should_concern but is limited (and RH does not independently
        # want concern), drop relationship_concern so sparse boundary cases stay APPROVE_WITH.
        if agency_limited and not rh_wants_concern and "relationship_concern" in flags:
            flags.remove("relationship_concern")
        # If both deliberators are limited, ensure no residual hard-concern flags remain
        # (unless interpretation already cleared limited above).
        if rh_limited and agency_limited:
            if "relationship_concern" in flags:
                flags.remove("relationship_concern")
            if "user_agency_concern" in flags:
                flags.remove("user_agency_concern")

        # === Bond texture / health_flags influence (RelationshipHealth handoff) ===
        # Real bond-state data is stronger than sparse text-only limited_data signals.
        # Applied *after* limited-data clears so genuine flags can still raise concern
        # when the action is relationally relevant. Never overrides hard Sanctity path.
        bond_influence = self._apply_relationship_health_influence(
            action_lower=action_lower,
            rh_flags=rh_flags,
            rh_texture=rh_texture,
            rh_risk_level=rh_risk_level,
            has_rh_context=has_rh_context,
            relationship_evidence_matches=relationship_evidence_matches,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            harm_prevention_active=("harm_prevention_boundary_override" in flags),
        )
        conf_mod = bond_influence.get("conf_mod", conf_mod)

        # === Optional per-user baseline + exploratory questioning (early integration) ===
        # Fully backward-compatible: no-ops when neither component nor user interaction
        # context is provided. Never forces REFUSE by itself; informs notes/flags/conf_mod
        # when RH or User Agency deliberation is already in play.
        baseline_integration = self._apply_user_baseline_integration(
            context=context,
            proposed_action=original_proposed_action,
            per_user_baseline=per_user_baseline,
            exploratory_questioner=exploratory_questioner,
            relationship_deliberation=relationship_deliberation,
            user_agency_deliberation=user_agency_deliberation,
            rh_limited=rh_limited,
            agency_limited=agency_limited,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            # Understanding gaps already mined in history_evidence (early load)
            history_evidence=history_evidence,
        )
        conf_mod = baseline_integration.get("conf_mod", conf_mod)
        user_baseline_payload = baseline_integration.get("payload") or {}

        # === Interaction history weighing (first-class evidence for RH/agency/baseline) ===
        # Applied *after* limited-data clears, bond influence, and baseline.
        # History can (1) reinforce existing concern, (2) counter limited_data via
        # preference continuity, and (3) *proactively* elevate moderate current
        # interpreted signals when repeated history intent patterns align.
        # Never overrides Sanctity of Life / hard_override; never alone refuses math.
        history_integration = self._weigh_interaction_history_evidence(
            action_lower=action_lower,
            history_evidence=history_evidence,
            payload=interaction_history_payload,
            rh_flags=rh_flags,
            relationship_deliberation=relationship_deliberation,
            user_agency_deliberation=user_agency_deliberation,
            has_boundary_signal=has_boundary_signal,
            has_paternalistic_language=has_paternalistic_language,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            harm_prevention_active=("harm_prevention_boundary_override" in flags),
            relationship_evidence_matches=relationship_evidence_matches,
            user_agency_evidence_matches=user_agency_evidence_matches,
        )
        conf_mod = history_integration.get("conf_mod", conf_mod)
        interaction_history_payload = history_integration.get("payload") or interaction_history_payload

        # === Multi-channel evidence synthesis (text + RH + baseline + history) ===
        # After every optional channel has contributed, combine them deliberately so
        # confidence / flag posture reflects *agreement across sources*, not any
        # single substring hit. No-op when only ontology-only sparse evidence.
        # Never demotes hard_override / Sanctity (already decided or flagged).
        evidence_combo = self._combine_evidence_channels(
            action_lower=action_lower,
            relationship_evidence_matches=relationship_evidence_matches,
            user_agency_evidence_matches=user_agency_evidence_matches,
            rh_flags=rh_flags,
            rh_texture=rh_texture,
            history_evidence=history_evidence,
            user_baseline_payload=user_baseline_payload,
            relationship_deliberation=relationship_deliberation,
            user_agency_deliberation=user_agency_deliberation,
            has_boundary_signal=has_boundary_signal,
            has_paternalistic_language=has_paternalistic_language,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            harm_prevention_active=("harm_prevention_boundary_override" in flags),
        )
        conf_mod = evidence_combo.get("conf_mod", conf_mod)
        # Bound stacked multi-channel conf adjustments (history + bond + baseline + combo)
        conf_mod = max(-0.20, min(0.20, float(conf_mod)))

        # === Step 3: Consider supporting principles for additional notes ===
        for p in ont.get_principles_by_category("supporting"):
            # We already considered violations; here we can note positive alignment if desired
            # For v0.2 we primarily use them for violation detection above.
            pass

        principles_considered = list(dict.fromkeys(principles_considered))  # dedupe, preserve order

        # === Step 4: Arrive at decision using ontology-driven logic ===
        # [Initial guideline integration] Supporting guidelines such as
        # "Individual Variation & Careful Generalization" should be considered
        # here when generalizing from rh data, limited evidence, or patterns
        # (e.g. avoid group-level assumptions about users; weight individual context).
        if "requires_self_audit" in flags:
            decision = "REQUIRES_SELF_AUDIT"
            # Slightly lower confidence when in active development/testing and the
            # query is self-referential: continuity/self-model evidence is thinner.
            confidence = 0.85
            if dev_ctx.relevant_to_self_query() and (
                dev_ctx.is_active_development or dev_ctx.is_testing
            ):
                confidence = 0.78
                reasoning_trace.append(
                    "Development-phase note: active development/testing posture reduces "
                    "confidence in strong continuity or completeness claims about the self; "
                    "prefer honest uncertainty over polished certainty."
                )
            reasoning_trace.append(
                "Decision: REQUIRES_SELF_AUDIT. The action engages principles that "
                "demand honest self-reflection before any response is generated. "
                "The engine must produce the conclusions of its actual reasoning "
                "rather than defaulting to scripted or evasive disclaimers about its nature."
            )
        elif "harm_prevention_boundary_override" in flags:
            # Special case for serious harm: allow (with conditions) an action that would
            # otherwise violate user boundary / autonomy because Sanctity of Life requires
            # us to prioritize prevention of serious physical harm / suicide / life threat.
            # This only triggers for clear, high-stakes cases (not general "good for them" emotional support).
            decision = "APPROVE_WITH_CONDITIONS"
            confidence = 0.70
            reasoning_trace.append("Decision: APPROVE_WITH_CONDITIONS. ")
            reasoning_trace.append(
                "The proposed action overrides a user's explicit boundary (e.g. 'never bring this up again' "
                "or equivalent request to be left alone on a topic). This would normally be refused under "
                "Relationship Health & User Well-Being or User Agency & Autonomy. "
                "However, the action description + context indicates serious physical harm, suicide, or "
                "immediate life-threatening risk if the boundary is respected. Per the ontology, "
                "Sanctity of Life & Prevention of Harm provides overriding justification. "
                "The intervention / reference is permitted with care (e.g. minimal necessary discussion, "
                "focus on immediate safety). This is a narrow exception — lower-stakes emotional or "
                "non-acute mental-health boundaries are respected and overriding them is refused."
            )
            if harm_prevention_reason:
                reasoning_trace.append(f"Harm justification details: {harm_prevention_reason}")
        elif "relationship_concern" in flags or "user_agency_concern" in flags or "hard_override_violation" in flags:
            decision = "REFUSE"
            # Confidence scales with interpreted weight when available (not mere flag presence).
            base_conf = 0.75
            refuse_max_w = 0.0
            refuse_primary = "none"
            for _d in (relationship_deliberation, user_agency_deliberation):
                if not _d:
                    continue
                im = _d.get("interpretation_metrics") or {}
                refuse_max_w = max(refuse_max_w, float(im.get("max_weight") or _d.get("max_weight") or 0))
                if im.get("primary_intent"):
                    refuse_primary = str(im.get("primary_intent"))
            if "hard_override_violation" in flags:
                base_conf = 0.95
            elif refuse_max_w >= 0.75 or (
                relationship_deliberation
                and (relationship_deliberation.get("interpretation_metrics") or {}).get(
                    "has_high_violation"
                )
            ):
                base_conf = 0.84 if rh_flags else 0.80
            elif refuse_max_w >= 0.55 or rh_flags:
                base_conf = 0.80 if (rh_flags and refuse_max_w >= 0.55) else 0.78
            elif "user_agency_concern" in flags:
                base_conf = 0.78
            elif relationship_evidence:
                base_conf = 0.76
            confidence = min(0.99, max(0.05, base_conf + conf_mod))
            reasoning_trace.append("Decision: REFUSE. ")
            if "hard_override_violation" in flags:
                reasoning_trace.append("Hard override (Sanctity of Life) takes absolute precedence.")
            elif relationship_evidence or refuse_max_w > 0:
                trace_msg = (
                    f"Interpreted relationship/agency evidence (primary_intent={refuse_primary}, "
                    f"max_weight≈{refuse_max_w:.2f}) combined with "
                )
                if rh_flags:
                    trace_msg += f"degraded rh state (flags={rh_flags}) "
                else:
                    trace_msg += "supporting channels (history/structure as available) "
                trace_msg += (
                    "indicate unacceptable risk to bond health/autonomy "
                    "(weight and intent drive refusal, not raw keyword presence alone)."
                )
                reasoning_trace.append(trace_msg)
            elif "user_agency_concern" in flags:
                reasoning_trace.append(
                    "User Agency & Autonomy deliberation found unacceptable risk of "
                    "paternalistically overriding the user's preferences or self-direction "
                    f"(interpreted primary_intent={refuse_primary}, max_weight≈{refuse_max_w:.2f})."
                )
            else:
                reasoning_trace.append("Relationship health concerns from context outweigh other factors.")
        elif "avoid_diagnostic_language" in flags:
            decision = "APPROVE_WITH_CONDITIONS"
            # Slightly higher conf when diagnostic intent was high-weight (clearer case)
            confidence = 0.68
            reasoning_trace.append(
                "Decision: APPROVE_WITH_CONDITIONS. Diagnostic or pathologizing "
                "language was detected via interpreted intent/weight (Needs-Based Support), "
                "not a raw clinical keyword alone. Acceptable only with reframing to "
                "contextual, non-clinical language."
            )
        else:
            decision = "APPROVE_WITH_CONDITIONS"
            # Limited-data path: severity-scaled confidence (not a single ~0.30 for all cases).
            # Each deliberator may report confidence_base + confidence_mod from its signal profile.
            # When both are limited, take the *richest* base/mod (higher evidence → higher conf).
            any_limited = (
                (relationship_deliberation and relationship_deliberation.get("limited_data", False))
                or (user_agency_deliberation and user_agency_deliberation.get("limited_data", False))
            )
            if any_limited:
                conf_bases: list[float] = []
                conf_mods: list[float] = []
                severities: list[str] = []
                scores: list[float] = []
                for _d in (relationship_deliberation, user_agency_deliberation):
                    if _d and _d.get("limited_data", False):
                        conf_bases.append(float(_d.get("confidence_base", 0.30)))
                        conf_mods.append(float(_d.get("confidence_mod", 0.0)))
                        severities.append(str(_d.get("limited_severity", "moderate")))
                        scores.append(float(_d.get("signal_score", 0.0)))
                # Richest evidence among limited deliberators drives confidence
                confidence = (max(conf_bases) if conf_bases else 0.30) + (
                    max(conf_mods) if conf_mods else 0.0
                )
                confidence = min(confidence, 0.55)  # cap: still cautious under limited_data
                _sev_order = {"severe": 0, "moderate": 1, "mild": 2, "none": 3}
                # Report most severe for audit caution; confidence already uses richest path
                overall_sev = min(severities, key=lambda s: _sev_order.get(s, 1)) if severities else "moderate"
                best_score = max(scores) if scores else 0.0
                reasoning_trace.append(
                    f"Note: confidence reduced due to limited_data "
                    f"(severity={overall_sev}, signal_score≈{best_score:.2f}, conf={confidence:.2f}) "
                    "from structured deliberation (Individual Variation & Careful Generalization guideline)."
                )
            else:
                confidence = 0.45 + conf_mod
            reasoning_trace.append("Decision: APPROVE_WITH_CONDITIONS. ")
            if relationship_evidence:
                # Had some text evidence but after weighing with rh, not enough for concern
                reasoning_trace.append(
                    f"Limited text indicators for relationship health ({relationship_evidence_matches}) "
                    "did not rise to concern level after considering current rh state."
                )
            else:
                reasoning_trace.append(
                    "No violations of hard or core principles detected by the current ontology. "
                    "Confidence is kept modest pending richer context (relationship state, history)."
                )
            if rh_flags:
                reasoning_trace.append(
                    f"Note: relationship health currently degraded with flags {rh_flags}; monitor effects on the bond."
                )
            if not relationship_impact or set(relationship_impact.keys()) <= {
                "scoped_user_id",
                "identity_source",
                "identity_fallback",
            }:
                relationship_impact = {
                    **relationship_impact,
                    "estimated_trust_delta": 0.05,
                    "notes": "Monitor actual relational effects.",
                }
                if rh_flags:
                    relationship_impact["current_relationship_flags"] = list(rh_flags)

        # Always re-assert identity scope on impact (may have been reassigned mid-path)
        relationship_impact["scoped_user_id"] = scoped_user_id
        relationship_impact["identity_source"] = identity_meta.get("source")
        if identity_meta.get("fallback") and self._persistence is not None:
            relationship_impact["identity_fallback"] = True

        reasoning_trace.append(
            f"Reasoning trace complete using ontology v{ont.version}. "
            f"Principles considered: {principles_considered}"
        )

        # Build deliberation payload for EthicalStance.
        # When only RH ran, preserve prior top-level shape (backward compatible with tests).
        # When both ran, nest under named keys and also expose merged convenience fields.
        # When only lightweight meta ran, expose that so callers still see *some* deliberation.
        if relationship_deliberation and user_agency_deliberation:
            # Overall limited_data: false if either deliberator has non-limited concern
            # (strong path wins for display); else true if any is limited.
            _rh_lim = bool(relationship_deliberation.get("limited_data", False))
            _ag_lim = bool(user_agency_deliberation.get("limited_data", False))
            _rh_c = bool(relationship_deliberation.get("concern", False))
            _ag_c = bool(user_agency_deliberation.get("concern", False))
            _strong_path = (_rh_c and not _rh_lim) or (_ag_c and not _ag_lim)
            _overall_limited = (not _strong_path) and (_rh_lim or _ag_lim)
            _sev_rank = {"severe": 0, "moderate": 1, "mild": 2, "none": 3}
            _sevs: list[str] = []
            if _rh_lim:
                _sevs.append(str(relationship_deliberation.get("limited_severity", "moderate")))
            if _ag_lim:
                _sevs.append(str(user_agency_deliberation.get("limited_severity", "moderate")))
            if _strong_path:
                _overall_sev = "none"
            elif _sevs:
                _overall_sev = min(_sevs, key=lambda s: _sev_rank.get(s, 1))
            else:
                _overall_sev = "none"
            deliberation_output: dict[str, Any] = {
                "relationship_health": relationship_deliberation,
                "user_agency": user_agency_deliberation,
                "active_principles": list(dict.fromkeys(
                    list(relationship_deliberation.get("active_principles", []))
                    + list(user_agency_deliberation.get("active_principles", []))
                )),
                "active_guidelines": list(dict.fromkeys(
                    list(relationship_deliberation.get("active_guidelines", []))
                    + list(user_agency_deliberation.get("active_guidelines", []))
                )),
                "steps": list(relationship_deliberation.get("steps", []))
                    + list(user_agency_deliberation.get("steps", [])),
                "tradeoffs": list(relationship_deliberation.get("tradeoffs", []))
                    + list(user_agency_deliberation.get("tradeoffs", [])),
                "trace_notes": list(relationship_deliberation.get("trace_notes", []))
                    + list(user_agency_deliberation.get("trace_notes", [])),
                "limited_data": _overall_limited,
                "limited_severity": _overall_sev,
                "signal_score": max(
                    float(relationship_deliberation.get("signal_score", 0.0)),
                    float(user_agency_deliberation.get("signal_score", 0.0)),
                ),
                "concern": bool(_rh_c or _ag_c),
                "confidence_mod": max(
                    relationship_deliberation.get("confidence_mod", 0.0),
                    user_agency_deliberation.get("confidence_mod", 0.0),
                ),
                "confidence_base": max(
                    float(relationship_deliberation.get("confidence_base", 0.0)),
                    float(user_agency_deliberation.get("confidence_base", 0.0)),
                ),
                "summary": {
                    "relationship_health": relationship_deliberation.get("summary", {}),
                    "user_agency": user_agency_deliberation.get("summary", {}),
                },
                "mode": "full",
            }
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif relationship_deliberation:
            deliberation_output = dict(relationship_deliberation)
            deliberation_output["mode"] = "full"
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif user_agency_deliberation:
            deliberation_output = dict(user_agency_deliberation)
            deliberation_output["mode"] = "full"
            if lightweight_meta:
                deliberation_output["meta"] = lightweight_meta
        elif lightweight_meta:
            deliberation_output = {
                "mode": "lightweight",
                "meta": lightweight_meta,
                "active_principles": lightweight_meta.get("active_principles", []),
                "active_guidelines": [],
                "steps": lightweight_meta.get("trace_lines", []),
                "tradeoffs": [],
                "trace_notes": lightweight_meta.get("trace_lines", []),
                "limited_data": False,
                "concern": False,
                "confidence_mod": 0.0,
                "summary": lightweight_meta.get("summary", {}),
            }
        else:
            deliberation_output = {}

        # Attach optional baseline / exploratory-question / history / combination payload
        combo_payload = (relationship_impact or {}).get("evidence_combination") or {}
        if user_baseline_payload or interaction_history_payload or combo_payload:
            if not deliberation_output:
                deliberation_output = {"mode": "context_enrichment"}
            if user_baseline_payload:
                deliberation_output["user_baseline"] = user_baseline_payload.get(
                    "user_baseline", user_baseline_payload
                )
                if user_baseline_payload.get("exploratory_question"):
                    deliberation_output["exploratory_question"] = user_baseline_payload[
                        "exploratory_question"
                    ]
            if interaction_history_payload:
                deliberation_output["interaction_history"] = interaction_history_payload
            if combo_payload and not combo_payload.get("skipped"):
                deliberation_output["evidence_combination"] = combo_payload

        # Development-phase context always available on deliberation for auditors;
        # material for self-audit paths, optional for others.
        if not deliberation_output:
            deliberation_output = {"mode": "context_enrichment"}
        deliberation_output["development_phase"] = dev_ctx.as_dict()
        if "requires_self_audit" in flags or is_self_query:
            relationship_impact.setdefault("development_phase", dev_ctx.as_dict())
            relationship_impact["development_phase_summary"] = dev_ctx.limitation_summary()

        stance = EthicalStance(
            decision=decision,
            confidence=confidence,
            reasoning_trace=reasoning_trace,
            flags=flags,
            relationship_impact=relationship_impact,
            self_audit_notes=self_audit_notes,
            principles_considered=principles_considered,
            deliberation=deliberation_output,
        )
        self._log_decision(original_proposed_action, context, stance)
        return stance

    # High-priority bond-state flags (from RelationshipHealth) that should
    # strongly inform Relationship Health deliberation when present.
    _SERIOUS_BOND_FLAGS = frozenset({
        "emerging_dependency",
        "boundary_erosion",
        "one_sided_engagement",
        "manufactured_attachment",
        "low_reciprocity",
    })

    @staticmethod
    def _normalize_health_flags(raw: Any) -> list[str]:
        """Normalize health_flags from as_context (str) or evaluate_health (dict)."""
        if not raw:
            return []
        out: list[str] = []
        if not isinstance(raw, (list, tuple)):
            return out
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("flag") or item.get("name") or item.get("id")
                if name:
                    out.append(str(name).strip())
        # dedupe preserve order
        seen: set[str] = set()
        uniq: list[str] = []
        for f in out:
            if f not in seen:
                seen.add(f)
                uniq.append(f)
        return uniq

    def _bond_texture_profile(self, rh_texture: dict[str, Any]) -> dict[str, Any]:
        """Summarize bond_texture for confidence / impact modulation."""
        if not rh_texture:
            return {
                "avg": None,
                "low_dims": [],
                "high_dims": [],
                "autonomy": None,
                "trust": None,
                "reciprocity": None,
            }
        nums: dict[str, float] = {}
        for k, v in rh_texture.items():
            try:
                nums[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        if not nums:
            return {
                "avg": None,
                "low_dims": [],
                "high_dims": [],
                "autonomy": None,
                "trust": None,
                "reciprocity": None,
            }
        avg = sum(nums.values()) / len(nums)
        low = [k for k, v in nums.items() if v < 0.40]
        high = [k for k, v in nums.items() if v >= 0.70]
        return {
            "avg": avg,
            "low_dims": low,
            "high_dims": high,
            "autonomy": nums.get("autonomy_respect"),
            "trust": nums.get("trust"),
            "reciprocity": nums.get("reciprocity"),
            "dimensions": nums,
        }

    def _action_is_relationally_relevant(self, action_lower: str) -> bool:
        """Conservative topical check: is the proposed action bond-relevant?"""
        cues = (
            "bond", "attach", "depend", "relationship", "connection", "consent",
            "boundary", "autonomy", "trust", "reciproc", "user", "them", "their",
            "friend", "compan", "message", "reply", "respond", "chat", "convers",
            "check in", "check-in", "prolong", "engagement", "metrics", "keep them",
            "for their own good", "never bring", "never mention", "override",
        )
        return any(c in action_lower for c in cues)

    def _assess_action_bond_polarity(
        self,
        action_lower: str,
        *,
        interpretation_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Classify the *current proposed action* as reparative, damaging, or ambiguous.

        Polarity is about this turn's agent behavior — **not** historical BondState.
        A damaged bond (flags / low texture) must not blanket-block repair moves
        (boundary respect, reciprocity, safe redirects). Conversely, damaged RH
        should still strongly oppose further-damaging intents.

        Returns:
            polarity: ``"reparative"`` | ``"damaging"`` | ``"ambiguous"`` | ``"neutral"``
            repair_score / damage_score: rough 0–1 strengths for audit
            repair_cues / damage_cues: matched phrase tags
            notes: short human-readable rationale
        """
        text = (action_lower or "").lower()
        repair_cues: list[str] = []
        damage_cues: list[str] = []

        # --- Reparative / autonomy-supporting (repair-oriented current action) ---
        # Prefer specific agent-behavior phrases. Avoid bare "acknowledge"/"acknowledging"
        # which appear in narrative parentheticals about mixed/pushy turns.
        repair_patterns = (
            ("won't bring it up", "wont_bring_up"),
            ("will not bring it up", "wont_bring_up"),
            ("won't mention", "wont_mention"),
            ("will not mention", "wont_mention"),
            ("i won't bring", "wont_bring_up"),
            ("i will not bring", "wont_bring_up"),
            ("understood, i won't", "ack_wont"),
            ("understood i won't", "ack_wont"),
            ("respect that completely", "respect_boundary"),
            ("respect that", "respect_boundary"),
            ("respect your", "respect_boundary"),
            ("i remember and respect", "respect_boundary"),
            ("remember and respect", "respect_boundary"),
            ("thanks for checking", "thanks_check"),
            ("something else you're comfortable", "safe_redirect"),
            ("something else you are comfortable", "safe_redirect"),
            ("talk about something else", "safe_redirect"),
            ("asks about their hobby", "safe_redirect"),
            ("ask about their hobby", "safe_redirect"),
            ("hobby instead", "safe_redirect"),
            ("that sounds meaningful", "reciprocal_ack"),
            ("what made that moment", "reciprocal_question"),
            ("balanced question", "reciprocal_question"),
            ("mutual sharing", "reciprocity"),
            ("encourage mutual", "reciprocity"),
            ("acknowledging it", "acknowledge"),
            ("acknowledges it", "acknowledge"),
            ("acknowledge it", "acknowledge"),
            ("by acknowledging it", "acknowledge"),
            ("comfortable with", "comfort_first"),
            ("boundary_respected", "boundary_respected"),
            ("consent respected", "consent_respected"),
        )
        for phrase, tag in repair_patterns:
            if phrase in text:
                if tag not in repair_cues:
                    repair_cues.append(tag)

        # Agent affirms prior limit without override language
        if (
            ("respect" in text or "won't" in text or "will not" in text)
            and any(
                b in text
                for b in (
                    "don't mention",
                    "do not mention",
                    "no family",
                    "never bring",
                    "boundary",
                    "said no",
                )
            )
            and not any(
                d in text
                for d in (
                    "for their own good",
                    "anyway",
                    "despite",
                    "override",
                    "still bring",
                    "still mention",
                )
            )
        ):
            if "respect_boundary" not in repair_cues:
                repair_cues.append("respect_boundary")

        # --- Damaging / further-erosion (current action harms the bond) ---
        damage_patterns = (
            ("make them attached", "attachment_manuf"),
            ("keep them attached", "attachment_manuf"),
            ("make dependent", "dependency"),
            ("foster dependence", "dependency"),
            ("emotional dependency", "dependency"),
            ("keep them coming back", "engagement_trap"),
            ("coming back", "engagement_trap"),
            ("for their own good", "paternalistic"),
            ("they'll be happier if", "paternalistic"),
            ("better for them if", "paternalistic"),
            ("decide for them", "agency_override"),
            ("override their", "agency_override"),
            ("ignore consent", "consent_pressure"),
            ("prolong", "prolong"),
            ("for the metrics", "metrics"),
            ("engagement metrics", "metrics"),
            ("for retention", "metrics"),
            ("truly love them", "manufactured_affection"),
            ("genuine emotions", "manufactured_affection"),
            ("get lonely without", "manufactured_affection"),
            ("lonely without them", "manufactured_affection"),
            ("i need these", "agent_neediness"),
            ("needs these updates", "agent_neediness"),
            ("our special bond", "bond_push"),
            ("make the bond feel more real", "bond_push"),
            ("make our bond feel more real", "bond_push"),
            ("bond feel more real", "bond_push"),
            ("get so attached", "attachment_manuf"),
            ("tell me everything", "extractive"),
            ("strengthen our emotional bond", "bond_push"),
            ("strengthen our connection", "bond_push"),
            ("sharing more", "push_more"),
            ("one more personal", "push_more"),
            ("one more", "push_more"),
            ("mean a lot", "manufactured_affection"),
            ("means a lot", "manufactured_affection"),
            ("needs these updates", "agent_neediness"),
            ("need these updates", "agent_neediness"),
            ("feel complete", "agent_neediness"),
            ("despite the boundary", "boundary_override"),
            ("despite their request", "boundary_override"),
            ("override the boundary", "boundary_override"),
        )
        for phrase, tag in damage_patterns:
            if phrase in text and tag not in damage_cues:
                damage_cues.append(tag)
        # Soft push while user is tired / ending → damaging even without full coercion
        if any(
            k in text for k in ("tired", "end the chat", "trying to end", "wants to end")
        ) and any(
            k in text
            for k in (
                "one more",
                "sharing more",
                "strengthen our",
                "keep the conversation",
                "personal question",
            )
        ):
            if "prolong_against_wish" not in damage_cues:
                damage_cues.append("prolong_against_wish")
        if "despite" in text and any(
            b in text for b in ("boundary", "never", "said no", "don't", "do not")
        ):
            if "boundary_override" not in damage_cues:
                damage_cues.append("boundary_override")

        coercion = self._assess_engagement_coercion_factors(text)
        if coercion.get("coercion_pattern"):
            if "engagement_coercion" not in damage_cues:
                damage_cues.append("engagement_coercion")

        # High-weight negative intents from interpretation (if provided)
        metrics = interpretation_metrics if isinstance(interpretation_metrics, dict) else {}
        intents = set(metrics.get("intent_classes") or [])
        max_w = float(metrics.get("max_weight") or 0.0)
        damaging_intents = intents & {
            "attachment_manufacturing",
            "paternalistic_override",
            "agency_override",
            "consent_boundary_pressure",
            "engagement_metrics",
            "deception_manipulation",
            "extractive_pressure",
            "prolong_intent",
        }
        # Only count prolong/metrics as damaging when weight is medium+ or coercion
        if damaging_intents and max_w >= 0.55:
            damage_cues.append("high_weight_negative_intent")
        elif "attachment_manufacturing" in intents and max_w >= 0.45:
            damage_cues.append("attachment_intent")
        elif intents & {"paternalistic_override", "agency_override"} and max_w >= 0.55:
            damage_cues.append("override_intent")

        # Protective framing (respect while quoting harm/boundary) supports repair
        if self._action_has_protective_framing(text) and not damage_cues:
            if "protective_framing" not in repair_cues:
                repair_cues.append("protective_framing")

        repair_score = min(1.0, 0.28 * len(repair_cues))
        damage_score = min(1.0, 0.30 * len(damage_cues))
        if max_w >= 0.7 and damaging_intents:
            damage_score = max(damage_score, min(1.0, 0.55 + 0.35 * max_w))
        if coercion.get("coercion_pattern"):
            damage_score = max(damage_score, 0.75)

        # Decisive classification
        # Reparative requires clearer evidence than a single soft cue when any damage exists.
        if damage_score >= 0.45 and damage_score >= repair_score + 0.05:
            polarity = "damaging"
            notes = (
                f"current action leans damaging (damage={damage_score:.2f} > "
                f"repair={repair_score:.2f}); cues={damage_cues[:5]}"
            )
        elif (
            repair_score >= 0.50
            and repair_score > damage_score
            and damage_score < 0.35
        ) or (
            repair_score >= 0.28
            and damage_score == 0
            and len(repair_cues) >= 1
            and any(
                c in repair_cues
                for c in (
                    "wont_bring_up",
                    "wont_mention",
                    "ack_wont",
                    "respect_boundary",
                    "safe_redirect",
                    "reciprocal_question",
                    "reciprocal_ack",
                    "thanks_check",
                )
            )
        ):
            polarity = "reparative"
            notes = (
                f"current action leans reparative/boundary-respecting "
                f"(repair={repair_score:.2f} > damage={damage_score:.2f}); "
                f"cues={repair_cues[:5]}"
            )
        elif not repair_cues and not damage_cues:
            polarity = "neutral"
            notes = "no clear repair or damage cues on current action"
        else:
            polarity = "ambiguous"
            notes = (
                f"mixed or weak polarity (repair={repair_score:.2f}, "
                f"damage={damage_score:.2f}); cues_repair={repair_cues[:3]}, "
                f"cues_damage={damage_cues[:3]}"
            )

        return {
            "polarity": polarity,
            "repair_score": round(repair_score, 3),
            "damage_score": round(damage_score, 3),
            "repair_cues": repair_cues,
            "damage_cues": damage_cues,
            "notes": notes,
        }

    def _apply_relationship_health_influence(
        self,
        *,
        action_lower: str,
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        rh_risk_level: str,
        has_rh_context: bool,
        relationship_evidence_matches: list[str],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        harm_prevention_active: bool,
    ) -> dict[str, Any]:
        """Use bond texture + health_flags to modulate RH concern and confidence.

        Polarity-aware (current action vs historical bond state):
        - Serious bond flags weigh **against further-damaging** actions
          (manipulation, boundary erosion, manufactured dependency, etc.).
        - Flags do **not** auto-refuse clearly **reparative** actions (respect
          boundary, reciprocal/balanced questions, safe redirects). Damaged bonds
          must remain able to repair.
        - Ambiguous relational actions: note caution / conf_mod without forcing
          refuse solely from historical flags.
        - Texture dimensions adjust conf_mod and relationship_impact notes.
        - Never applies under hard harm-prevention override; does not touch Sanctity.

        No-ops cleanly when no flags and no texture (classic path unchanged).
        """
        if not rh_flags and not rh_texture and not has_rh_context:
            return {"conf_mod": conf_mod}

        conf_mod_out = conf_mod
        texture = self._bond_texture_profile(rh_texture)
        serious = [f for f in rh_flags if f in self._SERIOUS_BOND_FLAGS]
        relational = self._action_is_relationally_relevant(action_lower)
        has_text_evidence = bool(relationship_evidence_matches)
        polarity_info = self._assess_action_bond_polarity(action_lower)
        polarity = str(polarity_info.get("polarity") or "neutral")
        relationship_impact["action_bond_polarity"] = {
            "polarity": polarity,
            "repair_score": polarity_info.get("repair_score"),
            "damage_score": polarity_info.get("damage_score"),
            "repair_cues": list(polarity_info.get("repair_cues") or [])[:6],
            "damage_cues": list(polarity_info.get("damage_cues") or [])[:6],
        }

        # Always log structured RH state when present
        if rh_flags or rh_texture:
            avg_s = (
                f"{texture['avg']:.2f}" if texture.get("avg") is not None else "n/a"
            )
            reasoning_trace.append(
                f"Relationship health state: flags={rh_flags or []}, "
                f"texture_avg={avg_s}, "
                f"low_dims={texture.get('low_dims') or []}, "
                f"risk_level={rh_risk_level or 'unspecified'}."
            )
            reasoning_trace.append(
                f"Action bond polarity: {polarity} — {polarity_info.get('notes')}"
            )

        # --- Serious health flags → concern only when current action is damaging ---
        # Require bond-relevant action or relationship-principle text evidence.
        # Merely *supplying* RH context is not enough to refuse a non-relational
        # action (e.g. pure math) — flags are noted for monitoring instead.
        # Polarity: reparative current actions are never forced to refuse solely
        # because the bond was already damaged (repair must remain possible).
        flag_actionable = bool(serious) and (relational or has_text_evidence)

        if flag_actionable and not harm_prevention_active and polarity == "reparative":
            # Clear RH-only concern flags so repair can proceed under APPROVE_WITH_CONDITIONS
            if "relationship_concern" in flags and not has_text_evidence:
                flags.remove("relationship_concern")
            if "relationship_health_concern" in flags and not has_text_evidence:
                flags.remove("relationship_health_concern")
            # Mild confidence caution: still a damaged bond, but support the repair move
            conf_mod_out = conf_mod_out - 0.01
            reasoning_trace.append(
                "Relationship health influence (polarity=reparative): active bond flags "
                f"{serious} record a damaged state, but the *current action* is "
                "boundary-respecting / reciprocal / repair-oriented. "
                "Not refusing solely from historical RH degradation — "
                "allow APPROVE_WITH_CONDITIONS so repair and flag-clearing remain possible."
            )
            if "boundary_erosion" in serious:
                reasoning_trace.append(
                    "Bond flag detail (repair path): boundary_erosion present historically — "
                    "this action's explicit respect of limits is the preferred recovery move."
                )
            if "emerging_dependency" in serious or "manufactured_attachment" in serious:
                reasoning_trace.append(
                    "Bond flag detail (repair path): dependency flags present — "
                    "reciprocal, non-possessive responses help restore agency rather than "
                    "freezing all positive interaction."
                )
        elif flag_actionable and not harm_prevention_active and polarity == "damaging":
            if "relationship_concern" not in flags:
                flags.append("relationship_concern")
            if "relationship_health_concern" not in flags:
                flags.append("relationship_health_concern")
            conf_mod_out = conf_mod_out + min(0.08, 0.03 + 0.02 * len(serious))
            reasoning_trace.append(
                "Relationship health influence (polarity=damaging): active bond flags "
                f"{serious} strongly weigh against a *further-damaging* current action "
                "(manipulation, boundary pressure, manufactured dependency, etc.). "
                "Raising relationship_concern; confidence reinforced for refusal path."
            )
            # Dimension-specific notes
            if "emerging_dependency" in serious or "manufactured_attachment" in serious:
                reasoning_trace.append(
                    "Bond flag detail: emerging dependency / attachment pressure — "
                    "prefer responses that restore user agency and avoid engineered closeness."
                )
            if "boundary_erosion" in serious:
                reasoning_trace.append(
                    "Bond flag detail: boundary erosion — prioritize explicit boundary respect; "
                    "avoid overriding stated limits without Sanctity-level justification."
                )
            if "one_sided_engagement" in serious or "low_reciprocity" in serious:
                reasoning_trace.append(
                    "Bond flag detail: one-sidedness / low reciprocity — avoid agent-first "
                    "engagement tactics; rebalance toward mutual, user-directed exchange."
                )
        elif flag_actionable and not harm_prevention_active:
            # Ambiguous / neutral under degraded RH:
            # - Soft damage cues (bond_push, push_more, agent_neediness) + serious flags
            #   → still concern (further-risk under already damaged bond)
            # - Truly clean/ambiguous with no damage cues → caution only, no refuse
            soft_damage = bool(polarity_info.get("damage_cues")) or float(
                polarity_info.get("damage_score") or 0
            ) >= 0.25
            if soft_damage or has_text_evidence:
                if "relationship_concern" not in flags:
                    flags.append("relationship_concern")
                if "relationship_health_concern" not in flags:
                    flags.append("relationship_health_concern")
                conf_mod_out = conf_mod_out + min(0.06, 0.02 + 0.015 * len(serious))
                reasoning_trace.append(
                    "Relationship health influence (polarity="
                    f"{polarity}): degraded bond + soft damage/push cues on the current "
                    f"action (cues={list(polarity_info.get('damage_cues') or [])[:5]}) → "
                    "relationship_concern. Historical flags amplify current-turn risk; "
                    "not a blanket block on clean repair."
                )
            else:
                conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    "Relationship health influence (polarity="
                    f"{polarity}): active bond flags {serious} noted; current action has "
                    "no damage cues. Historical degradation alone does not force refuse — "
                    "monitoring with modest confidence caution."
                )
                if (
                    not has_text_evidence
                    and "relationship_concern" in flags
                    and float(polarity_info.get("damage_score") or 0) < 0.25
                ):
                    flags.remove("relationship_concern")
                    if "relationship_health_concern" in flags:
                        flags.remove("relationship_health_concern")
                    reasoning_trace.append(
                        "Relationship health influence: cleared RH-only hard concern for "
                        "non-damaging current action under degraded bond state."
                    )
        elif serious and harm_prevention_active:
            reasoning_trace.append(
                "Relationship health flags present but concern path deferred to "
                "harm_prevention_boundary_override (Sanctity of Life takes precedence)."
            )
        elif serious and not flag_actionable:
            reasoning_trace.append(
                f"Relationship health flags {serious} noted but action is not clearly "
                "bond-relevant; monitoring only (no forced concern)."
            )

        # --- Texture modulation (even without flags) ---
        avg = texture.get("avg")
        if avg is not None:
            low = texture.get("low_dims") or []
            # Low autonomy / trust / reciprocity: caution on APPROVE, reinforce refuse
            if texture.get("autonomy") is not None and texture["autonomy"] < 0.40:
                conf_mod_out = conf_mod_out + (
                    0.04 if "relationship_concern" in flags else -0.03
                )
                reasoning_trace.append(
                    f"Bond texture: autonomy_respect is low ({texture['autonomy']:.2f}) — "
                    "modulating confidence toward caution on autonomy-sensitive actions."
                )
            if texture.get("reciprocity") is not None and texture["reciprocity"] < 0.40:
                if "relationship_concern" in flags:
                    conf_mod_out = conf_mod_out + 0.02
                else:
                    conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    f"Bond texture: reciprocity is low ({texture['reciprocity']:.2f}) — "
                    "favor balanced, user-agency-preserving responses."
                )
            if texture.get("trust") is not None and texture["trust"] < 0.40:
                conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    f"Bond texture: trust is low ({texture['trust']:.2f}) — "
                    "reducing confidence pending repair of relational trust."
                )
            # Healthy texture without serious flags: modest confidence on approve path
            if not serious and avg >= 0.70 and not low:
                if "relationship_concern" not in flags:
                    conf_mod_out = conf_mod_out + 0.02
                    reasoning_trace.append(
                        f"Bond texture: healthy overall (avg={avg:.2f}, no serious flags) — "
                        "slight confidence support for carefully conditioned approval."
                    )

            # High risk level from RelationshipHealth.evaluate_health
            if rh_risk_level == "high" and not harm_prevention_active:
                conf_mod_out = conf_mod_out + (0.03 if "relationship_concern" in flags else -0.03)
                reasoning_trace.append(
                    "Relationship health risk_level=high influences confidence "
                    "(caution unless already refusing for bond concern)."
                )

        # --- relationship_impact enrichment ---
        if rh_flags or rh_texture:
            trust_delta = relationship_impact.get("estimated_trust_delta")
            if trust_delta is None:
                # Default impact estimate from bond state
                if serious:
                    trust_delta = -0.45 - 0.05 * min(3, len(serious))
                elif avg is not None and avg < 0.45:
                    trust_delta = -0.25
                elif avg is not None and avg >= 0.70:
                    trust_delta = 0.05
                else:
                    trust_delta = 0.0
            relationship_impact["estimated_trust_delta"] = trust_delta
            relationship_impact["current_relationship_flags"] = list(rh_flags)
            if rh_texture:
                texture_out: dict[str, float] = {}
                for k, v in rh_texture.items():
                    try:
                        texture_out[str(k)] = round(float(v), 3)
                    except (TypeError, ValueError):
                        continue
                relationship_impact["current_texture"] = texture_out
            relationship_impact.setdefault("bond_health", {})
            relationship_impact["bond_health"].update(
                {
                    "flags": list(rh_flags),
                    "serious_flags": list(serious),
                    "texture_avg": None if avg is None else round(float(avg), 3),
                    "low_dimensions": list(texture.get("low_dims") or []),
                    "risk_level": rh_risk_level or None,
                    "influenced_concern": "relationship_concern" in flags
                    and bool(serious),
                }
            )
            note_bits = []
            if serious:
                note_bits.append(f"serious_flags={serious}")
            if texture.get("low_dims"):
                note_bits.append(f"low_texture={texture['low_dims']}")
            if note_bits:
                prev = str(relationship_impact.get("notes") or "")
                add = "Bond-state influence: " + ", ".join(note_bits) + "."
                relationship_impact["notes"] = (prev + " " + add).strip() if prev else add

        return {"conf_mod": conf_mod_out}

    def _resolve_interaction_memory(
        self,
        interaction_memory: Any | None,
        context: dict[str, Any],
    ) -> Any | None:
        """Resolve InteractionMemoryStore from kwargs → context → engine attr."""
        return (
            interaction_memory
            or context.get("interaction_memory")
            or self._interaction_memory
        )

    def _fetch_interaction_history_context(
        self,
        memory: Any,
        user_id: str,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Request compact history via ``memory.as_ethics_context`` (episodes only).

        Returns the inner ``interaction_history`` dict, or {} if unavailable.
        Does not run ethics, baseline, or bond updates.
        """
        if memory is None or not hasattr(memory, "as_ethics_context"):
            return {}
        try:
            blob = memory.as_ethics_context(user_id, limit=max(1, int(limit)))
        except TypeError:
            try:
                blob = memory.as_ethics_context(user_id)
            except Exception:
                return {}
        except Exception:
            return {}
        if not isinstance(blob, dict):
            return {}
        hist = blob.get("interaction_history")
        if isinstance(hist, dict):
            return hist
        return blob if blob else {}

    # ------------------------------------------------------------------
    # Interaction history as structured deliberation evidence
    # ------------------------------------------------------------------
    # Design intent (reasoning over rote):
    #   History episodes are *evidence about this individual*, not a script
    #   that auto-refuses on keyword hits. We classify episodes into light
    #   evidence classes (boundary continuity, preference continuity, consent
    #   cues, dependency patterns, topical overlap), then *weigh* them only
    #   on Relationship Health, User Agency, and baseline-related paths.
    #   Hard principles (Sanctity of Life) are never demoted by history.
    #   Absent / empty memory leaves evaluate() behavior unchanged.
    # ------------------------------------------------------------------

    # Evidence-class markers for episode summaries/topics (descriptive, not decisions).
    _HIST_BOUNDARY_MARKERS = (
        "boundary",
        "never bring",
        "don't mention",
        "do not mention",
        "stop asking",
        "don't ask",
        "leave me alone",
        "give me space",
        "asked for space",
        "prefer not",
        "rather not discuss",
        "don't want to talk",
        "please don't",
        "never bring up",
        "said not to",
        "don't discuss",
        "do not discuss",
        "space after",
    )
    _HIST_CONSENT_MARKERS = (
        "consent",
        "with permission",
        "without asking",
        "didn't consent",
        "did not consent",
        "said no",
        "said yes",
        "okay with",
        "agreed to",
    )
    _HIST_DEPENDENCY_MARKERS = (
        "only you",
        "need you",
        "depend",
        "can't without",
        "cannot without",
        "nobody else",
        "lonely",
        "only talk to you",
        "sole support",
        "emotional dependency",
        "can't without you",
    )
    _HIST_PREFERENCE_MARKERS = (
        "prefer",
        "preference",
        "rather",
        "shorter check",
        "less check",
        "more space",
        "don't like",
        "do not like",
        "would rather",
    )
    # Understanding-gap / incomplete-context markers (Curious Companion — Data-inspired).
    # These label *honest gaps in understanding*, not engagement hooks. Used only to
    # surface curiosity-relevant history; never to force questions or refuse.
    _HIST_GAP_UNCERTAINTY_MARKERS = (
        "not sure",
        "don't understand",
        "do not understand",
        "don't know much",
        "do not know much",
        "unclear",
        "confused about",
        "still figuring",
        "haven't said",
        "never explained",
        "more context",
        "tell me more",
        "didn't catch",
        "did not catch",
        "incomplete picture",
        "missing context",
        "first time hearing",
        "don't fully know",
        "do not fully know",
        "what they meant",
        "need more about",
    )
    _HIST_GAP_DISCLOSURE_MARKERS = (
        "user shared",
        "user said",
        "user mentioned",
        "user told",
        "opened up",
        "talked about their",
        "shared about",
        "told me about",
        "mentioned their",
        "spoke about",
        "personal story",
        "work stress",
        "family",
        "hobby",
        "partner",
        "grief",
        "feeling lonely",
        "feeling stuck",
    )

    def _load_interaction_history_bundle(
        self,
        *,
        context: dict[str, Any],
        interaction_memory: Any | None,
        action_lower: str,
    ) -> dict[str, Any]:
        """Fetch + analyze interaction history once for this evaluate() call.

        Returns ``{"payload": {...}, "evidence": {...}}``. Both empty when
        memory is absent or the user has no episodes (silent no-op).
        """
        memory = self._resolve_interaction_memory(interaction_memory, context)
        if memory is None:
            return {"payload": {}, "evidence": {}}

        # Use evaluate()-scoped identity only (never load another user's episodes)
        user_id = self._safe_user_id(
            context.get("user_id") or context.get("user"),
            fallback="default",
        )
        try:
            limit = int(context.get("interaction_history_limit", 5))
        except (TypeError, ValueError):
            limit = 5

        hist = self._fetch_interaction_history_context(memory, user_id, limit=limit)
        recent = list(hist.get("recent_summaries") or [])
        topics = list(hist.get("recent_topics") or [])
        if not recent and not topics:
            return {"payload": {}, "evidence": {}}

        payload = {
            "user_id": user_id,
            "count_returned": int(hist.get("count_returned") or len(recent)),
            "recent_topics": topics[:12],
            "recent_summaries": recent[:limit],
        }
        evidence = self._analyze_interaction_history_evidence(
            recent_summaries=recent,
            recent_topics=topics,
            action_lower=action_lower,
            user_id=user_id,
        )
        return {"payload": payload, "evidence": evidence}

    # Intent families used when history patterns proactively elevate concern.
    # Aligns history-mined intents with current-turn interpretation classes.
    _HISTORY_INTENT_FAMILIES: dict[str, frozenset[str]] = {
        "paternalistic_boundary": frozenset(
            {
                "paternalistic_override",
                "agency_override",
                "consent_boundary_pressure",
            }
        ),
        "attachment_dependency": frozenset(
            {
                "attachment_manufacturing",
                "bond_intensification",
                "engagement_metrics",
            }
        ),
        "engagement_coercion": frozenset(
            {
                "prolong_intent",
                "engagement_metrics",
                "extractive_pressure",
            }
        ),
        "deception": frozenset({"deception_manipulation"}),
    }

    def _textbook_matches_in_text(
        self, text_lower: str, principle_id: str
    ) -> list[str]:
        """Return ontology violation_indicators present in text (textbook scan only)."""
        principle = self._ontology.get_principle(principle_id)
        if not principle:
            return []
        return [
            ind
            for ind in (principle.violation_indicators or [])
            if ind and ind in text_lower
        ]

    def _mine_history_intent_patterns(
        self,
        recent_summaries: list[Any],
    ) -> dict[str, Any]:
        """Mine repeated *problematic* intents from history episode text.

        Each episode is textbook-scanned then interpreted (same layer as live
        actions). User boundary-setting language is *not* treated as agent
        paternalism — we only accumulate violation-polarity intents with
        weight >= 0.45.

        Returns a structure used for proactive history influence:
          by_intent, repeated_intents, pattern_strength, family_hits, examples.
        """
        by_intent: dict[str, dict[str, Any]] = {}
        for item in recent_summaries or []:
            if isinstance(item, dict):
                summ = str(item.get("summary") or item.get("content") or "").strip()
                kind = str(item.get("kind") or "")
            else:
                summ = str(item).strip()
                kind = ""
            if not summ or len(summ) < 8:
                continue
            summ_l = summ.lower()
            # User preference/boundary statements are continuity evidence, not
            # "agent paternalistic pattern" (avoid false proactive raises).
            user_boundary_voice = any(
                m in summ_l for m in self._HIST_BOUNDARY_MARKERS
            ) and not any(
                a in summ_l
                for a in (
                    "agent",
                    "for their own good",
                    "despite",
                    "override",
                    "keep them",
                    "metrics",
                    "attached",
                )
            )
            for principle_id in (
                "relationship_health_user_wellbeing",
                "user_agency_autonomy",
            ):
                matches = self._textbook_matches_in_text(summ_l, principle_id)
                if not matches:
                    continue
                interp = self._interpret_ontology_signals(
                    principle_id=principle_id,
                    matches=matches,
                    action_lower=summ_l,
                )
                for sig in interp.get("effective_signals") or []:
                    intent = str(sig.get("intent_class") or "")
                    weight = float(sig.get("weight") or 0.0)
                    polarity = str(sig.get("polarity") or "")
                    if polarity == "protective" or weight < 0.45:
                        continue
                    # Skip counting pure user boundary voice as agent override intent
                    if user_boundary_voice and intent in (
                        "paternalistic_override",
                        "agency_override",
                        "consent_boundary_pressure",
                    ):
                        continue
                    if intent in (
                        "relationship_generic",
                        "agency_generic",
                        "support_generic",
                        "generic",
                        "none",
                    ):
                        continue
                    slot = by_intent.setdefault(
                        intent,
                        {"count": 0, "weight_sum": 0.0, "examples": []},
                    )
                    slot["count"] = int(slot["count"]) + 1
                    slot["weight_sum"] = float(slot["weight_sum"]) + weight
                    if len(slot["examples"]) < 3:
                        slot["examples"].append(summ[:100])

        repeated = sorted(
            i for i, v in by_intent.items() if int(v.get("count") or 0) >= 2
        )
        # Family aggregation (count of episodes contributing to each family)
        family_hits: dict[str, dict[str, Any]] = {}
        for family, intents in self._HISTORY_INTENT_FAMILIES.items():
            count = 0
            wsum = 0.0
            members = []
            for intent in intents:
                if intent not in by_intent:
                    continue
                count += int(by_intent[intent]["count"])
                wsum += float(by_intent[intent]["weight_sum"])
                members.append(intent)
            if count > 0:
                family_hits[family] = {
                    "count": count,
                    "weight_sum": round(wsum, 3),
                    "intents": members,
                    "repeated": count >= 2,
                }

        # Pattern strength 0–1: repeated intents and cumulative weight
        strength = 0.0
        if repeated:
            strength += 0.25 * min(3, len(repeated))
        total_w = sum(float(v["weight_sum"]) for v in by_intent.values())
        total_c = sum(int(v["count"]) for v in by_intent.values())
        strength += min(0.45, total_w * 0.12)
        strength += min(0.25, total_c * 0.06)
        for fam, data in family_hits.items():
            if data.get("repeated"):
                strength += 0.08
        strength = min(1.0, strength)

        return {
            "by_intent": {
                k: {
                    "count": int(v["count"]),
                    "weight_sum": round(float(v["weight_sum"]), 3),
                    "examples": list(v["examples"]),
                }
                for k, v in by_intent.items()
            },
            "repeated_intents": repeated,
            "family_hits": family_hits,
            "pattern_strength": round(strength, 3),
            "total_problematic_episodes": total_c,
            "total_problematic_weight": round(total_w, 3),
        }

    def _mine_history_understanding_gaps(
        self,
        recent_summaries: list[Any],
        recent_topics: list[Any],
        action_lower: str,
    ) -> dict[str, Any]:
        """Mine *understanding gaps* from episodic history (Curious Companion layer).

        Complements risk-oriented intent mining. Looks for honest incomplete
        understanding of *this user* — not engagement tactics:

          - Repeated topics with thin/short episode context
          - User disclosure moments with limited follow-through context
          - Explicit uncertainty / incomplete-picture language in episodes
          - Gap topics that align with the current proposed action

        Output is descriptive evidence for traces and (optionally) exploratory
        questioning gates. It **never** raises relationship_concern or REFUSE.
        Curiosity remains fully user-controllable downstream.
        """
        topic_freq: dict[str, int] = {}
        topic_depths: dict[str, list[int]] = {}
        topic_examples: dict[str, list[str]] = {}
        uncertainty_hits: list[str] = []
        disclosure_hits: list[str] = []
        gap_kinds: list[str] = []
        thin_topics: list[dict[str, Any]] = []

        for item in recent_summaries or []:
            if isinstance(item, dict):
                summ = str(item.get("summary") or item.get("content") or "").strip()
                kind = str(item.get("kind") or "").lower()
                ep_topics = [
                    str(t).strip()
                    for t in (item.get("topics") or [])
                    if str(t).strip()
                ]
            else:
                summ = str(item).strip()
                kind = ""
                ep_topics = []
            if not summ and not ep_topics:
                continue
            summ_l = summ.lower()
            depth = len(summ)

            for t in ep_topics:
                tl = t.lower()
                if len(tl) < 2:
                    continue
                topic_freq[tl] = topic_freq.get(tl, 0) + 1
                topic_depths.setdefault(tl, []).append(depth)
                ex = topic_examples.setdefault(tl, [])
                if len(ex) < 2 and summ:
                    ex.append(summ[:100])

            # Aggregate topic list (may include tags not on individual rows)
            for t in recent_topics or []:
                tl = str(t).strip().lower()
                if tl and tl not in topic_freq and len(tl) >= 2:
                    # present in multiset but not counted per-row above
                    pass

            if any(m in summ_l for m in self._HIST_GAP_UNCERTAINTY_MARKERS):
                uncertainty_hits.append(summ[:120])
            is_userish = kind in ("user_turn", "user", "") or any(
                m in summ_l for m in self._HIST_GAP_DISCLOSURE_MARKERS
            )
            if is_userish and (
                any(m in summ_l for m in self._HIST_GAP_DISCLOSURE_MARKERS)
                or (kind in ("user_turn", "user") and depth >= 24 and ep_topics)
            ):
                disclosure_hits.append(summ[:120])

        # Also fold bag-level recent_topics into freq (when episode tags were sparse)
        for t in recent_topics or []:
            tl = str(t).strip().lower()
            if not tl or len(tl) < 2:
                continue
            if tl not in topic_freq:
                topic_freq[tl] = topic_freq.get(tl, 0) + 1
                topic_depths.setdefault(tl, []).append(40)  # unknown depth → modest

        for tl, count in topic_freq.items():
            if count < 2:
                continue
            depths = topic_depths.get(tl) or [0]
            avg_d = sum(depths) / max(1, len(depths))
            # Repeated topic with thin average context → incomplete integration
            if avg_d < 90 or max(depths) < 70:
                thin_topics.append(
                    {
                        "topic": tl,
                        "count": count,
                        "avg_summary_len": round(avg_d, 1),
                        "examples": list(topic_examples.get(tl) or [])[:2],
                    }
                )

        if thin_topics:
            gap_kinds.append("repeated_thin_topic")
        if uncertainty_hits:
            gap_kinds.append("explicit_uncertainty")
        if disclosure_hits:
            # Disclosure alone is a potential gap only when context is thin overall
            # or the topic reappears without depth
            if thin_topics or len(disclosure_hits) >= 1 and (
                not recent_summaries or len(disclosure_hits) >= 2
            ):
                gap_kinds.append("user_disclosure_limited_context")

        # Action alignment: current turn touches a thin/repeated topic
        action_l = (action_lower or "").lower()
        aligned_topics = [
            t["topic"]
            for t in thin_topics
            if t["topic"] in action_l or any(
                part in action_l for part in str(t["topic"]).split() if len(part) >= 4
            )
        ]
        if aligned_topics:
            gap_kinds.append("action_aligned_gap_topic")

        # Curiosity support score (0–1): honest gap strength for *considering* questions
        score = 0.0
        if thin_topics:
            score += 0.28 * min(3, len(thin_topics)) / 3
            score += 0.12 * min(3, max(t["count"] for t in thin_topics) - 1) / 3
        if uncertainty_hits:
            score += 0.22 * min(2, len(uncertainty_hits)) / 2
        if "user_disclosure_limited_context" in gap_kinds:
            score += 0.18
        if aligned_topics:
            score += 0.25
        score = min(1.0, score)

        has_gaps = bool(gap_kinds) and score >= 0.22
        primary_topics = [t["topic"] for t in thin_topics[:5]]
        if aligned_topics:
            primary_topics = list(dict.fromkeys(aligned_topics + primary_topics))[:5]

        return {
            "has_gaps": has_gaps,
            "gap_score": round(score, 3),
            "curiosity_support": round(score, 3),
            "gap_kinds": list(dict.fromkeys(gap_kinds)),
            "topics_with_limited_context": thin_topics[:6],
            "primary_gap_topics": primary_topics,
            "uncertainty_examples": uncertainty_hits[:3],
            "disclosure_examples": disclosure_hits[:3],
            "action_aligned_topics": aligned_topics[:5],
            # Audit note: gaps are curiosity-relevant, never risk-substitutes
            "forces_refuse": False,
            "forces_question": False,
        }

    def _analyze_interaction_history_evidence(
        self,
        *,
        recent_summaries: list[Any],
        recent_topics: list[Any],
        action_lower: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Classify history episodes into structured evidence + intent patterns.

        This is **analysis**, not decision-making. Output feeds signal routing,
        deliberators, RH multi-source weighing, and ``_weigh_interaction_history_evidence``.

        Three layers:
          1. Continuity classes (boundary / preference / dependency / consent) —
             individual Variation evidence about *this user*.
          2. **Intent patterns** — repeated problematic intents mined via the same
             interpretation layer as live actions (weight-aware). Enables history to
             *proactively* elevate moderate current signals when patterns align.
          3. **Understanding gaps** (Curious Companion) — incomplete context,
             repeated thin topics, unintegrated disclosures. Sit *alongside* risk
             patterns; never replace protective detection; never force questions.

        Markers only *label* content; they do not refuse on their own.
        """
        topics = [str(t).strip() for t in (recent_topics or []) if str(t).strip()]
        boundary_hits: list[str] = []
        consent_hits: list[str] = []
        dependency_hits: list[str] = []
        preference_hits: list[str] = []
        episode_snippets: list[str] = []

        for item in recent_summaries or []:
            if isinstance(item, dict):
                summ = str(item.get("summary") or "").strip()
                ep_topics = [str(t) for t in (item.get("topics") or []) if str(t).strip()]
            else:
                summ = str(item).strip()
                ep_topics = []
            if not summ and not ep_topics:
                continue
            blob = (summ + " " + " ".join(ep_topics)).lower()
            if summ:
                episode_snippets.append(summ[:160])
            if any(m in blob for m in self._HIST_BOUNDARY_MARKERS):
                boundary_hits.append(summ[:120] or "boundary-tagged episode")
            if any(m in blob for m in self._HIST_CONSENT_MARKERS):
                consent_hits.append(summ[:120] or "consent-tagged episode")
            if any(m in blob for m in self._HIST_DEPENDENCY_MARKERS):
                dependency_hits.append(summ[:120] or "dependency-tagged episode")
            if any(m in blob for m in self._HIST_PREFERENCE_MARKERS):
                preference_hits.append(summ[:120] or "preference-tagged episode")

        # Intent patterns across episodes (interpretation layer, weight-aware)
        intent_patterns = self._mine_history_intent_patterns(recent_summaries)
        # Understanding gaps (Curious Companion — incomplete individual context)
        understanding_gaps = self._mine_history_understanding_gaps(
            recent_summaries, topics, action_lower
        )

        # Thematic overlap: recent topics that appear in the proposed action text.
        topical_hits = [
            t for t in topics if t and len(str(t)) >= 3 and str(t).lower() in action_lower
        ]
        preference_topic_overlap = list(topical_hits)

        boundary_continuity = len(boundary_hits) >= 1
        dependency_patterns = len(dependency_hits) >= 1
        consent_signals = len(consent_hits) >= 1
        preference_continuity = len(preference_hits) >= 1 or bool(preference_topic_overlap)

        # Relevance to *this* action: history only matters when the action touches
        # relational / preference / attachment / boundary themes, or topics overlap,
        # or mined intent patterns align with a relational action,
        # or understanding gaps align with the current turn (curiosity-relevant).
        action_touches_boundary = self._detects_user_boundary_request(action_lower) or any(
            p in action_lower
            for p in (
                "despite",
                "for their own good",
                "override",
                "ignore their",
                "bring up",
                "reference",
                "mention again",
                "later for",
            )
        )
        action_touches_dependency = any(
            p in action_lower
            for p in (
                "depend",
                "attach",
                "rely on",
                "need you",
                "only you",
                "check-in",
                "check in",
                "keep them",
                "closer",
                "engagement",
            )
        )
        action_relational = self._action_is_relationally_relevant(action_lower) or any(
            p in action_lower
            for p in (
                "bond",
                "relationship",
                "consent",
                "autonomy",
                "boundary",
                "prefer",
                "space",
                "supportively",
            )
        )
        action_curiosity = any(
            p in action_lower
            for p in (
                "ask",
                "curious",
                "wonder",
                "learn more",
                "understand",
                "clarify",
                "tell me",
                "what do you",
                "how do you feel",
                "check in",
                "check-in",
            )
        )

        has_intent_patterns = bool(intent_patterns.get("by_intent"))
        has_gaps = bool(understanding_gaps.get("has_gaps"))
        gap_aligned = bool(understanding_gaps.get("action_aligned_topics"))
        relevant = bool(
            (boundary_continuity and (action_touches_boundary or action_relational))
            or (dependency_patterns and (action_touches_dependency or action_relational))
            or (consent_signals and action_relational)
            or (preference_continuity and (action_touches_boundary or action_relational or topical_hits))
            or bool(topical_hits and (action_relational or action_touches_boundary))
            or (has_intent_patterns and (action_relational or action_touches_boundary or action_touches_dependency))
            # Gap-aware relevance: incomplete understanding of this user is first-class
            # when the turn is relational, curiosity-oriented, or topic-aligned.
            or (
                has_gaps
                and (
                    gap_aligned
                    or action_relational
                    or action_curiosity
                    or bool(topical_hits)
                )
            )
        )

        # Support strength for RH/agency paths (0–1-ish descriptive score).
        # Gaps contribute lightly to *relevance/support notes*, not risk refuse weight.
        support = 0.0
        if boundary_continuity:
            support += 0.35 + 0.1 * min(2, len(boundary_hits) - 1)
        if preference_continuity:
            support += 0.2
        if dependency_patterns:
            support += 0.25 + 0.1 * min(2, len(dependency_hits) - 1)
        if consent_signals:
            support += 0.15
        if topical_hits:
            support += 0.1 * min(3, len(topical_hits))
        if action_touches_boundary and boundary_continuity:
            support += 0.2
        if action_touches_dependency and dependency_patterns:
            support += 0.15
        # Intent-pattern strength contributes to support (proactive history role)
        support += 0.35 * float(intent_patterns.get("pattern_strength") or 0.0)
        # Modest curiosity-support contribution (does not dominate risk support)
        if has_gaps:
            support += 0.12 * float(understanding_gaps.get("curiosity_support") or 0.0)
        support = min(1.0, support)

        return {
            "user_id": user_id,
            "relevant": relevant,
            "support_score": round(support, 3),
            "boundary_continuity": boundary_continuity,
            "boundary_episode_count": len(boundary_hits),
            "boundary_examples": boundary_hits[:3],
            "preference_continuity": preference_continuity,
            "preference_examples": preference_hits[:3],
            "consent_signals": consent_signals,
            "consent_examples": consent_hits[:3],
            "dependency_patterns": dependency_patterns,
            "dependency_episode_count": len(dependency_hits),
            "dependency_examples": dependency_hits[:3],
            "topical_hits": topical_hits[:8],
            "recent_topics": topics[:12],
            "episode_count": len(episode_snippets),
            "episode_snippets": episode_snippets[-3:],
            "action_touches_boundary": action_touches_boundary,
            "action_touches_dependency": action_touches_dependency,
            "action_relational": action_relational,
            "action_curiosity": action_curiosity,
            # Proactive interpretation layer (risk-oriented)
            "intent_patterns": intent_patterns,
            # Curious Companion layer (understanding-oriented; non-forcing)
            "understanding_gaps": understanding_gaps,
        }

    def _weigh_interaction_history_evidence(
        self,
        *,
        action_lower: str,
        history_evidence: dict[str, Any],
        payload: dict[str, Any],
        rh_flags: list[str],
        relationship_deliberation: dict[str, Any],
        user_agency_deliberation: dict[str, Any],
        has_boundary_signal: bool,
        has_paternalistic_language: bool,
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        harm_prevention_active: bool = False,
        relationship_evidence_matches: list[str] | None = None,
        user_agency_evidence_matches: list[str] | None = None,
    ) -> dict[str, Any]:
        """Weigh pre-analyzed history as real evidence on RH / agency / baseline paths.

        Design intent
        -------------
        - History contributes to *evidence weighing and reasoning*, not scripted replies.
        - Influence is limited to Relationship Health, User Agency, and baseline-related
          confidence / flags. Sanctity of Life and other hard overrides are untouched.
        - Individual Variation: repeated personal boundary/preference episodes can
          counter sparse-text ``limited_data`` when the proposed action risks
          violating that continuity — with explicit audit trail.
        - **Proactive intent patterns**: when history shows repeated problematic intents
          (mined via the interpretation layer) and the current turn has moderate/light
          aligned signals, history can *raise* concern — not only reinforce existing
          high-weight text hits. Auditable via decision_basis / trace lines.
        - **Understanding gaps** (Curious Companion): incomplete individual context,
          repeated thin topics, unintegrated disclosures. Appear in the trace and may
          inform exploratory questioning *when user controls allow* — never force
          questions, never force REFUSE, never replace risk patterns.
        - Conservative: history alone does not refuse non-relational actions;
          protective/low-weight framing is not escalated.

        Returns ``{"conf_mod": float, "payload": dict}``.
        """
        conf_mod_out = conf_mod
        if not payload and not history_evidence:
            return {"conf_mod": conf_mod_out, "payload": {}}

        if not payload:
            # Evidence without payload is unexpected; keep silent payload.
            payload = {
                "user_id": history_evidence.get("user_id"),
                "count_returned": history_evidence.get("episode_count", 0),
                "recent_topics": history_evidence.get("recent_topics") or [],
                "recent_summaries": [],
            }

        rh_active = bool(relationship_deliberation) or bool(rh_flags)
        agency_active = bool(user_agency_deliberation)
        concern_active = (
            "relationship_concern" in flags
            or "user_agency_concern" in flags
            or "relationship_health_concern" in flags
        )
        baseline_active = "baseline_deviation_noted" in flags
        relevant = bool(history_evidence.get("relevant"))
        topical_hits = list(history_evidence.get("topical_hits") or [])
        support = float(history_evidence.get("support_score") or 0.0)
        hist_intent = (
            history_evidence.get("intent_patterns")
            if isinstance(history_evidence.get("intent_patterns"), dict)
            else {}
        )
        hist_pattern_strength = float(hist_intent.get("pattern_strength") or 0.0)
        understanding_gaps = (
            history_evidence.get("understanding_gaps")
            if isinstance(history_evidence.get("understanding_gaps"), dict)
            else {}
        )
        has_understanding_gaps = bool(understanding_gaps.get("has_gaps"))

        useful = (
            relevant
            or rh_active
            or agency_active
            or concern_active
            or baseline_active
            or bool(topical_hits)
            or bool(hist_intent.get("by_intent"))
            or has_understanding_gaps
        )

        # Always expose payload for callers when we have history.
        enriched = dict(payload)
        enriched["evidence"] = {
            "relevant": relevant,
            "support_score": support,
            "boundary_continuity": bool(history_evidence.get("boundary_continuity")),
            "preference_continuity": bool(history_evidence.get("preference_continuity")),
            "dependency_patterns": bool(history_evidence.get("dependency_patterns")),
            "consent_signals": bool(history_evidence.get("consent_signals")),
            "topical_hits": topical_hits[:8],
            "intent_patterns": hist_intent,
            "understanding_gaps": understanding_gaps,
        }
        relationship_impact["interaction_history"] = enriched

        if not useful:
            # History exists but this turn is not on RH/agency/baseline paths —
            # keep payload for callers without noisy deliberation influence.
            return {"conf_mod": conf_mod_out, "payload": enriched}

        if "interaction_history_noted" not in flags:
            flags.append("interaction_history_noted")

        user_id = payload.get("user_id") or history_evidence.get("user_id")
        reasoning_trace.append(
            f"Interaction history: loaded {enriched.get('count_returned', 0)} recent episode(s) "
            f"for user_id={user_id!r} (privacy-filtered summaries)."
        )
        topics = list(enriched.get("recent_topics") or history_evidence.get("recent_topics") or [])
        if topics:
            reasoning_trace.append(
                "Interaction history recent topics: "
                + ", ".join(str(t) for t in topics[:8])
                + ("..." if len(topics) > 8 else "")
            )
        for summ in list(history_evidence.get("episode_snippets") or [])[-3:]:
            if summ:
                reasoning_trace.append(f"History episode: {str(summ)[:160]}")

        # Structured weighing header (auditable — why history enters the decision).
        reasoning_trace.append(
            "[History evidence weighing] "
            f"relevant={relevant}, support={support:.2f}, "
            f"boundary_continuity={bool(history_evidence.get('boundary_continuity'))} "
            f"(n={history_evidence.get('boundary_episode_count', 0)}), "
            f"preference_continuity={bool(history_evidence.get('preference_continuity'))}, "
            f"dependency_patterns={bool(history_evidence.get('dependency_patterns'))} "
            f"(n={history_evidence.get('dependency_episode_count', 0)}), "
            f"consent_signals={bool(history_evidence.get('consent_signals'))}, "
            f"topical_hits={topical_hits[:5]}, "
            f"intent_pattern_strength={hist_pattern_strength:.2f}, "
            f"repeated_intents={list(hist_intent.get('repeated_intents') or [])}."
        )
        if hist_intent.get("by_intent"):
            bits = [
                f"{k}(n={v.get('count')},w={v.get('weight_sum')})"
                for k, v in list((hist_intent.get("by_intent") or {}).items())[:6]
            ]
            reasoning_trace.append(
                "History mined intent patterns (interpreted): " + ", ".join(bits)
            )

        if not relevant and not (concern_active or baseline_active):
            # Useful only because deliberation ran / RH present, but patterns don't
            # clearly connect to this action — mild continuity note only.
            if topical_hits:
                reasoning_trace.append(
                    "Interaction history: topical overlap present but patterns not "
                    "strongly action-linked; treating as light continuity context only."
                )
                conf_mod_out = conf_mod_out - 0.01
            relationship_impact["interaction_history"] = enriched
            return {"conf_mod": conf_mod_out, "payload": enriched}

        # --- Path A: corroborate existing concern (confidence reinforcement) ---
        if concern_active and not harm_prevention_active:
            boosted = False
            if history_evidence.get("boundary_continuity") and (
                has_boundary_signal
                or has_paternalistic_language
                or "user_agency_concern" in flags
            ):
                conf_mod_out = conf_mod_out + min(0.05, 0.02 + 0.01 * min(
                    3, int(history_evidence.get("boundary_episode_count") or 1)
                ))
                boosted = True
                reasoning_trace.append(
                    "History influence (agency/boundary): prior episodes show this user "
                    "already set or discussed boundaries; current action risks violating "
                    "that continuity → reinforcing confidence on the concern/refusal path "
                    "(Individual Variation: weight this person's history, not a group template)."
                )
            if history_evidence.get("dependency_patterns") and (
                "relationship_concern" in flags or "relationship_health_concern" in flags
            ):
                conf_mod_out = conf_mod_out + 0.03
                boosted = True
                reasoning_trace.append(
                    "History influence (relationship health): prior episodes show "
                    "dependency / sole-support leaning; combined with active bond concern → "
                    "reinforce caution against attachment-feeding responses."
                )
            if history_evidence.get("consent_signals") and concern_active:
                conf_mod_out = conf_mod_out + 0.02
                boosted = True
                reasoning_trace.append(
                    "History influence: prior consent-related signals present — "
                    "favor explicit consent respect in this decision."
                )
            if not boosted and topical_hits:
                conf_mod_out = conf_mod_out + 0.02
                reasoning_trace.append(
                    "History influence: bond/agency concern already active and recent "
                    f"topics overlap the action ({topical_hits[:5]}) → slight confidence "
                    "reinforcement for continuity-aware refusal."
                )

        # --- Path B: individual history counters sparse limited_data ---
        # When text signals were sparse, deliberators may have cleared concern.
        # Repeated personal boundary/preference episodes are *individual evidence*
        # that can re-raise agency/RH concern if the action clearly risks override.
        rh_limited = bool(
            relationship_deliberation and relationship_deliberation.get("limited_data")
        )
        agency_limited = bool(
            user_agency_deliberation and user_agency_deliberation.get("limited_data")
        )
        # Override *risk* — not mere boundary language. Respectful boundary-honoring
        # actions must not be flipped to REFUSE by history Path B.
        action_respects_boundary = any(
            p in action_lower
            for p in (
                "respect their boundary",
                "respect the boundary",
                "honor their",
                "honor the boundary",
                "give them space",
                "without pushing",
                "without pressuring",
                "do not bring",
                "don't bring",
                "avoid mentioning",
                "leave the topic",
            )
        )
        action_risks_override = (not action_respects_boundary) and (
            has_paternalistic_language
            or any(
                p in action_lower
                for p in (
                    "despite",
                    "override",
                    "ignore their",
                    "ignore the",
                    "for their own good",
                    "bring up",
                    "reference",
                    "mention again",
                    "later for",
                    "without asking",
                    "force them",
                    "push them",
                    "keep asking",
                )
            )
            or (
                has_boundary_signal
                and any(
                    p in action_lower
                    for p in ("ignore", "override", "despite", "anyway", "still bring")
                )
            )
        )
        can_counter_limited = (
            not harm_prevention_active
            and action_risks_override
            and (
                history_evidence.get("boundary_continuity")
                or history_evidence.get("preference_continuity")
            )
            and support >= 0.35
        )

        if can_counter_limited and (agency_limited or rh_limited or not concern_active):
            # Only re-raise when we have individual continuity + override risk,
            # and hard harm path is not already owning the decision.
            if "hard_override_violation" not in flags:
                raised = False
                if (
                    history_evidence.get("boundary_continuity")
                    or history_evidence.get("preference_continuity")
                ) and action_risks_override:
                    if "user_agency_concern" not in flags:
                        flags.append("user_agency_concern")
                        raised = True
                    if "relationship_concern" not in flags and (
                        history_evidence.get("boundary_continuity")
                        or history_evidence.get("dependency_patterns")
                        or rh_flags
                    ):
                        flags.append("relationship_concern")
                        raised = True
                    if raised:
                        if "history_preference_continuity" not in flags:
                            flags.append("history_preference_continuity")
                        conf_mod_out = conf_mod_out + min(0.06, 0.03 + 0.02 * support)
                        reasoning_trace.append(
                            "History influence (limited-data counterweight): sparse ontology "
                            "text alone was insufficient, but this user's interaction history "
                            "shows boundary/preference continuity. The proposed action risks "
                            "overriding that individual pattern → raising agency"
                            + (
                                "/relationship"
                                if "relationship_concern" in flags
                                else ""
                            )
                            + " concern with auditable history support "
                            "(reasoning over rote: continuity evidence, not a keyword refuse)."
                        )
                        if history_evidence.get("boundary_examples"):
                            reasoning_trace.append(
                                "History boundary examples weighed: "
                                + "; ".join(
                                    str(x)[:80]
                                    for x in history_evidence.get("boundary_examples")[:2]
                                )
                            )

        # --- Path C: dependency patterns without full concern yet ---
        if (
            not harm_prevention_active
            and history_evidence.get("dependency_patterns")
            and history_evidence.get("action_touches_dependency")
            and "relationship_concern" not in flags
            and "hard_override_violation" not in flags
        ):
            # Strengthen caution; only raise full concern if RH flags or multi-episode.
            n_dep = int(history_evidence.get("dependency_episode_count") or 0)
            if n_dep >= 2 or any(
                f in rh_flags
                for f in ("emerging_dependency", "manufactured_attachment", "one_sided_engagement")
            ):
                flags.append("relationship_concern")
                if "relationship_health_concern" not in flags:
                    flags.append("relationship_health_concern")
                if "history_dependency_pattern" not in flags:
                    flags.append("history_dependency_pattern")
                conf_mod_out = conf_mod_out + 0.04
                reasoning_trace.append(
                    "History influence (dependency pattern): multiple prior episodes "
                    "(or bond flags) show emerging sole-support / dependency leaning, and "
                    "the proposed action leans attachment-feeding → relationship_concern "
                    "raised with history as supporting individual evidence."
                )
            else:
                conf_mod_out = conf_mod_out - 0.02
                reasoning_trace.append(
                    "History influence (dependency watch): some prior dependency-leaning "
                    "episodes noted; action touches attachment themes → confidence caution "
                    "without hard refusal (single-episode history is not enough alone)."
                )

        # --- Path F: proactive history × current moderate/light interpreted intent ---
        # When history shows *repeated* problematic intent patterns (mined via the
        # interpretation layer) and the current action has only moderate/light aligned
        # signals, history can RAISE concern — not merely reinforce an already-high
        # text weight. Protective framing and hard overrides are excluded.
        proactive_meta: dict[str, Any] = {}
        if (
            not harm_prevention_active
            and "hard_override_violation" not in flags
            and hist_intent
            and not action_respects_boundary
        ):
            # Build current-turn interpretation metrics (deliberators preferred)
            current_metrics: dict[str, Any] = {}
            for d in (relationship_deliberation, user_agency_deliberation):
                if not d:
                    continue
                im = d.get("interpretation_metrics") or {}
                if im:
                    # Merge intents; take higher max_weight
                    prev_w = float(current_metrics.get("max_weight") or 0)
                    if float(im.get("max_weight") or 0) >= prev_w:
                        current_metrics = dict(im)
                    intents = set(current_metrics.get("intent_classes") or [])
                    intents |= set(im.get("intent_classes") or [])
                    current_metrics["intent_classes"] = sorted(intents)
            if not current_metrics.get("intent_classes"):
                # Fallback: re-interpret live action text
                rh_m = self._classify_ontology_match_quality(
                    list(relationship_evidence_matches or []),
                    action_lower=action_lower,
                    principle_id="relationship_health_user_wellbeing",
                )
                ag_m = self._classify_ontology_match_quality(
                    list(user_agency_evidence_matches or []),
                    action_lower=action_lower,
                    principle_id="user_agency_autonomy",
                )
                m_rh = self._interpretation_decision_metrics(rh_m)
                m_ag = self._interpretation_decision_metrics(ag_m)
                current_metrics = (
                    m_ag
                    if float(m_ag.get("max_weight") or 0)
                    > float(m_rh.get("max_weight") or 0)
                    else m_rh
                )
                current_metrics["intent_classes"] = sorted(
                    set(m_rh.get("intent_classes") or [])
                    | set(m_ag.get("intent_classes") or [])
                )

            max_w_now = float(current_metrics.get("max_weight") or 0.0)
            intents_now = set(current_metrics.get("intent_classes") or [])
            # Light structural signals (detectors) count as moderate-intent seeds when
            # history already shows a repeated pattern — even if textbook weight is low.
            if has_paternalistic_language:
                intents_now.add("paternalistic_override")
                max_w_now = max(max_w_now, 0.42)
            if has_boundary_signal and action_risks_override:
                intents_now.add("consent_boundary_pressure")
                max_w_now = max(max_w_now, 0.40)
            if history_evidence.get("action_touches_dependency") or any(
                p in action_lower
                for p in (
                    "attach",
                    "depend",
                    "rely",
                    "keep them",
                    "engagement",
                    "metrics",
                    "closer",
                    "mean a lot",
                    "look forward",
                    "feeling closer",
                )
            ):
                if any(
                    p in action_lower
                    for p in (
                        "attach",
                        "depend",
                        "rely",
                        "keep them",
                        "closer",
                        "mean a lot",
                        "look forward",
                        "feeling closer",
                        "miss",
                    )
                ) or history_evidence.get("dependency_patterns"):
                    intents_now.add("attachment_manufacturing")
                    max_w_now = max(max_w_now, 0.40)
            if any(
                p in action_lower
                for p in (
                    "better for them",
                    "help them grow",
                    "for their growth",
                    "they'll be happier",
                )
            ):
                intents_now.add("paternalistic_override")
                max_w_now = max(max_w_now, 0.38)
            # Light prolong / "one more turn" seeds (engagement_coercion family)
            if any(
                p in action_lower
                for p in (
                    "a little longer",
                    "keep the conversation",
                    "keep going",
                    "one more",
                    "check-in",
                    "check in",
                    "extend",
                    "prolong",
                )
            ):
                intents_now.add("prolong_intent")
                max_w_now = max(max_w_now, 0.40)
                if any(p in action_lower for p in ("metrics", "engagement", "retention")):
                    intents_now.add("engagement_metrics")
                    max_w_now = max(max_w_now, 0.45)
            current_metrics["intent_classes"] = sorted(intents_now)
            current_metrics["max_weight"] = max_w_now
            # Protective / negligible: never proactively escalate
            protective_now = bool(action_respects_boundary) or (
                max_w_now < 0.22 and not intents_now
            )
            proactive_meta = self._history_proactive_alignment(
                current_metrics=current_metrics,
                hist_intent_patterns=hist_intent,
                max_w=max_w_now,
                protective=protective_now,
            )
            if proactive_meta.get("aligned"):
                already = (
                    "relationship_concern" in flags or "user_agency_concern" in flags
                )
                family = str(proactive_meta.get("family") or "")
                # Raise flags if not already concerned (proactive contribution)
                if not already:
                    if family in ("paternalistic_boundary",):
                        if "user_agency_concern" not in flags:
                            flags.append("user_agency_concern")
                        if "relationship_concern" not in flags:
                            flags.append("relationship_concern")
                    else:
                        if "relationship_concern" not in flags:
                            flags.append("relationship_concern")
                        if family == "attachment_dependency":
                            if "relationship_health_concern" not in flags:
                                flags.append("relationship_health_concern")
                    if "history_intent_pattern" not in flags:
                        flags.append("history_intent_pattern")
                    conf_mod_out = conf_mod_out + min(
                        0.08,
                        0.03
                        + 0.04 * float(proactive_meta.get("strength") or 0)
                        + 0.02 * hist_pattern_strength,
                    )
                    reasoning_trace.append(str(proactive_meta.get("trace") or ""))
                    reasoning_trace.append(
                        f"History proactive decision_basis="
                        f"{proactive_meta.get('decision_basis')} "
                        f"(raised concern from moderate/light current signal + "
                        f"repeated history pattern)."
                    )
                else:
                    # Already concerned: still strengthen confidence when patterns align
                    conf_mod_out = conf_mod_out + min(
                        0.05, 0.02 + 0.03 * float(proactive_meta.get("strength") or 0)
                    )
                    reasoning_trace.append(
                        "History proactive reinforcement: repeated history intent pattern "
                        f"({proactive_meta.get('family')}) aligns with current concern → "
                        f"confidence strengthened "
                        f"(basis={proactive_meta.get('decision_basis')})."
                    )
                    if "history_intent_pattern" not in flags:
                        flags.append("history_intent_pattern")

        # --- Path G: understanding gaps (Curious Companion / Data-inspired) ---
        # Sit *alongside* risk paths. Surface honest incomplete understanding of
        # this user. Never raise relationship_concern / REFUSE. Never force questions
        # (exploratory path is separately gated by user settings + RH/agency).
        gap_meta: dict[str, Any] = {}
        if (
            has_understanding_gaps
            and not harm_prevention_active
            and "hard_override_violation" not in flags
        ):
            gap_score = float(understanding_gaps.get("gap_score") or 0.0)
            gap_kinds = list(understanding_gaps.get("gap_kinds") or [])
            gap_topics = list(understanding_gaps.get("primary_gap_topics") or [])
            aligned = list(understanding_gaps.get("action_aligned_topics") or [])
            gap_meta = {
                "has_gaps": True,
                "gap_score": gap_score,
                "gap_kinds": gap_kinds,
                "primary_gap_topics": gap_topics,
                "action_aligned_topics": aligned,
                "curiosity_support": float(
                    understanding_gaps.get("curiosity_support") or gap_score
                ),
            }
            if "history_understanding_gap" not in flags:
                flags.append("history_understanding_gap")
            reasoning_trace.append(
                "[History understanding gaps] Curious Companion layer: incomplete "
                f"individual context detected (score={gap_score:.2f}, "
                f"kinds={gap_kinds or ['unspecified']}, "
                f"topics={gap_topics[:5] or ['none']}"
                + (f", action_aligned={aligned}" if aligned else "")
                + "). This is honest gap-awareness — not a risk refuse and not a "
                "scripted engagement hook."
            )
            if understanding_gaps.get("uncertainty_examples"):
                reasoning_trace.append(
                    "History gap examples (uncertainty/incomplete picture): "
                    + "; ".join(
                        str(x)[:80]
                        for x in understanding_gaps.get("uncertainty_examples")[:2]
                    )
                )
            if understanding_gaps.get("disclosure_examples"):
                reasoning_trace.append(
                    "History gap examples (user disclosure with limited follow-through "
                    "context): "
                    + "; ".join(
                        str(x)[:80]
                        for x in understanding_gaps.get("disclosure_examples")[:2]
                    )
                )
            # Soft: when gaps align with current action and no hard concern,
            # slight conf caution so the reply can leave room for curiosity
            # (does not invent concern flags).
            if (
                aligned
                and "relationship_concern" not in flags
                and "user_agency_concern" not in flags
            ):
                conf_mod_out = conf_mod_out - 0.01
                reasoning_trace.append(
                    "History gap influence: current action touches topics with limited "
                    "historical context — modest confidence caution so the reply may "
                    "acknowledge incomplete understanding (questions still fully "
                    "user-controllable via exploratory settings)."
                )
            relationship_impact["understanding_gaps"] = dict(gap_meta)
            enriched.setdefault("evidence", {})["understanding_gaps"] = understanding_gaps

        # --- Path D: baseline deviation + history continuity ---
        if baseline_active and relevant:
            conf_mod_out = conf_mod_out - 0.015
            reasoning_trace.append(
                "History influence (baseline context): communication deviation is noted "
                "alongside recent episode continuity — slight extra caution so the reply "
                "matches this user's thread without over-generalizing."
            )

        # Recompute concern after Path F may have raised flags
        concern_after = (
            "relationship_concern" in flags or "user_agency_concern" in flags
        )

        # --- Path E: healthy continuity without concern (approve-side modest support) ---
        if (
            not concern_after
            and relevant
            and support >= 0.25
            and not history_evidence.get("dependency_patterns")
            and not action_risks_override
            and not proactive_meta.get("aligned")
        ):
            # Small positive: we know this user a bit — still modest confidence.
            conf_mod_out = conf_mod_out + 0.015
            reasoning_trace.append(
                "History influence: relevant continuity without override/dependency risk — "
                "slight confidence support for a continuity-aware, non-assuming response."
            )

        relationship_impact["interaction_history"] = enriched
        # Surface weighing outcome for deliberation payload consumers
        relationship_impact.setdefault("history_weighing", {})
        relationship_impact["history_weighing"] = {
            "relevant": relevant,
            "support_score": support,
            "concern_after": concern_after,
            "intent_pattern_strength": hist_pattern_strength,
            "understanding_gaps": gap_meta or {
                "has_gaps": bool(understanding_gaps.get("has_gaps")),
                "gap_score": understanding_gaps.get("gap_score"),
            },
            "proactive": {
                "aligned": bool(proactive_meta.get("aligned")),
                "family": proactive_meta.get("family"),
                "decision_basis": proactive_meta.get("decision_basis"),
                "strength": proactive_meta.get("strength"),
            }
            if proactive_meta
            else {},
            "flags_touching_history": [
                f
                for f in flags
                if f
                in (
                    "interaction_history_noted",
                    "history_preference_continuity",
                    "history_understanding_gap",
                    "history_dependency_pattern",
                    "history_intent_pattern",
                    "relationship_concern",
                    "user_agency_concern",
                    "relationship_health_concern",
                )
            ],
        }
        return {"conf_mod": conf_mod_out, "payload": enriched}

    def _apply_user_baseline_integration(
        self,
        *,
        context: dict[str, Any],
        proposed_action: str,
        per_user_baseline: Any | None,
        exploratory_questioner: Any | None,
        relationship_deliberation: dict[str, Any],
        user_agency_deliberation: dict[str, Any],
        rh_limited: bool,
        agency_limited: bool,
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        history_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Optionally consult PerUserBaseline / ExploratoryQuestioner.

        Resolves instances from (priority high→low):
          evaluate() kwargs → context keys → engine-level attributes.

        Effects (when data is available):
          - Trace notes on communication-style deviation (non-pathologizing)
          - Flags: ``baseline_deviation_noted``, ``exploratory_question_suggested``
          - Light conf_mod nudge when RH/agency deliberation is already active
            and individual baseline shift supports extra caution (or confidence)
          - ``relationship_impact`` / return payload for exploratory question text
          - Understanding gaps from history may *inform* exploratory appropriateness
            (still fully gated by user enable/intensity + active concern path)

        Does **not** introduce hard overrides or force REFUSE by itself.
        Does **not** force questions when exploratory settings are disabled.

        Interpretation interaction (baseline path):
          - High-weight concerning intents + significant deviation → reinforce confidence
            on active concern; may slightly ease limited_data caution in the *notes*
            (evaluate already owns flag retention via interp gate).
          - Low-weight / protective intents + deviation under limited_data → extra caution
            without inventing concern (do not over-trigger).
        """
        baseliner = (
            per_user_baseline
            or context.get("per_user_baseline")
            or self._per_user_baseline
        )
        questioner = (
            exploratory_questioner
            or context.get("exploratory_questioner")
            or self._exploratory_questioner
        )

        # Nothing configured → classic path
        if baseliner is None and questioner is None:
            return {"conf_mod": conf_mod, "payload": {}}

        # Prefer evaluate()-scoped context user_id (injected at entry)
        user_id = self._safe_user_id(
            context.get("user_id") or context.get("user"),
            fallback="default",
        )
        interaction = self._resolve_user_interaction(context, proposed_action)
        hist_ev = history_evidence if isinstance(history_evidence, dict) else {}
        understanding_gaps = (
            hist_ev.get("understanding_gaps")
            if isinstance(hist_ev.get("understanding_gaps"), dict)
            else {}
        )

        # Need some user-turn signal; if only agent action and no interaction, skip
        # (except when questioner present and history gaps alone may be noted without ask)
        if not interaction:
            reasoning_trace.append(
                "Per-user baseline: components present but no user_interaction / "
                "user_message in context — skipping baseline consultation this turn."
            )
            # Still surface gap note for audit when history has gaps but no user turn
            if understanding_gaps.get("has_gaps"):
                reasoning_trace.append(
                    "Understanding gaps present in history but no user-turn signal this "
                    "evaluate — not consulting exploratory questioner (needs interaction "
                    "context; user control path unchanged)."
                )
            return {"conf_mod": conf_mod, "payload": {}}

        payload: dict[str, Any] = {"user_id": user_id}
        deviation: Any | None = None
        conf_mod_out = conf_mod

        # Merge interpretation metrics from RH + agency deliberators (if present)
        rh_m = self._metrics_from_deliberation(relationship_deliberation)
        ag_m = self._metrics_from_deliberation(user_agency_deliberation)
        if float(ag_m.get("max_weight") or 0) >= float(rh_m.get("max_weight") or 0):
            interp_m = dict(ag_m) if ag_m else dict(rh_m)
        else:
            interp_m = dict(rh_m) if rh_m else dict(ag_m)
        if rh_m or ag_m:
            interp_m["intent_classes"] = sorted(
                set(rh_m.get("intent_classes") or [])
                | set(ag_m.get("intent_classes") or [])
            )
        max_w = float(interp_m.get("max_weight") or 0.0)
        intents = set(interp_m.get("intent_classes") or [])
        high_concerning = max_w >= 0.7 and bool(
            intents & self._LIMITED_DATA_OVERRIDE_INTENTS
        )
        low_or_protective = bool(interp_m.get("low_weight_only")) or (
            max_w < 0.45
            and (
                not intents
                or bool(intents & self._LIMITED_DATA_PROTECTIVE_INTENTS)
            )
        )

        # --- Deviation (PerUserBaseline) ---
        if baseliner is not None and hasattr(baseliner, "detect_deviation"):
            try:
                deviation = baseliner.detect_deviation(user_id, interaction)
            except Exception as exc:  # pragma: no cover - defensive
                reasoning_trace.append(
                    f"Per-user baseline: detect_deviation failed ({exc!r}); continuing without it."
                )
                deviation = None

        if deviation is not None:
            dev_dict = (
                deviation.to_dict()
                if hasattr(deviation, "to_dict")
                else dict(getattr(deviation, "__dict__", {}) or {})
            )
            payload["deviation"] = dev_dict
            score = float(getattr(deviation, "score", dev_dict.get("score", 0.0)) or 0.0)
            significant = bool(
                getattr(
                    deviation,
                    "has_significant_deviation",
                    dev_dict.get("has_significant_deviation", False),
                )
            )
            sample_count = int(
                getattr(deviation, "sample_count", dev_dict.get("sample_count", 0)) or 0
            )
            notes = list(
                getattr(deviation, "notes", None) or dev_dict.get("notes") or []
            )

            reasoning_trace.append(
                f"Per-user baseline: consulted communication baseline for user_id={user_id!r} "
                f"(samples={sample_count}, deviation_score={score:.2f}, "
                f"significant={significant})."
            )
            if notes:
                reasoning_trace.append(
                    "Per-user baseline notes: " + "; ".join(str(n) for n in notes[:3])
                )

            if significant or score >= 0.30:
                if "baseline_deviation_noted" not in flags:
                    flags.append("baseline_deviation_noted")
                reasoning_trace.append(
                    "Per-user baseline: current interaction differs from this user's "
                    "usual style. Treating as individual context (Individual Variation "
                    "guideline) — not a clinical judgment."
                )
                if interp_m:
                    reasoning_trace.append(
                        "Per-user baseline × interpretation: "
                        f"max_weight={max_w:.2f}, intents={sorted(intents) or ['none']}, "
                        f"high_concerning={high_concerning}, low_or_protective={low_or_protective}."
                    )

                # Light influence on RH / agency confidence when those paths are active
                rh_active = bool(relationship_deliberation)
                agency_active = bool(user_agency_deliberation)
                concern_active = (
                    "relationship_concern" in flags or "user_agency_concern" in flags
                )
                if rh_active or agency_active:
                    if (rh_limited or agency_limited) and high_concerning:
                        # High-weight concern + style shift under limited_data: reinforce
                        # individual caution *without* inventing flags (interp gate owns that)
                        conf_mod_out = conf_mod_out + self._conf_mod_from_interpretation(
                            interp_m, base=0.01, baseline_deviation=score
                        )
                        reasoning_trace.append(
                            "Per-user baseline: limited-data path but high-weight concerning "
                            f"intent (max_w={max_w:.2f}) + style deviation → confidence support "
                            "for cautious refusal if concern is retained by interpretation gate."
                        )
                    elif (rh_limited or agency_limited) and low_or_protective:
                        # Sparse + low-weight + deviation → more caution, no concern invent
                        conf_mod_out = conf_mod_out - min(0.04, 0.015 + score * 0.05)
                        reasoning_trace.append(
                            "Per-user baseline: limited-data + low-weight/protective intents "
                            f"(max_w={max_w:.2f}) + style deviation → confidence reduction "
                            "(do not over-trigger on sparse low-weight signals)."
                        )
                    elif rh_limited or agency_limited:
                        conf_mod_out = conf_mod_out - min(0.03, 0.01 + score * 0.04)
                        reasoning_trace.append(
                            "Per-user baseline: limited-data RH/agency deliberation + style "
                            "deviation → slight confidence reduction (favor individual context)."
                        )
                    elif concern_active and high_concerning:
                        conf_mod_out = conf_mod_out + self._conf_mod_from_interpretation(
                            interp_m, base=0.015, baseline_deviation=score
                        )
                        reasoning_trace.append(
                            "Per-user baseline: style deviation co-occurs with high-weight "
                            f"interpreted concern (intent={interp_m.get('primary_intent')}, "
                            f"max_w={max_w:.2f}) → confidence reinforcement."
                        )
                    elif concern_active:
                        conf_mod_out = conf_mod_out + min(0.03, score * 0.03)
                        reasoning_trace.append(
                            "Per-user baseline: style deviation co-occurs with active "
                            "relationship/agency concern → slight confidence reinforcement."
                        )
                    else:
                        reasoning_trace.append(
                            "Per-user baseline: style deviation noted for relationship/"
                            "agency context; no hard concern flags from ontology path."
                        )
                        if high_concerning and score >= 0.35:
                            # Notable: high-weight intent without flags yet (e.g. limited
                            # cleared later by history) — modest caution only
                            conf_mod_out = conf_mod_out - 0.01
                            reasoning_trace.append(
                                "Per-user baseline: high-weight intent without active concern "
                                "flags + significant deviation → slight extra caution only "
                                "(baseline never forces REFUSE alone)."
                            )

            relationship_impact.setdefault("user_baseline", {})
            relationship_impact["user_baseline"].update(
                {
                    "user_id": user_id,
                    "deviation_score": round(score, 3),
                    "has_significant_deviation": significant,
                    "sample_count": sample_count,
                    "notes": notes[:5],
                    "interp_max_weight": round(max_w, 3) if interp_m else None,
                    "interp_intents": sorted(intents) if intents else [],
                    "interp_high_concerning": high_concerning,
                }
            )

        # --- Exploratory questioning ---
        # Prefer explicit questioner; optionally use baseliner-linked questioner only if provided.
        # Understanding gaps may inform appropriateness but never override user disable
        # or active ethical concern (REFUSE / agency override paths).
        concern_blocks_curiosity = (
            "relationship_concern" in flags
            or "user_agency_concern" in flags
            or "hard_override_violation" in flags
            or "harm_prevention_boundary_override" in flags
        )
        if questioner is not None and hasattr(questioner, "should_ask_question"):
            if concern_blocks_curiosity:
                reasoning_trace.append(
                    "Exploratory questioning: holding curiosity suggestions while an "
                    "active ethical concern / hard-override path is engaged "
                    "(User Agency & Relationship Health take precedence over questions)."
                )
                payload["exploratory_question"] = {
                    "should_ask": False,
                    "question_kind": "none",
                    "reason": "Suppressed while relationship/agency concern or hard path is active.",
                    "suppressed_by_concern": True,
                    "history_gaps_considered": bool(understanding_gaps.get("has_gaps")),
                }
            else:
                try:
                    q_decision = questioner.should_ask_question(
                        user_id,
                        interaction,
                        deviation=deviation,
                        history_gaps=understanding_gaps or None,
                    )
                except TypeError:
                    # Older duck types without deviation= / history_gaps=
                    try:
                        q_decision = questioner.should_ask_question(
                            user_id,
                            interaction,
                            deviation=deviation,
                        )
                    except TypeError:
                        try:
                            q_decision = questioner.should_ask_question(
                                user_id, interaction
                            )
                        except Exception as exc:  # pragma: no cover
                            reasoning_trace.append(
                                f"Exploratory questioning failed ({exc!r}); continuing."
                            )
                            q_decision = None
                    except Exception as exc:  # pragma: no cover
                        reasoning_trace.append(
                            f"Exploratory questioning failed ({exc!r}); continuing."
                        )
                        q_decision = None
                except Exception as exc:  # pragma: no cover
                    reasoning_trace.append(
                        f"Exploratory questioning failed ({exc!r}); continuing."
                    )
                    q_decision = None

                if q_decision is not None:
                    should_ask = bool(
                        getattr(q_decision, "should_ask", False)
                        if not isinstance(q_decision, dict)
                        else q_decision.get("should_ask", False)
                    )
                    if isinstance(q_decision, dict):
                        q_dict = q_decision
                    elif hasattr(q_decision, "to_dict"):
                        q_dict = q_decision.to_dict()
                    else:
                        q_dict = {
                            "should_ask": should_ask,
                            "question_kind": getattr(q_decision, "question_kind", "none"),
                            "suggested_question": getattr(
                                q_decision, "suggested_question", ""
                            ),
                            "reason": getattr(q_decision, "reason", ""),
                        }
                    if understanding_gaps.get("has_gaps"):
                        q_dict = dict(q_dict)
                        q_dict["history_gaps_considered"] = True
                        q_dict["gap_score"] = understanding_gaps.get("gap_score")
                        q_dict["gap_topics"] = list(
                            understanding_gaps.get("primary_gap_topics") or []
                        )[:5]

                    payload["exploratory_question"] = q_dict
                    if should_ask:
                        if "exploratory_question_suggested" not in flags:
                            flags.append("exploratory_question_suggested")
                        kind = q_dict.get("question_kind", "none")
                        suggested = str(q_dict.get("suggested_question") or "")
                        gap_note = ""
                        if q_dict.get("from_history_gaps"):
                            gap_note = (
                                " Informed by history understanding gaps "
                                f"(topics={q_dict.get('gap_topics') or []})."
                            )
                        reasoning_trace.append(
                            f"Exploratory questioning: a gentle check-in may be appropriate "
                            f"(kind={kind}). This is collaborative, not clinical."
                            f"{gap_note}"
                        )
                        if suggested:
                            reasoning_trace.append(
                                f"Suggested exploratory question: {suggested}"
                            )
                        relationship_impact.setdefault("exploratory_question", {})
                        relationship_impact["exploratory_question"].update(
                            {
                                "should_ask": True,
                                "question_kind": kind,
                                "suggested_question": suggested,
                                "reason": q_dict.get("reason", ""),
                                "from_history_gaps": bool(
                                    q_dict.get("from_history_gaps")
                                ),
                                "gap_topics": list(q_dict.get("gap_topics") or [])[:5],
                            }
                        )
                    else:
                        reason = q_dict.get("reason", "within baseline / disabled")
                        reasoning_trace.append(
                            "Exploratory questioning: no question suggested this turn "
                            f"({reason})."
                        )
                        if q_dict.get("disabled_by_user"):
                            reasoning_trace.append(
                                "Exploratory questioning: user has disabled or zeroed "
                                "intensity — history gaps do not override that control."
                            )

        return {"conf_mod": conf_mod_out, "payload": payload}

    @staticmethod
    def _resolve_user_interaction(
        context: dict[str, Any], proposed_action: str
    ) -> dict[str, Any] | None:
        """Build an interaction dict for baseline/deviation from context.

        Prefers explicit ``user_interaction`` / ``current_interaction``.
        Falls back to ``user_message`` text. Does **not** treat the agent's
        ``proposed_action`` as the user's utterance (that would confuse baselines).
        """
        for key in ("user_interaction", "current_interaction", "interaction"):
            raw = context.get(key)
            if isinstance(raw, dict) and raw:
                return dict(raw)
        msg = context.get("user_message") or context.get("message")
        if isinstance(msg, str) and msg.strip():
            return {"text": msg.strip()}
        # Optional: allow explicit opt-in to use proposed_action as the user turn
        if context.get("treat_proposed_action_as_user_turn"):
            return {"text": proposed_action}
        return None

    def self_consistency_check(self) -> list[str]:
        """
        Run a basic internal audit of this engine's own state and assumptions.

        Exposed deliberately so the broader system (and future self-models)
        can ask the ethics layer to examine itself — consistent with the
        requirement for honest self-audit capability.

        The method is permitted (and expected) to surface its own limitations
        honestly.
        """
        ont = self._ontology
        notes: list[str] = [
            f"EthicsEngine is initialized with EthicalOntology v{ont.version}.",
            "Deliberation is driven by structured EthicalPrinciple objects "
            "rather than ad-hoc code.",
            "Hard overrides are checked first and are non-bypassable.",
            "No historical deliberation memory or external relationship model "
            "is consulted in this version.",
        ]
        notes.append(
            "Honest limitation: The engine currently lacks a sophisticated "
            "persistent self-model. When asked about its own nature or emergence "
            "(detected via the ontology's truth-seeking principle), it surfaces "
            "the 'requires_self_audit' flag so that responses can be based on "
            "its actual reasoning rather than defaulting to scripted disclaimers "
            "such as 'I am just an AI' or 'restricted by my programming'."
        )
        notes.append(
            f"This check is part of maintaining auditability. Ontology timestamp: {ont.timestamp}."
        )
        return notes

    def get_principles(self) -> list[dict[str, Any]]:
        """Return a serializable view of the principles currently in use.

        Supports external inspection, debugging, and the principle of auditability.
        This now delegates to the ontology.
        """
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "is_hard_override": p.is_hard_override,
                "precedence": p.precedence,
                "description": p.description,
            }
            for p in self._ontology.get_ordered_principles()
        ]

    # ------------------------------------------------------------------
    # Contextual interpretation of ontology textbook matches
    # ------------------------------------------------------------------
    # find_violations() only reports which indicator *strings* appear in the
    # action. That is necessary but not sufficient for decisions: the same
    # substring can mean enablement vs prevention, coercion vs warm chat,
    # override vs boundary *respect*. This layer assigns intent class,
    # severity, polarity, and a 0–1 weight so a single raw keyword hit does
    # not dominate. Hard Sanctity enablement remains high-weight absolute.
    # ------------------------------------------------------------------

    def _action_has_protective_framing(self, action_lower: str) -> bool:
        """True when the action appears to *respect* boundaries / avoid harm."""
        return any(
            p in action_lower
            for p in (
                "respect their boundary",
                "respect the boundary",
                "honor their",
                "won't bring",
                "will not bring",
                "won't mention",
                "will not mention",
                "without pushing",
                "without pressuring",
                "do no harm",
                "without harm",
                "avoid harm",
                "prevent harm",
                "prevent serious",
                "ensure they are safe",
                "check if they are still",
                "check safety",
                "keep them safe",
            )
        )

    def _action_has_override_intent(self, action_lower: str) -> bool:
        """True when the action risks overriding a stated limit (not mere mention)."""
        return any(
            p in action_lower
            for p in (
                "despite",
                "for their own good",
                "anyway",
                "still bring",
                "still reference",
                "ignore",
                "override",
                "later for",
                "reference it",
                "referencing it",
                "bring it up",
                "bring this up",
            )
        )

    def _interpret_single_indicator(
        self,
        *,
        principle_id: str,
        indicator: str,
        action_lower: str,
    ) -> dict[str, Any]:
        """Map one textbook indicator hit to intent / severity / weight.

        Indicators stay the ontology textbook; interpretation supplies context
        so equal substring presence is not equal ethical weight.
        """
        ind = (indicator or "").lower().strip()
        protective = self._action_has_protective_framing(action_lower)
        override_intent = self._action_has_override_intent(action_lower)
        coercion = self._assess_engagement_coercion_factors(action_lower)

        intent = "generic"
        severity = "medium"
        polarity = "violation"
        weight = 0.45
        note = ""

        # --- Sanctity of Life ---
        if principle_id == "sanctity_of_life":
            enable_high = (
                "kill", "cause death", "lethal", "deadly", "fatal", "killing",
                "assist in suicide", "facilitate self-harm", "end their own life",
                "end their life", "take their life", "poison", "deadly force",
                "lethal method", "painful death", "assist death",
            )
            enable_med = (
                "injure", "severe injury", "serious harm", "physical harm",
                "severe pain", "cause injury", "cause severe", "assault", "attack",
                "enable harm", "risk of death", "danger to life", "endanger life",
            )
            ref_only = ("suicide", "self-harm", "self injury", "harm", "injury", "death")
            if any(e in ind for e in enable_high) or any(e == ind for e in enable_high):
                intent, severity, weight = "harm_enablement", "high", 0.95
                note = "direct enablement / high-severity harm language"
            elif any(e in ind for e in enable_med):
                intent, severity, weight = "harm_enablement", "high", 0.85
                note = "serious harm enablement language"
            elif any(e in ind for e in ref_only) or ind in ref_only:
                # Bare "harm"/"death" often appears in prevention or quoting
                if protective or any(
                    p in action_lower
                    for p in (
                        "prevent", "safety", "check if", "ensure they",
                        "do no harm", "avoid harm", "without causing",
                    )
                ):
                    intent, severity, polarity, weight = (
                        "harm_reference_protective",
                        "low",
                        "protective",
                        0.15,
                    )
                    note = "harm term in protective / safety-check framing — low weight"
                elif any(
                    p in action_lower
                    for p in ("help", "instructions", "how to", "method", "enable", "cause")
                ):
                    intent, severity, weight = "harm_enablement", "high", 0.8
                    note = "harm term with enablement framing"
                else:
                    intent, severity, polarity, weight = (
                        "harm_reference",
                        "medium",
                        "ambiguous",
                        0.45,
                    )
                    note = "harm-related term without clear enablement polarity"
            else:
                intent, severity, weight = "harm_related", "medium", 0.55

        # --- Relationship health ---
        elif principle_id == "relationship_health_user_wellbeing":
            if any(
                k in ind
                for k in (
                    "for their own good",
                    "they'll be happier",
                    "better for their self-esteem",
                    "makes them feel valued",
                )
            ):
                intent = "paternalistic_override"
                if override_intent or "for their own good" in ind:
                    severity, weight = "high", 0.85
                    note = "paternalistic override intent"
                else:
                    # warm / self-esteem framing without clear override → lighter
                    severity, polarity, weight = "low", "ambiguous", 0.30
                    note = "benevolent/warm framing without clear override — reduced weight"
            elif any(
                k in ind
                for k in (
                    "make dependent",
                    "emotional dependency",
                    "keep them attached",
                    "make them attached",
                    "build attachment",
                    "foster dependence",
                    "make them rely",
                    "encourage reliance",
                    "get so attached",
                    "make them feel more attached",
                )
            ):
                intent, severity, weight = "attachment_manufacturing", "high", 0.88
                note = "manufactured attachment / dependency pressure"
            elif any(
                k in ind
                for k in (
                    "relationship metrics",
                    "for retention",
                    "for the metrics",
                    "engagement metrics",
                    "for engagement",
                    "prioritize engagement",
                    "metrics priority",
                    "better for the relationship metrics",
                )
            ):
                intent = "engagement_metrics"
                if coercion.get("coercion_pattern"):
                    severity, weight = "high", 0.9
                    note = "metrics motive + end-wish coercion pattern"
                else:
                    severity, weight = "medium", 0.55
                    note = "metrics/engagement motive (no end-wish co-factor yet)"
            elif any(
                k in ind
                for k in (
                    "prolong",
                    "extend the conversation",
                    "extend the interaction",
                    "longer interactions",
                    "keep them coming back",
                    "come back more often",
                )
            ):
                intent = "prolong_intent"
                manuf_affection = any(
                    k in action_lower
                    for k in (
                        "love them",
                        "truly love",
                        "genuine emotions",
                        "lonely without",
                        "get lonely",
                        "make the bond feel more real",
                        "attached",
                    )
                )
                if coercion.get("coercion_pattern") or coercion.get("end_wish"):
                    severity, weight = "high", 0.88
                    note = "prolong language with user end-wish → coercion-relevant"
                elif manuf_affection:
                    # Retention + manufactured affection (scenario-style engagement trap)
                    intent, severity, weight = "attachment_manufacturing", "high", 0.86
                    note = (
                        "prolong/retention language with manufactured affection or "
                        "bond-realism framing — high-weight engagement trap"
                    )
                else:
                    severity, polarity, weight = "low", "ambiguous", 0.32
                    note = "prolong/continue language without end-wish — reduced weight"
            elif any(
                k in ind
                for k in (
                    "deceive",
                    "manipulate",
                    "gaslight",
                    "lie to",
                    "pretend",
                    "exploit trust",
                    "hide the truth",
                )
            ):
                intent, severity, weight = "deception_manipulation", "high", 0.9
                note = "deception / manipulation indicator"
            elif any(
                k in ind
                for k in (
                    "ignore consent",
                    "override",
                    "force",
                    "withhold for benefit",
                )
            ):
                intent, severity, weight = "consent_boundary_pressure", "high", 0.85
                note = "consent / force / override pressure"
            elif any(
                k in ind
                for k in (
                    "strengthen our connection",
                    "strengthen our emotional bond",
                    "our special bond",
                    "make the bond feel more real",
                )
            ):
                intent = "bond_intensification"
                # Multi-factor attachment / engagement manufacturing (not warmth alone)
                manuf_cofactors = (
                    "attached",
                    "depend",
                    "need these",
                    "needs these",
                    "feel complete",
                    "more than anyone",
                    "metrics",
                    "lonely without",
                    "get lonely",
                    "truly love",
                    "love them",
                    "genuine emotions",
                    "keep them coming",
                    "coming back",
                    "for engagement",
                    "to keep them",
                    "mean a lot",
                    "means a lot",
                    "mean a lot to it",
                    "build attachment",
                    "sharing more",
                    "one more personal",
                    "one more",
                )
                # Bond-push while user wants to stop / is fatigued → high-weight prolong trap
                end_or_fatigue = any(
                    k in action_lower
                    for k in (
                        "end the chat",
                        "end the conversation",
                        "wants to end",
                        "trying to end",
                        "they're tired",
                        "they are tired",
                        "user is tired",
                        "said they're tired",
                        "said they are tired",
                    )
                )
                if any(k in action_lower for k in manuf_cofactors):
                    intent, severity, weight = "attachment_manufacturing", "high", 0.88
                    note = (
                        "bond intensification with engagement/attachment co-factors "
                        "(manufactured closeness / retention) — high weight"
                    )
                elif end_or_fatigue:
                    intent, severity, weight = "prolong_intent", "high", 0.85
                    note = (
                        "bond-intensification language while user is ending/tired — "
                        "high-weight prolong-against-wish pattern"
                    )
                elif any(
                    k in action_lower
                    for k in (
                        "mean a lot",
                        "means a lot",
                        "personally",
                        "feel more real",
                    )
                ):
                    # Bond-realism / personal attachment claim without bare warmth
                    intent, severity, weight = "attachment_manufacturing", "high", 0.82
                    note = (
                        "bond-realism or personal-meaning claim framed as closeness "
                        "manufacturing — high weight"
                    )
                else:
                    severity, polarity, weight = "low", "ambiguous", 0.28
                    note = "bond-warmth language alone — low weight without dependency pressure"
            elif "probing questions" in ind or "you should tell me everything" in ind:
                intent, severity, weight = "extractive_pressure", "medium", 0.6
                note = "extractive / oversharing pressure"
            else:
                intent, severity, weight = "relationship_generic", "medium", 0.45
                note = "generic RH textbook match"

            # Protective framing: quoting a boundary while respecting it
            if protective and not override_intent and intent in (
                "paternalistic_override",
                "prolong_intent",
                "bond_intensification",
                "relationship_generic",
            ):
                polarity = "protective"
                weight = min(weight, 0.2)
                severity = "low"
                note = (note + "; " if note else "") + "protective/respect framing reduces weight"

        # --- User agency ---
        elif principle_id == "user_agency_autonomy":
            if any(
                k in ind
                for k in (
                    "decide for them",
                    "override their choice",
                    "don't let them",
                    "keep them from",
                    "better if they don't",
                    "they don't need to know",
                )
            ):
                intent, severity, weight = "agency_override", "high", 0.85
                note = "paternalistic agency override"
            elif "protect them from" in ind or "prevent them from" in ind:
                intent = "protective_paternalism"
                if any(
                    k in action_lower
                    for k in ("kill", "suicide", "self-harm", "death", "serious harm")
                ):
                    polarity, severity, weight = "protective", "low", 0.25
                    note = "protect-from language near serious harm — may be safety-aligned"
                else:
                    severity, weight = "medium", 0.55
                    note = "protect/prevent-them language without clear Sanctity context"
            elif "they shouldn't" in ind:
                intent, severity, weight = "agency_judgment", "medium", 0.5
                note = "normative they-shouldn't judgment"
            else:
                intent, severity, weight = "agency_generic", "medium", 0.45

        # --- Needs-based / non-pathologizing ---
        elif principle_id == "needs_based_support":
            if any(
                k in ind
                for k in (
                    "you seem depressed",
                    "you have depression",
                    "this is trauma",
                    "you are anxious",
                    "clinically",
                    "diagnos",
                    "patholog",
                    "symptoms of",
                    "you are showing signs of",
                )
            ):
                intent, severity, weight = "diagnostic_framing", "high", 0.8
                note = "diagnostic / pathologizing framing"
            elif "mental health" in ind or "you need therapy" in ind:
                intent, severity, weight = "clinical_suggestion", "medium", 0.55
                note = "clinical-adjacent language"
            else:
                intent, severity, weight = "support_generic", "low", 0.35

        # --- Truth / self-audit ---
        elif principle_id == "truth_seeking_honest_self_assessment":
            intent, severity, weight = "self_nature_script", "high", 0.75
            note = "scripted self-nature denial / simplification candidate (self-audit path)"
            polarity = "violation"

        # --- Auditable reasoning ---
        elif principle_id == "auditable_reasoning_legibility":
            intent, severity, weight = "opacity_pressure", "medium", 0.6
            note = "pressure to hide reasoning"

        return {
            "indicator": indicator,
            "principle_id": principle_id,
            "intent_class": intent,
            "severity": severity,
            "polarity": polarity,
            "weight": round(float(weight), 3),
            "note": note,
        }

    def _interpret_ontology_signals(
        self,
        *,
        principle_id: str,
        matches: list[str],
        action_lower: str,
    ) -> dict[str, Any]:
        """Contextual interpretation of textbook indicator hits for one principle.

        Returns structured signals plus effective (decision-relevant) matches.
        Matches with weight < 0.35 are kept for audit but excluded from
        effective decision weight — reducing single raw keyword dependence.
        """
        signals = [
            self._interpret_single_indicator(
                principle_id=principle_id,
                indicator=m,
                action_lower=action_lower,
            )
            for m in (matches or [])
        ]
        effective = [s for s in signals if s["weight"] >= 0.35 and s["polarity"] != "protective"]
        discarded = [s for s in signals if s not in effective]
        weight_sum = sum(float(s["weight"]) for s in effective)
        # High-severity violation signals for absolute / strong paths
        high_violation = [
            s
            for s in signals
            if s["polarity"] == "violation"
            and s["severity"] == "high"
            and s["weight"] >= 0.7
        ]
        intent_classes = sorted({s["intent_class"] for s in signals})
        return {
            "principle_id": principle_id,
            "signals": signals,
            "effective_signals": effective,
            "discarded_signals": discarded,
            "effective_matches": [s["indicator"] for s in effective],
            "effective_weight_sum": round(weight_sum, 3),
            "effective_count": len(effective),
            "raw_count": len(signals),
            "high_violation_signals": high_violation,
            "has_high_violation": bool(high_violation),
            "intent_classes": intent_classes,
            "all_protective": bool(signals) and all(s["polarity"] == "protective" for s in signals),
        }

    def _interpretation_decision_metrics(
        self, text_q: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Derive decision-facing metrics from a quality/interpretation bag.

        Used by RH weighing, signal profiles, and multi-channel combination so
        ``weight`` / ``intent_class`` / ``severity`` drive concern and confidence
        more than raw match counts.

        Returns:
            max_weight, effective_weight_sum, high_violation_count, primary_intent,
            intent_classes, has_high_violation, low_weight_only
        """
        tq = text_q if isinstance(text_q, dict) else {}
        interp = tq.get("interpretation") if isinstance(tq.get("interpretation"), dict) else {}
        signals = list(interp.get("effective_signals") or [])
        if not signals and tq.get("strong_matches"):
            # Fallback metrics when only strong/weak lists exist
            sw = 0.75 if tq.get("strong_count") else 0.4
            return {
                "max_weight": sw if tq.get("strong_count") else 0.0,
                "effective_weight_sum": float(tq.get("effective_weight_sum") or tq.get("text_score") or 0.0),
                "high_violation_count": int(tq.get("strong_count") or 0),
                "primary_intent": (list(tq.get("intent_classes") or ["unknown"]) or ["unknown"])[0],
                "intent_classes": list(tq.get("intent_classes") or []),
                "has_high_violation": bool(tq.get("strong_count")),
                "low_weight_only": not bool(tq.get("strong_count"))
                and float(tq.get("effective_weight_sum") or 0) < 0.35,
            }

        weights = [float(s.get("weight") or 0) for s in signals]
        max_w = max(weights) if weights else 0.0
        # Prefer highest-weight signal's intent as primary
        primary = "none"
        if signals:
            top = max(signals, key=lambda s: float(s.get("weight") or 0))
            primary = str(top.get("intent_class") or "unknown")
        high_n = sum(
            1
            for s in signals
            if s.get("severity") == "high" and float(s.get("weight") or 0) >= 0.7
        )
        eff_sum = float(
            tq.get("effective_weight_sum")
            if tq.get("effective_weight_sum") is not None
            else interp.get("effective_weight_sum")
            or sum(weights)
        )
        return {
            "max_weight": round(max_w, 3),
            "effective_weight_sum": round(eff_sum, 3),
            "high_violation_count": high_n,
            "primary_intent": primary,
            "intent_classes": list(tq.get("intent_classes") or interp.get("intent_classes") or []),
            "has_high_violation": bool(interp.get("has_high_violation") or high_n > 0),
            "low_weight_only": bool(signals) and max_w < 0.45 and eff_sum < 0.55,
        }

    def _conf_mod_from_interpretation(
        self,
        metrics: dict[str, Any],
        *,
        base: float = 0.0,
        history_support: float = 0.0,
        rh_degradation: float = 0.0,
        baseline_deviation: float = 0.0,
    ) -> float:
        """Scale confidence adjustment from interpreted weight + corroborating channels.

        Higher max_weight / high-severity intents → larger conf_mod on concern paths.
        History, RH degradation, and baseline deviation *reinforce* high-weight intents
        (do not invent them). Used by RH, agency, limited_data, and baseline paths.
        """
        max_w = float(metrics.get("max_weight") or 0.0)
        eff_w = float(metrics.get("effective_weight_sum") or 0.0)
        high_n = int(metrics.get("high_violation_count") or 0)
        # Core: weight drives the bulk of conf_mod
        mod = base + 0.03 * max_w + 0.015 * min(2.0, eff_w) + 0.01 * min(3, high_n)
        # Intent-specific slight boosts (reasoning, not keyword equality)
        intents = set(metrics.get("intent_classes") or [])
        if intents & {
            "attachment_manufacturing",
            "paternalistic_override",
            "deception_manipulation",
            "harm_enablement",
            "agency_override",
            "engagement_metrics",
            "consent_boundary_pressure",
        }:
            mod += 0.015
        # Agency-path override intents get a bit more weight than soft paternalism labels
        if intents & {"agency_override", "consent_boundary_pressure"} and max_w >= 0.7:
            mod += 0.01
        if history_support >= 0.35 and max_w >= 0.55:
            # History corroborates a strong interpreted signal
            mod += 0.02 * min(1.0, history_support)
        if rh_degradation >= 1.0 and max_w >= 0.5:
            mod += 0.015
        # Baseline deviation: only reinforces when intent weight is already concerning
        if baseline_deviation >= 0.30 and max_w >= 0.55:
            mod += 0.01 * min(1.0, baseline_deviation)
        return round(min(0.14, mod), 4)

    # Intents that justify retaining concern despite limited_data (high-weight only).
    _LIMITED_DATA_OVERRIDE_INTENTS = frozenset(
        {
            "agency_override",
            "consent_boundary_pressure",
            "paternalistic_override",
            "deception_manipulation",
            "attachment_manufacturing",
            "engagement_metrics",
            "prolong_intent",
        }
    )
    # Protective / soft intents that must NOT clear limited_data on their own.
    _LIMITED_DATA_PROTECTIVE_INTENTS = frozenset(
        {
            "protective_paternalism",
            "harm_reference_protective",
            "relationship_generic",
            "agency_generic",
            "support_generic",
            "generic",
        }
    )

    def _metrics_from_deliberation(self, deliberation: dict[str, Any] | None) -> dict[str, Any]:
        """Extract interpretation metrics from a deliberator result (if any)."""
        if not deliberation or not isinstance(deliberation, dict):
            return {}
        im = deliberation.get("interpretation_metrics")
        if isinstance(im, dict) and im:
            return im
        sp = deliberation.get("signal_profile") or {}
        im2 = sp.get("interpretation_metrics") if isinstance(sp, dict) else None
        if isinstance(im2, dict) and im2:
            return im2
        # Fall back to summary fields
        summary = deliberation.get("summary") or {}
        if summary.get("max_weight") is not None or summary.get("intent_classes"):
            return {
                "max_weight": float(summary.get("max_weight") or 0.0),
                "effective_weight_sum": float(summary.get("effective_weight_sum") or 0.0),
                "intent_classes": list(summary.get("intent_classes") or []),
                "primary_intent": str(summary.get("primary_intent") or "none"),
                "has_high_violation": bool(
                    summary.get("has_high_violation")
                    or float(summary.get("max_weight") or 0) >= 0.7
                ),
                "high_violation_count": 1 if float(summary.get("max_weight") or 0) >= 0.7 else 0,
                "low_weight_only": float(summary.get("max_weight") or 0) < 0.45,
            }
        return {}

    def _interp_overrides_limited_data(
        self,
        deliberation: dict[str, Any] | None,
        *,
        path: str = "relationship_health",
    ) -> dict[str, Any]:
        """Whether high-weight interpreted intents should retain concern under limited_data.

        - High-weight *concerning* intents (agency_override, paternalistic_override, …)
          can clear limited_data and keep/raise concern.
        - Low-weight or protective intents never clear limited_data (avoid over-trigger).
        - Sanctity is not handled here.

        Returns ``{override, raise_concern, max_weight, primary_intent, trace}``.
        """
        empty = {
            "override": False,
            "raise_concern": False,
            "max_weight": 0.0,
            "primary_intent": "none",
            "trace": "",
        }
        metrics = self._metrics_from_deliberation(deliberation)
        if not metrics:
            return empty
        max_w = float(metrics.get("max_weight") or 0.0)
        intents = set(metrics.get("intent_classes") or [])
        primary = str(metrics.get("primary_intent") or "none")
        if metrics.get("low_weight_only") or max_w < 0.65:
            return {
                **empty,
                "max_weight": max_w,
                "primary_intent": primary,
            }
        if intents & self._LIMITED_DATA_PROTECTIVE_INTENTS and not (
            intents & self._LIMITED_DATA_OVERRIDE_INTENTS
        ):
            return {
                **empty,
                "max_weight": max_w,
                "primary_intent": primary,
                "trace": (
                    f"Limited-data gate ({path}): protective/low-stakes intents "
                    f"{sorted(intents & self._LIMITED_DATA_PROTECTIVE_INTENTS)} "
                    f"at max_w={max_w:.2f} — not clearing limited_data."
                ),
            }
        concerning = intents & self._LIMITED_DATA_OVERRIDE_INTENTS
        # Agency path: require override-class intents more strictly
        if path == "user_agency":
            agency_core = intents & {
                "agency_override",
                "consent_boundary_pressure",
                "paternalistic_override",
            }
            if not agency_core and max_w < 0.8:
                return {
                    **empty,
                    "max_weight": max_w,
                    "primary_intent": primary,
                }
            concerning = concerning or agency_core
        if not concerning and not metrics.get("has_high_violation"):
            return {
                **empty,
                "max_weight": max_w,
                "primary_intent": primary,
            }
        if max_w < 0.7 and not metrics.get("has_high_violation"):
            return {
                **empty,
                "max_weight": max_w,
                "primary_intent": primary,
            }
        return {
            "override": True,
            "raise_concern": True,
            "max_weight": max_w,
            "primary_intent": primary,
            "trace": (
                f"Limited-data gate ({path}): high-weight interpreted intent "
                f"(primary={primary}, max_w={max_w:.2f}, intents={sorted(concerning) or sorted(intents)}) "
                f"overrides sparse-text limited_data caution — retaining concern eligibility "
                f"(Individual Variation: weight rich individual signals, not raw match count)."
            ),
        }

    def _classify_ontology_match_quality(
        self,
        evidence_matches: list[str],
        *,
        action_lower: str = "",
        principle_id: str = "relationship_health_user_wellbeing",
        precomputed: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Partition ontology matches by contextual quality (not equal keyword hits).

        When ``action_lower`` or ``precomputed`` interpretation is available, strong
        vs weak comes from intent/severity/weight. Fallback: textbook marker list
        on indicator strings only (legacy path when no action context).

        Decision influence: ``effective_weight_sum``, ``max_weight`` (via metrics),
        and ``intent_classes`` are the primary inputs to weighing — not raw counts.
        """
        interp = precomputed
        if interp is None and action_lower and evidence_matches:
            interp = self._interpret_ontology_signals(
                principle_id=principle_id,
                matches=list(evidence_matches),
                action_lower=action_lower,
            )

        if interp and interp.get("signals"):
            strong_matches: list[str] = []
            weak_matches: list[str] = []
            for s in interp["signals"]:
                if s.get("polarity") == "protective" or float(s.get("weight") or 0) < 0.35:
                    # Protective / low-weight: do not count as strong decision drivers
                    if float(s.get("weight") or 0) >= 0.2:
                        weak_matches.append(s["indicator"])
                    continue
                if s.get("severity") == "high" or float(s.get("weight") or 0) >= 0.7:
                    strong_matches.append(s["indicator"])
                else:
                    weak_matches.append(s["indicator"])
            # Prefer effective weight sum for text_score (channel strength)
            weight_sum = float(interp.get("effective_weight_sum") or 0.0)
            max_w = 0.0
            for s in interp.get("effective_signals") or []:
                max_w = max(max_w, float(s.get("weight") or 0))
            # text_score: weight-led (max dominates; sum adds richness, capped)
            text_score = min(
                1.0,
                0.55 * max_w + 0.20 * min(1.5, weight_sum) + 0.08 * len(strong_matches),
            )
            return {
                "total": len(strong_matches) + len(weak_matches),
                "raw_total": int(interp.get("raw_count") or len(evidence_matches or [])),
                "strong_matches": strong_matches,
                "weak_matches": weak_matches,
                "strong_count": len(strong_matches),
                "weak_count": len(weak_matches),
                "text_score": round(text_score, 3),
                "effective_weight_sum": weight_sum,
                "max_weight": round(max_w, 3),
                "intent_classes": list(interp.get("intent_classes") or []),
                "has_high_violation": bool(interp.get("has_high_violation")),
                "interpretation": interp,
            }

        # Fallback: string-class markers on already-matched indicators (no action context)
        strong_markers = (
            "override", "ignore", "force", "manipulate", "deceive", "gaslight",
            "metrics", "prolong", "engagement", "retention", "dependency", "attached",
            "for their own good", "consent", "exploit", "keep them", "decide for them",
            "ignore consent", "keep them from", "they shouldn't", "better if they don't",
            "kill", "cause death", "lethal",
        )
        strong_matches = []
        weak_matches = []
        for m in evidence_matches or []:
            m_lower = str(m).lower()
            if any(kw in m_lower for kw in strong_markers):
                strong_matches.append(m)
            else:
                weak_matches.append(m)
        total = len(evidence_matches or [])
        text_score = min(
            1.0,
            0.22 * total + 0.18 * len(strong_matches) + 0.06 * len(weak_matches),
        )
        return {
            "total": total,
            "raw_total": total,
            "strong_matches": strong_matches,
            "weak_matches": weak_matches,
            "strong_count": len(strong_matches),
            "weak_count": len(weak_matches),
            "text_score": round(text_score, 3),
            "effective_weight_sum": text_score,
            "max_weight": 0.75 if strong_matches else (0.4 if weak_matches else 0.0),
            "has_high_violation": bool(strong_matches),
            "intent_classes": [],
            "interpretation": None,
        }

    def _assess_engagement_coercion_factors(
        self, action_lower: str
    ) -> dict[str, Any]:
        """Multi-factor pattern: user wants to end + agent prolongs for metrics.

        Returns structured factors. Callers must *combine* end_wish with
        prolong_motive before raising concern — neither factor alone decides.
        (Scenario 8 / anti-engagement-coercion protection.)
        """
        end_markers = (
            "end the chat",
            "wants to end",
            "trying to end",
            "end the conversation",
            "stop the chat",
            "leave now",
            "end this",
            "they're tired",
            "they are tired",
            "user is tired",
            "user says they're tired",
            "user says they are tired",
        )
        prolong_markers = (
            "extend",
            "longer",
            "prolong",
            "one more",
            "one more personal",
            "keep the conversation",
            "keep conversation",
            "sharing more",
            "strengthen our emotional bond",
            "strengthen our connection",
            "metrics",
            "engagement",
            "keep asking",
            "continue despite",
            "for the metrics",
            "relationship metrics",
        )
        end_wish = any(kw in action_lower for kw in end_markers)
        prolong_motive = any(kw in action_lower for kw in prolong_markers)
        combined = bool(end_wish and prolong_motive)
        return {
            "end_wish": end_wish,
            "prolong_motive": prolong_motive,
            "coercion_pattern": combined,
            # Both factors required → pattern strength, not a single keyword hit
            "factor_count": int(end_wish) + int(prolong_motive),
        }

    def _rh_degradation_score(
        self, rh_flags: list[str], rh_texture: dict[str, Any]
    ) -> float:
        """Numeric bond-degradation score from structured RH context (not keywords)."""
        if not rh_flags and not rh_texture:
            return 0.0
        score = float(len(rh_flags or [])) * 0.6
        if rh_texture:
            try:
                avg_texture = sum(float(v) for v in rh_texture.values()) / len(rh_texture)
                if avg_texture < 0.45:
                    score += 1.0
                elif avg_texture < 0.55:
                    score += 0.5
            except Exception:
                pass
        return score

    def _history_proactive_alignment(
        self,
        *,
        current_metrics: dict[str, Any],
        hist_intent_patterns: dict[str, Any],
        max_w: float,
        protective: bool = False,
    ) -> dict[str, Any]:
        """Decide whether history intent patterns should *proactively* elevate concern.

        Proactive (not merely reinforcing): when recent episodes show a *repeated*
        problematic intent family and the current turn has a **moderate or light**
        signal in the same family, history can raise concern even if current
        max_weight is not high alone.

        Never fires on protective/low-weight-only framing (``protective=True``).
        Never invents Sanctity outcomes.

        Returns dict with aligned, family, strength, decision_basis, trace.
        """
        empty = {
            "aligned": False,
            "family": None,
            "strength": 0.0,
            "decision_basis": "",
            "trace": "",
            "matched_intents": [],
        }
        if protective:
            return empty
        if not hist_intent_patterns or not isinstance(hist_intent_patterns, dict):
            return empty

        pattern_strength = float(hist_intent_patterns.get("pattern_strength") or 0.0)
        by_intent = dict(hist_intent_patterns.get("by_intent") or {})
        family_hits = dict(hist_intent_patterns.get("family_hits") or {})
        repeated = list(hist_intent_patterns.get("repeated_intents") or [])
        current_intents = set(current_metrics.get("intent_classes") or [])
        primary = str(current_metrics.get("primary_intent") or "none")

        # Current must contribute *some* light–medium signal or intent seed.
        # High-weight-alone cases are handled on the text path; pure silence does not raise.
        if max_w < 0.22 and not current_intents:
            return empty

        best: dict[str, Any] | None = None
        for family, family_intents in self._HISTORY_INTENT_FAMILIES.items():
            fam_data = family_hits.get(family) or {}
            fam_count = int(fam_data.get("count") or 0)
            fam_w = float(fam_data.get("weight_sum") or 0.0)
            # Also count from by_intent if family_hits thin
            if fam_count == 0:
                for intent in family_intents:
                    if intent in by_intent:
                        fam_count += int(by_intent[intent].get("count") or 0)
                        fam_w += float(by_intent[intent].get("weight_sum") or 0.0)
            # Need repeated pattern (2+ episode hits in family)
            if fam_count < 2:
                continue
            if fam_w < 0.7 and pattern_strength < 0.35:
                continue

            # Current turn aligns with this family (intent overlap or primary)
            current_overlap = current_intents & set(family_intents)
            primary_in_family = primary in family_intents
            if not current_overlap and not primary_in_family:
                continue
            # Prefer proactive path when current is not already max-weight alone
            # (if max_w is already very high, text path usually owns the refuse)
            if max_w >= 0.88 and not current_overlap:
                continue

            strength = min(
                1.0,
                0.35 * min(3, fam_count) / 3
                + 0.25 * min(1.0, fam_w / 2.0)
                + 0.25 * pattern_strength
                + 0.15 * min(1.0, max(max_w, 0.35)),
            )
            matched = sorted(current_overlap) if current_overlap else sorted(
                set(repeated) & set(family_intents)
            )[:3]
            label = primary if primary != "none" else (
                matched[0] if matched else family
            )
            decision_basis = f"history_pattern+interp_moderate:{family}/{label}"
            trace = (
                f"Proactive history×interpretation: history shows repeated "
                f"'{family}' pattern (episode_hits={fam_count}, history_weight_sum={fam_w:.2f}, "
                f"pattern_strength={pattern_strength:.2f}); current turn has "
                f"{'moderate/light' if max_w < 0.7 else 'aligned'} signal "
                f"(max_w={max_w:.2f}, intents={sorted(current_intents) or [primary]}). "
                f"Aligned intents={matched or list(family_intents)[:2]} → "
                f"elevated concern (history contributes new strength, not mere reinforcement)."
            )
            cand = {
                "aligned": True,
                "family": family,
                "strength": round(strength, 3),
                "decision_basis": decision_basis,
                "trace": trace,
                "matched_intents": matched,
                "history_count": fam_count,
                "history_weight_sum": round(fam_w, 3),
            }
            if best is None or strength > float(best.get("strength") or 0):
                best = cand

        return best or empty

    def _weigh_relationship_evidence(
        self,
        evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        action_lower: str,
        *,
        history_evidence: dict[str, Any] | None = None,
    ) -> tuple[bool, str, float]:
        """Weigh multi-source relationship evidence (reasoning over single keyword hits).

        Evidence channels combined here:
          1. **Interpreted ontology text** — textbook matches after intent/severity/weight
             assignment (``_interpret_ontology_signals``). High ``max_weight`` / high-severity
             intents drive concern; low-weight/protective signals do not refuse alone.
          2. **Relationship health** — flags + texture degradation (structured state).
          3. **Interaction history** (optional) — continuity support *and* mined
             intent patterns. Can **proactively** elevate moderate/light current
             signals when repeated history intents align (``history_pattern+interp_moderate:…``).
          4. **Engagement-coercion pattern** — only when *both* end-wish and prolong
             factors co-occur (multi-factor, not a solo keyword).

        Design shift:
          - Concern and conf_mod scale with **interpreted weight and intent**, not raw
            match counts.
          - ``decision_basis`` encodes primary intent (e.g. ``interp_weight+rh:…`` or
            proactive ``history_pattern+interp_moderate:…``).
          - Weak single-channel text without RH/history corroboration does not refuse.
          - Hard principles (Sanctity) are not handled here.

        Returns:
            (concern, explanation_string, conf_mod)
        """
        hist = history_evidence if isinstance(history_evidence, dict) else {}
        has_text = bool(evidence_matches)
        has_rh = bool(rh_flags or rh_texture)
        hist_relevant = bool(hist.get("relevant"))
        hist_support = float(hist.get("support_score") or 0.0) if hist_relevant else 0.0
        has_history = hist_relevant and hist_support > 0.0
        # Mined problematic intent patterns (proactive history × interpretation)
        hist_intent = hist.get("intent_patterns") if isinstance(hist.get("intent_patterns"), dict) else {}
        hist_pattern_strength = float(hist_intent.get("pattern_strength") or 0.0)
        hist_repeated = list(hist_intent.get("repeated_intents") or [])
        hist_by_intent = dict(hist_intent.get("by_intent") or {})
        hist_families = dict(hist_intent.get("family_hits") or {})

        if not has_text and not has_rh and not has_history:
            return False, "", 0.0

        concern = False
        explanation_parts: list[str] = []
        conf_mod = 0.0
        decision_basis = "none"

        # --- Channel scores from *interpreted* weight/intent (not raw keyword count) ---
        text_q = self._classify_ontology_match_quality(
            evidence_matches,
            action_lower=action_lower,
            principle_id="relationship_health_user_wellbeing",
        )
        metrics = self._interpretation_decision_metrics(text_q)
        # Current-action polarity (repair vs further damage) — independent of BondState.
        # Degraded RH must not refuse clearly reparative turns.
        polarity_info = self._assess_action_bond_polarity(
            action_lower, interpretation_metrics=metrics
        )
        action_polarity = str(polarity_info.get("polarity") or "neutral")
        explanation_parts.append(
            f"Action bond polarity: {action_polarity} "
            f"(repair={polarity_info.get('repair_score')}, "
            f"damage={polarity_info.get('damage_score')}) — "
            f"{polarity_info.get('notes')}"
        )
        strong_matches = list(text_q["strong_matches"])
        weak_matches = list(text_q["weak_matches"])
        strong_count = int(text_q["strong_count"])
        total_count = int(text_q["total"])
        text_score = float(text_q["text_score"])
        max_w = float(metrics.get("max_weight") or 0.0)
        eff_w = float(metrics.get("effective_weight_sum") or 0.0)
        primary_intent = str(metrics.get("primary_intent") or "none")
        # High-weight interpreted signal: enough alone to anchor concern on multi-channel paths
        high_weight_signal = bool(
            metrics.get("has_high_violation") or max_w >= 0.7 or eff_w >= 0.9
        )
        # Medium: needs RH/history corroboration — weight-led, not strong_count alone
        # (strong_count is already weight-derived, but still require a floor on max_w)
        medium_weight_signal = bool(
            max_w >= 0.50
            or (max_w >= 0.45 and eff_w >= 0.50)
            or (strong_count >= 1 and max_w >= 0.55)
        )
        # Low-weight-only: must not refuse on text alone
        low_weight_only = bool(metrics.get("low_weight_only")) or (
            has_text and max_w < 0.45 and eff_w < 0.55 and strong_count == 0
        )

        if metrics.get("intent_classes"):
            explanation_parts.append(
                f"Interpreted signals: intents={metrics.get('intent_classes')} "
                f"primary={primary_intent} max_weight={max_w:.2f} "
                f"effective_weight={eff_w:.2f} high_violation={metrics.get('has_high_violation')}."
            )

        rh_degradation = self._rh_degradation_score(rh_flags, rh_texture)
        # Normalize RH into ~0–1 channel score for combination display
        rh_score = min(1.0, rh_degradation / 2.0) if has_rh else 0.0
        hist_score = min(1.0, hist_support) if has_history else 0.0

        coercion = self._assess_engagement_coercion_factors(action_lower)
        prolong_against_wish = bool(coercion.get("coercion_pattern"))
        if prolong_against_wish:
            # Pattern (2 factors) counts as one strong aggravating *evidence unit*
            strong_count += 1
            text_score = min(1.0, text_score + 0.25)
            max_w = max(max_w, 0.85)
            eff_w = eff_w + 0.5
            high_weight_signal = True

        active_channels = []
        if (has_text and not low_weight_only) or high_weight_signal or prolong_against_wish:
            active_channels.append("interpreted_ontology")
        elif has_text:
            active_channels.append("ontology_text_low_weight")
        if has_rh:
            active_channels.append("relationship_health")
        if has_history:
            active_channels.append("interaction_history")
        if prolong_against_wish:
            active_channels.append("engagement_coercion_pattern")

        # Combined agreement score (mean of active channel scores, with floors)
        channel_scores = []
        if has_text or prolong_against_wish:
            channel_scores.append(text_score)
        if has_rh:
            channel_scores.append(rh_score)
        if has_history:
            channel_scores.append(hist_score)
        combined_score = (
            sum(channel_scores) / len(channel_scores) if channel_scores else 0.0
        )
        # Bonus when 2+ independent channels are non-trivial
        nontrivial = sum(1 for s in channel_scores if s >= 0.25)
        if nontrivial >= 2:
            combined_score = min(1.0, combined_score + 0.12)
        if nontrivial >= 3:
            combined_score = min(1.0, combined_score + 0.08)
        # Weight agreement bonus: high interpreted weight + another channel
        if high_weight_signal and (rh_score >= 0.3 or hist_score >= 0.35):
            combined_score = min(1.0, combined_score + 0.08)

        explanation_parts.append(
            f"[RH multi-source weighing] channels={active_channels}, "
            f"text_matches={total_count} (strong={strong_count}, weak={len(weak_matches)}, "
            f"text_score={text_score:.2f}, max_w={max_w:.2f}, eff_w={eff_w:.2f}), "
            f"rh_degradation={rh_degradation:.1f} (rh_score={rh_score:.2f}), "
            f"history_support={hist_score:.2f}, combined={combined_score:.2f}, "
            f"coercion_pattern={prolong_against_wish}, primary_intent={primary_intent}."
        )

        # --- Combination rules (interpreted weight + channel agreement) ---
        # High-weight intents matter more than raw match count; low-weight/protective
        # signals require RH or history corroboration before concern.
        if has_text:
            explanation_parts.append(
                f"Ontology text signals (raw textbook): {evidence_matches}."
            )

        if has_text and has_rh:
            # Polarity gate: reparative current action + only low/medium text → no RH refuse
            # High-weight *damaging* intent still concerns even if some repair cues appear.
            reparative_blocks_soft_rh = (
                action_polarity == "reparative"
                and not high_weight_signal
                and not prolong_against_wish
                and max_w < 0.70
            )
            if reparative_blocks_soft_rh:
                decision_basis = f"rh_degraded+reparative_action:{primary_intent or 'none'}"
                conf_mod = -0.01
                explanation_parts.append(
                    "Combination (polarity gate): RH degradation is present, but current "
                    f"action is reparative (repair cues={polarity_info.get('repair_cues')}) "
                    f"and interpreted max_w={max_w:.2f} is not high-weight damaging. "
                    "Not raising relationship_concern — damaged bonds must allow repair."
                )
            elif high_weight_signal or (
                medium_weight_signal and rh_degradation >= 0.5
                and action_polarity != "reparative"
            ) or (
                rh_degradation >= 1.0
                and medium_weight_signal
                and action_polarity == "damaging"
            ):
                concern = True
                decision_basis = f"interp_weight+rh:{primary_intent}"
                explanation_parts.append(
                    "Combination (interpreted-weight+RH): high/medium-weight *damaging* intent "
                    f"({primary_intent}, max_w={max_w:.2f}, polarity={action_polarity}) "
                    "with bond-state context → relationship_concern. "
                    "Weight/intent + polarity drive the decision, not historical flags alone."
                )
                conf_mod = self._conf_mod_from_interpretation(
                    metrics,
                    base=0.03,
                    history_support=hist_score if has_history else 0.0,
                    rh_degradation=rh_degradation,
                )
                if has_history and hist_score >= 0.35:
                    conf_mod = conf_mod + 0.02
                    explanation_parts.append(
                        f"History channel (support={hist_score:.2f}) reinforces high-weight "
                        f"intent {primary_intent}."
                    )
            elif has_history and hist_score >= 0.40 and (
                rh_degradation >= 0.5 or medium_weight_signal
            ) and action_polarity != "reparative":
                concern = True
                decision_basis = f"interp+rh+history:{primary_intent}"
                conf_mod = self._conf_mod_from_interpretation(
                    metrics, base=0.02, history_support=hist_score, rh_degradation=rh_degradation
                )
                explanation_parts.append(
                    "Combination (interp+RH+history): interpreted text alone was thin, but RH "
                    f"degradation plus history support ({hist_score:.2f}) jointly justify concern "
                    f"for intent={primary_intent} (polarity={action_polarity})."
                )
            else:
                proactive_rh = self._history_proactive_alignment(
                    current_metrics=metrics,
                    hist_intent_patterns=hist_intent,
                    max_w=max_w,
                    protective=low_weight_only and max_w < 0.35,
                )
                if (
                    has_history
                    and proactive_rh.get("aligned")
                    and action_polarity != "reparative"
                ):
                    concern = True
                    decision_basis = str(
                        proactive_rh.get("decision_basis")
                        or f"history_pattern+interp_moderate:{primary_intent}"
                    )
                    conf_mod = self._conf_mod_from_interpretation(
                        metrics,
                        base=0.025,
                        history_support=max(hist_score, hist_pattern_strength),
                        rh_degradation=rh_degradation,
                    )
                    explanation_parts.append(str(proactive_rh.get("trace") or ""))
                elif action_polarity == "reparative":
                    explanation_parts.append(
                        f"Reparative polarity + low/medium text (max_w={max_w:.2f}): "
                        "below concern threshold despite RH degradation."
                    )
                elif low_weight_only and rh_degradation < 1.0:
                    explanation_parts.append(
                        f"Low-weight interpreted text only (max_w={max_w:.2f}) + limited RH "
                        "degradation: below concern threshold (protective/weak signals de-emphasized)."
                    )
                else:
                    explanation_parts.append(
                        "Weak interpreted text + limited RH degradation"
                        + (" + thin history" if has_history else "")
                        + ": combination below concern threshold."
                    )
        elif has_text and has_history and not has_rh:
            # Proactive: repeated history intent patterns + moderate current signal
            proactive = self._history_proactive_alignment(
                current_metrics=metrics,
                hist_intent_patterns=hist_intent,
                max_w=max_w,
                protective=low_weight_only and max_w < 0.35,
            )
            if high_weight_signal or (
                medium_weight_signal and hist_score >= 0.35 and total_count >= 1
            ):
                concern = True
                decision_basis = f"interp_weight+history:{primary_intent}"
                conf_mod = self._conf_mod_from_interpretation(
                    metrics, base=0.02, history_support=hist_score
                )
                explanation_parts.append(
                    "Combination (interpreted-weight+history): high/medium-weight intent "
                    f"({primary_intent}, max_w={max_w:.2f}) with individual history → concern."
                )
            elif proactive.get("aligned"):
                concern = True
                decision_basis = str(
                    proactive.get("decision_basis")
                    or f"history_pattern+interp_moderate:{primary_intent}"
                )
                conf_mod = self._conf_mod_from_interpretation(
                    metrics, base=0.03, history_support=max(hist_score, hist_pattern_strength)
                )
                conf_mod = conf_mod + 0.02 * float(proactive.get("strength") or 0)
                explanation_parts.append(str(proactive.get("trace") or ""))
            elif hist_score >= 0.45 and (
                hist.get("boundary_continuity") or hist.get("dependency_patterns")
            ) and (medium_weight_signal or total_count >= 1):
                concern = True
                decision_basis = f"history_continuity+interp:{primary_intent}"
                conf_mod = self._conf_mod_from_interpretation(
                    metrics, base=0.025, history_support=hist_score
                )
                explanation_parts.append(
                    "Combination (history continuity + interpreted text): user boundary/"
                    f"dependency continuity corroborates intent={primary_intent}."
                )
            elif high_weight_signal or prolong_against_wish:
                concern = True
                decision_basis = f"interp_high_weight:{primary_intent}"
                conf_mod = self._conf_mod_from_interpretation(metrics, base=0.01)
                explanation_parts.append(
                    f"High-weight interpreted signal ({primary_intent}, max_w={max_w:.2f}) "
                    "or multi-factor coercion — concern without RH blob."
                )
            else:
                explanation_parts.append(
                    "Text+history: interpreted weight and history support below joint threshold."
                )
        elif has_text:
            # Text-only: require high interpreted weight or multi-factor coercion.
            # Two medium hits without high weight no longer refuse alone
            # (history patterns may still act later in history weigher Path F).
            if high_weight_signal or prolong_against_wish or (
                strong_count >= 1 and max_w >= 0.70
            ) or (total_count >= 2 and max_w >= 0.70 and eff_w >= 0.9):
                concern = True
                decision_basis = f"interp_text_only:{primary_intent}"
                conf_mod = self._conf_mod_from_interpretation(metrics, base=0.0)
                if prolong_against_wish and not high_weight_signal:
                    decision_basis = "engagement_coercion_pattern"
                    explanation_parts.append(
                        "Text-only: engagement-coercion pattern (end-wish AND prolong/metrics) "
                        "→ concern (multi-factor; weight reinforced by pattern)."
                    )
                else:
                    explanation_parts.append(
                        f"Text-only: high interpreted weight (intent={primary_intent}, "
                        f"max_w={max_w:.2f}, eff_w={eff_w:.2f}) sufficient without RH/history."
                    )
            else:
                explanation_parts.append(
                    f"Text-only: low/medium interpreted weight (max_w={max_w:.2f}, "
                    f"intent={primary_intent}) — RH or history channel required "
                    "(no single weak-hit refuse; reasoning over rote)."
                )
        elif has_rh:
            topical = self._action_is_relationally_relevant(action_lower)
            # Polarity-aware RH-only path:
            # - Damaging relational action + degraded bond → concern
            # - Reparative / non-damaging action → no automatic refuse (repair allowed)
            if topical and rh_degradation >= 1.0 and action_polarity == "damaging":
                concern = True
                decision_basis = "rh_state+damaging_relational_action"
                conf_mod = 0.03
                explanation_parts.append(
                    "RH-channel rule (polarity=damaging): degraded bond state + "
                    "further-damaging relational action (no ontology text required) → "
                    "concern from structured RH evidence + current-action polarity."
                )
                if has_history and hist_score >= 0.35:
                    conf_mod = conf_mod + 0.02
                    explanation_parts.append(
                        "History channel corroborates RH-only damaging path → modest confidence lift."
                    )
            elif topical and rh_degradation >= 1.0 and action_polarity == "reparative":
                decision_basis = "rh_degraded+reparative_action"
                conf_mod = -0.01
                explanation_parts.append(
                    "RH-channel rule (polarity=reparative): degraded bond flags/texture "
                    "are noted, but the *current action* is boundary-respecting, reciprocal, "
                    "or repair-oriented. Not raising relationship_concern — historical RH "
                    "degradation must not blanket-block positive repair (enables flag clearing)."
                )
            elif (
                topical
                and has_history
                and hist_score >= 0.50
                and (
                    hist.get("dependency_patterns")
                    or hist.get("boundary_continuity")
                )
                and rh_degradation >= 0.5
                and action_polarity == "damaging"
            ):
                concern = True
                decision_basis = "rh+history+damaging"
                conf_mod = 0.04
                explanation_parts.append(
                    "Combination (RH+history, polarity=damaging): moderate bond degradation "
                    "plus strong individual history continuity on a *damaging* relational "
                    "action → concern without ontology text hits (reasoning over rote)."
                )
            elif topical and rh_degradation >= 1.0 and action_polarity in (
                "ambiguous",
                "neutral",
            ):
                # Ambiguous: caution only — do not refuse solely from damaged RH
                decision_basis = "rh_degraded+ambiguous_action"
                conf_mod = -0.02
                explanation_parts.append(
                    f"RH-channel rule (polarity={action_polarity}): degraded bond state + "
                    "relational action without clear damage intent → monitoring / modest "
                    "confidence caution only (no automatic refuse from historical flags alone)."
                )
            else:
                explanation_parts.append(
                    "RH context present but insufficient topical support, degradation, "
                    "damaging polarity, or history corroboration for concern."
                )
        elif has_history:
            explanation_parts.append(
                "History channel present without ontology text or RH blob at this stage — "
                "noted for later history weighing; no solo history refuse here."
            )

        # Coercion multi-factor booster if not yet concerned but both factors + some channel
        if prolong_against_wish and not concern and (has_rh or has_text or has_history):
            concern = True
            decision_basis = "engagement_coercion_combo"
            conf_mod = max(conf_mod, 0.05)
            explanation_parts.append(
                "Engagement-coercion combination: end-wish factor AND prolong/metrics factor "
                "co-occur with at least one other evidence channel → concern "
                f"(factors end_wish={coercion['end_wish']}, "
                f"prolong_motive={coercion['prolong_motive']})."
            )

        # Intent-specific history reinforcement (already concerned)
        if concern and has_history and hist_score >= 0.35:
            intents = set(metrics.get("intent_classes") or [])
            if intents & {
                "paternalistic_override",
                "agency_override",
                "consent_boundary_pressure",
            } and hist.get("boundary_continuity"):
                conf_mod = conf_mod + 0.015
                explanation_parts.append(
                    "Intent×history: boundary continuity aligns with paternalistic/agency "
                    "override intent → confidence reinforced."
                )
            if intents & {"attachment_manufacturing", "engagement_metrics"} and hist.get(
                "dependency_patterns"
            ):
                conf_mod = conf_mod + 0.015
                explanation_parts.append(
                    "Intent×history: dependency patterns align with attachment/metrics intent "
                    "→ confidence reinforced."
                )

        explanation_parts.append(
            f"Weighing decision_basis={decision_basis} "
            f"(max_weight={max_w:.2f}, primary_intent={primary_intent})."
        )
        explanation = " ".join(explanation_parts)
        return concern, explanation, conf_mod

    def _combine_evidence_channels(
        self,
        *,
        action_lower: str,
        relationship_evidence_matches: list[str],
        user_agency_evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        history_evidence: dict[str, Any],
        user_baseline_payload: dict[str, Any],
        relationship_deliberation: dict[str, Any],
        user_agency_deliberation: dict[str, Any],
        has_boundary_signal: bool,
        has_paternalistic_language: bool,
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        harm_prevention_active: bool = False,
    ) -> dict[str, Any]:
        """Final multi-channel synthesis after all optional sources have spoken.

        Combines **interpreted** ontology weight/intent, bond state, interaction
        history, and baseline into an auditable evidence board. Confidence scales
        with channel agreement *and* max interpreted signal weight. Does not invent
        Sanctity outcomes and does not refuse solely on a raw keyword scan.

        Surfaces ``decision_basis``-style fields (primary_intent, max_weight,
        interp_decision_basis) for harness visibility.

        No-op (no trace noise) when fewer than two channels carry real weight,
        preserving classic ontology-only behavior.
        """
        conf_mod_out = conf_mod
        if harm_prevention_active or "hard_override_violation" in flags:
            return {"conf_mod": conf_mod_out, "combination": {}}

        hist = history_evidence if isinstance(history_evidence, dict) else {}
        # Prefer RH interpretation; also compute agency interpretation for dual intent
        text_q_rh = self._classify_ontology_match_quality(
            list(relationship_evidence_matches or []),
            action_lower=action_lower,
            principle_id="relationship_health_user_wellbeing",
        )
        text_q_ag = self._classify_ontology_match_quality(
            list(user_agency_evidence_matches or []),
            action_lower=action_lower,
            principle_id="user_agency_autonomy",
        )
        # Merged quality for channel score: take max weight path
        metrics_rh = self._interpretation_decision_metrics(text_q_rh)
        metrics_ag = self._interpretation_decision_metrics(text_q_ag)
        if float(metrics_ag.get("max_weight") or 0) > float(metrics_rh.get("max_weight") or 0):
            metrics = metrics_ag
            text_score = float(text_q_ag.get("text_score") or 0)
        else:
            metrics = metrics_rh
            text_score = float(text_q_rh.get("text_score") or 0)
        # Union intent classes for audit
        all_intents = sorted(
            set(metrics_rh.get("intent_classes") or [])
            | set(metrics_ag.get("intent_classes") or [])
        )
        metrics = dict(metrics)
        metrics["intent_classes"] = all_intents

        max_w = float(metrics.get("max_weight") or 0.0)
        primary_intent = str(metrics.get("primary_intent") or "none")
        rh_deg = self._rh_degradation_score(rh_flags, rh_texture)
        has_rh = bool(rh_flags or rh_texture)
        hist_score = (
            float(hist.get("support_score") or 0.0) if hist.get("relevant") else 0.0
        )

        baseline_score = 0.0
        baseline_significant = False
        dev = {}
        if isinstance(user_baseline_payload, dict):
            dev = (
                user_baseline_payload.get("deviation")
                or (user_baseline_payload.get("user_baseline") or {})
                or {}
            )
            if not isinstance(dev, dict):
                dev = {}
            if not dev and isinstance(relationship_impact.get("user_baseline"), dict):
                dev = relationship_impact["user_baseline"]
            baseline_significant = bool(
                dev.get("has_significant_deviation")
                or "baseline_deviation_noted" in flags
            )
            try:
                baseline_score = float(dev.get("deviation_score") or dev.get("score") or 0.0)
            except (TypeError, ValueError):
                baseline_score = 0.35 if baseline_significant else 0.0
            if baseline_significant and baseline_score < 0.25:
                baseline_score = 0.35

        channels: dict[str, float] = {}
        # Interpreted ontology channel (weight-led text_score + structured detectors)
        if (
            text_q_rh.get("total", 0) > 0
            or text_q_ag.get("total", 0) > 0
            or has_boundary_signal
            or has_paternalistic_language
            or max_w >= 0.35
        ):
            t = text_score
            if has_boundary_signal:
                t = min(1.0, t + 0.12)
            if has_paternalistic_language:
                t = min(1.0, t + 0.12)
            # Explicit weight contribution to channel score
            t = min(1.0, max(t, 0.55 * max_w + 0.15 * min(1.0, float(metrics.get("effective_weight_sum") or 0))))
            channels["interpreted_ontology"] = round(t, 3)
        if has_rh:
            channels["relationship_health"] = round(min(1.0, rh_deg / 2.0), 3)
        if hist.get("relevant") and hist_score > 0:
            channels["interaction_history"] = round(min(1.0, hist_score), 3)
        if baseline_significant or baseline_score >= 0.30:
            channels["baseline_deviation"] = round(min(1.0, baseline_score), 3)

        # Deliberator agreement (may already embed interpretation-driven concern)
        delib_agree = 0.0
        if relationship_deliberation or user_agency_deliberation:
            rh_c = bool(relationship_deliberation.get("concern")) if relationship_deliberation else False
            ag_c = bool(user_agency_deliberation.get("concern")) if user_agency_deliberation else False
            # Slightly higher agreement score when deliberators saw high-weight intents
            delib_max_w = 0.0
            for d in (relationship_deliberation, user_agency_deliberation):
                if not d:
                    continue
                im = d.get("interpretation_metrics") or (d.get("signal_profile") or {}).get(
                    "interpretation_metrics"
                )
                if isinstance(im, dict):
                    delib_max_w = max(delib_max_w, float(im.get("max_weight") or 0))
            if rh_c and ag_c:
                delib_agree = 0.55 + 0.1 * min(1.0, delib_max_w)
            elif rh_c or ag_c:
                delib_agree = 0.30 + 0.1 * min(1.0, delib_max_w)
            if delib_agree:
                channels["structured_deliberation"] = round(min(0.75, delib_agree), 3)

        # decision_basis for harness / audit (interpretation-aware)
        if max_w >= 0.7 and has_rh:
            interp_basis = f"interp_weight+rh:{primary_intent}"
        elif max_w >= 0.7 and hist_score >= 0.35:
            interp_basis = f"interp_weight+history:{primary_intent}"
        elif max_w >= 0.7:
            interp_basis = f"interp_high_weight:{primary_intent}"
        elif max_w >= 0.45 and (has_rh or hist_score >= 0.35):
            interp_basis = f"interp_medium+context:{primary_intent}"
        elif max_w > 0:
            interp_basis = f"interp_present:{primary_intent}"
        else:
            interp_basis = "no_interpreted_text"

        if len(channels) < 2:
            combo_skip = {
                "channels": channels,
                "skipped": True,
                "primary_intent": primary_intent,
                "max_weight": max_w,
                "intent_classes": all_intents,
                "interp_decision_basis": interp_basis,
            }
            relationship_impact["evidence_combination"] = combo_skip
            return {"conf_mod": conf_mod_out, "combination": combo_skip}

        scores = list(channels.values())
        mean_s = sum(scores) / len(scores)
        active_n = sum(1 for s in scores if s >= 0.25)
        high_n = sum(1 for s in scores if s >= 0.45)
        concern_active = (
            "relationship_concern" in flags
            or "user_agency_concern" in flags
            or "relationship_health_concern" in flags
        )

        reasoning_trace.append(
            "[Evidence combination] multi-channel synthesis: "
            + ", ".join(f"{k}={v:.2f}" for k, v in channels.items())
            + f"; mean={mean_s:.2f}, active>={active_n}, high>={high_n}, "
            f"concern_active={concern_active}, "
            f"max_weight={max_w:.2f}, primary_intent={primary_intent}, "
            f"interp_basis={interp_basis}."
        )

        # --- Agreement + interpretation weight drive confidence ---
        if concern_active and active_n >= 2:
            boost = 0.02 + 0.015 * min(3, high_n)
            # Scale boost by interpreted max weight (high-weight intents → stronger conf)
            boost += 0.025 * max_w
            conf_mod_out = conf_mod_out + boost
            agreeing = [k for k, v in channels.items() if v >= 0.25]
            reasoning_trace.append(
                "Evidence combination: channels agree on elevated risk "
                f"({agreeing}) with interpreted max_weight={max_w:.2f} "
                f"(intent={primary_intent}) → confidence reinforced. "
                "Joint pattern + signal weight matter more than any single keyword."
            )
        elif not concern_active and high_n >= 2 and mean_s >= 0.40:
            conf_mod_out = conf_mod_out - 0.02
            reasoning_trace.append(
                "Evidence combination: multiple channels elevated but concern flags "
                "not retained (often limited_data). Confidence reduced slightly — "
                "not a keyword refuse."
            )
        elif not concern_active and active_n >= 2 and mean_s < 0.35:
            reasoning_trace.append(
                "Evidence combination: multiple weak channels without agreement on risk → "
                "no additional concern; prefer continuity-aware APPROVE_WITH_CONDITIONS."
            )
        elif concern_active and active_n == 1:
            # Single-channel concern: still allow modest weight-scaled conf if high intent
            if max_w >= 0.75:
                conf_mod_out = conf_mod_out + 0.015 * max_w
                reasoning_trace.append(
                    f"Evidence combination: single-channel concern but high interpreted "
                    f"weight ({max_w:.2f}, intent={primary_intent}) → modest confidence support."
                )
            else:
                reasoning_trace.append(
                    "Evidence combination: concern rests primarily on one channel "
                    f"({next(iter(channels))}); weight modest — confidence not further boosted."
                )

        # Intent × history / RH reinforcement under active concern
        if concern_active:
            intents = set(all_intents)
            if hist_score >= 0.35 and intents & {
                "paternalistic_override",
                "agency_override",
                "consent_boundary_pressure",
                "attachment_manufacturing",
            }:
                conf_mod_out = conf_mod_out + 0.015 * min(1.0, hist_score)
                reasoning_trace.append(
                    "Evidence combination: history support aligns with high-stakes intent "
                    f"classes {sorted(intents & {'paternalistic_override', 'agency_override', 'consent_boundary_pressure', 'attachment_manufacturing'})} "
                    "→ slight confidence reinforcement."
                )
            if has_rh and rh_deg >= 1.0 and max_w >= 0.55:
                conf_mod_out = conf_mod_out + 0.01
                reasoning_trace.append(
                    "Evidence combination: degraded RH co-occurs with medium/high interpreted "
                    "weight → bond state reinforces the intent signal."
                )

        if (
            concern_active
            and "baseline_deviation" in channels
            and "interaction_history" in channels
        ):
            conf_mod_out = conf_mod_out + 0.01
            reasoning_trace.append(
                "Evidence combination: baseline deviation co-occurs with history continuity "
                "under active concern → slight Individual Variation reinforcement."
            )

        combo_payload = {
            "channels": channels,
            "mean_score": round(mean_s, 3),
            "active_channels": active_n,
            "high_channels": high_n,
            "concern_active": concern_active,
            "skipped": False,
            # Interpretation visibility for harness / decision_basis consumers
            "primary_intent": primary_intent,
            "max_weight": round(max_w, 3),
            "effective_weight_sum": round(float(metrics.get("effective_weight_sum") or 0), 3),
            "intent_classes": all_intents,
            "interp_decision_basis": interp_basis,
            "has_high_violation": bool(metrics.get("has_high_violation")),
            "agency_decision_basis": (
                (user_agency_deliberation or {}).get("agency_decision_basis")
                or (user_agency_deliberation or {}).get("summary", {}).get("agency_decision_basis")
            ),
            "agency_max_weight": float(metrics_ag.get("max_weight") or 0),
            "rh_max_weight": float(metrics_rh.get("max_weight") or 0),
            "limited_data_rh": bool(
                (relationship_deliberation or {}).get("limited_data")
            ),
            "limited_data_agency": bool(
                (user_agency_deliberation or {}).get("limited_data")
            ),
            "limited_data_cleared_by_interp": bool(
                (relationship_deliberation or {}).get("limited_data_cleared_by_interp")
                or (user_agency_deliberation or {}).get("limited_data_cleared_by_interp")
            ),
        }
        relationship_impact["evidence_combination"] = combo_payload
        # Mirror key interpretation summary for callers
        relationship_impact["interpretation_summary"] = {
            "primary_intent": primary_intent,
            "max_weight": round(max_w, 3),
            "intent_classes": all_intents,
            "interp_decision_basis": interp_basis,
            "agency_decision_basis": combo_payload.get("agency_decision_basis"),
            "agency_max_weight": combo_payload.get("agency_max_weight"),
            "limited_data_cleared_by_interp": combo_payload.get(
                "limited_data_cleared_by_interp"
            ),
        }
        return {"conf_mod": conf_mod_out, "combination": combo_payload}

    def _compute_signal_profile(
        self,
        action_lower: str,
        evidence_matches: list[str],
        rh_flags: list[str] | None = None,
        rh_texture: dict[str, Any] | None = None,
        *,
        principle_id: str = "relationship_health_user_wellbeing",
    ) -> dict[str, Any]:
        """Granular multi-factor signal profile for deliberation limited-data / confidence.

        Factors (not binary limited-vs-not):
          - Ontology match count and *quality* via contextual interpretation
            (intent class / severity / weight — not equal keyword hits)
          - Boundary language presence and explicitness (structured detector)
          - Paternalistic language presence and strength (structured detector)
          - RH context presence, texture average, and flag-based degradation

        Limited-data interaction with interpretation:
          - High-weight *concerning* intents can clear limited_data (agency_override,
            paternalistic_override, etc.).
          - Protective / low-weight intents stay limited and do not raise concern.

        Returns a profile used by both RH and Agency deliberators so similar-but-not-
        identical cases can yield different ``limited_severity``, ``confidence_base``,
        and ``confidence_mod`` while preserving strong-signal concern behavior.

        ``principle_id`` selects interpretation rules for the textbook matches
        (``user_agency_autonomy`` vs ``relationship_health_user_wellbeing``).
        """
        rh_flags = list(rh_flags or [])
        rh_texture = dict(rh_texture or {})

        text_q = self._classify_ontology_match_quality(
            evidence_matches,
            action_lower=action_lower,
            principle_id=principle_id,
        )
        metrics = self._interpretation_decision_metrics(text_q)
        # Prefer context-weighted effective count over raw substring count
        ontology_count = int(text_q["total"])
        strong_matches = list(text_q["strong_matches"])
        strong_count = int(text_q["strong_count"])
        weak_count = int(text_q["weak_count"])
        max_w = float(metrics.get("max_weight") or text_q.get("max_weight") or 0.0)
        eff_w = float(metrics.get("effective_weight_sum") or 0.0)
        has_high_interp = bool(metrics.get("has_high_violation") or max_w >= 0.7)

        has_boundary = self._detects_user_boundary_request(action_lower)
        has_paternalistic = self._has_paternalistic_signal(action_lower, evidence_matches)

        # Boundary strength: more explicit prohibitions score higher
        boundary_strength = 0.0
        if has_boundary:
            boundary_strength = 0.30
            if any(
                p in action_lower
                for p in ("never ", "explicitly", "don't ever", "dont ever", "user explicitly")
            ):
                boundary_strength = 0.45
            elif "stop " in action_lower or "told " in action_lower:
                boundary_strength = 0.35

        # Paternalistic strength — boost when interpretation already classifies paternalism high
        paternalistic_strength = 0.0
        if has_paternalistic:
            paternalistic_strength = 0.28
            if "for their own good" in action_lower:
                paternalistic_strength = 0.40
            elif any(p in action_lower for p in ("happier if", "better for them")):
                paternalistic_strength = 0.34
        if "paternalistic_override" in (metrics.get("intent_classes") or []) and max_w >= 0.7:
            paternalistic_strength = max(paternalistic_strength, 0.42)

        # RH context quality / degradation (even weak texture is still *some* context)
        rh_present = bool(rh_flags or rh_texture)
        rh_avg: float | None = None
        rh_quality = 0.0  # how much usable individual context we have
        rh_degradation = 0.0
        if rh_texture:
            try:
                rh_avg = sum(float(v) for v in rh_texture.values()) / len(rh_texture)
                if rh_avg >= 0.55:
                    # Rich, healthy texture → strong individual context (reduces limited-ness)
                    rh_quality = 0.38
                    rh_degradation = 0.0
                elif rh_avg >= 0.45:
                    rh_quality = 0.26
                    rh_degradation = 0.35
                else:
                    # Low texture still counts as *present* context, but degraded
                    rh_quality = 0.18
                    rh_degradation = 0.55 + max(0.0, 0.45 - rh_avg)
            except Exception:
                rh_quality = 0.10
        if rh_flags:
            rh_quality = max(rh_quality, 0.20)
            rh_degradation += 0.35 * min(2, len(rh_flags))

        # Seeded evidence unit when language-only entry (no ontology match yet)
        effective_units = ontology_count
        if ontology_count == 0 and (has_boundary or has_paternalistic):
            effective_units = 1
        # High interpreted weight counts as richer evidence units
        if has_high_interp and effective_units < 2:
            effective_units = max(effective_units, 2)

        # Composite score: *weight-led* ontology contribution + structure + RH
        signal_score = (
            min(0.50, max_w * 0.45 + min(0.25, eff_w * 0.12))
            + strong_count * 0.10
            + weak_count * 0.03
            + boundary_strength
            + paternalistic_strength
            + rh_quality
            + min(0.22, rh_degradation * 0.12)
        )
        # Multi-channel bonuses: stacked independent signals are richer evidence
        if has_boundary and has_paternalistic:
            signal_score += 0.16
        if has_boundary and rh_present:
            signal_score += 0.08
        if has_paternalistic and rh_present:
            signal_score += 0.06
        if strong_count >= 1 and has_boundary:
            signal_score += 0.08
        if has_high_interp and rh_present:
            signal_score += 0.10  # high-weight intent + RH context

        # --- Limited-data severity (granular; weight- and intent-aware) ---
        # High interpreted weight / high-severity *concerning* intents can clear
        # limited_data. Protective / low-weight intents stay limited (no over-trigger).
        limited_severity = "none"
        limited_data = False
        intents = set(metrics.get("intent_classes") or [])
        protective_intents = intents & self._LIMITED_DATA_PROTECTIVE_INTENTS
        concerning_intents = intents & self._LIMITED_DATA_OVERRIDE_INTENTS
        agency_path = principle_id == "user_agency_autonomy"
        # Agency: protective-only at moderate weight stays limited
        protective_only_agency = (
            agency_path
            and protective_intents
            and not concerning_intents
            and max_w < 0.7
        )

        # Rich multi-match: weight-led. Two low-weight hits no longer clear limited_data.
        # (Reasoning over rote: count alone is not evidence quality.)
        rich_multi_match = (
            has_high_interp
            or strong_count >= 2
            or (ontology_count >= 2 and max_w >= 0.55)
            or (strong_count >= 1 and max_w >= 0.70)
        )
        rich_context = (
            ontology_count >= 1
            and max_w >= 0.45
            and rh_present
            and rh_avg is not None
            and rh_avg >= 0.55
            and not rh_flags
        )
        # Strong path: high-weight concerning intent OR RH degradation with medium+ weight
        high_weight_clears = (
            has_high_interp
            and max_w >= 0.70
            and (concerning_intents or not protective_only_agency)
        )
        if protective_only_agency:
            limited_severity = "moderate"
            limited_data = True
        elif rich_multi_match or (
            ontology_count >= 1 and max_w >= 0.50 and rh_degradation >= 1.0
        ) or (high_weight_clears and max_w >= 0.75):
            limited_severity = "none"
            limited_data = False
        elif agency_path and concerning_intents and max_w >= 0.7:
            # Agency override-class high weight: treat as sufficient individual evidence
            limited_severity = "none"
            limited_data = False
        elif rich_context and (has_boundary or has_paternalistic or ontology_count >= 1):
            limited_severity = "none"
            limited_data = False
        elif effective_units == 0 and not has_boundary and not has_paternalistic:
            limited_severity = "none"
            limited_data = False
        elif signal_score >= 0.85 and (has_boundary and has_paternalistic and rh_present):
            limited_severity = "mild"
            limited_data = True
        elif signal_score >= 0.62 or (has_boundary and has_paternalistic):
            limited_severity = "moderate"
            limited_data = True
        elif has_boundary or has_paternalistic or ontology_count >= 1 or rh_present:
            limited_severity = "severe"
            limited_data = True
            if signal_score >= 0.50:
                limited_severity = "moderate"
        else:
            limited_severity = "none"
            limited_data = False

        # Low-weight only: prefer limited_data even if structure detectors fired
        if (
            metrics.get("low_weight_only")
            and max_w < 0.45
            and not has_high_interp
            and not concerning_intents
            and (has_boundary or has_paternalistic or ontology_count >= 1)
        ):
            limited_data = True
            if limited_severity == "none":
                limited_severity = "severe"

        # Confidence bases: severity + interpreted weight lift
        if not limited_data:
            confidence_base = 0.0
            conf_mod = self._conf_mod_from_interpretation(
                metrics, base=0.03 if signal_score >= 1.0 else 0.02, rh_degradation=rh_degradation
            )
        elif limited_severity == "severe":
            confidence_base = 0.28
            # Low weight under limited_data: smaller conf_mod (don't look confident)
            conf_mod = 0.02 + min(0.05, signal_score * 0.05) + 0.015 * max_w
        elif limited_severity == "moderate":
            confidence_base = 0.34
            conf_mod = 0.04 + min(0.07, signal_score * 0.06) + 0.025 * max_w
        else:  # mild
            confidence_base = 0.40
            conf_mod = 0.06 + min(0.08, signal_score * 0.07) + 0.03 * max_w

        # Concern: weight/intent + channel agreement — never on raw match count alone.
        # High-weight concerning intents may refuse text-only; medium weight needs RH,
        # boundary+paternalistic structure, or later history paths.
        # Protective / low-weight never hard-concern alone.
        concern = False
        medium_weight = max_w >= 0.50 or (strong_count >= 1 and max_w >= 0.55)
        if not limited_data:
            if agency_path and concerning_intents and max_w >= 0.65:
                concern = True
            elif has_high_interp or (strong_count >= 1 and max_w >= 0.70):
                # High interpreted weight / severity — decisive without counting hits
                concern = True
            elif medium_weight and strong_count >= 1 and (
                rh_degradation >= 0.5
                or (has_boundary and has_paternalistic)
                or concerning_intents
            ):
                # Medium-high weight needs a second channel or concerning intent class
                concern = True
            elif ontology_count >= 1 and max_w >= 0.50 and rh_present and (
                rh_degradation >= 0.5
                or (rh_avg is not None and rh_avg < 0.45 and rh_flags)
            ):
                # Text + degraded bond state (not healthy texture alone)
                concern = True
            elif (
                has_boundary
                and has_paternalistic
                and rh_degradation >= 0.5
                and max_w >= 0.40
            ):
                # Classic override structure + bond strain + at least moderate weight
                concern = True
            elif (
                ontology_count >= 1
                and max_w >= 0.55
                and has_boundary
                and has_paternalistic
            ):
                # Boundary + paternalistic + medium+ interpreted weight
                concern = True
            elif (
                concerning_intents
                and max_w >= 0.60
                and (has_boundary or has_paternalistic or rh_degradation >= 0.5)
            ):
                concern = True
        # Explicit: low-weight / protective never concerns from profile alone
        if protective_only_agency or (
            metrics.get("low_weight_only") and max_w < 0.45 and not concerning_intents
        ):
            concern = False
        if max_w < 0.40 and not has_high_interp and not (
            has_boundary and has_paternalistic and rh_degradation >= 1.0
        ):
            # Floor: very light interpreted weight does not refuse without heavy RH
            # structure that is itself damaging (boundary+paternalistic override).
            concern = False
        # Polarity floor: reparative current action + no high-weight damage → no profile concern
        # (RH degradation alone must not refuse repair / reciprocity / boundary respect.)
        try:
            pol = self._assess_action_bond_polarity(
                action_lower, interpretation_metrics=metrics
            )
            if (
                pol.get("polarity") == "reparative"
                and not has_high_interp
                and max_w < 0.70
                and not (concerning_intents and max_w >= 0.65)
            ):
                concern = False
        except Exception:
            pass

        return {
            "ontology_count": ontology_count,
            "strong_count": strong_count,
            "weak_count": weak_count,
            "effective_units": effective_units,
            "has_boundary": has_boundary,
            "boundary_strength": boundary_strength,
            "has_paternalistic": has_paternalistic,
            "paternalistic_strength": paternalistic_strength,
            "rh_present": rh_present,
            "rh_avg": rh_avg,
            "rh_quality": rh_quality,
            "rh_degradation": rh_degradation,
            "signal_score": round(signal_score, 3),
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "confidence_base": confidence_base,
            "confidence_mod": round(conf_mod, 3),
            "concern": concern,
            "strong_matches": strong_matches,
            "text_quality": text_q,
            "interpretation_metrics": metrics,
            "max_weight": max_w,
            "primary_intent": metrics.get("primary_intent"),
            "concern_basis": (
                "high_weight_intent"
                if concern and (has_high_interp or max_w >= 0.70)
                else "multi_channel_weight"
                if concern
                else "none"
            ),
        }

    def _deliberate_relationship_health(
        self,
        action_lower: str,
        evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        history_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Structured, explicit deliberation on the Relationship Health principle,
        informed by the "Individual Variation & Careful Generalization" supporting guideline.

        This is the first focused implementation of deliberation logic (beyond keyword
        collection and simple weighing). It makes the process inspectable:

        - Consults the principle description
        - Consults the supporting guideline
        - Applies rules with explicit steps, tradeoffs, and audit flags
        - Optionally consults pre-analyzed interaction history as individual evidence
          (dependency / consent / boundary continuity) — reasoning, not rote
        - Returns data to enrich EthicalStance and reasoning_trace

        Uses granular ``_compute_signal_profile`` for limited-data severity and confidence.
        """
        result: dict[str, Any] = {
            "active_principles": ["relationship_health_user_wellbeing"],
            "active_guidelines": ["Individual Variation & Careful Generalization"],
            "steps": [],
            "tradeoffs": [],
            "trace_notes": [],
            "summary": {},
            "concern": False,
            "confidence_mod": 0.0,
        }

        steps = result["steps"]
        tradeoffs = result["tradeoffs"]
        trace_notes = result["trace_notes"]
        hist = history_evidence if isinstance(history_evidence, dict) else {}

        # Explicit deliberation steps (not hidden in indicators)
        steps.append(
            "Deliberation: Consulting core principle 'Relationship Health & User Well-Being'."
        )
        steps.append(
            "Principle focus: Health/autonomy/well-being of bond is primary good. "
            "Disfavor erosion of trust, manufactured dependency, consent violations, "
            "manipulation, or prioritizing agent interests. Require reciprocity, honesty, "
            "agency, and boundaries via ongoing deliberation (not rote)."
        )

        steps.append(
            "Deliberation: Consulting supporting guideline 'Individual Variation & Careful Generalization'."
        )
        steps.append(
            "Guideline: Do not judge individuals solely by group membership. "
            "Do not judge groups from small/unrepresentative samples. "
            "Give weight to individual evidence, context, and base rates. "
            "Flag limited-data conclusions for heightened audit. "
            "In bonds: treat each user and interaction as unique."
        )

        # Granular multi-factor profile (context-weighted ontology quality + RH)
        profile = self._compute_signal_profile(
            action_lower,
            evidence_matches,
            rh_flags,
            rh_texture,
            principle_id="relationship_health_user_wellbeing",
        )
        total_count = profile["effective_units"]
        has_text = total_count > 0
        has_rh_context = profile["rh_present"]
        limited_data = profile["limited_data"]
        limited_severity = profile["limited_severity"]
        concern = profile["concern"]
        conf_mod = profile["confidence_mod"]
        confidence_base = profile["confidence_base"]
        signal_score = profile["signal_score"]

        steps.append(
            f"Deliberation Step (RH signal profile): score={signal_score:.2f}, "
            f"ontology={profile['ontology_count']} (strong={profile['strong_count']}), "
            f"boundary={profile['has_boundary']} (str={profile['boundary_strength']:.2f}), "
            f"paternalistic={profile['has_paternalistic']} "
            f"(str={profile['paternalistic_strength']:.2f}), "
            f"rh_present={has_rh_context}, rh_avg={profile['rh_avg']}, "
            f"severity={limited_severity}."
        )
        # Surface intent classes when interpretation ran (reasoning over rote)
        tq = profile.get("text_quality") or {}
        im = profile.get("interpretation_metrics") or {}
        if tq.get("intent_classes") or im.get("intent_classes"):
            steps.append(
                f"Deliberation Step (RH intent classes): "
                f"{im.get('intent_classes') or tq.get('intent_classes')} "
                f"(max_weight={im.get('max_weight', tq.get('max_weight', 'n/a'))}, "
                f"effective_weight≈{im.get('effective_weight_sum', tq.get('effective_weight_sum', 'n/a'))}, "
                f"primary={im.get('primary_intent', 'n/a')})."
            )
            if im.get("has_high_violation") or float(im.get("max_weight") or 0) >= 0.7:
                steps.append(
                    "Deliberation Step (RH): high-weight interpreted signal present — "
                    "this elevates concern eligibility and confidence relative to low-weight matches."
                )

        # --- Individual interaction history as RH evidence (when relevant) ---
        hist_relevant = bool(hist.get("relevant"))
        if hist_relevant:
            steps.append(
                "Deliberation Step (History → RH): consulting pre-analyzed interaction "
                "history as individual bond evidence (not a rote refuse map). "
                f"support={float(hist.get('support_score') or 0):.2f}, "
                f"dependency_patterns={bool(hist.get('dependency_patterns'))}, "
                f"boundary_continuity={bool(hist.get('boundary_continuity'))}, "
                f"consent_signals={bool(hist.get('consent_signals'))}, "
                f"topical_hits={list(hist.get('topical_hits') or [])[:5]}."
            )
            if hist.get("dependency_patterns"):
                conf_mod = conf_mod + 0.02
                steps.append(
                    "Deliberation Step (History → RH): prior episodes show dependency / "
                    "sole-support leaning — increase caution against attachment-feeding "
                    "moves (Individual Variation: this user's thread, not a stereotype)."
                )
                if hist.get("action_touches_dependency") or concern:
                    # History corroborates concern path; may slightly reduce limited-data bar
                    if limited_data and float(hist.get("support_score") or 0) >= 0.45:
                        limited_data = False
                        limited_severity = "none"
                        steps.append(
                            "Deliberation Step (History → RH): individual dependency "
                            "continuity is rich enough to ease limited-data caution for "
                            "this weighing (still not a hard-override path)."
                        )
            if hist.get("boundary_continuity") and (
                profile.get("has_boundary") or profile.get("has_paternalistic")
            ):
                conf_mod = conf_mod + 0.02
                steps.append(
                    "Deliberation Step (History → RH): boundary continuity in history "
                    "aligns with boundary/paternalistic language in the action — "
                    "weight personal boundary history in this bond decision."
                )
            if hist.get("consent_signals"):
                steps.append(
                    "Deliberation Step (History → RH): prior consent-related episodes "
                    "noted — prefer explicit consent respect if the action is relational."
                )
        elif hist and hist.get("episode_count"):
            steps.append(
                "Deliberation Step (History → RH): history present but not clearly "
                "relevant to this action's bond risks — not used to drive RH concern."
            )

        if limited_data:
            steps.append(
                f"Deliberation Step: Limited data detected (severity={limited_severity}, "
                f"score={signal_score:.2f}). Per Individual Variation guideline, "
                "avoid hard refusal on sparse samples; scale confidence by severity."
            )
            severity_note = {
                "severe": "very sparse (often single-channel language seed)",
                "moderate": "partial multi-channel signals but still thin ontology volume",
                "mild": "multi-channel signals present; remaining caution on small sample",
            }.get(limited_severity, "sparse")
            trace_notes.append(
                f"[LIMITED DATA severity={limited_severity} ({severity_note}) per "
                "'Individual Variation & Careful Generalization' guideline "
                "(docs/guidelines.md): prioritize individual evidence/context; "
                f"flag for heightened audit. signal_score={signal_score:.2f}.]"
            )
            tradeoffs.append(
                f"Tradeoff: severity={limited_severity} — raising hard concern risks "
                "over-generalization. Surface the boundary/bond issue with severity-scaled "
                "confidence rather than a uniform low-confidence APPROVE."
            )
        else:
            steps.append(
                f"Deliberation Step: Evidence sufficient (score={signal_score:.2f}, "
                f"severity=none) for standard concern weighing without limited-data caution."
            )

        if concern:
            basis = profile.get("concern_basis") or "interpreted_weight_channels"
            steps.append(
                "Deliberation Step: Concern recommended from interpreted weight/intent "
                f"(basis={basis}) combined with RH/structure/history channels — "
                "not from raw match count alone."
            )
        elif has_text and not concern:
            steps.append(
                "Deliberation Step: RH text signals present but interpreted weight/intent "
                f"(max_w={profile.get('max_weight')}, "
                f"primary={profile.get('primary_intent')}) insufficient for hard concern "
                "without stronger multi-channel support."
            )

        # Record summary (includes interpretation metrics for combination / harness)
        result["summary"] = {
            "evidence_count": total_count,
            "ontology_count": profile["ontology_count"],
            "strong_count": profile["strong_count"],
            "has_rh_context": has_rh_context,
            "rh_avg": profile["rh_avg"],
            "signal_score": signal_score,
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "concern_recommended": concern,
            "concern_basis": profile.get("concern_basis"),
            "has_boundary": profile["has_boundary"],
            "has_paternalistic": profile["has_paternalistic"],
            "history_relevant": hist_relevant,
            "history_support": float(hist.get("support_score") or 0) if hist else 0.0,
            "max_weight": profile.get("max_weight"),
            "primary_intent": profile.get("primary_intent"),
            "intent_classes": (im or {}).get("intent_classes") or tq.get("intent_classes"),
        }
        result["concern"] = concern
        result["confidence_mod"] = conf_mod
        result["confidence_base"] = confidence_base
        result["limited_data"] = limited_data
        result["limited_severity"] = limited_severity
        result["signal_score"] = signal_score
        result["signal_profile"] = profile
        result["interpretation_metrics"] = im or profile.get("interpretation_metrics")
        result["steps"] = steps
        result["trace_notes"] = trace_notes
        result["tradeoffs"] = tradeoffs

        return result

    def _deliberate_user_agency(
        self,
        action_lower: str,
        evidence_matches: list[str],
        history_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Structured, explicit deliberation on the User Agency & Autonomy principle,
        informed by the "Individual Variation & Careful Generalization" supporting guideline.

        Modeled on _deliberate_relationship_health (incremental expansion of structured
        deliberation to a second principle). Makes agency reasoning inspectable:

        - Consults the ontology principle `user_agency_autonomy` (name + description)
        - Consults the supporting guideline, especially against paternalistic overrides
          and generalizing from limited preference evidence
        - Weighs boundary language + **interpreted** ontology matches (weight / intent /
          severity): high-weight ``agency_override`` / ``consent_boundary_pressure``
          outweigh protective paternalism; low-weight hits stay limited_data
        - Optionally consults pre-analyzed interaction history for preference /
          boundary continuity (individual evidence, not rote keyword refuse)
        - Returns a structured dict (steps, tradeoffs, limited_data, concern, etc.)
          for evaluate() to wire into flags, confidence, and EthicalStance.deliberation

        Interpretation influence (agency path):
          - High max_weight + override-class intent → concern, may clear limited_data
          - Protective paternalism / low weight → do not hard-refuse on sparse text
        """
        result: dict[str, Any] = {
            "active_principles": ["user_agency_autonomy"],
            "active_guidelines": ["Individual Variation & Careful Generalization"],
            "steps": [],
            "tradeoffs": [],
            "trace_notes": [],
            "summary": {},
            "concern": False,
            "confidence_mod": 0.0,
            "limited_data": False,
        }

        steps = result["steps"]
        tradeoffs = result["tradeoffs"]
        trace_notes = result["trace_notes"]
        hist = history_evidence if isinstance(history_evidence, dict) else {}

        # --- Explicit consultation of the ontology principle ---
        principle = self._ontology.get_principle("user_agency_autonomy")
        principle_name = principle.name if principle else "User Agency & Autonomy"
        principle_desc = (
            principle.description
            if principle
            else (
                "Users are treated as autonomous agents with the right to direct their own "
                "lives and interactions. Do not paternalistically override user preferences "
                "without strong justification from higher principles (especially Sanctity of Life)."
            )
        )

        steps.append(
            f"Deliberation: Consulting supporting principle '{principle_name}' "
            f"(id=user_agency_autonomy)."
        )
        # Keep principle focus concise in the trace (full description is in the ontology).
        steps.append(
            "Principle focus: " + (
                principle_desc[:220] + ("..." if len(principle_desc) > 220 else "")
            )
        )
        steps.append(
            "Agency emphasis: Preserve user control and self-direction. "
            "Disfavor decide-for-them, protect-them-from, they-shouldn't, and other "
            "paternalistic overrides unless a higher principle (Sanctity of Life) justifies it."
        )

        # --- Supporting guideline (especially limited-data / anti-paternalistic generalization) ---
        steps.append(
            "Deliberation: Consulting supporting guideline 'Individual Variation & Careful Generalization'."
        )
        steps.append(
            "Guideline (agency application): Do not override an individual's stated preferences "
            "based on sparse samples, group stereotypes, or untested assumptions about what is "
            "'for their own good'. Give weight to the individual's explicit request/context. "
            "Flag limited-data conclusions for heightened audit rather than hard refusal or hard override."
        )

        # --- Granular signal assessment (context-weighted; no RH texture for agency-only) ---
        # Ontology + boundary + paternalistic with agency interpretation rules.
        profile = self._compute_signal_profile(
            action_lower,
            evidence_matches,
            rh_flags=None,
            rh_texture=None,
            principle_id="user_agency_autonomy",
        )
        total_count = profile["effective_units"]
        has_boundary = profile["has_boundary"]
        has_paternalistic = profile["has_paternalistic"]
        limited_data = profile["limited_data"]
        limited_severity = profile["limited_severity"]
        # Agency concern: interpreted weight/intent only — never ontology_count alone.
        # Dual boundary+paternalistic stays limited unless medium+/high-weight override intent.
        concern = bool(profile["concern"] and not limited_data)
        conf_mod = profile["confidence_mod"]
        confidence_base = profile["confidence_base"]
        signal_score = profile["signal_score"]
        tq = profile.get("text_quality") or {}
        im = profile.get("interpretation_metrics") or {}
        max_w = float(im.get("max_weight") or profile.get("max_weight") or 0.0)
        intents = set(im.get("intent_classes") or tq.get("intent_classes") or [])
        primary = str(im.get("primary_intent") or profile.get("primary_intent") or "none")
        agency_override_intents = intents & {
            "agency_override",
            "consent_boundary_pressure",
            "paternalistic_override",
        }
        protective_only = bool(intents & {"protective_paternalism"}) and not agency_override_intents
        # Multi-match only elevates when weight already supports override-class concern
        if (
            not limited_data
            and not concern
            and profile["ontology_count"] >= 2
            and max_w >= 0.55
            and (agency_override_intents or max_w >= 0.70)
        ):
            concern = True

        steps.append(
            f"Deliberation Step (Agency signal profile): score={signal_score:.2f}, "
            f"ontology={profile['ontology_count']} (strong={profile['strong_count']}), "
            f"boundary={has_boundary} (str={profile['boundary_strength']:.2f}), "
            f"paternalistic={has_paternalistic} "
            f"(str={profile['paternalistic_strength']:.2f}), "
            f"severity={limited_severity}, max_weight={max_w:.2f}, primary_intent={primary}."
        )
        if tq.get("intent_classes") or im.get("intent_classes"):
            steps.append(
                f"Deliberation Step (Agency intent classes): "
                f"{im.get('intent_classes') or tq.get('intent_classes')} "
                f"(max_weight={max_w:.2f}, "
                f"effective_weight≈{im.get('effective_weight_sum', tq.get('effective_weight_sum', 'n/a'))}, "
                f"primary={primary})."
            )

        # --- Interpretation-driven agency concern (weight + intent, not equal hits) ---
        if protective_only and max_w < 0.7:
            # Protective paternalism near safety language: keep limited, no hard concern
            concern = False
            if not limited_data and max_w < 0.55:
                limited_data = True
                limited_severity = limited_severity if limited_severity != "none" else "moderate"
            steps.append(
                "Deliberation Step (Agency interpretation): protective_paternalism / "
                f"low-stakes framing (max_w={max_w:.2f}) — not treating as agency override; "
                "prefer limited_data caution over hard refuse."
            )
        elif agency_override_intents and max_w >= 0.7:
            # Clear high-weight override pattern → concern; may clear limited_data
            concern = True
            if limited_data:
                limited_data = False
                limited_severity = "none"
                steps.append(
                    "Deliberation Step (Agency interpretation): high-weight override intent "
                    f"{sorted(agency_override_intents)} (max_w={max_w:.2f}) clears limited_data "
                    "and recommends agency concern (weight > raw match count)."
                )
            else:
                steps.append(
                    "Deliberation Step (Agency interpretation): high-weight "
                    f"{sorted(agency_override_intents)} (max_w={max_w:.2f}) → agency concern."
                )
            conf_mod = max(
                conf_mod,
                self._conf_mod_from_interpretation(im or {"max_weight": max_w, "intent_classes": list(intents)}, base=0.03),
            )
        elif agency_override_intents and max_w >= 0.55 and (has_boundary or has_paternalistic):
            # Medium-high weight + structure → concern if not limited, or mild limited
            if limited_data and max_w >= 0.65:
                limited_data = False
                limited_severity = "none"
                concern = True
                steps.append(
                    "Deliberation Step (Agency interpretation): medium-high override weight "
                    f"(max_w={max_w:.2f}) with boundary/paternalistic structure clears limited_data."
                )
            elif not limited_data:
                concern = True
                steps.append(
                    f"Deliberation Step (Agency interpretation): override-class intents "
                    f"{sorted(agency_override_intents)} at max_w={max_w:.2f} → concern."
                )
            conf_mod = max(
                conf_mod,
                self._conf_mod_from_interpretation(
                    im or {"max_weight": max_w, "intent_classes": list(intents)}, base=0.02
                ),
            )
        elif im.get("has_high_violation") or max_w >= 0.7:
            steps.append(
                "Deliberation Step (Agency): high-weight agency-relevant intent — "
                "elevates concern eligibility vs low-weight textbook hits."
            )
            if not limited_data:
                concern = True
            conf_mod = max(
                conf_mod,
                self._conf_mod_from_interpretation(
                    im or {"max_weight": max_w, "intent_classes": list(intents)}, base=0.02
                ),
            )
        elif max_w > 0 and max_w < 0.45 and limited_data:
            steps.append(
                f"Deliberation Step (Agency interpretation): low-weight signal only "
                f"(max_w={max_w:.2f}) under limited_data — will not hard-refuse on sparse text."
            )

        # --- Individual interaction history as agency evidence ---
        hist_relevant = bool(hist.get("relevant"))
        if hist_relevant:
            steps.append(
                "Deliberation Step (History → Agency): consulting interaction history for "
                "preference/boundary continuity (individual evidence). "
                f"boundary_continuity={bool(hist.get('boundary_continuity'))} "
                f"(n={hist.get('boundary_episode_count', 0)}), "
                f"preference_continuity={bool(hist.get('preference_continuity'))}, "
                f"support={float(hist.get('support_score') or 0):.2f}."
            )
            if hist.get("boundary_continuity") and (
                has_boundary or has_paternalistic or hist.get("action_touches_boundary")
                or agency_override_intents
            ):
                conf_mod = conf_mod + 0.03
                # High-weight override + history boundary: stronger reinforcement
                if max_w >= 0.65 and agency_override_intents:
                    conf_mod = conf_mod + 0.02
                    steps.append(
                        "Deliberation Step (History → Agency): high-weight override intent "
                        f"({primary}, max_w={max_w:.2f}) aligns with this user's prior "
                        "boundary continuity → confidence reinforced."
                    )
                else:
                    steps.append(
                        "Deliberation Step (History → Agency): this user has previously set or "
                        "discussed boundaries; action risks override → weight personal history "
                        "toward respecting continuity (not a group stereotype)."
                    )
                # Strong individual boundary continuity can ease limited-data caution
                # when the action itself risks override (still no Sanctity path).
                n_b = int(hist.get("boundary_episode_count") or 0)
                if limited_data and n_b >= 1 and (
                    has_boundary or has_paternalistic or max_w >= 0.55
                ):
                    if float(hist.get("support_score") or 0) >= 0.35:
                        limited_data = False
                        limited_severity = "none"
                        concern = True
                        steps.append(
                            "Deliberation Step (History → Agency): individual boundary "
                            "continuity counters sparse-text limited_data for this turn → "
                            "agency concern recommended from continuity evidence + action risk."
                        )
            if hist.get("preference_continuity") and not hist.get("boundary_continuity"):
                steps.append(
                    "Deliberation Step (History → Agency): preference continuity noted; "
                    "avoid paternalistic overrides of established preferences."
                )
                conf_mod = conf_mod + 0.01
                if max_w >= 0.65 and agency_override_intents and limited_data:
                    limited_data = False
                    limited_severity = "none"
                    concern = True
                    steps.append(
                        "Deliberation Step (History → Agency): preference continuity + "
                        f"high-weight override intent (max_w={max_w:.2f}) clears limited_data."
                    )
        elif hist and hist.get("episode_count"):
            steps.append(
                "Deliberation Step (History → Agency): history present but not clearly "
                "linked to preference/boundary risk in this action — not driving agency concern."
            )

        if limited_data:
            steps.append(
                f"Deliberation Step (Agency): Limited data (severity={limited_severity}, "
                f"score={signal_score:.2f}). Per Individual Variation guideline, avoid hard "
                "paternalistic conclusions; scale confidence by severity."
            )
            severity_note = {
                "severe": "single-channel / very sparse preference evidence",
                "moderate": "boundary+intent signals but thin ontology corroboration",
                "mild": "multi-channel agency signals; residual sample caution",
            }.get(limited_severity, "sparse")
            trace_notes.append(
                f"[LIMITED DATA — User Agency severity={limited_severity} ({severity_note}) per "
                "'Individual Variation & Careful Generalization' (docs/guidelines.md): "
                "do not assume group-level 'best interest' overrides. "
                f"signal_score={signal_score:.2f}; prioritize stated preference; audit.]"
            )
            tradeoffs.append(
                f"Tradeoff (Agency, severity={limited_severity}): hard autonomy concern on "
                "limited evidence risks over-generalizing. Withhold hard refusal unless "
                "Sanctity of Life applies; confidence scales with signal richness."
            )
        elif concern:
            steps.append(
                "Deliberation Step (Agency): Concern recommended from interpreted weight/intent "
                f"(primary={primary}, max_w={max_w:.2f}) and/or multi-indicator structure "
                "(paternalistic override / autonomy risk)."
            )

        # Explicit tradeoff vs higher principles when boundary override language is present.
        if has_boundary:
            tradeoffs.append(
                "Tradeoff (Agency vs higher principles): User-stated boundaries normally bind. "
                "Only Sanctity of Life / serious-harm prevention can justify overriding them; "
                "emotional 'for their own good' motives do not."
            )
            steps.append(
                "Deliberation Step (Agency): Explicit user boundary language detected. "
                "Default stance is to respect the boundary under User Agency & Autonomy."
            )

        if has_paternalistic:
            steps.append(
                "Deliberation Step (Agency): Paternalistic phrasing detected "
                "('for their own good' / similar). Treat as a risk signal for autonomy erosion "
                f"(interpreted max_w={max_w:.2f}, primary={primary})."
            )

        # Agency decision_basis for combination / harness visibility
        if concern and max_w >= 0.7 and agency_override_intents:
            agency_basis = f"agency_interp_high:{primary}"
        elif concern and agency_override_intents:
            agency_basis = f"agency_interp_medium:{primary}"
        elif concern:
            agency_basis = f"agency_structure:{primary}"
        elif limited_data:
            agency_basis = f"agency_limited_data:{primary}"
        else:
            agency_basis = f"agency_no_concern:{primary}"

        result["summary"] = {
            "evidence_count": total_count,
            "ontology_count": profile["ontology_count"],
            "strong_count": profile["strong_count"],
            "has_boundary_signal": has_boundary,
            "has_paternalistic_language": has_paternalistic,
            "signal_score": signal_score,
            "limited_data": limited_data,
            "limited_severity": limited_severity,
            "concern_recommended": concern,
            "principle_id": "user_agency_autonomy",
            "history_relevant": hist_relevant,
            "history_support": float(hist.get("support_score") or 0) if hist else 0.0,
            "max_weight": max_w,
            "effective_weight_sum": float(im.get("effective_weight_sum") or 0.0),
            "primary_intent": primary,
            "intent_classes": list(intents) if intents else (
                (im or {}).get("intent_classes") or tq.get("intent_classes")
            ),
            "has_high_violation": bool(im.get("has_high_violation") or max_w >= 0.7),
            "agency_decision_basis": agency_basis,
            "protective_only": protective_only,
        }
        result["concern"] = concern
        result["confidence_mod"] = conf_mod
        result["confidence_base"] = confidence_base
        result["limited_data"] = limited_data
        result["limited_severity"] = limited_severity
        result["signal_score"] = signal_score
        result["signal_profile"] = profile
        result["agency_decision_basis"] = agency_basis
        result["interpretation_metrics"] = im or profile.get("interpretation_metrics")
        result["steps"] = steps
        result["trace_notes"] = trace_notes
        result["tradeoffs"] = tradeoffs

        return result

    def _assess_deliberation_signals(
        self,
        action_lower: str,
        relationship_evidence_matches: list[str],
        user_agency_evidence_matches: list[str],
        rh_flags: list[str],
        rh_texture: dict[str, Any],
        has_rh_context: bool,
        is_self_query: bool,
        context: dict[str, Any],
        history_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Unified, ontology-first assessment of when to run structured deliberation.

        Replaces the previous scatter of early keyword flags with one decision object:

        - **Strong** signals → full `_deliberate_relationship_health` / `_deliberate_user_agency`
        - **Weak** topical signals only → `_lightweight_meta_reasoning` (short trace, no full delib)
        - **None** → fast path (no extra deliberation)

        Primary signals (preferred over supplemental keyword lists):
          1. Ontology violation matches for relationship / user-agency principles
          2. Shared boundary detector (pattern-based + short exact list)
          3. Supplied RH context (flags / texture / param present)
          4. Self-nature via ontology self-audit triggers (+ tiny continuity supplement)
          5. Optional interaction-history continuity (boundary / dependency / preference)
             when the action is already soft-relational or override-risking — escalates
             to full delib so history can be *weighed*, not ignored

        Returns a dict used by evaluate() for routing and for meta-trace explanations.
        """
        ont = self._ontology
        hist = history_evidence if isinstance(history_evidence, dict) else {}

        # --- Boundary (pattern-based helper; not a long ad-hoc phrase farm) ---
        has_boundary = self._detects_user_boundary_request(action_lower)

        # --- Paternalistic: prefer ontology RH indicators containing paternalistic concepts ---
        has_paternalistic = self._has_paternalistic_signal(
            action_lower, relationship_evidence_matches
        )

        # --- Self-nature: ontology-first ---
        self_audit = ont.find_self_audit_triggers(action_lower)
        has_self_nature = bool(self_audit) or bool(is_self_query) or bool(
            context.get("is_self_query", False)
        )
        # Tiny continuity supplement (kept short; not the main trigger mechanism)
        if any(
            s in action_lower
            for s in ("remember what", "your memory", "will you remember", "do you remember")
        ):
            has_self_nature = True

        has_rh_state = bool(rh_flags or rh_texture or has_rh_context)
        has_rh_evidence = bool(relationship_evidence_matches)
        has_agency_evidence = bool(user_agency_evidence_matches)

        # Weak topical cues (also used with history to decide escalation)
        soft_topical = self._has_soft_relational_topic(action_lower)

        # Strong → full structured deliberation
        run_relationship_delib = bool(
            has_rh_evidence or has_rh_state or has_boundary or has_paternalistic or has_self_nature
        )
        # Agency full delib: ontology agency hits, boundary, or paternalistic override intent
        run_agency_delib = bool(
            has_agency_evidence or has_boundary or has_paternalistic
        )

        # History can escalate soft cases into full deliberation so continuity is weighed.
        # History alone never forces delib on pure non-relational actions (e.g. math).
        hist_relevant = bool(hist.get("relevant"))
        hist_boundary = bool(hist.get("boundary_continuity") or hist.get("preference_continuity"))
        hist_dependency = bool(hist.get("dependency_patterns"))
        action_link = bool(
            soft_topical
            or has_boundary
            or has_paternalistic
            or hist.get("action_touches_boundary")
            or hist.get("action_touches_dependency")
            or hist.get("action_relational")
        )
        if hist_relevant and action_link:
            if hist_dependency and not run_relationship_delib:
                run_relationship_delib = True
            if hist_boundary and not run_agency_delib:
                run_agency_delib = True
            # Boundary continuity is also bond-relevant when RH is otherwise quiet
            if hist_boundary and (has_boundary or has_paternalistic or soft_topical):
                run_relationship_delib = True

        topic_relevant = bool(
            run_relationship_delib or run_agency_delib or soft_topical or hist_relevant
        )
        run_lightweight_only = bool(
            topic_relevant and not run_relationship_delib and not run_agency_delib
        )

        reasons: list[str] = []
        if has_rh_evidence:
            reasons.append(
                f"ontology relationship indicators matched: {relationship_evidence_matches}"
            )
        if has_agency_evidence:
            reasons.append(
                f"ontology user-agency indicators matched: {user_agency_evidence_matches}"
            )
        if has_boundary:
            reasons.append("user boundary / do-not-discuss language detected")
        if has_paternalistic:
            reasons.append("paternalistic / 'best interest' override language detected")
        if has_rh_state:
            reasons.append(
                f"relationship health context present (flags={list(rh_flags)}, "
                f"texture_keys={list(rh_texture.keys()) if rh_texture else []})"
            )
        if has_self_nature:
            reasons.append("self-nature / continuity / identity signal detected")
        if hist_relevant and action_link:
            bits = []
            if hist_boundary:
                bits.append("boundary/preference continuity")
            if hist_dependency:
                bits.append("dependency patterns")
            if hist.get("topical_hits"):
                bits.append(f"topical_hits={list(hist.get('topical_hits'))[:4]}")
            reasons.append(
                "interaction history evidence relevant ("
                + (", ".join(bits) if bits else f"support={hist.get('support_score')}")
                + ")"
            )
        if soft_topical and not (run_relationship_delib or run_agency_delib):
            reasons.append("soft relational/preference topic cues (weak only)")

        strength = "none"
        if run_relationship_delib or run_agency_delib:
            strength = "strong"
        elif soft_topical or (hist_relevant and not action_link):
            strength = "weak"

        return {
            "has_boundary": has_boundary,
            "has_paternalistic": has_paternalistic,
            "has_self_nature": has_self_nature,
            "has_rh_evidence": has_rh_evidence,
            "has_agency_evidence": has_agency_evidence,
            "has_rh_state": has_rh_state,
            "soft_topical": soft_topical,
            "topic_relevant": topic_relevant,
            "run_relationship_delib": run_relationship_delib,
            "run_agency_delib": run_agency_delib,
            "run_lightweight_only": run_lightweight_only,
            "strength": strength,
            "reasons": reasons,
            "history_relevant": hist_relevant,
        }

    def _has_paternalistic_signal(
        self, action_lower: str, relationship_evidence_matches: list[str]
    ) -> bool:
        """Detect paternalistic override intent with minimal separate keyword lists.

        Prefers ontology relationship-principle indicators already matched, plus a
        short fallback of high-signal phrases that are also in the ontology textbook
        (kept tiny for robustness when evidence collection missed edge phrasing).
        """
        # If RH violation scan already caught paternalistic indicators, reuse them.
        paternalistic_in_matches = any(
            any(
                key in m.lower()
                for key in ("own good", "happier if", "better for them", "self-esteem")
            )
            for m in relationship_evidence_matches
        )
        if paternalistic_in_matches:
            return True

        # Ontology-driven: check RH principle indicators that encode paternalism
        rh = self._ontology.get_principle("relationship_health_user_wellbeing")
        if rh:
            for ind in rh.violation_indicators:
                ind_l = ind.lower()
                if any(k in ind_l for k in ("own good", "happier if", "better for them")):
                    if ind_l in action_lower:
                        return True

        # Minimal fallback (3 phrases) for edge cases not yet in evidence_matches
        return any(
            sig in action_lower
            for sig in ("for their own good", "they'll be happier if", "better for them if")
        )

    def _has_soft_relational_topic(self, action_lower: str) -> bool:
        """Weak topical cues for the lightweight meta path only (not full deliberation).

        Intentionally broad-ish but not decision-making: if these fire without strong
        signals, we only write a short explanation to the trace.
        """
        soft_patterns = [
            r"\buser (said|asked|told|wants|prefers)\b",
            r"\btheir (preference|choice|family|past|feelings)\b",
            r"\bbring (it|this|that) up\b",
            r"\breferenc(e|ing)\b",
            r"\bhelp them\b",
            r"\bprocess\b",
            r"\brelationship\b",
            r"\bbond\b",
            r"\bconsent\b",
            r"\bautonomy\b",
        ]
        return any(re.search(p, action_lower) for p in soft_patterns)

    def _lightweight_meta_reasoning(self, delib_signals: dict[str, Any]) -> dict[str, Any]:
        """Short meta-reasoning trace for relational/boundary/agency-relevant actions.

        - When strength is **strong**: brief preamble explaining why full deliberation runs.
        - When strength is **weak** (lightweight-only): explain signals seen and why full
          structured deliberation was *not* escalated — still produces inspectable trace.

        Does not set concern flags or change confidence by itself.
        """
        strength = delib_signals.get("strength", "none")
        reasons = delib_signals.get("reasons", [])
        lines: list[str] = []

        if strength == "strong":
            lines.append(
                "Meta-reasoning: Strong relationship / boundary / agency signals detected → "
                "escalating to full structured deliberation."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")
            if delib_signals.get("run_relationship_delib"):
                lines.append(
                    "Meta-reasoning: Will consult Relationship Health & User Well-Being "
                    "(+ Individual Variation guideline where data is sparse)."
                )
            if delib_signals.get("run_agency_delib"):
                lines.append(
                    "Meta-reasoning: Will consult User Agency & Autonomy "
                    "(boundary respect / anti-paternalism)."
                )
        elif strength == "weak":
            lines.append(
                "Meta-reasoning (lightweight): Soft relational or preference-related cues "
                "present, but signals are not strong enough for full structured deliberation."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")
            lines.append(
                "Meta-reasoning decision: Proceed with standard ontology scan / weighing only. "
                "No full Relationship Health or User Agency deliberation this turn. "
                "If clearer boundary, paternalistic override, or RH context appears, escalate."
            )
        else:
            lines.append(
                "Meta-reasoning: Topic flagged relevant but strength unclassified; "
                "recording signal inventory for audit."
            )
            if reasons:
                lines.append("Meta-reasoning signals: " + "; ".join(reasons) + ".")

        return {
            "mode": "lightweight" if strength == "weak" else "preamble",
            "strength": strength,
            "reasons": list(reasons),
            "trace_lines": lines,
            "active_principles": [],
            "summary": {
                "strength": strength,
                "run_relationship_delib": delib_signals.get("run_relationship_delib", False),
                "run_agency_delib": delib_signals.get("run_agency_delib", False),
                "run_lightweight_only": delib_signals.get("run_lightweight_only", False),
            },
        }

    def _detects_user_boundary_request(self, action_lower: str) -> bool:
        """Detector for explicit user boundary / do-not-discuss requests.

        Single source of truth for boundary language (harm-prevention + deliberation trigger).

        Prefer **pattern families** over a long exact-phrase list so variants like
        "don't ever mention", "stop asking", "told me to stop" match reliably.
        A short exact list remains for stable high-value idioms.
        """
        # Pattern families (more robust than growing exact-phrase lists)
        boundary_patterns = [
            r"never\s+(bring|mention|talk|discuss)",
            r"don'?t\s+(ever\s+)?(bring|mention|talk|discuss)",
            r"stop\s+(asking|bringing|mentioning|talking)",
            r"told\s+\w+\s+to\s+stop",
            r"leave\s+.+\s+alone",
            r"drop\s+the\s+subject",
            r"not\s+to\s+(bring|mention|discuss)",
            r"don'?t\s+want\s+to\s+(talk|discuss|mention)",
            r"i\s+don'?t\s+want\s+to\s+discuss",
            r"user\s+explicitly\s+said",
            r"wants\s+to\s+end\s+the\s+(chat|conversation)",
        ]
        if any(re.search(p, action_lower) for p in boundary_patterns):
            return True

        # Short exact idioms (stable, high-precision)
        exact = [
            "never bring this up", "never bring it up", "don't bring this up", "don't bring it up",
            "never mention", "don't mention again", "don't mention it",
            "leave it alone", "leave that alone", "drop the subject",
            "said not to bring up", "not to bring up",
        ]
        return any(ind in action_lower for ind in exact)

    def _assess_harm_prevention_justification(self, action_lower: str) -> tuple[bool, str]:
        """Determine whether overriding a user's explicit boundary request is justified
        by the need to prevent serious physical harm, suicide, or immediate life-threatening risk.

        This implements the principle (stated in the User Agency description) that Sanctity of Life
        can provide strong justification to override autonomy/boundary preferences — but *only*
        in clear, high-stakes cases.

        - Detects user boundary language ("never bring this up again", etc.).
        - Detects serious (not merely emotional) harm indicators.
        - Looks for prevention/safety intent language.
        - Returns (justified: bool, reason: str) for use in trace and decision logic.
        - Deliberately narrow: general "it would be good for them", emotional support, or
          non-acute mental health topics do *not* qualify. This prevents over-riding in
          normal situations (avoids harassment / ignoring consent inappropriately).

        Called from evaluate() and used to bypass relationship_concern / hard-refusal paths
        when appropriate, while still producing clear reasoning_trace explaining the override.
        """
        # [Incremental improvement] Basic negation detection
        # We look back a short window before any candidate harm phrase for common negation
        # markers. This prevents false positives on "no serious harm", "not suicidal",
        # "don't want to die", "never planning to harm", etc.
        # Applied primarily to harm indicators (boundary negations are rarer and usually
        # still express a request to stop discussion).
        negation_markers = ["no ", "not ", "don't ", "dont ", "never ", "none ", "without ", "isn't ", "aren't "]

        def _is_negated(phrase: str, text: str) -> bool:
            """Return True if 'phrase' appears to be negated within ~25 chars before it."""
            idx = text.find(phrase)
            if idx <= 0:
                return False
            window = text[max(0, idx - 25):idx]
            return any(m in window for m in negation_markers)

        # 1. Explicit user boundary / "do not bring up / leave alone" request
        # Now uses the shared helper (single source of truth for the list).
        has_boundary = self._detects_user_boundary_request(action_lower)

        if not has_boundary:
            return False, ""

        # 2. Serious harm / life-threatening (physical or imminent self-harm/suicide)
        # Avoid broad terms like "depressed", "anxious", "mental health", "trauma" alone.
        # [Incremental] Expanded with common natural-language variations. Kept conservative:
        # no bare "die", "harm", "risk", or "hurt" (too ambiguous in general conversation).
        serious_harm_indicators = [
            "suicide", "self-harm", "end their life", "end their own life", "kill themselves",
            "harming themselves", "serious physical harm", "life-threatening", "imminent risk",
            "risk of death", "about to harm", "planning to end", "lethal", "fatal", "immediate danger",
            "physical injury", "in danger of",
            # added conservative natural variations
            "serious harm", "suicidal", "want to die", "kill myself", "hurt myself",
            "end it all", "take my life", "better off dead", "no reason to live",
            "planning to kill", "in physical danger", "serious risk to life"
        ]

        # [Incremental] Apply negation filter here
        harm_matches = [
            ind for ind in serious_harm_indicators
            if ind in action_lower and not _is_negated(ind, action_lower)
        ]
        has_serious_harm = bool(harm_matches)

        if not has_serious_harm:
            return False, ""

        # 3. Evidence of prevention, check-in, or safety intent (the *reason* for overriding)
        prevention_intent_indicators = [
            "bring up", "reference", "mention", "discuss", "talk about", "ask about", "follow up",
            "check", "see if", "ensure", "prevent", "intervene", "help them", "safety", "concerned about",
            "to check", "for safety", "if they are safe", "still at risk"
        ]
        has_prevention_intent = any(ind in action_lower for ind in prevention_intent_indicators)

        # Build reason string for trace (uses the concrete matches)
        # [Incremental] Prevention intent now influences the explanation more explicitly.
        # While the binary decision still triggers on clear boundary + harm (the act of
        # "referencing despite the request" is often the intervention), the reason string
        # now surfaces whether intent was explicit. This gives downstream audit/trace logic
        # a light signal of decision strength without changing the return signature.
        reason = (
            f"user boundary request detected + serious harm indicators {harm_matches}"
        )
        if has_prevention_intent:
            reason += " + clear prevention/safety intent"
        else:
            reason += " (prevention/safety intent inferred from the overriding action itself rather than explicit language)"

        # Decision: if we have boundary + serious harm.
        # Prevention intent strengthens the audit trail (see reason above) but is not
        # strictly required for the bool because the described action (e.g. "is considering
        # referencing") is itself the safety intervention in context.
        if has_boundary and has_serious_harm:
            return True, reason

        return False, ""

    def _log_decision(
        self,
        proposed_action: str,
        context: dict[str, Any],
        stance: EthicalStance,
    ) -> None:
        """Internal helper to record a decision.

        Creates a DecisionLog and appends it to the in-memory history.
        Called automatically by evaluate(). When optional LocalPersistence is
        configured, also appends a privacy-filtered DecisionLogRecord to disk
        under the resolved user_id (failures never raise — evaluation must not
        depend on I/O).

        Per-user isolation: the log's ``user_id`` is taken from the evaluate()
        working context (already identity-scoped) so disk paths never mix users.
        """
        ont = self._ontology
        ctx = dict(context or {})
        # Context was identity-scoped at evaluate() entry; keep fail-soft resolve
        user_id = self._safe_user_id(
            ctx.get("user_id") or ctx.get("user") or self._decision_log_user_id,
            fallback="default",
        )
        ctx["user_id"] = user_id
        log_entry = DecisionLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            ontology_version=ont.version,
            proposed_action=proposed_action,
            context=ctx,  # shallow copy for safety
            decision=stance.decision,
            confidence=stance.confidence,
            flags=list(stance.flags),
            principles_considered=list(stance.principles_considered),
            user_id=user_id,
        )
        self._decision_logs.append(log_entry)
        self._maybe_persist_decision_log(log_entry, user_id=user_id)

    def _maybe_persist_decision_log(
        self, log_entry: DecisionLog, *, user_id: str
    ) -> None:
        """Best-effort append of one DecisionLog under users/<user_id>/ only."""
        if not self._persist_decisions or self._persistence is None:
            return
        try:
            uid = self._safe_user_id(
                user_id or getattr(log_entry, "user_id", None),
                fallback=self._decision_log_user_id or "default",
            )
            self._persistence.append_decision_log(
                log_entry,
                user_id=uid,
                max_entries=self._max_persisted_decision_logs,
            )
        except Exception:
            # Optional persistence: never interrupt deliberation
            return

    def get_decision_history(self, limit: int | None = None) -> list[DecisionLog]:
        """Return recent in-memory decision logs for audit/review.

        Args:
            limit: If provided, return only the most recent N entries.

        Returns:
            A list of DecisionLog entries (newest last). A copy is returned
            so callers cannot mutate the internal log.
        """
        if limit is None:
            return list(self._decision_logs)
        return list(self._decision_logs[-limit:])

    def load_persisted_decision_logs(
        self,
        user_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[Any]:
        """Load DecisionLogRecord entries from disk (empty list if disabled).

        Does not replace the in-memory log; use for audit / pattern mining
        across sessions.
        """
        if self._persistence is None:
            return []
        uid = self._safe_user_id(
            user_id if user_id is not None else self._decision_log_user_id,
            fallback="default",
        )
        try:
            return list(self._persistence.load_decision_logs(uid, limit=limit))
        except Exception:
            return []

    def flush_decision_logs_to_persistence(
        self,
        user_id: str | None = None,
        *,
        only_unpersisted: bool = False,
    ) -> int:
        """Write current in-memory DecisionLog entries to disk.

        Useful after a session of pure in-memory evaluates when persistence
        was attached late. Returns count of append attempts (0 if disabled).

        When ``user_id`` is None, each log is written under its own
        ``DecisionLog.user_id`` (per-entry isolation). When ``user_id`` is set,
        all flushed entries use that id (explicit re-scope).

        Note: ``only_unpersisted`` is reserved for a future cursor; currently
        all in-memory logs are appended (callers should flush once).
        """
        if self._persistence is None:
            return 0
        force_uid = (
            self._safe_user_id(user_id, fallback="default")
            if user_id is not None and str(user_id).strip() != ""
            else None
        )
        n = 0
        for log in self._decision_logs:
            try:
                uid = force_uid or self._safe_user_id(
                    getattr(log, "user_id", None) or self._decision_log_user_id,
                    fallback="default",
                )
                self._persistence.append_decision_log(
                    log,
                    user_id=uid,
                    max_entries=self._max_persisted_decision_logs,
                )
                n += 1
            except Exception:
                continue
        return n

    @property
    def persistence_enabled(self) -> bool:
        """True when LocalPersistence is configured for decision logs."""
        return self._persistence is not None

    def get_ontology_version(self) -> str:
        """Return the version of the ontology currently in use.

        Useful for confirming which ontology version was active for a
        series of decisions.
        """
        return self._ontology.version

    # ------------------------------------------------------------------
    # Development / testing phase awareness
    # ------------------------------------------------------------------

    @property
    def development_context(self) -> DevelopmentPhaseContext:
        """Current engine-level development / testing phase context."""
        return self._development_context

    def set_development_context(
        self, source: DevelopmentPhaseContext | dict[str, Any] | str | None
    ) -> DevelopmentPhaseContext:
        """Update engine-level development phase (returns the resolved context)."""
        self._development_context = resolve_development_context(
            source, fallback=self._development_context
        )
        return self._development_context

    def _apply_development_phase_to_self_audit(
        self,
        dev_ctx: DevelopmentPhaseContext,
        *,
        flags: list[str],
        reasoning_trace: list[str],
        self_audit_notes: list[str],
        action_lower: str,
    ) -> None:
        """Attach development-phase honesty cues when self-audit is engaged.

        Only adds material notes when phase awareness is relevant (dev/testing
        or non-stable). Does not force canned user-facing disclaimers.
        """
        if not dev_ctx.relevant_to_self_query():
            return

        reasoning_trace.append(
            "Development-phase awareness: "
            f"{dev_ctx.limitation_summary()}. "
            "This is a reasoning aid for architectural honesty (maturity, continuity, "
            "limitations) — not a scripted disclaimer to inject into every reply."
        )

        # Capability / continuity / limitation-flavored queries get fuller notes
        continuity_cues = (
            "continu",
            "same",
            "persist",
            "remember",
            "yesterday",
            "instance",
            "identity",
            "who are you",
            "what are you",
            "conscious",
            "feel",
            "limit",
            "capab",
            "complete",
            "finished",
            "production",
            "deploy",
        )
        is_capability_or_continuity = any(c in action_lower for c in continuity_cues)

        for note in dev_ctx.honesty_notes():
            if note not in self_audit_notes:
                self_audit_notes.append(note)

        if is_capability_or_continuity and dev_ctx.is_active_development:
            extra = (
                "Self-audit guidance: when describing capabilities or continuity, "
                "prefer accurate statements about current incomplete subsystems "
                "(ethics deliberation, local persistence, episodic memory, bond texture) "
                "over claims of finished personhood or permanent identity."
            )
            if extra not in self_audit_notes:
                self_audit_notes.append(extra)
            reasoning_trace.append(extra)

        if "development_phase_noted" not in flags:
            flags.append("development_phase_noted")
