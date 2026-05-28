# Retry Hardening + Error-UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retry transient OpenRouter failures (HTTP 429 + 5xx) honoring `Retry-After`, and give clearer messages for more HTTP status codes.

**Architecture:** Add module constants + two static helpers (`_parse_retry_after`, `_backoff_delay`), rework the `HTTPError` branch of `_retryable_request` to retry the transient statuses within the existing `MAX_RETRIES` budget, and extend `_format_http_error`. No new valves, no new third-party deps (stdlib `email.utils`).

**Tech Stack:** Python 3, `requests`, stdlib `email.utils` + `time` + `random`. Tests: `_assert`/`_section` harness, `python test_pipe.py`. Lint: `python -m pyflakes openrouter_pipe.py`.

---

## Critical conventions (read first)

- ONE file `openrouter_pipe.py`. Line numbers APPROXIMATE — locate by name.
- **Tests are NOT pytest.** Append `_section`/`_assert` blocks; run `python test_pipe.py`; must end `All tests passed! ✓`, 0 failures. **Baseline: 624 passed.** Symbols bind near the top (`Pipe = mod.Pipe`, `mod`). The pipe's `requests` is reachable as `mod.requests`; module `time` as `mod.time`. `patch` (from `unittest.mock`) is imported in the test file.
- Lint clean each commit. Commit to `main`; `git add openrouter_pipe.py test_pipe.py` ONLY (never `-A`; untracked `.claude/`, `.swarm/`, `ruvector.db`, and a working-tree `LICENSE` edit must stay out — add files by explicit name).
- Current `_retryable_request` and `_format_http_error` are at the END of the `Pipe` class (just before `__all__ = ["Pipe"]`).

## Shared test scaffolding (added in Task 1, reused by Task 2)

A fake response + a scripted `_session.post`:

```python
class _FakeHTTPResp:
    def __init__(self, status, headers=None, body=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body or {}
        self.closed = False
    def raise_for_status(self):
        if self.status_code >= 400:
            raise mod.requests.exceptions.HTTPError(response=self)
    def json(self):
        return self._body
    def close(self):
        self.closed = True

def _script_post(pipe, responses):
    """Make pipe._session.post pop from `responses`; record call count on pipe._post_calls."""
    pipe._post_calls = 0
    def _post(*a, **k):
        pipe._post_calls += 1
        return responses.pop(0)
    pipe._session.post = _post  # type: ignore
```

---

## Task 1: Constants + `_parse_retry_after` + `_backoff_delay`

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append to `test_pipe.py` (also add the scaffolding above, once, in this task):

```python
# ── retry helpers (v1.8.1) ──────────────────────────────────────────────────────

_section("_parse_retry_after / _backoff_delay")

_pr = Pipe()
_assert(_pr._parse_retry_after("5") == 5.0, "integer seconds parsed")
_assert(_pr._parse_retry_after("99999") == mod._MAX_RETRY_AFTER, "huge value capped at _MAX_RETRY_AFTER")
_assert(_pr._parse_retry_after("-3") == 0.0, "negative clamped to 0")
_assert(_pr._parse_retry_after("Wed, 21 Oct 2099 07:28:00 GMT") == mod._MAX_RETRY_AFTER, "far-future HTTP-date capped")
_assert(_pr._parse_retry_after("Mon, 01 Jan 2001 00:00:00 GMT") == 0.0, "past HTTP-date clamped to 0")
_assert(_pr._parse_retry_after("") is None, "empty → None")
_assert(_pr._parse_retry_after(None) is None, "None → None")
_assert(_pr._parse_retry_after("abc") is None, "garbage → None")

_d0 = _pr._backoff_delay(0)
_assert(0.0 <= _d0 <= 1.0, "backoff attempt 0 in [0,1]")
_d3 = _pr._backoff_delay(3)
_assert(8.0 <= _d3 <= 9.0, "backoff attempt 3 in [8,9]")
_assert(_pr._backoff_delay(20) == 30, "backoff capped at 30")

_assert(mod._RETRYABLE_STATUS == frozenset({429, 500, 502, 503, 504}), "retryable status set")
```

- [ ] **Step 2: Run** `python test_pipe.py` → FAIL (`_parse_retry_after`/`_backoff_delay`/`_RETRYABLE_STATUS`/`_MAX_RETRY_AFTER` missing).

- [ ] **Step 3: Add import + constants.** In `openrouter_pipe.py`, add `import email.utils` to the stdlib import block (alphabetical: after `import copy`, before `import hashlib` — actually place after `import copy`). Then, next to the other module constants (search `_API_PATH_CREDITS`), add:

```python
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER = 60.0  # cap (seconds) — a huge Retry-After must not hang the request
```

(Import block becomes: asyncio, base64, copy, email.utils, hashlib, inspect, json, os, random, re, time, traceback. `email.utils` is a submodule import — `import email.utils` is correct and used by `_parse_retry_after`.)

- [ ] **Step 4: Add the two static helpers** — add to `class Pipe`, placed just before `_retryable_request`:

```python
    @staticmethod
    def _parse_retry_after(value) -> Optional[float]:
        """Parse a Retry-After header (integer seconds or HTTP-date) into seconds.

        Clamped to [0, _MAX_RETRY_AFTER]. Returns None when absent/unparseable.
        """
        if not value:
            return None
        value = str(value).strip()
        try:
            secs = float(int(value))
        except ValueError:
            parsed = email.utils.parsedate_tz(value)
            if not parsed:
                return None
            try:
                secs = email.utils.mktime_tz(parsed) - time.time()
            except (TypeError, ValueError, OverflowError):
                return None
        return max(0.0, min(secs, _MAX_RETRY_AFTER))

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff with jitter, capped at 30s."""
        return min(2 ** attempt + random.uniform(0, 1), 30)
```

- [ ] **Step 5: Run** `python test_pipe.py` → PASS (expect ~635; note exact). **Step 6: Lint** clean. **Step 7: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: add Retry-After parser and shared backoff helper"
```

---

## Task 2: Retry transient HTTP 429/5xx in `_retryable_request`

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append (uses the `_FakeHTTPResp`/`_script_post` scaffolding from Task 1):

```python
_section("retryable_request transient HTTP retries")

# 429 (with Retry-After) then 200 → one retry, returns 200, slept the Retry-After value
_p_r = Pipe(); _p_r.valves.OPENROUTER_API_KEY = "sk-or-test"; _p_r.valves.MAX_RETRIES = 2
_script_post(_p_r, [_FakeHTTPResp(429, {"Retry-After": "7"}), _FakeHTTPResp(200, body={"ok": 1})])
with patch.object(mod.time, "sleep") as _sl:
    _resp = _p_r._retryable_request({}, {}, False, _p_r.valves)
_assert(_resp.status_code == 200, "429→200: returns the success response")
_assert(_p_r._post_calls == 2, "429→200: exactly one retry")
_assert(_sl.call_args_list[0][0][0] == 7.0, "429: slept the Retry-After value (7s)")

# 503 without Retry-After then 200 → retried with a backoff delay (0..1 for attempt 0)
_p_s = Pipe(); _p_s.valves.OPENROUTER_API_KEY = "sk-or-test"; _p_s.valves.MAX_RETRIES = 2
_script_post(_p_s, [_FakeHTTPResp(503), _FakeHTTPResp(200, body={"ok": 1})])
with patch.object(mod.time, "sleep") as _sl2:
    _resp2 = _p_s._retryable_request({}, {}, False, _p_s.valves)
_assert(_resp2.status_code == 200, "503→200: returns success")
_assert(0.0 <= _sl2.call_args_list[0][0][0] <= 1.0, "503 no Retry-After: backoff delay used")

# Non-retryable 4xx → raise immediately, no retry
for _code in (400, 401, 403, 404):
    _p_e = Pipe(); _p_e.valves.OPENROUTER_API_KEY = "sk-or-test"; _p_e.valves.MAX_RETRIES = 2
    _script_post(_p_e, [_FakeHTTPResp(_code), _FakeHTTPResp(200)])
    _raised = False
    with patch.object(mod.time, "sleep"):
        try:
            _p_e._retryable_request({}, {}, False, _p_e.valves)
        except mod.requests.exceptions.HTTPError:
            _raised = True
    _assert(_raised, f"HTTP {_code} raised immediately")
    _assert(_p_e._post_calls == 1, f"HTTP {_code} not retried")

# Retryable every time → raises after MAX_RETRIES+1 attempts, sleeps MAX_RETRIES times
_p_x = Pipe(); _p_x.valves.OPENROUTER_API_KEY = "sk-or-test"; _p_x.valves.MAX_RETRIES = 2
_script_post(_p_x, [_FakeHTTPResp(429), _FakeHTTPResp(429), _FakeHTTPResp(429)])
_raised_x = False
with patch.object(mod.time, "sleep") as _sl3:
    try:
        _p_x._retryable_request({}, {}, False, _p_x.valves)
    except mod.requests.exceptions.HTTPError:
        _raised_x = True
_assert(_raised_x, "exhausted retries → HTTPError raised")
_assert(_p_x._post_calls == 3, "MAX_RETRIES=2 → 3 attempts total")
_assert(_sl3.call_count == 2, "slept twice (between the 3 attempts)")

# MAX_RETRIES=0 → no retry even on 429
_p_z = Pipe(); _p_z.valves.OPENROUTER_API_KEY = "sk-or-test"; _p_z.valves.MAX_RETRIES = 0
_script_post(_p_z, [_FakeHTTPResp(429), _FakeHTTPResp(200)])
_raised_z = False
with patch.object(mod.time, "sleep"):
    try:
        _p_z._retryable_request({}, {}, False, _p_z.valves)
    except mod.requests.exceptions.HTTPError:
        _raised_z = True
_assert(_raised_z and _p_z._post_calls == 1, "MAX_RETRIES=0 disables retry")
```

- [ ] **Step 2: Run** `python test_pipe.py` → FAIL (429/5xx currently raise immediately; `_post_calls`/sleep expectations fail).

- [ ] **Step 3: Replace `_retryable_request`** with this full version (locate the existing method and replace it entirely):

```python
    def _retryable_request(
        self, headers: dict, payload: dict, stream: bool, valves
    ) -> requests.Response:
        """Send a POST request with automatic retry and exponential backoff.

        Retries transient failures — network Timeout/ConnectionError and HTTP
        429/5xx (honouring Retry-After when present) — within the MAX_RETRIES
        budget. Non-transient 4xx fail fast.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(valves.MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    self.chat_url,
                    headers=headers,
                    json=payload,
                    timeout=valves.REQUEST_TIMEOUT,
                    stream=stream,
                    allow_redirects=False,
                )
                response.raise_for_status()
                return response
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                last_exc = exc
                print(f"[OpenRouter Pipe] Attempt {attempt + 1} failed: {exc}")
                if attempt == valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in _RETRYABLE_STATUS or attempt == valves.MAX_RETRIES:
                    raise
                delay = None
                if exc.response is not None:
                    delay = self._parse_retry_after(exc.response.headers.get("Retry-After"))
                    try:
                        exc.response.close()
                    except Exception:
                        pass
                if delay is None:
                    delay = self._backoff_delay(attempt)
                last_exc = exc
                print(f"[OpenRouter Pipe] HTTP {status} on attempt {attempt + 1}; retrying in {delay:.1f}s")
                time.sleep(delay)
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                print(f"[OpenRouter Pipe] Unexpected error: {exc}")
                if attempt == valves.MAX_RETRIES:
                    raise
                time.sleep(self._backoff_delay(attempt))
        if last_exc:
            raise last_exc  # pragma: no cover
        raise RuntimeError("OpenRouter Error: request not completed")  # pragma: no cover
```

- [ ] **Step 4: Run** `python test_pipe.py` → PASS (expect ~641; note exact). Existing tests stay green (Timeout/ConnectionError behavior unchanged — same backoff formula, now via `_backoff_delay`). **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: retry transient HTTP 429/5xx honoring Retry-After"
```

---

## Task 3: Enrich `_format_http_error`

**Files:** Modify `openrouter_pipe.py`; Test `test_pipe.py`.

- [ ] **Step 1: Failing test** — append:

```python
_section("_format_http_error new status codes")

def _err(status):
    r = _FakeHTTPResp(status)
    return mod.requests.exceptions.HTTPError(response=r)

_pf = Pipe()
_assert("404" in _pf._format_http_error(_err(404)) and "not found" in _pf._format_http_error(_err(404)).lower(), "404 message")
_assert("408" in _pf._format_http_error(_err(408)), "408 message")
_assert("413" in _pf._format_http_error(_err(413)) and ("large" in _pf._format_http_error(_err(413)).lower() or "limit" in _pf._format_http_error(_err(413)).lower()), "413 message")
_assert("500" in _pf._format_http_error(_err(500)), "500 message")
_assert("502" in _pf._format_http_error(_err(502)), "502 message")
_assert("503" in _pf._format_http_error(_err(503)), "503 message")
_assert("504" in _pf._format_http_error(_err(504)), "504 message")
```

- [ ] **Step 2: Run** → FAIL (these fall to the generic `HTTP {status}`, which DOES contain the number — so check the substrings that the generic message lacks). NOTE: the generic message `OpenRouter Error: HTTP 404` already contains "404", so the `"404" in ...` part passes even before the change; the `"not found"` / `"large"|"limit"` substrings are what fail. Confirm the run shows the wording asserts failing for 404/413 (and 408/500/502/503/504 still pass via the number). Implement to make ALL meaningful.

  To make the failing-first step crisp, the wording substrings (`not found`, `large`/`limit`) are the real gate. Proceed to Step 3.

- [ ] **Step 3: Implement** — in `_format_http_error`, insert the new `elif` branches between the existing `elif status == 403:` block and the final `else:`:

```python
        elif status == 404:
            base = "OpenRouter Error: Model or endpoint not found (HTTP 404). The model ID may be wrong or unavailable."
        elif status == 408:
            base = "OpenRouter Error: Request timed out on the server (HTTP 408). Try again."
        elif status == 413:
            base = "OpenRouter Error: Request too large (HTTP 413). The prompt or context likely exceeds the model's limit."
        elif status == 500:
            base = "OpenRouter Error: Provider error (HTTP 500). The upstream model provider failed; try again or pick another model."
        elif status == 502:
            base = "OpenRouter Error: Bad gateway (HTTP 502). The upstream provider is unreachable; try again."
        elif status == 503:
            base = "OpenRouter Error: Service unavailable (HTTP 503). The provider is overloaded; try again shortly."
        elif status == 504:
            base = "OpenRouter Error: Upstream timeout (HTTP 504). The provider took too long; try again."
```

- [ ] **Step 4: Run** → PASS (expect ~648; note exact). **Step 5: Lint** clean. **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: clearer messages for 404/408/413/5xx HTTP errors"
```

---

## Task 4: Version 1.8.1 + docstring + function.json (inline-friendly)

**Files:** Modify `openrouter_pipe.py`, `function.json`.

- [ ] **Step 1:** In `openrouter_pipe.py` header, `version: 1.8.0` → `version: 1.8.1`.
- [ ] **Step 2:** Append to the module `description:` line: ` Transient 429/5xx retries with Retry-After awareness.`
- [ ] **Step 3:** In `function.json`: set `"version": "1.8.1"` and append the same sentence to the description.
- [ ] **Step 4:** Verify: `grep -rn "1\.8\.0" openrouter_pipe.py function.json` → no version matches; `python -c "import json; json.load(open('function.json'))"` → valid.
- [ ] **Step 5:** `python test_pipe.py` → 0 failures; `python -m pyflakes openrouter_pipe.py` → clean.
- [ ] **Step 6: Commit**

```bash
git add openrouter_pipe.py function.json
git commit -m "chore: bump to v1.8.1, document transient-retry hardening"
```

---

## Task 5: Documentation

**Files:** Modify `CHANGELOG.md`, `README.md`, `TESTING.md`.

- [ ] **Step 1: CHANGELOG** — under `[Unreleased] → ### Added` (or a new `### Changed` if more apt), add:

```markdown
- **Transient-failure retries** — HTTP 429 (rate limit) and 5xx (500/502/503/504) are now retried within the existing `MAX_RETRIES` budget, honoring the `Retry-After` header (integer seconds or HTTP-date, capped at 60s) when present, otherwise exponential backoff. Non-transient 4xx still fail fast. Also added clearer error messages for HTTP 404/408/413/500/502/503/504.
```

- [ ] **Step 2: README** — in the Network valve area / near `MAX_RETRIES`, add a sentence: "Retries cover network errors **and** transient HTTP 429/5xx (honoring `Retry-After`, capped at 60s); non-transient 4xx fail fast." Bump any test-count reference if present.
- [ ] **Step 3: TESTING** — add a manual row under a robustness section (or section 14 error handling): "Simulate a 429 with `Retry-After` (e.g. via a throttled key) → request retries after the indicated delay, then succeeds or surfaces a clear rate-limit message." Bump the `python test_pipe.py` count in the checklist to the new total.
- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md TESTING.md
git commit -m "docs: document transient-retry hardening + error messages"
```

---

## Task 6: Final verification

- [ ] **Step 1:** `python test_pipe.py` → note total, 0 failures.
- [ ] **Step 2:** `python -m pyflakes openrouter_pipe.py test_pipe.py` → clean.
- [ ] **Step 3:** Regression sanity — existing Timeout/ConnectionError retry tests + all `_format_http_error` 401/402/403/429 tests still pass (behavior preserved; only HTTP-error retry added + new status messages).
- [ ] **Step 4:** `git status` → working tree clean of intended changes (the untracked tooling dirs and the unrelated `LICENSE` working-tree edit remain — do NOT commit them).

---

## Self-review notes (applied)

- **Spec coverage:** `_RETRYABLE_STATUS`/`_MAX_RETRY_AFTER` (T1), `_parse_retry_after` int+HTTP-date+cap+clamp (T1), `_backoff_delay` DRY (T1, wired T2), `_retryable_request` retry of 429/5xx + Retry-After + close response (T2), MAX_RETRIES budget reuse / `=0` disables (T2 test), `_format_http_error` 404/408/413/5xx (T3), version/docstring/function.json (T4), docs (T5), no new valve / `requests`+`pydantic` unchanged (stated). All spec sections map to a task.
- **No new deps:** only stdlib `import email.utils`.
- **Naming consistency:** `_parse_retry_after`, `_backoff_delay`, `_RETRYABLE_STATUS`, `_MAX_RETRY_AFTER` used identically across tasks; test scaffolding `_FakeHTTPResp`/`_script_post` defined in T1 and reused in T2.
- **Failing-first nuance (T3):** the generic message already contains the status number, so the real failing assertions are the wording substrings (`not found`, `large`/`limit`); noted in T3 Step 2.
