"""Offline tests; no OpenRouter access or secrets required."""

import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from sidj_ai_agent import MODEL, FREE_MODELS, TARGET, apply_proposal, parse_reply, free_completion


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.old = "const value = numbers.filter(Boolean).map(String);"
        self.new = "const value = numbers.flatMap(n => n ? [String(n)] : []);"
        self.source = f"// before\n{self.old}\n// after\n"
        self.proposal = {"summary": "Оптимизация", "reason": "Меньше проходов", "edits": [
            {"path": TARGET, "old": self.old, "new": self.new}]}

    def test_valid_replacement(self):
        self.assertEqual(apply_proposal(self.source, self.proposal), self.source.replace(self.old, self.new))

    def test_wrong_path_denied(self):
        self.proposal["edits"][0]["path"] = ".github/workflows/sidj-cloudflare.yml"
        with self.assertRaises(ValueError):
            apply_proposal(self.source, self.proposal)

    def test_ambiguous_fragment_denied(self):
        with self.assertRaises(ValueError):
            apply_proposal(self.source + self.old, self.proposal)

    def test_security_modification_denied(self):
        self.proposal["edits"][0]["new"] = "const token = numbers.filter(Boolean).map(String);"
        with self.assertRaises(ValueError):
            apply_proposal(self.source, self.proposal)

    def test_multiple_edits_denied(self):
        self.proposal["edits"].append(self.proposal["edits"][0])
        with self.assertRaises(ValueError):
            apply_proposal(self.source, self.proposal)

    def test_noop_denied(self):
        self.proposal["edits"][0]["new"] = self.old
        with self.assertRaises(ValueError):
            apply_proposal(self.source, self.proposal)

    def test_json_only(self):
        self.assertEqual(parse_reply('{"summary":"ok"}')["summary"], "ok")
        self.assertEqual(parse_reply('```json\n{"summary":"ok"}\n```')["summary"], "ok")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            parse_reply("not json")

    def test_empty_reply_has_safe_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "empty text"):
            parse_reply("")
        with self.assertRaisesRegex(ValueError, "empty text"):
            parse_reply("  ")

    def test_only_pinned_free_coder(self):
        self.assertEqual(MODEL, "recursive/flint-v1.0:free")
        self.assertEqual(FREE_MODELS, ("recursive/flint-v1.0:free", "nvidia/nemotron-3-ultra-550b-a55b:free"))
        self.assertTrue(all(x.endswith(":free") for x in FREE_MODELS))
        self.assertTrue(MODEL.endswith(":free"))

    def test_free_request_is_pinned_and_one_call(self):
        calls = []

        class FakeOpener:
            def open(self, request, timeout):
                calls.append(json.loads(request.data.decode("utf-8")))
                self_requested_model = calls[-1]["model"]
                return io.BytesIO(json.dumps({
                    "model": self_requested_model,
                    "choices": [{"finish_reason": "stop", "message": {"content":
                        '{"summary":"Safe","reason":"OK","edits":[]}'}}],
                }).encode())

        with patch("sidj_ai_agent.build_opener", return_value=FakeOpener()):
            proposal, model = free_completion("const foo = true;", "dummy-key")
        self.assertEqual(model, "recursive/flint-v1.0:free")
        self.assertEqual(proposal["edits"], [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "recursive/flint-v1.0:free")
        self.assertEqual(calls[0]["models"], list(FREE_MODELS))
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0]["max_tokens"], 3000)
        self.assertEqual(calls[0]["route"], "fallback")

    def test_empty_content_response_safe_error(self):
        class FakeOpener:
            def open(self, request, timeout):
                return io.BytesIO(json.dumps({"choices": [{"finish_reason": "length", "message": {"content": ""}}]}).encode())

        with patch("sidj_ai_agent.build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "finish_reason=length"):
                free_completion("const foo = true;", "dummy-key")

    def test_malformed_api_json_safe_error(self):
        class FakeOpener:
            def open(self, request, timeout):
                return io.BytesIO(b"not-json")

        with patch("sidj_ai_agent.build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(RuntimeError, "invalid HTTP JSON"):
                free_completion("const foo = true;", "dummy-key")


if __name__ == "__main__":
    unittest.main()
