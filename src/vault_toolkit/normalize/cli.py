"""CLI for vt-normalize."""

from pathlib import Path

import click

from vault_toolkit.core.db import connect, list_tables
from vault_toolkit.core.output import console
from vault_toolkit.normalize.ingest import ingest_files


@click.command()
@click.option(
    "--input", "-i",
    "input_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Input file or directory",
)
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file (TOML)",
)
@click.option(
    "--db", "-d",
    "db_path",
    required=True,
    type=click.Path(path_type=Path),
    help="DuckDB database file",
)
@click.option(
    "--table", "-t",
    "table_name",
    help="Target table name (overrides config)",
)
@click.option(
    "--no-deduplicate",
    is_flag=True,
    help="Disable deduplication",
)
@click.option(
    "--no-source-tag",
    is_flag=True,
    help="Don't add source file column",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Verbose output",
)
def normalize(
    input_path: Path,
    config_path: Path | None,
    db_path: Path,
    table_name: str | None,
    no_deduplicate: bool,
    no_source_tag: bool,
    verbose: bool,
):
    """Ingest raw data into clean, queryable format.

    Supports CSV, JSON, NDJSON, XML, and plain text logs.
    """
    if verbose:
        console(f"Input: {input_path}")
        console(f"Database: {db_path}")
        if config_path:
            console(f"Config: {config_path}")

    try:
        results = ingest_files(
            input_path,
            db_path,
            config_path,
            table_name=table_name,
            deduplicate=not no_deduplicate,
            tag_source=not no_source_tag,
        )

        if not results:
            console("No data ingested", error=True)
            raise SystemExit(1)

        # Summary
        total_rows = sum(results.values())
        console(f"Ingested {total_rows:,} rows into {len(results)} table(s)")

        if verbose:
            for table, count in sorted(results.items()):
                console(f"  {table}: {count:,} rows")

            # Show all tables in DB
            with connect(db_path) as conn:
                tables = list_tables(conn)
                console(f"\nTables in database: {', '.join(tables)}")

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
