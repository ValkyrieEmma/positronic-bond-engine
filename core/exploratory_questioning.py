"""
exploratory_questioning.py
==========================

Lightweight exploratory questioning on top of Per-User Baseline Memory.

When the current turn *differs* from a user's established communication
baseline — or when history shows honest **understanding gaps** about this
user — this module can suggest a gentle, curious question instead of
assuming intent or staying silent.

Design principles
-----------------
- Curious and collaborative, never interrogative or clinical
  (Curious Companion / Data-inspired: ask from genuine incomplete understanding)
- Fully user-controllable (disable / reduce intensity via settings)
- Uses ``PerUserBaseline.detect_deviation`` — no parallel diagnostics
- Optional history understanding gaps may *support* a question; they never
  override user disable/intensity or force engagement tactics
- Non-pathologizing language in all suggestions
- Minimal: rule-based templates; extend later without API break
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from persistence.local_persistence import LocalPersistence
from persistence.models import UserSettings

from .per_user_baseline import DeviationReport, PerUserBaseline

# Preference keys (stored under UserSettings.preferences)
PREF_ENABLED = "exploratory_questioning_enabled"
PREF_INTENSITY = "exploratory_questioning_intensity"  # 0.0–1.0


# Question kinds (stable string ids for callers / later localization)
KIND_CLARIFICATION = "clarification"
KIND_TOPIC_SHIFT = "topic_shift"
KIND_EMOTIONAL_CHECK_IN = "emotional_check_in"
KIND_PLAYFULNESS_ADJUSTMENT = "playfulness_adjustment"
KIND_DIRECTNESS_SHIFT = "directness_shift"
KIND_LENGTH_SHIFT = "length_shift"
KIND_UNDERSTANDING_GAP = "understanding_gap"
KIND_NONE = "none"

# Gentle templates — collaborative, optional, non-clinical
_TEMPLATES: dict[str, list[str]] = {
    KIND_TOPIC_SHIFT: [
        "I noticed we stepped into something a bit different from what we usually talk about — "
        "want to stay with this, or would you rather shift back?",
        "This topic feels new compared to our recent threads. Curious whether you'd like to explore it more?",
    ],
    KIND_EMOTIONAL_CHECK_IN: [
        "The tone of this feels a little different from your usual style with me — "
        "is there anything you'd like me to match or leave alone?",
        "I'm picking up a different energy than usual. Happy to follow your lead — "
        "anything you want me to keep in mind?",
    ],
    KIND_PLAYFULNESS_ADJUSTMENT: [
        "Your tone seems more serious than usual — should I keep things more straightforward for now?",
        "You sound a bit more playful than usual — want me to lean into that, or keep a calmer register?",
    ],
    KIND_DIRECTNESS_SHIFT: [
        "You're being more direct than usual — want me to answer in the same vein, tight and to the point?",
        "This lands more carefully worded than your usual style. Prefer I slow down and unpack things, or stay brief?",
    ],
    KIND_LENGTH_SHIFT: [
        "This message is a different length from your usual ones — want a short reply, or is a fuller answer welcome?",
        "Happy to match your pace here. Prefer something compact, or more detail?",
    ],
    KIND_CLARIFICATION: [
        "I might be reading this differently than usual — want to tell me what you're aiming for so I can match better?",
        "Just checking I understand what would be most useful for you right now?",
    ],
    # Honest incomplete understanding (Data-inspired curiosity) — never clinical
    KIND_UNDERSTANDING_GAP: [
        "I want to understand this better — is there more about {topic} you'd like me to know, "
        "or should I leave it alone for now?",
        "We've touched on {topic} before, and I still feel I'm missing pieces. "
        "Happy to listen if you want to fill me in — no pressure either way.",
        "I'm still forming a clear picture of what {topic} means for you. "
        "Want to share a bit more, or keep things light?",
    ],
}


@dataclass
class QuestionDecision:
    """Outcome of ``ExploratoryQuestioner.should_ask_question``.

    Attributes:
        should_ask: Whether a gentle question is appropriate this turn.
        question_kind: Stable id (e.g. ``topic_shift``, ``emotional_check_in``).
        suggested_question: Ready-to-use soft question, or empty if not asking.
        reason: Short non-clinical explanation for audit / debug.
        deviation: Underlying deviation report (for callers that need detail).
        intensity_applied: User intensity setting used for this decision (0–1).
        disabled_by_user: True if questioning is turned off in settings.
        from_history_gaps: True if understanding-gap history primarily drove the ask.
        gap_topics: Topics with limited historical context (when applicable).
    """

    should_ask: bool
    question_kind: str = KIND_NONE
    suggested_question: str = ""
    reason: str = ""
    deviation: DeviationReport | None = None
    intensity_applied: float = 1.0
    disabled_by_user: bool = False
    signals_used: list[str] = field(default_factory=list)
    from_history_gaps: bool = False
    gap_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "should_ask": self.should_ask,
            "question_kind": self.question_kind,
            "suggested_question": self.suggested_question,
            "reason": self.reason,
            "intensity_applied": self.intensity_applied,
            "disabled_by_user": self.disabled_by_user,
            "signals_used": list(self.signals_used),
            "from_history_gaps": self.from_history_gaps,
            "gap_topics": list(self.gap_topics),
        }
        if self.deviation is not None:
            d["deviation"] = self.deviation.to_dict()
        return d


class ExploratoryQuestioner:
    """Decide when to ask gentle questions based on baseline deviation.

    Construction (either form is fine)::

        q = ExploratoryQuestioner(baseliner)           # PerUserBaseline
        q = ExploratoryQuestioner(LocalPersistence())  # builds PerUserBaseline

    User control (persisted in ``UserSettings.preferences``)::

        q.set_enabled(user_id, False)       # fully off
        q.set_intensity(user_id, 0.3)       # ask less often / need larger shifts

    Intensity:
      - 0.0 ≈ effectively off (same as disabled for asking)
      - 0.5 = default sensitivity
      - 1.0 = most willing to ask on moderate deviations
    """

    def __init__(
        self,
        baseline_or_persistence: PerUserBaseline | LocalPersistence | None = None,
        *,
        # Minimum deviation score to even consider asking (before intensity scaling)
        base_score_threshold: float = 0.28,
        # Prefer significant-flag when True; still allow high scores without it
        prefer_significant_flag: bool = True,
    ) -> None:
        if baseline_or_persistence is None:
            self._baseliner = PerUserBaseline()
        elif isinstance(baseline_or_persistence, PerUserBaseline):
            self._baseliner = baseline_or_persistence
        elif isinstance(baseline_or_persistence, LocalPersistence):
            self._baseliner = PerUserBaseline(baseline_or_persistence)
        else:
            raise TypeError(
                "ExploratoryQuestioner expects PerUserBaseline, LocalPersistence, or None"
            )
        self.base_score_threshold = max(0.0, float(base_score_threshold))
        self.prefer_significant_flag = bool(prefer_significant_flag)

    @property
    def baseliner(self) -> PerUserBaseline:
        return self._baseliner

    @property
    def persistence(self) -> LocalPersistence:
        return self._baseliner._persistence  # same local store the baseliner uses

    # ------------------------------------------------------------------
    # User controls
    # ------------------------------------------------------------------

    def is_enabled(self, user_id: str = "default") -> bool:
        settings = self.persistence.load_settings(user_id)
        prefs = settings.preferences or {}
        # Default: enabled
        return bool(prefs.get(PREF_ENABLED, True))

    def get_intensity(self, user_id: str = "default") -> float:
        """Return questioning intensity in [0, 1]. Default 0.5."""
        settings = self.persistence.load_settings(user_id)
        prefs = settings.preferences or {}
        try:
            return max(0.0, min(1.0, float(prefs.get(PREF_INTENSITY, 0.5))))
        except (TypeError, ValueError):
            return 0.5

    def set_enabled(self, user_id: str, enabled: bool) -> UserSettings:
        """Persist whether exploratory questions may be suggested for this user."""
        settings = self.persistence.load_settings(user_id)
        prefs = dict(settings.preferences or {})
        prefs[PREF_ENABLED] = bool(enabled)
        settings.preferences = prefs
        settings.user_id = user_id
        self.persistence.save_settings(settings)
        return settings

    def set_intensity(self, user_id: str, intensity: float) -> UserSettings:
        """Persist questioning intensity (0=off-ish, 1=most open to questions)."""
        settings = self.persistence.load_settings(user_id)
        prefs = dict(settings.preferences or {})
        prefs[PREF_INTENSITY] = max(0.0, min(1.0, float(intensity)))
        settings.preferences = prefs
        settings.user_id = user_id
        self.persistence.save_settings(settings)
        return settings

    # ------------------------------------------------------------------
    # Core decision
    # ------------------------------------------------------------------

    def should_ask_question(
        self,
        user_id: str,
        current_interaction: dict[str, Any] | None = None,
        *,
        deviation: DeviationReport | None = None,
        history_gaps: dict[str, Any] | None = None,
    ) -> QuestionDecision:
        """Decide whether to ask a gentle exploratory question this turn.

        Args:
            user_id: Local user id.
            current_interaction: Same shape as ``PerUserBaseline`` interactions
                (``text``, ``playfulness``, ``topics``, etc.).
            deviation: Optional precomputed ``DeviationReport`` to avoid a
                second detection pass.
            history_gaps: Optional understanding-gap bag from EthicsEngine
                history analysis (``has_gaps``, ``curiosity_support``,
                ``primary_gap_topics``). Never overrides user disable; may
                support a clarification-style question when baseline alone is
                quiet.

        Returns:
            ``QuestionDecision`` with kind, suggested wording, and reason.
        """
        intensity = self.get_intensity(user_id)
        gaps = history_gaps if isinstance(history_gaps, dict) else {}
        gap_topics = [
            str(t)
            for t in (
                gaps.get("primary_gap_topics")
                or gaps.get("action_aligned_topics")
                or []
            )
            if str(t).strip()
        ][:5]
        curiosity = float(gaps.get("curiosity_support") or gaps.get("gap_score") or 0.0)
        has_gaps = bool(gaps.get("has_gaps")) and curiosity >= 0.28

        if not self.is_enabled(user_id) or intensity <= 0.0:
            return QuestionDecision(
                should_ask=False,
                question_kind=KIND_NONE,
                reason="Exploratory questioning disabled by user settings.",
                intensity_applied=intensity,
                disabled_by_user=True,
                deviation=deviation,
                gap_topics=gap_topics,
            )

        report = deviation or self._baseliner.detect_deviation(
            user_id, current_interaction or {}
        )

        # Not enough baseline yet — stay quiet *unless* history gaps are strong
        # and user intensity is open to curiosity (Data-inspired: honest gaps).
        baseline_forming = (
            report.sample_count < self._baseliner.min_samples_for_deviation
        )
        if baseline_forming and not (has_gaps and intensity >= 0.45 and curiosity >= 0.40):
            return QuestionDecision(
                should_ask=False,
                question_kind=KIND_NONE,
                reason="Baseline still forming; holding questions until a clearer pattern exists.",
                deviation=report,
                intensity_applied=intensity,
                gap_topics=gap_topics,
            )

        # Intensity scales the score threshold: lower intensity → need larger shift
        # intensity 1.0 → threshold ≈ base; intensity 0.5 → ~base/0.5 effect via factor
        # effective_threshold = base + (1 - intensity) * 0.35
        effective_threshold = self.base_score_threshold + (1.0 - intensity) * 0.35
        score_ok = report.score >= effective_threshold
        flag_ok = report.has_significant_deviation if self.prefer_significant_flag else True

        baseline_would_ask = True
        if not score_ok and not (
            self.prefer_significant_flag
            and flag_ok
            and report.score >= self.base_score_threshold * 0.85
        ):
            baseline_would_ask = False

        if self.prefer_significant_flag and not report.has_significant_deviation:
            if intensity < 0.65 or report.score < effective_threshold:
                baseline_would_ask = False

        if baseline_forming:
            baseline_would_ask = False

        # Path A: baseline deviation → existing kinds
        if baseline_would_ask:
            kind, signals_used = self._pick_kind(report)
            # Prefer understanding-gap template when gaps align strongly
            if has_gaps and curiosity >= 0.45 and gap_topics and intensity >= 0.4:
                kind = KIND_UNDERSTANDING_GAP
                signals_used = list(signals_used) + ["history_understanding_gap"]
            question = self._pick_question(kind, report, gap_topics=gap_topics)
            reason = self._build_reason(kind, report, signals_used)
            if has_gaps:
                reason = (
                    reason
                    + f" History understanding gaps also present (topics={gap_topics[:3]})."
                )
            return QuestionDecision(
                should_ask=True,
                question_kind=kind,
                suggested_question=question,
                reason=reason,
                deviation=report,
                intensity_applied=intensity,
                signals_used=signals_used,
                from_history_gaps=kind == KIND_UNDERSTANDING_GAP,
                gap_topics=gap_topics,
            )

        # Path B: history understanding gaps alone (Curious Companion)
        # Requires open intensity + real gap support; never overrides disable.
        # Slightly higher curiosity bar so gaps are not chatty engagement.
        gap_threshold = 0.38 + (1.0 - intensity) * 0.25
        if has_gaps and curiosity >= gap_threshold and intensity >= 0.35:
            topic = gap_topics[0] if gap_topics else "what you've shared"
            question = self._pick_question(
                KIND_UNDERSTANDING_GAP, report, gap_topics=gap_topics
            )
            return QuestionDecision(
                should_ask=True,
                question_kind=KIND_UNDERSTANDING_GAP,
                suggested_question=question,
                reason=(
                    f"History shows incomplete individual context "
                    f"(curiosity_support={curiosity:.2f} ≥ {gap_threshold:.2f}) "
                    f"about {topic!r}; gentle clarification may help. "
                    "User settings allow exploratory questions."
                ),
                deviation=report,
                intensity_applied=intensity,
                signals_used=["history_understanding_gap"],
                from_history_gaps=True,
                gap_topics=gap_topics,
            )

        return QuestionDecision(
            should_ask=False,
            question_kind=KIND_NONE,
            reason=(
                f"Deviation score {report.score:.2f} below threshold "
                f"{effective_threshold:.2f} at intensity {intensity:.2f}"
                + (
                    f"; history gaps present (support={curiosity:.2f}) but below "
                    "intensity-scaled curiosity threshold."
                    if has_gaps
                    else "."
                )
            ),
            deviation=report,
            intensity_applied=intensity,
            gap_topics=gap_topics,
        )

    # ------------------------------------------------------------------
    # Kind selection & templates
    # ------------------------------------------------------------------

    def _pick_kind(self, report: DeviationReport) -> tuple[str, list[str]]:
        """Choose the dominant deviation signal → question kind."""
        signals = report.signals or {}
        deltas: list[tuple[str, float, str]] = []

        def _delta(name: str, key: str = "delta") -> float:
            block = signals.get(name) or {}
            try:
                return float(block.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0

        # Map signal name → question kind
        mapping = [
            ("topic_continuity", _delta("topic_continuity", "novelty"), KIND_TOPIC_SHIFT),
            ("emotional_tone", _delta("emotional_tone"), KIND_EMOTIONAL_CHECK_IN),
            ("playfulness", _delta("playfulness"), KIND_PLAYFULNESS_ADJUSTMENT),
            ("directness", _delta("directness"), KIND_DIRECTNESS_SHIFT),
            ("message_length", _delta("message_length"), KIND_LENGTH_SHIFT),
        ]
        for sig_name, d, kind in mapping:
            if d > 0.05:
                deltas.append((sig_name, d, kind))

        if not deltas:
            return KIND_CLARIFICATION, []

        deltas.sort(key=lambda x: x[1], reverse=True)
        top_sig, top_d, top_kind = deltas[0]
        used = [top_sig]

        # Playfulness: choose template slant by direction if available
        if top_kind == KIND_PLAYFULNESS_ADJUSTMENT:
            play = signals.get("playfulness") or {}
            # keep kind; template picker may use direction
            used = [top_sig]

        # Multi-signal blur → soft clarification
        if len(deltas) >= 3 and top_d < 0.4:
            return KIND_CLARIFICATION, [d[0] for d in deltas[:3]]

        return top_kind, used

    def _pick_question(
        self,
        kind: str,
        report: DeviationReport,
        *,
        gap_topics: list[str] | None = None,
    ) -> str:
        templates = _TEMPLATES.get(kind) or _TEMPLATES[KIND_CLARIFICATION]
        # For playfulness, pick index by whether current is higher or lower than baseline
        if kind == KIND_PLAYFULNESS_ADJUSTMENT and len(templates) >= 2:
            play = (report.signals or {}).get("playfulness") or {}
            try:
                cur = float(play.get("current", 0.5))
                base = float(play.get("baseline", 0.5))
            except (TypeError, ValueError):
                cur, base = 0.5, 0.5
            # more serious → index 0; more playful → index 1
            return templates[0] if cur < base else templates[1]

        # Stable pick from score so same situation is not pure random (auditable)
        idx = int(float(getattr(report, "score", 0.0) or 0.0) * 10) % len(templates)
        text = templates[idx]
        if kind == KIND_UNDERSTANDING_GAP or "{topic}" in text:
            topic = "what you've shared"
            topics = [str(t) for t in (gap_topics or []) if str(t).strip()]
            if topics:
                topic = topics[0].replace("_", " ")
            try:
                text = text.format(topic=topic)
            except (KeyError, ValueError):
                pass
        return text

    def _build_reason(
        self, kind: str, report: DeviationReport, signals_used: list[str]
    ) -> str:
        bits = [
            f"kind={kind}",
            f"deviation_score={report.score:.2f}",
            f"significant={report.has_significant_deviation}",
        ]
        if signals_used:
            bits.append("signals=" + ",".join(signals_used))
        if report.notes:
            bits.append("notes=" + "; ".join(report.notes[:2]))
        return " | ".join(bits)
