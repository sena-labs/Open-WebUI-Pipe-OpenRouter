"""
title: OpenRouter Pipe
author: Sena Labs
author_url: https://github.com/sena-labs
funding_url: https://github.com/sponsors/sena-labs
version: 1.2.0
license: MIT
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNmQyOGQ5Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjYTc4YmZhIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIHJ4PSIyMCIgZmlsbD0idXJsKCNiZykiLz48cGF0aCBkPSJNMjAgNTAgQzIwIDMwLCA0MCAzMCwgNTAgMzAgTDUwIDIyIEw2OCA0MCBMNTAgNTggTDUwIDUwIEM0MCA1MCwgMzUgNDUsIDMwIDUwIEMyNSA1NSwgMjAgNzAsIDIwIDUwIFoiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSIzMCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxjaXJjbGUgY3g9IjgyIiBjeT0iNTAiIHI9IjciIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSI3MCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxsaW5lIHgxPSI2OCIgeTE9IjQwIiB4Mj0iNzYiIHkyPSIzMiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBvcGFjaXR5PSIwLjUiLz48bGluZSB4MT0iNjgiIHkxPSI0MCIgeDI9Ijc2IiB5Mj0iNTAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC41Ii8+PGxpbmUgeDE9IjY4IiB5MT0iNDAiIHgyPSI3NiIgeTI9IjY4IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIG9wYWNpdHk9IjAuNSIvPjwvc3ZnPg==
required_open_webui_version: 0.4.0
requirements: requests>=2.20, pydantic>=2.0
description: Access 300+ AI models through OpenRouter directly inside Open WebUI. Features provider routing, reasoning tokens with <think> tags, full SSE streaming, model fallbacks, middle-out compression, Anthropic cache control, citations, 22 provider icons, and configurable retry logic.
"""

import copy
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

# Provider icons — synced into the Open WebUI Models database by
# _sync_model_icons() so the frontend can serve them via
# /models/model/profile/image.  Disable with SYNC_PROVIDER_ICONS = False.
_PROVIDER_ICONS = {
    "openai": "https://openrouter.ai/images/models/openai.svg",
    "anthropic": "https://openrouter.ai/images/models/anthropic.svg",
    "google": "https://openrouter.ai/images/models/google.svg",
    "meta-llama": "https://openrouter.ai/images/models/meta.svg",
    "mistralai": "https://openrouter.ai/images/models/mistralai.svg",
    "amazon": "https://openrouter.ai/images/models/amazon.svg",
    "deepseek": "https://openrouter.ai/images/models/deepseek.svg",
    "x-ai": "https://openrouter.ai/images/models/xai.svg",
    "cohere": "https://openrouter.ai/images/models/cohere.svg",
    "perplexity": "https://openrouter.ai/images/models/perplexity.svg",
    "allenai": "https://openrouter.ai/images/models/allenai.svg",
    "qwen": "https://openrouter.ai/images/models/qwen.svg",
    "nvidia": "https://openrouter.ai/images/models/nvidia.svg",
    "databricks": "https://openrouter.ai/images/models/databricks.svg",
    "microsoft": "https://openrouter.ai/images/models/microsoft.svg",
    "together": "https://openrouter.ai/images/models/together.svg",
    "fireworks": "https://openrouter.ai/images/models/fireworks.svg",
    "sambanova": "https://openrouter.ai/images/models/sambanova.svg",
    "cerebras": "https://openrouter.ai/images/models/cerebras.svg",
    "groq": "https://openrouter.ai/images/models/groq.svg",
    "inflection": "https://openrouter.ai/images/models/inflection.svg",
    "01-ai": "https://openrouter.ai/images/models/01ai.svg",
}


def _is_safe_url(url: str) -> bool:
    """Return True only for http:// and https:// URLs."""
    return isinstance(url, str) and url.lower().startswith(("http://", "https://"))


def _is_owui_managed_icon(url: str) -> bool:
    """Return True if the icon URL was set by OWUI or our sync logic.

    data: URLs are the pipe's own SVG icon that OWUI assigns as default to all
    manifold child models.  openrouter.ai/images/models/ URLs are the provider
    icons we write.  Any other URL is assumed to be a user-set custom icon and
    must not be overwritten.
    """
    return (
        not url
        or url.startswith("data:")
        or url.startswith("https://openrouter.ai/images/models/")
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


def _format_citation_list(citations: Optional[List[str]]) -> str:
    if not citations:
        return ""
    try:
        rendered = "\n".join(f"{idx + 1}. {url}" for idx, url in enumerate(citations))
        return f"\n\n---\nCitations:\n{rendered}"
    except Exception as exc:  # pragma: no cover
        print(f"[OpenRouter Pipe] Citation formatting error: {exc}")
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

        @field_validator("OPENROUTER_BASE_URL")
        @classmethod
        def _validate_base_url(cls, v: str) -> str:
            v = v.strip()
            if not v.startswith(("https://", "http://")):
                raise ValueError("Base URL must start with https:// or http://")
            return v

    def __init__(self) -> None:
        self.type = "manifold"
        self.valves = self.Valves()
        self._session = requests.Session()
        # Cache env vars that don't change at runtime
        self._referer = os.getenv("WEBUI_URL", "http://localhost:3000")
        self._title = os.getenv("WEBUI_NAME", "OpenWebUI")
        # Model list cache
        self._models_cache: Optional[List[dict]] = None
        self._models_cache_ts: float = 0.0
        self._models_cache_key: str = ""
        # Track which model IDs already have icons synced (avoids repeated DB writes)
        self._icons_synced: set = set()
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

    def _models_cache_valid(self) -> bool:
        """Check if the cached model list is still valid."""
        if not self._models_cache:
            return False
        key = f"{self.valves.OPENROUTER_API_KEY}|{self.valves.FREE_ONLY}|{self.valves.MODEL_PROVIDERS}|{self.valves.INVERT_PROVIDER_LIST}|{self.valves.MODEL_PREFIX}"
        if key != self._models_cache_key:
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

        headers = self._build_headers(include_content_type=False)
        response = None
        try:
            response = self._session.get(
                self.models_url, headers=headers, timeout=self.valves.REQUEST_TIMEOUT
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
            msg = f"HTTP {exc.response.status_code} fetching models"
            try:
                err = exc.response.json().get("error", {})
                detail = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                if detail:
                    msg += f": {detail}"
            except Exception:
                pass
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

            # Split model_id once for provider extraction
            parts = model_id.split("/", 1)
            provider_key = parts[0].lower() if len(parts) > 1 else "openrouter"

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
        self._models_cache_key = f"{self.valves.OPENROUTER_API_KEY}|{self.valves.FREE_ONLY}|{self.valves.MODEL_PROVIDERS}|{self.valves.INVERT_PROVIDER_LIST}|{self.valves.MODEL_PREFIX}"

        # Sync provider icons into Open WebUI's Models database
        if self.valves.SYNC_PROVIDER_ICONS:
            self._sync_model_icons(models)

        return models

    @staticmethod
    def _clean_model_id(model_id: str) -> str:
        """Strip the manifold prefix from a model ID."""
        if "." in model_id:
            return model_id.split(".", 1)[-1]
        return model_id

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
    ) -> Union[str, Generator[str, None, None], AsyncGenerator[str, None]]:
        """Route a chat completion request to OpenRouter (stream or non-stream).

        Returns an async generator for streaming (allows proper status cleanup),
        or a plain string for non-streaming responses.
        """
        if not self.valves.OPENROUTER_API_KEY:
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

        payload = self._prepare_payload(body)
        headers = self._build_headers()
        stream = body.get("stream", False)

        if stream:
            gen = self._stream_response(headers, payload)

            # Wrap in an async generator so we can await the done event
            if __event_emitter__:
                async def _wrap_stream():
                    try:
                        for chunk in gen:
                            yield chunk
                    finally:
                        await __event_emitter__(
                            {"type": "status", "data": {"description": "", "done": True}}
                        )
                return _wrap_stream()

            return gen

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

            # Determine provider icon
            parts = model_id.split("/", 1)
            provider_key = parts[0].lower() if len(parts) > 1 else ""
            icon_url = _PROVIDER_ICONS.get(provider_key)
            if not icon_url:
                self._icons_synced.add(model_id)
                continue

            # Build the prefixed ID that Open WebUI uses in the frontend
            db_model_id = f"{function_id}.{model_id}"

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
        user_field = payload.get("user")
        if isinstance(user_field, dict):
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
                        if chunk.get("type") != "text":
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
            "Authorization": f"Bearer {self.valves.OPENROUTER_API_KEY}",
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
            content = _insert_citations(message.get("content", ""), citations)
            rendered_citations = _format_citation_list(citations)

            final_parts = []
            if reasoning:
                final_parts.append(f"<think>\n{reasoning}\n</think>\n")
            if content:
                final_parts.append(content)

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

        def _close_think_tag():
            nonlocal in_think
            if in_think:
                in_think = False
                return "\n</think>\n"
            return ""

        try:
            response = self._retryable_request(headers, payload, stream=True)
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

                citations = chunk.get("citations")
                if citations is not None:
                    latest_citations = citations

                choices = chunk.get("choices") or []
                first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                delta = first_choice.get("delta", {})
                reasoning = delta.get("reasoning", "")
                content = delta.get("content", "")

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

    def _retryable_request(self, headers: dict, payload: dict, stream: bool):
        """Send a POST request with automatic retry and exponential backoff."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.valves.MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                    timeout=self.valves.REQUEST_TIMEOUT,
                    stream=stream,
                )
                response.raise_for_status()
                return response
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                last_exc = exc
                print(f"[OpenRouter Pipe] Attempt {attempt + 1} failed: {exc}")
                if attempt == self.valves.MAX_RETRIES:
                    raise
                # Exponential backoff with jitter
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                time.sleep(delay)
            except requests.exceptions.HTTPError:
                raise
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                print(f"[OpenRouter Pipe] Unexpected error: {exc}")
                if attempt == self.valves.MAX_RETRIES:
                    raise
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                time.sleep(delay)
        if last_exc:
            raise last_exc  # pragma: no cover
        raise RuntimeError("OpenRouter Error: request not completed")  # pragma: no cover

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
