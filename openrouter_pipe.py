"""
title: OpenRouter Pipe
author: Sena Labs
author_url: https://github.com/sena-labs
funding_url: https://github.com/sponsors/sena-labs
version: 0.2.0
license: MIT
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNmQyOGQ5Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjYTc4YmZhIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIHJ4PSIyMCIgZmlsbD0idXJsKCNiZykiLz48cGF0aCBkPSJNMjAgNTAgQzIwIDMwLCA0MCAzMCwgNTAgMzAgTDUwIDIyIEw2OCA0MCBMNTAgNTggTDUwIDUwIEM0MCA1MCwgMzUgNDUsIDMwIDUwIEMyNSA1NSwgMjAgNzAsIDIwIDUwIFoiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSIzMCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxjaXJjbGUgY3g9IjgyIiBjeT0iNTAiIHI9IjciIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjk1Ii8+PGNpcmNsZSBjeD0iNzgiIGN5PSI3MCIgcj0iNyIgZmlsbD0id2hpdGUiIG9wYWNpdHk9IjAuOCIvPjxsaW5lIHgxPSI2OCIgeTE9IjQwIiB4Mj0iNzYiIHkyPSIzMiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBvcGFjaXR5PSIwLjUiLz48bGluZSB4MT0iNjgiIHkxPSI0MCIgeDI9Ijc2IiB5Mj0iNTAiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgb3BhY2l0eT0iMC41Ii8+PGxpbmUgeDE9IjY4IiB5MT0iNDAiIHgyPSI3NiIgeTI9IjY4IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIG9wYWNpdHk9IjAuNSIvPjwvc3ZnPg==
required_open_webui_version: 0.4.0
requirements: requests, pydantic
description: Access 300+ AI models through OpenRouter directly inside Open WebUI. Features provider routing, reasoning tokens with <think> tags, full SSE streaming, model fallbacks, middle-out compression, Anthropic cache control, citations, 22 provider icons, and configurable retry logic.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from typing import Generator, List, Optional, Union

import requests
from pydantic import BaseModel, Field

# Keys injected by Open WebUI internals — must not be forwarded to OpenRouter
_OWUI_INTERNAL_KEYS = frozenset(
    {"chat_id", "title", "task", "task_id", "features", "citations"}
)


def _insert_citations(text: str, citations: Optional[List[str]]) -> str:
    """Replace [n] references with markdown links."""
    if not citations or not text:
        return text

    pattern = r"\[(\d+)\]"

    def _replace(match_obj):
        try:
            idx = int(match_obj.group(1)) - 1
            if 0 <= idx < len(citations):
                return f"[[{idx + 1}]]({citations[idx]})"
        except (ValueError, IndexError):
            pass
        return match_obj.group(0)

    try:
        return re.sub(pattern, _replace, text)
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
        )
        OPENROUTER_BASE_URL: str = Field(
            default=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            description="OpenRouter base endpoint",
        )
        REASONING_EFFORT: str = Field(
            default=os.getenv("OPENROUTER_REASONING_EFFORT", ""),
            description="Reasoning effort: empty=disabled, low, medium, high",
        )
        INCLUDE_REASONING: bool = Field(
            default=os.getenv("OPENROUTER_INCLUDE_REASONING", "true").lower() == "true",
            description="Request reasoning tokens (shows <think> blocks)",
        )
        MODEL_PREFIX: Optional[str] = Field(
            default=None, description="Prefix shown in model names"
        )
        MODEL_PROVIDERS: Optional[str] = Field(
            default=os.getenv("OPENROUTER_MODEL_PROVIDERS"),
            description="Comma-separated provider list to filter models",
        )
        INVERT_PROVIDER_LIST: bool = Field(
            default=os.getenv("OPENROUTER_INVERT_PROVIDER_LIST", "false").lower()
            == "true",
            description="When true the provider list becomes an exclusion list",
        )
        FREE_ONLY: bool = Field(
            default=os.getenv("OPENROUTER_FREE_ONLY", "false").lower() == "true",
            description="Show only free-tier models",
        )
        PROVIDER_SORT: str = Field(
            default=os.getenv("OPENROUTER_PROVIDER_SORT", ""),
            description="Provider sort order: empty=default, price, throughput, latency",
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
            description="Only use providers that support all request parameters",
        )
        DATA_COLLECTION: str = Field(
            default=os.getenv("OPENROUTER_DATA_COLLECTION", "allow"),
            description="Provider data collection policy: allow or deny",
        )
        FALLBACK_MODELS: str = Field(
            default=os.getenv("OPENROUTER_FALLBACK_MODELS", ""),
            description="Fallback model IDs, comma-separated (e.g. openai/gpt-4o,anthropic/claude-3.5-sonnet)",
        )
        ENABLE_MIDDLE_OUT: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_MIDDLE_OUT", "false").lower()
            == "true",
            description="Middle-out compression for prompts exceeding context window",
        )
        ENABLE_CACHE_CONTROL: bool = Field(
            default=os.getenv("OPENROUTER_ENABLE_CACHE_CONTROL", "false").lower()
            == "true",
            description="Inject cache_control on long messages (Anthropic)",
        )
        REQUEST_TIMEOUT: int = Field(
            default=int(os.getenv("OPENROUTER_REQUEST_TIMEOUT", "90")),
            gt=0,
            description="API request timeout in seconds",
        )
        MAX_RETRIES: int = Field(
            default=2, ge=0, description="Auto-retries on transient errors"
        )

    def __init__(self) -> None:
        self.type = "manifold"
        self.valves = self.Valves()
        if not self.valves.OPENROUTER_API_KEY:
            print("[OpenRouter Pipe] Warning: OPENROUTER_API_KEY not set")

    @property
    def models_url(self) -> str:
        return f"{self.valves.OPENROUTER_BASE_URL.rstrip('/')}/models"

    @property
    def chat_url(self) -> str:
        return f"{self.valves.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"

    def pipes(self) -> List[dict]:
        if not self.valves.OPENROUTER_API_KEY:
            return [{"id": "error", "name": "OpenRouter API key not configured"}]

        headers = self._build_headers(include_content_type=False)
        try:
            response = requests.get(
                self.models_url, headers=headers, timeout=self.valves.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json().get("data", [])
        except requests.exceptions.Timeout:
            return [{"id": "error", "name": "Timeout fetching models"}]
        except requests.exceptions.HTTPError as exc:
            msg = f"HTTP {exc.response.status_code} fetching models"
            try:
                detail = exc.response.json().get("error", {}).get("message", "")
                if detail:
                    msg += f": {detail}"
            except Exception:
                pass
            print(f"[OpenRouter Pipe] {msg}")
            return [{"id": "error", "name": msg}]
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Model fetch error: {exc}")
            traceback.print_exc()
            return [{"id": "error", "name": f"Unexpected error: {exc}"}]

        provider_filter = self._parse_provider_filter()
        prefix = self.valves.MODEL_PREFIX or ""
        models: List[dict] = []

        for model in data:
            model_id = model.get("id")
            if not model_id:
                continue

            if self.valves.FREE_ONLY and ":free" not in model_id.lower():
                continue

            if provider_filter:
                provider = model_id.split("/", 1)[0].lower()
                keep = (provider in provider_filter) ^ self.valves.INVERT_PROVIDER_LIST
                if not keep:
                    continue

            model_name = model.get("name", model_id)
            provider = model_id.split("/", 1)[0] if "/" in model_id else "openrouter"
            icon_url = self._get_provider_icon(provider)

            model_dict = {
                "id": model_id,
                "name": f"{prefix}{model_name}",
                "info": {"meta": {"profile_image_url": icon_url or ""}},
            }

            models.append(model_dict)

        if not models:
            error_text = "No models found"
            if self.valves.FREE_ONLY:
                error_text = "No free models available"
            elif provider_filter:
                error_text = "No models match the specified providers"
            return [{"id": "error", "name": error_text}]

        return models

    async def pipe(
        self, body: dict, __user__: Optional[dict] = None
    ) -> Union[str, Generator[str, None, None]]:
        if not self.valves.OPENROUTER_API_KEY:
            return "OpenRouter Pipe Error: OPENROUTER_API_KEY not configured"

        payload = self._prepare_payload(body)
        headers = self._build_headers()
        stream = body.get("stream", False)

        if stream:
            return self._stream_response(headers, payload)
        return self._non_stream_response(headers, payload)

    def _get_provider_icon(self, provider: str) -> Optional[str]:
        """Return icon URL for the given provider."""
        provider_icons = {
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
        return provider_icons.get(provider.lower())

    def _parse_provider_filter(self) -> Optional[set]:
        if not self.valves.MODEL_PROVIDERS:
            return None
        return {
            provider.strip().lower()
            for provider in self.valves.MODEL_PROVIDERS.split(",")
            if provider.strip()
        }

    @staticmethod
    def _parse_csv(value: str) -> List[str]:
        """Parse a comma-separated string into a list, skipping empty items."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _prepare_payload(self, body: dict) -> dict:
        payload = body.copy()

        # Strip Open WebUI internal keys
        for key in _OWUI_INTERNAL_KEYS:
            payload.pop(key, None)

        # Open WebUI sends 'user' as dict; OpenRouter expects a string
        user_field = payload.get("user")
        if isinstance(user_field, dict):
            payload.pop("user", None)

        # Fix model ID (strip manifold prefix)
        model = payload.get("model")
        if model and "." in model:
            payload["model"] = model.split(".", 1)[-1]

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
            payload["models"] = fallbacks

        # --- Transforms (middle-out) ---
        if self.valves.ENABLE_MIDDLE_OUT:
            payload["transforms"] = ["middle-out"]

        # --- Cache control (Anthropic) ---
        if self.valves.ENABLE_CACHE_CONTROL:
            self._inject_cache_control(payload)

        return payload

    def _inject_cache_control(self, payload: dict) -> None:
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
        headers = {
            "Authorization": f"Bearer {self.valves.OPENROUTER_API_KEY}",
            "HTTP-Referer": os.getenv("WEBUI_URL", "http://localhost:3000"),
            "X-Title": os.getenv("WEBUI_NAME", "OpenWebUI"),
        }
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _non_stream_response(self, headers: dict, payload: dict) -> str:
        try:
            response = self._retryable_request(headers, payload, stream=False)
            res = response.json()

            # Handle API error in response body
            if "error" in res and not res.get("choices"):
                err = res["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"OpenRouter Pipe Error: {msg}"

            if not res.get("choices"):
                return ""
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
            if rendered_citations:
                final_parts.append(rendered_citations)
            return "".join(final_parts)
        except requests.exceptions.Timeout:
            return f"OpenRouter Pipe Error: timeout {self.valves.REQUEST_TIMEOUT}s"
        except requests.exceptions.HTTPError as exc:
            return self._format_http_error(exc)
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Non-stream response error: {exc}")
            traceback.print_exc()
            return f"OpenRouter Pipe Error: {exc}"

    def _stream_response(
        self, headers: dict, payload: dict
    ) -> Generator[str, None, None]:
        response = None
        in_think = False
        latest_citations: List[str] = []
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
                    if in_think:
                        yield "\n</think>\n"
                        in_think = False
                    yield f"\n\nOpenRouter Pipe Error: {msg}"
                    return

                citations = chunk.get("citations")
                if citations is not None:
                    latest_citations = citations

                delta = chunk.get("choices", [{}])[0].get("delta", {})
                reasoning = delta.get("reasoning", "")
                content = delta.get("content", "")

                if reasoning:
                    if not in_think:
                        yield "<think>\n"
                        in_think = True
                    yield _insert_citations(reasoning, latest_citations)

                if content:
                    if in_think:
                        yield "\n</think>\n"
                        in_think = False
                    yield _insert_citations(content, latest_citations)

            # Close <think> if still open
            if in_think:
                yield "\n</think>\n"
            rendered_citations = _format_citation_list(latest_citations)
            if rendered_citations:
                yield rendered_citations
        except requests.exceptions.Timeout:
            yield f"OpenRouter Pipe Error: timeout {self.valves.REQUEST_TIMEOUT}s"
        except requests.exceptions.HTTPError as exc:
            yield self._format_http_error(exc)
        except Exception as exc:  # pragma: no cover
            print(f"[OpenRouter Pipe] Stream error: {exc}")
            traceback.print_exc()
            yield f"OpenRouter Pipe Error: {exc}"
        finally:
            if response is not None:
                response.close()

    def _retryable_request(self, headers: dict, payload: dict, stream: bool):
        last_exc: Optional[Exception] = None
        for attempt in range(self.valves.MAX_RETRIES + 1):
            try:
                response = requests.post(
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
            except requests.exceptions.HTTPError:
                raise
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                print(f"[OpenRouter Pipe] Unexpected error: {exc}")
                if attempt == self.valves.MAX_RETRIES:
                    raise
        if last_exc:
            raise last_exc  # pragma: no cover
        raise RuntimeError("OpenRouter Pipe Error: request not completed")

    def _format_http_error(self, exc: requests.exceptions.HTTPError) -> str:
        status = exc.response.status_code if exc.response is not None else "?"
        base = f"OpenRouter Pipe Error: HTTP {status}"
        try:
            detail = exc.response.json().get("error", {}).get("message", "")
            if detail:
                base += f" - {detail}"
        except Exception:
            pass
        return base


__all__ = ["Pipe"]
