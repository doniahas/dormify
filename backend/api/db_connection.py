"""
Database connection health check shared by long-running request paths.

Used by the synchronous allocation run and the Excel import workflows,
which hold a request open long enough for the pooled connection to go
stale between two ORM calls.
"""

from django.db import connection


def refresh_db_connection():
    """Reuse a healthy connection; reconnect only when it is actually stale."""
    if connection.connection is None:
        connection.ensure_connection()
        return

    try:
        if connection.is_usable():
            return
    except Exception:
        pass

    connection.close()
    connection.ensure_connection()
