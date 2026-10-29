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

    def test_browser_skipped_for_staging_without_false_success(self):
        with patch.object(runner, 'execute', return_value=(0, {'requests': []})):
            checks = runner.runtime_checks(['staging'], compose=Path('/nonexistent'),
                build_log=None, expected_sha=None, browser=True, extended=False)
        self.assertEqual(checks[-1]['code'], 'truenas_target_required')
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


if __name__ == '__main__':
    unittest.main()
