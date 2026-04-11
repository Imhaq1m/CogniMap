"""
Core Graph Operations — Graph data read/write, node/edge CRUD.
All graph operations work with the JSON-based graph storage.
"""

import json
from pathlib import Path
from datetime import datetime

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
GRAPH_DATA_PATH = OUTPUT_DIR / "graph_data.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def load_graph_data() -> dict:
    """Load confirmed graph data from JSON file."""
    if not GRAPH_DATA_PATH.exists():
        return {"concepts": [], "relationships": []}

    try:
        with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"concepts": [], "relationships": []}


def save_confirmed_concepts(concepts: list) -> dict:
    """
    Save user-confirmed concepts to graph data file.

    Args:
        concepts: List of concept dicts with keys: name, source, page, type, heading

    Returns:
        The saved graph data dict
    """
    graph_data = {
        "concepts": concepts,
        "relationships": [],
        "confirmed_at": datetime.now().isoformat(),
    }

    with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)

    return graph_data


def get_concepts_for_level(layer: int = None) -> list:
    """
    Get concepts filtered by layer.

    Args:
        layer: 1=Main Topics, 2=Sub-topics, None=all

    Returns:
        List of concept dicts
    """
    graph_data = load_graph_data()
    concepts = graph_data.get("concepts", [])

    if layer is None:
        return concepts

    return [c for c in concepts if c.get("type") == ("main_topic" if layer == 1 else "sub_topic")]


def add_edge(from_node: str, to_node: str, justification: str) -> dict:
    """
    Add a relationship edge to the graph.

    Args:
        from_node: Source concept name
        to_node: Target concept name
        justification: Student's reasoning for the connection

    Returns:
        The created edge dict with id and timestamps
    """
    graph_data = load_graph_data()

    edge = {
        "id": f"{from_node}__{to_node}",
        "from": from_node,
        "to": to_node,
        "justification": justification,
        "adversarial_challenge": None,
        "defended_at": None,
        "created_at": datetime.now().isoformat(),
    }

    # Avoid duplicate edges
    existing_ids = {e.get("id") for e in graph_data.get("relationships", [])}
    if edge["id"] not in existing_ids:
        graph_data.setdefault("relationships", []).append(edge)

    with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)

    return edge


def get_defended_edge_count() -> int:
    """Count how many edges have been defended."""
    graph_data = load_graph_data()
    relationships = graph_data.get("relationships", [])
    return sum(1 for e in relationships if e.get("defended_at"))


def defend_edge(edge_id: str):
    """Mark an edge as defended."""
    graph_data = load_graph_data()

    for edge in graph_data.get("relationships", []):
        if edge.get("id") == edge_id:
            edge["defended_at"] = datetime.now().isoformat()
            break

    with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)


def update_edge_challenge(edge_id: str, challenge: str):
    """Save AI's adversarial challenge to an edge."""
    graph_data = load_graph_data()

    for edge in graph_data.get("relationships", []):
        if edge.get("id") == edge_id:
            edge["adversarial_challenge"] = challenge
            break

    with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)


def get_vis_nodes() -> list:
    """
    Prepare graph concepts for vis.js rendering.

    Returns:
        List of vis.js node dicts with id, label, color, etc.
    """
    graph_data = load_graph_data()
    concepts = graph_data.get("concepts", [])

    nodes = []
    for idx, concept in enumerate(concepts):
        nodes.append({
            "id": f"node-{idx}-{concept.get('name', 'unknown').replace(' ', '_')}",
            "label": concept.get("name", "Unknown"),
            "size": 20,
            "color": {
                "background": "#6366f1",
                "border": "#818cf8",
            },
            "shape": "dot",
            "title": _build_tooltip(concept),
        })

    return nodes


def get_vis_edges() -> list:
    """
    Prepare graph relationships for vis.js rendering.

    Returns:
        List of vis.js edge dicts with from, to, label
    """
    graph_data = load_graph_data()
    relationships = graph_data.get("relationships", [])

    edges = []
    for rel in relationships:
        edges.append({
            "from": rel.get("from", ""),
            "to": rel.get("to", ""),
            "label": rel.get("justification", "")[:30],
            "arrows": "to",
        })

    return edges


def _build_tooltip(concept: dict) -> str:
    """Build HTML tooltip for a concept node."""
    tooltip = f"<b>{concept.get('name', 'Unknown')}</b>"
    if concept.get("source"):
        tooltip += f"<br>Source: {concept['source']}"
    if concept.get("page"):
        tooltip += f" (p. {concept['page']})"
    return tooltip
