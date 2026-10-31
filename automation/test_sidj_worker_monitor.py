"""Network-free checks for the separate health monitor and alert deduplication."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import sidj_worker_monitor as mon


class MonitorTests(unittest.TestCase):
    def test_confirmed_outage_one_alert_then_one_recovery(self):
        track = {}
        self.assertIsNone(mon.advance(track, 'bad', 1000))
        self.assertEqual(mon.advance(track, 'bad', 1300), 0)
        self.assertIsNone(mon.advance(track, 'bad', 1600))
        self.assertIsNone(mon.advance(track, 'good', 1900))
        self.assertEqual(mon.advance(track, 'good', 2200), 1)
        self.assertIsNone(mon.advance(track, 'good', 2500))

    def test_delayed_actions_and_unknown_are_not_false_confirmations(self):
        track = {}
        self.assertIsNone(mon.advance(track, 'bad', 1000))
        self.assertIsNone(mon.advance(track, 'bad', 1000 + mon.MAX_GAP + 1))
        self.assertIsNone(mon.advance(track, 'unknown', 7000))
        self.assertIsNone(mon.advance(track, 'bad', 7100))
        self.assertEqual(mon.advance(track, 'bad', 7400), 0)

    def test_webhook_mismatch_is_bad_and_bad_telegram_credential_is_uncertain(self):
        with patch.object(mon, 'get', side_effect=[
                'B/S tech Worker доступен.'.encode('utf-8'), json.dumps({'ok': True, 'result': {
                    'url': 'https://different.example/telegram'}}).encode()]):
            self.assertEqual(mon.probe('123:fake'), ('bad', 'good', None))
        unauthorized = HTTPError('https://api.telegram.org/', 401, 'unauthorized', {}, None)
        with patch.object(mon, 'get', side_effect=['B/S tech Worker доступен.'.encode('utf-8'), unauthorized]):
            self.assertEqual(mon.probe('123:fake'), ('unknown', 'bad', None))

    def test_analytics_expired_does_not_mark_worker_down(self):
        with patch.object(mon, 'get', side_effect=[
            'B/S tech Worker доступен.'.encode('utf-8'),
            json.dumps({'ok': True, 'result': {'url': mon.BASE + 'telegram'}}).encode(),
            json.dumps({'success': True, 'result': {'status': 'expired'}}).encode(),
        ]):
            self.assertEqual(mon.probe('123:fake', 'analytics-secret'), ('good', 'good', 'bad'))

    def test_alerts_are_sent_only_to_owner_and_state_survives_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / 'state.json'
            alerts = []
            fake = lambda token, chat, msg: alerts.append((token, chat, msg))
            env = {'SIDJ_TELEGRAM_BOT_TOKEN': '12345:' + 'x' * 35,
                   'SIDJ_TELEGRAM_CHAT_ID': '42',
                   'CLOUDFLARE_ANALYTICS_TOKEN': 'analytics-secret'}
            with patch.dict(mon.os.environ, env), patch.object(mon, 'STATE', state_file):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    mon.check(now=1000, observed=('bad', 'good', 'bad'), notify=fake)
                    mon.check(now=1300, observed=('bad', 'good', 'bad'), notify=fake)
                    mon.check(now=1600, observed=('bad', 'good', 'bad'), notify=fake)
                    mon.check(now=1900, observed=('good', 'good', 'good'), notify=fake)
                    mon.check(now=2200, observed=('good', 'good', 'good'), notify=fake)
                self.assertEqual(len(alerts), 2)
                self.assertTrue(all(chat == '42' for _, chat, _ in alerts))
                self.assertIn('аналитики', alerts[0][2])
                self.assertIn('восстанов', alerts[1][2])
                self.assertNotIn(env['SIDJ_TELEGRAM_BOT_TOKEN'], output.getvalue())
                self.assertEqual(json.loads(state_file.read_text())['version'], 1)

    def test_monitor_fault_not_reported_as_bot_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            alerts = []
            with patch.dict(mon.os.environ, {
                'SIDJ_TELEGRAM_BOT_TOKEN': '12345:' + 'x' * 35,
                'SIDJ_TELEGRAM_CHAT_ID': '42'}, clear=True), patch.object(mon, 'STATE', Path(temp) / 'state.json'):
                mon.check(now=1000, observed=('unknown', 'bad', None), notify=lambda *args: alerts.append(args))
                mon.check(now=1300, observed=('unknown', 'bad', None), notify=lambda *args: alerts.append(args))
            self.assertEqual(len(alerts), 1)
            self.assertIn('проверка', alerts[0][2])
            self.assertNotIn('подтверждён сбой Worker', alerts[0][2])


if __name__ == '__main__':
    unittest.main()
