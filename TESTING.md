# Pre-Release Testing Guide

Manual checklist to verify every Pipe feature before release. Run the automated suite first,
then work through each section in order against a live Open WebUI instance.

## Prerequisites

- **Open WebUI** ≥ 0.4.0 running locally or in Docker.
- A valid **OpenRouter API key** (starts with `sk-or-`).

---

## 0. Automated tests

```bash
python test_pipe.py
```

Must exit with `All tests passed! ✓` and `✗ Failed: 0`. If any test fails, **do not release**.

---

## 1. Installation and loading

| # | Action | Expected result |
|---|--------|-----------------|
| 1.1 | Paste the contents of `openrouter_pipe.py` into **Functions > Pipe** in Open WebUI | No errors, the pipe is saved |
| 1.2 | Open **Admin > Settings > Connections** and verify the pipe appears | Type **manifold**, purple SVG icon visible |
| 1.3 | Select the pipe and open **Valves** | All configurable fields are visible with correct defaults |

---

## 2. API Key and model list

| # | Action | Expected result |
|---|--------|-----------------|
| 2.1 | Leave `OPENROUTER_API_KEY` empty > open the model selector | A single "error" model appears with message `API key not configured` |
| 2.2 | Enter a valid key in Valves > reopen the selector | OpenRouter models appear (400+ models), each with provider icon |
| 2.3 | Enter an **invalid** key (e.g. `sk-fake`) > reopen the selector | An "error" model appears with message `Invalid API key (HTTP ...)` |

---

## 3. Non-streaming chat

| # | Action | Expected result |
|---|--------|-----------------|
| 3.1 | Select a model (e.g. `openai/gpt-4o`), type "Hello" with `stream: false` | The response appears all at once, correct text |
| 3.2 | Select a reasoning model (e.g. `deepseek/deepseek-r1`) | The response contains `<think>...</think>` blocks followed by content |

---

## 4. Streaming chat (SSE)

| # | Action | Expected result |
|---|--------|-----------------|
| 4.1 | Select a model, type "Tell me a story" with stream enabled | Text appears token by token in real time |
| 4.2 | Use a reasoning model in streaming | `<think>` tag opens, progressive reasoning, `</think>` closes, then content |
| 4.3 | During streaming, verify in the Network tab that each SSE chunk starts with `data: ` | Correct SSE format |

---

## 5. Reasoning tokens

| # | Action | Expected result |
|---|--------|-----------------|
| 5.1 | Set `INCLUDE_REASONING = true` (default) | Payload contains `"include_reasoning": true` |
| 5.2 | Set `INCLUDE_REASONING = false` | The `include_reasoning` field does **not** appear in payload |
| 5.3 | Set `REASONING_EFFORT = high` | Payload contains `"reasoning": {"effort": "high"}` |
| 5.4 | Set `REASONING_EFFORT = ""` (empty) | No `reasoning` field in payload |
| 5.5 | Try effort `low`, `medium`, `high` | Accepted. Any other value is ignored |

---

## 6. Provider routing

| # | Action | Expected result |
|---|--------|-----------------|
| 6.1 | Set `PROVIDER_SORT = throughput` | payload > `provider.sort = "throughput"` |
| 6.2 | Set `PROVIDER_ORDER = anthropic, openai` | payload > `provider.order = ["anthropic", "openai"]` |
| 6.3 | Set `PROVIDER_IGNORE = google` | payload > `provider.ignore = ["google"]` |
| 6.4 | Set `REQUIRE_PARAMETERS = true` | payload > `provider.require_parameters = true` |
| 6.5 | Set `DATA_COLLECTION = deny` | payload > `provider.data_collection = "deny"` |
| 6.6 | Leave all empty/default | No `provider` field in payload |

---

## 7. Model filter

| # | Action | Expected result |
|---|--------|-----------------|
| 7.1 | Set `MODEL_PROVIDERS = openai` | Only OpenAI models visible in selector |
| 7.2 | Set `MODEL_PROVIDERS = openai` + `INVERT_PROVIDER_LIST = true` | All models **except** OpenAI visible |
| 7.3 | Set `MODEL_PROVIDERS = ALL` or clear the field | **All** models visible again. Default `ALL` means no filter |
| 7.4 | Set `FREE_MODEL_FILTER = only` | Only free models (including those with pricing 0/0 without `:free` suffix) |
| 7.5 | `FREE_MODEL_FILTER = only` > verify that free `google/gemma-*` or `qwen/qwen3-*` appear | Models without `:free` but with pricing 0/0 are included |
| 7.6 | Set `FREE_MODEL_FILTER = exclude` | Free models hidden; only paid models remain |
| 7.7 | Set env `OPENROUTER_FREE_ONLY=true` (legacy), leave `FREE_MODEL_FILTER` unset | Back-compat: behaves like `only` |

---

## 8. Model prefix

| # | Action | Expected result |
|---|--------|-----------------|
| 8.1 | Set `MODEL_PREFIX = "🔥 "` | All model names start with `🔥 ` in the selector |
| 8.2 | Clear `MODEL_PREFIX` | Model names without prefix (the UI allows clearing the field) |

---

## 9. Fallback models

| # | Action | Expected result |
|---|--------|-----------------|
| 9.1 | While using `openai/gpt-4o` as primary, set `FALLBACK_MODELS = anthropic/claude-3.5-sonnet` | payload contains `"models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]` (primary model first, then fallbacks) |
| 9.2 | Leave `FALLBACK_MODELS` empty | No `models` field in payload |

---

## 10. Middle-out compression

| # | Action | Expected result |
|---|--------|-----------------|
| 10.1 | Set `ENABLE_MIDDLE_OUT = true` | payload > `"transforms": ["middle-out"]` |
| 10.2 | `ENABLE_MIDDLE_OUT = false` | No `transforms` field in payload |

---

## 11. Cache control (Anthropic)

| # | Action | Expected result |
|---|--------|-----------------|
| 11.1 | Set `ENABLE_CACHE_CONTROL = true`, send a long prompt with list-type content | The longest text chunk receives `"cache_control": {"type": "ephemeral"}` |
| 11.2 | `ENABLE_CACHE_CONTROL = false` | No modification to messages |
| 11.3 | Send a message with plain string content + cache enabled | No crash, cache not applied (list-type content only) |

---

## 12. Retry logic

| # | Action | Expected result |
|---|--------|-----------------|
| 12.1 | Set `MAX_RETRIES = 2`, simulate a temporary server timeout | The pipe retries up to 3 total attempts (1 + 2 retries), then shows error |
| 12.2 | Check logs for `[OpenRouter Pipe] Attempt X failed:` | Logs show each failed attempt |
| 12.3 | A non-transient 4xx error (e.g. 401/403/404) is **not** retried | Error returned immediately without retry |
| 12.4 | HTTP 429 or transient 5xx (502/503/504) with `MAX_RETRIES ≥ 1` | Retried within the budget; succeeds, or surfaces the error after exhaustion |
| 12.5 | A 429/503 response carrying `Retry-After` | The pipe waits the indicated delay (capped at 60s) before retrying |

---

## 13. Timeout

| # | Action | Expected result |
|---|--------|-----------------|
| 13.1 | Set `REQUEST_TIMEOUT = 5` (seconds), send a prompt to a slow model | After 5s `timeout` appears in the error message |
| 13.2 | Set `REQUEST_TIMEOUT = -1` | Pydantic validation error: value not saved in valves |
| 13.3 | Default `REQUEST_TIMEOUT = 90` | Works normally without premature timeouts |

---

## 14. Error handling

| # | Action | Expected result |
|---|--------|-----------------|
| 14.1 | Send a prompt that triggers an API error (e.g. non-existent model) | Message `OpenRouter Error: HTTP 4xx — ...` |
| 14.2 | Stream with mid-stream error (e.g. context_length_exceeded) | Partial content is preserved, then error message appears |
| 14.3 | Stream with open `<think>` + error | `</think>` is automatically closed before the error message |

---

## 15. Citations

| # | Action | Expected result |
|---|--------|-----------------|
| 15.1 | Use a model that returns citations (e.g. with web search plugin) | References `[1]`, `[2]` in text are converted to markdown links `[[1]](url)` |
| 15.2 | The `Citations:` section appears at the end of the response | Numbered list of URLs |
| 15.3 | Stream with citations in a separate chunk | Citations are correctly applied to subsequent portions |

---

## 16. Headers and security

| # | Action | Expected result |
|---|--------|-----------------|
| 16.1 | In the Network tab, verify the request headers | `Authorization: Bearer sk-or-...`, `HTTP-Referer`, `X-Title`, `Content-Type` |
| 16.2 | Verify the API key **never** appears in logs or error messages | Only generic errors, never the key value |
| 16.3 | Verify no Open WebUI internal fields (`chat_id`, `title`, `task`, `features`) are in the payload | All removed before sending |

---

## 17. Provider icons

| # | Action | Expected result |
|---|--------|-----------------|
| 17.1 | Open the model selector | Models from OpenAI, Anthropic, Google, Meta, etc. show their own icon |
| 17.2 | Check an unknown provider (e.g. `aion-labs`) | No icon (empty field), no error |
| 17.3 | Leave `USE_GSTATIC_FAVICONS = false` (default) | Providers only resolvable via gstatic show OWUI's default icon (no `t0.gstatic.com` requests) |
| 17.4 | Set `USE_GSTATIC_FAVICONS = true` | Registry-discovered gstatic favicons appear for extra providers |

---

## 18. Output modalities & catalog filters (v1.4–v1.6)

| # | Action | Expected result |
|---|--------|-----------------|
| 18.1 | Default `OUTPUT_MODALITIES = all` | TTS / audio / image / embedding models appear alongside chat models |
| 18.2 | Set `OUTPUT_MODALITIES = text` | Only text-output models listed; `/models` request carries `output_modalities=text` |
| 18.3 | Set `MODEL_CATEGORY = programming` | `/models` request carries `category=programming`; catalog narrows |
| 18.4 | Set `HIDE_DEPRECATED_MODELS = false` | Deprecated models appear tagged `⚠ … (deprecated)` |
| 18.5 | Set `HIDE_DEPRECATED_MODELS = true` | Deprecated models removed from the selector |
| 18.6 | Set `TOOL_CALLING_FILTER = only` | Only tool-capable models listed |
| 18.7 | Set `ZDR_MODELS_ONLY = true` | Catalog narrows to ZDR-capable models (`/endpoints/zdr` consulted) |

---

## 19. Reasoning extensions (v1.5)

| # | Action | Expected result |
|---|--------|-----------------|
| 19.1 | `REASONING_EFFORT = minimal` / `xhigh` | Payload `reasoning.effort` carries the value |
| 19.2 | `REASONING_MAX_TOKENS = 2000` | Payload `reasoning.max_tokens = 2000` |
| 19.3 | `REASONING_SUMMARY_MODE = concise` | Payload `reasoning.summary = "concise"` |
| 19.4 | Anthropic model + `ENABLE_ANTHROPIC_INTERLEAVED_THINKING = true` | Request carries header `anthropic-beta: interleaved-thinking-2025-05-14` |
| 19.5 | `ANTHROPIC_PROMPT_CACHE_TTL = 1h` | Anthropic cache breakpoint uses the `1h` TTL |

---

## 20. Provider preferences, service tier, ZDR enforce (v1.5–v1.6)

| # | Action | Expected result |
|---|--------|-----------------|
| 20.1 | `PROVIDER_ONLY = openai` | Payload `provider.only = ["openai"]` |
| 20.2 | `PROVIDER_QUANTIZATIONS = bf16,fp8` | Payload `provider.quantizations = ["bf16","fp8"]` |
| 20.3 | `PROVIDER_MAX_PRICE_PROMPT = 5` | Payload `provider.max_price.prompt = 5` |
| 20.4 | `SERVICE_TIER = flex` | Payload top-level `service_tier = "flex"` |
| 20.5 | `ZDR_ENFORCE = true` | Payload `provider.zdr = true` |

---

## 21. Web search, generation ID, cost (v1.6)

| # | Action | Expected result |
|---|--------|-----------------|
| 21.1 | `ENABLE_WEB_SEARCH = true` | Payload `plugins` contains a `web` entry with `max_results` / domain filters |
| 21.2 | `WEB_SEARCH_INCLUDE_DOMAINS = example.com` | Web plugin carries the allowlist |
| 21.3 | `SHOW_GENERATION_ID = true`, non-stream | Response ends with `*Generation ID: gen-…*` |
| 21.4 | `SHOW_GENERATION_ID = true`, streaming | Footer still appears at end of the stream |
| 21.5 | `SHOW_COST_INFO = true`, streaming | Cost line appears (payload sends `usage.include=true`); cached-token split shown when reported |

---

## 22. Variant routing (v1.5)

| # | Action | Expected result |
|---|--------|-----------------|
| 22.1 | `MODEL_VARIANTS = openai/gpt-4o:nitro` | A virtual `GPT-4o Nitro` row appears in the selector with the OpenAI icon |
| 22.2 | `MODEL_VARIANTS = unknown/model:nitro` | Silently skipped (base not in catalog), no error |
| 22.3 | `MODEL_VARIANTS = openai/gpt-4o:bogus` | Unknown tag dropped |

---

## 23. Referer override (v1.5)

| # | Action | Expected result |
|---|--------|-----------------|
| 23.1 | `HTTP_REFERER_OVERRIDE = https://my.app` | `HTTP-Referer` header = `https://my.app` |
| 23.2 | `HTTP_REFERER_OVERRIDE` with CR/LF or non-http value | Ignored; falls back to `WEBUI_URL`/default (no header injection) |

---

## 24. Per-user valves & key encryption (v1.7)

| # | Action | Expected result |
|---|--------|-----------------|
| 24.1 | With `WEBUI_SECRET_KEY` set, save an API key in admin Valves, then inspect the stored function valves in OWUI's DB | Stored `OPENROUTER_API_KEY` is ciphertext prefixed `encrypted:` (not the raw `sk-or-...` key) |
| 24.2 | Chat with the encrypted key | Request succeeds — the key is decrypted only for the `Authorization` header |
| 24.3 | As a non-admin user, set a personal key under Valves → User Valves, then chat | Request uses the user's own key (verify via that key's OpenRouter usage/credits) |
| 24.4 | As a user, leave the User Valves key blank but set `REASONING_EFFORT = high` | Request inherits the admin key but uses the user's reasoning effort |
| 24.5 | Two users with different User Valves chat concurrently | Each request uses that user's own settings; neither leaks into the other (admin valves unchanged) |
| 24.6 | Unset `WEBUI_SECRET_KEY` (or remove `cryptography`) and load the pipe | Key stored/used as plaintext; one-time `[OpenRouter Pipe] API key stored in plaintext (...)` warning; pipe still works |

---

## 25. Native tool calling & remaining credit (v1.8)

| # | Action | Expected result |
|---|--------|-----------------|
| 25.1 | Enable Function Calling: Native, give the model a tool, ask something that needs it (non-streaming) | Tool runs; model's final answer uses the tool result |
| 25.2 | Same as 25.1 but streaming | Answer streams after the tool executes; tool-call internals not shown as content |
| 25.3 | A prompt that triggers multiple tools in one round | Tools execute in parallel; all results fed back |
| 25.4 | A tool that raises / bad args | Error returned to the model as the tool result; turn does not crash |
| 25.5 | Force a tool loop beyond `MAX_TOOL_ITERATIONS` | Loop stops at the cap with a `Tool calling stopped: reached MAX_TOOL_ITERATIONS.` note |
| 25.6 | Set `SHOW_REMAINING_CREDIT = true`, chat | Response shows `OpenRouter credit remaining: $…` after the cost line; repeat within ~60s makes no extra `/credits` call |

---

## Quick pre-release checklist

- [ ] `python test_pipe.py` → 696 passed, 0 failed
- [ ] `python integration_test.py` → 44/44
- [ ] Empty API key → clear error message in model selector
- [ ] Valid API key → 400+ models with provider icons
- [ ] Non-streaming chat works
- [ ] Streaming chat works (token by token)
- [ ] Reasoning tokens shown with `<think>`
- [ ] `FREE_MODEL_FILTER` filters correctly (`only`/`exclude`/`all`; `:free` suffix + 0/0 pricing)
- [ ] Provider filter + inversion works
- [ ] Model prefix applied and removable
- [ ] Fallback models present in payload
- [ ] Middle-out present in payload
- [ ] Cache control applied on list-type message content
- [ ] Retry on timeout, no retry on 4xx errors
- [ ] Errors formatted correctly (no raw tracebacks)
- [ ] No secrets in logs or error messages
- [ ] Open WebUI internal fields removed from payload
- [ ] API key stored encrypted at rest (`encrypted:` prefix) when `WEBUI_SECRET_KEY` is set
- [ ] Per-user UserValves override admin defaults; admin key inherited when the user key is blank
