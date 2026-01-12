"""CLI for vt-correlate."""

from datetime import timedelta
from pathlib import Path

import click

from vault_toolkit.core.output import console, markdown_table
from vault_toolkit.correlate.rules import (
    load_rules,
    run_correlation_rules,
    correlate_entity,
    CorrelationRule,
)
from vault_toolkit.correlate.temporal import correlate_temporal


def parse_duration(value: str) -> timedelta:
    """Parse a duration string like '5m', '1h', '30s'."""
    unit = value[-1].lower()
    amount = int(value[:-1])

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
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Correlation rules configuration file (TOML)",
)
@click.option(
    "--entity", "-e",
    help="Find correlations for a specific entity",
)
@click.option(
    "--window", "-w",
    default="10m",
    help="Time window for temporal correlation",
)
@click.option(
    "--source", "-s",
    "source_table",
    help="Source table for ad-hoc correlation",
)
@click.option(
    "--target", "-t",
    "target_table",
    help="Target table for ad-hoc correlation",
)
@click.option(
    "--output", "-o",
    "output_table",
    default="correlations",
    help="Output table name",
)
@click.option(
    "--limit", "-l",
    default=50,
    type=int,
    help="Maximum results to display",
)
def correlate(
    db_path: Path,
    config_path: Path | None,
    entity: str | None,
    window: str,
    source_table: str | None,
    target_table: str | None,
    output_table: str,
    limit: int,
):
    """Find relationships between entities and events.

    Supports temporal proximity, spatial proximity, and co-occurrence.
    """
    try:
        time_window = parse_duration(window)

        # Entity-specific correlation
        if entity:
            df = correlate_entity(
                str(db_path),
                entity,
                time_window=time_window,
            )
            if df.is_empty():
                console(f"No correlations found for entity: {entity}")
                return

            console(f"Correlations for entity '{entity}':")
            console(markdown_table(df.head(limit)))
            return

        # Config-based correlation
        if config_path:
            rules = load_rules(str(config_path))
            df = run_correlation_rules(
                str(db_path),
                rules,
                output_table=output_table,
            )

            if df.is_empty():
                console("No correlations found")
                return

            console(f"Found {len(df):,} correlations from {len(rules)} rules")
            console(f"Saved to table: {output_table}\n")

            # Show summary by rule
            summary = df.group_by("rule_name").agg([
                pl.len().alias("count"),
                pl.col("score").mean().alias("avg_score"),
            ]).sort("count", descending=True)

            console("Correlations by rule:")
            console(markdown_table(summary))
            return

        # Ad-hoc temporal correlation
        if source_table and target_table:
            rule = CorrelationRule(
                name="adhoc",
                source_table=source_table,
                target_table=target_table,
                rule_type="temporal",
                time_window=time_window,
            )

            df = run_correlation_rules(
                str(db_path),
                [rule],
                output_table=output_table,
            )

            if df.is_empty():
                console(f"No correlations found between {source_table} and {target_table}")
                return

            console(f"Found {len(df):,} correlations")
            console(f"Saved to table: {output_table}\n")
            console(markdown_table(df.head(limit)))
            return

        # No valid options
        console("Specify --config, --entity, or both --source and --target", error=True)
        raise SystemExit(1)

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)


# Import for group_by
import polars as pl
