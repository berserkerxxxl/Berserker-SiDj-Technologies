"""Offline tests of read-only portfolio AI: no secrets, no writes, only free models."""

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import sidj_portfolio_audit as ai


class PortfolioTests(unittest.TestCase):
    def test_seven_named_projects(self):
        self.assertEqual(set(ai.PROJECTS), {
            "sidj", "agent", "reserve", "toolkit", "limits", "site", "codex"})
        self.assertTrue(all(len(v[0]) > 5 for v in ai.PROJECTS.values()))

    def test_prohibit_unknown_project(self):
        with self.assertRaises(ValueError):
            ai.read_source("other", 0)

    def test_codex_binary_never_sent_as_source(self):
        source, info, partial = ai.read_source("codex", 0)
        self.assertEqual(source, "")
        self.assertIn("EXE", info)
        self.assertFalse(partial)

    def test_bot_source_is_public_and_bounded(self):
        source, path, partial = ai.read_source("sidj", 0)
        self.assertTrue(source)
        self.assertLessEqual(len(source), ai.MAX_SOURCE)
        self.assertEqual(path, "cloudflare/sidj-worker/src/index.js")
        self.assertFalse(partial)

    def test_rotate_large_html_windows(self):
        a, path_a, partial_a = ai.read_source("toolkit", 0)
        b, path_b, partial_b = ai.read_source("toolkit", 1)
        self.assertNotEqual(a, b)
        self.assertTrue(partial_a and partial_b)
        self.assertIn("фрагмент", path_a)
        self.assertIn("фрагмент", path_b)

    def test_source_selection_is_allowlisted(self):
        for name in ai.PROJECTS:
            if name == "codex":
                continue
            _, path, _ = ai.read_source(name, 0)
            self.assertFalse(".." in path)
            self.assertNotIn("secret", path.lower())

    def test_parse_well_formed_russian_analysis(self):
        analysis = ai.parse_analysis(json.dumps({
            "finding": "Нужна проверка кэша",
            "recommendation": "Добавить тест истечения TTL",
            "severity": "низкий"
        }))
        self.assertIn("кэша", analysis["finding"])
        self.assertEqual(analysis["severity"], "низкий")

    def test_reject_bad_model_json_or_severity(self):
        for payload in ("", "not json", "[]", '{"finding":"x","recommendation":"y","severity":"critical"}'):
            with self.assertRaises(ValueError):
                ai.parse_analysis(payload)

    def test_one_request_and_free_only_fallback(self):
        requests = []

        class FakeOpener:
            def open(self, req, timeout):
                requests.append(json.loads(req.data.decode("utf-8")))
                response = {
                    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "choices": [{"message": {"content": json.dumps({
                        "finding": "Улучшить сообщения",
                        "recommendation": "Добавить тест",
                        "severity": "низкий"
                    })}}],
                }
                return io.BytesIO(json.dumps(response).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            report, model = ai.free_review("public source", "public/file.js", "B/S tech", "fake-key")
        self.assertEqual(model, "nvidia/nemotron-3-ultra-550b-a55b:free")
        self.assertEqual(report["severity"], "низкий")
        self.assertEqual(len(requests), 1)
        self.assertTrue(all(m.endswith(":free") for m in requests[0]["models"]))
        self.assertEqual(requests[0]["route"], "fallback")
        self.assertEqual(requests[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("token", json.dumps(requests[0]).lower())

    def test_denies_non_free_model(self):
        with patch.object(ai, "FREE_MODELS", ("expensive/model",)):
            with self.assertRaisesRegex(RuntimeError, "non-free"):
                ai.free_review("source", "file", "project", "key")


if __name__ == "__main__":
    unittest.main()
