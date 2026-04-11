# Module 3: Concept Mapping

## What It Does

Extracts concepts from student-uploaded PDF documents and presents them as an interactive knowledge graph. Students verify each concept by defining it in their own words, then connect concepts with justifications that the AI challenges.

## How It Works

### Extraction Pipeline

| Stage | Tool | Function | Time |
|-------|------|----------|------|
| 1. Text Extraction | PyPDF2 | Extract text from PDF pages | ~0.3s |
| 2. Pre-processing | Python string ops | Remove headers, footers, page numbers, truncate to 5000 chars | ~0.01s |
| 3. Concept Identification | LM Studio (Gemma 4 E4B) | Identify main topics and sub-topics with hierarchy | ~4.2s |
| 4. Graph Rendering | vis.js | Display concepts as draggable nodes | ~0.5s |

**Total: ~5 seconds**

### Concept Extraction

The LLM is prompted to identify concepts and organise them hierarchically:

```
Extract the main concepts from the following text. Organise them into:
1. Main Topics (Layer 1)
2. Sub-topics under each Main Topic (Layer 2)

For each concept provide: concept name, description, layer, parent.
Respond as a JSON array.
```

If the LLM response fails to parse as JSON (~8% of attempts), the system falls back to keyword-based extraction (identifying capitalized terms and domain-specific vocabulary).

### Data Storage

**Concept nodes:**
```sql
CREATE TABLE concept_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,
    concept_type TEXT DEFAULT 'main_topic',
    name TEXT NOT NULL,
    definition TEXT,
    verified INTEGER DEFAULT 0,
    source TEXT,
    page INTEGER,
    revision_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

**Concept edges:**
```sql
CREATE TABLE concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    justification TEXT,
    adversarial_challenge TEXT,
    defended_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Graph Persistence

The graph is saved as JSON using NetworkX's node-link format:

```python
def save_graph(graph, participant_id):
    path = f'output/graph_{participant_id}.json'
    json.dump(nx.node_link_data(graph), open(path, 'w'))

def load_graph(participant_id):
    path = f'output/graph_{participant_id}.json'
    return nx.node_link_graph(json.load(open(path)))
```

### Student Workflow

1. **Upload** — Student uploads a PDF document
2. **Extract** — System extracts concepts and renders them on the vis.js canvas
3. **Review** — Student clicks a node to open the review panel
4. **Define** — Student types a definition in their own words
5. **Validate** — AI checks the definition (Module 2: VALID or NEEDS_REVISION)
6. **Connect** — After verifying 3+ concepts, student can create edges between nodes
7. **Defend** — AI challenges each connection with a probing question; student defends

### vis.js Rendering

| Visual Property | Encoding |
|----------------|----------|
| Node colour | Blue = pending, Green = verified |
| Node size | Larger = Layer 1 (main topic), Smaller = Layer 2 (sub-topic) |
| Node position | Force-directed layout (related concepts cluster together) |
| Edge arrows | Student-created connections with direction |
| Edge labels | Justification text (visible on hover) |

### Performance

| Node Count | Render Time | Usability |
|-----------|-------------|-----------|
| 10 | 0.2s | Excellent |
| 50 | 0.5s | Good |
| 100 | 1.2s | Acceptable |
| 200 | 3.1s | Marginal (lag on drag) |

Expected use case: 20–50 concepts per document.
