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
import traceback
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
_assert(v.OPENROUTER_API_KEY == frozen_default, f"API key default matches frozen class default")
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

_section("7. _get_provider_icon()")

pipe = Pipe()
_assert(pipe._get_provider_icon("openai") is not None, "openai icon found")
_assert(pipe._get_provider_icon("Anthropic") is not None, "Anthropic (case) icon found")
_assert(pipe._get_provider_icon("unknown-provider") is None, "unknown → None")

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

# 11d. Timeout
with patch.object(
    pipe, "_retryable_request",
    side_effect=req_lib.exceptions.Timeout("timeout"),
):
    result = pipe._non_stream_response({}, {})
_assert("timeout" in result.lower(), "timeout error message")

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
        chunks = list(result)
    return "".join(chunks), events

res_s, events_s = asyncio.run(_test_pipe_event_emitter_stream())
_assert(len(events_s) == 1, "pipe stream event_emitter: 1 event (start only)")
_assert(events_s[0]["data"]["done"] is False, "pipe stream event_emitter: start not done")
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
_assert("info" in models[0], "pipes: info key present")
_assert("meta" in models[0]["info"], "pipes: meta key present")

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
