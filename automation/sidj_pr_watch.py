"""Daily read-only review of open B/S tech GitHub PRs via private Telegram.

No untrusted PR code is executed and no tokens or raw API errors are logged.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "berserkerxxxl/Berserker-SiDj-Technologies"
API = "https://api.github.com/repos/" + REPOSITORY
MAX_ITEMS = 8


def safe_text(value: object, length: int = 90) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(c for c in value if c.isprintable()).strip()[:length]


def github_get(path: str, token: str) -> object:
    if not re.fullmatch(
        r"/(?:pulls\?state=open&per_page=100&page=[12]|"
        r"commits/[0-9a-f]{40}/check-runs\?per_page=100)", path
    ):
        raise ValueError("Unapproved GitHub API path")
    req = Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "B-S-tech-SiDj-PR-Watch",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(req, timeout=20) as res:
        body = res.read(500_001)
    if len(body) > 500_000:
        raise ValueError("GitHub response exceeds bound")
    return json.loads(body)


def open_prs(token: str) -> list[dict]:
    prs: list[dict] = []
    for page in (1, 2):
        response = github_get(f"/pulls?state=open&per_page=100&page={page}", token)
        if not isinstance(response, list):
            raise ValueError("Invalid GitHub PR listing")
        for item in response:
            if not isinstance(item, dict):
                continue
            number = item.get("number")
            if (type(number) is not int or number < 1
                    or item.get("state") != "open"):
                continue
            prs.append(item)
        if len(response) < 100:
            break
    return prs


def check_label(pr: dict, token: str) -> str:
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else ""
    if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha):
        return "⚪ Проверки неизвестны"
    try:
        response = github_get(f"/commits/{sha}/check-runs?per_page=100", token)
        checks = response.get("check_runs") if isinstance(response, dict) else None
        if not isinstance(checks, list) or not checks:
            return "⚪ Проверки отсутствуют"
        if any(not isinstance(c, dict) for c in checks):
            return "⚪ Проверки неизвестны"
        if any(c.get("status") != "completed" for c in checks):
            return "🟡 Проверки выполняются"
        conclusions = {c.get("conclusion") for c in checks}
        if conclusions & {"failure", "timed_out", "cancelled", "action_required"}:
            return "🔴 Есть ошибки"
        if conclusions <= {"success", "neutral", "skipped"} and "success" in conclusions:
            return "🟢 Проверки пройдены"
        return "⚪ Проверки требуют внимания"
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return "⚪ Результат проверок недоступен"


def create_summary(prs: list[dict], token: str, now: datetime) -> dict | None:
    """Return Telegram payload, or None for an empty backlog."""
    if not prs:
        return None
    lines = [
        "📋 B/S tech | PR на контроле",
        f"Открытых PR: {len(prs)}",
        "🕒 Москва: " + now.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M"),
        "",
    ]
    buttons = []
    for pr in prs[:MAX_ITEMS]:
        number = pr["number"]
        title = safe_text(pr.get("title"), 100) or "Без названия"
        state = "📝 Черновик" if pr.get("draft") else "👀 Ожидает решения"
        result = check_label(pr, token)
        lines.append(f"#{number} · {state}\n{title}\n{result}\n")
        buttons.append([{
            "text": f"🔍 PR #{number}",
            "url": f"https://github.com/{REPOSITORY}/pull/{number}",
        }])
    if len(prs) > MAX_ITEMS:
        lines.append(f"Ещё PR: {len(prs) - MAX_ITEMS} — открой общий список.")
    buttons.append([{"text": "📋 Все открытые PR", "url": f"https://github.com/{REPOSITORY}/pulls"}])
    lines.append("🔒 Это напоминание. Слияние и публикация не выполняются.")
    return {
        "text": "\n".join(lines)[:3500],
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": buttons},
    }


def send(payload: dict, token: str, chat: str) -> None:
    req = Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=json.dumps({"chat_id": chat, **payload}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as res:
            result = json.load(res)
    except HTTPError as exc:
        raise RuntimeError(f"Telegram HTTP {exc.code}") from None
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Telegram request failed") from None
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError("Telegram did not confirm the notification")


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise RuntimeError("Unexpected repository")
    gh = os.environ.get("GH_TOKEN", "").strip()
    bot = os.environ.get("SIDJ_BOT_TOKEN", "").strip()
    chat = os.environ.get("SIDJ_CHAT_ID", "").strip()
    if not gh or not bot or not re.fullmatch(r"[1-9][0-9]{0,15}", chat):
        raise RuntimeError("Private notifier credentials are unavailable")
    try:
        prs = open_prs(gh)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Unable to obtain open GitHub PRs") from None
    summary = create_summary(prs, gh, datetime.now(ZoneInfo("Europe/Moscow")))
    if summary is None:
        print("No open PRs: no Telegram notification.")
        return
    send(summary, bot, chat)
    print(f"Sent read-only PR review reminder for {len(prs)} open PR(s).")


if __name__ == "__main__":
    main()
