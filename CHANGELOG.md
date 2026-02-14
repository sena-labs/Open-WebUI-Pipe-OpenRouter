# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-14

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

## [0.1.0] - 2026-01-21

### Added
- Initial release
- Basic OpenRouter integration as Open WebUI manifold pipe
- Model listing with provider filtering (`MODEL_PROVIDERS`, `INVERT_PROVIDER_LIST`)
- Free-only model filtering
- Streaming and non-streaming chat completions
- Basic error handling and timeout configuration
- Model prefix customization
