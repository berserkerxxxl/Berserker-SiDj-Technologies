#!/usr/bin/env python3
"""СиДжи: приватные Telegram-команды через GitHub Actions без отдельного сервера.

Telegram хранит непрочитанные updates; подтверждение выполняется offset после
успешной обработки, поэтому отдельная база состояния не требуется.
"""
import json
import os
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ.get("SIDJ_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("SIDJ_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
BOT_USERNAME = "bs_sidj_bot"

COMMANDS = [
    {"command": "start", "description": "Приветствие и возможности"},
    {"command": "status", "description": "Состояние B/S Reserve"},
    {"command": "builds", "description": "Последние сборки"},
    {"command": "errors", "description": "Ошибки сборок"},
    {"command": "help", "description": "Помощь по командам"},
]
HELP = (
    "🤖 СиДжи | B/S tech\n\n"
    "Привет! Я помощник нашей лаборатории.\n\n"
    "/status — состояние последней сборки B/S Reserve\n"
    "/builds — пять последних сборок\n"
    "/errors — недавние ошибки сборок\n"
    "/help — эта подсказка\n\n"
    "🔔 О завершении сборок сообщаю автоматически.\n"
    "⏱ Команды обрабатываются приблизительно раз в 5 минут (иногда позже)."
)


def telegram(method, data):
    request = Request(
        "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            result = json.load(response)
    except HTTPError as error:
        # Не печатать URL: он содержит секретный токен.
        raise RuntimeError(f"Telegram {method}: HTTP {error.code}") from None
    except URLError:
        raise RuntimeError(f"Telegram {method}: ошибка подключения") from None
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method}: запрос отклонён")
    return result.get("result")


def github_runs():
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", REPO):
        raise RuntimeError("Некорректный GITHUB_REPOSITORY")
    url = (
        "https://api.github.com/repos/" + REPO
        + "/actions/workflows/reserve-platforms.yml/runs?per_page=100"
    )
    request = Request(
        url,
        headers={
            "Authorization": "Bearer " + GITHUB_TOKEN,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "B-S-tech-SiDj-Bot",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API: HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("GitHub API: нет соединения") from None
    return data.get("workflow_runs", [])


def moscow_time(value):
    if not value:
        return "дата неизвестна"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return "дата неизвестна"


def status_label(run):
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status in ("queued", "waiting", "pending", "requested"):
        return "🕒 Ожидает запуска"
    if status == "in_progress":
        return "🔄 Выполняется"
    return {
        "success": "✅ Успешно",
        "failure": "❌ Ошибка",
        "cancelled": "⚪ Отменена",
        "timed_out": "⏱ Превышено время",
        "skipped": "⏭ Пропущена",
        "neutral": "ℹ️ Без итоговой оценки",
    }.get(conclusion, "ℹ️ Статус не определён")


def one_run(run):
    return (
        f"#{run.get('run_number', '?')} — {status_label(run)}\n"
        f"Ветка: {run.get('head_branch') or 'неизвестна'}\n"
        f"Москва: {moscow_time(run.get('updated_at') or run.get('created_at'))}\n"
        f"{run.get('html_url', '')}"
    )


def answer(command):
    if command in ("/start", "/help"):
        return HELP
    if command not in ("/status", "/builds", "/errors"):
        return "🤖 Я пока понимаю только команды:\n/status, /builds, /errors, /help"

    runs = github_runs()
    if not runs:
        return "💾 B/S Reserve\nВ GitHub пока нет доступных запусков сборки."

    if command == "/status":
        return "🤖 СиДжи | B/S tech\n💾 B/S Reserve — последняя сборка\n\n" + one_run(runs[0])
    if command == "/builds":
        lines = [
            f"#{r.get('run_number', '?')}: {status_label(r)}"
            f" — {moscow_time(r.get('updated_at') or r.get('created_at'))}"
            for r in runs[:5]
        ]
        return "💾 B/S Reserve — последние сборки\n\n" + "\n".join(lines)

    errors = [r for r in runs if r.get("conclusion") in ("failure", "timed_out")]
    if not errors:
        return (
            "✅ Среди последних " + str(len(runs))
            + " запусков B/S Reserve ошибок не найдено."
        )
    return (
        "🚨 B/S Reserve — недавние ошибки\n\n"
        + "\n\n".join(one_run(r) for r in errors[:5])
    )


def process(update):
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    # Строгая привязка к владельцу: чужие чаты полностью игнорируем.
    if chat.get("type") != "private" or str(chat.get("id")) != CHAT_ID:
        return
    raw = (message.get("text") or "").strip()
    if not raw:
        return
    first = raw.split(maxsplit=1)[0].lower()
    if first.startswith("/") and "@" in first:
        cmd, mentioned = first.split("@", 1)
        if mentioned != BOT_USERNAME:
            return
        first = cmd
    if not first.startswith("/"):
        first = "/help"
    try:
        response = answer(first)
    except RuntimeError as error:
        response = "⚠️ Не удалось получить данные:\n" + str(error)
    telegram("sendMessage", {
        "chat_id": CHAT_ID,
        "text": response[:4000],
        "disable_web_page_preview": True,
    })


def main():
    if not BOT_TOKEN or not CHAT_ID or not GITHUB_TOKEN:
        raise RuntimeError("Отсутствуют секреты Telegram или GITHUB_TOKEN")

    current = telegram("getMyCommands", {})
    if current != COMMANDS:
        telegram("setMyCommands", {"commands": COMMANDS})
        print("Команды Telegram зарегистрированы.")

    processed = 0
    # Один рабочий процесс, без webhook, с подтверждением каждого update.
    for _ in range(5):
        updates = telegram("getUpdates", {
            "limit": 100, "timeout": 0, "allowed_updates": ["message"]
        })
        if not updates:
            break
        for update in updates:
            process(update)
            # Telegram подтверждает все updates строго ниже offset.
            telegram("getUpdates", {
                "offset": update["update_id"] + 1,
                "limit": 1, "timeout": 0, "allowed_updates": ["message"]
            })
            processed += 1
        if len(updates) < 100:
            break
    print(f"Обработано входящих обновлений: {processed}")


if __name__ == "__main__":
    main()
