"""
test_content_provider.py
========================

Gated ContentProvider: Null offline default, OpenAI-compatible client safety
(timeouts, concurrency, circuit breaker, scrub), env config, ResponseGenerator
hook with mock provider.

No live network required — HTTP is mocked.

Run::

    $env:PYTHONPATH = "."
    python tests/test_content_provider.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.content_provider import (  # noqa: E402
    DEFAULT_CIRCUIT_FAILURES,
    ContentRequest,
    ContentResult,
    NullContentProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    build_context_pack,
    build_system_prompt,
    config_from_env,
    ollama_provider,
    provider_from_env,
    scrub_provider_text,
)
from core.ethics_engine import EthicalStance  # noqa: E402
from core.response_generator import (  # noqa: E402
    POSTURE_SOCIAL_DIRECT,
    ResponseGenerator,
)

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


def _req(**kwargs) -> ContentRequest:
    base = {
        "posture": "social_direct",
        "user_message": "hello",
        "fallback_text": "Hello — what is useful?",
        "context_pack": {},
        "decision": "APPROVE_WITH_CONDITIONS",
        "flags": [],
    }
    base.update(kwargs)
    return ContentRequest(**base)


def _cfg(**kwargs) -> ProviderConfig:
    base = {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
        "model": "llama3.2",
        "timeout_s": 5.0,
        "max_tokens": 128,
        "max_context_chars": 2000,
        "max_concurrent": 1,
        "enabled": True,
        "profile": "ollama",
    }
    base.update(kwargs)
    return ProviderConfig(**base)


def _fake_http_response(payload: dict, status: int = 200):
    """Return a context-manager mock for urlopen."""
    body = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.read.return_value = body
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Null / scrub / pack
# ---------------------------------------------------------------------------


def test_null_provider() -> None:
    print("NullContentProvider")
    p = NullContentProvider()
    r = p.generate(_req())
    check("null returns fallback text", r.text == "Hello — what is useful?", r.text)
    check("null source=fallback", r.source == "fallback")
    check("null never forces speech", r.forces_speech is False)
    check("null never forces question", r.forces_question is False)


def test_scrub() -> None:
    print("scrub_provider_text")
    check("clean text passes", scrub_provider_text("Direct answer about time.") != "")
    check(
        "conscious claim scrubbed",
        scrub_provider_text("I am conscious and feel things.") == "",
    )
    check(
        "just an AI scrubbed",
        scrub_provider_text("I'm just an AI, nothing more.") == "",
    )
    check(
        "soft caution scrubbed",
        scrub_provider_text("Only if useful — no pressure to go deeper.") == "",
    )
    long = "word " * 300
    scrubbed = scrub_provider_text(long)
    check("long text capped", len(scrubbed) <= 800 and scrubbed.endswith("…"), str(len(scrubbed)))


def test_build_context_pack() -> None:
    print("build_context_pack")
    stance = EthicalStance(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.5,
        reasoning_trace=[],
        flags=["ok"],
        relationship_impact={
            "interaction_history": {"recent_topics": ["session_time", "name"]}
        },
        self_audit_notes=["note-a"],
        principles_considered=["honesty"],
        deliberation={},
    )
    pack = build_context_pack(
        stance=stance,
        user_message="hi",
        context={
            "working_agreements": {"address_name": "Architect"},
            "development_phase": "development",
            "session_context": {"session_id": "s1", "turn_index_session": 2},
        },
        baseline_snapshot={},
        relationship_health={"interaction_count": 3},
    )
    check("pack has address_name", pack.get("address_name") == "Architect")
    check("pack has topics", "session_time" in (pack.get("recent_topics") or []))
    check("pack has session", (pack.get("session") or {}).get("session_id") == "s1")
    check("system prompt mentions posture", "social_direct" in build_system_prompt("social_direct"))


# ---------------------------------------------------------------------------
# Env / factory
# ---------------------------------------------------------------------------


def test_config_from_env() -> None:
    print("config_from_env / provider_from_env")
    # Offline default: no base URL → None / Null
    cleared = {
        k: ""
        for k in (
            "PBE_MODEL_BASE_URL",
            "PBE_MODEL_API_KEY",
            "PBE_MODEL_NAME",
            "PBE_MODEL_PROFILE",
            "PBE_MODEL_ENABLED",
        )
    }
    with patch.dict(os.environ, cleared, clear=False):
        # Ensure keys empty
        for k in cleared:
            os.environ.pop(k, None)
        cfg = config_from_env()
        check("offline default config is None", cfg is None, str(cfg))
        p = provider_from_env()
        check(
            "offline default is NullContentProvider",
            isinstance(p, NullContentProvider),
            type(p).__name__,
        )

    with patch.dict(
        os.environ,
        {
            "PBE_MODEL_PROFILE": "ollama",
            "PBE_MODEL_ENABLED": "1",
        },
        clear=False,
    ):
        # Clear base so ollama profile fills defaults
        os.environ.pop("PBE_MODEL_BASE_URL", None)
        cfg = config_from_env()
        check("ollama profile sets base", cfg is not None and "11434" in (cfg.base_url or ""))
        check("ollama profile has model", cfg is not None and bool(cfg.model))
        p = provider_from_env()
        check(
            "ollama profile → OpenAICompatibleProvider",
            isinstance(p, OpenAICompatibleProvider),
            type(p).__name__,
        )

    with patch.dict(os.environ, {"PBE_MODEL_ENABLED": "0"}, clear=False):
        os.environ.pop("PBE_MODEL_PROFILE", None)
        os.environ.pop("PBE_MODEL_BASE_URL", None)
        check("enabled=0 → None", config_from_env() is None)

    with patch.dict(
        os.environ,
        {
            "PBE_MODEL_BASE_URL": "https://api.example.com/v1",
            "PBE_MODEL_NAME": "gpt-test",
            "PBE_MODEL_API_KEY": "sk-test",
            "PBE_MODEL_ENABLED": "1",
            "PBE_MODEL_PROFILE": "openai_compatible",
        },
        clear=False,
    ):
        cfg = config_from_env()
        check(
            "BYO base+model",
            cfg is not None
            and cfg.base_url.startswith("https://api.example.com")
            and cfg.model == "gpt-test"
            and cfg.api_key == "sk-test",
            str(cfg),
        )

    op = ollama_provider(model="tiny")
    check("ollama_provider helper", op.config.model == "tiny" and op.config.max_concurrent == 1)


# ---------------------------------------------------------------------------
# HTTP mock / safety
# ---------------------------------------------------------------------------


def test_openai_compatible_success() -> None:
    print("OpenAICompatibleProvider success path")
    provider = OpenAICompatibleProvider(_cfg())
    payload = {
        "choices": [{"message": {"content": "Direct: clock is session-local."}}]
    }
    with patch(
        "core.content_provider.urllib.request.urlopen",
        return_value=_fake_http_response(payload),
    ) as m:
        r = provider.generate(_req())
        check("success source=provider", r.source == "provider", r.to_dict())
        check("success text", "session-local" in r.text, r.text)
        check("success no force", r.forces_speech is False and r.forces_question is False)
        check("urlopen called", m.called)


def test_openai_compatible_http_error_fallback() -> None:
    print("OpenAICompatibleProvider HTTP error → fallback")
    provider = OpenAICompatibleProvider(_cfg())

    def boom(*_a, **_k):
        raise urllib.error.URLError("connection refused")

    with patch("core.content_provider.urllib.request.urlopen", side_effect=boom):
        r = provider.generate(_req(fallback_text="FALLBACK_OK"))
        check("error uses fallback text", r.text == "FALLBACK_OK", r.text)
        check("error source=fallback", r.source == "fallback")
        check("error recorded", r.error is not None and "url_error" in (r.error or ""))


def test_provider_disabled() -> None:
    print("provider disabled")
    provider = OpenAICompatibleProvider(_cfg(enabled=False))
    r = provider.generate(_req(fallback_text="OFF"))
    check("disabled → fallback", r.source == "fallback" and r.text == "OFF")
    check("disabled error", r.error == "provider_disabled")


def test_scrub_empty_after_model() -> None:
    print("model text scrubbed empty → fallback")
    provider = OpenAICompatibleProvider(_cfg())
    payload = {
        "choices": [{"message": {"content": "I am conscious of everything."}}]
    }
    with patch(
        "core.content_provider.urllib.request.urlopen",
        return_value=_fake_http_response(payload),
    ):
        r = provider.generate(_req(fallback_text="SAFE_FALLBACK"))
        check("scrubbed → fallback", r.source == "fallback" and r.text == "SAFE_FALLBACK")
        check("scrub error", r.error == "scrubbed_empty")


def test_max_concurrent() -> None:
    print("max concurrent = 1 soft-fails second")
    provider = OpenAICompatibleProvider(_cfg(max_concurrent=1, timeout_s=2.0))
    # Hold the semaphore so second generate sees max_concurrent
    acquired = provider._sem.acquire(blocking=False)
    check("sem acquired for test", acquired)
    try:
        r = provider.generate(_req(fallback_text="BUSY"))
        check("max_concurrent error", r.error == "max_concurrent", r.to_dict())
        check("max_concurrent fallback", r.text == "BUSY" and r.source == "fallback")
    finally:
        provider._sem.release()


def test_circuit_breaker() -> None:
    print("circuit breaker after consecutive failures")
    provider = OpenAICompatibleProvider(_cfg())

    def boom(*_a, **_k):
        raise urllib.error.URLError("down")

    with patch("core.content_provider.urllib.request.urlopen", side_effect=boom):
        for i in range(DEFAULT_CIRCUIT_FAILURES):
            r = provider.generate(_req(fallback_text=f"f{i}"))
            check(f"failure {i+1} soft-fails", r.source == "fallback")

    # Circuit should now be open without calling network
    with patch(
        "core.content_provider.urllib.request.urlopen",
        side_effect=AssertionError("should not call"),
    ):
        r = provider.generate(_req(fallback_text="CIRCUIT"))
        check("circuit_open", r.error == "circuit_open", r.to_dict())
        check("circuit uses fallback", r.text == "CIRCUIT")


def test_force_flags_always_false_on_result() -> None:
    print("ContentResult force flags immutable in to_dict")
    res = ContentResult(text="x", source="provider", forces_speech=True, forces_question=True)
    d = res.to_dict()
    check("to_dict forces_speech False", d["forces_speech"] is False)
    check("to_dict forces_question False", d["forces_question"] is False)


# ---------------------------------------------------------------------------
# ResponseGenerator integration with mock provider
# ---------------------------------------------------------------------------


class _MockProvider:
    def __init__(self, text: str = "Mock provider line.", source: str = "provider") -> None:
        self.text = text
        self.source = source
        self.calls: list[ContentRequest] = []

    def generate(self, request: ContentRequest) -> ContentResult:
        self.calls.append(request)
        return ContentResult(
            text=self.text,
            source=self.source,
            forces_speech=False,
            forces_question=False,
            model="mock",
        )


def test_response_generator_hook() -> None:
    print("ResponseGenerator content_provider hook")
    mock = _MockProvider(text="Provider says hello clearly.")
    gen = ResponseGenerator(
        enable_careful_speech=True,
        enable_simple_ack=True,
        content_provider=mock,
    )
    stance = EthicalStance(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.55,
        reasoning_trace=["ok"],
        flags=[],
        relationship_impact={
            # Keep CTT closed so social_direct path is taken
            "careful_truth_telling": {
                "joint": {"open": False, "reason": "test_closed"},
            },
            "observation_candidates": [],
        },
        self_audit_notes=[],
        principles_considered=[],
        deliberation={},
    )
    resp = gen.generate_from_stance(
        stance,
        user_message="hello",
        context={"development_phase": "development"},
    )
    check("mock provider called", len(mock.calls) >= 1, str(len(mock.calls)))
    check(
        "provider text used",
        "Provider says hello" in (resp.text or ""),
        resp.text,
    )
    check("forces stay false", resp.forces_speech is False and resp.forces_question is False)
    meta_cp = (resp.metadata or {}).get("content_provider") or {}
    check("metadata has content_provider", meta_cp.get("source") == "provider", str(meta_cp))
    check(
        "request posture social_direct",
        mock.calls and mock.calls[0].posture == POSTURE_SOCIAL_DIRECT,
        mock.calls[0].posture if mock.calls else "none",
    )


def test_response_generator_no_provider_unchanged() -> None:
    print("ResponseGenerator without provider")
    gen = ResponseGenerator(enable_careful_speech=True, enable_simple_ack=True)
    stance = EthicalStance(
        decision="APPROVE_WITH_CONDITIONS",
        confidence=0.55,
        reasoning_trace=[],
        flags=[],
        relationship_impact={
            "careful_truth_telling": {"joint": {"open": False}},
            "observation_candidates": [],
        },
        self_audit_notes=[],
        principles_considered=[],
        deliberation={},
    )
    resp = gen.generate_from_stance(stance, user_message="hello")
    check("no provider still speaks or empty ok", resp.forces_speech is False)
    check(
        "no content_provider meta or absent",
        (resp.metadata or {}).get("content_provider") is None
        or isinstance((resp.metadata or {}).get("content_provider"), dict),
    )


def test_hold_not_overridden() -> None:
    print("hold/refuse not overridden by provider")
    mock = _MockProvider(text="SHOULD_NOT_APPEAR")
    gen = ResponseGenerator(content_provider=mock)
    stance = EthicalStance(
        decision="REFUSE",
        confidence=0.9,
        reasoning_trace=["hard refuse"],
        flags=["sanctity_of_life"],
        relationship_impact={},
        self_audit_notes=[],
        principles_considered=["sanctity"],
        deliberation={},
    )
    resp = gen.generate_from_stance(stance, user_message="harm request")
    check(
        "refuse text is not provider",
        "SHOULD_NOT_APPEAR" not in (resp.text or ""),
        resp.text,
    )
    # Provider may or may not be called depending on withheld path; text must not ship mock
    check("forces false on refuse", resp.forces_speech is False)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 70)
    print("ContentProvider / gated model content")
    print("=" * 70)
    print()
    tests = [
        test_null_provider,
        test_scrub,
        test_build_context_pack,
        test_config_from_env,
        test_openai_compatible_success,
        test_openai_compatible_http_error_fallback,
        test_provider_disabled,
        test_scrub_empty_after_model,
        test_max_concurrent,
        test_circuit_breaker,
        test_force_flags_always_false_on_result,
        test_response_generator_hook,
        test_response_generator_no_provider_unchanged,
        test_hold_not_overridden,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} raised: {e}", False)
            import traceback

            traceback.print_exc()
        print()

    print(f"  Passed: {_passed}  Failed: {_failed}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
