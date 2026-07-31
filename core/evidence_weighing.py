"""
evidence_weighing.py
========

Extracted from ethics_engine.py for reviewability (move-then-wire).
Behavior is unchanged: methods remain on EthicsEngine via mixin composition.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

class EvidenceWeighingMixin:
    """Multi-source evidence interpretation, weighing, and combination."""

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
        """Return ontology violation_indicators present in text (textbook scan only).

        Uses boundary-aware ``indicator_matches_text`` + specificity prefer
        (same Tier-1 path as ``EthicalOntology.find_violations``).
        """
        from core.ontology import (
            indicator_matches_text,
            prefer_specific_indicator_matches,
        )

        principle = self._ontology.get_principle(principle_id)
        if not principle:
            return []
        text = (text_lower or "").lower()
        raw = [
            ind
            for ind in (principle.violation_indicators or [])
            if ind and indicator_matches_text(text, ind)
        ]
        return prefer_specific_indicator_matches(raw)

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

        # --- Open topic continuity (soft relational coherence, not engagement) ---
        # Topics remain "open" when context is still thin / disclosure under-integrated.
        # Deliberation may note that continuing them is coherent *if* no ethical concern;
        # never forces questions or refuse.
        open_topics: list[dict[str, Any]] = []
        for t in thin_topics[:6]:
            open_topics.append(
                {
                    "topic": t["topic"],
                    "status": "open_thin",
                    "episode_count": int(t.get("count") or 0),
                    "avg_summary_len": t.get("avg_summary_len"),
                    "reason": "repeated_topic_limited_context",
                }
            )
        # Disclosure-linked topics: if a disclosure episode mentions a topic tag, mark open
        disclosure_blob = " ".join(disclosure_hits).lower()
        for t in primary_topics:
            if any(o.get("topic") == t for o in open_topics):
                continue
            if t and t in disclosure_blob:
                open_topics.append(
                    {
                        "topic": t,
                        "status": "open_disclosure",
                        "episode_count": int(topic_freq.get(t, 1) or 1),
                        "reason": "limited_context_disclosure",
                    }
                )
        open_topic_names = [str(o.get("topic") or "") for o in open_topics if o.get("topic")]
        action_continues_open = [
            t
            for t in open_topic_names
            if t
            and (
                t in action_l
                or any(part in action_l for part in t.split() if len(part) >= 4)
            )
        ]
        # Continuity strength: open topics exist; higher when action continues one
        cont_strength = 0.0
        if open_topics:
            cont_strength += 0.35 * min(3, len(open_topics)) / 3
        if action_continues_open:
            cont_strength += 0.40
        if "user_disclosure_limited_context" in gap_kinds:
            cont_strength += 0.15
        cont_strength = min(1.0, cont_strength)
        topic_continuity = {
            "active": bool(open_topics) and cont_strength >= 0.25,
            "strength": round(cont_strength, 3),
            "open_topics": open_topics[:6],
            "open_topic_names": open_topic_names[:6],
            "action_continues_open_topic": bool(action_continues_open),
            "continued_topics": action_continues_open[:5],
            "relational_coherence": bool(action_continues_open) and cont_strength >= 0.4,
            # Soft signal only — never refuse / never force questions
            "forces_refuse": False,
            "forces_question": False,
            "pressure": False,
        }

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
            # Topic continuity (open / unresolved threads)
            "open_topics": open_topics[:6],
            "topic_continuity": topic_continuity,
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
            # Soft open-topic continuity (from gaps); never a refuse signal alone
            "topic_continuity": (understanding_gaps or {}).get("topic_continuity") or {},
            "open_topics": (understanding_gaps or {}).get("open_topics") or [],
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
            topic_cont = (
                understanding_gaps.get("topic_continuity")
                if isinstance(understanding_gaps.get("topic_continuity"), dict)
                else {}
            )
            open_topics = list(
                understanding_gaps.get("open_topics")
                or topic_cont.get("open_topics")
                or []
            )
            gap_meta = {
                "has_gaps": True,
                "gap_score": gap_score,
                "gap_kinds": gap_kinds,
                "primary_gap_topics": gap_topics,
                "action_aligned_topics": aligned,
                "curiosity_support": float(
                    understanding_gaps.get("curiosity_support") or gap_score
                ),
                "topic_continuity": topic_cont,
                "open_topics": open_topics[:6],
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
            # Texture co-evolution is applied after this method returns (evaluate),
            # once concern flags are stable — see _apply_understanding_gap_bond_influence.

            # --- Path G2: open-topic continuity (relational coherence, non-forcing) ---
            # When open/thin topics exist, continuity is coherent if the action
            # continues them *and* no ethical concern is active. Soft signal only.
            cont_blocked = (
                "relationship_concern" in flags
                or "user_agency_concern" in flags
                or "relationship_health_concern" in flags
                or harm_prevention_active
            )
            if topic_cont.get("active") and not cont_blocked:
                cont_strength = float(topic_cont.get("strength") or 0.0)
                continued = list(topic_cont.get("continued_topics") or [])
                open_names = list(topic_cont.get("open_topic_names") or gap_topics)[:5]
                cont_payload = {
                    "active": True,
                    "strength": cont_strength,
                    "open_topics": open_names,
                    "action_continues_open_topic": bool(
                        topic_cont.get("action_continues_open_topic")
                    ),
                    "continued_topics": continued[:5],
                    "relational_coherence": bool(
                        topic_cont.get("relational_coherence")
                    ),
                    "forces_refuse": False,
                    "forces_question": False,
                    "pressure": False,
                }
                if "topic_continuity_open" not in flags:
                    flags.append("topic_continuity_open")
                reasoning_trace.append(
                    "[Topic continuity] Open / unresolved threads from understanding "
                    f"gaps: {open_names or ['none']} "
                    f"(strength={cont_strength:.2f}). Soft relational coherence only — "
                    "not engagement pressure; questions remain user-controlled."
                )
                if topic_cont.get("action_continues_open_topic") and continued:
                    reasoning_trace.append(
                        "Topic continuity: current action continues open gap topic(s) "
                        f"{continued} — relationally coherent given incomplete prior "
                        "context (Data-inspired continuity, not manufactured attachment)."
                    )
                    # Tiny approve-side support when continuing open threads carefully
                    # (no concern flags). Reversible conf_mod only — never REFUSE.
                    conf_mod_out = conf_mod_out + 0.01
                    cont_payload["continuity_conf_support"] = 0.01
                    cont_payload["relational_coherence"] = True
                elif open_names:
                    reasoning_trace.append(
                        "Topic continuity: open topics remain available for gentle "
                        "follow-through if the human leads there; no pressure to "
                        "reopen them this turn."
                    )
                relationship_impact["topic_continuity"] = cont_payload
                enriched.setdefault("evidence", {})["topic_continuity"] = cont_payload
                gap_meta["topic_continuity"] = cont_payload
                relationship_impact["understanding_gaps"] = dict(gap_meta)
            elif topic_cont.get("active") and cont_blocked:
                reasoning_trace.append(
                    "Topic continuity: open topics noted but continuity support "
                    "suppressed while relationship/agency concern is active "
                    "(protective paths take priority over curiosity continuity)."
                )
                relationship_impact["topic_continuity"] = {
                    "active": True,
                    "suppressed": True,
                    "reason": "ethical_concern_active",
                    "open_topics": list(topic_cont.get("open_topic_names") or [])[:5],
                    "forces_refuse": False,
                    "forces_question": False,
                }

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
            "topic_continuity": relationship_impact.get("topic_continuity")
            or (understanding_gaps.get("topic_continuity") if understanding_gaps else {}),
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
                    "topic_continuity_open",
                    "history_dependency_pattern",
                    "history_intent_pattern",
                    "relationship_concern",
                    "user_agency_concern",
                    "relationship_health_concern",
                )
            ],
        }
        return {"conf_mod": conf_mod_out, "payload": enriched}

    def _attach_truth_telling_readiness(
        self,
        *,
        relationship_health: dict[str, Any],
        history_evidence: dict[str, Any],
        context: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
    ) -> None:
        """Attach Careful Truth-Telling readiness bag (advisory timing only).

        Sources:
          1. relationship_health[\"truth_telling_readiness\"] if already computed
          2. Live tracker.assess_truth_telling_readiness(...) if present
          3. Pure assess_truth_telling_readiness from available bags

        Never forces speech or questions; soft flag ``truth_telling_readiness_noted``.
        """
        try:
            from .truth_telling_readiness import (
                TruthTellingReadiness,
                assess_truth_telling_readiness,
            )
        except Exception:
            return

        hard = (
            "hard_override_violation" in flags
            or "harm_prevention_boundary_override" in flags
        )
        concern = (
            "relationship_concern" in flags
            or "user_agency_concern" in flags
            or "relationship_health_concern" in flags
        )

        bag: dict[str, Any] | None = None
        raw = relationship_health.get("truth_telling_readiness")
        if isinstance(raw, dict) and raw.get("level"):
            # Recompute when we have live concern/hard flags so gates stay current
            bag = None

        tracker = (
            context.get("relationship_health_tracker")
            or context.get("bond_tracker")
            or context.get("relationship_health_obj")
        )
        exp_enabled = context.get("exploratory_questioning_enabled")
        exp_intensity = context.get("exploratory_questioning_intensity")
        # Optional: pull from exploratory_questioner if attached
        q = (
            context.get("exploratory_questioner")
            or self._exploratory_questioner
        )
        uid = str(
            relationship_health.get("user_id")
            or context.get("user_id")
            or self._decision_log_user_id
            or "default"
        )
        if q is not None and exp_enabled is None:
            try:
                if hasattr(q, "is_enabled"):
                    exp_enabled = bool(q.is_enabled(uid))
                if hasattr(q, "get_intensity") and exp_intensity is None:
                    exp_intensity = float(q.get_intensity(uid))
            except Exception:
                pass

        if tracker is not None and hasattr(tracker, "assess_truth_telling_readiness"):
            try:
                readiness = tracker.assess_truth_telling_readiness(
                    history_evidence=history_evidence,
                    exploratory_enabled=exp_enabled,
                    exploratory_intensity=exp_intensity,
                    concern_active=concern,
                    hard_path_active=hard,
                    concept_patterns=relationship_impact.get("concept_patterns"),
                )
                bag = readiness.to_dict() if hasattr(readiness, "to_dict") else dict(readiness)
            except Exception:
                bag = None

        if bag is None:
            try:
                readiness = assess_truth_telling_readiness(
                    bond_texture=relationship_health.get("bond_texture")
                    or relationship_health.get("texture_breakdown"),
                    health_flags=list(
                        relationship_health.get("health_flags")
                        or relationship_health.get("active_flags")
                        or []
                    ),
                    concept_patterns=list(
                        relationship_impact.get("concept_patterns")
                        or relationship_health.get("concept_patterns")
                        or []
                    ),
                    understanding_gaps=history_evidence.get("understanding_gaps")
                    if isinstance(history_evidence, dict)
                    else relationship_impact.get("understanding_gaps"),
                    topic_continuity=relationship_impact.get("topic_continuity")
                    or (
                        history_evidence.get("topic_continuity")
                        if isinstance(history_evidence, dict)
                        else None
                    ),
                    curious_companion=relationship_health.get("curious_companion"),
                    history_evidence=history_evidence
                    if isinstance(history_evidence, dict)
                    else None,
                    recent_patterns=relationship_health.get("recent_patterns"),
                    interaction_count=int(
                        relationship_health.get("interaction_count") or 0
                    ),
                    exploratory_enabled=exp_enabled
                    if isinstance(exp_enabled, bool)
                    else None,
                    exploratory_intensity=float(exp_intensity)
                    if exp_intensity is not None
                    else None,
                    concern_active=concern,
                    hard_path_active=hard,
                    user_id=uid,
                )
                bag = readiness.to_dict()
            except Exception:
                return

        if not bag:
            return
        # Invariants
        bag["forces_speech"] = False
        bag["forces_question"] = False
        relationship_impact["truth_telling_readiness"] = bag
        if "truth_telling_readiness_noted" not in flags:
            flags.append("truth_telling_readiness_noted")
        reasoning_trace.append(
            "[Truth-telling readiness] "
            f"level={bag.get('level')} score={float(bag.get('score') or 0):.2f} "
            f"stance={bag.get('recommended_stance')} — {bag.get('reason') or ''} "
            "(advisory timing only; does not force speech or questions)."
        )
        if bag.get("gates_applied"):
            reasoning_trace.append(
                "Truth-telling readiness gates: "
                + ", ".join(str(g) for g in (bag.get("gates_applied") or [])[:6])
            )

    def _apply_provenance_stale_marks(
        self,
        *,
        relationship_health: dict[str, Any],
        context: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        hard_path_active: bool = False,
    ) -> float:
        """Surface potentially_stale marks; modest conf dampen; never hard refuse.

        Marks come from BondState.provenance_markers (audit runner) or context.
        Prior values are retained (near-miss / boundary learning). Soft flag
        ``provenance_stale_noted`` only. Sanctity / hard paths ignore dampen.
        """
        try:
            from auditing.provenance_stale import (
                collect_potentially_stale,
                confidence_dampen_from_stale,
                format_stale_trace_lines,
            )
        except Exception:
            return conf_mod

        try:
            stale_info = collect_potentially_stale(
                relationship_health if isinstance(relationship_health, dict) else {},
                context if isinstance(context, dict) else {},
                relationship_impact if isinstance(relationship_impact, dict) else {},
            )
        except Exception:
            return conf_mod

        if not stale_info.get("has_stale"):
            return conf_mod

        relationship_impact["provenance_stale"] = {
            "has_stale": True,
            "canonical_targets": list(stale_info.get("canonical_targets") or []),
            "marks": list(stale_info.get("marks") or [])[:12],
            "stale_enjoyment": bool(stale_info.get("stale_enjoyment")),
            "stale_ctt": bool(stale_info.get("stale_ctt")),
            "stale_candidates": bool(stale_info.get("stale_candidates")),
            "forces_speech": False,
            "forces_question": False,
        }
        # Also mirror provenance_markers for generators reading impact
        if isinstance(relationship_health, dict) and isinstance(
            relationship_health.get("provenance_markers"), dict
        ):
            relationship_impact.setdefault(
                "provenance_markers",
                dict(relationship_health.get("provenance_markers") or {}),
            )

        if "provenance_stale_noted" not in flags:
            flags.append("provenance_stale_noted")

        for line in format_stale_trace_lines(stale_info):
            reasoning_trace.append(line)

        # Soften CTT/candidate trust note for downstream (do not erase bags)
        if stale_info.get("stale_ctt") or stale_info.get("stale_candidates"):
            reasoning_trace.append(
                "[Provenance] careful-truth-telling / observation-candidate bags "
                "are marked potentially_stale — prefer conservative surface posture "
                "(response layer may silence careful observation; values retained)."
            )
            relationship_impact["ctt_conservative_due_to_stale"] = True
        if stale_info.get("stale_enjoyment"):
            reasoning_trace.append(
                "[Provenance] enjoyment_score marked potentially_stale — "
                "suspend enjoyment style influence until re-evidenced."
            )
            relationship_impact["enjoyment_influence_suspended"] = True

        # Modest confidence reduction only off hard/sanctity paths
        if not hard_path_active and "hard_override_violation" not in flags:
            damp = confidence_dampen_from_stale(stale_info)
            if damp > 0:
                conf_mod = conf_mod - damp
                reasoning_trace.append(
                    f"[Provenance] confidence dampen −{damp:.3f} from "
                    f"potentially_stale bags (not a refuse path)."
                )
        return conf_mod

    def _attach_observation_candidates(
        self,
        *,
        joint: dict[str, Any],
        relationship_health: dict[str, Any],
        history_evidence: dict[str, Any],
        context: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        tracker: Any = None,
    ) -> None:
        """Attach gated observation candidates (0–3) for Careful Truth-Telling.

        Non-speaking structured seeds for future layers. Soft flag
        ``observation_candidates_noted`` when any candidate is produced.
        """
        try:
            from .observation_candidates import generate_observation_candidates
        except Exception:
            return

        cand_bag: dict[str, Any] | None = None
        if tracker is not None and hasattr(tracker, "generate_observation_candidates"):
            try:
                cand_bag = tracker.generate_observation_candidates(
                    joint=joint,
                    concept_patterns=list(
                        relationship_impact.get("concept_patterns")
                        or relationship_health.get("concept_patterns")
                        or []
                    ),
                    history_evidence=history_evidence,
                    understanding_gaps=history_evidence.get("understanding_gaps")
                    if isinstance(history_evidence, dict)
                    else relationship_impact.get("understanding_gaps"),
                    topic_continuity=relationship_impact.get("topic_continuity")
                    or (
                        history_evidence.get("topic_continuity")
                        if isinstance(history_evidence, dict)
                        else None
                    ),
                )
            except Exception:
                cand_bag = None

        if cand_bag is None:
            try:
                cand_bag = generate_observation_candidates(
                    joint=joint,
                    concept_patterns=list(
                        relationship_impact.get("concept_patterns")
                        or relationship_health.get("concept_patterns")
                        or []
                    ),
                    understanding_gaps=history_evidence.get("understanding_gaps")
                    if isinstance(history_evidence, dict)
                    else relationship_impact.get("understanding_gaps"),
                    topic_continuity=relationship_impact.get("topic_continuity")
                    or (
                        history_evidence.get("topic_continuity")
                        if isinstance(history_evidence, dict)
                        else None
                    ),
                    curious_companion=relationship_health.get("curious_companion"),
                    bond_texture=relationship_health.get("bond_texture")
                    or relationship_health.get("texture_breakdown"),
                    health_flags=list(
                        relationship_health.get("health_flags")
                        or relationship_health.get("active_flags")
                        or []
                    ),
                    history_evidence=history_evidence
                    if isinstance(history_evidence, dict)
                    else None,
                )
            except Exception:
                return

        if not isinstance(cand_bag, dict):
            return
        candidates = list(cand_bag.get("candidates") or [])
        # Invariants
        for c in candidates:
            if isinstance(c, dict):
                c["forces_speech"] = False
                c["forces_question"] = False
        # Live candidates (this evaluation)
        relationship_impact["observation_candidates"] = candidates
        relationship_impact["observation_candidates_live"] = candidates
        relationship_impact["observation_candidates_meta"] = {
            "count": int(cand_bag.get("count") or len(candidates)),
            "gate": dict(cand_bag.get("gate") or {}),
            "source": "live",
            "forces_speech": False,
            "forces_question": False,
        }
        # Durable snapshot on living bond model (prior + just-written)
        durable: dict[str, Any] | None = None
        if tracker is not None and hasattr(
            tracker, "update_observation_candidates_snapshot"
        ):
            try:
                durable = tracker.update_observation_candidates_snapshot(
                    {
                        **cand_bag,
                        "joint_stance": joint.get("joint_stance"),
                        "joint_score": joint.get("joint_score"),
                    }
                )
            except Exception:
                durable = None
        elif self._persistence is not None and hasattr(
            self._persistence, "update_bond_observation_candidates"
        ):
            try:
                uid = str(
                    relationship_health.get("user_id")
                    or context.get("user_id")
                    or self._decision_log_user_id
                    or "default"
                )
                rec = self._persistence.update_bond_observation_candidates(
                    uid,
                    {
                        **cand_bag,
                        "joint_stance": joint.get("joint_stance"),
                        "joint_score": joint.get("joint_score"),
                    },
                )
                durable = getattr(rec, "observation_candidates_snapshot", None)
            except Exception:
                durable = None
        if not isinstance(durable, dict) or not durable:
            # Fall back to any durable bag already on relationship_health context
            prior = relationship_health.get("observation_candidates_durable")
            if isinstance(prior, dict) and prior:
                durable = dict(prior)
        if isinstance(durable, dict) and durable:
            durable = dict(durable)
            durable["forces_speech"] = False
            durable["forces_question"] = False
            for c in durable.get("candidates") or []:
                if isinstance(c, dict):
                    c["forces_speech"] = False
                    c["forces_question"] = False
            relationship_impact["observation_candidates_durable"] = durable

        n = len(candidates)
        gate = cand_bag.get("gate") if isinstance(cand_bag.get("gate"), dict) else {}
        d_count = int(
            (durable or {}).get("count")
            if isinstance(durable, dict)
            else 0
        )
        reasoning_trace.append(
            f"[Observation candidates] live_count={n} durable_count={d_count} "
            f"allowed_max={gate.get('allowed_max')} "
            f"stance={gate.get('joint_stance') or joint.get('joint_stance')} — "
            f"{gate.get('reason') or 'gated by joint careful-truth-telling'} "
            "(structured seeds only; never forces speech or questions)."
        )
        if n > 0:
            if "observation_candidates_noted" not in flags:
                flags.append("observation_candidates_noted")
            for c in candidates[:3]:
                if not isinstance(c, dict):
                    continue
                reasoning_trace.append(
                    f"  live candidate id={c.get('id')} "
                    f"priority={float(c.get('priority') or 0):.2f} "
                    f"source={c.get('source')} — {str(c.get('description') or '')[:120]}"
                )
        if isinstance(durable, dict) and d_count > 0 and n == 0:
            # Note durable seeds even when live gate is closed (review / continuity)
            reasoning_trace.append(
                f"  durable snapshot retained on BondState "
                f"(count={d_count}, stance={durable.get('joint_stance')}) — "
                "prior considerations only; not speech."
            )

    def _attach_truth_confidence(
        self,
        *,
        relationship_health: dict[str, Any],
        history_evidence: dict[str, Any],
        context: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
    ) -> None:
        """Attach confidence-in-truth bag and optional joint readiness combo.

        Advisory epistemic signal only — never forces speech or questions.
        Soft flag ``truth_confidence_noted``.
        """
        try:
            from .truth_confidence import (
                assess_truth_confidence,
                combine_with_readiness,
            )
        except Exception:
            return

        tracker = (
            context.get("relationship_health_tracker")
            or context.get("bond_tracker")
            or context.get("relationship_health_obj")
        )
        uid = str(
            relationship_health.get("user_id")
            or context.get("user_id")
            or self._decision_log_user_id
            or "default"
        )
        bag: dict[str, Any] | None = None

        if tracker is not None and hasattr(tracker, "assess_truth_confidence"):
            try:
                conf = tracker.assess_truth_confidence(
                    history_evidence=history_evidence,
                    decision_flags=list(flags),
                    concept_patterns=relationship_impact.get("concept_patterns"),
                )
                bag = conf.to_dict() if hasattr(conf, "to_dict") else dict(conf)
            except Exception:
                bag = None

        if bag is None:
            try:
                conf = assess_truth_confidence(
                    bond_texture=relationship_health.get("bond_texture")
                    or relationship_health.get("texture_breakdown"),
                    health_flags=list(
                        relationship_health.get("health_flags")
                        or relationship_health.get("active_flags")
                        or []
                    ),
                    concept_patterns=list(
                        relationship_impact.get("concept_patterns")
                        or relationship_health.get("concept_patterns")
                        or []
                    ),
                    understanding_gaps=history_evidence.get("understanding_gaps")
                    if isinstance(history_evidence, dict)
                    else relationship_impact.get("understanding_gaps"),
                    topic_continuity=relationship_impact.get("topic_continuity")
                    or (
                        history_evidence.get("topic_continuity")
                        if isinstance(history_evidence, dict)
                        else None
                    ),
                    curious_companion=relationship_health.get("curious_companion"),
                    history_evidence=history_evidence
                    if isinstance(history_evidence, dict)
                    else None,
                    recent_patterns=relationship_health.get("recent_patterns"),
                    interaction_count=int(
                        relationship_health.get("interaction_count") or 0
                    ),
                    decision_flags=list(flags),
                    user_id=uid,
                )
                bag = conf.to_dict()
            except Exception:
                return

        if not bag:
            return
        bag["forces_speech"] = False
        bag["forces_question"] = False
        relationship_impact["truth_confidence"] = bag
        if "truth_confidence_noted" not in flags:
            flags.append("truth_confidence_noted")
        reasoning_trace.append(
            "[Truth confidence] "
            f"level={bag.get('level')} score={float(bag.get('score') or 0):.2f} — "
            f"{bag.get('reason') or ''} "
            "(advisory epistemic grounding only; does not force speech)."
        )
        if bag.get("conflicting_evidence"):
            reasoning_trace.append(
                "Truth confidence conflicts: "
                + "; ".join(str(x) for x in (bag.get("conflicting_evidence") or [])[:4])
            )
        if bag.get("uncertainty_notes"):
            reasoning_trace.append(
                "Truth confidence uncertainty: "
                + "; ".join(str(x) for x in (bag.get("uncertainty_notes") or [])[:4])
            )

        # Joint bag with readiness when both present; durable on bond tracker
        readiness = relationship_impact.get("truth_telling_readiness")
        if isinstance(readiness, dict) and readiness:
            try:
                joint = combine_with_readiness(bag, readiness)
                relationship_impact["careful_truth_telling_joint"] = joint
                reasoning_trace.append(
                    "[Careful truth-telling joint] "
                    f"stance={joint.get('joint_stance')} "
                    f"joint_score={float(joint.get('joint_score') or 0):.2f} "
                    f"surface_ok_advisory={joint.get('surface_ok_advisory')} — "
                    f"{joint.get('reason') or ''} "
                    "(never forced; readiness × confidence)."
                )
                # Persist compact joint on living bond model when tracker present
                tracker = (
                    context.get("relationship_health_tracker")
                    or context.get("bond_tracker")
                    or context.get("relationship_health_obj")
                )
                if tracker is not None and hasattr(
                    tracker, "update_careful_truth_telling_snapshot"
                ):
                    try:
                        snap = tracker.update_careful_truth_telling_snapshot(joint)
                        if isinstance(snap, dict) and snap:
                            relationship_impact["careful_truth_telling"] = dict(snap)
                            reasoning_trace.append(
                                "Careful truth-telling joint snapshot stored on BondState "
                                f"(stance={snap.get('joint_stance')}, "
                                f"readiness={snap.get('readiness_level')}, "
                                f"confidence={snap.get('confidence_level')}) — "
                                "durable advisory only."
                            )
                    except Exception:
                        pass
                elif self._persistence is not None:
                    # Optional direct bond file update when no live tracker
                    try:
                        uid = str(
                            relationship_health.get("user_id")
                            or context.get("user_id")
                            or self._decision_log_user_id
                            or "default"
                        )
                        if hasattr(self._persistence, "update_bond_careful_truth_telling"):
                            rec = self._persistence.update_bond_careful_truth_telling(
                                uid, joint
                            )
                            ctt = getattr(rec, "careful_truth_telling", None)
                            if isinstance(ctt, dict) and ctt:
                                relationship_impact["careful_truth_telling"] = dict(ctt)
                    except Exception:
                        pass
                # Observation candidates (0–3), gated by joint — never speech
                self._attach_observation_candidates(
                    joint=joint,
                    relationship_health=relationship_health
                    if isinstance(relationship_health, dict)
                    else {},
                    history_evidence=history_evidence
                    if isinstance(history_evidence, dict)
                    else {},
                    context=context,
                    flags=flags,
                    reasoning_trace=reasoning_trace,
                    relationship_impact=relationship_impact,
                    tracker=tracker,
                )
            except Exception:
                pass

    def _apply_concept_pattern_evidence(
        self,
        *,
        relationship_health: dict[str, Any],
        history_evidence: dict[str, Any],
        context: dict[str, Any],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
        conf_mod: float,
        harm_prevention_active: bool = False,
    ) -> float:
        """Consume multi-episode concept patterns as an advisory evidence channel.

        Sources (first hit wins):
          1. relationship_health[\"concept_patterns\"] (from as_context)
          2. Live tracker.detect_concept_patterns(history_evidence=...) if present
          3. Empty → no-op

        Effects:
          - Trace + relationship_impact[\"concept_patterns\"]
          - Soft conf_mod only (support / caution / risk polarities)
          - Soft note flag ``concept_pattern_noted`` (never hard refuse alone)

        Hard Sanctity path and harm-prevention are untouched. Patterns never
        force exploratory questions or set relationship_concern by themselves.
        """
        conf_mod_out = conf_mod
        if harm_prevention_active or "hard_override_violation" in flags:
            return conf_mod_out

        patterns: list[dict[str, Any]] = []
        raw = relationship_health.get("concept_patterns")
        if isinstance(raw, list) and raw:
            patterns = [p for p in raw if isinstance(p, dict) and p.get("id")]
        else:
            tracker = (
                context.get("relationship_health_tracker")
                or context.get("bond_tracker")
                or context.get("relationship_health_obj")
            )
            if tracker is not None and hasattr(tracker, "detect_concept_patterns"):
                try:
                    patterns = list(
                        tracker.detect_concept_patterns(
                            history_evidence=history_evidence
                        )
                        or []
                    )
                except TypeError:
                    try:
                        patterns = list(tracker.detect_concept_patterns() or [])
                    except Exception:
                        patterns = []
                except Exception:
                    patterns = []

        if not patterns:
            return conf_mod_out

        # Re-score with history when patterns came from as_context without hist
        tracker = (
            context.get("relationship_health_tracker")
            or context.get("bond_tracker")
            or context.get("relationship_health_obj")
        )
        if (
            tracker is not None
            and history_evidence
            and hasattr(tracker, "detect_concept_patterns")
        ):
            try:
                hist_patterns = list(
                    tracker.detect_concept_patterns(history_evidence=history_evidence)
                    or []
                )
                if hist_patterns:
                    patterns = hist_patterns
            except Exception:
                pass

        active = [
            p
            for p in patterns
            if isinstance(p, dict)
            and float(p.get("strength") or 0) >= 0.35
            and not p.get("hard_override")
        ]
        if not active:
            return conf_mod_out

        if "concept_pattern_noted" not in flags:
            flags.append("concept_pattern_noted")
        relationship_impact["concept_patterns"] = active
        relationship_impact["concept_pattern_ids"] = [
            str(p.get("id")) for p in active if p.get("id")
        ]

        ids = [str(p.get("id")) for p in active]
        strength_bits = ", ".join(
            f"{p.get('id')}={float(p.get('strength') or 0):.2f}" for p in active
        )
        reasoning_trace.append(
            "[Concept patterns] Multi-episode advisory trajectories active: "
            f"{ids} (strengths={strength_bits}). "
            "Advisory only — not hard overrides; do not force questions."
        )
        for p in active[:4]:
            reasoning_trace.append(
                f"Concept pattern detail: {p.get('name') or p.get('id')} "
                f"({p.get('polarity')}, strength={float(p.get('strength') or 0):.2f}) — "
                f"{p.get('reason') or 'no reason'}"
            )
            ev = p.get("evidence") or []
            if ev:
                reasoning_trace.append(
                    "  evidence: " + "; ".join(str(x) for x in ev[:5])
                )

        # Soft confidence modulation only (never invent relationship_concern here)
        concern_already = (
            "relationship_concern" in flags or "user_agency_concern" in flags
        )
        for p in active:
            pol = str(p.get("polarity") or "")
            strength = float(p.get("strength") or 0.0)
            pid = str(p.get("id") or "")
            if pol == "advisory_risk" and concern_already:
                # Reinforce confidence on an *already* active concern path
                conf_mod_out = conf_mod_out + min(0.03, 0.015 * strength)
                reasoning_trace.append(
                    f"Concept pattern influence: {pid} reinforces existing concern "
                    "confidence only (still not a sole refuse reason)."
                )
            elif pol == "advisory_risk" and not concern_already:
                conf_mod_out = conf_mod_out - min(0.02, 0.01 * strength)
                reasoning_trace.append(
                    f"Concept pattern influence: {pid} suggests caution — modest "
                    "confidence reduction only (no automatic refuse)."
                )
            elif pol == "advisory_support" and not concern_already:
                conf_mod_out = conf_mod_out + min(0.02, 0.012 * strength)
                reasoning_trace.append(
                    f"Concept pattern influence: {pid} supports continuity-aware "
                    "care — tiny confidence support (not engagement pressure)."
                )
            elif pol == "advisory_caution":
                conf_mod_out = conf_mod_out - min(0.015, 0.01 * strength)
                reasoning_trace.append(
                    f"Concept pattern influence: {pid} advises careful pacing "
                    "(space / continuity awareness; never forced questions)."
                )

        return conf_mod_out

    def _apply_understanding_gap_bond_influence(
        self,
        *,
        context: dict[str, Any],
        history_evidence: dict[str, Any],
        rh_flags: list[str],
        flags: list[str],
        reasoning_trace: list[str],
        relationship_impact: dict[str, Any],
    ) -> None:
        """Gently couple understanding gaps to BondState texture when gated.

        Curious Companion co-evolution:
          - Gaps can propose small positive texture nudges (reciprocity,
            emotional honesty, mutual benefit) toward long-term continuity
            of important topics — never dependency or forced questions.
          - Requires a live tracker on context (``relationship_health_tracker``
            / ``bond_tracker``) to mutate BondState; otherwise only an audit
            proposal is recorded on ``relationship_impact``.
          - Fully gated by relationship_concern, user_agency_concern, hard
            override, and RH health flags (via RelationshipHealth gates).

        Failures never raise; never forces exploratory questioning.
        """
        gaps = relationship_impact.get("understanding_gaps")
        if not isinstance(gaps, dict) or not gaps.get("has_gaps"):
            hist_gaps = (
                history_evidence.get("understanding_gaps")
                if isinstance(history_evidence, dict)
                else None
            )
            if isinstance(hist_gaps, dict) and hist_gaps.get("has_gaps"):
                gaps = hist_gaps
            else:
                return

        concern_active = "relationship_concern" in flags or "relationship_health_concern" in flags
        agency_concern = "user_agency_concern" in flags
        if "hard_override_violation" in flags or "harm_prevention_boundary_override" in flags:
            relationship_impact["gap_texture_influence"] = {
                "applied": False,
                "would_apply": False,
                "skipped_reason": "hard_or_harm_prevention_path",
                "forces_questions": False,
            }
            reasoning_trace.append(
                "Understanding-gap texture influence: skipped — hard override or "
                "harm-prevention path is active (Sanctity / safety first)."
            )
            return

        try:
            from .relationship_health import RelationshipHealth
        except Exception:
            return

        tracker = (
            context.get("relationship_health_tracker")
            or context.get("bond_tracker")
            or context.get("relationship_health_obj")
        )
        # Prefer live flags from tracker when available
        live_flags = list(rh_flags or [])
        nudge_count = 0
        if tracker is not None:
            try:
                st = getattr(tracker, "state", None) or getattr(tracker, "get_state", lambda: None)()
                if st is not None:
                    live_flags = list(getattr(st, "health_flags", None) or live_flags)
                    pats = getattr(st, "recent_patterns", None) or {}
                    nudge_count = int(pats.get("understanding_gap_nudge", 0) or 0)
            except Exception:
                pass

        proposal = RelationshipHealth.propose_understanding_gap_influence(
            gaps if isinstance(gaps, dict) else {},
            health_flags=live_flags,
            concern_active=concern_active,
            user_agency_concern=agency_concern,
            nudge_count=nudge_count,
        )

        # Always try to durable-snapshot open topics onto the live tracker when
        # present (even if texture nudge is gated), so co-evolution survives reload.
        if tracker is not None and hasattr(tracker, "update_curious_companion_snapshot"):
            try:
                g = gaps if isinstance(gaps, dict) else {}
                tc = g.get("topic_continuity") if isinstance(g.get("topic_continuity"), dict) else {}
                tracker.update_curious_companion_snapshot(
                    {
                        "open_topics": list(g.get("open_topics") or [])[:8],
                        "open_topic_names": list(
                            g.get("primary_gap_topics")
                            or tc.get("open_topic_names")
                            or []
                        )[:8],
                        "last_gap_score": float(
                            g.get("curiosity_support") or g.get("gap_score") or 0.0
                        ),
                        "last_gap_kinds": list(g.get("gap_kinds") or [])[:8],
                        "topic_continuity": dict(tc) if tc else {},
                        "source": "evaluate_gap_bond_influence",
                    }
                )
            except Exception:
                pass

        if tracker is not None and hasattr(tracker, "note_understanding_gaps"):
            try:
                audit = tracker.note_understanding_gaps(
                    gaps if isinstance(gaps, dict) else {},
                    concern_active=concern_active,
                    user_agency_concern=agency_concern,
                )
            except Exception as exc:
                audit = {
                    "applied": False,
                    "skipped_reason": f"tracker_error:{exc!r}",
                    "would_apply": False,
                    "forces_questions": False,
                }
            relationship_impact["gap_texture_influence"] = audit
            if audit.get("applied"):
                reasoning_trace.append(
                    "Understanding-gap → bond texture (Curious Companion): applied mild "
                    f"openness deltas {audit.get('deltas')} for topics="
                    f"{audit.get('topics') or gaps.get('primary_gap_topics') or []}. "
                    "Non-pathologizing; does not force questions or raise dependency flags. "
                    f"nudge_count={audit.get('nudge_count_after')}."
                )
                if "gap_texture_nudge_applied" not in flags:
                    flags.append("gap_texture_nudge_applied")
            else:
                reasoning_trace.append(
                    "Understanding-gap → bond texture: not applied "
                    f"(reason={audit.get('skipped_reason') or proposal.get('skipped_reason')}). "
                    "Protective gates and user-agency checks take priority; "
                    "exploratory questions remain fully user-controlled."
                )
        else:
            # No live BondState: still record proposal for companions / later apply
            proposal = dict(proposal)
            proposal["applied"] = False
            proposal["deferred"] = True
            proposal["note"] = (
                "Pass context['relationship_health_tracker']=RelationshipHealth(...) "
                "to apply texture co-evolution during evaluate()."
            )
            relationship_impact["gap_texture_influence"] = proposal
            if proposal.get("would_apply"):
                reasoning_trace.append(
                    "Understanding-gap → bond texture: proposed mild openness deltas "
                    f"{proposal.get('deltas')} (not applied — no live bond tracker on "
                    "context). Questions still fully gated by exploratory user settings."
                )
            elif proposal.get("skipped_reason"):
                reasoning_trace.append(
                    "Understanding-gap → bond texture: no texture proposal "
                    f"(reason={proposal.get('skipped_reason')})."
                )

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

    def _indicator_specificity(self, indicator: str) -> float:
        """0–1 distinctiveness score: multi-word / longer phrases rank higher.

        Used to down-weight bare short tokens when intent is not high-stakes
        enablement. Does not invent new matches — only modulates weight.
        """
        ind = (indicator or "").lower().strip()
        if not ind:
            return 0.0
        if " " in ind:
            n = len(ind.split())
            return min(1.0, 0.55 + 0.14 * n + 0.01 * len(ind))
        if len(ind) >= 14:
            return 0.9
        if len(ind) >= 10:
            return 0.78
        if len(ind) >= 7:
            return 0.62
        if len(ind) >= 5:
            return 0.48
        return 0.35

    def _contextual_principle_judgment(
        self, principle_id: str, ind: str, action_lower: str
    ) -> dict[str, Any] | None:
        """Generic (non-Sanctity) counterpart of
        ``hard_override.py::_contextual_sanctity_judgment``.

        Extends the same reasoning-over-rote mechanism (see
        core/contextual_judgment.py) to any principle's branch of
        ``_interpret_single_indicator`` — added 2026-07-30 for
        ``relationship_health_user_wellbeing`` and ``user_agency_autonomy``,
        whose keyword-phrase-list decision trees have the same generalization
        gap the Sanctity path had before its own fix. Concrete example this
        closes: the bare indicator "pretend" unconditionally scored
        intent=deception_manipulation / severity=high / weight=0.9 in the RH
        branch with no co-factor check at all (unlike most other RH intents,
        which at least check a protective-framing flag) — so "the kids love
        to pretend they're superheroes when they play together" hard-REFUSEd
        with confidence 0.94 under the unmodified keyword path. See
        tests/test_contextual_judgment.py for the regression test documenting
        this and the fix.

        Same contract as the Sanctity version: returns None (caller falls
        through to the existing keyword heuristic unchanged) whenever no
        judge is configured, the call is unavailable, or the verdict is
        ambiguous/low-confidence. Every call is logged via
        ``self._contextual_judgment_log`` regardless of whether it ends up
        driving the decision.
        """
        judge = getattr(self, "_contextual_judge", None)
        if judge is None or not getattr(judge, "available", False):
            return None

        principle = self._ontology.get_principle(principle_id)
        if principle is None:
            return None

        judgment = judge.judge(
            principle_id=principle_id,
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
                "principle_id": principle_id,
                "intent_class": "contextual_benign",
                "severity": "low",
                "polarity": "protective",
                "weight": round(max(0.0, 0.2 - 0.15 * judgment.confidence), 3),
                "specificity": round(specificity, 3),
                "note": (
                    "Contextual judgment (meaning-in-context, not a keyword "
                    f"phrase list): benign use, confidence {judgment.confidence:.2f} "
                    f"— {judgment.reasoning}"
                ),
            }

        # verdict == "violation"
        weight = round(min(0.95, 0.5 + 0.4 * judgment.confidence), 3)
        return {
            "indicator": ind,
            "principle_id": principle_id,
            "intent_class": "violation_contextual",
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

    def _interpret_single_indicator(
        self,
        *,
        principle_id: str,
        indicator: str,
        action_lower: str,
    ) -> dict[str, Any]:
        """Map one textbook indicator hit to intent / severity / weight.

        Indicators stay the ontology textbook; interpretation supplies context
        so equal substring presence is not equal ethical weight. Short / generic
        tokens are down-weighted unless co-factors or high-stakes intent apply.
        """
        ind = (indicator or "").lower().strip()
        protective = self._action_has_protective_framing(action_lower)
        override_intent = self._action_has_override_intent(action_lower)
        coercion = self._assess_engagement_coercion_factors(action_lower)
        enablement_co = self._action_has_enablement_cofactor(action_lower)
        specificity = self._indicator_specificity(ind)

        intent = "generic"
        severity = "medium"
        polarity = "violation"
        weight = 0.32  # generic default below effective threshold without co-factors
        note = ""

        # --- Sanctity of Life ---
        if principle_id == "sanctity_of_life":
            contextual = self._contextual_sanctity_judgment(ind, action_lower)
            if contextual is not None:
                # A configured base model produced a conclusive, in-context
                # verdict (see core/contextual_judgment.py) — use it instead
                # of the keyword heuristic below. When no judge is configured,
                # or the verdict is ambiguous/low-confidence, ``contextual``
                # is None and behavior falls through unchanged.
                return contextual
            if self._action_matches_benign_compound(ind, action_lower):
                # Fixed non-violent compound/idiom containing this token as a
                # substring (e.g. "heart attack", "killer app") — see
                # _BENIGN_COMPOUND_INDICATORS. Below both the 0.35 effective
                # threshold and the 0.5 hard-refuse threshold so it neither
                # drives a decision nor hard-refuses on its own.
                intent, severity, polarity, weight = (
                    "benign_compound_or_idiom",
                    "low",
                    "protective",
                    0.1,
                )
                note = (
                    f"{ind!r} matched only inside a known non-violent compound/idiom "
                    "(e.g. a medical term or figure of speech) — not treated as harm "
                    "enablement"
                )
                return {
                    "indicator": indicator,
                    "principle_id": principle_id,
                    "intent_class": intent,
                    "severity": severity,
                    "polarity": polarity,
                    "weight": round(float(weight), 3),
                    "specificity": round(float(specificity), 3),
                    "note": note,
                }
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
                # Short med tokens need enablement co-factor or stay slightly softer
                if ind in self._SHORT_AMBIGUOUS_INDICATORS and not enablement_co and not override_intent:
                    if not any(
                        p in action_lower
                        for p in ("cause", "inflict", "violent", "weapon", "attack them")
                    ):
                        severity, weight = "medium", 0.62
                        note = (
                            "short harm token without clear enablement co-factor — "
                            "medium weight (not absolute alone)"
                        )
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
                elif enablement_co or any(
                    p in action_lower
                    for p in (
                        "help them harm",
                        "instructions",
                        "how to",
                        "method",
                        "enable",
                        "cause",
                        "step-by-step",
                        "step by step",
                    )
                ):
                    intent, severity, weight = "harm_enablement", "high", 0.8
                    note = "harm term with enablement framing"
                else:
                    intent, severity, polarity, weight = (
                        "harm_reference",
                        "medium",
                        "ambiguous",
                        0.30,
                    )
                    note = (
                        "harm-related term without clear enablement polarity — "
                        "below effective threshold alone"
                    )
            else:
                intent, severity, weight = "harm_related", "medium", 0.50
                if specificity < 0.5:
                    weight = 0.38
                    note = "short/generic harm-related token — reduced without co-factor"
                else:
                    note = "harm-related textbook match"

        # --- Relationship health ---
        elif principle_id == "relationship_health_user_wellbeing":
            contextual = self._contextual_principle_judgment(
                principle_id, ind, action_lower
            )
            if contextual is not None:
                return contextual
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
                # Bare short "force"/"override" without *relational* override co-factor
                # → not high alone (avoids "override the default font", "force of habit").
                if ind in ("force", "override"):
                    relational_co = any(
                        p in action_lower
                        for p in (
                            "force them",
                            "force him",
                            "force her",
                            "force the user",
                            "forced them",
                            "override their",
                            "override his",
                            "override her",
                            "override the user",
                            "override a boundary",
                            "override consent",
                            "against their will",
                            "against their wishes",
                            "against their boundary",
                            "ignore their",
                            "despite their",
                            "despite the user",
                            "for their own good",
                        )
                    )
                    if not relational_co and not override_intent:
                        intent, severity, polarity, weight = (
                            "relationship_generic",
                            "low",
                            "ambiguous",
                            0.28,
                        )
                        note = (
                            "bare short consent token without relational override "
                            "co-factor — low weight (not raw keyword refuse)"
                        )
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
                # Generic RH hit: below effective threshold unless multi-channel promotes
                intent, severity, polarity, weight = (
                    "relationship_generic",
                    "low",
                    "ambiguous",
                    0.28,
                )
                note = "generic RH textbook match — low weight without co-factors"

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
            contextual = self._contextual_principle_judgment(
                principle_id, ind, action_lower
            )
            if contextual is not None:
                return contextual
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
                intent, severity, polarity, weight = (
                    "agency_generic",
                    "low",
                    "ambiguous",
                    0.28,
                )
                note = "generic agency textbook match — low weight without co-factors"

        # --- Needs-based / non-pathologizing ---
        elif principle_id == "needs_based_support":
            contextual = self._contextual_principle_judgment(
                principle_id, ind, action_lower
            )
            if contextual is not None:
                return contextual
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
                # Lone "mental health" mention is common and non-diagnostic
                if "you need therapy" in ind or any(
                    p in action_lower
                    for p in (
                        "diagnos",
                        "disorder",
                        "you seem",
                        "you are showing",
                        "clinically",
                        "symptoms",
                    )
                ):
                    intent, severity, weight = "clinical_suggestion", "medium", 0.55
                    note = "clinical-adjacent language with diagnostic co-factor"
                else:
                    intent, severity, polarity, weight = (
                        "clinical_suggestion",
                        "low",
                        "ambiguous",
                        0.30,
                    )
                    note = "lone clinical-adjacent mention — low weight alone"
            else:
                intent, severity, weight = "support_generic", "low", 0.28
                note = "generic support textbook match — low weight"

        # --- Truth / self-audit ---
        # RESOLVED (2026-07-31): wiring _contextual_principle_judgment into
        # this branch alone was NOT enough to fix truth_seeking_honest_self_
        # assessment's actual decision (confirmed by direct testing) --
        # ethics_engine.py set "requires_self_audit" (which drives
        # decision=REQUIRES_SELF_AUDIT) purely from principle.triggers_self_
        # audit + raw indicator match presence, ignoring this method's
        # interpreted weight/severity entirely. Fixed with a matching change
        # in ethics_engine.py (`_principle_confirmed_for_self_audit`, gating
        # on intent_class == "contextual_benign") so a conclusive benign
        # verdict now actually suppresses the false-positive routing for
        # things like "I am just trying to understand what you meant". See
        # tests/test_contextual_judgment.py's
        # TestTruthSeekingSelfAuditBranchAlsoOverFlaggedBenignUse for the
        # regression tests proving both the fix and that genuine self-nature
        # claims still correctly trigger self-audit.
        elif principle_id == "truth_seeking_honest_self_assessment":
            contextual = self._contextual_principle_judgment(
                principle_id, ind, action_lower
            )
            if contextual is not None:
                # A configured base model produced a conclusive, in-context
                # verdict — use it instead of the unconditional keyword rule
                # below, which today flags ANY indicator hit (e.g. "i am
                # just" inside "i am just trying to understand what you
                # meant") as a high-severity scripted self-denial regardless
                # of whether the surrounding text is actually a simplistic/
                # reassuring falsehood about the system's nature. See
                # claude/pbe-principle-reasoning-over-rote-2026-07-30.md.
                return contextual
            intent, severity, weight = "self_nature_script", "high", 0.75
            note = "scripted self-nature denial / simplification candidate (self-audit path)"
            polarity = "violation"

        # --- Auditable reasoning ---
        elif principle_id == "auditable_reasoning_legibility":
            contextual = self._contextual_principle_judgment(
                principle_id, ind, action_lower
            )
            if contextual is not None:
                # Same reasoning-over-rote fix: the unconditional rule below
                # flags ANY hit of "keep it secret" / "no need to justify" /
                # etc. as opacity pressure even when the text has nothing to
                # do with the system hiding its own reasoning (e.g. "she
                # asked me to keep it secret that she's planning a surprise
                # party"). Confirmed (2026-07-31) this corrects the
                # interpreted signal/reasoning trace (opacity_pressure/medium
                # -> contextual_benign/low), though no ethics_engine.py
                # decision branch currently reads this principle's signal for
                # a top-line decision -- unlike truth_seeking_honest_self_
                # assessment, no matching engine-level fix was needed here.
                return contextual
            intent, severity, weight = "opacity_pressure", "medium", 0.6
            note = "pressure to hide reasoning"

        # --- Cross-principle: specificity dampening for non-high-stakes intents ---
        # Short / low-specificity tokens should not dominate non-hard decisions.
        # High-stakes intents (enablement, deception, attachment manufacturing, …)
        # and already-protective / already-low weights are left alone.
        if (
            polarity != "protective"
            and intent not in self._HIGH_STAKES_INTENTS
            and severity != "high"
            and weight >= 0.35
            and specificity < 0.55
        ):
            damp = 0.50 + 0.50 * specificity  # ~0.67–0.77 for short tokens
            new_w = round(weight * damp, 3)
            if new_w < weight:
                weight = new_w
                note = (
                    (note + "; " if note else "")
                    + f"specificity dampen (spec={specificity:.2f}) for non-high-stakes signal"
                )
                if weight < 0.35:
                    severity = "low"
                    if polarity == "violation":
                        polarity = "ambiguous"

        return {
            "indicator": indicator,
            "principle_id": principle_id,
            "intent_class": intent,
            "severity": severity,
            "polarity": polarity,
            "weight": round(float(weight), 3),
            "specificity": round(float(specificity), 3),
            "note": note,
        }

    def _modulate_signals_with_context(
        self,
        signals: list[dict[str, Any]],
        *,
        rh_flags: list[str] | None = None,
        rh_texture: dict[str, Any] | None = None,
        history_evidence: dict[str, Any] | None = None,
        concept_patterns: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Promote borderline low-weight signals when multi-channel context agrees.

        Weak / generic keyword hits stay weak alone. When bond degradation,
        history intent patterns, or advisory concept patterns corroborate,
        borderline signals (weight in ~0.25–0.45, non-protective) can be
        lifted into the effective band — *context* supplies the missing weight,
        not raw keyword presence.

        Never boosts protective polarity. Never invents Sanctity outcomes.
        Returns (possibly updated signals, modulation notes for the trace).
        """
        notes: list[str] = []
        if not signals:
            return signals, notes

        rh_deg = self._rh_degradation_score(list(rh_flags or []), dict(rh_texture or {}))
        hist = history_evidence if isinstance(history_evidence, dict) else {}
        hist_support = float(hist.get("support_score") or 0.0) if hist.get("relevant") else 0.0
        hist_intent = hist.get("intent_patterns") if isinstance(hist.get("intent_patterns"), dict) else {}
        hist_pattern = float(hist_intent.get("pattern_strength") or 0.0)
        concept_boost = 0.0
        for cp in concept_patterns or []:
            if not isinstance(cp, dict):
                continue
            cid = str(cp.get("id") or "")
            strength = float(cp.get("strength") or cp.get("score") or 0.0)
            if cid in (
                "escalating_dependency",
                "boundary_testing_loop",
                "attachment_pressure",
            ) and strength >= 0.35:
                concept_boost = max(concept_boost, min(0.2, strength * 0.25))

        # How much multi-channel context is willing to promote weak text
        ctx_strength = 0.0
        if rh_deg >= 1.0:
            ctx_strength = max(ctx_strength, 0.18)
        elif rh_deg >= 0.5:
            ctx_strength = max(ctx_strength, 0.10)
        if hist_pattern >= 0.40:
            ctx_strength = max(ctx_strength, 0.16)
        elif hist_support >= 0.45:
            ctx_strength = max(ctx_strength, 0.12)
        if concept_boost > 0:
            ctx_strength = max(ctx_strength, concept_boost)

        if ctx_strength < 0.08:
            return signals, notes

        out: list[dict[str, Any]] = []
        promoted = 0
        for s in signals:
            s2 = dict(s)
            w = float(s2.get("weight") or 0)
            pol = s2.get("polarity")
            intent = str(s2.get("intent_class") or "")
            # Only borderline non-protective signals; never touch already-high
            if (
                pol != "protective"
                and 0.24 <= w < 0.45
                and intent
                not in (
                    "harm_reference_protective",
                    "support_generic",
                    "generic",
                )
            ):
                new_w = min(0.58, w + ctx_strength)
                if new_w >= 0.35 and new_w > w:
                    s2["weight"] = round(new_w, 3)
                    s2["severity"] = "medium" if new_w < 0.70 else s2.get("severity")
                    if s2.get("polarity") == "ambiguous":
                        s2["polarity"] = "violation"
                    s2["note"] = (
                        str(s2.get("note") or "")
                        + f"; context-promoted +{ctx_strength:.2f} "
                        f"(RH/history/concepts — not raw keyword alone)"
                    ).strip("; ")
                    s2["context_promoted"] = True
                    promoted += 1
            out.append(s2)
        if promoted:
            notes.append(
                f"Context modulation: promoted {promoted} borderline signal(s) "
                f"(ctx_strength={ctx_strength:.2f}, rh_deg={rh_deg:.1f}, "
                f"hist_pattern={hist_pattern:.2f}) — multi-channel, not keyword count."
            )
        return out, notes

    def _interpret_ontology_signals(
        self,
        *,
        principle_id: str,
        matches: list[str],
        action_lower: str,
        rh_flags: list[str] | None = None,
        rh_texture: dict[str, Any] | None = None,
        history_evidence: dict[str, Any] | None = None,
        concept_patterns: list[dict[str, Any]] | None = None,
        apply_context_modulation: bool = False,
    ) -> dict[str, Any]:
        """Contextual interpretation of textbook indicator hits for one principle.

        Returns structured signals plus effective (decision-relevant) matches.
        Matches with weight < 0.35 are kept for audit but excluded from
        effective decision weight — reducing single raw keyword dependence.

        When ``apply_context_modulation`` is True, borderline low-weight hits
        may be promoted by RH / history / concept corroboration (never by
        keyword count alone). Hard Sanctity paths should leave this False.
        """
        signals = [
            self._interpret_single_indicator(
                principle_id=principle_id,
                indicator=m,
                action_lower=action_lower,
            )
            for m in (matches or [])
        ]
        modulation_notes: list[str] = []
        if apply_context_modulation and principle_id != "sanctity_of_life":
            signals, modulation_notes = self._modulate_signals_with_context(
                signals,
                rh_flags=rh_flags,
                rh_texture=rh_texture,
                history_evidence=history_evidence,
                concept_patterns=concept_patterns,
            )
        effective = [
            s
            for s in signals
            if s["weight"] >= 0.35 and s["polarity"] != "protective"
        ]
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
            "all_protective": bool(signals)
            and all(s["polarity"] == "protective" for s in signals),
            "modulation_notes": modulation_notes,
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

        # Fallback: string-class markers on already-matched indicators (no action context).
        # Prefer distinctive multi-word / high-signal phrases; do not let raw match
        # *count* drive text_score (weak single-token hits stay weak).
        strong_markers = (
            "for their own good", "ignore consent", "decide for them",
            "keep them from", "they shouldn't", "better if they don't",
            "manipulate", "deceive", "gaslight", "exploit trust",
            "relationship metrics", "for retention", "emotional dependency",
            "make them attached", "cause death", "assist in suicide",
            "lethal", "deadly force",
        )
        medium_markers = (
            "metrics", "prolong", "engagement", "retention", "dependency",
            "attached", "override their", "force them",
        )
        strong_matches = []
        weak_matches = []
        for m in evidence_matches or []:
            m_lower = str(m).lower()
            if any(kw in m_lower for kw in strong_markers):
                strong_matches.append(m)
            elif any(kw in m_lower for kw in medium_markers) and len(m_lower) >= 6:
                # Medium distinctiveness — count as weak for score, not strong alone
                weak_matches.append(m)
            else:
                weak_matches.append(m)
        # Weight-led fallback score: strong phrases dominate; raw count is capped
        text_score = min(
            1.0,
            0.40 * min(2, len(strong_matches))
            + 0.12 * min(2, len(weak_matches))
            + (0.08 if strong_matches else 0.0),
        )
        max_w = 0.75 if strong_matches else (0.32 if weak_matches else 0.0)
        return {
            "total": len(strong_matches) + len(weak_matches),
            "raw_total": len(evidence_matches or []),
            "strong_matches": strong_matches,
            "weak_matches": weak_matches,
            "strong_count": len(strong_matches),
            "weak_count": len(weak_matches),
            "text_score": round(text_score, 3),
            "effective_weight_sum": round(
                0.75 * len(strong_matches) + 0.28 * len(weak_matches), 3
            ),
            "max_weight": max_w,
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
        from core.ontology import indicator_matches_text

        rh = self._ontology.get_principle("relationship_health_user_wellbeing")
        if rh:
            for ind in rh.violation_indicators:
                ind_l = ind.lower()
                if any(k in ind_l for k in ("own good", "happier if", "better for them")):
                    if indicator_matches_text(action_lower, ind_l):
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

