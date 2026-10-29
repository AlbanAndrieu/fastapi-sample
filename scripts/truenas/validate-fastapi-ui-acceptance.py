#!/usr/bin/env python3
"""Read-only FastAPI UI acceptance runner for a reviewed checkout.

Offline by default. Runtime is opt-in, targets and programs are fixed, and
child stdout/stderr are never forwarded. This script never deploys, writes
secrets, installs packages, or changes firewall/container configuration.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = Path('/mnt/cpool/compose/nabla-compose')
SHA = re.compile(r'^[0-9a-f]{40}$')
LOG = re.compile(r'^/tmp/tmp\.[A-Za-z0-9]{6,64}$')
ATOM = re.compile(r'^[a-zA-Z0-9_./-]{1,96}$')
STATE = {'PASS', 'FAIL', 'DENIED', 'UNVERIFIED', 'NOT_RUN'}


def safe_atom(value: object, fallback: str = 'unknown') -> str:
    return value if isinstance(value, str) and ATOM.fullmatch(value) else fallback


def execute(argv: list[str], *, timeout: int = 45, json_report: bool = False) -> tuple[int | None, dict[str, Any]]:
    """Run a pinned command; never display stdout, stderr, paths or credentials."""
    try:
        result = subprocess.run(
            argv, cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if json_report else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return None, {'state': 'dependency_missing'}
    except subprocess.TimeoutExpired:
        return None, {'state': 'deadline_exceeded'}
    except OSError:
        return None, {'state': 'execution_unavailable'}
    if not json_report:
        return result.returncode, {}
    # Ignore verbose progress text; consider only the final bounded JSON line.
    output = (result.stdout or b'')[-16384:]
    for line in reversed(output.splitlines()):
        if len(line) > 8192:
            continue
        try:
            report = json.loads(line)
            if isinstance(report, dict):
                return result.returncode, report
        except (ValueError, UnicodeError):
            continue
    return result.returncode, {'state': 'report_unavailable'}


def item(name: str, verdict: str, code: str, **extra: object) -> dict[str, object]:
    assert verdict in STATE
    return {'name': name, 'verdict': verdict, 'code': safe_atom(code), **extra}


def source_sha() -> str | None:
    # Only a strict 40-hex revision is included; never expose Git errors.
    try:
        completed = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        value = completed.stdout.decode('ascii', errors='ignore').strip()
        return value if completed.returncode == 0 and SHA.fullmatch(value) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def local_checks() -> list[dict[str, object]]:
    cases = [
        ('node_ui_contracts', ['node', '--test',
          'tests/js/api-public-fast-start.test.mjs',
          'tests/js/api-chromium-preflight-runner.test.mjs'], 45),
        ('python_ui_contracts', [sys.executable, '-m', 'pytest', '-q',
          'tests/unit/test_api_ui_assets.py',
          'tests/unit/test_cloud_browser_diagnostic_contract.py'], 90),
        ('acceptance_selftests', [sys.executable, '-m', 'unittest', 'discover',
          '-s', 'tests', '-p', 'test_fastapi_ui_acceptance.py', '-q'], 15),
    ]
    results = []
    for name, argv, timeout in cases:
        if name == 'acceptance_selftests' and not (ROOT / 'tests/test_fastapi_ui_acceptance.py').is_file():
            results.append(item(name, 'NOT_RUN', 'test_module_missing'))
            continue
        code, report = execute(argv, timeout=timeout)
        if code is None:
            results.append(item(name, 'NOT_RUN', safe_atom(report.get('state'))))
        else:
            results.append(item(name, 'PASS' if code == 0 else 'FAIL',
                                'tests_passed' if code == 0 else 'tests_failed'))
    return results


def runtime_checks(targets: list[str], *, compose: Path, build_log: str | None,
                   expected_sha: str | None, browser: bool, extended: bool) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    if build_log:
        script = compose / 'scripts/truenas/classify-fastapi-build-failure.py'
        if not LOG.fullmatch(build_log):
            results.append(item('historical_build', 'NOT_RUN', 'invalid_private_log_path'))
        elif not script.is_file():
            results.append(item('historical_build', 'NOT_RUN', 'classifier_missing'))
        else:
            _, payload = execute([sys.executable, str(script), '--check',
                 '--failure-shape', '--log', build_log], timeout=12, json_report=True)
            results.append(item('historical_build', 'UNVERIFIED',
                                safe_atom(payload.get('state')), next_check=safe_atom(payload.get('next_check'))))
    for target in targets:
        code, report = execute([sys.executable, str(ROOT / 'scripts/diagnose-api-ui-transport.py'),
               '--target', target], timeout=20, json_report=True)
        requests = report.get('requests') if isinstance(report.get('requests'), list) else []
        statuses = {x.get('path'): x.get('state') for x in requests if isinstance(x, dict)
                    and x.get('path') in ('/api', '/api/ui/session', '/api/ui/services')}
        values = tuple(statuses.get(p) for p in ('/api', '/api/ui/session', '/api/ui/services'))
        if code is None or len(statuses) != 3:
            verdict, state = 'UNVERIFIED', 'transport_unverified'
        elif values == ('http_200', 'http_200', 'http_200'):
            verdict, state = 'PASS', 'three_http_200'
        elif any(value in ('http_401', 'http_403') for value in values):
            verdict, state = 'DENIED', 'access_policy_or_auth'
        else:
            verdict, state = 'UNVERIFIED', 'http_or_network_degraded'
        results.append(item(f'http_{target}', verdict, state,
                            api=safe_atom(statuses.get('/api')),
                            session=safe_atom(statuses.get('/api/ui/session')),
                            services=safe_atom(statuses.get('/api/ui/services'))))
    if 'truenas' in targets:
        code, report = execute([sys.executable,
            str(ROOT / 'scripts/truenas/diagnose-fastapi-metrics-auth.py'), '--check'],
            timeout=15, json_report=True)
        state = safe_atom(report.get('state'))
        verdict = ('PASS' if state == 'scrape_auth_accepted'
                   else 'FAIL' if state in ('unexpected_anonymous_metrics_access', 'scrape_credential_rejected')
                   else 'UNVERIFIED')
        results.append(item('metrics_auth', verdict, state,
                            anonymous_http=report.get('anonymous_http') if isinstance(report.get('anonymous_http'), int) else None))
    if extended:
        script = compose / 'scripts/truenas/diagnose-fastapi-sample.sh'
        if not script.is_file():
            results.append(item('compose_acceptance', 'NOT_RUN', 'compose_diagnostic_missing'))
        else:
            argv = ['bash', str(script), '--cycles', '1', '--color', 'never', '--icons', 'never']
            if expected_sha:
                argv += ['--expected-sha', expected_sha]
            code, report = execute(argv, timeout=155)
            results.append(item('compose_acceptance',
                                'NOT_RUN' if code is None else 'PASS' if code == 0 else 'UNVERIFIED',
                                safe_atom(report.get('state')) if code is None else 'script_exit_0' if code == 0 else 'script_nonzero'))
    if browser and 'truenas' not in targets:
        results.append(item('chromium_preflight', 'NOT_RUN', 'truenas_target_required'))
    if browser and 'truenas' in targets:
        runner = ROOT / 'scripts/diagnose-production-api-ui-freeze.mjs'
        command = ['node', str(runner), 'truenas', '--preflight']
        code, report = execute(command, timeout=12, json_report=True)
        preflight = safe_atom(report.get('state'))
        ok = code == 0 and preflight == 'browser_binary_ready'
        results.append(item('chromium_preflight', 'PASS' if ok else 'NOT_RUN', preflight))
        if ok:
            scenarios = [('public', []), ('safe', ['--safe']),
                         ('operator', ['--operator']), ('rich_owner', ['--full', '--operator'])]
            for label, flags in scenarios:
                code, report = execute(['node', str(runner), 'truenas', '--native', *flags],
                                       timeout=39, json_report=True)
                state = safe_atom(report.get('state'))
                sampled = code == 0 and state == 'sampled'
                if not sampled:
                    verdict = 'FAIL' if state == 'main_thread_unresponsive' else 'UNVERIFIED'
                    results.append(item('chromium_' + label, verdict, state))
                    continue
                rich = report.get('richAssetLoaded') is True
                owner_visible = report.get('ownerUnlockVisible') is True
                expected_rich = label == 'rich_owner'
                expected_owner = label in ('operator', 'rich_owner')
                passed = rich == expected_rich and owner_visible == expected_owner
                results.append(item('chromium_' + label, 'PASS' if passed else 'FAIL',
                                    'ui_contract_ok' if passed else 'ui_contract_mismatch',
                                    public_rows=report.get('publicRows') if isinstance(report.get('publicRows'), int) else None,
                                    detailed_rows=report.get('detailedRows') if isinstance(report.get('detailedRows'), int) else None))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('offline', 'runtime', 'all'), default='offline')
    parser.add_argument('--target', action='append', choices=('truenas', 'staging'), dest='targets')
    parser.add_argument('--build-log', help='Optional historical private /tmp/tmp.* Docker build evidence')
    parser.add_argument('--expected-sha', help='Exact immutable commit to compare in Compose diagnostic')
    parser.add_argument('--compose-root', type=Path, default=COMPOSE)
    parser.add_argument('--browser', action='store_true', help='Opt-in native Playwright; no dependency installation')
    parser.add_argument('--extended', action='store_true', help='Opt-in read-only Compose 1-cycle acceptance')
    args = parser.parse_args(argv)
    if args.expected_sha and not SHA.fullmatch(args.expected_sha):
        parser.error('--expected-sha requires an exact 40-hex SHA')
    if (args.browser or args.extended or args.build_log or args.targets) and args.phase == 'offline':
        parser.error('runtime options require --phase runtime or --phase all')
    targets = list(dict.fromkeys(args.targets or ['truenas']))
    checks: list[dict[str, object]] = []
    if args.phase in ('offline', 'all'):
        checks.extend(local_checks())
    if args.phase in ('runtime', 'all'):
        checks.extend(runtime_checks(targets, compose=args.compose_root, build_log=args.build_log,
                                     expected_sha=args.expected_sha, browser=args.browser,
                                     extended=args.extended))
    failed = any(row['verdict'] == 'FAIL' for row in checks)
    pending = any(row['verdict'] in ('NOT_RUN', 'UNVERIFIED', 'DENIED') for row in checks)
    output = {'schema': 'fastapi-ui-acceptance/v1', 'phase': args.phase,
              'code_sha': source_sha(), 'checks': checks,
              'decision': 'BLOCKED' if failed else 'INCOMPLETE' if pending else 'PRECHECK_PASS_MANUAL_OWNER_REQUIRED',
              'manual_owner_browser_acceptance': 'NOT_RUN'}
    print(json.dumps(output, sort_keys=True))
    return 1 if failed else 2 if pending else 0


if __name__ == '__main__':
    raise SystemExit(main())
