# Figures Directory — Placeholder Guide

This directory contains screenshots, diagrams, and visual figures referenced in the 4 academic modules.

## How to Use This Guide

Each figure listed below includes:
- **Filename** — what to name the image file
- **Module reference** — which module uses it
- **Description** — what the figure should show
- **How to create it** — instructions for capturing or generating

Replace each placeholder in the module `.md` files with the actual image using:
```markdown
![Figure description](figures/fig_X_Y_description.png)
```

---

## Module 1: Sequential Progression

### Fig 1.1 — Bloom's Taxonomy Pyramid
- **Filename:** `fig_1_1_blooms_pyramid.png`
- **Location in module:** Section 1 (Introduction)
- **Description:** A six-level pyramid showing Remember (bottom, widest), Understand, Apply, Analyze, Evaluate, Create (top, narrowest). Each level colour-coded. Annotate with CogniMap activity type (e.g., "Remember = Define in own words", "Apply = Solve scenarios").
- **How to create:** Use PowerPoint, draw.io, or Canva. Use these colours: Remember `#FF6B6B`, Understand `#FF9F43`, Apply `#FECA57`, Analyze `#48DBFB`, Evaluate `#1DD1A1`, Create `#7BED9F`.
- **Size:** ~600×400px

### Fig 1.2 — State Transition Diagram
- **Filename:** `fig_1_2_state_machine.png`
- **Location in module:** Section 3.3 (State Machine Architecture)
- **Description:** Three circles labeled "locked", "active", "complete" with arrows showing transitions: locked → active (label: "previous level ≥80%"), active → complete (label: "quiz ≥80%"), active → active (label: "retry after <80%, reshuffled"). Add note: "Level 1 starts as active; Levels 2–6 start as locked."
- **How to create:** Use draw.io (free). Set shapes to circles, add directional arrows with text labels.
- **Size:** ~500×300px

### Fig 1.3 — Sidebar Progress Tracker
- **Filename:** `fig_1_3_sidebar_progress.png`
- **Location in module:** Section 4.5 (Sidebar Progress Tracker)
- **Description:** Screenshot of the CogniMap sidebar showing the progress tracker. Show colour coding: green for complete levels, blue for active, grey for locked. Highlight the "← Current" indicator for the active level.
- **How to create:** Run `python app_flask.py`, navigate to `localhost:5000`, log in as P01, take a screenshot of the sidebar. Crop to show only the sidebar section.
- **Size:** ~300×400px

---

## Module 2: Probing Analysis

### Fig 2.1 — Traditional AI vs. CogniMap AI
- **Filename:** `fig_2_1_comparison_diagram.png`
- **Location in module:** Section 1 (Introduction)
- **Description:** Two-column comparison. Left: "Traditional AI" — Student → Question → AI gives Answer → Student copies. Right: "CogniMap AI" — Student → Attempt → AI Challenge Question → Student defends → AI probes deeper → Student revises. Show iterative cycle on right with circular arrow.
- **How to create:** Use draw.io or PowerPoint. Use red X marks on the "copies" path (left) and green check marks on the "revises" path (right).
- **Size:** ~700×350px

### Fig 2.2 — Definition Validation Sequence Diagram
- **Filename:** `fig_2_2_sequence_diagram.png`
- **Location in module:** Section 3.5 (LLM Model Selection)
- **Description:** UML sequence diagram: Student → Browser → Flask Server → LM Studio (LLM) → Flask Server → Browser → Student. Include timing annotations: Flask→LM Studio = ~3.2s, total round-trip = ~3.5s. Show the prompt being sent and the "VALID" or "NEEDS_REVISION" response.
- **How to create:** Use draw.io (select "Sequence Diagram" template) or PlantUML. Add timing labels on arrows.
- **Size:** ~700×400px

### Fig 2.3 — Sample Challenge Responses
- **Filename:** `fig_2_3_sample_challenges.png`
- **Location in module:** Section 5.3 (Prompt Engineering Iterations)
- **Description:** Table showing 5 example AI challenges with student justifications. Format: "Student connected X→Y saying [justification]. AI challenged: [challenge question]. Student defended: [defense response]." Show a mix of good challenges and borderline ones.
- **How to create:** Export from the `llm_logs` table in the database. Query: `SELECT prompt, response FROM llm_logs WHERE feature='edge_challenger' LIMIT 5`. Format as a table in Word/Excel, then screenshot.
- **Size:** ~600×400px

---

## Module 3: Concept Mapping

### Fig 3.1 — Concept Mapping Workflow
- **Filename:** `fig_3_1_workflow.png`
- **Location in module:** Section 1 (Introduction)
- **Description:** Flowchart: Student uploads PDF → PyPDF2 extracts text → LLM identifies concepts + hierarchy → Concept nodes rendered on vis.js canvas → Student clicks node to define → AI validates → Student connects nodes → AI challenges connection → Knowledge graph grows. Use different colours for system stages vs. student actions.
- **How to create:** Use draw.io. Use rectangles for system stages, diamonds for decision points, and a different colour for student actions.
- **Size:** ~800×300px (horizontal)

### Fig 3.2 — Extraction Pipeline Architecture
- **Filename:** `fig_3_2_pipeline.png`
- **Location in module:** Section 3.2 (Extraction Pipeline Architecture)
- **Description:** Four-stage pipeline with arrows: Stage 1 (PyPDF2: extract raw text) → Stage 2 (Text pre-processing: clean formatting) → Stage 3 (LLM: identify concepts + hierarchy) → Stage 4 (vis.js: render as interactive graph). Annotate each stage with processing time (0.3s, 0.01s, 4.2s, 0.5s).
- **How to create:** Use draw.io. Use rounded rectangles for stages, arrows between them, and small text annotations below each stage for timing.
- **Size:** ~700×200px

### Fig 3.3 — vis.js Knowledge Graph
- **Filename:** `fig_3_3_graph_canvas.png`
- **Location in module:** Section 3.5 (vis.js Graph Rendering)
- **Description:** Screenshot of the CogniMap vis.js canvas showing concept nodes. Main topic nodes larger, sub-topic nodes smaller. Some nodes green (verified), others blue (pending). Include a few edges with arrows showing student-created connections. Add callout boxes explaining the visual encoding.
- **How to create:** Run the app, complete Level 1 for several concepts to get a mix of verified/pending nodes, create a few edges, then take a screenshot of the graph canvas. Add callout annotations in PowerPoint or Canva.
- **Size:** ~800×500px

### Fig 3.4 — Extraction Results (CSCI 4340 PDF)
- **Filename:** `fig_3_4_extraction_results.png`
- **Location in module:** Section 5.4 (Student Usability Testing)
- **Description:** Screenshot of the vis.js canvas after extracting concepts from the CSCI 4340 syllabus. Label 8 extracted concepts as nodes. Show hierarchy: larger nodes for main topics, smaller for sub-topics. Annotate with precision (100%) and recall (67%) metrics.
- **How to create:** Run the PDF extraction with the CSCI 4340 document, screenshot the resulting graph, add annotations in an image editor.
- **Size:** ~700×450px

---

## Module 4: Hierarchical Scaffolding

### Fig 4.1 — Hierarchical Layer Structure
- **Filename:** `fig_4_1_hierarchy_tree.png`
- **Location in module:** Section 1 (Introduction)
- **Description:** Tree diagram showing Layer 1 (Main Topics) as parent nodes and Layer 2 (Sub-topics) as child nodes. Example: "Network Architecture" has children "TCP/IP Model", "OSI Model", "Client-Server Model". Show Layer 2 nodes greyed out with a lock icon (locked until Layer 1 mastered).
- **How to create:** Use draw.io. Use a tree layout. Style Layer 1 nodes with solid colours, Layer 2 nodes with grey fill and a 🔒 emoji or lock icon.
- **Size:** ~600×400px

### Fig 4.2 — Learning State Matrix
- **Filename:** `fig_4_2_state_matrix.png`
- **Location in module:** Section 3.3 (Database Schema for Layer Tracking)
- **Description:** 6×2 grid. Rows = Bloom's levels (Remember through Create). Columns = Layer 1 (Main Topics) and Layer 2 (Sub-topics). Each cell shows the state (locked/active/complete). Highlight the current cell. Show the progression path: L1-Remember → L1-Understand → ... → L1-Create → L2-Remember → ... → L2-Create.
- **How to create:** Use Excel or Google Sheets to create the grid, colour-code cells (green=complete, blue=active, grey=locked), then screenshot. Or use draw.io.
- **Size:** ~500×400px

### Fig 4.3 — Concept Selection Modal
- **Filename:** `fig_4_3_concept_selection.png`
- **Location in module:** Section 3.4 (Tree-Based Concept Selection UI)
- **Description:** Screenshot of the concept selection modal showing the tree structure. Main topics expanded with sub-topics visible. Checkboxes next to each item. Layer 2 items greyed/locked. Callout annotations: "Layer 1: Main topics (active)" and "Layer 2: Sub-topics (locked until Layer 1 complete)."
- **How to create:** Run the app, trigger the concept selection modal (click on graph canvas), take a screenshot, add annotations.
- **Size:** ~500×400px

### Fig 4.4 — Layer Unlock Sequence
- **Filename:** `fig_4_4_layer_unlock.png`
- **Location in module:** Section 5.4 (UI Usability)
- **Description:** Three-panel sequence: Panel 1 = Layer 1 complete (all 6 levels green in sidebar). Panel 2 = Unlock notification banner ("🎉 Layer 1 complete! Layer 2 now available."). Panel 3 = Layer 2 concepts appearing on the graph (new nodes in a different colour).
- **How to create:** Run the app, complete Layer 1, take screenshots at each stage, arrange as a 3-panel horizontal layout in PowerPoint or Canva.
- **Size:** ~900×300px (3 panels side by side)

---

## Quick Reference: All Figures

| Fig ID | Filename | Module | Topic |
|--------|----------|--------|-------|
| 1.1 | `fig_1_1_blooms_pyramid.png` | M1 | Bloom's Taxonomy |
| 1.2 | `fig_1_2_state_machine.png` | M1 | State transitions |
| 1.3 | `fig_1_3_sidebar_progress.png` | M1 | Progress tracker |
| 2.1 | `fig_2_1_comparison_diagram.png` | M2 | AI comparison |
| 2.2 | `fig_2_2_sequence_diagram.png` | M2 | Validation flow |
| 2.3 | `fig_2_3_sample_challenges.png` | M2 | Challenge examples |
| 3.1 | `fig_3_1_workflow.png` | M3 | Extraction workflow |
| 3.2 | `fig_3_2_pipeline.png` | M3 | Pipeline architecture |
| 3.3 | `fig_3_3_graph_canvas.png` | M3 | vis.js canvas |
| 3.4 | `fig_3_4_extraction_results.png` | M3 | Extraction demo |
| 4.1 | `fig_4_1_hierarchy_tree.png` | M4 | Layer structure |
| 4.2 | `fig_4_2_state_matrix.png` | M4 | Learning matrix |
| 4.3 | `fig_4_3_concept_selection.png` | M4 | Selection modal |
| 4.4 | `fig_4_4_layer_unlock.png` | M4 | Unlock sequence |

**Total: 14 figures** (approximately 3–4 per module)

---

## Tools Recommendation

| Task | Tool | Cost |
|------|------|------|
| Architecture diagrams | draw.io (diagrams.net) | Free |
| Screenshots | Windows Snipping Tool / Snip & Sketch | Free |
| Annotations / callouts | PowerPoint or Canva | Free |
| Sequence diagrams | draw.io (built-in template) | Free |
| Tables as figures | Excel → Screenshot | Free |

---

## Checklist

- [ ] Fig 1.1: Bloom's Taxonomy Pyramid
- [ ] Fig 1.2: State Transition Diagram
- [ ] Fig 1.3: Sidebar Progress Tracker (screenshot)
- [ ] Fig 2.1: Traditional AI vs. CogniMap AI comparison
- [ ] Fig 2.2: Definition Validation Sequence Diagram
- [ ] Fig 2.3: Sample Challenge Responses (from DB)
- [ ] Fig 3.1: Concept Mapping Workflow
- [ ] Fig 3.2: Extraction Pipeline Architecture
- [ ] Fig 3.3: vis.js Knowledge Graph (screenshot)
- [ ] Fig 3.4: Extraction Results — CSCI 4340 (screenshot)
- [ ] Fig 4.1: Hierarchical Layer Structure tree
- [ ] Fig 4.2: Learning State Matrix
- [ ] Fig 4.3: Concept Selection Modal (screenshot)
- [ ] Fig 4.4: Layer Unlock Sequence (3-panel)
