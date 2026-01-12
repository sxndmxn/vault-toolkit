"""CLI for vt-report."""

from pathlib import Path

import click

from vault_toolkit.core.output import console
from vault_toolkit.report.templates import generate_report, quick_report


@click.command()
@click.option(
    "--db", "-d",
    "db_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="DuckDB database file",
)
@click.option(
    "--template", "-t",
    "template_path",
    type=click.Path(exists=True, path_type=Path),
    help="Report template file (TOML)",
)
@click.option(
    "--output", "-o",
    "output_path",
    type=click.Path(path_type=Path),
    help="Output file path (default: stdout)",
)
@click.option(
    "--quick", "-q",
    is_flag=True,
    help="Generate quick summary report",
)
@click.option(
    "--title",
    help="Report title (overrides template)",
)
def report(
    db_path: Path,
    template_path: Path | None,
    output_path: Path | None,
    quick: bool,
    title: str | None,
):
    """Generate markdown reports from analysis results.

    Uses template-based generation with automatic table formatting,
    timeline embedding, and graph visualization.
    """
    try:
        if quick:
            content = quick_report(str(db_path))
        elif template_path:
            content = generate_report(
                str(db_path),
                str(template_path),
                title=title,
            )
        else:
            # Default to quick report if no template
            content = quick_report(str(db_path))

        if output_path:
            output_path.write_text(content)
            console(f"Report written to: {output_path}")
        else:
            console(content)

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
