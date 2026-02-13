# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-13

### Added

#### Provider Routing
- **Provider sort** — route by `price`, `throughput`, or `latency`
- **Provider order** — prioritize specific providers (e.g. `anthropic,openai`)
- **Provider ignore** — exclude providers from routing
- **Require parameters** — only use providers supporting all request params
- **Data collection policy** — `allow` or `deny` data collection by providers

#### Model Capabilities
- **Model fallbacks** — automatic failover to backup models via `models` array
- **Middle-out compression** — `transforms: ["middle-out"]` for long prompts
- **Cache control** — Anthropic-style `cache_control` injection on longest message chunk

#### Reasoning
- **Reasoning effort** — configurable `low`, `medium`, `high` effort levels
- **Include reasoning** — `<think>` tag support with proper open/close management

#### Robustness
- **Payload sanitization** — strips Open WebUI internal keys (`chat_id`, `title`, `task`, `task_id`, `features`, `citations`) and dict-type `user` field
- **Mid-stream error handling** — detects `"error"` in SSE chunks, cleanly closes reasoning blocks
- **Auto-close `<think>` tags** — if stream ends during reasoning, the tag is properly closed
- **API body error detection** — checks for `"error"` key in non-stream JSON responses
- **Retry logic** — configurable auto-retry on timeout and connection errors

#### Display
- **Provider icons** — 22 provider logos (OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, xAI, and more)
- **Citation injection** — `[n]` references replaced with markdown links, citation list appended

#### Testing
- **Comprehensive test suite** — 131 tests covering all functions, edge cases, and error paths

### Changed
- `pipe()` method is now `async` with `__user__` parameter (Open WebUI v0.4+ compliance)
- `FREE_ONLY` filter now checks for `:free` suffix instead of substring match
- Model ID prefix stripping uses `.split(".", 1)[-1]` for correct manifold prefix removal

### Fixed
- Open WebUI internal keys no longer forwarded to OpenRouter API
- `user` field sent as dict no longer causes OpenRouter validation errors
- Stream parser no longer crashes on malformed JSON chunks
- HTTP error handler no longer crashes when response body is not JSON

## [0.1.0] - 2026-01-21

### Added
- Initial release
- Basic OpenRouter integration as Open WebUI manifold pipe
- Model listing with provider filtering (`MODEL_PROVIDERS`, `INVERT_PROVIDER_LIST`)
- Free-only model filtering
- Streaming and non-streaming chat completions
- Basic error handling and timeout configuration
- Model prefix customization
