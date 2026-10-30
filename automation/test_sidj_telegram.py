"""Read-only regression checks for the polling fallback and migration race."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("sidj_telegram", Path(__file__).with_name("sidj_telegram.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


class PollerTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(bot, CHAT_ID="42", BOT_TOKEN="12345:" + "x" * 35, GITHUB_TOKEN="test")
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def test_existing_webhook_stops_getupdates(self):
        with patch.object(bot, "telegram", return_value={"url": "https://worker.example/telegram"}) as telegram:
            with contextlib.redirect_stdout(io.StringIO()):
                bot.run()
        self.assertEqual(telegram.call_args_list[0].args[0], "getWebhookInfo")
        self.assertEqual(telegram.call_count, 1)

    def test_activation_race_stops_polling_without_deleting_webhook(self):
        checks = 0

        def telegram(method, data):
            nonlocal checks
            if method == "getWebhookInfo":
                checks += 1
                return {"url": "" if checks == 1 else "https://worker.example/telegram"}
            if method == "getMyCommands":
                return bot.COMMANDS
            if method == "getUpdates":
                raise bot.PollingConflict("test")
            self.fail("Unexpected state-changing call: " + method)

        with patch.object(bot, "telegram", side_effect=telegram) as call:
            with contextlib.redirect_stdout(io.StringIO()):
                bot.run()
        self.assertEqual([c.args[0] for c in call.call_args_list].count("getUpdates"), 1)
        self.assertEqual(checks, 2)

    def test_conflict_without_webhook_is_not_silenced(self):
        with patch.object(bot, "main", side_effect=bot.PollingConflict("test")):
            with patch.object(bot, "telegram", return_value={"url": ""}):
                with self.assertRaises(bot.PollingConflict):
                    bot.run()

    def test_409_diagnostic_never_includes_token_url(self):
        error = HTTPError("https://api.telegram.org/bot" + bot.BOT_TOKEN + "/getUpdates", 409, "Conflict", {}, None)
        with patch.object(bot, "urlopen", side_effect=error):
            with self.assertRaises(bot.PollingConflict) as caught:
                bot.telegram("getUpdates", {})
        self.assertNotIn(bot.BOT_TOKEN, str(caught.exception))

    def test_callback_checks_sender_and_private_owner_chat(self):
        callback = {"callback_query": {"id": "button", "from": {"id": 43, "is_bot": False},
                    "message": {"chat": {"id": 42, "type": "private"}}, "data": "projects"}}
        with patch.object(bot, "telegram") as telegram, patch.object(bot, "list_projects") as projects:
            bot.process(callback)
            telegram.assert_not_called()
            projects.assert_not_called()
            callback["callback_query"]["from"]["id"] = 42
            bot.process(callback)
            telegram.assert_called_once_with("answerCallbackQuery", {"callback_query_id": "button"})
            projects.assert_called_once()


if __name__ == "__main__":
    unittest.main()
