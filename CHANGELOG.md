# Changelog

All notable changes to **OpenRouter Pipe** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.12.0] — 2026-07-24

### Added

- **TTS reading quality overhaul — the voice now speaks prose, not markup.** A speech model read its `input` verbatim, so `**bold**` was spoken as "asterisk asterisk bold …", `# Heading` as "hash Heading", `[label](https://…)` read the whole URL character-by-character, and emoji / fenced code / reasoning `<details>` panels were all read aloud. New `_clean_tts_text()` reproduces Open WebUI's native TTS cleaning chain (`removeEmojis` + the 15-step `removeFormattings`, plus `<details>` stripping) and adds LaTeX removal (`$…$`, `$$…$$`, `\(…\)`, `\[…\]` — a documented gap in OWUI's own path). Dependency-free (broad Unicode-range emoji regex; the repo keeps its `requests`+`pydantic`-only footprint). It also strips our own `<audio>`/`<video>` embeds so a prior TTS turn is never fed back as text to speak.
- **Length handling — long text no longer fails.** Previously a single unbounded POST hit OpenRouter's ~4096-char `/audio/speech` cap and returned HTTP 400 (or was silently truncated). New `_split_tts_text()` splits cleaned text into ≤3900-char chunks (OWUI-style: `punctuation` default with a <4-word/<50-char merge pass, `paragraphs`, or `none`; oversize chunks hard-wrapped on whitespace), synthesizes each, and **concatenates the audio back into one clip** — mp3 frames are concatenated directly; a provider that ignores the mp3 request and returns raw PCM (e.g. Gemini-TTS via OpenRouter) has its concatenated samples wrapped once in a WAV container. The cumulative 50 MiB byte cap is enforced across chunks.
- **`TTS_SOURCE` valve (auto / user / assistant).** Chooses what a speech model reads: `auto` (default) speaks the last assistant reply when the chat has one (the "read that answer aloud" case), otherwise the user's message; `user` and `assistant` force either. `auto` skips our own audio embeds so repeated TTS turns don't try to "speak" a previous clip.
- **`AUDIO_OUTPUT_SPEED` valve** — forwards a `speed` multiplier to `/audio/speech` (a per-request body `speed` still wins). Empty = provider default.
- **Per-message `[voice=NAME]` directive** — pick a voice for a single message (validated against the model's `supported_voices`, with the directive stripped from the spoken text) without editing the global valve.
- **`AUDIO_TTS_SPLIT` valve** (`punctuation` / `paragraphs` / `none`) mirroring OWUI's Response Splitting.
- **In-memory TTS result cache** keyed on `sha256(model | voice | format | speed | split | cleaned text)` → the hosted clip URL, so regenerating or re-sending identical text is returned instantly without re-billing the provider or re-uploading. Bounded (cleared wholesale past 256 entries).

### Changed

- `_run_speech_generation` refactored around the clean → split → synthesize-each → concatenate → cache pipeline; per-chunk HTTP moved into `_tts_fetch_chunk`. All new valves mirrored into `UserValves` for per-user override. Module + `function.json` descriptions and the `AUDIO_OUTPUT_VOICE` valve doc updated.

### Fixed

- **Tool calling on a non-tool model no longer 404s the whole request.** With any Open WebUI tool enabled (e.g. `get_current_timestamp`), a `tools`/`tool_choice` signal reached every model — but 175 of the ~447 catalog models have no tool-capable endpoint, so OpenRouter rejected the entire request with `HTTP 404 "No endpoints found that support tool use. Try disabling …"`. The model appeared broken even though it simply can't do tools. `pipes()` now tracks tool-capable models (`supported_parameters` containing `tools`/`tool_choice`) in `_tool_capable_ids`, and for a model that isn't tool-capable `pipe()` strips **both** sources of the tool signal — the `tools` array the pipe builds from `__tools__`, **and** the `tools`/`tool_choice` that Open WebUI's native function-calling injects straight into the request body (which `_prepare_payload` would otherwise pass through) — so the model answers normally instead of 404ing (with a status note + log line). Verified end-to-end through the real OWUI HTTP stack: a tool enabled on `perceptron/perceptron-mk1` reproduced the exact 404 before the fix and returns a normal answer after. Virtual variants (`base:nitro`) inherit the base model's capability; when the capability set is unknown (pre-fetch/fetch failure) tools are forwarded as before so tool use is never broken blindly. The generic 404 message was also reworded (it no longer claims "the model ID may be wrong" — it now names the capability-mismatch case).

- **More capability-mismatch fixes (same class as the tool 404), from a full audit of every OpenRouter model kind against the docs.** OpenRouter treats `tools`/`tool_choice`/`response_format(json_schema)/structured_outputs` as *hard routing constraints* — sending one to a model whose endpoints lack it 404s the whole request (everything else, like sampling params or `reasoning`, is silently ignored unless `require_parameters` is set). `pipes()` now also tracks `_structured_output_ids` and `_reasoning_ids`, and `pipe()` gates accordingly (generalized `_model_has_cap`):
    - **`response_format`** (from the `RESPONSE_FORMAT`/`RESPONSE_SCHEMA` valves or the body) is dropped for a model without structured-output support, instead of 404/400ing (verified: a non-structured model now answers normally with the valve set).
    - **Orphan `tool_choice`** — a `TOOL_CHOICE=required`/`auto` valve (or body value) with no tools present is now stripped for *every* model; providers 400 on a bare `tool_choice`.
    - **`reasoning`/`include_reasoning`** (forced on every request via `INCLUDE_REASONING`) is dropped for non-reasoning models, so `REQUIRE_PARAMETERS=true` no longer 404s them (and dead params aren't sent).
    - **Non-chat models** — embeddings (27), transcription/STT (12) and rerank (4) have no `/chat/completions` endpoint and 400/404 when selected in the chat picker. They now return a clear, actionable message ("'X' is a embeddings-type model … call OpenRouter's /api/v1/embeddings endpoint directly") instead of the raw upstream error. They stay visible in the catalog (per user preference); speech/video/audio/image keep their existing dedicated handling. Image models are left to try chat (many, e.g. gemini-image, return images fine; the ones that don't — new /images-only models like gpt-image — surface OpenRouter's own clear detail).

### Notes

- `/audio/speech` only supports `response_format` `mp3` or `pcm`, so the TTS path stays on mp3 (universally playable + concatenable) rather than honouring `AUDIO_OUTPUT_FORMAT` (wav/flac/opus) — the raw-PCM→WAV fallback covers providers that ignore the mp3 request. STT (`transcription`) remains unrouted (audio-input, doesn't fit a text-first turn).

### Tests

- ~47 new TTS tests: text cleaning (markdown/emoji/ZWJ/code/LaTeX/`<details>`/media-embed), splitting (punctuation merge, paragraphs, none, hard-wrap), source selection (auto/user/assistant + audio-embed skip), `[voice=]` directive, speed valve, end-to-end cleaned input, multi-chunk concatenation, raw-PCM→WAV fallback, and cache reuse (no second POST).
- ~14 tool-gate tests + ~18 capability-gating tests: `pipes()` capability tracking (`_tool_capable_ids`/`_structured_output_ids`/`_reasoning_ids`/`_nonchat_kind`), `_model_has_cap` semantics (capable / variant / unknown-set), and pipe() end-to-end — tools dropped for a non-tool model (from both `__tools__` and body) but forwarded for a capable one, `response_format` stripped for a non-structured model but kept for a structured one, `reasoning` stripped for a non-reasoning model, orphan `tool_choice` stripped when no tools present, and a clear error for embeddings/rerank/transcription. All 1050 tests green.

## [1.11.0] — 2026-07-24

### Added

- **Text-to-speech (TTS) routing via the dedicated `/audio/speech` endpoint.** OpenRouter serves three distinct "audio-ish" model classes on three different endpoints: audio-gen (`output_modalities: ["audio"]` — gpt-audio, lyria) over `/chat/completions`; TTS (`output_modalities: ["speech"]` — kokoro, deepgram/aura-2, gemini-tts, minimax/speech, x-ai/grok-voice-tts, ...) over `POST /api/v1/audio/speech`; and STT (`output_modalities: ["transcription"]`) over `/audio/transcriptions`. Previously only the audio-gen class was handled — the 15 `speech` models were imported into the catalog but, when selected, fell through to `/chat/completions` (the wrong endpoint) and failed. `pipes()` now tracks them in `_speech_model_ids`, and `pipe()` routes them to the new `_run_speech_generation()`, which extracts the latest user message as `input`, calls `/audio/speech` with `response_format=mp3` (the endpoint defaults to raw `pcm`, which browsers can't play without a WAV wrapper), enforces the same 50 MiB byte cap as the other media flows, re-hosts the returned bytes through OWUI's file system, and embeds them as a block-HTML `<audio>` element. Upstream error statuses (401/402/429/4xx) are mapped to human-readable messages; the `X-Generation-Id` response header feeds the optional `SHOW_GENERATION_ID` footer (sanitized via the shared `_format_generation_id` helper).
- **Per-model voice auto-selection for TTS.** Voice names are provider-specific (kokoro: `af_bella`/`am_adam`, deepgram: `aura-2-thalia-en`, gemini: `Zephyr`, ...), so the single `AUDIO_OUTPUT_VOICE` valve can't be right for every provider — sending the OpenAI-flavoured default `alloy` to kokoro would 400. `pipes()` now harvests each speech model's `supported_voices` list from the catalog into `_speech_voices` (fully dynamic — no hardcoded table, updates automatically as OpenRouter changes voices). `_run_speech_generation()` keeps the configured voice when it's valid for the selected model, otherwise falls back to that model's first advertised voice; only when a model exposes no voice list does it pass the valve value through as-is (blank → `alloy`).

### Changed

- **Module-level frontmatter + `function.json` description** now document the `/audio/speech` TTS flow, and `function.json` gains a `text-to-speech` tag.
- **`AUDIO_OUTPUT_VOICE` valve description** clarifies that it drives both gpt-audio and dedicated TTS models, and that TTS models auto-fall back to a valid per-model voice when the configured value isn't one they accept.

### Notes

- **STT (`transcription`) is intentionally not routed.** Those models take audio *input* (`/audio/transcriptions`), which doesn't fit a text-first OWUI chat turn; they remain in the catalog but are not dispatched to a dedicated flow.

### Tests

- New "text-to-speech (TTS)" section in `test_pipe.py`: model detection (speech vs audio vs transcription vs text, catalog completeness), `/audio/speech` routing + payload shape, mp3 enforcement, upstream error mapping, byte cap, missing-OWUI-context handling, and per-provider voice resolution (valid → kept, invalid → first supported, blank → first supported or `alloy`, no list → verbatim). All 971 tests green.

## [1.10.5] — 2026-06-18

### Fixed

- **`ZDR_MODELS_ONLY` returned 0 models — ID mismatch between `/endpoints/zdr` and `/models`** ([#14](https://github.com/sena-labs/Public/issues/14)). OpenRouter's `/endpoints/zdr` returns entries keyed on the `model_id` field (e.g. `anthropic/claude-4.8-opus-20260528`), but `_load_zdr_model_ids()` only read `id`/`model`, so the ZDR set came back empty and every model was filtered out ("No ZDR-capable models available."). Two changes: (1) `_load_zdr_model_ids()` now extracts `model_id` first, falling back to `id`/`model` for forward-compat; (2) the `pipes()` filter compares **both** the short `/models` `id` and the entry's `canonical_slug` against the ZDR set, since the canonical slug is what the ZDR endpoint keys on and frequently differs from the short id.

### Tests

- `19i. ZDR_MODELS_ONLY filter` mock rewritten from the string-list shape (which masked the bug) to the real `/endpoints/zdr` dict shape with `model_id`, plus a `canonical_slug`-only match to guard both fix paths. All 939 tests green.

## [1.10.4] — 2026-05-31

### Changed

- **Funding source switched to Ko-fi only** — `.github/FUNDING.yml` rewritten to `ko_fi: senalabs`, `funding_url` in both `function.json` and the module-level docstring frontmatter point to `https://ko-fi.com/senalabs`. GitHub Sponsors link removed. No code change; openwebui.com portal re-reads the frontmatter on next sync to surface the new support link.

## [1.10.3] — 2026-05-31

### Fixed

- **openwebui.com community portal upload — *undefined* error.** Re-grounded in OWUI source instead of the slug visible in the form. `src/lib/utils/index.ts` defines `nameToId` as `name.replace(/[^\w]+/g, '_').toLowerCase()` (`\w = [A-Za-z0-9_]`), so `OpenRouter Pipe` slugifies to `openrouter_pipe` — **underscores are correct, dashes are not**. v1.10.2 had momentarily swapped the id to dashes on a misdiagnosis; this release reverts that change. The real culprit was a stale module-level frontmatter docstring in `openrouter_pipe.py` (parsed by `backend/open_webui/utils/plugin.py:extract_frontmatter` via `^\s*([a-z_]+):\s*(.*)$`): `version: 1.9.0` (last touched at that release) and a description that pre-dated the image/video/audio output flows. When the portal renders the parsed frontmatter alongside the form, missing-or-stale keys surface as a JavaScript `undefined` tooltip on the preview pane.

### Changed

- **Function ID reverted to `openrouter_pipe`.** Reason: see *Fixed* above — matches the portal's actual slugifier. Reason for the revert specifically: v1.10.2's `openrouter-pipe` would have failed the portal's own validation (every existing community pipe in `/f/<user>/<slug>` uses underscores) and would have created a *new* function row in every existing install's OWUI DB, forcing a manual config copy with no upside. Cleaner to keep the historical id.
- **Module-level frontmatter docstring refreshed** — `version: 1.10.3` and a v1.10.x-accurate description (image / video / audio output flows, SSRF-guarded media downloads, 99.3% icon coverage, `MAX_TOOL_ITERATIONS`, encrypted UserValves keys, atomic routing-set swap). Arrow character `→` replaced with `..` since the OWUI frontmatter parser keeps the literal value but the portal's frontend renderer occasionally chokes on non-ASCII in metadata tooltips.

### Docs

- Docstring references in `_clean_model_id` and `_sync_model_icons` reverted to `openrouter_pipe.openai/gpt-4o` form.
- 5 `test_pipe.py` `_function_id` simulations and 2 prefix-assertion strings reverted to `openrouter_pipe.*`. All 939 tests green.

### Breaking note for v1.10.2 testers

If you tagged or installed `1.10.2` between the previous release and this one, your OWUI DB now has a stranded function row under the `openrouter-pipe` id. To clean up: **Admin Panel → Functions** → delete the `openrouter-pipe` entry → install/update `openrouter_pipe` to 1.10.3. Valves config does not migrate automatically — copy it before the delete. No chat history is affected (chat history is keyed on the model selector entry, not the function row).

## [1.10.2] — 2026-05-31  *(superseded by 1.10.3 — do not use)*

Identifier-rename release based on a misread of the OWUI portal slugifier. See 1.10.3 *Fixed* for the corrected root cause. Tag remains in git history for traceability; the published manifest was never accepted by the portal.

## [1.10.1] — 2026-05-31

### Added

- **Layered icon-resolution fallback chain** — every model in the selector now shows a real brand icon (or, as a last resort, a deterministic letter tile). New order: OpenRouter registry → hyphen-stripped slug → hardcoded `_PROVIDER_ICONS` → `_PROVIDER_SLUG_ALIASES` rewrite → provider-domain favicon (extracted from the registry's gstatic `url=` query parameter) → generated letter-SVG. Live VPS audit went from 261/408 hosted icons (64%) to **448/451 (99.3%)** — only the three `kwaivgi/kling-*` models remain on letter-SVG because Kuaishou's video team has no public icon source.
- **41 official brand / HuggingFace-avatar icons added to `_PROVIDER_ICONS`** — covers nousresearch, sao10k, openrouter, sentence-transformers, inclusionai, baai, intfloat, tencent, zyphra, thenlper, allenai, kwaipilot, deepcogito, gryphe, essentialai, undi95, cognitivecomputations, writer, anthracite-org, prime-intellect, canopylabs, hexgrad, sesame, alfredpros, upstage, inflection, baidu, stepfun, rekaai, relace, aion-labs, arcee-ai, inception, liquid, z-ai, ai21, mancer, bytedance, bytedance-seed, thedrummer, ibm-granite, nex-agi. Each URL HEAD-checked against the actual served content type so SPA fallbacks that return `text/html` for missing assets no longer leak through as broken images.
- **`USE_PROVIDER_DOMAIN_FAVICON` admin valve** (default `true`) — when gstatic is suppressed for privacy and no hardcoded icon exists, fall back to `https://<provider-domain>/favicon.ico` rather than the letter-SVG. Privacy-preferable to gstatic (the favicon request hits the provider directly, no Google middleman).
- **`_generate_letter_icon` final fallback** — deterministic data: SVG with the provider's initial on an HSL-from-SHA256-of-key background. Privacy-safe (no external request), stable across syncs (no churn on the icon-managed check).
- **`_sync_orphan_db_icons` sweep** — `pipes()` now also iterates active OWUI model rows whose ID has our manifold prefix but no longer appears in the current catalog (deprecated / withdrawn models OWUI never cleans up). Six visible orphans on the live deployment were stuck on `/static/favicon.png` because the per-catalog sync only walked the current `pipes()` output.

### Fixed

- **`/static/favicon.png` was not recognised as managed** — the OWUI 0.4+ server-default favicon placeholder slipped through `_is_owui_managed_icon` and the regular sync refused to overwrite it. Added `/static/` to the managed-prefix list.
- **`Models.{get,update,insert}_model_by_id` are async on OWUI ≥ 0.4** — `_sync_model_icons` was sync and the coroutines were silently discarded, so the in-place sync never wrote to the model DB on modern OWUI. New `_resolve_maybe_awaitable` helper drains the coroutine with `asyncio.run` when needed (thread-pool fallback when invoked from inside a running loop).
- **Provider-domain favicon URLs that returned `text/html` (SPA shell)** — `ai21.com/favicon.ico` (200 but 0 bytes), `bytedance.com/favicon.svg`, `mancer.tech/favicon.ico`, and `openrouter.ai/favicon.svg` all returned the SPA index page instead of an image, so the OWUI selector rendered them as broken-image placeholders. Replaced each with the HuggingFace avatar URL or, for OpenRouter itself, `apple-touch-icon.png` (a real 6.4KB PNG).
- **Provider slug aliases** — new `_PROVIDER_SLUG_ALIASES` map (`bytedance-seed → bytedance`, `rekaai → reka`, `grok → x-ai`, plus convenience entries for `gemini`/`claude`/`google-vertex`) handles model-author IDs that don't appear in the OpenRouter registry directly.

### Changed

- **`_is_owui_managed_icon` recognises every CDN we ship** — `cdn-avatars.huggingface.co`, `huggingface.co/avatars/`, `github.com/<user>.png`, `gravatar.com/avatar/`, `openrouter.ai/{favicon.svg,apple-touch-icon.png}`, `sbert.net/_static/logo.png`, `bytedance.com/favicon.svg`, plus any top-level `https://<host>/favicon.ico`. Future refreshes can rotate stale CDN URLs without ever touching a user-set custom icon (which would live on a different host).
- **Module-level `_PROVIDER_DOMAIN_CACHE`** populated alongside the icon registry — the provider website extracted from each gstatic favicon `url=` query param is indexed under both the exact slug and the hyphen-stripped variant.

### Docs

- **README**: expanded TOC to include all configuration subsections (Common valve combinations, Reasoning tokens, Citations, Media Generation, Cost Display, Per-user settings, API key encryption, Tool calling); added a dedicated **Media Generation** valve table documenting `VIDEO_GENERATION_TIMEOUT`, `VIDEO_POLL_INTERVAL`, `AUDIO_OUTPUT_FORMAT`, `AUDIO_OUTPUT_VOICE`; expanded **Common valve combinations** with flux / grok-imagine / Lyria / gpt-audio-mini examples and `SHOW_REMAINING_CREDIT` / `ZDR_ENFORCE` entries; rewrote the Architecture table with the actual live functions (`_non_stream_fetch + _non_stream_with_events` instead of the dead `_non_stream_response`, plus rows for the tool loop, video / audio generation, the shared `_owui_upload_bytes` helper, and the SSRF / size / MIME security guards); added release-version and test-count badges.
- **Test count updated to 939** across README, TESTING, CONTRIBUTING, and the PR template.

### Tests

- 868 → **939** tests (+71). New coverage for the letter-SVG fallback, provider-domain favicon path, slug aliases, the orphan-DB sweep, the awaitable-resolver helper, the 41 newly hardcoded icon URLs, and the `_is_owui_managed_icon` recognition of the seven CDNs we ship from. All green on Python 3.10–3.13.

## [1.10.0] — 2026-05-30

### Added

- **Image generation rendering (flux, gemini-image-preview, ...)** — `choices[0].message.images` and `delta.images` data-URL payloads are decoded, uploaded through Open WebUI's file-upload helper, and the message content is rewritten to `![Generated image](/api/v1/files/<id>/content)` so the chat client embeds them inline. Works for both the streaming path (`_wrap_stream` materializes after the SSE loop) and the non-streaming path (`_emit_image_files`); also wired into the native-tool loop so flux+tools no longer drops the image.
- **Video generation routing (veo, kling, sora, seedance, hailuo, wan, grok-imagine)** — video-output models from OpenRouter's catalog (architecture `output_modalities=["video"]`) are routed to the asynchronous `POST /api/v1/videos` endpoint instead of `/chat/completions` (which 500s for them). The pipe submits the job, polls the returned `polling_url` every `VIDEO_POLL_INTERVAL` (default 5 s) up to `VIDEO_GENERATION_TIMEOUT` (default 600 s), downloads the MP4 from `unsigned_urls[0]`, re-hosts it through OWUI, and embeds via the block-HTML token `<div><video>URL</video></div>` — the only emission shape OWUI's `Markdown.svelte` HTML-token renderer accepts for inline video. Forwards `duration`, `resolution`, `aspect_ratio`, `generate_audio`, `seed` from the body. Status emits dedupe on identical labels so long jobs don't pollute the status history.
- **Audio generation routing (lyria, gpt-audio, gpt-audio-mini)** — audio-output models are served via `/chat/completions` with `modalities=["text","audio"]` + `audio={format,voice}` + `stream=true` (the only combination that actually returns audio bytes). For OpenAI's gpt-audio family the format is forced to `pcm16` (the upstream only accepts pcm16 with stream=true) and the raw PCM bytes are wrapped in a minimal RIFF/WAVE container (24 kHz mono) before upload so the browser can play them via `<audio>`. Other providers (Lyria etc.) get mp3 by default; the format flows through `state["audio_format"]` so the materializer picks the correct MIME per request. Embedded as `<div><audio>URL</audio></div>` (same block-HTML token trick as video).
- **`VIDEO_GENERATION_TIMEOUT` + `VIDEO_POLL_INTERVAL` valves** — bound the async polling loop; both per-user-overridable via UserValves.
- **`AUDIO_OUTPUT_FORMAT` + `AUDIO_OUTPUT_VOICE` valves** — admin default for the audio container (mp3 / wav / flac / opus / ogg / aac / m4a / pcm16) and the voice id (gpt-audio family only; music models ignore it). Both per-user-overridable.
- **SSRF / auth-leak guard for media downloads** — new `_is_openrouter_url` helper restricts the polling URL and the unsigned download URL to `openrouter.ai` (or `*.openrouter.ai`); a compromised relay or malicious upstream JSON can no longer redirect the bearer-bearing GET to an attacker-controlled host. The polling URL falls back to the canonical `/videos/<id>` form; the download is refused outright if the host isn't OpenRouter.
- **Byte-size caps + MIME whitelists for media** — `_VIDEO_MAX_BYTES=100 MiB` / `_AUDIO_MAX_BYTES=50 MiB`. Video downloads use streaming `iter_content` with a Content-Length early-reject and a mid-stream cap so a hostile upstream cannot exhaust OWUI worker memory with a multi-GB blob. The post-download MIME is restricted to a per-modality whitelist (mp4/webm/mov/mkv for video, mpeg/wav/flac/ogg/opus/aac/mp4 for audio) so a spoofed `Content-Type` can't coerce OWUI's renderer.
- **Citation URL scheme filter** — `_emit_citation_events` refuses to emit events for non-`http(s)` URLs, closing the `javascript:` / `data:` / `vbscript:` XSS surface through citation-card rendering.

### Changed

- **Body never mutated** — `pipe()` now deep-copies the incoming body before injecting audio-modality flags, so the OWUI-owned dict (reused for history, title generation, etc.) is never touched by the pipe's per-request payload prep. Closes a CRIT correctness bug where a subsequent non-audio chat in the same OWUI session would inherit stale `modalities=["text","audio"]`.
- **Atomic routing-set swap** — `pipes()` now builds the audio/video `frozenset`s locally during a refresh and assigns them in one statement, instead of `.clear()` + re-populate. A concurrent `pipe()` call mid-refresh sees either the old set or the new one, never an empty intermediate state.
- **Lazy populate runs off the event loop** — first request after a container restart triggers `self.pipes()` via `asyncio.to_thread`, gated by a `_lazy_populated` flag so it doesn't repeat on every subsequent request when the user happens to have zero audio/video models.
- **Cached credit footer** — stream / non-stream / tool-stream / tool-nonstream footers now read the credit balance from cache only (`_credit_balance_cached`); a pre-warm coroutine (`_prefetch_credit_if_enabled`) runs the HTTP fetch via `asyncio.to_thread` BEFORE the footer is yielded. Previously a cold `SHOW_REMAINING_CREDIT` fetch could stall the SSE stream finalize.
- **Cached Authorization header** — `_build_headers` no longer runs `EncryptedStr.decrypt()` (Fernet, ~100 µs) on every chunk send / poll / footer. The decrypted `Bearer …` line is cached keyed on the encrypted ciphertext and auto-invalidates on key rotation. Bounded to 32 entries.
- **HTTP connection pool sized for concurrent users** — the shared `requests.Session` now mounts an `HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=0)`. Default urllib3 pool of 10 was a hard limit on concurrent streamed chats; `max_retries=0` because `_retryable_request` already drives Retry-After-aware retries.
- **`_effective_valves` fast path** — when `__user__` has no UserValves attached (the overwhelmingly common case), return `self.valves` directly instead of pydantic-copying + per-key validating. Admin valves are treated as read-only by the rest of the pipe.
- **`_models_cache_valid` short-circuit** — compare the cheap presence + TTL first, only pay the Fernet-decrypt + SHA256 cost of `_build_cache_key` when both match and we're about to serve from cache.
- **Shared `_owui_upload_bytes` helper** — image, video, and audio uploads now share one helper with consistent error logging (`Image upload / Video upload / Audio upload to OWUI failed`), replacing three duplicated 30-line copies of the OWUI helper import + user-resolve + upload-image dance.
- **Module-level constants** — `_DATA_IMAGE_RE`, `_VIDEO_MAX_BYTES`, `_AUDIO_MAX_BYTES`, `_VIDEO_MIME_WHITELIST`, `_AUDIO_MIME_WHITELIST`, `_AUDIO_FORMAT_TO_MIME`, `_CITATION_ALLOWED_SCHEMES` — hoisted from per-call locals so the hot path doesn't pay re-compile / re-allocate costs.
- **SSE reads use `iter_lines(chunk_size=8192)`** — fewer syscalls on high-throughput streams than the default 512.
- **Tool-loop non-stream cap-reached branch** — now catches `Timeout` and `HTTPError` explicitly before the generic `Exception`, so a network timeout on the very last call surfaces the friendly `Request timed out after Xs` wrap instead of the sanitized `Internal request error` message. Also builds a clean `{role, content, tool_calls}` assistant message instead of forwarding the raw upstream dict (which can carry `refusal` / legacy `function_call` / vendor reasoning blobs that some downstream models reject on re-submission).
- **Video polling status emit dedupe** — repeated `Generating video (pending)…` labels are suppressed; the operator only sees a new status line when the upstream `status` field changes.

### Fixed

- **`_run_video_generation` resource leaks** — `submit_resp` and per-iteration `poll_resp` are wrapped in `try/finally` with explicit `close()`; previously each unhappy branch leaked a socket and a long-running job could leak up to 120 connections.
- **Video error mapping** — 402 maps to `Insufficient credits (HTTP 402)`, 429 to `Rate limited (HTTP 429)`; previously both fell through to a generic `Failed to start video job` that hid the cause.
- **Non-stream `status: done` event always emitted** — `_non_stream_with_events` call now wrapped in `try/finally` so the shimmer line clears even on an unhandled exception (matches the stream and video paths).
- **`ZDR_ENFORCE` removed from `UserValves`** — privacy policy is admin-only; a regular user can no longer flip it off through the per-user override.
- **Generic exception sanitization** — `_stream_response` and `_non_stream_fetch` no longer surface raw Python exception text to the chat client on a non-`requests.RequestException` failure. Detail goes to server stdout, client gets `Internal stream/request error (see server logs)`. Network-level `RequestException` messages still surface verbatim (operator-safe, useful debug).
- **Audio payload regression** — when `_stream_one_round` enters the tool loop with an audio-output model, captured `delta.audio.data` is now surfaced via `state["audio_b64"]` so `_run_tools_stream` can materialize and embed it. Previously a flux / lyria / gpt-audio model with tools enabled would silently drop the media.

### Security

- All four media-related changes above are also security-relevant: SSRF whitelist, byte-size caps, MIME whitelists, citation URL scheme filter, sanitized internal exceptions, admin-only ZDR.

### Tests

- Suite grew from 727 to **868 tests**: +141 tests covering image / video / audio routing, the SSRF whitelist, atomic frozenset swap, body deepcopy isolation, ZDR + media combo, generic-exception sanitization, the auth-header cache (decrypt-once + key rotation + 32-cap eviction), the `_AUDIO_FORMAT_TO_MIME` table, user-supplied `audio` and `modalities` preservation, base64 padding edge cases, video error branches (Timeout / ConnectionError / mid-poll RequestException / deadline expiry / malformed `unsigned_urls` / non-dict failed-status error / forwarded knobs / Content-Type fallback), and the tool-nonstream cap-branch Timeout path. All green on Python 3.10–3.13.

## [1.9.0] — 2026-05-29

### Added

- **`RESPONSE_FORMAT` json_schema mode + `RESPONSE_SCHEMA` valve** — set `RESPONSE_FORMAT = json_schema` and paste a JSON Schema string into `RESPONSE_SCHEMA` to inject a strict `response_format: {"type": "json_schema", "json_schema": {"name", "schema", "strict": true}}`. Invalid JSON is logged and skipped. The request body's own `response_format` always wins. Mirrored in `UserValves`
- **Open WebUI native citation events** — the tool-calling paths (streaming + non-streaming) now emit `{"type": "citation", "data": {"source": {"name": url, "url": url}}}` events to the OWUI event emitter, in addition to the existing markdown footer, so the UI can render citations as native footnotes
- **`RESPONSE_FORMAT` + `TOOL_CHOICE` valves** — force a JSON output mode (`json_object`) and/or set a default `tool_choice` (`none`/`auto`/`required`) when the request doesn't specify one; the request body's own values always win. Both mirrored in `UserValves`
- **Explicit usage accounting + user attribution** — when `SHOW_COST_INFO` is on, the pipe requests `usage: {include: true}` so cost/credit footers aren't blank when OpenRouter omits usage; the Open WebUI `user` object is now forwarded to OpenRouter as its id string (for abuse tracking) instead of being dropped

### Fixed

- **CI green on Python 3.10–3.13** — installed `cryptography` in the CI image so the at-rest encryption path is exercised (it is an optional runtime dep), and made the ciphertext assertions crypto-aware so the suite also passes in a bare environment (gated on `_Fernet` availability, with an explicit forced-`_Fernet=None` fallback section)
- **`SyntaxError` on Python 3.10/3.11** — the citation-URL sanitize regex was inlined in an f-string expression, illegal before 3.12; hoisted to a module-level compiled regex so the module imports on every CI matrix leg (Open WebUI's runtime is 3.11)
- **Credit fetch in tool-path footers blocked the event loop** — `_run_tools_stream` / `_run_tools_nonstream` now pre-warm the credit cache via `asyncio.to_thread` before each footer, so a cold `SHOW_REMAINING_CREDIT` fetch no longer stalls other users when tools are used
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
