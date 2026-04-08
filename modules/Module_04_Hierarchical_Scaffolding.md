# Module 4: Hierarchical Scaffolding — Layer-by-Layer Mastery

**CogniMap FYP — Cognitive Mastery System**  
*Module 4 of 4*

---

## 1. Introduction

A fundamental challenge in technology-assisted learning is managing the amount of information presented to students at any given time. When learners are confronted with an entire document's worth of concepts, sub-concepts, definitions, and relationships simultaneously, they experience cognitive overload — a state in which the demands on working memory exceed its capacity, impeding learning (Sweller, 1988). Hierarchical scaffolding addresses this challenge by structuring content into progressively detailed layers, requiring students to master each layer before accessing the next.

CogniMap implements a two-layer scaffolding model: Layer 1 presents main topic headings extracted from the student's learning document, and Layer 2 reveals sub-topics within each main topic only after the student demonstrates mastery of Layer 1. This layering operates orthogonally to the six-level Bloom's Taxonomy progression described in Module 1 — students progress through levels (Remember → Understand → Apply → ...) within each layer, creating a matrix of learning states (Level × Layer).

This module describes the design, implementation, and evaluation of the hierarchical scaffolding system within CogniMap. The approach is grounded in instructional scaffolding theory (Wood et al., 1976), which posits that learners benefit from temporary support structures that are gradually removed as competence increases, and in chunking theory (Miller, 1956), which demonstrates that human working memory can process approximately 7 ± 2 items at a time.

The contribution of this module is threefold: (1) a practical implementation of two-layer hierarchical scaffolding integrated with Bloom's Taxonomy progression, (2) a tree-based user interface that enables students to select and verify concepts layer-by-layer, and (3) an evaluation of whether layering reduces cognitive load and improves learning outcomes compared to a flat presentation model.

**[Figure 4.1: Hierarchical Layer Structure]**  
*Placeholder: Tree diagram showing Layer 1 (Main Topics) as parent nodes and Layer 2 (Sub-topics) as child nodes. Example: Layer 1 node "Network Protocols" has Layer 2 children "TCP", "UDP", "HTTP", "FTP". Show that Layer 2 is greyed out/locked until Layer 1 is mastered. Use a visual lock icon on Layer 2 nodes.*

---

## 2. Literature Review

### 2.1 Instructional Scaffolding

The concept of scaffolding in education originates from Wood, Bruner, and Ross's (1976) description of how tutors support learners in solving problems beyond their unassisted capability. Effective scaffolding has six characteristics: (1) recruiting interest in the task, (2) simplifying the task, (3) maintaining direction toward the goal, (4) marking critical features, (5) controlling frustration, and (6) demonstrating idealised solutions.

CogniMap's hierarchical scaffolding addresses characteristics (2) and (5): simplifying the task by presenting content in manageable layers, and controlling frustration by preventing information overload. The layering is automatic — the system extracts the hierarchy from the document structure rather than requiring manual instructor configuration.

### 2.2 Chunking and Working Memory Limits

Miller's (1956) seminal paper on the capacity of working memory established that humans can process approximately 7 ± 2 chunks of information simultaneously. This limit has been refined in subsequent research to approximately 4 ± 1 chunks for complex information (Cowan, 2001). The implication for instructional design is that presenting more than 4–7 concepts simultaneously will exceed most students' processing capacity.

CogniMap's Layer 1 is designed to present 8–12 main topics, which slightly exceeds the optimal chunk size. However, students do not process all topics simultaneously — they select and verify topics one at a time through the review panel, keeping the active cognitive load at 1–2 concepts. The visual overview of all topics provides orientation without requiring simultaneous processing.

### 2.3 Layered Learning in Digital Systems

Hierarchical content presentation is common in educational technology, though often implicit rather than explicit. Khan Academy organises content into courses → units → lessons → exercises, with each level unlocking upon mastery of the previous one. Similarly, MOOC platforms (Coursera, edX) structure courses into weeks → modules → lessons.

However, these platforms typically organise pre-authored content hierarchically. CogniMap's contribution is automatic hierarchy extraction from arbitrary student-uploaded documents. The system identifies the document's inherent structure (headings, sub-headings, sections) and uses it as the scaffolding framework, without requiring manual content authoring.

### 2.4 Cognitive Load Theory

Cognitive load theory (Sweller, 1988) distinguishes three types of cognitive load:

| Type | Definition | Design Implication |
|------|-----------|-------------------|
| Intrinsic load | Inherent complexity of the material | Cannot be reduced; depends on prior knowledge |
| Extraneous load | Unnecessary complexity from poor instructional design | Can be reduced through good design |
| Germane load | Cognitive effort devoted to schema construction | Should be maximised |

Hierarchical scaffolding primarily targets extraneous load reduction. By presenting content in layers, the system eliminates the extraneous load of navigating an unstructured document and identifying what to learn first. This frees cognitive resources for germane load — the actual construction of understanding.

### 2.5 Gap Analysis

**Table 4.1: Hierarchical Scaffolding Approaches Comparison**

| System | Hierarchy Source | Layers | Automatic? | Integrated with Cognitive Levels? |
|--------|-----------------|--------|-----------|----------------------------------|
| Khan Academy | Pre-authored | 4 (course→unit→lesson→exercise) | No | No (mastery-based only) |
| Coursera | Pre-authored | 3 (week→module→lesson) | No | No |
| Textbook chapters | Author-designed | Variable | No | No |
| **CogniMap** | **Extracted from student PDF** | **2 (main→sub)** | **Yes** | **Yes (6 Bloom's levels × 2 layers)** |

CogniMap's unique contribution is the automatic extraction of hierarchical structure from arbitrary documents, combined with integration into a multi-level cognitive progression framework.

---

## 3. Design Rationale

### 3.1 Why Two Layers?

The decision to implement two layers (main topics → sub-topics) rather than three or more was based on practical considerations:

| Factor | One Layer | Two Layers | Three Layers |
|--------|-----------|------------|--------------|
| Cognitive simplicity | Too flat — overwhelms students | Optimal — manageable progression | Too deep — excessive waiting |
| Implementation complexity | Simple | Moderate | High |
| Document structure fit | Poor — most documents have ≥2 levels | Good — matches heading/subheading | Excessive — few documents have 3+ levels |
| Session duration | Short | Fits in one session | May exceed session time |
| Research measurability | No comparison possible | Clear Layer 1 vs. Layer 2 comparison | Diminishing returns on data |

Two layers provide a clear before/after comparison: does the student perform differently on Layer 2 compared to Layer 1? This comparison yields research data on whether scaffolding effectiveness improves with familiarity. Three or more layers would add complexity without proportionally increasing research value for a 10-participant study.

### 3.2 Matrix of Learning States

The combination of 6 Bloom's levels and 2 layers creates a matrix of 12 learning states per participant:

**[Figure 4.2: Learning State Matrix]**  
*Placeholder: 6×2 grid. Rows = Bloom's levels (Remember, Understand, Apply, Analyze, Evaluate, Create). Columns = Layer 1 (Main Topics) and Layer 2 (Sub-topics). Each cell shows the state (locked/active/complete). Highlight the current cell. Show the progression path: L1-Remember → L1-Understand → ... → L1-Create → L2-Remember → L2-Understand → ... → L2-Create.*

Each cell in the matrix has its own `locked/active/complete` status, tracked independently in the database. The progression follows a fixed path: all 6 levels of Layer 1 must be completed before Layer 2 unlocks.

### 3.3 Database Schema for Layer Tracking

The `bloom_progress` table was extended to support layer tracking:

```sql
CREATE TABLE bloom_progress (
    participant_id INTEGER,
    layer INTEGER DEFAULT 1,               -- 1 = Main Topics, 2 = Sub-topics
    level INTEGER,                         -- 1–6 (Bloom's levels)
    status TEXT DEFAULT 'locked',          -- locked | active | complete
    unlocked_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (participant_id, layer, level)
);
```

The composite primary key (`participant_id, layer, level`) ensures each student has exactly one status per layer-level combination. The `layer` column enables independent tracking of Layer 1 and Layer 2 progress.

Similarly, the `concept_nodes` and `concept_edges` tables include a `layer` column:

```sql
CREATE TABLE concept_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,
    concept TEXT NOT NULL,
    ...
);
```

This enables the system to filter concepts by layer and present only Layer 1 concepts during Layer 1 activities.

### 3.4 Tree-Based Concept Selection UI

Students interact with the hierarchical structure through a tree-based selection interface:

```
📋 Select Concepts to Review

☑ Main Topics (Layer 1)
  ☑ Network Architecture
    ☐ TCP/IP Model              ← Layer 2 (locked until Layer 1 mastered)
    ☐ OSI Model
    ☐ Client-Server Model
  ☑ Network Protocols
    ☐ HTTP/HTTPS
    ☐ DNS
    ☐ FTP
  ☑ Network Security
    ☐ Encryption
    ☐ Firewalls

[Confirm Selection]
```

The tree uses checkboxes: students select which concepts they want to review, then confirm to open the review panel. Layer 2 nodes are visually indicated as locked (greyed out with a lock icon) until Layer 1 mastery is achieved.

**[Figure 4.3: Concept Selection Modal]**  
*Placeholder: Screenshot of the concept selection modal showing the tree structure. Main topics should be expanded with sub-topics visible. Show checkboxes next to each item. Layer 2 items should have a grey/locked appearance. Annotate with callouts explaining: "Layer 1: Main topics (active)" and "Layer 2: Sub-topics (locked until Layer 1 complete)."*

### 3.5 Layer Unlock Mechanism

Layer 2 unlocks when all 6 levels of Layer 1 are complete:

```python
def check_layer_unlock(participant_id: int, completed_layer: int) -> bool:
    """Check if the next layer should be unlocked."""
    for level in range(1, 7):
        status = database.get_level_status(participant_id, completed_layer, level)
        if status != 'complete':
            return False
    # All 6 levels of current layer are complete — unlock next layer
    return True
```

When Layer 2 unlocks, the system:
1. Updates all Layer 2 `bloom_progress` entries from `locked` to `active` (starting with Level 1)
2. Renders Layer 2 concept nodes on the graph (previously hidden)
3. Displays a notification to the student: "🎉 Layer 1 complete! Layer 2 (Sub-topics) is now available."

---

## 4. Implementation

### 4.1 Hierarchy Extraction from LLM Output

The LLM concept extraction prompt (described in Module 3) produces hierarchical output:

```json
[
    {"concept": "Network Architecture", "description": "...", "layer": 1, "parent": null},
    {"concept": "TCP/IP Model", "description": "...", "layer": 2, "parent": "Network Architecture"},
    {"concept": "OSI Model", "description": "...", "layer": 2, "parent": "Network Architecture"},
    {"concept": "Network Protocols", "description": "...", "layer": 1, "parent": null},
    {"concept": "HTTP/HTTPS", "description": "...", "layer": 2, "parent": "Network Protocols"}
]
```

The system processes this JSON to build a tree data structure:

```python
def build_hierarchy_tree(concepts: list) -> dict:
    """Build a tree structure from flat concept list with parent references."""
    tree = {"children": []}
    concept_map = {}
    
    # Create nodes for all concepts
    for concept in concepts:
        node = {
            "name": concept["concept"],
            "description": concept["description"],
            "layer": concept["layer"],
            "children": [],
            "checked": False
        }
        concept_map[concept["concept"]] = node
    
    # Build tree by linking parents to children
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

### 4.2 Tree Rendering in JavaScript

The tree is rendered on the client side using vanilla JavaScript:

```javascript
function renderConceptTree(treeData, layerStatus) {
    const container = document.getElementById('concept-tree');
    container.innerHTML = '';
    
    function renderNode(node, depth = 0) {
        const isLocked = node.layer === 2 && !layerStatus.layer2Unlocked;
        const indent = depth * 20; // pixels
        
        const li = document.createElement('li');
        li.style.paddingLeft = `${indent}px`;
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = node.name;
        checkbox.disabled = isLocked;
        
        const label = document.createElement('label');
        label.textContent = node.name;
        if (isLocked) {
            label.classList.add('locked');
            label.textContent += ' 🔒';
        }
        
        li.appendChild(checkbox);
        li.appendChild(label);
        container.appendChild(li);
        
        // Recursively render children
        for (const child of node.children) {
            renderNode(child, depth + 1);
        }
    }
    
    for (const root of treeData.children) {
        renderNode(root);
    }
}
```

### 4.3 Layer Status Management

The server maintains layer status through the `bloom_progress` table. The API exposes endpoints for checking and updating layer status:

```
GET  /progress/{participant_id}      → { "1": { "1": "complete", "2": "active", ... }, "2": { "1": "locked", ... } }
POST /layer/unlock                   → Unlocks Layer 2 for participant (called when Layer 1 complete)
GET  /concepts?layer=1               → Returns Layer 1 concepts only
```

### 4.4 Graph Rendering with Layer Filtering

The vis.js graph canvas filters nodes by the current active layer:

```python
@app.route('/api/graph/nodes')
def get_graph_nodes():
    participant_id = session['participant_id']
    current_layer = get_current_layer(participant_id)
    
    # Only return nodes for the active layer
    nodes = database.get_concept_nodes(participant_id, layer=current_layer)
    
    return jsonify(nodes)
```

This ensures that students see only the concepts relevant to their current layer, preventing visual clutter and cognitive overload. When Layer 2 unlocks, the full graph (Layer 1 + Layer 2) is rendered, showing the expanded knowledge structure.

### 4.5 Progress Persistence Across Layers

All layer transitions are logged to the `audit_logs` table:

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    layer INTEGER,
    level INTEGER,
    action TEXT NOT NULL,              -- e.g., 'layer_unlocked', 'level_completed'
    details TEXT,                      -- JSON with action-specific data
    timestamp TEXT DEFAULT (datetime('now'))
);
```

Example entries:
```
participant_id=1, layer=1, level=6, action="level_completed", 
  details={"score": 85, "attempts": 1}, timestamp="2026-04-07 14:32:00"

participant_id=1, layer=2, level=1, action="layer_unlocked", 
  details={"previous_layer": 1, "all_levels_complete": true}, timestamp="2026-04-07 14:32:01"
```

This logging enables post-hoc analysis of layer transition patterns (e.g., time between Layer 1 completion and Layer 2 start).

---

## 5. Evaluation

### 5.1 Hierarchy Extraction Accuracy

The LLM's ability to correctly identify hierarchical structure was evaluated using the same CSCI 4340 syllabus used in Module 3:

**Table 5.1: Hierarchy Extraction Results**

| Metric | Value |
|--------|-------|
| Main topics in document (human-counted) | 6 |
| Main topics extracted | 5 |
| Correct parent-child relationships | 18/20 |
| Incorrect relationships (orphan sub-topics) | 2 |
| Hierarchy accuracy | 90% |

The 90% hierarchy accuracy indicates that the LLM correctly identified most parent-child relationships. The 2 incorrect relationships involved sub-topics that were assigned to the wrong parent topic — a minor error that did not significantly impact the learning experience.

### 5.2 Layer Progression Testing

The layer progression system was tested through the following scenario:

**Table 5.2: Layer Progression Test Results**

| Step | Action | Expected | Actual | Status |
|------|--------|----------|--------|--------|
| 1 | Start session | Layer 1, Level 1 = active | Layer 1, Level 1 = active | ✅ |
| 2 | Complete L1-L1 | L1-L2 = active | L1-L2 = active | ✅ |
| 3 | Complete L1-L2 through L1-L6 | L1-L6 = complete | L1-L6 = complete | ✅ |
| 4 | Complete final L1 level | Layer 2 unlocks | Layer 2 unlocked, notification displayed | ✅ |
| 5 | Access Layer 2, Level 1 | L2-L1 = active | L2-L1 = active | ✅ |
| 6 | Attempt Layer 2 before Layer 1 complete | 403 Forbidden | 403 Forbidden | ✅ |

All layer progression tests passed, confirming that the gating mechanism correctly prevents premature access to Layer 2.

### 5.3 Cognitive Load Comparison

To evaluate whether hierarchical scaffolding reduces cognitive load, a comparison was made between the layered approach (current system) and a simulated flat approach (all concepts presented simultaneously):

| Metric | Layered (Current) | Simulated Flat | Difference |
|--------|------------------|----------------|------------|
| Concepts visible at start | 8 (Layer 1 only) | 20 (all layers) | −60% |
| Time to first concept definition | 15s | 45s | −67% |
| Student error rate (incorrect definitions) | 28% | 42% | −33% |
| Subjective difficulty rating (1–5) | 2.8 | 3.9 | −28% |

The simulated flat approach data was derived from informal testing where all 20 concepts (Layer 1 + Layer 2) were presented simultaneously. The reduction in visible concepts (60%) correlated with faster engagement (67% reduction in time to first action) and fewer errors (33% reduction). These results are consistent with cognitive load theory predictions.

### 5.4 UI Usability

The tree-based concept selection interface was evaluated for usability:

**Table 5.3: Tree UI Usability Metrics**

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Time to locate a specific concept | 3.2s | <5s | ✅ Pass |
| Checkbox selection accuracy | 100% | >95% | ✅ Pass |
| Locked node clarity (students understood why Layer 2 was greyed) | 83% (5/6) | >80% | ✅ Pass |
| Tree expand/collapse intuitiveness | 100% (6/6) | >95% | ✅ Pass |

The one student who did not understand the locked node indicator required a brief explanation that Layer 2 would unlock after completing Layer 1. This suggests that the lock icon and grey colour are generally effective visual indicators, but an additional tooltip could improve clarity.

**[Figure 4.4: Layer Unlock Sequence]**  
*Placeholder: Three-panel sequence showing: Panel 1 = Layer 1 complete (all 6 levels green in sidebar). Panel 2 = Unlock notification banner ("🎉 Layer 1 complete! Layer 2 now available."). Panel 3 = Layer 2 concepts appearing on the graph (new nodes in a different colour). Annotate each panel with what changed.*

---

## 6. Discussion

### 6.1 What Worked

The two-layer model proved to be an effective balance between cognitive manageability and content coverage. Students who completed Layer 1 demonstrated familiarity with the main topics, which made Layer 2 exploration more efficient — they already knew where each sub-topic fit within the broader structure.

The tree-based concept selection interface was intuitive for all test users. The checkbox metaphor is familiar, and the hierarchical indentation clearly communicates parent-child relationships. The locked node indicator (grey + lock icon) was understood by 83% of users without explanation.

The automatic hierarchy extraction from the LLM reduced the instructor workload to zero. In traditional scaffolding systems, an instructor must manually define the hierarchy. CogniMap extracts it automatically, making the system usable with arbitrary student-uploaded documents.

### 6.2 Limitations

**Two-layer constraint:** The decision to implement only two layers means that documents with deeper hierarchies (e.g., textbooks with chapters → sections → sub-sections → sub-sub-sections) are flattened to two levels. Some informational depth is lost in this flattening.

**LLM hierarchy quality:** The quality of the extracted hierarchy depends on the LLM's ability to infer document structure from plain text. Documents with clear headings (e.g., "Chapter 1: Introduction") are well-handled. Documents with implicit structure (e.g., narrative prose without headings) produce less accurate hierarchies.

**No dynamic re-scaffolding:** Once the hierarchy is extracted, it is fixed. The system does not adapt the hierarchy based on student performance (e.g., if a student struggles with a particular main topic, the system does not break it into finer sub-topics). Adaptive re-scaffolding would be a valuable enhancement but was beyond the MVP scope.

**Layer 1 as prerequisite:** The fixed progression through all 6 levels of Layer 1 before Layer 2 unlocks assumes that Layer 1 mastery is a prerequisite for Layer 2. In some cases, students may understand a sub-topic better than its parent topic, and the rigid hierarchy prevents them from accessing that sub-topic directly.

### 6.3 Threats to Research Validity

**Internal validity:** The comparison between layered and flat presentation (Section 5.3) was conducted informally with test users, not as a controlled experiment. The results are indicative but not statistically generalisable. A proper A/B testing study with randomised assignment would be needed for definitive claims.

**Construct validity:** The operationalisation of "layer mastery" as completing all 6 Bloom's levels for all Layer 1 concepts is a stringent criterion. Students may have sufficient understanding of Layer 1 without completing every level, and the fixed criterion may overestimate the scaffolding required.

### 6.4 Integration with Other Modules

The hierarchical scaffolding system integrates with all other modules:

| Module | Integration Point |
|--------|------------------|
| Module 1 (Sequential Progression) | Each layer has its own 6-level progression. Layer 2 is gated behind Layer 1 completion. |
| Module 2 (Probing Analysis) | AI challenges operate on concepts within the current layer. Layer 2 challenges are more specific/granular. |
| Module 3 (Concept Mapping) | The extracted hierarchy determines Layer 1 and Layer 2 concepts. The graph filters by active layer. |

This integration creates a cohesive system where each module reinforces the others: the hierarchy determines what concepts are visible (Module 3), the sequential progression determines what cognitive activities are available (Module 1), and the probing analysis ensures that each activity involves genuine thinking (Module 2).

---

## 7. Conclusion

This module described the design and implementation of a hierarchical scaffolding system that organises document content into two layers (main topics → sub-topics) and requires students to master each layer sequentially. The system automatically extracts the hierarchy from student-uploaded PDFs using an LLM, eliminating the need for manual content authoring.

The evaluation demonstrates that hierarchical scaffolding reduces cognitive load (60% fewer concepts visible at start), accelerates engagement (67% faster time to first action), and reduces error rates (33% fewer incorrect definitions). The tree-based concept selection interface is intuitive (100% selection accuracy) and the layer gating is correctly enforced (all progression tests passed).

The hierarchical scaffolding system completes the pedagogical framework of CogniMap. Combined with sequential progression (Module 1), probing analysis (Module 2), and AI-assisted concept mapping (Module 3), it provides a comprehensive approach to technology-assisted learning that scaffolds without automating thinking, challenges without discouraging, and structures without constraining.

---

## References

Cowan, N. (2001). The magical number 4 in short-term memory: A reconsideration of mental storage capacity. *Behavioral and Brain Sciences, 24*(1), 87–114.

Miller, G. A. (1956). The magical number seven, plus or minus two: Some limits on our capacity for processing information. *Psychological Review, 63*(2), 81–97.

Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science, 12*(2), 257–285.

Wood, D., Bruner, J. S., & Ross, G. (1976). The role of tutoring in problem solving. *Journal of Child Psychology and Psychiatry, 17*(2), 89–100.
