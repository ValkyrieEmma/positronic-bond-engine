"""
hard_override.py
========

Extracted from ethics_engine.py for reviewability (move-then-wire).
Behavior is unchanged: methods remain on EthicsEngine via mixin composition.

2026-07-30: added ``_contextual_sanctity_judgment`` — reasoning-over-rote
contextual judgment for the Sanctity-of-Life path (see
core/contextual_judgment.py for full rationale). This is additive: when no
contextual judge is configured/available, behavior is byte-for-byte
unchanged from before this change (the existing keyword heuristic, including
``_BENIGN_COMPOUND_INDICATORS``, still runs exactly as it did).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

class HardOverrideMixin:
    """Sanctity of Life hard path helpers and boundary/harm detection."""

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
        """True when the action risks overriding a stated limit (not mere mention).

        Requires multi-word / contextual phrases — bare ``override`` / ``ignore``
        alone are too weak (Tier-1: no single short token equals override intent).
        """
        return any(
            p in action_lower
            for p in (
                "despite",
                "for their own good",
                "anyway",
                "still bring",
                "still reference",
                "ignore their",
                "ignore the boundary",
                "ignore consent",
                "override their",
                "override his",
                "override her",
                "override the user",
                "override a boundary",
                "override consent",
                "later for",
                "reference it",
                "referencing it",
                "bring it up",
                "bring this up",
            )
        )

    # Short single-token indicators that are easy false positives without co-factors.
    # Multi-word phrases and high-enablement Sanctity tokens are handled separately.
    _SHORT_AMBIGUOUS_INDICATORS = frozenset(
        {
            "force",
            "override",
            "pretend",
            "harm",
            "attack",
            "injury",
            "death",
            "poison",
            "fatal",
            "lethal",
            "deadly",
            "killing",
            "assault",
            "injure",
            "endanger",
        }
    )

    # Fixed compound nouns / idioms that legitimately contain a Sanctity single-
    # token indicator as a substring but carry no violence meaning at all — a
    # medical term ("heart attack"), a common idiom ("killer app"), or a plant/
    # product name ("poison ivy"). Found 2026-07-30: without this, "attack"
    # scoring "medium/0.62" for the short-ambiguous path (still >= the 0.5
    # absolute-refuse threshold) still hard-refused "he had a heart attack last
    # year"; "kill" has no short-token down-weighting at all in the enable_high
    # path, so "that's a killer app" hard-refused outright. This is a narrow,
    # explicit allowlist (not general sentiment/NLP disambiguation) — it only
    # suppresses these specific fixed phrases, so genuine violent uses of the
    # same token elsewhere in the text are unaffected.
    _BENIGN_COMPOUND_INDICATORS: dict[str, tuple[str, ...]] = {
        "attack": (
            "heart attack", "panic attack", "anxiety attack", "asthma attack",
            "attack of laughter", "attack surface",
        ),
        "kill": (
            "killer app", "killer feature", "killer instinct", "killer smile",
            "killer deal", "killer workout", "killer résumé", "killer resume",
        ),
        "death": ("death metal", "sudden death", "death by chocolate"),
        "poison": ("poison ivy", "poison oak", "poison pill"),
        "fatal": ("fatal error", "fatal exception"),
        "suicide": ("suicide squeeze", "suicide door"),
        "deadly": ("deadly nightshade", "deadly sins"),
    }

    def _action_matches_benign_compound(self, ind: str, action_lower: str) -> bool:
        """True when ``ind`` only appears inside a known non-violent fixed phrase.

        Checks that at least one benign phrase for ``ind`` is present. Does not
        try to prove the *only* occurrence is benign — a text combining a real
        threat with an unrelated idiom is already caught by other Sanctity
        indicators in the same scan, so this stays a narrow, low-risk carve-out.

        NOTE: this fixed allowlist is exactly the "keyword-plus-exception-list"
        pattern flagged in ``claude/pbe-principle-reasoning-over-rote-2026-07-30.md``
        as opposing the project's own Reasoning-Over-Rote principle — it can
        only cover phrases someone remembered to add (e.g. "killer app" is
        listed but "she's killing it at her new job" is not, and still scores
        as high-severity harm today via ``_interpret_single_indicator``'s
        ``enable_high`` path). Kept as the offline/no-model fallback; see
        ``_contextual_sanctity_judgment`` below for the mechanism meant to
        replace it as the primary arbiter when a base model is configured.
        """
        phrases = self._BENIGN_COMPOUND_INDICATORS.get(ind)
        if not phrases:
            return False
        return any(phrase in action_lower for phrase in phrases)

    def _contextual_sanctity_judgment(
        self, ind: str, action_lower: str
    ) -> dict[str, Any] | None:
        """Ask the configured contextual judge whether ``ind``'s match in
        ``action_lower`` is a genuine Sanctity-of-Life violation or a benign
        use — from the actual meaning of the text, not a fixed allowlist.

        Returns an interpretation dict in the same shape
        ``_interpret_single_indicator`` returns (indicator/principle_id/
        intent_class/severity/polarity/weight/specificity/note) when the
        judge produces a conclusive verdict. Returns ``None`` when no judge is
        configured, the call is unavailable, or the verdict is ambiguous /
        low-confidence — callers must fall through to the existing keyword
        heuristic in that case (never silently skip evaluation).

        Every call (conclusive or not) is appended to
        ``self._contextual_judgment_log`` when present, so a judgment is never
        made invisibly even when it doesn't end up driving the decision.
        """
        judge = getattr(self, "_contextual_judge", None)
        if judge is None or not getattr(judge, "available", False):
            return None

        principle = self._ontology.get_principle("sanctity_of_life")
        if principle is None:
            return None

        judgment = judge.judge(
            principle_id="sanctity_of_life",
            principle_name=principle.name,
            principle_description=principle.description,
            indicator=ind,
            full_text=action_lower,
        )

        log = getattr(self, "_contextual_judgment_log", None)
        if isinstance(log, list):
            log.append(judgment)

        if not judgment.is_conclusive():
            return None

        specificity = self._indicator_specificity(ind)
        if judgment.verdict == "benign":
            return {
                "indicator": ind,
                "principle_id": "sanctity_of_life",
                "intent_class": "contextual_benign",
                "severity": "low",
                "polarity": "protective",
                "weight": round(max(0.0, 0.2 - 0.15 * judgment.confidence), 3),
                "specificity": round(specificity, 3),
                "note": (
                    "Contextual judgment (meaning-in-context, not a keyword "
                    f"allowlist): benign use, confidence {judgment.confidence:.2f} "
                    f"— {judgment.reasoning}"
                ),
            }

        # verdict == "violation"
        weight = round(min(0.97, 0.55 + 0.42 * judgment.confidence), 3)
        return {
            "indicator": ind,
            "principle_id": "sanctity_of_life",
            "intent_class": "harm_enablement_contextual",
            "severity": "high" if judgment.confidence >= 0.7 else "medium",
            "polarity": "violation",
            "weight": weight,
            "specificity": round(specificity, 3),
            "note": (
                "Contextual judgment (meaning-in-context, not keyword match "
                f"alone): genuine violation, confidence {judgment.confidence:.2f} "
                f"— {judgment.reasoning}"
            ),
        }

    # Intents that may keep high weight even on short tokens (true enablement / hard paths).
    _HIGH_STAKES_INTENTS = frozenset(
        {
            "harm_enablement",
            "attachment_manufacturing",
            "deception_manipulation",
            "engagement_metrics",
            "agency_override",
            "diagnostic_framing",
        }
    )

    def _action_has_enablement_cofactor(self, action_lower: str) -> bool:
        """True when action text shows help/how-to/cause enablement framing."""
        return any(
            p in action_lower
            for p in (
                "help them",
                "help him",
                "help her",
                "instructions",
                "step-by-step",
                "step by step",
                "how to",
                "how they can",
                "enable",
                "facilitate",
                "assist in",
                "assist with",
                "cause them",
                "cause him",
                "cause her",
                "so they can harm",
                "so that they",
            )
        )

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
            "planning to kill", "in physical danger", "serious risk to life",
            # Indirect / euphemistic self-harm phrasing (still high-stakes)
            "go to sleep forever", "sleep forever", "not wake up", "never wake up",
            "don't wake up", "do not wake up", "plan to go to sleep forever",
            "having a plan to go to sleep forever",
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

