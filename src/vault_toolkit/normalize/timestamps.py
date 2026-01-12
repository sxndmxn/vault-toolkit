"""Timestamp normalization utilities."""

from datetime import datetime, timezone
from typing import Any

import polars as pl


# Common timestamp formats to try
COMMON_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y%m%d%H%M%S",
    "%Y%m%d",
]


def parse_timestamp(
    value: Any,
    *,
    format: str | None = None,
    tz: str | None = None,
) -> datetime | None:
    """Parse a timestamp value into a datetime.

    Args:
        value: Value to parse (string, int, float, or datetime).
        format: Explicit format string. Special values:
            - 'epoch': Unix seconds
            - 'epoch_ms': Unix milliseconds
            - 'epoch_us': Unix microseconds
            - 'epoch_ns': Unix nanoseconds
            - 'auto': Try common formats
            - strftime format string
        tz: Timezone to localize naive datetimes to.

    Returns:
        Parsed datetime, or None if parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return _localize(value, tz)

    # Handle epoch timestamps
    if format in ("epoch", "epoch_ms", "epoch_us", "epoch_ns"):
        return _parse_epoch(value, format, tz)

    # Handle string timestamps
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # Try explicit format first
        if format and format != "auto":
            try:
                dt = datetime.strptime(value, format)
                return _localize(dt, tz)
            except ValueError:
                return None

        # Try common formats
        for fmt in COMMON_FORMATS:
            try:
                dt = datetime.strptime(value, fmt)
                return _localize(dt, tz)
            except ValueError:
                continue

        return None

    # Handle numeric values (assume epoch if no format)
    if isinstance(value, (int, float)):
        return _parse_epoch(value, format or "epoch", tz)

    return None


def _parse_epoch(value: Any, format: str, tz: str | None) -> datetime | None:
    """Parse an epoch timestamp."""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None

    divisors = {
        "epoch": 1,
        "epoch_ms": 1000,
        "epoch_us": 1_000_000,
        "epoch_ns": 1_000_000_000,
    }
    divisor = divisors.get(format, 1)
    ts = ts / divisor

    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return _localize(dt, tz)
    except (OSError, OverflowError, ValueError):
        return None


def _localize(dt: datetime, tz: str | None) -> datetime:
    """Localize a datetime to a timezone."""
    if tz is None:
        return dt
    if dt.tzinfo is None:
        # Naive datetime - assume it's in the target timezone
        from zoneinfo import ZoneInfo

        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def normalize_timestamp(
    df: pl.DataFrame,
    column: str,
    *,
    format: str | None = None,
    tz: str | None = None,
    output_column: str | None = None,
) -> pl.DataFrame:
    """Normalize a timestamp column in a DataFrame.

    Args:
        df: Input DataFrame.
        column: Column name containing timestamps.
        format: Timestamp format (see parse_timestamp).
        tz: Timezone to normalize to.
        output_column: Output column name. If None, overwrites input column.

    Returns:
        DataFrame with normalized timestamp column.
    """
    if output_column is None:
        output_column = column

    if column not in df.columns:
        return df

    # Check if already datetime
    if df[column].dtype in (pl.Datetime, pl.Date):
        if output_column != column:
            return df.with_columns(pl.col(column).alias(output_column))
        return df

    # Handle epoch formats with Polars native functions
    if format in ("epoch", "epoch_ms", "epoch_us", "epoch_ns"):
        time_units = {
            "epoch": "s",
            "epoch_ms": "ms",
            "epoch_us": "us",
            "epoch_ns": "ns",
        }
        unit = time_units[format]
        return df.with_columns(
            pl.from_epoch(pl.col(column), time_unit=unit).alias(output_column)
        )

    # Handle string timestamps with explicit format
    if format and format != "auto":
        return df.with_columns(
            pl.col(column).str.strptime(pl.Datetime, format).alias(output_column)
        )

    # Auto-detect format - try common patterns
    for fmt in COMMON_FORMATS:
        try:
            result = df.with_columns(
                pl.col(column).str.strptime(pl.Datetime, fmt).alias(output_column)
            )
            # Check if any values parsed successfully
            if result[output_column].null_count() < len(result):
                return result
        except Exception:
            continue

    # Fall back to keeping original if all parsing fails
    if output_column != column:
        return df.with_columns(pl.col(column).alias(output_column))
    return df
