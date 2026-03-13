"""Database connection pool and helpers.

Uses psycopg 3's built-in ConnectionPool, which manages a pool of
reusable Postgres connections. This avoids the overhead of opening a
new TCP connection + TLS handshake on every function call.

Usage in tool functions:

    from studio_data.db import get_connection

    def create_client(name: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "INSERT INTO clients (name) VALUES (%s) RETURNING *",
                (name,),
            ).fetchone()
        return row  # dict thanks to row_factory=dict_row

The `with` block automatically:
  - Grabs a connection from the pool
  - Commits the transaction if no exception is raised
  - Rolls back if an exception is raised
  - Returns the connection to the pool when done
"""

from collections.abc import Generator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from studio_data.config import get_settings

# Module-level pool — initialized lazily on first use.
# We use a module-level variable (not lru_cache) because the pool
# needs to be explicitly opened/closed and has mutable state.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    """Return the module-level connection pool, creating it on first call.

    The pool starts with 1 connection and grows up to 10 as needed.
    dict_row is set as the default row factory so every query returns
    dicts instead of tuples — much easier to work with in tool functions.
    """
    global _pool  # noqa: PLW0603
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    """Yield a database connection from the pool.

    Automatically commits on success, rolls back on exception,
    and returns the connection to the pool when done.
    """
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    """Shut down the connection pool (for clean teardown in tests)."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        _pool.close()
        _pool = None
