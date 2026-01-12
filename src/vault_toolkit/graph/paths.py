"""Path finding and graph analysis algorithms."""

from collections import deque
from typing import Generator

from vault_toolkit.graph.build import Graph


def find_path(
    graph: Graph,
    source: str,
    target: str,
) -> list[str] | None:
    """Find shortest path between two nodes using BFS.

    Args:
        graph: Graph to search.
        source: Source node ID.
        target: Target node ID.

    Returns:
        List of node IDs representing path, or None if no path exists.
    """
    if source not in graph.nodes or target not in graph.nodes:
        return None

    if source == target:
        return [source]

    visited = {source}
    queue = deque([(source, [source])])

    while queue:
        current, path = queue.popleft()

        for neighbor in graph.get_neighbors(current):
            if neighbor == target:
                return path + [neighbor]

            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return None


def find_all_paths(
    graph: Graph,
    source: str,
    target: str,
    max_depth: int = 5,
) -> list[list[str]]:
    """Find all paths between two nodes up to max depth.

    Args:
        graph: Graph to search.
        source: Source node ID.
        target: Target node ID.
        max_depth: Maximum path length.

    Returns:
        List of paths (each path is a list of node IDs).
    """
    if source not in graph.nodes or target not in graph.nodes:
        return []

    paths = []

    def dfs(current: str, path: list[str], visited: set[str]) -> None:
        if len(path) > max_depth:
            return

        if current == target:
            paths.append(path.copy())
            return

        for neighbor in graph.get_neighbors(current):
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                dfs(neighbor, path, visited)
                path.pop()
                visited.remove(neighbor)

    dfs(source, [source], {source})
    return paths


def find_connected_components(graph: Graph) -> list[set[str]]:
    """Find all connected components in the graph.

    Args:
        graph: Graph to analyze.

    Returns:
        List of sets, each containing node IDs of a connected component.
    """
    visited: set[str] = set()
    components: list[set[str]] = []

    for node_id in graph.nodes:
        if node_id in visited:
            continue

        # BFS to find all connected nodes
        component: set[str] = set()
        queue = deque([node_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)
            component.add(current)

            for neighbor in graph.get_neighbors(current):
                if neighbor not in visited:
                    queue.append(neighbor)

        if component:
            components.append(component)

    # Sort by size (largest first)
    components.sort(key=len, reverse=True)
    return components


def calculate_centrality(graph: Graph) -> dict[str, float]:
    """Calculate degree centrality for all nodes.

    Args:
        graph: Graph to analyze.

    Returns:
        Dictionary mapping node IDs to centrality scores (0-1).
    """
    if graph.node_count <= 1:
        return {node_id: 1.0 for node_id in graph.nodes}

    max_possible = graph.node_count - 1
    centrality = {}

    for node_id in graph.nodes:
        degree = len(graph.get_neighbors(node_id))
        centrality[node_id] = degree / max_possible

    return centrality


def find_bridges(graph: Graph) -> list[tuple[str, str]]:
    """Find bridge edges whose removal disconnects the graph.

    Args:
        graph: Graph to analyze.

    Returns:
        List of (source, target) tuples representing bridge edges.
    """
    bridges = []
    visited: set[str] = set()
    disc: dict[str, int] = {}  # Discovery time
    low: dict[str, int] = {}   # Lowest discovery time reachable
    parent: dict[str, str | None] = {}
    time = [0]

    def dfs(u: str) -> None:
        visited.add(u)
        disc[u] = low[u] = time[0]
        time[0] += 1

        for v in graph.get_neighbors(u):
            if v not in visited:
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])

                if low[v] > disc[u]:
                    bridges.append((u, v))
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node_id in graph.nodes:
        if node_id not in visited:
            parent[node_id] = None
            dfs(node_id)

    return bridges


def path_score(graph: Graph, path: list[str]) -> float:
    """Calculate the total score of a path based on edge weights.

    Args:
        graph: Graph containing the path.
        path: List of node IDs.

    Returns:
        Sum of edge weights along the path.
    """
    if len(path) < 2:
        return 0.0

    total = 0.0
    for i in range(len(path) - 1):
        source, target = path[i], path[i + 1]
        # Find edge between source and target
        for edge in graph.edges:
            if (edge.source == source and edge.target == target) or \
               (edge.source == target and edge.target == source):
                total += edge.weight
                break

    return total


def format_path(graph: Graph, path: list[str]) -> str:
    """Format a path for display.

    Args:
        graph: Graph containing the path.
        path: List of node IDs.

    Returns:
        Formatted path string.
    """
    if not path:
        return "(no path)"

    parts = []
    for node_id in path:
        node = graph.get_node(node_id)
        if node:
            parts.append(node.label)
        else:
            parts.append(node_id)

    path_str = " → ".join(parts)
    score = path_score(graph, path)

    return f"{path_str} ({len(path) - 1} hops, score: {score:.1f})"
