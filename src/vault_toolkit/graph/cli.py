"""CLI for vt-graph."""

from pathlib import Path

import click

from vault_toolkit.core.output import console
from vault_toolkit.graph.build import build_graph, build_graph_centered, graph_to_dataframe
from vault_toolkit.graph.render import render_dot, render_ascii, render_summary
from vault_toolkit.graph.paths import (
    find_path,
    find_connected_components,
    calculate_centrality,
    format_path,
)


@click.command()
@click.option(
    "--db", "-d",
    "db_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="DuckDB database file",
)
@click.option(
    "--center", "-c",
    help="Center graph on this entity",
)
@click.option(
    "--depth",
    default=2,
    type=int,
    help="Maximum depth from center node",
)
@click.option(
    "--path", "-p",
    "path_nodes",
    nargs=2,
    help="Find path between two entities",
)
@click.option(
    "--output", "-o",
    "output_path",
    type=click.Path(path_type=Path),
    help="Output file for DOT format",
)
@click.option(
    "--ascii", "-a",
    "ascii_mode",
    is_flag=True,
    help="Output ASCII visualization",
)
@click.option(
    "--dot",
    is_flag=True,
    help="Output DOT format (default if --output specified)",
)
@click.option(
    "--min-score",
    default=0.0,
    type=float,
    help="Minimum correlation score to include",
)
@click.option(
    "--components",
    is_flag=True,
    help="Show connected components",
)
@click.option(
    "--centrality",
    is_flag=True,
    help="Show centrality scores",
)
def graph(
    db_path: Path,
    center: str | None,
    depth: int,
    path_nodes: tuple[str, str] | None,
    output_path: Path | None,
    ascii_mode: bool,
    dot: bool,
    min_score: float,
    components: bool,
    centrality: bool,
):
    """Build relationship networks from correlated data.

    Creates graphs from entity correlations with DOT and ASCII output.
    """
    try:
        # Build graph
        if center:
            g = build_graph_centered(
                str(db_path),
                center,
                depth=depth,
            )
            if not g.nodes:
                console(f"Entity '{center}' not found or has no connections")
                return
        else:
            g = build_graph(str(db_path), min_score=min_score)

        if not g.nodes:
            console("No graph data found. Run vt-extract and vt-correlate first.")
            return

        # Show summary
        console(render_summary(g))
        console("")

        # Find path between nodes
        if path_nodes:
            source, target = path_nodes
            path_result = find_path(g, source, target)
            if path_result:
                console(f"Path: {format_path(g, path_result)}")
            else:
                console(f"No path found between {source} and {target}")
            return

        # Show connected components
        if components:
            comps = find_connected_components(g)
            console(f"Connected components: {len(comps)}")
            for i, comp in enumerate(comps[:10]):
                nodes = ", ".join(list(comp)[:5])
                if len(comp) > 5:
                    nodes += f" ... ({len(comp)} total)"
                console(f"  {i + 1}. {nodes}")
            return

        # Show centrality
        if centrality:
            cent = calculate_centrality(g)
            sorted_cent = sorted(cent.items(), key=lambda x: -x[1])
            console("Top entities by centrality:")
            for node_id, score in sorted_cent[:20]:
                console(f"  {node_id}: {score:.3f}")
            return

        # Output DOT format
        if output_path or dot:
            dot_str = render_dot(g)
            if output_path:
                output_path.write_text(dot_str)
                console(f"Graph written to: {output_path}")
            else:
                console(dot_str)
            return

        # Default: ASCII output
        if ascii_mode or (not output_path and not dot):
            console(render_ascii(g, center=center, max_depth=depth))

    except Exception as e:
        console(f"Error: {e}", error=True)
        raise SystemExit(1)
