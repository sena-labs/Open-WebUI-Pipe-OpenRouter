# Native Function Calling + Remaining-Credit Display — Design Spec

- **Date:** 2026-05-28
- **Target version:** 1.7.0 → 1.8.0 (minor, backward-compatible)
- **Goal:** Add native (model-side) function/tool calling so the pipe executes OpenWebUI tools through OpenRouter, and surface the remaining OpenRouter credit in the response footer. Both move the pipe toward being the reference OpenWebUI OpenRouter pipe.

## Problem

Today the pipe forwards `tools` if OWUI puts them in the request body, but it never receives `__tools__`, never inspects `tool_calls` in the response, and never runs the execute→re-request loop. So OWUI's **native** function-calling mode does nothing useful (only the prompt-based mode, handled entirely by OWUI middleware, works). To be a reference pipe it must support native tool calling end-to-end.

Separately, users want to see their **remaining OpenRouter credit** after each response (alongside the existing per-response cost), which the pipe cannot currently show.

These are two independent features shipped together; each gets its own implementation task.

## Decisions (locked)

- **Scope:** full native function-calling loop (not just pass-through).
- **Streaming:** supported in both streaming and non-streaming paths.
- **Tool execution:** parallel (`asyncio.gather`), result-message order preserved.
- **Credit display:** opt-in via a dedicated valve, independent of `SHOW_COST_INFO`, appended right after the cost footer.
- **Lean preserved:** only stdlib additions (`asyncio`, `inspect`); no new third-party deps. Transport stays sync `requests`; the loop is orchestrated in the already-`async` `pipe()`.

## Architecture — Feature 1: Native function calling

### OWUI contract (assumption, validate in a live OWUI)

In *Function Calling: Native* mode, OWUI passes `__tools__` to the pipe:

```python
__tools__ = {
  "tool_name": {
    "spec": { "name": ..., "description": ..., "parameters": {...} },  # OpenAI function schema
    "callable": <fn(**kwargs)>,   # may be sync or async (coroutine fn)
    "tool_id": "...",
  }, ...
}
```

The design is **defensive**: if `__tools__` is absent/empty, the current code path runs unchanged (no regression). If the shape differs across OWUI versions, missing keys degrade gracefully.

### `pipe()` signature

`async def pipe(self, body, __user__=None, __event_emitter__=None, __tools__=None)` — `__tools__` is a new keyword arg defaulting to `None`.

### Flow (both modes)

1. Compute `eff` (effective valves) as today. Build `payload`/`headers` as today.
2. `tools = self._build_tools_payload(__tools__)`. If `tools` is falsy → run the existing non-tool path (unchanged). Otherwise set `payload["tools"] = tools` and enter the tool loop.
3. Tool loop, capped at `eff.MAX_TOOL_ITERATIONS` rounds:
   - Send a round to OpenRouter (reusing `_retryable_request` + `eff`).
   - If the assistant message has no `tool_calls` (or `finish_reason != "tool_calls"`) → this is the final answer; format/stream it and stop.
   - Else: emit a `🔧 Calling {name}…` status per call, execute all tool calls (parallel), append the assistant message (with `tool_calls`) and one `{"role":"tool","tool_call_id":id,"content":str(result)}` per call to `payload["messages"]`, then loop.
   - If the cap is hit while still requesting tools → return the last content plus a short "max tool iterations reached" note.

### Non-streaming tool loop

A helper drives rounds synchronously (reusing `_retryable_request`) and `await`s tool execution between rounds. The final round is formatted exactly as today (content / citations / cost / generation-id). Returns a string.

### Streaming tool loop

Returns an **async generator** (OWUI consumes it). Structure:

- `_stream_one_round(headers, payload, valves, state)` — a sync generator that yields user-facing **content** deltas as they arrive, while accumulating into the passed-in mutable `state`: `tool_calls` (assembled by `index` — concatenate `arguments` fragments, capture `id`+`name` on first delta), `usage`, `generation_id`, `citations`, `finish_reason`.
- The async orchestrator yields content deltas to the user, then inspects `state["tool_calls"]`: if present and under the cap → `await` parallel tool execution, append assistant + tool messages, run the next round; else → emit the final footer (citations / cost / credit) and stop.
- Tool-call rounds normally carry no user-visible content, so only status events surface; the final (answer) round streams the content.

### New components (methods on `Pipe`, flat file)

- `_build_tools_payload(__tools__) -> Optional[list]` — `[{"type":"function","function": v["spec"]} for v in __tools__.values()]`, or `None` when empty/absent.
- `async _execute_tool_calls(tool_calls, __tools__, __event_emitter__) -> list[dict]` — parallel via `asyncio.gather`; each task parses `arguments` JSON, resolves the callable, invokes it (awaiting if it returns an awaitable — supports sync and async callables), and wraps the result/error in a `role:"tool"` message. Order preserved by `gather`.
- non-streaming tool driver + streaming round helper/orchestrator as above.

### Error handling (tool loop)

- Invalid JSON `arguments`, unknown tool name, or a callable that raises → the error string is returned as the tool message content so the model can recover; the loop continues, no crash.
- Iteration cap reached → return partial content + a note.
- `__tools__` absent/empty → existing path, zero behavior change.

### Valve

- `MAX_TOOL_ITERATIONS: int = 5` (admin `Valves`, `ge=1`; mirrored in `UserValves` as `Optional[int] = None`). Prevents infinite tool loops.

## Architecture — Feature 2: Remaining-credit display

Independent of tool calling; separate implementation task.

- **Endpoint:** `GET {_base}/credits` → `{"data": {"total_credits": float, "total_usage": float}}`. **remaining = total_credits − total_usage.** Auth via the decrypted key; `allow_redirects=False`; bounded timeout. New constant `_API_PATH_CREDITS = "/credits"`.
- **Helper:** `_fetch_credit_balance(valves) -> Optional[float]` — fetches and computes remaining; returns `None` on any failure (network, non-200, missing fields) so the credit line is simply omitted, never crashing a response.
- **Cache:** an instance dict `self._credit_cache: {key_hash: (remaining, ts)}` with a ~60s TTL. Keyed by the SHA-256 hash of the *decrypted* key because per-user `UserValves` keys have per-key balances; this avoids a `/credits` call on every response.
- **Formatting:** `_format_credit_info(remaining, currency) -> str` → a markdown line like `*OpenRouter credit remaining: $12.34*`, appended right after the cost footer in both the non-streaming result and the streaming final-round footer.
- **Valve:** `SHOW_REMAINING_CREDIT: bool = False` (admin `Valves`; mirrored in `UserValves`). Independent of `SHOW_COST_INFO` because the credit requires an extra `/credits` request, so it is opt-in on its own.

## Data flow (tool round, non-stream)

```
pipe(body, __user__, __event_emitter__, __tools__)
  eff = _effective_valves(__user__)
  payload = _prepare_payload(body, eff); payload["tools"] = _build_tools_payload(__tools__)
  loop up to eff.MAX_TOOL_ITERATIONS:
     res = _retryable_request(headers, payload, stream=False, valves=eff).json()
     msg = res.choices[0].message
     if not msg.tool_calls: return format(res, eff)   # + credit if eff.SHOW_REMAINING_CREDIT
     tool_msgs = await _execute_tool_calls(msg.tool_calls, __tools__, emitter)   # parallel
     payload.messages += [msg, *tool_msgs]
```

## Testing (`_assert`/`_section` harness)

Function calling:
- `_build_tools_payload`: empty/None → None; specs → correct `{"type":"function","function":...}` list.
- `_execute_tool_calls`: callable invoked with parsed args; result wrapped in `role:"tool"` message with correct `tool_call_id`; multiple calls run and all results returned in order; sync and async callables both supported; invalid-JSON args → error content, no raise; unknown tool name → error content.
- non-stream loop: round 1 returns `tool_calls`, round 2 returns final content (mock `_retryable_request`); assistant + tool messages appended in order; iteration cap respected (stops, returns note).
- streaming: `tool_calls` deltas accumulated across chunks by index → reconstructed call; final round streams content; tool round surfaces no content.
- `__tools__=None` → behavior identical to pre-feature (regression guard).

Credit:
- `_fetch_credit_balance`: parses `total_credits-total_usage`; returns None on non-200/missing fields/exception (mock the session).
- cache: second call within TTL does not refetch (mock asserts single request); different key-hash → separate entry.
- `_format_credit_info`: formats the line; appended only when `SHOW_REMAINING_CREDIT` is on.

Lint: pyflakes clean. Full suite green.

## Scope / files

- `openrouter_pipe.py` — `pipe()` signature + tool branch, `_build_tools_payload`, `_execute_tool_calls`, non-stream tool driver, streaming round helper + orchestrator, `_fetch_credit_balance`/`_format_credit_info` + cache, valves (`MAX_TOOL_ITERATIONS`, `SHOW_REMAINING_CREDIT`) + `UserValves` mirror, imports (`asyncio`, `inspect`), `_API_PATH_CREDITS`, version → 1.8.0, module docstring.
- `function.json` — version + description mirror.
- `test_pipe.py` — new sections above.
- `CHANGELOG.md`, `README.md`, `TESTING.md` — document both features.
- `requirements.txt` — unchanged.

## Out of scope (YAGNI)

- Cumulative cost across tool rounds (show final-round usage as today).
- Streaming the tool-call *arguments* to the user (only status events during tool rounds).
- Tool-result caching, retries on tool callables (OWUI owns the tool implementations).
- Credit auto-refresh/alerts; only an on-demand cached fetch when the valve is on.

## Risks

- The `__tools__` contract is OWUI-version-dependent and not testable here — design defensively and validate in a live OWUI before release.
- Streaming multi-round orchestration (delta accumulation + re-stream between tool rounds) is the most delicate part; isolate the accumulation in `_stream_one_round` and cover it with unit tests.
- Blocking sync `_retryable_request` inside `async pipe()` is consistent with the current non-stream path; acceptable, not a regression.
