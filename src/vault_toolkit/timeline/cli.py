"""CLI for vt-timeline."""

from datetime import datetime, timedelta
from pathlib import Path

import click

from vault_toolkit.core.db import connect, list_tables
from vault_toolkit.core.output import console
from vault_toolkit.timeline.merge import merge_timelines, create_unified_timeline
from vault_toolkit.timeline.gaps import (
    detect_gaps,
    format_timeline_summary,
    format_gaps_summary,
)


def parse_duration(value: str) -> timedelta:
    """Parse a duration string like '5m', '1h', '30s'."""
    if not value:
        raise ValueError("Empty duration")

    unit = value[-1].lower()
    try:
        amount = int(value[:-1])
    except ValueError:
        raise ValueError(f"Invalid duration: {value}")

    if unit == "s":
        return timedelta(seconds=amount)
    elif unit == "m":
        return timedelta(minutes=amount)
    elif unit == "h":
        return timedelta(hours=amount)
    elif unit == "d":
        return timedelta(days=amount)
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


@click.command()
@click.option(
    "--db", "-d",
    "db_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="DuckDB database file",
)
@click.option(
    "--start", "-s",
    type=click.DateTime(),
    help="Start of time range (ISO format)",
)
@click.option(
    "--end", "-e",
    type=click.DateTime(),
    help="End of time range (ISO format)",
)
@click.option(
    "--table", "-t",
    "tables",
    multiple=True,
    help="Tables to include (can specify multiple)",
)
@click.option(
    "--timestamp-column", "-c",
    default="timestamp",
    help="Name of timestamp column",
)
@click.option(
    "--gaps", "-g",
    is_flag=True,
    help="Detect and report gaps",
)
@click.option(
    "--threshold",
    default="5m",
    help="Gap detection threshold (e.g., 5m, 1h, 30s)",
)
@click.option(
    "--output", "-o",
    "output_table",
    help="Save unified timeline to this table",
)
@click.option(
    "--interval",
    default="1h",
    help="Histogram interval (e.g., 1h, 30m)",
)
def timeline(
    db_path: Path,
    start: datetime | None,
    end: datetime | None,
    tables: tuple[str, ...],
    timestamp_column: str,
    gaps: bool,
    threshold: str,
    output_table: str | None,
    interval: str,
):
    """Merge events from multiple sources into unified chronology.

    Shows timeline summary with event density histogram.
    """
    try:
        # Parse threshold
        threshold_td = parse_duration(threshold)
        interval_td = parse_duration(interval)
        interval_hours = max(1, int(interval_td.total_seconds() / 3600))

        # Merge timelines
        df = merge_timelines(
            str(db_path),
            tables=list(tables) if tables else None,
            timestamp_column=timestamp_column,
            start=start,
            end=end,
        )

        if df.is_empty():
            console("No timeline data found")
            return

        # Show summary
        summary = format_timeline_summary(
            df,
            timestamp_column,
            interval_hours=interval_hours,
        )
        console(summary)

        # Detect gaps if requested
        if gaps:
            console("")
            detected_gaps = detect_gaps(
                df,
                threshold_td,
                timestamp_column,
                source_column="_timeline_source",
            )
            console(format_gaps_summary(detected_gaps, threshold_td))

        # Save to table if requested
        if output_table:
            with connect(db_path) as conn:
                from vault_toolkit.core.db import polars_to_table
                polars_to_table(conn, df, output_table)
            console(f"\nSaved {len(df):,} events to table: {output_table}")

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
