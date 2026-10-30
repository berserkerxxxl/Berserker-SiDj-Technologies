#!/usr/bin/env python3
"""Read-only Cloudflare Workers analytics. Never print credentials or account IDs."""
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
from zoneinfo import ZoneInfo

from sidj_cloudflare import request

ENDPOINT = 'https://api.cloudflare.com/client/v4/graphql'
WORKER = 'bs-tech-sidj'
FREE_DAILY_REQUESTS = 100_000
CUTOVER = datetime(2026, 10, 30, 19, 6, 49, tzinfo=timezone.utc)
QUERY = '''query SiDjMetrics($accountTag: string, $dayStart: string,
                            $liveStart: string, $end: string, $scriptName: string) {
  viewer { accounts(filter: {accountTag: $accountTag}) {
    accountToday: workersInvocationsAdaptive(limit: 1, filter: {
      datetime_geq: $dayStart, datetime_leq: $end
    }) { sum { requests } }
    workerToday: workersInvocationsAdaptive(limit: 1, filter: {
      scriptName: $scriptName, datetime_geq: $dayStart, datetime_leq: $end
    }) { sum { requests errors subrequests }
         quantiles { __typename cpuTimeP50 cpuTimeP99 } }
    workerLive: workersInvocationsAdaptive(limit: 1, filter: {
      scriptName: $scriptName, datetime_geq: $liveStart, datetime_leq: $end
    }) { sum { requests errors subrequests }
         quantiles { __typename cpuTimeP50 cpuTimeP99 } }
    outcomes: workersInvocationsAdaptive(limit: 30, filter: {
      scriptName: $scriptName, datetime_geq: $liveStart, datetime_leq: $end
    }) { dimensions { status } sum { requests errors } }
  } }
}'''


def settings(environ):
    names = ('CLOUDFLARE_ANALYTICS_TOKEN', 'CLOUDFLARE_ACCOUNT_ID')
    values = {name: environ.get(name, '').strip() for name in names}
    for name, value in values.items():
        if not value:
            raise RuntimeError('Не настроен GitHub Actions Secret: ' + name)
    token = values['CLOUDFLARE_ANALYTICS_TOKEN']
    if not 20 <= len(token) <= 2048 or re.search(r'\s', token):
        raise RuntimeError('Некорректный формат CLOUDFLARE_ANALYTICS_TOKEN')
    if not re.fullmatch(r'[a-fA-F0-9]{32}', values['CLOUDFLARE_ACCOUNT_ID']):
        raise RuntimeError('Некорректный CLOUDFLARE_ACCOUNT_ID')
    return values


def graphql(query, variables, values):
    if not query.lstrip().startswith('query '):
        raise RuntimeError('Разрешены только запросы чтения GraphQL.')
    raw = request(ENDPOINT, headers={
        'Authorization': 'Bearer ' + values['CLOUDFLARE_ANALYTICS_TOKEN']},
        payload={'query': query, 'variables': variables})
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError('Cloudflare вернул некорректную аналитику.') from None
    if not isinstance(body, dict) or body.get('errors') or not isinstance(body.get('data'), dict):
        # Messages can echo GraphQL variables. Classify errors without logging
        # response text, account IDs, the query's variables, or any credential.
        errors = (body.get('errors') or []) if isinstance(body, dict) else []
        if not isinstance(errors, list):
            errors = []
        messages = ' '.join(str(item.get('message', '')) for item in errors if isinstance(item, dict)).lower()
        if any(word in messages for word in ('authoriz', 'permission', 'authentication')):
            raise RuntimeError('Нет доступа к аналитике: проверь Account / Account Analytics / Read и выбранный аккаунт.')
        raise RuntimeError('Cloudflare отклонил запрос аналитики; сырые сообщения скрыты.')
    return body['data']


def aggregate(rows):
    if not isinstance(rows, list) or len(rows) > 1:
        # Never average or combine percentiles from independently grouped rows.
        raise RuntimeError('Неожиданная группировка аналитики; процентили не объединяются.')
    return rows[0] if rows else None


def numeric(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise RuntimeError('Некорректное числовое значение аналитики.')
    return value


def cpu_scale(description):
    value = description.lower()
    if 'nanosecond' in value:
        return 0.000001
    if 'microsecond' in value or 'µs' in value or 'μs' in value:
        return 0.001
    if 'millisecond' in value:
        return 1
    return None


def summarize(row, scale):
    if row is None:
        return {'available': False}
    result = {'available': True}
    result.update({key: numeric(row['sum'][key]) for key in ('requests', 'errors', 'subrequests')})
    cpu = {key: numeric(row['quantiles'][key]) for key in ('cpuTimeP50', 'cpuTimeP99')}
    result['cpu_ms' if scale is not None else 'cpu_raw_unit_unconfirmed'] = {
        key: round(number * scale, 6) if scale is not None else number for key, number in cpu.items()}
    return result


def collect(values, now=None):
    end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    day = end.replace(hour=0, minute=0, second=0)
    live = max(end - timedelta(hours=1), CUTOVER)
    if live >= end:
        raise RuntimeError('Окно после переключения ещё не доступно.')
    iso = lambda value: value.isoformat().replace('+00:00', 'Z')
    data = graphql(QUERY, {'accountTag': values['CLOUDFLARE_ACCOUNT_ID'],
        'scriptName': WORKER, 'dayStart': iso(day), 'liveStart': iso(live), 'end': iso(end)}, values)
    accounts = data.get('viewer', {}).get('accounts', [])
    if len(accounts) != 1:
        raise RuntimeError('Выбранный аккаунт недоступен для аналитики.')
    account = accounts[0]
    today, recent = aggregate(account['workerToday']), aggregate(account['workerLive'])
    usage = aggregate(account['accountToday'])
    count = numeric(usage['sum']['requests']) if usage else 0
    metadata = ''
    sample = recent or today
    type_name = sample.get('quantiles', {}).get('__typename', '') if sample else ''
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', type_name):
        try:
            schema = graphql('query CpuUnits($typeName: String!) { __type(name: $typeName) { description fields { name description } } }',
                             {'typeName': type_name}, values).get('__type') or {}
            metadata = ' '.join([schema.get('description') or '', *[
                field.get('description') or '' for field in schema.get('fields', [])
                if field['name'] in ('cpuTimeP50', 'cpuTimeP99')]])
        except RuntimeError:
            pass  # Counts remain useful; unknown CPU units must stay explicit.
    scale = cpu_scale(metadata)
    outcomes = []
    for row in account['outcomes']:
        status = row.get('dimensions', {}).get('status', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', status):
            raise RuntimeError('Неизвестный формат статуса исполнения.')
        outcomes.append({'status': status, 'requests': numeric(row['sum']['requests']),
                         'errors': numeric(row['sum']['errors'])})
    msk = lambda value: value.astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M:%S МСК')
    return {'worker': WORKER, 'checked_at_msk': msk(end),
        'day_start_msk': msk(day), 'recent_start_msk': msk(live),
        'account_requests_today_estimate': count,
        'free_daily_limit': FREE_DAILY_REQUESTS,
        'free_daily_limit_used_percent_estimate': round(count / FREE_DAILY_REQUESTS * 100, 6),
        'quota_resets_at_msk': msk(day + timedelta(days=1)),
        'worker_today': summarize(today, scale), 'worker_recent': summarize(recent, scale),
        'recent_invocation_statuses': outcomes,
        'cpu_unit_schema_description': metadata[:1200],
        'notes': ['Analytics may be sampled and delayed.',
                  'errors counts runtime failures, not all HTTP error responses.',
                  'P99 is a percentile, not the maximum CPU time.',
                  'The Free plan was confirmed by the owner; this query does not read billing or change a plan.']}


def main():
    try:
        print(json.dumps(collect(settings(os.environ)), ensure_ascii=False, indent=2))
    except RuntimeError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
