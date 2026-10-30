#!/usr/bin/env python3
"""Read-only health checks for SiDj. Only send incident/recovery messages to owner."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request
from zoneinfo import ZoneInfo

from sidj_cloudflare import HTTP, USER_AGENT

BASE = 'https://bs-tech-sidj.berserkerxxxl.workers.dev/'
STATE = Path(os.environ.get('SIDJ_MONITOR_STATE', '.sidj-monitor-state.json'))
MSK = ZoneInfo('Europe/Moscow')
# A delayed GitHub cron job is not evidence of downtime. Do not count
# observations separated by a long scheduling gap as consecutive.
MAX_GAP = 90 * 60
MIN_CONFIRM = 5 * 60
TRACKS = ('bot', 'check', 'analytics')
MESSAGES = {
    'bot': ('🚨 СиДжи: подтверждён сбой Worker или адреса webhook.',
            '✅ СиДжи: доступность Worker и адрес webhook восстановлены.'),
    'check': ('⚠️ СиДжи: проверка состояния не смогла подтвердить результат; сбой бота НЕ установлен.',
              '✅ СиДжи: независимая проверка снова работает.'),
    'analytics': ('⚠️ СиДжи: токен аналитики Cloudflare недействителен или истёк. На работу бота это не влияет.',
                  '✅ СиДжи: доступ токена аналитики Cloudflare восстановлен.'),
}


def get(url, headers=None):
    req = Request(url, headers={'User-Agent': USER_AGENT, **(headers or {})})
    with HTTP.open(req, timeout=12) as res:
        if res.status != 200:
            raise ValueError('unexpected status')
        raw = res.read(32769)
        if len(raw) > 32768:
            raise ValueError('oversized response')
    return raw


def probe(token, analytics_token=''):
    """(bot, check, analytics): good/bad/unknown, good/bad, good/bad/None.
    401 Telegram = monitoring credentials cannot verify, not proof of Worker outage.
    """
    worker = 'unknown'
    try:
        body = get(BASE).decode('utf-8')
        worker = 'good' if 'Worker доступен.' in body and 'B/S tech' in body else 'bad'
    except HTTPError:
        worker = 'bad'  # A repeatable non-200 from the canonical Worker.
    except (URLError, TimeoutError, ValueError, UnicodeError, OSError):
        pass  # Network/probe fault, not a confirmed Worker outage.

    webhook = 'unknown'
    if token:
        try:
            data = json.loads(get('https://api.telegram.org/bot' + token + '/getWebhookInfo'))
            if isinstance(data, dict) and data.get('ok') is True and isinstance(data.get('result'), dict):
                webhook = 'good' if data['result'].get('url') == BASE + 'telegram' else 'bad'
        except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError, OSError):
            pass

    # A valid HTTP 200 from the Worker plus a verified Telegram webhook are both required.
    if worker == 'bad' or webhook == 'bad':
        bot, check = 'bad', 'good'
    elif worker == webhook == 'good':
        bot, check = 'good', 'good'
    else:
        bot, check = 'unknown', 'bad'

    analytics = None
    if analytics_token:
        try:
            value = json.loads(get('https://api.cloudflare.com/client/v4/user/tokens/verify',
                                   {'Authorization': 'Bearer ' + analytics_token}))
            status = (value.get('result') or {}).get('status') if isinstance(value, dict) else None
            if status == 'active' and value.get('success') is True:
                analytics = 'good'
            elif status in ('expired', 'disabled'):
                analytics = 'bad'
            else:
                analytics = 'unknown'
        except HTTPError as exc:
            analytics = 'bad' if exc.code in (401, 403) else 'unknown'
        except (URLError, TimeoutError, ValueError, UnicodeError, OSError):
            analytics = 'unknown'
    return bot, check, analytics


def load():
    try:
        data = json.loads(STATE.read_text(encoding='utf-8'))
        if data.get('version') == 1 and isinstance(data.get('tracks'), dict):
            return data
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {'version': 1, 'tracks': {}}


def advance(track, observation, now):
    """Two matching observations separated by >=5 minutes, no repeated alerts."""
    if observation is None or observation == 'unknown':
        # An uncertain probe breaks a streak; it cannot confirm an incident.
        track.pop('seen', None)
        track['count'] = 0
        return None
    same = (track.get('seen') == observation and
            0 <= now - track.get('last_at', 0) <= MAX_GAP)
    if same:
        track['count'] = min(track.get('count', 0) + 1, 100)
        track['first_at'] = track.get('first_at', now)
    else:
        track.update(seen=observation, count=1, first_at=now)
    track['last_at'] = now
    if track['count'] >= 2 and now - track['first_at'] >= MIN_CONFIRM:
        previous = track.get('stable', 'good')
        if previous != observation:
            track['stable'] = observation
            return 0 if observation == 'bad' else 1
    return None


def send(token, chat, message):
    payload = json.dumps({'chat_id': chat, 'text': message, 'disable_web_page_preview': True},
                         ensure_ascii=False).encode()
    req = Request('https://api.telegram.org/bot' + token + '/sendMessage', data=payload,
                  headers={'Content-Type': 'application/json', 'User-Agent': USER_AGENT}, method='POST')
    with HTTP.open(req, timeout=12) as res:
        result = json.loads(res.read(4096))
    if not result.get('ok'):
        raise ValueError('Telegram did not confirm delivery')


def check(now=None, observed=None, notify=send):
    now = int(now if now is not None else datetime.now(timezone.utc).timestamp())
    token = os.environ.get('SIDJ_TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.environ.get('SIDJ_TELEGRAM_CHAT_ID', '').strip()
    analytics_token = os.environ.get('CLOUDFLARE_ANALYTICS_TOKEN', '').strip()
    if not token or not chat.isdecimal():
        raise RuntimeError('Секреты Telegram отсутствуют; мониторинг не запускался.')
    bot, check_status, analytics = observed if observed is not None else probe(token, analytics_token)
    observations = {'bot': bot, 'check': check_status, 'analytics': analytics}
    state = load()
    messages = []
    for key, value in observations.items():
        track = state['tracks'].setdefault(key, {})
        changed = advance(track, value, now)
        if changed is not None:
            messages.append(MESSAGES[key][changed])
    # Commit state only after Telegram confirms delivery. A failed send can
    # be retried on the next run; a lost response may rarely duplicate a notice.
    msk = datetime.fromtimestamp(now, MSK).strftime('%d.%m.%Y %H:%M МСК')
    for message in messages:
        try:
            notify(token, chat, '🤖 B/S tech | Мониторинг\n' + message + '\n🕒 ' + msk)
        except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError, OSError) as exc:
            raise RuntimeError('Не удалось доставить уведомление о состоянии. Проверь журнал GitHub Actions.') from None
    STATE.write_text(json.dumps(state, separators=(',', ':')), encoding='utf-8')
    # Fixed, nonsensitive diagnostic only (no response bodies or URLs with tokens).
    print(f'Проверено {msk}: bot={bot}; check={check_status}; analytics={analytics or "not-configured"}; notifications={len(messages)}')


if __name__ == '__main__':
    try:
        check()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
