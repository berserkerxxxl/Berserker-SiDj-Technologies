#!/usr/bin/env python3
"""Manual GitHub Actions operations for bs-tech-sidj. Never print credentials."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / 'cloudflare/sidj-worker'


def settings(environ):
    names = ('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'SIDJ_TELEGRAM_BOT_TOKEN',
             'SIDJ_TELEGRAM_CHAT_ID', 'SIDJ_ADMIN_TOKEN')
    values = {name: environ.get(name, '').strip() for name in names}
    for name, value in values.items():
        if not value:
            raise RuntimeError('Не настроен GitHub Actions Secret: ' + name)
    if not re.fullmatch(r'[a-fA-F0-9]{32}', values['CLOUDFLARE_ACCOUNT_ID']):
        raise RuntimeError('Некорректный CLOUDFLARE_ACCOUNT_ID')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', values['SIDJ_ADMIN_TOKEN']):
        raise RuntimeError('SIDJ_ADMIN_TOKEN: нужны 32–128 случайных символов A-Z a-z 0-9 _ -')
    if not re.fullmatch(r'\d{5,16}:[A-Za-z0-9_-]{20,}', values['SIDJ_TELEGRAM_BOT_TOKEN']):
        raise RuntimeError('Некорректный SIDJ_TELEGRAM_BOT_TOKEN')
    if not re.fullmatch(r'[1-9]\d{0,15}', values['SIDJ_TELEGRAM_CHAT_ID']):
        raise RuntimeError('Некорректный SIDJ_TELEGRAM_CHAT_ID')
    if environ.get('SIDJ_FREE_PLAN_CONFIRMED') != 'yes':
        raise RuntimeError('Сначала проверь Workers Free в Cloudflare и подтверди его в форме запуска.')
    return values


def request(url, *, headers=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    hdr = {'Content-Type': 'application/json', **(headers or {})}
    req = Request(url, headers=hdr, data=data, method='GET' if data is None else 'POST')
    try:
        with urlopen(req, timeout=30) as res:
            return res.read(256 * 1024).decode('utf-8')
    except HTTPError as exc:
        raise RuntimeError('Сервис отклонил операцию: HTTP ' + str(exc.code)) from None
    except (URLError, TimeoutError, UnicodeError):
        raise RuntimeError('Нет подтверждения операции. Проверь состояние перед повтором.') from None


def public_url(values):
    endpoint = ('https://api.cloudflare.com/client/v4/accounts/'
                + values['CLOUDFLARE_ACCOUNT_ID'] + '/workers/subdomain')
    try:
        result = json.loads(request(endpoint, headers={
            'Authorization': 'Bearer ' + values['CLOUDFLARE_API_TOKEN']}))
        subdomain = result.get('result', {}).get('subdomain', '')
    except (ValueError, AttributeError):
        raise RuntimeError('Cloudflare не вернул корректный workers.dev адрес.') from None
    if not result.get('success') or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', subdomain):
        raise RuntimeError('Сначала настрой поддомен workers.dev в своём Cloudflare аккаунте.')
    return 'https://bs-tech-sidj.' + subdomain + '.workers.dev/'


def wrangler(arguments, values, payload=None):
    child_env = {key: value for key, value in os.environ.items() if not key.startswith('SIDJ_')}
    child_env.update(CLOUDFLARE_API_TOKEN=values['CLOUDFLARE_API_TOKEN'],
                     CLOUDFLARE_ACCOUNT_ID=values['CLOUDFLARE_ACCOUNT_ID'],
                     WRANGLER_SEND_METRICS='false', WRANGLER_LOG='warn')
    cmd = [str(WORKER / 'node_modules/.bin/wrangler'), *arguments]
    try:
        result = subprocess.run(cmd, cwd=WORKER, env=child_env, input=payload,
                                text=True, capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Wrangler не подтвердил операцию. Проверь состояние перед повтором.') from None
    # Raw CLI output may contain API diagnostics. Do not forward it to logs.
    if result.returncode:
        raise RuntimeError('Wrangler не выполнил шаг ' + arguments[0] + '; проверь права токена и Workers Free.')


def operate(action, values):
    url = public_url(values)
    if action == 'deploy':
        wrangler(['deploy', '--var', 'SIDJ_PUBLIC_URL:' + url], values)
        print('Код Worker развёрнут; webhook пока не переключён.')
        secrets = {name: values[name] for name in
                   ('SIDJ_TELEGRAM_BOT_TOKEN', 'SIDJ_TELEGRAM_CHAT_ID', 'SIDJ_ADMIN_TOKEN')}
        wrangler(['secret', 'bulk', '--name', 'bs-tech-sidj'], values, json.dumps(secrets))
        print('Секреты Worker применены без вывода значений.')
        request(url)
    else:
        # The workflow shares a concurrency group with the old poller, so its
        # running job finishes before activation/rollback begins.
        request(url)
        text = request(url + 'admin/' + action, headers={
            'Authorization': 'Bearer ' + values['SIDJ_ADMIN_TOKEN']}, payload={'confirm': action})
        print(text)
    print('Worker: ' + url)
    if action == 'activate':
        print('Проверь реальные команды/кнопки/файлы; только потом отключай старый опрос.')
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('deploy', 'status', 'activate', 'rollback'))
    args = parser.parse_args()
    try:
        operate(args.operation, settings(os.environ))
    except RuntimeError as exc:
        # All messages above are fixed diagnostics; no URLs carrying credentials.
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    main()
