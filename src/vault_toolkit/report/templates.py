"""Report template rendering."""

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars, list_tables, table_exists
from vault_toolkit.core.config import load_config
from vault_toolkit.core.output import markdown_table, ascii_histogram


def generate_report(
    db_path: str,
    template_path: str | None = None,
    *,
    title: str | None = None,
    sections: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a markdown report from database.

    Args:
        db_path: Path to DuckDB database.
        template_path: Path to report template (TOML).
        title: Report title (overrides template).
        sections: Section definitions (overrides template).

    Returns:
        Markdown report string.
    """
    # Load template
    if template_path:
        config = load_config(template_path)
        if title is None:
            title = config.get("title", "Analysis Report")
        if sections is None:
            sections = config.get("sections", [])
    else:
        if title is None:
            title = "Analysis Report"
        if sections is None:
            sections = []

    lines = [
        f"# {title}",
        "",
        f"*Generated: {datetime.now().isoformat()}*",
        "",
    ]

    with connect(db_path) as conn:
        for section in sections:
            section_content = render_section(conn, section)
            if section_content:
                lines.append(section_content)
                lines.append("")

    return "\n".join(lines)


def render_section(conn: Any, section: dict[str, Any]) -> str:
    """Render a single report section.

    Args:
        conn: DuckDB connection.
        section: Section definition dictionary.

    Returns:
        Markdown section string.
    """
    section_type = section.get("type", "table")
    section_name = section.get("name", "Section")

    lines = [f"## {section_name}", ""]

    try:
        if section_type == "table":
            content = _render_table_section(conn, section)
        elif section_type == "query":
            content = _render_query_section(conn, section)
        elif section_type == "timeline":
            content = _render_timeline_section(conn, section)
        elif section_type == "graph":
            content = _render_graph_section(conn, section)
        elif section_type == "auto_summary":
            content = _render_auto_summary(conn, section)
        elif section_type == "text":
            content = section.get("content", "")
        else:
            content = f"*Unknown section type: {section_type}*"

        lines.append(content)

    except Exception as e:
        lines.append(f"*Error rendering section: {e}*")

    return "\n".join(lines)


def _render_table_section(conn: Any, section: dict[str, Any]) -> str:
    """Render a table section."""
    source = section.get("source")
    query = section.get("query")
    filter_expr = section.get("filter")
    limit = section.get("limit", 50)

    if query:
        df = query_to_polars(conn, query)
    elif source and table_exists(conn, source):
        sql = f"SELECT * FROM {source}"
        if filter_expr:
            sql += f" WHERE {filter_expr}"
        sql += f" LIMIT {limit}"
        df = query_to_polars(conn, sql)
    else:
        return f"*Table not found: {source}*"

    if df.is_empty():
        return "*No data*"

    return markdown_table(df, max_rows=limit)


def _render_query_section(conn: Any, section: dict[str, Any]) -> str:
    """Render a custom query section."""
    query = section.get("query")
    if not query:
        return "*No query specified*"

    df = query_to_polars(conn, query)
    if df.is_empty():
        return "*No results*"

    return markdown_table(df)


def _render_timeline_section(conn: Any, section: dict[str, Any]) -> str:
    """Render a timeline section."""
    source = section.get("source", "unified_timeline")
    timestamp_col = section.get("timestamp_column", "timestamp")
    interval_hours = section.get("interval_hours", 1)

    if not table_exists(conn, source):
        return f"*Timeline table not found: {source}*"

    # Get event counts by hour
    sql = f"""
        SELECT
            date_trunc('hour', {timestamp_col}) as hour,
            COUNT(*) as events
        FROM {source}
        WHERE {timestamp_col} IS NOT NULL
        GROUP BY hour
        ORDER BY hour
        LIMIT 48
    """

    df = query_to_polars(conn, sql)
    if df.is_empty():
        return "*No timeline data*"

    # Build histogram
    values = []
    for row in df.iter_rows(named=True):
        hour = row["hour"]
        if hour:
            label = hour.strftime("%H:%M")
            values.append((label, row["events"]))

    if values:
        return f"```\n{ascii_histogram(values)}\n```"
    return "*No timeline data*"


def _render_graph_section(conn: Any, section: dict[str, Any]) -> str:
    """Render a graph section."""
    format_type = section.get("format", "ascii")
    center = section.get("center")
    depth = section.get("depth", 2)

    from vault_toolkit.graph.build import build_graph, build_graph_centered
    from vault_toolkit.graph.render import render_ascii, render_dot, render_summary

    # Build graph (need db_path, reconstruct from connection)
    # This is a simplification - in practice we'd need the db_path
    return "*Graph section requires db_path (use quick_report for graphs)*"


def _render_auto_summary(conn: Any, section: dict[str, Any]) -> str:
    """Render an automatic summary section."""
    tables = section.get("tables", [])
    lines = []

    # Database overview
    all_tables = list_tables(conn)
    lines.append(f"**Database contains {len(all_tables)} tables**")
    lines.append("")

    # Summarize specified tables
    for table_name in tables:
        if not table_exists(conn, table_name):
            continue

        count = query_to_polars(conn, f"SELECT COUNT(*) as cnt FROM {table_name}")["cnt"][0]
        lines.append(f"- **{table_name}**: {count:,} rows")

    if not tables:
        # Summarize all tables
        for table_name in all_tables[:10]:
            count = query_to_polars(conn, f"SELECT COUNT(*) as cnt FROM {table_name}")["cnt"][0]
            lines.append(f"- **{table_name}**: {count:,} rows")

        if len(all_tables) > 10:
            lines.append(f"- *... and {len(all_tables) - 10} more tables*")

    return "\n".join(lines)


def quick_report(db_path: str) -> str:
    """Generate a quick summary report.

    Args:
        db_path: Path to DuckDB database.

    Returns:
        Markdown report string.
    """
    lines = [
        "# Quick Analysis Report",
        "",
        f"*Generated: {datetime.now().isoformat()}*",
        "",
    ]

    with connect(db_path) as conn:
        tables = list_tables(conn)

        # Overview
        lines.append("## Overview")
        lines.append("")
        lines.append(f"Database contains **{len(tables)}** tables:")
        lines.append("")

        for table_name in tables:
            count = query_to_polars(conn, f"SELECT COUNT(*) as cnt FROM {table_name}")["cnt"][0]
            lines.append(f"- {table_name}: {count:,} rows")

        lines.append("")

        # Anomalies summary
        if table_exists(conn, "anomalies"):
            lines.append("## Anomalies")
            lines.append("")

            anomalies = query_to_polars(conn, """
                SELECT severity, COUNT(*) as count
                FROM anomalies
                GROUP BY severity
                ORDER BY count DESC
            """)

            if not anomalies.is_empty():
                lines.append(markdown_table(anomalies))
            else:
                lines.append("No anomalies detected.")

            lines.append("")

        # Correlations summary
        if table_exists(conn, "correlations"):
            lines.append("## Correlations")
            lines.append("")

            correlations = query_to_polars(conn, """
                SELECT correlation_type, COUNT(*) as count, AVG(score) as avg_score
                FROM correlations
                GROUP BY correlation_type
                ORDER BY count DESC
            """)

            if not correlations.is_empty():
                lines.append(markdown_table(correlations))
            else:
                lines.append("No correlations found.")

            lines.append("")

        # Entities summary
        if table_exists(conn, "entities"):
            lines.append("## Entities")
            lines.append("")

            entities = query_to_polars(conn, """
                SELECT entity_type, COUNT(DISTINCT value) as unique_values, COUNT(*) as occurrences
                FROM entities
                GROUP BY entity_type
                ORDER BY occurrences DESC
                LIMIT 10
            """)

            if not entities.is_empty():
                lines.append(markdown_table(entities))
            else:
                lines.append("No entities extracted.")

            lines.append("")

    return "\n".join(lines)
