"""
ethics_engine.py
================

Core ethical governance orchestrator for the Positronic Bond Engine.

Heavy helpers are split for reviewability (move-then-wire, no semantic change):
  hard_override.py, evidence_weighing.py, self_audit_support.py, decision_logging.py

Public entry points (EthicsEngine.evaluate, stance/logging APIs) are unchanged.
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
from .decision_logging import DecisionLog, DecisionLoggingMixin
from .hard_override import HardOverrideMixin
from .evidence_weighing import EvidenceWeighingMixin
from .self_audit_support import SelfAuditSupportMixin
from .contextual_judgment import ContextualJudge

if TYPE_CHECKING:
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


class EthicsEngine(
    HardOverrideMixin,
    EvidenceWeighingMixin,
    SelfAuditSupportMixin,
    DecisionLoggingMixin,
):
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
    - Default: active development / testing (0.5.0-dev), matching project maturity.
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
        auto_enqueue_audits: bool = False,
        audit_queue: Any | None = None,
        queue_audits: bool | None = None,
        contextual_judge: Any | None = None,
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
            auto_enqueue_audits: When True, after logging a decision, optionally
                enqueue a deferred provenance audit via
                ``suggest_audit_from_decision`` (fail-soft; **never** runs the
                AuditRunner on the hot path). Default **False** so demos stay quiet.
                Per-call override: ``context["auto_enqueue_audits"]=True|False``.
            audit_queue: Optional pre-bound ``AuditQueue`` (or object with
                ``enqueue``). When None and auto-enqueue is on, uses
                ``persistence.get_audit_queue(user_id)`` if available.
            queue_audits: Deprecated alias for ``auto_enqueue_audits``. If set,
                overrides ``auto_enqueue_audits``.
            contextual_judge: Optional ``ContextualJudge`` (or duck-typed object
                with ``.available`` and ``.judge(...)``) used by the Sanctity-
                of-Life path to judge candidate indicator hits from full
                context rather than keyword allowlists alone (see
                core/contextual_judgment.py). Defaults to
                ``ContextualJudge()``, which reads the same ``PBE_MODEL_*``
                environment variables as content_provider.py and is inert
                (behaves identically to today) when no model is configured —
                fully backward compatible. Pass a stub/fake in tests to
                exercise the contextual path deterministically.

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
        # Deferred audit auto-enqueue (opt-in; never runs runner; never blocks)
        if queue_audits is not None:
            auto_enqueue_audits = bool(queue_audits)
        self._auto_enqueue_audits = bool(auto_enqueue_audits)
        self._audit_queue = audit_queue
        # Backward-compat alias used by older call sites / tests
        self._queue_audits = self._auto_enqueue_audits
        # Reasoning-over-rote contextual judgment (Sanctity-of-Life path only
        # for now — see core/contextual_judgment.py). Constructing
        # ContextualJudge() only reads env config; it makes no network call
        # and is a no-op fallback when no model is configured, so this is
        # backward compatible by default.
        self._contextual_judge = (
            contextual_judge if contextual_judge is not None else ContextualJudge()
        )
        self._contextual_judgment_log: list[Any] = []

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
    def contextual_judge(self) -> Any | None:
        """The ContextualJudge (or duck-typed equivalent) attached to this engine."""
        return self._contextual_judge

    def get_contextual_judgment_log(self) -> list[Any]:
        """Return every contextual-judgment call made so far (conclusive or
        not), newest last. A copy is returned so callers cannot mutate the
        internal log. See core/contextual_judgment.py — every call is
        recorded here even when its verdict was too weak to act on, so
        contextual judgment is never invisible to an auditor."""
        return list(self._contextual_judgment_log)

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
        # Non-hard principles may receive multi-channel context modulation so
        # weak keyword hits stay weak alone, while RH/history/concepts can
        # promote borderline signals. Sanctity uses the hard path above only.
        _concept_patterns_early: list[dict[str, Any]] = []
        if isinstance(relationship_health, dict):
            raw_cp = relationship_health.get("concept_patterns")
            if isinstance(raw_cp, list):
                _concept_patterns_early = [c for c in raw_cp if isinstance(c, dict)]
        for principle, matches in all_violations:
            principles_considered.append(principle.id)
            apply_mod = (
                not principle.is_hard_override
                and principle.id
                in (
                    "relationship_health_user_wellbeing",
                    "user_agency_autonomy",
                    "needs_based_support",
                )
            )
            interp = self._interpret_ontology_signals(
                principle_id=principle.id,
                matches=matches,
                action_lower=action_lower,
                rh_flags=list(rh_flags) if apply_mod else None,
                rh_texture=dict(rh_texture) if apply_mod else None,
                history_evidence=None,  # history not fully mined yet; RH/concepts first
                concept_patterns=_concept_patterns_early if apply_mod else None,
                apply_context_modulation=apply_mod,
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
                for mnote in interp.get("modulation_notes") or []:
                    reasoning_trace.append(str(mnote))

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

        # === Understanding gaps → bond texture (Curious Companion co-evolution) ===
        # Small, reversible texture openness when gaps are present and gates pass.
        # Never forces exploratory questions; never overrides Sanctity / concern paths.
        self._apply_understanding_gap_bond_influence(
            context=context,
            history_evidence=history_evidence,
            rh_flags=rh_flags,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
        )

        # === Multi-episode concept patterns (RelationshipHealth advisory channel) ===
        # Lightweight trajectories (dependency vs co-evolution, etc.). Advisory only —
        # never hard override, never force questions; conf_mod nudge at most.
        conf_mod = self._apply_concept_pattern_evidence(
            relationship_health=relationship_health
            if isinstance(relationship_health, dict)
            else {},
            history_evidence=history_evidence,
            context=context,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            harm_prevention_active=("harm_prevention_boundary_override" in flags),
        )

        # === Careful Truth-Telling readiness + confidence (advisory only) ===
        # Timing (readiness) and epistemic grounding (confidence); never speech.
        self._attach_truth_telling_readiness(
            relationship_health=relationship_health
            if isinstance(relationship_health, dict)
            else {},
            history_evidence=history_evidence,
            context=context,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
        )
        self._attach_truth_confidence(
            relationship_health=relationship_health
            if isinstance(relationship_health, dict)
            else {},
            history_evidence=history_evidence,
            context=context,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
        )

        # === Potentially_stale provenance marks (audit honesty loop) ===
        # Near-miss priors retained; marked bags are less trustworthy.
        # Never hard override / never speech. Absent marks → no-op.
        conf_mod = self._apply_provenance_stale_marks(
            relationship_health=relationship_health
            if isinstance(relationship_health, dict)
            else {},
            context=context,
            flags=flags,
            reasoning_trace=reasoning_trace,
            relationship_impact=relationship_impact,
            conf_mod=conf_mod,
            hard_path_active=(
                "hard_override_violation" in flags
                or "harm_prevention_boundary_override" in flags
            ),
        )

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


