"""CLI for vt-extract."""

from pathlib import Path

import click

from vault_toolkit.core.output import console, markdown_table
from vault_toolkit.extract.entities import extract_entities, aggregate_entities


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
    help="Source table to extract from",
)
@click.option(
    "--field", "-f",
    required=True,
    help="Field to extract entities from",
)
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Extraction configuration file (TOML)",
)
@click.option(
    "--output", "-o",
    "output_table",
    default="entities",
    help="Output table name for extracted entities",
)
@click.option(
    "--pattern", "-p",
    "patterns",
    multiple=True,
    help="Pattern in format 'name:regex' (can specify multiple)",
)
@click.option(
    "--builtin", "-b",
    "builtins",
    multiple=True,
    help="Use builtin pattern (email, ipv4, url, etc.)",
)
@click.option(
    "--summary",
    is_flag=True,
    help="Show aggregated entity summary",
)
def extract(
    db_path: Path,
    table: str,
    field: str,
    config_path: Path | None,
    output_table: str,
    patterns: tuple[str, ...],
    builtins: tuple[str, ...],
    summary: bool,
):
    """Extract structured entities from unstructured text.

    Supports regex-based extraction with named groups,
    coordinate parsing, and custom patterns.
    """
    try:
        # Build patterns dict
        pattern_dict = {}

        # Add builtin patterns
        from vault_toolkit.extract.patterns import BUILTIN_PATTERNS
        for name in builtins:
            if name in BUILTIN_PATTERNS:
                pattern_dict[name] = {"pattern": BUILTIN_PATTERNS[name]}
            else:
                console(f"Warning: Unknown builtin pattern '{name}'", error=True)

        # Add custom patterns from CLI
        for p in patterns:
            if ":" in p:
                name, regex = p.split(":", 1)
                pattern_dict[name] = {"pattern": regex}
            else:
                console(f"Warning: Invalid pattern format '{p}' (use name:regex)", error=True)

        # Use config file if provided
        if config_path:
            count = extract_entities(
                str(db_path),
                table,
                field,
                config_path=str(config_path),
                output_table=output_table,
            )
        elif pattern_dict:
            count = extract_entities(
                str(db_path),
                table,
                field,
                patterns=pattern_dict,
                output_table=output_table,
            )
        else:
            # Use all builtins by default
            count = extract_entities(
                str(db_path),
                table,
                field,
                output_table=output_table,
            )

        console(f"Extracted {count:,} entities to table: {output_table}")

        # Show summary if requested
        if summary:
            console("\nEntity Summary:")
            agg = aggregate_entities(str(db_path), output_table)
            if not agg.is_empty():
                console(markdown_table(agg.head(20)))
            else:
                console("No entities found")

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
