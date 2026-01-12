"""Gap detection and density analysis."""

from datetime import datetime, timedelta
from typing import Any

import polars as pl

from vault_toolkit.core.types import Gap, TimeRange
from vault_toolkit.core.output import ascii_histogram


def detect_gaps(
    df: pl.DataFrame,
    threshold: timedelta,
    timestamp_column: str = "timestamp",
    *,
    source_column: str | None = None,
) -> list[Gap]:
    """Detect gaps in timeline data.

    A gap is a period where no events occur for longer than the threshold.

    Args:
        df: Timeline DataFrame sorted by timestamp.
        threshold: Minimum duration to consider a gap.
        timestamp_column: Name of timestamp column.
        source_column: Optional column to track which source the gap is in.

    Returns:
        List of Gap objects.
    """
    if df.is_empty() or len(df) < 2:
        return []

    # Ensure sorted
    df = df.sort(timestamp_column)

    # Calculate time differences
    timestamps = df[timestamp_column].to_list()
    gaps = []

    for i in range(1, len(timestamps)):
        prev_ts = timestamps[i - 1]
        curr_ts = timestamps[i]

        if prev_ts is None or curr_ts is None:
            continue

        diff = curr_ts - prev_ts
        if diff >= threshold:
            source = None
            if source_column and source_column in df.columns:
                source = df[source_column][i]

            gaps.append(Gap(
                start=prev_ts,
                end=curr_ts,
                source=source,
            ))

    return gaps


def analyze_density(
    df: pl.DataFrame,
    interval: timedelta,
    timestamp_column: str = "timestamp",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pl.DataFrame:
    """Analyze event density over time intervals.

    Args:
        df: Timeline DataFrame.
        interval: Time interval for grouping.
        timestamp_column: Name of timestamp column.
        start: Start of analysis period.
        end: End of analysis period.

    Returns:
        DataFrame with interval start, end, and event count.
    """
    if df.is_empty():
        return pl.DataFrame(schema={
            "interval_start": pl.Datetime,
            "interval_end": pl.Datetime,
            "event_count": pl.Int64,
        })

    # Get time bounds
    timestamps = df[timestamp_column].drop_nulls()
    if timestamps.is_empty():
        return pl.DataFrame()

    if start is None:
        start = timestamps.min()
    if end is None:
        end = timestamps.max()

    # Generate intervals
    intervals = []
    current = start
    while current < end:
        interval_end = min(current + interval, end)
        count = df.filter(
            (pl.col(timestamp_column) >= current) &
            (pl.col(timestamp_column) < interval_end)
        ).height

        intervals.append({
            "interval_start": current,
            "interval_end": interval_end,
            "event_count": count,
        })
        current = interval_end

    return pl.DataFrame(intervals)


def format_timeline_summary(
    df: pl.DataFrame,
    timestamp_column: str = "timestamp",
    *,
    source_column: str | None = "_timeline_source",
    interval_hours: int = 1,
) -> str:
    """Format a timeline summary with ASCII histogram.

    Args:
        df: Timeline DataFrame.
        timestamp_column: Name of timestamp column.
        source_column: Column containing source names.
        interval_hours: Hours per interval in histogram.

    Returns:
        Formatted summary string.
    """
    if df.is_empty():
        return "No events in timeline"

    lines = []

    # Time range
    timestamps = df[timestamp_column].drop_nulls()
    start = timestamps.min()
    end = timestamps.max()
    lines.append(f"Timeline: {start} - {end}")

    # Source counts
    if source_column and source_column in df.columns:
        sources = df.group_by(source_column).len().sort("len", descending=True)
        source_strs = [
            f"{row[source_column]} ({row['len']:,})"
            for row in sources.iter_rows(named=True)
        ]
        lines.append(f"Sources: {', '.join(source_strs)}")

    lines.append("")

    # Density histogram
    interval = timedelta(hours=interval_hours)
    density = analyze_density(df, interval, timestamp_column)

    if not density.is_empty():
        values = []
        for row in density.iter_rows(named=True):
            hour = row["interval_start"].strftime("%H:%M")
            values.append((hour, row["event_count"]))

        lines.append(ascii_histogram(values))

    return "\n".join(lines)


def format_gaps_summary(gaps: list[Gap], threshold: timedelta) -> str:
    """Format a summary of detected gaps.

    Args:
        gaps: List of Gap objects.
        threshold: Threshold used for detection.

    Returns:
        Formatted summary string.
    """
    if not gaps:
        return f"No gaps detected (threshold: {threshold})"

    lines = [f"Gaps detected: {len(gaps)}"]

    for gap in gaps:
        source_str = f" [{gap.source}]" if gap.source else ""
        lines.append(f"  {gap.start} - {gap.end} ({gap.duration_str}){source_str}")

    return "\n".join(lines)
