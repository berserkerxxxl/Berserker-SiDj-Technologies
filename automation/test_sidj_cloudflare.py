import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from urllib.request import Request

spec = importlib.util.spec_from_file_location('sidj_cloudflare', Path(__file__).with_name('sidj_cloudflare.py'))
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def configuration():
    return dict(CLOUDFLARE_API_TOKEN='c' * 40, CLOUDFLARE_ACCOUNT_ID='a' * 32,
                SIDJ_TELEGRAM_BOT_TOKEN='12345:' + 'x' * 35, SIDJ_TELEGRAM_CHAT_ID='42',
                SIDJ_ADMIN_TOKEN='k' * 48, SIDJ_FREE_PLAN_CONFIRMED='yes')


class CloudflareOperationsTests(unittest.TestCase):
    def test_missing_secrets_and_unconfirmed_plan_fail_without_network(self):
        for key in configuration():
            if key == 'SIDJ_ADMIN_TOKEN':
                continue
            env = configuration(); env.pop(key)
            with patch.object(ops.HTTP, 'open') as network:
                with self.assertRaises(RuntimeError):
                    ops.settings(env)
                network.assert_not_called()

    def test_default_admin_key_is_stable_and_separate_from_webhook_credentials(self):
        env = configuration(); env.pop('SIDJ_ADMIN_TOKEN')
        first = ops.settings(env)['SIDJ_ADMIN_TOKEN']
        self.assertRegex(first, r'^[a-f0-9]{64}$')
        self.assertEqual(first, ops.settings(env)['SIDJ_ADMIN_TOKEN'])
        webhook = ops.hashlib.sha256(('B/S-SiDj-webhook:' + env['SIDJ_TELEGRAM_BOT_TOKEN']).encode()).hexdigest()
        self.assertNotEqual(first, webhook)
        env['SIDJ_TELEGRAM_BOT_TOKEN'] = '12345:' + 'y' * 35
        self.assertNotEqual(first, ops.settings(env)['SIDJ_ADMIN_TOKEN'])
        self.assertEqual(ops.settings(configuration())['SIDJ_ADMIN_TOKEN'], configuration()['SIDJ_ADMIN_TOKEN'])

    def test_invalid_values_do_not_echo_credentials(self):
        for key, value in [('CLOUDFLARE_API_TOKEN', 'line\nbreak'), ('CLOUDFLARE_ACCOUNT_ID', 'wrong'),
                           ('SIDJ_ADMIN_TOKEN', 'short'), ('SIDJ_TELEGRAM_CHAT_ID', '-1')]:
            env = configuration(); env[key] = value
            with self.assertRaises(RuntimeError) as caught:
                ops.settings(env)
            self.assertNotIn(value, str(caught.exception))

    def test_url_is_derived_only_from_valid_account_subdomain(self):
        values = ops.settings(configuration())
        with patch.object(ops, 'request', return_value=json.dumps({'success': True, 'result': {'subdomain': 'example'}})):
            self.assertEqual(ops.public_url(values), 'https://bs-tech-sidj.example.workers.dev/')
        for name in ('evil.example/path', None, '', 'https://evil.example'):
            with patch.object(ops, 'request', return_value=json.dumps({'success': True, 'result': {'subdomain': name}})):
                with self.assertRaises(RuntimeError):
                    ops.public_url(values)

    def test_redirects_never_forward_authorization(self):
        req = Request('https://api.cloudflare.com/', headers={'Authorization': 'Bearer secret'})
        with self.assertRaises(HTTPError):
            ops.NoRedirect().redirect_request(req, None, 302, 'Found', {}, 'https://evil.example')

    def test_http_errors_are_redacted_and_negative_auth_probe_is_expected(self):
        error = HTTPError('https://worker.example/' + 'private', 403, configuration()['SIDJ_ADMIN_TOKEN'], {}, None)
        with patch.object(ops.HTTP, 'open', side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                ops.request('https://worker.example/')
            self.assertNotIn(configuration()['SIDJ_ADMIN_TOKEN'], str(caught.exception))
            self.assertEqual(ops.request('https://worker.example/', expected_status=403), '')

    def test_secret_bulk_uses_stdin_and_failure_output_is_not_printed(self):
        values = ops.settings(configuration())
        output = io.StringIO()
        with patch.object(ops.subprocess, 'run', return_value=Mock(returncode=1, stdout=values['SIDJ_ADMIN_TOKEN'])) as run:
            with contextlib.redirect_stdout(output), self.assertRaises(RuntimeError):
                ops.wrangler(['secret', 'bulk'], values, json.dumps({'SIDJ_ADMIN_TOKEN': values['SIDJ_ADMIN_TOKEN']}))
        self.assertNotIn(values['SIDJ_ADMIN_TOKEN'], repr(run.call_args.args[0]))
        self.assertIn(values['SIDJ_ADMIN_TOKEN'], run.call_args.kwargs['input'])
        self.assertNotIn('SIDJ_ADMIN_TOKEN', run.call_args.kwargs['env'])
        self.assertEqual(output.getvalue(), '')

    def test_deploy_only_does_not_activate_webhook(self):
        values = ops.settings(configuration())
        with patch.object(ops, 'public_url', return_value='https://bs-tech-sidj.example.workers.dev/'):
            with patch.object(ops, 'wrangler') as wrangler, patch.object(ops, 'request') as request:
                with contextlib.redirect_stdout(io.StringIO()):
                    ops.operate('deploy', values)
        self.assertEqual(wrangler.call_args_list[0].args[0][0], 'deploy')
        secret_call = wrangler.call_args_list[1]
        self.assertEqual(secret_call.args[0][:2], ['secret', 'bulk'])
        self.assertEqual(json.loads(secret_call.args[2])['SIDJ_TELEGRAM_BOT_TOKEN'], values['SIDJ_TELEGRAM_BOT_TOKEN'])
        self.assertEqual(request.call_count, 1)
        self.assertNotIn('admin/activate', request.call_args.args[0])

    def test_activation_checks_unsigned_rejection_then_owner_before_switching(self):
        values = ops.settings(configuration())
        with patch.object(ops, 'public_url', return_value='https://bs-tech-sidj.example.workers.dev/'):
            with patch.object(ops, 'request', return_value='Webhook active ' + values['SIDJ_ADMIN_TOKEN']) as request:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    ops.operate('activate', values)
        paths = [call.args[0].split('.dev/')[-1] for call in request.call_args_list]
        self.assertEqual(paths, ['', 'telegram', 'admin/status', 'admin/activate'])
        self.assertEqual(request.call_args_list[1].kwargs['expected_status'], 403)
        self.assertNotIn(values['SIDJ_ADMIN_TOKEN'], output.getvalue())

    def test_failed_auth_probe_stops_activation(self):
        values = ops.settings(configuration())
        with patch.object(ops, 'public_url', return_value='https://bs-tech-sidj.example.workers.dev/'):
            with patch.object(ops, 'request', side_effect=['ready', RuntimeError('unexpected HTTP status')]) as request:
                with self.assertRaises(RuntimeError):
                    ops.operate('activate', values)
        self.assertEqual(request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
