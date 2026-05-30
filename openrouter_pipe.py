"""
title: OpenRouter Pipe
author: Sena Labs
author_url: https://github.com/sena-labs
funding_url: https://github.com/sponsors/sena-labs
version: 1.9.0
license: MIT
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNmQyOGQ5Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjYTc4YmZhIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIHJ4PSIyMCIgZmlsbD0idXJsKCNiZykiLz48cGF0aCBkPSJNMjAgNTAgQzIwIDMwLCA0MCAzMCwgNTAgMzAgTDUwIDIyIEw2OCA0MCBMNTAgNTggTDUwIDUwIEM0MCA1MCwgMzUgNDUsIDMwIDUwIEMyNSA1NSwgMjAgNzAsIDIwIDUwIFoiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSIzMCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxjaXJjbGUgY3g9IjgyIiBjeT0iNTAiIHI9IjciIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSI3MCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxsaW5lIHgxPSI2OCIgeTE9IjQwIiB4Mj0iNzYiIHkyPSIzMiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBvcGFjaXR5PSIwLjUiLz48bGluZSB4MT0iNjgiIHkxPSI0MCIgeDI9Ijc2IiB5Mj0iNTAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC41Ii8+PGxpbmUgeDE9IjY4IiB5MT0iNDAiIHgyPSI3NiIgeTI9IjY4IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIG9wYWNpdHk9IjAuNSIvPjwvc3ZnPg==
required_open_webui_version: 0.4.0
requirements: requests>=2.32.4, pydantic>=2.0
description: The definitive OpenRouter integration for Open WebUI. Full catalog (chat/TTS/audio/image/embeddings), variant routing (:nitro/:exacto/:thinking/:online/:free/:extended), web search plugin with domain filters, server-side category filter, deprecation warnings, extended reasoning (minimal→xhigh + max_tokens + summary), Anthropic interleaved thinking + cache TTL, ZDR enforcement, tool/free-tier filters, provider preferences (only/quantizations/max_price/allow_fallbacks), service tier routing (flex/priority), generation-ID auditability, cached-input cost breakdown, model fallbacks, middle-out compression, citations, auto-discovered provider icons. Per-user API keys and preferences via UserValves, with at-rest key encryption (Fernet, keyed on WEBUI_SECRET_KEY). Native function/tool calling (parallel execution, streaming + non-streaming) with a tool-iteration cap, and an opt-in OpenRouter remaining-credit footer. Transient 429/5xx retries with Retry-After awareness.
"""

import asyncio
import base64
import copy
import email.utils
import hashlib
import inspect
import json
import os
import random
import re
import time
import traceback
from typing import AsyncGenerator, Callable, Generator, List, Optional, Union

import requests
from pydantic import BaseModel, Field, field_validator

# Keys injected by Open WebUI internals — must not be forwarded to OpenRouter
_OWUI_INTERNAL_KEYS = frozenset(
    {"chat_id", "title", "task", "task_id", "features", "citations",
     "metadata", "files", "tool_ids", "session_id", "message_id"}
)

_CITATION_RE = re.compile(r"\[(\d+)\]")

# API path constants
_API_PATH_MODELS = "/models"
_API_PATH_CHAT = "/chat/completions"
_API_PATH_ZDR_ENDPOINTS = "/endpoints/zdr"
_API_PATH_CREDITS = "/credits"

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER = 60.0  # cap (seconds) — a huge Retry-After must not hang the request

# Sentinel used with asyncio.to_thread(next, it, _STREAM_DONE) to detect
# exhausted sync generators without raising StopIteration across thread boundaries.
_STREAM_DONE = object()

# Beta header for Claude's interleaved-thinking + tool-use mode.
# https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
_ANTHROPIC_INTERLEAVED_THINKING_BETA = "interleaved-thinking-2025-05-14"

# OpenRouter variant suffixes that route to specialized providers/profiles.
# https://openrouter.ai/docs/features/preset-routing
_RECOGNISED_VARIANT_TAGS = frozenset(
    {"free", "thinking", "online", "nitro", "exacto", "extended"}
)

# Cache TTL for model list (seconds)
_MODELS_CACHE_TTL = 300.0  # 5 minutes

# Cache TTL for the OpenRouter provider registry (seconds).
# Refreshed periodically so transient fetch failures and CDN path changes
# are recovered automatically without restarting the pipe.
_PROVIDER_REGISTRY_TTL = 3600.0  # 1 hour

# Back-off TTL used when the registry fetch fails or returns non-200.
# Shorter than the success TTL so transient failures are retried sooner
# without hammering the OpenRouter API.
_PROVIDER_REGISTRY_FAIL_TTL = 300.0  # 5 minutes

# OpenRouter's frontend provider registry — gives us icon URLs for ~70 providers
# (hosted SVG/PNG when available, gstatic favicons otherwise). Used as a
# dynamic fallback when a model's author isn't in _PROVIDER_ICONS.
_PROVIDER_REGISTRY_URL = "https://openrouter.ai/api/frontend/all-providers"

# Provider icons — synced into the Open WebUI Models database by
# _sync_model_icons() so the frontend can serve them via
# /models/model/profile/image.  Disable with SYNC_PROVIDER_ICONS = False.
# Hardcoded fast path for top model authors; everything else is auto-discovered
# via _load_provider_registry().
# URLs verified against https://openrouter.ai/images/icons/ (May 2025).
_PROVIDER_ICONS = {
    "openai": "https://openrouter.ai/images/icons/OpenAI.svg",
    "anthropic": "https://openrouter.ai/images/icons/Anthropic.svg",
    "google": "https://openrouter.ai/images/icons/GoogleGemini.svg",
    "meta-llama": "https://openrouter.ai/images/icons/Meta.png",
    "mistralai": "https://openrouter.ai/images/icons/Mistral.png",
    "amazon": "https://openrouter.ai/images/icons/Bedrock.svg",
    "deepseek": "https://openrouter.ai/images/icons/DeepSeek.png",
    "cohere": "https://openrouter.ai/images/icons/Cohere.png",
    "perplexity": "https://openrouter.ai/images/icons/Perplexity.svg",
    "qwen": "https://openrouter.ai/images/icons/Qwen.png",
    "microsoft": "https://openrouter.ai/images/icons/Microsoft.svg",
    "fireworks": "https://openrouter.ai/images/icons/Fireworks.png",
    "moonshotai": "https://openrouter.ai/images/icons/MoonshotAI.png",
}


def _is_safe_url(url: str) -> bool:
    """Return True only for http:// and https:// URLs."""
    return isinstance(url, str) and url.lower().startswith(("http://", "https://"))


def _is_owui_managed_icon(url: str) -> bool:
    """Return True if the icon URL was set by OWUI or our sync logic.

    data: URLs are the pipe's own SVG icon that OWUI assigns as default to all
    manifold child models.  openrouter.ai/images/models/ and
    openrouter.ai/images/icons/ are the OpenRouter-hosted provider icons we
    write (the former was the old path, superseded by the latter).
    t0.gstatic.com/faviconV2 URLs are the gstatic favicons returned by
    OpenRouter's provider registry for providers without a hosted icon — we
    write those too as part of icon auto-discovery, so they must remain
    overwriteable when OpenRouter updates its mapping.  Any other URL is
    assumed to be a user-set custom icon and must not be overwritten.
    """
    return (
        not url
        or url.startswith("data:")
        or url.startswith("https://openrouter.ai/images/models/")
        or url.startswith("https://openrouter.ai/images/icons/")
        # Require the query string ("?") so a user-set bare gstatic URL isn't
        # misclassified — real faviconV2 icons always carry query params.
        or url.startswith("https://t0.gstatic.com/faviconV2?")
    )


def _insert_citations(text: str, citations: Optional[List[str]]) -> str:
    """Replace [n] references with markdown links (only safe HTTP URLs)."""
    if not citations or not text:
        return text

    def _replace(match_obj):
        try:
            idx = int(match_obj.group(1)) - 1
            if 0 <= idx < len(citations) and _is_safe_url(citations[idx]):
                safe_url = citations[idx].replace(")", "%29")
                return f"[[{idx + 1}]]({safe_url})"
        except (ValueError, IndexError):
            pass
        return match_obj.group(0)

    try:
        return _CITATION_RE.sub(_replace, text)
    except Exception as exc:  # pragma: no cover
        print(f"[OpenRouter Pipe] Citation injection error: {exc}")
        return text


_CITATION_SANITIZE_RE = re.compile(r"[`\r\n]")


def _format_citation_list(citations: Optional[List[str]]) -> str:
    if not citations:
        return ""
    try:
        rendered = "\n".join(
            f"{idx + 1}. {_CITATION_SANITIZE_RE.sub('', str(url))}"
            for idx, url in enumerate(citations)
        )
        return f"\n\n---\nCitations:\n{rendered}"
    except Exception as exc:  # pragma: no cover
        print(f"[OpenRouter Pipe] Citation formatting error: {exc}")
        return ""


_CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CAD": "CA$",
    "AUD": "A$",
}


def _format_cost_info(usage: dict, currency: str = "USD") -> str:
    """Format token usage and cost from an OpenRouter usage dict.

    When the provider reports cached prompt tokens (90%+ cheaper on most
    providers), the breakdown is shown so users see the savings.
    """
    if not usage:
        return ""
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0) or (prompt + completion)
    cost = usage.get("cost")

    # Cached prompt tokens — emitted by Anthropic prompt caching, OpenAI
    # implicit caching, and Gemini context caching. Shape varies per provider.
    cached_tokens = 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached_tokens = details.get("cached_tokens") or 0
    if not cached_tokens:
        cached_tokens = usage.get("cache_read_input_tokens") or 0

    if cached_tokens:
        non_cached = max(prompt - int(cached_tokens), 0)
        token_str = (
            f"{non_cached:,} prompt + {int(cached_tokens):,} cached + "
            f"{completion:,} completion = {total:,} total"
        )
    else:
        token_str = f"{prompt:,} prompt + {completion:,} completion = {total:,} total"
    parts = [f"**Tokens:** {token_str}"]

    if cost is not None:
        try:
            cost_f = float(cost)
            symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
            if cost_f == 0:
                cost_str = f"{symbol}0.00"
            elif cost_f < 0.0001:
                cost_str = f"{symbol}{cost_f:.6f}"
            elif cost_f < 0.01:
                cost_str = f"{symbol}{cost_f:.5f}"
            else:
                cost_str = f"{symbol}{cost_f:.4f}"
            parts.append(f"**Cost:** {cost_str}")
        except (ValueError, TypeError):
            pass

    return f"\n\n---\n*{' · '.join(parts)}*"


def _format_generation_id(generation_id: Optional[str]) -> str:
    """Format the OpenRouter generation ID footer.

    Users can pass the ID to ``GET /api/v1/generation?id={id}`` to retrieve
    detailed usage and routing info for any past request.
    """
    if not generation_id:
        return ""
    # Strip backticks/newlines so a malicious upstream ID can't break out of
    # the code span and inject markdown into the rendered response.
    safe = re.sub(r"[`\r\n]", "", str(generation_id))
    if not safe:
        return ""
    return f"\n\n---\n*Generation ID: `{safe}`*"


def _format_image_output(images: list) -> str:
    """Format OpenRouter image output objects as markdown image tags.

    Only http(s) and data:image/* URLs are rendered; others are dropped.
    Closing parentheses in URLs are percent-encoded to avoid breaking markdown.
    """
    parts = []
    for img in (images or []):
        if not isinstance(img, dict):
            continue
        url = (img.get("image_url") or {}).get("url", "")
        if not url or len(url) > 2_000_000:
            continue
        lower = url.lower()
        allowed_data = lower.startswith((
            "data:image/png", "data:image/jpeg", "data:image/jpg",
            "data:image/gif", "data:image/webp",
        ))
        if not (lower.startswith(("http://", "https://")) or allowed_data):
            continue
        parts.append(f"![Generated image]({url.replace(')', '%29')})")
    return "\n\n".join(parts)


# Optional dependency: Open WebUI bundles `cryptography`. When absent (e.g. the
# pipe is imported in a bare environment) the key degrades to plaintext storage
# rather than failing — see EncryptedStr.
try:
    from cryptography.fernet import Fernet as _Fernet
except Exception:  # pragma: no cover - exercised only without cryptography
    _Fernet = None

_ENC_PREFIX = "encrypted:"
_ENC_WARNED = False


class EncryptedStr(str):
    """A valve value encrypted at rest in Open WebUI's database.

    Ciphertext is tagged with the ``encrypted:`` prefix. Real OpenRouter keys
    begin ``sk-or-`` so plaintext never collides with the marker. The Fernet key
    is derived from ``WEBUI_SECRET_KEY``. When that env var is missing, or the
    ``cryptography`` package is unavailable, values are stored and returned as
    plaintext (with a one-time warning) so the pipe keeps working.
    """

    @staticmethod
    def _fernet():
        global _ENC_WARNED
        secret = os.getenv("WEBUI_SECRET_KEY")
        if not secret or _Fernet is None:
            if not _ENC_WARNED:
                _ENC_WARNED = True
                reason = "WEBUI_SECRET_KEY not set" if not secret else "cryptography not installed"
                print(f"[OpenRouter Pipe] API key stored in plaintext ({reason})")
            return None
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return _Fernet(key)

    @classmethod
    def encrypt(cls, value: str) -> str:
        if not value or value.startswith(_ENC_PREFIX):
            return value
        fernet = cls._fernet()
        if fernet is None:
            return value
        return _ENC_PREFIX + fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, value: str) -> str:
        if not value or not value.startswith(_ENC_PREFIX):
            return value
        fernet = cls._fernet()
        if fernet is None:
            return value
        try:
            token = value[len(_ENC_PREFIX):].encode("utf-8")
            return fernet.decrypt(token).decode("utf-8")
        except Exception:
            return ""


class Pipe:
    class Valves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default=os.getenv("OPENROUTER_API_KEY", ""),
            description="OpenRouter API key",
            json_schema_extra={"input": {"type": "password"}},
        )
        OPENROUTER_BASE_URL: str = Field(
            default=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            description="OpenRouter base endpoint (must start with https://)",
        )
        REASONING_EFFORT: str = Field(
            default=os.getenv("OPENROUTER_REASONING_EFFORT", ""),
            description=(
                "Controls reasoning depth. Works independently of Include Reasoning. "
                "'minimal' favors fastest output, 'xhigh' requests maximum depth on "
                "supporting models."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "", "label": "Disabled"},
                        {"value": "minimal", "label": "Minimal"},
                        {"value": "low", "label": "Low"},
                        {"value": "medium", "label": "Medium"},
                        {"value": "high", "label": "High"},
                        {"value": "xhigh", "label": "Extra High"},
                    ],
                }
            },
        )
        REASONING_SUMMARY_MODE: str = Field(
            default=os.getenv("OPENROUTER_REASONING_SUMMARY_MODE", "disabled"),
            description=(
                "Reasoning summary verbosity sent as `reasoning.summary` in the "
                "request payload. 'disabled' (default) skips the field entirely; "
                "supporting models emit a concise/detailed summary block alongside "
                "their reasoning trace."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "disabled", "label": "Disabled"},
                        {"value": "auto", "label": "Auto"},
                        {"value": "concise", "label": "Concise"},
                        {"value": "detailed", "label": "Detailed"},
                    ],
                }
            },
        )
        REASONING_MAX_TOKENS: int = Field(
            default=int(os.getenv("OPENROUTER_REASONING_MAX_TOKENS", "0")),
            ge=0,
            description=(
                "Hard cap on reasoning tokens per response (sent as "
                "`reasoning.max_tokens`). 0 (default) leaves the cap to the "
                "provider. Useful for budget control on deep-thinking models."
            ),
        )
        INCLUDE_REASONING: bool = Field(
            default=os.getenv("OPENROUTER_INCLUDE_REASONING", "true").lower() == "true",
            description="Show model reasoning in <think> blocks. Can be used with or without Reasoning Effort",
        )
        ENABLE_ANTHROPIC_INTERLEAVED_THINKING: bool = Field(
            default=os.getenv(
                "OPENROUTER_ANTHROPIC_INTERLEAVED_THINKING", "true"
            ).lower()
            == "true",
            description=(
                "When True and the selected model is `anthropic/...`, send the "
                "`anthropic-beta: interleaved-thinking-2025-05-14` header so Claude "
                "interleaves reasoning with tool use. No effect on other providers."
            ),
        )
        MODEL_PREFIX: Optional[str] = Field(
            default=None, description="Prefix shown before model names (include trailing space if needed, e.g. 'OR: ')"
        )
        MODEL_PROVIDERS: str = Field(
            default=os.getenv("OPENROUTER_MODEL_PROVIDERS", "ALL"),
            description="Provider filter (e.g. openai,google). Use ALL for all models",
        )
        INVERT_PROVIDER_LIST: bool = Field(
            default=os.getenv("OPENROUTER_INVERT_PROVIDER_LIST", "false").lower()
            == "true",
            description="When true the provider list becomes an exclusion list",
        )
        FREE_MODEL_FILTER: str = Field(
            # Back-compat: honour the legacy OPENROUTER_FREE_ONLY env var
            # (boolean) when the new var is unset, so installs upgrading from
            # the FREE_ONLY era don't silently start returning paid models.
            default=os.getenv(
                "OPENROUTER_FREE_MODEL_FILTER",
                "only" if os.getenv("OPENROUTER_FREE_ONLY", "").lower() == "true" else "all",
            ),
            description=(
                "Filter the catalog by free-tier status (':free' suffix or zero "
                "prompt+completion pricing). 'all' = no filter (default), "
                "'only' = keep just free models, 'exclude' = hide free models. "
                "Replaces the legacy FREE_ONLY valve (FREE_ONLY=true → 'only')."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "all", "label": "All"},
                        {"value": "only", "label": "Only free"},
                        {"value": "exclude", "label": "Exclude free"},
                    ],
                }
            },
        )
        TOOL_CALLING_FILTER: str = Field(
            default=os.getenv("OPENROUTER_TOOL_CALLING_FILTER", "all"),
            description=(
                "Filter the catalog by tool-calling capability "
                "(`supported_parameters` containing `tools` or `tool_choice`). "
                "'all' (default) keeps everything, 'only' restricts to tool-capable "
                "models, 'exclude' hides them."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "all", "label": "All"},
                        {"value": "only", "label": "Only tool-capable"},
                        {"value": "exclude", "label": "Exclude tool-capable"},
                    ],
                }
            },
        )
        MODEL_VARIANTS: str = Field(
            default=os.getenv("OPENROUTER_MODEL_VARIANTS", ""),
            description=(
                "Comma-separated `base_id:variant` entries to expose as virtual "
                "models that inherit the base model's metadata (name, icon). "
                "Example: 'openai/gpt-4o:nitro, anthropic/claude-3.5-sonnet:thinking'. "
                "Recognised tags: free, thinking, online, nitro, exacto, extended. "
                "OpenRouter routes the suffixed ID specially "
                "(see https://openrouter.ai/docs/features/preset-routing)."
            ),
        )
        MODEL_CATEGORY: str = Field(
            default=os.getenv("OPENROUTER_MODEL_CATEGORY", ""),
            description=(
                "Server-side category filter for `/models` (passed as "
                "`?category=...`). Empty disables. Common values: "
                "programming, roleplay, marketing, marketing/seo, technology, "
                "science, translation, legal, finance, health, trivia, academia."
            ),
        )
        HIDE_DEPRECATED_MODELS: bool = Field(
            default=os.getenv("OPENROUTER_HIDE_DEPRECATED_MODELS", "false").lower()
            == "true",
            description=(
                "Hide models with a non-null `expiration_date`. When False "
                "(default), deprecated models stay visible but are tagged with "
                "a ⚠ prefix in the display name."
            ),
        )
        OUTPUT_MODALITIES: str = Field(
            default=os.getenv("OPENROUTER_OUTPUT_MODALITIES", "all"),
            description=(
                "Output modalities to fetch from OpenRouter's /models endpoint. "
                "'all' (default) lists every model — chat, TTS, audio, image, and embeddings. "
                "Use 'text' for chat-only, or a comma list e.g. 'text,audio'. "
                "Valid tokens: text, image, audio, embeddings, all."
            ),
        )
        PROVIDER_SORT: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_SORT", ""),
            description="Provider sort order: empty=default, price, throughput, latency",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "", "label": "Default"},
                        {"value": "price", "label": "Price"},
                        {"value": "throughput", "label": "Throughput"},
                        {"value": "latency", "label": "Latency"},
                    ],
                }
            },
        )
        PROVIDER_ORDER: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_ORDER", ""),
            description="Preferred providers, comma-separated (e.g. anthropic,openai)",
        )
        PROVIDER_IGNORE: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_IGNORE", ""),
            description="Excluded providers, comma-separated",
        )
        PROVIDER_ONLY: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_ONLY", ""),
            description=(
                "Allowlist of provider slugs to use (comma-separated). When "
                "set, OpenRouter routes only to these providers. Merged with "
                "your account-wide allowlist."
            ),
        )
        PROVIDER_QUANTIZATIONS: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_QUANTIZATIONS", ""),
            description=(
                "Comma-separated quantization filters (e.g. 'bf16,fp8'). Only "
                "endpoints serving the model at one of these precisions will "
                "be used. Common values: bf16, fp16, fp8, int8, int4."
            ),
        )
        PROVIDER_ALLOW_FALLBACKS: bool = Field(
            default=os.getenv("OPENROUTER_PROVIDER_ALLOW_FALLBACKS", "true").lower()
            == "true",
            description=(
                "When True (default), OpenRouter falls back to alternate "
                "providers if the primary one (or those in PROVIDER_ORDER) is "
                "unavailable. Set False to fail fast on the primary provider."
            ),
        )
        PROVIDER_MAX_PRICE_PROMPT: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_MAX_PRICE_PROMPT", ""),
            description=(
                "Maximum prompt price (USD per 1M tokens) you accept for this "
                "request, e.g. '3.0'. Empty disables. Sent as "
                "`provider.max_price.prompt`."
            ),
        )
        PROVIDER_MAX_PRICE_COMPLETION: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_MAX_PRICE_COMPLETION", ""),
            description=(
                "Maximum completion price (USD per 1M tokens) you accept for "
                "this request, e.g. '15.0'. Empty disables. Sent as "
                "`provider.max_price.completion`."
            ),
        )
        SERVICE_TIER: str = Field(
            default=os.getenv("OPENROUTER_SERVICE_TIER", ""),
            description=(
                "Service tier hint forwarded to compatible providers. "
                "OpenRouter supports 'flex' (cheaper, slower) and 'priority' "
                "(faster, costlier); empty leaves the choice to the provider."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "", "label": "Default"},
                        {"value": "flex", "label": "Flex (cheaper, slower)"},
                        {"value": "priority", "label": "Priority (faster)"},
                    ],
                }
            },
        )
        REQUIRE_PARAMETERS: bool = Field(
            default=os.getenv("OPENROUTER_REQUIRE_PARAMETERS", "false").lower()
            == "true",
            description="Restrict to providers supporting all parameters in the request (e.g., temperature, top_p). May reduce available providers",
        )
        DATA_COLLECTION: str = Field(
            default=os.getenv("OPENROUTER_DATA_COLLECTION", "allow"),
            description="Whether AI providers can use your prompts for training. 'deny' opts out of data collection",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "allow", "label": "Allow"},
                        {"value": "deny", "label": "Deny"},
                    ],
                }
            },
        )
        FALLBACK_MODELS: str = Field(
            default=os.getenv("OPENROUTER_FALLBACK_MODELS", ""),
            description="Fallback model IDs, comma-separated (e.g. openai/gpt-4o,anthropic/claude-3.5-sonnet)",
        )
        ENABLE_MIDDLE_OUT: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_MIDDLE_OUT", "false").lower()
            == "true",
            description="Automatically compress long conversations that exceed the model's context window by summarizing middle messages",
        )
        ENABLE_WEB_SEARCH: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_WEB_SEARCH", "false").lower()
            == "true",
            description=(
                "Attach OpenRouter's `web` plugin to every request so the "
                "model can ground answers in fresh web results. Stacks with "
                "the `:online` variant tag (provider-side) — pick one. "
                "OpenRouter charges per search call separately from tokens."
            ),
        )
        WEB_SEARCH_MAX_RESULTS: int = Field(
            default=int(os.getenv("OPENROUTER_WEB_SEARCH_MAX_RESULTS", "5")),
            ge=1,
            le=20,
            description="Maximum number of search results returned to the model when ENABLE_WEB_SEARCH is on.",
        )
        WEB_SEARCH_PROMPT: str = Field(
            default=os.getenv("OPENROUTER_WEB_SEARCH_PROMPT", ""),
            description=(
                "Optional custom search prompt forwarded to the search engine "
                "(`plugins[].search_prompt`). Empty uses OpenRouter's default."
            ),
        )
        WEB_SEARCH_INCLUDE_DOMAINS: str = Field(
            default=os.getenv("OPENROUTER_WEB_SEARCH_INCLUDE_DOMAINS", ""),
            description=(
                "Comma-separated domain allowlist for web search. Wildcards "
                "and path filters supported (e.g. '*.substack.com, "
                "openai.com/blog')."
            ),
        )
        WEB_SEARCH_EXCLUDE_DOMAINS: str = Field(
            default=os.getenv("OPENROUTER_WEB_SEARCH_EXCLUDE_DOMAINS", ""),
            description="Comma-separated domain denylist for web search (same format as include list).",
        )
        ENABLE_CACHE_CONTROL: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_CACHE_CONTROL", "false").lower()
            == "true",
            description="Enable prompt caching for Anthropic models (reduces cost on repeated long prompts). No effect on other providers",
        )
        ANTHROPIC_PROMPT_CACHE_TTL: str = Field(
            default=os.getenv("OPENROUTER_ANTHROPIC_PROMPT_CACHE_TTL", "5m"),
            description=(
                "TTL for the Anthropic ephemeral cache breakpoint when "
                "ENABLE_CACHE_CONTROL is on. '5m' (default) keeps the standard "
                "short-lived cache; '1h' costs more on cache writes but persists "
                "longer between turns."
            ),
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "5m", "label": "5 minutes"},
                        {"value": "1h", "label": "1 hour"},
                    ],
                }
            },
        )
        ZDR_ENFORCE: bool = Field(
            default=os.getenv("OPENROUTER_ZDR_ENFORCE", "false").lower() == "true",
            description=(
                "When True, every chat request includes `provider.zdr=true` so "
                "OpenRouter rejects the call unless a Zero Data Retention "
                "endpoint is available for the chosen model."
            ),
        )
        ZDR_MODELS_ONLY: bool = Field(
            default=os.getenv("OPENROUTER_ZDR_MODELS_ONLY", "false").lower() == "true",
            description=(
                "Catalog-side filter: when True, fetch OpenRouter's "
                "`/endpoints/zdr` list and hide models without any ZDR-capable "
                "endpoint. Pairs well with ZDR_ENFORCE for end-to-end privacy "
                "guarantees."
            ),
        )
        HTTP_REFERER_OVERRIDE: str = Field(
            default=os.getenv("OPENROUTER_HTTP_REFERER", ""),
            description=(
                "Override the `HTTP-Referer` header sent to OpenRouter for app "
                "attribution (must be a full URL with scheme). Empty falls back "
                "to WEBUI_URL or http://localhost:3000."
            ),
        )
        SYNC_PROVIDER_ICONS: bool = Field(
            default=os.getenv("OPENROUTER_SYNC_ICONS", "true").lower() == "true",
            description="Automatically sync provider icons into Open WebUI's model database so they appear in the UI",
        )
        USE_GSTATIC_FAVICONS: bool = Field(
            default=os.getenv("OPENROUTER_USE_GSTATIC_FAVICONS", "false").lower() == "true",
            description="Allow registry-discovered Google gstatic favicons for providers without an OpenRouter-hosted icon. Off by default: when enabled, the browser fetches these from t0.gstatic.com on every model render, leaking the provider domain to Google",
        )
        REQUEST_TIMEOUT: int = Field(
            default=int(os.getenv("OPENROUTER_REQUEST_TIMEOUT", "90")),
            gt=0,
            description="API request timeout in seconds",
        )
        MAX_RETRIES: int = Field(
            default=2, ge=0, description="Auto-retries on transient errors (with exponential backoff)"
        )
        SHOW_COST_INFO: bool = Field(
            default=False,
            description="Append token usage and cost to each response",
        )
        SHOW_GENERATION_ID: bool = Field(
            default=os.getenv("OPENROUTER_SHOW_GENERATION_ID", "false").lower()
            == "true",
            description=(
                "Append the OpenRouter generation ID to each response so it "
                "can be looked up later via `GET /generation?id=...` for "
                "audit trails and per-request usage details."
            ),
        )
        COST_CURRENCY: str = Field(
            default=os.getenv("OPENROUTER_COST_CURRENCY", "USD"),
            description="Currency label shown in cost display (display only; OpenRouter bills in USD)",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "USD", "label": "USD ($)"},
                        {"value": "EUR", "label": "EUR (€)"},
                        {"value": "GBP", "label": "GBP (£)"},
                        {"value": "JPY", "label": "JPY (¥)"},
                        {"value": "CAD", "label": "CAD (CA$)"},
                        {"value": "AUD", "label": "AUD (A$)"},
                    ],
                }
            },
        )

        RESPONSE_FORMAT: str = Field(
            default=os.getenv("OPENROUTER_RESPONSE_FORMAT", ""),
            description="Force output format when the request doesn't set one: '' (off), 'json_object' (any valid JSON), or 'json_schema' (uses RESPONSE_SCHEMA). The body's own response_format always wins.",
            json_schema_extra={"input": {"type": "select", "options": [
                {"value": "", "label": "Off"},
                {"value": "json_object", "label": "JSON object"},
                {"value": "json_schema", "label": "JSON schema (use RESPONSE_SCHEMA)"},
            ]}},
        )
        RESPONSE_SCHEMA: str = Field(
            default=os.getenv("OPENROUTER_RESPONSE_SCHEMA", ""),
            description="JSON Schema (as a JSON string) used when RESPONSE_FORMAT='json_schema'. Invalid JSON is logged and skipped. The body's own response_format always wins.",
        )
        TOOL_CHOICE: str = Field(
            default=os.getenv("OPENROUTER_TOOL_CHOICE", ""),
            description="Default tool_choice when the request doesn't set one: '' (auto/model decides), 'none', 'auto', or 'required'. The request body's own tool_choice always wins.",
            json_schema_extra={"input": {"type": "select", "options": [
                {"value": "", "label": "Default (auto)"},
                {"value": "none", "label": "None"},
                {"value": "auto", "label": "Auto"},
                {"value": "required", "label": "Required"},
            ]}},
        )

        MAX_TOOL_ITERATIONS: int = Field(
            default=int(os.getenv("OPENROUTER_MAX_TOOL_ITERATIONS", "5")),
            ge=1,
            description=(
                "Max native tool-call rounds per request before stopping. Each "
                "round = one model response containing tool_calls that the pipe "
                "executes and feeds back. Caps runaway tool loops."
            ),
        )
        SHOW_REMAINING_CREDIT: bool = Field(
            default=os.getenv("OPENROUTER_SHOW_REMAINING_CREDIT", "false").lower() == "true",
            description=(
                "Append your remaining OpenRouter credit to each response "
                "(after the cost line). Makes one extra cached GET /credits call "
                "per ~60s. Independent of Show Cost Info."
            ),
        )

        @field_validator("OPENROUTER_BASE_URL")
        @classmethod
        def _validate_base_url(cls, v: str) -> str:
            v = v.strip()
            if not v.startswith(("https://", "http://")):
                raise ValueError("Base URL must start with https:// or http://")
            return v

        @field_validator("OPENROUTER_API_KEY")
        @classmethod
        def _encrypt_api_key(cls, v: str) -> str:
            return EncryptedStr.encrypt(v or "")

    class UserValves(BaseModel):
        """Per-user overrides. Each field defaults to None = inherit the admin
        Valves value. Only chat-path settings are exposed; catalog/display
        settings are admin-global because the model list has no user context.
        """

        OPENROUTER_API_KEY: Optional[str] = Field(
            default=None,
            description="Your personal OpenRouter API key. Leave blank to use the admin key.",
            json_schema_extra={"input": {"type": "password"}},
        )
        INCLUDE_REASONING: Optional[bool] = None
        REASONING_EFFORT: Optional[str] = None
        REASONING_SUMMARY_MODE: Optional[str] = None
        REASONING_MAX_TOKENS: Optional[int] = Field(default=None, ge=0)
        ENABLE_ANTHROPIC_INTERLEAVED_THINKING: Optional[bool] = None
        SERVICE_TIER: Optional[str] = None
        PROVIDER_SORT: Optional[str] = None
        PROVIDER_ORDER: Optional[str] = None
        PROVIDER_IGNORE: Optional[str] = None
        PROVIDER_ONLY: Optional[str] = None
        PROVIDER_QUANTIZATIONS: Optional[str] = None
        PROVIDER_ALLOW_FALLBACKS: Optional[bool] = None
        PROVIDER_MAX_PRICE_PROMPT: Optional[str] = None
        PROVIDER_MAX_PRICE_COMPLETION: Optional[str] = None
        REQUIRE_PARAMETERS: Optional[bool] = None
        DATA_COLLECTION: Optional[str] = None
        ZDR_ENFORCE: Optional[bool] = None
        FALLBACK_MODELS: Optional[str] = None
        ENABLE_MIDDLE_OUT: Optional[bool] = None
        ENABLE_WEB_SEARCH: Optional[bool] = None
        WEB_SEARCH_MAX_RESULTS: Optional[int] = Field(default=None, ge=1, le=20)
        WEB_SEARCH_PROMPT: Optional[str] = None
        WEB_SEARCH_INCLUDE_DOMAINS: Optional[str] = None
        WEB_SEARCH_EXCLUDE_DOMAINS: Optional[str] = None
        ENABLE_CACHE_CONTROL: Optional[bool] = None
        ANTHROPIC_PROMPT_CACHE_TTL: Optional[str] = None
        HTTP_REFERER_OVERRIDE: Optional[str] = None
        REQUEST_TIMEOUT: Optional[int] = Field(default=None, gt=0)
        MAX_RETRIES: Optional[int] = Field(default=None, ge=0)
        SHOW_COST_INFO: Optional[bool] = None
        SHOW_GENERATION_ID: Optional[bool] = None
        COST_CURRENCY: Optional[str] = None
        RESPONSE_FORMAT: Optional[str] = None
        RESPONSE_SCHEMA: Optional[str] = None
        TOOL_CHOICE: Optional[str] = None
        MAX_TOOL_ITERATIONS: Optional[int] = Field(default=None, ge=1)
        SHOW_REMAINING_CREDIT: Optional[bool] = None

        @field_validator("OPENROUTER_API_KEY")
        @classmethod
        def _encrypt_user_api_key(cls, v):
            return EncryptedStr.encrypt(v) if v else v

    def __init__(self) -> None:
        self.type = "manifold"
        self.valves = self.Valves()
        self._session = requests.Session()
        # Cache env vars that don't change at runtime
        _raw_referer = os.getenv("WEBUI_URL", "http://localhost:3000")
        self._referer = re.sub(r"[\r\n\x00]", "", _raw_referer) or "http://localhost:3000"
        _raw_title = os.getenv("WEBUI_NAME", "OpenWebUI")
        self._title = re.sub(r"[\r\n\x00]", "", _raw_title) or "OpenWebUI"
        # Model list cache
        self._models_cache: Optional[List[dict]] = None
        self._models_cache_ts: float = 0.0
        self._models_cache_key: str = ""
        # Track which model IDs already have icons synced (avoids repeated DB writes)
        self._icons_synced: set = set()
        # Lazy-loaded mirror of OpenRouter's provider registry (slug → icon URL).
        # Refreshed every _PROVIDER_REGISTRY_TTL seconds; None = not yet fetched.
        self._provider_registry: Optional[dict] = None
        self._provider_registry_ts: float = 0.0
        # Lazy-loaded set of model IDs that have at least one ZDR endpoint.
        # None = not attempted; frozenset() = attempted but failed/empty.
        self._zdr_model_ids: Optional[frozenset] = None
        self._zdr_model_ids_ts: float = 0.0
        # Per-key remaining-credit cache: {key_hash: (remaining_float, ts)}.
        # Keyed by the decrypted key's hash because per-user keys have per-key balances.
        self._credit_cache: dict = {}
        # Cache function_id once: OWUI sets __module__ to "function_{id}" at load time
        _fm = type(self).__module__ or ""
        self._function_id: Optional[str] = (
            _fm[len("function_"):] if _fm.startswith("function_") else None
        )
        if not self.valves.OPENROUTER_API_KEY:
            print("[OpenRouter Pipe] Warning: OPENROUTER_API_KEY not set")

    @property
    def _base(self) -> str:
        """Return the sanitized base URL (no trailing slash)."""
        return self.valves.OPENROUTER_BASE_URL.rstrip("/")

    @property
    def models_url(self) -> str:
        """Return the full URL for the models endpoint."""
        return f"{self._base}{_API_PATH_MODELS}"

    @property
    def chat_url(self) -> str:
        """Return the full URL for the chat completions endpoint."""
        return f"{self._base}{_API_PATH_CHAT}"

    def _build_cache_key(self) -> str:
        """Build a fingerprint of the valves that affect the model list.

        The API key is hashed (not embedded raw) so it doesn't sit in plaintext
        in long-lived strings that may end up in logs or memory dumps.
        """
        _resolved_key = EncryptedStr.decrypt(self.valves.OPENROUTER_API_KEY or "")
        api_key_hash = (
            hashlib.sha256(_resolved_key.encode("utf-8")).hexdigest()[:16]
            if _resolved_key
            else ""
        )
        return (
            f"{api_key_hash}|{self.valves.FREE_MODEL_FILTER}|"
            f"{self.valves.MODEL_PROVIDERS}|{self.valves.INVERT_PROVIDER_LIST}|"
            f"{self.valves.MODEL_PREFIX}|{self.valves.OUTPUT_MODALITIES}|"
            f"{self.valves.TOOL_CALLING_FILTER}|{self.valves.ZDR_MODELS_ONLY}|"
            f"{self.valves.MODEL_VARIANTS}|{self.valves.MODEL_CATEGORY}|"
            f"{self.valves.HIDE_DEPRECATED_MODELS}"
        )

    def _models_cache_valid(self) -> bool:
        """Check if the cached model list is still valid."""
        if not self._models_cache:
            return False
        if self._build_cache_key() != self._models_cache_key:
            return False
        return (time.monotonic() - self._models_cache_ts) < _MODELS_CACHE_TTL

    def pipes(self) -> List[dict]:
        """Fetch and return the list of available OpenRouter models."""
        if not self.valves.OPENROUTER_API_KEY:
            return [{"id": "error", "name": "OpenRouter API key not configured. Set it in Settings."}]

        # Return cached models if still valid
        if self._models_cache_valid() and self._models_cache is not None:
            # Continue syncing icons on cache hits until all models are confirmed.
            # This resolves the race condition where OWUI registers models (and may
            # overwrite icons) only after the first pipes() call returns.
            if self.valves.SYNC_PROVIDER_ICONS and len(self._icons_synced) < len(self._models_cache):
                self._sync_model_icons(self._models_cache)
            return self._models_cache

        headers = self._build_headers(include_content_type=False, valves=self.valves)
        modalities = (self.valves.OUTPUT_MODALITIES or "all").strip() or "all"
        params: dict = {"output_modalities": modalities}
        category = (self.valves.MODEL_CATEGORY or "").strip()
        if category:
            params["category"] = category
        response = None
        try:
            response = self._session.get(
                self.models_url,
                headers=headers,
                params=params,
                timeout=self.valves.REQUEST_TIMEOUT,
                allow_redirects=False,
            )
            # Detect auth errors from the models endpoint itself
            # 502 from Clerk usually means the key format is invalid
            if response.status_code in (401, 403, 502):
                detail = ""
                try:
                    detail = response.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                msg = f"Invalid API key (HTTP {response.status_code})"
                if detail:
                    msg += f": {detail}"
                msg += ". Check your OPENROUTER_API_KEY in valve settings."
                return [{"id": "error", "name": msg}]
            response.raise_for_status()
            data = response.json().get("data", [])
        except requests.exceptions.Timeout:
            return [{"id": "error", "name": "Timeout fetching models. Try again or increase REQUEST_TIMEOUT."}]
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None:
                msg = f"HTTP {exc.response.status_code} fetching models"
                try:
                    err = exc.response.json().get("error", {})
                    detail = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    if detail:
                        msg += f": {detail}"
                except Exception:
                    pass
            else:
                msg = "HTTP error fetching models (no response)"
            print(f"[OpenRouter Pipe] {msg}")
            return [{"id": "error", "name": msg}]
        except Exception as exc:
            print(f"[OpenRouter Pipe] Model fetch error: {exc}")
            traceback.print_exc()
            return [{"id": "error", "name": f"Unexpected error: {exc}"}]
        finally:
            if response is not None:
                response.close()

        provider_filter = self._parse_provider_filter()
        prefix = self.valves.MODEL_PREFIX or ""
        free_filter = (self.valves.FREE_MODEL_FILTER or "all").strip().lower()
        tool_filter = (self.valves.TOOL_CALLING_FILTER or "all").strip().lower()
        zdr_only = self.valves.ZDR_MODELS_ONLY
        zdr_capable_ids: Optional[frozenset] = (
            self._load_zdr_model_ids() if zdr_only else None
        )
        models: List[dict] = []

        for model in data:
            model_id = model.get("id")
            if not model_id:
                continue

            if free_filter in ("only", "exclude"):
                is_free = ":free" in model_id.lower()
                if not is_free:
                    pricing = model.get("pricing") or {}
                    try:
                        is_free = (
                            float(pricing.get("prompt", 1)) == 0
                            and float(pricing.get("completion", 1)) == 0
                        )
                    except (ValueError, TypeError):
                        is_free = False
                if free_filter == "only" and not is_free:
                    continue
                if free_filter == "exclude" and is_free:
                    continue

            if tool_filter in ("only", "exclude"):
                supported = model.get("supported_parameters") or []
                tool_capable = any(
                    p in supported for p in ("tools", "tool_choice")
                )
                if tool_filter == "only" and not tool_capable:
                    continue
                if tool_filter == "exclude" and tool_capable:
                    continue

            if zdr_only and zdr_capable_ids is not None:
                # OpenRouter's /endpoints/zdr returns base IDs (no '~' alias prefix
                # and no ':variant' suffix). Strip both before comparing.
                base_id = model_id.lstrip("~").split(":", 1)[0]
                if base_id not in zdr_capable_ids:
                    continue

            # Deprecation handling: a non-null `expiration_date` means
            # OpenRouter has scheduled the model for removal. Hide the entry
            # entirely when the operator opts in; otherwise keep it but tag
            # the display name so users notice before relying on it.
            expiration = model.get("expiration_date")
            is_deprecated = expiration is not None and str(expiration).strip() != ""
            if is_deprecated and self.valves.HIDE_DEPRECATED_MODELS:
                continue

            # Split model_id once for provider extraction.
            # Strip leading '~' (OpenRouter "latest" aliases like ~anthropic/claude-haiku-latest)
            # so they match the same provider filter as their base provider.
            parts = model_id.split("/", 1)
            provider_key = parts[0].lstrip("~").lower() if len(parts) > 1 else "openrouter"

            if provider_filter:
                keep = (provider_key in provider_filter) ^ self.valves.INVERT_PROVIDER_LIST
                if not keep:
                    continue

            model_name = model.get("name", model_id)
            if is_deprecated:
                model_name = f"⚠ {model_name} (deprecated)"

            model_dict = {
                "id": model_id,
                "name": f"{prefix}{model_name}",
            }

            models.append(model_dict)

        # Append virtual variant entries (e.g. openai/gpt-4o:nitro). Variants
        # inherit the base model's display name; only the suffix and a tag
        # label change — the icon-sync step writes the same provider icon.
        models = self._expand_variant_models(models, prefix)

        if not models:
            if free_filter == "only":
                error_text = "No free models available. Set FREE_MODEL_FILTER to 'all' to see paid models."
            elif tool_filter == "only":
                error_text = "No tool-capable models available. Set TOOL_CALLING_FILTER to 'all' to broaden the catalog."
            elif zdr_only:
                error_text = "No ZDR-capable models available. Disable ZDR_MODELS_ONLY or check your OpenRouter privacy settings."
            elif provider_filter:
                providers_str = ", ".join(sorted(provider_filter))
                error_text = f"No models match providers: {providers_str}. Check MODEL_PROVIDERS setting."
            else:
                error_text = "No models found. Check your OpenRouter account and API key."
            return [{"id": "error", "name": error_text}]

        # Store in cache
        self._models_cache = models
        self._models_cache_ts = time.monotonic()
        self._models_cache_key = self._build_cache_key()
        # Reset synced-set on every model cache refresh so _sync_model_icons
        # re-checks all models. OWUI upserts models with the default data: icon
        # after every pipes() call; clearing here ensures any overwritten icon
        # is restored on the next sync pass.
        self._icons_synced.clear()

        # Sync provider icons into Open WebUI's Models database
        if self.valves.SYNC_PROVIDER_ICONS:
            self._sync_model_icons(models)

        return models

    @staticmethod
    def _clean_model_id(model_id: str) -> str:
        """Strip the manifold prefix from a model ID.

        OpenRouter model IDs use the format ``provider/model`` (e.g.
        ``anthropic/claude-3.5-sonnet``). The manifold prefix added by Open
        WebUI is a function id without ``/`` (e.g. ``openrouter_pipe``). We
        only strip when the text before the first ``.`` contains no ``/`` —
        otherwise the dot is part of the model version (e.g.
        ``claude-3.5-sonnet``) and must be preserved.
        """
        if "." not in model_id:
            return model_id
        prefix, rest = model_id.split(".", 1)
        if "/" in prefix:
            return model_id
        return rest

    def _effective_valves(self, __user__):
        """Return a per-request copy of admin valves with user overrides applied.

        Never mutates self.valves (shared across users/requests). A user field
        of None means "inherit the admin value".
        """
        eff = self.valves.model_copy()
        user = __user__ or {}
        uv = user.get("valves") if isinstance(user, dict) else None
        if uv is None:
            return eff
        data = uv.model_dump() if hasattr(uv, "model_dump") else dict(uv)
        for key, val in data.items():
            if val is not None and hasattr(eff, key):
                setattr(eff, key, val)
        return eff

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __tools__: Optional[dict] = None,
        __request__=None,
        __metadata__: Optional[dict] = None,
    ) -> Union[str, Generator[str, None, None], AsyncGenerator[str, None]]:
        """Route a chat completion request to OpenRouter (stream or non-stream).

        Returns an async generator for streaming (allows proper status cleanup),
        or a plain string for non-streaming responses.
        """
        eff = self._effective_valves(__user__)
        if not eff.OPENROUTER_API_KEY:
            return "OpenRouter Error: OPENROUTER_API_KEY not configured. Set it in Settings → Connections."

        model_id = self._clean_model_id(body.get("model", ""))

        # Guard against selecting the error pseudo-model
        if model_id == "error":
            return "OpenRouter Error: No valid model selected. Check the model list for configuration issues."

        # Validate messages exist
        if not body.get("messages"):
            return "OpenRouter Error: No messages provided."

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Querying {model_id or 'OpenRouter'}...",
                        "done": False,
                    },
                }
            )

        payload = self._prepare_payload(body, eff)
        headers = self._build_headers(model_id=payload.get("model"), valves=eff)
        stream = body.get("stream", False)

        tools_payload = self._build_tools_payload(__tools__)
        if tools_payload:
            payload["tools"] = tools_payload

        if tools_payload and not stream:
            result = await self._run_tools_nonstream(headers, payload, eff, __tools__, __event_emitter__, __request__, __user__, __metadata__)
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "", "done": True}})
            return result

        if stream and tools_payload:
            agen = self._run_tools_stream(headers, payload, eff, __tools__, __event_emitter__)
            if __event_emitter__:
                async def _wrap_tool_stream():
                    try:
                        async for piece in agen:
                            yield piece
                    finally:
                        await __event_emitter__({"type": "status", "data": {"description": "", "done": True}})
                return _wrap_tool_stream()
            return agen

        if stream:
            gen = self._stream_response(headers, payload, eff)
            it = iter(gen)

            async def _wrap_stream():
                try:
                    while True:
                        chunk = await asyncio.to_thread(next, it, _STREAM_DONE)
                        if chunk is _STREAM_DONE:
                            break
                        yield chunk
                finally:
                    if __event_emitter__:
                        await __event_emitter__({"type": "status", "data": {"description": "", "done": True}})
            return _wrap_stream()

        result = await self._non_stream_with_events(headers, payload, eff, __event_emitter__, __request__, __user__, __metadata__)

        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "", "done": True}}
            )

        return result

    def _sync_model_icons(self, models: List[dict]) -> None:
        """Write provider icons into Open WebUI's Models DB.

        Open WebUI serves model icons from its database, not from the dicts
        returned by ``pipes()``.  OWUI prefixes every pipe model ID with
        ``{function_id}.`` (e.g. ``openrouter_pipe.openai/gpt-4o``) and the
        frontend requests icons using that prefixed ID.

        Called both on cache miss and on subsequent cache hits (until all
        models are confirmed synced).  The cache-hit path is needed because
        OWUI registers models *after* ``pipes()`` returns, potentially
        overwriting any early insert with its own default icon; the second
        call finds the models already in DB and updates them correctly.

        User-set custom icons (any URL that is not a ``data:`` URL and does not
        start with ``https://openrouter.ai/images/models/``) are preserved.
        This is a best-effort operation — failures are silently logged.
        """
        try:
            from open_webui.models.models import (
                ModelForm,
                ModelMeta,
                ModelParams,
                Models,
            )
        except ImportError:
            # Running outside Open WebUI (e.g. standalone tests) — skip silently
            return

        # function_id was resolved once in __init__ from type(self).__module__
        if not self._function_id:
            return
        function_id = self._function_id

        for model in models:
            model_id = model.get("id", "")
            if not model_id or model_id == "error":
                continue

            # Skip if already synced this session
            if model_id in self._icons_synced:
                continue

            # Determine provider icon. Strip '~' so latest aliases (e.g.
            # ~anthropic/claude-haiku-latest) resolve to the correct icon.
            parts = model_id.split("/", 1)
            provider_key = parts[0].lstrip("~").lower() if len(parts) > 1 else ""
            icon_url = self._get_provider_icon(provider_key)
            # Build the prefixed ID that Open WebUI uses in the frontend
            db_model_id = f"{function_id}.{model_id}"

            if not icon_url:
                # No icon for this provider. If the DB holds one of our old
                # broken /images/models/ URLs, clear it so OWUI shows its
                # default icon rather than a broken image.
                try:
                    existing = Models.get_model_by_id(db_model_id)
                    if existing and hasattr(existing, "meta") and existing.meta:
                        stale = getattr(existing.meta, "profile_image_url", "") or ""
                        if stale.startswith("https://openrouter.ai/images/models/"):
                            existing_params = ModelParams()
                            if hasattr(existing, "params") and existing.params:
                                existing_params = existing.params
                            Models.update_model_by_id(
                                db_model_id,
                                ModelForm(
                                    id=db_model_id,
                                    name=(
                                        existing.name
                                        if hasattr(existing, "name")
                                        else model.get("name", model_id)
                                    ),
                                    meta=ModelMeta(profile_image_url=""),
                                    params=existing_params,
                                ),
                            )
                except Exception:
                    pass
                self._icons_synced.add(model_id)
                continue

            try:
                existing = Models.get_model_by_id(db_model_id)
                if existing:
                    existing_icon = ""
                    if hasattr(existing, "meta") and existing.meta:
                        existing_icon = (
                            getattr(existing.meta, "profile_image_url", "") or ""
                        )

                    # Skip if icon is already the correct provider URL
                    if existing_icon == icon_url:
                        self._icons_synced.add(model_id)
                        continue

                    # Skip if icon was set by the user (not by OWUI or our sync).
                    # data: URLs are OWUI defaults; openrouter.ai URLs are ours.
                    if existing_icon and not _is_owui_managed_icon(existing_icon):
                        self._icons_synced.add(model_id)
                        continue

                    # Proceed: icon is empty, an OWUI default, or one of our URLs
                    # Update existing model with icon, preserving user-set params
                    existing_params = ModelParams()
                    if hasattr(existing, "params") and existing.params:
                        existing_params = existing.params
                    Models.update_model_by_id(
                        db_model_id,
                        ModelForm(
                            id=db_model_id,
                            name=(
                                existing.name
                                if hasattr(existing, "name")
                                else model.get("name", model_id)
                            ),
                            meta=ModelMeta(profile_image_url=icon_url),
                            params=existing_params,
                        ),
                    )
                else:
                    # Model not yet in DB — best-effort early insert.
                    # OWUI will register models after pipes() returns and may
                    # overwrite this record, so do NOT mark as synced here.
                    # The next cache-hit call to _sync_model_icons will find the
                    # model in DB and update it correctly.
                    try:
                        Models.insert_new_model(
                            ModelForm(
                                id=db_model_id,
                                name=model.get("name", model_id),
                                meta=ModelMeta(profile_image_url=icon_url),
                                params=ModelParams(),
                            ),
                            user_id="pipe:openrouter",
                        )
                    except Exception:
                        pass
                    continue  # do not add to _icons_synced yet

                self._icons_synced.add(model_id)
            except Exception as exc:
                # Best-effort — don't let icon sync break model listing
                # Do NOT add to _icons_synced: allow retry on next call
                print(f"[OpenRouter Pipe] Icon sync failed for {db_model_id}: {exc}")

    @staticmethod
    def get_provider_icon(provider: str) -> Optional[str]:
        """Return hardcoded icon URL for the given provider (fast path only).

        Does not consult the dynamic OpenRouter provider registry — for that,
        use ``_get_provider_icon`` on a Pipe instance.
        """
        return _PROVIDER_ICONS.get(provider.lower())

    def _load_provider_registry(self) -> dict:
        """Load OpenRouter's provider registry, refreshing every hour.

        Returns ``{slug: icon_url}`` (with each slug also indexed under its
        hyphen-stripped variant so e.g. ``x-ai`` resolves to the registry's
        ``xai`` entry).

        On a successful 200 response the full ``_PROVIDER_REGISTRY_TTL``
        applies.  On failure (non-200 or network error) the *existing* cached
        registry is preserved so previously-known icons are not lost; a
        shorter ``_PROVIDER_REGISTRY_FAIL_TTL`` back-off is applied so we
        retry sooner without hammering the API.  If no registry has ever been
        fetched successfully an empty dict is returned and the caller falls
        back to ``_PROVIDER_ICONS``.
        """
        now = time.monotonic()
        if (
            self._provider_registry is not None
            and (now - self._provider_registry_ts) < _PROVIDER_REGISTRY_TTL
        ):
            return self._provider_registry

        registry: dict = {}
        success = False
        try:
            resp = self._session.get(
                _PROVIDER_REGISTRY_URL,
                timeout=min(self.valves.REQUEST_TIMEOUT, 15),
                allow_redirects=False,
            )
            try:
                if resp.status_code == 200:
                    data = resp.json().get("data") or []
                    for entry in data:
                        slug = (entry or {}).get("slug") or ""
                        icon = ((entry or {}).get("icon") or {}).get("url") or ""
                        if not slug or not icon:
                            continue
                        if icon.startswith("/"):
                            icon = f"https://openrouter.ai{icon}"
                        if not _is_safe_url(icon):
                            continue
                        registry[slug] = icon
                        # Also index by hyphen-stripped slug — model-author IDs
                        # like ``x-ai`` map to provider slug ``xai``.
                        compact = slug.replace("-", "")
                        if compact and compact != slug:
                            registry.setdefault(compact, icon)
                    success = True
                else:
                    print(
                        f"[OpenRouter Pipe] Provider registry returned HTTP "
                        f"{resp.status_code} — provider icons may be incomplete"
                    )
            finally:
                resp.close()
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Provider registry fetch failed: {exc}")

        if success:
            # Successful fetch — update the cached registry and start the full TTL.
            self._provider_registry = registry
            self._provider_registry_ts = now
        else:
            # Failed fetch (non-200 or network error): preserve any previously-good
            # registry so icons that were already known are not lost.  Apply a short
            # back-off so we retry in _PROVIDER_REGISTRY_FAIL_TTL seconds instead of
            # waiting the full hour.
            if self._provider_registry is None:
                self._provider_registry = {}
            self._provider_registry_ts = (
                now - _PROVIDER_REGISTRY_TTL + _PROVIDER_REGISTRY_FAIL_TTL
            )
        return self._provider_registry

    def _get_provider_icon(self, provider_key: str) -> Optional[str]:
        """Resolve a provider icon URL using the layered fallback chain.

        Order: registry exact match → registry hyphen-stripped →
        hardcoded ``_PROVIDER_ICONS``. The registry is authoritative because
        it always reflects OpenRouter's current CDN paths; the hardcoded dict
        is a reliable offline fallback when the registry is unavailable.
        Returns ``None`` if no source has it.
        """
        if not provider_key:
            return None
        key = provider_key.lower()
        registry = self._load_provider_registry()
        icon = registry.get(key) or registry.get(key.replace("-", ""))
        if icon:
            # gstatic favicons are fetched by the browser on every model render,
            # leaking the provider's domain to Google.  Privacy-conscious
            # deployments can disable them (default off) — fall back to the
            # hardcoded OpenRouter-hosted icon, else no icon (OWUI default).
            if icon.startswith("https://t0.gstatic.com/") and not self.valves.USE_GSTATIC_FAVICONS:
                return _PROVIDER_ICONS.get(key)
            return icon
        return _PROVIDER_ICONS.get(key)

    def _parse_provider_filter(self) -> Optional[set]:
        """Parse MODEL_PROVIDERS valve into a set of lowercase provider names."""
        val = (self.valves.MODEL_PROVIDERS or "").strip()
        if not val or val.upper() == "ALL":
            return None
        return {p.lower() for p in self._parse_csv(val)}

    @staticmethod
    def _parse_csv(value: str) -> List[str]:
        """Parse a comma-separated string into a list, skipping empty items."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _load_zdr_model_ids(self) -> frozenset:
        """Lazy-load OpenRouter's ZDR-capable model IDs and cache for the pipe lifetime.

        Returns the cached set on subsequent calls (including the empty-set
        sentinel returned on network failure, so we don't retry on every
        ``pipes()`` call). The endpoint returns a list of model IDs that have
        at least one Zero Data Retention provider endpoint.
        """
        if self._zdr_model_ids is not None and (
            time.monotonic() - self._zdr_model_ids_ts
        ) < _PROVIDER_REGISTRY_TTL:
            return self._zdr_model_ids

        ids: set = set()
        try:
            resp = self._session.get(
                f"{self._base}{_API_PATH_ZDR_ENDPOINTS}",
                headers=self._build_headers(include_content_type=False, valves=self.valves),
                timeout=min(self.valves.REQUEST_TIMEOUT, 30),
                allow_redirects=False,
            )
            try:
                if resp.status_code == 200:
                    payload = resp.json() or {}
                    raw = payload.get("data") or payload.get("models") or []
                    for entry in raw:
                        if isinstance(entry, str):
                            ids.add(entry)
                        elif isinstance(entry, dict):
                            mid = entry.get("id") or entry.get("model")
                            if isinstance(mid, str) and mid:
                                ids.add(mid)
            finally:
                resp.close()
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] ZDR endpoint fetch failed: {exc}")

        self._zdr_model_ids = frozenset(ids)
        self._zdr_model_ids_ts = time.monotonic()
        return self._zdr_model_ids

    def _parse_variant_specs(self) -> List[tuple]:
        """Parse MODEL_VARIANTS into ``(base_id, variant_tag)`` pairs.

        Recognised tags are listed in ``_RECOGNISED_VARIANT_TAGS`` and ensure
        we don't accidentally fabricate IDs OpenRouter wouldn't honour.
        Unknown tags are skipped with a console note.
        """
        raw = self.valves.MODEL_VARIANTS or ""
        out: List[tuple] = []
        for spec in self._parse_csv(raw):
            if ":" not in spec:
                print(f"[OpenRouter Pipe] Skipping malformed variant spec '{spec}' (expected base_id:variant_tag)")
                continue
            base_id, _, tag = spec.rpartition(":")
            base_id = base_id.strip()
            tag = tag.strip().lower()
            if not base_id or not tag:
                continue
            if tag not in _RECOGNISED_VARIANT_TAGS:
                print(
                    f"[OpenRouter Pipe] Skipping unknown variant tag ':{tag}' "
                    f"(supported: {', '.join(sorted(_RECOGNISED_VARIANT_TAGS))})"
                )
                continue
            out.append((base_id, tag))
        return out

    def _build_web_search_plugin(self, valves) -> Optional[dict]:
        """Assemble the OpenRouter `web` plugin spec from valve settings.

        Returns ``None`` when the feature is disabled. Output mirrors the
        WebSearchPlugin schema from the official SDK
        (id/enabled/max_results/search_prompt/include_domains/exclude_domains).
        """
        if not valves.ENABLE_WEB_SEARCH:
            return None
        plugin: dict = {"id": "web"}
        max_results = valves.WEB_SEARCH_MAX_RESULTS
        if max_results:
            plugin["max_results"] = int(max_results)
        prompt = (valves.WEB_SEARCH_PROMPT or "").strip()
        if prompt:
            plugin["search_prompt"] = prompt
        include = self._parse_csv(valves.WEB_SEARCH_INCLUDE_DOMAINS)
        if include:
            plugin["include_domains"] = include
        exclude = self._parse_csv(valves.WEB_SEARCH_EXCLUDE_DOMAINS)
        if exclude:
            plugin["exclude_domains"] = exclude
        return plugin

    def _expand_variant_models(self, models: List[dict], prefix: str) -> List[dict]:
        """Append virtual variant entries to the catalog.

        Each ``base_id:variant`` entry inherits the base model's display name
        (with the tag appended) and reuses the same provider icon — only the
        ID changes so OpenRouter routes the request via the variant suffix.
        Variants whose base model isn't in the catalog (filtered out, or
        unknown to OpenRouter) are silently skipped.
        """
        specs = self._parse_variant_specs()
        if not specs:
            return models

        # Strip the user-set prefix so we can reuse base names verbatim.
        by_id: dict = {}
        for entry in models:
            mid = entry.get("id")
            if isinstance(mid, str):
                by_id[mid] = entry

        seen_variant_ids = {entry.get("id") for entry in models}
        appended: List[dict] = []
        for base_id, tag in specs:
            base_entry = by_id.get(base_id)
            if base_entry is None:
                print(
                    f"[OpenRouter Pipe] Variant base not in catalog: "
                    f"{base_id} (skipping :{tag})"
                )
                continue
            variant_id = f"{base_id}:{tag}"
            if variant_id in seen_variant_ids:
                continue
            base_name = base_entry.get("name", base_id)
            # If the user set a prefix it's already in base_name; we only need
            # to suffix the tag label.
            tag_label = tag.capitalize()
            appended.append(
                {
                    "id": variant_id,
                    "name": f"{base_name} {tag_label}",
                }
            )
            seen_variant_ids.add(variant_id)

        return models + appended

    def _prepare_payload(self, body: dict, valves) -> dict:
        """Sanitize OWUI internals and inject provider routing, reasoning, and fallbacks."""
        payload = copy.deepcopy(body)

        # Strip Open WebUI internal keys
        for key in _OWUI_INTERNAL_KEYS:
            payload.pop(key, None)

        # Open WebUI sends 'user' as a dict; OpenRouter expects a string id.
        user_val = payload.get("user")
        if isinstance(user_val, dict):
            uid = user_val.get("id") or ""
            if uid:
                payload["user"] = str(uid)
            else:
                payload.pop("user", None)

        # Fix model ID (strip manifold prefix)
        model = payload.get("model")
        if model:
            payload["model"] = self._clean_model_id(model)

        # --- Reasoning ---
        if valves.INCLUDE_REASONING:
            payload["include_reasoning"] = True

        effort = valves.REASONING_EFFORT.strip().lower()
        summary = valves.REASONING_SUMMARY_MODE.strip().lower()
        reasoning_cfg: dict = {}
        if effort in ("minimal", "low", "medium", "high", "xhigh"):
            reasoning_cfg["effort"] = effort
        if summary in ("auto", "concise", "detailed"):
            reasoning_cfg["summary"] = summary
        if valves.REASONING_MAX_TOKENS > 0:
            reasoning_cfg["max_tokens"] = int(valves.REASONING_MAX_TOKENS)
        if reasoning_cfg:
            payload["reasoning"] = reasoning_cfg

        # --- Service tier ---
        # OpenRouter documents only "flex" and "priority" as supported values.
        tier = (valves.SERVICE_TIER or "").strip().lower()
        if tier in ("flex", "priority"):
            payload["service_tier"] = tier

        # --- Provider routing ---
        provider: dict = {}

        sort_val = valves.PROVIDER_SORT.strip().lower()
        if sort_val in ("price", "throughput", "latency"):
            provider["sort"] = sort_val

        order = self._parse_csv(valves.PROVIDER_ORDER)
        if order:
            provider["order"] = order

        ignore = self._parse_csv(valves.PROVIDER_IGNORE)
        if ignore:
            provider["ignore"] = ignore

        only = self._parse_csv(valves.PROVIDER_ONLY)
        if only:
            provider["only"] = only

        quantizations = self._parse_csv(valves.PROVIDER_QUANTIZATIONS)
        if quantizations:
            provider["quantizations"] = [q.lower() for q in quantizations]

        # `allow_fallbacks` defaults to true on OpenRouter, so only emit the
        # field when the operator opted out.
        if not valves.PROVIDER_ALLOW_FALLBACKS:
            provider["allow_fallbacks"] = False

        max_price: dict = {}
        prompt_cap = (valves.PROVIDER_MAX_PRICE_PROMPT or "").strip()
        if prompt_cap:
            max_price["prompt"] = prompt_cap
        completion_cap = (valves.PROVIDER_MAX_PRICE_COMPLETION or "").strip()
        if completion_cap:
            max_price["completion"] = completion_cap
        if max_price:
            provider["max_price"] = max_price

        if valves.REQUIRE_PARAMETERS:
            provider["require_parameters"] = True

        dc = valves.DATA_COLLECTION.strip().lower()
        if dc == "deny":
            provider["data_collection"] = "deny"

        # ZDR enforcement: forces OpenRouter to route only to Zero Data
        # Retention endpoints; the call fails fast if none exist for the
        # selected model.
        if valves.ZDR_ENFORCE:
            provider["zdr"] = True

        if provider:
            payload["provider"] = provider

        # --- Fallback models ---
        fallbacks = self._parse_csv(valves.FALLBACK_MODELS)
        if fallbacks:
            primary = payload.get("model", "")
            seen = {primary}
            unique_fallbacks = []
            for f in fallbacks:
                if f not in seen:
                    seen.add(f)
                    unique_fallbacks.append(f)
            payload["models"] = [primary] + unique_fallbacks

        # --- Transforms (middle-out) ---
        if valves.ENABLE_MIDDLE_OUT:
            payload["transforms"] = ["middle-out"]

        # --- Web search plugin ---
        # Append (don't overwrite) so the user can stack additional plugins
        # via the request body. Skip silently if a `web` plugin is already
        # present — first-match wins.
        web_plugin = self._build_web_search_plugin(valves)
        if web_plugin is not None:
            existing_plugins = payload.get("plugins")
            if not isinstance(existing_plugins, list):
                existing_plugins = []
            already_has_web = any(
                isinstance(p, dict) and p.get("id") == "web"
                for p in existing_plugins
            )
            if not already_has_web:
                existing_plugins.append(web_plugin)
                payload["plugins"] = existing_plugins

        # --- Cache control (Anthropic) ---
        if valves.ENABLE_CACHE_CONTROL:
            self._inject_cache_control(payload, valves)

        # Request usage accounting explicitly so cost/credit footers aren't blank.
        if valves.SHOW_COST_INFO:
            payload["usage"] = {"include": True}

        rf = (valves.RESPONSE_FORMAT or "").strip()
        if "response_format" not in payload:
            if rf == "json_object":
                payload["response_format"] = {"type": "json_object"}
            elif rf == "json_schema":
                _schema_str = (getattr(valves, "RESPONSE_SCHEMA", "") or "").strip()
                if _schema_str:
                    try:
                        _schema = json.loads(_schema_str)
                        payload["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "response",
                                "schema": _schema,
                                "strict": True,
                            },
                        }
                    except json.JSONDecodeError as exc:
                        print(f"[OpenRouter Pipe] RESPONSE_SCHEMA not applied (invalid JSON): {exc}")

        tc = (valves.TOOL_CHOICE or "").strip().lower()
        if tc in ("none", "auto", "required") and "tool_choice" not in payload:
            payload["tool_choice"] = tc

        return payload

    def _inject_cache_control(self, payload: dict, valves) -> None:
        """Inject Anthropic cache_control on the longest text chunk.

        Applies to the first matching role (system, then user) with list-type
        content. Only one chunk is tagged ('first match wins') to avoid
        excessive cache entries. The TTL valve (5m/1h) is propagated into the
        breakpoint so longer-lived caches are honoured by Anthropic.
        """
        ttl = (valves.ANTHROPIC_PROMPT_CACHE_TTL or "").strip().lower()
        cache_payload: dict = {"type": "ephemeral"}
        if ttl in ("5m", "1h"):
            cache_payload["ttl"] = ttl
        try:
            messages = payload.get("messages", [])
            for role in ("system", "user"):
                for message in (msg for msg in messages if msg.get("role") == role):
                    content = message.get("content")
                    if not isinstance(content, list):
                        continue
                    longest_idx, longest_len = -1, -1
                    for idx, chunk in enumerate(content):
                        if chunk.get("type") != "text":
                            continue
                        length = len(chunk.get("text", ""))
                        if length > longest_len:
                            longest_idx, longest_len = idx, length
                    if longest_idx >= 0:
                        content[longest_idx]["cache_control"] = dict(cache_payload)
                        return
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] cache_control not applied: {exc}")

    @staticmethod
    def _is_anthropic_model(model_id: str) -> bool:
        """Return True if the (possibly variant-suffixed) model ID is Claude."""
        if not isinstance(model_id, str):
            return False
        # Strip leading '~' (latest aliases) before the prefix check.
        return model_id.lstrip("~").lower().startswith("anthropic/")

    def _resolve_referer(self, valves) -> str:
        """Pick the HTTP-Referer header sent to OpenRouter.

        Order: explicit valve override → cached WEBUI_URL env → default.
        Validates that an override is a full URL with scheme; falls back
        silently otherwise so a misconfigured valve never breaks requests.
        """
        override = (valves.HTTP_REFERER_OVERRIDE or "").strip()
        # Reject control characters (CR/LF/NUL) that could split the header,
        # then require a full http(s) URL.  Fall back silently otherwise.
        if override and not any(c in override for c in "\r\n\x00"):
            if override.startswith(("http://", "https://")):
                return override
        return self._referer

    def _build_headers(
        self,
        include_content_type: bool = True,
        *,
        model_id: Optional[str] = None,
        valves,
    ) -> dict:
        """Build HTTP headers for OpenRouter API requests.

        ``model_id`` is the (post-clean) ID about to be invoked; passing it
        lets us inject provider-specific beta headers (e.g. Anthropic's
        interleaved-thinking) only when relevant.
        """
        headers = {
            "Authorization": f"Bearer {EncryptedStr.decrypt(valves.OPENROUTER_API_KEY or '')}",
            "HTTP-Referer": self._resolve_referer(valves),
            "X-Title": self._title,
        }
        if include_content_type:
            headers["Content-Type"] = "application/json"

        if (
            model_id
            and valves.ENABLE_ANTHROPIC_INTERLEAVED_THINKING
            and self._is_anthropic_model(model_id)
        ):
            existing = headers.get("anthropic-beta", "")
            features = [p.strip() for p in existing.split(",") if p.strip()]
            if _ANTHROPIC_INTERLEAVED_THINKING_BETA not in features:
                features.append(_ANTHROPIC_INTERLEAVED_THINKING_BETA)
            headers["anthropic-beta"] = ",".join(features)

        return headers

    @staticmethod
    def _build_tools_payload(__tools__) -> Optional[list]:
        """Convert OWUI's __tools__ dict into an OpenAI `tools` array, or None.

        Entries without a usable `spec` are skipped. Returns None when there is
        nothing to send so callers can cleanly fall back to the non-tool path.
        """
        if not __tools__:
            return None
        out = []
        for entry in __tools__.values():
            spec = entry.get("spec") if isinstance(entry, dict) else None
            if spec:
                out.append({"type": "function", "function": spec})
        return out or None

    async def _execute_tool_calls(self, tool_calls, __tools__, __event_emitter__) -> list:
        """Execute model tool_calls in parallel; return one role:tool message each.

        Supports sync and async callables. Any failure (unknown tool, bad JSON
        args, callable raising) is returned as the tool message content so the
        model can recover — never raised.
        """
        async def _run_one(call):
            fn_block = call.get("function", {}) if isinstance(call, dict) else {}
            name = fn_block.get("name", "")
            call_id = call.get("id", "")
            if __event_emitter__:
                try:
                    await __event_emitter__(
                        {"type": "status", "data": {"description": f"🔧 Calling {name}…", "done": False}}
                    )
                except Exception:
                    pass
            entry = (__tools__ or {}).get(name)
            if not entry:
                return {"role": "tool", "tool_call_id": call_id, "content": f"Error: unknown tool '{name}'"}
            try:
                args = json.loads(fn_block.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments did not decode to an object")
            except Exception as exc:
                return {"role": "tool", "tool_call_id": call_id, "content": f"Error: invalid tool arguments — {exc}"}
            try:
                callable_fn = entry.get("callable")
                result = callable_fn(**args)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                result = f"Error: tool '{name}' failed — {exc}"
            return {"role": "tool", "tool_call_id": call_id, "content": str(result)}

        if not tool_calls:
            return []
        return list(await asyncio.gather(*(_run_one(c) for c in tool_calls)))

    _CREDIT_TTL = 60.0

    def _credit_cache_evict_if_needed(self) -> None:
        """Bound the per-key credit cache to avoid unbounded growth."""
        if len(self._credit_cache) > 1000:
            self._credit_cache.clear()

    def _fetch_credit_balance(self, valves) -> Optional[float]:
        """Return remaining OpenRouter credit (total_credits - total_usage), cached
        ~60s per key. Returns None on any failure so the footer is simply omitted.
        """
        key = EncryptedStr.decrypt(valves.OPENROUTER_API_KEY or "")
        if not key:
            return None
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        cached = self._credit_cache.get(key_hash)
        if cached and (time.monotonic() - cached[1]) < self._CREDIT_TTL:
            return cached[0]
        resp = None
        try:
            resp = self._session.get(
                f"{self._base}{_API_PATH_CREDITS}",
                headers=self._build_headers(include_content_type=False, valves=valves),
                timeout=min(valves.REQUEST_TIMEOUT, 15),
                allow_redirects=False,
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", {})
            remaining = float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))
        except Exception:
            return None
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
        self._credit_cache_evict_if_needed()
        self._credit_cache[key_hash] = (remaining, time.monotonic())
        return remaining

    @staticmethod
    def _format_credit_info(remaining: Optional[float], currency: str = "USD") -> str:
        """Format the remaining-credit footer line."""
        if remaining is None:
            return ""
        symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
        return f"\n\n---\n*OpenRouter credit remaining: {symbol}{remaining:.2f}*"

    async def _emit_image_files(self, emitter, message, request=None, user=None, metadata=None) -> bool:
        """Emit a native Open WebUI ``files`` event for generated images.

        Image-output models (e.g. flux, gemini-image-preview) return raster
        data URLs in ``message.images``. Open WebUI's chat client only renders
        image attachments fetched from its own ``/api/v1/files/{id}/content``
        endpoint, so inline ``data:`` URLs never appear in the UI. When the
        Open WebUI runtime context is available (``request`` + ``user`` +
        ``metadata`` with chat_id/message_id), we upload each base64 image
        through OWUI's ``upload_image`` helper and emit the resulting file URL
        instead. Without that context the data URL is emitted as a fallback.

        Mutates ``message`` to clear ``images`` after a successful emit so the
        markdown formatter doesn't double-render them. Returns True when at
        least one image was emitted, False otherwise.
        """
        if not emitter or not isinstance(message, dict):
            return False
        images = message.get("images") or []
        if not images:
            return False

        # Resolve a real Open WebUI user object once (upload_image expects
        # attribute-style access, the __user__ kwarg is a dict).
        owui_user = None
        upload_image = None
        if request is not None and isinstance(user, dict) and user.get("id") and metadata:
            try:
                from open_webui.routers.images import upload_image as _upload_image
                from open_webui.models.users import Users as _Users
                upload_image = _upload_image
                _maybe_user = _Users.get_user_by_id(user["id"])
                if inspect.isawaitable(_maybe_user):
                    _maybe_user = await _maybe_user
                owui_user = _maybe_user
            except Exception as exc:
                print(f"[OpenRouter Pipe] OWUI image-upload helpers unavailable: {exc}")

        _data_re = re.compile(r"data:(image/[A-Za-z0-9.+-]+);base64,(.+)", re.DOTALL)
        files = []
        for img in images:
            if not isinstance(img, dict):
                continue
            url = (img.get("image_url") or {}).get("url", "")
            if not isinstance(url, str) or not url:
                continue
            lower = url.lower()

            # Convert a data: URL into a real OWUI file when we can
            if upload_image is not None and owui_user is not None and lower.startswith("data:image/"):
                m = _data_re.match(url)
                if m:
                    try:
                        content_type = m.group(1)
                        image_bytes = base64.b64decode(m.group(2))
                        _item, new_url = await upload_image(
                            request, image_bytes, content_type, metadata, owui_user
                        )
                        if new_url:
                            url = str(new_url)
                            lower = url.lower()
                    except Exception as exc:
                        print(f"[OpenRouter Pipe] Image upload to OWUI failed: {exc}")

            if not (
                lower.startswith(("http://", "https://"))
                or url.startswith("/")  # path-only URL produced by upload_image
                or lower.startswith("data:image/")
            ):
                continue
            files.append({"type": "image", "url": url})

        if not files:
            return False
        try:
            await emitter({"type": "files", "data": {"files": files}})
        except Exception:
            return False
        message["images"] = []
        return True

    async def _emit_citation_events(self, emitter, citations) -> None:
        """Emit one Open WebUI 'citation' event per URL when an emitter is provided.

        Markdown citations still ship in the final footer; this adds a structured
        event so OWUI can render citations as native footnotes. No-op when the
        emitter is missing or citations are empty; emitter exceptions are
        swallowed so a misbehaving consumer never breaks a response.
        """
        if not emitter or not citations:
            return
        for url in citations:
            if not isinstance(url, str) or not url:
                continue
            try:
                await emitter({
                    "type": "citation",
                    "data": {"source": {"name": url, "url": url}},
                })
            except Exception:
                pass

    async def _prefetch_credit_if_enabled(self, valves) -> None:
        """Pre-warm the credit cache off the event loop, so the synchronous
        _fetch_credit_balance call inside a footer hits the cache (no blocking I/O).
        """
        if valves.SHOW_REMAINING_CREDIT:
            await asyncio.to_thread(self._fetch_credit_balance, valves)

    def _format_final_message(self, res: dict, payload: dict, valves) -> str:
        """Format a completed OpenRouter response dict into the user-facing string.

        Shared by the plain non-stream path and the tool-loop final round.
        """
        if not res.get("choices"):
            return "OpenRouter Error: Empty response. The model may be temporarily unavailable."
        choice = res["choices"][0]
        message = choice.get("message", {})
        citations = res.get("citations", [])

        reasoning = _insert_citations(message.get("reasoning", ""), citations)
        content = _insert_citations(message.get("content") or "", citations)
        rendered_citations = _format_citation_list(citations)

        audio_obj = message.get("audio") or {}
        if audio_obj and not content:
            transcript = audio_obj.get("transcript", "")
            content = transcript or "*[Audio response — transcript not available.]*"

        image_md = _format_image_output(message.get("images") or [])

        final_parts = []
        if reasoning:
            final_parts.append(f"<think>\n{reasoning}\n</think>\n")
        if content:
            final_parts.append(content)
        if image_md:
            prefix = "\n\n" if final_parts else ""
            final_parts.append(prefix + image_md)

        actual_model = res.get("model", "")
        requested_model = payload.get("model", "")
        if payload.get("models") and actual_model and actual_model != requested_model:
            safe_model = re.sub(r"[`\r\n\]\[()]", "", str(actual_model))
            final_parts.append(f"\n\n---\n*Responded by: {safe_model}*")

        if rendered_citations:
            final_parts.append(rendered_citations)

        if valves.SHOW_COST_INFO:
            cost_info = _format_cost_info(res.get("usage", {}), valves.COST_CURRENCY)
            if cost_info:
                final_parts.append(cost_info)

        if valves.SHOW_GENERATION_ID:
            gen_footer = _format_generation_id(res.get("id"))
            if gen_footer:
                final_parts.append(gen_footer)

        if valves.SHOW_REMAINING_CREDIT:
            credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
            if credit_line:
                final_parts.append(credit_line)

        return "".join(final_parts)

    def _non_stream_fetch(self, headers: dict, payload: dict, valves):
        """Send a non-streaming request, return the parsed res dict or an
        error string. Sync (run via asyncio.to_thread from async callers).
        """
        try:
            response = self._retryable_request(headers, payload, stream=False, valves=valves)
            try:
                res = response.json()
            finally:
                response.close()
            if "error" in res and not res.get("choices"):
                err = res["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"OpenRouter Error: {msg}"
            if not res.get("choices"):
                return "OpenRouter Error: Empty response. The model may be temporarily unavailable."
            return res
        except requests.exceptions.Timeout:
            return f"OpenRouter Error: Request timed out after {valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
        except requests.exceptions.HTTPError as exc:
            return self._format_http_error(exc)
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Non-stream fetch error: {exc}")
            traceback.print_exc()
            return f"OpenRouter Error: {exc}"

    async def _non_stream_with_events(self, headers: dict, payload: dict, valves, emitter, request=None, user=None, metadata=None) -> str:
        """Wrap _non_stream_fetch with image-files + citation event emits and
        credit prefetch, then format. Used by pipe()'s no-tools non-stream
        path so generated images render as native OWUI attachments rather
        than huge inline markdown links.
        """
        res = await asyncio.to_thread(self._non_stream_fetch, headers, payload, valves)
        if isinstance(res, str):
            return res
        choices = res.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        await self._emit_image_files(emitter, message, request, user, metadata)
        await self._emit_citation_events(emitter, res.get("citations") or [])
        await self._prefetch_credit_if_enabled(valves)
        return self._format_final_message(res, payload, valves)

    def _non_stream_response(self, headers: dict, payload: dict, valves) -> str:
        """Send a non-streaming request and return the formatted response."""
        try:
            response = self._retryable_request(headers, payload, stream=False, valves=valves)
            try:
                res = response.json()
            finally:
                response.close()

            # Handle API error in response body
            if "error" in res and not res.get("choices"):
                err = res["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"OpenRouter Error: {msg}"

            if not res.get("choices"):
                return "OpenRouter Error: Empty response. The model may be temporarily unavailable."

            return self._format_final_message(res, payload, valves)
        except requests.exceptions.Timeout:
            return f"OpenRouter Error: Request timed out after {valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
        except requests.exceptions.HTTPError as exc:
            return self._format_http_error(exc)
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Non-stream response error: {exc}")
            traceback.print_exc()
            return f"OpenRouter Error: {exc}"

    async def _run_tools_nonstream(self, headers, payload, valves, __tools__, __event_emitter__, __request__=None, __user__=None, __metadata__=None) -> str:
        """Drive the non-streaming native-tool loop: request → execute → repeat."""
        max_iter = max(int(getattr(valves, "MAX_TOOL_ITERATIONS", 5) or 5), 1)
        for _ in range(max_iter):
            try:
                resp = await self._call_request_async(False, headers, payload, valves)
                try:
                    res = resp.json()
                finally:
                    if hasattr(resp, "close"):
                        resp.close()
            except requests.exceptions.Timeout:
                return f"OpenRouter Error: Request timed out after {valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
            except requests.exceptions.HTTPError as exc:
                return self._format_http_error(exc)
            except Exception as exc:  # pragma: no cover
                return f"OpenRouter Error: {exc}"

            if "error" in res and not res.get("choices"):
                err = res["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"OpenRouter Error: {msg}"

            choices = res.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                await self._emit_image_files(__event_emitter__, message, __request__, __user__, __metadata__)
                await self._emit_citation_events(__event_emitter__, res.get("citations") or [])
                await self._prefetch_credit_if_enabled(valves)
                return self._format_final_message(res, payload, valves)

            tool_msgs = await self._execute_tool_calls(tool_calls, __tools__, __event_emitter__)
            payload.setdefault("messages", []).append(message)
            payload["messages"].extend(tool_msgs)

        # Cap reached while still requesting tools: one last call, then a note.
        try:
            resp = await self._call_request_async(False, headers, payload, valves)
            try:
                res = resp.json()
            finally:
                if hasattr(resp, "close"):
                    resp.close()
        except Exception as exc:  # pragma: no cover
            return f"OpenRouter Error: {exc}"
        _choices = res.get("choices") or []
        _msg = _choices[0].get("message", {}) if _choices else {}
        await self._emit_image_files(__event_emitter__, _msg, __request__, __user__, __metadata__)
        await self._emit_citation_events(__event_emitter__, res.get("citations") or [])
        await self._prefetch_credit_if_enabled(valves)
        final = self._format_final_message(res, payload, valves)
        if final.startswith("OpenRouter Error:"):
            return final
        return final + "\n\n---\n*Tool calling stopped: reached MAX_TOOL_ITERATIONS.*"

    def _stream_one_round(self, headers, payload, valves, state: dict):
        """Stream ONE model round. Yield user-facing content; record into `state`:
        tool_calls (assembled by index), usage, generation_id, citations,
        finish_reason. <think> handling mirrors _stream_response.
        """
        in_think = False
        tool_acc: dict = {}

        def _close_think():
            nonlocal in_think
            if in_think:
                in_think = False
                return "\n</think>\n"
            return ""

        response = None
        try:
            response = self._retryable_request(headers, payload, stream=True, valves=valves)
            for raw_line in response.iter_lines():
                if not raw_line or not raw_line.startswith(b"data: "):
                    continue
                data = raw_line[len(b"data: "):].decode("utf-8")
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    err = chunk["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    ct = _close_think()
                    if ct:
                        yield ct
                    yield f"\n\nOpenRouter Error: {msg}"
                    state["error"] = True
                    return

                gid = chunk.get("id")
                if gid and not state.get("generation_id"):
                    state["generation_id"] = gid
                if chunk.get("usage"):
                    state["usage"] = chunk["usage"]
                cits = chunk.get("citations")
                if cits is not None:
                    state["citations"] = cits

                choices = chunk.get("choices") or []
                first = choices[0] if choices and isinstance(choices[0], dict) else {}
                if first.get("finish_reason"):
                    state["finish_reason"] = first["finish_reason"]
                delta = first.get("delta", {})

                for tc in (delta.get("tool_calls") or []):
                    idx = tc.get("index", 0)
                    slot = tool_acc.setdefault(idx, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]

                reasoning = delta.get("reasoning", "")
                content = delta.get("content") or ""
                if not content:
                    content = (delta.get("audio") or {}).get("transcript", "")

                if reasoning:
                    if not in_think:
                        yield "<think>\n"
                        in_think = True
                    yield _insert_citations(reasoning, state.get("citations") or [])
                if content:
                    ct = _close_think()
                    if ct:
                        yield ct
                    yield _insert_citations(content, state.get("citations") or [])

            ct = _close_think()
            if ct:
                yield ct
        except requests.exceptions.Timeout:
            yield f"OpenRouter Error: Request timed out after {valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
            state["error"] = True
        except requests.exceptions.HTTPError as exc:
            yield self._format_http_error(exc)
            state["error"] = True
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Stream round error: {exc}")
            state["error"] = True
        finally:
            if tool_acc:
                state["tool_calls"] = [tool_acc[k] for k in sorted(tool_acc)]
            if response is not None:
                response.close()

    async def _run_tools_stream(self, headers, payload, valves, __tools__, __event_emitter__):
        """Async generator: stream rounds, executing tools between them."""
        max_iter = max(int(getattr(valves, "MAX_TOOL_ITERATIONS", 5) or 5), 1)
        for _ in range(max_iter):
            state: dict = {}
            it = iter(self._stream_one_round(headers, payload, valves, state))
            while True:
                piece = await asyncio.to_thread(next, it, _STREAM_DONE)
                if piece is _STREAM_DONE:
                    break
                yield piece
            if state.get("error"):
                return
            tool_calls = state.get("tool_calls")
            if not tool_calls:
                await self._emit_citation_events(__event_emitter__, state.get("citations") or [])
                await self._prefetch_credit_if_enabled(valves)
                yield self._stream_footer(state, valves)
                return
            tool_msgs = await self._execute_tool_calls(tool_calls, __tools__, __event_emitter__)
            assistant_msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            payload.setdefault("messages", []).append(assistant_msg)
            payload["messages"].extend(tool_msgs)

        state = {}
        it = iter(self._stream_one_round(headers, payload, valves, state))
        while True:
            piece = await asyncio.to_thread(next, it, _STREAM_DONE)
            if piece is _STREAM_DONE:
                break
            yield piece
        if not state.get("error"):
            await self._emit_citation_events(__event_emitter__, state.get("citations") or [])
            await self._prefetch_credit_if_enabled(valves)
            yield self._stream_footer(state, valves)
            yield "\n\n---\n*Tool calling stopped: reached MAX_TOOL_ITERATIONS.*"

    def _stream_footer(self, state: dict, valves) -> str:
        """Build the citations/cost/generation-id footer for a streamed answer."""
        parts = []
        rendered = _format_citation_list(state.get("citations") or [])
        if rendered:
            parts.append(rendered)
        if valves.SHOW_COST_INFO:
            ci = _format_cost_info(state.get("usage") or {}, valves.COST_CURRENCY)
            if ci:
                parts.append(ci)
        if valves.SHOW_GENERATION_ID:
            gf = _format_generation_id(state.get("generation_id"))
            if gf:
                parts.append(gf)
        if valves.SHOW_REMAINING_CREDIT:
            credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
            if credit_line:
                parts.append(credit_line)
        return "".join(parts)

    def _stream_response(
        self, headers: dict, payload: dict, valves
    ) -> Generator[str, None, None]:
        """Stream SSE chunks with <think> block management and mid-stream error recovery."""
        response = None
        in_think = False
        latest_citations: List[str] = []
        latest_usage: dict = {}
        latest_generation_id: Optional[str] = None

        def _close_think_tag():
            nonlocal in_think
            if in_think:
                in_think = False
                return "\n</think>\n"
            return ""

        try:
            response = self._retryable_request(headers, payload, stream=True, valves=valves)
            for raw_line in response.iter_lines():
                if not raw_line or not raw_line.startswith(b"data: "):
                    continue
                data = raw_line[len(b"data: ") :].decode("utf-8")
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                # Handle mid-stream errors
                if "error" in chunk:
                    err = chunk["error"]
                    msg = (
                        err.get("message", str(err))
                        if isinstance(err, dict)
                        else str(err)
                    )
                    close_tag = _close_think_tag()
                    if close_tag:
                        yield close_tag
                    yield f"\n\nOpenRouter Error: {msg}"
                    return

                # Generation ID arrives on the first chunk and stays stable.
                gen_id = chunk.get("id")
                if gen_id and not latest_generation_id:
                    latest_generation_id = gen_id

                usage_data = chunk.get("usage")
                if usage_data:
                    latest_usage = usage_data

                citations = chunk.get("citations")
                if citations is not None:
                    latest_citations = citations

                choices = chunk.get("choices") or []
                first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                delta = first_choice.get("delta", {})
                reasoning = delta.get("reasoning", "")
                content = delta.get("content") or ""

                # Audio transcript fallback: stream the transcript when the model
                # returns audio instead of text (e.g. openai/gpt-audio).
                if not content:
                    audio_delta = delta.get("audio") or {}
                    content = audio_delta.get("transcript", "")

                if reasoning:
                    if not in_think:
                        yield "<think>\n"
                        in_think = True
                    yield _insert_citations(reasoning, latest_citations)

                if content:
                    close_tag = _close_think_tag()
                    if close_tag:
                        yield close_tag
                    yield _insert_citations(content, latest_citations)

            # Close <think> if still open
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            rendered_citations = _format_citation_list(latest_citations)
            if rendered_citations:
                yield rendered_citations

            if valves.SHOW_COST_INFO:
                cost_info = _format_cost_info(latest_usage, valves.COST_CURRENCY)
                if cost_info:
                    yield cost_info

            if valves.SHOW_GENERATION_ID:
                gen_footer = _format_generation_id(latest_generation_id)
                if gen_footer:
                    yield gen_footer

            if valves.SHOW_REMAINING_CREDIT:
                credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
                if credit_line:
                    yield credit_line
        except requests.exceptions.Timeout:
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            yield f"OpenRouter Error: Request timed out after {valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
        except requests.exceptions.HTTPError as exc:
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            if exc.response is not None:
                try:
                    _ = exc.response.content  # Cache body before closing
                except Exception:
                    pass
                try:
                    exc.response.close()
                except Exception:
                    pass
            yield self._format_http_error(exc)
        except Exception as exc:
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            print(f"[OpenRouter Pipe] Stream error: {exc}")
            traceback.print_exc()
            yield f"OpenRouter Error: {exc}"
        finally:
            # Clean up resources — do NOT yield here because
            # GeneratorExit (consumer break) would cause RuntimeError.
            in_think = False
            if response is not None:
                response.close()

    @staticmethod
    def _parse_retry_after(value) -> Optional[float]:
        """Parse a Retry-After header (integer seconds or HTTP-date) into seconds.

        Clamped to [0, _MAX_RETRY_AFTER]. Returns None when absent/unparseable.
        """
        if not value:
            return None
        value = str(value).strip()
        try:
            secs = float(value)
        except ValueError:
            parsed = email.utils.parsedate_tz(value)
            if not parsed:
                return None
            try:
                secs = email.utils.mktime_tz(parsed) - time.time()
            except (TypeError, ValueError, OverflowError):
                return None
        return max(0.0, min(secs, _MAX_RETRY_AFTER))

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff with jitter, capped at 30s."""
        return min(2 ** attempt + random.uniform(0, 1), 30)

    def _retryable_request(
        self, headers: dict, payload: dict, stream: bool, valves
    ) -> requests.Response:
        """Send a POST request with automatic retry and exponential backoff.

        Retries transient failures — network Timeout/ConnectionError and HTTP
        429/5xx (honouring Retry-After when present) — within the MAX_RETRIES
        budget. Non-transient 4xx fail fast.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(valves.MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                    timeout=valves.REQUEST_TIMEOUT,
                    stream=stream,
                    allow_redirects=False,
                )
                response.raise_for_status()
                return response
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                last_exc = exc
                print(f"[OpenRouter Pipe] Attempt {attempt + 1} failed: {exc}")
                if attempt == valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in _RETRYABLE_STATUS or attempt == valves.MAX_RETRIES:
                    raise
                delay = None
                if exc.response is not None:
                    delay = self._parse_retry_after(exc.response.headers.get("Retry-After"))
                    try:
                        exc.response.close()
                    except Exception:
                        pass
                if delay is None:
                    delay = self._backoff_delay(attempt)
                last_exc = exc
                print(f"[OpenRouter Pipe] HTTP {status} on attempt {attempt + 1}; retrying in {delay:.1f}s")
                time.sleep(delay)
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                print(f"[OpenRouter Pipe] Unexpected error: {exc}")
                if attempt == valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
        if last_exc:
            raise last_exc  # pragma: no cover
        raise RuntimeError("OpenRouter Error: request not completed")  # pragma: no cover

    async def _call_request_async(self, stream, headers, payload, valves) -> requests.Response:
        """Run the blocking _retryable_request (incl. retry sleeps) off the event loop."""
        return await asyncio.to_thread(self._retryable_request, headers, payload, stream, valves)

    def _format_http_error(self, exc: requests.exceptions.HTTPError) -> str:
        """Format an HTTP error into a user-friendly message."""
        status = exc.response.status_code if exc.response is not None else "?"

        # Specific messages for common error codes
        if status == 429:
            base = "OpenRouter Error: Rate limit exceeded (HTTP 429). Please wait a moment and try again."
        elif status == 402:
            base = "OpenRouter Error: Insufficient credits (HTTP 402). Check your OpenRouter account balance."
        elif status == 401:
            base = "OpenRouter Error: Invalid API key (HTTP 401). Check your OPENROUTER_API_KEY."
        elif status == 403:
            base = "OpenRouter Error: Access denied (HTTP 403). Your API key may not have permission for this model."
        elif status == 404:
            base = "OpenRouter Error: Model or endpoint not found (HTTP 404). The model ID may be wrong or unavailable."
        elif status == 408:
            base = "OpenRouter Error: Request timed out on the server (HTTP 408). Try again."
        elif status == 413:
            base = "OpenRouter Error: Request too large (HTTP 413). The prompt or context likely exceeds the model's limit."
        elif status == 500:
            base = "OpenRouter Error: Provider error (HTTP 500). The upstream model provider failed; try again or pick another model."
        elif status == 502:
            base = "OpenRouter Error: Bad gateway (HTTP 502). The upstream provider is unreachable; try again."
        elif status == 503:
            base = "OpenRouter Error: Service unavailable (HTTP 503). The provider is overloaded; try again shortly."
        elif status == 504:
            base = "OpenRouter Error: Upstream timeout (HTTP 504). The provider took too long; try again."
        else:
            base = f"OpenRouter Error: HTTP {status}"

        if exc.response is not None:
            try:
                err = exc.response.json().get("error", {})
                detail = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                if detail:
                    base += f" — {detail}"
            except Exception:
                pass
        return base


__all__ = ["Pipe"]
