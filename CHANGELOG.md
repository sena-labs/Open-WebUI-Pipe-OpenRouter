# Changelog

All notable changes to **OpenRouter Pipe** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
