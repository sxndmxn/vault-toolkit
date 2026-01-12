"""Data ingestion logic."""

import hashlib
from pathlib import Path
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, polars_to_table, table_exists
from vault_toolkit.core.config import load_config, get_nested
from vault_toolkit.normalize.parsers import parse_file, detect_format
from vault_toolkit.normalize.timestamps import normalize_timestamp


def ingest_files(
    input_path: str | Path,
    db_path: str | Path,
    config_path: str | Path | None = None,
    *,
    table_name: str | None = None,
    deduplicate: bool = True,
    tag_source: bool = True,
) -> dict[str, int]:
    """Ingest files from a directory into DuckDB.

    Args:
        input_path: Path to input file or directory.
        db_path: Path to DuckDB database.
        config_path: Optional path to config file.
        table_name: Target table name. If None, derived from config or filename.
        deduplicate: Whether to remove duplicate rows.
        tag_source: Whether to add source file column.

    Returns:
        Dictionary mapping table names to row counts.
    """
    input_path = Path(input_path)
    config = load_config(config_path) if config_path else {}

    results: dict[str, int] = {}

    if input_path.is_file():
        files = [input_path]
    else:
        # Get all files matching patterns from config, or all files
        patterns = get_nested(config, "input", "patterns", default=["*"])
        if isinstance(patterns, str):
            patterns = [patterns]

        files = []
        for pattern in patterns:
            files.extend(input_path.glob(pattern))
        files = [f for f in files if f.is_file()]

    # Group files by source config
    sources = get_nested(config, "sources", default={})

    with connect(db_path) as conn:
        for file_path in files:
            # Find matching source config
            source_config = _find_source_config(file_path, sources)
            source_name = source_config.get("name", file_path.stem)
            target_table = table_name or source_config.get("table", source_name)

            # Parse file
            df = _parse_with_config(file_path, source_config)

            if df.is_empty():
                continue

            # Tag source
            if tag_source:
                df = df.with_columns(
                    pl.lit(str(file_path)).alias("_source_file"),
                    pl.lit(source_name).alias("_source"),
                )

            # Normalize timestamps
            ts_field = source_config.get("timestamp_field")
            ts_format = source_config.get("timestamp_format")
            if ts_field and ts_field in df.columns:
                df = normalize_timestamp(df, ts_field, format=ts_format)

            # Deduplicate
            if deduplicate:
                df = _deduplicate(df, source_config)

            # Write to table
            if table_exists(conn, target_table):
                # Append mode - align schemas
                existing = conn.execute(f"SELECT * FROM {target_table} LIMIT 0").pl()
                df = _align_schema(df, existing)
                polars_to_table(conn, df, target_table, replace=False)
            else:
                polars_to_table(conn, df, target_table, replace=True)

            # Update results
            results[target_table] = results.get(target_table, 0) + len(df)

    return results


def ingest_source(
    source_name: str,
    input_path: str | Path,
    db_path: str | Path,
    config: dict[str, Any],
) -> int:
    """Ingest a single source with explicit config.

    Args:
        source_name: Name of the source.
        input_path: Path to input file or directory.
        db_path: Path to DuckDB database.
        config: Source configuration dictionary.

    Returns:
        Number of rows ingested.
    """
    input_path = Path(input_path)
    pattern = config.get("pattern", "*")

    if input_path.is_file():
        files = [input_path]
    else:
        files = list(input_path.glob(pattern))

    total_rows = 0
    table_name = config.get("table", source_name)

    with connect(db_path) as conn:
        for file_path in files:
            df = _parse_with_config(file_path, config)

            if df.is_empty():
                continue

            # Tag source
            df = df.with_columns(
                pl.lit(str(file_path)).alias("_source_file"),
                pl.lit(source_name).alias("_source"),
            )

            # Normalize timestamp
            ts_field = config.get("timestamp_field")
            ts_format = config.get("timestamp_format")
            if ts_field and ts_field in df.columns:
                df = normalize_timestamp(df, ts_field, format=ts_format)

            # Deduplicate
            if config.get("deduplicate", True):
                df = _deduplicate(df, config)

            # Write
            if table_exists(conn, table_name):
                polars_to_table(conn, df, table_name, replace=False)
            else:
                polars_to_table(conn, df, table_name, replace=True)

            total_rows += len(df)

    return total_rows


def _find_source_config(file_path: Path, sources: dict) -> dict:
    """Find the source config that matches a file."""
    for name, config in sources.items():
        pattern = config.get("pattern", "")
        if file_path.match(pattern):
            return {"name": name, **config}

    # Default config based on file type
    return {
        "name": file_path.stem,
        "parser": detect_format(file_path),
    }


def _parse_with_config(file_path: Path, config: dict) -> pl.DataFrame:
    """Parse a file using source config."""
    parser = config.get("parser", detect_format(file_path))

    kwargs: dict[str, Any] = {}

    if parser == "csv":
        kwargs["delimiter"] = config.get("delimiter", ",")
        kwargs["has_header"] = config.get("has_header", True)
    elif parser == "json":
        kwargs["json_path"] = config.get("json_path")
    elif parser == "xml":
        kwargs["record_tag"] = config.get("record_tag")
        kwargs["flatten"] = config.get("flatten", True)
    elif parser in ("regex", "text"):
        kwargs["pattern"] = config.get("regex", r"(?P<line>.*)")
        kwargs["encoding"] = config.get("encoding", "utf-8")

    return parse_file(file_path, parser=parser, **kwargs)


def _deduplicate(df: pl.DataFrame, config: dict) -> pl.DataFrame:
    """Deduplicate a DataFrame based on config."""
    dedup_columns = config.get("deduplicate_columns")

    if dedup_columns:
        return df.unique(subset=dedup_columns)

    # Default: hash all columns for deduplication
    # Exclude internal columns
    columns = [c for c in df.columns if not c.startswith("_")]
    if columns:
        return df.unique(subset=columns)

    return df


def _align_schema(df: pl.DataFrame, target: pl.DataFrame) -> pl.DataFrame:
    """Align DataFrame schema to match target."""
    # Add missing columns with nulls
    for col in target.columns:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    # Select only columns that exist in target
    return df.select(target.columns)
