"""
Comprehensive test suite for OpenRouter Pipe v0.2.0
Runs with: python test_pipe.py
"""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import json
import os
import sys
import traceback
from io import BytesIO
from types import ModuleType
from typing import List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

# ── Load the pipe module from the .json file ──────────────────────────────────
_PIPE_PATH = os.path.join(os.path.dirname(__file__), "OpenRouter - SenaLabs.json")
# Force SourceFileLoader since file has .json extension
_loader = importlib.machinery.SourceFileLoader("openrouter_pipe", _PIPE_PATH)
spec = importlib.util.spec_from_loader("openrouter_pipe", _loader, origin=_PIPE_PATH)
mod: ModuleType = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

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
_assert(v.MODEL_PREFIX is None, "prefix None")
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

# ── 4. Pipe.__init__ ────────────────────────────────────────────────────────

_section("4. Pipe.__init__()")

pipe = Pipe()
_assert(pipe.type == "manifold", "type is manifold")
_assert(pipe.models_url.endswith("/models"), "models_url ends with /models")
_assert(pipe.chat_url.endswith("/chat/completions"), "chat_url ends with /chat/completions")

# ── 5. _prepare_payload ─────────────────────────────────────────────────────

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
    payload["models"] == ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
    "fallback models",
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
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MODEL_PROVIDERS=None)
_assert(pipe._parse_provider_filter() is None, "None → None")

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
exc = MagicMock(spec=["response"])
exc.response = mock_resp
exc.__class__ = type("HTTPError", (Exception,), {})
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

# ── 11. _non_stream_response ────────────────────────────────────────────────

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

_assert(result == "", "empty choices → empty string")

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

# ── 13. _retryable_request ──────────────────────────────────────────────────

_section("13. _retryable_request()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k", MAX_RETRIES=2, REQUEST_TIMEOUT=5)
pipe.chat_url = "https://openrouter.ai/api/v1/chat/completions"

# 13a. Success on first try
mock_ok = MagicMock()
mock_ok.raise_for_status = MagicMock()
with patch("requests.post", return_value=mock_ok) as mock_post:
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

with patch("requests.post", side_effect=_post_retry):
    call_count[0] = 0
    result = pipe._retryable_request({}, {}, stream=False)
    _assert(call_count[0] == 2, "retryable: retried after timeout")

# 13c. All retries exhausted
with patch("requests.post", side_effect=req_lib.exceptions.Timeout("timeout")):
    try:
        pipe._retryable_request({}, {}, stream=False)
        _assert(False, "retryable: should raise after all retries")
    except req_lib.exceptions.Timeout:
        _assert(True, "retryable: raises Timeout after exhausting retries")

# 13d. HTTPError not retried
with patch("requests.post") as mock_post:
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
async def _test_pipe_stream():
    sse = _make_sse_response([
        b"data: " + json.dumps({"choices": [{"delta": {"content": "World"}}]}).encode(),
        b"data: [DONE]",
    ])
    with patch.object(pipe, "_retryable_request", return_value=sse):
        result = await pipe.pipe(
            {"model": "openai/gpt-4o", "messages": [], "stream": True}
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
mock_resp.json.return_value = mock_models
mock_resp.raise_for_status = MagicMock()

with patch("requests.get", return_value=mock_resp):
    models = pipe.pipes()

_assert(len(models) == 3, "pipes: returns 3 models")
_assert(models[0]["id"] == "openai/gpt-4o", "pipes: first model ID")
_assert("info" in models[0], "pipes: info key present")
_assert("meta" in models[0]["info"], "pipes: meta key present")

# 15b. FREE_ONLY filter
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="test-key", FREE_ONLY=True)
with patch("requests.get", return_value=mock_resp):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes FREE_ONLY: only 1 free model")
_assert(":free" in models[0]["id"].lower(), "pipes FREE_ONLY: is free model")

# 15c. Provider filter
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="openai"
)
with patch("requests.get", return_value=mock_resp):
    models = pipe.pipes()
_assert(len(models) == 1, "pipes provider filter: only openai")
_assert(models[0]["id"] == "openai/gpt-4o", "pipes provider filter: correct model")

# 15d. Invert provider filter
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PROVIDERS="openai", INVERT_PROVIDER_LIST=True
)
with patch("requests.get", return_value=mock_resp):
    models = pipe.pipes()
_assert(len(models) == 2, "pipes invert: excludes openai → 2 models")

# 15e. PREFIX
pipe.valves = Pipe.Valves(
    OPENROUTER_API_KEY="test-key", MODEL_PREFIX="🔥 "
)
with patch("requests.get", return_value=mock_resp):
    models = pipe.pipes()
_assert(models[0]["name"].startswith("🔥 "), "pipes prefix: name prefixed")

# 15f. No API key
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="")
models = pipe.pipes()
_assert(len(models) == 1, "pipes no key: 1 error entry")
_assert(models[0]["id"] == "error", "pipes no key: error id")

# 15g. Timeout
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY="k")
with patch("requests.get", side_effect=req_lib.exceptions.Timeout("t")):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes timeout: error")
_assert("timeout" in models[0]["name"].lower(), "pipes timeout: timeout in name")

# 15h. HTTP error
mock_resp_err = MagicMock()
mock_resp_err.status_code = 403
mock_resp_err.json.return_value = {"error": {"message": "Forbidden"}}
mock_resp_err.raise_for_status.side_effect = req_lib.exceptions.HTTPError(response=mock_resp_err)
with patch("requests.get", return_value=mock_resp_err):
    models = pipe.pipes()
_assert(models[0]["id"] == "error", "pipes HTTP error: error id")
_assert("403" in models[0]["name"], "pipes HTTP error: status in name")

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
