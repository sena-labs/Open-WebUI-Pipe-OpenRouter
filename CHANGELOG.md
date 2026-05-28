# Changelog

All notable changes to **OpenRouter Pipe** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Automatic provider-icon sync** — new `_sync_model_icons()` method writes provider icons directly into Open WebUI's Models database so they appear in the UI; controlled by the `SYNC_PROVIDER_ICONS` valve (default: enabled). Models with a manually-set icon are never overwritten
- **`_is_owui_managed_icon()` helper** — distinguishes OWUI-default icons (`data:` URLs) and our own provider icons from user-set custom icons, enabling safe icon updates without clobbering user customisations
- **`_md_escape_url()` helper** — percent-encodes markdown-breaking characters (`(`, `)`, `[`, `]`, `<`, `>`, whitespace) in citation and image URLs so prompt-injected URLs cannot break out of the `[text](url)` construct and inject secondary links
- **`_is_safe_image_data_uri()` helper** — restricts `data:image/*` rendering to inert raster formats; `data:image/svg+xml` is blocked to prevent inline-script XSS in renderers that inline SVG instead of using `<img>`
- **5xx + 429 retry** — `_retryable_request` now retries HTTP 502, 503, 504, and 429 transparently, honouring the `Retry-After` header on 429 (capped at 30 s); makes the pipe resilient to upstream-provider hiccups
- **Connection-pool tuning** — `requests.Session` now mounts an `HTTPAdapter` with `pool_connections=20, pool_maxsize=50` to keep TLS handshakes amortised under bursty multi-user Open WebUI workloads
- **Empty-model guard** — `pipe()` now returns `"OpenRouter Error: No model specified."` instead of forwarding a blank model ID to the upstream API
- **Icon-insert retry cap** — `_sync_model_icons` no longer retries an insert indefinitely; after 3 attempts the model is marked synced to avoid unbounded DB churn when OWUI never registers it
- **Backoff/Retry helpers** — `_backoff_delay()` and `_parse_retry_after()` extracted as static methods; backoff jitter is now proportional (`0.5x–1.5x`) to better distribute load under correlated failures
- **Image-CDN allow-list** — `_looks_like_image_content()` now recognises a curated list of image-generation CDN hosts; combined with a positive image-extension list this eliminates the false-positive case where a bare URL in a regular chat response (e.g. "What is GitHub's URL?" → `https://github.com`) was being rendered as a broken image (see the Changed entry for the full host list and parsing rules)
- **`_write_model_icon()` static helper** — extracted from `_sync_model_icons` to DRY the two near-identical `Models.update_model_by_id` call sites (clear-stale and apply-icon)

### Changed

- **Bumped minimum `requests` dependency to `>=2.32.4`** in `requirements.txt`, `function.json`, and the module docstring. Pre-2.32 versions leak the `Authorization` header to redirect targets when the header is set manually (CVE-2024-35195 family); we also pass `allow_redirects=False` on all OpenRouter calls so a misconfigured base URL cannot exfiltrate the bearer token off-host
- **Stricter `OPENROUTER_BASE_URL` validation** — plaintext `http://` is now rejected except for loopback hosts (`localhost`, `127.0.0.1`, `::1`, `*.localhost`); prevents bearer-token leakage in transit and SSRF to public/internal HTTP endpoints when the valve is misconfigured. **Breaking change:** operators with an existing non-loopback `http://` base URL must switch to `https://` after upgrading
- **API key key-handling** — `OPENROUTER_API_KEY` remains a plain `str` (UI-masked via the `password` input type) and is read through a single `Pipe._api_key` accessor. *(A `pydantic.SecretStr` variant was evaluated and rejected: Open WebUI persists valves by JSON-serialising them, and `SecretStr` serialises to the literal mask `"**********"`, which would overwrite the stored key on the next valve save.)*
- **`pipe()` streaming return type unified** — streaming now always returns an `AsyncGenerator[str, None]` regardless of whether `__event_emitter__` is supplied. The previous code branched between sync `Generator` and async wrapper; the new wrapper also guarantees the "done" status event fires in its `finally` block. Open WebUI iterates the result with `async for` in both cases
- **Image-content detection uses positive allow-list** — `_looks_like_image_content()` now requires either a known image extension on the URL path *or* a known image-CDN host (`_IMAGE_CDN_HOSTS`: Replicate, fal.ai, OpenAI/DALL-E blob, Black Forest Labs, Midjourney/Discord, Google `lh3.googleusercontent.com`/`storage.googleapis.com`, …). Arbitrary bare URLs (e.g. `https://github.com`) are no longer treated as images. Host matching tolerates trailing-dot FQDNs and `:port`; `.svg` paths are never auto-rendered even from a trusted host (inline-script XSS defence)

### Fixed

- **Streaming cost display never appeared (`SHOW_COST_INFO`)** — OpenRouter only emits the `usage` block (with `cost`) when the request opts in via `{"usage": {"include": true}}`. The pipe never sent it, so for streaming responses (Open WebUI's default) `latest_usage` stayed empty and the cost line was silently omitted. `_prepare_payload` now sets `usage.include=true` whenever `SHOW_COST_INFO` is enabled
- **Provider icon never corrected after insert-cap exhaustion** — the PERF-3 insert cap marked an exhausted model as *synced*, which both removed it from the cache-hit re-sync loop and conflated "gave up inserting" with "successfully synced". A model that Open WebUI registered *after* the 3 insert attempts therefore never received its icon. Exhausted models are now tracked in a separate `_icon_insert_exhausted` set: the insert is skipped (no DB churn) but the model is still re-checked each pass, so a late registration is picked up via the update path
- **Stale icon-sync state after a valve change** — `_icons_synced` / `_icon_insert_attempts` / `_icon_insert_exhausted` are now pruned to the current model set on every cache rebuild, so changing a model-affecting valve (e.g. provider filter) can no longer skew the re-sync guard or leak attempt counters
- **SSE lines without a space after `data:`** — the stream parser now accepts both `data: {…}` and the spec-valid `data:{…}` (optional leading space), preventing silently-dropped chunks from strict SSE producers
- **`cache_control` injection aborted on bare-string content parts** — a multimodal `content` list containing a bare string (not a dict) raised `AttributeError`, caught by the broad handler, so cache_control was silently skipped for the whole message; bare-string parts are now skipped individually and the longest text part is still tagged
- **`pipes()` HTTPError handler crashed on `exc.response is None`** — manually-raised `HTTPError` objects (without an attached `Response`) caused `AttributeError` instead of returning the error pseudo-model; now guarded explicitly with a "no response" fallback message
- **Model-list cache served stale data after `OPENROUTER_BASE_URL` change** — `_build_cache_key()` did not include the base URL in its fingerprint, so switching prod ↔ staging continued to serve cached models from the previous endpoint until the 5-minute TTL expired; the base URL is now part of the cache key
- **Audio transcript bypassed `_insert_citations`** — `_non_stream_response` applied citation linking to `content` *before* the audio-fallback block replaced `content` with the transcript, so `[1]` references in audio responses were never linked; citations are now applied to the transcript itself
- **Image-generation output now renders in Open WebUI** — models such as FLUX.1 Flex and other image-gen providers on OpenRouter return the generated image as `message.content` (a bare CDN URL or `data:image/` base-64 URI) rather than in `message.images`; the pipe previously passed this through as plain text so no image appeared in the UI. A new `_looks_like_image_content()` helper detects these responses in both streaming and non-streaming paths and converts them to `![Generated image](…)` markdown. Non-image-gen models are unaffected: text with spaces, multi-line content, and URLs with known non-image extensions (`.html`, `.json`, `.py`, …) are never converted.

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

## [1.2.0] — 2026-02-17

### Added

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

### Fixed

- Fixed potential payload mutation when `ENABLE_CACHE_CONTROL` is active (deepcopy prevents side effects)
- Fixed potential `IndexError` on stream chunks with empty `choices` array
- Fixed stream error handler not caching response body before closing connection
- Safe `isinstance(err, dict)` checks before calling `.get()` on error objects
- `_close_think_tag()` helper eliminates duplicated think-tag closure logic (was 5x repeated)
- `_stream_response` now closes the response in a `finally` block even on consumer `break`

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

<!-- Compare links -->
[Unreleased]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/releases/tag/v0.1.0
