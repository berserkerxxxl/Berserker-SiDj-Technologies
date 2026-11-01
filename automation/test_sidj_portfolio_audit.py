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
        full = (ai.ROOT / "cloudflare/sidj-worker/src/index.js").read_text(encoding="utf-8")
        windows, omitted = ai.source_windows(full)
        self.assertTrue(source)
        self.assertLessEqual(len(source), ai.MAX_SOURCE)
        self.assertEqual(source, windows[0])
        self.assertEqual(
            path, "cloudflare/sidj-worker/src/index.js" +
            (f" (фрагмент 1/{len(windows)})" if len(windows) > 1 else "")
        )
        self.assertEqual(partial, len(windows) > 1 or omitted)
        self.assertFalse(omitted)
        self.assertEqual("".join(windows), full)

    def test_rotate_large_html_windows(self):
        a, path_a, partial_a = ai.read_source("toolkit", 0)
        b, path_b, partial_b = ai.read_source("toolkit", 1)
        self.assertNotEqual(a, b)
        self.assertTrue(partial_a and partial_b)
        self.assertIn("фрагмент", path_a)
        self.assertIn("фрагмент", path_b)

    def test_site_css_rule_is_not_cut_in_half(self):
        data = (ai.ROOT / "index.html").read_text(encoding="utf-8")
        windows, omitted = ai.source_windows(data)
        self.assertFalse(omitted)
        self.assertEqual("".join(windows), data)
        self.assertTrue(all(len(window) <= ai.MAX_SOURCE for window in windows))
        self.assertTrue(any(
            ".visits-error{font-size:.74rem;color:#d6b4c1}" in window
            for window in windows
        ))

    def test_oversized_minified_line_is_omitted_not_truncated(self):
        source = "before\n" + "x" * (ai.MAX_SOURCE + 1) + "\nafter\n"
        windows, omitted = ai.source_windows(source)
        self.assertTrue(omitted)
        self.assertTrue(all(len(window) <= ai.MAX_SOURCE for window in windows))
        self.assertIn("AUDIT OMITTED line 2", "".join(windows))
        self.assertIn("after\n", "".join(windows))
        self.assertNotIn("x" * 100, "".join(windows))

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

    def test_json_fences_and_short_explanations(self):
        object_text = json.dumps({
            "finding": "Возможна лишняя очистка кэша",
            "recommendation": "Проверить выборочное удаление",
            "severity": "низкий"
        }, ensure_ascii=False)
        examples = [
            object_text,
            "```json\n" + object_text + "\n```",
            "```\n" + object_text + "\n```",
            "Краткий отчёт:\n" + object_text,
            object_text + "\nПроверяйте предложение вручную.",
        ]
        for response in examples:
            with self.subTest(response=response[:30]):
                analysis = ai.parse_analysis(response)
                self.assertEqual(analysis["severity"], "низкий")

    def test_reject_unfinished_or_multiple_json_objects(self):
        item = json.dumps({"finding": "a", "recommendation": "b", "severity": "низкий"})
        for candidate in ('{"finding":', item + "\n" + item, "x" * 250 + item):
            with self.subTest(candidate=candidate[:30]):
                with self.assertRaises(ValueError):
                    ai.parse_analysis(candidate)

    def test_finish_reason_length_gives_safe_diagnostic(self):
        class Truncated:
            def open(self, req, timeout):
                response = {"choices": [{
                    "finish_reason": "length",
                    "message": {"content": '{"finding":"too long",'}
                }]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=Truncated()):
            with self.assertRaisesRegex(ValueError, "оборвался по лимиту токенов"):
                ai.free_review("public source", "path.js", "B/S", "fake-key")

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
                        "severity": "низкий",
                        "intent": "Проверяет локальное поведение по назначению",
                        "impact": "Реальный сценарий сбоя может влиять на работу",
                        "counterargument": "Ограничение может быть частью защиты системы",
                        "decision": "исправить",
                        "evidence": "public source"
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
        self.assertEqual(requests[0]["max_tokens"], 3600)
        self.assertNotIn("api_key", requests[0])
        self.assertNotIn("authorization", requests[0])
        self.assertNotIn("secret", requests[0])

    def test_rejects_unverified_model_evidence(self):
        class FakeOpener:
            def open(self, req, timeout):
                response = {
                    "choices": [{"message": {"content": json.dumps({
                        "finding": "Синтаксическая ошибка",
                        "recommendation": "Исправить CSS",
                        "severity": "низкий",
                        "intent": "Проверяет локальное поведение по назначению",
                        "impact": "Реальный сценарий сбоя может влиять на работу",
                        "counterargument": "Ограничение может быть частью защиты системы",
                        "decision": "исправить",
                        "evidence": ".visits-error{colo"
                    })}}]
                }
                return io.BytesIO(json.dumps(response).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "не подтверждается исходным кодом"):
                ai.free_review(
                    ".visits-error{color:#d6b4c1}", "index.html", "Сайт", "fake-key"
                )

    def test_long_quote_is_not_silently_cut_and_retry_uses_next_free_model(self):
        source = "const someLongName = " + "x" * 240 + ";"
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                payload = json.loads(req.data)
                calls.append(payload)
                evidence = source if len(calls) == 1 else "const someLongName = "
                response = {"model": payload["model"], "choices": [{
                    "message": {"content": json.dumps({
                        "finding": "Избыточная проверка",
                        "recommendation": "Добавить ограничение",
                        "severity": "низкий",
                        "intent": "Проверяет локальное поведение по назначению",
                        "impact": "Реальный сценарий сбоя может влиять на работу",
                        "counterargument": "Ограничение может быть частью защиты системы",
                        "decision": "исправить",
                        "evidence": evidence,
                    })}
                }]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            result, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["evidence"], "const someLongName =")
        self.assertEqual(calls[0]["model"], ai.FREE_MODELS[0])
        self.assertEqual(calls[1]["model"], ai.FREE_MODELS[1])
        self.assertTrue(all(model.endswith(":free") for call in calls for model in call["models"]))
        self.assertTrue(all(call["max_tokens"] == 3600 for call in calls))

    def test_truncated_first_answer_succeeds_on_retry(self):
        source = "const timeout = 25;\n"
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(1)
                item = (
                    {"finish_reason": "length", "message": {"content": "{"}}
                    if len(calls) == 1 else
                    {"finish_reason": "stop", "message": {"content": json.dumps({
                        "finding": "Проверить таймаут",
                        "recommendation": "Добавить тест",
                        "severity": "низкий",
                        "intent": "Проверяет локальное поведение по назначению",
                        "impact": "Реальный сценарий сбоя может влиять на работу",
                        "counterargument": "Ограничение может быть частью защиты системы",
                        "decision": "исправить",
                        "evidence": "const timeout = 25;",
                    })}}
                )
                return io.BytesIO(json.dumps({"choices": [item]}).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            analysis, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertEqual(analysis["severity"], "низкий")

    def test_no_finding_with_evidence_requires_retry(self):
        source = "const timeout = 25;\n"
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(1)
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Замечаний нет",
                    "recommendation": "Продолжать проверку",
                    "severity": "нет замечаний",
                    "intent": "Проверяет локальное поведение по назначению",
                    "impact": "Реальный сценарий сбоя может влиять на работу",
                    "counterargument": "Ограничение может быть частью защиты системы",
                    "decision": "нет замечаний",
                    "evidence": "const timeout = 25;" if len(calls) == 1 else "",
                })}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            analysis, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertEqual(analysis["evidence"], "")

    def test_two_invalid_answers_fail_closed_in_russian(self):
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(1)
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Проверить логи",
                    "recommendation": "Добавить тест",
                    "severity": "низкий",
                    "evidence": ["не цитата"],
                })}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "после двух попыток"):
                ai.free_review("const timeout = 25;", "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)

    def test_reasoning_is_required_for_real_ai_reports(self):
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Проблема с конфигурацией",
                    "recommendation": "Добавить тест",
                    "severity": "низкий",
                    "evidence": "const timeout = 25;",
                })}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "после двух попыток"):
                ai.free_review("const timeout = 25;", "index.js", "sidj", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertIn("Design context:", calls[0]["messages"][1]["content"])
        self.assertIn("private chat", calls[0]["messages"][1]["content"])

    def test_thoughtful_no_finding_is_valid(self):
        class FakeOpener:
            def open(self, req, timeout):
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Подтверждённых проблем не выявлено",
                    "recommendation": "Изменений не требуется",
                    "severity": "нет замечаний",
                    "evidence": "",
                    "intent": "Проверяет ограничение доступа к локальному сервису",
                    "impact": "Нет подтверждённого сбоя при обычном сценарии",
                    "counterargument": "Ослабление ограничения может ухудшить безопасность",
                    "decision": "нет замечаний",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            analysis, _ = ai.free_review("127.0.0.1:12345", "main.go", "reserve", "fake-key")
        self.assertEqual(analysis["decision"], "нет замечаний")
        self.assertEqual(analysis["evidence"], "")

    def test_conflicting_severity_and_decision_rejected(self):
        class FakeOpener:
            def open(self, req, timeout):
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Проблема",
                    "recommendation": "Проверить",
                    "severity": "нет замечаний",
                    "evidence": "",
                    "intent": "Проверяет существующее поведение сервиса",
                    "impact": "Потенциальный сценарий требует проверки",
                    "counterargument": "Существующее поведение может быть намеренным",
                    "decision": "исправить",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "Противоречие"):
                ai.free_review("const timeout = 25;", "file.js", "site", "fake-key")

    def test_denies_non_free_model(self):
        with patch.object(ai, "FREE_MODELS", ("expensive/model",)):
            with self.assertRaisesRegex(RuntimeError, "только бесплатные модели"):
                ai.free_review("source", "file", "project", "key")


if __name__ == "__main__":
    unittest.main()
