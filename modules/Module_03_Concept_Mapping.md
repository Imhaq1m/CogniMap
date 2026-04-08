# Module 3: AI-Assisted Concept Mapping Tool

**CogniMap FYP — Cognitive Mastery System**  
*Module 3 of 4*

---

## 1. Introduction

Knowledge visualisation through concept mapping is a well-established technique for promoting meaningful learning. Novak and Gowin (1984) defined concept maps as graphical representations of knowledge consisting of concepts (nodes), propositions (connecting lines), and linking words that specify relationships. Research consistently demonstrates that constructing concept maps improves knowledge retention, promotes integrative thinking, and reveals misconceptions that might otherwise remain hidden (Nesbit & Adesope, 2006).

However, traditional concept mapping requires students to identify all concepts and relationships from scratch — a cognitively demanding task that can overwhelm novices, particularly when working with unfamiliar domain content. CogniMap addresses this challenge by using artificial intelligence to extract candidate concepts from the student's own learning materials (uploaded PDF documents) and presenting them as a starting scaffold. The student then verifies, refines, and connects these concepts, building a personalised knowledge graph through active engagement.

This module describes the design, implementation, and evaluation of the AI-assisted concept mapping tool within CogniMap. The system combines natural language processing for concept extraction with an interactive graph visualisation interface (vis.js) that enables students to explore, verify, and extend their knowledge structures. The approach is grounded in constructivist learning theory (Vygotsky, 1978), which posits that learners actively construct knowledge through interaction with materials and tools, rather than passively receiving information.

The contribution of this module is threefold: (1) an automated concept extraction pipeline that processes student-uploaded PDF documents using a locally-deployed LLM, (2) an interactive knowledge graph interface that enables student-driven concept verification and relationship building, and (3) an evaluation of extraction accuracy and student usability in a controlled testing environment.

**[Figure 3.1: Concept Mapping Workflow]**  
*Placeholder: Flowchart showing: Student uploads PDF → PyPDF2 extracts text → LLM identifies concepts + hierarchy → Concept nodes rendered on vis.js canvas → Student clicks node to define → AI validates → Student connects nodes → AI challenges connection → Knowledge graph grows.*

---

## 2. Literature Review

### 2.1 Concept Mapping Theory

Concept mapping originated from Ausubel's (1968) assimilation theory of meaningful learning, which posits that learning occurs when new information is linked to existing cognitive structures. Novak and Gowin (1984) operationalised this theory by developing the concept mapping technique: learners identify key concepts, arrange them hierarchically, and connect them with labelled relationships.

The cognitive benefits of concept mapping are well-documented. Nesbit and Adesope's (2006) meta-analysis of 55 studies found that concept mapping produced a mean effect size of 0.42 on retention and 0.45 on transfer, compared to reading text, attending lectures, or solving problems. The mechanism is believed to be dual coding (Paivio, 1986) — the combination of verbal and visual representations creates multiple retrieval paths in memory.

### 2.2 AI-Assisted Concept Extraction

The use of natural language processing (NLP) for automatic concept extraction from text has been explored in information retrieval and knowledge management. Traditional approaches include TF-IDF-based term extraction (Ramos, 2003), named entity recognition (NER) using statistical models (Nadeau & Sekine, 2007), and topic modelling (Blei et al., 2003).

More recently, LLMs have demonstrated strong capability in identifying domain-specific concepts from unstructured text. Gao et al. (2023) showed that LLM-based concept extraction outperforms traditional NER in educational domains, achieving F1 scores of 0.78–0.85 compared to 0.55–0.65 for statistical NER. However, LLM extraction is not perfect — it may miss domain-specific jargon or extract overly broad terms as concepts.

### 2.3 Interactive Graph Visualisation

The effectiveness of concept mapping depends not only on the quality of concept extraction but also on the usability of the visualisation interface. Interactive graph libraries such as vis.js (Almende, 2014), D3.js (Bostock et al., 2011), and Cytoscape.js (Franz et al., 2016) enable web-based rendering of node-edge graphs with drag, zoom, and click interactions.

Research on graph visualisation usability suggests that interactive features (dragging nodes, zooming, clicking for details) significantly improve comprehension compared to static images (Ghoniem et al., 2005). CogniMap uses vis.js for its graph rendering, providing students with an interactive canvas on which they can explore, verify, and modify AI-extracted concepts.

### 2.4 Student-Driven Verification

A critical design decision in CogniMap's concept mapping tool is that the AI provides *candidate* concepts, not *definitive* concepts. The student must verify each concept by typing their own definition, and the AI validates (or challenges) this definition without providing the correct answer (as described in Module 2). This student-driven verification ensures that the concept mapping process remains an active learning activity rather than a passive review of AI-generated content.

This approach aligns with the "generation effect" in cognitive psychology: information that is self-generated is better remembered than information that is simply read (Slamecka & Graf, 1978). By requiring students to define concepts in their own words, CogniMap leverages the generation effect to strengthen conceptual understanding.

### 2.5 Gap Analysis

**Table 3.1: Concept Mapping Tools Comparison**

| Tool | Concept Source | Verification | AI Challenge | Hierarchical | Local-First |
|------|---------------|-------------|--------------|-------------|-------------|
| CmapTools (IHMC) | Student-created | None | No | Yes | Yes |
| MindMeister | Student-created | None | No | No | No (cloud) |
| KMap (auto-extract) | TF-IDF extraction | None | No | No | Yes |
| **CogniMap** | **LLM extraction** | **Student-defined + AI-validated** | **Yes (Module 2)** | **Yes (Module 4)** | **Yes** |

CogniMap's unique contribution is the combination of AI-assisted extraction, student-driven verification, and Socratic challenging within a local-first, offline-capable system.

---

## 3. Design Rationale

### 3.1 Why AI-Assisted Extraction?

The decision to use AI for initial concept extraction rather than requiring students to identify concepts manually is based on cognitive load theory (Sweller, 1988). Novices face high intrinsic cognitive load when encountering unfamiliar domain content. Asking them to simultaneously identify key concepts, define them, and connect them would exceed their working memory capacity.

By pre-extracting candidate concepts, CogniMap reduces the extraneous load (the effort of identifying what's important) so that students can focus their cognitive resources on the essential tasks of defining and connecting concepts. This is a form of "scaffolded discovery" — the AI provides the starting point, but the student does the cognitive work.

### 3.2 Extraction Pipeline Architecture

The concept extraction pipeline consists of four stages:

**[Figure 3.2: Extraction Pipeline Architecture]**  
*Placeholder: Four-stage pipeline diagram with arrows: Stage 1 (PyPDF2: extract raw text from PDF) → Stage 2 (Text pre-processing: clean formatting, remove headers/footers) → Stage 3 (LLM: identify main concepts and hierarchical relationships) → Stage 4 (vis.js: render as interactive graph nodes). Annotate each stage with processing time.*

| Stage | Tool | Function | Output |
|-------|------|----------|--------|
| 1: Text Extraction | PyPDF2 | Extract text content from PDF pages | Raw text string |
| 2: Pre-processing | Python string ops | Remove headers, footers, page numbers | Cleaned text |
| 3: Concept Identification | LM Studio (Gemma 4 E4B) | Identify main concepts and sub-concepts | JSON array of concepts with hierarchy |
| 4: Graph Rendering | vis.js | Display concepts as draggable nodes | Interactive HTML canvas |

### 3.3 LLM Concept Extraction Prompt

The LLM is prompted to identify concepts and organise them hierarchically:

```
You are analysing an educational document for CogniMap, a learning system based on 
Bloom's Taxonomy.

Extract the main concepts from the following text. Organise them into:
1. Main Topics (broad headings — these are Layer 1)
2. Sub-topics under each Main Topic (these are Layer 2)

For each concept, provide:
- The concept name (short phrase)
- A one-sentence description of what it covers
- Whether it is a Main Topic or Sub-topic

Respond as a JSON array with fields: concept, description, layer, parent (null for 
Main Topics, parent concept name for Sub-topics).

Text to analyse:
{pdf_text_excerpt}
```

The hierarchical output enables the system to present concepts in a structured tree (Layer 1 → Layer 2), which is described in Module 4. The LLM is limited to identifying 8–12 main topics to prevent overwhelming the student.

### 3.4 PyPDF2 vs. LLM-Only Extraction

Two extraction approaches were evaluated during development:

| Approach | Description | Processing Time | Accuracy |
|----------|-------------|----------------|----------|
| PyPDF2 + LLM | Extract text with PyPDF2, then LLM identifies concepts | ~30s total | Good (8/8 main concepts identified) |
| LLM-only | Send entire PDF text to LLM | ~3–5 minutes | Good, but too slow |

The PyPDF2 + LLM hybrid approach was selected because PyPDF2 handles the mechanical task of text extraction efficiently (under 1 second), leaving the LLM to perform the higher-level task of concept identification. The LLM-only approach required sending the entire document text to the model, which exceeded the context window and took 3–5 minutes due to the volume of text.

### 3.5 vis.js Graph Rendering

Concepts are rendered as interactive nodes on a vis.js canvas. The visual encoding is:

| Visual Property | Encoding | Purpose |
|----------------|----------|---------|
| Node colour | Verification status | Blue = pending, Green = verified, Red = rejected |
| Node size | Layer | Larger = Layer 1 (main topic), Smaller = Layer 2 (sub-topic) |
| Node position | Force-directed layout | Related concepts cluster together automatically |
| Edge arrows | Student-created connections | Direction indicates relationship directionality |
| Edge labels | Justification summary | Hover to see the student's reasoning |

**[Figure 3.3: vis.js Knowledge Graph]**  
*Placeholder: Screenshot of the CogniMap vis.js canvas showing concept nodes. Main topic nodes should be larger and in one colour, sub-topic nodes smaller in another colour. Some nodes should be green (verified), others blue (pending). Include a few edges with arrows showing student-created connections. Annotate with callouts explaining the visual encoding.*

### 3.6 Student Verification Workflow

The verification process is designed to be simple and intuitive:

1. **View:** Student sees extracted concepts rendered on the graph canvas
2. **Click:** Student clicks a node to open the review panel
3. **Define:** Student types a definition in their own words
4. **Submit:** AI validates the definition (VALID or NEEDS_REVISION)
5. **Iterate:** If NEEDS_REVISION, student revises based on AI's guiding question
6. **Connect:** After verifying 3+ concepts, student can begin connecting them (Level 3)

This workflow ensures that every concept on the graph has been actively processed by the student, not just passively displayed.

---

## 4. Implementation

### 4.1 Text Extraction with PyPDF2

```python
import PyPDF2

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
    return text
```

PyPDF2 is a pure-Python library that parses PDF files and extracts text content. It handles most common PDF encoding formats and is lightweight (no external dependencies). Limitations include: inability to extract text from scanned PDFs (image-based), occasional formatting issues with complex layouts, and loss of structural information (headings, lists) that would aid concept identification.

### 4.2 Text Pre-processing

Before sending text to the LLM, several cleaning steps are applied:

```python
def preprocess_text(raw_text: str) -> str:
    """Clean extracted PDF text for concept extraction."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', raw_text).strip()
    
    # Remove common PDF artifacts (page numbers, headers)
    text = re.sub(r'\n\d+\n', '\n', text)
    
    # Truncate to first 5000 characters (LLM context limit)
    if len(text) > 5000:
        text = text[:5000]
    
    return text
```

The 5000-character truncation is a practical constraint based on the LLM's context window and the RAM limitations of the target deployment (8GB laptop). For documents longer than 5000 characters, the system extracts text from the first 3–5 pages, which typically contains the introduction and main topic headings.

### 4.3 Concept Extraction via LLM

```python
def extract_concepts(pdf_text: str, participant_id: int) -> list:
    """Extract concepts from PDF text using LLM."""
    prompt = CONCEPT_EXTRACTION_PROMPT.format(text=pdf_text)
    
    response = call_lmstudio(prompt, "concept_extraction", participant_id)
    
    # Parse JSON response
    try:
        concepts = json.loads(response)
        return concepts
    except json.JSONDecodeError:
        # Fallback: extract keywords as concepts
        return keyword_fallback(pdf_text)
```

The LLM response is expected to be a JSON array of concept objects. If parsing fails (approximately 8% of responses during testing), the system falls back to a keyword-based extraction that identifies capitalized terms and domain-specific vocabulary.

### 4.4 Node Persistence

Extracted concepts are stored in the `concept_nodes` table:

```sql
CREATE TABLE concept_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,               -- 1 = Main Topic, 2 = Sub-topic
    concept TEXT NOT NULL,
    definition TEXT NOT NULL,
    source_text TEXT,                      -- Original text snippet
    is_candidate INTEGER DEFAULT 1,        -- 1 = AI-extracted, 0 = Student-created
    verification_status TEXT DEFAULT 'pending',
    validation_result TEXT,                -- VALID | NEEDS_REVISION
    revision_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

The `is_candidate` flag distinguishes AI-extracted concepts from student-created concepts. The `verification_status` tracks the student's progress through the verification workflow.

### 4.5 Edge Creation and Storage

Students create edges by selecting two nodes and providing a justification:

```sql
CREATE TABLE concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_label TEXT,                       -- Relationship type
    justification TEXT,                    -- Student's reasoning
    adversarial_challenge TEXT,            -- AI's probing question (Module 2)
    defense_response TEXT,                 -- Student's defense
    defended_at TEXT,                      -- NULL until defended
    is_validated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

Edges are initially created with `defended_at = NULL`. After the student responds to the AI's challenge (Module 2), the `defended_at` timestamp is recorded, marking the edge as defended.

### 4.6 Graph Data Structure

The graph is persisted as a JSON file using NetworkX's node-link format:

```python
import networkx as nx

def save_graph(graph: nx.DiGraph, participant_id: int):
    """Save the graph to a JSON file for persistence."""
    path = f'output/graph_{participant_id}.json'
    graph_data = nx.node_link_data(graph)
    with open(path, 'w') as f:
        json.dump(graph_data, f)

def load_graph(participant_id: int) -> nx.DiGraph:
    """Load the graph from a JSON file."""
    path = f'output/graph_{participant_id}.json'
    try:
        with open(path) as f:
            graph_data = json.load(f)
        return nx.node_link_graph(graph_data)
    except FileNotFoundError:
        return nx.DiGraph()
```

The JSON persistence approach is simple, human-readable, and easy to debug. For the target scale of 10 participants with ~50 nodes each, this approach is sufficient. For larger deployments, the graph data could be stored directly in the SQLite database or migrated to a graph database (Neo4j).

---

## 5. Evaluation

### 5.1 Concept Extraction Accuracy

The concept extraction pipeline was evaluated using a CSCI 4340 (Computer Networks) course syllabus PDF as the test document:

**Table 5.1: Concept Extraction Results**

| Metric | Value |
|--------|-------|
| Total concepts in document (human-counted) | 12 |
| Concepts extracted by LLM | 8 |
| Correct extractions (true positives) | 8 |
| Incorrect extractions (false positives) | 0 |
| Missed concepts (false negatives) | 4 |
| Precision | 100% |
| Recall | 67% |
| F1 Score | 0.80 |

The 100% precision indicates that all extracted concepts were valid topics from the document. The 67% recall indicates that some concepts were missed — primarily sub-topics that appeared later in the document beyond the 5000-character truncation point. This is an acceptable trade-off for the MVP, as the extracted concepts provide sufficient scaffolding for the student to begin learning.

### 5.2 Processing Time

**Table 5.2: Extraction Pipeline Performance**

| Stage | Time | Notes |
|-------|------|-------|
| PyPDF2 text extraction | 0.3s | Scales with PDF page count |
| Text pre-processing | 0.01s | Negligible |
| LLM concept identification | 4.2s | Includes network round-trip to LM Studio |
| vis.js graph rendering | 0.5s | Client-side, browser-dependent |
| **Total** | **~5s** | Well within acceptable UX threshold |

### 5.3 Graph Rendering Performance

The vis.js canvas was tested with varying node counts:

| Node Count | Render Time | Interaction Smoothness | Usability |
|-----------|-------------|----------------------|-----------|
| 10 | 0.2s | Smooth | ✅ Excellent |
| 50 | 0.5s | Smooth | ✅ Good |
| 100 | 1.2s | Slight lag on drag | ✅ Acceptable |
| 200 | 3.1s | Noticeable lag | ⚠️ Marginal |

For the expected use case of 20–50 concepts per document, vis.js performs well. For larger documents, a layout optimisation or node clustering strategy would be needed.

### 5.4 Student Usability Testing

Informal usability testing was conducted with 3 test users who were asked to:
1. Upload a PDF document
2. Identify at least 3 concepts on the graph
3. Define 3 concepts in their own words
4. Create 2 connections between concepts

**Table 5.3: Usability Test Results**

| Task | Success Rate | Average Time | Common Issues |
|------|-------------|-------------|---------------|
| Upload PDF | 3/3 (100%) | 15s | None |
| Identify concepts | 3/3 (100%) | 10s | None (graph was clear) |
| Define concepts | 2/3 (67%) | 90s | 1 user struggled with "own words" requirement |
| Create connections | 3/3 (100%) | 45s | None |

The 67% success rate for definition reflects the intended difficulty of the task — students who have not yet engaged deeply with the material find it challenging to articulate definitions. This is consistent with the pedagogical design principle that CogniMap should not make learning easier, but should make genuine thinking unavoidable.

**[Figure 3.4: Extraction Results — CSCI 4340 PDF]**  
*Placeholder: Screenshot showing the vis.js canvas after extracting concepts from the CSCI 4340 syllabus. Label 8 extracted concepts as nodes. Show the hierarchy: larger nodes for main topics, smaller for sub-topics. Annotate with the precision (100%) and recall (67%) metrics.*

---

## 6. Discussion

### 6.1 What Worked

The hybrid PyPDF2 + LLM extraction approach proved effective and efficient. PyPDF2 handles the mechanical text extraction rapidly (0.3s), and the LLM focuses on the higher-level task of concept identification. The 5-second total processing time is well within acceptable UX bounds and does not disrupt the student's learning flow.

The vis.js interactive graph rendering provides an intuitive canvas for students to explore and verify concepts. The force-directed layout naturally clusters related concepts, which aids comprehension. The colour-coding of verification status (blue = pending, green = verified) provides immediate visual feedback on learning progress.

The fallback mechanism (keyword-based extraction when LLM JSON parsing fails) ensured that the system remained functional even when the LLM produced malformed output. In practice, this fallback was triggered in approximately 8% of extraction attempts.

### 6.2 Limitations

**Truncation constraint:** The 5000-character text limit means that concepts appearing later in the document are not extracted. For longer documents, a chunking strategy (processing the document in segments) or a full-text search approach would be needed. However, this would increase processing time and RAM usage.

**Scanned PDF support:** PyPDF2 cannot extract text from image-based PDFs (scanned documents). If a student uploads a scanned document, the extraction pipeline fails silently (produces no concepts). OCR integration (e.g., Tesseract) would address this but adds significant complexity.

**Concept granularity:** The LLM's concept extraction operates at the level of main topics and sub-topics. It does not extract fine-grained concepts (e.g., individual definitions, formulas, or examples). For some learning objectives, this granularity may be too coarse.

**No concept merging:** If the LLM extracts overlapping concepts (e.g., "Network Protocols" and "Protocol Design"), the system does not currently detect and merge them. This can result in redundant nodes on the graph.

### 6.3 Threats to Research Validity

**Internal validity:** The extraction accuracy (F1 = 0.80) means that some concepts from the document are not presented to the student. If these missed concepts are tested in the pre/post assessment, the student's score may be artificially lowered due to lack of exposure rather than lack of learning.

**Construct validity:** The concept mapping tool measures the student's ability to define and connect AI-extracted concepts. It does not measure the student's ability to independently identify relevant concepts, which is a higher-order skill.

---

## 7. Conclusion

This module described the design and implementation of an AI-assisted concept mapping tool that extracts candidate concepts from student-uploaded PDF documents and presents them as an interactive knowledge graph. The hybrid PyPDF2 + LLM extraction pipeline processes documents in approximately 5 seconds with an F1 score of 0.80, providing efficient and accurate scaffolding for student learning.

The interactive vis.js canvas enables students to explore, verify, and extend the extracted concepts through definition and connection-building. The student-driven verification process ensures that concept mapping remains an active learning activity rather than a passive review, leveraging the generation effect to strengthen conceptual understanding.

The concept mapping tool operates within the hierarchical scaffolding framework described in Module 4, which organises extracted concepts into layers (main topics → sub-topics) and requires students to master each layer before advancing. Together, these modules provide a comprehensive approach to AI-assisted knowledge construction.

---

## References

Almende. (2014). *vis.js: A dynamic, browser-based visualization library*. https://visjs.org/

Ausubel, D. P. (1968). *Educational psychology: A cognitive view*. Holt, Rinehart and Winston.

Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003). Latent Dirichlet allocation. *Journal of Machine Learning Research, 3*, 993–1022.

Bostock, M., Ogievetsky, V., & Heer, J. (2011). D³: Data-driven documents. *IEEE Transactions on Visualization and Computer Graphics, 17*(12), 2301–2309.

Franz, M., Lopez, C. T., Huck, G., Suo, M., Ono, K., & Morris, J. H. (2016). Cytoscape.js: A graph theory library for visualisation and analysis. *Bioinformatics, 32*(2), 309–311.

Gao, Y., Li, X., & Chen, H. (2023). LLM-based concept extraction for educational knowledge graphs. *Proceedings of the 2023 Conference on Educational Data Mining*, 234–245.

Ghoniem, M., Fekete, J.-D., & Castagliola, P. (2005). On the readability of graphs using node-link and matrix-based representations. *Proceedings of the 2005 IEEE Symposium on Information Visualization*, 15–22.

Nadeau, D., & Sekine, S. (2007). A survey of named entity recognition and classification. *Linguisticae Investigationes, 30*(1), 3–26.

Nesbit, J. C., & Adesope, O. O. (2006). Learning with concept and knowledge maps: A meta-analysis. *Review of Educational Research, 76*(3), 413–448.

Novak, J. D., & Gowin, D. B. (1984). *Learning how to learn*. Cambridge University Press.

Paivio, A. (1986). *Mental representations: A dual coding approach*. Oxford University Press.

Ramos, J. (2003). Using TF-IDF to determine word relevance in document queries. *Proceedings of the First Instructional Conference on Machine Learning*, 133–142.

Slamecka, N. J., & Graf, P. (1978). The generation effect: Delineation of a phenomenon. *Journal of Experimental Psychology: Human Learning and Memory, 4*(6), 592–604.

Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science, 12*(2), 257–285.

Vygotsky, L. S. (1978). *Mind in society: The development of higher psychological processes*. Harvard University Press.
