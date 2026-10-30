"""Offline no-secret contract tests for the consolidated acceptance runner."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

RUNNER = Path(__file__).resolve().parents[1] / 'scripts/truenas/validate-fastapi-ui-acceptance.py'
spec = importlib.util.spec_from_file_location('fastapi_ui_acceptance', RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class AcceptanceTests(unittest.TestCase):
    def test_local_checks_never_expose_child_output(self):
        code, data = runner.execute([sys.executable, '-c',
            "import sys; print('PRIVATE_MARKER');print('SECRET',file=sys.stderr)"],
            json_report=False)
        self.assertEqual(code, 0)
        self.assertEqual(data, {})

    def test_json_is_fixed_and_only_final_line_used(self):
        code, data = runner.execute([sys.executable, '-c',
            "print('private-before');print('{\"state\":\"browser_binary_ready\"}')"],
            json_report=True)
        self.assertEqual(code, 0)
        self.assertEqual(data['state'], 'browser_binary_ready')

    def test_fake_build_log_path_is_rejected_before_subprocess(self):
        with patch.object(runner, 'execute', side_effect=AssertionError('should not execute')):
            checks = runner.runtime_checks([], compose=Path('/nonexistent'),
                build_log='/tmp/../../secret', expected_sha=None, browser=False, extended=False)
        self.assertEqual(checks[0]['code'], 'invalid_private_log_path')
        self.assertEqual(checks[0]['verdict'], 'NOT_RUN')

    def test_failure_is_never_accepted(self):
        with patch.object(runner, 'local_checks', return_value=[runner.item('test', 'FAIL', 'tests_failed')]):
            with patch.object(runner, 'source_sha', return_value=None):
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = runner.main(['--phase', 'offline'])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(output.getvalue())['decision'], 'BLOCKED')

    def test_runtime_transport_denied_not_declared_outage(self):
        payload = {'requests': [
            {'path': '/api', 'state': 'http_403'},
            {'path': '/api/ui/session', 'state': 'http_403'},
            {'path': '/api/ui/services', 'state': 'http_403'}]}
        with patch.object(runner, 'execute', return_value=(0, payload)):
            checks = runner.runtime_checks(['staging'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=False, extended=False)
        self.assertEqual(checks[0]['verdict'], 'DENIED')

    def test_runtime_transport_success(self):
        payload = {'requests': [
            {'path': p, 'state': 'http_200'} for p in
            ('/api', '/api/ui/session', '/api/ui/services')]}
        with patch.object(runner, 'execute', return_value=(0, payload)):
            checks = runner.runtime_checks(['staging'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=False, extended=False)
        self.assertEqual(checks[0]['verdict'], 'PASS')

    def test_browser_staging_missing_preflight_is_not_false_success(self):
        with patch.object(runner, 'execute', return_value=(2, {'state': 'playwright_python_missing'})):
            checks = runner.runtime_checks(['staging'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=True, extended=False)
        self.assertEqual(checks[-1]['code'], 'playwright_python_missing')
        self.assertEqual(checks[-1]['verdict'], 'NOT_RUN')

    def test_no_runtime_options_implicitly_enable_network(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                runner.main(['--phase', 'offline', '--browser'])
        self.assertEqual(ctx.exception.code, 2)

    def test_invalid_sha_rejected_without_execution(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                runner.main(['--phase', 'runtime', '--expected-sha', ';cat /etc/shadow'])
        self.assertEqual(ctx.exception.code, 2)

    def test_secret_or_path_never_embedded_in_code(self):
        self.assertEqual(runner.safe_atom('SECRET=private'), 'unknown')
        self.assertEqual(runner.safe_atom('http://x/private?token=abc'), 'unknown')
        self.assertEqual(runner.safe_atom('source_unverified'), 'source_unverified')


    def test_browser_modes_have_explicit_owner_and_rich_contracts(self):
        transport = {'requests': [
            {'path': p, 'state': 'http_200'} for p in
            ('/api', '/api/ui/session', '/api/ui/services')]}

        def fake_execute(argv, **kwargs):
            if '--preflight' in argv:
                return 0, {'state': 'browser_binary_ready'}
            if '--native' in argv:
                return 0, {'state': 'sampled',
                           'ownerUnlockVisible': '--operator' in argv,
                           'richAssetLoaded': '--full' in argv,
                           'publicRows': 10, 'detailedRows': 4}
            if '--target' in argv:
                return 0, transport
            return 2, {'state': 'key_configured_scraper_credentials_unverified'}

        with patch.object(runner, 'execute', side_effect=fake_execute):
            checks = runner.runtime_checks(['truenas'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=True, extended=False)
        browser = [row for row in checks if row['name'].startswith('chromium_')]
        self.assertEqual(len(browser), 5)
        self.assertTrue(all(row['verdict'] == 'PASS' for row in browser))
        self.assertEqual(next(row for row in checks if row['name'] == 'metrics_auth')['verdict'],
                         'UNVERIFIED')

    def test_owner_button_missing_is_failure_not_false_pass(self):
        transport = {'requests': [
            {'path': p, 'state': 'http_200'} for p in
            ('/api', '/api/ui/session', '/api/ui/services')]}

        def fake_execute(argv, **kwargs):
            if '--preflight' in argv:
                return 0, {'state': 'browser_binary_ready'}
            if '--native' in argv:
                return 0, {'state': 'sampled',
                           'ownerUnlockVisible': False,
                           'richAssetLoaded': '--full' in argv}
            if '--target' in argv:
                return 0, transport
            return 2, {'state': 'key_configured_scraper_credentials_unverified'}

        with patch.object(runner, 'execute', side_effect=fake_execute):
            checks = runner.runtime_checks(['truenas'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=True, extended=False)
        self.assertEqual(
            next(row for row in checks if row['name'] == 'chromium_operator')['verdict'],
            'FAIL')

    def test_browser_main_thread_block_is_failure(self):
        transport = {'requests': [
            {'path': p, 'state': 'http_200'} for p in
            ('/api', '/api/ui/session', '/api/ui/services')]}

        def fake_execute(argv, **kwargs):
            if '--preflight' in argv:
                return 0, {'state': 'browser_binary_ready'}
            if '--native' in argv:
                return 1, {'state': 'main_thread_unresponsive'}
            if '--target' in argv:
                return 0, transport
            return 2, {'state': 'key_configured_scraper_credentials_unverified'}

        with patch.object(runner, 'execute', side_effect=fake_execute):
            checks = runner.runtime_checks(['truenas'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=True, extended=False)
        self.assertEqual(
            next(row for row in checks if row['name'] == 'chromium_rich_owner')['verdict'],
            'FAIL')



    def test_browser_cloud_denied_vs_loading_state(self):
        transport = {'requests': [{'path': p, 'state': 'http_403'} for p in
                     ('/api', '/api/ui/session', '/api/ui/services')]}
        for state, expected in [('ui_loading_without_content', 'FAIL'),
                                ('http_access_restricted', 'DENIED')]:
            def fake_execute(argv, **kwargs):
                if '--preflight' in argv:
                    return 0, {'state': 'browser_binary_ready'}
                if '--native' in argv:
                    self.assertIn('cloud', argv)
                    return 1, {'state': state}
                return 0, transport
            with self.subTest(state=state):
                with patch.object(runner, 'execute', side_effect=fake_execute):
                    checks = runner.runtime_checks(['cloud'], compose=Path('/nonexistent'),
                        build_log=None, expected_sha=None, browser=True, extended=False)
                self.assertEqual(
                    next(c for c in checks if c['name'] == 'chromium_rich_owner')['verdict'],
                    expected)


if __name__ == '__main__':
    unittest.main()
