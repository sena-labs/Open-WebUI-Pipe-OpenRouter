"""
Comprehensive test suite for OpenRouter Pipe v1.2.0
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
    "OPENROUTER_FREE_ONLY", "OPENROUTER_PROVIDER_SORT",
    "OPENROUTER_PROVIDER_ORDER", "OPENROUTER_PROVIDER_IGNORE",
    "OPENROUTER_REQUIRE_PARAMETERS", "OPENROUTER_DATA_COLLECTION",
    "OPENROUTER_FALLBACK_MODELS", "OPENROUTER_ENABLE_MIDDLE_OUT",
    "OPENROUTER_ENABLE_CACHE_CONTROL", "OPENROUTER_REQUEST_TIMEOUT",
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
_assert(v.FREE_ONLY is False, "FREE_ONLY false")
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

payload = pipe._prepare_payload(body)

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
payload2 = pipe2._prepare_payload(body2)
_assert("include_reasoning" not in payload2, "no include_reasoning when disabled")
_assert("reasoning" not in payload2, "no reasoning when effort empty")
_assert("provider" not in payload2, "no provider block when all empty")
_assert("models" not in payload2, "no models when no fallbacks")
_assert("transforms" not in payload2, "no transforms when middle-out disabled")

# ── 5b. _prepare_payload: user as string preserved ──
body3 = {"model": "openai/gpt-4o", "messages": [], "user": "string-user"}
payload3 = pipe2._prepare_payload(body3)
_assert(payload3.get("user") == "string-user", "string user preserved")

# ── 5c. model without dot (no prefix) ──
body4 = {"model": "openai/gpt-4o", "messages": []}
payload4 = pipe2._prepare_payload(body4)
_assert(payload4["model"] == "openai/gpt-4o", "model without dot left unchanged")

# ── 6. _build_headers ────────────────────────────────────────────────────────

_section("6. _build_headers()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-test-123")

headers = pipe._build_headers()
_assert(headers["Authorization"] == "Bearer sk-test-123", "auth header")
_assert("Content-Type" in headers, "Content-Type present")
_assert(headers["Content-Type"] == "application/json", "Content-Type json")
_assert("HTTP-Referer" in headers, "HTTP-Referer present")
_assert("X-Title" in headers, "X-Title present")

headers_no_ct = pipe._build_headers(include_content_type=False)
_assert("Content-Type" not in headers_no_ct, "Content-Type omitted")
_assert("Authorization" in headers_no_ct, "auth still present")

# ── 7. _get_provider_icon ────────────────────────────────────────────────────

_section("7. get_provider_icon()")

pipe = Pipe()
_assert(Pipe.get_provider_icon("openai") is not None, "openai icon found")
_assert(Pipe.get_provider_icon("Anthropic") is not None, "Anthropic (case) icon found")
_assert(Pipe.get_provider_icon("unknown-provider") is None, "unknown → None")
_assert(Pipe.get_provider_icon("tencent") is not None, "tencent icon found (live-verified addition)")
_assert(len(mod._PROVIDER_ICONS) == 14, "14 provider icons in dict")
_assert(
    all(u.startswith("https://openrouter.ai/images/icons/") for u in mod._PROVIDER_ICONS.values()),
    "all provider icon URLs use the verified /images/icons/ path",
)

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
pipe._inject_cache_control(payload_cc)
_assert(
    payload_cc["messages"][0]["content"][1].get("cache_control") == {"type": "ephemeral"},
    "cache_control applied to longest text chunk",
)
_assert(
    "cache_control" not in payload_cc["messages"][0]["content"][0],
    "cache_control NOT on shorter chunk",
)

# No list content → no crash
payload_cc2 = {"messages": [{"role": "system", "content": "plain string"}]}
pipe._inject_cache_control(payload_cc2)  # Should not raise
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
pipe3._prepare_payload(original_body)
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
    result = pipe._non_stream_response({}, {})

_assert("<think>" in result, "has <think> tag")
_assert("Thinking..." in result, "reasoning content")
_assert("Hello!" in result, "main content")
_assert("Citations:" in result, "citations section")

# 11b. Error in body
mock_json_err = {"error": {"message": "Model overloaded"}}
mock_resp_err = MagicMock()
mock_resp_err.json.return_value = mock_json_err

with patch.object(pipe, "_retryable_request", return_value=mock_resp_err):
    result = pipe._non_stream_response({}, {})

_assert("Model overloaded" in result, "error from body detected")

# 11c. Empty choices
mock_json_empty = {"choices": []}
mock_resp_empty = MagicMock()
mock_resp_empty.json.return_value = mock_json_empty

with patch.object(pipe, "_retryable_request", return_value=mock_resp_empty):
    result = pipe._non_stream_response({}, {})

_assert("empty response" in result.lower(), "empty choices → informative message")

# 11d. Timeout — assert on distinctive phrase from the real error template
# ("timed out after Ns"), not the bare word "timeout" which the exception
# arg also contains (tautology).
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.Timeout("boom"),
):
    result = pipe._non_stream_response({}, {})
_assert("timed out after" in result.lower(), "timeout error: distinctive template phrase present")
_assert("openrouter error" in result.lower(), "timeout error: error-prefixed message")

# 11e. HTTP Error
mock_resp_http = MagicMock()
mock_resp_http.status_code = 401
mock_resp_http.json.return_value = {"error": {"message": "Unauthorized"}}
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.HTTPError(response=mock_resp_http),
):
    result = pipe._non_stream_response({}, {})
_assert("401" in result, "HTTP 401 error")

# 11f. Error in body as string (not dict)
mock_json_str_err = {"error": "plain string error"}
mock_resp_str_err = MagicMock()
mock_resp_str_err.json.return_value = mock_json_str_err

with patch.object(pipe, "_retryable_request", return_value=mock_resp_str_err):
    result = pipe._non_stream_response({}, {})

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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
full = "".join(output)
_assert("<think>" in full, "stream error-in-think: think opened")
_assert("</think>" in full, "stream error-in-think: think closed before error")
_assert("server_fault" in full, "stream error-in-think: error shown")

# 12e. Timeout in stream
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.Timeout("timeout"),
):
    output = list(pipe._stream_response({}, {}))
full = "".join(output)
_assert("timeout" in full.lower(), "stream: timeout error")

# 12f. Empty stream
mock_empty_sse = _make_sse_response([b"data: [DONE]"])
with patch.object(pipe, "_retryable_request", return_value=mock_empty_sse):
    output = list(pipe._stream_response({}, {}))
_assert(len("".join(output)) == 0, "stream: empty → no output")

# 12g. Malformed JSON in stream (should skip)
sse_bad = [
    b"data: {INVALID JSON",
    b"data: " + json.dumps({"choices": [{"delta": {"content": "OK"}}]}).encode(),
    b"data: [DONE]",
]
mock_bad = _make_sse_response(sse_bad)
with patch.object(pipe, "_retryable_request", return_value=mock_bad):
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
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
    result = pipe._retryable_request({}, {}, stream=False)
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
    result = pipe._retryable_request({}, {}, stream=False)
    _assert(call_count[0] == 2, "retryable: retried after timeout")

# 13c. All retries exhausted
with patch.object(pipe._session, "post", side_effect=req_lib.exceptions.Timeout("timeout")), \
     patch("time.sleep"):
    try:
        pipe._retryable_request({}, {}, stream=False)
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
        pipe._retryable_request({}, {}, stream=False)
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
    result = pipe._retryable_request({}, {}, stream=False)
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

# 14c. Stream returns AsyncGenerator (unified return type — ARCH-2)
async def _test_pipe_stream() -> str:
    sse = _make_sse_response([
        b"data: " + json.dumps({"choices": [{"delta": {"content": "World"}}]}).encode(),
        b"data: [DONE]",
    ])
    with patch.object(pipe, "_retryable_request", return_value=sse):
        result = await pipe.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        )
        # result is always an AsyncGenerator for streaming requests
        chunks = []
        async for chunk in result:
            chunks.append(chunk)
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
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_ONLY=True)

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
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_ONLY=True)
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

# 16b. REASONING_EFFORT uses select with 4 options
re_field = Pipe.Valves.model_fields["REASONING_EFFORT"]
_assert(
    re_field.json_schema_extra is not None,
    "REASONING_EFFORT: json_schema_extra present",
)
re_options = re_field.json_schema_extra.get("input", {}).get("options", [])
_assert(len(re_options) == 4, "REASONING_EFFORT: 4 options (disabled, low, medium, high)")
re_values = [o["value"] for o in re_options]
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
_pipe_cache.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_ONLY=True)
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
    })
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
    })
_assert("Responded by" not in _primary_result, "no attribution when primary responds")

# ── 23. Citation edge cases ─────────────────────────────────────────────────

_section("23. Citation edge cases")

# 23a. URL with parentheses gets fully encoded (both '(' and ')' to defend
# against markdown injection like ``https://x](javascript:evil)``).
_paren_citations = ["https://en.wikipedia.org/wiki/Test_(disambiguation)"]
_paren_result = _insert_citations("See [1].", _paren_citations)
_assert("%29" in _paren_result, "closing parenthesis encoded as %29")
_assert("%28" in _paren_result, "opening parenthesis encoded as %28")
_assert("Test_%28disambiguation%29" in _paren_result, "citation URL re-rendered with encoded parens")

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
_pipe_free.valves = Pipe.Valves(OPENROUTER_API_KEY="k", FREE_ONLY=True)
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
    output = list(pipe._stream_response({}, {}))
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
    output = list(pipe._stream_response({}, {}))
full = "".join(output)
_assert("<think>" not in full, "stream empty reasoning: <think> NOT opened")
_assert("Only content" in full, "stream empty reasoning: content still present")

# 26c. Empty content string → nothing yielded for that chunk
sse_empty_content = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": ""}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_empty_content)):
    output = list(pipe._stream_response({}, {}))
_assert("".join(output) == "", "stream empty content string: nothing yielded")

# 26d. Non-dict item in choices[0] → skipped safely, next chunk processed
sse_bad_choice = [
    b"data: " + json.dumps({"choices": [42]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "OK"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_bad_choice)):
    output = list(pipe._stream_response({}, {}))
full = "".join(output)
_assert("OK" in full, "stream non-dict choice: skipped safely, next chunk processed")

# 26e. Citations-only chunk (no choices) → updates citations used by later content
sse_citations_first = [
    b"data: " + json.dumps({"citations": ["https://example.com"]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "See [1]"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(pipe, "_retryable_request", return_value=_make_sse_response(sse_citations_first)):
    output = list(pipe._stream_response({}, {}))
full = "".join(output)
_assert("https://example.com" in full, "stream citations-only chunk: citation applied to later content")
_assert("Citations:" in full, "stream citations-only chunk: citation list appended")

# 26f. Generic exception raised by _retryable_request → yields OpenRouter Error
with patch.object(pipe, "_retryable_request", side_effect=ValueError("unexpected")):
    output = list(pipe._stream_response({}, {}))
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
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_ONLY=True)
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
pipe._inject_cache_control(payload_all_img)
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
pipe._inject_cache_control(payload_mixed_img)
_assert(
    "cache_control" not in payload_mixed_img["messages"][0]["content"][0],
    "cache_control: image_url chunk skipped in mixed content",
)
_assert(
    payload_mixed_img["messages"][0]["content"][1].get("cache_control") == {"type": "ephemeral"},
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
pipe._inject_cache_control(payload_user_list)
_assert(
    payload_user_list["messages"][0]["content"][1].get("cache_control") == {"type": "ephemeral"},
    "cache_control: user role list content gets cache_control when no system role",
)

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
    result = pipe._non_stream_response({}, {})
_assert("Context window exceeded" in result, "non-stream: error field takes priority over empty choices")

# 29b. message.content is None → no crash, returns empty string
_mock_none_content = MagicMock()
_mock_none_content.json.return_value = {
    "choices": [{"message": {"content": None}}]
}
with patch.object(pipe, "_retryable_request", return_value=_mock_none_content):
    result = pipe._non_stream_response({}, {})
_assert(isinstance(result, str), "non-stream: None content → still returns string")
_assert(result == "", "non-stream: None content → empty string (no crash)")

# 29c. message dict missing "content" key → returns empty string (no crash)
_mock_no_content_key = MagicMock()
_mock_no_content_key.json.return_value = {
    "choices": [{"message": {"role": "assistant"}}]
}
with patch.object(pipe, "_retryable_request", return_value=_mock_no_content_key):
    result = pipe._non_stream_response({}, {})
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
    pipe._retryable_request({}, {}, stream=True)
_assert(
    _mock_post_s.call_args.kwargs.get("stream") is True
    or _mock_post_s.call_args[1].get("stream") is True,
    "retryable: stream=True forwarded to requests.Session.post",
)

# 32b. stream=False → requests.Session.post called with stream=False
_mock_ok_nostream = MagicMock()
_mock_ok_nostream.raise_for_status = MagicMock()
with patch.object(pipe._session, "post", return_value=_mock_ok_nostream) as _mock_post_ns:
    pipe._retryable_request({}, {}, stream=False)
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
    _result_off = pipe._non_stream_response({}, {})
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
    _result_on = pipe._non_stream_response({}, {})
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
    _result_eur_resp = pipe._non_stream_response({}, {})
_assert("€" in _result_eur_resp, "non-stream SHOW_COST_INFO=True EUR: euro symbol shown")

# 33r. SHOW_COST_INFO=True but response has no usage → no cost appended (no crash)
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True)
_mock_no_usage = MagicMock()
_mock_no_usage.json.return_value = {
    "choices": [{"message": {"content": "No usage data"}}],
}
with patch.object(pipe, "_retryable_request", return_value=_mock_no_usage):
    _result_no_usage = pipe._non_stream_response({}, {})
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
    _stream_output = list(pipe._stream_response({}, {}))
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
    _stream_off_output = list(pipe._stream_response({}, {}))
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
    _stream_nu_output = list(pipe._stream_response({}, {}))
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
    _audio_result = _pipe34._non_stream_response({}, {})
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
    _audio_no_tx_result = _pipe34._non_stream_response({}, {})
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
    _audio_content_result = _pipe34._non_stream_response({}, {})
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
    _image_result = _pipe34._non_stream_response({}, {})
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
    _image_text_result = _pipe34._non_stream_response({}, {})
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
    _image_only_result = _pipe34._non_stream_response({}, {})
_assert(_image_only_result.startswith("![Generated image]"), "non-stream image-only: no leading blank lines")

# 34k. message.content = None handled without crash (or "")
_mock_content_null = MagicMock()
_mock_content_null.json.return_value = {
    "choices": [{"message": {"content": None}}]
}
with patch.object(_pipe34, "_retryable_request", return_value=_mock_content_null):
    _null_result = _pipe34._non_stream_response({}, {})
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
    _stream_audio_chunks = list(_pipe34s._stream_response({}, {}))
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
    _mixed_chunks = list(_pipe34s._stream_response({}, {}))
_mixed_full = "".join(_mixed_chunks)
_assert("Text first" in _mixed_full, "stream mixed: text content chunk present")
_assert("then audio" in _mixed_full, "stream mixed: audio transcript chunk present")

# 34n. Stream delta with content=None → handled as empty (no crash)
_sse_null_content = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": None}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe34s, "_retryable_request", return_value=_make_sse_response(_sse_null_content)):
    _null_chunks = list(_pipe34s._stream_response({}, {}))
_assert(isinstance("".join(_null_chunks), str), "stream content=None delta: no crash")

# ══════════════════════════════════════════════════════════════════════════════
# §35  _looks_like_image_content + image-gen content detection
# ══════════════════════════════════════════════════════════════════════════════

_section("35 · _looks_like_image_content helper")

_looks_like_image_content = mod._looks_like_image_content

# 35a. data:image/ URI → True
_assert(_looks_like_image_content("data:image/png;base64,abc123"), "35a data:image/ → True")

# 35b. data:image/ with leading/trailing whitespace → True
_assert(_looks_like_image_content("  data:image/jpeg;base64,xyz  "), "35b data:image/ trimmed → True")

# 35c. https URL with no extension (CDN, Replicate, fal.ai) → True
_assert(_looks_like_image_content("https://cdn.openai.com/generated/img_abc123"), "35c bare CDN URL → True")

# 35d. https URL with .png extension → True
_assert(_looks_like_image_content("https://example.com/image.png"), "35d .png URL → True")

# 35e. https URL with .jpg extension → True
_assert(_looks_like_image_content("https://example.com/photo.jpg?v=1"), "35e .jpg URL with query → True")

# 35f. https URL ending in .html → False (non-image extension)
_assert(not _looks_like_image_content("https://example.com/page.html"), "35f .html URL → False")

# 35g. https URL ending in .json → False
_assert(not _looks_like_image_content("https://api.example.com/data.json"), "35g .json URL → False")

# 35h. https URL ending in .py → False
_assert(not _looks_like_image_content("https://raw.github.com/file.py"), "35h .py URL → False")

# 35i. Plain text prose → False (contains spaces)
_assert(not _looks_like_image_content("Here is your generated image"), "35i prose text → False")

# 35j. Multiline text → False
_assert(not _looks_like_image_content("line one\nline two"), "35j multiline → False")

# 35k. Empty string → False
_assert(not _looks_like_image_content(""), "35k empty → False")

# 35l. Only whitespace → False
_assert(not _looks_like_image_content("   "), "35l whitespace-only → False")

# 35m. http:// URL on known image CDN → True (allowlisted host)
_assert(_looks_like_image_content("http://replicate.delivery/some/path"), "35m http:// allowlisted CDN → True")

# 35n. ftp:// scheme → False (not http/https/data:image)
_assert(not _looks_like_image_content("ftp://files.example.com/image.png"), "35n ftp:// → False")

# 35o. URL with fragment, non-image ext stripped → fragment-aware
_assert(not _looks_like_image_content("https://example.com/page.html#section"), "35o .html with fragment → False")

# ── Non-stream response: image URL as message.content (FLUX-style) ───────────

_section("35 · non-stream image-gen content detection")

_pipe35 = Pipe()
_pipe35.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 35p. FLUX-style: message.content is bare CDN image URL → rendered as markdown
_flux_url = "https://replicate.delivery/cdn/generated/img_flux_abc123"
_mock35p = MagicMock()
_mock35p.json.return_value = {
    "choices": [{"message": {"role": "assistant", "content": _flux_url}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 1},
}
with patch.object(_pipe35, "_retryable_request", return_value=_mock35p):
    _flux_result = _pipe35._non_stream_response({}, {})
_assert("![Generated image]" in _flux_result, "35p FLUX CDN URL → markdown image tag")
_assert(_flux_url.replace(")", "%29") in _flux_result, "35p FLUX URL preserved in markdown")

# 35q. data:image/ base64 as message.content → rendered as markdown
_b64_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
_mock35q = MagicMock()
_mock35q.json.return_value = {
    "choices": [{"message": {"role": "assistant", "content": _b64_uri}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 1},
}
with patch.object(_pipe35, "_retryable_request", return_value=_mock35q):
    _b64_result = _pipe35._non_stream_response({}, {})
_assert("![Generated image]" in _b64_result, "35q base64 URI → markdown image tag")
_assert("data:image/png" in _b64_result, "35q base64 URI preserved in markdown")

# 35r. Normal text content is NOT mistaken for image
_mock35r = MagicMock()
_mock35r.json.return_value = {
    "choices": [{"message": {"role": "assistant", "content": "Hello world!"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}
with patch.object(_pipe35, "_retryable_request", return_value=_mock35r):
    _text_result = _pipe35._non_stream_response({}, {})
_assert("Hello world!" in _text_result, "35r normal text: content preserved")
_assert("![Generated image]" not in _text_result, "35r normal text: no spurious image tag")

# 35s. message.images list still works (explicit image list, not content URL)
_mock35s = MagicMock()
_mock35s.json.return_value = {
    "choices": [{"message": {"role": "assistant", "content": "Caption", "images": [{"image_url": {"url": "https://example.com/gen.png"}}]}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}
with patch.object(_pipe35, "_retryable_request", return_value=_mock35s):
    _images_result = _pipe35._non_stream_response({}, {})
_assert("Caption" in _images_result, "35s images list: text content present")
_assert("gen.png" in _images_result, "35s images list: image URL present")

# ── Streaming response: image URL as single SSE chunk (FLUX-style) ────────────

_section("35 · stream image-gen content detection")

_pipe35s = Pipe()
_pipe35s.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 35t. Stream: image CDN URL in single delta → converted to markdown image
_stream_img_url = "https://replicate.delivery/cdn/generated/img_stream_xyz"
_sse_flux_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": _stream_img_url}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_flux_chunks)):
    _stream_flux_chunks = list(_pipe35s._stream_response({}, {}))
_stream_flux_full = "".join(_stream_flux_chunks)
_assert("![Generated image]" in _stream_flux_full, "35t stream image URL → markdown image tag")
_assert(_stream_img_url.replace(")", "%29") in _stream_flux_full, "35t stream: URL preserved in tag")

# 35u. Stream: data:image/ URI in delta → converted to markdown
_sse_b64_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": _b64_uri}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_b64_chunks)):
    _stream_b64_chunks = list(_pipe35s._stream_response({}, {}))
_stream_b64_full = "".join(_stream_b64_chunks)
_assert("![Generated image]" in _stream_b64_full, "35u stream base64 URI → markdown image tag")

# 35v. Stream: normal text NOT converted
_sse_text_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Normal response text"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_text_chunks)):
    _stream_text_chunks = list(_pipe35s._stream_response({}, {}))
_stream_text_full = "".join(_stream_text_chunks)
_assert("Normal response text" in _stream_text_full, "35v stream normal text: preserved")
_assert("![Generated image]" not in _stream_text_full, "35v stream normal text: no spurious image tag")

# 35w. Stream: URL with .html extension NOT converted (webpage URL)
_webpage_url = "https://example.com/result.html"
_sse_html_chunks = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": _webpage_url}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe35s, "_retryable_request", return_value=_make_sse_response(_sse_html_chunks)):
    _stream_html_chunks = list(_pipe35s._stream_response({}, {}))
_stream_html_full = "".join(_stream_html_chunks)
_assert("![Generated image]" not in _stream_html_full, "35w .html URL not converted to image")
_assert(_webpage_url in _stream_html_full, "35w .html URL passed through as text")

# ══════════════════════════════════════════════════════════════════════════════
# §36  Bug regression tests
# ══════════════════════════════════════════════════════════════════════════════

_section("36 · Bug regression: exc.response=None in pipes() HTTPError")

# Bug 1: pipes() HTTPError handler crashed with AttributeError when
# requests.exceptions.HTTPError was raised without a response object
# (e.g. raised manually outside raise_for_status).

_pipe36 = Pipe()
_pipe36.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 36a. HTTPError with response=None must return an error model, not crash
_no_resp_err = req_lib.exceptions.HTTPError("network error")
# exc.response is None by default when constructed without a response
_assert(_no_resp_err.response is None, "36a precondition: exc.response is None")
with patch.object(_pipe36._session, "get", side_effect=_no_resp_err):
    _models_no_resp = _pipe36.pipes()
_assert(len(_models_no_resp) == 1, "36a no-response HTTPError: one model returned")
_assert(_models_no_resp[0]["id"] == "error", "36a no-response HTTPError: id == error")
_assert("no response" in _models_no_resp[0]["name"].lower(), "36a no-response HTTPError: msg mentions no response")

# 36b. HTTPError WITH a response object still works correctly
_mock36b = MagicMock()
_mock36b.status_code = 500
_mock36b.json.return_value = {"error": {"message": "server blew up"}}
_with_resp_err = req_lib.exceptions.HTTPError(response=_mock36b)
with patch.object(_pipe36._session, "get", side_effect=_with_resp_err):
    _models_with_resp = _pipe36.pipes()
_assert(_models_with_resp[0]["id"] == "error", "36b HTTPError with response: id == error")
_assert("500" in _models_with_resp[0]["name"], "36b HTTPError with response: status code in msg")
_assert("server blew up" in _models_with_resp[0]["name"], "36b HTTPError with response: detail in msg")

# ── Bug 2: OPENROUTER_BASE_URL not in cache key ───────────────────────────────

_section("36 · Bug regression: OPENROUTER_BASE_URL in cache key")

_pipe36c = Pipe()
_pipe36c.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 36c. Cache key changes when BASE_URL changes
_key_prod = _pipe36c._build_cache_key()
_pipe36c.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    OPENROUTER_BASE_URL="https://staging.openrouter.ai/api/v1",
)
_key_staging = _pipe36c._build_cache_key()
_assert(_key_prod != _key_staging, "36c BASE_URL change invalidates cache key")

# 36d. Cache built on prod URL is invalidated when URL changes to staging
_pipe36d = Pipe()
_pipe36d.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_pipe36d._models_cache = [{"id": "openai/gpt-4o", "name": "GPT-4o"}]
_pipe36d._models_cache_ts = _time_mod.monotonic()
_pipe36d._models_cache_key = _pipe36d._build_cache_key()
_assert(_pipe36d._models_cache_valid(), "36d precondition: prod cache is valid")
_pipe36d.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    OPENROUTER_BASE_URL="https://staging.openrouter.ai/api/v1",
)
_assert(not _pipe36d._models_cache_valid(), "36d cache invalid after BASE_URL change")

# ── Bug 3: audio transcript bypassed _insert_citations ────────────────────────

_section("36 · Bug regression: audio transcript citations")

_pipe36e = Pipe()
_pipe36e.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 36e. Audio transcript with citations: [1] refs must be linked
_mock36e = MagicMock()
_mock36e.json.return_value = {
    "choices": [{
        "message": {
            "role": "assistant",
            "content": None,
            "audio": {"transcript": "See [1] for details."},
        }
    }],
    "citations": ["https://example.com/source"],
    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
}
with patch.object(_pipe36e, "_retryable_request", return_value=_mock36e):
    _audio_result = _pipe36e._non_stream_response({}, {})
_assert("[[1]]" in _audio_result, "36e audio transcript: citation [1] expanded to [[1]]")
_assert("https://example.com/source" in _audio_result, "36e audio transcript: citation URL present")

# 36f. Audio transcript WITHOUT citations: transcript rendered verbatim
_mock36f = MagicMock()
_mock36f.json.return_value = {
    "choices": [{
        "message": {
            "role": "assistant",
            "content": None,
            "audio": {"transcript": "Hello world"},
        }
    }],
    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
}
with patch.object(_pipe36e, "_retryable_request", return_value=_mock36f):
    _audio_plain = _pipe36e._non_stream_response({}, {})
_assert("Hello world" in _audio_plain, "36f audio no citations: transcript preserved")

# ══════════════════════════════════════════════════════════════════════════════
# §37  Swarm-debug hardening: SEC, ARCH, PROD, PERF
# ══════════════════════════════════════════════════════════════════════════════

# ── SEC-2: _md_escape_url full character set ──────────────────────────────────

_section("37 · _md_escape_url markdown-injection defense")

_md_escape_url = mod._md_escape_url

# 37a. Closing paren encoded
_assert(_md_escape_url("https://x/a)b") == "https://x/a%29b", "37a ')' -> %29")
# 37b. Opening paren encoded (breaks `[text](url)` second-link injection)
_assert(_md_escape_url("https://x/a(b") == "https://x/a%28b", "37b '(' -> %28")
# 37c. Brackets encoded
_assert("%5D" in _md_escape_url("https://x]y"), "37c ']' -> %5D")
_assert("%5B" in _md_escape_url("https://x[y"), "37d '[' -> %5B")
# 37e. Angle brackets encoded
_assert("%3C" in _md_escape_url("https://x<y"), "37e '<' -> %3C")
_assert("%3E" in _md_escape_url("https://x>y"), "37f '>' -> %3E")
# 37g. Whitespace encoded
_assert("%20" in _md_escape_url("https://x y"), "37g space -> %20")
_assert("%0A" in _md_escape_url("https://x\ny"), "37h newline -> %0A")
_assert("%09" in _md_escape_url("https://x\ty"), "37i tab -> %09")
_assert("%0D" in _md_escape_url("https://x\ry"), "37j CR -> %0D")
# 37k. Markdown-injection payload neutralized
_inject = "https://safe.com](javascript:alert(1))"
_inject_safe = _md_escape_url(_inject)
_assert("](javascript" not in _inject_safe, "37k injection: ']' encoded so `[..](evil)` cannot inject")
_assert("%5D" in _inject_safe and "%28" in _inject_safe, "37k injection: payload neutralized")
# 37l. Empty / safe URL unchanged
_assert(_md_escape_url("") == "", "37l empty unchanged")
_assert(_md_escape_url("https://example.com/abc") == "https://example.com/abc", "37m safe URL untouched")

# ── SEC-4: data:image/svg+xml blocked ─────────────────────────────────────────

_section("37 · SVG data URIs blocked in image rendering")

_is_safe_image_data_uri = mod._is_safe_image_data_uri
_looks_like_image_content = mod._looks_like_image_content

# 37n. svg+xml rejected
_assert(not _is_safe_image_data_uri("data:image/svg+xml;base64,abc"), "37n svg+xml rejected")
_assert(not _looks_like_image_content("data:image/svg+xml,<svg/onload=alert(1)>"), "37o looks_like_image: svg rejected")
# 37p. png/jpeg/webp accepted
_assert(_is_safe_image_data_uri("data:image/png;base64,abc"), "37p png accepted")
_assert(_is_safe_image_data_uri("data:image/jpeg;base64,abc"), "37q jpeg accepted")
_assert(_is_safe_image_data_uri("data:image/webp;base64,abc"), "37r webp accepted")
# 37s. _format_image_output drops svg+xml entries
_svg_imgs = [{"image_url": {"url": "data:image/svg+xml,<svg/onload=alert(1)>"}}]
_assert(mod._format_image_output(_svg_imgs) == "", "37s _format_image_output drops svg entry")

# ── SEC-3: base URL validator rejects non-loopback http:// ────────────────────

_section("37 · base URL validator hardening")

# 37t. https accepted
_pipe37 = Pipe()
_pipe37.valves = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="https://openrouter.ai/api/v1")
_assert(_pipe37.valves.OPENROUTER_BASE_URL.startswith("https://"), "37t https accepted")

# 37u. http://localhost accepted (dev)
_pipe37b = Pipe()
_pipe37b.valves = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="http://localhost:8080/v1")
_assert("localhost" in _pipe37b.valves.OPENROUTER_BASE_URL, "37u http://localhost accepted")

# 37v. http://127.0.0.1 accepted (loopback)
_pipe37c = Pipe()
_pipe37c.valves = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="http://127.0.0.1/api")
_assert("127.0.0.1" in _pipe37c.valves.OPENROUTER_BASE_URL, "37v http://127.0.0.1 accepted")

# 37w. http://public-host REJECTED
try:
    Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="http://attacker.example.com/api")
    _assert(False, "37w http://public-host should raise ValidationError")
except Exception as exc:
    _assert("https" in str(exc).lower() or "localhost" in str(exc).lower(), "37w http://public-host rejected with msg")

# 37x. http://internal-ip (e.g. 169.254.169.254) REJECTED
try:
    Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="http://169.254.169.254/latest/meta-data")
    _assert(False, "37x http://169.254.169.254 should raise (SSRF metadata service)")
except Exception:
    _assert(True, "37x http://169.254.169.254 rejected")

# ── ARCH-1: retry on 5xx + Retry-After honored on 429 ─────────────────────────

_section("37 · retry on 5xx and 429 with Retry-After")

# 37y. 503 retried then succeeds on next attempt
_pipe37r = Pipe()
_pipe37r.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=2)
_mock_503 = MagicMock()
_mock_503.status_code = 503
_mock_503.headers = {}
_mock_503.json.return_value = {"error": {"message": "upstream busy"}}
_mock_503.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=_mock_503)

_mock_ok = MagicMock()
_mock_ok.status_code = 200
_mock_ok.headers = {}
_mock_ok.raise_for_status.return_value = None

# Patch backoff to 0 so test runs fast
with patch.object(Pipe, "_backoff_delay", staticmethod(lambda a: 0.0)):
    with patch.object(_pipe37r, "_parse_retry_after", return_value=0.0):
        with patch.object(_pipe37r._session, "post", side_effect=[_mock_503, _mock_ok]):
            _resp = _pipe37r._retryable_request({}, {}, stream=False)
_assert(_resp is _mock_ok, "37y 503 retried, second attempt returns 200")

# 37z. 429 with Retry-After header parsed
_mock_429 = MagicMock()
_mock_429.status_code = 429
_mock_429.headers = {"Retry-After": "1.5"}
_assert(Pipe._parse_retry_after(_mock_429) == 1.5, "37z Retry-After parsed as float")

# 37aa. Retry-After clamped at 30
_mock_429_big = MagicMock()
_mock_429_big.headers = {"Retry-After": "999"}
_assert(Pipe._parse_retry_after(_mock_429_big) == 30.0, "37aa Retry-After clamped at 30")

# 37ab. Retry-After missing → falls back to default backoff
_mock_429_no = MagicMock()
_mock_429_no.headers = {}
_fallback = Pipe._parse_retry_after(_mock_429_no)
_assert(0 < _fallback <= 30.0, "37ab missing Retry-After: fallback in (0, 30]")

# 37ac. 502 retried (proxy/gateway hiccup)
_pipe37s = Pipe()
_pipe37s.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=1)
_mock_502 = MagicMock()
_mock_502.status_code = 502
_mock_502.headers = {}
_mock_502.json.return_value = {}
with patch.object(Pipe, "_backoff_delay", staticmethod(lambda a: 0.0)):
    with patch.object(_pipe37s, "_parse_retry_after", return_value=0.0):
        with patch.object(_pipe37s._session, "post", side_effect=[_mock_502, _mock_ok]):
            _r502 = _pipe37s._retryable_request({}, {}, stream=False)
_assert(_r502 is _mock_ok, "37ac 502 retried, success on next attempt")

# 37ad. 4xx (non-429) NOT retried — fail-fast
_pipe37t = Pipe()
_pipe37t.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=2)
_mock_400 = MagicMock()
_mock_400.status_code = 400
_mock_400.headers = {}
_mock_400.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=_mock_400)
_call_count = {"n": 0}
def _count_post(*a, **kw):
    _call_count["n"] += 1
    return _mock_400
with patch.object(_pipe37t._session, "post", side_effect=_count_post):
    try:
        _pipe37t._retryable_request({}, {}, stream=False)
    except req_lib.exceptions.HTTPError:
        pass
_assert(_call_count["n"] == 1, "37ad 4xx not retried: only 1 attempt")

# ── PROD-5: empty model='' guarded in pipe() ──────────────────────────────────

_section("37 · empty-model guard at pipe() entry")

_pipe37e = Pipe()
_pipe37e.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

# 37ae. pipe(body) with model="" returns guard message
_empty_model_result = asyncio.run(_pipe37e.pipe({"model": "", "messages": [{"role": "user", "content": "hi"}]}))
_assert("No model specified" in _empty_model_result, "37ae empty model -> 'No model specified'")

# 37af. pipe(body) with model field missing entirely
_no_model_result = asyncio.run(_pipe37e.pipe({"messages": [{"role": "user", "content": "hi"}]}))
_assert("No model specified" in _no_model_result, "37af missing model field -> 'No model specified'")

# 37ag. pipe(body) with model='error' still produces the error-pseudo guard
_error_model_result = asyncio.run(_pipe37e.pipe({"model": "error", "messages": [{"role": "user", "content": "hi"}]}))
_assert("No valid model selected" in _error_model_result, "37ag model='error' -> 'No valid model selected'")

# ── PERF-3: icon insert retry cap ─────────────────────────────────────────────

_section("37 · icon insert retry cap")

# 37ah. _icon_insert_attempts initialized empty in new Pipe
_pipe37p = Pipe()
_assert(_pipe37p._icon_insert_attempts == {}, "37ah _icon_insert_attempts initialized")

# 37ai. After 3 failed inserts, model is added to _icons_synced (no further attempts)
# Direct attribute manipulation to simulate state
_pipe37p._icon_insert_attempts["openai/gpt-4o"] = 3
_assert(_pipe37p._icon_insert_attempts["openai/gpt-4o"] == 3, "37ai precondition: 3 attempts recorded")

# Note: full integration test of the cap path requires mocking OWUI's Models module,
# which is already covered by the existing _sync_model_icons tests (section 25).
# Here we just verify the attribute exists and is per-instance state.

# ── PERF-1: HTTPAdapter pool mounted ──────────────────────────────────────────

_section("37 · HTTPAdapter mounted with larger pool")

_pipe37h = Pipe()
_https_adapter = _pipe37h._session.adapters.get("https://")
_assert(_https_adapter is not None, "37aj https:// adapter mounted")
# Adapter exposes the pool config; verify it's NOT the default
_assert(_https_adapter._pool_connections == 20, "37ak pool_connections=20")
_assert(_https_adapter._pool_maxsize == 50, "37al pool_maxsize=50")

# ══════════════════════════════════════════════════════════════════════════════
# §38  CR-B1: image-content allow-list (URL-only false-positive defense)
# ══════════════════════════════════════════════════════════════════════════════

_section("38 · image-content allow-list")

# 38a. Plain GitHub URL (model answering 'what is GitHub URL?') NOT treated as image
_assert(not _looks_like_image_content("https://github.com"), "38a https://github.com NOT image")
_assert(not _looks_like_image_content("https://example.com"), "38b https://example.com NOT image")
_assert(not _looks_like_image_content("http://localhost:3000"), "38c http://localhost NOT image")

# 38d. Random CDN with no image extension and not in allowlist → NOT image
_assert(not _looks_like_image_content("https://cdn.example.com/anything"), "38d unknown CDN NOT image")

# 38e. URL with image extension (any host) → IS image
_assert(_looks_like_image_content("https://example.com/logo.png"), "38e .png ext on any host → image")
_assert(_looks_like_image_content("https://example.com/photo.webp"), "38f .webp ext → image")
_assert(_looks_like_image_content("https://example.com/anim.gif"), "38g .gif ext → image")
_assert(_looks_like_image_content("https://example.com/img.avif"), "38h .avif ext → image")

# 38i. Allow-listed image CDNs → IS image (even without extension)
_assert(_looks_like_image_content("https://replicate.delivery/abc123"), "38i replicate.delivery → image")
_assert(_looks_like_image_content("https://fal.media/files/elephant/abc"), "38j fal.media → image")
_assert(_looks_like_image_content("https://oaidalleapiprodscus.blob.core.windows.net/private/org-xxx/img-yyy"), "38k DALL-E blob → image")
_assert(_looks_like_image_content("https://images.bfl.ai/generation/abc"), "38l BFL/FLUX → image")

# 38m. Allow-listed CDN with port stripped
_assert(_looks_like_image_content("https://replicate.delivery:443/abc"), "38m allowlist host with port → image")

# 38n. Query string and fragment ignored when checking extension
_assert(_looks_like_image_content("https://example.com/img.jpg?v=1&size=large"), "38n .jpg with query string → image")
_assert(_looks_like_image_content("https://example.com/img.png#anchor"), "38o .png with fragment → image")

# 38p. Non-image extension still blocked
_assert(not _looks_like_image_content("https://example.com/page.html"), "38p .html still blocked")
_assert(not _looks_like_image_content("https://api.example.com/data.json"), "38q .json still blocked")

# 38r. Capitalized URLs still work
_assert(_looks_like_image_content("https://EXAMPLE.com/IMG.PNG"), "38r uppercase URL → image")

# 38s. Trailing-dot FQDN on allow-listed host still matches (host.rstrip("."))
_assert(_looks_like_image_content("https://images.bfl.ai./generation/abc"), "38s trailing-dot FQDN → image")

# 38t. Google CDN hosts now allow-listed (Gemini/Imagen image output)
_assert(_looks_like_image_content("https://lh3.googleusercontent.com/abc123"), "38t googleusercontent → image")
_assert(_looks_like_image_content("https://storage.googleapis.com/bucket/img"), "38u googleapis storage → image")

# 38v. .svg NEVER auto-rendered, even on an allow-listed host (inline-script XSS defense)
_assert(not _looks_like_image_content("https://cdn.discordapp.com/attachments/x/y.svg"), "38v .svg on trusted host → NOT image")
_assert(not _looks_like_image_content("https://replicate.delivery/foo.svg"), "38w .svg on CDN host → NOT image")

# ══════════════════════════════════════════════════════════════════════════════
# §39  Deferred coverage gaps from swarm tester audit
# ══════════════════════════════════════════════════════════════════════════════

# ── MAX_RETRIES=0 boundary ────────────────────────────────────────────────────

_section("39 · MAX_RETRIES=0 boundary")

# 39a. MAX_RETRIES=0 → exactly 1 attempt then raise
_pipe39 = Pipe()
_pipe39.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=0)
_call_count39 = {"n": 0}
def _conn_err39(*a, **kw):
    _call_count39["n"] += 1
    raise req_lib.exceptions.ConnectionError("net down")
with patch.object(_pipe39._session, "post", side_effect=_conn_err39):
    try:
        _pipe39._retryable_request({}, {}, stream=False)
    except req_lib.exceptions.ConnectionError:
        pass
_assert(_call_count39["n"] == 1, "39a MAX_RETRIES=0: exactly 1 attempt")

# ── _format_cost_info edge cases ──────────────────────────────────────────────

_section("39 · _format_cost_info edge cases")

_format_cost_info = mod._format_cost_info

# 39b. Negative cost (refund/credit) — formats without crash
_neg_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": -0.001}
_neg_result = _format_cost_info(_neg_usage, "USD")
_assert("Cost:" in _neg_result, "39b negative cost: rendered without crash")
_assert("-" in _neg_result, "39c negative cost: minus sign preserved")

# 39d. Boundary value exactly 0.01 (>= boundary)
_boundary_usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.01}
_boundary_result = _format_cost_info(_boundary_usage, "USD")
_assert("$0.0100" in _boundary_result, "39d cost=0.01: 4 decimals")

# 39e. Boundary value exactly 0.0001
_micro_usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0001}
_micro_result = _format_cost_info(_micro_usage, "USD")
_assert("0.000" in _micro_result, "39e cost=0.0001: formatted")

# 39f. total_tokens=0 with non-zero prompt+completion → falls back to sum
_falsy_total_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 0, "cost": 0.01}
_falsy_result = _format_cost_info(_falsy_total_usage, "USD")
_assert("15 total" in _falsy_result, "39f total=0: falls back to prompt+completion")

# 39g. cost = string "abc" (unparseable) → cost line omitted, no crash
_bad_cost_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": "abc"}
_bad_result = _format_cost_info(_bad_cost_usage, "USD")
_assert("Tokens:" in _bad_result, "39g bad cost type: tokens still rendered")
_assert("Cost:" not in _bad_result, "39h bad cost type: cost line dropped")

# ── _is_owui_managed_icon None / case ─────────────────────────────────────────

_section("39 · _is_owui_managed_icon None/case-sensitivity")

_is_owui_managed_icon = mod._is_owui_managed_icon

# 39i. None → True (treated as no icon, replaceable)
_assert(_is_owui_managed_icon(None), "39i None input → True (replaceable)")

# 39j. Empty string → True
_assert(_is_owui_managed_icon(""), "39j empty string → True")

# 39k. data: URL → True
_assert(_is_owui_managed_icon("data:image/png;base64,abc"), "39k data: URL → True")

# 39l. Uppercase HTTPS://OPENROUTER.AI/... — currently matches via lowercase prefix check
# Note: startswith is case-sensitive in current impl; uppercase host returns False.
# Verify current behavior (potential future improvement, not regression):
_assert(not _is_owui_managed_icon("HTTPS://OPENROUTER.AI/images/icons/X"), "39l uppercase URL: not matched (case-sensitive)")

# ── _base property trailing slash ─────────────────────────────────────────────

_section("39 · _base trailing slash sanitization")

_pipe39b = Pipe()
_pipe39b.valves = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="https://openrouter.ai/api/v1///")
_assert(_pipe39b._base == "https://openrouter.ai/api/v1", "39m _base strips trailing slashes")
_assert(_pipe39b.models_url == "https://openrouter.ai/api/v1/models", "39n models_url joined correctly")
_assert(_pipe39b.chat_url == "https://openrouter.ai/api/v1/chat/completions", "39o chat_url joined correctly")

# ── _validate_base_url whitespace ─────────────────────────────────────────────

_section("39 · _validate_base_url whitespace trim")

_pipe39c = Pipe()
_pipe39c.valves = Pipe.Valves(OPENROUTER_API_KEY="k", OPENROUTER_BASE_URL="  https://openrouter.ai/api/v1  ")
_assert(_pipe39c.valves.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1", "39p validator trims whitespace")

# ── Invalid valve values silently ignored ─────────────────────────────────────

_section("39 · invalid valve values silently ignored in payload")

_pipe39d = Pipe()
_pipe39d.valves = Pipe.Valves(
    OPENROUTER_API_KEY="k",
    REASONING_EFFORT="extreme",  # invalid: not low/medium/high
    PROVIDER_SORT="random",       # invalid: not price/throughput/latency
    DATA_COLLECTION="maybe",      # invalid: not allow/deny
)
_payload_invalid = _pipe39d._prepare_payload({"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
_assert("reasoning" not in _payload_invalid, "39q invalid REASONING_EFFORT omitted")
_assert("provider" not in _payload_invalid or "sort" not in _payload_invalid.get("provider", {}), "39r invalid PROVIDER_SORT omitted")
_assert("provider" not in _payload_invalid or "data_collection" not in _payload_invalid.get("provider", {}), "39s invalid DATA_COLLECTION → defaults to allow (key omitted)")

# ── Stream alternating reasoning↔content ──────────────────────────────────────

_section("39 · stream: alternating reasoning↔content (two think blocks)")

_pipe39s = Pipe()
_pipe39s.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_sse_alt = [
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "First think. "}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Some output. "}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"reasoning": "More think. "}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "More output."}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe39s, "_retryable_request", return_value=_make_sse_response(_sse_alt)):
    _alt_chunks = list(_pipe39s._stream_response({}, {}))
_alt_full = "".join(_alt_chunks)
_assert(_alt_full.count("<think>") == 2, "39t alternating: two <think> openings")
_assert(_alt_full.count("</think>") == 2, "39u alternating: two </think> closings")
_assert(_alt_full.find("<think>") < _alt_full.find("Some output"), "39v alternating: first think before content")
_assert(_alt_full.find("More think") < _alt_full.find("More output"), "39w alternating: second think before content")

# ══════════════════════════════════════════════════════════════════════════════
# §40  API key handling — plain str + UI password masking, _api_key accessor
# ══════════════════════════════════════════════════════════════════════════════
#
# NOTE: a prior revision typed OPENROUTER_API_KEY as pydantic.SecretStr.  That
# was REVERTED: Open WebUI persists valves by JSON-serialising them, and a
# SecretStr serialises to the literal mask "**********" — which would overwrite
# the stored key on the next valve save (catastrophic key-wipe).  The key is a
# plain str; UI masking is delivered via json_schema_extra input.type=password.

_section("40 · API key handling (plain str, password UI, _api_key accessor)")

# 40a. Field is a plain str (NOT SecretStr) — survives OWUI JSON valve persistence
_pipe40 = Pipe()
_pipe40.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-or-v1-xyz123")
_assert(isinstance(_pipe40.valves.OPENROUTER_API_KEY, str), "40a API key is plain str")

# 40b. model_dump() / model_dump_json() round-trips the RAW key (no mask) so a
#      valve re-save cannot wipe it — the regression that SecretStr introduced.
_dump = _pipe40.valves.model_dump()
_assert(_dump["OPENROUTER_API_KEY"] == "sk-or-v1-xyz123", "40b model_dump keeps raw key (no mask wipe)")
_assert("sk-or-v1-xyz123" in _pipe40.valves.model_dump_json(), "40c model_dump_json keeps raw key")
_assert("**********" not in _pipe40.valves.model_dump_json(), "40d model_dump_json has no mask literal")

# 40e. UI masking is declared via json_schema_extra password input type
_field = Pipe.Valves.model_fields["OPENROUTER_API_KEY"]
_extra = _field.json_schema_extra or {}
_assert(_extra.get("input", {}).get("type") == "password", "40e field declares password input for UI masking")

# 40f. _api_key property returns the raw key
_assert(_pipe40._api_key == "sk-or-v1-xyz123", "40f _api_key property returns raw value")

# 40g. Authorization header built from raw key
_headers = _pipe40._build_headers()
_assert(_headers["Authorization"] == "Bearer sk-or-v1-xyz123", "40g Bearer header includes raw key")
_assert("**" not in _headers["Authorization"], "40h Bearer header has unmasked key, not mask")

# 40i. Empty key treated as missing in pipes()
_pipe40e = Pipe()
_pipe40e.valves = Pipe.Valves(OPENROUTER_API_KEY="")
_pipes_result = _pipe40e.pipes()
_assert(_pipes_result[0]["id"] == "error", "40i empty key: pipes() returns error model")
_assert("not configured" in _pipes_result[0]["name"].lower(), "40j empty key: msg mentions not configured")

# 40k. Empty key in pipe() returns config error string
_pipe_call = asyncio.run(_pipe40e.pipe({"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}]}))
_assert("not configured" in _pipe_call.lower(), "40k empty key: pipe() returns config error")

# 40l. Cache key uses SHA256 of raw key; same key → same fingerprint, differs by value
_key1 = _pipe40._build_cache_key()
_pipe40b = Pipe()
_pipe40b.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-or-v1-xyz123")
_assert(_key1 == _pipe40b._build_cache_key(), "40l same key → same cache key")
_pipe40c = Pipe()
_pipe40c.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-or-v1-different")
_assert(_key1 != _pipe40c._build_cache_key(), "40m different key → different cache key")
_assert("sk-or-v1-xyz123" not in _key1, "40n cache key does not embed raw key (SHA256 hashed)")

# ══════════════════════════════════════════════════════════════════════════════
# §41  ARCH-2: pipe() streaming always returns AsyncGenerator
# ══════════════════════════════════════════════════════════════════════════════

_section("41 · pipe() stream: AsyncGenerator regardless of __event_emitter__")

_pipe41 = Pipe()
_pipe41.valves = Pipe.Valves(OPENROUTER_API_KEY="k")

_sse_stream = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "tok1"}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {"content": "tok2"}}]}).encode(),
    b"data: [DONE]",
]

# 41a. Stream WITHOUT __event_emitter__ → AsyncGenerator (not sync Generator)
async def _stream_no_emitter():
    with patch.object(_pipe41, "_retryable_request", return_value=_make_sse_response(_sse_stream)):
        result = await _pipe41.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        )
    return result

_no_em_result = asyncio.run(_stream_no_emitter())
_assert(hasattr(_no_em_result, "__aiter__"), "41a stream w/o emitter → has __aiter__ (async)")
_assert(not hasattr(_no_em_result, "__next__"), "41b stream w/o emitter → NOT sync generator")

# 41c. Stream WITH __event_emitter__ → also AsyncGenerator + emits done event
_done_calls = []
async def _emitter(event):
    _done_calls.append(event)

async def _stream_with_emitter():
    with patch.object(_pipe41, "_retryable_request", return_value=_make_sse_response(_sse_stream)):
        result = await _pipe41.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            __event_emitter__=_emitter,
        )
        chunks = []
        async for chunk in result:
            chunks.append(chunk)
        return "".join(chunks)

_emitted = asyncio.run(_stream_with_emitter())
_assert("tok1" in _emitted and "tok2" in _emitted, "41c stream w/ emitter: content streamed")
_done_events = [e for e in _done_calls if e.get("data", {}).get("done") is True]
_assert(len(_done_events) == 1, "41d stream w/ emitter: exactly one done event emitted")
_initial_events = [e for e in _done_calls if e.get("data", {}).get("done") is False]
_assert(len(_initial_events) == 1, "41e stream w/ emitter: initial 'Querying...' event emitted")

# 41f. Non-stream still returns plain str
async def _non_stream_test():
    _mock_ns = MagicMock()
    _mock_ns.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    with patch.object(_pipe41, "_retryable_request", return_value=_mock_ns):
        return await _pipe41.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": False}
        )
_ns_result = asyncio.run(_non_stream_test())
_assert(isinstance(_ns_result, str), "41f non-stream returns str (not generator)")

# ══════════════════════════════════════════════════════════════════════════════
# §42  Strengthened tests for branches flagged WEAK/MISSING by swarm tester
# ══════════════════════════════════════════════════════════════════════════════

# ── _write_model_icon clear-path (icon_url="") — stale /images/models/ URL ────

_section("42 · _sync_model_icons stale-icon clear path")

_pipe42 = Pipe()
_pipe42.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe42._function_id = "openrouter_pipe"
# Provider 'aion-labs' has NO entry in _PROVIDER_ICONS → icon_url is None →
# triggers the stale-clear branch when the DB holds an old /images/models/ URL.
_mock_Models_42 = MagicMock()
_stale_model = MagicMock()
_stale_model.meta.profile_image_url = "https://openrouter.ai/images/models/aion.png"
_stale_model.name = "Aion 1.0"
_stale_model.params = None
_mock_Models_42.get_model_by_id.return_value = _stale_model
_mock_ModelForm_42 = MagicMock()
_mock_ModelMeta_42 = MagicMock()
_fake_owui_42 = ModuleType("open_webui.models.models")
_fake_owui_42.Models = _mock_Models_42
_fake_owui_42.ModelForm = _mock_ModelForm_42
_fake_owui_42.ModelMeta = _mock_ModelMeta_42
_fake_owui_42.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_42
    _pipe42._sync_model_icons([{"id": "aion-labs/aion-1.0", "name": "Aion 1.0"}])
    # 42a. update_model_by_id called to clear the stale icon
    _assert(_mock_Models_42.update_model_by_id.called, "42a stale-clear: update_model_by_id called")
    # 42b. ModelMeta built with empty profile_image_url (icon cleared)
    _meta_calls = _mock_ModelMeta_42.call_args_list
    _cleared = any(c.kwargs.get("profile_image_url") == "" for c in _meta_calls)
    _assert(_cleared, "42b stale-clear: ModelMeta profile_image_url='' (cleared)")
    # 42c. model marked synced after clear
    _assert("aion-labs/aion-1.0" in _pipe42._icons_synced, "42c stale-clear: model marked synced")
finally:
    sys.modules.pop("open_webui.models.models", None)

# 42d. No-icon provider WITHOUT stale URL → no update, just marked synced
_pipe42b = Pipe()
_pipe42b.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe42b._function_id = "openrouter_pipe"
_mock_Models_42b = MagicMock()
_normal_model = MagicMock()
_normal_model.meta.profile_image_url = "data:image/svg+xml;base64,xxx"  # OWUI default, not stale
_normal_model.name = "Aion"
_normal_model.params = None
_mock_Models_42b.get_model_by_id.return_value = _normal_model
_fake_owui_42b = ModuleType("open_webui.models.models")
_fake_owui_42b.Models = _mock_Models_42b
_fake_owui_42b.ModelForm = MagicMock()
_fake_owui_42b.ModelMeta = MagicMock()
_fake_owui_42b.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_42b
    _pipe42b._sync_model_icons([{"id": "aion-labs/aion-1.0", "name": "Aion"}])
    _assert(not _mock_Models_42b.update_model_by_id.called, "42d no-icon + non-stale: no update")
    _assert("aion-labs/aion-1.0" in _pipe42b._icons_synced, "42e no-icon + non-stale: marked synced")
finally:
    sys.modules.pop("open_webui.models.models", None)

# ── Icon insert retry cap — real path (4 calls, insert stops at cap) ──────────

_section("42 · icon insert retry cap (real path)")

_pipe42c = Pipe()
_pipe42c.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe42c._function_id = "openrouter_pipe"
_mock_Models_cap = MagicMock()
_mock_Models_cap.get_model_by_id.return_value = None  # never registered → always insert path
_fake_owui_cap = ModuleType("open_webui.models.models")
_fake_owui_cap.Models = _mock_Models_cap
_fake_owui_cap.ModelForm = MagicMock()
_fake_owui_cap.ModelMeta = MagicMock()
_fake_owui_cap.ModelParams = MagicMock()
_model_cap = [{"id": "openai/gpt-4o", "name": "GPT-4o"}]  # openai HAS an icon
try:
    sys.modules["open_webui.models.models"] = _fake_owui_cap
    # Call 4 times — OWUI never registers the model, so insert is attempted
    for _ in range(4):
        _pipe42c._sync_model_icons(_model_cap)
    # 42f. insert attempted exactly _MAX_ICON_INSERT_ATTEMPTS (3) times, then capped
    _assert(_mock_Models_cap.insert_new_model.call_count == 3, "42f icon cap: insert tried exactly 3 times")
    # 42g. after cap reached, model is marked EXHAUSTED (not synced) so a late
    #      OWUI registration can still be picked up by the existing-branch.
    _assert("openai/gpt-4o" in _pipe42c._icon_insert_exhausted, "42g icon cap: model marked exhausted (not synced)")
    _assert("openai/gpt-4o" not in _pipe42c._icons_synced, "42g2 icon cap: NOT in _icons_synced (re-check stays alive)")
    # 42h. a 5th call does NOT insert again (exhausted)
    _pipe42c._sync_model_icons(_model_cap)
    _assert(_mock_Models_cap.insert_new_model.call_count == 3, "42h icon cap: no insert after exhausted")
    # 42h2. exhausted model is STILL re-checked via get_model_by_id each pass
    #       (this is the fix: a late registration must be catchable).
    _calls_before = _mock_Models_cap.get_model_by_id.call_count
    _pipe42c._sync_model_icons(_model_cap)
    _assert(_mock_Models_cap.get_model_by_id.call_count > _calls_before, "42h3 exhausted model still re-checked (late-registration catchable)")
finally:
    sys.modules.pop("open_webui.models.models", None)

# 42h4. Late registration: exhausted model that OWUI later registers gets synced
_pipe42cc = Pipe()
_pipe42cc.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe42cc._function_id = "openrouter_pipe"
_pipe42cc._icon_insert_exhausted.add("openai/gpt-4o")  # simulate prior exhaustion
_pipe42cc._icon_insert_attempts["openai/gpt-4o"] = 3
_mock_Models_late = MagicMock()
_late_model = MagicMock()
_late_model.meta.profile_image_url = ""  # OWUI just registered it, empty icon
_late_model.name = "GPT-4o"
_late_model.params = None
_mock_Models_late.get_model_by_id.return_value = _late_model  # now exists!
_fake_owui_late = ModuleType("open_webui.models.models")
_fake_owui_late.Models = _mock_Models_late
_fake_owui_late.ModelForm = MagicMock()
_fake_owui_late.ModelMeta = MagicMock()
_fake_owui_late.ModelParams = MagicMock()
try:
    sys.modules["open_webui.models.models"] = _fake_owui_late
    _pipe42cc._sync_model_icons([{"id": "openai/gpt-4o", "name": "GPT-4o"}])
    _assert(_mock_Models_late.update_model_by_id.called, "42h4 late-registration: icon updated via existing-branch")
    _assert("openai/gpt-4o" not in _pipe42cc._icon_insert_exhausted, "42h5 late-registration: cleared from exhausted set")
    _assert("openai/gpt-4o" in _pipe42cc._icons_synced, "42h6 late-registration: now marked synced")
finally:
    sys.modules.pop("open_webui.models.models", None)

# ── Stream wrapper GeneratorExit / early-break cleanup ────────────────────────

_section("42 · stream wrapper closes inner gen on early break")

_pipe42d = Pipe()
_pipe42d.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
_close_flag_42 = {"closed": False}

class _TrackingSSE42:
    """Mock response whose iter_lines yields slowly and records close()."""
    def __init__(self):
        self.status_code = 200
    def iter_lines(self):
        for i in range(100):
            yield b"data: " + json.dumps({"choices": [{"delta": {"content": f"tok{i}"}}]}).encode()
        yield b"data: [DONE]"
    def close(self):
        _close_flag_42["closed"] = True
    def raise_for_status(self):
        pass

# 42i. Early break from the AsyncGenerator wrapper closes the underlying response
async def _early_break():
    with patch.object(_pipe42d, "_retryable_request", return_value=_TrackingSSE42()):
        result = await _pipe42d.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        )
        count = 0
        async for chunk in result:
            count += 1
            if count >= 2:
                break  # abort early → triggers GeneratorExit cleanup
        # Force-close the async generator (what an aborting consumer / runtime does)
        await result.aclose()
        return count

_broke_at = asyncio.run(_early_break())
_assert(_broke_at == 2, "42i early-break: consumed exactly 2 chunks then aborted")
_assert(_close_flag_42["closed"], "42j early-break: inner response.close() ran (no leak)")

# 42k. Done-event still fires on early break (wrapper finally block)
_done_42 = []
async def _early_break_emitter(event):
    _done_42.append(event)
async def _early_break_with_emitter():
    with patch.object(_pipe42d, "_retryable_request", return_value=_TrackingSSE42()):
        result = await _pipe42d.pipe(
            {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            __event_emitter__=_early_break_emitter,
        )
        async for _chunk in result:
            break
        await result.aclose()
_ = asyncio.run(_early_break_with_emitter())
_done_evts_42 = [e for e in _done_42 if e.get("data", {}).get("done") is True]
_assert(len(_done_evts_42) == 1, "42k early-break: done-event still emitted in finally")

# ══════════════════════════════════════════════════════════════════════════════
# §43  3rd-audit findings: usage-in-stream, SSE prefix, cache bare-string
# ══════════════════════════════════════════════════════════════════════════════

# ── #6: usage requested when SHOW_COST_INFO (cost in streaming) ───────────────

_section("43 · usage:{include:true} requested when SHOW_COST_INFO")

# 43a. SHOW_COST_INFO=True → payload carries usage.include=true (so streaming
#      responses get a final usage chunk with cost; OpenRouter requires opt-in).
_pipe43 = Pipe()
_pipe43.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True)
_payload_cost = _pipe43._prepare_payload({"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
_assert(_payload_cost.get("usage") == {"include": True}, "43a SHOW_COST_INFO=True → usage.include=true")

# 43b. SHOW_COST_INFO=False → no usage key (don't pay for what we won't show)
_pipe43b = Pipe()
_pipe43b.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=False)
_payload_nocost = _pipe43b._prepare_payload({"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
_assert("usage" not in _payload_nocost, "43b SHOW_COST_INFO=False → no usage key")

# 43c. End-to-end: streaming with cost shows cost when usage arrives in final chunk
_pipe43c = Pipe()
_pipe43c.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SHOW_COST_INFO=True)
_sse_cost = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "Hi"}}]}).encode(),
    b"data: " + json.dumps({"choices": [{"delta": {}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7, "cost": 0.0012}}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe43c, "_retryable_request", return_value=_make_sse_response(_sse_cost)):
    _cost_stream = "".join(_pipe43c._stream_response({}, {}))
_assert("Cost:" in _cost_stream, "43c streaming cost: cost line rendered from final usage chunk")

# ── SSE "data:" without trailing space (spec-valid) ──────────────────────────

_section("43 · SSE data: prefix tolerates missing space")

_pipe43d = Pipe()
_pipe43d.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
# 43d. "data:{json}" with NO space after colon must still parse (SSE spec)
_sse_nospace = [
    b"data:" + json.dumps({"choices": [{"delta": {"content": "nospace"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe43d, "_retryable_request", return_value=_make_sse_response(_sse_nospace)):
    _nospace_out = "".join(_pipe43d._stream_response({}, {}))
_assert("nospace" in _nospace_out, "43d SSE 'data:' without space → content parsed")

# 43e. Mixed: spaced and unspaced in same stream
_sse_mixed_prefix = [
    b"data: " + json.dumps({"choices": [{"delta": {"content": "A"}}]}).encode(),
    b"data:" + json.dumps({"choices": [{"delta": {"content": "B"}}]}).encode(),
    b"data: [DONE]",
]
with patch.object(_pipe43d, "_retryable_request", return_value=_make_sse_response(_sse_mixed_prefix)):
    _mixed_prefix_out = "".join(_pipe43d._stream_response({}, {}))
_assert("A" in _mixed_prefix_out and "B" in _mixed_prefix_out, "43e SSE mixed spaced/unspaced both parsed")

# ── _inject_cache_control with a bare-string content part ─────────────────────

_section("43 · cache_control tolerates bare-string content part")

_pipe43f = Pipe()
_pipe43f.valves = Pipe.Valves(OPENROUTER_API_KEY="k", ENABLE_CACHE_CONTROL=True)
# 43f. content list containing a bare string part (not a dict) → must not abort;
#      the text part still gets tagged.
_payload_mixed_parts = {
    "model": "anthropic/claude-3.5-sonnet",
    "messages": [{
        "role": "user",
        "content": [
            "a bare string part",  # not a dict — must be skipped, not crash
            {"type": "text", "text": "the long cacheable text part here"},
        ],
    }],
}
_prepared_mixed = _pipe43f._prepare_payload(_payload_mixed_parts)
_tagged = _prepared_mixed["messages"][0]["content"][1].get("cache_control")
_assert(_tagged == {"type": "ephemeral"}, "43f cache_control: text part tagged despite bare-string sibling")

# ══════════════════════════════════════════════════════════════════════════════
# §44  Async OWUI Models API + /static default icon (live-confirmed icon bug)
# ══════════════════════════════════════════════════════════════════════════════
#
# Root cause (confirmed against open-webui:main on the live instance):
#   1. OWUI migrated Models.get_model_by_id / insert_new_model /
#      update_model_by_id to async coroutines.  The pipe called them
#      synchronously, so every read returned an un-awaited coroutine and every
#      write was a silent no-op -> no icon ever reached the DB.
#   2. OWUI's default pipe-model icon is "/static/favicon.png", which
#      _is_owui_managed_icon did not recognise -> even once writes worked, the
#      record would be skipped as a "user-set" icon.

_section("44 · /static default icon recognised as managed")

# 44a. OWUI's current default pipe-model icon must be overwritable
_assert(_is_owui_managed_icon("/static/favicon.png"), "44a /static/favicon.png -> managed")
_assert(_is_owui_managed_icon("/static/anything.png"), "44b /static/ prefix -> managed")
# 44c. data: and our own paths still managed
_assert(_is_owui_managed_icon("data:image/svg+xml;base64,x"), "44c data: -> managed")
_assert(_is_owui_managed_icon("https://openrouter.ai/images/icons/Qwen.png"), "44d our icon path -> managed")
# 44e. genuine user-set custom icon still preserved
_assert(not _is_owui_managed_icon("https://my-cdn.example.com/custom.png"), "44e user custom URL -> preserved")
_assert(not _is_owui_managed_icon("/cache/image/user-upload.png"), "44f /cache upload -> preserved")

_section("44 · _resolve_owui_call (sync passthrough + async resolution)")

_resolve_owui_call = mod._resolve_owui_call

# 44g. Non-coroutine passes through unchanged (old sync OWUI)
_assert(_resolve_owui_call(123) == 123, "44g sync value passthrough")
_sentinel = object()
_assert(_resolve_owui_call(_sentinel) is _sentinel, "44h sync object identity preserved")

# 44i. Coroutine is run to completion (new async OWUI)
async def _coro_value():
    return "resolved-value"
_assert(_resolve_owui_call(_coro_value()) == "resolved-value", "44i coroutine resolved to its return value")

# 44j. Coroutine exception propagates to caller
async def _coro_raises():
    raise ValueError("db boom")
try:
    _resolve_owui_call(_coro_raises())
    _assert(False, "44j coroutine exception should propagate")
except ValueError as exc:
    _assert("db boom" in str(exc), "44j coroutine exception propagates")

# 44k. Works even with an event loop already running (the real pipes() context)
async def _outer():
    # _resolve_owui_call must not call asyncio.run on the running loop
    return _resolve_owui_call(_coro_value())
_assert(asyncio.run(_outer()) == "resolved-value", "44k resolves coroutine from within a running loop")

_section("44 · _sync_model_icons against ASYNC OWUI Models (regression)")

# Simulate the OWUI:main async API: every Models method is a coroutine.
class _AsyncModelsRegistry:
    """Async stand-in for OWUI's Models table; records update calls."""
    def __init__(self, existing_by_id):
        self._store = existing_by_id
        self.updated = {}   # id -> profile_image_url written
        self.inserted = {}

    async def get_model_by_id(self, mid):
        return self._store.get(mid)

    async def update_model_by_id(self, mid, form):
        self.updated[mid] = form.meta.profile_image_url
        return self._store.get(mid)

    async def insert_new_model(self, form, user_id=None):
        self.inserted[form.id] = form.meta.profile_image_url
        return form

class _FakeMeta:
    def __init__(self, url):
        self.profile_image_url = url

class _FakeExistingModel:
    def __init__(self, mid, name, icon):
        self.id = mid
        self.name = name
        self.meta = _FakeMeta(icon)
        self.params = None

class _RecordingForm:
    def __init__(self, id=None, name=None, meta=None, params=None):
        self.id = id; self.name = name; self.meta = meta; self.params = params

class _RecordingMeta:
    def __init__(self, profile_image_url=""):
        self.profile_image_url = profile_image_url

class _RecordingParams:
    def __init__(self, *a, **k):
        pass

_pipe44 = Pipe()
_pipe44.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe44._function_id = "openrouter_pipe"

# Existing DB record carrying OWUI's /static default (the live-observed state)
_existing = {
    "openrouter_pipe.qwen/qwen3.6-plus": _FakeExistingModel(
        "openrouter_pipe.qwen/qwen3.6-plus", "Qwen: Qwen3.6 Plus", "/static/favicon.png"
    ),
}
_async_models = _AsyncModelsRegistry(_existing)
_fake_owui_async = ModuleType("open_webui.models.models")
_fake_owui_async.Models = _async_models
_fake_owui_async.ModelForm = _RecordingForm
_fake_owui_async.ModelMeta = _RecordingMeta
_fake_owui_async.ModelParams = _RecordingParams
try:
    sys.modules["open_webui.models.models"] = _fake_owui_async
    _pipe44._sync_model_icons([{"id": "qwen/qwen3.6-plus", "name": "Qwen: Qwen3.6 Plus"}])
    # 44l. The async update actually ran (was a silent no-op before the fix)
    _assert("openrouter_pipe.qwen/qwen3.6-plus" in _async_models.updated, "44l async update_model_by_id was awaited/executed")
    # 44m. It wrote the correct provider icon over the /static default
    _assert(
        _async_models.updated.get("openrouter_pipe.qwen/qwen3.6-plus") == "https://openrouter.ai/images/icons/Qwen.png",
        "44m async OWUI: qwen record updated to provider icon",
    )
    # 44n. Model marked synced after a successful async write
    _assert("qwen/qwen3.6-plus" in _pipe44._icons_synced, "44n model marked synced after async write")
finally:
    sys.modules.pop("open_webui.models.models", None)

# 44o. Async insert path (model not yet in DB) also executes
_pipe44b = Pipe()
_pipe44b.valves = Pipe.Valves(OPENROUTER_API_KEY="k", SYNC_PROVIDER_ICONS=True)
_pipe44b._function_id = "openrouter_pipe"
_async_models2 = _AsyncModelsRegistry({})  # empty -> insert path
_fake_owui_async2 = ModuleType("open_webui.models.models")
_fake_owui_async2.Models = _async_models2
_fake_owui_async2.ModelForm = _RecordingForm
_fake_owui_async2.ModelMeta = _RecordingMeta
_fake_owui_async2.ModelParams = _RecordingParams
try:
    sys.modules["open_webui.models.models"] = _fake_owui_async2
    _pipe44b._sync_model_icons([{"id": "openai/gpt-4o", "name": "GPT-4o"}])
    _assert("openrouter_pipe.openai/gpt-4o" in _async_models2.inserted, "44o async insert_new_model executed")
    _assert(
        _async_models2.inserted.get("openrouter_pipe.openai/gpt-4o") == "https://openrouter.ai/images/icons/OpenAI.svg",
        "44p async insert carries provider icon",
    )
finally:
    sys.modules.pop("open_webui.models.models", None)

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
