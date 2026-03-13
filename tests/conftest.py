"""Shared test fixtures.

Every test runs inside a database transaction that gets rolled back
at the end — so tests never leave data behind and can run in any order.
This is a common pattern for database-backed tests: you get a real
Postgres connection (no mocking), but tests stay isolated and fast.
"""

import pytest

from studio_data.db import _get_pool, close_pool


@pytest.fixture(autouse=True)
def _rollback_after_each_test():
    """Wrap every test in a transaction that rolls back when done.

    How it works:
    1. Grab a raw connection from the pool (not via get_connection(),
       which auto-commits).
    2. Monkey-patch _get_pool so all code under test uses this same
       connection via a single-connection pool.
    3. After the test, roll back everything and restore the real pool.

    This means create_client(), create_project(), etc. all write to
    real Postgres tables during the test, but nothing persists.
    """
    import studio_data.db as db_module

    pool = _get_pool()

    # Get a connection and start a transaction
    conn = pool.getconn()
    # Save a reference to the original pool getter
    original_get_pool = db_module._get_pool

    # Create a minimal mock pool that always returns our transactional connection
    class _SingleConnPool:
        """Fake pool that yields the same connection every time."""

        def __init__(self, conn):
            self._conn = conn

        def connection(self):
            """Return a context manager that yields conn."""
            from contextlib import contextmanager

            @contextmanager
            def _no_commit_connection():
                # Yield the connection but do NOT commit — the rollback
                # in the fixture teardown will undo everything
                yield self._conn

            return _no_commit_connection()

    # Patch the module so get_connection() uses our transactional connection
    db_module._get_pool = lambda: _SingleConnPool(conn)  # type: ignore[assignment]

    yield

    # Teardown: roll back all changes and restore the real pool
    conn.rollback()
    pool.putconn(conn)
    db_module._get_pool = original_get_pool


@pytest.fixture(scope="session", autouse=True)
def _cleanup_pool():
    """Close the connection pool after all tests finish."""
    yield
    close_pool()
