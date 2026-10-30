#!/usr/bin/env python3
"""СиДжи: каталог проектов, их сборки и выдача файлов через Telegram.

Запускается по расписанию GitHub Actions. Токен и chat ID читаются из секретов,
а пути скачивания — только из проверенного каталога этого репозитория.
"""
import hashlib
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "automation" / "sidj_projects.json"
BOT_TOKEN = os.environ.get("SIDJ_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("SIDJ_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
BOT_USERNAME = "bs_sidj_bot"
MAX_DOCUMENT_BYTES = 49 * 1024 * 1024

COMMANDS = [
    {"command": "start", "description": "Приветствие и возможности"},
    {"command": "projects", "description": "Все программы B/S tech"},
    {"command": "project", "description": "Описание выбранной программы"},
    {"command": "download", "description": "Скачать программу в Telegram"},
    {"command": "status", "description": "Состояние всех проектов"},
    {"command": "builds", "description": "Последние сборки программ"},
    {"command": "errors", "description": "Ошибки сборок"},
    {"command": "help", "description": "Справка на русском"},
]
HELP = (
    "🤖 СиДжи | B/S tech\n\n"
    "📂 /projects — каталог наших программ\n"
    "📖 /project — описание и версии\n"
    "📥 /download — получить файлы прямо сюда\n"
    "📊 /status — состояние всех проектов\n"
    "🔧 /builds — последние сборки\n"
    "🚨 /errors — последние ошибки сборок\n"
    "❓ /help — справка\n\n"
    "Выбирай проект кнопками под сообщением.\n"
    "⏱ Команды проверяются примерно раз в 5 минут; GitHub иногда задерживает запуск.\n"
    "🔒 Бот отвечает только владельцу."
)


class PollingConflict(RuntimeError):
    """getUpdates raced with webhook activation or another poller."""


def catalog_projects():
    with CATALOG.open(encoding="utf-8") as stream:
        return json.load(stream)["projects"]


def get_project(project_id):
    for project in catalog_projects():
        if project["id"] == project_id:
            return project
    return None


def keyboard(rows):
    return {"inline_keyboard": rows}


def button(label, data):
    return {"text": label, "callback_data": data}


def telegram(method, data):
    request = Request(
        "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        # URL содержит токен: не раскрываем его в логах ошибок.
        if method == "getUpdates" and error.code == 409:
            raise PollingConflict("Telegram: конфликт обработчика getUpdates") from None
        raise RuntimeError(f"Telegram {method}: HTTP {error.code}") from None
    except URLError:
        raise RuntimeError(f"Telegram {method}: не удалось подключиться") from None
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method}: запрос отклонён")
    return result.get("result")


def say(message, markup=None):
    payload = {"chat_id": CHAT_ID, "text": message[:3900], "disable_web_page_preview": True}
    if markup:
        payload["reply_markup"] = markup
    telegram("sendMessage", payload)


def github_get(url):
    request = Request(url, headers={
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "B-S-tech-SiDj-Bot",
    })
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API: HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("GitHub API: нет соединения") from None


def project_runs(project, limit=12):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", REPO):
        raise RuntimeError("Некорректный адрес репозитория")
    runs = []
    for name in project.get("workflows", []):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", name):
            continue
        url = (
            f"https://api.github.com/repos/{REPO}/actions/workflows/"
            f"{name}/runs?per_page={min(limit, 30)}"
        )
        runs.extend(github_get(url).get("workflow_runs", []))
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]


def time_msk(timestamp):
    if not timestamp:
        return "дата неизвестна"
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return "дата неизвестна"


def state(run):
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status in ("queued", "waiting", "pending", "requested"):
        return "🕒 Ожидание"
    if status == "in_progress":
        return "🔄 Выполняется"
    return {
        "success": "✅ Успешно",
        "failure": "❌ Ошибка",
        "cancelled": "⚪ Отменена",
        "timed_out": "⏱ Превышено время",
        "skipped": "⏭ Пропущена",
    }.get(conclusion, "ℹ️ Нет результата")


def failure_reason(run):
    """Краткая причина по неуспешному заданию, без выдуманных подробностей."""
    conclusion = run.get("conclusion")
    if conclusion == "timed_out":
        return "Превышено время выполнения."
    if conclusion != "failure":
        return None
    run_id = run.get("id")
    if not isinstance(run_id, int):
        return "Один из этапов сборки завершился ошибкой."
    try:
        jobs = github_get(
            f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"
        ).get("jobs", [])
    except RuntimeError:
        return "Не удалось получить подробности сбоя из GitHub."
    for job in jobs:
        if job.get("conclusion") in ("failure", "timed_out"):
            failed_step = next(
                (step.get("name", "") for step in job.get("steps", [])
                 if step.get("conclusion") in ("failure", "timed_out")), ""
            )
            job_name = job.get("name") or "неизвестный этап"
            return "Не прошёл этап: " + job_name + (
                " → " + failed_step if failed_step else ""
            )
    return "Один из этапов сборки завершился ошибкой."


def error_button(project, run):
    """Кнопка вместо длинной ссылки. Только для настоящих ошибок."""
    if run.get("conclusion") not in ("failure", "timed_out"):
        return None
    url = run.get("html_url", "")
    if not re.fullmatch(
        r"https://github\.com/" + re.escape(REPO) + r"/actions/runs/[0-9]+", url
    ):
        return None
    label = "🔍 Посмотреть ошибку"
    number = run.get("run_number")
    if number:
        label += f" #{number}"
    return {"text": label, "url": url}


def run_text(run, name, version=""):
    label = name + (" · " + str(version) if version else "")
    result = (
        f"{label}: {state(run)}\n"
        f"Время МСК: {time_msk(run.get('updated_at') or run.get('created_at'))}"
    )
    reason = failure_reason(run)
    if reason:
        result += "\nПричина: " + reason
    return result


def list_projects():
    projects = catalog_projects()
    text = "🤖 B/S tech — наши разработки\n\n"
    text += "\n".join(
        f"• {p['name']} — {p.get('version', 'версия не указана')}"
        for p in projects
    )
    text += "\n\nНажми на проект, чтобы прочитать описание и скачать файлы."
    markup = keyboard([[button(p["name"], "p:" + p["id"])] for p in projects])
    say(text, markup)


def show_project(project_id):
    project = get_project(project_id)
    if not project:
        list_projects()
        return
    text = (
        f"📦 {project['name']} · {project.get('version', '')}\n\n"
        f"{project['description']}\n\n"
        f"ℹ️ {project['notes']}\n\n"
        f"🌐 {project['page']}\n\n"
        "📥 Выбери нужный файл для загрузки в этот чат."
    )
    rows = [[button(d["label"], f"d:{project_id}:{d['id']}")] for d in project["downloads"]]
    rows.append([button("◀️ Все проекты", "projects")])
    say(text, keyboard(rows))


def show_downloads():
    projects = catalog_projects()
    say(
        "📥 Выбери программу, затем нужную версию файла.\n"
        "Файл придёт вложением в этот чат. Большие файлы могут отправляться дольше.",
        keyboard([[button(p["name"], "p:" + p["id"])] for p in projects]),
    )


def safe_document(project_id, download_id):
    project = get_project(project_id)
    if not project:
        say("⚠️ Такой программы нет в каталоге.")
        return
    entry = next((d for d in project["downloads"] if d["id"] == download_id), None)
    if not entry:
        show_project(project_id)
        return
    path = ROOT / entry["path"]
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or not path.is_file():
        say("⚠️ Файл не найден в текущей версии GitHub. Используй ссылку на сайте:\n" + project["page"])
        return
    count = resolved.stat().st_size
    if count > MAX_DOCUMENT_BYTES:
        say("⚠️ Файл превышает лимит загрузки бота (примерно 50 МБ).\n" + project["page"])
        return
    # Проверяем контрольную сумму опубликованных архивов, если она доступна.
    sha_file = path.with_name(path.name + ".sha256")
    expected = entry.get("sha256")
    if sha_file.is_file():
        expected = sha_file.read_text(encoding="utf-8").split()[0]
    if expected:
        actual = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if actual.lower() != expected.lower():
            say("⛔ Проверка контрольной суммы не пройдена. Отправка отменена.")
            return

    # Telegram sendDocument: multipart/form-data, оригинальные байты из репозитория.
    boundary = "sidj-" + uuid.uuid4().hex
    filename = path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    caption = f"📦 {project['name']} · {project.get('version', '')}\n{entry['label']}"
    parts = []
    def field(name, value):
        return (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n"
        ).encode("utf-8")
    parts.append(field("chat_id", CHAT_ID))
    parts.append(field("caption", caption))
    parts.append(field("disable_content_type_detection", "true"))
    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    body = b"".join(parts) + header + path.read_bytes() + b"\r\n" + f"--{boundary}--\r\n".encode("ascii")
    req = Request(
        "https://api.telegram.org/bot" + BOT_TOKEN + "/sendDocument",
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        method="POST",
    )
    try:
        with urlopen(req, timeout=130) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Не удалось отправить файл: Telegram HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("Не удалось подключиться к Telegram для отправки файла") from None
    if not result.get("ok"):
        raise RuntimeError("Telegram не принял файл")
    print(f"Файл отправлен: {project_id}/{download_id} ({count} байт)")


def all_builds(errors_only=False):
    entries = []
    for project in catalog_projects():
        if project.get("workflows"):
            for run in project_runs(project):
                if not errors_only or run.get("conclusion") in ("failure", "timed_out"):
                    entries.append((run.get("created_at", ""), project, run))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def show_status():
    sections = ["📊 B/S tech — состояние проектов"]
    failed = []
    for project in catalog_projects():
        if not project.get("workflows"):
            sections.append(
                f"📦 {project['name']} · {project.get('version', '')}\n"
                "Опубликован. Автоматическая сборка не настроена."
            )
        else:
            runs = project_runs(project, limit=5)
            if runs:
                run = runs[0]
                sections.append(
                    "💾 " + run_text(run, project["name"], project.get("version", ""))
                )
                failed.append((project, run))
            else:
                sections.append(f"💾 {project['name']}: данных о сборках пока нет.")
    rows = [[button("📂 Каталог программ", "projects")]]
    rows.extend([[b] for project, run in failed
                 if (b := error_button(project, run)) is not None])
    say("\n\n".join(sections), keyboard(rows))


def show_builds():
    entries = all_builds()
    if not entries:
        say("🔧 У подключённых проектов пока нет записей автоматических сборок.")
        return
    latest = entries[:5]
    text = "🔧 Последние сборки подключённых проектов\n\n"
    text += "\n\n".join(
        run_text(run, project["name"], project.get("version", ""))
        for _, project, run in latest
    )
    text += "\n\nДля остальных программ автоматические сборки пока не настроены."
    rows = [[b] for _, project, run in latest
            if (b := error_button(project, run)) is not None]
    say(text, keyboard(rows) if rows else None)


def show_errors():
    entries = all_builds(errors_only=True)
    if not entries:
        say("✅ Среди доступных запусков подключённых проектов ошибок не обнаружено.")
        return
    latest = entries[:5]
    text = "🚨 Последние ошибки сборок\n\n"
    text += "\n\n".join(
        run_text(run, project["name"], project.get("version", ""))
        for _, project, run in latest
    )
    rows = [[b] for _, project, run in latest
            if (b := error_button(project, run)) is not None]
    say(text, keyboard(rows) if rows else None)


def handle_command(raw):
    words = raw.strip().split()
    cmd = words[0].lower() if words else "/help"
    if cmd.startswith("/") and "@" in cmd:
        cmd, mention = cmd.split("@", 1)
        if mention != BOT_USERNAME:
            return
    if cmd in ("/help", "/start"):
        say(HELP, keyboard([[button("📂 Все проекты", "projects")],
                            [button("📥 Скачать программу", "downloads")]]))
    elif cmd == "/projects":
        list_projects()
    elif cmd == "/project":
        show_project(words[1].lower() if len(words) > 1 else "")
    elif cmd == "/download":
        if len(words) >= 3:
            safe_document(words[1].lower(), words[2].lower())
        elif len(words) == 2:
            show_project(words[1].lower())
        else:
            show_downloads()
    elif cmd == "/status":
        show_status()
    elif cmd == "/builds":
        show_builds()
    elif cmd == "/errors":
        show_errors()
    else:
        say("🤖 Не знаю такой команды. Напиши /help или открой /projects.")


def process(update):
    cb = update.get("callback_query") or {}
    if cb:
        chat = (cb.get("message") or {}).get("chat") or {}
        sender = cb.get("from") or {}
        if (chat.get("type") != "private" or str(chat.get("id")) != CHAT_ID
                or str(sender.get("id")) != CHAT_ID or sender.get("is_bot") is not False):
            return
        telegram("answerCallbackQuery", {"callback_query_id": cb["id"]})
        action = cb.get("data", "")
        if action == "projects":
            list_projects()
        elif action == "downloads":
            show_downloads()
        elif re.fullmatch(r"p:[a-z0-9_]+", action):
            show_project(action.split(":")[1])
        elif re.fullmatch(r"d:[a-z0-9_]+:[a-z0-9_]+", action):
            _, project, file_id = action.split(":")
            safe_document(project, file_id)
        return
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if (chat.get("type") != "private" or str(chat.get("id")) != CHAT_ID
            or str(sender.get("id")) != CHAT_ID or sender.get("is_bot") is not False):
        return
    raw = (message.get("text") or "").strip()
    if raw:
        handle_command(raw if raw.startswith("/") else "/help")


def main():
    if not BOT_TOKEN or not CHAT_ID or not GITHUB_TOKEN:
        raise RuntimeError("Не настроены секреты Telegram или GITHUB_TOKEN")
    webhook = telegram("getWebhookInfo", {})
    if webhook.get("url"):
        print("Активен Cloudflare webhook. Опрос Telegram отключён во избежание конфликта.")
        return
    current = telegram("getMyCommands", {})
    if current != COMMANDS:
        telegram("setMyCommands", {"commands": COMMANDS})
        print("Меню команд обновлено.")
    offset = None
    processed = 0
    for _ in range(5):
        payload = {"limit": 100, "timeout": 0,
                   "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        updates = telegram("getUpdates", payload)
        if not updates:
            break
        for update in updates:
            try:
                process(update)
            except RuntimeError as error:
                print(f"Ошибка обработки команды: {error}")
                try:
                    say("⚠️ Не удалось выполнить команду: " + str(error))
                except RuntimeError:
                    # Не подтверждаем update при ошибке отправки: повторим позже.
                    raise
            offset = update["update_id"] + 1
            processed += 1
        if len(updates) < 100:
            break
    if offset is not None:
        # Подтверждаем обработанные updates на стороне Telegram.
        telegram("getUpdates", {
            "offset": offset, "limit": 1, "timeout": 0,
            "allowed_updates": ["message", "callback_query"]
        })
    print(f"Обработано обновлений Telegram: {processed}")


def run():
    try:
        main()
    except PollingConflict:
        # Activation can happen after the initial getWebhookInfo check.
        # Never delete a webhook, consume another batch or expose the token.
        if telegram("getWebhookInfo", {}).get("url"):
            print("Webhook включён во время опроса. Опрос остановлен; очередь не сброшена.")
            return
        raise


if __name__ == "__main__":
    run()
