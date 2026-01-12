"""DuckDB connection management and utilities."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import duckdb
import polars as pl


@contextmanager
def connect(db_path: str | Path) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Context manager for DuckDB connections.

    Args:
        db_path: Path to the DuckDB database file.

    Yields:
        DuckDB connection object.
    """
    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


def polars_to_table(
    conn: duckdb.DuckDBPyConnection,
    df: pl.DataFrame,
    table: str,
    replace: bool = True,
) -> None:
    """Write a Polars DataFrame to a DuckDB table.

    Args:
        conn: DuckDB connection.
        df: Polars DataFrame to write.
        table: Target table name.
        replace: If True, replace existing table. Otherwise append.
    """
    if replace:
        conn.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df")
    else:
        if table_exists(conn, table):
            conn.execute(f"INSERT INTO {table} SELECT * FROM df")
        else:
            conn.execute(f"CREATE TABLE {table} AS SELECT * FROM df")


def table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    """Check if a table exists in the database.

    Args:
        conn: DuckDB connection.
        table: Table name to check.

    Returns:
        True if the table exists.
    """
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchone()
    return result[0] > 0 if result else False


def list_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """List all tables in the database.

    Args:
        conn: DuckDB connection.

    Returns:
        List of table names.
    """
    result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    return [row[0] for row in result]


def table_to_polars(conn: duckdb.DuckDBPyConnection, table: str) -> pl.DataFrame:
    """Read a DuckDB table into a Polars DataFrame.

    Args:
        conn: DuckDB connection.
        table: Table name to read.

    Returns:
        Polars DataFrame with table contents.
    """
    return conn.execute(f"SELECT * FROM {table}").pl()


def query_to_polars(conn: duckdb.DuckDBPyConnection, query: str) -> pl.DataFrame:
    """Execute a query and return results as Polars DataFrame.

    Args:
        conn: DuckDB connection.
        query: SQL query to execute.

    Returns:
        Polars DataFrame with query results.
    """
    return conn.execute(query).pl()
