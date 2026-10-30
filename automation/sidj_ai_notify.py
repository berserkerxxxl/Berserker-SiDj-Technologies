"""Send read-only Russian Telegram summaries of free AI improvement runs.

Called only by a trusted GitHub Actions workflow. Never executes code from pull requests.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "berserkerxxxl/Berserker-SiDj-Technologies"
AI_WORKFLOW = "B/S tech - free AI improvement proposals"
AI_BRANCH_PREFIX = "ai/sidj-free-"
AI_PROJECT = "B/S SiDj — Telegram-бот (Cloudflare Worker)"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY


def safe_text(value: object, length: int) -> str:
    """Never format untrusted PR text as Telegram markup or print raw API data."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", "".join(c for c in value if c.isprintable())).strip()[:length]


def github_get(path: str, token: str) -> object:
    if not path.startswith("/") or "://" in path or ".." in path:
        raise ValueError("Unsafe GitHub API path")
    req = Request(API_ROOT + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "B-S-tech-SiDj-AI-Notifier",
    })
    with urlopen(req, timeout=18) as res:
        data = res.read(300_000 + 1)
    if len(data) > 300_000:
        raise RuntimeError("GitHub response too large")
    return json.loads(data)


def is_our_ai_run(event: dict) -> bool:
    run = event.get("workflow_run")
    if not isinstance(run, dict):
        return False
    return (
        run.get("name") == AI_WORKFLOW
        and run.get("head_branch") == "main"
        and (run.get("head_repository") or {}).get("full_name") == REPOSITORY
        and run.get("event") in ("workflow_dispatch", "schedule")
        and run.get("status") == "completed"
        and isinstance(run.get("id"), int)
        and isinstance(run.get("run_attempt"), int)
        and run.get("run_attempt") >= 1
    )


def run_url(run: dict) -> str:
    run_id = run.get("id")
    if isinstance(run_id, int) and run_id > 0:
        return "https://github.com/" + REPOSITORY + "/actions/runs/" + str(run_id)
    return "https://github.com/" + REPOSITORY + "/actions/workflows/sidj-free-ai.yml"


def valid_pr(pr: object, exact_branch: str | None = None) -> bool:
    if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
        return False
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    branch = head.get("ref", "")
    number = pr["number"]
    return (
        isinstance(branch, str)
        and branch.startswith(AI_BRANCH_PREFIX)
        and (exact_branch is None or branch == exact_branch)
        and isinstance(head.get("repo"), dict)
        and head["repo"].get("full_name") == REPOSITORY
        and base.get("ref") == "main"
        and pr.get("state") == "open"
        and pr.get("draft") is True
        and pr.get("html_url") == "https://github.com/" + REPOSITORY + "/pull/" + str(number)
    )


def extract_details(body: object) -> tuple[str, str, str]:
    if not isinstance(body, str):
        return "", "", ""
    def field(name: str, length: int) -> str:
        match = re.search(r"(?m)^\*\*" + re.escape(name) + r":\*\*\s*(.+)$", body)
        return safe_text(match.group(1), length) if match else ""
    model = field("Модель", 90).strip(chr(96))
    return model, field("Улучшение", 240), field("Причина", 400)


def build_message(pr: dict | None, event_name: str, run: dict | None) -> tuple[str, str, str]:
    now = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M")
    if pr is not None:
        model, summary, reason = extract_details(pr.get("body"))
        content = (
            "🤖 СиДжи | B/S tech\n"
            + "📦 Программа: " + AI_PROJECT + "\n"
            + f"💡 ИИ нашёл улучшение № {pr['number']}\n\n"
            + "Что предложено: " + (summary or "Изменение кода Telegram-бота") + "\n"
            + "Зачем: " + (reason or "Пояснение доступно в GitHub") + "\n"
            + ("Модель: " + model + "\n" if model else "")
            + "\n✅ Автоматические тесты завершены; требуется наше одобрение."
            + "\n🔒 В работающий бот изменения не внесены."
            + "\n🕒 Москва: " + now
        )
        return content[:2300], pr["html_url"], "🔍 Посмотреть предложение"
    if event_name == "workflow_dispatch":
        return ("🤖 СиДжи | B/S tech\n📦 Программа: " + AI_PROJECT + "\n✅ Канал уведомлений об ИИ работает.\n"
                "Новых открытых предложений ИИ сейчас нет.\n🕒 Москва: " + now,
                "https://github.com/" + REPOSITORY + "/pulls", "📋 Все предложения")
    run = run or {}
    conclusion = run.get("conclusion")
    if conclusion == "success":
        status = "ℹ️ Аудит завершён. Новое предложение не создано (возможно, уже есть открытый PR)."
    elif conclusion == "failure":
        status = "❌ ИИ-аудит завершился ошибкой. Код не был автоматически принят."
    elif conclusion == "cancelled":
        status = "⚪ ИИ-аудит отменён."
    else:
        status = "ℹ️ ИИ-аудит завершён без нового предложения."
    return ("🤖 СиДжи | B/S tech\n📦 Программа: " + AI_PROJECT + "\n" + status + "\n🕒 Москва: " + now,
            run_url(run), "📋 Журнал аудита")


def find_pr(event_name: str, event: dict, token: str) -> dict | None:
    if event_name == "workflow_run":
        run = event["workflow_run"]
        if run.get("conclusion") != "success":
            return None
        branch = AI_BRANCH_PREFIX + str(run["id"]) + "-" + str(run["run_attempt"])
        head = quote(REPOSITORY.split("/")[0] + ":" + branch, safe="")
        data = github_get("/pulls?state=open&per_page=10&head=" + head, token)
        return next((pr for pr in data if valid_pr(pr, branch)), None) if isinstance(data, list) else None
    # A manual test should show the most recent existing AI proposal without
    # requesting a new AI completion or altering the pull request.
    data = github_get("/pulls?state=open&sort=created&direction=desc&per_page=40", token)
    return next((pr for pr in data if valid_pr(pr)), None) if isinstance(data, list) else None


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise RuntimeError("Unexpected repository")
    event_name = os.environ.get("GH_EVENT_NAME", "")
    if event_name not in ("workflow_run", "workflow_dispatch"):
        raise RuntimeError("Unsupported trigger")
    with open(os.environ["GH_EVENT_PATH"], encoding="utf-8") as stream:
        event = json.load(stream)
    if event_name == "workflow_run" and not is_our_ai_run(event):
        print("Other/untrusted workflow run ignored.")
        return
    gh_token = os.environ.get("GH_TOKEN", "").strip()
    bot_token = os.environ.get("SIDJ_BOT_TOKEN", "").strip()
    chat = os.environ.get("SIDJ_CHAT_ID", "").strip()
    if not gh_token or not bot_token or not re.fullmatch(r"[1-9]\d{0,15}", chat):
        raise RuntimeError("Missing GitHub or private Telegram credentials")
    try:
        pr = find_pr(event_name, event, gh_token)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Could not verify matching AI PR via GitHub API") from None
    message, link, button = build_message(pr, event_name, event.get("workflow_run"))
    payload = {
        "chat_id": chat,
        "text": message,
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": [[{"text": button, "url": link}]]},
    }
    request = Request(
        "https://api.telegram.org/bot" + bot_token + "/sendMessage",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=22) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Telegram notification rejected (HTTP {error.code})") from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError("Telegram notification network error") from None
    if not result.get("ok"):
        raise RuntimeError("Telegram did not accept the message")
    print("Private Russian AI audit notification delivered to Telegram.")


if __name__ == "__main__":
    main()
