"""Tests for graph module."""

import pytest

from vault_toolkit.graph.build import Graph, build_graph
from vault_toolkit.graph.render import render_dot, render_ascii
from vault_toolkit.graph.paths import find_path, find_connected_components
from vault_toolkit.core.types import GraphNode, GraphEdge


class TestGraph:
    """Tests for graph data structure."""

    def test_graph_add_node(self):
        g = Graph()
        node = GraphNode(id="a", label="Node A")
        g.add_node(node)
        assert "a" in g.nodes
        assert g.node_count == 1

    def test_graph_add_edge(self):
        g = Graph()
        g.add_node(GraphNode(id="a", label="A"))
        g.add_node(GraphNode(id="b", label="B"))
        g.add_edge(GraphEdge(source="a", target="b"))
        assert g.edge_count == 1
        assert "b" in g.get_neighbors("a")
        assert "a" in g.get_neighbors("b")  # Undirected

    def test_graph_subgraph(self):
        g = Graph()
        g.add_node(GraphNode(id="a", label="A"))
        g.add_node(GraphNode(id="b", label="B"))
        g.add_node(GraphNode(id="c", label="C"))
        g.add_edge(GraphEdge(source="a", target="b"))
        g.add_edge(GraphEdge(source="b", target="c"))

        sub = g.subgraph({"a", "b"})
        assert sub.node_count == 2
        assert sub.edge_count == 1


class TestGraphPaths:
    """Tests for path finding algorithms."""

    def test_find_path(self):
        g = Graph()
        for node_id in "abcd":
            g.add_node(GraphNode(id=node_id, label=node_id.upper()))

        g.add_edge(GraphEdge(source="a", target="b"))
        g.add_edge(GraphEdge(source="b", target="c"))
        g.add_edge(GraphEdge(source="c", target="d"))

        path = find_path(g, "a", "d")
        assert path is not None
        assert path == ["a", "b", "c", "d"]

    def test_find_path_no_path(self):
        g = Graph()
        g.add_node(GraphNode(id="a", label="A"))
        g.add_node(GraphNode(id="b", label="B"))
        # No edge between them

        path = find_path(g, "a", "b")
        assert path is None

    def test_find_connected_components(self):
        g = Graph()
        # Component 1
        g.add_node(GraphNode(id="a", label="A"))
        g.add_node(GraphNode(id="b", label="B"))
        g.add_edge(GraphEdge(source="a", target="b"))

        # Component 2
        g.add_node(GraphNode(id="c", label="C"))
        g.add_node(GraphNode(id="d", label="D"))
        g.add_edge(GraphEdge(source="c", target="d"))

        components = find_connected_components(g)
        assert len(components) == 2


class TestGraphRender:
    """Tests for graph rendering."""

    def test_render_dot(self):
        g = Graph()
        g.add_node(GraphNode(id="a", label="Node A"))
        g.add_node(GraphNode(id="b", label="Node B"))
        g.add_edge(GraphEdge(source="a", target="b"))

        dot = render_dot(g)
        assert "digraph" in dot
        assert "Node A" in dot
        assert "Node B" in dot

    def test_render_ascii(self):
        g = Graph()
        g.add_node(GraphNode(id="a", label="A"))
        g.add_node(GraphNode(id="b", label="B"))
        g.add_node(GraphNode(id="c", label="C"))
        g.add_edge(GraphEdge(source="a", target="b"))
        g.add_edge(GraphEdge(source="a", target="c"))

        ascii_out = render_ascii(g, center="a")
        assert "A" in ascii_out
        assert "B" in ascii_out
        assert "C" in ascii_out
