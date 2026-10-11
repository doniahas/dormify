#!/usr/bin/env bash
#
# Run the complete allocation regression suite (api.tests.allocation) the way
# CI does, and fail unless every test passes.
#
# Contract
#   * The suite always runs in full. Nothing is filtered and no failure is
#     tolerated. The complete output is written to a log file that CI
#     uploads as a build artifact.
#   * Success requires all of: the Django test runner exits 0, every
#     discovered test was run, no test reports FAIL or ERROR, and the final
#     verdict is OK.
#   * Anything else is a failure, including a run that did not complete or
#     whose summary cannot be found in the log.
#
# Usage
#   scripts/ci/run_allocation_suite.sh
#
#     ALLOCATION_LOG  Optional path for the full test log.
#                     Default: allocation-suite.log in the current directory.
#                     CI points this outside the checkout so a test run never
#                     leaves an untracked file in the working tree.
#
#   Database and Django settings come from the environment, exactly as for
#   `python manage.py test` (see docs/TESTING.md).
#
# Exit status
#   0  every allocation test passed
#   1  anything else
#
# `set -e` is deliberately not used: the test runner's exit status is captured
# so the summary below is always printed before the verdict.
set -uo pipefail

if [ "$#" -ne 0 ]; then
    echo "::error::Unexpected argument(s): $*"
    echo "Usage: scripts/ci/run_allocation_suite.sh   (log path: ALLOCATION_LOG)"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
LOG="${ALLOCATION_LOG:-allocation-suite.log}"

if [ ! -f "${BACKEND_DIR}/manage.py" ]; then
    echo "::error::Django project not found: ${BACKEND_DIR}/manage.py"
    exit 1
fi

# Resolve the log path against the invocation directory and create its parent,
# before the working directory changes to backend/ below. Resolving through
# cd/pwd rather than string concatenation keeps this correct for relative and
# already-absolute paths alike, on any platform where this script runs.
LOG_DIR="$(dirname -- "${LOG}")"
LOG_NAME="$(basename -- "${LOG}")"
if ! mkdir -p "${LOG_DIR}"; then
    echo "::error::Could not create the log directory: ${LOG_DIR}"
    exit 1
fi
LOG="$(cd -- "${LOG_DIR}" && pwd)/${LOG_NAME}"

echo "Allocation regression suite"
echo "  backend : ${BACKEND_DIR}"
echo "  log     : ${LOG}"
echo

cd "${BACKEND_DIR}" || {
    echo "::error::Could not enter ${BACKEND_DIR}"
    exit 1
}

# The full run is captured to a file rather than streamed to the console: at
# verbosity 2 this suite prints large diagnostic tables, which would bury the
# result. The summary below and the uploaded artifact carry the detail.
python manage.py test api.tests.allocation --noinput --verbosity 2 \
    > "${LOG}" 2>&1
RUNNER_STATUS=$?

echo "Django test runner exit status: ${RUNNER_STATUS}"
echo
echo "--- runner summary -------------------------------------------------"
grep -E '^(Found [0-9]+ test|Ran [0-9]+ test|OK|FAILED)' "${LOG}" || true
grep -E '^(FAIL|ERROR): ' "${LOG}" || true
echo "--------------------------------------------------------------------"
echo

# Django prints "Found N test(s)." before the run, then one "FAIL: ..." or
# "ERROR: ..." header per problem, "Ran N tests in ...", and a final "OK" or
# "FAILED (...)" verdict. Each is read from the log and checked independently,
# so a change in the output format fails the job instead of passing it.
found="$(sed -nE 's/^Found ([0-9]+) test.*/\1/p' "${LOG}" | tail -n 1)"
ran="$(sed -nE 's/^Ran ([0-9]+) tests? in .*/\1/p' "${LOG}" | tail -n 1)"
verdict="$(grep -E '^(OK|FAILED)( \(.*\))?[[:space:]]*$' "${LOG}" | tail -n 1)"
problems="$(grep -cE '^(FAIL|ERROR): ' "${LOG}" || true)"

status=0
incomplete=0
report() {
    echo "::error::$*"
    status=1
}

if [ -z "${ran}" ] || [ -z "${verdict}" ]; then
    report "The allocation suite did not complete: the log has no 'Ran N tests' summary or no final verdict."
    incomplete=1
elif [ -z "${found}" ] || [ "${found}" -ne "${ran}" ]; then
    report "The runner discovered ${found:-an unknown number of} test(s) but ran ${ran}: the run did not cover the whole suite."
    incomplete=1
fi

if [ "${problems}" -gt 0 ]; then
    report "${problems} failing or erroring test(s). Every allocation test must pass:"
    grep -E '^(FAIL|ERROR): ' "${LOG}" | sed 's/^/  - /'
fi

if [ "${RUNNER_STATUS}" -ne 0 ]; then
    report "The Django test runner exited ${RUNNER_STATUS}."
fi

case "${verdict}" in
    OK*) ;;
    "") ;;
    *) report "Final verdict: ${verdict}" ;;
esac

if [ "${status}" -ne 0 ]; then
    if [ "${incomplete}" -eq 1 ]; then
        echo "--- last 100 log lines ---------------------------------------------"
        tail -n 100 "${LOG}"
    fi
    echo "::error::See the full log: ${LOG}"
    exit 1
fi

echo "OK - all ${ran} allocation tests passed (${verdict})."
exit 0
