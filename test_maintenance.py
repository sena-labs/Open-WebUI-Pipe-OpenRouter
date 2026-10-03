"""Regression tests for TTS ownership, cache invalidation and media concurrency."""

import asyncio
import threading
import time
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import requests

import openrouter_pipe as mod


class MediaResponse:
    def __init__(self, data=None, content=b"audio", status=200, threads=None):
        self.data = data
        self.content = content
        self.status_code = status
        self.headers = {"Content-Type": "audio/mpeg"}
        self.text = ""
        self.closed = False
        self.threads = threads if threads is not None else []

    def json(self):
        self.threads.append(threading.get_ident())
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def iter_content(self, **kwargs):
        self.threads.append(threading.get_ident())
        yield self.content

    def close(self):
        self.threads.append(threading.get_ident())
        self.closed = True


class SpeechCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network_guard = patch.object(
            requests.sessions.Session, "request",
            side_effect=AssertionError("Unexpected live HTTP request"),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.pipe = mod.Pipe()
        self.addCleanup(self.pipe._session.close)
        self.pipe.valves.OPENROUTER_API_KEY = "test-key-a"
        self.pipe._lazy_populated = True
        self.pipe._speech_model_ids = frozenset({"test/speech"})
        self.pipe._tts_fetch_chunk = Mock(return_value=(
            None, b"mock-audio", "audio/mpeg", "test-generation",
        ))
        self.pipe._speech_file_exists = AsyncMock(return_value=True)
        self.uploaded_users = []

        async def upload(request, user, metadata, audio_bytes, content_type):
            user_id = (user or {}).get("id", "anonymous")
            self.uploaded_users.append(user_id)
            file_id = f"{user_id}-{len(self.uploaded_users)}"
            return (file_id, f"/api/v1/files/{file_id}/content")

        self.pipe._upload_audio_to_owui = AsyncMock(side_effect=upload)
        self.body = {
            "model": "test/speech",
            "messages": [{"role": "user", "content": "Read this public test phrase."}],
        }

    async def speak(self, user_id="alice", chat_id="chat-a", key=None):
        user = {"id": user_id} if user_id else None
        if key and user:
            user["valves"] = {"OPENROUTER_API_KEY": key}
        return await self.pipe.pipe(
            self.body, __user__=user, __request__=object(),
            __metadata__={"chat_id": chat_id} if chat_id else {},
        )

    async def test_same_owner_chat_and_credentials_reuse_existing_file(self):
        first = await self.speak()
        second = await self.speak()
        self.assertEqual(first, second)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 1)
        self.pipe._speech_file_exists.assert_awaited_once_with("alice-1")

    async def test_different_users_get_their_own_files(self):
        first = await self.speak()
        second = await self.speak(user_id="bob")
        self.assertIn("alice-1", first)
        self.assertIn("bob-2", second)
        self.assertNotIn("alice-1", second)
        self.assertEqual(self.uploaded_users, ["alice", "bob"])

    async def test_different_chats_do_not_reuse_old_chat_files(self):
        first = await self.speak()
        second = await self.speak(chat_id="chat-b")
        self.assertNotEqual(first, second)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)

    async def test_rotated_personal_key_invalidates_cache(self):
        await self.speak(key="personal-key-a")
        await self.speak(key="personal-key-b")
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)

    async def test_rotated_admin_key_invalidates_cache(self):
        await self.speak()
        self.pipe.valves.OPENROUTER_API_KEY = "test-key-b"
        await self.speak()
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)

    async def test_new_endpoint_invalidates_cache(self):
        await self.speak()
        self.pipe.valves.OPENROUTER_BASE_URL = "https://example.invalid/api/v1"
        await self.speak()
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)

    async def test_expired_file_is_regenerated(self):
        await self.speak()
        key, (file_id, url, _) = next(iter(self.pipe._speech_cache.items()))
        self.pipe._speech_cache[key] = (
            file_id, url, time.monotonic() - mod._SPEECH_CACHE_TTL - 1,
        )
        await self.speak()
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)
        self.pipe._speech_file_exists.assert_not_awaited()

    async def test_deleted_file_is_regenerated(self):
        await self.speak()
        self.pipe._speech_file_exists.return_value = False
        second = await self.speak()
        self.assertIn("alice-2", second)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)

    async def test_missing_chat_disables_result_cache(self):
        await self.speak(chat_id=None)
        await self.speak(chat_id=None)
        self.assertEqual(self.pipe._tts_fetch_chunk.call_count, 2)
        self.assertFalse(self.pipe._speech_cache)

    async def test_tts_transport_does_not_starve_other_coroutines(self):
        main_thread = threading.get_ident()
        started = threading.Event()
        release = threading.Event()
        threads = []

        def fetch(*args):
            threads.append(threading.get_ident())
            started.set()
            if not release.wait(2):
                raise AssertionError("Event loop did not release the TTS worker")
            return (None, b"audio", "audio/mpeg", "generation")

        async def heartbeat():
            while not started.is_set():
                await asyncio.sleep(0)
            release.set()

        self.pipe._tts_fetch_chunk = fetch
        await asyncio.gather(self.speak(), heartbeat())
        self.assertTrue(threads)
        self.assertNotIn(main_thread, threads)


class MediaTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pipe = mod.Pipe()
        self.addCleanup(self.pipe._session.close)
        self.pipe.valves.OPENROUTER_API_KEY = "test-key"

    async def test_video_submit_poll_download_parse_and_close_are_off_loop(self):
        threads = []
        responses = [
            MediaResponse({"id": "job", "status": "pending"}, threads=threads),
            MediaResponse({
                "id": "job", "status": "completed",
                "unsigned_urls": ["https://openrouter.ai/api/v1/videos/job/content"],
            }, threads=threads),
            MediaResponse(content=b"video-bytes", threads=threads),
        ]
        pending = list(responses)

        def request(*args, **kwargs):
            threads.append(threading.get_ident())
            self.assertFalse(kwargs["allow_redirects"])
            return pending.pop(0)

        self.pipe._session.post = Mock(side_effect=request)
        self.pipe._session.get = Mock(side_effect=request)
        self.pipe._upload_video_to_owui = AsyncMock(return_value=(
            "video", "/api/v1/files/video/content",
        ))
        main_thread = threading.get_ident()
        with patch.object(mod.asyncio, "sleep", new=AsyncMock()):
            result = await self.pipe._run_video_generation(
                {"messages": [{"role": "user", "content": "Public video probe"}]},
                "test/video", self.pipe.valves, None, object(),
                {"id": "alice"}, {"chat_id": "chat"},
            )
        self.assertIn("<video>", result)
        self.assertNotIn(main_thread, threads)
        self.assertTrue(all(response.closed for response in responses))
        self.pipe._upload_video_to_owui.assert_awaited_once()

    async def test_download_network_failure_returns_error_without_response(self):
        self.pipe._session.get = Mock(side_effect=requests.exceptions.ConnectionError("offline"))
        error, data, content_type = await asyncio.to_thread(
            self.pipe._video_download, "https://openrouter.ai/video", {}, self.pipe.valves,
        )
        self.assertIn("Video download failed", error)
        self.assertEqual(data, b"")
        self.assertEqual(content_type, "")

    async def test_media_redirects_are_rejected_and_closed(self):
        for method in ("speech", "submit", "poll", "download"):
            with self.subTest(method=method):
                response = MediaResponse(status=302)
                self.pipe._session.post = Mock(return_value=response)
                self.pipe._session.get = Mock(return_value=response)
                if method == "speech":
                    result = await asyncio.to_thread(
                        self.pipe._tts_fetch_chunk, "text", "test/speech", "alloy",
                        None, {}, self.pipe.valves, mod._AUDIO_MAX_BYTES,
                    )
                elif method == "submit":
                    result = await asyncio.to_thread(
                        self.pipe._video_submit_job, {}, {}, self.pipe.valves,
                    )
                else:
                    helper = self.pipe._video_poll_job if method == "poll" else self.pipe._video_download
                    result = await asyncio.to_thread(
                        helper, "https://openrouter.ai/video", {}, self.pipe.valves,
                    )
                self.assertIn("redirect rejected", result[0])
                self.assertTrue(response.closed)


class CachedFileLookupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pipe = mod.Pipe()
        self.addCleanup(self.pipe._session.close)

    async def test_async_file_lookup_and_deleted_file(self):
        lookup = AsyncMock(return_value=object())
        fake = types.ModuleType("open_webui.models.files")
        fake.Files = types.SimpleNamespace(get_file_by_id=lookup)
        with patch.dict("sys.modules", {"open_webui.models.files": fake}):
            self.assertTrue(await self.pipe._speech_file_exists("file"))
            lookup.return_value = None
            self.assertFalse(await self.pipe._speech_file_exists("file"))

    async def test_sync_file_lookup_is_off_loop(self):
        threads = []

        def lookup(file_id):
            threads.append(threading.get_ident())
            return object()

        fake = types.ModuleType("open_webui.models.files")
        fake.Files = types.SimpleNamespace(get_file_by_id=lookup)
        with patch.dict("sys.modules", {"open_webui.models.files": fake}):
            self.assertTrue(await self.pipe._speech_file_exists("file"))
        self.assertNotIn(threading.get_ident(), threads)

    async def test_database_error_does_not_reuse_unverifiable_file(self):
        fake = types.ModuleType("open_webui.models.files")
        fake.Files = types.SimpleNamespace(get_file_by_id=AsyncMock(side_effect=RuntimeError("DB unavailable")))
        with patch.dict("sys.modules", {"open_webui.models.files": fake}):
            self.assertFalse(await self.pipe._speech_file_exists("file"))


if __name__ == "__main__":
    unittest.main()
