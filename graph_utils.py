"""
graph_utils.py — NetworkX graph operations for CogniMap

All graph operations for Levels 3-6 (Apply, Analyze, Evaluate, Create).
Graphs are persisted as JSON files per participant and layer.
"""

import networkx as nx
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# ==================== Graph File Management ====================

def get_graph_path(participant_id: int, layer: int = 1) -> str:
    """Get the graph file path for a participant and layer."""
    return f"graph_P{participant_id:02d}_layer{layer}.json"


def load_graph(participant_id: int, layer: int = 1) -> nx.DiGraph:
    """
    Load a participant's concept graph.
    
    Args:
        participant_id: Participant ID
        layer: Layer (1=Main Headings, 2=Subheadings)
    
    Returns:
        NetworkX DiGraph (empty if file doesn't exist)
    """
    path = get_graph_path(participant_id, layer)
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return nx.node_link_graph(data)
    except FileNotFoundError:
        # Return empty graph for new participants
        return nx.DiGraph()


def save_graph(G: nx.DiGraph, participant_id: int, layer: int = 1):
    """
    Save a participant's concept graph.
    
    Args:
        G: NetworkX DiGraph
        participant_id: Participant ID
        layer: Layer (1 or 2)
    """
    path = get_graph_path(participant_id, layer)
    with open(path, 'w') as f:
        json.dump(nx.node_link_data(G), f, indent=2)


def create_empty_graph(participant_id: int, layer: int = 1) -> nx.DiGraph:
    """Create and save an empty graph for a participant."""
    G = nx.DiGraph()
    G.graph['participant_id'] = participant_id
    G.graph['layer'] = layer
    G.graph['created_at'] = datetime.now().isoformat()
    save_graph(G, participant_id, layer)
    return G


# ==================== Node Operations ====================

def add_node_to_graph(G: nx.DiGraph, concept: str, definition: str, 
                      node_id: int = None, **attributes) -> str:
    """
    Add a node to the graph.
    
    Args:
        G: NetworkX DiGraph
        concept: Concept name
        definition: Concept definition
        node_id: Optional node ID (uses concept name if not provided)
        **attributes: Additional attributes (source_text, verification_status, etc.)
    
    Returns:
        Node ID (concept name or provided ID)
    """
    node_id = node_id if node_id else concept
    
    # Prepare node attributes
    node_attrs = {
        'concept': concept,
        'definition': definition,
        'created_at': datetime.now().isoformat(),
        **attributes
    }
    
    G.add_node(node_id, **node_attrs)
    return node_id


def remove_node_from_graph(G: nx.DiGraph, node_id: str):
    """Remove a node and all its edges from the graph."""
    G.remove_node(node_id)


def get_node(G: nx.DiGraph, node_id: str) -> Optional[Dict]:
    """Get a node's data."""
    if node_id in G:
        return dict(G.nodes[node_id])
    return None


def get_all_nodes(G: nx.DiGraph) -> List[Dict]:
    """Get all nodes with their data."""
    return [
        {'id': node_id, **data}
        for node_id, data in G.nodes(data=True)
    ]


def update_node(G: nx.DiGraph, node_id: str, **attributes):
    """Update a node's attributes."""
    if node_id in G:
        for key, value in attributes.items():
            G.nodes[node_id][key] = value


# ==================== Edge Operations ====================

def add_edge_to_graph(G: nx.DiGraph, from_node: str, to_node: str, 
                      edge_label: str = "Related to", justification: str = None,
                      **attributes) -> Tuple[str, str]:
    """
    Add an edge to the graph.
    
    Args:
        G: NetworkX DiGraph
        from_node: Source node ID
        to_node: Target node ID
        edge_label: Label for the edge (e.g., "Causes", "Part of")
        justification: Student's justification for the connection
        **attributes: Additional attributes
    
    Returns:
        Tuple of (from_node, to_node)
    """
    edge_attrs = {
        'edge_label': edge_label,
        'justification': justification,
        'created_at': datetime.now().isoformat(),
        'is_validated': False,
        **attributes
    }
    
    G.add_edge(from_node, to_node, **edge_attrs)
    return (from_node, to_node)


def remove_edge_from_graph(G: nx.DiGraph, from_node: str, to_node: str):
    """Remove an edge from the graph."""
    if G.has_edge(from_node, to_node):
        G.remove_edge(from_node, to_node)


def get_edge(G: nx.DiGraph, from_node: str, to_node: str) -> Optional[Dict]:
    """Get an edge's data."""
    if G.has_edge(from_node, to_node):
        return dict(G.edges[from_node, to_node])
    return None


def get_all_edges(G: nx.DiGraph) -> List[Dict]:
    """Get all edges with their data."""
    return [
        {
            'from_node': u,
            'to_node': v,
            **data
        }
        for u, v, data in G.edges(data=True)
    ]


def update_edge(G: nx.DiGraph, from_node: str, to_node: str, **attributes):
    """Update an edge's attributes."""
    if G.has_edge(from_node, to_node):
        for key, value in attributes.items():
            G.edges[from_node, to_node][key] = value


# ==================== Graph Analysis ====================

def get_node_count(G: nx.DiGraph) -> int:
    """Get the number of nodes in the graph."""
    return G.number_of_nodes()


def get_edge_count(G: nx.DiGraph) -> int:
    """Get the number of edges in the graph."""
    return G.number_of_edges()


def get_validated_edges(G: nx.DiGraph) -> List[Dict]:
    """Get all validated edges."""
    return [
        {
            'from_node': u,
            'to_node': v,
            **data
        }
        for u, v, data in G.edges(data=True)
        if data.get('is_validated', False)
    ]


def get_defended_edges(G: nx.DiGraph) -> List[Dict]:
    """Get all defended edges (edges with defense_response)."""
    return [
        {
            'from_node': u,
            'to_node': v,
            **data
        }
        for u, v, data in G.edges(data=True)
        if data.get('defense_response') is not None
    ]


def get_graph_density(G: nx.DiGraph) -> float:
    """Calculate graph density (how connected the graph is)."""
    return nx.density(G)


def get_central_nodes(G: nx.DiGraph, top_k: int = 5) -> List[str]:
    """Get the most central nodes (by degree centrality)."""
    if G.number_of_nodes() == 0:
        return []
    
    centrality = nx.degree_centrality(G)
    sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    return [node for node, _ in sorted_nodes[:top_k]]


def find_orphan_nodes(G: nx.DiGraph) -> List[str]:
    """Find nodes with no connections."""
    return [
        node for node in G.nodes()
        if G.in_degree(node) == 0 and G.out_degree(node) == 0
    ]


# ==================== Graph Visualization ====================

def get_graph_for_visualization(G: nx.DiGraph) -> Dict:
    """
    Prepare graph data for pyvis/streamlit visualization.
    
    Returns:
        Dict with 'nodes' and 'edges' lists for visualization
    """
    nodes = []
    for node_id, data in G.nodes(data=True):
        nodes.append({
            'id': node_id,
            'label': data.get('concept', node_id),
            'title': data.get('definition', ''),  # Tooltip
            'color': data.get('color', '#2E86AB'),
            'size': data.get('size', 20)
        })
    
    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            'from': u,
            'to': v,
            'label': data.get('edge_label', ''),
            'title': data.get('justification', ''),  # Tooltip
            'arrows': 'to',
            'color': data.get('color', '#666666')
        })
    
    return {'nodes': nodes, 'edges': edges}


def render_graph_in_streamlit(G: nx.DiGraph, height: str = '500px'):
    """
    Render an interactive graph in Streamlit using pyvis.
    
    Args:
        G: NetworkX DiGraph
        height: Height of the visualization
    """
    try:
        from pyvis.network import Network
        import streamlit.components.v1 as components
        import os
        
        # Create pyvis network
        net = Network(height=height, width='100%', directed=True, bgcolor='#ffffff')
        
        # Configure node and edge styling
        net.set_options('''
        var options = {
          "nodes": {
            "font": {"size": 14, "color": "#1A1A1A"},
            "color": {"background": "#2E86AB", "border": "#1A1A1A"},
            "shape": "ellipse",
            "size": 20
          },
          "edges": {
            "color": {"color": "#666666"},
            "width": 2,
            "arrows": {"to": {"enabled": true, "scaleFactor": 1}}
          },
          "physics": {
            "enabled": true,
            "stabilization": {"iterations": 100}
          }
        }''')
        
        # Add nodes
        for node_id, data in G.nodes(data=True):
            label = data.get('concept', node_id)
            net.add_node(
                node_id,
                label=label,
                title=data.get('definition', ''),
                color='#2E86AB',
                size=25
            )
        
        # Add edges
        for u, v, data in G.edges(data=True):
            net.add_edge(
                u, v,
                label=data.get('edge_label', ''),
                title=data.get('justification', ''),
                color='#666666'
            )
        
        # Save and render
        temp_path = '/tmp/cognimap_graph.html'
        if os.name == 'nt':  # Windows
            temp_path = 'C:/temp/cognimap_graph.html'
            os.makedirs('C:/temp', exist_ok=True)
        
        net.save_graph(temp_path)
        
        with open(temp_path, 'r') as f:
            html = f.read()
        
        components.html(html, height=int(height.replace('px', '')) + 20)
        
    except ImportError:
        # Fallback if pyvis not installed
        import streamlit as st
        st.warning("pyvis not installed. Install with: pip install pyvis")
        st.json(get_graph_for_visualization(G))


# ==================== Graph Export/Import ====================

def export_graph_to_json(G: nx.DiGraph) -> str:
    """Export graph to JSON string."""
    return json.dumps(nx.node_link_data(G), indent=2)


def import_graph_from_json(json_str: str) -> nx.DiGraph:
    """Import graph from JSON string."""
    data = json.loads(json_str)
    return nx.node_link_graph(data)


def export_graph_for_study(participant_id: int, layer: int = 1) -> Dict:
    """
    Export a participant's graph for study/research purposes.
    
    Returns:
        Dict with graph data and statistics
    """
    G = load_graph(participant_id, layer)
    
    return {
        'participant_id': participant_id,
        'layer': layer,
        'node_count': get_node_count(G),
        'edge_count': get_edge_count(G),
        'density': get_graph_density(G),
        'central_nodes': get_central_nodes(G),
        'orphan_nodes': find_orphan_nodes(G),
        'validated_edges': len(get_validated_edges(G)),
        'defended_edges': len(get_defended_edges(G)),
        'graph_data': export_graph_to_json(G)
    }


# ==================== Graph Comparison (for Error Detection) ====================

def compare_graphs(G1: nx.DiGraph, G2: nx.DiGraph) -> Dict:
    """
    Compare two graphs to find differences.
    
    Args:
        G1: First graph (e.g., original)
        G2: Second graph (e.g., with injected errors)
    
    Returns:
        Dict with differences
    """
    # Find node differences
    nodes1 = set(G1.nodes())
    nodes2 = set(G2.nodes())
    
    added_nodes = list(nodes2 - nodes1)
    removed_nodes = list(nodes1 - nodes2)
    
    # Find edge differences
    edges1 = set(G1.edges())
    edges2 = set(G2.edges())
    
    added_edges = list(edges2 - edges1)
    removed_edges = list(edges1 - edges2)
    
    # Find modified nodes (same ID, different attributes)
    modified_nodes = []
    for node in nodes1 & nodes2:
        attrs1 = dict(G1.nodes[node])
        attrs2 = dict(G2.nodes[node])
        if attrs1 != attrs2:
            modified_nodes.append({
                'node': node,
                'original': attrs1,
                'modified': attrs2
            })
    
    # Find modified edges
    modified_edges = []
    for edge in edges1 & edges2:
        attrs1 = dict(G1.edges[edge])
        attrs2 = dict(G2.edges[edge])
        if attrs1 != attrs2:
            modified_edges.append({
                'edge': edge,
                'original': attrs1,
                'modified': attrs2
            })
    
    return {
        'added_nodes': added_nodes,
        'removed_nodes': removed_nodes,
        'added_edges': added_edges,
        'removed_edges': removed_edges,
        'modified_nodes': modified_nodes,
        'modified_edges': modified_edges
    }
