# Changelog

All notable changes to **OpenRouter Pipe** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`RESPONSE_FORMAT` + `TOOL_CHOICE` valves** — force a JSON output mode (`json_object`) and/or set a default `tool_choice` (`none`/`auto`/`required`) when the request doesn't specify one; the request body's own values always win. Both mirrored in `UserValves`
- **Explicit usage accounting + user attribution** — when `SHOW_COST_INFO` is on, the pipe requests `usage: {include: true}` so cost/credit footers aren't blank when OpenRouter omits usage; the Open WebUI `user` object is now forwarded to OpenRouter as its id string (for abuse tracking) instead of being dropped

### Fixed

- `integration_test.py` calls updated for the v1.7 `valves`-threaded method signatures
- Remaining-credit footer now also shown on the plain streaming path; tool-iteration cap note no longer appended to error responses
- Fractional `Retry-After` values are now honored (previously truncated to whole seconds); the per-key credit cache is now bounded; the ZDR-capable model list refreshes hourly instead of caching for the whole process lifetime

### Changed

- Blocking retry waits and streaming pulls now run off the asyncio event loop (via `asyncio.to_thread`) so a slow `Retry-After` no longer stalls other users

### Security

- Sanitized `X-Title`/`HTTP-Referer` (CR/LF/NUL) and the "Responded by"/citation footers (markdown injection)
- Restricted `data:image` model output to raster subtypes with a size cap
- `EncryptedStr.decrypt` now returns empty (not ciphertext) on failure so a rotated `WEBUI_SECRET_KEY` never sends a stale token

## [1.8.1] — 2026-05-29

### Changed

- **Transient-failure retries + clearer errors** — HTTP 429 (rate limit) and 5xx (500/502/503/504) are now retried within the existing `MAX_RETRIES` budget, honoring the `Retry-After` header (integer seconds or HTTP-date, capped at 60s) when present, otherwise exponential backoff. Non-transient 4xx still fail fast. Added specific error messages for HTTP 404/408/413/500/502/503/504

## [1.8.0] — 2026-05-28

### Added

- **Native function/tool calling** — `pipe()` now accepts OWUI `__tools__`, forwards them to OpenRouter, and runs the execute→re-request loop in both streaming and non-streaming modes. Tool calls execute in parallel; sync and async tool callables are supported; tool errors are fed back to the model rather than crashing the turn. New `MAX_TOOL_ITERATIONS` valve (default 5) caps runaway loops. Prompt-based tool mode (handled by OWUI) is unaffected
- **Remaining-credit footer** — opt-in `SHOW_REMAINING_CREDIT` valve appends your remaining OpenRouter credit after the cost line, via a cached (~60s, per-key) `GET /credits` call. Independent of `SHOW_COST_INFO`; fails silently (line omitted) if the balance can't be fetched

## [1.7.0] — 2026-05-28

### Added

- **`USE_GSTATIC_FAVICONS` valve (default off)** — registry-discovered Google `t0.gstatic.com` favicons are now opt-in. When off, providers only resolvable via gstatic fall back to OWUI's default icon, so the browser never leaks the provider domain to Google on every model render. The gstatic icon classifier was also tightened to require a query string, so a user-set bare gstatic URL is no longer misclassified as pipe-managed
- **Per-user configuration (`UserValves`)** — each Open WebUI user can now set their own OpenRouter API key and chat-path preferences (reasoning, provider routing, web search, fallbacks, service tier, cache control, referer, timeout, retries, cost display), overriding the admin defaults per request. Unset fields inherit the admin value. Catalog/display settings (model filters, prefix, icons, base URL) remain admin-global because the model list has no per-user context. The merge is concurrency-safe — it copies the admin valves per request and never mutates shared state, so users cannot leak settings or keys into each other's requests
- **At-rest API key encryption (`EncryptedStr`)** — the OpenRouter API key (admin and per-user) is now stored encrypted in Open WebUI's database (Fernet, keyed on `WEBUI_SECRET_KEY`) and decrypted only at the moment it is used. `cryptography` is soft-imported: when it or `WEBUI_SECRET_KEY` is unavailable the key falls back to plaintext storage with a one-time warning, so existing installs keep working. Legacy plaintext keys are read transparently and re-encrypted on the next save

### Changed

- **`FREE_MODEL_FILTER` honours the legacy `OPENROUTER_FREE_ONLY` env var** — when `OPENROUTER_FREE_MODEL_FILTER` is unset, `OPENROUTER_FREE_ONLY=true` now maps to `only`, so installs upgrading from the pre-1.5 `FREE_ONLY` era don't silently start returning paid models
- **`SERVICE_TIER` restricted to OpenRouter's documented values** — only `flex` and `priority` are forwarded now (verified against OpenRouter's API docs). The previously-offered OpenAI-direct tiers `auto`/`default`/`scale` are not valid on OpenRouter and are no longer sent or shown in the valve dropdown

### Fixed

- **Version metadata** — `function.json` reported `1.6.0` while the code was `1.6.1`; bumped the manifest version (and `updated_at`) to match
- **Docs: `FREE_ONLY` → `FREE_MODEL_FILTER`** — README and TESTING.md still referenced the removed `FREE_ONLY` valve; updated all references, added a migration note, documented the missing `SHOW_COST_INFO` / `COST_CURRENCY` valves, and corrected the test counts

### Security

- **No redirect following on any OpenRouter call** — `allow_redirects=False` is now passed to all four HTTP requests (`/models`, `/chat/completions`, the provider-registry fetch, and the ZDR `/endpoints/zdr` fetch). Combined with the `requests>=2.32.4` floor, this prevents the `Authorization: Bearer` header from being forwarded to a redirect target (CVE-2024-35195 family) if the base URL is misconfigured
- **`HTTP_REFERER_OVERRIDE` header-injection guard** — the referer override is rejected if it contains CR/LF/NUL control characters, so a misconfigured valve cannot split the request headers
- **Generation-ID markdown sanitization** — `_format_generation_id` strips backticks/newlines from the upstream generation ID before wrapping it in a code span, so a malicious upstream value cannot break out and inject markdown into the rendered response

## [1.6.1] — 2026-05-08

### Fixed

- **Provider icon lookup order** — `_get_provider_icon` now consults the dynamic OpenRouter registry first and falls back to the hardcoded `_PROVIDER_ICONS` dict only when the registry is unavailable. Previously the hardcoded dict always took priority, meaning any CDN path change on OpenRouter's side would silently serve 404 URLs for the 13 built-in providers while the registry (which always has correct current URLs) was ignored for them.
- **Provider registry now refreshes hourly** — `_load_provider_registry` previously cached the result for the entire lifetime of the `Pipe` instance. A transient network failure at startup (API down, rate-limited, not yet reachable) would permanently leave the registry empty until the pipe was restarted. Now the cache expires after `_PROVIDER_REGISTRY_TTL` (1 hour) and a fresh fetch is attempted automatically.
- **Non-200 registry responses now logged** — HTTP 4xx/5xx responses from `GET /api/frontend/all-providers` were previously swallowed silently, making it impossible to diagnose why icons were missing. A `[OpenRouter Pipe] Provider registry returned HTTP {status}` message is now printed.
- **`_icons_synced` cleared on model cache refresh** — the set of "already synced" model IDs was never reset between 5-minute model-cache cycles. OWUI upserts models (resetting their `profile_image_url` to the default `data:` icon) after every `pipes()` call; the permanent `_icons_synced` state meant the corrective re-sync was never retried. The set is now cleared whenever the model cache is refreshed, so any OWUI-overwritten icon is restored on the next sync pass.

## [1.6.0] — 2026-05-08

### Added

- **Web search plugin** — five new valves (`ENABLE_WEB_SEARCH`, `WEB_SEARCH_MAX_RESULTS`, `WEB_SEARCH_PROMPT`, `WEB_SEARCH_INCLUDE_DOMAINS`, `WEB_SEARCH_EXCLUDE_DOMAINS`) attach OpenRouter's `web` plugin to every request so any model can ground answers in fresh web results, with domain allow/deny lists and a custom search prompt
- **`MODEL_CATEGORY` valve** — server-side `?category=...` filter on `/models` (e.g. `programming`, `roleplay`, `marketing`, `science`, `legal`, `finance`, `health`, `academia`)
- **Deprecation handling** — models with a non-null `expiration_date` are tagged `⚠ {name} (deprecated)` in the selector. New `HIDE_DEPRECATED_MODELS` valve removes them entirely
- **`REASONING_MAX_TOKENS` valve** — hard cap on reasoning tokens per response (sent as `reasoning.max_tokens`) for budget control on deep-thinking models
- **Provider preferences extras** — `PROVIDER_ONLY` (allowlist), `PROVIDER_QUANTIZATIONS` (e.g. `bf16,fp8`), `PROVIDER_ALLOW_FALLBACKS`, `PROVIDER_MAX_PRICE_PROMPT`, `PROVIDER_MAX_PRICE_COMPLETION`. Translates to `provider.only/quantizations/allow_fallbacks/max_price` per the OpenRouter SDK schema
- **`SERVICE_TIER` valve** — OpenAI-style tier hint (`auto`/`default`/`flex`/`priority`/`scale`) forwarded to compatible providers
- **`SHOW_GENERATION_ID` valve** — captures the `id` field from chat-completion responses (works in both streaming and non-streaming modes) and appends `*Generation ID: gen-…*` so users can later call `GET /api/v1/generation?id={id}` for audit trails and per-request usage details
- **Cached prompt-token cost breakdown** — when the provider reports `prompt_tokens_details.cached_tokens` (Anthropic prompt caching, OpenAI implicit caching, Gemini context caching), the `SHOW_COST_INFO` footer splits out cached vs. non-cached prompt tokens so users can see the savings (Anthropic caches save up to 90% on input cost)
- **`_build_web_search_plugin()`**, **`_format_generation_id()`** — new helpers on `Pipe`

### Changed

- Model-list cache fingerprint now also includes `MODEL_CATEGORY` and `HIDE_DEPRECATED_MODELS` so toggling either invalidates the cached list
- `pipes()` now sends `params={"output_modalities": ..., "category": ...}` when a category is set
- `_prepare_payload()` now emits `service_tier`, `provider.only`, `provider.quantizations`, `provider.allow_fallbacks=false`, `provider.max_price.{prompt,completion}`, `reasoning.max_tokens`, and a `web` entry in `plugins` (without overwriting any user-supplied plugins)

## [1.5.0] — 2026-05-07

### Added

- **Variant model routing** — new `MODEL_VARIANTS` valve (env: `OPENROUTER_MODEL_VARIANTS`). Comma-separated `base_id:variant` entries surface as virtual catalog rows that inherit the base model's display name and provider icon while OpenRouter routes the suffixed ID via its variant logic. Recognised tags: `free`, `thinking`, `online`, `nitro`, `exacto`, `extended`. Example: `MODEL_VARIANTS=openai/gpt-4o:nitro,anthropic/claude-3.5-sonnet:thinking`
- **Reasoning effort: `minimal` and `xhigh`** — extends `REASONING_EFFORT` with two new levels for fastest/maximum-depth thinking on supporting models
- **`REASONING_SUMMARY_MODE` valve** (env: `OPENROUTER_REASONING_SUMMARY_MODE`, default `disabled`) — requests a `reasoning.summary` block from supporting models. Options: `auto`, `concise`, `detailed`, `disabled`
- **Anthropic interleaved thinking** — new `ENABLE_ANTHROPIC_INTERLEAVED_THINKING` valve (default on, env: `OPENROUTER_ANTHROPIC_INTERLEAVED_THINKING`). When the selected model is `anthropic/...`, automatically injects the `anthropic-beta: interleaved-thinking-2025-05-14` header so Claude interleaves reasoning with tool use
- **`ANTHROPIC_PROMPT_CACHE_TTL` valve** (env: `OPENROUTER_ANTHROPIC_PROMPT_CACHE_TTL`, default `5m`) — extends `ENABLE_CACHE_CONTROL` so the ephemeral cache breakpoint can be set to either `5m` (default) or `1h` for longer cache lifetimes between turns
- **`TOOL_CALLING_FILTER` valve** (env: `OPENROUTER_TOOL_CALLING_FILTER`, default `all`) — catalog filter for tool-capable models. Options: `all`, `only`, `exclude`. Reads `supported_parameters` from `/models` and matches on `tools`/`tool_choice`
- **ZDR (Zero Data Retention) support** — two new valves: `ZDR_MODELS_ONLY` (catalog filter — fetches `/endpoints/zdr` and hides models without a ZDR-capable endpoint) and `ZDR_ENFORCE` (request-side — adds `provider.zdr=true` so OpenRouter rejects the call if no ZDR endpoint is available)
- **`HTTP_REFERER_OVERRIDE` valve** (env: `OPENROUTER_HTTP_REFERER`) — explicit override for the `HTTP-Referer` app-attribution header. Empty falls back to `WEBUI_URL` env or `http://localhost:3000`
- **`_load_zdr_model_ids()`**, **`_parse_variant_specs()`**, **`_expand_variant_models()`**, **`_resolve_referer()`**, **`_is_anthropic_model()`** — new instance methods on `Pipe`

### Changed

- **Breaking:** `FREE_ONLY` (boolean) replaced by **`FREE_MODEL_FILTER`** (env: `OPENROUTER_FREE_MODEL_FILTER`, default `all`). Options: `all`, `only`, `exclude`. Setups using `FREE_ONLY=true` should switch to `FREE_MODEL_FILTER=only`; setups using `FREE_ONLY=false` need no change
- **Reasoning payload shape:** when both `REASONING_EFFORT` and `REASONING_SUMMARY_MODE` are set, both fields are merged into the same `reasoning` object instead of overwriting
- Model-list cache fingerprint now also includes `FREE_MODEL_FILTER`, `TOOL_CALLING_FILTER`, `ZDR_MODELS_ONLY`, and `MODEL_VARIANTS` so toggling any of them invalidates the 5-minute cache
- `_build_headers()` accepts an optional `model_id` kwarg so it can decide whether to inject Anthropic-specific beta headers

## [1.4.0] — 2026-05-07

### Added

- **`OUTPUT_MODALITIES` valve** (env: `OPENROUTER_OUTPUT_MODALITIES`, default `all`) — controls which model output modalities are fetched from OpenRouter's `/models` endpoint. Accepts `text`, `image`, `audio`, `embeddings`, `all`, or a comma-separated combination
- **Full-catalog model listing** — TTS (e.g. `openai/gpt-4o-mini-tts-*`), audio-output, image-generation, and embedding models now appear in the Open WebUI model selector by default
- **Auto-discovered provider icons** — for providers not in the hardcoded fast-path dict, the pipe now lazy-loads OpenRouter's frontend provider registry (`/api/frontend/all-providers`) and resolves the icon from there. Adds icon coverage for ~20 additional model authors (xAI, Inflection, NVIDIA, Arcee, Morph, Cerebras, etc.) including gstatic favicons for providers without an OpenRouter-hosted logo. Slug normalization handles `x-ai` ↔ `xai` style mismatches
- **`_load_provider_registry()`** and **`_get_provider_icon()`** methods on `Pipe` — layered icon resolution: hardcoded dict → registry exact slug → registry hyphen-stripped slug. Network failures are silent (best-effort fallback)

### Changed

- The `/models` request now passes `output_modalities=all` by default, so the catalog is no longer silently restricted to text-output models. Set `OUTPUT_MODALITIES = text` to restore the previous chat-only behaviour
- Model-list cache fingerprint now includes `OUTPUT_MODALITIES`, so toggling the valve correctly invalidates the cached list
- `_is_owui_managed_icon()` now also recognises `https://t0.gstatic.com/faviconV2` URLs as pipe-managed, so registry-sourced gstatic favicons remain overwriteable when OpenRouter updates its provider mapping

## [1.3.0] — 2026-05-07

### Added

- **Automatic provider-icon sync** — new `_sync_model_icons()` method writes provider icons directly into Open WebUI's Models database so they appear in the UI; controlled by the `SYNC_PROVIDER_ICONS` valve (default: enabled). Models with a manually-set icon are never overwritten
- **`_is_owui_managed_icon()` helper** — distinguishes OWUI-default icons (`data:` URLs) and our own provider icons from user-set custom icons, enabling safe icon updates without clobbering user customisations
- **Audio output handling** — models that return audio (e.g. `openai/gpt-4o-audio-preview`) now have their transcript surfaced as text in both streaming and non-streaming responses
- **Image output handling** — models that return images (e.g. `google/gemini-2.5-flash-image-preview`) now embed valid HTTP/HTTPS image URLs as markdown, with a leading blank-line separator and URL validation to drop unsafe schemes
- **Token usage and cost display** — non-stream responses append a "Tokens: X in / Y out · Cost: $Z" footer when the OpenRouter response includes `usage` data
- **Connection pooling** via `requests.Session` for better performance across multiple API calls
- **Model list caching** with 5-minute TTL and valve-fingerprint invalidation — avoids redundant API calls when reopening the model selector
- **Exponential backoff with jitter** on transient errors (Timeout, ConnectionError) — `min(2^attempt + random, 30s)`
- **Fallback deduplication** — duplicate models in `FALLBACK_MODELS` are silently removed
- **Citation URL sanitization** — non-HTTP URLs are filtered out; parentheses in URLs are percent-encoded
- **Base URL validation** — `OPENROUTER_BASE_URL` must start with `https://` or `http://` (Pydantic field_validator)
- **"error" model guard** — selecting the error pseudo-model returns an actionable message instead of hitting the API
- **Empty messages guard** — returns a clear error if the message list is empty
- **Fallback model attribution** — non-stream responses show "Responded by: model-id" when a fallback model handled the request
- **HTTP 502 auth detection** — Clerk 502 errors (malformed API key) are now caught at model-list time

### Changed

- Minimum requirements bumped: `requests>=2.20`, `pydantic>=2.0`
- Error prefix changed from "OpenRouter Pipe Error" to "OpenRouter Error" for cleaner UX
- HTTP error messages now include specific guidance per status code (429=rate limit, 402=credits, 401=key, 403=access)
- Empty API response returns an informative message instead of an empty string
- Timeout error messages now show the configured timeout value and suggest increasing it
- Improved all valve descriptions for clarity and actionability
- Pre-flight `/auth/key` check removed — auth errors are now detected directly from the `/models` response (eliminates one HTTP round-trip)
- `_prepare_payload` uses `copy.deepcopy` instead of shallow `body.copy()` to prevent mutation of nested structures
- `_build_headers` uses cached env vars (`WEBUI_URL`, `WEBUI_NAME`) instead of calling `os.getenv()` on every request
- `FREE_ONLY` pricing comparison uses `float()` instead of string comparison
- Model cache key includes `MODEL_PREFIX` to prevent stale results after prefix changes
- Removed unused `_API_PATH_AUTH` constant and `auth_url` property
- Provider-icon catalogue trimmed to 13 verified providers (was previously documented as 22 but only 13 were ever defined in `_PROVIDER_ICONS`); tilde model filtering and model-ID stripping corrected at the same time

### Fixed

- **Icon sync: correct prefixed model IDs** — `_sync_model_icons()` now discovers the pipe's `function_id` via `type(self).__module__` and writes DB records with the full prefixed ID (e.g. `openrouter_pipe.openai/gpt-4o`) matching what Open WebUI's frontend requests at `/models/model/profile/image`
- **Icon sync: icons now actually appear in the UI** — five bugs prevented provider icons from ever showing after the first pipe load:
  - *Wrong skip condition* — `if existing_icon:` skipped any model with *any* icon (including the generic `data:` SVG that OWUI assigns by default), so provider icons were never applied; fixed to skip only user-set custom URLs
  - *Race condition* — `_sync_model_icons()` was called before `pipes()` returned, i.e. before OWUI registered the models; OWUI then overwrote the early insert with its own default icon; fixed by also calling `_sync_model_icons()` on cache-hit paths (until all models are confirmed synced)
  - *Exception swallowed retry* — DB errors added the model to `_icons_synced` anyway, permanently preventing retry; removed the erroneous add
  - *Insert marked as synced prematurely* — after `insert_new_model` the model was marked synced even though OWUI could overwrite it; the insert path no longer updates `_icons_synced`
  - *User params clobbered* — `update_model_by_id` used an empty `ModelParams()`, erasing user-configured temperature/system-prompt/etc.; now preserves `existing.params`
- **Icon sync: `function_id` cached at init** — `type(self).__module__` is evaluated once in `__init__` instead of on every `_sync_model_icons()` call
- **Streaming status event** — the "done" status event is now correctly emitted at the end of streaming responses (async generator wrapper replaces sync generator that could not `await`)
- **Dead provider-icon code removed** — `info.meta.profile_image_url` was included in model dicts returned by `pipes()` but Open WebUI ignores all fields except `id` and `name`; the field has been removed in favour of the new DB-sync approach
- **`pipes()` response always closed** — added `finally: response.close()` to guarantee HTTP connections are returned to the session pool in all code paths (auth errors, JSON decode failures, unexpected exceptions)
- **Image markdown safety** — image URLs are validated against `http://`/`https://` schemes before being embedded; invalid URLs are silently dropped instead of producing broken markdown
- Fixed potential payload mutation when `ENABLE_CACHE_CONTROL` is active (deepcopy prevents side effects)
- Fixed potential `IndexError` on stream chunks with empty `choices` array
- Fixed stream error handler not caching response body before closing connection
- Safe `isinstance(err, dict)` checks before calling `.get()` on error objects
- `_close_think_tag()` helper eliminates duplicated think-tag closure logic (was 5x repeated)
- `_stream_response` now closes the response in a `finally` block even on consumer `break`

## [1.2.0] — 2026-02-17

> Documented but never tagged on GitHub. The features below shipped to users via direct paste-install of `openrouter_pipe.py` and were rolled into the `v1.3.0` GitHub release.

### Added

- See `[1.3.0]` for the consolidated entry list. Original 1.2.0 scope: connection pooling, model list caching, exponential backoff with jitter, fallback deduplication, citation URL sanitization, base URL validation, "error" model guard, empty messages guard, fallback model attribution, HTTP 502 auth detection.

## [1.1.1] — 2026-02-17

### Changed

- Pre-compiled citation regex at module level for better performance
- Added docstrings to all public and internal methods (`pipe`, `_prepare_payload`, `_stream_response`, `_non_stream_response`, `_retryable_request`, `_build_headers`)
- Translated TESTING.md to English for international audience

### Fixed

- Test suite now runs on Windows without requiring `PYTHONUTF8=1` (UTF-8 stdout wrapper)
- Fixed stale test count in CONTRIBUTING.md and TESTING.md (170 → 193)
- Fixed typo in TESTING.md pre-release checklist
- Updated SECURITY.md to list v1.1.x as supported
- Updated `function.json` metadata date

## [1.1.0] — 2026-02-15

### Added

- Password-masked API key field in valve settings (Open WebUI v0.8+ feature)
- Native dropdown menus for Reasoning Effort, Provider Sort, and Data Collection valves
- Optional `__event_emitter__` support — shows "Querying OpenRouter..." status in chat UI
- Additional defensive keys (`metadata`, `files`, `tool_ids`, `session_id`, `message_id`) stripped from payload

## [1.0.0] — 2026-02-14

### Added

- Provider routing: sort by `price`/`throughput`/`latency`, preferred and ignored providers, `require_parameters`, data collection policy
- Model fallbacks via `models` array for automatic failover
- Middle-out compression (`transforms: ["middle-out"]`) for long prompts
- Anthropic-style `cache_control` injection on the longest message chunk
- Configurable reasoning effort (`low`, `medium`, `high`) and `<think>` tag support
- Payload sanitization — strips Open WebUI internal keys and dict-type `user` field
- Mid-stream SSE error handling with clean `<think>` block closure
- Auto-retry on timeout and connection errors (configurable `MAX_RETRIES`)
- 22 provider icons (OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, xAI, etc.)
- Citation injection — `[n]` references replaced with markdown links
- Pre-flight API key validation via `/auth/key` — invalid keys are caught at model listing, not at chat time
- Comprehensive test suite: 170 unit tests + 47 integration tests
- GitHub Actions CI pipeline (Python 3.10–3.13)
- Issue templates, security policy, and sponsor configuration

### Changed

- `pipe()` is now `async` with `__user__` parameter (Open WebUI v0.4+)
- `FREE_ONLY` checks for `:free` suffix instead of substring match
- Model ID prefix stripping uses `.split(".", 1)[-1]`

### Fixed

- Open WebUI internal keys no longer forwarded to OpenRouter API
- `user` field sent as dict no longer causes validation errors
- Stream parser no longer crashes on malformed JSON chunks
- HTTP error handler no longer crashes when response body is not JSON

## [0.1.0] — 2026-01-21

### Added

- Initial release
- Basic OpenRouter integration as Open WebUI manifold pipe
- Model listing with provider filtering (`MODEL_PROVIDERS`, `INVERT_PROVIDER_LIST`)
- Free-only model filtering
- Streaming and non-streaming chat completions
- Basic error handling and timeout configuration
- Model prefix customization

<!-- Compare links — only point to tags that exist on GitHub.
     v1.1.1 and v1.2.0 were documented but never tagged; their content is consolidated under v1.3.0. -->
[Unreleased]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.1.0...v1.3.0
[1.1.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/releases/tag/v0.1.0
