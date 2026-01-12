"""Entity extraction from tables and text."""

from typing import Any
import uuid

import polars as pl

from vault_toolkit.core.db import connect, polars_to_table, query_to_polars, table_exists
from vault_toolkit.core.config import load_config
from vault_toolkit.core.types import Entity
from vault_toolkit.extract.patterns import (
    compile_patterns,
    extract_with_pattern,
    BUILTIN_PATTERNS,
)


def extract_entities(
    db_path: str,
    table: str,
    field: str,
    config_path: str | None = None,
    *,
    patterns: dict[str, str] | None = None,
    output_table: str = "entities",
) -> int:
    """Extract entities from a table field and store them.

    Args:
        db_path: Path to DuckDB database.
        table: Source table name.
        field: Field to extract from.
        config_path: Path to extraction config file.
        patterns: Direct pattern definitions (alternative to config).
        output_table: Name of output table for entities.

    Returns:
        Number of entities extracted.
    """
    # Load patterns
    if config_path:
        config = load_config(config_path)
    elif patterns:
        config = {"entities": patterns}
    else:
        # Use all builtin patterns
        config = {"entities": {k: {"pattern": v} for k, v in BUILTIN_PATTERNS.items()}}

    compiled = compile_patterns(config)

    with connect(db_path) as conn:
        # Get source data
        df = query_to_polars(conn, f"SELECT rowid as _row, {field} FROM {table}")

        if df.is_empty():
            return 0

        # Extract entities
        entities = []
        for row in df.iter_rows(named=True):
            text = row[field]
            row_id = row["_row"]

            if not text:
                continue

            for name, (pattern, pattern_config) in compiled.items():
                extracted = extract_with_pattern(str(text), pattern, pattern_config)
                for entity in extracted:
                    entities.append({
                        "id": str(uuid.uuid4()),
                        "entity_type": entity["entity_type"],
                        "value": entity["value"],
                        "source_table": table,
                        "source_field": field,
                        "source_row": row_id,
                    })

        if not entities:
            return 0

        # Create entities DataFrame
        entities_df = pl.DataFrame(entities)

        # Append or create table
        if table_exists(conn, output_table):
            polars_to_table(conn, entities_df, output_table, replace=False)
        else:
            polars_to_table(conn, entities_df, output_table, replace=True)

        return len(entities)


def extract_from_table(
    conn: Any,
    table: str,
    fields: list[str],
    patterns: dict[str, tuple],
) -> pl.DataFrame:
    """Extract entities from multiple fields in a table.

    Args:
        conn: DuckDB connection.
        table: Source table name.
        fields: Fields to extract from.
        patterns: Compiled patterns from compile_patterns().

    Returns:
        DataFrame with extracted entities.
    """
    # Build field selection
    field_list = ", ".join(fields)
    df = query_to_polars(conn, f"SELECT rowid as _row, {field_list} FROM {table}")

    if df.is_empty():
        return pl.DataFrame()

    entities = []
    for row in df.iter_rows(named=True):
        row_id = row["_row"]

        for field in fields:
            text = row.get(field)
            if not text:
                continue

            for name, (pattern, pattern_config) in patterns.items():
                extracted = extract_with_pattern(str(text), pattern, pattern_config)
                for entity in extracted:
                    entities.append({
                        "id": str(uuid.uuid4()),
                        "entity_type": entity["entity_type"],
                        "value": entity["value"],
                        "source_table": table,
                        "source_field": field,
                        "source_row": row_id,
                        "position_start": entity["start"],
                        "position_end": entity["end"],
                    })

    if not entities:
        return pl.DataFrame(schema={
            "id": pl.Utf8,
            "entity_type": pl.Utf8,
            "value": pl.Utf8,
            "source_table": pl.Utf8,
            "source_field": pl.Utf8,
            "source_row": pl.Int64,
            "position_start": pl.Int64,
            "position_end": pl.Int64,
        })

    return pl.DataFrame(entities)


def aggregate_entities(
    db_path: str,
    entity_table: str = "entities",
) -> pl.DataFrame:
    """Aggregate entity counts by type and value.

    Args:
        db_path: Path to DuckDB database.
        entity_table: Name of entities table.

    Returns:
        DataFrame with entity type, value, and count.
    """
    with connect(db_path) as conn:
        return query_to_polars(conn, f"""
            SELECT
                entity_type,
                value,
                COUNT(*) as count,
                COUNT(DISTINCT source_table) as source_count
            FROM {entity_table}
            GROUP BY entity_type, value
            ORDER BY count DESC
        """)


def get_entity_sources(
    db_path: str,
    entity_value: str,
    entity_table: str = "entities",
) -> pl.DataFrame:
    """Get all source locations for an entity.

    Args:
        db_path: Path to DuckDB database.
        entity_value: Entity value to look up.
        entity_table: Name of entities table.

    Returns:
        DataFrame with source information.
    """
    with connect(db_path) as conn:
        return query_to_polars(conn, f"""
            SELECT
                source_table,
                source_field,
                source_row,
                entity_type
            FROM {entity_table}
            WHERE value = ?
        """.replace("?", f"'{entity_value}'"))
