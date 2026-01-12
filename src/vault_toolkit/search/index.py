"""Full-text search implementation using DuckDB."""

import re
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, list_tables, query_to_polars


def search(
    db_path: str,
    query: str,
    *,
    tables: list[str] | None = None,
    fields: list[str] | None = None,
    regex: bool = False,
    case_sensitive: bool = False,
    limit: int = 100,
    context: int = 0,
) -> pl.DataFrame:
    """Search across all tables in the database.

    Args:
        db_path: Path to DuckDB database.
        query: Search query (text or regex).
        tables: Tables to search. If None, search all.
        fields: Fields to search. If None, search all text fields.
        regex: Whether to treat query as regex.
        case_sensitive: Whether search is case-sensitive.
        limit: Maximum results per table.
        context: Number of characters of context to show.

    Returns:
        DataFrame with search results.
    """
    results = []

    with connect(db_path) as conn:
        if tables is None:
            tables = list_tables(conn)

        for table in tables:
            df = search_table(
                conn,
                table,
                query,
                fields=fields,
                regex=regex,
                case_sensitive=case_sensitive,
                limit=limit,
                context=context,
            )
            if not df.is_empty():
                results.append(df)

    if not results:
        return pl.DataFrame(
            schema={"_table": pl.Utf8, "_field": pl.Utf8, "_match": pl.Utf8, "_row": pl.Int64}
        )

    return pl.concat(results)


def search_table(
    conn: Any,
    table: str,
    query: str,
    *,
    fields: list[str] | None = None,
    regex: bool = False,
    case_sensitive: bool = False,
    limit: int = 100,
    context: int = 0,
) -> pl.DataFrame:
    """Search within a single table.

    Args:
        conn: DuckDB connection.
        table: Table name to search.
        query: Search query.
        fields: Fields to search. If None, search all text fields.
        regex: Whether to treat query as regex.
        case_sensitive: Whether search is case-sensitive.
        limit: Maximum results.
        context: Number of characters of context to show.

    Returns:
        DataFrame with search results.
    """
    # Get table schema to find text columns
    schema_query = f"DESCRIBE {table}"
    schema = conn.execute(schema_query).fetchall()

    text_columns = []
    for col_name, col_type, *_ in schema:
        if "VARCHAR" in col_type.upper() or "TEXT" in col_type.upper():
            if fields is None or col_name in fields:
                text_columns.append(col_name)

    if not text_columns:
        return pl.DataFrame()

    # Build search query
    results = []

    for column in text_columns:
        if regex:
            match_expr = _build_regex_match(column, query, case_sensitive)
        else:
            match_expr = _build_text_match(column, query, case_sensitive)

        sql = f"""
            SELECT
                '{table}' as _table,
                '{column}' as _field,
                {column} as _match,
                rowid as _row
            FROM {table}
            WHERE {match_expr}
            LIMIT {limit}
        """

        try:
            df = query_to_polars(conn, sql)
            if not df.is_empty():
                # Add context if requested
                if context > 0:
                    df = _add_context(df, query, context, regex, case_sensitive)
                results.append(df)
        except Exception:
            # Skip columns that can't be searched
            continue

    if not results:
        return pl.DataFrame()

    return pl.concat(results)


def search_regex(
    db_path: str,
    pattern: str,
    *,
    tables: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = 100,
) -> pl.DataFrame:
    """Search using a regex pattern.

    Args:
        db_path: Path to DuckDB database.
        pattern: Regex pattern.
        tables: Tables to search.
        fields: Fields to search.
        limit: Maximum results.

    Returns:
        DataFrame with search results.
    """
    return search(
        db_path,
        pattern,
        tables=tables,
        fields=fields,
        regex=True,
        limit=limit,
    )


def _build_text_match(column: str, query: str, case_sensitive: bool) -> str:
    """Build a text match SQL expression."""
    escaped = query.replace("'", "''")
    if case_sensitive:
        return f"{column} LIKE '%{escaped}%'"
    else:
        return f"LOWER({column}) LIKE LOWER('%{escaped}%')"


def _build_regex_match(column: str, pattern: str, case_sensitive: bool) -> str:
    """Build a regex match SQL expression."""
    escaped = pattern.replace("'", "''")
    if case_sensitive:
        return f"regexp_matches({column}, '{escaped}')"
    else:
        return f"regexp_matches({column}, '{escaped}', 'i')"


def _add_context(
    df: pl.DataFrame,
    query: str,
    context: int,
    regex: bool,
    case_sensitive: bool,
) -> pl.DataFrame:
    """Add context around matches."""

    def extract_context(text: str) -> str:
        if text is None:
            return ""

        flags = 0 if case_sensitive else re.IGNORECASE
        if regex:
            pattern = query
        else:
            pattern = re.escape(query)

        match = re.search(pattern, text, flags)
        if not match:
            return text[:context * 2] + "..." if len(text) > context * 2 else text

        start = max(0, match.start() - context)
        end = min(len(text), match.end() + context)

        result = ""
        if start > 0:
            result += "..."
        result += text[start:end]
        if end < len(text):
            result += "..."

        return result

    return df.with_columns(
        pl.col("_match").map_elements(extract_context, return_dtype=pl.Utf8).alias("_context")
    )
