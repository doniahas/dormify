"""Audit Dormify's dependencies for known vulnerabilities.

    python scripts/ci/dependency_audit.py python [--fail-on {none,any}]
    python scripts/ci/dependency_audit.py npm [--fail-on {none,any,low,moderate,high,critical}]

`python` audits the backend runtime graph exactly as pinned in
backend/constraints.txt (the resolved closure of backend/requirements.txt),
without re-resolving it, so the audit covers the versions the backend image
installs - not the development tools. `npm` audits the committed
frontend/package-lock.json without installing anything or changing it.

Both scanners exit non-zero both when they find vulnerabilities and when they
fail to run, so success is judged by whether a complete report was produced:

    0  the audit ran; findings are reported but do not fail (advisory mode)
    1  the audit ran and found vulnerabilities at or above --fail-on
    2  the scanner could not run or did not produce a usable report

Advisory mode is the default: the audits report discovered vulnerabilities
without failing. Passing --fail-on turns findings into a blocking gate.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# This file lives in scripts/ci/, two levels below the repository root.
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
FRONTEND = ROOT / 'frontend'

SEVERITIES = ['low', 'moderate', 'high', 'critical']

OK, FINDINGS, SCANNER_ERROR = 0, 1, 2


class ScannerError(Exception):
    """The scanner could not run or did not produce a usable report."""


def in_github_actions():
    return os.environ.get('GITHUB_ACTIONS') == 'true'


def annotate(level, title, message):
    """Print a GitHub Actions annotation; plain text everywhere else."""
    if in_github_actions():
        print(f'::{level} title={title}::{message}')
    else:
        print(f'{level.upper()}: {title}: {message}')


def step_summary(markdown):
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(markdown + '\n')


def print_table(headers, rows):
    widths = [max(len(str(c)) for c in col) for col in zip(headers, *rows, strict=False)]
    line = '  '.join(f'{{:<{w}}}' for w in widths)
    print(line.format(*headers).rstrip())
    print(line.format(*('-' * w for w in widths)).rstrip())
    for row in rows:
        print(line.format(*row).rstrip())


def short_list(items, limit=3):
    """Keep table cells readable; the full list is in the scanner's own output."""
    text = ', '.join(items[:limit])
    return f'{text} +{len(items) - limit} more' if len(items) > limit else text


def failure_detail(proc):
    """Echo a failed scanner's output to the log; return its last meaningful lines."""
    output = '\n'.join(s for s in (proc.stderr.strip(), proc.stdout.strip()) if s)
    if output:
        print(output)
    # pip-audit always notes that --no-deps works best with hashed pins;
    # that notice is not the reason a run failed.
    lines = [
        line.strip() for line in output.splitlines()
        if line.strip() and '--no-deps is supported' not in line and 'pip-compile' not in line
    ]
    return ' | '.join(lines[-3:]) or 'no output'


def markdown_table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '|' + '---|' * len(headers)]
    out += ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]
    return '\n'.join(out)


# --------------------------------------------------------------------------
# Python: backend runtime graph
# --------------------------------------------------------------------------

def _requirement_lines(path):
    """Map normalized package name -> version specifier for a pinned file."""
    pins = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        match = re.match(r'([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)', line)
        if not match:
            raise ScannerError(f'cannot parse {path.name} line: {raw!r}')
        pins[re.sub(r'[-_.]+', '-', match.group(1)).lower()] = match.group(2).strip()
    return pins


def audit_python():
    requirements = _requirement_lines(BACKEND / 'requirements.txt')
    constraints = _requirement_lines(BACKEND / 'constraints.txt')

    # constraints.txt is what gets audited, so it must cover every declared
    # runtime dependency and agree with every exact pin in requirements.txt.
    missing = sorted(set(requirements) - set(constraints))
    mismatched = sorted(
        name for name, spec in requirements.items()
        if spec.startswith('==') and name in constraints and constraints[name] != spec
    )
    if missing or mismatched:
        raise ScannerError(
            'backend/constraints.txt is out of date with requirements.txt '
            f'(missing: {missing or "none"}; different pins: {mismatched or "none"}); '
            'regenerate it before auditing'
        )
    if not all(spec.startswith('==') for spec in constraints.values()):
        raise ScannerError('every backend/constraints.txt entry must be an exact == pin')

    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / 'pip-audit.json'
        cmd = [
            sys.executable, '-m', 'pip_audit',
            '--requirement', str(BACKEND / 'constraints.txt'),
            '--no-deps', '--disable-pip', '--strict',
            '--progress-spinner', 'off',
            '--format', 'json', '--output', str(report_path),
        ]
        print('$ python -m', ' '.join(cmd[3:]))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not report_path.exists():
            raise ScannerError(
                f'pip-audit produced no report (exit {proc.returncode}): {failure_detail(proc)}'
            )
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            dependencies = report['dependencies']
        except (ValueError, KeyError) as exc:
            raise ScannerError(f'pip-audit report is not usable: {exc}') from exc

    audited = [d for d in dependencies if not d.get('skip_reason')]
    if len(audited) != len(constraints):
        raise ScannerError(
            f'pip-audit audited {len(audited)} of {len(constraints)} pinned packages'
        )

    # The PyPI service can return the same advisory twice for one package;
    # each (package, advisory) pair is counted once.
    rows, seen = [], set()
    for dep in audited:
        for vuln in dep.get('vulns', []):
            key = (dep['name'], vuln['id'])
            if key in seen:
                continue
            seen.add(key)
            aliases = ', '.join(a for a in vuln.get('aliases', []) if a.startswith('GHSA-'))
            fixes = ', '.join(vuln.get('fix_versions', [])) or 'none listed'
            rows.append((dep['name'], dep['version'], vuln['id'], aliases or '-', fixes))

    packages = sorted({r[0] for r in rows})
    print(f'Audited {len(audited)} pinned backend runtime packages.')
    headers = ('Package', 'Version', 'Advisory', 'GHSA', 'Fixed in')
    if rows:
        print_table(headers, rows)
        annotate(
            'warning', 'Python dependency audit',
            f'{len(rows)} known vulnerabilities in {len(packages)} backend runtime '
            f'packages: {", ".join(packages)}',
        )
    else:
        print('No known vulnerabilities.')
    step_summary(
        f'### Python runtime dependencies\n\n{len(audited)} packages audited, '
        f'{len(rows)} known vulnerabilities in {len(packages)} packages.\n\n'
        + (markdown_table(headers, rows) if rows else '')
    )
    return len(rows), None


# --------------------------------------------------------------------------
# npm: committed frontend lockfile
# --------------------------------------------------------------------------

def audit_npm():
    npm = shutil.which('npm')
    if not npm:
        raise ScannerError('npm is not installed or not on PATH')

    cmd = [npm, 'audit', '--package-lock-only', '--json']
    print('$ npm audit --package-lock-only --json   (in frontend/)')
    proc = subprocess.run(
        cmd, cwd=FRONTEND, capture_output=True, text=True, encoding='utf-8', check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except ValueError as exc:
        raise ScannerError(
            f'npm audit did not return JSON (exit {proc.returncode}): {failure_detail(proc)}'
        ) from exc
    if report.get('auditReportVersion') != 2 or 'metadata' not in report:
        detail = report.get('error', {}).get('summary') or report.get('message') or report
        raise ScannerError(f'npm audit did not produce a report (exit {proc.returncode}): {detail}')

    counts = report['metadata']['vulnerabilities']
    order = {s: i for i, s in enumerate(reversed(SEVERITIES))}
    rows = []
    for name, vuln in sorted(
        report.get('vulnerabilities', {}).items(),
        key=lambda item: (order.get(item[1]['severity'], len(order)), item[0]),
    ):
        advisories = sorted({
            via['url'].rsplit('/', 1)[-1]
            for via in vuln.get('via', []) if isinstance(via, dict) and via.get('url')
        })
        # Whether a fix exists, and a package's own upgrade target, are stable
        # between runs; the parent npm proposes upgrading to fix a transitive
        # package is not, so only the stable facts are shown.
        fix = vuln.get('fixAvailable')
        if isinstance(fix, dict) and fix.get('name') == name:
            fix_text = f"upgrade to {fix.get('version')}"
            if fix.get('isSemVerMajor'):
                fix_text += ' (major)'
        elif fix:
            fix_text = 'yes'
        else:
            fix_text = 'NO'
        via_packages = [v for v in vuln.get('via', []) if isinstance(v, str)]
        rows.append((
            vuln['severity'], name, 'direct' if vuln.get('isDirect') else 'transitive',
            short_list(advisories) if advisories else 'via ' + short_list(via_packages),
            fix_text,
        ))

    total = counts.get('total', 0)
    breakdown = ', '.join(f'{counts.get(s, 0)} {s}' for s in reversed(SEVERITIES))
    deps = report['metadata'].get('dependencies', {}).get('total', '?')
    print(f'Audited {deps} packages in frontend/package-lock.json: {total} vulnerable ({breakdown}).')
    headers = ('Severity', 'Package', 'Dependency', 'Advisories', 'Fix available')
    if rows:
        print_table(headers, rows)
        annotate(
            'warning', 'npm dependency audit',
            f'{total} vulnerable frontend packages ({breakdown})',
        )
    else:
        print('No known vulnerabilities.')
    step_summary(
        f'### Frontend npm dependencies\n\n{deps} packages audited, {total} vulnerable '
        f'({breakdown}).\n\n' + (markdown_table(headers, rows) if rows else '')
    )
    return total, counts


# --------------------------------------------------------------------------

def exceeds(fail_on, total, counts):
    if fail_on == 'none':
        return False
    if fail_on == 'any':
        return total > 0
    threshold = SEVERITIES.index(fail_on)
    return any(counts.get(s, 0) for s in SEVERITIES[threshold:])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    parser.add_argument('ecosystem', choices=['python', 'npm'])
    parser.add_argument(
        '--fail-on', default='none', choices=['none', 'any', *SEVERITIES],
        help='exit 1 when findings reach this level (default: none, advisory only); '
             'Python advisories carry no severity, so python accepts only none or any',
    )
    args = parser.parse_args(argv)

    if args.ecosystem == 'python' and args.fail_on not in ('none', 'any'):
        parser.error('python findings have no severity; use --fail-on none or any')

    try:
        total, counts = audit_python() if args.ecosystem == 'python' else audit_npm()
    except ScannerError as exc:
        annotate('error', f'{args.ecosystem} dependency audit could not run', str(exc))
        return SCANNER_ERROR

    if exceeds(args.fail_on, total, counts or {}):
        annotate('error', f'{args.ecosystem} dependency audit',
                 f'findings at or above --fail-on {args.fail_on}')
        return FINDINGS
    return OK


if __name__ == '__main__':
    sys.exit(main())
