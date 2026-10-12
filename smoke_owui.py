"""Exercise OWUI save/schema/valves, DB preservation, tools and media storage.

Run only against a disposable, empty Open WebUI instance. This creates the
first admin account and a function, then deletes that function on completion.
"""

import argparse
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


SELFTEST = """
# Disposable smoke shim: all inference transport is forbidden.
Pipe.pipes = lambda self: [{"id": "audit", "name": "Local compatibility audit"}]

async def _smoke_pipe(self, body, __request__=None, __user__=None, __metadata__=None):
    from open_webui.models.models import Models, ModelForm, ModelMeta, ModelParams
    from open_webui.utils.tools import get_async_tool_function_and_apply_extra_params
    self._session.request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Inference forbidden"))
    uid = __user__["id"]
    command = body["messages"][-1]["content"]
    if command.startswith("cleanup:"):
        from open_webui.models.files import Files
        from open_webui.storage.provider import Storage
        fid = command.split(":", 1)[1]
        item = await Files.get_file_by_id(fid)
        if item is None or item.user_id != uid:
            raise RuntimeError("Smoke cleanup ownership mismatch")
        await asyncio.to_thread(Storage.delete_file, item.path)
        if not await Files.delete_file_by_id(fid):
            raise RuntimeError("Smoke file cleanup failed")
        return json.dumps({"cleanup":True})
    mid = self._function_id + ".test/private"
    original = ModelForm(id=mid, name="Private smoke model", base_model_id="alternate/model",
        is_active=False, meta=ModelMeta(profile_image_url="/static/favicon.png",
        description="preserve", knowledge=[{"id":"smoke-knowledge"}], capabilities={"vision":False}),
        params=ModelParams(temperature=0.5), access_grants=[])
    before = await Models.insert_new_model(original, uid)
    if before is None:
        raise RuntimeError("Could not create smoke model")
    try:
        self._get_provider_icon = lambda _: "https://openrouter.ai/images/icons/OpenAI.svg"
        await asyncio.to_thread(self._sync_model_icons, [{"id":"test/private", "name":"Private smoke model"}])
        after = await Models.get_model_by_id(mid)
        for key in ("description", "knowledge", "capabilities"):
            if getattr(after.meta, key) != getattr(before.meta, key):
                raise RuntimeError("Icon sync changed " + key)
        if after.is_active or after.base_model_id != before.base_model_id or after.access_grants != before.access_grants:
            raise RuntimeError("Icon sync changed model state/routing/access")
        if after.meta.profile_image_url == before.meta.profile_image_url:
            raise RuntimeError("Icon update did not persist")
    finally:
        await Models.delete_model_by_id(mid)
    ticks = []
    def sync_tool(count: int, __user__):
        time.sleep(0.05)
        return json.dumps([count, __user__["id"]])
    wrapped = await get_async_tool_function_and_apply_extra_params(sync_tool, {"__user__":__user__})
    asyncio.get_running_loop().call_later(0.01, lambda: ticks.append(True))
    result = await self._execute_tool_calls([{"id":"smoke", "function":{"name":"probe",
        "arguments":json.dumps({"count":"2", "__user__":{"id":"forged"}})}}],
        {"probe":{"spec":{"parameters":{"properties":{"count":{"type":"integer"}}}},"callable":wrapped}}, None)
    if json.loads(result[0]["content"]) != [2, uid] or not ticks:
        raise RuntimeError("Real OWUI wrapper violated context/coercion/event-loop contract")
    uploaded = await self._owui_upload_bytes(__request__, __user__, __metadata__,
        self._wrap_pcm16_as_wav(b"\\x00\\x00" * 100), "audio/wav", "Audio")
    if not uploaded:
        raise RuntimeError("Real media upload failed")
    return json.dumps({"file_id":uploaded[0], "url":uploaded[1], "db":True, "tools":True})

Pipe.pipe = _smoke_pipe
"""


def api(base_url, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{request.method} {path}: HTTP {error.code}: {detail}") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source", default="openrouter_pipe.py")
    parser.add_argument("--from-ref", help="Test source from a Git ref instead of disk")
    parser.add_argument("--startup-timeout", type=int, default=240)
    args = parser.parse_args()
    if args.from_ref:
        source = subprocess.check_output(
            ["git", "show", f"{args.from_ref}:openrouter_pipe.py"],
            text=True,
        )
    else:
        source = Path(args.source).read_text(encoding="utf-8")

    deadline = time.monotonic() + args.startup_timeout
    while True:
        try:
            api(args.base_url, "/health")
            break
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise RuntimeError("Open WebUI did not become healthy") from None
            time.sleep(2)

    # A fresh disposable deployment has no accounts; its first signup is admin.
    auth = api(
        args.base_url,
        "/api/v1/auths/signup",
        {
            "name": "Pipe compatibility smoke",
            "email": f"pipe-smoke-{secrets.token_hex(8)}@example.invalid",
            "password": secrets.token_urlsafe(32),
        },
    )
    if auth.get("role") != "admin" or not auth.get("token"):
        raise RuntimeError("Smoke requires a fresh instance whose first signup is admin")
    token = auth["token"]
    function_id = "openrouter_smoke"
    form = {
        "id": function_id,
        "name": "OpenRouter compatibility smoke",
        "content": source,
        "meta": {"description": "Disposable compatibility test"},
    }
    prefix = f"/api/v1/functions/id/{function_id}"
    created = False
    try:
        saved = api(args.base_url, "/api/v1/functions/create", form, token)
        created = True
        require(saved["type"] == "pipe", "Function type mismatch")
        require(saved["meta"]["manifest"]["version"], "Function manifest missing")
        print("PASS: create function through real OWUI loader and database")
        admin_schema = api(args.base_url, prefix + "/valves/spec", token=token)
        require("OPENROUTER_API_KEY" in admin_schema["properties"], "Admin schema missing key")
        print(f"PASS: admin valves schema ({len(admin_schema['properties'])} fields)")
        api(args.base_url, prefix + "/toggle", {}, token)
        user_schema = api(args.base_url, prefix + "/valves/user/spec", token=token)
        require("OPENROUTER_API_KEY" in user_schema["properties"], "User schema missing key")
        print(f"PASS: user valves schema ({len(user_schema['properties'])} fields)")
        # No API key is set: this checks validation and persistence without
        # allowing a background catalog request or generation to be billed.
        valves = {"SYNC_PROVIDER_ICONS": False, "TTS_SOURCE": "user", "REQUEST_TIMEOUT": 30}
        api(args.base_url, prefix + "/valves/update", valves, token)
        stored = api(args.base_url, prefix + "/valves", token=token)
        require(
            stored["TTS_SOURCE"] == "user" and stored["REQUEST_TIMEOUT"] == 30,
            "Valve persistence mismatch",
        )
        print("PASS: save and read valves through real OWUI endpoints")
        updated = api(args.base_url, prefix + "/update", form, token)
        require(updated["type"] == "pipe", "Updated function type mismatch")
        print("PASS: update function through real OWUI loader and database")
        probe_form = {**form, "content": source + SELFTEST}
        api(args.base_url, prefix + "/update", probe_form, token)
        chat = api(
            args.base_url,
            "/api/v1/chats/new",
            {
                "chat": {
                    "title": "Disposable media compatibility smoke",
                    "models": [function_id + ".audit"],
                    "messages": [],
                    "history": {"messages": {}, "currentId": None},
                }
            },
            token,
        )
        chat_id = chat["id"]
        try:
            result = api(
                args.base_url,
                "/api/chat/completions",
                {
                    "model": function_id + ".audit",
                    "stream": False,
                    "chat_id": chat_id,
                    "id": "smoke-media",
                    "messages": [{"role": "user", "content": "Local smoke; no inference"}],
                    "metadata": {"chat_id": chat_id, "message_id": "smoke-media"},
                },
                token,
            )
            require("choices" in result, "OWUI runtime probe failed: " + str(result.get("error")))
            probe = json.loads(result["choices"][0]["message"]["content"])
            require(probe["db"] and probe["tools"], "Runtime compatibility probe failed")
            require(probe["url"].startswith("/api/v1/files/"), "Upload did not return a file URL")
            request = urllib.request.Request(
                args.base_url.rstrip("/") + probe["url"],
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                require(response.read().startswith(b"RIFF"), "Stored audio is not a WAV file")
            print("PASS: real DB metadata/state/grants, OWUI tool wrapper and persisted WAV")
        finally:
            request = urllib.request.Request(
                args.base_url.rstrip("/") + "/api/v1/chats/" + chat_id,
                method="DELETE",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=30):
                pass
        # The synthetic WAV was never indexed. Slim images may have no vector
        # backend: remove owned bytes/metadata via OWUI storage, not RAG delete.
        cleanup = api(
            args.base_url,
            "/api/chat/completions",
            {
                "model": function_id + ".audit",
                "stream": False,
                "messages": [{"role": "user", "content": "cleanup:" + probe["file_id"]}],
            },
            token,
        )
        require("choices" in cleanup, "OWUI file cleanup failed: " + str(cleanup.get("error")))
        require(
            json.loads(cleanup["choices"][0]["message"]["content"])["cleanup"],
            "OWUI storage cleanup failed",
        )
    finally:
        if created:
            request = urllib.request.Request(
                args.base_url.rstrip("/") + prefix + "/delete",
                method="DELETE",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                require(json.load(response) is True, "Could not delete disposable function")
            print("PASS: remove disposable test function")


if __name__ == "__main__":
    main()
