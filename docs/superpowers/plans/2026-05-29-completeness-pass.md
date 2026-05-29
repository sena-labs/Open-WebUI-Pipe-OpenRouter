# Completeness Pass (audit punch-list) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the audited gaps to make the pipe reference-complete: fix 2 real defects, harden security, correct docs, add high-value API surface + robustness, and fill test gaps.

**Architecture:** Surgical fixes to the single-file `openrouter_pipe.py` + `integration_test.py` + docs. One behavior item (non-blocking retry sleeps) touches the async/sync boundary via stdlib `asyncio.to_thread` — no new deps, transport stays sync `requests`.

**Tech Stack:** Python 3, `requests`, `pydantic`, stdlib. Tests: `_assert`/`_section` harness, `python test_pipe.py`. Lint: `python -m pyflakes openrouter_pipe.py`.

---

## Conventions (read first)

- ONE file `openrouter_pipe.py` (v1.8.1, ~2400 lines). Line numbers APPROXIMATE — locate by name.
- Tests NOT pytest. `python test_pipe.py` must end `All tests passed! ✓`, 0 failures. **Baseline: 660 passed.** `Pipe = mod.Pipe`, `mod.requests`, `mod.time`; `patch` imported; `_FakeHTTPResp`/`_script_post` scaffolding exist.
- Lint clean each commit. Commit to `main`; `git add` by explicit filename (never `-A`; tooling dirs + any `LICENSE` working-tree edit stay out).
- Tasks are sequenced P0 → P1 → P2; each is independently committable + green.

---

## Task 1 (P0): Fix broken `integration_test.py` call signatures

`integration_test.py` predates the `valves` threading (v1.7) + tool/credit work; several pipe-method calls now have wrong signatures (e.g. `_prepare_payload(body)` → TypeError; method is `(body, valves)`).

**Files:** Modify `integration_test.py`.

- [ ] **Step 1: Find every stale call.** Run: `grep -nE "_prepare_payload\(|_build_headers\(|_non_stream_response\(|_stream_response\(|_retryable_request\(|_format_http_error\(|_resolve_referer\(|_inject_cache_control\(|_build_web_search_plugin\(" integration_test.py`
- [ ] **Step 2:** For each call, add the now-required `valves` argument using the test pipe's own valves. Examples:
  - `pipe._prepare_payload(body)` → `pipe._prepare_payload(body, pipe.valves)`
  - `pipe._build_headers(...)` → `pipe._build_headers(..., valves=pipe.valves)`
  - `pipe._non_stream_response(h, p)` → `pipe._non_stream_response(h, p, pipe.valves)`
  - `pipe._resolve_referer()` → `pipe._resolve_referer(pipe.valves)`
  - `pipe._build_web_search_plugin()` → `pipe._build_web_search_plugin(pipe.valves)`
  - `pipe._inject_cache_control(p)` → `pipe._inject_cache_control(p, pipe.valves)`
  Use the SAME pipe instance's `.valves` (behavior preserved). Update the module docstring version `v1.3.0` → `v1.8.2`.
- [ ] **Step 3:** Run `python integration_test.py` if it can run offline; if it requires a live `OPENROUTER_API_KEY`, instead do a syntax+import check: `python -c "import ast; ast.parse(open('integration_test.py').read()); print('parse ok')"` and verify by reading that no remaining call omits `valves`. Note in the report whether a live run was possible.
- [ ] **Step 4: Commit**

```bash
git add integration_test.py
git commit -m "fix: update integration_test calls for valves-threaded signatures"
```

---

## Task 2 (P0): Credit footer on plain stream + non-stream cap-note guard

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("credit footer on plain streaming + cap-note guard")

# plain streaming path emits the credit footer when enabled
_pcs = Pipe(); _pcs.valves.OPENROUTER_API_KEY = "sk-or-test"
_pcs.valves.SHOW_REMAINING_CREDIT = True
_pcs._fetch_credit_balance = lambda valves: 4.25  # type: ignore
_pcs._script = [_FakeStream([b"data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]}).encode(), b"data: [DONE]"])]
_pcs._retryable_request = lambda headers, payload, stream, valves: _pcs._script.pop(0)  # type: ignore
_out_cs = "".join(_pcs._stream_response({}, {"model": "x"}, _pcs.valves))
_assert("credit remaining" in _out_cs.lower(), "plain stream shows credit footer when enabled")

# non-stream cap note NOT appended to an error string
_pcn = Pipe(); _pcn.valves.OPENROUTER_API_KEY = "sk-or-test"; _pcn.valves.MAX_TOOL_ITERATIONS = 1
_errbody = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": "{}"}}]}}]}
_errfinal = {"error": {"message": "boom"}}
_seqn = [_FakeResp(_errbody), _FakeResp(_errfinal)] if "_FakeResp" in dir() else None
```

NOTE: `_FakeStream` is defined in the streaming-tool-loop test section; `_FakeResp` in the non-stream-tool section — reuse them. If a name isn't in scope at this point in the file, move this new `_section` to AFTER those sections, or re-bind locally. Keep the cap-note assertion focused:

```python
_pcn = Pipe(); _pcn.valves.OPENROUTER_API_KEY = "sk-or-test"; _pcn.valves.MAX_TOOL_ITERATIONS = 1
class _CapResp:
    def __init__(s, body): s._b = body
    def json(s): return s._b
    def close(s): pass
_tc = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": "{}"}}]}}]}
_seq = [_CapResp(_tc), _CapResp({"error": {"message": "boom"}})]
_pcn._retryable_request = lambda headers, payload, stream, valves: _seq.pop(0)  # type: ignore
_capout = _run(_pcn._run_tools_nonstream({}, {"model": "x", "messages": []}, _pcn.valves, {"t": {"spec": {}, "callable": lambda: "ok"}}, None))
_assert(_capout.startswith("OpenRouter Error:"), "cap-exit error returns the error string")
_assert("MAX_TOOL_ITERATIONS" not in _capout, "cap note NOT appended to an error string")
```

- [ ] **Step 2: Run** → FAIL (plain stream lacks credit; cap note appended to error).

- [ ] **Step 3: Add credit to `_stream_response`.** In `_stream_response`, after the `SHOW_GENERATION_ID` yield block (ends ~line 2283) and before the `except` clauses, add:

```python
            if valves.SHOW_REMAINING_CREDIT:
                credit_line = self._format_credit_info(self._fetch_credit_balance(valves), valves.COST_CURRENCY)
                if credit_line:
                    yield credit_line
```

- [ ] **Step 4: Guard the non-stream cap note.** In `_run_tools_nonstream`, change the final two lines (the cap-exit) from:

```python
        final = self._format_final_message(res, payload, valves)
        return final + "\n\n---\n*Tool calling stopped: reached MAX_TOOL_ITERATIONS.*"
```
to:
```python
        final = self._format_final_message(res, payload, valves)
        if final.startswith("OpenRouter Error:"):
            return final
        return final + "\n\n---\n*Tool calling stopped: reached MAX_TOOL_ITERATIONS.*"
```

- [ ] **Step 5: Run** → PASS (note total). **Step 6: Lint** clean. **Step 7: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "fix: emit credit footer on plain stream; don't tag cap note onto errors"
```

---

## Task 3 (P0): Non-blocking retry sleeps (event loop) — HIGH RISK

`_retryable_request` does sync `time.sleep` (up to 60s with Retry-After) while reachable from the async `pipe()` → freezes the loop for all users. Fix: offload blocking work to a worker thread via stdlib `asyncio.to_thread` at the async boundaries; transport stays sync.

> **Implementer note:** This is the delicate task. Make the tests pass, iterate, and if the async/sync wiring fights you after a couple of honest attempts, report BLOCKED with specifics.

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("retry sleep does not block the event loop")

import threading as _threading
_pb = Pipe(); _pb.valves.OPENROUTER_API_KEY = "sk-or-test"; _pb.valves.MAX_RETRIES = 1
_seqb = [_FakeHTTPResp(429, {"Retry-After": "0"}), _FakeHTTPResp(200, body={"choices": [{"message": {"content": "ok"}}]})]
_pb._post_calls = 0
def _postb(*a, **k):
    _pb._post_calls += 1
    return _seqb.pop(0)
_pb._session.post = _postb  # type: ignore

_main_thread = _threading.get_ident()
_sleep_threads = []
_orig_sleep = mod.time.sleep
def _track_sleep(s):
    _sleep_threads.append(_threading.get_ident())
    # don't actually sleep
mod.time.sleep = _track_sleep
try:
    async def _drive():
        return await _pb._call_request_async(False, {}, {"model": "x"}, _pb.valves)
    _r = _run(_drive())
finally:
    mod.time.sleep = _orig_sleep
_assert(_r.status_code == 200, "async retry returns success")
_assert(_sleep_threads and all(t != _main_thread for t in _sleep_threads), "retry sleep ran off the main/event-loop thread")
```

- [ ] **Step 2: Run** → FAIL (`_call_request_async` missing).

- [ ] **Step 3: Add an async wrapper** that offloads the blocking sync request to a thread. Add to `class Pipe` (just after `_retryable_request`):

```python
    async def _call_request_async(self, stream, headers, payload, valves) -> requests.Response:
        """Run the blocking _retryable_request (incl. retry sleeps) off the event loop."""
        return await asyncio.to_thread(self._retryable_request, headers, payload, stream, valves)
```

- [ ] **Step 4: Use it in the async non-stream + tool-nonstream paths.**
  - In `pipe()`, the no-tools non-stream branch currently calls `result = self._non_stream_response(headers, payload, eff)` synchronously. Change `_non_stream_response` to remain sync, but offload it: `result = await asyncio.to_thread(self._non_stream_response, headers, payload, eff)`.
  - In `_run_tools_nonstream`, replace BOTH `self._retryable_request(headers, payload, stream=False, valves=valves)` calls (loop body + cap-exit) with `await self._call_request_async(False, headers, payload, valves)`.

- [ ] **Step 5: Make streaming pulls non-blocking.** The streaming sync generators (`_stream_response`, `_stream_one_round`) call `_retryable_request` (blocking) on first pull and do blocking `iter_lines`. Wrap their consumption so each pull runs off-loop. Add a module sentinel near the top constants: `_STREAM_DONE = object()`. Then change the async wrappers in `pipe()` and `_run_tools_stream` to pull via a thread:
  - In `pipe()`'s `_wrap_stream` (no-tools streaming) and the bare `return gen` path: ALWAYS wrap streaming in an async generator that pulls via `asyncio.to_thread`. Replace the whole `if stream:` (no-tools) block with:

```python
        if stream:
            gen = self._stream_response(headers, payload, eff)
            it = iter(gen)

            async def _wrap_stream():
                try:
                    while True:
                        chunk = await asyncio.to_thread(next, it, _STREAM_DONE)
                        if chunk is _STREAM_DONE:
                            break
                        yield chunk
                finally:
                    if __event_emitter__:
                        await __event_emitter__({"type": "status", "data": {"description": "", "done": True}})
            return _wrap_stream()
```

  - In `_run_tools_stream`, the inner `for piece in self._stream_one_round(...)` loops run blocking pulls on the event loop. Change each `for piece in self._stream_one_round(headers, payload, valves, state):` to pull via thread:

```python
            it = iter(self._stream_one_round(headers, payload, valves, state))
            while True:
                piece = await asyncio.to_thread(next, it, _STREAM_DONE)
                if piece is _STREAM_DONE:
                    break
                yield piece
```
  (apply to both the in-loop round and the post-cap final round).

- [ ] **Step 6: Run** `python test_pipe.py` → PASS. Existing streaming + tool tests must stay green (behavior identical; only the thread the pulls run on changes). **Step 7: Lint** clean. **Step 8: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "fix: run blocking retry/stream pulls off the event loop via asyncio.to_thread"
```

---

## Task 4 (P1 security): sanitize headers/output + decrypt-fail hardening

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("security sanitization")

# X-Title CR/LF stripped
with patch.dict(os.environ, {"WEBUI_NAME": "Evil\r\nX-Inject: 1"}):
    _px = Pipe(); _px.valves.OPENROUTER_API_KEY = "sk-or-x"
    _h = _px._build_headers(valves=_px.valves)
    _assert("\r" not in _h["X-Title"] and "\n" not in _h["X-Title"], "X-Title strips CR/LF")

# 'Responded by' sanitized
_pm = Pipe()
_res_fb = {"choices": [{"message": {"content": "hi"}}], "model": "evil`](http://x)", "models": ["a"]}
_msg = _pm._format_final_message(_res_fb, {"model": "a", "models": ["a", "b"]}, _pm.valves)
_assert("`" not in _msg.split("Responded by")[-1] if "Responded by" in _msg else True, "Responded-by strips backticks")

# data:image restricted + size-capped
_assert(mod._format_image_output([{"image_url": {"url": "data:image/svg+xml,<svg onload=alert(1)>"}}]) == "", "svg data URL rejected")
_assert("data:image/png;base64,iVBOR" in mod._format_image_output([{"image_url": {"url": "data:image/png;base64,iVBOR"}}]), "png data URL allowed")
_big = "data:image/png;base64," + ("A" * 3_000_000)
_assert(mod._format_image_output([{"image_url": {"url": _big}}]) == "", "oversized data URL rejected")

# decrypt failure → "" (not raw ciphertext)
with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "secretA"}):
    _ct = mod.EncryptedStr.encrypt("sk-or-real")
with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "secretB"}):  # wrong key
    _assert(mod.EncryptedStr.decrypt(_ct) == "", "wrong-key decrypt returns empty, not ciphertext")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.**
  - **X-Title:** in `__init__`, sanitize the title. Replace `self._title = os.getenv("WEBUI_NAME", "OpenWebUI")` with:
    ```python
    _raw_title = os.getenv("WEBUI_NAME", "OpenWebUI")
    self._title = re.sub(r"[\r\n\x00]", "", _raw_title) or "OpenWebUI"
    ```
  - **Responded-by:** in `_format_final_message`, change the append to strip markdown-breaking chars:
    ```python
        if payload.get("models") and actual_model and actual_model != requested_model:
            safe_model = re.sub(r"[`\r\n\]\[()]", "", str(actual_model))
            final_parts.append(f"\n\n---\n*Responded by: {safe_model}*")
    ```
  - **data:image cap:** in `_format_image_output`, replace the accept check:
    ```python
        for img in (images or []):
            if not isinstance(img, dict):
                continue
            url = (img.get("image_url") or {}).get("url", "")
            if not url or len(url) > 2_000_000:
                continue
            lower = url.lower()
            allowed_data = lower.startswith(("data:image/png", "data:image/jpeg", "data:image/jpg", "data:image/gif", "data:image/webp"))
            if not (lower.startswith(("http://", "https://")) or allowed_data):
                continue
            parts.append(f"![Generated image]({url.replace(')', '%29')})")
    ```
  - **decrypt-fail → "":** in `EncryptedStr.decrypt`, change the `except Exception: return value` to `except Exception: return ""`. (Empty key → callers show the "not configured" guard rather than sending junk; matches README key-rotation guidance.) Also update the existing EncryptedStr test that asserts corrupt-token passthrough returns the input — change it to assert `== ""` for a prefixed-but-undecryptable token. Find the assertion `decrypt("encrypted:not-a-valid-token") == "encrypted:not-a-valid-token"` and change expected to `== ""` with message "undecryptable prefixed token → empty".

- [ ] **Step 4: Run** → PASS. **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "fix: sanitize X-Title/Responded-by, cap data: images, empty on decrypt fail"
```

---

## Task 5 (P1 docs): accuracy + release hygiene

**Files:** Modify `SECURITY.md`, `README.md`, `test_pipe.py`, `integration_test.py` (docstring done in Task 1), `CHANGELOG.md`.

- [ ] **Step 1: SECURITY.md supported versions** — update the version table (search the `## Supported Versions` / "1.6.x" rows) to list `1.8.x` (active) and `1.7.x` (security fixes); drop the stale `1.5.x`/`1.6.x` lines or mark EOL. Match the current `1.8.x` reality.
- [ ] **Step 2: README FAQ tool calling** — find the FAQ answer stating "Open WebUI manages tool calling in an iterative loop … pipe forwards the full message list" and replace with the v1.8 truth: native function-calling mode is handled BY THE PIPE (it runs the execute→re-request loop, parallel, streaming + non-streaming, capped by `MAX_TOOL_ITERATIONS`); prompt-based mode is still handled by OWUI.
- [ ] **Step 3: test_pipe.py docstring** — change `v1.3.0` → `v1.8.2` in the module docstring (line ~2).
- [ ] **Step 4: CHANGELOG release dating** — convert `## [Unreleased]` into dated sections. Move the encryption/UserValves items under `## [1.7.0] — 2026-05-28`, the tool-calling/credit items under `## [1.8.0] — 2026-05-28`, the retry/error-message items under `## [1.8.1] — 2026-05-29`, and start a fresh `## [1.8.2] — 2026-05-29` for THIS pass's fixes. Keep an empty `## [Unreleased]` at top. (Group the existing bullets by which feature they belong to — they're already written; just re-home them under the right version headers.)
- [ ] **Step 5: Commit**

```bash
git add SECURITY.md README.md test_pipe.py CHANGELOG.md
git commit -m "docs: correct SECURITY versions + tool-calling FAQ, date CHANGELOG releases"
```

---

## Task 6 (P2 API): usage.include + forward user-id

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("usage.include + user-id forwarding")

_pu = Pipe(); _pu.valves.SHOW_COST_INFO = True
_pp = _pu._prepare_payload({"model": "x", "messages": [], "user": {"id": "u123", "name": "n"}}, _pu.valves)
_assert(_pp.get("usage") == {"include": True}, "usage.include injected when SHOW_COST_INFO on")
_assert(_pp.get("user") == "u123", "user dict reduced to its id string")

_pu2 = Pipe(); _pu2.valves.SHOW_COST_INFO = False
_pp2 = _pu2._prepare_payload({"model": "x", "messages": []}, _pu2.valves)
_assert("usage" not in _pp2, "no usage.include when SHOW_COST_INFO off")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** in `_prepare_payload`. Replace the user-drop block:
```python
        # Open WebUI sends 'user' as dict; OpenRouter expects a string (forward the id)
        user_val = payload.get("user")
        if isinstance(user_val, dict):
            uid = user_val.get("id") or ""
            if uid:
                payload["user"] = str(uid)
            else:
                payload.pop("user", None)
```
Then, near the end of `_prepare_payload` (before `return payload`), add:
```python
        # Request usage accounting explicitly so cost/credit footers aren't blank.
        if valves.SHOW_COST_INFO:
            payload["usage"] = {"include": True}
```

- [ ] **Step 4: Run** → PASS. **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: request usage.include for cost display; forward user id string"
```

---

## Task 7 (P2 API): RESPONSE_FORMAT + TOOL_CHOICE valves

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("RESPONSE_FORMAT + TOOL_CHOICE valves")

_prf = Pipe()
_assert(_prf.valves.RESPONSE_FORMAT == "", "RESPONSE_FORMAT default empty")
_assert(_prf.valves.TOOL_CHOICE == "", "TOOL_CHOICE default empty")
_prf.valves.RESPONSE_FORMAT = "json_object"
_pp = _prf._prepare_payload({"model": "x", "messages": []}, _prf.valves)
_assert(_pp.get("response_format") == {"type": "json_object"}, "json_object response_format injected")
_prf.valves.TOOL_CHOICE = "required"
_pp2 = _prf._prepare_payload({"model": "x", "messages": []}, _prf.valves)
_assert(_pp2.get("tool_choice") == "required", "tool_choice injected")
# body value wins over valve default
_pp3 = _prf._prepare_payload({"model": "x", "messages": [], "response_format": {"type": "json_schema", "json_schema": {}}}, _prf.valves)
_assert(_pp3["response_format"]["type"] == "json_schema", "explicit body response_format preserved over valve")
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.** Add to admin `Valves` (after `COST_CURRENCY`, before `MAX_TOOL_ITERATIONS`):
```python
        RESPONSE_FORMAT: str = Field(
            default=os.getenv("OPENROUTER_RESPONSE_FORMAT", ""),
            description="Force output format: '' (off), 'json_object' (any valid JSON), or 'json_schema' (set the schema in the request). The request body's own response_format always wins.",
            json_schema_extra={"input": {"type": "select", "options": [
                {"value": "", "label": "Off"},
                {"value": "json_object", "label": "JSON object"},
            ]}},
        )
        TOOL_CHOICE: str = Field(
            default=os.getenv("OPENROUTER_TOOL_CHOICE", ""),
            description="Default tool_choice when tools are present: '' (model decides / auto), 'none', 'required', or 'auto'. The request body's own tool_choice always wins.",
        )
```
Add `UserValves` mirrors (after `COST_CURRENCY`): `RESPONSE_FORMAT: Optional[str] = None` and `TOOL_CHOICE: Optional[str] = None`.

In `_prepare_payload`, before `return payload`, add (valve only fills when the body didn't set it):
```python
        rf = (valves.RESPONSE_FORMAT or "").strip()
        if rf == "json_object" and "response_format" not in payload:
            payload["response_format"] = {"type": "json_object"}

        tc = (valves.TOOL_CHOICE or "").strip().lower()
        if tc in ("none", "auto", "required") and "tool_choice" not in payload:
            payload["tool_choice"] = tc
```
(Note: `json_schema` mode is documented as "set the schema in the request body"; the valve only auto-injects `json_object`. No schema is fabricated.)

- [ ] **Step 4: Run** → PASS. **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: add RESPONSE_FORMAT (json mode) and TOOL_CHOICE valves"
```

---

## Task 8 (P2 robustness): cache races, credit cap, retry-after float, ZDR TTL

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("robustness polish")

# _parse_retry_after honors fractional seconds
_prr = Pipe()
_assert(_prr._parse_retry_after("1.5") == 1.5, "fractional Retry-After honored")

# credit cache capped
_pcc = Pipe()
for _i in range(1100):
    _pcc._credit_cache[f"k{_i}"] = (1.0, 0.0)
_pcc._credit_cache_evict_if_needed()
_assert(len(_pcc._credit_cache) <= 1000, "credit cache capped at 1000")

# _sync iteration safe against concurrent clear (iterate a copy)
# (smoke: calling with a set snapshot must not raise)
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.**
  - **Fractional Retry-After:** in `_parse_retry_after`, change `secs = float(int(value))` to `secs = float(value)` (the `except ValueError` already handles HTTP-date fallthrough).
  - **Credit cache cap:** add a method + call it in `_fetch_credit_balance` right before writing the cache:
    ```python
    def _credit_cache_evict_if_needed(self) -> None:
        if len(self._credit_cache) > 1000:
            self._credit_cache.clear()
    ```
    In `_fetch_credit_balance`, before `self._credit_cache[key_hash] = (...)`, call `self._credit_cache_evict_if_needed()`.
  - **Icon-sync race:** in `_sync_model_icons`, iterate over a snapshot — wherever it iterates `self._icons_synced` or compares against it during a `pipes()` refresh, take `list(self._icons_synced)` / build a local copy so a concurrent `_icons_synced.clear()` cannot raise `RuntimeError: Set changed size during iteration`. (Locate the iteration in `_sync_model_icons`; wrap the iterated set with `set(self._icons_synced)`.)
  - **ZDR TTL:** in `_load_zdr_model_ids`, add a timestamp guard mirroring the provider-registry pattern: store `self._zdr_model_ids_ts` and re-fetch when `time.monotonic() - ts > _PROVIDER_REGISTRY_TTL`. Add `self._zdr_model_ids_ts: float = 0.0` in `__init__`. (Keep the existing failure/back-off semantics.)

- [ ] **Step 4: Run** → PASS. **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "fix: fractional Retry-After, cap credit cache, iterate icon set copy, ZDR TTL"
```

---

## Task 9 (P2 tests + version): coverage gaps + bump to 1.8.2

**Files:** Modify `test_pipe.py`, `openrouter_pipe.py`, `function.json`.

- [ ] **Step 1: Add coverage** — append tests for the previously-uncovered paths:
  - `pipe()` entry with `__tools__` (non-stream): mock `_retryable_request`, call `await pipe(body, __tools__=tools)`, assert the tool loop ran and a final string returned.
  - streaming tool-loop iteration cap: drive `_run_tools_stream` with always-tool rounds beyond `MAX_TOOL_ITERATIONS`, assert the cap note appears.
  - `SHOW_REMAINING_CREDIT` end-to-end in `_format_final_message` (stub `_fetch_credit_balance`), assert credit line in output.
  - wrong-key decrypt already covered in Task 4; ensure it's present.

  (Write each as a `_section` + `_assert` block; reuse `_FakeResp`/`_FakeStream`/`_run`.)

- [ ] **Step 2:** Bump version: `openrouter_pipe.py` header `version: 1.8.1` → `1.8.2`; `function.json` `"version": "1.8.2"`. (No description change needed — these are fixes.)
- [ ] **Step 3:** Run `python test_pipe.py` → 0 failures; note total. `python -m pyflakes openrouter_pipe.py test_pipe.py` → clean. `grep -rn "1\.8\.1" openrouter_pipe.py function.json` → none.
- [ ] **Step 4: Update doc counts** — bump the `python test_pipe.py → NNN passed` references (README ×3, CONTRIBUTING ×2, SECURITY ×1, TESTING ×1, PR template ×1) to the new total.
- [ ] **Step 5: Commit**

```bash
git add test_pipe.py openrouter_pipe.py function.json README.md CONTRIBUTING.md SECURITY.md TESTING.md .github/PULL_REQUEST_TEMPLATE.md
git commit -m "test: cover tool dispatch/cap/credit paths; bump to v1.8.2"
```

---

## Task 10: Final verification

- [ ] `python test_pipe.py` → 0 failures (note total). `python -m pyflakes openrouter_pipe.py test_pipe.py` → clean.
- [ ] `python -c "import json; json.load(open('function.json'))"` → valid; `grep -rn "1\.8\.1" openrouter_pipe.py function.json` → none.
- [ ] Regression: existing streaming + tool + retry tests still green (behavior preserved; Task 3 only changed the thread pulls run on).
- [ ] `git status` → only untracked tooling dirs (+ possible `LICENSE` working-tree edit) remain uncommitted.

---

## Self-review notes (applied)

- **Coverage of punch-list:** #1 (T1), #2+#19 (T2), #3 (T3), #4+#5+#6+#7 (T4), #8+#9+#10+#11 (T5), #12+#13 (T6), #14+#15 (T7), #16+#17+#18+#20 (T8), #21 + version (T9). All 21 mapped.
- **#3 risk:** flagged high-risk; `asyncio.to_thread` keeps transport sync (lean) while unblocking the loop; existing tests guard behavior.
- **Sequencing:** P0 (T1-T3) → P1 (T4-T5) → P2 (T6-T9) → verify (T10). Each task green + committable.
- **No new deps:** stdlib `asyncio` only (already imported).
- **Naming consistency:** `_call_request_async`, `_credit_cache_evict_if_needed`, `_STREAM_DONE`, valves `RESPONSE_FORMAT`/`TOOL_CHOICE` used consistently.
- **Known nuance (T2/T9 tests):** reuse the existing `_FakeResp`/`_FakeStream`/`_run` scaffolding; if a helper isn't in scope at the append point, place the new `_section` after the section that defines it.
