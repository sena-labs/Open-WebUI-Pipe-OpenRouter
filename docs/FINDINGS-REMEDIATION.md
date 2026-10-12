# Audit remediation — candidate 1.13.0

Scope: the 32 confirmed findings in the 2026-10-11 audit (H01–H04,
M01–M21, L01–L07). Changes are local/unreleased; publication is a separate step.
The operator approved minimum Open WebUI **0.11.4**. Historical platform
compatibility claims are replaced with the versions exercised by real smoke tests.

## Closure matrix

All rows below are implemented. Evidence is behavioral unit coverage, real OWUI
runtime/storage checks, or source/configuration inspection where appropriate.

| ID | Fix | Evidence |
| --- | --- | --- |
| H01 | Normalize decrypted keys, reject embedded controls, log exception types rather than bearer-bearing messages | `test_malformed_key_never_reaches_chat_or_logs`; prepared headers |
| H02 | Public-property allowlist and reserved-argument rejection | `test_real_wrapper_context_cannot_be_overridden_and_coercion_survives`; actual OWUI wrapper smoke |
| H03 | Copy complete existing ModelForm/ModelMeta, preserve routing/state, leave grants untouched, check DB result | Pydantic row regressions and actual DB preservation smoke |
| H04 | Declare/enforce supported minimum 0.11.4; accept actual dict URL result | Manifest consistency, upload regressions and real WAV persistence on pinned/current OWUI |
| M01 | HTTPS/default port, no controls/backslashes/userinfo; compare URL parser with prepared request host | `test_video_url_uses_transport_host_https_and_default_port` |
| M02 | Execute OWUI's wrapper of a sync callable off-loop while preserving coercion/context | Heartbeat regression plus actual imported wrapper smoke |
| M03 | Linear block scans, bounded input before cleanup, non-quadratic link matching | Unmatched markup timing/input-limit regression |
| M04 | Await shared bootstrap, retry failures after backoff, lookup missing metadata even after failed discovery | Concurrent bootstrap and retry regressions |
| M05 | Blank/whitespace personal key inherits administrator key | Blank-key regression |
| M06 | Validate and encrypt defaults as well as explicit values | Child-process environment/default-encryption regression |
| M07 | Retry only connect timeouts and retryable HTTP statuses; never resubmit ambiguous read/connection or permanent preparation failures | Call-count regression with ReadTimeout/ConnectionError/InvalidHeader |
| M08 | Bounded transient GET retry within polling deadline; retain known job and include its ID after polling/storage errors | Video polling/storage recovery regression |
| M09 | Check storage before billing; retain completed speech chunks and known video jobs, with ownership/credential/privacy scope and bounded lifetime | No-context/no-submit, partial-chunk resume and storage-retry regressions |
| M10 | Normalize `url_citation` annotations alongside legacy citation URLs | Public `pipe()` ordinary-stream annotation regression and formatter coverage |
| M11 | Emit document and source metadata required by OWUI | Native citation event contract regression |
| M12 | Async finalization emits citations and prefetches key quota before ordinary-stream footer | Cold-quota public-entrypoint regression |
| M13 | Accumulate/deduplicate incremental image lists | Incremental image regression |
| M14 | Read `limit_remaining` through `/key`, label it as key quota, negative-cache missing/unavailable limits | Endpoint, negative-cache and unlimited-key regressions |
| M15 | Isolate every `OPENROUTER_*` variable and `WEBUI_SECRET_KEY` before test imports | Hermetic test helper; polluted-environment execution |
| M16 | Side-effect-free integration entrypoint; explicit --live; async iteration; real read-only preflight failures | Import/no-HTTP and opt-in regressions |
| M17 | Correct tool spec, explicit current model selection, capability/video preflight, small token limits, pre/post usage checkpoints | Schema/checkpoint order, missing capability and limited-key regressions |
| M18 | Preserve dollar amounts while removing actual math delimiters | Currency-text regression |
| M19 | Skip diagnostic assistant replies and strip only assistant pipe footers | TTS source/footer regression |
| M20 | Encoded/decoded media limits and image count/aggregate budget before materialization | Decode/upload-not-called cap regression and stream accumulator checks |
| M21 | Shared SSE parser: optional space, multiline data, comments; report streams without useful completion events | SSE multiline/null-delta and empty-stream regressions |
| L01 | Omit unknown token counts; bounded read-only statistics retries; grouped TTS generation IDs; mark invalid/null round costs incomplete | Cost-only/null-cost regressions; TTS accounting coverage |
| L02 | Validate generation envelopes and completion text/choice shapes; tolerate null deltas; preserve reasoning_content | Invalid-shape and reasoning-content regressions |
| L03 | Safe bounded numeric environment parsing; diagnostic never prints the environment value | Invalid numeric env subprocess regression |
| L04 | Reject unsupported video MIME; recognize MP4/WebM signatures only for octet-stream | Video download source checks and transport coverage |
| L05 | Require exact provenance for CDN/domain icon ownership instead of guessing from host | Custom CDN/favicon regression; marker retained in ModelMeta |
| L06 | Anchor debug screenshot glob to repository root | `git check-ignore` no longer ignores nested legitimate documents/images |
| L07 | Align README, SECURITY, TESTING, CONTRIBUTING, PR checklist, manifest and pending changelog with actual behavior | Manifest/version regression, static review and reproducible commands |

## Additional corrections and maintenance

- Credential identities use bounded LRU eviction rather than a wholesale flush
  after 64 credentials. ZDR cache is scoped to endpoint/credential and applies
  a shorter failure TTL.
- Network readers use a bounded dedicated executor, isolating long network
  reads from OWUI's general worker pool. Cancellation closes a reader once a
  pending synchronous read returns; it does not promise an upstream cancellation.
- Ordinary and tool streams share parsing/finalization; legacy synchronous
  non-stream formatting delegates to the actual public-path fetcher.
- Speech recovery buffers for one owner/chat/model are serialized so different
  request histories cannot race the same partially completed synthesis.
- Current discovery showed video text-token prices `0/0` while its per-second
  SKUs were positive on `/videos/models`. Such entries are excluded from the
  free-only picker unless they have an explicit real free catalog variant.
- A latest media-only message no longer falls back to an earlier text prompt.
- Tests use mocked clocks/sleeps instead of real two-second polling waits.
- Ruff/mypy run in CI with a pinned, hashed dependency snapshot; typing includes
  bodies of unannotated functions. Correctness lint is configured explicitly;
  formatting targets 100 columns, with indivisible literals/frontmatter exceptions.
- CI cancellation applies to superseded PR runs, not successive main pushes.
  Both pinned and moving OWUI smoke checks remain enabled.

## Verification boundary

Local results (2026-10-12):

| Check | Result |
| --- | --- |
| Procedural suite | **1058/1058** assertions passed |
| Unittest suites, including deliberately polluted environment | **98/98** tests passed |
| Configured Ruff | PASS |
| Mypy, including unannotated function bodies | PASS, no issues |
| Hashed CI snapshot installation | PASS |
| Real OWUI `v0.11.4-slim` extended smoke | PASS, including runtime/storage cleanup |
| Freshly pulled OWUI `main-slim` extended smoke | PASS, including runtime/storage cleanup |
| Legitimate nested docs/image debug-style names | No longer ignored by Git |

Container images exercised:

- `v0.11.4-slim`: `sha256:0487ad4a5a4b986062dedace806c3ef1e88fec38c10d1e64d6a5501c66671e5e`
- `main-slim`: `sha256:6d72fda4b01e1216d1c7bc8d69ea9f4b27934b5ab0a9a56cec651ac0ffebcb0f`

These were local remediation results. Runtime commit `62456b3` has since passed
the full GitHub matrix and CodeQL; [live provider results](LIVE-VERIFICATION-2026-10-12.md)
document successful ZDR-compatible chat/tools/TTS and the video policy restriction.

```bash
python test_pipe.py
python -m unittest -v test_maintenance test_alignment test_regressions
ruff check .
mypy
python smoke_owui.py --base-url http://127.0.0.1:3001
```

The extended smoke creates a disposable first-admin account, installs the actual
source through OWUI's loader/DB, checks schemas/valves, runs a local runtime shim
that blocks inference transport, verifies full workspace metadata/state/grants,
imports OWUI's actual tool wrapper, persists a synthetic WAV and reads its bytes
through the authenticated file route. Its cleanup uses owned OWUI file/storage
helpers because an unindexed synthetic WAV does not need a configured RAG backend.

New inference tests use mocked transport and fake credentials. Public capability
discovery was read without credentials; no paid generation was used for remediation.
The smoke verifies persisted bytes/contracts, not perceptual playback or provider
quality. Paid `--live` checks and publishing remain explicit operator actions.

## Intentional limits

- Recovery is in-memory, bounded and expires after five minutes. A restart or
  expiry loses recovery state; unknown submissions require checking provider history.
- `--budget` measures reported key usage and can lag. It is a tripwire, not a
  price quote or guaranteed request cost cap; paid runs require an upstream key limit.
- The 1.12.x security support table tracks released versions. Candidate 1.13.0
  remains under `Unreleased` until it is actually published.
- Previously rejected/conditional signals (independently padded audio base64,
  speculative socket leaks, newer dependency versions without advisories) are not
  treated as confirmed defects. The documented OpenRouter audio chunk contract
  remains intact.
- New Image/STT/reference/router subsystems remain in the approved Phase 2/3
  roadmap, separate from this correctness/security remediation.
