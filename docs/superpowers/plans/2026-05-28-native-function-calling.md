# Native Function Calling + Remaining-Credit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native (model-side) function/tool calling — `pipe()` receives `__tools__`, forwards them to OpenRouter, runs the execute→re-request loop (parallel tool execution, streaming + non-streaming) — and add an opt-in OpenRouter remaining-credit footer.

**Architecture:** The loop is orchestrated in the already-`async` `pipe()`; transport stays sync `requests`. Tool callables (sync or async) are awaited at the `pipe()` level. A defensive guard keeps the existing non-tool path byte-for-byte unchanged when `__tools__` is absent. Credit is a separate cached `/credits` fetch appended to the response footer.

**Tech Stack:** Python 3, `requests`, `pydantic` v2, stdlib `asyncio` + `inspect` (new). Tests: hand-rolled `_assert`/`_section` harness in `test_pipe.py`, run `python test_pipe.py`. Lint: `python -m pyflakes openrouter_pipe.py`.

---

## Critical conventions (read first)

- **Tests are NOT pytest.** Append `_section("…")` + `_assert(cond, "msg")` blocks to `test_pipe.py`; run `python test_pipe.py`; it must end `All tests passed! ✓` with 0 failures. Symbols bind near the top as `Pipe = mod.Pipe`. **Baseline: 595 passed.**
- **Line numbers are APPROXIMATE.** Locate by name/signature.
- `pipe()` is `async` (line ~1069). Streaming returns either the sync generator `gen` or an async `_wrap_stream()` wrapper. Non-streaming returns a `str`.
- The request path already takes an explicit `valves` argument; the chat path uses `eff` (effective valves with per-user overrides). Keep using `valves`/`eff`, never `self.valves`, inside the chat path.
- Commit DIRECTLY to `main`. `git add` only the files each task names — never `git add -A` (untracked `.claude/`, `.swarm/`, `ruvector.db` must stay out).
- `cryptography` is installed in this dev env. Async tests use `asyncio.run(...)` (the test file already imports `asyncio`).

## Async test helper

Several tasks test `async` methods. Use a tiny runner in the test file (add once, in Task 3, right after the symbol bindings near the top, if not already present):

```python
def _run(coro):
    return asyncio.run(coro)
```

## File Structure

All code in `openrouter_pipe.py` (flat single-file pipe; follow that pattern — add methods to `Pipe`, do not create new modules). Docs in `CHANGELOG.md`/`README.md`/`TESTING.md`; manifest in `function.json`; tests in `test_pipe.py`.

---

## Task 1: Foundation — imports, constant, valves, credit cache

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append to `test_pipe.py`:

```python
# ── v1.8 foundation: tool + credit valves ──────────────────────────────────────

_section("v1.8 valves present")

_p18 = Pipe()
_assert(_p18.valves.MAX_TOOL_ITERATIONS == 5, "MAX_TOOL_ITERATIONS default 5")
_assert(_p18.valves.SHOW_REMAINING_CREDIT is False, "SHOW_REMAINING_CREDIT default False")
_uv18 = Pipe.UserValves()
_assert(_uv18.MAX_TOOL_ITERATIONS is None, "UserValves MAX_TOOL_ITERATIONS inherits (None)")
_assert(_uv18.SHOW_REMAINING_CREDIT is None, "UserValves SHOW_REMAINING_CREDIT inherits (None)")
_assert(isinstance(_p18._credit_cache, dict), "credit cache dict initialized")
_assert(mod._API_PATH_CREDITS == "/credits", "credits path constant")
```

- [ ] **Step 2: Run** `python test_pipe.py` → FAIL (`MAX_TOOL_ITERATIONS` missing, etc.).

- [ ] **Step 3: Add imports** — in the stdlib import block at the top of `openrouter_pipe.py`, add `import asyncio` and `import inspect` (keep alphabetical: `asyncio` before `base64`; `inspect` after `hashlib`). Result:

```python
import asyncio
import base64
import copy
import hashlib
import inspect
import json
import os
import random
import re
import time
import traceback
```

- [ ] **Step 4: Add the credits path constant** — next to the existing `_API_PATH_*` constants (search `_API_PATH_CHAT`), add:

```python
_API_PATH_CREDITS = "/credits"
```

- [ ] **Step 5: Add admin valves** — inside `class Valves`, immediately after the `COST_CURRENCY` field (before the `_validate_base_url` validator), add:

```python
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
```

- [ ] **Step 6: Add UserValves mirrors** — inside `class UserValves`, after `COST_CURRENCY: Optional[str] = None` (before the `_encrypt_user_api_key` validator), add:

```python
        MAX_TOOL_ITERATIONS: Optional[int] = Field(default=None, ge=1)
        SHOW_REMAINING_CREDIT: Optional[bool] = None
```

- [ ] **Step 7: Init credit cache** — in `__init__`, after the `self._zdr_model_ids` line, add:

```python
        # Per-key remaining-credit cache: {key_hash: (remaining_float, ts)}.
        # Keyed by the decrypted key's hash because per-user keys have per-key balances.
        self._credit_cache: dict = {}
```

- [ ] **Step 8: Run** `python test_pipe.py` → PASS (601). **Step 9: Lint** `python -m pyflakes openrouter_pipe.py` (note: `asyncio`/`inspect` are used in later tasks; if pyflakes flags them as unused now, complete Step of Task 3 before the lint gate, OR temporarily proceed — but prefer committing Task 1 together with their first use is NOT allowed since tasks are atomic; instead silence by ordering: it is acceptable for `import asyncio`/`import inspect` to be reported unused until Task 3. To keep pyflakes clean per-commit, add the imports in Task 3 instead.)

> **Resolution for Step 8/9:** Move `import asyncio` and `import inspect` OUT of this task. Add them in **Task 3 Step 3** (their first use). Task 1 adds only `base64`-independent items (constant, valves, cache). Re-run lint after this change — clean.

- [ ] **Step 10: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: add tool-iteration + remaining-credit valves and credit cache"
```

---

## Task 2: `_build_tools_payload`

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test**

```python
_section("_build_tools_payload")

_pbt = Pipe()
_assert(_pbt._build_tools_payload(None) is None, "None __tools__ → None")
_assert(_pbt._build_tools_payload({}) is None, "empty __tools__ → None")
_spec = {"name": "get_time", "description": "now", "parameters": {"type": "object", "properties": {}}}
_tp = _pbt._build_tools_payload({"get_time": {"spec": _spec, "callable": lambda: "x"}})
_assert(_tp == [{"type": "function", "function": _spec}], "spec wrapped as function tool")
_assert(_pbt._build_tools_payload({"bad": {"callable": lambda: 1}}) is None, "entry without spec skipped → None")
```

- [ ] **Step 2: Run** → FAIL (no `_build_tools_payload`).

- [ ] **Step 3: Implement** — add to `class Pipe` (place it just before `_non_stream_response`):

```python
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
```

- [ ] **Step 4: Run** → PASS (605). **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: build OpenRouter tools payload from OWUI __tools__"
```

---

## Task 3: `_execute_tool_calls` (parallel, sync+async callables)

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Add the async runner + failing test** — first add the `_run` helper near the top symbol bindings (if not present):

```python
def _run(coro):
    return asyncio.run(coro)
```

Then append:

```python
_section("_execute_tool_calls")

_pe = Pipe()

def _sync_tool(city=None):
    return f"weather in {city}: sunny"

async def _async_tool(x=0):
    return x + 1

_tools_map = {
    "weather": {"spec": {"name": "weather"}, "callable": _sync_tool},
    "inc": {"spec": {"name": "inc"}, "callable": _async_tool},
}

# two parallel calls, order preserved
_calls = [
    {"id": "c1", "type": "function", "function": {"name": "weather", "arguments": '{"city": "Rome"}'}},
    {"id": "c2", "type": "function", "function": {"name": "inc", "arguments": '{"x": 41}'}},
]
_res = _run(_pe._execute_tool_calls(_calls, _tools_map, None))
_assert(len(_res) == 2, "one tool message per call")
_assert(_res[0] == {"role": "tool", "tool_call_id": "c1", "content": "weather in Rome: sunny"}, "sync callable result")
_assert(_res[1]["tool_call_id"] == "c2" and _res[1]["content"] == "42", "async callable awaited, order preserved")

# unknown tool
_unk = _run(_pe._execute_tool_calls([{"id": "c3", "function": {"name": "nope", "arguments": "{}"}}], _tools_map, None))
_assert("Error" in _unk[0]["content"] and _unk[0]["tool_call_id"] == "c3", "unknown tool → error content, no raise")

# bad JSON args
_bad = _run(_pe._execute_tool_calls([{"id": "c4", "function": {"name": "weather", "arguments": "{not json"}}], _tools_map, None))
_assert("Error" in _bad[0]["content"], "invalid JSON args → error content")

# callable raises
def _boom():
    raise RuntimeError("kaboom")
_raise = _run(_pe._execute_tool_calls([{"id": "c5", "function": {"name": "b", "arguments": "{}"}}], {"b": {"spec": {}, "callable": _boom}}, None))
_assert("Error" in _raise[0]["content"] and "kaboom" in _raise[0]["content"], "callable exception → error content, no raise")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Add imports + implement** — in `openrouter_pipe.py` add `import asyncio` and `import inspect` to the stdlib block now (see Task 1 Step 3 for the alphabetized block). Then add to `class Pipe`:

```python
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
```

- [ ] **Step 4: Run** → PASS. **Step 5: Lint** clean (asyncio/inspect now used). **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: execute model tool_calls in parallel with graceful errors"
```

---

## Task 4: Non-stream tool loop + `_format_final_message` extraction + `pipe()` wiring

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

This task (a) extracts the non-stream formatting into a reusable method, (b) adds the non-stream tool loop, (c) wires `__tools__` into `pipe()`.

- [ ] **Step 1: Failing test**

```python
_section("non-stream tool loop")

class _FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def close(self): pass

_pl = Pipe()
_pl.valves.OPENROUTER_API_KEY = "sk-or-test"  # plaintext (no WEBUI_SECRET_KEY in this test)
_pl.valves.MAX_TOOL_ITERATIONS = 3

# round 1 returns a tool_call; round 2 returns final content
_round1 = {"choices": [{"message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "weather", "arguments": '{"city": "Rome"}'}}]}}]}
_round2 = {"choices": [{"message": {"role": "assistant", "content": "It is sunny in Rome."}}], "model": "x"}
_seq = [_FakeResp(_round1), _FakeResp(_round2)]

def _fake_retry(headers, payload, stream, valves):
    return _seq.pop(0)

_pl._retryable_request = _fake_retry  # type: ignore
_tools_map2 = {"weather": {"spec": {"name": "weather"}, "callable": lambda city=None: f"sunny {city}"}}
_payload = {"model": "x", "messages": [{"role": "user", "content": "weather?"}], "tools": _pl._build_tools_payload(_tools_map2)}
_out = _run(_pl._run_tools_nonstream({}, _payload, _pl.valves, _tools_map2, None))
_assert("It is sunny in Rome." in _out, "final content returned after tool round")
# messages now contain the assistant tool_call message + the tool result
_roles = [m.get("role") for m in _payload["messages"]]
_assert("tool" in _roles and "assistant" in _roles, "assistant + tool messages appended")
_assert(any(m.get("tool_call_id") == "c1" for m in _payload["messages"]), "tool result carries tool_call_id")

# cap: every round asks for tools → stops with note
_pl.valves.MAX_TOOL_ITERATIONS = 2
_loopres = [_FakeResp(_round1) for _ in range(5)]
def _always_tools(headers, payload, stream, valves):
    return _loopres.pop(0)
_pl._retryable_request = _always_tools  # type: ignore
_payload2 = {"model": "x", "messages": [{"role": "user", "content": "go"}], "tools": _pl._build_tools_payload(_tools_map2)}
_capout = _run(_pl._run_tools_nonstream({}, _payload2, _pl.valves, _tools_map2, None))
_assert("MAX_TOOL_ITERATIONS" in _capout or "tool" in _capout.lower(), "iteration cap produces a note")
```

- [ ] **Step 2: Run** → FAIL (`_run_tools_nonstream`, `_format_final_message` missing).

- [ ] **Step 3: Extract `_format_final_message`** — in `_non_stream_response`, replace the block from `choice = res["choices"][0]` through `return "".join(final_parts)` (the formatting tail) with a call:

```python
            return self._format_final_message(res, payload, valves)
```

Then add the new method (place it just before `_non_stream_response`). It is the extracted body, verbatim, plus a credit hook placeholder that Task 6 fills (for now it ends after generation-id):

```python
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
            final_parts.append(f"\n\n---\n*Responded by: {actual_model}*")

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

        return "".join(final_parts)
```

After extraction, `_non_stream_response` keeps its `try/except` wrapper, the body-error check (`if "error" in res and not res.get("choices")`), and now ends with `return self._format_final_message(res, payload, valves)`.

- [ ] **Step 4: Add the non-stream tool loop**

```python
    async def _run_tools_nonstream(self, headers, payload, valves, __tools__, __event_emitter__) -> str:
        """Drive the non-streaming native-tool loop: request → execute → repeat."""
        max_iter = max(int(getattr(valves, "MAX_TOOL_ITERATIONS", 5) or 5), 1)
        for _ in range(max_iter):
            try:
                resp = self._retryable_request(headers, payload, stream=False, valves=valves)
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
                return self._format_final_message(res, payload, valves)

            tool_msgs = await self._execute_tool_calls(tool_calls, __tools__, __event_emitter__)
            payload.setdefault("messages", []).append(message)
            payload["messages"].extend(tool_msgs)

        # Cap reached while still requesting tools: one last call, then a note.
        try:
            resp = self._retryable_request(headers, payload, stream=False, valves=valves)
            try:
                res = resp.json()
            finally:
                if hasattr(resp, "close"):
                    resp.close()
        except Exception as exc:  # pragma: no cover
            return f"OpenRouter Error: {exc}"
        final = self._format_final_message(res, payload, valves)
        return final + "\n\n---\n*Tool calling stopped: reached MAX_TOOL_ITERATIONS.*"
```

- [ ] **Step 5: Wire `pipe()`** — change the signature to add `__tools__`:

```python
    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __tools__: Optional[dict] = None,
    ) -> Union[str, Generator[str, None, None], AsyncGenerator[str, None]]:
```

After `payload = self._prepare_payload(body, eff)` and `headers = ...`, insert:

```python
        tools_payload = self._build_tools_payload(__tools__)
        if tools_payload:
            payload["tools"] = tools_payload
        stream = body.get("stream", False)

        if tools_payload and not stream:
            result = await self._run_tools_nonstream(headers, payload, eff, __tools__, __event_emitter__)
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "", "done": True}})
            return result
```

Keep the existing `stream = body.get("stream", False)` line only once — if you add it above, remove the later duplicate. The existing streaming branch and the existing non-stream `result = self._non_stream_response(...)` remain as the fallback for the no-tools case. (Streaming WITH tools is wired in Task 5; until then, streaming + tools falls through to the plain stream path, which simply won't execute tools — acceptable mid-plan, fixed in Task 5.)

- [ ] **Step 6: Run** `python test_pipe.py` → PASS (existing non-stream tests still green after extraction + new tool-loop tests pass). **Step 7: Lint** clean. **Step 8: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: non-streaming native tool-calling loop"
```

---

## Task 5: Streaming tool loop (highest-risk — pin with tests)

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

> **Implementer note:** This is the delicate task — async generator driving per-round sync streaming with tool_call delta accumulation. The tests below are the behavior contract. Implement the reference code, run the tests, and iterate until green. If the async-generator wiring fights you after a couple of honest attempts, report DONE_WITH_CONCERNS or BLOCKED with specifics rather than guessing.

- [ ] **Step 1: Failing test** — these tests drive the round helper and the orchestrator with a fake streaming transport.

```python
_section("streaming tool loop")

class _FakeStream:
    """Mimics requests.Response.iter_lines() over preset SSE byte lines."""
    def __init__(self, lines): self._lines = lines
    def iter_lines(self): return iter(self._lines)
    def close(self): pass

def _sse(d):
    return ("data: " + json.dumps(d)).encode("utf-8")

_ps = Pipe()
_ps.valves.OPENROUTER_API_KEY = "sk-or-test"
_ps.valves.MAX_TOOL_ITERATIONS = 3

# Round 1: tool_call assembled across two deltas; Round 2: content answer.
_r1 = [
    _sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function", "function": {"name": "weather", "arguments": '{"ci'}}]}}]}),
    _sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ty": "Rome"}'}}]}, "finish_reason": "tool_calls"}]}),
    b"data: [DONE]",
]
_r2 = [
    _sse({"choices": [{"delta": {"content": "Sunny "}}]}),
    _sse({"choices": [{"delta": {"content": "in Rome."}}]}),
    b"data: [DONE]",
]
_streams = [_FakeStream(_r1), _FakeStream(_r2)]
def _fake_retry_stream(headers, payload, stream, valves):
    return _streams.pop(0)
_ps._retryable_request = _fake_retry_stream  # type: ignore

_tools_map3 = {"weather": {"spec": {"name": "weather"}, "callable": lambda city=None: f"sunny {city}"}}
_payload_s = {"model": "x", "messages": [{"role": "user", "content": "weather?"}], "tools": _ps._build_tools_payload(_tools_map3)}

async def _collect():
    out = []
    async for piece in _ps._run_tools_stream({}, _payload_s, _ps.valves, _tools_map3, None):
        out.append(piece)
    return "".join(out)

_streamed = _run(_collect())
_assert("Sunny in Rome." in _streamed, "final answer streamed after tool round")
_assert("c1" not in _streamed, "raw tool_call id not leaked to user output")
_roles_s = [m.get("role") for m in _payload_s["messages"]]
_assert("tool" in _roles_s, "tool result appended to messages during stream loop")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement the round helper** — a sync generator that yields user content and records round state. Add to `class Pipe`:

```python
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

                # Accumulate tool_call deltas by index.
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
```

- [ ] **Step 4: Implement the orchestrator**

```python
    async def _run_tools_stream(self, headers, payload, valves, __tools__, __event_emitter__):
        """Async generator: stream rounds, executing tools between them."""
        max_iter = max(int(getattr(valves, "MAX_TOOL_ITERATIONS", 5) or 5), 1)
        for _ in range(max_iter):
            state: dict = {}
            for piece in self._stream_one_round(headers, payload, valves, state):
                yield piece
            if state.get("error"):
                return
            tool_calls = state.get("tool_calls")
            if not tool_calls:
                yield self._stream_footer(state, valves)
                return
            tool_msgs = await self._execute_tool_calls(tool_calls, __tools__, __event_emitter__)
            assistant_msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            payload.setdefault("messages", []).append(assistant_msg)
            payload["messages"].extend(tool_msgs)

        # Cap reached: one final content round.
        state = {}
        for piece in self._stream_one_round(headers, payload, valves, state):
            yield piece
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
        return "".join(parts)
```

- [ ] **Step 5: Wire `pipe()` streaming-with-tools** — in the `if stream:` branch, BEFORE building the plain `gen`, add:

```python
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
```

Place this so it takes precedence over the existing plain-stream block (which stays for the no-tools case).

- [ ] **Step 6: Run** → PASS. **Step 7: Lint** clean. **Step 8: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: streaming native tool-calling loop"
```

---

## Task 6: Remaining-credit footer

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test**

```python
_section("remaining credit")

_pc = Pipe()
_pc.valves.OPENROUTER_API_KEY = "sk-or-test"
_pc.valves.SHOW_REMAINING_CREDIT = True

class _CredResp:
    status_code = 200
    def json(self): return {"data": {"total_credits": 10.0, "total_usage": 3.5}}
    def raise_for_status(self): pass
    def close(self): pass

_calls = {"n": 0}
def _fake_get(url, headers=None, timeout=None, allow_redirects=None, params=None):
    _calls["n"] += 1
    return _CredResp()
_pc._session.get = _fake_get  # type: ignore

_bal = _pc._fetch_credit_balance(_pc.valves)
_assert(abs(_bal - 6.5) < 1e-9, "remaining = total_credits - total_usage")
_bal2 = _pc._fetch_credit_balance(_pc.valves)
_assert(_calls["n"] == 1, "second call within TTL served from cache (no refetch)")
_line = _pc._format_credit_info(6.5, "USD")
_assert("6.5" in _line and "credit" in _line.lower(), "credit line formatted")

# failure → None, omitted
def _boom_get(*a, **k):
    raise RuntimeError("net down")
_pc2 = Pipe(); _pc2.valves.OPENROUTER_API_KEY = "sk-or-x"
_pc2._session.get = _boom_get  # type: ignore
_assert(_pc2._fetch_credit_balance(_pc2.valves) is None, "fetch failure → None")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement fetch + cache + format** — add to `class Pipe`:

```python
    _CREDIT_TTL = 60.0

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
            try:
                resp.close()
            except Exception:
                pass
        self._credit_cache[key_hash] = (remaining, time.monotonic())
        return remaining

    @staticmethod
    def _format_credit_info(remaining: Optional[float], currency: str = "USD") -> str:
        """Format the remaining-credit footer line."""
        if remaining is None:
            return ""
        symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
        return f"\n\n---\n*OpenRouter credit remaining: {symbol}{remaining:.2f}*"
```

- [ ] **Step 4: Wire into both footers.** In `_format_final_message`, after the generation-id block and before `return "".join(final_parts)`:

```python
        if valves.SHOW_REMAINING_CREDIT:
            credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
            if credit_line:
                final_parts.append(credit_line)
```

In `_stream_footer` (Task 5), after the generation-id block and before `return "".join(parts)`:

```python
        if valves.SHOW_REMAINING_CREDIT:
            credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
            if credit_line:
                parts.append(credit_line)
```

- [ ] **Step 5: Run** → PASS. **Step 6: Lint** clean. **Step 7: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: opt-in OpenRouter remaining-credit footer (cached /credits)"
```

---

## Task 7: Version 1.8.0 + docstring + function.json

**Files:** Modify `openrouter_pipe.py`, `function.json`.

- [ ] **Step 1:** In `openrouter_pipe.py` header, change `version: 1.7.0` → `version: 1.8.0`.
- [ ] **Step 2:** Append to the module `description:` line: ` Native function/tool calling (parallel execution, streaming + non-streaming) with a tool-iteration cap, and an opt-in OpenRouter remaining-credit footer.`
- [ ] **Step 3:** In `function.json`: set `"version": "1.8.0"` and append the same sentence to the `description`. Optionally add `"tool-calling"` to the `tags` array.
- [ ] **Step 4:** Verify: `grep -rn "1\.7\.0" openrouter_pipe.py function.json` → no version matches; `python -c "import json; json.load(open('function.json'))"` → valid.
- [ ] **Step 5:** `python test_pipe.py` → 0 failures; `python -m pyflakes openrouter_pipe.py` → clean.
- [ ] **Step 6: Commit**

```bash
git add openrouter_pipe.py function.json
git commit -m "chore: bump to v1.8.0, document tool calling + credit footer"
```

---

## Task 8: Documentation

**Files:** Modify `CHANGELOG.md`, `README.md`, `TESTING.md`.

- [ ] **Step 1: CHANGELOG** — under `[Unreleased] → ### Added`, add:

```markdown
- **Native function/tool calling** — `pipe()` now accepts OWUI `__tools__`, forwards them to OpenRouter, and runs the execute→re-request loop in both streaming and non-streaming modes. Tool calls execute in parallel; sync and async tool callables are supported; tool errors are fed back to the model rather than crashing the turn. New `MAX_TOOL_ITERATIONS` valve (default 5) caps runaway loops. Prompt-based tool mode (handled by OWUI) is unaffected.
- **Remaining-credit footer** — opt-in `SHOW_REMAINING_CREDIT` valve appends your remaining OpenRouter credit after the cost line, via a cached (~60s, per-key) `GET /credits` call. Independent of `SHOW_COST_INFO`; fails silently (line omitted) if the balance can't be fetched.
```

- [ ] **Step 2: README** — add a `### Tool calling (native function calling)` subsection near the Configuration section documenting: requires OWUI "Function Calling: Native"; the pipe runs the loop; `MAX_TOOL_ITERATIONS`; parallel execution; streaming + non-streaming. Add `MAX_TOOL_ITERATIONS` and `SHOW_REMAINING_CREDIT` rows to the valve tables (Advanced / Cost Display). Add a sentence to the credit/cost area about `SHOW_REMAINING_CREDIT`.
- [ ] **Step 3: TESTING** — add a manual section `## 25. Native tool calling & remaining credit (v1.8)` with rows: native tool round executes a tool and returns the final answer; multiple parallel tools; streaming tool call; `MAX_TOOL_ITERATIONS` cap; `SHOW_REMAINING_CREDIT` shows credit after cost. Bump the `python test_pipe.py` count in the checklist to the new total.
- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md TESTING.md
git commit -m "docs: document native tool calling + remaining-credit footer"
```

---

## Task 9: Final verification

- [ ] **Step 1:** `python test_pipe.py` → note the new total, 0 failures.
- [ ] **Step 2:** `python -m pyflakes openrouter_pipe.py test_pipe.py` → clean.
- [ ] **Step 3:** Regression smoke — confirm a no-tools request is unchanged: a `pipe()` call with `__tools__=None` must take the existing non-tool path (the existing streaming/non-streaming tests already assert this; verify they pass).
- [ ] **Step 4:** `git status` → working tree clean of intended changes (untracked tooling dirs may remain; do not commit them).

---

## Self-review notes (applied)

- **Spec coverage:** `__tools__` contract + `pipe()` param (T4/T5), `_build_tools_payload` (T2), parallel `_execute_tool_calls` w/ sync+async + error handling (T3), non-stream loop (T4), streaming loop + delta accumulation (T5), `MAX_TOOL_ITERATIONS` (T1, enforced T4/T5), credit fetch/cache/format/valve (T1/T6), version/docstring/function.json (T7), docs (T8), defensive no-`__tools__` path (T4 wiring + T9 regression). All spec sections map to a task.
- **Naming consistency:** `_build_tools_payload`, `_execute_tool_calls`, `_run_tools_nonstream`, `_run_tools_stream`, `_stream_one_round`, `_stream_footer`, `_format_final_message`, `_fetch_credit_balance`, `_format_credit_info`, `_credit_cache`, `_API_PATH_CREDITS`, valves `MAX_TOOL_ITERATIONS`/`SHOW_REMAINING_CREDIT` — used identically across tasks.
- **Import ordering correction:** `asyncio`/`inspect` are added in Task 3 (their first use) so each commit stays pyflakes-clean (Task 1 Step 9 note).
- **Risk:** Task 5 (streaming orchestrator) is the delicate one; its tests are the behavior contract and the implementer iterates to green, escalating if blocked.
- **DRY:** `_format_final_message` is extracted so the plain non-stream path and the tool-loop final round share formatting; `_stream_footer` shared by streaming tool path.
