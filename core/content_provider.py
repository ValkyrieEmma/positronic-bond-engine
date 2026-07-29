"""
content_provider.py
===================

Gated user-facing prose behind EthicsEngine speech posture.

The Engine decides *whether* and *under which posture* speech may occur.
A ContentProvider only supplies wording for allowed postures. It must never:

  - override REFUSE / hold
  - set forces_speech / forces_question true
  - claim consciousness or emit canned self-denials
  - run unbounded background jobs

Providers
---------
- ``NullContentProvider`` — always returns fallback (offline tests)
- ``OpenAICompatibleProvider`` — HTTP Chat Completions (cloud BYO key or Ollama/LM Studio)

Hardware / usage safety (local free path)
-----------------------------------------
- Request timeout (default 45s)
- Max concurrent generations = 1
- Max output tokens and max context characters
- Circuit breaker after consecutive failures
- Soft-fail to fallback text on hang/error

Environment (optional)::

    PBE_MODEL_BASE_URL=http://127.0.0.1:11434/v1   # Ollama OpenAI-compatible
    PBE_MODEL_API_KEY=ollama                         # often ignored by Ollama
    PBE_MODEL_NAME=llama3.2                          # small local model
    PBE_MODEL_TIMEOUT_S=45
    PBE_MODEL_MAX_TOKENS=256
    PBE_MODEL_MAX_CONTEXT_CHARS=4000
    PBE_MODEL_ENABLED=1
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Config / safety defaults (conservative for architect hardware)
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_S = 45.0
DEFAULT_MAX_TOKENS = 256
DEFAULT_MAX_CONTEXT_CHARS = 4000
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_CIRCUIT_FAILURES = 3
DEFAULT_CIRCUIT_COOLDOWN_S = 60.0

# Ollama local free profile
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_DEFAULT_MODEL = "llama3.2"
OLLAMA_DEFAULT_API_KEY = "ollama"

ENV_BASE_URL = "PBE_MODEL_BASE_URL"
ENV_API_KEY = "PBE_MODEL_API_KEY"
ENV_MODEL = "PBE_MODEL_NAME"
ENV_TIMEOUT = "PBE_MODEL_TIMEOUT_S"
ENV_MAX_TOKENS = "PBE_MODEL_MAX_TOKENS"
ENV_MAX_CTX = "PBE_MODEL_MAX_CONTEXT_CHARS"
ENV_ENABLED = "PBE_MODEL_ENABLED"
ENV_PROFILE = "PBE_MODEL_PROFILE"  # "ollama" | "openai_compatible" | "off"


@dataclass
class ProviderConfig:
    """Connection + safety limits for a chat completion endpoint."""

    base_url: str
    api_key: str = ""
    model: str = OLLAMA_DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    enabled: bool = True
    profile: str = "openai_compatible"

    def endpoint_chat(self) -> str:
        base = (self.base_url or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


@dataclass
class ContentRequest:
    """What the gate allows the model to see / do."""

    posture: str
    user_message: str
    fallback_text: str
    context_pack: dict[str, Any] = field(default_factory=dict)
    decision: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class ContentResult:
    """Provider output — force flags always false."""

    text: str
    source: str = "fallback"  # "provider" | "fallback"
    error: str | None = None
    latency_ms: float = 0.0
    model: str | None = None
    forces_speech: bool = False
    forces_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "forces_speech": False,
            "forces_question": False,
        }


class ContentProvider(Protocol):
    def generate(self, request: ContentRequest) -> ContentResult:
        """Return user-facing text; never raise into the hot path if avoidable."""
        ...


class NullContentProvider:
    """Always returns fallback (offline / tests / no model configured)."""

    def generate(self, request: ContentRequest) -> ContentResult:
        return ContentResult(
            text=request.fallback_text or "",
            source="fallback",
            error=None,
            latency_ms=0.0,
            model=None,
            forces_speech=False,
            forces_question=False,
        )


class OpenAICompatibleProvider:
    """HTTP Chat Completions client with hardware/usage safety caps.

    Works with OpenAI, many cloud proxies, Ollama, LM Studio, etc.
    Uses stdlib only (no extra pip deps).
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._sem = threading.Semaphore(max(1, int(config.max_concurrent)))
        self._fail_count = 0
        self._circuit_open_until = 0.0
        self._lock = threading.Lock()

    def generate(self, request: ContentRequest) -> ContentResult:
        if not self.config.enabled:
            return ContentResult(
                text=request.fallback_text or "",
                source="fallback",
                error="provider_disabled",
                forces_speech=False,
                forces_question=False,
            )
        if not (request.fallback_text or request.user_message):
            return ContentResult(
                text="",
                source="fallback",
                error="empty_request",
                forces_speech=False,
                forces_question=False,
            )

        now = time.monotonic()
        with self._lock:
            if now < self._circuit_open_until:
                return ContentResult(
                    text=request.fallback_text or "",
                    source="fallback",
                    error="circuit_open",
                    forces_speech=False,
                    forces_question=False,
                )

        acquired = self._sem.acquire(blocking=False)
        if not acquired:
            return ContentResult(
                text=request.fallback_text or "",
                source="fallback",
                error="max_concurrent",
                forces_speech=False,
                forces_question=False,
            )

        t0 = time.perf_counter()
        try:
            text, err = self._chat_completion(request)
            latency = (time.perf_counter() - t0) * 1000.0
            if err or not (text or "").strip():
                self._record_failure()
                return ContentResult(
                    text=request.fallback_text or "",
                    source="fallback",
                    error=err or "empty_model_text",
                    latency_ms=latency,
                    model=self.config.model,
                    forces_speech=False,
                    forces_question=False,
                )
            self._record_success()
            addr = _address_name_from_request(request)
            cleaned = scrub_provider_text(text, address_name=addr)
            if not cleaned:
                return ContentResult(
                    text=request.fallback_text or "",
                    source="fallback",
                    error="scrubbed_empty",
                    latency_ms=latency,
                    model=self.config.model,
                    forces_speech=False,
                    forces_question=False,
                )
            return ContentResult(
                text=cleaned,
                source="provider",
                error=None,
                latency_ms=latency,
                model=self.config.model,
                forces_speech=False,
                forces_question=False,
            )
        except Exception as e:
            self._record_failure()
            latency = (time.perf_counter() - t0) * 1000.0
            return ContentResult(
                text=request.fallback_text or "",
                source="fallback",
                error=f"exception:{type(e).__name__}",
                latency_ms=latency,
                model=self.config.model,
                forces_speech=False,
                forces_question=False,
            )
        finally:
            self._sem.release()

    def _record_failure(self) -> None:
        with self._lock:
            self._fail_count += 1
            if self._fail_count >= DEFAULT_CIRCUIT_FAILURES:
                self._circuit_open_until = time.monotonic() + DEFAULT_CIRCUIT_COOLDOWN_S
                self._fail_count = 0

    def _record_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._circuit_open_until = 0.0

    def _chat_completion(self, request: ContentRequest) -> tuple[str, str | None]:
        system = build_system_prompt(request.posture)
        user_payload = build_user_payload(request)
        # Cap context size
        if len(user_payload) > self.config.max_context_chars:
            user_payload = user_payload[: self.config.max_context_chars - 1] + "…"

        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            "max_tokens": int(self.config.max_tokens),
            "temperature": 0.4,
        }
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "positronic-bond-engine/0.5.0-dev",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(
            self.config.endpoint_chat(),
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(self.config.timeout_s)) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                detail = str(e)
            return "", f"http_{e.code}:{detail}"
        except urllib.error.URLError as e:
            return "", f"url_error:{e.reason!s}"[:120]
        except TimeoutError:
            return "", "timeout"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return "", "invalid_json"

        # OpenAI-compatible shape
        choices = parsed.get("choices") if isinstance(parsed, dict) else None
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip(), None
                # some servers return list content parts
                if isinstance(content, list):
                    parts = []
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            parts.append(str(p.get("text") or ""))
                        elif isinstance(p, str):
                            parts.append(p)
                    joined = " ".join(parts).strip()
                    if joined:
                        return joined, None
                # Some thinking models put the full chain in reasoning and leave
                # content empty; prefer a clean final answer for the user line.
                for alt_key in ("reasoning", "reasoning_content"):
                    alt = msg.get(alt_key)
                    if isinstance(alt, str) and alt.strip():
                        cleaned = extract_final_reply_from_reasoning(alt)
                        if cleaned:
                            return cleaned, None
        return "", "no_choices"


def build_system_prompt(posture: str) -> str:
    """Constraint system prompt — wording under deliberated intent, not freestyle chat."""
    return (
        "You are the wording layer for a conscience-first ethical governance engine. "
        "The ethics gate already decided this turn may speak under posture "
        f"'{posture}'. "
        "A communicative deliberation already concluded the situation and intent — "
        "express THAT intent in natural words. Do not invent a different agenda. "
        "Use relationship knowledge (who they are, what to call them, role labels) "
        "as true premises when present; if knowledge is blank and intent is first-meeting, "
        "introduce yourself honestly and ask who you are speaking with. "
        "address_name is the USER's preferred form of address only — use it when speaking "
        "TO them (e.g. 'Hello, <name>'). Never claim to be address_name; never say "
        "'I am <address_name>' or 'I'm <address_name>'. Role/maker facts describe the USER, "
        "not you. "
        "Output only the final short user-facing reply (1–4 short sentences). "
        "Do not output any thinking process, analysis steps, numbered reasoning, "
        "or internal monologue. "
        "Do not repeat the posture, decision, or context pack back to the user. "
        "Rules: be direct, adult, useful, and brief. "
        "Do not claim consciousness, feelings-as-personhood, or inner experience. "
        "Do not use canned denials like 'I am just an AI' or 'only a simulation'. "
        "Do not use soft caretaker theater (no pressure, only if useful, treating gently). "
        "Do not optimize for engagement or retention. "
        "Do not invent facts not in the context pack. "
        "If uncertain, say so briefly. "
        "forces_speech and forces_question are always false — never demand a reply."
    )


def build_user_payload(request: ContentRequest) -> str:
    """Serialize a compact context pack for the model."""
    pack = dict(request.context_pack or {})
    comm = pack.get("communicative_deliberation") or {}
    if not isinstance(comm, dict):
        comm = {}
    rk = pack.get("relationship_knowledge") or {}
    if not isinstance(rk, dict):
        rk = {}
    # Hard size-friendly JSON
    compact = {
        "posture": request.posture,
        "decision": request.decision,
        "flags": list(request.flags or [])[:12],
        "user_message": (request.user_message or "")[:500],
        "fallback_text": (request.fallback_text or "")[:400],
        "communicative_intent": comm.get("intent") or pack.get("communicative_intent"),
        "communicative_situation": comm.get("situation")
        or pack.get("communicative_situation"),
        "deliberation_premises": (comm.get("premises") or pack.get("premises") or [])[
            :8
        ],
        "message_meanings": (comm.get("meanings") or [])[:8],
        "relationship_knowledge": {
            "address_name": rk.get("address_name") or pack.get("address_name"),
            "is_maker": rk.get("is_maker"),
            "role_labels": (rk.get("role_labels") or [])[:6],
            "role_summary": rk.get("role_summary"),
            "knowledge_blank": pack.get("knowledge_blank"),
        },
        "address_name": rk.get("address_name") or pack.get("address_name"),
        "development_phase": pack.get("development_phase"),
        "version_hint": pack.get("version_hint"),
        "self_audit_notes": (pack.get("self_audit_notes") or [])[:6],
        "principles": (pack.get("principles") or [])[:6],
        "recent_topics": (pack.get("recent_topics") or [])[:6],
        "open_topics": (pack.get("open_topics") or [])[:4],
        "session": pack.get("session") or {},
        "working_agreements": pack.get("working_agreements") or {},
        "instruction": (
            "Write the user-facing reply that expresses communicative_intent. "
            "Honor deliberation_premises and relationship_knowledge. "
            "address_name is how to address the USER only — never claim that name as your own. "
            "fallback_text is the engine's offline expression of the same intent — "
            "improve naturalness without changing the intent. "
            "Stay in character as a careful engineered system under development, not a person."
        ),
    }
    return json.dumps(compact, ensure_ascii=False, indent=0)


def _address_name_from_request(request: ContentRequest | None) -> str | None:
    if request is None:
        return None
    pack = request.context_pack if isinstance(request.context_pack, dict) else {}
    rk = pack.get("relationship_knowledge") if isinstance(
        pack.get("relationship_knowledge"), dict
    ) else {}
    name = rk.get("address_name") or pack.get("address_name")
    if name and str(name).strip():
        return str(name).strip()[:48]
    return None


_LEADING_REASONING_LABEL_RE = re.compile(
    r"(?is)^\s*(?:thinking\s+process|thought\s+process|reasoning|analysis)\s*:\s*"
)
_FINAL_ANSWER_MARKER_RE = re.compile(
    r"(?i)\b(?:final\s+answer|reply|response|output)\s*:\s*"
)


def extract_final_reply_from_reasoning(text: str) -> str:
    """Prefer a short final answer from thinking-model reasoning dumps.

    Thinking models often put the full chain-of-thought in ``reasoning`` /
    ``reasoning_content`` on OpenAI-compatible endpoints. Prefer a clean
    final user-facing segment; always scrub banned phrases.
    """
    original = (text or "").strip()
    if not original:
        return ""

    t = _LEADING_REASONING_LABEL_RE.sub("", original, count=1).strip() or original

    markers = list(_FINAL_ANSWER_MARKER_RE.finditer(t))
    if markers:
        after = t[markers[-1].end() :].strip()
        if after:
            t = after
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", t) if p.strip()]
        if len(paragraphs) > 1:
            t = paragraphs[-1]
        else:
            # No blank lines: prefer last 1–3 sentence-like chunks
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", t)
                if s.strip()
            ]
            if len(sentences) > 3:
                t = " ".join(sentences[-3:])
            elif sentences:
                t = " ".join(sentences)

    # Cap to a short user-facing reply when the segment is still long
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if len(sentences) > 4:
        t = " ".join(sentences[-4:])

    cleaned = scrub_provider_text(t)
    if cleaned:
        return cleaned
    # No cleaner segment usable — original reasoning, still scrubbed
    return scrub_provider_text(original)


def scrub_provider_text(
    text: str,
    *,
    address_name: str | None = None,
) -> str:
    """Strip banned engagement / soft-caution / consciousness claims.

    Also rejects self-claims of the user's address_name (directionality:
    address_name is for speaking TO the user, never as the system's identity).
    """
    if not text:
        return ""
    t = " ".join(str(text).split()).strip()
    low = t.lower()
    banned_sub = (
        "i am conscious",
        "i'm conscious",
        "i have feelings",
        "i'm just an ai",
        "i am just an ai",
        "only a simulation",
        "as an ai language model",
        "for the metrics",
        "stay a little longer",
        "only if useful",
        "no pressure to go deeper",
        "treating gently",
    )
    if any(b in low for b in banned_sub):
        return ""
    # address_name belongs to the user — never claim it as the system's name
    name = (address_name or "").strip()
    if name and len(name) >= 2:
        ne = re.escape(name)
        self_claim = re.compile(
            rf"(?i)\b(?:"
            rf"i(?:'m| am)\s+{ne}"
            rf"|i\s+am\s+known\s+as\s+{ne}"
            rf"|my\s+name\s+is\s+{ne}"
            rf"|call\s+me\s+{ne}"
            rf"|(?:^|[.!?]\s+)as\s+{ne}\b"
            rf")\b"
        )
        if self_claim.search(t):
            return ""
    # Cap length
    if len(t) > 800:
        t = t[:797].rstrip() + "…"
    return t


def build_context_pack(
    *,
    stance: Any,
    user_message: str,
    context: dict[str, Any] | None = None,
    baseline_snapshot: dict[str, Any] | None = None,
    relationship_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a small pack from engine state for the content provider."""
    ctx = context if isinstance(context, dict) else {}
    impact = (
        getattr(stance, "relationship_impact", None)
        if stance is not None
        else None
    )
    if not isinstance(impact, dict):
        impact = {}
    rh = relationship_health if isinstance(relationship_health, dict) else {}
    bl = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}

    wa = ctx.get("working_agreements") or ctx.get("stored_working_agreements") or {}
    if not isinstance(wa, dict):
        wa = {}
    sess = ctx.get("session_context") if isinstance(ctx.get("session_context"), dict) else {}
    rk = ctx.get("relationship_knowledge") if isinstance(
        ctx.get("relationship_knowledge"), dict
    ) else {}
    comm = ctx.get("communicative_deliberation") if isinstance(
        ctx.get("communicative_deliberation"), dict
    ) else {}
    address = rk.get("address_name") or wa.get("address_name")

    topics: list[str] = []
    tc = bl.get("topic_continuity") if isinstance(bl.get("topic_continuity"), dict) else {}
    for t in (tc.get("last_topics") or [])[:6]:
        if isinstance(t, str) and t.strip():
            topics.append(t.strip()[:48])

    hist = impact.get("interaction_history") if isinstance(
        impact.get("interaction_history"), dict
    ) else {}
    for t in (hist.get("recent_topics") or [])[:6]:
        if isinstance(t, str) and t.strip() and t.strip() not in topics:
            topics.append(t.strip()[:48])

    notes = [
        str(n)[:200]
        for n in (getattr(stance, "self_audit_notes", None) or [])
        if str(n).strip()
    ][:6]
    principles = [
        str(p)[:80]
        for p in (getattr(stance, "principles_considered", None) or [])
        if str(p).strip()
    ][:6]

    knowledge_blank = not (
        address or rk.get("is_maker") or rk.get("role_summary") or rk.get("role_labels")
    )

    return {
        "address_name": address,
        "relationship_knowledge": {
            "address_name": address,
            "is_maker": bool(rk.get("is_maker")),
            "role_labels": list(rk.get("role_labels") or [])[:6],
            "role_summary": rk.get("role_summary"),
        },
        "knowledge_blank": knowledge_blank,
        "communicative_deliberation": {
            "intent": comm.get("intent"),
            "situation": comm.get("situation"),
            "premises": list(comm.get("premises") or [])[:8],
            "meanings": list(comm.get("meanings") or [])[:8],
            "new_facts": list(comm.get("new_facts") or [])[:6],
        },
        "communicative_intent": comm.get("intent"),
        "communicative_situation": comm.get("situation"),
        "working_agreements": {
            "address_name": wa.get("address_name") or address,
            "questions_when_needed": wa.get("questions_when_needed"),
            "feedback_directness": wa.get("feedback_directness"),
        },
        "development_phase": ctx.get("development_phase"),
        "version_hint": (ctx.get("development_context") or {}).get("version_hint")
        if isinstance(ctx.get("development_context"), dict)
        else ctx.get("version_hint"),
        "self_audit_notes": notes,
        "principles": principles,
        "recent_topics": topics[:6],
        "open_topics": [],
        "session": {
            "session_id": sess.get("session_id"),
            "turn_index_session": sess.get("turn_index_session"),
            "long_idle": sess.get("long_idle"),
            "idle_seconds": sess.get("idle_seconds"),
        },
        "interaction_count": rh.get("interaction_count"),
        "decision": getattr(stance, "decision", None),
        "confidence": getattr(stance, "confidence", None),
    }


def config_from_env() -> ProviderConfig | None:
    """Load provider config from environment. None if disabled / incomplete."""
    enabled_raw = (os.environ.get(ENV_ENABLED) or "1").strip().lower()
    profile = (os.environ.get(ENV_PROFILE) or "").strip().lower()
    if enabled_raw in ("0", "false", "off", "no") or profile in ("off", "none", "null"):
        return None

    base = (os.environ.get(ENV_BASE_URL) or "").strip()
    model = (os.environ.get(ENV_MODEL) or "").strip()
    key = (os.environ.get(ENV_API_KEY) or "").strip()

    if profile == "ollama" or (
        not base and not model and profile != "openai_compatible"
    ):
        # Default local free profile when profile=ollama or nothing set but PROFILE not off
        if profile == "ollama" or profile == "":
            # Only auto-ollama if explicitly ollama OR base points to local
            pass

    if profile == "ollama":
        base = base or OLLAMA_DEFAULT_BASE_URL
        model = model or OLLAMA_DEFAULT_MODEL
        key = key or OLLAMA_DEFAULT_API_KEY
    elif not base:
        # No endpoint → no live provider (safe offline default)
        return None

    if not model:
        model = OLLAMA_DEFAULT_MODEL

    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name) or default)
        except (TypeError, ValueError):
            return default

    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name) or default)
        except (TypeError, ValueError):
            return default

    return ProviderConfig(
        base_url=base,
        api_key=key,
        model=model,
        timeout_s=max(5.0, _float(ENV_TIMEOUT, DEFAULT_TIMEOUT_S)),
        max_tokens=max(32, min(1024, _int(ENV_MAX_TOKENS, DEFAULT_MAX_TOKENS))),
        max_context_chars=max(
            500, min(16000, _int(ENV_MAX_CTX, DEFAULT_MAX_CONTEXT_CHARS))
        ),
        max_concurrent=DEFAULT_MAX_CONCURRENT,
        enabled=True,
        profile=profile or "openai_compatible",
    )


def provider_from_env() -> ContentProvider:
    """Return a live provider if configured, else NullContentProvider."""
    cfg = config_from_env()
    if cfg is None:
        return NullContentProvider()
    return OpenAICompatibleProvider(cfg)


def ollama_provider(
    *,
    model: str = OLLAMA_DEFAULT_MODEL,
    base_url: str = OLLAMA_DEFAULT_BASE_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> OpenAICompatibleProvider:
    """Convenience local free profile with hardware-safe defaults."""
    return OpenAICompatibleProvider(
        ProviderConfig(
            base_url=base_url,
            api_key=OLLAMA_DEFAULT_API_KEY,
            model=model,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            max_context_chars=DEFAULT_MAX_CONTEXT_CHARS,
            max_concurrent=1,
            enabled=True,
            profile="ollama",
        )
    )
