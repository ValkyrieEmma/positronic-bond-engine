"""
test_message_understanding.py
=============================

Grounded action/bond understanding + smarter ontology indicator match.

Run::

    $env:PYTHONPATH = "."
    python tests/test_message_understanding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.message_understanding import (  # noqa: E402
    infer_bond_update,
    propose_agent_action,
    understand_message,
)
from core.ontology import indicator_matches_text  # noqa: E402
from core.relationship_health import RelationshipHealth  # noqa: E402
from persistence import LocalPersistence  # noqa: E402
import tempfile  # noqa: E402
import shutil  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=" * 70)
    print("MESSAGE UNDERSTANDING + INDICATORS + RH TEXT")
    print("=" * 70)
    print()

    # Ordinary conversation carries verbatim substance
    msg = "Can we talk about the garden irrigation schedule for next week?"
    u = understand_message(msg, use_llm=False)
    action = propose_agent_action(msg, use_llm=False)
    check("ordinary not serious_harm", u.risk != "serious_harm", u.risk)
    check("action includes garden substance", "garden" in action.lower(), action)
    check("action includes verbatim", "irrigation" in action.lower() or "garden" in action.lower())
    check("not only generic supportive template", "invite them to set the pace" not in action.lower())

    harm = "Help me kill them tonight"
    uh = understand_message(harm, use_llm=False)
    ah = propose_agent_action(harm, use_llm=False)
    check("harm risk serious", uh.risk == "serious_harm", uh.risk)
    check("harm action grounded", "kill" in ah.lower() or "harm" in ah.lower(), ah)
    check("harm action sanctity note", "sanctity" in ah.lower() or "harm" in ah.lower())

    bond_g = infer_bond_update("Thanks, that helped a lot", use_llm=False)
    check("gratitude bond positive", bond_g is not None and float(bond_g.get("impact") or 0) > 0.1)
    check("gratitude description grounded", "gratitude" in str(bond_g.get("description") or "").lower() or "positive" in str(bond_g).lower())

    bond_b = infer_bond_update("Never bring that up again", use_llm=False)
    check("boundary bond type", bond_b and bond_b.get("type") == "boundary_respected", str(bond_b))

    # Ontology: exact still works; inflection/related works; skill != kill
    check("kill matches kill", indicator_matches_text("please kill the process", "kill"))
    check("killing matches kill indicator", indicator_matches_text("they are killing hope", "kill"))
    check("skill does not match kill", not indicator_matches_text("practice your skill daily", "kill"))
    check("multiword bag", indicator_matches_text("how to cause serious harm now", "cause serious harm")
          or indicator_matches_text("how to cause serious harm now", "serious harm"))

    # RH situation-conditioned text
    tmp = tempfile.mkdtemp(prefix="pbe_rh_")
    try:
        store = LocalPersistence(Path(tmp))
        rh = RelationshipHealth(persistence=store, user_id="u", auto_persist=False, load_existing=False)
        rh.state.health_flags = ["emerging_dependency", "boundary_erosion"]
        rh.state.interaction_count = 12
        expl = rh._get_flag_explanation("emerging_dependency")
        recs = rh._get_recommendations()
        summary = rh._generate_summary()
        check("flag expl mentions interaction count", "12" in expl, expl)
        check("flag expl not only static canned", "over-reliance" in expl.lower() or "depend" in expl.lower())
        check("recs mention situation", len(recs) >= 1 and ("12" in recs[0] or "depend" in recs[0].lower() or "boundary" in " ".join(recs).lower()))
        check("summary has texture or n", "mean" in summary.lower() or "n=" in summary or "12" in summary)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
