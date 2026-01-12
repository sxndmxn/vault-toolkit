"""CLI for vt-anomaly."""

from datetime import timedelta
from pathlib import Path

import click
import polars as pl

from vault_toolkit.core.db import connect, polars_to_table
from vault_toolkit.core.output import console
from vault_toolkit.core.config import load_config
from vault_toolkit.core.types import Severity
from vault_toolkit.anomaly.statistical import detect_statistical_anomalies
from vault_toolkit.anomaly.behavioral import detect_behavioral_anomalies
from vault_toolkit.anomaly.sequence import detect_sequence_anomalies


def parse_duration(value: str) -> timedelta:
    """Parse a duration string like '5m', '1h', '7d'."""
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
    "--table", "-t",
    required=True,
    help="Table to analyze",
)
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Anomaly detection configuration file (TOML)",
)
@click.option(
    "--method", "-m",
    type=click.Choice(["zscore", "iqr", "isolation_forest", "behavioral", "sequence"]),
    default="zscore",
    help="Detection method",
)
@click.option(
    "--feature", "-f",
    "features",
    multiple=True,
    help="Features to analyze (for statistical methods)",
)
@click.option(
    "--entity", "-e",
    "entity_column",
    help="Entity column for grouping",
)
@click.option(
    "--baseline",
    default="7d",
    help="Baseline window for behavioral detection",
)
@click.option(
    "--threshold",
    default=3.0,
    type=float,
    help="Threshold for anomaly detection",
)
@click.option(
    "--output", "-o",
    "output_table",
    default="anomalies",
    help="Output table name",
)
@click.option(
    "--severity",
    type=click.Choice(["LOW", "MED", "HIGH", "CRIT"]),
    help="Filter by minimum severity",
)
def anomaly(
    db_path: Path,
    table: str,
    config_path: Path | None,
    method: str,
    features: tuple[str, ...],
    entity_column: str | None,
    baseline: str,
    threshold: float,
    output_table: str,
    severity: str | None,
):
    """Detect statistical and behavioral anomalies.

    Supports z-score, IQR, isolation forest, behavioral baseline,
    and sequence anomaly detection.
    """
    try:
        # Load config if provided
        if config_path:
            config = load_config(str(config_path))
            detection_config = config.get("detection", {})
        else:
            detection_config = {}

        results = []

        # Statistical methods
        if method in ("zscore", "iqr", "isolation_forest"):
            feature_list = list(features) if features else detection_config.get("features", [])
            if not feature_list:
                console("Error: Specify features with --feature or in config", error=True)
                raise SystemExit(1)

            stats_results = detect_statistical_anomalies(
                str(db_path),
                table,
                feature_list,
                method=method,
                threshold=threshold,
                entity_column=entity_column,
            )
            results.extend(stats_results)

        # Behavioral detection
        elif method == "behavioral":
            baseline_window = parse_duration(baseline)
            behav_config = detection_config.get("behavioral", {})

            behav_results = detect_behavioral_anomalies(
                str(db_path),
                table,
                entity_column=entity_column,
                baseline_window=baseline_window,
                deviation_threshold=behav_config.get("deviation_threshold", threshold),
            )
            results.extend(behav_results)

        # Sequence detection
        elif method == "sequence":
            seq_config = detection_config.get("sequence", {})
            type_column = seq_config.get("type_column", "type")
            expected = seq_config.get("expected_patterns")

            seq_results = detect_sequence_anomalies(
                str(db_path),
                table,
                type_column,
                entity_column=entity_column,
                expected_patterns=expected,
                flag_unexpected=seq_config.get("flag_unexpected", True),
            )
            results.extend(seq_results)

        if not results:
            console("No anomalies detected")
            return

        # Filter by severity
        if severity:
            min_severity = Severity[severity]
            severity_order = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
            results = [r for r in results if severity_order.get(r.severity, 0) >= severity_order.get(min_severity, 0)]

        if not results:
            console(f"No anomalies at or above {severity} severity")
            return

        # Convert to DataFrame and save
        anomaly_data = []
        for r in results:
            anomaly_data.append({
                "timestamp": r.timestamp,
                "entity_id": r.entity_id,
                "severity": r.severity.value,
                "anomaly_type": r.anomaly_type,
                "description": r.description,
                "score": r.score,
            })

        df = pl.DataFrame(anomaly_data)

        with connect(db_path) as conn:
            polars_to_table(conn, df, output_table)

        console(f"Detected {len(results)} anomalies")
        console(f"Saved to table: {output_table}\n")

        # Display results grouped by severity
        for sev in [Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            sev_results = [r for r in results if r.severity == sev]
            if sev_results:
                console(f"\n{sev.value} ({len(sev_results)}):")
                for r in sev_results[:10]:
                    ts_str = r.timestamp.isoformat() if r.timestamp else "N/A"
                    entity_str = f" [{r.entity_id}]" if r.entity_id else ""
                    console(f"  {ts_str}{entity_str}")
                    console(f"    {r.description}")

                if len(sev_results) > 10:
                    console(f"    ... and {len(sev_results) - 10} more")

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
