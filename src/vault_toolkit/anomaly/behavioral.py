"""Behavioral anomaly detection based on baselines."""

from datetime import datetime, timedelta
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars
from vault_toolkit.core.types import AnomalyResult, Severity


def detect_behavioral_anomalies(
    db_path: str,
    table: str,
    *,
    timestamp_column: str = "timestamp",
    entity_column: str | None = None,
    metric_column: str | None = None,
    baseline_window: timedelta = timedelta(days=7),
    deviation_threshold: float = 2.5,
    aggregation: str = "count",  # 'count', 'sum', 'mean'
    bucket_size: timedelta = timedelta(hours=1),
) -> list[AnomalyResult]:
    """Detect anomalies by comparing to behavioral baseline.

    Args:
        db_path: Path to DuckDB database.
        table: Table to analyze.
        timestamp_column: Column containing timestamps.
        entity_column: Column to group by (optional).
        metric_column: Column to aggregate (for sum/mean).
        baseline_window: Time window for baseline calculation.
        deviation_threshold: Standard deviations for anomaly threshold.
        aggregation: Aggregation method ('count', 'sum', 'mean').
        bucket_size: Time bucket size for aggregation.

    Returns:
        List of AnomalyResult objects.
    """
    with connect(db_path) as conn:
        # Get time range
        time_range = query_to_polars(conn, f"""
            SELECT
                MIN({timestamp_column}) as min_ts,
                MAX({timestamp_column}) as max_ts
            FROM {table}
            WHERE {timestamp_column} IS NOT NULL
        """)

        if time_range.is_empty():
            return []

        min_ts = time_range["min_ts"][0]
        max_ts = time_range["max_ts"][0]

        if min_ts is None or max_ts is None:
            return []

        # Build baseline for the window
        baseline = build_baseline(
            conn,
            table,
            timestamp_column,
            entity_column=entity_column,
            metric_column=metric_column,
            baseline_window=baseline_window,
            aggregation=aggregation,
            bucket_size=bucket_size,
        )

        if baseline.is_empty():
            return []

        # Compare recent data against baseline
        results = []
        current_time = max_ts

        # Analyze the most recent period
        recent_start = current_time - bucket_size
        recent_data = _get_bucket_data(
            conn,
            table,
            timestamp_column,
            recent_start,
            current_time,
            entity_column,
            metric_column,
            aggregation,
        )

        for row in recent_data.iter_rows(named=True):
            entity_id = row.get("entity_id") if entity_column else None
            current_value = row["value"]

            # Get baseline stats for this entity
            if entity_column and entity_id:
                entity_baseline = baseline.filter(pl.col("entity_id") == entity_id)
            else:
                entity_baseline = baseline

            if entity_baseline.is_empty():
                continue

            baseline_mean = entity_baseline["value"].mean()
            baseline_std = entity_baseline["value"].std()

            if baseline_std is None or baseline_std == 0:
                continue

            # Calculate deviation
            zscore = (current_value - baseline_mean) / baseline_std

            if abs(zscore) > deviation_threshold:
                # This is anomalous
                severity = _zscore_to_severity(abs(zscore))
                direction = "above" if zscore > 0 else "below"

                results.append(AnomalyResult(
                    timestamp=current_time,
                    entity_id=str(entity_id) if entity_id else None,
                    severity=severity,
                    anomaly_type="behavioral",
                    description=(
                        f"Behavioral anomaly: {current_value:.1f} {aggregation} "
                        f"(baseline: {baseline_mean:.1f}, z-score: {zscore:.1f})"
                    ),
                    score=abs(zscore),
                    metadata={
                        "current_value": current_value,
                        "baseline_mean": baseline_mean,
                        "baseline_std": baseline_std,
                        "direction": direction,
                    },
                ))

        return results


def build_baseline(
    conn: Any,
    table: str,
    timestamp_column: str,
    *,
    entity_column: str | None = None,
    metric_column: str | None = None,
    baseline_window: timedelta = timedelta(days=7),
    aggregation: str = "count",
    bucket_size: timedelta = timedelta(hours=1),
) -> pl.DataFrame:
    """Build a baseline from historical data.

    Args:
        conn: DuckDB connection.
        table: Table to analyze.
        timestamp_column: Column containing timestamps.
        entity_column: Column to group by.
        metric_column: Column to aggregate.
        baseline_window: Time window for baseline.
        aggregation: Aggregation method.
        bucket_size: Time bucket size.

    Returns:
        DataFrame with baseline statistics per bucket.
    """
    # Get time range
    time_range = query_to_polars(conn, f"""
        SELECT MAX({timestamp_column}) as max_ts
        FROM {table}
        WHERE {timestamp_column} IS NOT NULL
    """)

    if time_range.is_empty() or time_range["max_ts"][0] is None:
        return pl.DataFrame()

    max_ts = time_range["max_ts"][0]
    baseline_start = max_ts - baseline_window

    bucket_seconds = int(bucket_size.total_seconds())

    # Build aggregation expression
    if aggregation == "count":
        agg_expr = "COUNT(*)"
    elif aggregation == "sum" and metric_column:
        agg_expr = f"SUM({metric_column})"
    elif aggregation == "mean" and metric_column:
        agg_expr = f"AVG({metric_column})"
    else:
        agg_expr = "COUNT(*)"

    # Group by time bucket and optional entity
    if entity_column:
        group_by = f"time_bucket, {entity_column}"
        select_entity = f"{entity_column} as entity_id,"
    else:
        group_by = "time_bucket"
        select_entity = "NULL as entity_id,"

    sql = f"""
        SELECT
            {select_entity}
            time_bucket(INTERVAL '{bucket_seconds} seconds', {timestamp_column}) as time_bucket,
            {agg_expr} as value
        FROM {table}
        WHERE {timestamp_column} >= '{baseline_start}'
          AND {timestamp_column} < '{max_ts}'
        GROUP BY {group_by}
        ORDER BY time_bucket
    """

    return query_to_polars(conn, sql)


def _get_bucket_data(
    conn: Any,
    table: str,
    timestamp_column: str,
    start: datetime,
    end: datetime,
    entity_column: str | None,
    metric_column: str | None,
    aggregation: str,
) -> pl.DataFrame:
    """Get aggregated data for a time bucket."""
    if aggregation == "count":
        agg_expr = "COUNT(*)"
    elif aggregation == "sum" and metric_column:
        agg_expr = f"SUM({metric_column})"
    elif aggregation == "mean" and metric_column:
        agg_expr = f"AVG({metric_column})"
    else:
        agg_expr = "COUNT(*)"

    if entity_column:
        group_by = f"GROUP BY {entity_column}"
        select_entity = f"{entity_column} as entity_id,"
    else:
        group_by = ""
        select_entity = "NULL as entity_id,"

    sql = f"""
        SELECT
            {select_entity}
            {agg_expr} as value
        FROM {table}
        WHERE {timestamp_column} >= '{start}'
          AND {timestamp_column} < '{end}'
        {group_by}
    """

    return query_to_polars(conn, sql)


def _zscore_to_severity(zscore: float) -> Severity:
    """Convert z-score to severity level."""
    if zscore >= 4.0:
        return Severity.HIGH
    elif zscore >= 3.0:
        return Severity.MEDIUM
    else:
        return Severity.LOW
