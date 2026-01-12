"""Temporal correlation analysis."""

from datetime import datetime, timedelta
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars
from vault_toolkit.core.types import Correlation


def correlate_temporal(
    db_path: str,
    source_table: str,
    target_table: str,
    *,
    join_field: str | None = None,
    source_timestamp: str = "timestamp",
    target_timestamp: str = "timestamp",
    time_window: timedelta,
    direction: str = "both",  # 'before', 'after', 'both'
    score_weight: float = 1.0,
) -> pl.DataFrame:
    """Find temporal correlations between two tables.

    Args:
        db_path: Path to DuckDB database.
        source_table: Source table name.
        target_table: Target table name.
        join_field: Field to join on (e.g., entity_id). If None, uses time only.
        source_timestamp: Timestamp column in source table.
        target_timestamp: Timestamp column in target table.
        time_window: Maximum time difference for correlation.
        direction: Time direction ('before', 'after', 'both').
        score_weight: Weight multiplier for correlation scores.

    Returns:
        DataFrame with correlation results.
    """
    with connect(db_path) as conn:
        # Build time condition
        window_seconds = time_window.total_seconds()

        if direction == "before":
            time_cond = f"""
                s.{source_timestamp} >= t.{target_timestamp}
                AND s.{source_timestamp} <= t.{target_timestamp} + INTERVAL '{window_seconds} seconds'
            """
        elif direction == "after":
            time_cond = f"""
                s.{source_timestamp} <= t.{target_timestamp}
                AND s.{source_timestamp} >= t.{target_timestamp} - INTERVAL '{window_seconds} seconds'
            """
        else:  # both
            time_cond = f"""
                ABS(EPOCH(s.{source_timestamp}) - EPOCH(t.{target_timestamp})) <= {window_seconds}
            """

        # Build join condition
        if join_field:
            join_cond = f"s.{join_field} = t.{join_field}"
            join_clause = f"ON {join_cond} AND {time_cond}"
        else:
            join_clause = f"ON {time_cond}"

        # Calculate time-based score (closer = higher score)
        sql = f"""
            SELECT
                s.rowid as source_row,
                t.rowid as target_row,
                s.{source_timestamp} as source_time,
                t.{target_timestamp} as target_time,
                ABS(EPOCH(s.{source_timestamp}) - EPOCH(t.{target_timestamp})) as time_diff_seconds,
                {score_weight} * (1.0 - (ABS(EPOCH(s.{source_timestamp}) - EPOCH(t.{target_timestamp})) / {window_seconds})) as score,
                '{source_table}' as source_table,
                '{target_table}' as target_table,
                'temporal' as correlation_type
            FROM {source_table} s
            JOIN {target_table} t {join_clause}
            WHERE s.{source_timestamp} IS NOT NULL
              AND t.{target_timestamp} IS NOT NULL
            ORDER BY score DESC
        """

        return query_to_polars(conn, sql)


def find_temporal_proximity(
    conn: Any,
    entity: str,
    entity_table: str,
    event_table: str,
    *,
    entity_field: str = "value",
    timestamp_field: str = "timestamp",
    time_window: timedelta,
    direction: str = "both",
) -> pl.DataFrame:
    """Find events temporally proximate to an entity's occurrences.

    Args:
        conn: DuckDB connection.
        entity: Entity value to search for.
        entity_table: Table containing entities.
        event_table: Table containing events.
        entity_field: Field in entity table containing the value.
        timestamp_field: Timestamp field name.
        time_window: Time window for proximity.
        direction: Search direction ('before', 'after', 'both').

    Returns:
        DataFrame with proximate events.
    """
    window_seconds = time_window.total_seconds()

    if direction == "before":
        time_cond = f"""
            e.{timestamp_field} <= ent.{timestamp_field}
            AND e.{timestamp_field} >= ent.{timestamp_field} - INTERVAL '{window_seconds} seconds'
        """
    elif direction == "after":
        time_cond = f"""
            e.{timestamp_field} >= ent.{timestamp_field}
            AND e.{timestamp_field} <= ent.{timestamp_field} + INTERVAL '{window_seconds} seconds'
        """
    else:
        time_cond = f"""
            ABS(EPOCH(e.{timestamp_field}) - EPOCH(ent.{timestamp_field})) <= {window_seconds}
        """

    sql = f"""
        SELECT
            e.*,
            ent.{timestamp_field} as entity_time,
            ABS(EPOCH(e.{timestamp_field}) - EPOCH(ent.{timestamp_field})) as time_diff_seconds
        FROM {event_table} e
        JOIN {entity_table} ent ON {time_cond}
        WHERE ent.{entity_field} = '{entity}'
        ORDER BY time_diff_seconds
    """

    return query_to_polars(conn, sql)


def detect_sequences(
    db_path: str,
    table: str,
    type_field: str,
    timestamp_field: str = "timestamp",
    *,
    group_field: str | None = None,
    max_gap: timedelta = timedelta(hours=1),
) -> pl.DataFrame:
    """Detect event sequences within groups.

    Args:
        db_path: Path to DuckDB database.
        table: Table containing events.
        type_field: Field containing event type.
        timestamp_field: Timestamp field.
        group_field: Field to group sequences by.
        max_gap: Maximum gap between events in a sequence.

    Returns:
        DataFrame with sequence information.
    """
    with connect(db_path) as conn:
        # Get events ordered by time
        if group_field:
            order_by = f"{group_field}, {timestamp_field}"
            partition_by = f"PARTITION BY {group_field}"
        else:
            order_by = timestamp_field
            partition_by = ""

        sql = f"""
            WITH ordered_events AS (
                SELECT
                    *,
                    LAG({timestamp_field}) OVER ({partition_by} ORDER BY {timestamp_field}) as prev_time,
                    LAG({type_field}) OVER ({partition_by} ORDER BY {timestamp_field}) as prev_type
                FROM {table}
                WHERE {timestamp_field} IS NOT NULL
            ),
            sequenced AS (
                SELECT
                    *,
                    CASE
                        WHEN prev_time IS NULL THEN 1
                        WHEN EPOCH({timestamp_field}) - EPOCH(prev_time) > {max_gap.total_seconds()} THEN 1
                        ELSE 0
                    END as new_sequence
                FROM ordered_events
            ),
            with_seq_id AS (
                SELECT
                    *,
                    SUM(new_sequence) OVER ({partition_by} ORDER BY {timestamp_field}) as sequence_id
                FROM sequenced
            )
            SELECT
                sequence_id,
                {f'{group_field},' if group_field else ''}
                LIST({type_field} ORDER BY {timestamp_field}) as sequence,
                MIN({timestamp_field}) as sequence_start,
                MAX({timestamp_field}) as sequence_end,
                COUNT(*) as event_count
            FROM with_seq_id
            GROUP BY sequence_id{f', {group_field}' if group_field else ''}
            HAVING COUNT(*) > 1
            ORDER BY sequence_start
        """

        return query_to_polars(conn, sql)
