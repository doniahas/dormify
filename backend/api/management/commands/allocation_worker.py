"""
The durable allocation worker process.

    python manage.py allocation_worker            # run until SIGTERM / Ctrl+C
    python manage.py allocation_worker --once     # one pass, then exit

Background allocation runs are queued by the web process as AllocationRun
rows; this process claims them from PostgreSQL and executes them (see
api.domains.allocation.jobs for the lease and recovery rules). Any number
of these processes may run against the same database. A stop signal lets
the run in progress finish before the process exits; a worker that is
killed mid-run is detected by the others once its lease expires.
"""

import logging
import signal
import sys

from django.core.management.base import BaseCommand, CommandError

from api.domains.allocation.jobs import WorkerSettings
from api.domains.allocation.worker import AllocationWorker

LOGGER_NAME = 'dormify.allocation.worker'


class Command(BaseCommand):
    help = 'Run the durable allocation worker that executes queued allocation runs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once', action='store_true',
            help='Recover stale runs, execute at most one queued run, then exit.',
        )
        parser.add_argument(
            '--poll-interval', type=float, default=None, dest='poll_interval_seconds',
            help='Seconds to wait when no run is queued (default: settings).',
        )
        parser.add_argument(
            '--lease-seconds', type=int, default=None, dest='lease_seconds',
            help='Lease held on a claimed run; a run whose lease expires is recovered.',
        )
        parser.add_argument(
            '--heartbeat-seconds', type=float, default=None, dest='heartbeat_seconds',
            help='Lease renewal interval while a run executes (0 disables renewal).',
        )
        parser.add_argument(
            '--max-attempts', type=int, default=None, dest='max_attempts',
            help='Claims a run may receive before a pre-solve worker loss fails it.',
        )
        parser.add_argument(
            '--worker-id', default=None,
            help='Identity recorded on claimed runs (default: host:pid:random).',
        )
        parser.add_argument(
            '--log-level', default='INFO',
            help='Log level of the worker logger (default: INFO).',
        )

    def handle(self, *args, **options):
        self._configure_logging(options['log_level'])
        try:
            worker_settings = WorkerSettings.from_settings(
                poll_interval_seconds=options['poll_interval_seconds'],
                lease_seconds=options['lease_seconds'],
                heartbeat_seconds=options['heartbeat_seconds'],
                max_attempts=options['max_attempts'],
            )
        except ValueError as invalid:
            raise CommandError(str(invalid)) from invalid

        worker = AllocationWorker(worker_id=options['worker_id'], worker_settings=worker_settings)

        if options['once']:
            cycle = worker.run_once()
            self.stdout.write(
                f'worker={worker.worker_id} recovered={len(cycle.recovered)} '
                f'claimed={getattr(cycle.claimed, "run_id", None)} '
                f'status={getattr(cycle.outcome, "status", None)} error={cycle.error or None}'
            )
            if cycle.error:
                raise CommandError(cycle.error)
            return

        previous_handlers = self._install_stop_handlers(worker)
        try:
            worker.run_forever()
        finally:
            self._restore_handlers(previous_handlers)

    def _configure_logging(self, level_name):
        logger = logging.getLogger(LOGGER_NAME)
        level = logging.getLevelName(str(level_name).upper())
        if not isinstance(level, int):
            raise CommandError(f'unknown log level: {level_name}')
        logger.setLevel(level)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
            logger.addHandler(handler)
            logger.propagate = False

    def _install_stop_handlers(self, worker):
        def request_stop(signum, _frame):
            logging.getLogger(LOGGER_NAME).info(
                'event=stop_requested signal=%s worker=%s', signum, worker.worker_id,
            )
            worker.request_stop()

        previous = {}
        for name in ('SIGINT', 'SIGTERM'):
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                previous[signum] = signal.signal(signum, request_stop)
            except (ValueError, OSError):
                # Not on the main thread, or the platform refuses the signal.
                continue
        return previous

    def _restore_handlers(self, previous):
        for signum, handler in previous.items():
            try:
                signal.signal(signum, handler)
            except (ValueError, OSError):
                continue
