"""Offline security and behavior tests for AI Telegram summaries."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import sidj_ai_notify as notify


def proposal():
    return {
        "number": 8,
        "state": "open",
        "draft": True,
        "head": {"ref": "ai/sidj-free-41127627177-1", "repo": {"full_name": notify.REPOSITORY}},
        "base": {"ref": "main"},
        "html_url": "https://github.com/" + notify.REPOSITORY + "/pull/8",
        "body": "**Модель:** " + chr(96) + "nvidia/nemotron-3-ultra-550b-a55b:free" + chr(96) +
                "\n**Улучшение:** Умная очистка кэша\n**Причина:** Сохранять полезные записи.",
    }


def ai_event():
    return {"workflow_run": {
        "name": notify.AI_WORKFLOW,
        "head_branch": "main",
        "head_repository": {"full_name": notify.REPOSITORY},
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "id": 41127627177,
        "run_attempt": 1,
    }}


class AINotifyTests(unittest.TestCase):
    def test_trusted_run(self):
        self.assertTrue(notify.is_our_ai_run(ai_event()))

    def test_reject_fork_branch_and_different_workflow(self):
        for path, wrong in (("name", "other"), ("head_branch", "hacked"), ("event", "pull_request")):
            event = ai_event()
            event["workflow_run"][path] = wrong
            self.assertFalse(notify.is_our_ai_run(event))
        event = ai_event()
        event["workflow_run"]["head_repository"]["full_name"] = "attacker/clone"
        self.assertFalse(notify.is_our_ai_run(event))

    def test_valid_pr_strict(self):
        self.assertTrue(notify.valid_pr(proposal(), "ai/sidj-free-41127627177-1"))

    def test_reject_mismatched_pr_or_non_draft(self):
        for modification in ("wrong-branch", "wrong-repo", "merged", "link"):
            item = proposal()
            if modification == "wrong-branch":
                item["head"]["ref"] = "evil/other"
            elif modification == "wrong-repo":
                item["head"]["repo"]["full_name"] = "evil/other"
            elif modification == "merged":
                item["draft"] = False
            elif modification == "link":
                item["html_url"] = "https://example.com/malicious"
            self.assertFalse(notify.valid_pr(item))

    def test_extract_russian_report(self):
        model, summary, reason = notify.extract_details(proposal()["body"])
        self.assertEqual(model, "nvidia/nemotron-3-ultra-550b-a55b:free")
        self.assertEqual(summary, "Умная очистка кэша")
        self.assertEqual(reason, "Сохранять полезные записи.")

    def test_user_message_and_trusted_link(self):
        msg, url, button = notify.build_message(proposal(), "workflow_run", ai_event()["workflow_run"])
        self.assertIn("Умная очистка кэша", msg)
        self.assertIn("одобрение", msg)
        self.assertEqual(url, proposal()["html_url"])
        self.assertIn("предложение", button.lower())

    def test_failure_notification(self):
        event = ai_event()["workflow_run"]
        event["conclusion"] = "failure"
        msg, url, _ = notify.build_message(None, "workflow_run", event)
        self.assertIn("ошибкой", msg)
        self.assertEqual(url, notify.run_url(event))

    def test_manual_test_with_existing_ai_pr(self):
        with patch.object(notify, "github_get", return_value=[
            {"number": 9, "state": "open", "draft": True, "head": {"ref": "malicious/9"}},
            proposal()
        ]) as fetch:
            match = notify.find_pr("workflow_dispatch", {}, "dummy-token")
        self.assertEqual(match["number"], 8)
        self.assertIn("/pulls?state=open", fetch.call_args.args[0])

    def test_match_exact_run_and_avoid_mismatched_pr(self):
        with patch.object(notify, "github_get", return_value=[proposal()]) as fetch:
            match = notify.find_pr("workflow_run", ai_event(), "dummy-token")
        self.assertEqual(match["number"], 8)
        self.assertIn("41127627177-1", fetch.call_args.args[0])

    def test_failure_does_not_fetch_ai_pr(self):
        event = ai_event()
        event["workflow_run"]["conclusion"] = "failure"
        with patch.object(notify, "github_get") as fetch:
            self.assertIsNone(notify.find_pr("workflow_run", event, "dummy-token"))
        fetch.assert_not_called()

    def test_untrusted_text_is_plain_and_bounded(self):
        message, _, _ = notify.build_message({
            **proposal(), "body": "**Улучшение:** " + "x" * 6000 + "\n**Причина:** a\nb"
        }, "workflow_run", None)
        self.assertLess(len(message), 2301)
        self.assertNotIn("x" * 300, message)


if __name__ == "__main__":
    unittest.main()
