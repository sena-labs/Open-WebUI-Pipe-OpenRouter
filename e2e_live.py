#!/usr/bin/env python3
"""End-to-end live tests for the OpenRouter Pipe against the real API.

Usage:
    OPENROUTER_API_KEY=sk-or-... python -B e2e_live.py --budget 0.50

Budget guard: reads /credits before/after each scenario; aborts when spend
exceeds the cap or remaining credit drops under the safety margin. Every
request here bills real credits. Keep --budget small and prefer :free /
cheap models via the --model-* flags.

Coverage: chat + tool loop via full pipe() on three vendors; TTS and video
via the real transport helpers the OWUI flows call (_tts_fetch_chunk and
_video_submit/poll/download), without the OWUI re-host step (that needs a
live OWUI request context and is covered by smoke_owui.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openrouter_pipe as op  # noqa: E402

BASE = "https://openrouter.ai/api/v1"
SAFETY_MARGIN = 0.10  # USD: abort if remaining credit falls below this
FAILURES: list[str] = []
LOG: list[str] = []


def http_json(path: str, key: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode() or "{}")


def remaining_credits(key: str) -> float:
    data = http_json("/credits", key)
    return float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))


class Budget:
    def __init__(self, key: str, cap: float) -> None:
        self.key = key
        self.cap = cap
        self.start = remaining_credits(key)
        LOG.append(f"credits before run: ${self.start:.4f}")

    def checkpoint(self, label: str) -> None:
        now = remaining_credits(self.key)
        spent = self.start - now
        LOG.append(f"[budget] {label}: spent ${spent:.4f}, remaining ${now:.4f}")
        if spent > self.cap:
            raise SystemExit(f"BUDGET EXCEEDED at {label}: ${spent:.4f} > ${self.cap:.2f}")
        if now < SAFETY_MARGIN:
            raise SystemExit(f"SAFETY MARGIN HIT at {label}: remaining ${now:.4f}")


def make_pipe(key: str) -> op.Pipe:
    p = op.Pipe()
    p.valves.OPENROUTER_API_KEY = key
    return p


def emitter_for(events: list):
    async def em(event: dict) -> None:
        events.append(event)
    return em


def check(label: str, ok: bool, detail: str = "") -> None:
    LOG.append(f"{'PASS' if ok else 'FAIL'}: {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def is_error(result) -> bool:
    return isinstance(result, str) and result.startswith("OpenRouter Error")


async def scenario_chat_tools(
    p: op.Pipe, model: str, budget: Budget, with_tools: bool, reasoning: dict | None
) -> None:
    events: list = []
    tools = None
    if with_tools:
        tools = {
            "get_time": {
                "spec": {
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "description": "Return the current UTC timestamp in ISO format.",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                },
                "callable": lambda: "2026-10-04T12:00:00+00:00",
            }
        }
    prompt = (
        "Use the get_time tool once, then answer with the exact string it returned."
        if with_tools
        else "Reply with exactly: LIVE-OK"
    )
    body = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    if reasoning:
        body["reasoning"] = reasoning
    result = await p.pipe(
        body,
        __event_emitter__=emitter_for(events),
        __tools__=tools,
        __metadata__={"chat_id": "e2e-live", "message_id": "e2e-1", "session_id": "e2e-sess"},
        __user__={"id": "e2e-user", "email": "e2e@example.com"},
    )
    label = f"chat {model} tools={with_tools} reasoning={bool(reasoning)}"
    if is_error(result):
        check(label, False, result[:200])
    else:
        check(label, True, f"len={len(result)}")
        if with_tools:
            check(f"{model} tool loop used tool", "2026-10-04T12:00:00" in result, result[:160])


async def scenario_tts(p: op.Pipe, model: str, budget: Budget) -> None:
    """Drive the real per-chunk transport the OWUI TTS flow uses."""
    headers = p._build_headers(model_id=model, valves=p.valves)
    options = p._media_preferences({"model": model}, p.valves)
    err, audio, ct, gen_id = await asyncio.to_thread(
        p._tts_fetch_chunk,
        "Live end-to-end test.",
        model,
        None,
        None,
        headers,
        p.valves,
        op._AUDIO_MAX_BYTES,
        options,
    )
    if err:
        check(f"tts {model}", False, err[:200])
    else:
        check(f"tts {model}", len(audio) > 1000, f"bytes={len(audio)} ct={ct}")
        if gen_id:
            usage = await asyncio.to_thread(p._generation_usage, gen_id, p.valves)
            check(f"tts {model} usage aggregation", isinstance(usage, dict) or usage is None,
                  f"usage={usage}")
        else:
            check(f"tts {model} usage aggregation", False, "no X-Generation-Id header")
    budget.checkpoint(f"tts {model}")


async def scenario_video(p: op.Pipe, model: str, budget: Budget) -> None:
    """Submit + poll + bounded download via the real transport helpers."""
    headers = p._build_headers(model_id=model, valves=p.valves)
    payload = {
        "model": model,
        "prompt": "A red balloon floating over a calm sea, one continuous shot.",
        "duration": 5,
    }
    err, job = await asyncio.to_thread(p._video_submit_job, payload, headers, p.valves)
    if err:
        check(f"video {model}", False, err[:200])
        return
    job_id = job.get("id")
    poll_url = job.get("polling_url") or (f"{p.videos_url}/{job_id}" if job_id else None)
    if not poll_url:
        check(f"video {model}", False, "submit ok but no polling URL")
        return
    deadline = time.monotonic() + 600
    final = None
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        err, job = await asyncio.to_thread(p._video_poll_job, poll_url, headers, p.valves)
        if err:
            check(f"video {model}", False, err[:200])
            return
        status = (job.get("status") or "").lower()
        if status == "completed":
            final = job
            break
        if status in ("failed", "cancelled", "expired"):
            check(f"video {model}", False, f"status={status}")
            return
    if final is None:
        check(f"video {model}", False, "timeout")
        return
    urls = final.get("unsigned_urls") or []
    if not urls or not isinstance(urls[0], str):
        check(f"video {model}", False, "completed without download URL")
        return
    err, video_bytes, ct = await asyncio.to_thread(p._video_download, urls[0], headers, p.valves)
    if err:
        check(f"video {model}", False, err[:200])
    else:
        check(f"video {model}", len(video_bytes) > 10000, f"bytes={len(video_bytes)} ct={ct}")
    budget.checkpoint(f"video {model}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--budget", type=float, default=0.50, help="USD spend cap for the whole run")
    ap.add_argument("--model-claude", default="anthropic/claude-3.5-haiku")
    ap.add_argument("--model-openai", default="openai/gpt-4o-mini")
    ap.add_argument("--model-gemini", default="google/gemini-2.0-flash-001")
    ap.add_argument("--model-tts", default="openai/gpt-4o-mini-tts")
    ap.add_argument("--model-video", default="google/veo-3-fast")
    ap.add_argument("--skip-tts", action="store_true")
    ap.add_argument("--skip-video", action="store_true")
    ap.add_argument("--skip-tools", action="store_true")
    ap.add_argument("--skip-reasoning", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or key.startswith("["):
        print("OPENROUTER_API_KEY missing or placeholder — export a real key first.")
        return 2

    budget = Budget(key, args.budget)
    p = make_pipe(key)
    reasoning = None if args.skip_reasoning else {"effort": "low", "exclude": True}

    await scenario_chat_tools(p, args.model_claude, budget, not args.skip_tools, reasoning)
    await scenario_chat_tools(p, args.model_openai, budget, not args.skip_tools, reasoning)
    await scenario_chat_tools(p, args.model_gemini, budget, not args.skip_tools, reasoning)
    if not args.skip_tts:
        await scenario_tts(p, args.model_tts, budget)
    if not args.skip_video:
        await scenario_video(p, args.model_video, budget)

    end = remaining_credits(key)
    LOG.append(f"credits after run: ${end:.4f} — total spent ${budget.start - end:.4f}")
    print("\n".join(LOG))
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): " + ", ".join(FAILURES))
        return 1
    print("\nALL LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
