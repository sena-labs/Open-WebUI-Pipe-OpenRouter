# OpenRouter Pipe

[![Build](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/workflows/tests.yml/badge.svg)](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Access the **full OpenRouter catalog (400+ models)** — chat, TTS, audio, image-generation, and
embedding models — directly inside Open WebUI, with provider routing, reasoning tokens, streaming,
fallbacks, and cache control out of the box.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
  - [From Open WebUI Community](#from-open-webui-community)
  - [Manual install](#manual-install)
  - [From source](#from-source)
- [Usage](#usage)
- [Configuration](#configuration)
  - [Core](#core)
  - [Reasoning](#reasoning)
  - [Display & Filtering](#display--filtering)
  - [Provider Routing](#provider-routing)
  - [Advanced](#advanced)
  - [Network](#network)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [License](#license)

---

## Features

- **Manifold pipe** — exposes the full OpenRouter catalog (chat, TTS, audio, image, embeddings) as native Open WebUI models in the model selector. Configurable via `OUTPUT_MODALITIES` and `MODEL_CATEGORY`.
- **Web search plugin** — attach OpenRouter's `web` plugin to any model with domain allow/deny lists, custom search prompt, and result-count limits.
- **Variant routing** — surface virtual `:nitro`/`:exacto`/`:thinking`/`:online`/`:free`/`:extended` model entries that route to OpenRouter's specialized profiles.
- **Service tier hint** — forward `flex` (cheaper/slower) or `priority` (faster) tiers to compatible providers.
- **Generation auditability** — optional generation ID footer maps each response to OpenRouter's `/generation?id=` activity API.
- **Cached-input savings** — surface cached vs. non-cached prompt tokens in the cost footer (Anthropic prompt caching, OpenAI implicit caching, Gemini context caching).
- **Deprecation visibility** — models with an `expiration_date` are tagged with ⚠ in the selector (or hidden via `HIDE_DEPRECATED_MODELS`).
- **Provider routing** — sort by `price`, `throughput`, or `latency`; prefer or exclude specific providers; enforce `require_parameters`.
- **Reasoning tokens** — `<think>` blocks streamed in real time with configurable effort (`low`, `medium`, `high`).
- **Streaming** — full SSE streaming with mid-stream error handling and automatic `<think>` closure on error.
- **Model fallbacks** — automatic failover to one or more backup models via `FALLBACK_MODELS`.
- **Middle-out compression** — fits long prompts within context windows (`transforms: ["middle-out"]`).
- **Cache control** — Anthropic-style `cache_control` injection on the longest message chunk.
- **Citations** — `[n]` references from web-search-enabled models are converted to markdown links.
- **Provider icons** — 13 hardcoded fast-path logos plus auto-discovered icons for ~20 more providers (xAI, Inflection, NVIDIA, Arcee, Morph, Cerebras, …) lazy-loaded from OpenRouter's provider registry, all synced directly into Open WebUI's model database.
- **ZDR (Zero Data Retention)** — filter the catalog to ZDR-capable models (`ZDR_MODELS_ONLY`) and/or enforce ZDR per request (`ZDR_ENFORCE`).
- **Tool-calling filter** — show all / only / exclude tool-capable models (`TOOL_CALLING_FILTER`).
- **Provider preferences** — `PROVIDER_ONLY` allowlist, `PROVIDER_QUANTIZATIONS`, `PROVIDER_ALLOW_FALLBACKS`, and `PROVIDER_MAX_PRICE_PROMPT/COMPLETION` price caps.
- **Free-tier filter** — `FREE_MODEL_FILTER` shows all / only / excludes free-tier models (`:free` suffix or `0/0` pricing).
- **Retry logic** — exponential backoff with proportional jitter on timeout/connection errors and on HTTP 429/502/503/504 (honours `Retry-After`).
- **Cost transparency** — `SHOW_COST_INFO` appends token usage + cost (currency configurable via `COST_CURRENCY`).
- **Pre-flight validation** — invalid API keys are caught at model-fetch time, not after sending a message.

## Requirements

- **[Open WebUI](https://docs.openwebui.com/)** ≥ 0.4.0 running locally or in Docker.
- **[OpenRouter API key](https://openrouter.ai/keys)** — free account, key starts with `sk-or-`.
- **Python** ≥ 3.10 (managed by Open WebUI; no separate install needed for the pipe).

## Installation

### From Open WebUI Community

Search for **"OpenRouter Pipe"** on [openwebui.com](https://openwebui.com) and install it directly
from the community hub — no copy-paste required.

### Manual install

1. Copy the full content of [`openrouter_pipe.py`](openrouter_pipe.py).
2. In Open WebUI, navigate to **Admin Panel → Functions**.
3. Click **+ Add Function** (or **Import**).
4. Paste the code and save.
5. **Enable** the function using the toggle.
6. Click the **⚙️ Valves** icon and enter your `OPENROUTER_API_KEY`.

All OpenRouter models will appear in the model selector immediately.

> **Note:** You can also set `OPENROUTER_API_KEY` as a server environment variable instead of
> entering it in Valves.

### From source

```bash
git clone https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter.git
cd Open-WebUI-Pipe-OpenRouter
pip install -r requirements.txt
python test_pipe.py        # 624 tests — verify everything is green
```

## Usage

All behavior is controlled through **Valves** in the Open WebUI admin panel. Every valve accepts
an environment variable fallback (see [Configuration](#configuration)).

### Common valve combinations

| Goal | Valves to set |
| --- | --- |
| Show only OpenAI and Anthropic models | `MODEL_PROVIDERS = openai,anthropic` |
| Show only free models | `FREE_MODEL_FILTER = only` |
| Use DeepSeek for reasoning | select `deepseek/deepseek-r1`, `INCLUDE_REASONING = true` |
| Route cheapest provider first | `PROVIDER_SORT = price` |
| Add a fallback model | `FALLBACK_MODELS = anthropic/claude-3.5-sonnet` |

### Reasoning tokens

When `INCLUDE_REASONING` is enabled (default), the pipe requests reasoning tokens from models that
support them. The internal reasoning appears inside `<think>…</think>` blocks before the main
response.

Set `REASONING_EFFORT` to `low`, `medium`, or `high` to control how much compute the model
allocates to reasoning. Leave it empty to let the model decide.

### Citations

Models with web-search capabilities return citation annotations. The pipe automatically converts
`[1]`, `[2]` references to `[[1]](url)` markdown links and appends a numbered **Citations:**
section at the end of the response.

## Configuration

Every valve accepts an environment variable fallback. The table below lists both.

### Core

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | `""` | Your OpenRouter API key |
| `OPENROUTER_BASE_URL` | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API endpoint |

### Reasoning

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `INCLUDE_REASONING` | `OPENROUTER_INCLUDE_REASONING` | `true` | Request reasoning tokens (`<think>` blocks) |
| `REASONING_EFFORT` | `OPENROUTER_REASONING_EFFORT` | `""` | Effort level: `minimal`, `low`, `medium`, `high`, `xhigh`, or empty |
| `REASONING_SUMMARY_MODE` | `OPENROUTER_REASONING_SUMMARY_MODE` | `disabled` | Reasoning-summary verbosity: `auto`, `concise`, `detailed`, `disabled` |
| `REASONING_MAX_TOKENS` | `OPENROUTER_REASONING_MAX_TOKENS` | `0` | Hard cap on reasoning tokens per response (0 disables the cap) |
| `ENABLE_ANTHROPIC_INTERLEAVED_THINKING` | `OPENROUTER_ANTHROPIC_INTERLEAVED_THINKING` | `true` | Auto-inject `anthropic-beta: interleaved-thinking-2025-05-14` for `anthropic/*` models |

### Display & Filtering

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `MODEL_PREFIX` | — | `None` | Custom prefix for model names (e.g. `🔥 `) |
| `MODEL_PROVIDERS` | `OPENROUTER_MODEL_PROVIDERS` | `ALL` | Provider filter (e.g. `openai,anthropic`). `ALL` means no filter |
| `INVERT_PROVIDER_LIST` | `OPENROUTER_INVERT_PROVIDER_LIST` | `false` | Treat `MODEL_PROVIDERS` as an exclusion list |
| `FREE_MODEL_FILTER` | `OPENROUTER_FREE_MODEL_FILTER` | `all` | Free-tier filter: `all` / `only` / `exclude` |
| `TOOL_CALLING_FILTER` | `OPENROUTER_TOOL_CALLING_FILTER` | `all` | Tool-capable filter (reads `supported_parameters`): `all` / `only` / `exclude` |
| `OUTPUT_MODALITIES` | `OPENROUTER_OUTPUT_MODALITIES` | `all` | Output modalities to fetch from `/models`. `all` (default) lists every model. Restrict with `text`, `image`, `audio`, `embeddings`, or a comma list (e.g. `text,audio`) |
| `MODEL_VARIANTS` | `OPENROUTER_MODEL_VARIANTS` | `""` | Comma-separated `base_id:tag` entries that surface virtual variant models (e.g. `openai/gpt-4o:nitro`). Tags: `free`, `thinking`, `online`, `nitro`, `exacto`, `extended` |
| `MODEL_CATEGORY` | `OPENROUTER_MODEL_CATEGORY` | `""` | Server-side category filter (`?category=`). Common values: `programming`, `roleplay`, `marketing`, `science`, `legal`, `finance`, `health`, `academia` |
| `HIDE_DEPRECATED_MODELS` | `OPENROUTER_HIDE_DEPRECATED_MODELS` | `false` | Hide models with a non-null `expiration_date`. When False, deprecated models are tagged `⚠ {name} (deprecated)` |
| `ZDR_MODELS_ONLY` | `OPENROUTER_ZDR_MODELS_ONLY` | `false` | Catalog-side: hide models without a ZDR endpoint (reads `/endpoints/zdr`) |

### Provider Routing

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `PROVIDER_SORT` | `OPENROUTER_PROVIDER_SORT` | `""` | Sort: `price`, `throughput`, `latency` |
| `PROVIDER_ORDER` | `OPENROUTER_PROVIDER_ORDER` | `""` | Preferred providers (comma-separated) |
| `PROVIDER_IGNORE` | `OPENROUTER_PROVIDER_IGNORE` | `""` | Excluded providers (comma-separated) |
| `PROVIDER_ONLY` | `OPENROUTER_PROVIDER_ONLY` | `""` | Provider allowlist (comma-separated). Merged with account-wide settings |
| `PROVIDER_QUANTIZATIONS` | `OPENROUTER_PROVIDER_QUANTIZATIONS` | `""` | Allowed quantizations (comma-separated, e.g. `bf16,fp8`) |
| `PROVIDER_ALLOW_FALLBACKS` | `OPENROUTER_PROVIDER_ALLOW_FALLBACKS` | `true` | When False, OpenRouter fails fast on the primary/ordered provider instead of falling back |
| `PROVIDER_MAX_PRICE_PROMPT` | `OPENROUTER_PROVIDER_MAX_PRICE_PROMPT` | `""` | Maximum prompt price (USD per 1M tokens) |
| `PROVIDER_MAX_PRICE_COMPLETION` | `OPENROUTER_PROVIDER_MAX_PRICE_COMPLETION` | `""` | Maximum completion price (USD per 1M tokens) |
| `SERVICE_TIER` | `OPENROUTER_SERVICE_TIER` | `""` | Service tier hint: `flex` (cheaper/slower) or `priority` (faster). Empty leaves it to the provider |
| `REQUIRE_PARAMETERS` | `OPENROUTER_REQUIRE_PARAMETERS` | `false` | Only use providers that support all request parameters |
| `DATA_COLLECTION` | `OPENROUTER_DATA_COLLECTION` | `allow` | Data policy: `allow` or `deny` |
| `ZDR_ENFORCE` | `OPENROUTER_ZDR_ENFORCE` | `false` | Send `provider.zdr=true` so OpenRouter routes only to ZDR endpoints (request fails if none available) |

### Advanced

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `FALLBACK_MODELS` | `OPENROUTER_FALLBACK_MODELS` | `""` | Fallback model IDs (comma-separated) |
| `ENABLE_MIDDLE_OUT` | `OPENROUTER_ENABLE_MIDDLE_OUT` | `false` | Middle-out compression for long prompts |
| `ENABLE_WEB_SEARCH` | `OPENROUTER_ENABLE_WEB_SEARCH` | `false` | Attach OpenRouter's `web` plugin so any model can ground answers in fresh web results |
| `WEB_SEARCH_MAX_RESULTS` | `OPENROUTER_WEB_SEARCH_MAX_RESULTS` | `5` | Max search results passed to the model (1-20) |
| `WEB_SEARCH_PROMPT` | `OPENROUTER_WEB_SEARCH_PROMPT` | `""` | Optional custom search prompt forwarded to the search engine |
| `WEB_SEARCH_INCLUDE_DOMAINS` | `OPENROUTER_WEB_SEARCH_INCLUDE_DOMAINS` | `""` | Domain allowlist (supports wildcards & paths) |
| `WEB_SEARCH_EXCLUDE_DOMAINS` | `OPENROUTER_WEB_SEARCH_EXCLUDE_DOMAINS` | `""` | Domain denylist |
| `ENABLE_CACHE_CONTROL` | `OPENROUTER_ENABLE_CACHE_CONTROL` | `false` | Inject Anthropic `cache_control` on the longest message |
| `ANTHROPIC_PROMPT_CACHE_TTL` | `OPENROUTER_ANTHROPIC_PROMPT_CACHE_TTL` | `5m` | TTL for the Anthropic ephemeral cache breakpoint: `5m` or `1h` |
| `SHOW_GENERATION_ID` | `OPENROUTER_SHOW_GENERATION_ID` | `false` | Append the OpenRouter generation ID to each response (for `GET /generation?id=` lookups) |
| `SYNC_PROVIDER_ICONS` | `OPENROUTER_SYNC_ICONS` | `true` | Sync provider icons into Open WebUI's model database |
| `USE_GSTATIC_FAVICONS` | `OPENROUTER_USE_GSTATIC_FAVICONS` | `false` | Allow registry-discovered Google gstatic favicons for providers without an OpenRouter-hosted icon. Off by default (avoids per-render requests to `t0.gstatic.com`) |

### Network

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `REQUEST_TIMEOUT` | `OPENROUTER_REQUEST_TIMEOUT` | `90` | HTTP timeout in seconds |
| `MAX_RETRIES` | — | `2` | Auto-retry count on transient errors |
| `MAX_TOOL_ITERATIONS` | `OPENROUTER_MAX_TOOL_ITERATIONS` | `5` | Max native tool-call rounds per request before stopping (caps runaway tool loops) |
| `HTTP_REFERER_OVERRIDE` | `OPENROUTER_HTTP_REFERER` | `""` | Override the `HTTP-Referer` header sent to OpenRouter (must include scheme). Empty falls back to `WEBUI_URL` |

### Cost Display

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `SHOW_COST_INFO` | — | `false` | Append token usage and cost to each response (also requests `usage` so streaming responses include cost) |
| `COST_CURRENCY` | `OPENROUTER_COST_CURRENCY` | `USD` | Currency label for the cost display (display only; OpenRouter bills in USD) |
| `SHOW_REMAINING_CREDIT` | `OPENROUTER_SHOW_REMAINING_CREDIT` | `false` | Append remaining OpenRouter credit after the cost line (cached ~60s `GET /credits` call; independent of Show Cost Info) |

> **Migration (v1.5.0):** the old boolean `FREE_ONLY` valve was replaced by `FREE_MODEL_FILTER` (`all` / `only` / `exclude`). Set `FREE_MODEL_FILTER = only` to preserve the old `FREE_ONLY = true` behaviour. For backward compatibility, the legacy `OPENROUTER_FREE_ONLY=true` environment variable is still honoured when `FREE_MODEL_FILTER` is unset.

### Per-user settings (UserValves)

On a shared Open WebUI instance, each user can override the admin defaults with their own values under **Valves → User Valves**:

- **`OPENROUTER_API_KEY`** — use a personal OpenRouter key instead of the admin key (leave blank to inherit the admin key).
- **Chat-path preferences** — reasoning, provider routing, web search, fallbacks, service tier, cache control, referer, timeout, retries, and cost display. Any field left unset inherits the admin default.

Catalog and display settings (model filters, `MODEL_PREFIX`, provider-icon sync, `OPENROUTER_BASE_URL`) are **admin-global** — the model list is built once without a user context, so per-user overrides of those would have no effect and are intentionally not exposed.

The merge is concurrency-safe: each request works on a copy of the admin valves, so users never affect each other's settings or keys.

### API key encryption at rest

The `OPENROUTER_API_KEY` (admin and per-user) is stored **encrypted** in Open WebUI's database when `WEBUI_SECRET_KEY` is set (Fernet, derived from that secret) and decrypted only at the moment a request is sent. If `WEBUI_SECRET_KEY` or the `cryptography` package is unavailable, the key falls back to plaintext storage with a one-time warning. Existing plaintext keys keep working and are re-encrypted on the next save.

> **Key rotation:** the encryption is keyed on `WEBUI_SECRET_KEY`. If that secret is rotated or removed after keys are stored, previously encrypted keys can no longer be decrypted and requests will fail with HTTP 401 — re-enter the API key(s) in Valves to re-encrypt under the new secret.

### Tool calling (native function calling)

Enable **Function Calling: Native** for the model in Open WebUI. The pipe then receives the selected tools, forwards them to OpenRouter, and runs the full tool loop itself: it executes the model's `tool_calls`, feeds the results back, and repeats until the model produces a final answer — in both streaming and non-streaming chats.

- **Parallel execution** — multiple tool calls in one round run concurrently.
- **Sync and async tools** are both supported; a failing tool returns its error to the model (the turn never crashes).
- **`MAX_TOOL_ITERATIONS`** (default 5) caps the number of tool rounds per request.

Open WebUI's default (prompt-based) tool mode is unaffected — it is handled by OWUI middleware and needs no pipe support.

## Architecture

The pipe implements the **Manifold** pattern: one pipe entry point that surfaces multiple models.

| Layer | Files | Responsibility |
| --- | --- | --- |
| Entry points | `Pipe.pipes()`, `Pipe.pipe()` | Model listing and chat routing |
| Payload | `_prepare_payload()` | Sanitize OWUI internals, inject routing and reasoning |
| Transport | `_retryable_request()` | Retry wrapper with exponential backoff |
| Streaming | `_stream_response()` | SSE parser, `<think>` management, mid-stream errors |
| Non-streaming | `_non_stream_response()` | JSON response, body-level error detection |
| Enrichment | `_inject_cache_control()`, `_insert_citations()` | Post-processing |

```text
Open-WebUI-Pipe-OpenRouter/
├── openrouter_pipe.py      # Main pipe source — install this in Open WebUI
├── function.json           # Open WebUI community manifest
├── test_pipe.py            # Unit test suite (624 tests)
├── integration_test.py     # Live API integration tests (44 assertions)
├── TESTING.md              # Manual pre-release checklist
├── SECURITY.md             # Security policy
├── CONTRIBUTING.md         # Contribution guidelines
├── CHANGELOG.md            # Version history
├── LICENSE                 # MIT License
├── requirements.txt        # Python dependencies
└── .github/
    ├── workflows/
    │   └── tests.yml       # CI pipeline (Python 3.10–3.13)
    └── ISSUE_TEMPLATE/
        ├── bug_report.yml
        └── feature_request.yml
```

The pipe strips these Open WebUI-internal keys before forwarding to OpenRouter:

```python
_OWUI_INTERNAL_KEYS = {
    "chat_id", "title", "task", "task_id", "features", "citations",
    "metadata", "files", "tool_ids", "session_id", "message_id"
}
```

It also removes `user` when sent as a dict (Open WebUI format) since OpenRouter expects a string.

## Development

```bash
python test_pipe.py                       # Unit tests (624 tests)
python integration_test.py               # Live API tests (requires OPENROUTER_API_KEY)
```

The unit test suite covers: valve defaults, payload preparation, streaming and non-streaming
responses, retry logic, citation injection, model listing, and `pipe()` routing.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full playbook.

## Troubleshooting

### "OpenRouter API key not configured"

#### Solution

Set your API key in **Admin Panel → Functions → OpenRouter Pipe → Valves** (⚙️), or set the
`OPENROUTER_API_KEY` environment variable on the server and restart Open WebUI.

### "Invalid API key (HTTP 401 / 502)"

#### Solution

Your key is incorrect or malformed. Retrieve a valid key from
[openrouter.ai/keys](https://openrouter.ai/keys) — it should start with `sk-or-`.

### "Rate limit exceeded (HTTP 429)"

#### Solution

Wait a moment and retry. `MAX_RETRIES` only retries on network timeouts and connection failures —
HTTP 429 errors are returned immediately. Consider upgrading your OpenRouter plan for higher limits.

### "Insufficient credits (HTTP 402)"

#### Solution

Add credits at [openrouter.ai/credits](https://openrouter.ai/credits).

### "Request timed out"

#### Solution

Increase `REQUEST_TIMEOUT` in Valves (default: 90 seconds), or try a faster model. Some large
reasoning models can take over a minute for complex prompts.

### No models appear in the selector

#### Solution

1. Verify your API key is valid (a single "error" model appears if it is not).
2. If `MODEL_PROVIDERS` is set, confirm the provider names are lowercase: `openai`, `anthropic`, `google`.
3. If `FREE_MODEL_FILTER = only` is set, some providers may have no free models — set it back to `all`.
4. Set `MODEL_PROVIDERS = ALL` to show the full catalog.

### Models load but chat returns errors

#### Solution

Some models may be temporarily unavailable. Try a different model or check
[status.openrouter.ai](https://status.openrouter.ai).

## FAQ

**Q: Does this work with Open WebUI's native tool calling?**

A: Open WebUI manages tool calling in an iterative loop: when the pipe's response contains
tool calls, Open WebUI executes them, appends the results as `role: "tool"` messages, and
re-invokes the pipe with the updated thread. The pipe forwards the full message list to
OpenRouter on each invocation. Whether a model can generate tool calls depends on
OpenRouter's provider support for that model.

**Q: Why does `FREE_MODEL_FILTER = only` include models without a `:free` suffix?**

A: Some models are listed as free on OpenRouter without carrying a `:free` suffix in their
ID. The pipe uses a two-pass check: first it looks for the `:free` suffix, then it falls
back to inspecting the `pricing.prompt` and `pricing.completion` fields returned by the
OpenRouter `/models` endpoint — if both are `0`, the model is treated as free.

**Q: Can I use multiple provider filters at once?**

A: `MODEL_PROVIDERS` accepts a comma-separated list (e.g. `openai,anthropic`). Enable
`INVERT_PROVIDER_LIST` to turn it into an exclusion list instead.

**Q: How do fallback models work?**

A: `FALLBACK_MODELS` adds extra model IDs to the `models` array in the OpenRouter request. If the
primary model fails, OpenRouter automatically tries the next one. Non-streaming responses include
a "Responded by: model-id" attribution when a fallback handled the request.

**Q: I selected a TTS / embeddings / image-generation model and got an error — why?**

A: The pipe routes every request through OpenRouter's `/chat/completions` endpoint. Models that
only expose a non-chat endpoint (e.g. pure TTS models served via `/audio/speech`) return an
"endpoint not supported" error from OpenRouter. The pipe surfaces that error verbatim. Chat
completion models that *output* audio or images (e.g. `openai/gpt-audio`) work normally — their
audio transcript and generated images are rendered inline. To hide non-chat models from the
selector entirely, set `OUTPUT_MODALITIES = text`.

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
