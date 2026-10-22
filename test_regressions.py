"""Audit regressions: actual trust boundaries and observable runtime behavior."""

import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import types
import unittest
from functools import partial, update_wrapper
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import requests
from pydantic import BaseModel, ConfigDict

from test_support import isolate_environment

isolate_environment()
import openrouter_pipe as mod
from test_maintenance import MediaResponse


def sse(value, spaced=True):
    return (b"data: " if spaced else b"data:") + json.dumps(value).encode()


class StreamResponse(MediaResponse):
    def __init__(self, lines):
        super().__init__()
        self.lines = lines

    def iter_lines(self, **kwargs):
        return iter(self.lines)


class ModelMeta(BaseModel):
    """Relevant v0.11.4 schema, including arbitrary saved workspace metadata."""

    model_config = ConfigDict(extra="allow")
    profile_image_url: str | None = None
    description: str | None = None
    knowledge: list | None = None
    capabilities: dict | None = None


class ModelParams(BaseModel):
    model_config = ConfigDict(extra="allow")


class ModelForm(BaseModel):
    id: str
    name: str
    base_model_id: str | None = None
    meta: ModelMeta
    params: ModelParams
    is_active: bool = True
    access_grants: list[dict] | None = None


class ModelRow(ModelForm):
    user_id: str


def owui_modules(**attributes):
    names = ("open_webui", "open_webui.models", "open_webui.models.models")
    modules = {name: types.ModuleType(name) for name in names}
    for name, value in attributes.items():
        setattr(modules[names[-1]], name, value)
    return modules


def owui_sync_wrapper(function, extra):
    """OWUI 0.11.4 wrapper contract: async wrapper, sync underlying function.

    Mirrors utils/tools.py:189-250, including coercion and metadata. The smoke
    additionally exercises the real wrapper inside the pinned OWUI container.
    """
    frozen = partial(function, **extra)

    async def wrapper(**kwargs):
        if "count" in kwargs and isinstance(kwargs["count"], str):
            kwargs["count"] = int(kwargs["count"])
        return frozen(**kwargs)

    update_wrapper(wrapper, function)
    wrapper.__function__ = function
    wrapper.__extra_params__ = extra
    return wrapper


class AuditRegressions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard = patch.object(
            requests.sessions.Session, "request", side_effect=AssertionError("Unexpected live HTTP")
        )
        guard.start()
        self.addCleanup(guard.stop)
        self.pipe = mod.Pipe()
        self.addCleanup(self.pipe._session.close)
        self.pipe.valves.OPENROUTER_API_KEY = "audit-test-key"
        self.pipe.valves.SYNC_PROVIDER_ICONS = False
        self.pipe.valves.MAX_RETRIES = 0
        self.pipe._lazy_populated = True
        self.pipe._lookup_model = Mock()
        self.body = {"model": "test/chat", "messages": [{"role": "user", "content": "hello"}]}

    async def test_malformed_key_never_reaches_chat_or_logs(self):
        for key in ("sk-or-fake-secret\n", "sk-or-fake\nsecret"):
            self.pipe.valves.OPENROUTER_API_KEY = key

            def prepare(url, **kwargs):
                return requests.Request("POST", url, headers=kwargs["headers"]).prepare()

            self.pipe._session.post = Mock(side_effect=prepare)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = await self.pipe.pipe(self.body)
                if isinstance(result, str):
                    text = result
                else:
                    text = "".join([piece async for piece in result])
            self.assertNotIn("sk-or-fake", text + out.getvalue())
        self.pipe.valves.OPENROUTER_API_KEY = "audit-test-key\n"
        self.assertEqual(
            self.pipe._build_headers(valves=self.pipe.valves)["Authorization"],
            "Bearer audit-test-key",
        )

    async def test_real_wrapper_context_cannot_be_overridden_and_coercion_survives(self):
        authentic = {"id": "normal", "role": "user"}

        def tool(count, __user__, __request__):
            return json.dumps([count, __user__, __request__])

        wrapped = owui_sync_wrapper(tool, {"__user__": authentic, "__request__": "real"})
        args = {"count": "2", "__user__": {"role": "admin"}, "__request__": "forged"}
        entry = {
            "spec": {"parameters": {"properties": {"count": {"type": "integer"}}}},
            "callable": wrapped,
        }
        result = await self.pipe._execute_tool_calls(
            [{"id": "call", "function": {"name": "tool", "arguments": json.dumps(args)}}],
            {"tool": entry},
            None,
        )
        self.assertEqual(json.loads(result[0]["content"]), [2, authentic, "real"])

    async def test_sync_owui_wrapper_leaves_event_loop_responsive(self):
        started = threading.Event()
        release = threading.Event()

        def tool():
            started.set()
            if not release.wait(2):
                raise RuntimeError("test timed out")
            return "done"

        entry = {
            "spec": {"parameters": {"properties": {}}},
            "callable": owui_sync_wrapper(tool, {}),
        }
        task = asyncio.create_task(
            self.pipe._execute_tool_calls(
                [{"id": "c", "function": {"name": "tool", "arguments": "{}"}}],
                {"tool": entry},
                None,
            )
        )
        try:
            while not started.is_set():
                await asyncio.sleep(0.001)
            self.assertFalse(task.done())
            release.set()
            self.assertEqual((await task)[0]["content"], "done")
        finally:
            release.set()

    def test_icon_update_preserves_workspace_model_and_custom_cdns(self):
        row = ModelRow(
            id="audit.test/chat",
            name="Custom",
            user_id="owner",
            base_model_id="alternate/model",
            is_active=False,
            meta=ModelMeta(
                profile_image_url="data:default",
                description="keep",
                knowledge=[{"id": "file"}],
                capabilities={"vision": False},
            ),
            params=ModelParams(temperature=0.5),
            access_grants=[{"principal_id": "owner", "permission": "read"}],
        )
        original = row.model_dump()
        models = types.SimpleNamespace(
            get_model_by_id=Mock(return_value=row), update_model_by_id=Mock(return_value=row)
        )
        modules = owui_modules(
            Models=models, ModelForm=ModelForm, ModelMeta=ModelMeta, ModelParams=ModelParams
        )
        self.pipe._function_id = "audit"
        self.pipe._get_provider_icon = Mock(
            return_value="https://openrouter.ai/images/icons/OpenAI.svg"
        )
        with patch.dict(sys.modules, modules):
            self.pipe._sync_model_icons([{"id": "test/chat", "name": "Custom"}])
        form = models.update_model_by_id.call_args.args[1]
        saved = form.model_dump(exclude={"id", "access_grants"})
        self.assertFalse(saved["is_active"])
        self.assertEqual(saved["base_model_id"], original["base_model_id"])
        for key in ("description", "knowledge", "capabilities"):
            self.assertEqual(saved["meta"][key], original["meta"][key])
        self.assertIsNone(form.access_grants)
        self.assertFalse(mod._is_owui_managed_icon("https://github.com/user/custom.png"))
        self.assertFalse(mod._is_owui_managed_icon("https://brand.example/favicon.ico"))

    def test_failed_icon_update_is_not_marked_synced(self):
        row = ModelRow(
            id="audit.test/chat",
            name="x",
            user_id="owner",
            meta=ModelMeta(profile_image_url="data:default"),
            params=ModelParams(),
        )
        models = types.SimpleNamespace(
            get_model_by_id=Mock(return_value=row), update_model_by_id=Mock(return_value=None)
        )
        self.pipe._function_id = "audit"
        self.pipe._get_provider_icon = Mock(return_value="https://example.test/icon.png")
        with patch.dict(
            sys.modules,
            owui_modules(
                Models=models, ModelForm=ModelForm, ModelMeta=ModelMeta, ModelParams=ModelParams
            ),
        ):
            self.pipe._sync_model_icons([{"id": "test/chat"}])
        self.assertNotIn("test/chat", self.pipe._icons_synced)

    def test_icon_rejected_by_owui_write_is_not_marked_synced(self):
        row = ModelRow(
            id="audit.test/chat",
            name="x",
            user_id="owner",
            meta=ModelMeta(profile_image_url=None),
            params=ModelParams(),
        )
        # OWUI nulls profile images it refuses, but still returns the row.
        dropped = ModelRow(
            id="audit.test/chat",
            name="x",
            user_id="owner",
            meta=ModelMeta(profile_image_url=None),
            params=ModelParams(),
        )
        models = types.SimpleNamespace(
            get_model_by_id=Mock(return_value=row), update_model_by_id=Mock(return_value=dropped)
        )
        self.pipe._function_id = "audit"
        self.pipe._get_provider_icon = Mock(return_value="javascript:alert(1)")
        with patch.dict(
            sys.modules,
            owui_modules(
                Models=models, ModelForm=ModelForm, ModelMeta=ModelMeta, ModelParams=ModelParams
            ),
        ):
            self.pipe._sync_model_icons([{"id": "test/chat"}])
        self.assertNotIn("test/chat", self.pipe._icons_synced)

    def test_letter_fallback_passes_owui_profile_image_validation(self):
        tile = type(self.pipe)._generate_letter_icon("x-ai")
        self.assertTrue(tile.startswith("data:image/png;base64,"))
        self.assertNotIn("svg", tile.split(",", 1)[0])
        # Mirrors OWUI utils/validate.py: only raster data URIs are accepted.
        self.assertRegex(tile, r"^data:image/(png|jpeg|gif|webp);base64,")

    def test_known_gaps_resolve_to_real_icons_not_dead_favicons(self):
        for author in ("runway", "thinkingmachines", "typesafe", "meituan", "kwaivgi", "meta"):
            icon = self.pipe._get_provider_icon(author)
            self.assertTrue(icon.startswith("https://"), author)
            self.assertNotIn("/favicon.ico", icon, author)

    def test_video_url_uses_transport_host_https_and_default_port(self):
        for url in (
            "https://evil.test\\@openrouter.ai/video",
            "http://openrouter.ai/video",
            "https://user@openrouter.ai/video",
            "https://openrouter.ai:444/video",
            "https://openrouter.ai\n/video",
            "https://openrouter.ai.evil.test/video",
        ):
            self.assertFalse(self.pipe._is_openrouter_url(url), url)
        self.assertTrue(self.pipe._is_openrouter_url("https://openrouter.ai:443/video"))

    async def test_bootstrap_is_single_flight_and_second_request_waits(self):
        self.pipe._lazy_populated = False
        started, release = threading.Event(), threading.Event()

        def populate():
            started.set()
            release.wait(2)
            self.pipe._speech_model_ids = frozenset({"test/chat"})
            self.pipe._catalog = {"test/chat": {"id": "test/chat"}}
            return [{"id": "test/chat"}]

        self.pipe.pipes = Mock(side_effect=populate)
        self.pipe._run_speech_generation = AsyncMock(return_value="speech")
        first = asyncio.create_task(self.pipe.pipe(self.body))
        try:
            while not started.is_set():
                await asyncio.sleep(0.001)
            second = asyncio.create_task(self.pipe.pipe(self.body))
            await asyncio.sleep(0.01)
            self.assertFalse(second.done())
            release.set()
            self.assertEqual(await first, "speech")
            self.assertEqual(await second, "speech")
            self.assertEqual(self.pipe.pipes.call_count, 1)
        finally:
            release.set()

    async def test_failed_bootstrap_is_retryable_and_looks_up_missing_metadata(self):
        self.pipe._lazy_populated = False
        self.pipe.pipes = Mock(return_value=[{"id": "error"}])
        await self.pipe._ensure_catalog()
        self.assertFalse(self.pipe._lazy_populated)
        self.pipe._bootstrap_retry_at = 0
        await self.pipe._ensure_catalog()
        self.assertEqual(self.pipe.pipes.call_count, 2)

    def test_blank_personal_key_inherits_admin(self):
        for value in ("", "   "):
            effective = self.pipe._effective_valves({"valves": {"OPENROUTER_API_KEY": value}})
            self.assertEqual(effective.OPENROUTER_API_KEY, "audit-test-key")
            self.assertIsNone(mod.Pipe.UserValves(OPENROUTER_API_KEY=value).OPENROUTER_API_KEY)

    def test_ambiguous_read_and_connection_errors_are_not_resubmitted(self):
        self.pipe.valves.MAX_RETRIES = 2
        for exc in (
            requests.ReadTimeout(),
            requests.ConnectionError(),
            requests.exceptions.InvalidHeader(),
        ):
            self.pipe._session.post = Mock(side_effect=exc)
            with self.assertRaises(type(exc)), patch("openrouter_pipe.time.sleep"):
                self.pipe._retryable_request({}, {}, False, self.pipe.valves)
            self.assertEqual(self.pipe._session.post.call_count, 1)

    async def test_no_storage_context_never_generates_media(self):
        self.pipe._tts_fetch_chunk = Mock()
        self.pipe._video_submit_job = Mock()
        speech = await self.pipe._synthesize_speech(
            self.body, "test/tts", self.pipe.valves, None, None, {"id": "u"}, {"chat_id": "c"}
        )
        video = await self.pipe._run_video_generation(
            self.body, "test/video", self.pipe.valves, None, None, {"id": "u"}, {"chat_id": "c"}
        )
        self.assertIn("storage context", speech)
        self.assertIn("storage context", video)
        self.pipe._tts_fetch_chunk.assert_not_called()
        self.pipe._video_submit_job.assert_not_called()

    async def test_retry_storage_reuses_paid_speech_bytes(self):
        self.pipe._media_preflight = AsyncMock(return_value=None)
        self.pipe._tts_fetch_chunk = Mock(return_value=(None, b"audio", "audio/mpeg", "gen"))
        self.pipe._upload_audio_to_owui = AsyncMock(
            side_effect=[None, ("file", "/api/v1/files/file/content")]
        )
        args = (
            self.body,
            "test/tts",
            self.pipe.valves,
            None,
            object(),
            {"id": "u"},
            {"chat_id": "c"},
        )
        self.assertIn("without new synthesis", await self.pipe._synthesize_speech(*args))
        self.assertIn("<audio>", await self.pipe._synthesize_speech(*args))
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 1)

    async def test_speech_retry_resumes_after_a_known_chunk_failure(self):
        self.pipe._media_preflight = AsyncMock(return_value=None)
        self.pipe.valves.AUDIO_TTS_SPLIT = "paragraphs"
        self.pipe._tts_fetch_chunk = Mock(
            side_effect=[
                (None, b"one", "audio/mpeg", "g1"),
                ("OpenRouter Error: Rate limited (HTTP 429).", b"", "", ""),
                (None, b"two", "audio/mpeg", "g2"),
            ]
        )
        self.pipe._upload_audio_to_owui = AsyncMock(
            return_value=("file", "/api/v1/files/file/content")
        )
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": "First paragraph for recovery.\nSecond paragraph for recovery.",
                }
            ]
        }
        args = (body, "test/tts", self.pipe.valves, None, object(), {"id": "u"}, {"chat_id": "c"})
        self.assertIn("Rate limited", await self.pipe._synthesize_speech(*args))
        self.assertIn("<audio>", await self.pipe._synthesize_speech(*args))
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 3)
        self.assertEqual(self.pipe._upload_audio_to_owui.call_args.args[3], b"onetwo")

    async def test_video_transient_poll_and_storage_retry_reuse_job(self):
        self.pipe._media_preflight = AsyncMock(return_value=None)
        self.pipe._video_submit_job = Mock(return_value=(None, {"id": "job", "status": "pending"}))
        self.pipe._video_poll_job = Mock(
            side_effect=[
                ("OpenRouter Error: Video polling failed (HTTP 502).", None),
                (
                    None,
                    {
                        "id": "job",
                        "status": "completed",
                        "unsigned_urls": ["https://openrouter.ai/video"],
                    },
                ),
            ]
        )
        self.pipe._video_download = Mock(return_value=(None, b"video", "video/mp4"))
        self.pipe._upload_video_to_owui = AsyncMock(
            side_effect=[None, ("file", "/api/v1/files/file/content")]
        )
        args = (
            self.body,
            "test/video",
            self.pipe.valves,
            None,
            object(),
            {"id": "u"},
            {"chat_id": "c"},
        )
        with patch("openrouter_pipe.asyncio.sleep", AsyncMock()):
            first = await self.pipe._run_video_generation(*args)
            second = await self.pipe._run_video_generation(*args)
        self.assertIn("job id job", first)
        self.assertIn("<video>", second)
        self.assertEqual(self.pipe._video_submit_job.call_count, 1)

    async def test_plain_stream_annotations_and_cold_quota_are_finalized(self):
        self.pipe.valves.SHOW_REMAINING_CREDIT = True
        annotations = [
            {"type": "url_citation", "url_citation": {"url": "https://example.test/source"}}
        ]
        self.pipe._retryable_request = Mock(
            return_value=StreamResponse(
                [
                    sse(
                        {"choices": [{"delta": {"content": "hello", "annotations": annotations}}]},
                        False,
                    )
                ]
            )
        )
        self.pipe._session.get = Mock(return_value=MediaResponse({"data": {"limit_remaining": 2}}))
        events = []

        async def emit(event):
            events.append(event)

        stream = await self.pipe.pipe({**self.body, "stream": True}, __event_emitter__=emit)
        output = "".join([x async for x in stream])
        self.assertIn("API-key limit remaining: $2.00", output)
        self.assertIn("https://example.test/source", output)
        citation = next(e["data"] for e in events if e["type"] == "citation")
        self.assertEqual(citation["metadata"][0]["source"], citation["document"][0])
        self.assertTrue(self.pipe._session.get.call_args.args[0].endswith("/key"))

    def test_quota_negative_cache_and_unlimited_key(self):
        self.pipe._session.get = Mock(return_value=MediaResponse(status=403))
        for _ in range(3):
            self.assertIsNone(self.pipe._fetch_credit_balance(self.pipe.valves))
        self.assertEqual(self.pipe._session.get.call_count, 1)
        self.pipe._credit_cache.clear()
        self.pipe._session.get = Mock(
            return_value=MediaResponse({"data": {"limit_remaining": None}})
        )
        self.assertIsNone(self.pipe._fetch_credit_balance(self.pipe.valves))

    def test_sse_multiline_optional_space_null_delta_and_reasoning_content(self):
        lines = [
            b": keepalive",
            b'data:{"choices": [',
            b'data: {"delta": {"reasoning_content": "why"}}]}',
            b"",
            sse({"choices": [{"delta": None}]}),
            sse({"choices": [{"delta": {"content": "ok"}}]}),
        ]
        self.pipe._retryable_request = Mock(return_value=StreamResponse(lines))
        output = "".join(self.pipe._stream_response({}, {}, self.pipe.valves))
        self.assertIn("why", output)
        self.assertIn("ok", output)
        self.assertNotIn("Error", output)

    def test_empty_stream_reports_an_error(self):
        self.pipe._retryable_request = Mock(
            return_value=StreamResponse([b": ping", b"data: [DONE]"])
        )
        self.assertIn(
            "OpenRouter Error:", "".join(self.pipe._stream_response({}, {}, self.pipe.valves))
        )

    def test_incremental_images_are_accumulated_and_deduplicated(self):
        one = {"image_url": {"url": "https://example.test/1.png"}}
        two = {"image_url": {"url": "https://example.test/2.png"}}
        self.pipe._retryable_request = Mock(
            return_value=StreamResponse(
                [
                    sse({"choices": [{"delta": {"images": [one]}}]}),
                    sse({"choices": [{"delta": {"images": [one, two]}}]}),
                ]
            )
        )
        state = {}
        list(self.pipe._stream_response({}, {}, self.pipe.valves, state))
        self.assertEqual(state["images"], [one, two])

    async def test_media_caps_are_applied_before_decoding_or_upload(self):
        self.pipe._upload_audio_to_owui = AsyncMock()
        with (
            patch.object(mod, "_AUDIO_MAX_BYTES", 3),
            patch.object(mod.base64, "b64decode") as decode,
        ):
            await self.pipe._materialize_audio_output("A" * 100, self.pipe.valves, None, None, None)
            decode.assert_not_called()
        with patch.object(mod, "_IMAGE_MAX_BYTES", 3):
            with self.assertRaises(ValueError):
                await self.pipe._emit_image_files(
                    None, {"images": [{"image_url": {"url": "data:image/png;base64," + "A" * 100}}]}
                )

    def test_tts_preserves_money_and_unmatched_markup_is_fast(self):
        self.assertEqual(
            self.pipe._clean_tts_text("It costs $5 and $10 total."), "It costs $5 and $10 total."
        )
        start = time.monotonic()
        self.pipe._clean_tts_text("[" * 50_000)
        self.pipe._clean_tts_text("<details>" * 10_000)
        self.assertLess(time.monotonic() - start, 1)
        with self.assertRaises(ValueError):
            self.pipe._clean_tts_text("x" * (mod._TTS_INPUT_MAX_CHARS + 1))

    def test_tts_auto_ignores_errors_and_strips_only_assistant_footers(self):
        body = {
            "messages": [
                {"role": "user", "content": "speak this"},
                {"role": "assistant", "content": "OpenRouter Error: timeout"},
            ]
        }
        self.assertEqual(self.pipe._extract_tts_text(body, "auto"), "speak this")
        body["messages"][-1]["content"] = "Answer\n\n---\n***Tokens:** 3*"
        self.assertEqual(self.pipe._extract_tts_text(body, "auto"), "Answer")

    def test_media_only_latest_message_does_not_reuse_an_old_prompt(self):
        body = {
            "messages": [
                {"role": "user", "content": "Old prompt"},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.test/image"}}
                    ],
                },
            ]
        }
        self.assertEqual(self.pipe._extract_video_prompt(body), "")
        self.assertEqual(self.pipe._extract_message_text(body, "user"), "")

    def test_cost_only_usage_never_invents_token_counts(self):
        self.assertNotIn("Tokens", mod._format_cost_info({"cost": 0.1}))
        self.assertNotIn("Tokens", mod._format_cost_info({"cost_incomplete": True}))
        self.assertNotIn("nan", mod._format_cost_info({"cost": float("nan")}))

    async def test_null_round_cost_is_marked_incomplete(self):
        call = {"id": "c", "function": {"name": "clock", "arguments": "{}"}}
        self.pipe.valves.SHOW_COST_INFO = True
        self.pipe._call_request_async = AsyncMock(
            side_effect=[
                MediaResponse(
                    {"choices": [{"message": {"tool_calls": [call]}}], "usage": {"cost": 0.02}}
                ),
                MediaResponse(
                    {"choices": [{"message": {"content": "Done"}}], "usage": {"cost": None}}
                ),
            ]
        )
        output = await self.pipe._run_tools_nonstream(
            {},
            dict(self.body),
            self.pipe.valves,
            {"clock": {"callable": lambda: "noon", "spec": {"parameters": {"properties": {}}}}},
            None,
        )
        self.assertIn("$0.0200", output)
        self.assertIn("cost unavailable for some rounds", output)

    def test_generation_usage_handles_invalid_shapes(self):
        for data in ([], {"data": []}, {"data": {"total_cost": "nan"}}):
            self.pipe._session.get = Mock(return_value=MediaResponse(data))
            self.assertIsNone(self.pipe._generation_usage("gen", self.pipe.valves))

    def test_free_filter_does_not_infer_free_video_from_zero_text_rates(self):
        self.pipe.valves.FREE_MODEL_FILTER = "only"
        self.pipe._validate_api_key = Mock(return_value=None)
        self.pipe._session.get = Mock(
            return_value=MediaResponse(
                {
                    "data": [
                        {
                            "id": "test/video",
                            "architecture": {"output_modalities": ["video"]},
                            "pricing": {"prompt": "0", "completion": "0"},
                        },
                        {
                            "id": "test/chat",
                            "architecture": {"output_modalities": ["text"]},
                            "pricing": {"prompt": "0", "completion": "0"},
                        },
                    ]
                }
            )
        )
        self.assertEqual([m["id"] for m in self.pipe.pipes()], ["test/chat"])

    def test_opaque_identity_does_not_flush_at_64_credentials(self):
        first = self.pipe._credential_fingerprint("audit-stable-credential")
        for n in range(100):
            self.pipe._credential_fingerprint(f"audit-{n}")
        self.assertEqual(first, self.pipe._credential_fingerprint("audit-stable-credential"))

    def test_invalid_numeric_env_and_default_encryption_are_safe(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPENROUTER_")}
        env.update(
            OPENROUTER_REQUEST_TIMEOUT="bad",
            OPENROUTER_API_KEY="audit-fake",
            WEBUI_SECRET_KEY="audit-secret",
        )
        code = (
            "import openrouter_pipe as p; v=p.Pipe.Valves(); "
            "assert v.REQUEST_TIMEOUT==90; assert v.OPENROUTER_API_KEY.startswith('encrypted:')"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            env=env,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class RepositoryContracts(unittest.TestCase):
    def test_manifest_version_and_minimum_match_source(self):
        root = Path(__file__).parent
        source = (root / "openrouter_pipe.py").read_text()
        manifest = json.loads((root / "function.json").read_text())["meta"]["manifest"]
        self.assertIn("version: " + manifest["version"], source)
        self.assertIn(
            "required_open_webui_version: " + manifest["required_open_webui_version"], source
        )
        self.assertEqual(manifest["required_open_webui_version"], "0.11.4")
        self.assertIn("## [Unreleased]", (root / "CHANGELOG.md").read_text())

    def test_live_runner_import_never_contacts_the_network(self):
        code = (
            "from unittest.mock import patch; "
            "p=patch('urllib.request.urlopen', side_effect=AssertionError('HTTP forbidden')); "
            "p.start(); import integration_test, e2e_live"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_paid_runner_rejects_missing_live_opt_in_before_any_http(self):
        import e2e_live

        with patch.object(e2e_live, "http_json") as http, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                asyncio.run(e2e_live.main([]))
        http.assert_not_called()

    def test_model_preflight_rejects_missing_capability_before_generation(self):
        import e2e_live

        args = types.SimpleNamespace(
            model_claude="test/no-tools",
            model_openai="test/no-tools",
            model_gemini="test/no-tools",
            skip_tts=True,
            skip_video=True,
            skip_tools=False,
        )
        with patch.object(
            e2e_live,
            "http_json",
            return_value={
                "data": [
                    {
                        "id": "test/no-tools",
                        "architecture": {"output_modalities": ["text"]},
                        "supported_parameters": [],
                    }
                ]
            },
        ):
            with self.assertRaisesRegex(ValueError, "advertise tools"):
                e2e_live.preflight_models(args)

    def test_live_tool_schema_and_budget_check_order(self):
        import e2e_live

        events = []

        class FakePipe:
            async def pipe(self, body, **kwargs):
                events.append("submit")
                entry = kwargs["__tools__"]["get_time"]
                payload = mod.Pipe._build_tools_payload(kwargs["__tools__"])
                if payload[0]["function"].get("name") != "get_time":
                    raise AssertionError("Malformed tool schema")
                return entry["callable"]()

        budget = types.SimpleNamespace(checkpoint=lambda label: events.append(label))
        asyncio.run(e2e_live.scenario_chat_tools(FakePipe(), "test/chat", budget, True))
        self.assertTrue(events[0].startswith("pre "))
        self.assertEqual(events[1], "submit")
        self.assertTrue(events[2].startswith("post "))

    def test_budget_uses_key_limit_and_rejects_unlimited_keys(self):
        import e2e_live

        with patch.object(
            e2e_live, "http_json", return_value={"data": {"usage": 0, "limit_remaining": None}}
        ) as http:
            with self.assertRaisesRegex(RuntimeError, "spending limit"):
                e2e_live.Budget("audit-key", 0.5)
        self.assertEqual(http.call_args.args[0], "/key")


if __name__ == "__main__":
    unittest.main()
