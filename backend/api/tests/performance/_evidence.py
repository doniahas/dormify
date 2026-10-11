"""
Optional evidence output for the performance suite.

Every assertion in this package is self-contained; the human-readable
query-count files these tests can emit are diagnostic output, never part
of a pass/fail decision. They are therefore written only when the caller
asks for them by naming an output directory, so an ordinary run writes
nothing at all and leaves the working tree untouched.

To collect the evidence, point DORMIFY_PERF_EVIDENCE_DIR at a directory
of your choosing:

    DORMIFY_PERF_EVIDENCE_DIR=/tmp/perf-evidence python manage.py test api.tests.performance

There is deliberately no default location. An unset or empty variable
means no output, rather than a path chosen on the caller's behalf.
"""

import os
from pathlib import Path


def write_evidence(filename, lines):
    """
    Write `lines` as `filename` inside the configured evidence directory.

    Does nothing unless DORMIFY_PERF_EVIDENCE_DIR names a directory. When
    it does, the directory is created if needed and the file is written as
    UTF-8 text, one entry per line.
    """
    target = os.environ.get('DORMIFY_PERF_EVIDENCE_DIR', '').strip()
    if not target:
        return

    directory = Path(target)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text('\n'.join(lines) + '\n', encoding='utf-8')
