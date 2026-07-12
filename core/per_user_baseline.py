"""
per_user_baseline.py
====================

Per-User Baseline Memory — lightweight foundation.

Tracks a non-pathologizing, user-controllable snapshot of how a person
typically communicates with the agent:

  - Message length & directness
  - Emotional tone range (descriptive range, not a diagnosis)
  - Topic continuity
  - Playfulness / casualness level

Persistence
-----------
Uses ``persistence.UserBaseline`` and the baseline store via
``LocalPersistence`` (local JSON only). This module does not implement
its own file I/O.

Design principles
-----------------
- Lightweight v1: simple heuristics + exponential moving averages
- Do **not** pathologize the user; deviations are descriptive, not clinical
- User-controllable: ``reset_baseline`` restores defaults; notes can be adjusted
- Modular: extraction, update, and deviation logic stay in this module;
  storage stays in ``persistence``

Future work can add exploratory questioning and richer estimators without
changing the public method names below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from persistence.local_persistence import LocalPersistence
from persistence.models import UserBaseline

# ---------------------------------------------------------------------------
# Defaults & constants
# ---------------------------------------------------------------------------

_DEFAULT_PLAYFULNESS = 0.5
_DEFAULT_DIRECTNESS = 0.5
_DEFAULT_LENGTH_SCORE = 0.5  # mid-range message length
_EMA_ALPHA_DEFAULT = 0.25  # higher = faster adaptation to new samples
_MAX_RECENT_TOPICS = 12
_MAX_TOPIC_TOKEN_LEN = 32

# Very light tone markers (descriptive only — not clinical labels)
_POS_TONE = frozenset(
    "happy glad love great wonderful nice good excited grateful thanks thank "
    "joy fun enjoy excited lovely warm".split()
)
_NEG_TONE = frozenset(
    "sad angry upset frustrated annoyed hate terrible awful bad worried "
    "anxious stressed hurt disappointed".split()
)
_HEDGE_MARKERS = frozenset(
    "maybe perhaps might kinda sort of somewhat possibly probably i guess "
    "i think not sure um uh like".split()
)
_PLAYFUL_MARKERS = frozenset(
    "haha lol lmao hehe funny joke kidding silly goofy meme lolz :)"
    " :-) :d 😂 😄 😊 🙃".split()
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _ema(prev: float, new: float, alpha: float) -> float:
    a = _clamp01(alpha)
    return (1.0 - a) * float(prev) + a * float(new)


@dataclass
class DeviationReport:
    """Result of comparing a current interaction to the stored baseline.

    Language is deliberately non-pathologizing: signals are "notable shifts"
    relative to *this user's* usual patterns, not judgments of health.
    """

    user_id: str
    has_significant_deviation: bool
    score: float
    """0.0 = fully in-line with baseline; 1.0 = large multi-signal shift."""

    signals: dict[str, Any] = field(default_factory=dict)
    """Per-dimension comparisons (baseline vs current, deltas)."""

    notes: list[str] = field(default_factory=list)
    """Short human-readable observations (for audit / companion tone)."""

    sample_count: int = 0
    """How many interactions have informed the baseline (0 = not yet established)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "has_significant_deviation": self.has_significant_deviation,
            "score": round(self.score, 3),
            "signals": self.signals,
            "notes": list(self.notes),
            "sample_count": self.sample_count,
        }


class PerUserBaseline:
    """Manage per-user communication baselines with local persistence.

    Typical usage::

        baseliner = PerUserBaseline()  # uses default local data root
        baseliner.update_from_interaction("alice", {"text": "Hey! How's it going?"})
        baseline = baseliner.get_baseline("alice")
        report = baseliner.detect_deviation("alice", {"text": "I need this fixed now."})
        baseliner.reset_baseline("alice")  # user control

    Args:
        persistence: Optional ``LocalPersistence`` instance. If omitted, a
            default local store is created (same as other local-only features).
        ema_alpha: Smoothing factor for rolling updates (0–1).
        deviation_threshold: Aggregate score above which
            ``has_significant_deviation`` is True.
        min_samples_for_deviation: Below this sample count, deviations are
            reported cautiously (usually not "significant") so early noise
            does not over-trigger.
    """

    def __init__(
        self,
        persistence: LocalPersistence | None = None,
        *,
        ema_alpha: float = _EMA_ALPHA_DEFAULT,
        deviation_threshold: float = 0.35,
        min_samples_for_deviation: int = 3,
    ) -> None:
        self._persistence = persistence or LocalPersistence()
        self.ema_alpha = _clamp01(ema_alpha)
        self.deviation_threshold = max(0.0, float(deviation_threshold))
        self.min_samples_for_deviation = max(1, int(min_samples_for_deviation))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_baseline(self, user_id: str = "default") -> UserBaseline:
        """Return the current persisted baseline for ``user_id``.

        If none exists yet, returns a default ``UserBaseline`` (not written
        until the first ``update_from_interaction`` or explicit save).
        """
        return self._persistence.load_baseline(user_id)

    def update_from_interaction(
        self,
        user_id: str,
        interaction_data: dict[str, Any] | None = None,
        *,
        persist: bool = True,
    ) -> UserBaseline:
        """Update the user's baseline from one message / conversation turn.

        ``interaction_data`` may include any of:
          - ``text`` / ``message`` / ``content``: raw utterance (optional)
          - ``message_length``: int word or char count override
          - ``directness``: float 0–1
          - ``emotional_tone`` / ``tone``: float 0–1 (calm→intense or low→high valence)
          - ``topics``: list[str] coarse topic tags
          - ``playfulness``: float 0–1

        Missing fields are estimated with lightweight heuristics when text
        is available; otherwise prior baseline values are held.

        Returns the updated ``UserBaseline`` (and saves it when ``persist``).
        """
        interaction_data = interaction_data or {}
        current = self.get_baseline(user_id)
        features = self._extract_features(interaction_data, current)
        updated = self._apply_update(current, features, user_id=user_id)
        if persist:
            self._persistence.save_baseline(updated)
        return updated

    def detect_deviation(
        self,
        user_id: str,
        current_interaction: dict[str, Any] | None = None,
    ) -> DeviationReport:
        """Lightweight check: does this turn differ from the user's baseline?

        Returns a ``DeviationReport`` with per-signal deltas. Does **not**
        diagnose, label, or pathologize the user — only describes shift
        relative to their own prior pattern.
        """
        current_interaction = current_interaction or {}
        baseline = self.get_baseline(user_id)
        features = self._extract_features(current_interaction, baseline)
        sample_count = int(
            (baseline.communication_patterns or {}).get("sample_count", 0)
        )

        signals: dict[str, Any] = {}
        notes: list[str] = []
        weighted_parts: list[float] = []

        # --- length ---
        base_len = float(
            (baseline.communication_patterns or {}).get(
                "message_length_score", _DEFAULT_LENGTH_SCORE
            )
        )
        cur_len = float(features["message_length_score"])
        d_len = abs(cur_len - base_len)
        signals["message_length"] = {
            "baseline": round(base_len, 3),
            "current": round(cur_len, 3),
            "delta": round(d_len, 3),
        }
        weighted_parts.append(d_len)
        if d_len >= 0.35:
            notes.append(
                "Message length differs from this user's usual range."
            )

        # --- directness ---
        base_dir = float(
            (baseline.communication_patterns or {}).get(
                "directness", _DEFAULT_DIRECTNESS
            )
        )
        cur_dir = float(features["directness"])
        d_dir = abs(cur_dir - base_dir)
        signals["directness"] = {
            "baseline": round(base_dir, 3),
            "current": round(cur_dir, 3),
            "delta": round(d_dir, 3),
        }
        weighted_parts.append(d_dir)
        if d_dir >= 0.35:
            notes.append(
                "Directness of wording differs from this user's usual style."
            )

        # --- emotional tone vs established range ---
        tone_range = baseline.emotional_tone_range or {}
        cur_tone = float(features["emotional_tone"])
        t_min = float(tone_range["min"]) if "min" in tone_range else None
        t_max = float(tone_range["max"]) if "max" in tone_range else None
        t_mean = float(tone_range["mean"]) if "mean" in tone_range else 0.5
        if t_min is not None and t_max is not None and sample_count > 0:
            # Outside prior min–max is a stronger signal than distance from mean
            if cur_tone < t_min - 0.05 or cur_tone > t_max + 0.05:
                d_tone = min(1.0, abs(cur_tone - t_mean) + 0.25)
                notes.append(
                    "Emotional tone sits outside the range seen so far for this user."
                )
            else:
                d_tone = abs(cur_tone - t_mean) * 0.5
        else:
            d_tone = abs(cur_tone - t_mean) * 0.4
        signals["emotional_tone"] = {
            "baseline_mean": round(t_mean, 3),
            "baseline_min": None if t_min is None else round(t_min, 3),
            "baseline_max": None if t_max is None else round(t_max, 3),
            "current": round(cur_tone, 3),
            "delta": round(d_tone, 3),
        }
        weighted_parts.append(min(1.0, d_tone))

        # --- playfulness ---
        base_play = float(baseline.playfulness_level)
        cur_play = float(features["playfulness"])
        d_play = abs(cur_play - base_play)
        signals["playfulness"] = {
            "baseline": round(base_play, 3),
            "current": round(cur_play, 3),
            "delta": round(d_play, 3),
        }
        weighted_parts.append(d_play)
        if d_play >= 0.35:
            notes.append(
                "Playfulness / casualness differs from this user's usual level."
            )

        # --- topic continuity ---
        recent = list(
            (baseline.topic_continuity or {}).get("recent_topics") or []
        )
        cur_topics = list(features.get("topics") or [])
        if recent and cur_topics:
            overlap = len(set(recent) & set(cur_topics)) / max(
                1, len(set(cur_topics))
            )
            d_topic = 1.0 - overlap
        elif cur_topics and not recent:
            d_topic = 0.15  # first topics — mild novelty only
        else:
            d_topic = 0.0
        base_cont = float(
            (baseline.topic_continuity or {}).get("continuity_score", 0.5)
        )
        signals["topic_continuity"] = {
            "baseline_continuity_score": round(base_cont, 3),
            "current_topics": cur_topics[:8],
            "recent_topics_sample": recent[-6:],
            "novelty": round(d_topic, 3),
        }
        weighted_parts.append(d_topic * 0.7)
        if d_topic >= 0.7 and sample_count >= self.min_samples_for_deviation:
            notes.append(
                "Topics differ from recent themes this user has been covering."
            )

        if not weighted_parts:
            score = 0.0
        else:
            score = _clamp01(sum(weighted_parts) / len(weighted_parts))

        established = sample_count >= self.min_samples_for_deviation
        significant = bool(
            established and score >= self.deviation_threshold
        )
        if not established and score >= self.deviation_threshold:
            notes.append(
                "Baseline still forming (few samples); treat any shift as tentative."
            )
        if not notes and significant:
            notes.append(
                "Several style signals differ from this user's baseline together."
            )

        return DeviationReport(
            user_id=user_id,
            has_significant_deviation=significant,
            score=score,
            signals=signals,
            notes=notes,
            sample_count=sample_count,
        )

    def reset_baseline(self, user_id: str = "default") -> UserBaseline:
        """Reset the user's baseline to neutral defaults and persist it.

        User control: clearing baseline memory is always allowed and does
        not require justification. Also clears free-text notes.
        """
        fresh = UserBaseline(
            user_id=user_id,
            communication_patterns={
                "message_length_score": _DEFAULT_LENGTH_SCORE,
                "directness": _DEFAULT_DIRECTNESS,
                "sample_count": 0,
            },
            emotional_tone_range={},
            topic_continuity={"recent_topics": [], "continuity_score": 0.5},
            playfulness_level=_DEFAULT_PLAYFULNESS,
            notes="",
            updated_at=_utc_now_iso(),
        )
        self._persistence.save_baseline(fresh)
        return fresh

    def set_notes(self, user_id: str, notes: str) -> UserBaseline:
        """User-controllable free-text note on the baseline (privacy-filtered on save)."""
        baseline = self.get_baseline(user_id)
        baseline.notes = notes or ""
        baseline.updated_at = _utc_now_iso()
        self._persistence.save_baseline(baseline)
        return baseline

    def adjust_playfulness(self, user_id: str, level: float) -> UserBaseline:
        """User-controllable direct set of playfulness level (0–1)."""
        baseline = self.get_baseline(user_id)
        baseline.playfulness_level = _clamp01(level)
        baseline.updated_at = _utc_now_iso()
        self._persistence.save_baseline(baseline)
        return baseline

    # ------------------------------------------------------------------
    # Feature extraction (lightweight heuristics)
    # ------------------------------------------------------------------

    def _extract_features(
        self,
        interaction: dict[str, Any],
        baseline: UserBaseline,
    ) -> dict[str, Any]:
        text = str(
            interaction.get("text")
            or interaction.get("message")
            or interaction.get("content")
            or ""
        ).strip()
        words = self._tokenize(text)

        # Message length score: map word count onto ~0–1 (soft cap at 80 words)
        if "message_length" in interaction:
            raw_len = float(interaction["message_length"])
            # Treat as word count if small, else chars
            if raw_len > 200:
                length_score = _clamp01(raw_len / 400.0)
            else:
                length_score = _clamp01(raw_len / 80.0)
        elif words:
            length_score = _clamp01(len(words) / 80.0)
        else:
            length_score = float(
                (baseline.communication_patterns or {}).get(
                    "message_length_score", _DEFAULT_LENGTH_SCORE
                )
            )

        # Directness
        if "directness" in interaction:
            directness = _clamp01(float(interaction["directness"]))
        elif words:
            hedges = sum(1 for w in words if w in _HEDGE_MARKERS)
            # More hedges → less direct; short + few hedges → more direct
            hedge_ratio = hedges / max(1, len(words))
            directness = _clamp01(0.75 - hedge_ratio * 2.0 + (0.1 if len(words) < 12 else 0.0))
        else:
            directness = float(
                (baseline.communication_patterns or {}).get(
                    "directness", _DEFAULT_DIRECTNESS
                )
            )

        # Emotional tone (0–1 descriptive intensity/valence blend — not a diagnosis)
        if "emotional_tone" in interaction:
            emotional_tone = _clamp01(float(interaction["emotional_tone"]))
        elif "tone" in interaction:
            emotional_tone = _clamp01(float(interaction["tone"]))
        elif words:
            pos = sum(1 for w in words if w in _POS_TONE)
            neg = sum(1 for w in words if w in _NEG_TONE)
            # Map: more positive markers → higher; more negative → lower; both → mid intensity
            if pos == 0 and neg == 0:
                emotional_tone = 0.5
            else:
                emotional_tone = _clamp01(0.5 + 0.15 * (pos - neg))
        else:
            mean = (baseline.emotional_tone_range or {}).get("mean", 0.5)
            emotional_tone = float(mean)

        # Playfulness
        if "playfulness" in interaction:
            playfulness = _clamp01(float(interaction["playfulness"]))
        elif text:
            lower = text.lower()
            hits = sum(1 for m in _PLAYFUL_MARKERS if m in lower)
            excl = text.count("!")
            playfulness = _clamp01(0.35 + 0.12 * hits + 0.05 * min(3, excl))
        else:
            playfulness = float(baseline.playfulness_level)

        # Topics (coarse tokens; drop tiny/common words)
        if "topics" in interaction and interaction["topics"] is not None:
            topics = [
                str(t).lower().strip()[:_MAX_TOPIC_TOKEN_LEN]
                for t in interaction["topics"]
                if str(t).strip()
            ]
        elif words:
            stop = {
                "the", "a", "an", "and", "or", "but", "to", "of", "in", "on",
                "for", "is", "it", "i", "you", "we", "they", "my", "me", "this",
                "that", "with", "as", "at", "be", "was", "are", "have", "has",
                "not", "do", "did", "so", "if", "just", "about", "from",
            }
            topics = [
                w for w in words
                if len(w) > 3 and w not in stop
            ][:8]
        else:
            topics = []

        return {
            "message_length_score": length_score,
            "directness": directness,
            "emotional_tone": emotional_tone,
            "playfulness": playfulness,
            "topics": topics,
        }

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        return re.findall(r"[a-zA-Z']+|[^\w\s]", text.lower())

    # ------------------------------------------------------------------
    # Update merge
    # ------------------------------------------------------------------

    def _apply_update(
        self,
        baseline: UserBaseline,
        features: dict[str, Any],
        *,
        user_id: str,
    ) -> UserBaseline:
        alpha = self.ema_alpha
        patterns = dict(baseline.communication_patterns or {})
        sample_count = int(patterns.get("sample_count", 0)) + 1

        prev_len = float(patterns.get("message_length_score", _DEFAULT_LENGTH_SCORE))
        prev_dir = float(patterns.get("directness", _DEFAULT_DIRECTNESS))
        # First sample: take observation as-is; later: EMA
        if sample_count == 1:
            new_len = float(features["message_length_score"])
            new_dir = float(features["directness"])
            new_play = float(features["playfulness"])
        else:
            new_len = _ema(prev_len, float(features["message_length_score"]), alpha)
            new_dir = _ema(prev_dir, float(features["directness"]), alpha)
            new_play = _ema(
                float(baseline.playfulness_level),
                float(features["playfulness"]),
                alpha,
            )

        patterns["message_length_score"] = round(_clamp01(new_len), 4)
        patterns["directness"] = round(_clamp01(new_dir), 4)
        patterns["sample_count"] = sample_count
        # Optional rolling raw word-count hint for inspectability
        if "message_length_score" in features:
            patterns["last_length_score"] = round(
                float(features["message_length_score"]), 4
            )

        # Emotional tone range: expand min/max, EMA mean
        tone = float(features["emotional_tone"])
        tr = dict(baseline.emotional_tone_range or {})
        if "mean" not in tr:
            tr["mean"] = tone
            tr["min"] = tone
            tr["max"] = tone
        else:
            tr["mean"] = round(_ema(float(tr["mean"]), tone, alpha), 4)
            tr["min"] = round(min(float(tr["min"]), tone), 4)
            tr["max"] = round(max(float(tr["max"]), tone), 4)

        # Topic continuity
        tc = dict(baseline.topic_continuity or {})
        recent = list(tc.get("recent_topics") or [])
        new_topics = list(features.get("topics") or [])
        if new_topics:
            for t in new_topics:
                if t not in recent:
                    recent.append(t)
            recent = recent[-_MAX_RECENT_TOPICS:]
            if len(recent) > 0 and new_topics:
                overlap = len(set(recent) & set(new_topics)) / max(
                    1, len(set(new_topics))
                )
            else:
                overlap = 0.5
            prev_c = float(tc.get("continuity_score", 0.5))
            if sample_count == 1:
                continuity = overlap
            else:
                continuity = _ema(prev_c, overlap, alpha)
            tc["recent_topics"] = recent
            tc["continuity_score"] = round(_clamp01(continuity), 4)
            tc["last_topics"] = new_topics[:8]

        return UserBaseline(
            user_id=user_id,
            communication_patterns=patterns,
            emotional_tone_range=tr,
            topic_continuity=tc,
            playfulness_level=round(_clamp01(new_play), 4),
            notes=baseline.notes,
            updated_at=_utc_now_iso(),
            schema_version=baseline.schema_version,
        )
