"""Exercise real OWUI function save/schema/valve endpoints; no model generation.

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
            ["git", "show", f"{args.from_ref}:openrouter_pipe.py"], text=True,
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
    auth = api(args.base_url, "/api/v1/auths/signup", {
        "name": "Pipe compatibility smoke",
        "email": f"pipe-smoke-{secrets.token_hex(8)}@example.invalid",
        "password": secrets.token_urlsafe(32),
    })
    if auth.get("role") != "admin" or not auth.get("token"):
        raise RuntimeError("Smoke requires a fresh instance whose first signup is admin")
    token = auth["token"]
    function_id = "openrouter_smoke"
    form = {
        "id": function_id, "name": "OpenRouter compatibility smoke",
        "content": source, "meta": {"description": "Disposable compatibility test"},
    }
    prefix = f"/api/v1/functions/id/{function_id}"
    created = False
    try:
        saved = api(args.base_url, "/api/v1/functions/create", form, token)
        created = True
        assert saved["type"] == "pipe", saved
        assert saved["meta"]["manifest"]["version"], saved
        print("PASS: create function through real OWUI loader and database")
        admin_schema = api(args.base_url, prefix + "/valves/spec", token=token)
        assert "OPENROUTER_API_KEY" in admin_schema["properties"], admin_schema
        print(f"PASS: admin valves schema ({len(admin_schema['properties'])} fields)")
        api(args.base_url, prefix + "/toggle", {}, token)
        user_schema = api(args.base_url, prefix + "/valves/user/spec", token=token)
        assert "OPENROUTER_API_KEY" in user_schema["properties"], user_schema
        print(f"PASS: user valves schema ({len(user_schema['properties'])} fields)")
        # No API key is set: this checks validation and persistence without
        # allowing a background catalog request or generation to be billed.
        valves = {"SYNC_PROVIDER_ICONS": False, "TTS_SOURCE": "user", "REQUEST_TIMEOUT": 30}
        api(args.base_url, prefix + "/valves/update", valves, token)
        stored = api(args.base_url, prefix + "/valves", token=token)
        assert stored["TTS_SOURCE"] == "user" and stored["REQUEST_TIMEOUT"] == 30, stored
        print("PASS: save and read valves through real OWUI endpoints")
        updated = api(args.base_url, prefix + "/update", form, token)
        assert updated["type"] == "pipe", updated
        print("PASS: update function through real OWUI loader and database")
    finally:
        if created:
            request = urllib.request.Request(
                args.base_url.rstrip("/") + prefix + "/delete", method="DELETE",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                assert json.load(response) is True
            print("PASS: remove disposable test function")


if __name__ == "__main__":
    main()
