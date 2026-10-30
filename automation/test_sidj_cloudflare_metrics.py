from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

import sidj_cloudflare_metrics as metrics


VALUES = {'CLOUDFLARE_ANALYTICS_TOKEN': 'test-only-' + 'q' * 40,
          'CLOUDFLARE_ACCOUNT_ID': 'a' * 32}


class MetricsTests(unittest.TestCase):
    def test_missing_or_invalid_credentials_never_echo_values(self):
        for values in ({}, {**VALUES, 'CLOUDFLARE_ANALYTICS_TOKEN': 'secret\ninvalid'},
                       {**VALUES, 'CLOUDFLARE_ACCOUNT_ID': 'wrong-account'}):
            with patch.object(metrics, 'request') as request:
                with self.assertRaises(RuntimeError) as caught:
                    metrics.settings(values)
                request.assert_not_called()
            for value in values.values():
                self.assertNotIn(value, str(caught.exception))

    def test_only_read_queries_and_no_raw_error_response(self):
        payload = {'errors': [{'message': 'Not authorized ' + VALUES['CLOUDFLARE_ANALYTICS_TOKEN'] + VALUES['CLOUDFLARE_ACCOUNT_ID']}], 'data': None}
        with patch.object(metrics, 'request', return_value=json.dumps(payload)) as request:
            with self.assertRaises(RuntimeError) as caught:
                metrics.graphql('query Test { viewer { __typename } }', {}, VALUES)
        for value in VALUES.values():
            self.assertNotIn(value, str(caught.exception))
        self.assertEqual(request.call_args.args[0], metrics.ENDPOINT)
        with patch.object(metrics, 'request') as request:
            with self.assertRaises(RuntimeError):
                metrics.graphql('mutation Unsafe { anything }', {}, VALUES)
            request.assert_not_called()

    def test_units_quota_timezone_and_aggregate_percentiles(self):
        row = {'sum': {'requests': 70, 'errors': 0, 'subrequests': 96},
               'quantiles': {'__typename': 'CpuQuantiles', 'cpuTimeP50': 240, 'cpuTimeP99': 900}}
        account = {'accountToday': [{'sum': {'requests': 137}}], 'workerToday': [row],
                   'workerLive': [row], 'outcomes': [{'dimensions': {'status': 'success'},
                                                     'sum': {'requests': 70, 'errors': 0}}]}
        data = {'viewer': {'accounts': [account]}}
        schema = {'__type': {'fields': [{'name': 'cpuTimeP50', 'description': 'CPU time in microseconds'}]}}
        with patch.object(metrics, 'graphql', side_effect=[data, schema]):
            report = metrics.collect(VALUES, datetime(2026, 10, 30, 19, 40, tzinfo=timezone.utc))
        self.assertEqual(report['worker_recent']['cpu_ms']['cpuTimeP99'], 0.9)
        self.assertEqual(report['free_daily_limit_used_percent_estimate'], 0.137)
        self.assertEqual(report['quota_resets_at_msk'], '31.10.2026 03:00:00 МСК')
        self.assertEqual(report['recent_start_msk'], '30.10.2026 22:06:49 МСК')
        self.assertNotIn(VALUES['CLOUDFLARE_ACCOUNT_ID'], json.dumps(report))
        with self.assertRaises(RuntimeError):
            metrics.aggregate([row, row])

    def test_missing_data_and_unconfirmed_units_are_not_reported_as_zero_cpu(self):
        self.assertEqual(metrics.summarize(None, None), {'available': False})
        self.assertIsNone(metrics.cpu_scale('CPU time percentile'))
        self.assertEqual(metrics.cpu_scale('CPU time in nanoseconds'), 0.000001)
        row = {'sum': {'requests': 2, 'errors': 0, 'subrequests': 1},
               'quantiles': {'cpuTimeP50': 600, 'cpuTimeP99': 900}}
        self.assertIn('cpu_raw_unit_unconfirmed', metrics.summarize(row, None))
        self.assertNotIn('cpu_ms', metrics.summarize(row, None))


if __name__ == '__main__':
    unittest.main()
