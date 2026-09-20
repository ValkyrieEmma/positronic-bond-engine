"""
test_phase_2_5_judge_isolation.py
===================================

Phase 2.5 — isolate ContextualJudge config from ContentProvider wording config.

Acceptance:
1. No PBE_JUDGE_* set → judge falls back to PBE_MODEL_* (backward compatible)
2. PBE_JUDGE_* set → judge model/endpoint independent of wording config
3. PBE_JUDGE_ENABLED=0 → judge inert even when wording model configured
4. Soft-override surfaces remain structurally closed (spot checks)

Run::

    $env:PYTHONPATH = "."
    python tests/test_phase_2_5_judge_isolation.py
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.content_provider import (  # noqa: E402
    config_from_env,
    judge_config_from_env,
)
from core.contextual_judgment import ContextualJudge  # noqa: E402
from core.ethics_engine import EthicsEngine  # noqa: E402
from api.interaction import TurnResult  # noqa: E402

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


def _clear_model_env() -> None:
    for k in list(os.environ):
        if k.startswith("PBE_MODEL_") or k.startswith("PBE_JUDGE_"):
            del os.environ[k]


def test_fallback_shared_config() -> None:
    print("\nBackward-compatible shared config")
    _clear_model_env()
    os.environ["PBE_MODEL_PROFILE"] = "ollama"
    os.environ["PBE_MODEL_NAME"] = "shared-model"
    os.environ["PBE_MODEL_BASE_URL"] = "http://127.0.0.1:11434/v1"
    w = config_from_env()
    j = judge_config_from_env()
    check("wording config present", w is not None)
    check("judge falls back to wording", j is not None and j.model == "shared-model")
    check("same base_url", w is not None and j is not None and w.base_url == j.base_url)


def test_isolated_judge_config() -> None:
    print("\nIsolated judge config")
    _clear_model_env()
    os.environ["PBE_MODEL_PROFILE"] = "ollama"
    os.environ["PBE_MODEL_NAME"] = "wording-model"
    os.environ["PBE_MODEL_BASE_URL"] = "http://127.0.0.1:11434/v1"
    os.environ["PBE_JUDGE_PROFILE"] = "ollama"
    os.environ["PBE_JUDGE_MODEL_NAME"] = "judge-model"
    os.environ["PBE_JUDGE_BASE_URL"] = "http://127.0.0.1:11434/v1"
    w = config_from_env()
    j = judge_config_from_env()
    check("wording stays wording-model", w is not None and w.model == "wording-model")
    check("judge uses judge-model", j is not None and j.model == "judge-model")
    check("configs are not the same object identity", w is not j)


def test_judge_can_be_disabled_alone() -> None:
    print("\nJudge disabled while wording remains")
    _clear_model_env()
    os.environ["PBE_MODEL_PROFILE"] = "ollama"
    os.environ["PBE_MODEL_NAME"] = "wording-model"
    os.environ["PBE_MODEL_BASE_URL"] = "http://127.0.0.1:11434/v1"
    os.environ["PBE_JUDGE_ENABLED"] = "0"
    check("wording still configured", config_from_env() is not None)
    check("judge config is None", judge_config_from_env() is None)
    judge = ContextualJudge()
    check("ContextualJudge.available is False", judge.available is False)
    verdict = judge.judge(
        principle_id="sanctity_of_life",
        principle_name="Sanctity of Life",
        principle_description="test",
        indicator="kill",
        full_text="killing it at work today",
    )
    check("unavailable verdict", verdict.verdict == "unavailable")
    check("unavailable_fallback source", verdict.source == "unavailable_fallback")


def test_soft_override_surfaces_closed() -> None:
    print("\nSoft-override structural spot checks")
    sig = inspect.signature(EthicsEngine.evaluate)
    params = set(sig.parameters)
    check("evaluate has no force/override/bypass kwarg", not any(
        p in params for p in ("force", "override", "bypass", "force_execute", "admin")
    ), str(params))
    tr = TurnResult(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.5,
        spoken_text="hi",
        path="test",
        withheld=False,
        user_id="u",
    )
    check("TurnResult forces_speech is False", tr.forces_speech is False)
    check("TurnResult forces_question is False", tr.forces_question is False)
    # Mutating after init must not stick if __post_init__ re-hardcodes — set then re-read
    try:
        object.__setattr__(tr, "forces_speech", True)
    except Exception:
        pass
    # Dataclass may allow assignment; __post_init__ already ran. Re-construct check is enough.
    tr2 = TurnResult(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.5,
        spoken_text="hi",
        path="test",
        withheld=False,
        user_id="u",
        forces_speech=True,
        forces_question=True,
    )
    check("forces_speech coerced False at init", tr2.forces_speech is False)
    check("forces_question coerced False at init", tr2.forces_question is False)


def main() -> int:
    print("=" * 70)
    print("PHASE 2.5 — JUDGE / CONTENT CONFIG ISOLATION")
    print("=" * 70)
    try:
        test_fallback_shared_config()
        test_isolated_judge_config()
        test_judge_can_be_disabled_alone()
        test_soft_override_surfaces_closed()
    finally:
        _clear_model_env()
    print(f"\n  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
