# Module 4: Hierarchical Scaffolding

## What It Does

Organises extracted concepts into two layers (main topics → sub-topics) and requires students to master all 6 Bloom's levels of Layer 1 before Layer 2 unlocks. This prevents cognitive overload by limiting how much content is shown at once.

## How It Works

### Two-Layer Structure

| Layer | Content | Unlock Condition |
|-------|---------|-----------------|
| Layer 1 | Main topic headings from the PDF | Default (active at session start) |
| Layer 2 | Sub-topics under each main topic | All 6 levels of Layer 1 completed |

The `layer` field in `bloom_progress` and `concept_nodes` tracks which layer each item belongs to:

```sql
CREATE TABLE bloom_progress (
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,
    level INTEGER,
    status TEXT DEFAULT 'locked',
    unlocked_at TEXT,
    completed_at TEXT,
    UNIQUE(participant_id, layer, level)
);
```

### Learning State Matrix

6 Bloom's levels × 2 layers = 12 learning states per student:

```
Layer 1: Remember → Understand → Apply → Analyze → Evaluate → Create
Layer 2: Remember → Understand → Apply → Analyze → Evaluate → Create
```

Each cell has its own `locked/active/complete` status. Progression is fixed: complete all 6 levels of Layer 1, then Layer 2 unlocks.

### Hierarchy Extraction

The LLM extraction prompt (Module 3) returns hierarchical JSON:

```json
[
    {"concept": "Network Architecture", "layer": 1, "parent": null},
    {"concept": "TCP/IP Model", "layer": 2, "parent": "Network Architecture"},
    {"concept": "Network Protocols", "layer": 1, "parent": null},
    {"concept": "HTTP/HTTPS", "layer": 2, "parent": "Network Protocols"}
]
```

The system builds a tree structure from this data:

```python
def build_hierarchy_tree(concepts):
    tree = {"children": []}
    concept_map = {}

    for concept in concepts:
        node = {"name": concept["concept"], "layer": concept["layer"], "children": []}
        concept_map[concept["concept"]] = node

    for concept in concepts:
        node = concept_map[concept["concept"]]
        if concept["parent"] is None:
            tree["children"].append(node)
        else:
            parent = concept_map.get(concept["parent"])
            if parent:
                parent["children"].append(node)

    return tree
```

### Tree UI

Concepts are displayed as a checkbox tree:

```
☑ Main Topics (Layer 1)
  ☑ Network Architecture
    ☐ TCP/IP Model              ← Layer 2 (locked)
    ☐ OSI Model
  ☑ Network Protocols
    ☐ HTTP/HTTPS
    ☐ DNS
```

- Layer 2 nodes are greyed out with a lock icon (🔒) until Layer 1 is complete
- Students select concepts via checkboxes, then confirm to open the review panel
- Tree is rendered client-side with vanilla JavaScript (recursive `renderNode()` function)

### Layer Unlock Flow

When all 6 levels of Layer 1 are complete:

1. System checks `bloom_progress` — all Layer 1 entries have `status = 'complete'`
2. Layer 2 entries are updated: `status` changes from `locked` to `active` (Level 1 first)
3. Layer 2 concept nodes appear on the vis.js graph
4. Student sees notification: "🎉 Layer 1 complete! Layer 2 (Sub-topics) is now available."

```python
def check_layer_unlock(participant_id, completed_layer):
    for level in range(1, 7):
        if database.get_level_status(participant_id, completed_layer, level) != 'complete':
            return False
    return True
```

### Graph Filtering by Layer

The vis.js canvas only shows nodes for the active layer:

```python
@app.route('/api/graph/nodes')
def get_graph_nodes():
    participant_id = session['participant_id']
    current_layer = get_current_layer(participant_id)
    nodes = database.get_concept_nodes(participant_id, layer=current_layer)
    return jsonify(nodes)
```

When Layer 2 unlocks, the full graph (Layer 1 + Layer 2) is rendered.

### Integration with Other Modules

| Module | Integration |
|--------|------------|
| Module 1 (Sequential Progression) | Each layer has its own 6-level progression. Layer 2 is gated behind Layer 1 completion. |
| Module 2 (Probing Analysis) | AI challenges operate on concepts within the current layer. |
| Module 3 (Concept Mapping) | The extracted hierarchy determines Layer 1 and Layer 2 concepts. |
