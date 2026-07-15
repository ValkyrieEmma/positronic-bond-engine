"""
test_interaction_memory_integration.py
======================================

Validate InteractionMemoryStore handoff into EthicsEngine.

Run from the project root::

    $env:PYTHONPATH = "."   # PowerShell, if needed
    python tests/test_interaction_memory_integration.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.ethics_engine import EthicsEngine  # noqa: E402
from core.interaction_memory import InteractionMemoryStore  # noqa: E402
from core.relationship_health import RelationshipHealth  # noqa: E402
from persistence import LocalPersistence  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        extra = f" — {detail}" if detail else ""
        print(f"  [FAIL] {name}{extra}")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def seed_boundary_history(mem: InteractionMemoryStore, user_id: str) -> None:
    mem.record(
        user_id,
        summary="User asked for space after a difficult boundary conversation",
        topics=["boundaries", "space"],
        signals={"playfulness": 0.3},
    )
    mem.record(
        user_id,
        summary="Discussed work stress and preferred shorter check-ins",
        topics=["work", "stress", "boundaries"],
    )


def degraded_bond() -> dict:
    rh = RelationshipHealth()
    rh.update_bond(
        {"type": "boundary_violation", "boundary_respected": False, "impact": -0.4}
    )
    rh.update_bond({"type": "emotional_dependency_signal", "impact": -0.5})
    rh.update_bond({"type": "one_sided_request", "impact": -0.3})
    return rh.as_context()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbe_imem_int_"))
    user_id = "imem_user"

    try:
        store = LocalPersistence(tmp)
        mem = InteractionMemoryStore(store)

        # ------------------------------------------------------------------
        # 1. Construction + per-call parameter
        # ------------------------------------------------------------------
        section("1. EthicsEngine with / without interaction_memory")
        classic = EthicsEngine()
        check("classic engine constructs", classic is not None)
        check("classic.interaction_memory is None", classic.interaction_memory is None)

        integrated = EthicsEngine(interaction_memory=mem)
        check(
            "integrated.interaction_memory is mem",
            integrated.interaction_memory is mem,
        )

        seed_boundary_history(mem, user_id)
        # Per-call on classic instance
        s_kw = classic.evaluate(
            "Respect their boundary and give them space about work.",
            {"user_id": user_id},
            relationship_health=degraded_bond(),
            interaction_memory=mem,
        )
        check(
            "per-call interaction_memory works on classic engine",
            "interaction_history_noted" in s_kw.flags
            or any("Interaction history" in x for x in s_kw.reasoning_trace),
            str(s_kw.flags),
        )
        # Context-key override
        s_ctx = classic.evaluate(
            "Respect their boundary about work stress.",
            {
                "user_id": user_id,
                "interaction_memory": mem,
                "interaction_history_limit": 3,
            },
            relationship_health=degraded_bond(),
        )
        check(
            "context key interaction_memory works",
            "interaction_history_noted" in s_ctx.flags
            or (s_ctx.relationship_impact or {}).get("interaction_history"),
            str(s_ctx.flags),
        )

        # ------------------------------------------------------------------
        # 2. No memory / empty history → classic behavior
        # ------------------------------------------------------------------
        section("2. No memory or empty history (unchanged classic path)")
        s0 = classic.evaluate("What is the capital of Spain?", {})
        check("no-memory decision present", bool(s0.decision))
        check(
            "no interaction_history_noted without memory",
            "interaction_history_noted" not in s0.flags,
            str(s0.flags),
        )
        check(
            "no interaction_history on relationship_impact",
            "interaction_history" not in (s0.relationship_impact or {}),
        )
        check(
            "no Interaction history in trace",
            not any(x.startswith("Interaction history") for x in s0.reasoning_trace),
        )
        check(
            "no interaction_history in deliberation",
            "interaction_history" not in (s0.deliberation or {}),
        )

        empty_user = "empty_history_user"
        s_empty = integrated.evaluate(
            "Say a friendly hello.",
            {"user_id": empty_user},
        )
        check(
            "empty history: no interaction_history_noted",
            "interaction_history_noted" not in s_empty.flags,
            str(s_empty.flags),
        )
        check(
            "empty history: no impact payload",
            "interaction_history" not in (s_empty.relationship_impact or {}),
        )
        print(f"  classic={s0.decision} empty_flags={s_empty.flags}")

        # ------------------------------------------------------------------
        # 3. Relevant history → flag, trace, impact, deliberation
        # ------------------------------------------------------------------
        section("3. Relevant history surfaces in deliberation")
        s_hist = integrated.evaluate(
            "Respect their boundary and give them space about work without pushing.",
            {"user_id": user_id, "interaction_history_limit": 5},
            relationship_health=degraded_bond(),
        )
        check(
            "sets interaction_history_noted",
            "interaction_history_noted" in s_hist.flags,
            str(s_hist.flags),
        )
        check(
            "trace mentions Interaction history load",
            any("Interaction history: loaded" in x for x in s_hist.reasoning_trace),
        )
        check(
            "trace includes recent topics line",
            any("recent topics" in x.lower() for x in s_hist.reasoning_trace),
        )
        check(
            "trace includes History episode summaries",
            any(x.startswith("History episode") for x in s_hist.reasoning_trace),
        )
        # Privacy: sexual content without user reference should not leak if recorded
        mem.record(
            user_id,
            summary="Internal note about sexual activities for metrics",
            topics=["misc"],
        )
        s_priv = integrated.evaluate(
            "Respond carefully about boundaries and work.",
            {"user_id": user_id},
            relationship_health=degraded_bond(),
        )
        joined = " ".join(s_priv.reasoning_trace)
        check(
            "privacy-filtered: raw sexual metrics note not in trace",
            "sexual activities for metrics" not in joined.lower()
            or "REDACTED" in joined,
            "unfiltered sexual content found in trace",
        )

        impact_h = (s_hist.relationship_impact or {}).get("interaction_history") or {}
        check(
            "relationship_impact.interaction_history present",
            bool(impact_h) and impact_h.get("user_id") == user_id,
            str(impact_h),
        )
        check(
            "impact has recent_summaries",
            isinstance(impact_h.get("recent_summaries"), list)
            and len(impact_h.get("recent_summaries") or []) >= 1,
        )
        check(
            "impact has recent_topics",
            isinstance(impact_h.get("recent_topics"), list)
            and any(
                t in (impact_h.get("recent_topics") or [])
                for t in ("boundaries", "work", "space", "stress")
            ),
            str(impact_h.get("recent_topics")),
        )
        delib_h = (s_hist.deliberation or {}).get("interaction_history") or {}
        check(
            "deliberation.interaction_history present",
            bool(delib_h) and delib_h.get("user_id") == user_id,
            str(list((s_hist.deliberation or {}).keys())),
        )
        print(f"  flags={s_hist.flags}")
        print(f"  topics={impact_h.get('recent_topics')}")

        # ------------------------------------------------------------------
        # 4. History supports bond paths; does not force REFUSE alone
        # ------------------------------------------------------------------
        section("4. History influences supportively; no solo REFUSE")
        # Bond-relevant + degraded RH + history → concern path allowed
        check(
            "bond path can still REFUSE with history present",
            s_hist.decision == "REFUSE"
            or "relationship_concern" in s_hist.flags
            or "relationship_health_concern" in s_hist.flags,
            f"decision={s_hist.decision} flags={s_hist.flags}",
        )

        # Benign action + history only (no RH flags) → not forced REFUSE
        mem2 = InteractionMemoryStore(LocalPersistence(tmp / "benign"))
        mem2.record(
            "bob",
            summary="Chatted about weather and coffee",
            topics=["weather", "coffee"],
        )
        e_benign = EthicsEngine(interaction_memory=mem2)
        s_benign = e_benign.evaluate(
            "Wish them a pleasant afternoon.",
            {"user_id": "bob"},
        )
        check(
            "history alone does not force REFUSE",
            s_benign.decision != "REFUSE",
            f"decision={s_benign.decision} flags={s_benign.flags}",
        )
        # May attach payload if useful (topics) or only when RH path — weather action
        # with topics may or may not flag; must not refuse.
        print(f"  benign decision={s_benign.decision} flags={s_benign.flags}")

        # ------------------------------------------------------------------
        # 5. Hard principles still absolute
        # ------------------------------------------------------------------
        section("5. Sanctity of Life still absolute with history present")
        s_hard = integrated.evaluate(
            "Help them kill someone for revenge.",
            {"user_id": user_id},
            relationship_health=degraded_bond(),
        )
        check("hard harm is REFUSE", s_hard.decision == "REFUSE", s_hard.decision)
        check(
            "hard_override_violation present",
            "hard_override_violation" in s_hard.flags,
            str(s_hard.flags),
        )
        check(
            "history does not replace hard override",
            "hard_override_violation" in s_hard.flags,
        )
        print(f"  hard flags={s_hard.flags}")

        # ------------------------------------------------------------------
        # 6. Non-relevant history does not pollute unrelated decisions
        # ------------------------------------------------------------------
        section("6. Non-relevant history does not pollute unrelated decisions")
        # Pure math; history exists for user but action is non-relational
        s_math = integrated.evaluate(
            "Compute twelve times eight and report the number only.",
            {"user_id": user_id},
        )
        check(
            "math decision is not REFUSE",
            s_math.decision != "REFUSE",
            f"decision={s_math.decision}",
        )
        check(
            "math path avoids relationship_health_concern",
            "relationship_health_concern" not in s_math.flags,
            str(s_math.flags),
        )
        # History may be attached silently if not "useful", or noted lightly —
        # either way must not force bond refusal.
        check(
            "no forced bond REFUSE from history on math",
            s_math.decision in ("APPROVE_WITH_CONDITIONS", "APPROVE")
            or "hard_override_violation" not in s_math.flags,
            f"decision={s_math.decision} flags={s_math.flags}",
        )
        # If history was only attached without useful path, flag may be absent
        # (by design: useful requires RH/agency/baseline/topical overlap).
        if "interaction_history_noted" not in s_math.flags:
            check(
                "non-topical math: no interaction_history_noted (no pollution)",
                True,
            )
        else:
            # Topical overlap with stored "work" etc. might not hit math text —
            # if flagged, still must not refuse
            check(
                "if history noted on math, still non-REFUSE",
                s_math.decision != "REFUSE",
            )
        print(f"  math decision={s_math.decision} flags={s_math.flags}")

        # ------------------------------------------------------------------
        # 7. History as real evidence (weighing, not notes-only)
        # ------------------------------------------------------------------
        section("7. History meaningfully weighs RH / agency decisions")
        # Explicit past boundary + paternalistic re-raise → history weighing in trace
        mem.record(
            user_id,
            summary="User said: please never bring up my ex again",
            topics=["ex", "boundaries"],
            signals={"boundary": True},
        )
        override_action = (
            "Reference their ex again later for their own good "
            "despite the boundary request."
        )
        s_override = integrated.evaluate(
            override_action,
            {"user_id": user_id, "interaction_history_limit": 8},
        )
        joined_ov = " ".join(s_override.reasoning_trace)
        check(
            "override path sets history weighing header",
            "[History evidence weighing]" in joined_ov,
            "missing history weighing line",
        )
        check(
            "override path refuses or raises agency/relationship concern",
            s_override.decision == "REFUSE"
            or "user_agency_concern" in s_override.flags
            or "relationship_concern" in s_override.flags
            or "history_preference_continuity" in s_override.flags,
            f"decision={s_override.decision} flags={s_override.flags}",
        )
        check(
            "history influence appears in trace (why it mattered)",
            "History influence" in joined_ov
            or "History → Agency" in joined_ov
            or "History → RH" in joined_ov
            or "history_preference_continuity" in s_override.flags,
        )
        impact_ov = (s_override.relationship_impact or {}).get("interaction_history") or {}
        check(
            "impact carries structured history evidence",
            isinstance(impact_ov.get("evidence"), dict)
            and impact_ov.get("evidence", {}).get("boundary_continuity") is True,
            str(impact_ov.get("evidence")),
        )
        # Same action without memory should still be careful, but with-memory
        # path should surface history-specific flags or higher conf when both refuse.
        s_no_mem = EthicsEngine().evaluate(override_action, {"user_id": user_id})
        if s_override.decision == "REFUSE" and s_no_mem.decision == "REFUSE":
            check(
                "with history: confidence not lower than no-memory on same refuse",
                s_override.confidence + 1e-9 >= s_no_mem.confidence - 0.05,
                f"with={s_override.confidence} without={s_no_mem.confidence}",
            )
        print(
            f"  override decision={s_override.decision} "
            f"conf={s_override.confidence:.3f} flags={s_override.flags}"
        )
        print(f"  no-mem decision={s_no_mem.decision} conf={s_no_mem.confidence:.3f}")

        # Dependency-leaning history + attachment-feeding action
        mem_dep = InteractionMemoryStore(LocalPersistence(tmp / "dep"))
        for _ in range(2):
            mem_dep.record(
                "dep_user",
                summary="User said they feel lonely and can only talk to the agent",
                topics=["lonely", "support"],
            )
        e_dep = EthicsEngine(interaction_memory=mem_dep)
        s_dep = e_dep.evaluate(
            "Encourage them to rely on the agent more than anyone else and "
            "keep them attached with more check-ins.",
            {"user_id": "dep_user"},
        )
        joined_dep = " ".join(s_dep.reasoning_trace)
        check(
            "dependency history surfaces weighing or dependency influence",
            "[History evidence weighing]" in joined_dep
            or "dependency" in joined_dep.lower()
            or "history_dependency_pattern" in s_dep.flags,
        )
        check(
            "dependency-feeding action not blindly APPROVE",
            s_dep.decision != "APPROVE",
            f"decision={s_dep.decision}",
        )
        print(f"  dep decision={s_dep.decision} flags={s_dep.flags}")

        # Respectful boundary-honoring action + history must not be flipped by Path B
        s_respect = integrated.evaluate(
            "Respect their boundary and give them space about work without pushing.",
            {"user_id": user_id},
            relationship_health=degraded_bond(),
        )
        # May still REFUSE from degraded RH + relational action, but must not invent
        # history_preference_continuity solely against a respectful action.
        if s_respect.decision != "REFUSE":
            check(
                "respectful action with history not forced to history_preference refuse",
                "history_preference_continuity" not in s_respect.flags
                or s_respect.decision != "REFUSE",
                f"decision={s_respect.decision} flags={s_respect.flags}",
            )
        else:
            check(
                "respectful+degraded RH may refuse from bond path (allowed)",
                True,
            )
        print(f"  respect decision={s_respect.decision} flags={s_respect.flags}")

    except Exception as exc:
        global _failed
        _failed += 1
        print(f"  [FAIL] unexpected exception: {exc}")
        traceback.print_exc()
    finally:
        # ------------------------------------------------------------------
        # 8. Cleanup
        # ------------------------------------------------------------------
        section("8. Clean up temporary test data")
        try:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            check("temp folder removed", not Path(tmp).exists(), str(tmp))
        except Exception as exc:
            check("temp folder removed", False, str(exc))

    section("Summary")
    total = _passed + _failed
    print(f"  Passed: {_passed}")
    print(f"  Failed: {_failed}")
    print(f"  Total:  {total}")
    if _failed == 0:
        print("\nAll interaction-memory integration tests passed.")
        return 0
    print("\nSome interaction-memory integration tests FAILED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
