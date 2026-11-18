"""Exercise maintainer event routing without contacting GitHub or OpenAI."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run as relay


class DispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.event_path = Path(temp.name) / "event.json"
        self.base = "a" * 40
        self.issue = {"id": 70, "number": 42, "state": "open", "labels": [],
                      "author_association": "NONE", "title": "Missing output", "body": "Steps"}
        self.session = {"id": "session", "metadata": {"base": self.base, "issue_id": "70"}}
        self.pulls = []
        env = patch.dict(os.environ, {"GITHUB_REPOSITORY": relay.REPO, "GITHUB_SHA": self.base,
                         "GITHUB_EVENT_PATH": str(self.event_path), "AGENT_ID": "test", "OPENAI_API_KEY": "test"})
        env.start()
        self.addCleanup(env.stop)
        self.github = self.mock("github", side_effect=self.read_github)
        self.head = self.mock("branch_head", return_value=None)
        self.api = self.mock("api", return_value={"data": []})
        self.create = self.mock("make_session", return_value=self.session)
        self.turns = self.mock("recent_turns", return_value=[])
        self.send = self.mock("send")
        self.mock("wait_turn", return_value="turn")
        self.artifact = self.mock("artifact", return_value=b"")

    def mock(self, name, **kwargs):
        target = patch.object(relay, name, **kwargs)
        result = target.start()
        self.addCleanup(target.stop)
        return result

    def read_github(self, path):
        if path == "issues/42":
            return self.issue
        if path.startswith("pulls?"):
            return self.pulls
        if path == "pulls/100":
            return self.pulls[0]
        if path == "actions/runs/18/jobs?per_page=100":
            return {"jobs": []}
        self.fail(f"Unexpected GitHub request: {path}")

    def dispatch(self, action, **payload):
        self.event_path.write_text(json.dumps({"action": action, **payload}), encoding="utf-8")
        relay.main()

    def test_new_issue_starts_triage_and_reaches_publication_without_labels(self):
        for login, association in [("outside-user", "NONE"), ("sena-labs", "OWNER")]:
            with self.subTest(association=association):
                self.issue["author_association"] = association
                self.dispatch("opened", sender={"login": login}, issue=self.issue)
                self.create.assert_called_once_with(self.base, "70")
                self.assertEqual(self.send.call_args.args[2], "issue-70-initial")
                self.assertIn(self.issue["title"], self.send.call_args.args[1])
                self.artifact.assert_any_call("session", "turn", "maintainer.patch")
                self.create.reset_mock()
                self.send.reset_mock()
                self.artifact.reset_mock()

    def test_other_issue_events_do_not_start_triage(self):
        for action in ("labeled", "edited", "reopened"):
            self.dispatch(action, sender={"login": "sena-labs"}, issue=self.issue,
                          label={"name": "maintainer:fix"})
        self.github.assert_not_called()
        self.api.assert_not_called()

    def test_closed_issue_stops_intake_and_publication(self):
        self.issue["state"] = "closed"
        self.dispatch("opened", sender={"login": "outside-user"}, issue=self.issue)
        self.api.assert_not_called()
        relay.publish(self.base, None, 42, "maintainer/issue-42", "session", "turn", None)
        self.artifact.assert_not_called()

    def test_failed_ci_continues_the_unlabeled_issue_only_for_the_current_head(self):
        head = "b" * 40
        self.head.return_value = head
        self.pulls.append({"number": 100, "state": "open", "draft": True,
                           "head": {"sha": head}, "base": {"ref": "main"}})
        run = {"id": 18, "head_branch": "maintainer/issue-42", "head_sha": head,
               "head_repository": {"full_name": relay.REPO}, "path": ".github/workflows/tests.yml",
               "event": "pull_request", "conclusion": "failure"}
        self.api.return_value = {"data": [self.session]}
        self.turns.return_value = [{"id": "first", "status": "completed"}]
        self.dispatch("completed", workflow_run=run)
        self.assertEqual(self.send.call_args.args[2], f"ci-70-{head}")
        self.artifact.assert_any_call("session", "turn", "maintainer.patch")
        self.dispatch("completed", workflow_run={**run, "head_sha": "c" * 40})
        self.dispatch("opened", sender={"login": "outside-user"}, issue=self.issue)
        self.send.assert_called_once()
        self.create.assert_not_called()
