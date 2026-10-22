#!/usr/bin/env python3
"""Opt-in live chat/tool/TTS/video checks; no HTTP on import.

Use --preflight-only for read-only discovery/auth/capability checks. Inference
requires --live and an explicitly selected model per enabled scenario. --budget
is a usage tripwire, not a cost quote: use an upstream key spending limit too.
Transport checks do not test Open WebUI file persistence or rendering.
"""

import argparse
import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request

import openrouter_pipe as op

BASE = "https://openrouter.ai/api/v1"
SAFETY_MARGIN = 0.10
FAILURES: list[str] = []
LOG: list[str] = []


def http_json(path: str, key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Read-only preflight {path}: HTTP {exc.code}") from None
    except (OSError, ValueError):
        raise RuntimeError(f"Read-only preflight {path} failed") from None
    if not isinstance(result, dict):
        raise RuntimeError(f"Invalid response from {path}")
    return result


def key_stats(key: str) -> tuple[float, float | None]:
    data = http_json("/key", key).get("data") or {}
    usage = float(data["usage"])
    remaining = data.get("limit_remaining")
    remaining = float(remaining) if remaining is not None else None
    if not math.isfinite(usage) or (remaining is not None and not math.isfinite(remaining)):
        raise RuntimeError("Invalid API-key usage counters")
    return usage, remaining


class Budget:
    def __init__(self, key: str, cap: float):
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError("--budget must be finite and positive")
        self.key, self.cap = key, cap
        self.start, remaining = key_stats(key)
        if remaining is None:
            raise RuntimeError(
                "Configure an upstream API-key spending limit before paid live checks"
            )
        if remaining < SAFETY_MARGIN:
            raise RuntimeError("API-key limit is below the safety margin")

    def checkpoint(self, label: str) -> None:
        now, remaining = key_stats(self.key)
        spent = now - self.start
        LOG.append(f"[usage] {label}: ${spent:.4f}; key limit remaining={remaining}")
        if spent >= self.cap:
            raise RuntimeError(f"Usage tripwire reached: ${spent:.4f} >= ${self.cap:.2f}")
        if remaining is None or remaining < SAFETY_MARGIN:
            raise RuntimeError("API-key spending limit safety margin reached")


def check(label: str, ok: bool, detail: str = "") -> None:
    LOG.append(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def preflight_models(args) -> dict:
    """Validate all selected models before the first billable request."""
    catalog = {m["id"]: m for m in http_json("/models?output_modalities=all").get("data", [])}
    wanted = [(args.model_claude, "text"), (args.model_openai, "text"), (args.model_gemini, "text")]
    if not args.skip_tts:
        wanted.append((args.model_tts, "speech"))
    if not args.skip_video:
        wanted.append((args.model_video, "video"))
    for name, modality in wanted:
        if not name or name not in catalog:
            raise ValueError(
                f"Explicit {modality} model is missing from the current catalog: {name}"
            )
        entry = catalog[name]
        if modality not in (entry.get("architecture") or {}).get("output_modalities", []):
            raise ValueError(f"Model does not support {modality}: {name}")
        if (
            modality == "text"
            and not args.skip_tools
            and "tools" not in entry.get("supported_parameters", [])
        ):
            raise ValueError(f"Model does not advertise tools: {name}")
    if not args.skip_video:
        videos = {m["id"]: m for m in http_json("/videos/models").get("data", [])}
        entry = videos.get(args.model_video) or {}
        if args.video_duration not in entry.get("supported_durations", []):
            raise ValueError(
                f"Unsupported video duration; allowed: {entry.get('supported_durations', [])}"
            )
        if args.video_resolution not in entry.get("supported_resolutions", []):
            raise ValueError(f"Unsupported video resolution: {args.video_resolution}")
    return catalog


async def scenario_chat_tools(p, model, budget, with_tools, reasoning=None, stream=False):
    called = []

    def get_time():
        called.append(True)
        return "2026-10-04T12:00:00+00:00"

    tools = (
        {
            "get_time": {
                "spec": {
                    "name": "get_time",
                    "description": "Return a UTC timestamp",
                    "parameters": {"type": "object", "properties": {}},
                },
                "callable": get_time,
            }
        }
        if with_tools
        else None
    )
    body = {
        "model": model,
        "stream": stream,
        "max_tokens": 96,
        "messages": [
            {
                "role": "user",
                "content": "Use get_time once and repeat its result."
                if with_tools
                else "Reply LIVE-OK",
            }
        ],
    }
    if reasoning:
        body["reasoning"] = reasoning
    label = f"chat {model} stream={stream}"
    await asyncio.to_thread(budget.checkpoint, "pre " + label)
    try:
        result = await p.pipe(body, __tools__=tools)
        text = result if isinstance(result, str) else "".join([part async for part in result])
        check(label, bool(text) and "OpenRouter Error:" not in text)
        if with_tools:
            check(label + " executed tool", bool(called) and "2026-10-04T12:00:00" in text)
    finally:
        await asyncio.to_thread(budget.checkpoint, "post " + label)


async def scenario_tts(p, model, budget):
    await asyncio.to_thread(budget.checkpoint, "pre tts")
    try:
        voices = p._speech_voices.get(model) or []
        err, audio, ct, gid = await asyncio.to_thread(
            p._tts_fetch_chunk,
            "Live test.",
            model,
            voices[0] if voices else None,
            None,
            p._build_headers(valves=p.valves),
            p.valves,
            op._AUDIO_MAX_BYTES,
        )
        check(f"tts {model}", err is None and len(audio) > 1000, op._safe_detail(err or ct))
        if gid:
            check("tts generation ID", bool(gid))
    finally:
        await asyncio.to_thread(budget.checkpoint, "post tts")


async def scenario_video(p, model, budget, duration=4, resolution="720p"):
    await asyncio.to_thread(budget.checkpoint, "pre video")
    try:
        headers = p._build_headers(valves=p.valves)
        payload = {
            "model": model,
            "prompt": "A red balloon over a calm sea.",
            "duration": duration,
            "resolution": resolution,
            "generate_audio": False,
        }
        err, job = await asyncio.to_thread(p._video_submit_job, payload, headers, p.valves)
        if err:
            check("video submit", False, op._safe_detail(err))
            return
        job_id = job.get("id")
        url = job.get("polling_url") or f"{p.videos_url}/{job_id}"
        if not p._is_openrouter_url(url):
            raise RuntimeError(f"Untrusted polling URL (job id {job_id})")
        LOG.append(f"video job id: {job_id}")
        deadline = time.monotonic() + 600
        while job.get("status") != "completed":
            if (
                job.get("status") in {"failed", "cancelled", "expired"}
                or time.monotonic() >= deadline
            ):
                check("video completion", False, f"job id {job_id}; status={job.get('status')}")
                return
            await asyncio.sleep(5)
            err, polled = await asyncio.to_thread(p._video_poll_job, url, headers, p.valves)
            if err:
                check("video polling", False, f"job id {job_id}; {op._safe_detail(err)}")
                return
            job = polled
        urls = job.get("unsigned_urls") or []
        if not urls or not p._is_openrouter_url(urls[0]):
            raise RuntimeError(f"Missing/untrusted download URL (job id {job_id})")
        err, content, ct = await asyncio.to_thread(p._video_download, urls[0], headers, p.valves)
        check("video download", err is None and len(content) > 10000, f"job id {job_id}; {ct}")
    finally:
        await asyncio.to_thread(budget.checkpoint, "post video")


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--budget", type=float, default=0.50)
    for vendor in ("claude", "openai", "gemini", "tts", "video"):
        ap.add_argument(f"--model-{vendor}", help="Exact model ID; checked against live discovery")
    ap.add_argument("--video-duration", type=int, default=4)
    ap.add_argument("--video-resolution", default="720p")
    for flag in ("tts", "video", "tools", "reasoning"):
        ap.add_argument(f"--skip-{flag}", action="store_true")
    args = ap.parse_args(argv)
    if not args.live and not args.preflight_only:
        ap.error("Use --preflight-only (read-only) or --live (billable)")
    LOG.clear()
    FAILURES.clear()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key.startswith("sk-or-") or any(c.isspace() for c in key):
        print("OPENROUTER_API_KEY missing or malformed (value redacted)")
        return 2
    p = None
    try:
        catalog = await asyncio.to_thread(preflight_models, args)
        await asyncio.to_thread(key_stats, key)
        if args.preflight_only:
            print("PASS: discovery, capability and key preflight; no inference submitted")
            return 0
        budget = await asyncio.to_thread(Budget, key, args.budget)
        p = op.Pipe()
        p.valves.OPENROUTER_API_KEY = key
        p.valves.MAX_RETRIES = 0
        p.valves.MAX_TOOL_ITERATIONS = 2
        p.valves.SYNC_PROVIDER_ICONS = False
        p._catalog = catalog
        p._lazy_populated = True
        p._speech_voices = {
            mid: entry.get("supported_voices") or [] for mid, entry in catalog.items()
        }
        p._tool_capable_ids = frozenset(
            mid for mid, m in catalog.items() if "tools" in m.get("supported_parameters", [])
        )
        p._reasoning_ids = frozenset(
            mid
            for mid, entry in catalog.items()
            if "reasoning" in entry.get("supported_parameters", [])
            or isinstance(entry.get("reasoning"), dict)
        )
        for model in (args.model_claude, args.model_openai, args.model_gemini):
            reasoning = None
            if not args.skip_reasoning and model in p._reasoning_ids:
                efforts = (catalog[model].get("reasoning") or {}).get("supported_efforts")
                effort = "low" if not efforts or "low" in efforts else efforts[0]
                reasoning = {"effort": effort, "exclude": True}
            for stream in (False, True):
                await scenario_chat_tools(
                    p, model, budget, not args.skip_tools, reasoning, stream=stream
                )
        if not args.skip_tts:
            await scenario_tts(p, args.model_tts, budget)
        if not args.skip_video:
            await scenario_video(
                p, args.model_video, budget, args.video_duration, args.video_resolution
            )
        return 1 if FAILURES else 0
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        LOG.append("FAILED: " + op._safe_detail(exc))
        return 1
    finally:
        if p:
            p._session.close()
        if LOG:
            print("\n".join(LOG))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
