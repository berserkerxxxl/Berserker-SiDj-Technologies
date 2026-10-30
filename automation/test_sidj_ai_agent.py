"""Offline tests; no OpenRouter access or secrets required."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from sidj_ai_agent import TARGET, apply_proposal, parse_reply


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
        with self.assertRaises(ValueError):
            parse_reply("not json")


if __name__ == "__main__":
    unittest.main()
