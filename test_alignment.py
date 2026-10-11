"""OpenRouter contract regressions. All HTTP is mocked, never billed."""

import asyncio
import copy
import json
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import requests
import openrouter_pipe as mod
from test_maintenance import MediaResponse

_accumulate_reasoning = mod._accumulate_reasoning


def sse(value):
    return b"data: " + json.dumps(value).encode()


class AlignmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard = patch.object(requests.sessions.Session, "request",
                             side_effect=AssertionError("Unexpected live HTTP"))
        guard.start()
        self.addCleanup(guard.stop)
        self.pipe = mod.Pipe()
        self.addCleanup(self.pipe._session.close)
        self.pipe.valves.OPENROUTER_API_KEY = "alignment-test-key"
        self.pipe.valves.SYNC_PROVIDER_ICONS = False
        self.pipe._lazy_populated = True
        self.body = {"model": "test/chat", "messages": [{"role": "user", "content": "Public probe"}]}

    def catalog(self, entries):
        self.pipe._validate_api_key = Mock(return_value=None)
        self.pipe._session.get = Mock(return_value=MediaResponse({"data": entries}))
        return self.pipe.pipes()

    def test_provider_merge_preserves_request_policy_and_options(self):
        self.pipe.valves.PROVIDER_SORT = "price"
        self.pipe.valves.PROVIDER_MAX_PRICE_PROMPT = "2"
        body = {**self.body, "provider": {"zdr": True, "data_collection": "deny",
                "preferred_max_latency": 2, "options": {"openai": {"foo": 1}},
                "max_price": {"image": 0.01}}}
        original = copy.deepcopy(body)
        provider = self.pipe._prepare_payload(body, self.pipe.valves)["provider"]
        self.assertTrue(provider["zdr"])
        self.assertEqual(provider["data_collection"], "deny")
        self.assertEqual(provider["preferred_max_latency"], 2)
        self.assertEqual(provider["max_price"], {"image": 0.01, "prompt": "2"})
        self.assertEqual(provider["options"], body["provider"]["options"])
        self.assertEqual(body, original)

    def test_personal_preferences_cannot_weaken_admin_privacy(self):
        self.pipe.valves.ZDR_ENFORCE = True
        self.pipe.valves.DATA_COLLECTION = "deny"
        effective = self.pipe._effective_valves({"valves": {
            "ZDR_ENFORCE": False, "DATA_COLLECTION": "allow"}})
        self.assertTrue(effective.ZDR_ENFORCE)
        self.assertEqual(effective.DATA_COLLECTION, "deny")

    def test_price_cap_cannot_increase_stricter_explicit_limit(self):
        self.pipe.valves.PROVIDER_MAX_PRICE_PROMPT = "2"
        self.pipe.valves.PROVIDER_MAX_PRICE_COMPLETION = "3"
        payload = self.pipe._prepare_payload({**self.body, "provider": {
            "max_price": {"prompt": "1", "completion": "4", "image": "0.01"}}}, self.pipe.valves)
        self.assertEqual(payload["provider"]["max_price"], {"prompt": "1", "completion": "3", "image": "0.01"})

    def test_reasoning_merge_preserves_explicit_controls(self):
        self.pipe.valves.REASONING_EFFORT = "high"
        self.pipe.valves.REASONING_MAX_TOKENS = 1000
        body = {**self.body, "reasoning": {"exclude": True, "enabled": True, "effort": "low"}}
        payload = self.pipe._prepare_payload(body, self.pipe.valves)
        self.assertEqual(payload["reasoning"], body["reasoning"])
        self.assertNotIn("include_reasoning", payload)

    def test_budget_and_effort_defaults_do_not_conflict(self):
        self.pipe.valves.REASONING_EFFORT = "high"
        self.pipe.valves.REASONING_MAX_TOKENS = 1000
        self.assertEqual(self.pipe._prepare_payload(self.body, self.pipe.valves)["reasoning"],
                         {"max_tokens": 1000})

    def test_explicit_reasoning_off_does_not_inherit_budget_or_effort(self):
        self.pipe.valves.REASONING_EFFORT = "high"
        self.pipe.valves.REASONING_MAX_TOKENS = 1000
        payload = self.pipe._prepare_payload({**self.body, "reasoning": {"enabled": False}}, self.pipe.valves)
        self.assertEqual(payload["reasoning"], {"enabled": False})

    def test_explicit_reasoning_on_overrides_off_default(self):
        self.pipe.valves.REASONING_EFFORT = "none"
        payload = self.pipe._prepare_payload({**self.body, "reasoning": {"enabled": True}}, self.pipe.valves)
        self.assertEqual(payload["reasoning"], {"enabled": True})

    def test_mandatory_reasoning_rejects_disable(self):
        self.pipe._catalog = {"test/chat": {"reasoning": {"mandatory": True}}}
        for cfg in ({"effort": "none"}, {"enabled": False}):
            with self.subTest(cfg=cfg), self.assertRaisesRegex(ValueError, "requires reasoning"):
                self.pipe._prepare_payload({**self.body, "reasoning": cfg}, self.pipe.valves)

    def test_max_effort_supported_and_model_efforts_validated(self):
        self.pipe.valves.REASONING_EFFORT = "max"
        self.assertEqual(self.pipe._prepare_payload(self.body, self.pipe.valves)["reasoning"]["effort"], "max")
        self.pipe._catalog = {"test/chat": {"reasoning": {"supported_efforts": ["low"]}}}
        with self.assertRaisesRegex(ValueError, "Unsupported reasoning effort"):
            self.pipe._prepare_payload(self.body, self.pipe.valves)

    async def test_session_mapping_is_scoped_and_does_not_forward_owui_session(self):
        self.pipe._non_stream_with_events = AsyncMock(return_value="done")
        sessions = []
        for uid, chat in (("alice", "one"), ("alice", "one"), ("bob", "one"), ("alice", "two")):
            await self.pipe.pipe({**self.body, "session_id": "internal-owui-id"},
                                 __user__={"id": uid}, __metadata__={"chat_id": chat})
            sessions.append(self.pipe._non_stream_with_events.call_args.args[1]["session_id"])
        self.assertEqual(sessions[0], sessions[1])
        self.assertNotEqual(sessions[0], sessions[2])
        self.assertNotEqual(sessions[0], sessions[3])
        self.assertNotIn("internal-owui-id", sessions)

    def test_explicit_openrouter_session_field(self):
        result = self.pipe._prepare_payload({**self.body, "session_id": "internal",
                                             "openrouter_session_id": "explicit"}, self.pipe.valves)
        self.assertEqual(result["session_id"], "explicit")
        self.assertNotIn("openrouter_session_id", result)

    def test_auth_checks_key_endpoint_and_cache_is_credential_scoped(self):
        response = MediaResponse({"data": {}}, status=200)
        self.pipe._session.get = Mock(return_value=response)
        self.assertIsNone(self.pipe._validate_api_key(self.pipe.valves))
        self.assertIsNone(self.pipe._validate_api_key(self.pipe.valves))
        self.assertEqual(self.pipe._session.get.call_count, 1)
        self.assertTrue(self.pipe._session.get.call_args.args[0].endswith("/key"))
        self.assertTrue(response.closed)
        self.pipe.valves.OPENROUTER_API_KEY = "rotated"
        self.pipe._validate_api_key(self.pipe.valves)
        self.assertEqual(self.pipe._session.get.call_count, 2)

    def test_custom_base_skips_key_validation(self):
        response = MediaResponse({"data": {}}, status=200)
        self.pipe._session.get = Mock(return_value=response)
        self.pipe.valves.OPENROUTER_BASE_URL = "https://proxy.example.com/api/v1"
        self.assertIsNone(self.pipe._validate_api_key(self.pipe.valves))
        self.pipe._session.get.assert_not_called()

    def test_unindexed_reasoning_records_do_not_duplicate_or_merge(self):
        state = {}
        _accumulate_reasoning(state, [{"type": "text", "id": "a", "text": "Think "}])
        _accumulate_reasoning(state, [{"type": "text", "text": "about it"}])
        _accumulate_reasoning(state, [{"type": "text", "id": "b", "text": "Second record"}])
        details = state["reasoning_details"]
        texts = sorted(d.get("text", "") for d in details)
        self.assertEqual(texts, ["Second record", "Think about it"])
        self.assertTrue(all("index" not in d for d in details))

    def test_trailing_signature_stays_with_the_reasoning_it_signs(self):
        """A signature-only delta seals the streamed block, not a new record."""
        state = {}
        _accumulate_reasoning(state, [{"type": "reasoning.text", "text": "Let me "}])
        _accumulate_reasoning(state, [{"type": "reasoning.text", "text": "think."}])
        _accumulate_reasoning(state, [{"type": "reasoning.text", "signature": "sig-abc"}])
        self.assertEqual(state["reasoning_details"],
                         [{"type": "reasoning.text", "text": "Let me think.",
                           "signature": "sig-abc"}])

    def test_block_after_a_signed_one_starts_a_new_record(self):
        """Once sealed, a slot no longer absorbs the next block's fragments."""
        state = {}
        _accumulate_reasoning(state, [{"type": "reasoning.text", "text": "First", "signature": "s1"}])
        _accumulate_reasoning(state, [{"type": "reasoning.text", "text": "Second"}])
        _accumulate_reasoning(state, [{"type": "reasoning.text", "signature": "s2"}])
        self.assertEqual(state["reasoning_details"],
                         [{"type": "reasoning.text", "text": "First", "signature": "s1"},
                          {"type": "reasoning.text", "text": "Second", "signature": "s2"}])

    def test_unindexed_encrypted_payload_fragments_concatenate(self):
        """Encrypted blocks arrive in pieces; only a signature seals them."""
        state = {}
        _accumulate_reasoning(state, [{"type": "reasoning.encrypted", "data": "AAA"}])
        _accumulate_reasoning(state, [{"type": "reasoning.encrypted", "data": "BBB"}])
        self.assertEqual(state["reasoning_details"],
                         [{"type": "reasoning.encrypted", "data": "AAABBB"}])

    def test_public_models_do_not_prove_credential_validity(self):
        response = MediaResponse({"error": {"message": "Unauthorized"}}, status=401)
        self.pipe._session.get = Mock(return_value=response)
        models = self.pipe.pipes()
        self.assertEqual(models[0]["id"], "error")
        self.assertIn("Invalid API key", models[0]["name"])
        self.assertTrue(self.pipe._session.get.call_args.args[0].endswith("/key"))

    async def test_personal_key_without_admin_routes_speech(self):
        self.pipe.valves.OPENROUTER_API_KEY = ""
        self.pipe._lazy_populated = False
        self.pipe._session.get = Mock(return_value=MediaResponse({"data": [{
            "id": "hexgrad/kokoro-82m", "architecture": {"output_modalities": ["speech"]}}]}))
        self.pipe._run_speech_generation = AsyncMock(return_value="speech")
        result = await self.pipe.pipe({**self.body, "model": "hexgrad/kokoro-82m"},
                                     __user__={"id": "alice", "valves": {"OPENROUTER_API_KEY": "personal"}})
        self.assertEqual(result, "speech")

    def test_hidden_model_metadata_remains_available(self):
        self.pipe.valves.MODEL_PROVIDERS = "openai"
        listed = self.catalog([
            {"id": "openai/chat", "architecture": {"output_modalities": ["text"]}},
            {"id": "hexgrad/speech", "architecture": {"output_modalities": ["speech"]}},
        ])
        self.assertEqual([m["id"] for m in listed], ["openai/chat"])
        self.assertIn("hexgrad/speech", self.pipe._speech_model_ids)

    def test_free_filter_excludes_paid_media_with_zero_token_prices(self):
        self.pipe.valves.FREE_MODEL_FILTER = "only"
        listed = self.catalog([
            {"id": "a/image", "pricing": {"prompt": "0", "completion": "0", "image": "0.003"}},
            {"id": "a/request", "pricing": {"prompt": "0", "completion": "0", "request": "0.01"}},
            {"id": "a/free-chat", "pricing": {"prompt": "0", "completion": "0"}},
        ])
        self.assertEqual([m["id"] for m in listed], ["a/free-chat"])

    async def test_server_filtered_catalog_looks_up_selected_speech(self):
        self.pipe._catalog = {"openai/chat": {"id": "openai/chat"}}
        response = MediaResponse({"data": {"id": "hexgrad/kokoro-82m",
                                           "architecture": {"output_modalities": ["speech"]}}})
        self.pipe._session.get = Mock(return_value=response)
        self.pipe._run_speech_generation = AsyncMock(return_value="speech")
        result = await self.pipe.pipe({**self.body, "model": "hexgrad/kokoro-82m:nitro"})
        self.assertEqual(result, "speech")
        self.assertNotIn("headers", self.pipe._session.get.call_args.kwargs)
        self.assertTrue(response.closed)

    def test_combined_picker_variants_keep_real_free_entry(self):
        self.pipe.valves.MODEL_VARIANTS = "a/chat:free:nitro:exacto"
        listed = self.catalog([
            {"id": "a/chat", "architecture": {"output_modalities": ["text"]}},
            {"id": "a/chat:free", "architecture": {"output_modalities": ["text"]}},
        ])
        self.assertIn("a/chat:free:nitro:exacto", {m["id"] for m in listed})

    def test_catalog_variant_resolution(self):
        self.assertEqual(self.pipe._catalog_id("a/b:free:nitro:exacto"), "a/b:free")
        self.assertEqual(self.pipe._catalog_id("a/b:floor:nitro"), "a/b")
        self.assertEqual(self.pipe._catalog_id("a/b:batch:nitro"), "a/b:batch")

    def test_variant_picker_never_fabricates_free_or_media_variants(self):
        self.pipe.valves.MODEL_VARIANTS = "a/chat:free,a/chat:floor,a/video:nitro"
        listed = self.catalog([
            {"id": "a/chat", "architecture": {"output_modalities": ["text"]}},
            {"id": "a/video", "architecture": {"output_modalities": ["video"]}},
        ])
        ids = {m["id"] for m in listed}
        self.assertIn("a/chat:floor", ids)
        self.assertNotIn("a/chat:free", ids)
        self.assertNotIn("a/video:nitro", ids)

    async def test_media_dispatch_uses_resolved_metadata(self):
        self.pipe._video_model_ids = frozenset({"a/video"})
        self.pipe._run_video_generation = AsyncMock(return_value="video")
        self.assertEqual(await self.pipe.pipe({**self.body, "model": "a/video:nitro:exacto"}), "video")
        self.assertEqual(self.pipe._run_video_generation.call_args.args[1], "a/video:nitro:exacto")

    async def test_decisions_and_batch_are_discovery_only(self):
        self.catalog([
            {"id": "a/decision", "architecture": {"output_modalities": ["decisions"]}},
            {"id": "a/chat:batch", "architecture": {"output_modalities": ["text"]}},
        ])
        self.pipe._non_stream_with_events = AsyncMock()
        for model, endpoint in (("a/decision", "/api/alpha/decisions"), ("a/chat:batch", "/api/v1/batches")):
            result = await self.pipe.pipe({**self.body, "model": model})
            self.assertIn(endpoint, result)
        self.pipe._non_stream_with_events.assert_not_awaited()

    def test_unknown_preset_does_not_lose_capabilities(self):
        self.pipe._catalog = {"a/chat": {"supported_parameters": []}}
        self.assertTrue(self.pipe._model_has_cap("@preset/private", frozenset()))
        self.assertFalse(self.pipe._model_has_cap("a/chat", frozenset()))

    async def test_tools_server_client_union(self):
        self.pipe._run_tools_nonstream = AsyncMock(return_value="done")
        server = {"type": "openrouter:web_search"}
        await self.pipe.pipe({**self.body, "tools": [server]},
                             __tools__={"clock": {"spec": {"name": "clock"}}})
        tools = self.pipe._run_tools_nonstream.call_args.args[1]["tools"]
        self.assertEqual(tools[0], server)
        self.assertEqual(tools[1]["function"]["name"], "clock")

    async def test_server_tools_survive_non_client_tool_capable_model(self):
        self.pipe._catalog = {"test/chat": {"supported_parameters": []}}
        self.pipe._non_stream_with_events = AsyncMock(return_value="done")
        server = {"type": "openrouter:web_search"}
        await self.pipe.pipe({**self.body, "tools": [server]},
                             __tools__={"clock": {"spec": {"name": "clock"}}})
        self.assertEqual(self.pipe._non_stream_with_events.call_args.args[1]["tools"], [server])

    async def test_sync_tools_do_not_block_event_loop(self):
        started, release = threading.Event(), threading.Event()
        main = threading.get_ident()
        def tool():
            started.set()
            if not release.wait(2):
                raise AssertionError("Event loop blocked")
            return str(threading.get_ident())
        async def heartbeat():
            while not started.is_set():
                await asyncio.sleep(0)
            release.set()
        results, _ = await asyncio.gather(self.pipe._execute_tool_calls([
            {"id": "call", "function": {"name": "clock", "arguments": "{}"}}
        ], {"clock": {"callable": tool}}, None), heartbeat())
        self.assertNotEqual(results[0]["content"], str(main))
        self.assertNotIn("Error", results[0]["content"])

    async def test_nonstream_replays_signed_reasoning_and_accumulates_cost(self):
        detail = [{"type": "reasoning.encrypted", "data": "opaque", "signature": "signed", "index": 0}]
        call = {"id": "call", "type": "function", "function": {"name": "clock", "arguments": "{}"}}
        replies = [MediaResponse({"id": "one", "choices": [{"message": {
            "content": "Before tool", "reasoning_details": detail, "tool_calls": [call], "refusal": "drop"}}],
            "usage": {"cost": 0.02, "prompt_tokens": 10}}),
            MediaResponse({"id": "two", "choices": [{"message": {"content": "Done"}}],
                           "usage": {"cost": 0.01, "prompt_tokens": 20}})]
        sent = []
        async def request(stream, headers, payload, valves):
            sent.append(copy.deepcopy(payload))
            return replies.pop(0)
        self.pipe._call_request_async = request
        self.pipe.valves.SHOW_COST_INFO = True
        self.pipe.valves.SHOW_GENERATION_ID = True
        output = await self.pipe._run_tools_nonstream({}, copy.deepcopy(self.body), self.pipe.valves,
                                                    {"clock": {"callable": lambda: "noon"}}, None)
        replay = sent[1]["messages"][1]
        self.assertEqual(replay["reasoning_details"], detail)
        self.assertEqual(replay["content"], "Before tool")
        self.assertNotIn("refusal", replay)
        self.assertIn("$0.0300", output)
        self.assertIn("30 prompt", output)
        self.assertIn("one", output)
        self.assertIn("two", output)

    async def test_stream_replays_reasoning_content_and_cost(self):
        call = {"index": 0, "id": "call", "function": {"name": "clock", "arguments": "{}"},
                "extra_content": {"google": {"thought_signature": "signed"}}}
        streams = [[sse({"id": "one", "choices": [{"delta": {"content": "Before tool",
                    "reasoning_details": [{"type": "reasoning.encrypted", "index": 0, "data": "A"}],
                    "tool_calls": [call]}}]}),
                    sse({"choices": [{"delta": {"reasoning_details": [{"type": "reasoning.encrypted", "index": 0, "data": "B"}]}}],
                         "usage": {"cost": 0.02}})],
                   [sse({"id": "two", "choices": [{"delta": {"content": "Done"}}], "usage": {"cost": 0.01}})]]
        sent = []
        def request(headers, payload, stream, valves):
            sent.append(copy.deepcopy(payload))
            response = MediaResponse()
            response.iter_lines = Mock(return_value=iter(streams.pop(0)))
            return response
        self.pipe._retryable_request = request
        self.pipe.valves.SHOW_COST_INFO = True
        output = "".join([piece async for piece in self.pipe._run_tools_stream(
            {}, copy.deepcopy(self.body), self.pipe.valves, {"clock": {"callable": lambda: "noon"}}, None)])
        replay = sent[1]["messages"][1]
        self.assertEqual(replay["content"], "Before tool")
        self.assertEqual(replay["reasoning_details"][0]["data"], "AB")
        self.assertEqual(replay["tool_calls"][0]["extra_content"], call["extra_content"])
        self.assertIn("$0.0300", output)

    async def test_background_audio_never_generates(self):
        self.pipe._audio_model_ids = frozenset({"a/music"})
        self.pipe._stream_response = Mock()
        result = await self.pipe.pipe({**self.body, "model": "a/music"},
                                     __metadata__={"task": "title_generation"})
        self.assertEqual(result, "Media Generation")
        self.pipe._stream_response.assert_not_called()

    async def test_video_privacy_rejected_before_submit(self):
        self.pipe._video_submit_job = Mock()
        self.pipe.valves.ZDR_ENFORCE = True
        result = await self.pipe._run_video_generation(self.body, "a/video", self.pipe.valves,
                                                      None, None, None, None)
        self.assertIn("privacy policy", result)
        self.pipe._video_submit_job.assert_not_called()

    async def test_video_terminal_statuses_stop_polling(self):
        self.pipe._video_submit_job = Mock(return_value=(None, {"id": "job", "status": "pending"}))
        for status in ("cancelled", "expired"):
            self.pipe._video_poll_job = Mock(return_value=(None, {"status": status}))
            with patch.object(mod.asyncio, "sleep", new=AsyncMock()):
                result = await self.pipe._run_video_generation(self.body, "a/video", self.pipe.valves,
                                                              None, None, None, None)
            self.assertIn(status, result)
            self.pipe._video_poll_job.assert_called_once()

    def test_tts_policy_contract_does_not_forward_chat_routing(self):
        self.pipe.valves.ZDR_ENFORCE = True
        self.pipe.valves.DATA_COLLECTION = "deny"
        response = MediaResponse()
        self.pipe._session.post = Mock(return_value=response)
        options = self.pipe._media_preferences({"provider": {"only": ["x"], "options": {"openai": {"instructions": "calm"}}}}, self.pipe.valves)
        self.pipe._tts_fetch_chunk("text", "a/speech", "alloy", None, {}, self.pipe.valves,
                                   mod._AUDIO_MAX_BYTES, options)
        provider = self.pipe._session.post.call_args.kwargs["json"]["provider"]
        self.assertEqual(provider, {"zdr": True, "data_collection": "deny", "options": {"openai": {"instructions": "calm"}}})

    async def test_seed_prompt_limit_and_default_voice(self):
        self.pipe._tts_fetch_chunk = Mock(return_value=(None, b"audio", "audio/mpeg", "gen"))
        self.pipe._upload_audio_to_owui = AsyncMock(return_value=("file", "/api/v1/files/file/content"))
        result = await self.pipe._run_speech_generation(
            {"messages": [{"role": "user", "content": "a" * 3500}]}, "bytedance-seed/seed-audio-1-0",
            self.pipe.valves, None, object(), None, None)
        self.assertIn("3000", result)
        self.pipe._tts_fetch_chunk.assert_not_called()
        await self.pipe._run_speech_generation(self.body, "bytedance-seed/seed-audio-1-0",
                                              self.pipe.valves, None, object(), None, None)
        self.assertIsNone(self.pipe._tts_fetch_chunk.call_args.args[2])

    async def test_seed_invalid_speed_never_submits_or_falls_back_to_default(self):
        self.pipe._tts_fetch_chunk = Mock()
        for speed in (0, -1, 0.1, 3, True, "1", float("nan")):
            with self.subTest(speed=speed):
                result = await self.pipe._run_speech_generation(
                    {**self.body, "speed": speed}, "bytedance-seed/seed-audio-1-0",
                    self.pipe.valves, None, None, None, None)
                self.assertIn("between 0.5 and 2.0", result)
        self.pipe._tts_fetch_chunk.assert_not_called()

    def test_monetary_values_are_usd_not_relabelled(self):
        output = mod._format_cost_info({"cost": 0.01}, "EUR")
        self.assertIn("$0.0100", output)
        self.assertNotIn("€", output)
        self.assertIn("$", self.pipe._format_credit_info(5, "EUR"))

    async def test_identical_concurrent_speech_and_disconnect_share_one_job(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def synthesize(*args):
            started.set()
            await release.wait()
            return "clip"
        self.pipe._synthesize_speech = AsyncMock(side_effect=synthesize)
        args = (self.body, "a/speech", self.pipe.valves, None, object(),
                {"id": "alice"}, {"chat_id": "one"})
        first = asyncio.create_task(self.pipe._run_speech_generation(*args))
        await started.wait()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(self.pipe._run_speech_generation(*args))
        await asyncio.sleep(0)
        release.set()
        self.assertEqual(await second, "clip")
        self.pipe._synthesize_speech.assert_awaited_once()
        self.assertFalse(self.pipe._speech_inflight)

    async def test_tts_cache_invalidates_when_privacy_changes(self):
        self.pipe._tts_fetch_chunk = Mock(return_value=(None, b"audio", "audio/mpeg", "gen"))
        self.pipe._upload_audio_to_owui = AsyncMock(return_value=("file", "/api/v1/files/file/content"))
        self.pipe._speech_file_exists = AsyncMock(return_value=True)
        args = (self.body, "a/speech", self.pipe.valves, None, object(),
                {"id": "alice"}, {"chat_id": "one"})
        await self.pipe._run_speech_generation(*args)
        self.pipe.valves.ZDR_ENFORCE = True
        await self.pipe._run_speech_generation(*args)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)
        self.assertTrue(self.pipe._tts_fetch_chunk.call_args.args[-1]["provider"]["zdr"])

    async def test_cached_speech_refreshes_expired_credit_without_resynthesis(self):
        self.pipe.valves.SHOW_REMAINING_CREDIT = True
        self.pipe._tts_fetch_chunk = Mock(return_value=(None, b"audio", "audio/mpeg", "gen"))
        self.pipe._upload_audio_to_owui = AsyncMock(return_value=("file", "/api/v1/files/file/content"))
        self.pipe._speech_file_exists = AsyncMock(return_value=True)
        self.pipe._session.get = Mock(return_value=MediaResponse({"data": {
            "total_credits": 100, "total_usage": 1}}))
        args = (self.body, "a/speech", self.pipe.valves, None, object(),
                {"id": "alice"}, {"chat_id": "one"})
        first = await self.pipe._run_speech_generation(*args)
        self.assertIn("$99.00", first)
        key = next(iter(self.pipe._credit_cache))
        self.pipe._credit_cache[key] = (99, time.monotonic() - self.pipe._CREDIT_TTL - 1)
        self.pipe._session.get.return_value = MediaResponse({"data": {
            "total_credits": 100, "total_usage": 2}})
        second = await self.pipe._run_speech_generation(*args)
        self.assertIn("$98.00", second)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 1)
        self.assertEqual(self.pipe._session.get.call_count, 2)

    async def test_tts_chunk_costs_and_generation_ids_are_accumulated(self):
        self.pipe.valves.SHOW_COST_INFO = True
        self.pipe.valves.SHOW_GENERATION_ID = True
        self.pipe.valves.AUDIO_TTS_SPLIT = "paragraphs"
        self.pipe._tts_fetch_chunk = Mock(side_effect=[
            (None, b"first", "audio/mpeg", "first-gen"),
            (None, b"second", "audio/mpeg", "second-gen")])
        self.pipe._generation_usage = Mock(side_effect=[{"cost": 0.02}, {"cost": 0.01}])
        self.pipe._upload_audio_to_owui = AsyncMock(return_value=("file", "/api/v1/files/file/content"))
        output = await self.pipe._run_speech_generation(
            {"messages": [{"role": "user", "content": "First complete paragraph for the clip.\nSecond complete paragraph for the clip."}]},
            "a/speech", self.pipe.valves, None, object(), None, None)
        self.assertIn("$0.0300", output)
        self.assertIn("first-gen", output)
        self.assertIn("second-gen", output)


if __name__ == "__main__":
    unittest.main()
