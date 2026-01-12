"""Statistical anomaly detection methods."""

from typing import Any

import polars as pl
import numpy as np

from vault_toolkit.core.db import connect, query_to_polars
from vault_toolkit.core.types import AnomalyResult, Severity


def detect_statistical_anomalies(
    db_path: str,
    table: str,
    features: list[str],
    *,
    method: str = "zscore",
    threshold: float = 3.0,
    contamination: float = 0.05,
    timestamp_column: str | None = "timestamp",
    entity_column: str | None = None,
) -> list[AnomalyResult]:
    """Detect statistical anomalies in data.

    Args:
        db_path: Path to DuckDB database.
        table: Table to analyze.
        features: Columns to use for anomaly detection.
        method: Detection method ('zscore', 'iqr', 'isolation_forest').
        threshold: Threshold for zscore/iqr methods.
        contamination: Expected proportion of outliers (for isolation forest).
        timestamp_column: Column containing timestamps.
        entity_column: Column containing entity identifiers.

    Returns:
        List of AnomalyResult objects.
    """
    with connect(db_path) as conn:
        # Load data
        columns = features.copy()
        if timestamp_column and timestamp_column not in columns:
            columns.append(timestamp_column)
        if entity_column and entity_column not in columns:
            columns.append(entity_column)

        col_str = ", ".join(columns)
        df = query_to_polars(conn, f"SELECT rowid, {col_str} FROM {table}")

        if df.is_empty():
            return []

        # Apply detection method
        if method == "zscore":
            anomaly_mask = zscore_anomalies(df, features, threshold)
        elif method == "iqr":
            anomaly_mask = iqr_anomalies(df, features, threshold)
        elif method == "isolation_forest":
            anomaly_mask = isolation_forest_anomalies(df, features, contamination)
        else:
            raise ValueError(f"Unknown method: {method}")

        # Build results
        results = []
        anomaly_rows = df.filter(anomaly_mask)

        for row in anomaly_rows.iter_rows(named=True):
            # Calculate severity based on deviation
            severity = _calculate_severity(row, df, features, method)

            # Build description
            desc_parts = []
            for feat in features:
                val = row.get(feat)
                if val is not None:
                    mean = df[feat].mean()
                    std = df[feat].std()
                    if std and std > 0:
                        zscore = abs((val - mean) / std)
                        desc_parts.append(f"{feat}={val:.2f} (z={zscore:.1f})")
                    else:
                        desc_parts.append(f"{feat}={val:.2f}")

            timestamp = row.get(timestamp_column) if timestamp_column else None
            entity_id = row.get(entity_column) if entity_column else None

            results.append(AnomalyResult(
                timestamp=timestamp,
                entity_id=str(entity_id) if entity_id else None,
                severity=severity,
                anomaly_type="statistical",
                description=f"Statistical outlier: {', '.join(desc_parts)}",
                score=_calculate_score(row, df, features),
                metadata={"method": method, "features": features},
            ))

        return results


def zscore_anomalies(
    df: pl.DataFrame,
    features: list[str],
    threshold: float = 3.0,
) -> pl.Series:
    """Detect anomalies using z-score method.

    Args:
        df: DataFrame to analyze.
        features: Columns to use.
        threshold: Z-score threshold.

    Returns:
        Boolean Series indicating anomalies.
    """
    # Calculate z-scores for each feature
    conditions = []
    for feat in features:
        if feat not in df.columns:
            continue

        col = df[feat]
        if col.dtype not in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            continue

        mean = col.mean()
        std = col.std()

        if std is None or std == 0:
            continue

        zscore = ((col - mean) / std).abs()
        conditions.append(zscore > threshold)

    if not conditions:
        return pl.Series([False] * len(df))

    # Any feature exceeding threshold
    result = conditions[0]
    for cond in conditions[1:]:
        result = result | cond

    return result


def iqr_anomalies(
    df: pl.DataFrame,
    features: list[str],
    threshold: float = 1.5,
) -> pl.Series:
    """Detect anomalies using IQR method.

    Args:
        df: DataFrame to analyze.
        features: Columns to use.
        threshold: IQR multiplier (1.5 = standard, 3.0 = extreme).

    Returns:
        Boolean Series indicating anomalies.
    """
    conditions = []
    for feat in features:
        if feat not in df.columns:
            continue

        col = df[feat]
        if col.dtype not in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            continue

        q1 = col.quantile(0.25)
        q3 = col.quantile(0.75)

        if q1 is None or q3 is None:
            continue

        iqr = q3 - q1
        lower = q1 - threshold * iqr
        upper = q3 + threshold * iqr

        conditions.append((col < lower) | (col > upper))

    if not conditions:
        return pl.Series([False] * len(df))

    result = conditions[0]
    for cond in conditions[1:]:
        result = result | cond

    return result


def isolation_forest_anomalies(
    df: pl.DataFrame,
    features: list[str],
    contamination: float = 0.05,
) -> pl.Series:
    """Detect anomalies using Isolation Forest.

    Args:
        df: DataFrame to analyze.
        features: Columns to use.
        contamination: Expected proportion of outliers.

    Returns:
        Boolean Series indicating anomalies.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        # Fall back to z-score if sklearn not available
        return zscore_anomalies(df, features, threshold=3.0)

    # Prepare feature matrix
    valid_features = []
    for feat in features:
        if feat in df.columns and df[feat].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            valid_features.append(feat)

    if not valid_features:
        return pl.Series([False] * len(df))

    X = df.select(valid_features).to_numpy()

    # Handle missing values
    X = np.nan_to_num(X, nan=0.0)

    # Fit isolation forest
    clf = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    predictions = clf.fit_predict(X)

    # -1 indicates anomaly
    return pl.Series(predictions == -1)


def _calculate_severity(
    row: dict[str, Any],
    df: pl.DataFrame,
    features: list[str],
    method: str,
) -> Severity:
    """Calculate severity based on how extreme the anomaly is."""
    max_zscore = 0.0

    for feat in features:
        val = row.get(feat)
        if val is None:
            continue

        mean = df[feat].mean()
        std = df[feat].std()

        if std and std > 0:
            zscore = abs((val - mean) / std)
            max_zscore = max(max_zscore, zscore)

    if max_zscore >= 5.0:
        return Severity.HIGH
    elif max_zscore >= 4.0:
        return Severity.MEDIUM
    else:
        return Severity.LOW


def _calculate_score(
    row: dict[str, Any],
    df: pl.DataFrame,
    features: list[str],
) -> float:
    """Calculate anomaly score (higher = more anomalous)."""
    total_zscore = 0.0
    count = 0

    for feat in features:
        val = row.get(feat)
        if val is None:
            continue

        mean = df[feat].mean()
        std = df[feat].std()

        if std and std > 0:
            zscore = abs((val - mean) / std)
            total_zscore += zscore
            count += 1

    return total_zscore / count if count > 0 else 0.0
