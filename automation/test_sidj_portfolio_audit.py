"""Offline tests of read-only portfolio AI: no secrets, no writes, only free models."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

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
                        "confidence": "высокая",
                        "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                        "evidence": "public source"
                    })}}],
                }
                return io.BytesIO(json.dumps(response).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            report, model = ai.free_review("public source", "public/file.js", "B/S tech", "fake-key")
        self.assertEqual(model, "nvidia/nemotron-3-ultra-550b-a55b:free")
        self.assertEqual(report["severity"], "низкий")
        self.assertEqual(len(requests), 1)
        self.assertTrue(all(m.endswith(":free") or m == ai.FREE_ROUTER for m in requests[0]["models"]))
        self.assertEqual(requests[0]["route"], "fallback")
        self.assertEqual(requests[0]["response_format"], {"type": "json_object"})
        self.assertEqual(requests[0]["max_tokens"], 3600)
        self.assertEqual(requests[0]["provider"], {"require_parameters": True})
        self.assertNotIn("reasoning", requests[0])
        self.assertEqual(requests[0]["models"][-1], ai.FREE_ROUTER)
        self.assertLess(ai.RETRY_SOURCE, ai.MAX_SOURCE)
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
                        "confidence": "высокая",
                        "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
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
                        "confidence": "высокая",
                        "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                        "evidence": evidence,
                    })}
                }]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            result, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["evidence"], "const someLongName =")
        self.assertEqual(calls[0]["model"], ai.FREE_MODELS[0])
        self.assertEqual(calls[1]["model"], ai.COMPACT_MODEL)
        self.assertTrue(all(model.endswith(":free") or model == ai.FREE_ROUTER for call in calls for model in call["models"]))
        self.assertEqual([call["max_tokens"] for call in calls], [3600, 5200])
        self.assertTrue(all(call["provider"] == {"require_parameters": True}
                            for call in calls))
        self.assertTrue(all("reasoning" not in call for call in calls))

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
                        "confidence": "высокая",
                        "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                        "evidence": "const timeout = 25;",
                    })}}
                )
                return io.BytesIO(json.dumps({"choices": [item]}).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            analysis, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertEqual(analysis["severity"], "низкий")

    def test_truncation_uses_compact_json_capable_free_retry(self):
        calls = []

        class FakeOpener:
            def open(self, req, timeout):
                request = json.loads(req.data)
                calls.append(request)
                if len(calls) == 1:
                    response = {"choices": [{"finish_reason": "length",
                                             "message": {"content": "{"}}]}
                else:
                    response = {"model": ai.COMPACT_MODEL,
                                "choices": [{"finish_reason": "stop",
                                             "message": {"content": json.dumps({
                                                 "finding": "Подтверждённых проблем не выявлено",
                                                 "recommendation": "Изменений не требуется",
                                                 "severity": "нет замечаний",
                                                 "evidence": "",
                                                 "intent": "Проверяет явно заданный фрагмент программы",
                                                 "impact": "Сбой по фрагменту кода пока не доказан",
                                                 "counterargument": "Изменения могут ухудшить поведение",
                                                 "decision": "нет замечаний",
                                                 "confidence": "средняя",
                                                 "verification": "Сравнить результаты ручной проверки",
                                             }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            result, model = ai.free_review("const timeout = 25;", "path.js", "B/S", "fake-key")
        self.assertEqual(result["decision"], "нет замечаний")
        self.assertEqual(model, ai.COMPACT_MODEL)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["models"], [ai.COMPACT_MODEL, ai.FREE_ROUTER])
        self.assertEqual(calls[1]["max_tokens"], 5200)
        self.assertIn("900 characters total", calls[1]["messages"][1]["content"])
        self.assertLess(ai.RETRY_SOURCE, ai.MAX_SOURCE)

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
                    "confidence": "средняя",
                    "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
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
                    "confidence": "средняя",
                    "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
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
                    "confidence": "высокая",
                    "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "Противоречие"):
                ai.free_review("const timeout = 25;", "file.js", "site", "fake-key")

    def test_retry_uses_smaller_complete_source_and_exact_evidence(self):
        source = "const checked = 1;\n" + "".join(
            f"const field_{i} = {i};\\n" for i in range(350)).replace("\\n", "\n")
        self.assertGreater(len(source), ai.MAX_SOURCE)
        source = source[:ai.MAX_SOURCE]
        # Use full-line source as real source_windows would provide.
        source = source[:source.rfind("\n") + 1]
        calls = []

        class FakeOpener:
            def open(self, req, timeout):
                payload = json.loads(req.data)
                calls.append(payload)
                response = ({"finish_reason": "length", "message": {"content": ""}}
                            if len(calls) == 1 else
                            {"finish_reason": "stop", "message": {"content": json.dumps({
                                "finding": "Проверка требует теста",
                                "recommendation": "Добавить точечный тест",
                                "severity": "низкий",
                                "evidence": "const checked = 1;",
                                "intent": "Сохраняет локальные значения исходного кода",
                                "impact": "Некорректное значение может нарушить работу",
                                "counterargument": "Ограничение может быть намеренной защитой",
                                "decision": "наблюдать",
                                "confidence": "средняя",
                                "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                            }, ensure_ascii=False)}})
                return io.BytesIO(json.dumps({"choices": [response]}).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            result, _ = ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        first = calls[0]["messages"][1]["content"]
        second = calls[1]["messages"][1]["content"]
        self.assertIn(source, first)
        self.assertLess(len(second), len(first))
        self.assertIn("const checked = 1;\n", second)
        self.assertTrue(result["_retry_excerpt"])
        self.assertEqual(result["decision"], "наблюдать")

    def test_retry_rejects_evidence_missing_from_reduced_excerpt(self):
        source = ("const before = 1;\n" * 300) + "const hidden = 99;\n"
        calls = []

        class FakeOpener:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                output = ({"finish_reason": "length", "message": {"content": ""}}
                          if len(calls) == 1 else
                          {"finish_reason": "stop", "message": {"content": json.dumps({
                              "finding": "Проблема",
                              "recommendation": "Исправить",
                              "severity": "низкий",
                              "evidence": "const hidden = 99;",
                              "intent": "Управляет локальными значениями настройки",
                              "impact": "Ошибка изменяет результат последующего вызова",
                              "counterargument": "Значение может быть намеренным ограничением",
                              "decision": "исправить",
                              "confidence": "высокая",
                              "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                          }, ensure_ascii=False)}})
                return io.BytesIO(json.dumps({"choices": [output]}).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "не подтверждается исходным кодом"):
                ai.free_review(source, "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)

    def test_transient_http_429_retries_free_model_once(self):
        from urllib.error import HTTPError

        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                payload = json.loads(req.data)
                calls.append(payload)
                if len(calls) == 1:
                    raise HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Подтверждённых проблем не выявлено",
                    "recommendation": "Изменений не требуется",
                    "severity": "нет замечаний",
                    "evidence": "",
                    "intent": "Ограничивает работу программы локальным сценарием",
                    "impact": "Нет подтверждённого сбоя при обычном сценарии",
                    "counterargument": "Изменение может ослабить защиту приложения",
                    "decision": "нет замечаний",
                    "confidence": "средняя",
                    "verification": "Сравнить поведение до и после изменения в тестовом сценарии",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            result, _ = ai.free_review("const timeout = 25;\n", "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(model.endswith(":free") or model == ai.FREE_ROUTER for call in calls for model in call["models"]))
        self.assertEqual(result["decision"], "нет замечаний")

    def test_retry_excerpt_never_splits_an_identifier(self):
        source = "const first = 1;\n" + "x" * ai.MAX_SOURCE + "\n"
        excerpt = ai.retry_excerpt(source)
        self.assertEqual(excerpt, "const first = 1;\n")
        self.assertTrue(excerpt.endswith("\n"))
        self.assertEqual(ai.retry_excerpt("x" * ai.MAX_SOURCE), "x" * ai.MAX_SOURCE)

    def test_professor_observation_has_reproducible_test(self):
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                result = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Сканирование DOM может быть дорогим",
                    "recommendation": "Замерить время поиска в профилировщике",
                    "severity": "средний",
                    "evidence": "for(const target of document.querySelectorAll('body *'))",
                    "intent": "Поиск боковой панели в интерфейсе",
                    "impact": "Большой DOM может замедлить один поиск панели",
                    "counterargument": "Поиск работает не постоянно и кэширует элемент",
                    "decision": "наблюдать",
                    "confidence": "средняя",
                    "verification": "Измерить длительность findNav при 5000 элементах DOM",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(result).encode("utf-8"))
        source = "for(const target of document.querySelectorAll('body *')) {"
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            analysis, _ = ai.free_review(source, "limits.js", "B/S", "fake-key")
        self.assertEqual(analysis["decision"], "наблюдать")
        self.assertEqual(analysis["confidence"], "средняя")
        self.assertIn("findNav", analysis["verification"])
        self.assertEqual(len(calls), 1)
        self.assertIn("verification", calls[0]["messages"][0]["content"])
        self.assertIn("MANUAL test", calls[0]["messages"][0]["content"])

    def test_professor_weak_fix_is_rejected_on_both_attempts(self):
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Может замедлять страницу",
                    "recommendation": "Переписать поиск",
                    "severity": "средний",
                    "evidence": "const timeout = 25;",
                    "intent": "Контролирует ожидание ответа в программе",
                    "impact": "В отдельных случаях возможна задержка",
                    "counterargument": "Таймаут защищает от зависших запросов",
                    "decision": "исправить",
                    "confidence": "низкая",
                    "verification": "Померить время ожидания для десяти запросов",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "Категоричное исправление без высокой уверенности"):
                ai.free_review("const timeout = 25;", "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)

    def test_professor_missing_verification_is_rejected(self):
        calls = []
        class FakeOpener:
            def open(self, req, timeout):
                calls.append(1)
                response = {"choices": [{"message": {"content": json.dumps({
                    "finding": "Возможная ошибка",
                    "recommendation": "Проверить",
                    "severity": "низкий",
                    "evidence": "const timeout = 25;",
                    "intent": "Контролирует ожидание ответа в программе",
                    "impact": "Запрос может завершиться преждевременно",
                    "counterargument": "Таймаут мог быть выбран намеренно",
                    "decision": "наблюдать",
                    "confidence": "средняя",
                    "verification": "",
                }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch.object(ai, "build_opener", return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError, "проверку"):
                ai.free_review("const timeout = 25;", "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)


    def test_http_503_twice_reports_safe_route_and_backoff(self):
        from urllib.error import HTTPError
        calls = []

        class Unavailable:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                raise HTTPError(req.full_url, 503, "Service Unavailable", {}, None)

        with patch.object(ai, "build_opener", return_value=Unavailable()), \
                patch.object(ai, "sleep") as pause:
            with self.assertRaisesRegex(RuntimeError, "HTTP 503.*openrouter/free"):
                ai.free_review("const enabled = true;", "file.js", "B/S", "fake-key")

        self.assertEqual(len(calls), 2)
        pause.assert_called_once_with(1)
        self.assertEqual([call["model"] for call in calls], [ai.FREE_MODELS[0], ai.COMPACT_MODEL])
        self.assertTrue(all(call["models"][-1] == ai.FREE_ROUTER for call in calls))
        self.assertTrue(all(call["provider"]["require_parameters"] for call in calls))

    def test_http_503_recovers_and_reports_router_selected_free_model(self):
        from urllib.error import HTTPError
        calls = []

        class Recovering:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                if len(calls) == 1:
                    raise HTTPError(req.full_url, 503, "Service Unavailable", {}, None)
                reply = {"model": "qwen/qwen3-4b:free",
                         "choices": [{"message": {"content": json.dumps({
                             "finding": "Подтверждённых проблем не выявлено",
                             "recommendation": "Изменений не требуется",
                             "severity": "нет замечаний",
                             "evidence": "",
                             "intent": "Сохраняет локальную конфигурацию системы",
                             "impact": "Нет подтверждённого сбоя в исходном коде",
                             "counterargument": "Изменения могут нарушить существующее поведение",
                             "decision": "нет замечаний",
                             "confidence": "средняя",
                             "verification": "Сравнить ответы в ручной проверке",
                         }, ensure_ascii=False)}}]}
                return io.BytesIO(json.dumps(reply).encode("utf-8"))

        with patch.object(ai, "build_opener", return_value=Recovering()), \
                patch.object(ai, "sleep") as pause:
            analysis, model = ai.free_review("const enabled = true;", "file.js", "B/S", "fake-key")
        self.assertEqual(len(calls), 2)
        pause.assert_called_once_with(1)
        self.assertEqual(analysis["decision"], "нет замечаний")
        self.assertEqual(model, "qwen/qwen3-4b:free")
        self.assertTrue(all(call["models"][-1] == ai.FREE_ROUTER for call in calls))

    def test_free_router_is_the_only_non_suffix_route(self):
        self.assertEqual(ai.FREE_ROUTER, "openrouter/free")
        self.assertTrue(ai.FREE_MODELS)
        self.assertTrue(all(m.endswith(":free") for m in ai.FREE_MODELS))
        self.assertTrue(ai.COMPACT_MODEL.endswith(":free"))

    def test_denies_non_free_model(self):
        with patch.object(ai, "FREE_MODELS", ("expensive/model",)):
            with self.assertRaisesRegex(RuntimeError, "только бесплатные модели"):
                ai.free_review("source", "file", "project", "key")


class AttemptDiagnosticsTests(unittest.TestCase):
    KEY = "diagnostic-key-sentinel"
    SOURCE = "const source_sentinel = true;"
    PRIVATE_TEXT = "response-text-sentinel"

    def reply(self, *, model=ai.COMPACT_MODEL, finish="stop", evidence=""):
        return {"model": model, "choices": [{"finish_reason": finish, "message": {
            "content": json.dumps({
                "finding": self.PRIVATE_TEXT,
                "recommendation": "Изменений не требуется",
                "severity": "нет замечаний", "evidence": evidence,
                "intent": "Проверяет явно заданный фрагмент программы",
                "impact": "Сбой по фрагменту кода пока не доказан",
                "counterargument": "Изменения могут ухудшить поведение",
                "decision": "нет замечаний", "confidence": "средняя",
                "verification": "Сравнить результаты ручной проверки",
            }, ensure_ascii=False)}}]}

    def review(self, *responses):
        calls, output = [], io.StringIO()
        pending = iter(responses)

        class FakeOpener:
            def open(self, req, timeout):
                calls.append(json.loads(req.data))
                value = next(pending)
                if isinstance(value, Exception):
                    raise value
                return io.BytesIO(value if isinstance(value, bytes) else
                                  json.dumps(value).encode("utf-8"))

        result, error = None, None
        with patch.object(ai, "build_opener", return_value=FakeOpener()), \
                patch.object(ai, "sleep"), redirect_stdout(output):
            try:
                result = ai.free_review(self.SOURCE, "path-sentinel.js", "B/S", self.KEY)
            except (ValueError, RuntimeError) as failure:
                error = failure
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(events), len(calls))
        self.assertLessEqual(len(calls), 2)
        for event in events:
            self.assertEqual(set(event) - {"http_status"}, {
                "event", "attempt", "requested_models", "actual_model", "outcome",
                "reason", "finish_reason", "will_retry", "elapsed_ms"})
            self.assertEqual(event["event"], "professor_attempt")
            self.assertIsInstance(event["elapsed_ms"], int)
            self.assertGreaterEqual(event["elapsed_ms"], 0)
        for private in (self.KEY, self.SOURCE, self.PRIVATE_TEXT, "path-sentinel.js"):
            self.assertNotIn(private, output.getvalue())
        return result, error, events

    def test_token_limit_recovers_with_actual_router_model_and_safe_events(self):
        first = self.reply(model=ai.FREE_MODELS[0], finish="length")
        first["choices"][0]["message"]["content"] = self.KEY + self.SOURCE
        model = "nvidia/nemotron-3.5-super-vl:free"
        result, error, events = self.review(first, self.reply(model=model))
        self.assertIsNone(error)
        self.assertEqual(result[1], model)
        self.assertEqual([event["attempt"] for event in events], [1, 2])
        self.assertEqual([event["outcome"] for event in events], ["retry", "success"])
        self.assertEqual([event["reason"] for event in events], ["token_limit", "validated"])
        self.assertEqual([event["will_retry"] for event in events], [True, False])
        self.assertEqual(events[0]["finish_reason"], "length")
        self.assertEqual(events[0]["actual_model"], ai.FREE_MODELS[0])
        self.assertEqual(events[1]["actual_model"], model)
        self.assertEqual(events[1]["requested_models"], [ai.COMPACT_MODEL, ai.FREE_ROUTER])
        self.assertEqual(events[0]["requested_models"], [*ai.FREE_MODELS, ai.FREE_ROUTER])

    def test_success_without_model_metadata_does_not_invent_actual_model(self):
        reply = self.reply()
        del reply["model"]
        result, error, events = self.review(reply)
        self.assertIsNone(error)
        self.assertIn("идентификатор не указан", result[1])
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["actual_model"])
        self.assertFalse(events[0]["will_retry"])

    def test_two_http_failures_log_status_without_provider_error_text(self):
        failures = [HTTPError(ai.ENDPOINT, 503, self.KEY + self.PRIVATE_TEXT,
                              {"secret": self.KEY}, io.BytesIO(self.SOURCE.encode()))
                    for _ in range(2)]
        _, error, events = self.review(*failures)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual([event["http_status"] for event in events], [503, 503])
        self.assertEqual([event["reason"] for event in events], ["http_error"] * 2)
        self.assertEqual([event["outcome"] for event in events], ["retry", "failed"])
        self.assertTrue(all(event["actual_model"] is None for event in events))

    def test_http_429_recovers_without_changing_the_two_attempt_budget(self):
        _, error, events = self.review(
            HTTPError(ai.ENDPOINT, 429, self.KEY, {}, None), self.reply())
        self.assertIsNone(error)
        self.assertEqual(events[0]["http_status"], 429)
        self.assertEqual(events[1]["actual_model"], ai.COMPACT_MODEL)

    def test_network_and_timeout_causes_are_safe_and_distinct(self):
        for failure, reason in (
            (TimeoutError(self.KEY), "timeout"),
            (URLError(TimeoutError(self.KEY)), "timeout"),
            (URLError(self.KEY), "network_error"),
        ):
            with self.subTest(reason=reason, failure=type(failure)):
                _, error, events = self.review(failure, failure)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual([event["reason"] for event in events], [reason] * 2)
                self.assertEqual([event["outcome"] for event in events], ["retry", "failed"])

    def test_validation_failure_is_logged_without_echoing_model_output(self):
        invalid = self.reply(finish={"private": self.KEY})
        invalid["choices"][0]["message"]["content"] = self.KEY + self.PRIVATE_TEXT
        _, error, events = self.review(invalid, invalid)
        self.assertIsInstance(error, ValueError)
        self.assertEqual([event["reason"] for event in events], ["invalid_analysis"] * 2)
        self.assertTrue(all(event["finish_reason"] is None for event in events))
        self.assertEqual(events[-1]["outcome"], "failed")

    def test_unverified_evidence_has_specific_reason(self):
        invalid = self.reply(evidence="const fabricated = true;")
        content = json.loads(invalid["choices"][0]["message"]["content"])
        content.update(severity="низкий", decision="наблюдать")
        invalid["choices"][0]["message"]["content"] = json.dumps(content)
        _, error, events = self.review(invalid, self.reply())
        self.assertIsNone(error)
        self.assertEqual(events[0]["reason"], "unverified_evidence")

    def test_untrusted_model_identifiers_are_not_published(self):
        for model in (None, {}, "paid/model", "provider/model:free\n" + self.KEY,
                      "provider/" + "x" * 101 + ":free", "provider/" + self.KEY + ":free"):
            with self.subTest(model_type=type(model)):
                result, error, events = self.review(self.reply(model=model))
                self.assertIsNone(error)
                self.assertIsNone(events[0]["actual_model"])
                self.assertIn("идентификатор не указан", result[1])

    def test_terminal_api_errors_are_logged_without_new_retries(self):
        for failure, reason in (
            (self.KEY.encode(), "invalid_api_json"),
            (b"\xff\xfe\xff", "invalid_api_json"),
            (b"x" * (ai.MAX_RESPONSE + 1), "response_too_large"),
            (HTTPError(ai.ENDPOINT, 401, self.KEY, {}, None), "http_error"),
            (RuntimeError("Переадресация OpenRouter отклонена"), "request_blocked"),
        ):
            with self.subTest(reason=reason):
                _, error, events = self.review(failure)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["reason"], reason)
                self.assertFalse(events[0]["will_retry"])

    def test_api_error_envelope_logs_only_safe_metadata(self):
        invalid = {"model": ai.FREE_MODELS[0],
                   "error": {"message": self.KEY + self.PRIVATE_TEXT}}
        _, error, events = self.review(invalid, invalid)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual([event["reason"] for event in events], ["api_error"] * 2)
        self.assertEqual(events[0]["actual_model"], ai.FREE_MODELS[0])


if __name__ == "__main__":
    unittest.main()

