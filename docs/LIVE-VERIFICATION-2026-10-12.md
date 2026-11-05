# Live verification — 2026-10-12

Runtime tested: `62456b3a61fa40338213a8bcc9e2a3cdbe5172f0`, branch
`fix/audit-remediation`. Provider requests used synthetic prompts and a disposable
inference key. Account ZDR settings were not weakened or changed.

## CI

- [Tests: SUCCESS](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/runs/38250340020): Python 3.10–3.14, pinned/current OWUI smoke, configured Ruff and mypy.
- [CodeQL: SUCCESS](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/runs/38250339940).

Both runs target the exact runtime commit above.

## Positive provider checks with ZDR retained

| Vendor/model | Plain non-stream | Plain stream | Native tool non-stream | Native tool stream |
| --- | --- | --- | --- | --- |
| Anthropic `claude-haiku-4.5` | PASS | PASS | PASS | PASS |
| OpenAI `gpt-4o-mini` / `gpt-4.1-mini` | PASS (`gpt-4o-mini`) | PASS (`gpt-4o-mini`) | PASS (`gpt-4.1-mini`, Azure) | PASS (`gpt-4.1-mini`, Azure) |
| Google `gemini-2.5-flash`, Vertex | PASS | PASS | PASS | PASS |

Twelve successful chat scenarios across the three vendors. Each native-tool
scenario executed the local timestamp tool exactly once and used its returned
value in the final response. Subsequent requests retained assistant/tool messages.
Signed/encrypted reasoning was replayed where emitted; cumulative token/cost
footers and generation IDs were observed in the explicitly metered ZDR cases.

For Azure/Vertex cases the actual request preferences were:

```json
{
  "provider": {
    "only": ["azure"],
    "sort": "price",
    "allow_fallbacks": false,
    "data_collection": "deny",
    "zdr": true
  }
}
```

Google used `only: ["google-vertex"]` with the same restrictive preferences.

### TTS

`elevenlabs/eleven-flash-v2.5`: PASS. A single `/audio/speech` request returned
29,301 bytes, `audio/mpeg`. FFprobe successfully decoded MP3, mono, 44.1 kHz,
duration 1.764717 seconds. Actual provider bytes were checked; this provider test
does not claim an OWUI playback/UI review. The separate extended OWUI smoke
already verifies real file persistence and authenticated readback using a WAV.

## Why initial selections were rejected

- `gpt-4o-mini`'s advertised Azure ZDR endpoints did **not** expose tools.
  Tool requests selected a non-ZDR endpoint and were rejected with HTTP 404.
  Switching to `gpt-4.1-mini`'s tool-capable Azure ZDR endpoints succeeded.
- `gemini-3.1-flash-lite-preview` exposed AI Studio endpoints only in the
  inspected discovery. Account ZDR rejected them. Tool-capable Vertex ZDR
  endpoints for `gemini-2.5-flash` were advertised and succeeded instead.
- Discovery is endpoint-specific: model-level `supported_parameters` does not
  prove that a particular ZDR-compatible endpoint supports every capability.

These refusals were retained as evidence. Already successful cases and TTS
were not regenerated when completing the remaining compatible cases.

## Video: blocked by the required policy

The selected `google/veo-3.1-lite` video submit was rejected before a job was
accepted: HTTP 404, `ZDR violation (account settings)`. No video job or playable
video was generated. The negative data-policy check therefore behaved as expected;
positive video generation remains **unverified/blocked**, not passed.

The [official Video Generation guide](https://openrouter.ai/docs/guides/overview/multimodal/video-generation#zero-data-retention)
states that video generation is **not eligible for ZDR**: asynchronous polling
requires temporary provider retention of the generated output and this cannot be
bypassed. No ZDR video model was found in the public ZDR endpoint discovery.

The [ZDR guide](https://openrouter.ai/docs/guides/features/zdr) also states that
request preferences cannot disable account/guardrail enforcement; declaring ZDR
on a BYOK key does not cover video generation. A model switch or `zdr:false`
does not resolve this incompatibility while strict ZDR remains required.

## Spending and artifacts

- Monitored test budget: $0.50. The supplied key had a verified expiry but no
  configured monetary limit. The operator explicitly authorized these expiring-key
  tests; this task-local authorization did not remove the published runner's
  upstream-limit requirement.
- Final observed cumulative key usage: **$0.0060346**, starting from zero.
  Immediate `/key` snapshots lagged and briefly regressed; the settled reading
  matched the initial successful batch plus the recorded follow-up round costs.
- No paid generation was retried after an unknown submission outcome.
- Local detailed evidence and generated audio: `/tmp/opencode/or-live-62456b3/`.
  Credentials, signed URLs and account identifiers are excluded from this report.

Commit/push and full CI verification are complete. Chat/tools/TTS live checks are
complete for the compatible ZDR routing pool. A positive OpenRouter video check
cannot be completed under the retained account ZDR requirement.
