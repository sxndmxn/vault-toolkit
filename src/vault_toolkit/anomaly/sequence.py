"""Sequence-based anomaly detection."""

from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars
from vault_toolkit.core.types import AnomalyResult, Severity


def detect_sequence_anomalies(
    db_path: str,
    table: str,
    type_column: str,
    *,
    timestamp_column: str = "timestamp",
    entity_column: str | None = None,
    expected_patterns: list[list[str]] | None = None,
    max_gap_seconds: int = 3600,
    flag_unexpected: bool = True,
) -> list[AnomalyResult]:
    """Detect anomalies in event sequences.

    Args:
        db_path: Path to DuckDB database.
        table: Table to analyze.
        type_column: Column containing event types.
        timestamp_column: Column containing timestamps.
        entity_column: Column to group sequences by.
        expected_patterns: List of expected type sequences.
        max_gap_seconds: Maximum gap between events in a sequence.
        flag_unexpected: Whether to flag sequences not in expected list.

    Returns:
        List of AnomalyResult objects.
    """
    with connect(db_path) as conn:
        # Extract sequences
        sequences = _extract_sequences(
            conn,
            table,
            type_column,
            timestamp_column,
            entity_column,
            max_gap_seconds,
        )

        if sequences.is_empty():
            return []

        results = []

        # Learn patterns if not provided
        if expected_patterns is None:
            learned_patterns = _learn_common_patterns(sequences)
        else:
            learned_patterns = [tuple(p) for p in expected_patterns]

        # Find unexpected sequences
        if flag_unexpected:
            for row in sequences.iter_rows(named=True):
                seq = tuple(row["sequence"])

                if not _matches_any_pattern(seq, learned_patterns):
                    entity_id = row.get("entity_id")
                    timestamp = row.get("sequence_start")

                    results.append(AnomalyResult(
                        timestamp=timestamp,
                        entity_id=str(entity_id) if entity_id else None,
                        severity=Severity.LOW,
                        anomaly_type="sequence",
                        description=f"Unexpected sequence: {' -> '.join(seq)}",
                        score=1.0,
                        metadata={
                            "sequence": list(seq),
                            "expected_patterns": [list(p) for p in learned_patterns[:5]],
                        },
                    ))

        return results


def find_unexpected_patterns(
    db_path: str,
    table: str,
    type_column: str,
    expected_patterns: list[list[str]],
    *,
    timestamp_column: str = "timestamp",
    entity_column: str | None = None,
    max_gap_seconds: int = 3600,
) -> pl.DataFrame:
    """Find sequences that don't match expected patterns.

    Args:
        db_path: Path to DuckDB database.
        table: Table to analyze.
        type_column: Column containing event types.
        expected_patterns: List of expected type sequences.
        timestamp_column: Column containing timestamps.
        entity_column: Column to group sequences by.
        max_gap_seconds: Maximum gap between events in a sequence.

    Returns:
        DataFrame with unexpected sequences.
    """
    with connect(db_path) as conn:
        sequences = _extract_sequences(
            conn,
            table,
            type_column,
            timestamp_column,
            entity_column,
            max_gap_seconds,
        )

        if sequences.is_empty():
            return sequences

        expected_tuples = [tuple(p) for p in expected_patterns]

        # Filter to unexpected sequences
        unexpected_mask = []
        for row in sequences.iter_rows(named=True):
            seq = tuple(row["sequence"])
            unexpected_mask.append(not _matches_any_pattern(seq, expected_tuples))

        return sequences.filter(pl.Series(unexpected_mask))


def _extract_sequences(
    conn: Any,
    table: str,
    type_column: str,
    timestamp_column: str,
    entity_column: str | None,
    max_gap_seconds: int,
) -> pl.DataFrame:
    """Extract event sequences from a table."""
    # Build partition and ordering
    if entity_column:
        partition_by = f"PARTITION BY {entity_column}"
        group_by = f", {entity_column}"
        select_entity = f"{entity_column} as entity_id,"
    else:
        partition_by = ""
        group_by = ""
        select_entity = "NULL as entity_id,"

    sql = f"""
        WITH ordered_events AS (
            SELECT
                {select_entity}
                {type_column} as event_type,
                {timestamp_column} as event_time,
                LAG({timestamp_column}) OVER ({partition_by} ORDER BY {timestamp_column}) as prev_time
            FROM {table}
            WHERE {timestamp_column} IS NOT NULL
              AND {type_column} IS NOT NULL
        ),
        sequenced AS (
            SELECT
                *,
                CASE
                    WHEN prev_time IS NULL THEN 1
                    WHEN EPOCH(event_time) - EPOCH(prev_time) > {max_gap_seconds} THEN 1
                    ELSE 0
                END as new_sequence
            FROM ordered_events
        ),
        with_seq_id AS (
            SELECT
                *,
                SUM(new_sequence) OVER ({partition_by} ORDER BY event_time) as sequence_id
            FROM sequenced
        )
        SELECT
            sequence_id,
            {select_entity.replace(',', '')}
            LIST(event_type ORDER BY event_time) as sequence,
            MIN(event_time) as sequence_start,
            MAX(event_time) as sequence_end,
            COUNT(*) as sequence_length
        FROM with_seq_id
        GROUP BY sequence_id{group_by}
        HAVING COUNT(*) >= 2
        ORDER BY sequence_start
    """

    return query_to_polars(conn, sql)


def _learn_common_patterns(
    sequences: pl.DataFrame,
    min_frequency: float = 0.05,
) -> list[tuple[str, ...]]:
    """Learn common patterns from observed sequences."""
    pattern_counts: dict[tuple, int] = {}

    for row in sequences.iter_rows(named=True):
        seq = tuple(row["sequence"])
        pattern_counts[seq] = pattern_counts.get(seq, 0) + 1

    total = len(sequences)
    if total == 0:
        return []

    # Return patterns above frequency threshold
    common = [
        pattern for pattern, count in pattern_counts.items()
        if count / total >= min_frequency
    ]

    # Sort by frequency (most common first)
    common.sort(key=lambda p: pattern_counts[p], reverse=True)

    return common


def _matches_any_pattern(
    sequence: tuple[str, ...],
    patterns: list[tuple[str, ...]],
) -> bool:
    """Check if a sequence matches any of the expected patterns."""
    if not patterns:
        return True  # No patterns = everything is expected

    for pattern in patterns:
        if _matches_pattern(sequence, pattern):
            return True

    return False


def _matches_pattern(
    sequence: tuple[str, ...],
    pattern: tuple[str, ...],
) -> bool:
    """Check if a sequence matches a pattern.

    Supports exact match and subsequence matching.
    """
    # Exact match
    if sequence == pattern:
        return True

    # Check if pattern is a subsequence
    if len(pattern) <= len(sequence):
        for i in range(len(sequence) - len(pattern) + 1):
            if sequence[i:i + len(pattern)] == pattern:
                return True

    return False
