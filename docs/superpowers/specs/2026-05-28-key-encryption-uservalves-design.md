# Key Encryption + UserValves — Design Spec

- **Date:** 2026-05-28
- **Target version:** 1.6.1 → 1.7.0 (minor, backward-compatible)
- **Goal:** Make the pipe safe for shared/multi-user Open WebUI instances — the gap blocking adoption as a community reference pipe.

## Problem

1. **API key stored plaintext** in the valve DB. On a shared instance any admin-DB read leaks the OpenRouter key.
2. **No per-user configuration.** A single admin `Valves` set is shared by every user, so all users transmit on one key and one preference set.

Upstream rbb-dev (v2.6.4) solves both with `EncryptedStr` + `UserValves`. We port the capability while preserving our differentiator: a tiny declared dependency surface (`requests`, `pydantic`) and an auditable single file.

## Decisions (locked)

- **Crypto dependency:** soft-import `cryptography`, plaintext fallback. `requirements.txt` stays `requests` + `pydantic`. Open WebUI already bundles `cryptography`, so encryption works in-product without adding a declared dependency; outside OWUI (or pre-`WEBUI_SECRET_KEY`) the key degrades to plaintext with a one-time warning.
- **UserValves scope:** API key + full preference mirror. Each user may override the API key and (optionally) any chat-path preference; unset fields inherit the admin default.

## Architecture

### 1. `EncryptedStr`

A `str` subclass providing `encrypt`/`decrypt` class methods. Ciphertext is tagged with the literal prefix `encrypted:`. Real OpenRouter keys begin `sk-or-`, so plaintext never collides with the marker.

- Fernet key derived as `urlsafe_b64encode(sha256(WEBUI_SECRET_KEY))`.
- No `WEBUI_SECRET_KEY` **or** `cryptography` absent → value stored/returned plaintext, warn once.
- `encrypt` is idempotent (prefix guard) — safe to run on every pydantic model init.
- `decrypt` on a non-prefixed value returns it unchanged (legacy plaintext passthrough).
- `decrypt` on a corrupt/foreign token returns it unchanged — never raises into a request.

New imports: `base64` (stdlib). Soft `from cryptography.fernet import Fernet` guarded by try/except → `Fernet = None`.

### 2. Encrypt-on-store

A pydantic `field_validator` on `OPENROUTER_API_KEY` (admin `Valves` and `UserValves`) runs `EncryptedStr.encrypt(v or "")`. Idempotent, so reloading an already-encrypted stored value is a no-op.

### 3. `UserValves`

Nested `BaseModel` mirroring admin preference fields, every field `Optional[...] = None` where **None means "inherit admin"**. Optional/None sentinel (not empty-string/false) is required so a deliberate `False`/`""` override is distinguishable from "not set". The API-key field carries the same encrypt validator and the password input hint.

### 4. Effective-valves merge (concurrency-safe)

The `Pipe` instance is shared across users and requests, so `self.valves` MUST NOT be mutated per request (that would race and leak keys between users). Instead, build a per-request copy:

```python
def _effective_valves(self, __user__):
    eff = self.valves.model_copy()
    uv = (__user__ or {}).get("valves")
    if uv is None:
        return eff
    data = uv.model_dump() if hasattr(uv, "model_dump") else dict(uv)
    for k, val in data.items():
        if val is not None and hasattr(eff, k):
            setattr(eff, k, val)
    return eff
```

### 5. Threading

`pipe()` computes `eff = self._effective_valves(__user__)` once and threads it through the request path. These methods gain a `valves` parameter instead of reading `self.valves`:

- `_prepare_payload`
- `_build_headers`
- `_resolve_referer`
- `_inject_cache_control`
- `_build_web_search_plugin`
- `_non_stream_response`
- `_stream_response`
- `_retryable_request`

The API key is decrypted at the point of use: `EncryptedStr.decrypt(eff.OPENROUTER_API_KEY)` in `_build_headers` (Authorization) and in the cache-key hash.

`pipes()` (model listing) is called by OWUI **without** `__user__`, so it stays on `self.valves` / the admin key. This is a documented limitation: the model catalog and its filters are admin-global; per-user preferences apply to the chat path only.

## Data flow

```
OWUI chat request
  -> Pipe.pipe(body, __user__, ...)
       eff = _effective_valves(__user__)      # admin copy + user overrides
       payload = _prepare_payload(body, eff)
       headers = _build_headers(model_id, eff) # Authorization = decrypt(eff key)
       -> _stream_response / _non_stream_response (eff)
            -> _retryable_request (eff)
```

## Error handling

- Missing key after merge → existing "OPENROUTER_API_KEY not configured" guard (now checks effective key).
- Decrypt failure → plaintext passthrough, no raise.
- Crypto unavailable → warn once at init, operate plaintext.

## Testing

Unit (pytest, `test_pipe.py`):

- encrypt → decrypt roundtrip equals original
- plaintext (non-prefixed) decrypt passthrough
- no `WEBUI_SECRET_KEY` → encrypt/decrypt are no-ops
- `Fernet = None` (simulated) → no-ops
- encrypt idempotent (double-encrypt stable)
- merge: user value wins; `None` inherits admin; `False` overrides admin `True`
- per-user API key appears in `_build_headers` Authorization
- model list (`pipes()`) still uses admin key when `__user__` present elsewhere

Lint: pyflakes clean. Full suite must stay green.

## Scope / files

- `openrouter_pipe.py` — `EncryptedStr`, `UserValves`, validators, `_effective_valves`, thread `eff`, version → 1.7.0, module docstring.
- `function.json` — mirror docstring/version.
- `requirements.txt` — unchanged.
- `test_pipe.py` — new tests above.
- `CHANGELOG.md` — `[Unreleased]` entry.
- `README.md`, `TESTING.md` — document UserValves + at-rest encryption + the admin-global catalog limitation.

## Out of scope (YAGNI)

- Responses API, video, tool executor, artifact persistence (separate future threads).
- Encrypting non-key valves.
- Migrating already-stored plaintext keys (they keep working; re-save re-encrypts).

## Risks

- Threading touches ~8 method signatures — mechanical but a wide diff. Mitigated by full test coverage of the request path.
- Full-prefs `UserValves` ≈ 40 mirrored Optional fields — verbose; accepted for user flexibility.
