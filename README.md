# OpenRouter Pipe

[![Build](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/workflows/tests.yml/badge.svg)](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-%E2%89%A53.10-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Access **300+ AI models** through OpenRouter directly inside Open WebUI — with provider routing,
reasoning tokens, streaming, fallbacks, and cache control out of the box.

## Feature gallery

### Model selector

*Models from OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek and more — each with its provider icon.*

### Reasoning tokens

*`<think>` blocks streamed in real time with configurable effort levels.*

### Provider routing in action

*Sort, prefer, exclude and require parameters across providers per request.*

---

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

- **Manifold pipe** — exposes all OpenRouter models as native Open WebUI models in the model selector.
- **Provider routing** — sort by `price`, `throughput`, or `latency`; prefer or exclude specific providers; enforce `require_parameters`.
- **Reasoning tokens** — `<think>` blocks streamed in real time with configurable effort (`low`, `medium`, `high`).
- **Streaming** — full SSE streaming with mid-stream error handling and automatic `<think>` closure on error.
- **Model fallbacks** — automatic failover to one or more backup models via `FALLBACK_MODELS`.
- **Middle-out compression** — fits long prompts within context windows (`transforms: ["middle-out"]`).
- **Cache control** — Anthropic-style `cache_control` injection on the longest message chunk.
- **Citations** — `[n]` references from web-search-enabled models are converted to markdown links.
- **Provider icons** — 22 provider logos synced directly into Open WebUI's model database.
- **Retry logic** — exponential backoff with jitter on timeout and connection errors.
- **FREE_ONLY mode** — filter to show only free-tier models (`:free` suffix or `0/0` pricing).
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
python test_pipe.py        # 252 tests — verify everything is green
```

## Usage

All behavior is controlled through **Valves** in the Open WebUI admin panel. Every valve accepts
an environment variable fallback (see [Configuration](#configuration)).

### Common valve combinations

| Goal | Valves to set |
| --- | --- |
| Show only OpenAI and Anthropic models | `MODEL_PROVIDERS = openai,anthropic` |
| Show only free models | `FREE_ONLY = true` |
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
| `REASONING_EFFORT` | `OPENROUTER_REASONING_EFFORT` | `""` | Effort level: `low`, `medium`, `high`, or empty |

### Display & Filtering

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `MODEL_PREFIX` | — | `None` | Custom prefix for model names (e.g. `🔥 `) |
| `MODEL_PROVIDERS` | `OPENROUTER_MODEL_PROVIDERS` | `ALL` | Provider filter (e.g. `openai,anthropic`). `ALL` means no filter |
| `INVERT_PROVIDER_LIST` | `OPENROUTER_INVERT_PROVIDER_LIST` | `false` | Treat `MODEL_PROVIDERS` as an exclusion list |
| `FREE_ONLY` | `OPENROUTER_FREE_ONLY` | `false` | Show only free-tier models |

### Provider Routing

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `PROVIDER_SORT` | `OPENROUTER_PROVIDER_SORT` | `""` | Sort: `price`, `throughput`, `latency` |
| `PROVIDER_ORDER` | `OPENROUTER_PROVIDER_ORDER` | `""` | Preferred providers (comma-separated) |
| `PROVIDER_IGNORE` | `OPENROUTER_PROVIDER_IGNORE` | `""` | Excluded providers (comma-separated) |
| `REQUIRE_PARAMETERS` | `OPENROUTER_REQUIRE_PARAMETERS` | `false` | Only use providers that support all request parameters |
| `DATA_COLLECTION` | `OPENROUTER_DATA_COLLECTION` | `allow` | Data policy: `allow` or `deny` |

### Advanced

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `FALLBACK_MODELS` | `OPENROUTER_FALLBACK_MODELS` | `""` | Fallback model IDs (comma-separated) |
| `ENABLE_MIDDLE_OUT` | `OPENROUTER_ENABLE_MIDDLE_OUT` | `false` | Middle-out compression for long prompts |
| `ENABLE_CACHE_CONTROL` | `OPENROUTER_ENABLE_CACHE_CONTROL` | `false` | Inject Anthropic `cache_control` on the longest message |
| `SYNC_PROVIDER_ICONS` | `OPENROUTER_SYNC_ICONS` | `true` | Sync provider icons into Open WebUI's model database |

### Network

| Valve | Env Var | Default | Description |
| --- | --- | --- | --- |
| `REQUEST_TIMEOUT` | `OPENROUTER_REQUEST_TIMEOUT` | `90` | HTTP timeout in seconds |
| `MAX_RETRIES` | — | `2` | Auto-retry count on transient errors |

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
├── test_pipe.py            # Unit test suite (252 tests)
├── integration_test.py     # Live API integration tests (47 tests)
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
python test_pipe.py                       # Unit tests (252 tests)
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
3. If `FREE_ONLY` is enabled, some providers may have no free models — try disabling it.
4. Set `MODEL_PROVIDERS = ALL` to show the full catalog.

### Models load but chat returns errors

#### Solution

Some models may be temporarily unavailable. Try a different model or check
[status.openrouter.ai](https://status.openrouter.ai).

## FAQ

**Q: Does this work with Open WebUI's native tool calling?**

A: Tool calling is handled by Open WebUI before the pipe receives the request — the pipe forwards
the composed messages as-is. Whether a given OpenRouter model supports tool use depends on
OpenRouter's provider support for that model.

**Q: Why does `FREE_ONLY` include models without a `:free` suffix?**

A: Some models (e.g. `google/gemma-*`, `qwen/qwen3-*`) are genuinely free but are not suffixed
with `:free`. The pipe checks both the suffix and the actual pricing (`0/0` prompt and completion
cost) to catch these cases.

**Q: Can I use multiple provider filters at once?**

A: `MODEL_PROVIDERS` accepts a comma-separated list (e.g. `openai,anthropic`). Enable
`INVERT_PROVIDER_LIST` to turn it into an exclusion list instead.

**Q: How do fallback models work?**

A: `FALLBACK_MODELS` adds extra model IDs to the `models` array in the OpenRouter request. If the
primary model fails, OpenRouter automatically tries the next one. Non-streaming responses include
a "Responded by: model-id" attribution when a fallback handled the request.

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
