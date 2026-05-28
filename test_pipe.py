"""
Comprehensive test suite for OpenRouter Pipe v1.3.0
Runs with: python test_pipe.py

Author: Sena Labs (https://github.com/sena-labs)
License: MIT
Copyright (c) 2026 Sena Labs
"""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
from types import ModuleType
from typing import List
from unittest.mock import MagicMock, patch

# Ensure UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

# ── Load the pipe module ──────────────────────────────────────────────────────
_PIPE_PATH = os.path.join(os.path.dirname(__file__), "openrouter_pipe.py")
_loader = importlib.machinery.SourceFileLoader("openrouter_pipe", _PIPE_PATH)
spec = importlib.util.spec_from_loader("openrouter_pipe", _loader, origin=_PIPE_PATH)
assert spec is not None and spec.loader is not None
mod: ModuleType = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.modules["openrouter_pipe"] = mod

Pipe = mod.Pipe
_insert_citations = mod._insert_citations
_format_citation_list = mod._format_citation_list
_OWUI_INTERNAL_KEYS = mod._OWUI_INTERNAL_KEYS
_is_owui_managed_icon = mod._is_owui_managed_icon
_PROVIDER_REGISTRY_TTL = mod._PROVIDER_REGISTRY_TTL
_PROVIDER_REGISTRY_FAIL_TTL = mod._PROVIDER_REGISTRY_FAIL_TTL
EncryptedStr = mod.EncryptedStr

# ── Helpers ───────────────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0


def _assert(condition: bool, msg: str):
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ✓ {msg}")
    else:
        _FAIL += 1
        print(f"  ✗ FAIL: {msg}")


def _section(title: str):
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


# ── 1. Helper functions ──────────────────────────────────────────────────────

_section("1. _insert_citations()")

_assert(_insert_citations("", None) == "", "empty text + None citations → empty")
_assert(_insert_citations("", []) == "", "empty text + empty list → empty")
_assert(_insert_citations("Hello", None) == "Hello", "text + None → unchanged")
_assert(_insert_citations("Hello", []) == "Hello", "text + empty → unchanged")

citations = ["https://a.com", "https://b.com"]
_assert(
    _insert_citations("See [1] and [2].", citations)
    == "See [[1]](https://a.com) and [[2]](https://b.com).",
    "replaces [1] and [2] correctly",
)
_assert(
    _insert_citations("See [3].", citations) == "See [3].",
    "out-of-range index left unchanged",
)
_assert(
    _insert_citations("No refs here.", citations) == "No refs here.",
    "text without refs unchanged",
)

_section("1b. _format_citation_list()")

_assert(_format_citation_list(None) == "", "None → empty")
_assert(_format_citation_list([]) == "", "empty → empty")
result = _format_citation_list(["https://a.com", "https://b.com"])
_assert("1. https://a.com" in result, "first citation present")
_assert("2. https://b.com" in result, "second citation present")
_assert(result.startswith("\n\n---"), "starts with separator")

# ── 2. _parse_csv ────────────────────────────────────────────────────────────

_section("2. Pipe._parse_csv()")

_assert(Pipe._parse_csv("") == [], "empty → empty list")
_assert(Pipe._parse_csv("a, b , c") == ["a", "b", "c"], "trims whitespace")
_assert(Pipe._parse_csv("a,,b,") == ["a", "b"], "skips empty elements")
_assert(Pipe._parse_csv("single") == ["single"], "single element")

# ── 3. Valves ────────────────────────────────────────────────────────────────

_section("3. Valves defaults")

# Temporarily clear env vars that might interfere
_env_backup = {}
for k in [
    "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL",
    "OPENROUTER_REASONING_EFFORT", "OPENROUTER_INCLUDE_REASONING",
    "OPENROUTER_MODEL_PROVIDERS", "OPENROUTER_INVERT_PROVIDER_LIST",
    "OPENROUTER_FREE_MODEL_FILTER", "OPENROUTER_PROVIDER_SORT",
    "OPENROUTER_PROVIDER_ORDER", "OPENROUTER_PROVIDER_IGNORE",
    "OPENROUTER_REQUIRE_PARAMETERS", "OPENROUTER_DATA_COLLECTION",
    "OPENROUTER_FALLBACK_MODELS", "OPENROUTER_ENABLE_MIDDLE_OUT",
    "OPENROUTER_ENABLE_CACHE_CONTROL", "OPENROUTER_REQUEST_TIMEOUT",
    "OPENROUTER_OUTPUT_MODALITIES",
]:
    _env_backup[k] = os.environ.pop(k, None)

v = Pipe.Valves()
# The default is os.getenv() evaluated at class-definition time (module load);
# if the env var was set at that point, the default is non-empty — by design.
frozen_default = Pipe.Valves.model_fields["OPENROUTER_API_KEY"].default
_assert(v.OPENROUTER_API_KEY == frozen_default, "API key default matches frozen class default")
_assert(v.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1", "base URL default")
_assert(v.REASONING_EFFORT == "", "reasoning effort empty")
_assert(v.INCLUDE_REASONING is True, "include_reasoning True by default")
_assert(v.MODEL_PREFIX is None, "prefix None by default")
_assert(v.MODEL_PROVIDERS == "ALL", "MODEL_PROVIDERS default is ALL")
_assert(v.FREE_MODEL_FILTER == "all", "FREE_MODEL_FILTER default is 'all'")
_assert(v.TOOL_CALLING_FILTER == "all", "TOOL_CALLING_FILTER default is 'all'")
_assert(v.MODEL_VARIANTS == "", "MODEL_VARIANTS default empty")
_assert(v.ZDR_MODELS_ONLY is False, "ZDR_MODELS_ONLY default False")
_assert(v.ZDR_ENFORCE is False, "ZDR_ENFORCE default False")
_assert(v.REASONING_SUMMARY_MODE == "disabled", "REASONING_SUMMARY_MODE default 'disabled'")
_assert(v.ENABLE_ANTHROPIC_INTERLEAVED_THINKING is True, "interleaved thinking default True")
_assert(v.ANTHROPIC_PROMPT_CACHE_TTL == "5m", "ANTHROPIC_PROMPT_CACHE_TTL default '5m'")
_assert(v.HTTP_REFERER_OVERRIDE == "", "HTTP_REFERER_OVERRIDE default empty")
_assert(v.PROVIDER_SORT == "", "PROVIDER_SORT empty")
_assert(v.PROVIDER_ORDER == "", "PROVIDER_ORDER empty")
_assert(v.PROVIDER_IGNORE == "", "PROVIDER_IGNORE empty")
_assert(v.REQUIRE_PARAMETERS is False, "REQUIRE_PARAMETERS false")
_assert(v.DATA_COLLECTION == "allow", "DATA_COLLECTION allow")
_assert(v.FALLBACK_MODELS == "", "FALLBACK_MODELS empty")
_assert(v.ENABLE_MIDDLE_OUT is False, "ENABLE_MIDDLE_OUT false")
_assert(v.ENABLE_CACHE_CONTROL is False, "ENABLE_CACHE_CONTROL false")
_assert(v.REQUEST_TIMEOUT == 90, "REQUEST_TIMEOUT 90")
_assert(v.MAX_RETRIES == 2, "MAX_RETRIES 2")
_assert(v.SHOW_COST_INFO is False, "SHOW_COST_INFO false by default")
_assert(v.COST_CURRENCY == "USD", "COST_CURRENCY USD by default")
_assert(v.OUTPUT_MODALITIES == "all", "OUTPUT_MODALITIES default 'all' (full catalog)")

try:
    Pipe.Valves(REQUEST_TIMEOUT=-1)
    _assert(False, "REQUEST_TIMEOUT negative should fail validation")
except Exception:
    _assert(True, "REQUEST_TIMEOUT negative raises validation error")

# Restore env
for k, val in _env_backup.items():
    if val is not None:
        os.environ[k] = val

# ── 4. Pipe.__init__ ─────────────────────────────────────────────────────────

_section("4. Pipe.__init__()")

pipe = Pipe()
_assert(pipe.type == "manifold", "type is manifold")
_assert(pipe.models_url.endswith("/models"), "models_url ends with /models")
_assert(pipe.chat_url.endswith("/chat/completions"), "chat_url ends with /chat/completions")

# ── 5. _prepare_payload ──────────────────────────────────────────────────────

_section("5. _prepare_payload()")

pipe = Pipe()
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key",
    INCLUDE_REASONING=True,
    REASONING_EFFORT="high",
    PROVIDER_SORT="price",
    PROVIDER_ORDER="anthropic, openai",
    PROVIDER_IGNORE="google",
    REQUIRE_PARAMETERS=True,
    DATA_COLLECTION="deny",
    FALLBACK_MODELS="openai/gpt-4o, anthropic/claude-3.5-sonnet",
    ENABLE_MIDDLE_OUT=True,
    ENABLE_CACHE_CONTROL=False,
)

body = {
    "model": "openrouter.google/gemini-2.0-flash-exp",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": True,
    # OWUI internal keys
    "chat_id": "abc123",
    "title": "Test Chat",
    "task": "chat",
    "task_id": "tid1",
    "features": {"web_search": True},
    "citations": True,
    "metadata": {"session_id": "s1"},
    "files": [{"id": "f1"}],
    "tool_ids": ["tool1"],
    "session_id": "s1",
    "message_id": "m1",
    # user as dict (OWUI sends this)
    "user": {"id": "u1", "name": "Tester"},
}

payload = pipe._prepare_payload(body, pipe.valves)

_assert("chat_id" not in payload, "chat_id stripped")
_assert("title" not in payload, "title stripped")
_assert("task" not in payload, "task stripped")
_assert("task_id" not in payload, "task_id stripped")
_assert("features" not in payload, "features stripped")
_assert("citations" not in payload, "citations (OWUI) stripped")
_assert("metadata" not in payload, "metadata stripped")
_assert("files" not in payload, "files stripped")
_assert("tool_ids" not in payload, "tool_ids stripped")
_assert("session_id" not in payload, "session_id stripped")
_assert("message_id" not in payload, "message_id stripped")
_assert("user" not in payload, "dict user stripped")
_assert(payload["model"] == "google/gemini-2.0-flash-exp", "model prefix removed")
_assert(payload.get("include_reasoning") is True, "include_reasoning set")
_assert(payload.get("reasoning") == {"effort": "high"}, "reasoning effort high")
_assert(payload["provider"]["sort"] == "price", "provider sort")
_assert(payload["provider"]["order"] == ["anthropic", "openai"], "provider order")
_assert(payload["provider"]["ignore"] == ["google"], "provider ignore")
_assert(payload["provider"]["require_parameters"] is True, "require_parameters")
_assert(payload["provider"]["data_collection"] == "deny", "data_collection deny")
_assert(
    payload["models"] == ["google/gemini-2.0-flash-exp", "openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
    "fallback models (primary first)",
)
_assert(payload["transforms"] == ["middle-out"], "middle-out transform")

# --- Test with minimal/no valves ---
pipe2 = Pipe()
pipe2.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    INCLUDE_REASONING=False,
    REASONING_EFFORT="",
)
body2 = {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}
payload2 = pipe2._prepare_payload(body2, pipe2.valves)
_assert("include_reasoning" not in payload2, "no include_reasoning when disabled")
_assert("reasoning" not in payload2, "no reasoning when effort empty")
_assert("provider" not in payload2, "no provider block when all empty")
_assert("models" not in payload2, "no models when no fallbacks")
_assert("transforms" not in payload2, "no transforms when middle-out disabled")

# ── 5b. _prepare_payload: user as string preserved ──
body3 = {"model": "openai/gpt-4o", "messages": [], "user": "string-user"}
payload3 = pipe2._prepare_payload(body3, pipe2.valves)
_assert(payload3.get("user") == "string-user", "string user preserved")

# ── 5c. model without dot (no prefix) ──
body4 = {"model": "openai/gpt-4o", "messages": []}
payload4 = pipe2._prepare_payload(body4, pipe2.valves)
_assert(payload4["model"] == "openai/gpt-4o", "model without dot left unchanged")

# ── 5d. Extended REASONING_EFFORT levels (minimal, xhigh) ──
_pipe5d = Pipe()
_pipe5d.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_EFFORT="minimal")
_p5d = _pipe5d._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5d.valves)
_assert(_p5d.get("reasoning") == {"effort": "minimal"}, "REASONING_EFFORT='minimal' sent verbatim")

_pipe5d.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_EFFORT="xhigh")
_p5d = _pipe5d._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5d.valves)
_assert(_p5d.get("reasoning") == {"effort": "xhigh"}, "REASONING_EFFORT='xhigh' sent verbatim")

# Empty/garbage effort drops the key
_pipe5d.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_EFFORT="")
_p5d = _pipe5d._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5d.valves)
_assert("reasoning" not in _p5d, "empty REASONING_EFFORT: no reasoning field")
_pipe5d.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_EFFORT="bogus")
_p5d = _pipe5d._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5d.valves)
_assert("reasoning" not in _p5d, "garbage REASONING_EFFORT: silently dropped")

# ── 5e. REASONING_SUMMARY_MODE merged into reasoning object ──
_pipe5e = Pipe()
_pipe5e.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    REASONING_EFFORT="high",
    REASONING_SUMMARY_MODE="detailed",
)
_p5e = _pipe5e._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5e.valves)
_assert(
    _p5e.get("reasoning") == {"effort": "high", "summary": "detailed"},
    "effort + summary merged into one reasoning object",
)
# Summary alone (no effort)
_pipe5e.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k", REASONING_EFFORT="", REASONING_SUMMARY_MODE="auto"
)
_p5e = _pipe5e._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5e.valves)
_assert(_p5e.get("reasoning") == {"summary": "auto"}, "summary-only reasoning object")
# disabled summary skipped
_pipe5e.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k", REASONING_EFFORT="", REASONING_SUMMARY_MODE="disabled"
)
_p5e = _pipe5e._prepare_payload({"model": "openai/o1", "messages": []}, _pipe5e.valves)
_assert("reasoning" not in _p5e, "summary='disabled' + no effort: reasoning key dropped")

# ── 5f. ZDR_ENFORCE injects provider.zdr=true ──
_pipe5f = Pipe()
_pipe5f.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ZDR_ENFORCE=True)
_p5f = _pipe5f._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe5f.valves)
_assert(_p5f.get("provider", {}).get("zdr") is True, "ZDR_ENFORCE=True: provider.zdr=true injected")

_pipe5f.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ZDR_ENFORCE=False)
_p5f = _pipe5f._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe5f.valves)
_assert(
    "provider" not in _p5f or "zdr" not in _p5f.get("provider", {}),
    "ZDR_ENFORCE=False: no provider.zdr field",
)

# ZDR_ENFORCE plays nice with other provider fields
_pipe5f.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    ZDR_ENFORCE=True,
    PROVIDER_SORT="price",
    DATA_COLLECTION="deny",
)
_p5f = _pipe5f._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe5f.valves)
_assert(_p5f["provider"]["zdr"] is True, "ZDR_ENFORCE coexists with sort")
_assert(_p5f["provider"]["sort"] == "price", "ZDR_ENFORCE: sort preserved")
_assert(_p5f["provider"]["data_collection"] == "deny", "ZDR_ENFORCE: data_collection preserved")

# ── 6. _build_headers ────────────────────────────────────────────────────────

_section("6. _build_headers()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-test-123")

headers = pipe._build_headers(valves=pipe.valves)
_assert(headers["Authorization"] == "Bearer sk-test-123", "auth header")
_assert("Content-Type" in headers, "Content-Type present")
_assert(headers["Content-Type"] == "application/json", "Content-Type json")
_assert("HTTP-Referer" in headers, "HTTP-Referer present")
_assert("X-Title" in headers, "X-Title present")

headers_no_ct = pipe._build_headers(include_content_type=False, valves=pipe.valves)
_assert("Content-Type" not in headers_no_ct, "Content-Type omitted")
_assert("Authorization" in headers_no_ct, "auth still present")

# 6b. ENABLE_ANTHROPIC_INTERLEAVED_THINKING injects beta header for anthropic models only
pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_ANTHROPIC_INTERLEAVED_THINKING=True)
_h_anth = pipe._build_headers(model_id="anthropic/claude-3.5-sonnet", valves=pipe.valves)
_assert(
    _h_anth.get("anthropic-beta") == "interleaved-thinking-2025-05-14",
    "anthropic model: interleaved-thinking beta header injected",
)
_h_oai = pipe._build_headers(model_id="openai/gpt-4o", valves=pipe.valves)
_assert(
    "anthropic-beta" not in _h_oai,
    "non-anthropic model: no interleaved-thinking header",
)
# Tilde latest-alias still picks up the header
_h_alias = pipe._build_headers(model_id="~anthropic/claude-haiku-latest", valves=pipe.valves)
_assert(
    _h_alias.get("anthropic-beta") == "interleaved-thinking-2025-05-14",
    "tilde anthropic alias: interleaved-thinking header injected",
)
# When the valve is off, no header even on Claude
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_ANTHROPIC_INTERLEAVED_THINKING=False)
_h_off = pipe._build_headers(model_id="anthropic/claude-3.5-sonnet", valves=pipe.valves)
_assert(
    "anthropic-beta" not in _h_off,
    "valve off: no interleaved-thinking header even for Claude",
)

# 6c. HTTP_REFERER_OVERRIDE: explicit override > env fallback > default
pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_default_ref = pipe._build_headers(valves=pipe.valves)["HTTP-Referer"]
_assert(
    _default_ref.startswith(("http://", "https://")),
    "HTTP-Referer falls back to a valid scheme URL when no override set",
)
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    HTTP_REFERER_OVERRIDE="https://my-corp.example.com/owui",
)
_assert(
    pipe._build_headers(valves=pipe.valves)["HTTP-Referer"] == "https://my-corp.example.com/owui",
    "HTTP_REFERER_OVERRIDE: full URL respected",
)
# Bogus override (no scheme) → silently falls back
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", HTTP_REFERER_OVERRIDE="not-a-url")
_assert(
    pipe._build_headers(valves=pipe.valves)["HTTP-Referer"] != "not-a-url",
    "HTTP_REFERER_OVERRIDE: schemeless value silently ignored",
)

# ── 7. _get_provider_icon ────────────────────────────────────────────────────

_section("7. get_provider_icon()")

pipe = Pipe()
_assert(Pipe.get_provider_icon("openai") is not None, "openai icon found")
_assert(Pipe.get_provider_icon("Anthropic") is not None, "Anthropic (case) icon found")
_assert(Pipe.get_provider_icon("unknown-provider") is None, "unknown → None")

# ── 8. _parse_provider_filter ────────────────────────────────────────────────

_section("8. _parse_provider_filter()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_assert(pipe._parse_provider_filter() is None, "default ALL → None")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS="")
_assert(pipe._parse_provider_filter() is None, "empty string → None")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS="ALL")
_assert(pipe._parse_provider_filter() is None, "ALL → None")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS=" all ")
_assert(pipe._parse_provider_filter() is None, "all with spaces → None (case-insensitive)")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS="All")
_assert(pipe._parse_provider_filter() is None, "All mixed-case → None")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS="OpenAI, Google ")
filt = pipe._parse_provider_filter()
_assert(filt == {"openai", "google"}, "parses and lowercases")

# ── 9. _format_http_error ────────────────────────────────────────────────────

_section("9. _format_http_error()")

pipe = Pipe()

# With JSON error body
mock_resp = MagicMock()
mock_resp.status_code = 429
mock_resp.json.return_value = {"error": {"message": "Rate limited"}}
import requests as req_lib
real_exc = req_lib.exceptions.HTTPError(response=mock_resp)
result = pipe._format_http_error(real_exc)
_assert("429" in result, "status code in error")
_assert("Rate limited" in result, "detail in error")

# With non-JSON response
mock_resp2 = MagicMock()
mock_resp2.status_code = 500
mock_resp2.json.side_effect = ValueError("no json")
real_exc2 = req_lib.exceptions.HTTPError(response=mock_resp2)
result2 = pipe._format_http_error(real_exc2)
_assert("500" in result2, "status code without detail")

# With response=None
real_exc_none = req_lib.exceptions.HTTPError()
result_none = pipe._format_http_error(real_exc_none)
_assert("?" in result_none, "status '?' when response is None")

# ── 10. _inject_cache_control ────────────────────────────────────────────────

_section("10. _inject_cache_control()")

pipe = Pipe()

# System message with list content
payload_cc = {
    "messages": [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "Short intro"},
                {"type": "text", "text": "A much longer system prompt that should get cache_control applied to it because it is the longest"},
            ],
        },
        {"role": "user", "content": "Hello"},
    ]
}
pipe._inject_cache_control(payload_cc, pipe.valves)
_assert(
    payload_cc["messages"][0]["content"][1].get("cache_control")
    == {"type": "ephemeral", "ttl": "5m"},
    "cache_control applied to longest text chunk (default 5m TTL)",
)
_assert(
    "cache_control" not in payload_cc["messages"][0]["content"][0],
    "cache_control NOT on shorter chunk",
)

# Cache TTL valve switches the breakpoint to 1h
_pipe_ttl_1h = Pipe()
_pipe_ttl_1h.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    ENABLE_CACHE_CONTROL=True,
    ANTHROPIC_PROMPT_CACHE_TTL="1h",
)
payload_ttl = {
    "messages": [
        {
            "role": "system",
            "content": [{"type": "text", "text": "long system prompt"}],
        }
    ]
}
_pipe_ttl_1h._inject_cache_control(payload_ttl, _pipe_ttl_1h.valves)
_assert(
    payload_ttl["messages"][0]["content"][0].get("cache_control")
    == {"type": "ephemeral", "ttl": "1h"},
    "ANTHROPIC_PROMPT_CACHE_TTL='1h' propagated into breakpoint",
)

# No list content → no crash
payload_cc2 = {"messages": [{"role": "system", "content": "plain string"}]}
pipe._inject_cache_control(payload_cc2, pipe.valves)  # Should not raise
_assert(True, "plain string content doesn't crash")

# _prepare_payload deepcopy: original body must not be mutated
pipe3 = Pipe()
pipe3.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_CACHE_CONTROL=True)
original_body = {
    "model": "openai/gpt-4o",
    "messages": [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "Short"},
                {"type": "text", "text": "A much longer text block that should receive cache_control"},
            ],
        },
    ],
}
pipe3._prepare_payload(original_body, pipe3.valves)
_assert(
    "cache_control" not in original_body["messages"][0]["content"][1],
    "cache_control does not leak into original body",
)

# ── 11. _non_stream_response ─────────────────────────────────────────────────

_section("11. _non_stream_response()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 11a. Normal response 
mock_json = {
    "choices": [{"message": {"content": "Hello!", "reasoning": "Thinking..."}}],
    "citations": ["https://example.com"],
}
mock_response = MagicMock()
mock_response.json.return_value = mock_json

with patch.object(pipe, "_retryable_request", return_value=mock_response):
    result = pipe._non_stream_response({}, {}, pipe.valves)

_assert("<think>" in result, "has <think> tag")
_assert("Thinking..." in result, "reasoning content")
_assert("Hello!" in result, "main content")
_assert("Citations:" in result, "citations section")

# 11b. Error in body
mock_json_err = {"error": {"message": "Model overloaded"}}
mock_resp_err = MagicMock()
mock_resp_err.json.return_value = mock_json_err

with patch.object(pipe, "_retryable_request", return_value=mock_resp_err):
    result = pipe._non_stream_response({}, {}, pipe.valves)

_assert("Model overloaded" in result, "error from body detected")

# 11c. Empty choices
mock_json_empty = {"choices": []}
mock_resp_empty = MagicMock()
mock_resp_empty.json.return_value = mock_json_empty

with patch.object(pipe, "_retryable_request", return_value=mock_resp_empty):
    result = pipe._non_stream_response({}, {}, pipe.valves)

_assert("empty response" in result.lower(), "empty choices → informative message")

# 11d. Timeout
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.Timeout("timeout"),
):
    result = pipe._non_stream_response({}, {}, pipe.valves)
_assert("timeout" in result.lower(), "timeout error message")

# 11e. HTTP Error
mock_resp_http = MagicMock()
mock_resp_http.status_code = 401
mock_resp_http.json.return_value = {"error": {"message": "Unauthorized"}}
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.HTTPError(response=mock_resp_http),
):
    result = pipe._non_stream_response({}, {}, pipe.valves)
_assert("401" in result, "HTTP 401 error")

# 11f. Error in body as string (not dict)
mock_json_str_err = {"error": "plain string error"}
mock_resp_str_err = MagicMock()
mock_resp_str_err.json.return_value = mock_json_str_err

with patch.object(pipe, "_retryable_request", return_value=mock_resp_str_err):
    result = pipe._non_stream_response({}, {}, pipe.valves)

_assert("plain string error" in result, "error from body as string detected")

# ── 12. _stream_response ────────────────────────────────────────────────────

_section("12. _stream_response()")


def _make_sse_response(chunks: List[bytes]):
    """Build a mock requests.Response that yields SSE lines."""
    mock = MagicMock()
    mock.iter_lines.return_value = iter(chunks)
    mock.close = MagicMock()
    return mock


# 12a. Normal stream with reasoning + content + citations
sse_lines = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Step 1. "}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Step 2."}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Result: "}}], "citations": ["https://ex.com"]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "42 [1]"}}]}).encode(),
    b"data: [DONE]",
]

mock_sse = _make_sse_response(sse_lines)
with patch.object(pipe, "_retryable_request", return_value=mock_sse):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream: <think> present")
_assert("</think>" in full, "stream: </think> present")
_assert("Step 1." in full, "stream: reasoning step 1")
_assert("Step 2." in full, "stream: reasoning step 2")
_assert("Result:" in full or "Result: " in full, "stream: content")
_assert("42" in full, "stream: content with ref")
_assert("Citations:" in full, "stream: citations")

# 12b. Mid-stream error
sse_err = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Start..."}}]}).encode(),
    b"data: " + json.dumps({"error": {"message": "context_length_exceeded"}}).encode(),
]

mock_sse_err = _make_sse_response(sse_err)
with patch.object(pipe, "_retryable_request", return_value=mock_sse_err):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("context_length_exceeded" in full, "stream: mid-stream error detected")
_assert("Start..." in full, "stream: content before error preserved")

# 12c. Unclosed <think> at stream end
sse_think_open = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Thinking..."}}]}).encode(),
    b"data: [DONE]",
]

mock_sse_think = _make_sse_response(sse_think_open)
with patch.object(pipe, "_retryable_request", return_value=mock_sse_think):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream: think opened")
_assert("</think>" in full, "stream: think auto-closed at end")
_assert("Thinking..." in full, "stream: reasoning flushed")

# 12d. Mid-stream error while in <think>
sse_think_err = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Analyzing..."}}]}).encode(),
    b"data: " + json.dumps({"error": {"message": "server_fault"}}).encode(),
]

mock_sse_te = _make_sse_response(sse_think_err)
with patch.object(pipe, "_retryable_request", return_value=mock_sse_te):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream error-in-think: think opened")
_assert("</think>" in full, "stream error-in-think: think closed before error")
_assert("server_fault" in full, "stream error-in-think: error shown")

# 12e. Timeout in stream
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.Timeout("timeout"),
):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("timeout" in full.lower(), "stream: timeout error")

# 12f. Empty stream
mock_empty_sse = _make_sse_response([b"data: [DONE]"])
with patch.object(pipe, "_retryable_request", return_value=mock_empty_sse):
    output = list(pipe._stream_response({}, {}, pipe.valves))
_assert(len("".join(output)) == 0, "stream: empty → no output")

# 12g. Malformed JSON in stream (should skip)
sse_bad = [
    b"data: {INVALID JSON",
    b"data: " + json.dumps({"choices": [{"delta": {"content": "OK"}}]}).encode(),
    b"data: [DONE]",
]
mock_bad = _make_sse_response(sse_bad)
with patch.object(pipe, "_retryable_request", return_value=mock_bad):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("OK" in full, "stream: skips bad JSON, continues")

# 12h. Non-data lines skipped
sse_mixed = [
    b"",
    b": comment",
    b"event: ping",
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Valid"}}]}).encode(),
    b"data: [DONE]",
]
mock_mixed = _make_sse_response(sse_mixed)
with patch.object(pipe, "_retryable_request", return_value=mock_mixed):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("Valid" in full, "stream: non-data lines ignored")

# 12i. Stream chunk with empty choices array (guard against IndexError)
sse_empty_choices = [
    b"data: " + json.dumps({"choices": []}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "After"}}]}).encode(),
    b"data: [DONE]",
]
mock_ec = _make_sse_response(sse_empty_choices)
with patch.object(pipe, "_retryable_request", return_value=mock_ec):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("After" in full, "stream: empty choices array skipped safely")

# 12j. HTTPError in stream — detail preserved
mock_resp_stream_err = MagicMock()
mock_resp_stream_err.status_code = 429
mock_resp_stream_err.json.return_value = {"error": {"message": "Rate limited"}}
mock_resp_stream_err.content = json.dumps({"error": {"message": "Rate limited"}}).encode()
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.HTTPError(response=mock_resp_stream_err),
):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("429" in full, "stream: HTTP error status code")
_assert("Rate limited" in full, "stream: HTTP error detail preserved")

# 12k. Timeout mid-stream while in <think> → closes tag before error
def _iter_lines_timeout():
    yield b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Analyzing..."}}]}).encode()
    raise req_lib.exceptions.Timeout("read timeout")

mock_sse_t = MagicMock()
mock_sse_t.iter_lines.return_value = _iter_lines_timeout()
mock_sse_t.close = MagicMock()

with patch.object(pipe, "_retryable_request", return_value=mock_sse_t):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream timeout-in-think: think opened")
_assert("</think>" in full, "stream timeout-in-think: think closed before error")
_assert("timeout" in full.lower(), "stream timeout-in-think: timeout error")

# 12l. Generic exception mid-stream while in <think> → closes tag before error
def _iter_lines_conn_error():
    yield b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Reasoning..."}}]}).encode()
    raise req_lib.exceptions.ConnectionError("connection lost mid-stream")

mock_sse_ce = MagicMock()
mock_sse_ce.iter_lines.return_value = _iter_lines_conn_error()
mock_sse_ce.close = MagicMock()

with patch.object(pipe, "_retryable_request", return_value=mock_sse_ce):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream exception-in-think: think opened")
_assert("</think>" in full, "stream exception-in-think: think closed")
_assert("connection lost" in full.lower(), "stream exception-in-think: error shown")

# 12m. Mid-stream error as string (not dict)
sse_str_err = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Before..."}}]}).encode(),
    b"data: " + json.dumps({"error": "simple string error"}).encode(),
]
mock_str_err = _make_sse_response(sse_str_err)
with patch.object(pipe, "_retryable_request", return_value=mock_str_err):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("simple string error" in full, "stream: string error detected")

# ── 13. _retryable_request ──────────────────────────────────────────────────

_section("13. _retryable_request()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=2, REQUEST_TIMEOUT=5)

# 13a. Success on first try
mock_ok = MagicMock()
mock_ok.raise_for_status = MagicMock()
with patch.object(pipe._session, "post", return_value=mock_ok) as mock_post:
    result = pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
    _assert(result is mock_ok, "retryable: returns on first success")
    _assert(mock_post.call_count == 1, "retryable: only 1 call on success")

# 13b. Timeout then success
call_count = [0]
def _post_retry(*args, **kwargs):
    call_count[0] += 1
    if call_count[0] == 1:
        raise req_lib.exceptions.Timeout("first timeout")
    m = MagicMock()
    m.raise_for_status = MagicMock()
    return m

with patch.object(pipe._session, "post", side_effect=_post_retry), \
     patch("time.sleep"):
    call_count[0] = 0
    result = pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
    _assert(call_count[0] == 2, "retryable: retried after timeout")

# 13c. All retries exhausted
with patch.object(pipe._session, "post", side_effect=req_lib.exceptions.Timeout("timeout")), \
     patch("time.sleep"):
    try:
        pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
        _assert(False, "retryable: should raise after all retries")
    except req_lib.exceptions.Timeout:
        _assert(True, "retryable: raises Timeout after exhausting retries")

# 13d. HTTPError not retried
with patch.object(pipe._session, "post") as mock_post:
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=mock_resp)
    mock_post.return_value = mock_resp
    try:
        pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
        _assert(False, "retryable: HTTPError should raise immediately")
    except req_lib.exceptions.HTTPError:
        _assert(True, "retryable: HTTPError not retried")
        _assert(mock_post.call_count == 1, "retryable: only 1 call on HTTPError")

# 13e. ConnectionError triggers retry
_call_count_ce = [0]
def _post_retry_ce(*args, **kwargs):
    _call_count_ce[0] += 1
    if _call_count_ce[0] == 1:
        raise req_lib.exceptions.ConnectionError("connection refused")
    m = MagicMock()
    m.raise_for_status = MagicMock()
    return m

with patch.object(pipe._session, "post", side_effect=_post_retry_ce), \
     patch("time.sleep"):
    _call_count_ce[0] = 0
    result = pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
    _assert(_call_count_ce[0] == 2, "retryable: retried after ConnectionError")

# ── 14. pipe() async entry point ────────────────────────────────────────────

_section("14. pipe() async")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 14a. Missing API key
pipe_no_key = Pipe()
pipe_no_key.valves = Pipe.Valves(OPENROUTER_API_KEY="")


async def _test_pipe_no_key():
    result = await pipe_no_key.pipe({"model": "test", "messages": []})
    return result

res = asyncio.run(_test_pipe_no_key())
_assert("OPENROUTER_API_KEY" in res, "pipe: missing key error")

# 14a2. __event_emitter__ is called for non-stream
async def _test_pipe_event_emitter_non_stream():
    mock_resp_ev = MagicMock()
    mock_resp_ev.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    events = []
    async def _emitter(event):
        events.append(event)
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    with patch.object(p, "_retryable_request", return_value=mock_resp_ev):
        result = await p.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": False},
            __event_emitter__=_emitter,
        )
    return result, events

res_ev, events_ev = asyncio.run(_test_pipe_event_emitter_non_stream())
_assert(len(events_ev) == 2, "pipe event_emitter: 2 events (start + done)")
_assert(events_ev[0]["type"] == "status", "pipe event_emitter: first event is status")
_assert(events_ev[0]["data"]["done"] is False, "pipe event_emitter: first event not done")
_assert("openai/gpt-4o" in events_ev[0]["data"]["description"], "pipe event_emitter: model name in status")
_assert(events_ev[1]["data"]["done"] is True, "pipe event_emitter: second event done")
_assert("ok" in res_ev, "pipe event_emitter: content returned correctly")

# 14a3. __event_emitter__ is called for stream (start only)
async def _test_pipe_event_emitter_stream():
    sse = _make_sse_response([
        b"data: " + json.dumps({"choices": [{"delta": {"content": "Hi"}}]}).encode(),
        b"data: [DONE]",
    ])
    events = []
    async def _emitter(event):
        events.append(event)
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    with patch.object(p, "_retryable_request", return_value=sse):
        result = await p.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            __event_emitter__=_emitter,
        )
        chunks = [chunk async for chunk in result]
    return "".join(chunks), events

res_s, events_s = asyncio.run(_test_pipe_event_emitter_stream())
_assert(len(events_s) == 2, "pipe stream event_emitter: 2 events (start + done)")
_assert(events_s[0]["data"]["done"] is False, "pipe stream event_emitter: start not done")
_assert(events_s[1]["data"]["done"] is True, "pipe stream event_emitter: done event emitted")
_assert("Hi" in res_s, "pipe stream event_emitter: content correct")

# 14a4. pipe works without __event_emitter__ (backward compat)
async def _test_pipe_no_emitter():
    mock_resp_ne = MagicMock()
    mock_resp_ne.json.return_value = {"choices": [{"message": {"content": "compat"}}]}
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    with patch.object(p, "_retryable_request", return_value=mock_resp_ne):
        return await p.pipe({"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": False})

res_ne = asyncio.run(_test_pipe_no_emitter())
_assert("compat" in res_ne, "pipe no emitter: backward compatible")

# 14b. Non-stream returns string
mock_json_ok = {
    "choices": [{"message": {"content": "Hello!"}}],
}
mock_resp = MagicMock()
mock_resp.json.return_value = mock_json_ok


async def _test_pipe_non_stream():
    with patch.object(pipe, "_retryable_request", return_value=mock_resp):
        return await pipe.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": False}
        )

res = asyncio.run(_test_pipe_non_stream())
_assert(isinstance(res, str), "pipe non-stream: returns string")
_assert("Hello!" in res, "pipe non-stream: content correct")

# 14c. Stream returns generator
async def _test_pipe_stream() -> str:
    sse = _make_sse_response([
        b"data: " + json.dumps({"choices": [{"delta": {"content": "World"}}]}).encode(),
        b"data: [DONE]",
    ])
    with patch.object(pipe, "_retryable_request", return_value=sse):
        result = await pipe.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        )
        # result is a generator
        chunks = list(result)
        return "".join(chunks)

res = asyncio.run(_test_pipe_stream())
_assert("World" in res, "pipe stream: content correct")

# ── 15. pipes() model listing ───────────────────────────────────────────────

_section("15. pipes() model listing")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")

# 15a. Normal listing
mock_models = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
        {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash (Free)"},
    ]
}
mock_resp = MagicMock()
mock_resp.status_code = 200
mock_resp.json.return_value = mock_models
mock_resp.raise_for_status = MagicMock()

with patch.object(pipe._session, "get", return_value=mock_resp):
    models = pipe.pipes()

_assert(len(models) == 3, "pipes: returns 3 models")
_assert(models[0]["id"] == "openai/gpt-4o", "pipes: first model ID")
_assert("info" not in models[0], "pipes: info key removed (dead code)")

# 15b. FREE_ONLY filter
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_MODEL_FILTER="only")

# Mock data with pricing info: one :free suffix, one free-by-pricing, one paid
mock_models_pricing = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "pricing": {"prompt": "5", "completion": "15"}},
        {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash (Free)", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "google/gemma-3-1b-it", "name": "Gemma 3 1B", "pricing": {"prompt": "0", "completion": "0"}},
    ]
}
mock_resp_pricing = MagicMock()
mock_resp_pricing.status_code = 200
mock_resp_pricing.json.return_value = mock_models_pricing
mock_resp_pricing.raise_for_status = MagicMock()

pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_resp_pricing):
    models = pipe.pipes()
_assert(len(models) == 2, "pipes FREE_ONLY: 2 free models (suffix + pricing)")
free_ids = {m["id"] for m in models}
_assert("google/gemini-2.0-flash-exp:free" in free_ids, "pipes FREE_ONLY: :free suffix model kept")
_assert("google/gemma-3-1b-it" in free_ids, "pipes FREE_ONLY: pricing-based free model kept")
_assert("openai/gpt-4o" not in free_ids, "pipes FREE_ONLY: paid model excluded")

# 15c. Provider filter
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="openai"
)
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_resp):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes provider filter: only openai")
_assert(models[0]["id"] == "openai/gpt-4o", "pipes provider filter: correct model")

# 15d. Invert provider filter
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="openai", INVERT_PROVIDER_LIST=True
)
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_resp):
    models = pipe.pipes()
_assert(len(models) == 2, "pipes invert: excludes openai → 2 models")

# 15d-2. Provider filter includes tilde (~) latest-alias models for their base provider
_mock_tilde = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "~anthropic/claude-haiku-latest", "name": "Claude Haiku (Latest)"},
        {"id": "~openai/gpt-latest", "name": "GPT (Latest)"},
        {"id": "google/gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
    ]
}
_mock_resp_tilde = MagicMock()
_mock_resp_tilde.status_code = 200
_mock_resp_tilde.json.return_value = _mock_tilde
_mock_resp_tilde.raise_for_status = MagicMock()

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="openai")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_resp_tilde):
    _tilde_models = pipe.pipes()
_tilde_ids = {m["id"] for m in _tilde_models}
_assert("openai/gpt-4o" in _tilde_ids, "pipes tilde: base openai model included")
_assert("~openai/gpt-latest" in _tilde_ids, "pipes tilde: ~openai model included by openai filter")
_assert("~anthropic/claude-haiku-latest" not in _tilde_ids, "pipes tilde: ~anthropic excluded by openai filter")
_assert("google/gemini-2.0-flash" not in _tilde_ids, "pipes tilde: google excluded by openai filter")

pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="anthropic")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_resp_tilde):
    _tilde_models2 = pipe.pipes()
_tilde_ids2 = {m["id"] for m in _tilde_models2}
_assert("~anthropic/claude-haiku-latest" in _tilde_ids2, "pipes tilde: ~anthropic model included by anthropic filter")
_assert("openai/gpt-4o" not in _tilde_ids2, "pipes tilde: openai excluded by anthropic filter")

pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="anthropic", INVERT_PROVIDER_LIST=True
)
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_resp_tilde):
    _tilde_models3 = pipe.pipes()
_tilde_ids3 = {m["id"] for m in _tilde_models3}
_assert("~anthropic/claude-haiku-latest" not in _tilde_ids3, "pipes tilde: ~anthropic excluded by inverted anthropic filter")
_assert("openai/gpt-4o" in _tilde_ids3, "pipes tilde: openai kept by inverted anthropic filter")

# 15e. PREFIX
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PREFIX="🔥 "
)
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_resp):
    models = pipe.pipes()
_assert(models[0]["name"].startswith("🔥 "), "pipes prefix: name prefixed")

# 15f. No API key
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="")
models = pipe.pipes()
_assert(len(models) == 1, "pipes no key: 1 error entry")
_assert(models[0]["id"] == "error", "pipes no key: error id")

# 15g. Timeout
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
pipe._models_cache = None
with patch.object(pipe._session, "get", side_effect=req_lib.exceptions.Timeout("t")):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes timeout: error")
_assert("timeout" in models[0]["name"].lower(), "pipes timeout: timeout in name")

# 15h. Auth check returns 403
mock_resp_err = MagicMock()
mock_resp_err.status_code = 403
mock_resp_err.json.return_value = {"error": {"message": "Forbidden"}}
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_resp_err):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes auth check 403: error id")
_assert("403" in models[0]["name"], "pipes auth check 403: status in name")

# 15h2. HTTP error on models endpoint (returns 500)
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None
_mock_models_500 = MagicMock()
_mock_models_500.status_code = 500
_mock_models_500.json.return_value = {"error": {"message": "Internal Server Error"}}
_mock_models_500.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=_mock_models_500)

with patch.object(pipe._session, "get", return_value=_mock_models_500):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes models HTTP 500: error id")
_assert("500" in models[0]["name"], "pipes models HTTP 500: status in name")

# 15i. Invalid API key — returns 401
mock_auth_401 = MagicMock()
mock_auth_401.status_code = 401
mock_auth_401.json.return_value = {"error": {"message": "User not found."}}
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="bad-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_auth_401):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes invalid key 401: 1 error entry")
_assert(models[0]["id"] == "error", "pipes invalid key 401: error id")
_assert("Invalid API key" in models[0]["name"], "pipes invalid key 401: message")
_assert("401" in models[0]["name"], "pipes invalid key 401: status code in message")
_assert("User not found" in models[0]["name"], "pipes invalid key 401: detail in message")

# 15j. Invalid API key — returns 502 (malformed key, Clerk error)
mock_auth_502 = MagicMock()
mock_auth_502.status_code = 502
mock_auth_502.json.return_value = {"error": {"message": "Failed to authenticate request with Clerk"}}
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="bad-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=mock_auth_502):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes invalid key 502: 1 error entry")
_assert(models[0]["id"] == "error", "pipes invalid key 502: error id")
_assert("Invalid API key" in models[0]["name"], "pipes invalid key 502: message")
_assert("502" in models[0]["name"], "pipes invalid key 502: status code")

# 15k. Network error returns error entry
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None

with patch.object(pipe._session, "get", side_effect=req_lib.exceptions.ConnectionError("connection failed")):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes connection error: error id")
_assert("connection failed" in models[0]["name"].lower(), "pipes connection error: detail shown")

# 15l. Empty data from API → "No models found"
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None
_mock_empty_data = MagicMock()
_mock_empty_data.status_code = 200
_mock_empty_data.json.return_value = {"data": []}
_mock_empty_data.raise_for_status = MagicMock()

with patch.object(pipe._session, "get", return_value=_mock_empty_data):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes empty data: error id")
_assert("No models found" in models[0]["name"], "pipes empty data: correct message")

# 15m. FREE_ONLY + all paid models → "No free models available"
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_MODEL_FILTER="only")
pipe._models_cache = None
_mock_all_paid = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "pricing": {"prompt": "5", "completion": "15"}},
    ]
}
_mock_resp_paid = MagicMock()
_mock_resp_paid.status_code = 200
_mock_resp_paid.json.return_value = _mock_all_paid
_mock_resp_paid.raise_for_status = MagicMock()

with patch.object(pipe._session, "get", return_value=_mock_resp_paid):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes FREE_ONLY no free: error id")
_assert("No free models" in models[0]["name"], "pipes FREE_ONLY no free: correct message")

# 15n. Provider filter + no matching providers → "No models match"
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="nonexistent")
pipe._models_cache = None

with patch.object(pipe._session, "get", return_value=mock_resp):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes provider no match: error id")
_assert("No models match" in models[0]["name"], "pipes provider no match: correct message")

# 15o. response.close() called via finally on auth-error branch (401)
_close_auth_resp = MagicMock()
_close_auth_resp.status_code = 401
_close_auth_resp.json.return_value = {"error": {"message": "Unauthorized"}}
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="bad-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_close_auth_resp):
    pipe.pipes()
_assert(_close_auth_resp.close.call_count == 1, "pipes response.close(): called after 401 auth error")

# 15p. response.close() called via finally when response.json() raises (JSONDecodeError)
_close_json_err_resp = MagicMock()
_close_json_err_resp.status_code = 200
_close_json_err_resp.raise_for_status = MagicMock()
_close_json_err_resp.json.side_effect = ValueError("No JSON object could be decoded")
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_close_json_err_resp):
    pipe.pipes()
_assert(_close_json_err_resp.close.call_count == 1, "pipes response.close(): called after JSON decode error")

# 15q. response.close() called via finally on success path
_close_ok_resp = MagicMock()
_close_ok_resp.status_code = 200
_close_ok_resp.raise_for_status = MagicMock()
_close_ok_resp.json.return_value = {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]}
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_close_ok_resp):
    pipe.pipes()
_assert(_close_ok_resp.close.call_count == 1, "pipes response.close(): called after successful listing")

# ── 16. Valve json_schema_extra ──────────────────────────────────────────────

_section("16. Valve json_schema_extra")

# 16a. API key uses password input type
api_key_field = Pipe.Valves.model_fields["OPENROUTER_API_KEY"]
_assert(
    api_key_field.json_schema_extra is not None,
    "API key: json_schema_extra present",
)
_assert(
    api_key_field.json_schema_extra.get("input", {}).get("type") == "password",
    "API key: input type is password",
)

# 16b. REASONING_EFFORT uses select with 6 options (disabled, minimal, low, medium, high, xhigh)
re_field = Pipe.Valves.model_fields["REASONING_EFFORT"]
_assert(
    re_field.json_schema_extra is not None,
    "REASONING_EFFORT: json_schema_extra present",
)
re_options = re_field.json_schema_extra.get("input", {}).get("options", [])
_assert(
    len(re_options) == 6,
    "REASONING_EFFORT: 6 options (disabled, minimal, low, medium, high, xhigh)",
)
re_values = [o["value"] for o in re_options]
_assert("minimal" in re_values, "REASONING_EFFORT: minimal option present")
_assert("xhigh" in re_values, "REASONING_EFFORT: xhigh option present")
_assert("" in re_values and "high" in re_values, "REASONING_EFFORT: contains empty and high")

# 16c. PROVIDER_SORT uses select with 4 options
ps_field = Pipe.Valves.model_fields["PROVIDER_SORT"]
ps_options = ps_field.json_schema_extra.get("input", {}).get("options", [])
_assert(len(ps_options) == 4, "PROVIDER_SORT: 4 options")
ps_values = [o["value"] for o in ps_options]
_assert("price" in ps_values and "latency" in ps_values, "PROVIDER_SORT: price and latency")

# 16d. DATA_COLLECTION uses select with 2 options
dc_field = Pipe.Valves.model_fields["DATA_COLLECTION"]
dc_options = dc_field.json_schema_extra.get("input", {}).get("options", [])
_assert(len(dc_options) == 2, "DATA_COLLECTION: 2 options")
dc_values = [o["value"] for o in dc_options]
_assert("allow" in dc_values and "deny" in dc_values, "DATA_COLLECTION: allow and deny")

# ── 17. _is_safe_url() ──────────────────────────────────────────────────────

_section("17. _is_safe_url()")

_is_safe_url = mod._is_safe_url

_assert(_is_safe_url("https://example.com") is True, "https URL is safe")
_assert(_is_safe_url("http://example.com") is True, "http URL is safe")
_assert(_is_safe_url("HTTP://EXAMPLE.COM") is True, "case-insensitive http")
_assert(_is_safe_url("HTTPS://EXAMPLE.COM") is True, "case-insensitive https")
_assert(_is_safe_url("javascript:alert(1)") is False, "javascript: not safe")
_assert(_is_safe_url("data:text/html,<h1>hi</h1>") is False, "data: not safe")
_assert(_is_safe_url("ftp://files.example.com") is False, "ftp: not safe")
_assert(_is_safe_url("") is False, "empty string not safe")
_assert(_is_safe_url(123) is False, "non-string not safe")
_assert(_is_safe_url(None) is False, "None not safe")

# ── 18. _clean_model_id() ───────────────────────────────────────────────────

_section("18. _clean_model_id()")

_assert(Pipe._clean_model_id("openrouter.google/gemini") == "google/gemini", "strips manifold prefix")
_assert(Pipe._clean_model_id("google/gemini") == "google/gemini", "no prefix → unchanged")
_assert(Pipe._clean_model_id("") == "", "empty string → empty")
_assert(Pipe._clean_model_id("a.b.c/d") == "b.c/d", "no '/' before first '.' → strip prefix")
_assert(
    Pipe._clean_model_id("anthropic/claude-3.5-sonnet") == "anthropic/claude-3.5-sonnet",
    "'/' before '.' → preserve dotted model name",
)
_assert(
    Pipe._clean_model_id("openrouter.anthropic/claude-3.5-sonnet")
    == "anthropic/claude-3.5-sonnet",
    "manifold prefix stripped, dotted model preserved",
)
_assert(
    Pipe._clean_model_id("meta-llama/llama-3.1-8b-instruct")
    == "meta-llama/llama-3.1-8b-instruct",
    "real OpenRouter ID with dots preserved",
)
_assert(
    Pipe._clean_model_id("function_xyz.meta-llama/llama-3.3-70b-instruct")
    == "meta-llama/llama-3.3-70b-instruct",
    "OWUI function_id prefix stripped, dotted model preserved",
)

# ── 19. Model caching ───────────────────────────────────────────────────────

_section("19. Model caching")

import time as _time_mod

_MODELS_CACHE_TTL = mod._MODELS_CACHE_TTL

# 19a. Second call uses cache (no API call)
_pipe_cache = Pipe()
_pipe_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_pipe_cache._models_cache = None

_mock_cache_resp = MagicMock()
_mock_cache_resp.status_code = 200
_mock_cache_resp.json.return_value = {"data": [
    {"id": "openai/gpt-4o", "name": "GPT-4o"},
]}
_mock_cache_resp.raise_for_status = MagicMock()

_call_count = 0
_original_get = _pipe_cache._session.get

def _counting_get(*args, **kwargs):
    global _call_count
    _call_count += 1
    return _mock_cache_resp

with patch.object(_pipe_cache._session, "get", side_effect=_counting_get):
    _pipe_cache.pipes()  # first call → populates cache
    _pipe_cache.pipes()  # second call → should use cache
_assert(_call_count == 1, "cache hit: API called only once for two pipes() calls")

# 19b. Changing a valve invalidates cache
_pipe_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_MODEL_FILTER="only")
_call_count = 0
with patch.object(_pipe_cache._session, "get", side_effect=_counting_get):
    _pipe_cache.pipes()  # should miss cache (valve changed)
_assert(_call_count == 1, "cache miss: API called after valve change")

# 19c. Expired TTL invalidates cache
_pipe_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_pipe_cache._models_cache = None
_call_count = 0
with patch.object(_pipe_cache._session, "get", side_effect=_counting_get):
    _pipe_cache.pipes()
_assert(_call_count == 1, "cache: first call hits API")

# Simulate TTL expiration
_pipe_cache._models_cache_ts -= _MODELS_CACHE_TTL + 1
_call_count = 0
with patch.object(_pipe_cache._session, "get", side_effect=_counting_get):
    _pipe_cache.pipes()
_assert(_call_count == 1, "cache expired: API called after TTL")

# ── 19d. OUTPUT_MODALITIES query param ──────────────────────────────────────
_section("19d. OUTPUT_MODALITIES query param on /models")

_mock_modalities_resp = MagicMock()
_mock_modalities_resp.status_code = 200
_mock_modalities_resp.json.return_value = {"data": [
    {"id": "openai/gpt-4o", "name": "GPT-4o"},
    {"id": "openai/gpt-4o-mini-tts-2025-12-15", "name": "GPT-4o Mini TTS"},
]}
_mock_modalities_resp.raise_for_status = MagicMock()

_captured_kwargs = {}

def _capture_get(*args, **kwargs):
    _captured_kwargs.clear()
    _captured_kwargs.update(kwargs)
    return _mock_modalities_resp

# Default valve → params should request 'all'
_pipe_mod = Pipe()
_pipe_mod.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_pipe_mod._models_cache = None
with patch.object(_pipe_mod._session, "get", side_effect=_capture_get):
    _models = _pipe_mod.pipes()
_assert(
    _captured_kwargs.get("params") == {"output_modalities": "all"},
    "default OUTPUT_MODALITIES sends params={'output_modalities':'all'}",
)
_tts_ids = {m["id"] for m in _models}
_assert(
    "openai/gpt-4o-mini-tts-2025-12-15" in _tts_ids,
    "TTS model surfaced in pipes() output when API returns it",
)

# Custom valve value → forwarded verbatim
_pipe_mod = Pipe()
_pipe_mod.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="text,audio")
_pipe_mod._models_cache = None
with patch.object(_pipe_mod._session, "get", side_effect=_capture_get):
    _pipe_mod.pipes()
_assert(
    _captured_kwargs.get("params") == {"output_modalities": "text,audio"},
    "custom OUTPUT_MODALITIES forwarded as params value",
)

# Empty/whitespace valve → falls back to 'all'
_pipe_mod = Pipe()
_pipe_mod.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="   ")
_pipe_mod._models_cache = None
with patch.object(_pipe_mod._session, "get", side_effect=_capture_get):
    _pipe_mod.pipes()
_assert(
    _captured_kwargs.get("params") == {"output_modalities": "all"},
    "blank OUTPUT_MODALITIES falls back to 'all'",
)

# 19e. Cache key includes OUTPUT_MODALITIES — toggling invalidates
_pipe_mod_cache = Pipe()
_pipe_mod_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="all")
_key_all = _pipe_mod_cache._build_cache_key()
_pipe_mod_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="text")
_key_text = _pipe_mod_cache._build_cache_key()
_assert(_key_all != _key_text, "_build_cache_key differs for different OUTPUT_MODALITIES")

# Behavioral: pipes() refetches after OUTPUT_MODALITIES changes
_pipe_mod_cache = Pipe()
_pipe_mod_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="all")
_pipe_mod_cache._models_cache = None

_modalities_call_count = 0

def _counting_modalities_get(*args, **kwargs):
    global _modalities_call_count
    _modalities_call_count += 1
    return _mock_modalities_resp

with patch.object(_pipe_mod_cache._session, "get", side_effect=_counting_modalities_get):
    _pipe_mod_cache.pipes()  # populates cache
    _pipe_mod_cache.pipes()  # cache hit
_assert(_modalities_call_count == 1, "OUTPUT_MODALITIES cache hit: 1 API call across 2 pipes() invocations")

_pipe_mod_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", OUTPUT_MODALITIES="text")
_modalities_call_count = 0
with patch.object(_pipe_mod_cache._session, "get", side_effect=_counting_modalities_get):
    _pipe_mod_cache.pipes()
_assert(
    _modalities_call_count == 1,
    "OUTPUT_MODALITIES change invalidates cache: API refetched",
)

# ── 19f. FREE_MODEL_FILTER trinary (all/only/exclude) ────────────────────────
_section("19f. FREE_MODEL_FILTER trinary")

_mock_pricing = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "pricing": {"prompt": "5", "completion": "15"}},
        {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash (Free)", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "google/gemma-3-1b-it", "name": "Gemma 3 1B", "pricing": {"prompt": "0", "completion": "0"}},
    ]
}
_mock_pricing_resp = MagicMock()
_mock_pricing_resp.status_code = 200
_mock_pricing_resp.json.return_value = _mock_pricing
_mock_pricing_resp.raise_for_status = MagicMock()

# 'all' = no filter
_pipe_ff = Pipe()
_pipe_ff.valves = Pipe.Valves(OPENROUTER_API_KEY="k", FREE_MODEL_FILTER="all")
_pipe_ff._models_cache = None
with patch.object(_pipe_ff._session, "get", return_value=_mock_pricing_resp):
    _all_models = _pipe_ff.pipes()
_assert(len(_all_models) == 3, "FREE_MODEL_FILTER='all': all 3 models pass through")

# 'exclude' hides free models
_pipe_ff = Pipe()
_pipe_ff.valves = Pipe.Valves(OPENROUTER_API_KEY="k", FREE_MODEL_FILTER="exclude")
_pipe_ff._models_cache = None
with patch.object(_pipe_ff._session, "get", return_value=_mock_pricing_resp):
    _paid = _pipe_ff.pipes()
_paid_ids = {m["id"] for m in _paid}
_assert("openai/gpt-4o" in _paid_ids, "FREE_MODEL_FILTER='exclude': paid model kept")
_assert(":free" not in str(_paid_ids), "FREE_MODEL_FILTER='exclude': :free suffix excluded")
_assert("google/gemma-3-1b-it" not in _paid_ids, "FREE_MODEL_FILTER='exclude': zero-pricing excluded")

# ── 19g. TOOL_CALLING_FILTER ────────────────────────────────────────────────
_section("19g. TOOL_CALLING_FILTER")

_mock_tools = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "supported_parameters": ["tools", "tool_choice", "temperature"]},
        {"id": "openai/o1-mini", "name": "o1-mini", "supported_parameters": ["temperature"]},
        {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5", "supported_parameters": ["tool_choice"]},
    ]
}
_mock_tools_resp = MagicMock()
_mock_tools_resp.status_code = 200
_mock_tools_resp.json.return_value = _mock_tools
_mock_tools_resp.raise_for_status = MagicMock()

_pipe_tc = Pipe()
_pipe_tc.valves = Pipe.Valves(OPENROUTER_API_KEY="k", TOOL_CALLING_FILTER="only")
_pipe_tc._models_cache = None
with patch.object(_pipe_tc._session, "get", return_value=_mock_tools_resp):
    _tc_models = _pipe_tc.pipes()
_tc_ids = {m["id"] for m in _tc_models}
_assert("openai/gpt-4o" in _tc_ids, "TOOL_CALLING_FILTER='only': model with 'tools' kept")
_assert("openai/gpt-3.5-turbo" in _tc_ids, "TOOL_CALLING_FILTER='only': model with 'tool_choice' kept")
_assert("openai/o1-mini" not in _tc_ids, "TOOL_CALLING_FILTER='only': non-tool model dropped")

_pipe_tc = Pipe()
_pipe_tc.valves = Pipe.Valves(OPENROUTER_API_KEY="k", TOOL_CALLING_FILTER="exclude")
_pipe_tc._models_cache = None
with patch.object(_pipe_tc._session, "get", return_value=_mock_tools_resp):
    _tc_excl = _pipe_tc.pipes()
_tc_excl_ids = {m["id"] for m in _tc_excl}
_assert(_tc_excl_ids == {"openai/o1-mini"}, "TOOL_CALLING_FILTER='exclude': only non-tool model kept")

# ── 19h. MODEL_VARIANTS expansion ───────────────────────────────────────────
_section("19h. MODEL_VARIANTS expansion")

_mock_var = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
    ]
}
_mock_var_resp = MagicMock()
_mock_var_resp.status_code = 200
_mock_var_resp.json.return_value = _mock_var
_mock_var_resp.raise_for_status = MagicMock()

_pipe_var = Pipe()
_pipe_var.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    MODEL_VARIANTS="openai/gpt-4o:nitro,anthropic/claude-3.5-sonnet:thinking,openai/gpt-4o:exacto",
)
_pipe_var._models_cache = None
with patch.object(_pipe_var._session, "get", return_value=_mock_var_resp):
    _var_models = _pipe_var.pipes()
_var_ids = {m["id"] for m in _var_models}
_assert("openai/gpt-4o" in _var_ids, "MODEL_VARIANTS: base model preserved")
_assert("openai/gpt-4o:nitro" in _var_ids, "MODEL_VARIANTS: :nitro variant added")
_assert("openai/gpt-4o:exacto" in _var_ids, "MODEL_VARIANTS: :exacto variant added")
_assert("anthropic/claude-3.5-sonnet:thinking" in _var_ids, "MODEL_VARIANTS: :thinking variant added")
_nitro_entry = next(m for m in _var_models if m["id"] == "openai/gpt-4o:nitro")
_assert("Nitro" in _nitro_entry["name"], "MODEL_VARIANTS: tag label appended to display name")
_assert("GPT-4o" in _nitro_entry["name"], "MODEL_VARIANTS: base name retained")

# Variant whose base isn't in the catalog → silently skipped
_pipe_var = Pipe()
_pipe_var.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    MODEL_VARIANTS="missing/provider-model:nitro,openai/gpt-4o:nitro",
)
_pipe_var._models_cache = None
with patch.object(_pipe_var._session, "get", return_value=_mock_var_resp):
    _var_models = _pipe_var.pipes()
_var_ids = {m["id"] for m in _var_models}
_assert("missing/provider-model:nitro" not in _var_ids, "MODEL_VARIANTS: missing base skipped")
_assert("openai/gpt-4o:nitro" in _var_ids, "MODEL_VARIANTS: valid variant still added")

# Unrecognised tag → skipped
_pipe_var = Pipe()
_pipe_var.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k", MODEL_VARIANTS="openai/gpt-4o:bogus"
)
_pipe_var._models_cache = None
with patch.object(_pipe_var._session, "get", return_value=_mock_var_resp):
    _var_models = _pipe_var.pipes()
_assert(
    not any(m["id"] == "openai/gpt-4o:bogus" for m in _var_models),
    "MODEL_VARIANTS: unrecognised tag silently dropped",
)

# Empty MODEL_VARIANTS → no expansion
_pipe_var = Pipe()
_pipe_var.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_VARIANTS="")
_pipe_var._models_cache = None
with patch.object(_pipe_var._session, "get", return_value=_mock_var_resp):
    _var_models = _pipe_var.pipes()
_assert(len(_var_models) == 2, "MODEL_VARIANTS empty: no virtual entries added")

# ── 19i. ZDR_MODELS_ONLY filter + _load_zdr_model_ids ───────────────────────
_section("19i. ZDR_MODELS_ONLY filter")

_mock_zdr_resp = MagicMock()
_mock_zdr_resp.status_code = 200
_mock_zdr_resp.json.return_value = {
    "data": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]
}
_mock_zdr_resp.raise_for_status = MagicMock()

_mock_models_zdr = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude"},
        {"id": "google/gemini-2.0-flash-exp", "name": "Gemini"},
    ]
}
_mock_models_zdr_resp = MagicMock()
_mock_models_zdr_resp.status_code = 200
_mock_models_zdr_resp.json.return_value = _mock_models_zdr
_mock_models_zdr_resp.raise_for_status = MagicMock()


def _zdr_router(url, *args, **kwargs):
    if "/endpoints/zdr" in url:
        return _mock_zdr_resp
    return _mock_models_zdr_resp


_pipe_zdr = Pipe()
_pipe_zdr.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ZDR_MODELS_ONLY=True)
_pipe_zdr._models_cache = None
with patch.object(_pipe_zdr._session, "get", side_effect=_zdr_router):
    _zdr_models = _pipe_zdr.pipes()
_zdr_ids = {m["id"] for m in _zdr_models}
_assert(_zdr_ids == {"openai/gpt-4o", "anthropic/claude-3.5-sonnet"},
        "ZDR_MODELS_ONLY: catalog narrowed to ZDR-capable IDs")

# Loader caches: no second HTTP call when called twice
_pipe_zdr2 = Pipe()
_pipe_zdr2.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_zdr_call_count = 0


def _counting_zdr_router(url, *args, **kwargs):
    global _zdr_call_count
    if "/endpoints/zdr" in url:
        _zdr_call_count += 1
    return _mock_zdr_resp if "/endpoints/zdr" in url else _mock_models_zdr_resp


with patch.object(_pipe_zdr2._session, "get", side_effect=_counting_zdr_router):
    _ = _pipe_zdr2._load_zdr_model_ids()
    _ = _pipe_zdr2._load_zdr_model_ids()
_assert(_zdr_call_count == 1, "_load_zdr_model_ids: cached after first call")

# ── 19j. _build_cache_key includes new filters ──────────────────────────────
_section("19j. cache key includes FREE_MODEL_FILTER / TOOL_CALLING_FILTER / ZDR_MODELS_ONLY / MODEL_VARIANTS")

_keys = []
for v in [
    {},
    {"FREE_MODEL_FILTER": "only"},
    {"TOOL_CALLING_FILTER": "exclude"},
    {"ZDR_MODELS_ONLY": True},
    {"MODEL_VARIANTS": "openai/gpt-4o:nitro"},
]:
    _p = Pipe()
    _p.valves = Pipe.Valves(OPENROUTER_API_KEY="k", **v)
    _keys.append(_p._build_cache_key())
_assert(len(set(_keys)) == len(_keys), "cache key fingerprint differs per new-filter valve")

# ── 20. Base URL validator ───────────────────────────────────────────────────

_section("20. Base URL validator")

from pydantic import ValidationError as _ValidationError

# 20a. Invalid URL raises
_url_raised = False
try:
    Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="not-a-url")
except _ValidationError:
    _url_raised = True
_assert(_url_raised, "base URL without http(s):// raises ValidationError")

# 20b. Valid https passes
_url_ok = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="https://custom.api.example.com")
_assert(_url_ok.OPENROUTER_BASE_URL == "https://custom.api.example.com", "valid https URL accepted")

# 20c. http also passes
_url_http = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="http://localhost:8080")
_assert(_url_http.OPENROUTER_BASE_URL == "http://localhost:8080", "http URL accepted")

# ── 21. pipe() guards ───────────────────────────────────────────────────────

_section("21. pipe() guards")

# 21a. model_id == "error" returns actionable message
async def _test_pipe_error_model():
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    return await p.pipe({"model": "openrouter.error", "messages": [{"role": "user", "content": "hi"}], "stream": False})

_res_err_model = asyncio.run(_test_pipe_error_model())
_assert("No valid model selected" in _res_err_model, "error model guard: actionable message")
_assert("OpenRouter Error:" in _res_err_model, "error model guard: has prefix")

# 21b. Empty messages returns error
async def _test_pipe_empty_msgs():
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    return await p.pipe({"model": "openai/gpt-4o", "messages": [], "stream": False})

_res_empty_msgs = asyncio.run(_test_pipe_empty_msgs())
_assert("No messages provided" in _res_empty_msgs, "empty messages guard: clear error")
_assert("OpenRouter Error:" in _res_empty_msgs, "empty messages guard: has prefix")

# 21c. No messages key at all
async def _test_pipe_no_msgs_key():
    p = Pipe()
    p.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
    return await p.pipe({"model": "openai/gpt-4o", "stream": False})

_res_no_key = asyncio.run(_test_pipe_no_msgs_key())
_assert("No messages provided" in _res_no_key, "missing messages key: clear error")

# ── 22. Fallback model attribution ──────────────────────────────────────────

_section("22. Fallback model attribution")

# 22a. "Responded by" shown when fallback model responds
_mock_fallback_json = {
    "choices": [{"message": {"content": "Fallback reply"}}],
    "model": "anthropic/claude-3.5-sonnet",
}
_mock_fallback_resp = MagicMock()
_mock_fallback_resp.json.return_value = _mock_fallback_json

_pipe_fb = Pipe()
_pipe_fb.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

with patch.object(_pipe_fb, "_retryable_request", return_value=_mock_fallback_resp):
    _fb_result = _pipe_fb._non_stream_response({}, {
        "model": "openai/gpt-4o",
        "models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
    }, _pipe_fb.valves)
_assert("Responded by: anthropic/claude-3.5-sonnet" in _fb_result, "fallback attribution shown")

# 22b. No attribution when primary model responds
_mock_primary_json = {
    "choices": [{"message": {"content": "Primary reply"}}],
    "model": "openai/gpt-4o",
}
_mock_primary_resp = MagicMock()
_mock_primary_resp.json.return_value = _mock_primary_json

with patch.object(_pipe_fb, "_retryable_request", return_value=_mock_primary_resp):
    _primary_result = _pipe_fb._non_stream_response({}, {
        "model": "openai/gpt-4o",
        "models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
    }, _pipe_fb.valves)
_assert("Responded by" not in _primary_result, "no attribution when primary responds")

# ── 23. Citation edge cases ─────────────────────────────────────────────────

_section("23. Citation edge cases")

# 23a. URL with parentheses gets encoded
_paren_citations = ["https://en.wikipedia.org/wiki/Test_(disambiguation)"]
_paren_result = _insert_citations("See [1].", _paren_citations)
_assert("%29" in _paren_result, "parenthesis in URL encoded as %29")
_assert("Test_(disambiguation" in _paren_result, "citation content preserved")

# 23b. Unsafe URL not linked
_unsafe_citations = ["javascript:alert(1)"]
_unsafe_result = _insert_citations("See [1].", _unsafe_citations)
_assert("[1]" in _unsafe_result, "unsafe URL: reference kept as-is")
_assert("javascript:" not in _unsafe_result.replace("[1]", ""), "unsafe URL: not linked")

# 23c. Mixed safe and unsafe
_mixed_citations = ["https://safe.com", "javascript:alert(1)"]
_mixed_result = _insert_citations("See [1] and [2].", _mixed_citations)
_assert("[[1]](https://safe.com)" in _mixed_result, "mixed: safe URL linked")
_assert("[[2]]" not in _mixed_result, "mixed: unsafe URL not linked")

# ── 24. pipes() edge cases ──────────────────────────────────────────────────

_section("24. pipes() edge cases")

# 24a. Model without "id" is skipped
_pipe_skip = Pipe()
_pipe_skip.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_pipe_skip._models_cache = None
_mock_skip_resp = MagicMock()
_mock_skip_resp.status_code = 200
_mock_skip_resp.json.return_value = {"data": [
    {"name": "Missing ID Model"},
    {"id": "openai/gpt-4o", "name": "GPT-4o"},
    {"id": "", "name": "Empty ID Model"},
]}
_mock_skip_resp.raise_for_status = MagicMock()

with patch.object(_pipe_skip._session, "get", return_value=_mock_skip_resp):
    _skip_models = _pipe_skip.pipes()
_assert(len(_skip_models) == 1, "pipes: skips models without id")
_assert(_skip_models[0]["id"] == "openai/gpt-4o", "pipes: only valid model kept")

# 24b. FREE_ONLY with :free suffix
_pipe_free = Pipe()
_pipe_free.valves = Pipe.Valves(OPENROUTER_API_KEY="k", FREE_MODEL_FILTER="only")
_pipe_free._models_cache = None
_mock_free_resp = MagicMock()
_mock_free_resp.status_code = 200
_mock_free_resp.json.return_value = {"data": [
    {"id": "openai/gpt-4o:free", "name": "GPT-4o Free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "pricing": {"prompt": "5", "completion": "15"}},
]}
_mock_free_resp.raise_for_status = MagicMock()

with patch.object(_pipe_free._session, "get", return_value=_mock_free_resp):
    _free_models = _pipe_free.pipes()
_assert(len(_free_models) == 1, "FREE_ONLY: only :free model kept")
_assert(":free" in _free_models[0]["id"], "FREE_ONLY: model has :free suffix")

# 24c. Provider icon utility (static method)
_assert(Pipe.get_provider_icon("openai") is not None, "provider icon: openai icon available")
_assert("images/icons" in Pipe.get_provider_icon("openai"), "provider icon: openai URL uses /images/icons/")
_assert(Pipe.get_provider_icon("unknown-xyz") is None, "provider icon: unknown returns None")

# ── 25. _sync_model_icons ───────────────────────────────────────────────────

_section("25. _sync_model_icons()")

# 25a. Graceful no-op outside Open WebUI (ImportError on open_webui.models.models)
_pipe_sync = Pipe()
_pipe_sync.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe_sync._sync_model_icons([
    {"id": "openai/gpt-4o", "name": "GPT-4o"},
    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude"},
    {"id": "error", "name": "Error model"},
    {"id": "unknown-provider/model", "name": "Unknown"},
])
_assert(True, "_sync_model_icons: no error outside Open WebUI (graceful ImportError)")

# 25b. SYNC_PROVIDER_ICONS=False skips sync entirely
_pipe_no_sync = Pipe()
_pipe_no_sync.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=False)
_pipe_no_sync._models_cache = None
_mock_nosync = MagicMock()
_mock_nosync.status_code = 200
_mock_nosync.json.return_value = {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]}
_mock_nosync.raise_for_status = MagicMock()
with patch.object(_pipe_no_sync._session, "get", return_value=_mock_nosync):
    _pipe_no_sync.pipes()
_assert(len(_pipe_no_sync._icons_synced) == 0, "SYNC_PROVIDER_ICONS=False: no sync")

# 25c. SYNC_PROVIDER_ICONS=True calls _sync_model_icons
_pipe_with_sync = Pipe()
_pipe_with_sync.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe_with_sync._models_cache = None
_mock_withsync = MagicMock()
_mock_withsync.status_code = 200
_mock_withsync.json.return_value = {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]}
_mock_withsync.raise_for_status = MagicMock()
with patch.object(_pipe_with_sync._session, "get", return_value=_mock_withsync):
    with patch.object(_pipe_with_sync, "_sync_model_icons") as mock_sync:
        _pipe_with_sync.pipes()
        _assert(mock_sync.called, "SYNC_PROVIDER_ICONS=True: _sync_model_icons called")

# 25d. Valve default is True
_assert(Pipe.Valves(OPENROUTER_API_KEY="k").SYNC_PROVIDER_ICONS is True, "SYNC_PROVIDER_ICONS default is True")

# 25e. No function_id → returns early without DB calls
# function_id is cached in __init__; pipes created in tests have _function_id=None
# because the test module name doesn't start with "function_".
_pipe_nofunc = Pipe()
_pipe_nofunc.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_mock_Models_nf = MagicMock()
_fake_owui_nf = ModuleType("open_webui.models.models")
_fake_owui_nf.Models = _mock_Models_nf
_fake_owui_nf.ModelForm = MagicMock()
_fake_owui_nf.ModelMeta = MagicMock()
_fake_owui_nf.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_nf
    # _pipe_nofunc._function_id is None (no "function_" prefix at init time) → skip
    _assert(_pipe_nofunc._function_id is None, "_sync_model_icons: _function_id is None outside OWUI")
    _pipe_nofunc._sync_model_icons([{"id": "openai/gpt-4o", "name": "GPT-4o"}])
    _assert(
        not _mock_Models_nf.get_model_by_id.called,
        "_sync_model_icons: skips DB when _function_id is None",
    )
finally:
    sys.modules.pop("open_webui.models.models", None)

# 25f. With function_id set → uses prefixed IDs; does NOT add to _icons_synced after insert
# (OWUI may overwrite the record after pipes() returns; confirmed on next call)
_pipe_func = Pipe()
_pipe_func.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe_func._function_id = "openrouter_pipe"  # simulate OWUI module naming
_mock_Models_f = MagicMock()
_mock_Models_f.get_model_by_id.return_value = None  # No existing record yet
_mock_ModelForm_f = MagicMock()
_mock_ModelMeta_f = MagicMock()
_mock_ModelParams_f = MagicMock()
_fake_owui_f = ModuleType("open_webui.models.models")
_fake_owui_f.Models = _mock_Models_f
_fake_owui_f.ModelForm = _mock_ModelForm_f
_fake_owui_f.ModelMeta = _mock_ModelMeta_f
_fake_owui_f.ModelParams = _mock_ModelParams_f
try:
    sys.modules["open_webui.models.models"] = _fake_owui_f
    _pipe_func._sync_model_icons([
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5"},
    ])
    # Verify DB lookups used prefixed IDs
    _lookup_ids = [c.args[0] for c in _mock_Models_f.get_model_by_id.call_args_list]
    _assert(
        "openrouter_pipe.openai/gpt-4o" in _lookup_ids,
        "_sync_model_icons: DB lookup uses prefixed ID (openai)",
    )
    _assert(
        "openrouter_pipe.anthropic/claude-3.5-sonnet" in _lookup_ids,
        "_sync_model_icons: DB lookup uses prefixed ID (anthropic)",
    )
    # Verify insert_new_model was called (since get_model_by_id returned None)
    _assert(
        _mock_Models_f.insert_new_model.called,
        "_sync_model_icons: insert_new_model called for new models",
    )
    # Verify the ModelForm ID is prefixed
    _form_calls = _mock_ModelForm_f.call_args_list
    _form_ids = [c.kwargs.get("id", "") for c in _form_calls]
    _assert(
        "openrouter_pipe.openai/gpt-4o" in _form_ids,
        "_sync_model_icons: ModelForm uses prefixed ID (openai)",
    )
    _assert(
        "openrouter_pipe.anthropic/claude-3.5-sonnet" in _form_ids,
        "_sync_model_icons: ModelForm uses prefixed ID (anthropic)",
    )
    # After insert (model not yet registered by OWUI), _icons_synced must NOT be updated.
    # The next cache-hit call will confirm the icon is set correctly.
    _assert(
        "openai/gpt-4o" not in _pipe_func._icons_synced,
        "_sync_model_icons: _icons_synced NOT updated after insert (allows retry)",
    )
finally:
    sys.modules.pop("open_webui.models.models", None)

# 25g. Existing model with user custom icon → skips overwrite
_pipe_skip = Pipe()
_pipe_skip.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe_skip._function_id = "openrouter_pipe"  # simulate OWUI module naming
_mock_Models_s = MagicMock()
_existing_model = MagicMock()
_existing_model.meta.profile_image_url = "https://custom-icon.example.com/icon.png"
_existing_model.name = "Custom GPT"
_existing_model.params = None
_mock_Models_s.get_model_by_id.return_value = _existing_model
_fake_owui_s = ModuleType("open_webui.models.models")
_fake_owui_s.Models = _mock_Models_s
_fake_owui_s.ModelForm = MagicMock()
_fake_owui_s.ModelMeta = MagicMock()
_fake_owui_s.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_s
    _pipe_skip._sync_model_icons([{"id": "openai/gpt-4o", "name": "GPT-4o"}])
    _assert(
        not _mock_Models_s.update_model_by_id.called,
        "_sync_model_icons: skips update when model has user custom icon",
    )
    _assert(
        not _mock_Models_s.insert_new_model.called,
        "_sync_model_icons: skips insert when model has user custom icon",
    )
    _assert(
        "openai/gpt-4o" in _pipe_skip._icons_synced,
        "_sync_model_icons: adds to _icons_synced when skipping custom icon",
    )
finally:
    sys.modules.pop("open_webui.models.models", None)

# 25h. Existing model with OWUI default (data: URL) icon → updates with provider icon
_pipe_update = Pipe()
_pipe_update.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe_update._function_id = "openrouter_pipe"  # simulate OWUI module naming
_mock_Models_u = MagicMock()
_existing_default = MagicMock()
_existing_default.name = "GPT-4o"
_existing_default.meta.profile_image_url = "data:image/svg+xml;base64,ABC123=="
_existing_default.params = None
_mock_Models_u.get_model_by_id.return_value = _existing_default
_fake_owui_u = ModuleType("open_webui.models.models")
_fake_owui_u.Models = _mock_Models_u
_fake_owui_u.ModelForm = MagicMock()
_fake_owui_u.ModelMeta = MagicMock()
_fake_owui_u.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_u
    _pipe_update._sync_model_icons([{"id": "openai/gpt-4o", "name": "GPT-4o"}])
    _assert(
        _mock_Models_u.update_model_by_id.called,
        "_sync_model_icons: updates model when icon is OWUI default (data: URL)",
    )
    _assert(
        not _mock_Models_u.insert_new_model.called,
        "_sync_model_icons: does not insert when model already exists",
    )
    _assert(
        "openai/gpt-4o" in _pipe_update._icons_synced,
        "_sync_model_icons: adds to _icons_synced after successful update",
    )
finally:
    sys.modules.pop("open_webui.models.models", None)

# 25i. _is_owui_managed_icon helper
_is_owui = mod._is_owui_managed_icon
_assert(_is_owui(""), "_is_owui_managed_icon: empty string → True (no icon)")
_assert(_is_owui("data:image/svg+xml;base64,ABC"), "_is_owui_managed_icon: data: URL → True")
_assert(_is_owui("https://openrouter.ai/images/models/openai.svg"), "_is_owui_managed_icon: old /images/models/ URL → True")
_assert(_is_owui("https://openrouter.ai/images/icons/OpenAI.svg"), "_is_owui_managed_icon: new /images/icons/ URL → True")
_assert(_is_owui("https://openrouter.ai/images/icons/Anthropic.svg"), "_is_owui_managed_icon: icons path anthropic → True")
_assert(not _is_owui("https://custom-icon.example.com/icon.png"), "_is_owui_managed_icon: external URL → False")
_assert(not _is_owui("https://cdn.openai.com/logo.png"), "_is_owui_managed_icon: other https URL → False")
_assert(
    _is_owui("https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&url=https://x.ai/&size=256"),
    "_is_owui_managed_icon: gstatic faviconV2 URL → True (registry-sourced, overwriteable)",
)

# ── 25j. _load_provider_registry + _get_provider_icon ────────────────────────
_section("25j. provider registry auto-discovery")

# Mock the OpenRouter frontend providers payload
_registry_payload = {
    "data": [
        {"slug": "openai", "name": "OpenAI", "icon": {"url": "/images/icons/OpenAI.svg"}},
        {"slug": "xai", "name": "xAI", "icon": {"url": "https://t0.gstatic.com/faviconV2?url=https://x.ai/&size=256"}},
        {"slug": "arcee-ai", "name": "Arcee AI", "icon": {"url": "https://t0.gstatic.com/faviconV2?url=https://www.arcee.ai/&size=256"}},
        {"slug": "broken", "name": "Broken", "icon": {"url": ""}},  # empty icon — must be skipped
        {"slug": "unsafe", "name": "Unsafe", "icon": {"url": "javascript:alert(1)"}},  # unsafe — must be skipped
        {"slug": "noicon", "name": "NoIcon"},  # no icon key at all
    ]
}
_mock_reg_resp = MagicMock()
_mock_reg_resp.status_code = 200
_mock_reg_resp.json.return_value = _registry_payload

_pipe_reg = Pipe()
_pipe_reg.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")

_reg_call_count = 0
def _counting_reg_get(url, *args, **kwargs):
    global _reg_call_count
    if "all-providers" in url:
        _reg_call_count += 1
        return _mock_reg_resp
    return _mock_reg_resp  # fall-through is fine for this test

with patch.object(_pipe_reg._session, "get", side_effect=_counting_reg_get):
    _r1 = _pipe_reg._load_provider_registry()
    _r2 = _pipe_reg._load_provider_registry()  # cached, no second fetch

_assert(_reg_call_count == 1, "registry: HTTP fetched exactly once (caching)")
_assert(_r1 is _r2, "registry: cached object is the same instance on subsequent calls")
_assert(
    _r1.get("openai") == "https://openrouter.ai/images/icons/OpenAI.svg",
    "registry: relative /images/icons/ URL resolved against openrouter.ai",
)
_assert(
    _r1.get("xai", "").startswith("https://t0.gstatic.com/faviconV2"),
    "registry: gstatic favicon URL kept verbatim",
)
_assert(
    _r1.get("arcee-ai") == _r1.get("arceeai"),
    "registry: hyphen-stripped slug also indexed (arcee-ai → arceeai)",
)
_assert("broken" not in _r1, "registry: empty icon URL skipped")
_assert("unsafe" not in _r1, "registry: unsafe (non-http) icon URL skipped")
_assert("noicon" not in _r1, "registry: entry without icon key skipped")

# 25k. _get_provider_icon layered lookup (gstatic favicons enabled)
_pipe_lookup = Pipe()
_pipe_lookup.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", USE_GSTATIC_FAVICONS=True)
with patch.object(_pipe_lookup._session, "get", side_effect=_counting_reg_get):
    # Registry is consulted first; openai is in both registry and hardcoded dict —
    # the registry URL wins and matches the hardcoded one.
    _icon_openai = _pipe_lookup._get_provider_icon("openai")
    _assert(
        _icon_openai == "https://openrouter.ai/images/icons/OpenAI.svg",
        "_get_provider_icon: registry-first hit returns OpenAI icon",
    )

    # Slug not in dict but in registry (exact)
    _icon_arcee = _pipe_lookup._get_provider_icon("arcee-ai")
    _assert(
        _icon_arcee and _icon_arcee.startswith("https://t0.gstatic.com/faviconV2"),
        "_get_provider_icon: registry exact-slug hit (arcee-ai)",
    )

    # Hyphen-strip normalization: x-ai (model author) → xai (registry slug)
    _icon_xai = _pipe_lookup._get_provider_icon("x-ai")
    _assert(
        _icon_xai and _icon_xai.startswith("https://t0.gstatic.com/faviconV2"),
        "_get_provider_icon: hyphen-strip normalization (x-ai → xai)",
    )

    # Truly unknown provider returns None (registry has no entry)
    _icon_missing = _pipe_lookup._get_provider_icon("totally-unknown-provider")
    _assert(
        _icon_missing is None,
        "_get_provider_icon: unknown provider returns None",
    )

    # Empty/None provider key
    _assert(_pipe_lookup._get_provider_icon("") is None, "_get_provider_icon: empty key → None")

# 25k2. USE_GSTATIC_FAVICONS default OFF → gstatic registry icons suppressed
_pipe_nogstatic = Pipe()
_pipe_nogstatic.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")  # USE_GSTATIC_FAVICONS defaults False
with patch.object(_pipe_nogstatic._session, "get", side_effect=_counting_reg_get):
    # arcee-ai only resolvable via gstatic → suppressed → None (not in hardcoded dict)
    _assert(
        _pipe_nogstatic._get_provider_icon("arcee-ai") is None,
        "_get_provider_icon: gstatic suppressed when USE_GSTATIC_FAVICONS off",
    )
    # openai is in the hardcoded dict → still resolves even with gstatic off
    _assert(
        _pipe_nogstatic._get_provider_icon("openai") == "https://openrouter.ai/images/icons/OpenAI.svg",
        "_get_provider_icon: hardcoded icon still returned with gstatic off",
    )

# 25l. Registry network failure → cached empty dict, no retry within TTL window
_pipe_fail = Pipe()
_pipe_fail.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")

_fail_call_count = 0
def _failing_reg_get(*args, **kwargs):
    global _fail_call_count
    _fail_call_count += 1
    raise Exception("simulated network failure")

with patch.object(_pipe_fail._session, "get", side_effect=_failing_reg_get):
    _r_fail = _pipe_fail._load_provider_registry()
    _r_fail_2 = _pipe_fail._load_provider_registry()  # within back-off — no second fetch
_assert(_r_fail == {}, "registry: network failure → empty dict (no prior registry)")
_assert(_fail_call_count == 1, "registry: no retry within FAIL_TTL back-off window after failure")

# Hardcoded dict still works after registry failure
_assert(
    _pipe_fail._get_provider_icon("openai") == "https://openrouter.ai/images/icons/OpenAI.svg",
    "_get_provider_icon: hardcoded dict still resolves after registry failure",
)
_assert(
    _pipe_fail._get_provider_icon("x-ai") is None,
    "_get_provider_icon: x-ai falls back to None when registry failed",
)

# 25m. Registry HTTP non-200 → log message; empty dict on first-ever fetch;
#       existing registry preserved if one was already loaded.
_mock_reg_403 = MagicMock()
_mock_reg_403.status_code = 403
_mock_reg_403.json.return_value = {"data": []}

# 25m-a: first fetch fails → empty dict + warning logged
_pipe_403 = Pipe()
_pipe_403.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_log_403_msgs = []
with patch("builtins.print", side_effect=lambda *a, **kw: _log_403_msgs.append(" ".join(str(x) for x in a))):
    with patch.object(_pipe_403._session, "get", return_value=_mock_reg_403):
        _r_403 = _pipe_403._load_provider_registry()
_assert(_r_403 == {}, "registry: HTTP 403 on first fetch → empty dict")
_assert(
    any("403" in m for m in _log_403_msgs),
    "registry: HTTP 403 logs a warning message",
)

# 25m-b: subsequent non-200 with an existing registry → old registry preserved
_pipe_403_preserve = Pipe()
_pipe_403_preserve.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_pipe_403_preserve._provider_registry = {"openai": "https://example.com/openai.svg"}
_pipe_403_preserve._provider_registry_ts = _time_mod.monotonic() - _PROVIDER_REGISTRY_TTL - 1
with patch.object(_pipe_403_preserve._session, "get", return_value=_mock_reg_403):
    _r_403_preserve = _pipe_403_preserve._load_provider_registry()
_assert(
    _r_403_preserve == {"openai": "https://example.com/openai.svg"},
    "registry: HTTP 403 preserves existing non-empty registry",
)

# 25m-c: after FAIL_TTL back-off expires a new fetch is attempted
_pipe_fail_backoff = Pipe()
_pipe_fail_backoff.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
_pipe_fail_backoff._provider_registry = {"openai": "https://example.com/openai.svg"}
_pipe_fail_backoff._provider_registry_ts = _time_mod.monotonic() - _PROVIDER_REGISTRY_TTL - 1

_backoff_call_count = 0
def _backoff_403_get(url, *args, **kwargs):
    global _backoff_call_count
    if "all-providers" in url:
        _backoff_call_count += 1
    return _mock_reg_403

with patch.object(_pipe_fail_backoff._session, "get", side_effect=_backoff_403_get):
    _pipe_fail_backoff._load_provider_registry()           # fetch 1 → fail, set backoff ts
    # expire the back-off window
    _pipe_fail_backoff._provider_registry_ts -= _PROVIDER_REGISTRY_FAIL_TTL + 1
    _pipe_fail_backoff._load_provider_registry()           # fetch 2 → retried after backoff
_assert(_backoff_call_count == 2, "registry: re-fetches after FAIL_TTL back-off expires")

# 25n. Registry TTL expiry forces re-fetch
_pipe_ttl = Pipe()
_pipe_ttl.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")

_ttl_call_count = 0
def _ttl_reg_get(url, *args, **kwargs):
    global _ttl_call_count
    if "all-providers" in url:
        _ttl_call_count += 1
    return _mock_reg_resp  # reuse payload mock

with patch.object(_pipe_ttl._session, "get", side_effect=_ttl_reg_get):
    _pipe_ttl._load_provider_registry()               # first fetch
    _pipe_ttl._provider_registry_ts -= _PROVIDER_REGISTRY_TTL + 1  # expire TTL
    _pipe_ttl._load_provider_registry()               # should re-fetch
_assert(_ttl_call_count == 2, "registry: re-fetches after TTL expiry")

# 25o. _icons_synced cleared on model cache refresh
_pipe_sync_clear = Pipe()
_pipe_sync_clear.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", SYNC_PROVIDER_ICONS=False)
_pipe_sync_clear._models_cache = None

_mock_models_resp_sc = MagicMock()
_mock_models_resp_sc.status_code = 200
_mock_models_resp_sc.json.return_value = {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]}

with patch.object(_pipe_sync_clear._session, "get", return_value=_mock_models_resp_sc):
    _pipe_sync_clear.pipes()

# Populate _icons_synced to simulate prior sync
_pipe_sync_clear._icons_synced.add("openai/gpt-4o")
_assert(len(_pipe_sync_clear._icons_synced) == 1, "_icons_synced: populated before cache expire")

# Expire cache and call pipes() again — _icons_synced must be cleared.
# Subtract more than the TTL from the stored timestamp so the cache is
# expired regardless of how small time.monotonic() is on a fresh CI runner.
_pipe_sync_clear._models_cache_ts -= mod._MODELS_CACHE_TTL + 1
with patch.object(_pipe_sync_clear._session, "get", return_value=_mock_models_resp_sc):
    _pipe_sync_clear.pipes()

_assert(
    len(_pipe_sync_clear._icons_synced) == 0,
    "_icons_synced: cleared on model cache refresh (allows re-sync after OWUI upsert)",
)

# ── 26. _stream_response() edge cases ────────────────────────────────────────

_section("26. _stream_response() edge cases")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 26a. Reasoning + content in same chunk → <think>…</think> then content
sse_mixed_chunk = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "Inner thought", "content": "Answer"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_mixed_chunk)):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" in full, "stream mixed chunk: <think> opened for reasoning")
_assert("Inner thought" in full, "stream mixed chunk: reasoning present")
_assert("</think>" in full, "stream mixed chunk: </think> closed before content")
_assert("Answer" in full, "stream mixed chunk: content present after think")

# 26b. Empty reasoning string → <think> NOT opened
sse_empty_reason = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "", "content": "Only content"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_empty_reason)):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("<think>" not in full, "stream empty reasoning: <think> NOT opened")
_assert("Only content" in full, "stream empty reasoning: content still present")

# 26c. Empty content string → nothing yielded for that chunk
sse_empty_content = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": ""}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_empty_content)):
    output = list(pipe._stream_response({}, {}, pipe.valves))
_assert("".join(output) == "", "stream empty content string: nothing yielded")

# 26d. Non-dict item in choices[0] → skipped safely, next chunk processed
sse_bad_choice = [
    b"data: " + json.dumps({"choices": [42]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "OK"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_bad_choice)):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("OK" in full, "stream non-dict choice: skipped safely, next chunk processed")

# 26e. Citations-only chunk (no choices) → updates citations used by later content
sse_citations_first = [
    b"data: " + json.dumps({"citations": ["https://example.com"]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "See [1]"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_citations_first)):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("https://example.com" in full, "stream citations-only chunk: citation applied to later content")
_assert("Citations:" in full, "stream citations-only chunk: citation list appended")

# 26f. Generic exception raised by _retryable_request → yields OpenRouter Error
with patch.object(pipe, "_retryable_request", side_effect=ValueError("unexpected")):
    output = list(pipe._stream_response({}, {}, pipe.valves))
full = "".join(output)
_assert("OpenRouter Error" in full, "stream generic exception: error yielded")
_assert("unexpected" in full, "stream generic exception: detail preserved")

# ── 27. pipes() additional paths ─────────────────────────────────────────────

_section("27. pipes() additional paths")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")

# 27a. Model missing "id" key → skipped
_mock_no_id = MagicMock()
_mock_no_id.status_code = 200
_mock_no_id.raise_for_status = MagicMock()
_mock_no_id.json.return_value = {
    "data": [
        {"name": "No ID model"},
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
    ]
}
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_no_id):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes: model missing 'id' is skipped")
_assert(models[0]["id"] == "openai/gpt-4o", "pipes: model with valid id kept")

# 27b. Model missing "name" key → falls back to model_id as name
_mock_no_name = MagicMock()
_mock_no_name.status_code = 200
_mock_no_name.raise_for_status = MagicMock()
_mock_no_name.json.return_value = {
    "data": [
        {"id": "openai/gpt-4o"},
    ]
}
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_no_name):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes: model missing 'name' returns 1 entry")
_assert("openai/gpt-4o" in models[0]["name"], "pipes: model_id used as fallback name")

# 27c. FREE_ONLY with invalid pricing string (ValueError) → is_free=False → model excluded
_mock_invalid_price = MagicMock()
_mock_invalid_price.status_code = 200
_mock_invalid_price.raise_for_status = MagicMock()
_mock_invalid_price.json.return_value = {
    "data": [
        {"id": "some/model", "name": "Model", "pricing": {"prompt": "not-a-number", "completion": "0"}},
    ]
}
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_MODEL_FILTER="only")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_invalid_price):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes FREE_ONLY invalid pricing: model excluded → error entry")
_assert("No free models" in models[0]["name"], "pipes FREE_ONLY invalid pricing: correct error message")

# 27d. HTTPError on /models with non-JSON body → graceful error (no crash)
_mock_5xx_no_json = MagicMock()
_mock_5xx_no_json.status_code = 503
_mock_5xx_no_json.json.side_effect = ValueError("not JSON")
_mock_5xx_no_json.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=_mock_5xx_no_json)
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key")
pipe._models_cache = None
with patch.object(pipe._session, "get", return_value=_mock_5xx_no_json):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes models non-JSON HTTPError: error id")
_assert("503" in models[0]["name"], "pipes models non-JSON HTTPError: status code in name")

# ── 28. _inject_cache_control() edge cases ────────────────────────────────────

_section("28. _inject_cache_control() edge cases")

pipe = Pipe()

# 28a. All image_url chunks → no cache_control applied (no text chunks to tag)
payload_all_img = {
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://img.example.com/a.jpg"}},
                {"type": "image_url", "image_url": {"url": "https://img.example.com/b.jpg"}},
            ],
        }
    ]
}
pipe._inject_cache_control(payload_all_img, pipe.valves)
_assert(
    all("cache_control" not in chunk for chunk in payload_all_img["messages"][0]["content"]),
    "cache_control: all image chunks → nothing applied",
)

# 28b. Mixed image + text chunks → text chunk gets cache_control, image chunk does not
payload_mixed_img = {
    "messages": [
        {
            "role": "system",
            "content": [
                {"type": "image_url", "image_url": {"url": "https://img.example.com/a.jpg"}},
                {"type": "text", "text": "Describe this image in detail."},
            ],
        }
    ]
}
pipe._inject_cache_control(payload_mixed_img, pipe.valves)
_assert(
    "cache_control" not in payload_mixed_img["messages"][0]["content"][0],
    "cache_control: image_url chunk skipped in mixed content",
)
_assert(
    payload_mixed_img["messages"][0]["content"][1].get("cache_control")
    == {"type": "ephemeral", "ttl": "5m"},
    "cache_control: text chunk in mixed content gets cache_control",
)

# 28c. User role list content (no system) → falls through to user, applies cache_control
payload_user_list = {
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Short"},
                {"type": "text", "text": "A longer user message that should receive cache_control injection"},
            ],
        }
    ]
}
pipe._inject_cache_control(payload_user_list, pipe.valves)
_assert(
    payload_user_list["messages"][0]["content"][1].get("cache_control")
    == {"type": "ephemeral", "ttl": "5m"},
    "cache_control: user role list content gets cache_control when no system role",
)

# ── 28d. v1.6.0 — Web search plugin builder ─────────────────────────────────
_section("28d. v1.6.0 web search plugin")

_pipe_ws = Pipe()
_pipe_ws.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_WEB_SEARCH=False)
_assert(_pipe_ws._build_web_search_plugin(_pipe_ws.valves) is None, "web search disabled → None")

_pipe_ws.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    ENABLE_WEB_SEARCH=True,
    WEB_SEARCH_MAX_RESULTS=8,
    WEB_SEARCH_PROMPT="Find authoritative sources",
    WEB_SEARCH_INCLUDE_DOMAINS="*.gov, *.edu",
    WEB_SEARCH_EXCLUDE_DOMAINS="reddit.com",
)
_plugin = _pipe_ws._build_web_search_plugin(_pipe_ws.valves)
_assert(_plugin and _plugin["id"] == "web", "web plugin id is 'web'")
_assert(_plugin["max_results"] == 8, "max_results forwarded")
_assert(_plugin["search_prompt"] == "Find authoritative sources", "custom search_prompt")
_assert(_plugin["include_domains"] == ["*.gov", "*.edu"], "include_domains parsed")
_assert(_plugin["exclude_domains"] == ["reddit.com"], "exclude_domains parsed")

# Payload integration: appended to existing user plugins, never duplicated
_pipe_ws = Pipe()
_pipe_ws.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_WEB_SEARCH=True)
_p_ws = _pipe_ws._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_ws.valves)
_assert(any(p.get("id") == "web" for p in _p_ws.get("plugins", [])),
        "ENABLE_WEB_SEARCH: plugins[] contains web entry")

# User plugins preserved alongside web
_pipe_ws.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_WEB_SEARCH=True)
_p_ws = _pipe_ws._prepare_payload({
    "model": "openai/gpt-4o",
    "messages": [],
    "plugins": [{"id": "file-parser"}],
}, _pipe_ws.valves)
_p_ids = [p.get("id") for p in _p_ws.get("plugins", [])]
_assert("file-parser" in _p_ids and "web" in _p_ids, "user plugins coexist with auto web plugin")

# Existing user-supplied web plugin wins
_pipe_ws.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_WEB_SEARCH=True, WEB_SEARCH_MAX_RESULTS=20)
_p_ws = _pipe_ws._prepare_payload({
    "model": "openai/gpt-4o",
    "messages": [],
    "plugins": [{"id": "web", "max_results": 3}],
}, _pipe_ws.valves)
_assert(
    sum(1 for p in _p_ws["plugins"] if p.get("id") == "web") == 1,
    "user-supplied web plugin not duplicated by valve injection",
)
_assert(
    _p_ws["plugins"][0].get("max_results") == 3,
    "user-supplied web plugin keeps its own max_results",
)

# Web search disabled → no plugin emitted at all
_pipe_ws.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_WEB_SEARCH=False)
_p_ws = _pipe_ws._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_ws.valves)
_assert("plugins" not in _p_ws, "web search disabled: no plugins key added")

# ── 28e. v1.6.0 — REASONING_MAX_TOKENS ──────────────────────────────────────
_section("28e. v1.6.0 reasoning max_tokens")

_pipe_rmt = Pipe()
_pipe_rmt.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k", REASONING_EFFORT="high", REASONING_MAX_TOKENS=2048
)
_p_rmt = _pipe_rmt._prepare_payload({"model": "openai/o1", "messages": []}, _pipe_rmt.valves)
_assert(
    _p_rmt.get("reasoning") == {"effort": "high", "max_tokens": 2048},
    "reasoning.max_tokens emitted alongside effort",
)

_pipe_rmt.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_MAX_TOKENS=0)
_p_rmt = _pipe_rmt._prepare_payload({"model": "openai/o1", "messages": []}, _pipe_rmt.valves)
_assert("reasoning" not in _p_rmt, "max_tokens=0 + no effort: reasoning key omitted")

# ── 28f. v1.6.0 — Provider extras (only/quantizations/allow_fallbacks/max_price) ──
_section("28f. v1.6.0 provider preferences extras")

_pipe_pp = Pipe()
_pipe_pp.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    PROVIDER_ONLY="anthropic, openai",
    PROVIDER_QUANTIZATIONS="bf16, fp8",
    PROVIDER_ALLOW_FALLBACKS=False,
    PROVIDER_MAX_PRICE_PROMPT="3.0",
    PROVIDER_MAX_PRICE_COMPLETION="15.0",
)
_p_pp = _pipe_pp._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_pp.valves)
_p_provider = _p_pp.get("provider", {})
_assert(_p_provider.get("only") == ["anthropic", "openai"], "provider.only forwarded")
_assert(_p_provider.get("quantizations") == ["bf16", "fp8"], "provider.quantizations lower-cased")
_assert(_p_provider.get("allow_fallbacks") is False, "provider.allow_fallbacks=False emitted only when opted out")
_assert(
    _p_provider.get("max_price") == {"prompt": "3.0", "completion": "15.0"},
    "provider.max_price merged",
)

# Defaults: allow_fallbacks=true is implicit (omit field)
_pipe_pp.valves = Pipe.Valves(OPENROUTER_API_KEY="k", PROVIDER_ALLOW_FALLBACKS=True)
_p_pp = _pipe_pp._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_pp.valves)
_assert(
    "provider" not in _p_pp or "allow_fallbacks" not in _p_pp.get("provider", {}),
    "PROVIDER_ALLOW_FALLBACKS=True (default): field omitted",
)

# ── 28g. v1.6.0 — SERVICE_TIER ──────────────────────────────────────────────
_section("28g. v1.6.0 service tier")

# Only OpenRouter's documented tiers ('flex','priority') are forwarded.
for tier in ("flex", "priority"):
    _pipe_st = Pipe()
    _pipe_st.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SERVICE_TIER=tier)
    _p_st = _pipe_st._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_st.valves)
    _assert(_p_st.get("service_tier") == tier, f"SERVICE_TIER='{tier}' forwarded")

# Undocumented OpenAI-direct tiers + garbage are dropped (not valid on OpenRouter)
for tier in ("auto", "default", "scale", "bogus"):
    _pipe_st = Pipe()
    _pipe_st.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SERVICE_TIER=tier)
    _p_st = _pipe_st._prepare_payload({"model": "openai/gpt-4o", "messages": []}, _pipe_st.valves)
    _assert("service_tier" not in _p_st, f"unsupported SERVICE_TIER='{tier}' dropped")

# ── 28h. v1.6.0 — Cached prompt-token cost breakdown ────────────────────────
_section("28h. v1.6.0 cached prompt token reporting")

_format_cost_info = mod._format_cost_info

# OpenAI / Anthropic shape: prompt_tokens_details.cached_tokens
_cost_with_cache = _format_cost_info({
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "total_tokens": 1200,
    "prompt_tokens_details": {"cached_tokens": 800},
    "cost": 0.0030,
}, "USD")
_assert("800 cached" in _cost_with_cache, "cached tokens shown in token line")
_assert("200 prompt" in _cost_with_cache, "non-cached prompt tokens shown (1000-800=200)")

# Alternate shape: cache_read_input_tokens (some Anthropic surfaces)
_cost_alt = _format_cost_info({
    "prompt_tokens": 500,
    "completion_tokens": 100,
    "cache_read_input_tokens": 400,
}, "USD")
_assert("400 cached" in _cost_alt, "cache_read_input_tokens recognised")

# No cache info → original format preserved
_cost_plain = _format_cost_info({
    "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150
}, "USD")
_assert("cached" not in _cost_plain, "no cache field: footer unchanged")

# ── 28i. v1.6.0 — Generation ID footer ──────────────────────────────────────
_section("28i. v1.6.0 generation id footer")

_format_gen = mod._format_generation_id
_assert(_format_gen(None) == "", "None → empty string")
_assert(_format_gen("") == "", "empty → empty string")
out = _format_gen("gen-abc123")
_assert("gen-abc123" in out, "generation id appears in footer")
_assert("`gen-abc123`" in out, "generation id wrapped in backticks for click-to-copy")

# Non-stream response surfaces the id when SHOW_GENERATION_ID=True
_pipe_gen = Pipe()
_pipe_gen.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_GENERATION_ID=True)
_mock_gen_resp = MagicMock()
_mock_gen_resp.json.return_value = {
    "id": "gen-zzz111",
    "model": "openai/gpt-4o",
    "choices": [{"message": {"content": "hi", "role": "assistant"}}],
}
with patch.object(_pipe_gen, "_retryable_request", return_value=_mock_gen_resp):
    _out = _pipe_gen._non_stream_response({}, {"model": "openai/gpt-4o"}, _pipe_gen.valves)
_assert("gen-zzz111" in _out, "non-stream: generation id rendered when SHOW_GENERATION_ID=True")

# Toggled off → no footer
_pipe_gen.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_GENERATION_ID=False)
_mock_gen_resp.json.return_value = {
    "id": "gen-zzz111",
    "model": "openai/gpt-4o",
    "choices": [{"message": {"content": "hi", "role": "assistant"}}],
}
with patch.object(_pipe_gen, "_retryable_request", return_value=_mock_gen_resp):
    _out = _pipe_gen._non_stream_response({}, {"model": "openai/gpt-4o"}, _pipe_gen.valves)
_assert("gen-zzz111" not in _out, "SHOW_GENERATION_ID=False: footer suppressed")

# ── 28j. v1.6.0 — MODEL_CATEGORY query param ────────────────────────────────
_section("28j. v1.6.0 MODEL_CATEGORY")

_mock_cat_resp = MagicMock()
_mock_cat_resp.status_code = 200
_mock_cat_resp.json.return_value = {"data": [{"id": "openai/gpt-4o", "name": "GPT-4o"}]}
_mock_cat_resp.raise_for_status = MagicMock()

_captured_params = {}

def _capture_cat(*args, **kwargs):
    _captured_params.clear()
    _captured_params.update(kwargs)
    return _mock_cat_resp

_pipe_cat = Pipe()
_pipe_cat.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_CATEGORY="programming")
_pipe_cat._models_cache = None
with patch.object(_pipe_cat._session, "get", side_effect=_capture_cat):
    _pipe_cat.pipes()
_assert(
    _captured_params.get("params", {}).get("category") == "programming",
    "MODEL_CATEGORY: '?category=programming' forwarded to /models",
)

# Empty category → no category param sent
_pipe_cat = Pipe()
_pipe_cat.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_CATEGORY="")
_pipe_cat._models_cache = None
with patch.object(_pipe_cat._session, "get", side_effect=_capture_cat):
    _pipe_cat.pipes()
_assert(
    "category" not in _captured_params.get("params", {}),
    "empty MODEL_CATEGORY: no category param sent",
)

# ── 28k. v1.6.0 — Deprecated model tagging ──────────────────────────────────
_section("28k. v1.6.0 deprecated model handling")

_mock_deprec = {
    "data": [
        {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5", "expiration_date": "2026-09-01"},
        {"id": "openai/gpt-4o", "name": "GPT-4o"},
    ]
}
_mock_deprec_resp = MagicMock()
_mock_deprec_resp.status_code = 200
_mock_deprec_resp.json.return_value = _mock_deprec
_mock_deprec_resp.raise_for_status = MagicMock()

# Default: deprecated kept and tagged
_pipe_dep = Pipe()
_pipe_dep.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_pipe_dep._models_cache = None
with patch.object(_pipe_dep._session, "get", return_value=_mock_deprec_resp):
    _dep_models = _pipe_dep.pipes()
_dep_by_id = {m["id"]: m["name"] for m in _dep_models}
_assert("openai/gpt-3.5-turbo" in _dep_by_id, "deprecated model still listed by default")
_assert("⚠" in _dep_by_id["openai/gpt-3.5-turbo"], "deprecated model tagged with ⚠ marker")
_assert("(deprecated)" in _dep_by_id["openai/gpt-3.5-turbo"], "deprecated label appended to name")
_assert("⚠" not in _dep_by_id["openai/gpt-4o"], "live model untouched")

# HIDE_DEPRECATED_MODELS=True drops them
_pipe_dep = Pipe()
_pipe_dep.valves = Pipe.Valves(OPENROUTER_API_KEY="k", HIDE_DEPRECATED_MODELS=True)
_pipe_dep._models_cache = None
with patch.object(_pipe_dep._session, "get", return_value=_mock_deprec_resp):
    _dep_models = _pipe_dep.pipes()
_dep_ids = {m["id"] for m in _dep_models}
_assert(_dep_ids == {"openai/gpt-4o"}, "HIDE_DEPRECATED_MODELS=True: deprecated rows removed")

# ── 28l. v1.6.0 — Cache-key invalidates on new filter valves ────────────────
_section("28l. v1.6.0 cache key includes MODEL_CATEGORY / HIDE_DEPRECATED_MODELS")

_keys_v16 = []
for v in [
    {},
    {"MODEL_CATEGORY": "programming"},
    {"HIDE_DEPRECATED_MODELS": True},
]:
    _p = Pipe()
    _p.valves = Pipe.Valves(OPENROUTER_API_KEY="k", **v)
    _keys_v16.append(_p._build_cache_key())
_assert(len(set(_keys_v16)) == len(_keys_v16), "cache key differs per new v1.6 filter valve")

# ── 29. _non_stream_response() edge cases ────────────────────────────────────

_section("29. _non_stream_response() edge cases")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 29a. choices=[] AND top-level "error" → error message (not "empty response")
_mock_err_empty_choices = MagicMock()
_mock_err_empty_choices.json.return_value = {
    "choices": [],
    "error": {"message": "Context window exceeded"},
}
with patch.object(pipe, "_retryable_request", return_value=_mock_err_empty_choices):
    result = pipe._non_stream_response({}, {}, pipe.valves)
_assert("Context window exceeded" in result, "non-stream: error field takes priority over empty choices")

# 29b. message.content is None → no crash, returns empty string
_mock_none_content = MagicMock()
_mock_none_content.json.return_value = {
    "choices": [{"message": {"content": None}}]
}
with patch.object(pipe, "_retryable_request", return_value=_mock_none_content):
    result = pipe._non_stream_response({}, {}, pipe.valves)
_assert(isinstance(result, str), "non-stream: None content → still returns string")
_assert(result == "", "non-stream: None content → empty string (no crash)")

# 29c. message dict missing "content" key → returns empty string (no crash)
_mock_no_content_key = MagicMock()
_mock_no_content_key.json.return_value = {
    "choices": [{"message": {"role": "assistant"}}]
}
with patch.object(pipe, "_retryable_request", return_value=_mock_no_content_key):
    result = pipe._non_stream_response({}, {}, pipe.valves)
_assert(isinstance(result, str), "non-stream: missing content key → still returns string")
_assert(result == "", "non-stream: missing content key → empty string (no crash)")

# ── 30. Citation helper edge cases ───────────────────────────────────────────

_section("30. Citation helper edge cases")

# 30a. [0] reference → left unchanged (1-based; idx = -1 is out of range)
_assert(
    _insert_citations("See [0].", ["https://example.com"]) == "See [0].",
    "citations: [0] reference left unchanged (1-based indexing)",
)

# 30b. Multiple [1] references in same text → all replaced with the same URL
_result_dup = _insert_citations("See [1] and also [1].", ["https://example.com"])
_assert(
    _result_dup == "See [[1]](https://example.com) and also [[1]](https://example.com).",
    "citations: duplicate [1] references both replaced",
)

# 30c. Citation URL with query params → URL preserved verbatim in the link
_cite_url_params = "https://example.com/article?q=test&ref=2"
_result_params = _insert_citations("Check [1].", [_cite_url_params])
_assert(
    _cite_url_params in _result_params,
    "citations: URL query params preserved verbatim in link",
)

# 30d. _format_citation_list() with duplicate URLs → both listed (no deduplication)
_result_fmt_dup = _format_citation_list(["https://a.com", "https://a.com"])
_assert(_result_fmt_dup.count("https://a.com") == 2, "citations: duplicate URLs both listed")
_assert("1." in _result_fmt_dup and "2." in _result_fmt_dup, "citations: both entries numbered")

# ── 31. All provider icons ───────────────────────────────────────────────────

_section("31. All provider icons")

# Providers confirmed to have icons at /images/icons/ (verified May 2025)
_ALL_PROVIDER_KEYS = [
    "openai", "anthropic", "google", "meta-llama", "mistralai",
    "amazon", "deepseek", "cohere", "perplexity", "qwen",
    "microsoft", "fireworks", "moonshotai",
]
for _prov_key in _ALL_PROVIDER_KEYS:
    _prov_icon = Pipe.get_provider_icon(_prov_key)
    _assert(
        _prov_icon is not None and len(_prov_icon) > 0,
        f"provider icon: '{_prov_key}' → non-empty URL",
    )
    _assert(
        "images/icons" in (_prov_icon or ""),
        f"provider icon: '{_prov_key}' URL uses /images/icons/",
    )

# Providers without icons should return None (no broken-URL fallback)
_NO_ICON_PROVIDERS = ["x-ai", "allenai", "nvidia", "databricks", "together",
                      "sambanova", "cerebras", "groq", "inflection", "01-ai"]
for _prov_key in _NO_ICON_PROVIDERS:
    _assert(
        Pipe.get_provider_icon(_prov_key) is None,
        f"provider icon: '{_prov_key}' → None (no valid icon available)",
    )

_assert(Pipe.get_provider_icon("unknown-provider") is None, "provider icon: unknown → None")
_assert(
    Pipe.get_provider_icon("OPENAI") is not None,
    "provider icon: uppercase input → case-insensitive match",
)

# ── 32. _retryable_request() stream flag ─────────────────────────────────────

_section("32. _retryable_request() stream flag")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 32a. stream=True → requests.Session.post called with stream=True
_mock_ok_stream = MagicMock()
_mock_ok_stream.raise_for_status = MagicMock()
with patch.object(pipe._session, "post", return_value=_mock_ok_stream) as _mock_post_s:
    pipe._retryable_request({}, {}, stream=True, valves=pipe.valves)
_assert(
    _mock_post_s.call_args.kwargs.get("stream") is True
    or _mock_post_s.call_args[1].get("stream") is True,
    "retryable: stream=True forwarded to requests.Session.post",
)

# 32b. stream=False → requests.Session.post called with stream=False
_mock_ok_nostream = MagicMock()
_mock_ok_nostream.raise_for_status = MagicMock()
with patch.object(pipe._session, "post", return_value=_mock_ok_nostream) as _mock_post_ns:
    pipe._retryable_request({}, {}, stream=False, valves=pipe.valves)
_assert(
    _mock_post_ns.call_args.kwargs.get("stream") is False
    or _mock_post_ns.call_args[1].get("stream") is False,
    "retryable: stream=False forwarded to requests.Session.post",
)

# ── 33. _format_cost_info() and SHOW_COST_INFO ──────────────────────────────

_section("33. _format_cost_info() and SHOW_COST_INFO")

_format_cost_info = mod._format_cost_info
_CURRENCY_SYMBOLS = mod._CURRENCY_SYMBOLS

# 33a. Empty usage dict → empty string
_assert(_format_cost_info({}) == "", "_format_cost_info: empty dict → empty")
_assert(_format_cost_info({}, "EUR") == "", "_format_cost_info: empty dict with currency → empty")

# 33b. Usage with tokens only (no cost) → tokens shown
_result_tokens_only = _format_cost_info({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
_assert("100" in _result_tokens_only, "_format_cost_info: prompt tokens present")
_assert("50" in _result_tokens_only, "_format_cost_info: completion tokens present")
_assert("150" in _result_tokens_only, "_format_cost_info: total tokens present")
_assert("Tokens" in _result_tokens_only, "_format_cost_info: Tokens label present")
_assert("Cost" not in _result_tokens_only, "_format_cost_info: no cost when field absent")

# 33c. Zero cost → $0.00
_result_free = _format_cost_info({"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300, "cost": 0})
_assert("$0.00" in _result_free, "_format_cost_info: zero cost → $0.00")
_assert("Cost" in _result_free, "_format_cost_info: Cost label present for zero cost")

# 33d. Micro cost < 0.0001 → 6 decimal places
_result_micro = _format_cost_info({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.000005})
_assert("$0.000005" in _result_micro, "_format_cost_info: micro cost 6 decimal places")

# 33e. Small cost 0.0001–0.01 → 5 decimal places
_result_small = _format_cost_info({"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75, "cost": 0.001234})
_assert("$0.00123" in _result_small, "_format_cost_info: small cost 5 decimal places")

# 33f. Normal cost >= 0.01 → 4 decimal places
_result_normal = _format_cost_info({"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700, "cost": 0.05670})
_assert("$0.0567" in _result_normal, "_format_cost_info: normal cost 4 decimal places")

# 33g. EUR currency symbol
_result_eur = _format_cost_info({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.01}, "EUR")
_assert("€" in _result_eur, "_format_cost_info: EUR symbol shown")

# 33h. GBP currency symbol
_result_gbp = _format_cost_info({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.01}, "GBP")
_assert("£" in _result_gbp, "_format_cost_info: GBP symbol shown")

# 33i. Unknown currency → uses currency string as prefix
_result_unknown = _format_cost_info({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.01}, "XYZ")
_assert("XYZ " in _result_unknown, "_format_cost_info: unknown currency → code as prefix")

# 33j. Invalid cost value (string) → tokens shown, cost silently skipped
_result_bad_cost = _format_cost_info({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": "invalid"})
_assert("Tokens" in _result_bad_cost, "_format_cost_info: invalid cost → tokens still shown")
_assert("Cost" not in _result_bad_cost, "_format_cost_info: invalid cost → cost silently skipped")

# 33k. total_tokens missing → computed as prompt + completion
_result_no_total = _format_cost_info({"prompt_tokens": 80, "completion_tokens": 20, "cost": 0.005})
_assert("100" in _result_no_total, "_format_cost_info: total computed from prompt+completion when missing")

# 33l. Output format: starts with separator, italic, bold labels
_result_fmt = _format_cost_info({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.001})
_assert(_result_fmt.startswith("\n\n---\n"), "_format_cost_info: starts with separator")
_assert("*" in _result_fmt, "_format_cost_info: uses italic (asterisks)")
_assert("**Tokens:**" in _result_fmt, "_format_cost_info: bold Tokens label")
_assert("**Cost:**" in _result_fmt, "_format_cost_info: bold Cost label")

# 33m. Large numbers use comma separators
_result_large = _format_cost_info({"prompt_tokens": 1250, "completion_tokens": 342, "total_tokens": 1592, "cost": 0.00234})
_assert("1,250" in _result_large, "_format_cost_info: large prompt token count formatted with comma")
_assert("1,592" in _result_large, "_format_cost_info: large total formatted with comma")

# 33n. CURRENCY_SYMBOLS dict completeness
for _sym_key in ("USD", "EUR", "GBP", "JPY", "CAD", "AUD"):
    _assert(_sym_key in _CURRENCY_SYMBOLS, f"_CURRENCY_SYMBOLS: {_sym_key} present")

# ── 33 (cont). Non-stream SHOW_COST_INFO integration ────────────────────────

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 33o. SHOW_COST_INFO=False (default) → no cost appended
_mock_cost_off = MagicMock()
_mock_cost_off.json.return_value = {
    "choices": [{"message": {"content": "Hello"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001},
}
with patch.object(pipe, "_retryable_request", return_value=_mock_cost_off):
    _result_off = pipe._non_stream_response({}, {}, pipe.valves)
_assert("---" not in _result_off, "non-stream SHOW_COST_INFO=False: no separator appended")
_assert("Tokens" not in _result_off, "non-stream SHOW_COST_INFO=False: no Tokens line")

# 33p. SHOW_COST_INFO=True → cost appended after content
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True, COST_CURRENCY="USD")
_mock_cost_on = MagicMock()
_mock_cost_on.json.return_value = {
    "choices": [{"message": {"content": "Hello"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.00123},
}
with patch.object(pipe, "_retryable_request", return_value=_mock_cost_on):
    _result_on = pipe._non_stream_response({}, {}, pipe.valves)
_assert("Hello" in _result_on, "non-stream SHOW_COST_INFO=True: content preserved")
_assert("Tokens" in _result_on, "non-stream SHOW_COST_INFO=True: Tokens label present")
_assert("$" in _result_on, "non-stream SHOW_COST_INFO=True: cost shown in USD")
_assert("10" in _result_on, "non-stream SHOW_COST_INFO=True: prompt token count present")

# 33q. SHOW_COST_INFO=True with EUR currency
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True, COST_CURRENCY="EUR")
_mock_cost_eur = MagicMock()
_mock_cost_eur.json.return_value = {
    "choices": [{"message": {"content": "Ciao"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8, "cost": 0.05},
}
with patch.object(pipe, "_retryable_request", return_value=_mock_cost_eur):
    _result_eur_resp = pipe._non_stream_response({}, {}, pipe.valves)
_assert("€" in _result_eur_resp, "non-stream SHOW_COST_INFO=True EUR: euro symbol shown")

# 33r. SHOW_COST_INFO=True but response has no usage → no cost appended (no crash)
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True)
_mock_no_usage = MagicMock()
_mock_no_usage.json.return_value = {
    "choices": [{"message": {"content": "No usage data"}}],
}
with patch.object(pipe, "_retryable_request", return_value=_mock_no_usage):
    _result_no_usage = pipe._non_stream_response({}, {}, pipe.valves)
_assert("No usage data" in _result_no_usage, "non-stream no usage: content preserved")
_assert("Tokens" not in _result_no_usage, "non-stream no usage: no Tokens line (no crash)")

# ── 33 (cont). Stream SHOW_COST_INFO integration ─────────────────────────────

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True, COST_CURRENCY="USD")

# 33s. Usage in final SSE chunk → cost appended after stream
_usage_chunk = {"prompt_tokens": 150, "completion_tokens": 75, "total_tokens": 225, "cost": 0.00567}
sse_with_usage = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Answer"}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {}}], "usage": _usage_chunk}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_with_usage)):
    _stream_output = list(pipe._stream_response({}, {}, pipe.valves))
_stream_full = "".join(_stream_output)
_assert("Answer" in _stream_full, "stream SHOW_COST_INFO=True: content preserved")
_assert("Tokens" in _stream_full, "stream SHOW_COST_INFO=True: Tokens label in output")
_assert("150" in _stream_full, "stream SHOW_COST_INFO=True: prompt token count present")
_assert("$" in _stream_full, "stream SHOW_COST_INFO=True: cost in USD")

# 33t. SHOW_COST_INFO=False → usage in chunk but no cost appended
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=False)
sse_no_cost_display = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Reply"}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {}}], "usage": _usage_chunk}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_no_cost_display)):
    _stream_off_output = list(pipe._stream_response({}, {}, pipe.valves))
_stream_off_full = "".join(_stream_off_output)
_assert("Reply" in _stream_off_full, "stream SHOW_COST_INFO=False: content preserved")
_assert("Tokens" not in _stream_off_full, "stream SHOW_COST_INFO=False: no Tokens line")

# 33u. Stream with no usage chunk → no cost appended, no crash
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True)
sse_no_usage_chunk = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Text"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_no_usage_chunk)):
    _stream_nu_output = list(pipe._stream_response({}, {}, pipe.valves))
_stream_nu_full = "".join(_stream_nu_output)
_assert("Text" in _stream_nu_full, "stream no usage chunk: content preserved")
_assert("Tokens" not in _stream_nu_full, "stream no usage chunk: no cost line (no crash)")

# 33v. COST_CURRENCY valve uses select with 6 options
_cc_field = Pipe.Valves.model_fields["COST_CURRENCY"]
_cc_options = _cc_field.json_schema_extra.get("input", {}).get("options", [])
_assert(len(_cc_options) == 6, "COST_CURRENCY: 6 currency options")
_cc_values = [o["value"] for o in _cc_options]
_assert("USD" in _cc_values, "COST_CURRENCY options: USD present")
_assert("EUR" in _cc_values, "COST_CURRENCY options: EUR present")

# ══════════════════════════════════════════════════════════════════════════════
# 34. Audio and image output model support
# ══════════════════════════════════════════════════════════════════════════════

_section("34. Audio / image output model support")

# 34a. _format_image_output — empty list returns empty string
from openrouter_pipe import _format_image_output
_assert(_format_image_output([]) == "", "_format_image_output: empty list → empty string")
_assert(_format_image_output(None) == "", "_format_image_output: None → empty string")

# 34b. Single image with valid URL → markdown tag
_img_single = [{"image_url": {"url": "data:image/png;base64,ABC=="}}]
_result_img = _format_image_output(_img_single)
_assert(_result_img == "![Generated image](data:image/png;base64,ABC==)", "_format_image_output: single image → markdown tag")

# 34c. Multiple images → joined with double newline
_img_multi = [
    {"image_url": {"url": "data:image/png;base64,AAA=="}},
    {"image_url": {"url": "data:image/png;base64,BBB=="}},
]
_result_multi = _format_image_output(_img_multi)
_assert("![Generated image](data:image/png;base64,AAA==)" in _result_multi, "_format_image_output: multi — first image present")
_assert("![Generated image](data:image/png;base64,BBB==)" in _result_multi, "_format_image_output: multi — second image present")
_assert("\n\n" in _result_multi, "_format_image_output: multi — separated by double newline")

# 34d. Non-dict items in list are skipped gracefully
_img_mixed = ["not_a_dict", {"image_url": {"url": "https://example.com/img.png"}}, 42]
_result_mixed = _format_image_output(_img_mixed)
_assert("https://example.com/img.png" in _result_mixed, "_format_image_output: non-dict items skipped, valid item rendered")
_assert("not_a_dict" not in _result_mixed, "_format_image_output: string item not in output")

# 34e. Image dict missing 'url' key → skipped
_img_no_url = [{"image_url": {}}, {"image_url": {"url": ""}}]
_assert(_format_image_output(_img_no_url) == "", "_format_image_output: missing/empty url → empty string")

# 34e2. Unsafe URL schemes are rejected
_img_js = [{"image_url": {"url": "javascript:alert(1)"}}]
_assert(_format_image_output(_img_js) == "", "_format_image_output: javascript: scheme → empty (rejected)")
_img_file = [{"image_url": {"url": "file:///etc/passwd"}}]
_assert(_format_image_output(_img_file) == "", "_format_image_output: file: scheme → empty (rejected)")

# 34e3. Closing parenthesis in URL is percent-encoded
_img_paren = [{"image_url": {"url": "https://example.com/img(1).png"}}]
_result_paren = _format_image_output(_img_paren)
_assert("%29" in _result_paren, "_format_image_output: ) in URL → percent-encoded as %29")
_assert("(1)" not in _result_paren, "_format_image_output: raw ) not in output")

# ── Non-streaming audio response ───────────────────────────────────────────

_pipe34 = Pipe()
_pipe34.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 34f. Audio model with transcript → transcript used as content
_mock_audio = MagicMock()
_mock_audio.json.return_value = {
    "choices": [{
        "message": {
            "content": None,
            "audio": {"transcript": "Hello from audio", "data": "base64data...", "id": "audio_123"},
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_audio):
    _audio_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert("Hello from audio" in _audio_result, "non-stream audio: transcript used as content")

# 34g. Audio model without transcript → placeholder message returned
_mock_audio_no_transcript = MagicMock()
_mock_audio_no_transcript.json.return_value = {
    "choices": [{
        "message": {
            "content": None,
            "audio": {"data": "base64audiodata...", "id": "audio_456"},
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_audio_no_transcript):
    _audio_no_tx_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert("transcript not available" in _audio_no_tx_result, "non-stream audio no transcript: placeholder shown")

# 34h. Audio model with both content and audio → text content takes priority
_mock_audio_with_content = MagicMock()
_mock_audio_with_content.json.return_value = {
    "choices": [{
        "message": {
            "content": "Text response",
            "audio": {"transcript": "Audio transcript", "data": "base64..."},
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_audio_with_content):
    _audio_content_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert("Text response" in _audio_content_result, "non-stream audio+content: text content preserved")
_assert("Audio transcript" not in _audio_content_result, "non-stream audio+content: transcript not used when content present")

# 34i. Image output model → markdown image tag in response
_mock_image = MagicMock()
_mock_image.json.return_value = {
    "choices": [{
        "message": {
            "content": None,
            "images": [{"image_url": {"url": "data:image/png;base64,IMGDATA=="}}],
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_image):
    _image_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert("![Generated image]" in _image_result, "non-stream image: markdown image tag present")
_assert("IMGDATA==" in _image_result, "non-stream image: URL data in output")

# 34j. Image output with text content → both text and image in response, separated by blank line
_mock_image_with_text = MagicMock()
_mock_image_with_text.json.return_value = {
    "choices": [{
        "message": {
            "content": "Here is the image:",
            "images": [{"image_url": {"url": "data:image/png;base64,IMGDATA2=="}}],
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_image_with_text):
    _image_text_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert("Here is the image:" in _image_text_result, "non-stream image+text: text preserved")
_assert("![Generated image]" in _image_text_result, "non-stream image+text: image markdown present")
_assert("\n\n![Generated image]" in _image_text_result, "non-stream image+text: blank line before image tag")

# 34j2. Image-only (no text) → no leading blank lines before image tag
_mock_image_only = MagicMock()
_mock_image_only.json.return_value = {
    "choices": [{
        "message": {
            "content": None,
            "images": [{"image_url": {"url": "data:image/png;base64,ONLY=="}}],
        }
    }]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_image_only):
    _image_only_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert(_image_only_result.startswith("![Generated image]"), "non-stream image-only: no leading blank lines")

# 34k. message.content = None handled without crash (or "")
_mock_content_null = MagicMock()
_mock_content_null.json.return_value = {
    "choices": [{"message": {"content": None}}]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_content_null):
    _null_result = _pipe34._non_stream_response({}, {}, _pipe34.valves)
_assert(isinstance(_null_result, str), "non-stream content=None: returns string (no crash)")

# ── Streaming audio response ────────────────────────────────────────────────

_pipe34s = Pipe()
_pipe34s.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 34l. Audio transcript in streaming delta → yielded as content
_sse_audio_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "", "audio": {"transcript": "Hello "}}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "", "audio": {"transcript": "world"}}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe34s, "_retryable_request", return_value=_make_sse_response(_sse_audio_chunks)):
    _stream_audio_chunks = list(_pipe34s._stream_response({}, {}, _pipe34s.valves))
_stream_audio_full = "".join(_stream_audio_chunks)
_assert("Hello " in _stream_audio_full, "stream audio: first transcript chunk yielded")
_assert("world" in _stream_audio_full, "stream audio: second transcript chunk yielded")

# 34m. Mixed stream: normal content chunks + audio transcript fallback
_sse_mixed_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Text first"}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "", "audio": {"transcript": " then audio"}}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe34s, "_retryable_request", return_value=_make_sse_response(_sse_mixed_chunks)):
    _mixed_chunks = list(_pipe34s._stream_response({}, {}, _pipe34s.valves))
_mixed_full = "".join(_mixed_chunks)
_assert("Text first" in _mixed_full, "stream mixed: text content chunk present")
_assert("then audio" in _mixed_full, "stream mixed: audio transcript chunk present")

# 34n. Stream delta with content=None → handled as empty (no crash)
_sse_null_content = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": None}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe34s, "_retryable_request", return_value=_make_sse_response(_sse_null_content)):
    _null_chunks = list(_pipe34s._stream_response({}, {}, _pipe34s.valves))
_assert(isinstance("".join(_null_chunks), str), "stream content=None delta: no crash")

# ══════════════════════════════════════════════════════════════════════════════
# §35  Post-release-audit hardening (SEC LOW + coverage gaps)
# ══════════════════════════════════════════════════════════════════════════════

_section("35. SEC: _resolve_referer CRLF guard")

_pipe35 = Pipe()
# Valid override respected
_pipe35.valves = Pipe.Valves(OPENROUTER_API_KEY="k", HTTP_REFERER_OVERRIDE="https://my.app")
_assert(_pipe35._resolve_referer(_pipe35.valves) == "https://my.app", "35a valid referer override respected")
# CRLF-injection override rejected → falls back
_pipe35.valves = Pipe.Valves(OPENROUTER_API_KEY="k", HTTP_REFERER_OVERRIDE="https://x\r\nX-Evil: 1")
_assert("\r" not in _pipe35._resolve_referer(_pipe35.valves) and "\n" not in _pipe35._resolve_referer(_pipe35.valves), "35b CRLF override rejected (no control chars in referer)")
_assert(_pipe35._resolve_referer(_pipe35.valves) == _pipe35._referer, "35c CRLF override falls back to default referer")
# Non-http scheme rejected
_pipe35.valves = Pipe.Valves(OPENROUTER_API_KEY="k", HTTP_REFERER_OVERRIDE="ftp://x")
_assert(_pipe35._resolve_referer(_pipe35.valves) == _pipe35._referer, "35d non-http override falls back")

_section("35. SEC: generation ID markdown-breakout sanitization")

_format_generation_id = mod._format_generation_id
# Backticks/newlines stripped so the code span can't be broken out of
_dirty = _format_generation_id("gen-`</think><script>")
_assert("`</think>" not in _dirty, "35e generation ID: backtick-breakout neutralized")
_assert("script" in _dirty, "35f generation ID: remaining text preserved")
_assert(_format_generation_id("gen-abc123") == "\n\n---\n*Generation ID: `gen-abc123`*", "35g clean ID formatted normally")
_assert(_format_generation_id("") == "", "35h empty ID → empty string")
_assert(_format_generation_id("`\r\n`") == "", "35i all-unsafe ID → empty (no stray footer)")

_section("35. Coverage: stream SHOW_GENERATION_ID")

_pipe35s = Pipe()
_pipe35s.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_GENERATION_ID=True)
_sse_genid = [
    b"data: " + json.dumps({"id": "gen-stream-xyz", "choices": [{"delta": {"content": "hi"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_genid)):
    _genid_stream = "".join(_pipe35s._stream_response({}, {}, _pipe35s.valves))
_assert("gen-stream-xyz" in _genid_stream, "35j streaming SHOW_GENERATION_ID: footer present")
_assert("Generation ID" in _genid_stream, "35k streaming gen-id label present")
# Off → no footer
_pipe35s.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_GENERATION_ID=False)
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_genid)):
    _nogenid = "".join(_pipe35s._stream_response({}, {}, _pipe35s.valves))
_assert("Generation ID" not in _nogenid, "35l streaming gen-id off: no footer")

_section("35. Coverage: FREE_MODEL_FILTER=only + legacy FREE_ONLY shim")

# FREE_MODEL_FILTER='only' keeps just free models
_pipe35f = Pipe()
_pipe35f.valves = Pipe.Valves(OPENROUTER_API_KEY="k", FREE_MODEL_FILTER="only")
_free_models = {
    "data": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "pricing": {"prompt": "0.01", "completion": "0.03"}},
        {"id": "meta/free-model:free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "x/zerocost", "name": "Zero", "pricing": {"prompt": "0", "completion": "0"}},
    ]
}
_mock_free = MagicMock(); _mock_free.status_code = 200; _mock_free.json.return_value = _free_models; _mock_free.raise_for_status = MagicMock()
with patch.object(_pipe35f._session, "get", return_value=_mock_free):
    _free_result = _pipe35f.pipes()
_free_ids = [m["id"] for m in _free_result]
_assert("openai/gpt-4o" not in _free_ids, "35m FREE_MODEL_FILTER=only: paid model excluded")
_assert("meta/free-model:free" in _free_ids and "x/zerocost" in _free_ids, "35n FREE_MODEL_FILTER=only: free models kept (:free + 0/0)")

# Legacy OPENROUTER_FREE_ONLY=true env maps to 'only' when FREE_MODEL_FILTER
# unset. The valve default is frozen at module-import time, so test it by
# loading a fresh copy of the module under the legacy env var.
import os as _os35
import importlib.util as _ilu35
import importlib.machinery as _ilm35
_prev_free_only = _os35.environ.get("OPENROUTER_FREE_ONLY")
_prev_filter = _os35.environ.get("OPENROUTER_FREE_MODEL_FILTER")
_os35.environ.pop("OPENROUTER_FREE_MODEL_FILTER", None)
_os35.environ["OPENROUTER_FREE_ONLY"] = "true"
try:
    _loader35 = _ilm35.SourceFileLoader("openrouter_pipe_shimtest", _PIPE_PATH)
    _spec35 = _ilu35.spec_from_loader("openrouter_pipe_shimtest", _loader35, origin=_PIPE_PATH)
    _mod35 = _ilu35.module_from_spec(_spec35)
    _spec35.loader.exec_module(_mod35)
    _shim_default = _mod35.Pipe.Valves(OPENROUTER_API_KEY="k").FREE_MODEL_FILTER
    _assert(_shim_default == "only", "35o legacy OPENROUTER_FREE_ONLY=true → FREE_MODEL_FILTER 'only'")
finally:
    if _prev_free_only is None:
        _os35.environ.pop("OPENROUTER_FREE_ONLY", None)
    else:
        _os35.environ["OPENROUTER_FREE_ONLY"] = _prev_free_only
    if _prev_filter is not None:
        _os35.environ["OPENROUTER_FREE_MODEL_FILTER"] = _prev_filter

_section("35. Coverage: REASONING_SUMMARY_MODE=concise")

_pipe35r = Pipe()
_pipe35r.valves = Pipe.Valves(OPENROUTER_API_KEY="k", REASONING_SUMMARY_MODE="concise")
_payload35r = _pipe35r._prepare_payload({"model": "openai/o1", "messages": [{"role": "user", "content": "hi"}]}, _pipe35r.valves)
_assert(_payload35r.get("reasoning", {}).get("summary") == "concise", "35p REASONING_SUMMARY_MODE=concise → reasoning.summary='concise'")

_section("35. USE_GSTATIC_FAVICONS valve default")

_assert(Pipe.Valves(OPENROUTER_API_KEY="k").USE_GSTATIC_FAVICONS is False, "35q USE_GSTATIC_FAVICONS defaults False")

# ── EncryptedStr ──────────────────────────────────────────────────────────────

_section("EncryptedStr key-at-rest")

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _ct = EncryptedStr.encrypt("sk-or-v1-abcdef")
    _assert(_ct.startswith("encrypted:"), "encrypt() tags ciphertext with prefix")
    _assert(_ct != "sk-or-v1-abcdef", "encrypt() does not return plaintext")
    _assert(
        EncryptedStr.decrypt(_ct) == "sk-or-v1-abcdef",
        "decrypt() round-trips back to original",
    )
    _assert(
        EncryptedStr.encrypt(_ct) == _ct,
        "encrypt() is idempotent on already-encrypted input",
    )
    _assert(
        EncryptedStr.decrypt("sk-or-v1-plain") == "sk-or-v1-plain",
        "decrypt() passes through non-prefixed legacy plaintext",
    )
    _assert(EncryptedStr.encrypt("") == "", "encrypt() of empty string is empty")
    _assert(
        EncryptedStr.decrypt("encrypted:not-a-valid-token") == "encrypted:not-a-valid-token",
        "decrypt() returns corrupt/foreign token unchanged (never raises)",
    )

with patch.dict(os.environ, {}, clear=True):
    _assert(
        EncryptedStr.encrypt("sk-or-v1-x") == "sk-or-v1-x",
        "no WEBUI_SECRET_KEY → encrypt() is a plaintext no-op",
    )
    _assert(
        EncryptedStr.decrypt("sk-or-v1-x") == "sk-or-v1-x",
        "no WEBUI_SECRET_KEY → decrypt() is a plaintext no-op",
    )

# ── Admin key encryption wiring ────────────────────────────────────────────────

_section("Admin key encrypted at rest, decrypted on use")

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _p = Pipe()
    _p.valves.OPENROUTER_API_KEY = mod.EncryptedStr.encrypt("sk-or-v1-secret")
    _assert(
        _p.valves.OPENROUTER_API_KEY.startswith("encrypted:"),
        "stored admin key is ciphertext",
    )
    _hdrs = _p._build_headers(valves=_p.valves)
    _assert(
        _hdrs["Authorization"] == "Bearer sk-or-v1-secret",
        "Authorization header carries the decrypted key",
    )

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _p2 = Pipe()
    _v = Pipe.Valves(OPENROUTER_API_KEY="sk-or-v1-fromctor")
    _assert(
        _v.OPENROUTER_API_KEY.startswith("encrypted:"),
        "Valves constructor encrypts the key via field_validator",
    )

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════

_section("SUMMARY")
total = _PASS + _FAIL
print(f"\n  Total: {total}  |  ✓ Passed: {_PASS}  |  ✗ Failed: {_FAIL}\n")

if _FAIL > 0:
    sys.exit(1)
else:
    print("  All tests passed! ✓\n")
    sys.exit(0)
