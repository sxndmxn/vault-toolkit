"""Graph rendering to DOT and ASCII formats."""

from vault_toolkit.graph.build import Graph


def render_dot(
    graph: Graph,
    *,
    title: str = "Graph",
    rankdir: str = "TB",  # TB, BT, LR, RL
    node_shape: str = "box",
) -> str:
    """Render graph to DOT format for Graphviz.

    Args:
        graph: Graph to render.
        title: Graph title.
        rankdir: Layout direction.
        node_shape: Shape for nodes.

    Returns:
        DOT format string.
    """
    lines = [
        f'digraph "{title}" {{',
        f"  rankdir={rankdir};",
        f'  node [shape={node_shape}, style=filled, fillcolor="#e8e8e8"];',
        "",
    ]

    # Add nodes
    for node in graph.nodes.values():
        label = node.label.replace('"', '\\"')
        tooltip = f"{node.node_type}: {node.label}" if node.node_type else node.label

        # Color by type
        color = _get_node_color(node.node_type)

        lines.append(
            f'  "{node.id}" [label="{label}", tooltip="{tooltip}", fillcolor="{color}"];'
        )

    lines.append("")

    # Add edges (deduplicate for undirected)
    seen_edges = set()
    for edge in graph.edges:
        edge_key = tuple(sorted([edge.source, edge.target]))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        weight = f"{edge.weight:.2f}" if edge.weight else ""
        style = "solid"
        if edge.edge_type == "temporal":
            style = "dashed"
        elif edge.edge_type == "spatial":
            style = "dotted"

        lines.append(
            f'  "{edge.source}" -> "{edge.target}" [label="{weight}", style={style}, dir=none];'
        )

    lines.append("}")

    return "\n".join(lines)


def render_ascii(
    graph: Graph,
    center: str | None = None,
    max_depth: int = 3,
) -> str:
    """Render graph as ASCII tree.

    Args:
        graph: Graph to render.
        center: Center node for tree layout. If None, picks node with most connections.
        max_depth: Maximum depth to render.

    Returns:
        ASCII tree string.
    """
    if not graph.nodes:
        return "(empty graph)"

    # Pick center node
    if center is None or center not in graph.nodes:
        # Find node with most connections
        max_connections = 0
        for node_id in graph.nodes:
            connections = len(graph.get_neighbors(node_id))
            if connections > max_connections:
                max_connections = connections
                center = node_id

    if center is None:
        center = list(graph.nodes.keys())[0]

    # Build tree from center
    lines = []
    visited = set()

    def render_node(node_id: str, depth: int, prefix: str, is_last: bool) -> None:
        if depth > max_depth or node_id in visited:
            return

        visited.add(node_id)
        node = graph.get_node(node_id)

        # Build node line
        if depth == 0:
            connector = ""
        elif is_last:
            connector = "└── "
        else:
            connector = "├── "

        label = node.label if node else node_id
        type_str = f" [{node.node_type}]" if node and node.node_type else ""
        lines.append(f"{prefix}{connector}{label}{type_str}")

        # Get unvisited neighbors
        neighbors = [n for n in graph.get_neighbors(node_id) if n not in visited]

        # Render children
        for i, neighbor in enumerate(neighbors):
            is_last_child = i == len(neighbors) - 1
            if depth == 0:
                child_prefix = ""
            elif is_last:
                child_prefix = prefix + "    "
            else:
                child_prefix = prefix + "│   "

            render_node(neighbor, depth + 1, child_prefix, is_last_child)

    render_node(center, 0, "", True)

    return "\n".join(lines)


def render_summary(graph: Graph) -> str:
    """Render a summary of the graph.

    Args:
        graph: Graph to summarize.

    Returns:
        Summary string.
    """
    lines = [
        f"Nodes: {graph.node_count}",
        f"Edges: {graph.edge_count}",
    ]

    # Count by type
    type_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        t = node.node_type or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

    if type_counts:
        lines.append("\nNode types:")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {count}")

    # Edge types
    edge_types: dict[str, int] = {}
    for edge in graph.edges:
        t = edge.edge_type or "unknown"
        edge_types[t] = edge_types.get(t, 0) + 1

    if edge_types:
        lines.append("\nEdge types:")
        for t, count in sorted(edge_types.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {count}")

    return "\n".join(lines)


def _get_node_color(node_type: str | None) -> str:
    """Get a color for a node type."""
    colors = {
        "email": "#a8d5ba",
        "ipv4": "#f4a460",
        "url": "#87ceeb",
        "identifier": "#dda0dd",
        "coordinate": "#f0e68c",
        "timestamp": "#e0e0e0",
    }
    return colors.get(node_type or "", "#e8e8e8")
