"""Optional evidence output for the concurrency suite.

Concurrency assertions do not depend on the human-readable race and load
evidence files. Those files are diagnostic output and are written only when
the caller explicitly names an output directory, so an ordinary test run
leaves the working tree untouched.

To collect fresh evidence, point DORMIFY_CONCURRENCY_EVIDENCE_DIR at an
external directory:

    DORMIFY_CONCURRENCY_EVIDENCE_DIR=/tmp/concurrency-evidence \
        python manage.py test api.tests.concurrency

There is deliberately no default location. An unset or empty variable means
no output, rather than a path chosen on the caller's behalf.
"""

import os
from pathlib import Path


def write_evidence(filename, lines):
    """Write ``lines`` as ``filename`` inside the configured directory."""
    target = os.environ.get('DORMIFY_CONCURRENCY_EVIDENCE_DIR', '').strip()
    if not target:
        return

    directory = Path(target)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text('\n'.join(lines) + '\n', encoding='utf-8')
