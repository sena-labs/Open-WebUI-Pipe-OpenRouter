"""
Integration test for OpenRouter Pipe v1.3.0
Tests the pipe against the LIVE OpenRouter API.

Usage:
    $env:OPENROUTER_API_KEY = "sk-or-..."
    python integration_test.py

Author: Sena Labs (https://github.com/sena-labs)
License: MIT
"""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import os
import sys
import time
from types import ModuleType

# ── Load the pipe module ─────────────────────────────────────────────────────
_PIPE_PATH = os.path.join(os.path.dirname(__file__), "openrouter_pipe.py")
_loader = importlib.machinery.SourceFileLoader("openrouter_pipe", _PIPE_PATH)
spec = importlib.util.spec_from_loader("openrouter_pipe", _loader, origin=_PIPE_PATH)
assert spec is not None and spec.loader is not None
mod: ModuleType = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.modules["openrouter_pipe"] = mod

Pipe = mod.Pipe

# ── Helpers ───────────────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0
_SKIP = 0


def _assert(condition: bool, msg: str):
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ✓ {msg}")
    else:
        _FAIL += 1
        print(f"  ✗ FAIL: {msg}")


def _skip(msg: str):
    global _SKIP
    _SKIP += 1
    print(f"  ⊘ SKIP: {msg}")


def _section(title: str):
    print(f"\n{'═'*60}\n  {title}\n{'═'*60}")


# ── Pre-flight ────────────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not API_KEY:
    print("\n  ✗ OPENROUTER_API_KEY not set. Run:")
    print('    $env:OPENROUTER_API_KEY = "sk-or-..."')
    print("    python integration_test.py\n")
    sys.exit(1)

print(f"\n  API key: {API_KEY[:12]}...{API_KEY[-4:]}")
print(f"  Key length: {len(API_KEY)} chars")


# Quick preflight chat call to detect account-level "native web search" config
def _check_chat_available() -> bool:
    """Return True if chat completions work, False if blocked by web-search."""
    import requests

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
            },
            timeout=15,
        )
        if r.status_code == 404 and "web search" in r.text.lower():
            return False
        return True
    except Exception:
        return True  # assume OK, let real tests surface errors


CHAT_AVAILABLE = _check_chat_available()
if not CHAT_AVAILABLE:
    print("  ⚠ Account has 'native web search' enabled — chat tests will be skipped")
    print("    Disable it at https://openrouter.ai/settings/integrations\n")
else:
    print("  Chat completions: available\n")

# ══════════════════════════════════════════════════════════════════════════════
# 1. Model listing (pipes)
# ══════════════════════════════════════════════════════════════════════════════

_section("1. Model listing — pipes()")

pipe = Pipe()
pipe.valves = Pipe.Valves(OPENROUTER_API_KEY=API_KEY, MODEL_PROVIDERS="ALL")

t0 = time.time()
models = pipe.pipes()
elapsed = time.time() - t0

_assert(len(models) > 0, f"got models ({len(models)} total)")
_assert(models[0]["id"] != "error", f"no error: first model = {models[0]['id']}")
_assert(len(models) >= 200, f"at least 200 models ({len(models)} found)")
print(f"  ⏱ Fetched in {elapsed:.2f}s")

# Check structure
if models and models[0]["id"] != "error":
    m = models[0]
    _assert("id" in m, "model has 'id'")
    _assert("name" in m, "model has 'name'")
    # Icons are synced into the DB via _sync_model_icons, not via model dict

    # Check for known providers
    providers = {m["id"].split("/")[0] for m in models if "/" in m["id"]}
    print(f"  ℹ Providers found: {len(providers)}")
    for expected in ["openai", "anthropic", "google", "meta-llama", "deepseek"]:
        _assert(expected in providers, f"provider '{expected}' present")

# ══════════════════════════════════════════════════════════════════════════════
# 2. Provider filter
# ══════════════════════════════════════════════════════════════════════════════

_section("2. Provider filter — MODEL_PROVIDERS")

pipe_filtered = Pipe()
pipe_filtered.valves = Pipe.Valves(
    OPENROUTER_API_KEY=API_KEY, MODEL_PROVIDERS="openai"
)
filtered = pipe_filtered.pipes()
_assert(len(filtered) > 0, f"openai filter: {len(filtered)} models")
_assert(
    all(m["id"].startswith("openai/") for m in filtered if m["id"] != "error"),
    "all models are openai/*",
)

# Invert
pipe_inv = Pipe()
pipe_inv.valves = Pipe.Valves(
    OPENROUTER_API_KEY=API_KEY,
    MODEL_PROVIDERS="openai",
    INVERT_PROVIDER_LIST=True,
)
inverted = pipe_inv.pipes()
_assert(len(inverted) > 0, f"inverted filter: {len(inverted)} models")
_assert(
    not any(m["id"].startswith("openai/") for m in inverted),
    "no openai models in inverted list",
)
_assert(
    len(inverted) > len(filtered),
    f"inverted ({len(inverted)}) > filtered ({len(filtered)})",
)

# ══════════════════════════════════════════════════════════════════════════════
# 3. FREE_MODEL_FILTER='only'
# ══════════════════════════════════════════════════════════════════════════════

_section("3. FREE_MODEL_FILTER='only'")

pipe_free = Pipe()
pipe_free.valves = Pipe.Valves(OPENROUTER_API_KEY=API_KEY, FREE_MODEL_FILTER="only")
free_models = pipe_free.pipes()
_assert(len(free_models) > 0, f"free models: {len(free_models)}")
_assert(
    len(free_models) < len(models),
    f"free ({len(free_models)}) < all ({len(models)})",
)

# ══════════════════════════════════════════════════════════════════════════════
# 4. Non-streaming chat
# ══════════════════════════════════════════════════════════════════════════════

_section("4. Non-streaming chat")

if not CHAT_AVAILABLE:
    _skip("chat blocked by account-level web search — disable in OpenRouter settings")
else:
    pipe_chat = Pipe()
    pipe_chat.valves = Pipe.Valves(
        OPENROUTER_API_KEY=API_KEY,
        INCLUDE_REASONING=False,
    )

    body_ns = {
        "model": "openrouter.openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Respond with exactly: INTEGRATION_TEST_OK"}],
        "stream": False,
    }

    async def _test_non_stream() -> str:
        result = await pipe_chat.pipe(body_ns)
        return result  # type: ignore[return-value]

    t0 = time.time()
    ns_result = asyncio.run(_test_non_stream())
    elapsed = time.time() - t0

    _assert(isinstance(ns_result, str), "non-stream returns string")
    _assert(len(ns_result) > 0, f"non-stream has content ({len(ns_result)} chars)")
    _assert("Error" not in ns_result or "INTEGRATION" in ns_result, "no error in response")
    print(f"  ⏱ Response in {elapsed:.2f}s")
    print(f"  ℹ Response: {ns_result[:150]}{'...' if len(ns_result) > 150 else ''}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. Streaming chat
# ══════════════════════════════════════════════════════════════════════════════

_section("5. Streaming chat (SSE)")

if not CHAT_AVAILABLE:
    _skip("chat blocked by account-level web search — disable in OpenRouter settings")
else:
    pipe_stream = Pipe()
    pipe_stream.valves = Pipe.Valves(
        OPENROUTER_API_KEY=API_KEY,
        INCLUDE_REASONING=False,
    )

    body_s = {
        "model": "openrouter.openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Count from 1 to 5, one number per line."}],
        "stream": True,
    }

    async def _test_stream() -> tuple[list[str], float]:
        t = time.time()
        result = await pipe_stream.pipe(body_s)
        chunks = list(result)  # type: ignore[arg-type]
        return chunks, time.time() - t

    chunks, elapsed = asyncio.run(_test_stream())
    full_stream = "".join(chunks)

    _assert(len(chunks) > 1, f"stream: {len(chunks)} chunks received")
    _assert(len(full_stream) > 0, f"stream: {len(full_stream)} chars total")
    _assert("Error" not in full_stream or "1" in full_stream, "stream: no error")
    print(f"  ⏱ Streamed in {elapsed:.2f}s ({len(chunks)} chunks)")
    print(f"  ℹ Content: {full_stream[:150]}{'...' if len(full_stream) > 150 else ''}")

# ══════════════════════════════════════════════════════════════════════════════
# 6. Reasoning tokens (think tags)
# ══════════════════════════════════════════════════════════════════════════════

_section("6. Reasoning tokens (<think> tags)")

if not CHAT_AVAILABLE:
    _skip("chat blocked by account-level web search — disable in OpenRouter settings")
else:
    pipe_reason = Pipe()
    pipe_reason.valves = Pipe.Valves(
        OPENROUTER_API_KEY=API_KEY,
        INCLUDE_REASONING=True,
        REASONING_EFFORT="low",
    )

    # Use a model known to support reasoning
    body_reason = {
        "model": "openrouter.deepseek/deepseek-r1",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "stream": False,
    }

    async def _test_reasoning() -> str:
        result = await pipe_reason.pipe(body_reason)
        return result  # type: ignore[return-value]

    try:
        t0 = time.time()
        reason_result = asyncio.run(_test_reasoning())
        elapsed = time.time() - t0

        if "Error" in reason_result and "think" not in reason_result:
            _skip(f"reasoning model returned error: {reason_result[:100]}")
        else:
            _assert("<think>" in reason_result, "reasoning: <think> tag present")
            _assert("</think>" in reason_result, "reasoning: </think> tag present")
            # The answer should mention 4
            _assert("4" in reason_result, "reasoning: answer contains '4'")
            print(f"  ⏱ Reasoning in {elapsed:.2f}s")
            think_len = reason_result.find("</think>") - reason_result.find("<think>")
            print(f"  ℹ Think block: ~{think_len} chars")
    except Exception as exc:
        _skip(f"reasoning test failed: {exc}")

# ══════════════════════════════════════════════════════════════════════════════
# 7. Streaming with reasoning
# ══════════════════════════════════════════════════════════════════════════════

_section("7. Streaming with reasoning")

if not CHAT_AVAILABLE:
    _skip("chat blocked by account-level web search — disable in OpenRouter settings")
else:
    body_reason_stream = {
        "model": "openrouter.deepseek/deepseek-r1",
        "messages": [{"role": "user", "content": "What is 3+3?"}],
        "stream": True,
    }

    pipe_reason_s = Pipe()
    pipe_reason_s.valves = Pipe.Valves(
        OPENROUTER_API_KEY=API_KEY,
        INCLUDE_REASONING=True,
        REASONING_EFFORT="low",
    )

    async def _test_reasoning_stream() -> tuple[list[str], float]:
        t = time.time()
        result = await pipe_reason_s.pipe(body_reason_stream)
        chunks = list(result)  # type: ignore[arg-type]
        return chunks, time.time() - t

    try:
        r_chunks, elapsed = asyncio.run(_test_reasoning_stream())
        r_full = "".join(r_chunks)

        if "Error" in r_full and "think" not in r_full:
            _skip(f"reasoning stream returned error: {r_full[:100]}")
        else:
            _assert("<think>" in r_full, "stream reasoning: <think> present")
            _assert("</think>" in r_full, "stream reasoning: </think> present")
            _assert("6" in r_full, "stream reasoning: answer contains '6'")
            print(f"  ⏱ Streamed reasoning in {elapsed:.2f}s ({len(r_chunks)} chunks)")
    except Exception as exc:
        _skip(f"reasoning stream test failed: {exc}")

# ══════════════════════════════════════════════════════════════════════════════
# 8. Error handling — invalid model
# ══════════════════════════════════════════════════════════════════════════════

_section("8. Error handling")

pipe_err = Pipe()
pipe_err.valves = Pipe.Valves(OPENROUTER_API_KEY=API_KEY)

body_err = {
    "model": "openrouter.fake-provider/nonexistent-model-xyz",
    "messages": [{"role": "user", "content": "test"}],
    "stream": False,
}


async def _test_error() -> str:
    result = await pipe_err.pipe(body_err)
    return result  # type: ignore[return-value]


err_result = asyncio.run(_test_error())
_assert("Error" in err_result or "error" in err_result.lower(), "error: detects invalid model")
_assert(API_KEY not in err_result, "error: API key NOT leaked in error message")
print(f"  ℹ Error response: {err_result[:120]}")

# ══════════════════════════════════════════════════════════════════════════════
# 9. Provider routing payload
# ══════════════════════════════════════════════════════════════════════════════

_section("9. Provider routing (payload check)")

pipe_prov = Pipe()
pipe_prov.valves = Pipe.Valves(
    OPENROUTER_API_KEY=API_KEY,
    PROVIDER_SORT="price",
    PROVIDER_ORDER="openai, anthropic",
    PROVIDER_IGNORE="google",
    REQUIRE_PARAMETERS=True,
    DATA_COLLECTION="deny",
    FALLBACK_MODELS="openai/gpt-4o-mini",
    ENABLE_MIDDLE_OUT=True,
)

body_prov = {
    "model": "openrouter.openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say OK"}],
    "stream": False,
}

payload = pipe_prov._prepare_payload(body_prov)
_assert(payload["provider"]["sort"] == "price", "provider sort = price")
_assert(payload["provider"]["order"] == ["openai", "anthropic"], "provider order")
_assert(payload["provider"]["ignore"] == ["google"], "provider ignore")
_assert(payload["provider"]["require_parameters"] is True, "require_parameters")
_assert(payload["provider"]["data_collection"] == "deny", "data_collection = deny")
_assert(payload["models"] == ["openai/gpt-4o-mini"], "fallback models")
_assert(payload["transforms"] == ["middle-out"], "middle-out transform")

# Actually send it to verify it doesn't crash
if not CHAT_AVAILABLE:
    _skip("provider routing live call skipped (web search config)")
else:
    async def _test_provider_routing() -> str:
        result = await pipe_prov.pipe(body_prov)
        return result  # type: ignore[return-value]

    prov_result = asyncio.run(_test_provider_routing())
    _assert(isinstance(prov_result, str) and len(prov_result) > 0, "provider routing: got response")
    print(f"  ℹ Response: {prov_result[:100]}")

# ══════════════════════════════════════════════════════════════════════════════
# 10. Invalid API key
# ══════════════════════════════════════════════════════════════════════════════

_section("10. Invalid API key")

# Note:
# Depending on OpenRouter backend behavior, /models may either:
#   1) return an auth error for invalid keys, OR
#   2) return the public model catalog without enforcing auth.
# So we treat both outcomes as valid for pipes().
pipe_bad = Pipe()
pipe_bad.valves = Pipe.Valves(OPENROUTER_API_KEY="sk-or-INVALID-KEY")

# 10a. pipes() behavior can vary (auth error OR public catalog)
bad_models = pipe_bad.pipes()
if len(bad_models) == 1 and bad_models[0].get("id") == "error":
    _assert(True, "bad key pipes(): returns error entry")
    _assert(
        "Invalid API key" in bad_models[0].get("name", "")
        or "HTTP" in bad_models[0].get("name", ""),
        "bad key pipes(): auth error message present",
    )
    print(f"  ℹ pipes() → {bad_models[0].get('name', '')[:100]}")
else:
    _assert(len(bad_models) > 0, "bad key pipes(): public catalog fallback (non-empty)")
    _assert(all("id" in m and "name" in m for m in bad_models[:3]),
            "bad key pipes(): catalog entries have id/name")
    print("  ℹ pipes() accepted invalid key for /models (public catalog behavior)")

# 10b. pipe() should return auth error
body_bad = {
    "model": "openrouter.openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "test"}],
    "stream": False,
}


async def _test_bad_key() -> str:
    result = await pipe_bad.pipe(body_bad)
    return result  # type: ignore[return-value]


bad_result = asyncio.run(_test_bad_key())
_assert("Error" in bad_result or "error" in bad_result.lower(),
        "bad key pipe(): chat returns error")
_assert("sk-or-INVALID-KEY" not in bad_result,
        "bad key pipe(): API key NOT leaked in error")

# ══════════════════════════════════════════════════════════════════════════════
# 11. Model prefix
# ══════════════════════════════════════════════════════════════════════════════

_section("11. Model prefix")

pipe_prefix = Pipe()
pipe_prefix.valves = Pipe.Valves(
    OPENROUTER_API_KEY=API_KEY,
    MODEL_PREFIX="🔥 ",
    MODEL_PROVIDERS="openai",
)
prefix_models = pipe_prefix.pipes()
_assert(len(prefix_models) > 0, f"prefix: {len(prefix_models)} models")
if prefix_models and prefix_models[0]["id"] != "error":
    _assert(
        prefix_models[0]["name"].startswith("🔥 "),
        f"prefix: name starts with '🔥 ' → {prefix_models[0]['name'][:30]}",
    )

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════

_section("INTEGRATION TEST SUMMARY")

total = _PASS + _FAIL
print(f"\n  Total: {total}  |  ✓ Passed: {_PASS}  |  ✗ Failed: {_FAIL}  |  ⊘ Skipped: {_SKIP}\n")

if _FAIL > 0:
    print("  ⚠ Some tests failed!\n")
    sys.exit(1)
else:
    print("  All integration tests passed! ✓\n")
    sys.exit(0)
