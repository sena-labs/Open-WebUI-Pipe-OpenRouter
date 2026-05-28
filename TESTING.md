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
| 2.2 | Enter a valid key in Valves > reopen the selector | OpenRouter models appear (340+ models), each with provider icon |
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
| 7.4 | Set `FREE_ONLY = true` | Only free models (including those with pricing 0/0 without `:free` suffix) |
| 7.5 | `FREE_ONLY = true` > verify that free `google/gemma-*` or `qwen/qwen3-*` appear | Models without `:free` but with pricing 0/0 are included |

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
| 12.3 | An HTTP 4xx error (e.g. 401) is **not** retried | Error returned immediately without retry |

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

---

## 18. Cost display

| # | Action | Expected result |
|---|--------|-----------------|
| 18.1 | Set `SHOW_COST_INFO = true`, send a **non-streaming** prompt | Response ends with a `**Tokens:** … · **Cost:** $…` line |
| 18.2 | Set `SHOW_COST_INFO = true`, send a **streaming** prompt | Cost line still appears (payload sends `usage.include=true`, so the final SSE chunk carries cost) |
| 18.3 | Set `SHOW_COST_INFO = false` | No cost line; payload has no `usage` field |
| 18.4 | Set `COST_CURRENCY = EUR` | Cost line shows the `€` symbol (display only; billing remains USD) |

---

## 19. Image-generation output

| # | Action | Expected result |
|---|--------|-----------------|
| 19.1 | Select an image model (e.g. FLUX) that returns the image as `message.content` | Image renders inline as `![Generated image](…)`, not as a raw URL |
| 19.2 | Ask a text model "What is GitHub's URL?" | Bare URL is shown as text, **not** rendered as a broken image (allow-list gate) |
| 19.3 | A model returning an `.svg` URL or `data:image/svg+xml` | **Not** auto-rendered (inline-script XSS defence) |

---

## 20. Base-URL security

| # | Action | Expected result |
|---|--------|-----------------|
| 20.1 | Set `OPENROUTER_BASE_URL = http://attacker.example.com/api` | Pydantic validation error — value rejected (plaintext http only for loopback) |
| 20.2 | Set `OPENROUTER_BASE_URL = http://localhost:8080/v1` | Accepted (loopback exception) |
| 20.3 | Confirm `https://openrouter.ai/api/v1` default | Accepted; all requests sent with `allow_redirects=False` |
| 20.4 | Trigger a 503/429 from upstream | Request is retried (502/503/504/429), honouring `Retry-After` |

---

## Quick pre-release checklist

- [ ] `python test_pipe.py` → 603 passed, 0 failed
- [ ] `python integration_test.py` → 44/44
- [ ] Empty API key → clear error message in model selector
- [ ] Valid API key → 340+ models with provider icons
- [ ] Non-streaming chat works
- [ ] Streaming chat works (token by token)
- [ ] Reasoning tokens shown with `<think>`
- [ ] `FREE_ONLY` filters correctly (`:free` suffix + 0/0 pricing)
- [ ] Provider filter + inversion works
- [ ] Model prefix applied and removable
- [ ] Fallback models present in payload
- [ ] Middle-out present in payload
- [ ] Cache control applied on list-type message content
- [ ] Retry on timeout, no retry on 4xx errors
- [ ] Errors formatted correctly (no raw tracebacks)
- [ ] No secrets in logs or error messages
- [ ] Open WebUI internal fields removed from payload
