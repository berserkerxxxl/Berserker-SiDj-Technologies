"""Network-free tests of the B/S tech open-PR Telegram reminder."""
from datetime import datetime
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sidj_pr_watch as watch


def pr(number=4, draft=False, title="Контроль Telegram-бота"):
    return {
        "number": number,
        "state": "open",
        "draft": draft,
        "title": title,
        "head": {"sha": "a" * 40},
    }


class PRWatchTests(unittest.TestCase):
    def test_no_open_prs_means_no_message(self):
        self.assertIsNone(watch.create_summary([], "key", datetime.now(ZoneInfo("UTC"))))

    def test_open_pr_and_draft_in_russian_without_token(self):
        checks = [{"status": "completed", "conclusion": "success"}]
        with patch.object(watch, "github_get", return_value={"check_runs": checks}):
            message = watch.create_summary(
                [pr(4), pr(8, draft=True, title="Исправить кэш")],
                "super-secret-key",
                datetime(2026, 10, 31, tzinfo=ZoneInfo("UTC")),
            )
        self.assertIn("Открытых PR: 2", message["text"])
        self.assertIn("#4 · 👀 Ожидает решения", message["text"])
        self.assertIn("#8 · 📝 Черновик", message["text"])
        self.assertIn("Проверки пройдены", message["text"])
        self.assertNotIn("super-secret-key", json.dumps(message))
        self.assertEqual(
            message["reply_markup"]["inline_keyboard"][0][0]["url"],
            "https://github.com/berserkerxxxl/Berserker-SiDj-Technologies/pull/4",
        )

    def test_failed_and_in_progress_checks(self):
        with patch.object(watch, "github_get", return_value={
            "check_runs": [{"status": "completed", "conclusion": "failure"}]
        }):
            self.assertIn("Есть ошибки", watch.check_label(pr(), "token"))
        with patch.object(watch, "github_get", return_value={
            "check_runs": [{"status": "in_progress", "conclusion": None}]
        }):
            self.assertIn("выполняются", watch.check_label(pr(), "token"))
        with patch.object(watch, "github_get", return_value={"check_runs": []}):
            self.assertIn("отсутствуют", watch.check_label(pr(), "token"))

    def test_untrusted_title_is_plain_bounded_text(self):
        item = pr(title="hello\nhttps://evil.example" + "a" * 300)
        with patch.object(watch, "github_get", return_value={"check_runs": []}):
            message = watch.create_summary([item], "key", datetime.now(ZoneInfo("UTC")))
        self.assertNotIn("hello\nhttps", message["text"])
        self.assertLessEqual(len(message["text"]), 3500)
        self.assertNotIn("evil.example", json.dumps(message["reply_markup"]))

    def test_only_allowlisted_github_api_paths(self):
        with self.assertRaises(ValueError):
            watch.github_get("/secrets", "token")
        with self.assertRaises(ValueError):
            watch.github_get("/pulls?state=closed&per_page=100&page=1", "token")

    def test_listing_only_valid_open_prs(self):
        with patch.object(watch, "github_get", return_value=[
            pr(4), {"number": 5, "state": "closed"}, {"number": True, "state": "open"}
        ]):
            self.assertEqual([x["number"] for x in watch.open_prs("key")], [4])

    def test_message_has_max_eight_pr_buttons_and_all_link(self):
        with patch.object(watch, "github_get", return_value={"check_runs": []}):
            payload = watch.create_summary(
                [pr(number=x) for x in range(1, 13)], "token", datetime.now(ZoneInfo("UTC")))
        self.assertEqual(len(payload["reply_markup"]["inline_keyboard"]), 9)
        self.assertIn("Ещё PR: 4", payload["text"])


if __name__ == "__main__":
    unittest.main()
