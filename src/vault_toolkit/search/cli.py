"""CLI for vt-search."""

from pathlib import Path

import click
import polars as pl

from vault_toolkit.core.output import console, markdown_table
from vault_toolkit.search.index import search as search_fn


@click.command(name="search")
@click.argument("query")
@click.option(
    "--db", "-d",
    "db_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="DuckDB database file",
)
@click.option(
    "--table", "-t",
    "tables",
    multiple=True,
    help="Tables to search (can specify multiple)",
)
@click.option(
    "--field", "-f",
    "fields",
    multiple=True,
    help="Fields to search (can specify multiple)",
)
@click.option(
    "--regex", "-r",
    is_flag=True,
    help="Treat query as regex pattern",
)
@click.option(
    "--case-sensitive", "-s",
    is_flag=True,
    help="Case-sensitive search",
)
@click.option(
    "--limit", "-l",
    default=100,
    type=int,
    help="Maximum results per table",
)
@click.option(
    "--context", "-C",
    default=50,
    type=int,
    help="Characters of context to show around matches",
)
@click.option(
    "--output", "-o",
    "output_table",
    help="Save results to this table",
)
@click.option(
    "--markdown", "-m",
    is_flag=True,
    help="Output as markdown table",
)
def search_cmd(
    query: str,
    db_path: Path,
    tables: tuple[str, ...],
    fields: tuple[str, ...],
    regex: bool,
    case_sensitive: bool,
    limit: int,
    context: int,
    output_table: str | None,
    markdown: bool,
):
    """Search across all ingested data.

    QUERY is the search term or regex pattern to find.
    """
    try:
        results = search_fn(
            str(db_path),
            query,
            tables=list(tables) if tables else None,
            fields=list(fields) if fields else None,
            regex=regex,
            case_sensitive=case_sensitive,
            limit=limit,
            context=context,
        )

        if results.is_empty():
            console("No matches found")
            return

        # Save to table if requested
        if output_table:
            from vault_toolkit.core.db import connect, polars_to_table

            with connect(db_path) as conn:
                polars_to_table(conn, results, output_table)
            console(f"Results saved to table: {output_table}")

        # Display results
        total = len(results)
        console(f"Found {total:,} match(es)\n")

        if markdown:
            console(markdown_table(results))
        else:
            # Group by table
            for table in results["_table"].unique().to_list():
                table_results = results.filter(pl.col("_table") == table)
                console(f"\n=== {table} ({len(table_results)} matches) ===\n")

                for row in table_results.iter_rows(named=True):
                    field = row["_field"]
                    match_text = row.get("_context", row["_match"])
                    if match_text and len(match_text) > 200:
                        match_text = match_text[:200] + "..."
                    console(f"  [{field}] {match_text}")

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)


# Export the command for CLI registration
search = search_cmd
