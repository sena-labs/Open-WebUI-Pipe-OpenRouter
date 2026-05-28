"""
title: OpenRouter Pipe
author: Sena Labs
author_url: https://github.com/sena-labs
funding_url: https://github.com/sponsors/sena-labs
version: 1.2.0
license: MIT
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNmQyOGQ5Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjYTc4YmZhIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIHJ4PSIyMCIgZmlsbD0idXJsKCNiZykiLz48cGF0aCBkPSJNMjAgNTAgQzIwIDMwLCA0MCAzMCwgNTAgMzAgTDUwIDIyIEw2OCA0MCBMNTAgNTggTDUwIDUwIEM0MCA1MCwgMzUgNDUsIDMwIDUwIEMyNSA1NSwgMjAgNzAsIDIwIDUwIFoiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSIzMCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxjaXJjbGUgY3g9IjgyIiBjeT0iNTAiIHI9IjciIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSI3MCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxsaW5lIHgxPSI2OCIgeTE9IjQwIiB4Mj0iNzYiIHkyPSIzMiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBvcGFjaXR5PSIwLjUiLz48bGluZSB4MT0iNjgiIHkxPSI0MCIgeDI9Ijc2IiB5Mj0iNTAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC41Ii8+PGxpbmUgeDE9IjY4IiB5MT0iNDAiIHgyPSI3NiIgeTI9IjY4IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIG9wYWNpdHk9IjAuNSIvPjwvc3ZnPg==
required_open_webui_version: 0.4.0
requirements: requests>=2.32.4, pydantic>=2.0
description: Access 300+ AI models through OpenRouter directly inside Open WebUI. Features provider routing, reasoning tokens with <think> tags, full SSE streaming, model fallbacks, middle-out compression, Anthropic cache control, citations, 13 provider icons, and configurable retry logic.
"""

import copy
import hashlib
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

# Cache TTL for model list (seconds)
_MODELS_CACHE_TTL = 300.0  # 5 minutes

# HTTP status codes that warrant a transparent retry (transient/upstream).
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})

# Retry/backoff tuning.
_BACKOFF_CAP_S = 30.0          # max seconds for any single backoff/Retry-After wait
_MAX_ICON_INSERT_ATTEMPTS = 3  # give up inserting a model's icon after N tries

# Provider icons — synced into the Open WebUI Models database by
# _sync_model_icons() so the frontend can serve them via
# /models/model/profile/image.  Disable with SYNC_PROVIDER_ICONS = False.
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


# Characters that break out of a markdown ``[text](url)`` link.
# Includes parentheses, square brackets, angle brackets, and whitespace.
_MD_UNSAFE_URL_CHARS = {")", "(", "]", "[", "<", ">", " ", "\t", "\n", "\r"}


def _md_escape_url(url: str) -> str:
    """Percent-encode markdown-breaking characters in a URL.

    Defends against markdown injection in citation/image URLs of the form
    ``https://x/a](javascript:...)`` that would escape the ``[..](...)``
    construct and inject a second link.
    """
    if not url:
        return url
    out = []
    for ch in url:
        if ch in _MD_UNSAFE_URL_CHARS:
            out.append(f"%{ord(ch):02X}")
        else:
            out.append(ch)
    return "".join(out)


def _is_owui_managed_icon(url: str) -> bool:
    """Return True if the icon URL was set by OWUI or our sync logic.

    data: URLs are the pipe's own SVG icon that OWUI assigns as default to all
    manifold child models.  openrouter.ai/images/models/ and
    openrouter.ai/images/icons/ are the provider icon paths we write (the
    former was the old path, now superseded by the latter).  Any other URL is
    assumed to be a user-set custom icon and must not be overwritten.
    """
    return (
        not url
        or url.startswith("data:")
        or url.startswith("https://openrouter.ai/images/models/")
        or url.startswith("https://openrouter.ai/images/icons/")
    )


def _insert_citations(text: str, citations: Optional[List[str]]) -> str:
    """Replace [n] references with markdown links (only safe HTTP URLs)."""
    if not citations or not text:
        return text

    def _replace(match_obj):
        try:
            idx = int(match_obj.group(1)) - 1
            if 0 <= idx < len(citations) and _is_safe_url(citations[idx]):
                safe_url = _md_escape_url(citations[idx])
                return f"[[{idx + 1}]]({safe_url})"
        except (ValueError, IndexError):
            pass
        return match_obj.group(0)

    try:
        return _CITATION_RE.sub(_replace, text)
    except Exception as exc:  # pragma: no cover
        print(f"[OpenRouter Pipe] Citation injection error: {exc}")
        return text


def _format_citation_list(citations: Optional[List[str]]) -> str:
    if not citations:
        return ""
    try:
        rendered = "\n".join(f"{idx + 1}. {url}" for idx, url in enumerate(citations))
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
    """Format token usage and cost from an OpenRouter usage dict."""
    if not usage:
        return ""
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0) or (prompt + completion)
    cost = usage.get("cost")

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


def _is_safe_image_data_uri(lower_url: str) -> bool:
    """Accept only inert raster ``data:image/`` types.

    ``data:image/svg+xml`` is rejected because SVG can carry inline scripts
    (``<svg onload=...>``) and would run in any rendering context that inlines
    the SVG rather than loading it via ``<img>``.
    """
    if not lower_url.startswith("data:image/"):
        return False
    # Block svg+xml explicitly; allow png/jpeg/jpg/gif/webp/bmp/apng/avif.
    return not lower_url.startswith("data:image/svg")


def _format_image_output(images: list) -> str:
    """Format OpenRouter image output objects as markdown image tags.

    Only http(s) and inert ``data:image/*`` URLs are rendered (svg+xml is
    blocked).  Markdown-breaking characters in URLs are percent-encoded.
    """
    parts = []
    for img in (images or []):
        if not isinstance(img, dict):
            continue
        url = (img.get("image_url") or {}).get("url", "")
        if not url:
            continue
        lower = url.lower()
        if not (lower.startswith(("http://", "https://")) or _is_safe_image_data_uri(lower)):
            continue
        parts.append(f"![Generated image]({_md_escape_url(url)})")
    return "\n\n".join(parts)


# Image file extensions — positive list used by _looks_like_image_content.
_IMAGE_EXTENSIONS = frozenset((
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".apng", ".heic", ".heif",
))

# Known image-generation CDN hosts.  URLs on these hosts are treated as image
# output even when they carry no file extension (Replicate, fal.ai, and the
# OpenAI/DALL-E blob storage all serve extension-less URLs).
_IMAGE_CDN_HOSTS = frozenset((
    "replicate.delivery",
    "pbxt.replicate.delivery",
    "fal.media",
    "v2.fal.media",
    "v3.fal.media",
    "cdn.fal.ai",
    "oaidalleapiprodscus.blob.core.windows.net",
    "cdn.openai.com",
    "files.openai.com",
    "images.bfl.ai",  # Black Forest Labs / FLUX
    "delivery.bfl.ai",
    "cdn.luma-pictures.com",
    "ideogram.ai",
    "cdn.midjourney.com",
    "cdn.discordapp.com",  # Midjourney commonly serves via Discord CDN
    "lh3.googleusercontent.com",  # Google Gemini / Imagen image output
    "storage.googleapis.com",
))


def _looks_like_image_content(text: str) -> bool:
    """Return True when text is a standalone image URI or bare image URL.

    Image-generation models (e.g. FLUX, DALL-E via OpenRouter) return the
    generated image as ``message.content`` — either a ``data:image/`` base-64
    URI or a bare CDN URL with no surrounding prose.  Both cases need to be
    converted to a markdown ``![...]()`` tag so Open WebUI renders them.

    Heuristic (allow-list rather than deny-list to avoid false positives on
    LLM responses that contain a single bare URL):
      * ``data:image/<inert-type>`` URI → True
      * URL whose path ends in a known image extension → True
      * URL whose host is a known image-generation CDN → True
      * Anything else (including bare ``https://example.com``) → False
    """
    if not text:
        return False
    stripped = text.strip()
    if " " in stripped or "\n" in stripped:
        return False
    lower = stripped.lower()
    if lower.startswith("data:image/"):
        return _is_safe_image_data_uri(lower)
    if not lower.startswith(("http://", "https://")):
        return False

    # Extract host and path ("://" guaranteed present by the scheme check above)
    host_path = lower[lower.find("://") + 3:]
    slash_idx = host_path.find("/")
    if slash_idx == -1:
        host = host_path.split("?")[0].split("#")[0]
        path = ""
    else:
        host = host_path[:slash_idx]
        path = host_path[slash_idx:].split("?")[0].split("#")[0]
    # Strip optional :port and a trailing FQDN dot from the host
    host = host.split(":", 1)[0].rstrip(".")

    # SVG can carry inline scripts; never auto-render it even from a trusted host.
    if path.endswith(".svg"):
        return False
    if any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS):
        return True
    if host in _IMAGE_CDN_HOSTS:
        return True
    return False


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
            description="Controls reasoning depth. Works independently of Include Reasoning",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "", "label": "Disabled"},
                        {"value": "low", "label": "Low"},
                        {"value": "medium", "label": "Medium"},
                        {"value": "high", "label": "High"},
                    ],
                }
            },
        )
        INCLUDE_REASONING: bool = Field(
            default=os.getenv("OPENROUTER_INCLUDE_REASONING", "true").lower() == "true",
            description="Show model reasoning in <think> blocks. Can be used with or without Reasoning Effort",
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
        FREE_ONLY: bool = Field(
            default=os.getenv("OPENROUTER_FREE_ONLY", "false").lower() == "true",
            description="Show only free-tier models (by suffix :free or zero pricing)",
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
        ENABLE_CACHE_CONTROL: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_CACHE_CONTROL", "false").lower()
            == "true",
            description="Enable prompt caching for Anthropic models (reduces cost on repeated long prompts). No effect on other providers",
        )
        SYNC_PROVIDER_ICONS: bool = Field(
            default=os.getenv("OPENROUTER_SYNC_ICONS", "true").lower() == "true",
            description="Automatically sync provider icons into Open WebUI's model database so they appear in the UI",
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

        @field_validator("OPENROUTER_BASE_URL")
        @classmethod
        def _validate_base_url(cls, v: str) -> str:
            v = v.strip()
            if v.startswith("https://"):
                return v
            if v.startswith("http://"):
                # Reject plaintext HTTP except for loopback hosts to prevent
                # bearer-token leakage in transit and SSRF to public origins.
                host = v[len("http://"):].split("/", 1)[0].split(":", 1)[0].lower()
                if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
                    return v
                raise ValueError(
                    "Base URL must use https:// (plaintext http:// allowed only for localhost)"
                )
            raise ValueError("Base URL must start with https:// or http://")

    def __init__(self) -> None:
        self.type = "manifold"
        self.valves = self.Valves()
        self._session = requests.Session()
        # Larger connection pool keeps TLS handshakes amortized under bursty
        # multi-user Open WebUI workloads (default is 10).
        _adapter = requests.adapters.HTTPAdapter(
            pool_connections=20, pool_maxsize=50
        )
        self._session.mount("https://", _adapter)
        self._session.mount("http://", _adapter)
        # Cache env vars that don't change at runtime
        self._referer = os.getenv("WEBUI_URL", "http://localhost:3000")
        self._title = os.getenv("WEBUI_NAME", "OpenWebUI")
        # Model list cache
        self._models_cache: Optional[List[dict]] = None
        self._models_cache_ts: float = 0.0
        self._models_cache_key: str = ""
        # Track which model IDs already have icons synced (avoids repeated DB writes)
        self._icons_synced: set = set()
        # Cap retry attempts on failed DB inserts so transient OWUI registration
        # delays don't cause unbounded DB churn (PERF-3).
        self._icon_insert_attempts: dict = {}
        # Models whose insert attempts are exhausted (OWUI hasn't registered them).
        # Kept SEPARATE from _icons_synced so the cache-hit re-sync loop still
        # re-checks them via get_model_by_id and can pick up a late registration
        # (the insert is skipped, but a now-existing record is updated normally).
        self._icon_insert_exhausted: set = set()
        # Cache function_id once: OWUI sets __module__ to "function_{id}" at load time
        _fm = type(self).__module__ or ""
        self._function_id: Optional[str] = (
            _fm[len("function_"):] if _fm.startswith("function_") else None
        )
        if not self._api_key:
            print("[OpenRouter Pipe] Warning: OPENROUTER_API_KEY not set")

    @property
    def _api_key(self) -> str:
        """Return the API-key string.

        Kept as a single accessor so the storage type can change without
        touching call sites.  NOTE: the key is intentionally a plain ``str``,
        not ``pydantic.SecretStr`` — Open WebUI persists valves by
        JSON-serialising them, and a ``SecretStr`` serialises to the literal
        mask ``"**********"``, which would overwrite the stored key on the next
        valve save.  UI-level masking is provided via the ``password`` input
        type in the field's ``json_schema_extra`` instead.
        """
        return self.valves.OPENROUTER_API_KEY

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
        key = self._api_key
        api_key_hash = (
            hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] if key else ""
        )
        return (
            f"{api_key_hash}|{self.valves.FREE_ONLY}|"
            f"{self.valves.MODEL_PROVIDERS}|{self.valves.INVERT_PROVIDER_LIST}|"
            f"{self.valves.MODEL_PREFIX}|{self.valves.OPENROUTER_BASE_URL}"
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
        if not self._api_key:
            return [{"id": "error", "name": "OpenRouter API key not configured. Set it in Settings."}]

        # Return cached models if still valid
        if self._models_cache_valid() and self._models_cache is not None:
            # Continue syncing icons on cache hits until every model is either
            # synced or has exhausted its insert attempts.  This resolves the
            # race where OWUI registers models (and may overwrite icons) only
            # after the first pipes() call returns.  Exhausted models are still
            # re-checked each pass (cheap read) so a late registration is caught.
            resolved = len(self._icons_synced) + len(self._icon_insert_exhausted)
            if self.valves.SYNC_PROVIDER_ICONS and resolved < len(self._models_cache):
                self._sync_model_icons(self._models_cache)
            return self._models_cache

        headers = self._build_headers(include_content_type=False)
        response = None
        try:
            response = self._session.get(
                self.models_url,
                headers=headers,
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
        models: List[dict] = []

        for model in data:
            model_id = model.get("id")
            if not model_id:
                continue

            if self.valves.FREE_ONLY:
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
                if not is_free:
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

            model_dict = {
                "id": model_id,
                "name": f"{prefix}{model_name}",
            }

            models.append(model_dict)

        if not models:
            if self.valves.FREE_ONLY:
                error_text = "No free models available. Disable FREE_ONLY to see paid models."
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

        # Prune icon-sync state to the current model set so a valve change (e.g.
        # provider filter) cannot leave stale IDs that skew the cache-hit
        # re-sync guard or leak attempt counters for models no longer listed.
        _current_ids = {m["id"] for m in models}
        self._icons_synced &= _current_ids
        self._icon_insert_exhausted &= _current_ids
        self._icon_insert_attempts = {
            k: v for k, v in self._icon_insert_attempts.items() if k in _current_ids
        }

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

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """Route a chat completion request to OpenRouter (stream or non-stream).

        Returns an ``AsyncGenerator`` for streaming responses (Open WebUI iterates
        it with ``async for``) and a plain ``str`` for non-streaming responses
        and early-exit error conditions.
        """
        if not self._api_key:
            return "OpenRouter Error: OPENROUTER_API_KEY not configured. Set it in Settings → Connections."

        model_id = self._clean_model_id(body.get("model", ""))

        # Guard against missing or pseudo-error model
        if not model_id:
            return "OpenRouter Error: No model specified."
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

        payload = self._prepare_payload(body)
        headers = self._build_headers()
        stream = body.get("stream", False)

        if stream:
            # Always wrap the sync SSE generator in an AsyncGenerator so the
            # return type is consistent and so the optional done-event always
            # fires in the wrapper's ``finally`` block.
            gen = self._stream_response(headers, payload)

            async def _wrap_stream():
                try:
                    for chunk in gen:
                        yield chunk
                finally:
                    if __event_emitter__:
                        await __event_emitter__(
                            {"type": "status", "data": {"description": "", "done": True}}
                        )

            return _wrap_stream()

        result = self._non_stream_response(headers, payload)

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

        User-set custom icons are preserved: only ``data:`` URLs (OWUI defaults)
        and our own provider-icon paths (``https://openrouter.ai/images/models/``
        — legacy — and ``https://openrouter.ai/images/icons/`` — current) are
        treated as managed/overwritable (see ``_is_owui_managed_icon``).  This is
        a best-effort operation — failures are silently logged.
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
            icon_url = _PROVIDER_ICONS.get(provider_key)
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
                            self._write_model_icon(
                                Models, ModelForm, ModelMeta, ModelParams,
                                db_model_id, existing, model, model_id, "",
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

                    # Proceed: icon is empty, an OWUI default, or one of our URLs.
                    # A model that was previously insert-exhausted is now in the
                    # DB (OWUI registered it) — clear that state and sync it.
                    self._icon_insert_exhausted.discard(model_id)
                    self._write_model_icon(
                        Models, ModelForm, ModelMeta, ModelParams,
                        db_model_id, existing, model, model_id, icon_url,
                    )
                else:
                    # Model not yet in DB — best-effort early insert.
                    # OWUI will register models after pipes() returns and may
                    # overwrite this record, so do NOT mark as synced here.
                    # The next cache-hit call to _sync_model_icons will find the
                    # model in DB and update it correctly.
                    # Cap insert attempts so a model OWUI never registers does
                    # not cause unbounded DB churn (PERF-3).  Track exhaustion in
                    # a SEPARATE set (not _icons_synced) so the model keeps being
                    # re-checked and a late OWUI registration is still picked up.
                    attempts = self._icon_insert_attempts.get(model_id, 0)
                    if attempts >= _MAX_ICON_INSERT_ATTEMPTS:
                        self._icon_insert_exhausted.add(model_id)
                        continue
                    self._icon_insert_attempts[model_id] = attempts + 1
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
    def _write_model_icon(
        Models, ModelForm, ModelMeta, ModelParams,
        db_model_id: str, existing, model: dict, model_id: str, icon_url: str,
    ) -> None:
        """Update an existing OWUI model record with a new ``profile_image_url``.

        Preserves the model's current ``name`` and ``params`` to avoid clobbering
        user-configured fields (temperature, system prompt, etc.).  Passing
        ``icon_url=""`` clears the existing icon.
        """
        existing_params = ModelParams()
        if hasattr(existing, "params") and existing.params:
            existing_params = existing.params
        name = (
            existing.name if hasattr(existing, "name")
            else model.get("name", model_id)
        )
        Models.update_model_by_id(
            db_model_id,
            ModelForm(
                id=db_model_id,
                name=name,
                meta=ModelMeta(profile_image_url=icon_url),
                params=existing_params,
            ),
        )

    @staticmethod
    def get_provider_icon(provider: str) -> Optional[str]:
        """Return icon URL for the given provider."""
        return _PROVIDER_ICONS.get(provider.lower())

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

    def _prepare_payload(self, body: dict) -> dict:
        """Sanitize OWUI internals and inject provider routing, reasoning, and fallbacks."""
        payload = copy.deepcopy(body)

        # Strip Open WebUI internal keys
        for key in _OWUI_INTERNAL_KEYS:
            payload.pop(key, None)

        # Open WebUI sends 'user' as dict; OpenRouter expects a string
        if isinstance(payload.get("user"), dict):
            payload.pop("user", None)

        # Fix model ID (strip manifold prefix)
        model = payload.get("model")
        if model:
            payload["model"] = self._clean_model_id(model)

        # --- Reasoning ---
        if self.valves.INCLUDE_REASONING:
            payload["include_reasoning"] = True

        effort = self.valves.REASONING_EFFORT.strip().lower()
        if effort in ("low", "medium", "high"):
            payload["reasoning"] = {"effort": effort}

        # --- Provider routing ---
        provider: dict = {}

        sort_val = self.valves.PROVIDER_SORT.strip().lower()
        if sort_val in ("price", "throughput", "latency"):
            provider["sort"] = sort_val

        order = self._parse_csv(self.valves.PROVIDER_ORDER)
        if order:
            provider["order"] = order

        ignore = self._parse_csv(self.valves.PROVIDER_IGNORE)
        if ignore:
            provider["ignore"] = ignore

        if self.valves.REQUIRE_PARAMETERS:
            provider["require_parameters"] = True

        dc = self.valves.DATA_COLLECTION.strip().lower()
        if dc == "deny":
            provider["data_collection"] = "deny"

        if provider:
            payload["provider"] = provider

        # --- Fallback models ---
        fallbacks = self._parse_csv(self.valves.FALLBACK_MODELS)
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
        if self.valves.ENABLE_MIDDLE_OUT:
            payload["transforms"] = ["middle-out"]

        # --- Usage accounting ---
        # OpenRouter only emits the `usage` block (with `cost`) when the request
        # opts in via {"usage": {"include": true}}.  Without it, STREAMING
        # responses never carry usage, so SHOW_COST_INFO would render nothing.
        if self.valves.SHOW_COST_INFO:
            payload["usage"] = {"include": True}

        # --- Cache control (Anthropic) ---
        if self.valves.ENABLE_CACHE_CONTROL:
            self._inject_cache_control(payload)

        return payload

    def _inject_cache_control(self, payload: dict) -> None:
        """Inject Anthropic cache_control on the longest text chunk.

        Applies to the first matching role (system, then user) with list-type
        content. Only one chunk is tagged ('first match wins') to avoid
        excessive cache entries.
        """
        try:
            messages = payload.get("messages", [])
            for role in ("system", "user"):
                for message in (msg for msg in messages if msg.get("role") == role):
                    content = message.get("content")
                    if not isinstance(content, list):
                        continue
                    longest_idx, longest_len = -1, -1
                    for idx, chunk in enumerate(content):
                        # Multimodal content parts are dicts; a bare string part
                        # has no .get — skip it rather than aborting the whole
                        # cache-control pass via the broad except.
                        if not isinstance(chunk, dict) or chunk.get("type") != "text":
                            continue
                        length = len(chunk.get("text", ""))
                        if length > longest_len:
                            longest_idx, longest_len = idx, length
                    if longest_idx >= 0:
                        content[longest_idx]["cache_control"] = {"type": "ephemeral"}
                        return
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] cache_control not applied: {exc}")

    def _build_headers(self, include_content_type: bool = True) -> dict:
        """Build HTTP headers for OpenRouter API requests."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": self._referer,
            "X-Title": self._title,
        }
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _non_stream_response(self, headers: dict, payload: dict) -> str:
        """Send a non-streaming request and return the formatted response."""
        try:
            response = self._retryable_request(headers, payload, stream=False)
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
            choice = res["choices"][0]
            message = choice.get("message", {})
            citations = res.get("citations", [])

            reasoning = _insert_citations(message.get("reasoning", ""), citations)
            content = _insert_citations(message.get("content") or "", citations)
            rendered_citations = _format_citation_list(citations)

            # Audio output: show transcript when the model returns audio instead of text
            audio_obj = message.get("audio") or {}
            if audio_obj and not content:
                transcript = audio_obj.get("transcript", "")
                raw = transcript or "*[Audio response — transcript not available.]*"
                content = _insert_citations(raw, citations)

            # Image output: render generated images as markdown.
            # Some image-gen models (e.g. FLUX via OpenRouter) return the image
            # as message.content (a bare URL or data:image/ URI) rather than
            # message.images.  Detect and convert so OWUI renders the image.
            image_md = _format_image_output(message.get("images") or [])
            if not image_md and _looks_like_image_content(content):
                image_md = f"![Generated image]({_md_escape_url(content.strip())})"
                content = ""

            final_parts = []
            if reasoning:
                final_parts.append(f"<think>\n{reasoning}\n</think>\n")
            if content:
                final_parts.append(content)
            if image_md:
                # Ensure a blank line before the image when there is preceding text
                prefix = "\n\n" if final_parts else ""
                final_parts.append(prefix + image_md)

            # Show which fallback model actually responded
            actual_model = res.get("model", "")
            requested_model = payload.get("model", "")
            if (
                payload.get("models")
                and actual_model
                and actual_model != requested_model
            ):
                final_parts.append(f"\n\n---\n*Responded by: {actual_model}*")

            if rendered_citations:
                final_parts.append(rendered_citations)

            if self.valves.SHOW_COST_INFO:
                cost_info = _format_cost_info(res.get("usage", {}), self.valves.COST_CURRENCY)
                if cost_info:
                    final_parts.append(cost_info)

            return "".join(final_parts)
        except requests.exceptions.Timeout:
            return f"OpenRouter Error: Request timed out after {self.valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
        except requests.exceptions.HTTPError as exc:
            return self._format_http_error(exc)
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Non-stream response error: {exc}")
            traceback.print_exc()
            return f"OpenRouter Error: {exc}"

    def _stream_response(
        self, headers: dict, payload: dict
    ) -> Generator[str, None, None]:
        """Stream SSE chunks with <think> block management and mid-stream error recovery."""
        response = None
        in_think = False
        latest_citations: List[str] = []
        latest_usage: dict = {}

        def _close_think_tag():
            nonlocal in_think
            if in_think:
                in_think = False
                return "\n</think>\n"
            return ""

        try:
            response = self._retryable_request(headers, payload, stream=True)
            for raw_line in response.iter_lines():
                # SSE spec allows both "data: x" and "data:x" (the optional
                # leading space is stripped).  Accept either form.
                if not raw_line or not raw_line.startswith(b"data:"):
                    continue
                data = raw_line[len(b"data:"):].lstrip(b" ").decode("utf-8")
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
                    # Image-gen models (e.g. FLUX) may stream the image URL as
                    # a single content chunk.  Convert to markdown so OWUI renders it.
                    if _looks_like_image_content(content):
                        yield f"![Generated image]({_md_escape_url(content.strip())})"
                    else:
                        yield _insert_citations(content, latest_citations)

            # Close <think> if still open
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            rendered_citations = _format_citation_list(latest_citations)
            if rendered_citations:
                yield rendered_citations

            if self.valves.SHOW_COST_INFO:
                cost_info = _format_cost_info(latest_usage, self.valves.COST_CURRENCY)
                if cost_info:
                    yield cost_info
        except requests.exceptions.Timeout:
            close_tag = _close_think_tag()
            if close_tag:
                yield close_tag
            yield f"OpenRouter Error: Request timed out after {self.valves.REQUEST_TIMEOUT}s. Try increasing REQUEST_TIMEOUT or retry."
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

    def _retryable_request(
        self, headers: dict, payload: dict, stream: bool
    ) -> requests.Response:
        """Send a POST request with automatic retry and exponential backoff.

        Retries on transient conditions:
          * ``requests.Timeout`` / ``requests.ConnectionError`` — network blip
          * HTTP 502 / 503 / 504 — upstream provider hiccup (retryable per RFC)
          * HTTP 429 — rate limited (honors ``Retry-After`` if present)
        HTTP 4xx (except 429) is permanent and raised immediately.
        """
        for attempt in range(self.valves.MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                    timeout=self.valves.REQUEST_TIMEOUT,
                    stream=stream,
                    allow_redirects=False,
                )
                if response.status_code in _RETRYABLE_STATUS and attempt < self.valves.MAX_RETRIES:
                    retry_after = self._parse_retry_after(response)
                    print(
                        f"[OpenRouter Pipe] Attempt {attempt + 1}: HTTP "
                        f"{response.status_code}, retrying in {retry_after:.1f}s"
                    )
                    try:
                        response.close()
                    except Exception:
                        pass
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                print(f"[OpenRouter Pipe] Attempt {attempt + 1} failed: {exc}")
                if attempt == self.valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
            except requests.exceptions.HTTPError:
                raise
            except Exception as exc:  # pragma: no cover
                print(f"[OpenRouter Pipe] Unexpected error: {exc}")
                if attempt == self.valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
        # Loop exhausted without return — every path above either returns,
        # raises, or continues; this final raise is defensive only.
        raise RuntimeError("OpenRouter Error: request not completed")  # pragma: no cover

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff with proportional jitter, capped at _BACKOFF_CAP_S."""
        return min((2 ** attempt) * (0.5 + random.random()), _BACKOFF_CAP_S)

    @staticmethod
    def _parse_retry_after(response: requests.Response) -> float:
        """Parse the ``Retry-After`` header.

        Falls back to exponential backoff when the header is missing or
        unparseable.  Caps at _BACKOFF_CAP_S to avoid extreme waits from
        misbehaving upstreams.
        """
        raw = response.headers.get("Retry-After", "")
        if raw:
            try:
                return min(max(float(raw), 0.0), _BACKOFF_CAP_S)
            except ValueError:
                pass
        return min(2 + random.uniform(0, 1), _BACKOFF_CAP_S)

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
