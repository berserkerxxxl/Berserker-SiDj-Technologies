#!/usr/bin/env python3
"""Owner-authorized integration checks; sends test responses to the owner only.

These authenticated test updates exercise the deployed Worker and Telegram API.
They do not replace genuine Telegram button clicks or inspection of received files.
"""
import argparse
import hashlib
import json
import os
import secrets
import time

import sidj_cloudflare as ops


COMMANDS = (
    '/start', '/help', '/projects', '/project reserve', '/download',
    '/download limits script', '/download reserve win',
    '/download reserve linux_x64', '/status', '/builds', '/errors',
)


def verify(values):
    url = ops.public_url(values)
    status = ops.request(url + 'admin/status', headers={
        'Authorization': 'Bearer ' + values['SIDJ_ADMIN_TOKEN']}, payload={'confirm': 'status'})
    # This route verifies the real bot identity and private owner chat first.
    if 'Webhook: подключён к этому Worker' not in status:
        raise RuntimeError('Проверка остановлена: webhook не подтверждён для этого Worker.')
    owner = int(values['SIDJ_TELEGRAM_CHAT_ID'])
    secret = hashlib.sha256(('B/S-SiDj-webhook:' + values['SIDJ_TELEGRAM_BOT_TOKEN']).encode()).hexdigest()
    for index, command in enumerate(COMMANDS):
        update = {'update_id': secrets.randbelow(2 ** 52), 'message': {
            'message_id': index + 1, 'date': int(time.time()),
            'from': {'id': owner, 'is_bot': False, 'first_name': 'SiDj integration test'},
            'chat': {'id': owner, 'type': 'private'}, 'text': command}}
        started = time.monotonic()
        result = ops.request(url + 'telegram', headers={
            'X-Telegram-Bot-Api-Secret-Token': secret}, payload=update)
        if result != 'OK':
            raise RuntimeError('Worker не подтвердил обработку тестовой команды.')
        print(json.dumps({'command': command, 'accepted': True,
                          'seconds': round(time.monotonic() - started, 3)}, ensure_ascii=False), flush=True)
        if index + 1 < len(COMMANDS):
            time.sleep(1.1)  # Stay below Telegram's per-chat message rate.
    print('Обработка тестовых команд подтверждена. Реальные кнопки и полученные файлы проверяет владелец.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send-test-messages', action='store_true', required=True,
                        help='Send the test responses/files to the configured owner chat')
    parser.parse_args()
    try:
        verify(ops.settings(os.environ))
    except RuntimeError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
