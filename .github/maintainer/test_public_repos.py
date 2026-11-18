"""Regression checks for public repository onboarding and temporary credentials."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run as relay


class PublicRepositories(unittest.TestCase):
    def test_known_profiles_and_trusted_snapshot(self):
        cases = {
            "replicate-mcp-server": "src/server.ts", "OzBridge": "packages/oz-mcp-server/src/index.ts",
            "Perplexity-tts": "content.js", "chtdb": "cheats/SLUS-01068.cht",
            "agent-zero": "webui/components/modal.html", "awesome-mcp-servers": "README.md",
        }
        self.assertEqual(set(relay.PROFILES), {relay.PILOT, *("sena-labs/" + n for n in cases)})
        for name, example in cases.items():
            repo = "sena-labs/" + name
            branch, _, paths, _, hosts = relay.PROFILES[repo]
            with self.subTest(repo=repo), patch.object(relay, "REPO", repo), patch.object(relay, "HOSTS", hosts):
                self.assertRegex(example, "^(?:" + paths + ")$")
                self.assertNotRegex(".github/workflows/maintainer.yml", "^(?:" + paths + ")$")
                self.assertEqual(branch, "master" if name == "chtdb" else "main")
                with patch.dict(os.environ, {"AGENT_ID": "agent"}), patch.object(relay, "api") as api:
                    relay.make_session("a" * 40, "42")
                    body = api.call_args.args[1]
                    self.assertIn(repo + "/tar.gz/" + "a" * 40, body["environment"]["setup_commands"][0]["command"])
                    self.assertEqual(body["agent"]["tools"], [])
                    self.assertNotIn("vault_ids", body)
                    self.assertNotIn("OPENAI_API_KEY", str(body))

    def test_identity_exchange_uses_only_the_verified_endpoints_and_reuses_token(self):
        env = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.test/oidc?job=1",
               "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request", "OPENAI_IDENTITY_PROVIDER_ID": "provider",
               "OPENAI_SERVICE_ACCOUNT_ID": "service"}
        replies = [io.BytesIO(b'{"value":"signed"}'), io.BytesIO(b'{"access_token":"short","expires_in":3600}')]
        with patch.object(relay, "REPO", "sena-labs/OzBridge"), patch.object(relay, "_access_token", None), \
                patch.dict(os.environ, env), patch.object(relay, "urlopen", side_effect=replies) as opened:
            self.assertEqual(relay.bearer_token(), "short")
            self.assertEqual(relay.bearer_token(), "short")
            first, second = (call.args[0] for call in opened.call_args_list)
            self.assertIn("&audience=https%3A%2F%2Fapi.openai.com%2Fv1", first.full_url)
            self.assertEqual(second.full_url, "https://auth.openai.com/oauth/token")
            self.assertEqual(json.loads(second.data)["subject_token"], "signed")

    def test_connectivity_check_does_not_create_a_session(self):
        repo = "sena-labs/chtdb"
        event = {"repository": {"full_name": repo, "private": False, "default_branch": "master"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "event"
            path.write_text(json.dumps(event), encoding="utf-8")
            env = {"GITHUB_EVENT_PATH": str(path), "GITHUB_REPOSITORY": repo, "GITHUB_REF": "refs/heads/master",
                   "GITHUB_EVENT_NAME": "workflow_dispatch", "AGENT_ID": "agent"}
            with patch.dict(os.environ, env), patch.object(relay, "REPO", repo), \
                    patch.object(relay, "DEFAULT_BRANCH", "master"), patch.object(relay, "api") as api:
                relay.main()
                api.assert_called_once_with("?agent_id=agent&limit=1")
                with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/other"}), self.assertRaises(ValueError):
                    relay.main()
                api.assert_called_once()
