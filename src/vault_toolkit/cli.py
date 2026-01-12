"""Main CLI entry point for Vault Toolkit."""

import click

from vault_toolkit.normalize.cli import normalize
from vault_toolkit.search.cli import search
from vault_toolkit.timeline.cli import timeline
from vault_toolkit.extract.cli import extract
from vault_toolkit.correlate.cli import correlate
from vault_toolkit.graph.cli import graph
from vault_toolkit.anomaly.cli import anomaly
from vault_toolkit.report.cli import report


@click.group()
@click.version_option()
def cli():
    """Vault Toolkit - Offline-first data analysis tools.

    All tools read/write to a single DuckDB file. Config via TOML.
    Output to stdout or markdown.
    """
    pass


cli.add_command(normalize)
cli.add_command(search)
cli.add_command(timeline)
cli.add_command(extract)
cli.add_command(correlate)
cli.add_command(graph)
cli.add_command(anomaly)
cli.add_command(report)


if __name__ == "__main__":
    cli()
