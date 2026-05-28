# Retry Hardening + Error-UX — Design Spec

- **Date:** 2026-05-29
- **Target version:** 1.8.0 → 1.8.1 (patch — reliability hardening, no new valves/features)
- **Goal:** Make the pipe survive transient OpenRouter failures (rate limits, upstream 5xx) by retrying them with `Retry-After` awareness, and give users clearer messages for more HTTP status codes.

## Problem

In `_retryable_request`, HTTP errors are never retried — `except requests.exceptions.HTTPError: raise` fires immediately. So **HTTP 429 (rate limit) and transient 5xx (500/502/503/504)** — exactly the errors where a short retry usually succeeds — fail on the first try. The `Retry-After` header that OpenRouter/providers send on 429/503 is ignored. Separately, `_format_http_error` only special-cases 401/402/403/429; other common codes (404, 408, 413, 5xx) fall through to a bare `HTTP {status}` message.

## Decisions (locked)

- Retry **both** transient HTTP errors and enrich messages (one cohesive thread).
- Retryable statuses: `{429, 500, 502, 503, 504}`. All other 4xx (400/401/402/403/404/413) fail fast (unchanged).
- Honor `Retry-After` when present (integer seconds or HTTP-date), capped at 60s; otherwise exponential backoff with jitter (cap 30s).
- Reuse the existing `MAX_RETRIES` budget — **no new valve**. `MAX_RETRIES=0` disables all retries.

## Architecture

### Constants (module level, near the other `_API_PATH_*`/TTL constants)

```python
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER = 60.0  # cap, seconds — a huge Retry-After must not hang the request
```

### `_parse_retry_after(value) -> Optional[float]` (static helper)

Parse a `Retry-After` header value:
- Integer seconds (e.g. `"5"`) → `float`, clamped to `[0, _MAX_RETRY_AFTER]`.
- HTTP-date (RFC 7231, e.g. `"Wed, 21 Oct 2026 07:28:00 GMT"`) → seconds from now via `email.utils.parsedate_to_datetime`, clamped to `[0, _MAX_RETRY_AFTER]`.
- Missing/invalid → `None`.

Uses stdlib `email.utils` (no new dependency).

### `_backoff_delay(attempt) -> float` (static helper)

`min(2 ** attempt + random.uniform(0, 1), 30)` — extracted so the Timeout/ConnectionError, generic-exception, and new HTTP-retry paths share one definition (DRY).

### `_retryable_request` rework

Replace the bare `except requests.exceptions.HTTPError: raise` with:

```
except requests.exceptions.HTTPError as exc:
    status = exc.response.status_code if exc.response is not None else None
    retryable = status in _RETRYABLE_STATUS and attempt < valves.MAX_RETRIES
    if not retryable:
        raise
    # Honor Retry-After, else exponential backoff
    delay = None
    if exc.response is not None:
        delay = self._parse_retry_after(exc.response.headers.get("Retry-After"))
        try:
            exc.response.close()   # free the connection before sleeping
        except Exception:
            pass
    if delay is None:
        delay = self._backoff_delay(attempt)
    print(f"[OpenRouter Pipe] HTTP {status} on attempt {attempt + 1}; retrying in {delay:.1f}s")
    last_exc = exc
    time.sleep(delay)
```

The Timeout/ConnectionError and generic branches keep their behavior but call `self._backoff_delay(attempt)` instead of the inline expression. The loop bound (`range(valves.MAX_RETRIES + 1)`), final `raise last_exc`, and the streaming/non-streaming callers are unchanged.

### `_format_http_error` enrichment

Add specific messages (keep the existing 401/402/403/429 and the body-detail append):
- 404 → "Model or endpoint not found (HTTP 404). The model ID may be wrong or unavailable."
- 408 → "Request timed out on the server (HTTP 408). Try again."
- 413 → "Request too large (HTTP 413). The prompt/context likely exceeds the model's limit."
- 500 → "Provider error (HTTP 500). The upstream model provider failed; try again or another model."
- 502 → "Bad gateway (HTTP 502). The upstream provider is unreachable; try again."
- 503 → "Service unavailable (HTTP 503). The provider is overloaded; try again shortly."
- 504 → "Upstream timeout (HTTP 504). The provider took too long; try again."

## Data flow (retry of a 429)

```
_retryable_request loop, attempt n:
  POST /chat/completions → 429
  raise_for_status() → HTTPError
  status 429 ∈ _RETRYABLE_STATUS and n < MAX_RETRIES → retryable
  delay = _parse_retry_after(headers["Retry-After"]) or _backoff_delay(n)
  close response; sleep(delay); continue
  ... eventually 200 → return, or retries exhausted → raise (→ _format_http_error)
```

## Error handling / edge cases

- `exc.response is None` (rare) → not retryable → raise.
- Retries exhausted on a retryable status → the last HTTPError is raised and rendered by `_format_http_error`.
- `Retry-After` absent or unparseable → exponential backoff.
- Huge `Retry-After` → capped at 60s (never hangs).
- Streaming: `raise_for_status()` runs before the body is iterated, so a 429/5xx is retried before any chunk is yielded — safe.

## Testing (`_assert`/`_section` harness)

- `_parse_retry_after`: `"5"` → 5.0; HTTP-date ~N seconds out → ≈N (allow tolerance); `""`/`None`/`"abc"` → None; `"99999"` → 60.0 (cap); `"-3"` → 0.0.
- `_backoff_delay`: returns within `[2**n, 2**n + 1]` and ≤ 30.
- retry behavior (mock `_session.post` to a scripted sequence + monkeypatch `time.sleep` to record delays, not sleep):
  - 429 then 200 → one retry, returns the 200 response; recorded delay matches the mocked `Retry-After`.
  - 503 (no Retry-After) then 200 → retried with a backoff delay.
  - 400 / 401 / 403 / 404 → raised immediately, `_session.post` called once (NOT retried).
  - retryable status every time with `MAX_RETRIES=2` → raises after 3 attempts; `time.sleep` called twice.
  - `MAX_RETRIES=0` → no retry on 429.
- `_format_http_error`: 404/408/413/500/502/503/504 each return their specific substring; body `error.message` still appended.

Lint: pyflakes clean. Full suite green.

## Scope / files

- `openrouter_pipe.py` — `_RETRYABLE_STATUS`, `_MAX_RETRY_AFTER`, `_parse_retry_after`, `_backoff_delay`, `_retryable_request` HTTPError rework (+ the two existing branches call `_backoff_delay`), `_format_http_error` enrichment, `import email.utils` (stdlib), version → 1.8.1, module docstring (brief mention).
- `function.json` — version mirror (1.8.1).
- `test_pipe.py` — tests above.
- `CHANGELOG.md` — `[Unreleased]` entry.
- `README.md` — short note in the retry/network area that 429 + transient 5xx are retried (honoring `Retry-After`) within the `MAX_RETRIES` budget.
- `TESTING.md` — count bump + a manual row (simulate a 429 → observe retry).
- `requirements.txt` — unchanged.

## Out of scope (YAGNI)

- A separate "retry on rate limit" valve (MAX_RETRIES already governs this).
- Retrying non-idempotent edge cases beyond the listed statuses.
- Circuit-breaker / global rate-limit tracking across requests.
- Per-provider retry tuning.

## Risks

- Retrying 429/5xx adds latency before a hard failure surfaces; bounded by `MAX_RETRIES` (default 2) and the 60s `Retry-After` cap. Acceptable and tunable.
- `Retry-After` HTTP-date parsing depends on `email.utils.parsedate_to_datetime` returning tz-aware datetimes; compute "seconds from now" defensively (treat naive as UTC) and clamp to ≥ 0.
