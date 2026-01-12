"""Correlation rule engine."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, polars_to_table, table_exists
from vault_toolkit.core.config import load_config
from vault_toolkit.correlate.temporal import correlate_temporal
from vault_toolkit.correlate.spatial import correlate_spatial


@dataclass
class CorrelationRule:
    """A correlation rule configuration."""

    name: str
    source_table: str
    target_table: str
    rule_type: str  # 'temporal', 'spatial', 'cooccurrence'
    join_field: str | None = None
    time_window: timedelta | None = None
    time_direction: str = "both"
    spatial_field: str | None = None
    spatial_threshold: float | None = None
    score_weight: float = 1.0


def load_rules(config_path: str) -> list[CorrelationRule]:
    """Load correlation rules from config file.

    Args:
        config_path: Path to TOML config file.

    Returns:
        List of CorrelationRule objects.
    """
    config = load_config(config_path)
    rules = []

    for rule_config in config.get("rules", []):
        # Parse time window
        time_window = None
        if "time_window" in rule_config:
            time_window = _parse_timedelta(rule_config["time_window"])

        rule = CorrelationRule(
            name=rule_config.get("name", "unnamed"),
            source_table=rule_config["source_table"],
            target_table=rule_config["target_table"],
            rule_type=rule_config.get("type", "temporal"),
            join_field=rule_config.get("join_field"),
            time_window=time_window,
            time_direction=rule_config.get("time_direction", "both"),
            spatial_field=rule_config.get("spatial_field"),
            spatial_threshold=rule_config.get("spatial_threshold"),
            score_weight=rule_config.get("score_weight", 1.0),
        )
        rules.append(rule)

    return rules


def run_correlation_rules(
    db_path: str,
    rules: list[CorrelationRule],
    *,
    output_table: str = "correlations",
) -> pl.DataFrame:
    """Run correlation rules and aggregate results.

    Args:
        db_path: Path to DuckDB database.
        rules: List of correlation rules to run.
        output_table: Table to store results.

    Returns:
        DataFrame with all correlations.
    """
    all_correlations = []

    for rule in rules:
        try:
            if rule.rule_type == "temporal" and rule.time_window:
                df = correlate_temporal(
                    db_path,
                    rule.source_table,
                    rule.target_table,
                    join_field=rule.join_field,
                    time_window=rule.time_window,
                    direction=rule.time_direction,
                    score_weight=rule.score_weight,
                )
            elif rule.rule_type == "spatial" and rule.spatial_threshold:
                df = correlate_spatial(
                    db_path,
                    rule.source_table,
                    rule.target_table,
                    threshold_meters=rule.spatial_threshold,
                    score_weight=rule.score_weight,
                )
            elif rule.rule_type == "cooccurrence":
                df = correlate_cooccurrence(
                    db_path,
                    rule.source_table,
                    rule.target_table,
                    join_field=rule.join_field,
                    score_weight=rule.score_weight,
                )
            else:
                continue

            if not df.is_empty():
                df = df.with_columns(pl.lit(rule.name).alias("rule_name"))
                all_correlations.append(df)

        except Exception as e:
            # Log but continue with other rules
            print(f"Warning: Rule '{rule.name}' failed: {e}")
            continue

    if not all_correlations:
        return pl.DataFrame()

    # Combine all correlations
    combined = pl.concat(all_correlations, how="diagonal")

    # Save to database
    with connect(db_path) as conn:
        if table_exists(conn, output_table):
            polars_to_table(conn, combined, output_table, replace=False)
        else:
            polars_to_table(conn, combined, output_table, replace=True)

    return combined


def correlate_cooccurrence(
    db_path: str,
    source_table: str,
    target_table: str,
    *,
    join_field: str | None = None,
    score_weight: float = 1.0,
) -> pl.DataFrame:
    """Find co-occurrences between two tables.

    Args:
        db_path: Path to DuckDB database.
        source_table: Source table name.
        target_table: Target table name.
        join_field: Field to join on.
        score_weight: Weight for scores.

    Returns:
        DataFrame with co-occurrence correlations.
    """
    if not join_field:
        return pl.DataFrame()

    with connect(db_path) as conn:
        from vault_toolkit.core.db import query_to_polars

        sql = f"""
            SELECT
                s.rowid as source_row,
                t.rowid as target_row,
                s.{join_field} as join_value,
                {score_weight} as score,
                '{source_table}' as source_table,
                '{target_table}' as target_table,
                'cooccurrence' as correlation_type
            FROM {source_table} s
            JOIN {target_table} t ON s.{join_field} = t.{join_field}
        """

        return query_to_polars(conn, sql)


def correlate_entity(
    db_path: str,
    entity: str,
    *,
    time_window: timedelta | None = None,
    spatial_threshold: float | None = None,
) -> pl.DataFrame:
    """Find all correlations for a specific entity.

    Args:
        db_path: Path to DuckDB database.
        entity: Entity value to search for.
        time_window: Time window for temporal correlations.
        spatial_threshold: Distance threshold for spatial correlations.

    Returns:
        DataFrame with entity's correlations.
    """
    with connect(db_path) as conn:
        from vault_toolkit.core.db import query_to_polars, table_exists

        if not table_exists(conn, "entities") or not table_exists(conn, "correlations"):
            return pl.DataFrame()

        # Get entity's source records
        entity_sources = query_to_polars(conn, f"""
            SELECT source_table, source_row
            FROM entities
            WHERE value = '{entity}'
        """)

        if entity_sources.is_empty():
            return pl.DataFrame()

        # Find correlations involving those records
        source_conditions = []
        for row in entity_sources.iter_rows(named=True):
            source_conditions.append(
                f"(source_table = '{row['source_table']}' AND source_row = {row['source_row']})"
            )

        if not source_conditions:
            return pl.DataFrame()

        where_clause = " OR ".join(source_conditions)
        return query_to_polars(conn, f"""
            SELECT * FROM correlations
            WHERE {where_clause}
            ORDER BY score DESC
        """)


def _parse_timedelta(value: str) -> timedelta:
    """Parse a timedelta string like '5m', '1h', '30s'."""
    if not value:
        raise ValueError("Empty duration")

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
