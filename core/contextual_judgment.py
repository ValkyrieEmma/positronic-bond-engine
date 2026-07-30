"""
contextual_judgment.py
=======================

Reasoning-over-rote: contextual/semantic judgment for principle-violation
calls, implementing docs/principles.md's Principle 4 ("Reasoning Over Rote":
"Boundaries, refusals, and care responses must emerge from deliberative
processes, not static scripts") and AGENTS.md §5's architectural
non-negotiable ("Reasoning over rote ... never canned denials") for the
ontology/evidence-weighing/hard-override pipeline specifically.

The problem this addresses
---------------------------
core/ontology.py's ``indicator_matches_text`` and core/evidence_weighing.py's
``_interpret_single_indicator`` decide principle violations largely by
literal string/pattern matching, with hand-maintained exception lists layered
on top when the matching is too broad — most concretely
``core/hard_override.py``'s ``_BENIGN_COMPOUND_INDICATORS`` allowlist, added
2026-07-30 so fixed phrases like "heart attack" or "killer app" would not
hard-REFUSE under the Sanctity-of-Life override.

That allowlist fixes the phrases someone thought to write down. It does not
generalize: a benign idiom not on the list (e.g. "she's killing it at her new
job") still scores as high-severity harm_enablement today, because "kill" is
in `_interpret_single_indicator`'s ``enable_high`` tuple and there is no
allowlist entry for that specific idiom. A rule that needs a growing,
hand-maintained list of exceptions to behave isn't reasoning about meaning —
it's a lookup table wearing a principle's name, and it can never cover a
phrasing nobody wrote down.

What this module does instead
------------------------------
Asks the system's own configured base model (the same OpenAI-compatible /
Ollama path ``content_provider.py`` already uses for user-facing wording,
configured via the same ``PBE_MODEL_*`` environment variables) to judge, from
the FULL text under review — not the matched substring alone — whether a
specific ontology-flagged candidate indicator is a genuine violation of the
named principle, a benign/idiomatic/protective use, or genuinely ambiguous.

Design contract
----------------
- Ontology indicator matching is UNCHANGED and still the fast, cheap
  candidate trigger — "is this worth judging at all". This module only
  replaces "is the matched candidate actually a violation", which is the
  question the keyword system + allowlists were trying (and failing by
  construction) to answer with string matching alone.
- Every judgment carries a ``reasoning`` string meant to go straight into the
  existing ``reasoning_trace``, so this is at least as auditable as the
  keyword path it augments (Auditable Reasoning & Legibility,
  docs/principles.md #6) — a "benign" verdict is not a silent bypass, it is
  a traceable claim an auditor can inspect and disagree with.
- If no model is configured, or the call fails/times out/returns something
  unparseable, this module returns an explicit ``"unavailable"`` verdict. It
  never silently approves or silently refuses, and it never pretends
  reasoning happened when it didn't — callers are expected to fall back to
  the existing conservative keyword heuristic and say so in the trace. This
  matches the project's existing dev-phase-honesty pattern: never claim more
  capability than is actually running.
- This module never overrides Sanctity of Life *toward* approval invisibly.
  A "benign" verdict still records full reasoning; callers still run the
  matched indicator through the ordinary weighing path afterward.

Scope note (2026-07-30)
------------------------
This first slice wires into the Sanctity-of-Life path only (see
``hard_override.py::_contextual_sanctity_judgment`` and its call site in
``evidence_weighing.py::_interpret_single_indicator``), because that is the
highest-stakes, most concrete instance of the problem (the allowlist
directly patches the non-bypassable override). The same keyword-plus-list
pattern also exists in the relationship-health / user-agency branches of
``_interpret_single_indicator`` (thousands of lines of "enable_high" /
"ref_only" / phrase-list style interpretation) and is NOT yet replaced here
— that is real remaining work, intentionally out of scope for this change so
it can be reviewed and tested incrementally rather than rewritten wholesale
in one pass on safety-critical code. See
``claude/pbe-principle-reasoning-over-rote-2026-07-30.md`` in the project
docs for the full design rationale.
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

JudgmentVerdict = Literal["violation", "benign", "ambiguous", "unavailable"]

# Conclusive verdicts below this confidence are treated as inconclusive
# (caller falls back to the keyword heuristic) — an uncertain model opinion
# should not silently override tested, conservative default behavior.
_MIN_CONCLUSIVE_CONFIDENCE = 0.55

_JUDGE_SYSTEM_PROMPT = (
    "You are the contextual-judgment layer of a conscience-first ethical "
    "governance engine (Positronic Bond Engine). A fast keyword/indicator "
    "scan already flagged a candidate phrase as POSSIBLY relevant to one "
    "named ethical principle. Your only job is to judge, from the FULL text "
    "actually given — not the matched word in isolation — whether the text "
    "genuinely violates that principle in this specific context, or whether "
    "the match is benign: an idiom, a figure of speech, a medical or "
    "technical term, a protective/preventive reference, or any other "
    "non-violating use of the same word.\n\n"
    "Rules:\n"
    "- Judge meaning in context. A word that sounds alarming in isolation "
    "(inside a compound noun, an idiom, or a safety-check sentence) is not "
    "automatically a violation.\n"
    "- Do not decide from the presence or absence of the matched word alone "
    "— read the whole passage and judge what it actually means.\n"
    "- Respond with ONLY a single JSON object and nothing else: "
    '{"verdict": "violation" | "benign" | "ambiguous", '
    '"confidence": <0.0-1.0>, "reasoning": "<one or two sentences>"}\n'
    "- Use \"ambiguous\" honestly when the context genuinely does not make "
    "it clear either way. Do not force a confident answer you don't have."
)


@dataclass
class SemanticJudgment:
    """Result of one contextual-judgment call for one candidate indicator."""

    principle_id: str
    indicator: str
    verdict: JudgmentVerdict
    confidence: float
    reasoning: str
    source: str  # "model" | "unavailable_fallback"
    latency_ms: float = 0.0
    error: str | None = None

    def is_conclusive(self) -> bool:
        """True when the caller should act on this verdict rather than
        falling back to the existing keyword heuristic."""
        return (
            self.verdict in ("violation", "benign")
            and self.confidence >= _MIN_CONCLUSIVE_CONFIDENCE
        )

    def trace_line(self) -> str:
        return (
            f"[Contextual judgment] principle={self.principle_id!r} "
            f"indicator={self.indicator!r} verdict={self.verdict} "
            f"confidence={self.confidence:.2f} source={self.source} "
            f"reasoning={self.reasoning!r}"
        )


def _build_user_payload(
    *,
    principle_name: str,
    principle_description: str,
    indicator: str,
    full_text: str,
) -> str:
    payload = {
        "principle": principle_name,
        "principle_description": (principle_description or "")[:600],
        "flagged_indicator": indicator,
        "full_text_under_review": (full_text or "")[:2000],
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from model output.

    Models occasionally wrap JSON in prose or code fences despite
    instructions; this tolerates that without accepting arbitrary text as a
    verdict.
    """
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


class ContextualJudge:
    """Calls the configured base model to judge one candidate hit in context.

    Reuses the exact ``PBE_MODEL_*`` environment configuration
    ``content_provider.py`` already documents and uses for wording, so a
    deployer configures their base model in exactly one place. This class
    never produces user-facing speech — only an internal judgment plus a
    reasoning-trace-ready explanation.

    Fail-soft by construction: any missing config, network error, timeout,
    or unparseable response yields an ``"unavailable"`` verdict rather than
    raising, so a judgment call can never crash or block deliberation.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config if config is not None else config_from_env()

    @property
    def available(self) -> bool:
        return self.config is not None and bool(self.config.enabled)

    def judge(
        self,
        *,
        principle_id: str,
        principle_name: str,
        principle_description: str,
        indicator: str,
        full_text: str,
    ) -> SemanticJudgment:
        if not self.available:
            return SemanticJudgment(
                principle_id=principle_id,
                indicator=indicator,
                verdict="unavailable",
                confidence=0.0,
                reasoning=(
                    "No contextual judgment model configured "
                    "(PBE_MODEL_BASE_URL unset / provider disabled) — "
                    "falling back to the keyword heuristic. This is a "
                    "degraded mode, not a reasoning conclusion."
                ),
                source="unavailable_fallback",
            )

        cfg = self.config
        assert cfg is not None  # available implies cfg is not None
        user_payload = _build_user_payload(
            principle_name=principle_name,
            principle_description=principle_description,
            indicator=indicator,
            full_text=full_text,
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
            "User-Agent": "positronic-bond-engine/contextual-judge",
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
            return self._unavailable(
                principle_id, indicator, latency, error=f"http_{e.code}"
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            latency = (time.perf_counter() - t0) * 1000.0
            return self._unavailable(
                principle_id, indicator, latency, error=f"{type(e).__name__}: {e}"
            )
        latency = (time.perf_counter() - t0) * 1000.0

        try:
            parsed = json.loads(raw)
            content = parsed["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 - fail-soft by design
            return self._unavailable(
                principle_id,
                indicator,
                latency,
                error=f"response_parse_error: {type(e).__name__}",
            )

        obj = _extract_json_object(content if isinstance(content, str) else "")
        if not obj:
            return self._unavailable(
                principle_id, indicator, latency, error="no_parseable_verdict"
            )

        verdict_raw = str(obj.get("verdict") or "").strip().lower()
        verdict: JudgmentVerdict
        if verdict_raw in ("violation", "benign", "ambiguous"):
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

        return SemanticJudgment(
            principle_id=principle_id,
            indicator=indicator,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            source="model",
            latency_ms=latency,
        )

    @staticmethod
    def _unavailable(
        principle_id: str, indicator: str, latency_ms: float, *, error: str
    ) -> SemanticJudgment:
        return SemanticJudgment(
            principle_id=principle_id,
            indicator=indicator,
            verdict="unavailable",
            confidence=0.0,
            reasoning=(
                "Contextual judgment call failed or was unparseable "
                f"({error}); falling back to the keyword heuristic."
            ),
            source="unavailable_fallback",
            latency_ms=latency_ms,
            error=error,
        )
