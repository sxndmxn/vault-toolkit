"""Graph construction from correlations and entities."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from vault_toolkit.core.db import connect, query_to_polars, table_exists
from vault_toolkit.core.types import GraphNode, GraphEdge


@dataclass
class Graph:
    """A relationship graph."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
        self.adjacency[edge.source].append(edge.target)
        self.adjacency[edge.target].append(edge.source)  # Undirected

    def get_neighbors(self, node_id: str) -> list[str]:
        """Get all neighbors of a node."""
        return self.adjacency.get(node_id, [])

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def subgraph(self, node_ids: set[str]) -> "Graph":
        """Create a subgraph with only the specified nodes."""
        sub = Graph()
        for node_id in node_ids:
            if node_id in self.nodes:
                sub.add_node(self.nodes[node_id])

        for edge in self.edges:
            if edge.source in node_ids and edge.target in node_ids:
                sub.add_edge(edge)

        return sub

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


def build_graph(
    db_path: str,
    *,
    entity_table: str = "entities",
    correlation_table: str = "correlations",
    min_score: float = 0.0,
) -> Graph:
    """Build a graph from entities and correlations.

    Args:
        db_path: Path to DuckDB database.
        entity_table: Table containing entities.
        correlation_table: Table containing correlations.
        min_score: Minimum correlation score to include.

    Returns:
        Graph object.
    """
    graph = Graph()

    with connect(db_path) as conn:
        # Load entities as nodes
        if table_exists(conn, entity_table):
            entities = query_to_polars(conn, f"""
                SELECT DISTINCT
                    value as id,
                    entity_type as type,
                    COUNT(*) as occurrence_count
                FROM {entity_table}
                GROUP BY value, entity_type
            """)

            for row in entities.iter_rows(named=True):
                node = GraphNode(
                    id=row["id"],
                    label=row["id"],
                    node_type=row["type"],
                    weight=row["occurrence_count"],
                )
                graph.add_node(node)

        # Load correlations as edges
        if table_exists(conn, correlation_table):
            correlations = query_to_polars(conn, f"""
                SELECT
                    source_table,
                    target_table,
                    source_row,
                    target_row,
                    correlation_type,
                    score
                FROM {correlation_table}
                WHERE score >= {min_score}
            """)

            # Build entity lookup for row->entity mapping
            entity_lookup = _build_entity_lookup(conn, entity_table)

            for row in correlations.iter_rows(named=True):
                source_key = (row["source_table"], row["source_row"])
                target_key = (row["target_table"], row["target_row"])

                source_entities = entity_lookup.get(source_key, [])
                target_entities = entity_lookup.get(target_key, [])

                # Create edges between all entity pairs
                for source_entity in source_entities:
                    for target_entity in target_entities:
                        if source_entity != target_entity:
                            edge = GraphEdge(
                                source=source_entity,
                                target=target_entity,
                                edge_type=row["correlation_type"],
                                weight=row["score"],
                            )
                            graph.add_edge(edge)

    return graph


def build_graph_centered(
    db_path: str,
    center: str,
    depth: int = 2,
    *,
    entity_table: str = "entities",
    correlation_table: str = "correlations",
) -> Graph:
    """Build a graph centered on a specific entity.

    Args:
        db_path: Path to DuckDB database.
        center: Entity ID to center graph on.
        depth: Maximum depth from center node.
        entity_table: Table containing entities.
        correlation_table: Table containing correlations.

    Returns:
        Subgraph centered on the entity.
    """
    full_graph = build_graph(
        db_path,
        entity_table=entity_table,
        correlation_table=correlation_table,
    )

    if center not in full_graph.nodes:
        return Graph()

    # BFS to find all nodes within depth
    visited = {center}
    current_level = {center}

    for _ in range(depth):
        next_level = set()
        for node_id in current_level:
            for neighbor in full_graph.get_neighbors(node_id):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_level.add(neighbor)
        current_level = next_level

    return full_graph.subgraph(visited)


def _build_entity_lookup(conn: Any, entity_table: str) -> dict[tuple, list[str]]:
    """Build a lookup from (table, row) to entity values."""
    if not table_exists(conn, entity_table):
        return {}

    entities = query_to_polars(conn, f"""
        SELECT source_table, source_row, value
        FROM {entity_table}
    """)

    lookup: dict[tuple, list[str]] = defaultdict(list)
    for row in entities.iter_rows(named=True):
        key = (row["source_table"], row["source_row"])
        lookup[key].append(row["value"])

    return lookup


def graph_to_dataframe(graph: Graph) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Convert graph to node and edge DataFrames.

    Args:
        graph: Graph to convert.

    Returns:
        Tuple of (nodes_df, edges_df).
    """
    nodes_data = []
    for node in graph.nodes.values():
        nodes_data.append({
            "id": node.id,
            "label": node.label,
            "type": node.node_type,
            "weight": node.weight,
        })

    edges_data = []
    for edge in graph.edges:
        edges_data.append({
            "source": edge.source,
            "target": edge.target,
            "type": edge.edge_type,
            "weight": edge.weight,
        })

    nodes_df = pl.DataFrame(nodes_data) if nodes_data else pl.DataFrame()
    edges_df = pl.DataFrame(edges_data) if edges_data else pl.DataFrame()

    return nodes_df, edges_df
