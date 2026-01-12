"""Timeline merging functionality."""

from datetime import datetime, timedelta
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, list_tables, query_to_polars, polars_to_table


def merge_timelines(
    db_path: str,
    *,
    tables: list[str] | None = None,
    timestamp_column: str = "timestamp",
    start: datetime | None = None,
    end: datetime | None = None,
    tolerance: timedelta | None = None,
) -> pl.DataFrame:
    """Merge events from multiple tables into a unified timeline.

    Args:
        db_path: Path to DuckDB database.
        tables: Tables to merge. If None, use all tables with timestamp column.
        timestamp_column: Name of timestamp column.
        start: Filter events after this time.
        end: Filter events before this time.
        tolerance: Time tolerance for grouping events.

    Returns:
        Merged DataFrame sorted by timestamp.
    """
    with connect(db_path) as conn:
        if tables is None:
            tables = _find_timestamp_tables(conn, timestamp_column)

        if not tables:
            return pl.DataFrame()

        frames = []
        for table in tables:
            df = _load_table_timeline(
                conn,
                table,
                timestamp_column,
                start,
                end,
            )
            if not df.is_empty():
                frames.append(df)

        if not frames:
            return pl.DataFrame()

        # Concatenate all frames
        merged = pl.concat(frames, how="diagonal")

        # Sort by timestamp
        merged = merged.sort(timestamp_column)

        return merged


def create_unified_timeline(
    db_path: str,
    output_table: str = "unified_timeline",
    *,
    tables: list[str] | None = None,
    timestamp_column: str = "timestamp",
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Create a unified timeline table in the database.

    Args:
        db_path: Path to DuckDB database.
        output_table: Name of output table.
        tables: Tables to merge.
        timestamp_column: Name of timestamp column.
        start: Filter events after this time.
        end: Filter events before this time.

    Returns:
        Number of rows in unified timeline.
    """
    merged = merge_timelines(
        db_path,
        tables=tables,
        timestamp_column=timestamp_column,
        start=start,
        end=end,
    )

    if merged.is_empty():
        return 0

    with connect(db_path) as conn:
        polars_to_table(conn, merged, output_table)

    return len(merged)


def _find_timestamp_tables(conn: Any, timestamp_column: str) -> list[str]:
    """Find tables that have a timestamp column."""
    tables = list_tables(conn)
    result = []

    for table in tables:
        try:
            schema = conn.execute(f"DESCRIBE {table}").fetchall()
            columns = [row[0] for row in schema]
            if timestamp_column in columns:
                result.append(table)
        except Exception:
            continue

    return result


def _load_table_timeline(
    conn: Any,
    table: str,
    timestamp_column: str,
    start: datetime | None,
    end: datetime | None,
) -> pl.DataFrame:
    """Load a table's timeline data."""
    # Build WHERE clause
    conditions = []
    if start:
        conditions.append(f"{timestamp_column} >= '{start.isoformat()}'")
    if end:
        conditions.append(f"{timestamp_column} <= '{end.isoformat()}'")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get schema to build select
    schema = conn.execute(f"DESCRIBE {table}").fetchall()
    columns = [row[0] for row in schema]

    # Select all columns plus source tag
    sql = f"""
        SELECT
            *,
            '{table}' as _timeline_source
        FROM {table}
        {where_clause}
        ORDER BY {timestamp_column}
    """

    try:
        return query_to_polars(conn, sql)
    except Exception:
        return pl.DataFrame()


def slice_timeline(
    df: pl.DataFrame,
    start: datetime,
    end: datetime,
    timestamp_column: str = "timestamp",
) -> pl.DataFrame:
    """Extract a time slice from a timeline.

    Args:
        df: Timeline DataFrame.
        start: Start of slice.
        end: End of slice.
        timestamp_column: Name of timestamp column.

    Returns:
        Filtered DataFrame.
    """
    return df.filter(
        (pl.col(timestamp_column) >= start) & (pl.col(timestamp_column) <= end)
    )
