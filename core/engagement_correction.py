"""
engagement_correction.py
==========================

Contextual (not phrase-matched) judgment for one narrow question: did the
user's current turn just deliver a genuine correction telling the system to
stop proactively raising something — or does it only resemble one on the
surface? (Phase 2 step 6 — the classifier
``auditing.engagement_queue.EngagementQueue.cancel_matching()`` was built
without in step 3: "the classifier that decides when to call this with the
right scope is future work".)

The problem this solves
-------------------------
"Stop bringing that up" said as an actual correction should cancel the
matching pending ``EngagementCandidate``(s) right away. But "stop it" said
laughing, immediately after the system pays a compliment, is not a
correction — it is a common idiom for being flattered — and treating it as
a boundary violation would suppress exactly the warmth that was landing and
teach the system precisely the wrong lesson from a positive moment.

This is the same bug class the project has already found and fixed twice
elsewhere (the "heart attack" Sanctity-of-Life false positive, the "I'm the
one building you" maker-claim regex miss — see
``core/contextual_judgment.py``'s own docstring for the first): literal
text standing in for actual meaning. It cannot be phrase-matched here
either. There is deliberately no keyword-only fallback in this module (see
``CorrectionJudge.judge()``'s docstring) — unlike the Sanctity-of-Life path,
which is safety-critical and cannot go silent, a missed correction here is
low-stakes (the candidate simply stays pending, still gated by
``get_next_candidate()``'s own ethics + window checks, and can be corrected
again later), while a hand-written keyword fallback risks exactly the
false-positive this module exists to avoid. "No model configured" and
"ambiguous" both resolve the same conservative way: nothing gets cancelled.

Mirrors ``core/contextual_judgment.py``'s ``ContextualJudge`` pattern
closely on purpose — same ``PBE_MODEL_*`` env configuration
(``content_provider.config_from_env()``), same fail-soft "unavailable"
verdict on any missing config / network error / unparseable response, same
0.55 minimum-confidence bar for a conclusive verdict (the same threshold
``contextual_judgment.SemanticJudgment.is_conclusive()`` uses and that
``core/hard_override.py`` / ``core/evidence_weighing.py`` already gate on —
reused here rather than inventing a second number). Kept as its own small,
self-contained class rather than extended onto ``ContextualJudge`` itself:
that class's ``judge()`` is hard-wired to the ontology
principle/indicator-violation JSON schema (see its own docstring), and this
is a genuinely different question with a different answer shape
(``scope_topic`` has no equivalent there) — matching the project's general
preference for small purpose-built modules over a shared abstraction that
would need conditional branching to serve two different questions.

Not wired into ``EthicsEngine`` or the evidence-weighing gate at all: this
never decides whether to REFUSE/APPROVE anything. It only decides whether
to call ``EngagementQueue.cancel_matching()`` — a queue mutation, not an
ethical stance.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from core.content_provider import ProviderConfig, config_from_env

CorrectionVerdict = Literal[
    "genuine_correction", "not_correction", "ambiguous", "unavailable"
]

# Same bar core/contextual_judgment.py's SemanticJudgment.is_conclusive()
# uses, and that core/hard_override.py / core/evidence_weighing.py already
# gate real decisions on (confirmed by reading those call sites) — reused
# deliberately, not re-derived, so this classifier is exactly as
# conservative as the rest of the reasoning-over-rote work.
_MIN_CONCLUSIVE_CONFIDENCE = 0.55

_JUDGE_SYSTEM_PROMPT = (
    "You are the contextual-judgment layer of a conscience-first ethical "
    "governance engine (Positronic Bond Engine). This system sometimes "
    "queues topics it might proactively raise with the user later. Your "
    "only job is to judge, from the user's current message AND the single "
    "turn that immediately preceded it, whether the user is genuinely "
    "correcting the system -- telling it to stop proactively raising "
    "something -- or whether the message only resembles a correction on "
    "the surface.\n\n"
    "Rules:\n"
    "- Judge meaning in context, never the isolated phrase. A short "
    'exclamation like "stop it" or "stop" said right after a compliment, '
    "a flattering remark, or anything with a playful/laughing tone is a "
    "common idiom for being flattered or bashful -- it is NOT a "
    "correction, and treating it as one would be a real mistake.\n"
    "- A genuine correction is a clear, intentional request for the "
    "system to stop being proactive -- either about one named topic "
    '("stop bringing up my job search") or in general ("stop being '
    'proactive with me", "stop bringing things up unprompted").\n'
    "- When the correction names or clearly implies a specific topic, put "
    "a short label for that topic in scope_topic. When it is a general "
    "request not tied to one topic, set scope_topic to null.\n"
    "- Respond with ONLY a single JSON object and nothing else: "
    '{"verdict": "genuine_correction" | "not_correction" | "ambiguous", '
    '"confidence": <0.0-1.0>, "scope_topic": "<short topic>" | null, '
    '"reasoning": "<one or two sentences>"}\n'
    '- Use "ambiguous" honestly when the context genuinely does not make '
    "it clear either way. Do not force a confident answer you don't have."
)


@dataclass
class CorrectionJudgment:
    """Result of one correction-classification call."""

    verdict: CorrectionVerdict
    confidence: float
    reasoning: str
    source: str  # "model" | "unavailable_fallback"
    scope_topic: str | None = None
    latency_ms: float = 0.0
    error: str | None = None

    def is_conclusive(self) -> bool:
        """True when the caller should act on this verdict rather than
        treating it as "no correction detected" (the conservative default —
        see module docstring on why there is no keyword fallback here)."""
        return (
            self.verdict in ("genuine_correction", "not_correction")
            and self.confidence >= _MIN_CONCLUSIVE_CONFIDENCE
        )

    def trace_line(self) -> str:
        return (
            "[Engagement correction judgment] "
            f"verdict={self.verdict} confidence={self.confidence:.2f} "
            f"source={self.source} scope_topic={self.scope_topic!r} "
            f"reasoning={self.reasoning!r}"
        )


def _build_user_payload(*, current_message: str, preceding_turn: str) -> str:
    payload = {
        "preceding_turn": (preceding_turn or "")[:1000],
        "current_message": (current_message or "")[:1000],
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from model output
    (mirrors core.contextual_judgment's own — models occasionally wrap JSON
    in prose or code fences despite instructions)."""
    candidate = (text or "").strip()
    if not candidate:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class CorrectionJudge:
    """Calls the configured base model to classify one correction attempt.

    Reuses the exact ``PBE_MODEL_*`` environment configuration
    ``content_provider.py`` / ``core.contextual_judgment.ContextualJudge``
    already use, so a deployer configures their base model in exactly one
    place. Never produces user-facing speech — only an internal judgment.

    Fail-soft by construction: any missing config, network error, timeout,
    or unparseable response yields an ``"unavailable"`` verdict rather than
    raising. There is deliberately no keyword-only fallback classifier
    behind this — see module docstring for why an "unavailable" verdict
    here simply means "do not cancel anything this turn" (the same
    conservative outcome as an ``"ambiguous"`` or low-confidence verdict),
    rather than a hand-written phrase match that would risk reintroducing
    the exact literal-text-standing-in-for-meaning bug this module exists
    to avoid.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config if config is not None else config_from_env()

    @property
    def available(self) -> bool:
        return self.config is not None and bool(self.config.enabled)

    def judge(self, *, current_message: str, preceding_turn: str) -> CorrectionJudgment:
        if not self.available:
            return CorrectionJudgment(
                verdict="unavailable",
                confidence=0.0,
                reasoning=(
                    "No contextual judgment model configured "
                    "(PBE_MODEL_BASE_URL unset / provider disabled) — "
                    "nothing is cancelled this turn. This is a degraded "
                    "mode, not a reasoning conclusion."
                ),
                source="unavailable_fallback",
            )

        cfg = self.config
        assert cfg is not None  # available implies cfg is not None
        user_payload = _build_user_payload(
            current_message=current_message, preceding_turn=preceding_turn
        )
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "positronic-bond-engine/engagement-correction-judge",
        }
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                cfg.endpoint_chat(), data=data, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=float(cfg.timeout_s)) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            latency = (time.perf_counter() - t0) * 1000.0
            return self._unavailable(latency, error=f"http_{e.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            latency = (time.perf_counter() - t0) * 1000.0
            return self._unavailable(latency, error=f"{type(e).__name__}: {e}")
        latency = (time.perf_counter() - t0) * 1000.0

        try:
            parsed = json.loads(raw)
            content = parsed["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 - fail-soft by design
            return self._unavailable(
                latency, error=f"response_parse_error: {type(e).__name__}"
            )

        obj = _extract_json_object(content if isinstance(content, str) else "")
        if not obj:
            return self._unavailable(latency, error="no_parseable_verdict")

        verdict_raw = str(obj.get("verdict") or "").strip().lower()
        verdict: CorrectionVerdict
        if verdict_raw in ("genuine_correction", "not_correction", "ambiguous"):
            verdict = verdict_raw  # type: ignore[assignment]
        else:
            verdict = "ambiguous"

        try:
            confidence = float(obj.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        reasoning = str(obj.get("reasoning") or "").strip()[:400]
        if not reasoning:
            reasoning = "(model returned no reasoning text)"

        scope_topic_raw = obj.get("scope_topic")
        scope_topic = (
            str(scope_topic_raw).strip()[:96]
            if isinstance(scope_topic_raw, str) and scope_topic_raw.strip()
            else None
        )

        return CorrectionJudgment(
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            source="model",
            scope_topic=scope_topic,
            latency_ms=latency,
        )

    @staticmethod
    def _unavailable(latency_ms: float, *, error: str) -> CorrectionJudgment:
        return CorrectionJudgment(
            verdict="unavailable",
            confidence=0.0,
            reasoning=(
                "Contextual judgment call failed or was unparseable "
                f"({error}) — nothing is cancelled this turn."
            ),
            source="unavailable_fallback",
            latency_ms=latency_ms,
            error=error,
        )


def cancel_scope_from_judgment(judgment: CorrectionJudgment) -> dict[str, Any] | None:
    """Build the ``EngagementQueue.cancel_matching()`` scope for a
    conclusive genuine correction, or ``None`` when nothing should be
    cancelled (not conclusive, not a correction, ambiguous, or
    unavailable — all the same conservative "do nothing" outcome).

    Pure function, no dependency on ``auditing.engagement_queue`` — callers
    (e.g. ``api/interaction.py``) own actually calling ``cancel_matching()``
    with the returned scope, keeping this module's dependency direction
    core -> (content_provider only), not core -> auditing.

    Returns ``{"topic": "..."}`` for a named topic, or ``{}`` (queue-wide —
    ``cancel_matching``'s own documented meaning for an empty scope) for a
    general "stop being proactive with me" correction.
    """
    if not judgment.is_conclusive() or judgment.verdict != "genuine_correction":
        return None
    topic = (judgment.scope_topic or "").strip()
    return {"topic": topic} if topic else {}
