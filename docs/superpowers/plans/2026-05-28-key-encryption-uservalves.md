# Key Encryption + UserValves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the pipe safe on shared multi-user Open WebUI instances by encrypting the API key at rest and adding per-user configuration overrides.

**Architecture:** Add a module-level `EncryptedStr` (Fernet, soft-imported `cryptography`, plaintext fallback). Refactor the per-request call path to take an explicit `valves` argument (no mutation of the shared `self.valves`). Add a nested `UserValves` of chat-path fields and a concurrency-safe `_effective_valves(__user__)` merge that `pipe()` threads downstream.

**Tech Stack:** Python 3, `requests`, `pydantic` v2, optional `cryptography` (bundled by OWUI). Tests: hand-rolled `_assert`/`_section` harness in `test_pipe.py`, run via `python test_pipe.py`. Lint: `pyflakes`.

---

## Critical conventions (read first)

- **Tests are NOT pytest.** `test_pipe.py` is a flat script. You add a `_section("...")` header then `_assert(condition, "message")` lines. Running `python test_pipe.py` runs the whole file and prints a pass/fail tally that must end with `0` failures. The module under test is loaded as `mod`, and symbols are bound near the top (e.g. `Pipe = mod.Pipe`).
- **Never mutate `self.valves`** in the request path. The `Pipe` instance is shared across users and concurrent requests; mutating it leaks one user's config/key into another's request. Always operate on the per-request `valves` argument.
- **`pipes()` (model listing) has no user context.** OWUI calls it without `__user__`, so it stays on `self.valves` / the admin key. Per-user overrides apply to the chat path only. This is intentional and documented.
- The encrypted-value marker prefix is the literal string `encrypted:`. Real OpenRouter keys start with `sk-or-`, so plaintext never collides.
- `WEBUI_SECRET_KEY` is the env var OWUI sets; the Fernet key is derived from it.

---

## File Structure

- `openrouter_pipe.py` — all code changes (module-level `EncryptedStr`, threading refactor, `UserValves`, `_effective_valves`, version, docstring).
- `function.json` — mirror version + description.
- `test_pipe.py` — new `_section` + `_assert` blocks.
- `CHANGELOG.md` — `[Unreleased]` entry.
- `README.md`, `TESTING.md` — document encryption + UserValves + the admin-global catalog limitation.
- `requirements.txt` — unchanged (soft dependency).

---

## Task 1: EncryptedStr (module-level, unused for now)

**Files:**
- Modify: `openrouter_pipe.py` — imports block (~line 14-25) and a new class after the module constants, before `class Pipe` (~line 250).
- Test: `test_pipe.py` — add a new section.

- [ ] **Step 1: Add the failing test**

In `test_pipe.py`, after the existing symbol bindings near line 47, add:

```python
EncryptedStr = mod.EncryptedStr
```

Then append a new section at the end of the file, before the final tally/print:

```python
# ── EncryptedStr ──────────────────────────────────────────────────────────────

_section("EncryptedStr key-at-rest")

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _ct = EncryptedStr.encrypt("sk-or-v1-abcdef")
    _assert(_ct.startswith("encrypted:"), "encrypt() tags ciphertext with prefix")
    _assert(_ct != "sk-or-v1-abcdef", "encrypt() does not return plaintext")
    _assert(
        EncryptedStr.decrypt(_ct) == "sk-or-v1-abcdef",
        "decrypt() round-trips back to original",
    )
    _assert(
        EncryptedStr.encrypt(_ct) == _ct,
        "encrypt() is idempotent on already-encrypted input",
    )
    _assert(
        EncryptedStr.decrypt("sk-or-v1-plain") == "sk-or-v1-plain",
        "decrypt() passes through non-prefixed legacy plaintext",
    )
    _assert(EncryptedStr.encrypt("") == "", "encrypt() of empty string is empty")
    _assert(
        EncryptedStr.decrypt("encrypted:not-a-valid-token") == "encrypted:not-a-valid-token",
        "decrypt() returns corrupt/foreign token unchanged (never raises)",
    )

with patch.dict(os.environ, {}, clear=True):
    _assert(
        EncryptedStr.encrypt("sk-or-v1-x") == "sk-or-v1-x",
        "no WEBUI_SECRET_KEY → encrypt() is a plaintext no-op",
    )
    _assert(
        EncryptedStr.decrypt("sk-or-v1-x") == "sk-or-v1-x",
        "no WEBUI_SECRET_KEY → decrypt() is a plaintext no-op",
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_pipe.py`
Expected: FAIL — `AttributeError: module 'openrouter_pipe' has no attribute 'EncryptedStr'` at load (the `EncryptedStr = mod.EncryptedStr` binding raises).

- [ ] **Step 3: Add the import**

In `openrouter_pipe.py`, add `import base64` to the stdlib import block (keep alphabetical: after `import copy` is fine — exact placement isn't load-bearing, but put it before `import hashlib`). The block becomes:

```python
import base64
import copy
import hashlib
import json
import os
import random
import re
import time
import traceback
```

- [ ] **Step 4: Add the EncryptedStr class**

In `openrouter_pipe.py`, immediately before `class Pipe:` (line ~250), add:

```python
# Optional dependency: Open WebUI bundles `cryptography`. When absent (e.g. the
# pipe is imported in a bare environment) the key degrades to plaintext storage
# rather than failing — see EncryptedStr.
try:
    from cryptography.fernet import Fernet as _Fernet
except Exception:  # pragma: no cover - exercised only without cryptography
    _Fernet = None

_ENC_PREFIX = "encrypted:"
_ENC_WARNED = False


class EncryptedStr(str):
    """A valve value encrypted at rest in Open WebUI's database.

    Ciphertext is tagged with the ``encrypted:`` prefix. Real OpenRouter keys
    begin ``sk-or-`` so plaintext never collides with the marker. The Fernet key
    is derived from ``WEBUI_SECRET_KEY``. When that env var is missing, or the
    ``cryptography`` package is unavailable, values are stored and returned as
    plaintext (with a one-time warning) so the pipe keeps working.
    """

    @staticmethod
    def _fernet():
        global _ENC_WARNED
        secret = os.getenv("WEBUI_SECRET_KEY")
        if not secret or _Fernet is None:
            if not _ENC_WARNED:
                _ENC_WARNED = True
                reason = "WEBUI_SECRET_KEY not set" if not secret else "cryptography not installed"
                print(f"[OpenRouter Pipe] API key stored in plaintext ({reason})")
            return None
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return _Fernet(key)

    @classmethod
    def encrypt(cls, value: str) -> str:
        if not value or value.startswith(_ENC_PREFIX):
            return value
        fernet = cls._fernet()
        if fernet is None:
            return value
        return _ENC_PREFIX + fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, value: str) -> str:
        if not value or not value.startswith(_ENC_PREFIX):
            return value
        fernet = cls._fernet()
        if fernet is None:
            return value
        try:
            token = value[len(_ENC_PREFIX):].encode("utf-8")
            return fernet.decrypt(token).decode("utf-8")
        except Exception:
            return value
```

- [ ] **Step 5: Run to verify it passes**

Run: `python test_pipe.py`
Expected: PASS — the `EncryptedStr key-at-rest` section shows all ✓, final tally `0` failures.

- [ ] **Step 6: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: add EncryptedStr for at-rest API key encryption"
```

---

## Task 2: Thread `valves` through the request path (no-op refactor)

This is a pure refactor: every request-path method takes an explicit `valves` argument and reads it instead of `self.valves`. Call sites pass `self.valves`, so behavior is identical and all existing tests stay green. This isolates the wide mechanical change before any encryption/merge logic depends on it.

**Files:**
- Modify: `openrouter_pipe.py` — methods `_build_web_search_plugin`, `_prepare_payload`, `_inject_cache_control`, `_resolve_referer`, `_build_headers`, `_non_stream_response`, `_stream_response`, `_retryable_request`; call sites in `pipe()` and `pipes()`.

- [ ] **Step 1: Update method signatures and bodies**

Apply each change exactly. For bodies, the mechanical rule is: **within the method, replace every `self.valves.` with `valves.`** and update internal helper calls as noted.

1. `_build_web_search_plugin` (line ~1335):
   - Signature → `def _build_web_search_plugin(self, valves) -> Optional[dict]:`
   - Body: replace every `self.valves.` with `valves.`

2. `_prepare_payload` (line ~1406):
   - Signature → `def _prepare_payload(self, body: dict, valves) -> dict:`
   - Body: replace every `self.valves.` with `valves.`
   - Update the web-search call: `web_plugin = self._build_web_search_plugin(valves)`
   - Update the cache-control call: `self._inject_cache_control(payload, valves)`

3. `_inject_cache_control` (line ~1538):
   - Signature → `def _inject_cache_control(self, payload: dict, valves) -> None:`
   - Body: replace `self.valves.` with `valves.`

4. `_resolve_referer` (line ~1578):
   - Signature → `def _resolve_referer(self, valves) -> str:`
   - Body: replace `self.valves.` with `valves.` (the `self._referer` fallback stays as-is)

5. `_build_headers` (line ~1593):
   - Signature → `def _build_headers(self, include_content_type: bool = True, *, model_id: Optional[str] = None, valves) -> dict:`
   - In the body, change the referer call to `self._resolve_referer(valves)`
   - Replace `self.valves.ENABLE_ANTHROPIC_INTERLEAVED_THINKING` with `valves.ENABLE_ANTHROPIC_INTERLEAVED_THINKING`
   - Leave the `Authorization` line reading `valves.OPENROUTER_API_KEY` for now (decrypt is added in Task 3):
     `"Authorization": f"Bearer {valves.OPENROUTER_API_KEY}",`

6. `_non_stream_response` (line ~1626):
   - Signature → `def _non_stream_response(self, headers: dict, payload: dict, valves) -> str:`
   - Body: replace every `self.valves.` with `valves.`
   - Update the request call: `self._retryable_request(headers, payload, stream=False, valves=valves)`

7. `_stream_response` (line ~1703):
   - Signature → `def _stream_response(self, headers: dict, payload: dict, valves) -> Generator[str, None, None]:`
   - Body: replace every `self.valves.` with `valves.`
   - Update the request call: `self._retryable_request(headers, payload, stream=True, valves=valves)`

8. `_retryable_request` (line ~1834):
   - Signature → `def _retryable_request(self, headers: dict, payload: dict, stream: bool, valves) -> requests.Response:`
   - Body: replace every `self.valves.` with `valves.`

- [ ] **Step 2: Update call sites**

In `pipes()` (line ~752), change:
```python
headers = self._build_headers(include_content_type=False, valves=self.valves)
```

In `pipe()` (lines ~973-994), change:
```python
payload = self._prepare_payload(body, self.valves)
headers = self._build_headers(model_id=payload.get("model"), valves=self.valves)
```
and:
```python
gen = self._stream_response(headers, payload, self.valves)
```
and:
```python
result = self._non_stream_response(headers, payload, self.valves)
```

- [ ] **Step 3: Run the full suite to verify no regression**

Run: `python test_pipe.py`
Expected: PASS — same totals as before this task (behavior unchanged), `0` failures.

- [ ] **Step 4: Lint**

Run: `python -m pyflakes openrouter_pipe.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add openrouter_pipe.py
git commit -m "refactor: thread explicit valves through request path"
```

---

## Task 3: Encrypt the admin key at rest + decrypt at use

**Files:**
- Modify: `openrouter_pipe.py` — admin `Valves` (add validator), `_build_cache_key` (decrypt for hash), `_build_headers` (decrypt for Authorization).
- Test: `test_pipe.py` — new section.

- [ ] **Step 1: Add the failing test**

Append to `test_pipe.py`:

```python
# ── Admin key encryption wiring ────────────────────────────────────────────────

_section("Admin key encrypted at rest, decrypted on use")

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _p = Pipe()
    _p.valves.OPENROUTER_API_KEY = mod.EncryptedStr.encrypt("sk-or-v1-secret")
    _assert(
        _p.valves.OPENROUTER_API_KEY.startswith("encrypted:"),
        "stored admin key is ciphertext",
    )
    _hdrs = _p._build_headers(valves=_p.valves)
    _assert(
        _hdrs["Authorization"] == "Bearer sk-or-v1-secret",
        "Authorization header carries the decrypted key",
    )

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _p2 = Pipe()
    _v = Pipe.Valves(OPENROUTER_API_KEY="sk-or-v1-fromctor")
    _assert(
        _v.OPENROUTER_API_KEY.startswith("encrypted:"),
        "Valves constructor encrypts the key via field_validator",
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_pipe.py`
Expected: FAIL — `Authorization` assert fails (`Bearer encrypted:...` ≠ `Bearer sk-or-v1-secret`) and the constructor-encryption assert fails (plaintext, no validator yet).

- [ ] **Step 3: Add the encrypt-on-store validator to admin Valves**

In `openrouter_pipe.py`, inside `class Valves` (after the `_validate_base_url` validator at line ~659-665), add:

```python
        @field_validator("OPENROUTER_API_KEY")
        @classmethod
        def _encrypt_api_key(cls, v: str) -> str:
            return EncryptedStr.encrypt(v or "")
```

- [ ] **Step 4: Decrypt at the two use points**

In `_build_cache_key` (line ~716-718), change the hash source to the decrypted key:
```python
        _resolved_key = EncryptedStr.decrypt(self.valves.OPENROUTER_API_KEY or "")
        api_key_hash = (
            hashlib.sha256(_resolved_key.encode("utf-8")).hexdigest()[:16]
            if _resolved_key
            else ""
        )
```

In `_build_headers` (line ~1606), change the Authorization line to decrypt:
```python
            "Authorization": f"Bearer {EncryptedStr.decrypt(valves.OPENROUTER_API_KEY or '')}",
```

- [ ] **Step 5: Run to verify it passes**

Run: `python test_pipe.py`
Expected: PASS — new section all ✓, `0` failures. (The empty-key guards in `pipe()`/`pipes()` still work: an encrypted non-empty string is truthy; an empty key stays empty.)

- [ ] **Step 6: Lint**

Run: `python -m pyflakes openrouter_pipe.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: encrypt admin OpenRouter key at rest, decrypt on use"
```

---

## Task 4: UserValves + per-user effective-valves merge

**Files:**
- Modify: `openrouter_pipe.py` — add nested `UserValves`, add `_effective_valves`, wire `pipe()` to compute and thread `eff`.
- Test: `test_pipe.py` — new section.

- [ ] **Step 1: Add the failing test**

Append to `test_pipe.py`:

```python
# ── UserValves + effective-valves merge ────────────────────────────────────────

_section("UserValves merge + per-user key")

with patch.dict(os.environ, {"WEBUI_SECRET_KEY": "unit-test-secret"}):
    _p = Pipe()
    _p.valves.REASONING_EFFORT = "low"
    _p.valves.ENABLE_MIDDLE_OUT = True

    # No __user__ → effective == admin
    _eff0 = _p._effective_valves(None)
    _assert(_eff0.REASONING_EFFORT == "low", "no user → admin value preserved")

    # None field inherits admin; set field overrides; False overrides True
    _uv = Pipe.UserValves(REASONING_EFFORT="high", ENABLE_MIDDLE_OUT=False)
    _eff = _p._effective_valves({"valves": _uv})
    _assert(_eff.REASONING_EFFORT == "high", "user value overrides admin")
    _assert(_eff.ENABLE_MIDDLE_OUT is False, "user False overrides admin True")
    _assert(
        _eff.SERVICE_TIER == _p.valves.SERVICE_TIER,
        "unset (None) user field inherits admin default",
    )
    _assert(
        _p.valves.REASONING_EFFORT == "low",
        "merge does not mutate shared self.valves",
    )

    # Per-user API key flows into the Authorization header
    _uvk = Pipe.UserValves(OPENROUTER_API_KEY="sk-or-v1-userkey")
    _effk = _p._effective_valves({"valves": _uvk})
    _hdrs = _p._build_headers(valves=_effk)
    _assert(
        _hdrs["Authorization"] == "Bearer sk-or-v1-userkey",
        "per-user key decrypted into Authorization header",
    )

    # Dict-form user valves also supported
    _effd = _p._effective_valves({"valves": {"REASONING_EFFORT": "medium"}})
    _assert(_effd.REASONING_EFFORT == "medium", "dict-form user valves merge")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_pipe.py`
Expected: FAIL — `AttributeError`/`TypeError`: `Pipe` has no `UserValves` / no `_effective_valves`.

- [ ] **Step 3: Add the UserValves class**

In `openrouter_pipe.py`, inside `class Pipe`, immediately after the admin `Valves` class closes (after the `_encrypt_api_key` validator, before `def __init__` at line ~667), add. Every field is `Optional[...] = None` meaning "inherit admin". Only chat-path fields are mirrored — catalog/display fields (`MODEL_PROVIDERS`, `FREE_MODEL_FILTER`, `TOOL_CALLING_FILTER`, `MODEL_VARIANTS`, `MODEL_CATEGORY`, `HIDE_DEPRECATED_MODELS`, `OUTPUT_MODALITIES`, `MODEL_PREFIX`, `INVERT_PROVIDER_LIST`, `ZDR_MODELS_ONLY`, `SYNC_PROVIDER_ICONS`, `USE_GSTATIC_FAVICONS`, `OPENROUTER_BASE_URL`) are deliberately omitted because they are only read in `pipes()`, which has no user context.

```python
    class UserValves(BaseModel):
        """Per-user overrides. Each field defaults to None = inherit the admin
        Valves value. Only chat-path settings are exposed; catalog/display
        settings are admin-global because the model list has no user context.
        """

        OPENROUTER_API_KEY: Optional[str] = Field(
            default=None,
            description="Your personal OpenRouter API key. Leave blank to use the admin key.",
            json_schema_extra={"input": {"type": "password"}},
        )
        INCLUDE_REASONING: Optional[bool] = None
        REASONING_EFFORT: Optional[str] = None
        REASONING_SUMMARY_MODE: Optional[str] = None
        REASONING_MAX_TOKENS: Optional[int] = Field(default=None, ge=0)
        ENABLE_ANTHROPIC_INTERLEAVED_THINKING: Optional[bool] = None
        SERVICE_TIER: Optional[str] = None
        PROVIDER_SORT: Optional[str] = None
        PROVIDER_ORDER: Optional[str] = None
        PROVIDER_IGNORE: Optional[str] = None
        PROVIDER_ONLY: Optional[str] = None
        PROVIDER_QUANTIZATIONS: Optional[str] = None
        PROVIDER_ALLOW_FALLBACKS: Optional[bool] = None
        PROVIDER_MAX_PRICE_PROMPT: Optional[str] = None
        PROVIDER_MAX_PRICE_COMPLETION: Optional[str] = None
        REQUIRE_PARAMETERS: Optional[bool] = None
        DATA_COLLECTION: Optional[str] = None
        ZDR_ENFORCE: Optional[bool] = None
        FALLBACK_MODELS: Optional[str] = None
        ENABLE_MIDDLE_OUT: Optional[bool] = None
        ENABLE_WEB_SEARCH: Optional[bool] = None
        WEB_SEARCH_MAX_RESULTS: Optional[int] = Field(default=None, ge=1, le=20)
        WEB_SEARCH_PROMPT: Optional[str] = None
        WEB_SEARCH_INCLUDE_DOMAINS: Optional[str] = None
        WEB_SEARCH_EXCLUDE_DOMAINS: Optional[str] = None
        ENABLE_CACHE_CONTROL: Optional[bool] = None
        ANTHROPIC_PROMPT_CACHE_TTL: Optional[str] = None
        HTTP_REFERER_OVERRIDE: Optional[str] = None
        REQUEST_TIMEOUT: Optional[int] = Field(default=None, gt=0)
        MAX_RETRIES: Optional[int] = Field(default=None, ge=0)
        SHOW_COST_INFO: Optional[bool] = None
        SHOW_GENERATION_ID: Optional[bool] = None
        COST_CURRENCY: Optional[str] = None

        @field_validator("OPENROUTER_API_KEY")
        @classmethod
        def _encrypt_user_api_key(cls, v):
            return EncryptedStr.encrypt(v) if v else v
```

- [ ] **Step 4: Add the _effective_valves merge**

In `openrouter_pipe.py`, add this method to `class Pipe` (place it just before `def pipe(` at line ~938):

```python
    def _effective_valves(self, __user__):
        """Return a per-request copy of admin valves with user overrides applied.

        Never mutates self.valves (shared across users/requests). A user field
        of None means "inherit the admin value".
        """
        eff = self.valves.model_copy()
        user = __user__ or {}
        uv = user.get("valves") if isinstance(user, dict) else None
        if uv is None:
            return eff
        data = uv.model_dump() if hasattr(uv, "model_dump") else dict(uv)
        for key, val in data.items():
            if val is not None and hasattr(eff, key):
                setattr(eff, key, val)
        return eff
```

- [ ] **Step 5: Wire pipe() to use effective valves**

In `pipe()` (line ~938-994), compute `eff` as the **first statement** of the method body (immediately after the docstring), so the existing guard order is preserved. Change the existing empty-key guard (line ~949) to read from `eff`, then change the downstream call sites.

Make `eff` the first line:
```python
        eff = self._effective_valves(__user__)
```

Change the existing key guard at line ~949 from `self.valves.OPENROUTER_API_KEY` to `eff.OPENROUTER_API_KEY`:
```python
        if not eff.OPENROUTER_API_KEY:
            return "OpenRouter Error: OPENROUTER_API_KEY not configured. Set it in Settings → Connections."
```
(`eff` already contains the admin key when the user sets none, so this guard still fires correctly.)

Then change the three downstream calls to pass `eff` instead of `self.valves`:
```python
        payload = self._prepare_payload(body, eff)
        headers = self._build_headers(model_id=payload.get("model"), valves=eff)
```
```python
            gen = self._stream_response(headers, payload, eff)
```
```python
        result = self._non_stream_response(headers, payload, eff)
```

Leave the `model_id == "error"` and `not body.get("messages")` guards exactly where they are — only the key guard's source changes.

- [ ] **Step 6: Run to verify it passes**

Run: `python test_pipe.py`
Expected: PASS — `UserValves merge + per-user key` section all ✓, `0` failures.

- [ ] **Step 7: Lint**

Run: `python -m pyflakes openrouter_pipe.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add openrouter_pipe.py test_pipe.py
git commit -m "feat: add per-user UserValves with concurrency-safe merge"
```

---

## Task 5: Version bump, docstring, function.json mirror

**Files:**
- Modify: `openrouter_pipe.py` (version line, module docstring), `function.json`.

- [ ] **Step 1: Bump the version in the module header**

In `openrouter_pipe.py` line 6, change `version: 1.6.1` to `version: 1.7.0`.

- [ ] **Step 2: Extend the module docstring description**

In `openrouter_pipe.py` line 11 (the `description:` line), append this sentence before the closing period/quote: ` Per-user API keys and preferences via UserValves, with at-rest key encryption (Fernet, keyed on WEBUI_SECRET_KEY).`

- [ ] **Step 3: Mirror in function.json**

Run: `grep -n "1.6.1" function.json`
For each match, replace `1.6.1` with `1.7.0`. If `function.json` embeds the description string, append the same sentence as Step 2 so the two stay in sync.

- [ ] **Step 4: Verify nothing else references the old version**

Run: `grep -rn "1\.6\.1" openrouter_pipe.py function.json`
Expected: no matches (or only unrelated matches you can confirm are not the version).

- [ ] **Step 5: Run the suite + lint**

Run: `python test_pipe.py` → `0` failures.
Run: `python -m pyflakes openrouter_pipe.py` → no output.

- [ ] **Step 6: Commit**

```bash
git add openrouter_pipe.py function.json
git commit -m "chore: bump to v1.7.0, document encryption + UserValves"
```

---

## Task 6: Documentation

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `TESTING.md`.

- [ ] **Step 1: Add a CHANGELOG entry**

In `CHANGELOG.md`, under the `[Unreleased]` heading (add an `### Added` subsection if absent):

```markdown
### Added
- Per-user configuration via `UserValves`: each user can set their own OpenRouter API key and chat-path preferences (reasoning, provider routing, web search, fallbacks, cost display, etc.), overriding admin defaults. Catalog/display settings remain admin-global because the model list has no per-user context.
- At-rest encryption of the OpenRouter API key (`EncryptedStr`, Fernet keyed on `WEBUI_SECRET_KEY`). `cryptography` is soft-imported — when it or `WEBUI_SECRET_KEY` is unavailable the key falls back to plaintext storage with a warning. Existing plaintext keys keep working and are re-encrypted on next save.
```

- [ ] **Step 2: Document in README.md**

Add a short subsection (near the configuration/valves docs) explaining: per-user keys/prefs via UserValves, that catalog filters are admin-global, and that the admin key is encrypted at rest when `WEBUI_SECRET_KEY` is set. Keep it factual, no new claims beyond what the code does.

- [ ] **Step 3: Document in TESTING.md**

Add the new test sections (`EncryptedStr key-at-rest`, `Admin key encrypted at rest`, `UserValves merge + per-user key`) to the section inventory, and bump the stated total test count to the new number printed by `python test_pipe.py`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md TESTING.md
git commit -m "docs: document UserValves and at-rest key encryption"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full suite**

Run: `python test_pipe.py`
Expected: final line reports `0` failures; note the new total count.

- [ ] **Step 2: Lint**

Run: `python -m pyflakes openrouter_pipe.py test_pipe.py`
Expected: no output.

- [ ] **Step 3: Plaintext-fallback smoke check**

Run:
```bash
python -c "import os; os.environ.pop('WEBUI_SECRET_KEY', None); import importlib.machinery, importlib.util; l=importlib.machinery.SourceFileLoader('op','openrouter_pipe.py'); s=importlib.util.spec_from_loader('op',l); m=importlib.util.module_from_spec(s); l.exec_module(m); print(m.EncryptedStr.encrypt('sk-or-v1-x'))"
```
Expected: prints `sk-or-v1-x` (plaintext no-op) and a one-time plaintext warning.

- [ ] **Step 4: Confirm working tree is clean / changes committed**

Run: `git status`
Expected: no uncommitted changes from this plan (pre-existing unrelated modified files may remain — do not sweep them into these commits).

---

## Self-review notes (already applied)

- **Spec coverage:** EncryptedStr (Task 1+3), encrypt-on-store validator (Task 3), UserValves full chat-path mirror (Task 4), concurrency-safe merge (Task 4), threading (Task 2), version/docstring/function.json (Task 5), tests (every task), docs (Task 6), requirements unchanged (stated). The admin-global `pipes()` limitation is documented (Task 6) and enforced by design (no user context there).
- **Refinement vs spec:** the spec said "full preference mirror"; this plan scopes UserValves to chat-path fields only and explicitly omits catalog/display fields, because overriding those per-user would be dead config (they're read only in `pipes()`). This is the faithful interpretation of "let each user control their own requests".
- **Test harness:** corrected from the spec's "pytest" assumption to the actual `_assert`/`_section` script.
- **Type consistency:** `valves` is the parameter name everywhere; `EncryptedStr.encrypt`/`.decrypt` and `_effective_valves` signatures match across tasks.
