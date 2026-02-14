<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:1a1b2e,100:2d1b69&height=180&section=header&text=OpenRouter%20Pipe&fontColor=a78bfa&fontSize=42&animation=fadeIn&fontAlignY=36&desc=Open%20WebUI%20%E2%86%94%20OpenRouter%20Integration&descAlignY=56&descColor=8b5cf6" width="100%"/>

<a href="https://github.com/sena-labs/OpenRouter-Pipe"><img src="https://img.shields.io/badge/version-0.2.0-0d1117?style=for-the-badge&labelColor=7c3aed&color=0d1117" alt="version"></a>&nbsp;
<a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-≥3.10-0d1117?style=for-the-badge&logo=python&logoColor=white&labelColor=3776AB" alt="python"></a>&nbsp;
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0d1117?style=for-the-badge&labelColor=blue" alt="license"></a>&nbsp;
<a href="https://docs.openwebui.com"><img src="https://img.shields.io/badge/Open%20WebUI-compatible-0d1117?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyem0wIDE4Yy00LjQyIDAtOC0zLjU4LTgtOHMzLjU4LTggOC04IDggMy41OCA4IDgtMy41OCA0LTggOHoiLz48L3N2Zz4=&logoColor=white&labelColor=1a1a2e" alt="openwebui"></a>

</div>

# OpenRouter Pipe

**Access 300+ AI models through OpenRouter directly inside Open WebUI.**

Provider routing · Reasoning tokens · Streaming · Fallbacks · Cache control

---

## Quick Start

### Prerequisites

- [Open WebUI](https://docs.openwebui.com) v0.4+ running
- [OpenRouter](https://openrouter.ai) API key

### Installation

1. **Open your Open WebUI instance**
2. Navigate to **Admin Panel → Functions**
3. Click **"+ Add Function"** (or **Import**)
4. Paste the entire contents of [`openrouter_pipe.py`](openrouter_pipe.py)
5. Save and **enable** the function
6. Go to **Valves** (⚙️ icon) and enter your `OPENROUTER_API_KEY`
7. All OpenRouter models will appear in your model selector

> **Tip:** You can also set the API key via environment variable `OPENROUTER_API_KEY` on the server.

Alternatively, search for **"OpenRouter Pipe"** on [openwebui.com](https://openwebui.com) and install it directly from the community hub.

---

## Features

| Feature | Description |
|---------|-------------|
| **Manifold Pipe** | Exposes all OpenRouter models as native Open WebUI models |
| **Provider Routing** | Sort by price/throughput/latency, prefer or exclude providers |
| **Reasoning Tokens** | `<think>` tags with configurable effort (low/medium/high) |
| **Streaming** | Full SSE streaming with mid-stream error handling |
| **Model Fallbacks** | Automatic failover to backup models |
| **Middle-Out Compression** | Fit long prompts within context windows |
| **Cache Control** | Anthropic-style prompt caching for cost savings |
| **Citations** | Auto-inject citation links from web-search enabled models |
| **Provider Icons** | 22 provider logos displayed in the model selector |
| **Retry Logic** | Configurable auto-retry on timeout/connection errors |
| **FREE_ONLY Mode** | Filter to show only free-tier models |

---

## Configuration

All settings are configurable via **Valves** in the Open WebUI admin panel. Every valve also accepts an environment variable fallback.

### Core

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | `""` | Your OpenRouter API key |
| `OPENROUTER_BASE_URL` | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API endpoint |

### Reasoning

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `INCLUDE_REASONING` | `OPENROUTER_INCLUDE_REASONING` | `true` | Request reasoning tokens (shows `<think>` blocks) |
| `REASONING_EFFORT` | `OPENROUTER_REASONING_EFFORT` | `""` | Effort level: `low`, `medium`, `high`, or empty to disable |

### Display & Filtering

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `MODEL_PREFIX` | — | `None` | Custom prefix for model names (e.g. `🔥 `) |
| `MODEL_PROVIDERS` | `OPENROUTER_MODEL_PROVIDERS` | `None` | Comma-separated provider filter (e.g. `openai,anthropic`) |
| `INVERT_PROVIDER_LIST` | `OPENROUTER_INVERT_PROVIDER_LIST` | `false` | Invert filter → exclusion list |
| `FREE_ONLY` | `OPENROUTER_FREE_ONLY` | `false` | Show only `:free` models |

### Provider Routing

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `PROVIDER_SORT` | `OPENROUTER_PROVIDER_SORT` | `""` | Sort: `price`, `throughput`, `latency` |
| `PROVIDER_ORDER` | `OPENROUTER_PROVIDER_ORDER` | `""` | Preferred providers (comma-separated) |
| `PROVIDER_IGNORE` | `OPENROUTER_PROVIDER_IGNORE` | `""` | Excluded providers (comma-separated) |
| `REQUIRE_PARAMETERS` | `OPENROUTER_REQUIRE_PARAMETERS` | `false` | Only use providers supporting all request params |
| `DATA_COLLECTION` | `OPENROUTER_DATA_COLLECTION` | `allow` | Data policy: `allow` or `deny` |

### Advanced

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `FALLBACK_MODELS` | `OPENROUTER_FALLBACK_MODELS` | `""` | Fallback model IDs (comma-separated) |
| `ENABLE_MIDDLE_OUT` | `OPENROUTER_ENABLE_MIDDLE_OUT` | `false` | Middle-out compression for long prompts |
| `ENABLE_CACHE_CONTROL` | `OPENROUTER_ENABLE_CACHE_CONTROL` | `false` | Anthropic cache_control injection |

### Network

| Valve | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `REQUEST_TIMEOUT` | `OPENROUTER_REQUEST_TIMEOUT` | `90` | HTTP timeout in seconds |
| `MAX_RETRIES` | — | `2` | Auto-retry on transient errors |

---

## API Reference

### Architecture

This pipe implements the **Manifold** pattern:

```
Open WebUI ↔️ Pipe.pipes()   → model list from OpenRouter /models
Open WebUI ↔️ Pipe.pipe()    → chat completions via OpenRouter /chat/completions
```

### Key Methods

| Method | Description |
|--------|-------------|
| `pipes()` | Fetches and filters the model catalog from OpenRouter |
| `pipe(body, __user__)` | Routes chat completion to stream or non-stream handler |
| `_prepare_payload(body)` | Sanitizes OWUI internals, injects provider routing, reasoning, fallbacks |
| `_stream_response(headers, payload)` | SSE parser with `<think>` management and mid-stream error recovery |
| `_non_stream_response(headers, payload)` | JSON response handler with body-level error detection |
| `_retryable_request(headers, payload, stream)` | Retry wrapper for timeout/connection errors |
| `_inject_cache_control(payload)` | Applies Anthropic `cache_control` to longest message chunk |

### Payload Sanitization

The pipe strips these Open WebUI internal keys before forwarding to OpenRouter:

```python
_OWUI_INTERNAL_KEYS = {"chat_id", "title", "task", "task_id", "features", "citations"}
```

It also removes `user` when sent as a dict (OWUI format) since OpenRouter expects a string.

---

## Project Structure

```
OpenRouter-Pipe/
├── openrouter_pipe.py      # Main pipe source (install this in Open WebUI)
├── function.json           # Open WebUI community manifest (metadata, tags, categories)
├── test_pipe.py            # Test suite
├── README.md               # This file
├── CHANGELOG.md            # Version history
├── CONTRIBUTING.md         # Contribution guidelines
├── LICENSE                 # MIT License
└── .gitignore              # Git ignore rules
```

---

## Testing

```bash
python test_pipe.py
```

Tests cover:
- Helper functions (`_insert_citations`, `_format_citation_list`, `_parse_csv`)
- Valve defaults and validation
- Payload preparation (key stripping, model ID fix, provider routing, fallbacks)
- Stream response (reasoning tags, mid-stream errors, auto-close, citations)
- Non-stream response (API errors, empty choices, timeout handling)
- Retry logic (success, retry on timeout, exhaustion, HTTPError passthrough)
- Async `pipe()` entry point (stream/non-stream routing)
- Model listing (`pipes()`) with filters, prefix, error handling

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
Copyright (c) 2026 Sena Labs
```

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2d1b69,50:1a1b2e,100:0d1117&height=100&section=footer" width="100%"/>

Powered by **[Sena Labs](https://github.com/sena-labs)**

</div>
