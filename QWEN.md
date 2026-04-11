AGENTS.md — CogniMap MVP
Universal AI Coding Agent Instructions
> **How to use this file:** This is the brain file for any AI coding agent helping build CogniMap.
> Read this entirely before writing a single line of code. Every section is here for a reason.
> When in doubt, re-read. When stuck, re-read. When tempted to skip a step, re-read.

---

## 📅 Latest Updates (April 8, 2026 — Morning)

### ✅ Git Commit: v2.0 Architecture Pushed to `origin/main`
- **Commit:** `559cdc7` — Refactor to CogniMap v2.0: Flask + vis.js architecture
- **Changes:** 38 files changed, 7,831 insertions, 4,741 deletions
- **Status:** Working tree clean, branch up to date with `origin/main`
- **Milestone:** Complete migration from Streamlit to Flask single-page application

### ✅ Phase 1 Complete: UI Redesign + Level 1 (Remember)
- **Dark Theme UI:** 3-panel layout (Sidebar + Graph Canvas + Right Panel)
- **Centered Review Panel:** Modal overlay for concept selection with backdrop blur
- **Hierarchy Support:** Main Topics (Layer 1) → Sub-topics (Layer 2) with selectable checkboxes
- **Level 1 (Remember):** Define concepts in own words → AI validates without giving the answer
- **Database Layer Tracking:** SQLite with `database.py` (concept_nodes, bloom_progress tables)
- **Progress Persistence:** AI validation results saved, layer progression tracked
- **PDF Extraction:** PyPDF2 + LM Studio (Docling experiment abandoned due to 3-5 min first-run time)
- **Bug Fixes:** Duplicate node IDs in vis.js, white screen after confirmation, centered panel layout

### Files Created for v2.0 (Current)
- `app_flask.py` — Flask backend with progress tracking, extraction routes
- `database.py` — SQLite schema with layer tracking, Bloom progress
- `concept_extractor_pypdf2.py` — PDF text extraction using PyPDF2
- `concept_extractor_docling.py` — (Archived) Docling-based extraction, not used
- `pipeline_state.py` — Background task progress tracking with FileLock
- `templates/index.html` — Dark theme 3-panel UI with centered review modal
- `static/css/style.css` — Dark theme styles (~800 lines)
- `static/js/app.js` — Client-side logic with tree rendering, vis.js
- `static/lib/vis-9.1.2/` — vis.js graph visualization
- `static/lib/tom-select/` — Dropdown library for search/filters

### Current Status (April 8, 2026 — Morning)
**Phase 1 Complete ✅ | Git Pushed to `origin/main`**
- UI: ✅ Dark theme, 3-panel layout, centered review modal
- Hierarchy: ✅ Main topics → Sub-topics with selectable checkboxes
- Level 1: ✅ AI validation gate (activity-based progression)
- Database: ✅ SQLite with layer tracking, progress
- PDF Extraction: ✅ PyPDF2 + LM Studio (gpt-oss-20b-uncensored-hauhaucs-aggressive)
- Progress: ✅ Activity-based progression, layer progression (Layer 1 → Layer 2)
- Git: ✅ v2.0 architecture committed (`559cdc7`) and pushed
- Next: Level 2 (Understand) — Paraphrase + semantic similarity check

### Architecture Changes
| Component | Old | New |
|-----------|-----|-----|
| Extraction | LLM-only | PyPDF2 text + LLM hierarchy |
| Progression | Quiz-gated | Activity-gated (no quizzes) |
| UI | Light theme, full-width panels | Dark theme, centered modal overlay |
| Database | JSON only | SQLite with layer/progress tracking |
| Hierarchy | Flat list | Main Topics → Sub-topics with checkboxes |

---
1. Project Overview
CogniMap is a local-first, AI-powered learning system for a university Final Year Project (FYP) research study. It scaffolds learning through Bloom's Taxonomy levels without automating thinking.
Field	Value
App Name	CogniMap (Cognitive Mastery System)
Tagline	"AI that scaffolds learning without automating thinking"
Purpose	FYP research study — 10 participants, single study session each
Deployment	Localhost only (no cloud, no internet required during sessions)
Developer Level	Python learner / vibe-coder — beginner-safe patterns only
Primary Language	Python 3.11+ (tested on 3.13)
Timeline	9-week build window (Weeks 4–13 of FYP)
Budget	$0 — all open-source, all local
Current Status	All 6 Levels Implemented ✅ + Demo Mode Ready
What CogniMap Does
Students upload a learning document (PDF), then progress through 6 Bloom's Taxonomy levels:

Layer 1 (Main Headings) → Layer 2 (Subheadings)

| Level | Name | Activity | Gate |
|-------|------|----------|------|
| 1 | Remember | Define concepts in own words | All concepts AI-validated |
| 2 | Understand | Paraphrase definitions | Similarity 0.85-0.95 |
| 3 | Apply | Solve scenarios using concepts | 3 consecutive correct |
| 4 | Analyze | Build concept graph + defend edges | 5 edges defended |
| 5 | Evaluate | Find injected errors | ≥70% detection rate |
| 6 | Create | Generate export artifacts | Utility score ≥70% |

Demo Mode (For Testing):
Run `python setup_demo.py` once, then access http://localhost:8501/00_demo to jump to any level.

Students cannot skip levels. Gates are enforced by the FastAPI backend. All interactions are logged for research analysis.
Why It Exists (Research Context)
92% of students use AI tools, but 80–85% of AI-generated content only targets Remember/Understand
CogniMap forces genuine thinking by using AI to validate process, not provide answers
Pre/post tests measure actual learning gain; SUS + NASA-TLX measure usability and cognitive load
---
2. Tech Stack
Understand this before touching any file. Every tool was chosen deliberately.

### Tech Stack (Current v2.0)
| Layer | Tool | Version | Why |
|---|---|---|---|
| Frontend | HTML5 + CSS3 + Vanilla JS | — | Dark theme, no frameworks |
| Backend API | Flask | 3.0+ | Lightweight, session management |
| Graph Visual | vis.js | 9.1.2 | Interactive node/edge canvas |
| LLM Runtime | LM Studio | latest | Local LLM server, offline |
| LLM Model | GPT-OSS 20B Uncensored | — | 20B parameter, higher reasoning quality |
| PDF Reading | PyPDF2 | 3.0.1 | Text extraction from PDFs |
| Database | SQLite | — | Single file, zero setup |
| File Locking | filelock | 3.13+ | Safe concurrent access |
| Testing | pytest | 8.0+ | TDD workflow |
---
3. Project Folder Structure
Create this exact structure before writing feature code. Do not rename files — the rest of this document references them by name.
```
cognimap-fyp/
├── app_flask.py                    # Thin — blueprint registration + UI + file mgmt
├── database.py                     # All SQLite operations (single owner)
├── concept_extractor_pypdf2.py     # DEPRECATED — re-exports from core/
├── pipeline_state.py               # DEPRECATED — re-exports from core/
├── requirements.txt                # Python dependencies
├── .gitignore
├── README.md
├── run.bat                         # One-command launcher (Windows)
├── .streamlit/
│   └── config.toml                 # Streamlit theme (legacy)
├── core/                           # Shared infrastructure used by ALL levels
│   ├── __init__.py                 # Exports all core functions
│   ├── llm.py                      # LM Studio calls + research logging
│   ├── progress.py                 # Bloom gate enforcement, unlock logic
│   ├── graph_ops.py                # Graph read/write, node/edge CRUD
│   ├── extraction.py               # PDF text extraction + concept parsing
│   └── pipeline_state.py           # Background task progress tracking
├── levels/                         # Per-level logic (isolated, no cross-imports)
│   ├── __init__.py                 # Registers all level blueprints
│   ├── level1_remember/            # POST /api/level1/validate-definition
│   ├── level2_understand/          # POST /api/level2/validate-paraphrase
│   ├── level3_apply/               # POST /api/level3/add-edge
│   ├── level4_analyze/             # GET /api/level4/status
│   ├── level5_evaluate/            # GET /api/level5/status
│   └── level6_create/              # GET /api/level6/status
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── app.js                  # Bootstrapper
│   │   ├── shared/api.js           # Shared API client
│   │   └── levels/                 # Per-level JS modules
│   └── lib/
│       ├── vis-9.1.2/
│       └── tom-select/
├── templates/
│   └── index.html
├── data/                           # Uploaded PDFs + SQLite database
├── output/                         # Extraction cache, graph data, status
├── References/
└── images_problem/
```
---
4. Environment Setup
Complete these in order. Each step unlocks the next. Estimated time: 30 minutes on a fresh machine.

### Step 1 — Python 3.13
```bash
python --version  # Must show 3.13.x
```

### Step 2 — Virtual Environment
```bash
cd cognimap-fyp
python -m venv venv

# Activate (do this EVERY time you open a terminal):
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# You should see (venv) at the start of your prompt
```

### Step 3 — Install LM Studio + Model
```bash
# 1. Download LM Studio from lmstudio.ai for your OS
# 2. Open LM Studio GUI → Search for "gpt-oss-20b-uncensored-hauhaucs-aggressive" → Download
# 3. In LM Studio: Go to Local Server tab → Click "Start Server" (keep LM Studio open)
# 4. Test it responds under 10 seconds:
curl http://localhost:1234/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"gpt-oss-20b-uncensored-hauhaucs-aggressive","messages":[{"role":"user","content":"Say hello in one sentence"}]}'
```

### Step 4 — Install Dependencies
```bash
pip install -r requirements.txt
# Fast install — no heavy ML libraries needed
```

### Step 5 — Run Flask App
```bash
python app_flask.py
# Visit http://localhost:5000
```

### Step 6 — Git
```bash
git init
echo "venv/ *.db __pycache__/ .env backups/ data/*.db output/*.json" > .gitignore
git add .
git commit -m "Initial project setup"
# Push to a private GitHub repo
```
---
5. Database Schema
`database.py` owns all SQLite operations. No other file writes to the database directly.

### Core Tables (2 total)
```sql
CREATE TABLE IF NOT EXISTS concept_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,              -- 1=Main Topics, 2=Sub-topics
    concept_type TEXT DEFAULT 'main_topic', -- main_topic or sub_topic
    name TEXT NOT NULL,
    definition TEXT,
    verified INTEGER DEFAULT 0,           -- 1=AI-validated, 0=pending
    source TEXT,                          -- PDF filename
    page INTEGER,                         -- Page number in PDF
    revision_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bloom_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,              -- 1 or 2
    level INTEGER DEFAULT 1,              -- 1 through 6
    status TEXT DEFAULT 'locked',         -- locked | active | complete
    unlocked_at TEXT,
    completed_at TEXT,
    UNIQUE(participant_id, layer, level)
);
```

### Seed Data (Run Once)
```python
# In database.py — called on module import
def initialize_database():
    """Create tables and seed initial data."""
    # Layer 1, Level 1 is 'active' for P01
    cursor.execute("""
        INSERT OR IGNORE INTO bloom_progress 
        (participant_id, layer, level, status, unlocked_at)
        VALUES ('P01', 1, 1, 'active', datetime('now'))
    """)
```
---
6. Implementation Phases
Build in this order. Do not jump ahead. Each phase has a clear test before moving on.

---
### Phase 1 — Infrastructure + Level 1 (Remember) ✅ COMPLETE
**Goal:** UI working, PDF upload, concept extraction, Level 1 AI validation functional.

**Files created:**
- `app_flask.py` — Flask backend with progress tracking, extraction routes
- `database.py` — SQLite schema with layer tracking, Bloom progress
- `concept_extractor_pypdf2.py` — PDF text extraction using PyPDF2
- `pipeline_state.py` — Background task progress tracking
- `templates/index.html` — Dark theme 3-panel UI with centered modal
- `static/css/style.css` — Dark theme styles (~800 lines)
- `static/js/app.js` — Client-side logic with tree rendering, vis.js

**Test results:**
- [x] Upload PDF → Extract Concepts → Tree view with checkboxes
- [x] Select concepts → Confirm → Graph renders with blue dots
- [x] Layer progression tracked (Layer 1 → Layer 2)
- [x] Database saves progress

**Notes:**
- PyPDF2 + LM Studio for extraction (Docling abandoned due to 3-5 min first-run time)
- Hierarchy: Main Topics (Layer 1) → Sub-topics (Layer 2)
- vis.js for graph visualization with unique node IDs
- Dark theme with centered review modal overlay

---
### Phase 2 — Level 2: Understand 🔄 NEXT
**Goal:** Students paraphrase definitions. Semantic similarity detects copy-paste.

**Build order:**
1. `database.py` — add Level 2 status tracking
2. `app_flask.py` — add `POST /validate/paraphrase` route
3. `static/js/app.js` — add paraphrase UI (original definition read-only + textarea)
4. Use `sentence-transformers` for cosine similarity (0.85-0.95 threshold)

**Similarity Logic:**
```python
from sentence_transformers import SentenceTransformer, util
model = SentenceTransformer('all-MiniLM-L6-v2')

def check_paraphrase(original: str, paraphrase: str) -> dict:
    embeddings = model.encode([original, paraphrase])
    similarity = float(util.cos_sim(embeddings[0], embeddings[1]))
    
    if similarity > 0.95:
        return {"result": "COPY_PASTE", "feedback": "Too similar. Use your own words."}
    elif similarity >= 0.85:
        return {"result": "VALID", "feedback": "Good paraphrase!"}
    else:
        return {"result": "TOO_DIFFERENT", "feedback": "Off-topic. Try again."}
```

**Test before moving on:**
- [ ] Copy-pasting original definition rejected (similarity >0.95)
- [ ] Genuine paraphrase accepted (0.85-0.95)
- [ ] Unrelated text rejected (<0.85)
- [ ] Level 2 gate enforced; Level 3 unlocks on pass
---
Phase 5 — Level 3: Apply + Adversarial (Week 8)
Goal: Students connect concepts. AI challenges their justifications.
Files to create: `pages/05_level3_apply.py`
Build order:
`graph_utils.py` — add `add_edge(from_node, to_node, justification)`, `get_nodes_for_participant()`
`api.py` — add `POST /edges/add`, `POST /validate/edge`
`pages/05_level3_apply.py` — show existing nodes as dropdowns, justification textarea, submit → show adversarial challenge → student defends
LLM Prompt for Adversarial Edge Validator:
```python
ADVERSARIAL_PROMPT = """You are a Socratic AI tutor for CogniMap. A student has connected two concepts in their knowledge graph.

Concept A: {from_node}
Concept B: {to_node}
Student's Justification: {justification}

Your job is to challenge their reasoning to deepen understanding. Rules:
1. Do NOT confirm or deny if their connection is correct
2. Ask ONE probing question that makes them think harder about this connection
3. The question should be specific to their justification — not generic
4. Keep your response under 40 words
5. Start with "Challenge: "

Example format: "Challenge: You say X causes Y — but what happens when [specific counterexample]?"

Respond now:"""
```
Test before moving on:
[ ] Student can select two existing nodes from dropdowns
[ ] AI returns a challenge question (not a confirmation)
[ ] Student can type a defense; defense saved to `concept_edges.defended_at`
[ ] 3 defended edges required to complete Level 3
---
Phase 6 — Post-Test + Questionnaires (Week 9) ⚠️ ARCHIVED
Goal: Data collection complete. All metrics captured.
Status: **ARCHIVED** — Moved to `archive/` directory for future use
Files archived: `pages/09_posttest.py`, `pages/10_questionnaires.py`, `scoring_utils.py`
API routes commented out: `/test/submit`, `/questionnaire/sus`, `/questionnaire/nasa`

When to Restore:
- When ready for live participant studies
- When you need to measure learning gain (pre vs post test)
- When you need usability metrics (SUS > 68) or cognitive load (NASA-TLX)

How to Restore:
See `archive/README.md` for step-by-step restoration instructions.

Original Implementation Notes:
`pages/06_posttest.py` — same 18 questions, save with `test_type='post'`, show pre vs post comparison
`pages/07_questionnaires.py` — SUS 10 items + NASA-TLX 3 items, calculate SUS score, save both

SUS Score Formula (preserved for reference):
```python
def calculate_sus_score(responses: dict) -> float:
    """responses = {q1: 1-5, q2: 1-5, ..., q10: 1-5}"""
    odd_sum = sum(responses[f'q{i}'] - 1 for i in [1,3,5,7,9])
    even_sum = sum(5 - responses[f'q{i}'] for i in [2,4,6,8,10])
    return (odd_sum + even_sum) * 2.5
    # Success threshold: score > 68
```
---
Phase 7 — Polish + Study Readiness (Week 10)
Goal: Full session runs end-to-end without errors.
Tasks:
Add sidebar progress tracker to every page (`render_sidebar()` function in app.py)
Add `run.sh` / `run.bat` launcher scripts
Add auto-backup of database before each session
Test full flow: Login → Consent → Demo → L1 → L2 → L3 → L4 → L5 → L6 → (Archived: Post-test → SUS → NASA-TLX)
Try to skip levels via URL manipulation — must get blocked
Add debrief page explaining study purpose
Implement 2-revision-cycle limit per concept node
Sidebar Template:
```python
def render_sidebar(participant_id: int):
    with st.sidebar:
        st.markdown('### 🧠 Your Learning Journey')
        progress = httpx.get(f'http://localhost:8000/progress/{participant_id}').json()
        level_names = {1: 'Remember', 2: 'Understand', 3: 'Apply', 4: 'Analyze', 5: 'Evaluate', 6: 'Create'}
        for level, name in level_names.items():
            status = progress.get(str(level), 'locked')
            if status == 'complete':
                st.success(f'✅ Level {level}: {name}')
            elif status == 'active':
                st.info(f'▶️ Level {level}: {name} ← Current')
            else:
                st.text(f'🔒 Level {level}: {name}')
        st.divider()
        current = next((l for l, s in progress.items() if s == 'active'), 'N/A')
        st.metric('Current Level', level_names.get(int(current) if current != 'N/A' else 1, 'Complete'))
```
---
Phase 8 — P1 Features (Week 11, only if P0 is complete)
Goal: Add RAG chat assistant and PDF upload.
> ⚠️ **Do NOT build Phase 8 until all Phase 1–7 tests pass.** These are P1 features. If time is short, skip entirely and document as future work in the thesis.
Files to modify: `llm_utils.py`, `api.py`, new page `pages/00_upload.py`
RAG Fallback Strategy (if ChromaDB is too complex):
```python
def keyword_search_fallback(question: str, pdf_text: str) -> str:
    """Simple keyword search — 20 lines instead of 100+ for ChromaDB."""
    words = question.lower().split()
    sentences = pdf_text.split('.')
    scored = [(s, sum(w in s.lower() for w in words)) for s in sentences]
    top = sorted(scored, key=lambda x: x[1], reverse=True)[:3]
    return ' '.join(s for s, _ in top if _ > 0) or "No relevant content found."
```
---
7. Code Patterns
Always follow these patterns. They exist to prevent common bugs.
Pattern 1 — Every Database Operation Closes Its Connection
```python
# ✅ CORRECT
def get_participant(code: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM participants WHERE code = ?", (code,)).fetchone()
    conn.close()  # ALWAYS close — SQLite "database is locked" error if you forget
    return dict(row) if row else None

# ❌ WRONG — connection never closed
def get_participant_wrong(code: str):
    conn = get_connection()
    return conn.execute("SELECT * FROM participants WHERE code = ?", (code,)).fetchone()
```
Pattern 2 — Every LLM Call Goes Through call_lmstudio()
```python
# llm_utils.py
import httpx
import time
from database import get_connection

LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"

def call_lmstudio(prompt: str, feature: str, participant_id: int) -> str:
    start = time.time()
    response = httpx.post(
        LMSTUDIO_URL,
        json={
            "model": "gpt-oss-20b-uncensored-hauhaucs-aggressive",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200
        },
        timeout=30.0
    )
    elapsed_ms = int((time.time() - start) * 1000)
    result = response.json()["choices"][0]["message"]["content"]
    
    # Log every call — this is research data
    conn = get_connection()
    conn.execute(
        "INSERT INTO llm_logs (participant_id, feature, prompt, response, response_time_ms) VALUES (?, ?, ?, ?, ?)",
        (participant_id, feature, prompt, result, elapsed_ms)
    )
    conn.commit()
    conn.close()
    
    return result
```
Pattern 3 — Level Gate Check in Every FastAPI Route
```python
# api.py
from fastapi import HTTPException

def check_level_access(participant_id: int, required_level: int):
    """Call this at the start of any level-specific route."""
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM bloom_progress WHERE participant_id = ? AND level = ?",
        (participant_id, required_level)
    ).fetchone()
    conn.close()
    
    if not row or row['status'] == 'locked':
        raise HTTPException(status_code=403, detail=f"Level {required_level} is locked.")

@app.post("/validate/definition")
def validate_definition(data: DefinitionRequest):
    check_level_access(data.participant_id, 1)  # Gate check first
    # ... rest of handler
```
Pattern 4 — Session State Check on Every Streamlit Page
```python
# Put this at the TOP of every page in pages/
import streamlit as st
import httpx

# Gate 1: Must be logged in
if 'participant_id' not in st.session_state:
    st.error("Please log in first.")
    st.stop()

# Gate 2: Must have given consent (except consent page itself)
if 'consent_given' not in st.session_state or not st.session_state.consent_given:
    st.warning("Please complete the consent form first.")
    st.stop()
```
Pattern 5 — Autosave on Every Button Click
```python
# ✅ Save immediately when student submits — don't wait until end of session
if st.button("Submit Definition"):
    with st.spinner("Validating..."):
        result = httpx.post("http://localhost:8000/validate/definition", json={...}).json()
    # Save happens inside the API route — done before response returns
    st.success("Saved!")
```
Pattern 6 — Show Response Time to User
```python
# After every LLM call, show timing (this is a research metric)
response_time_s = elapsed_ms / 1000
if response_time_s > 10:
    st.warning(f"⚠️ AI took {response_time_s:.1f}s (over 10s threshold)")
else:
    st.caption(f"AI response time: {response_time_s:.1f}s")
```
---
7.5 Test-Driven Development (TDD) Strategy
**Added:** Phase 2+ | **Tools:** pytest + pytest-cov | **Coverage Target:** 60%+ for business logic

### Why pytest for CogniMap?

| Advantage | Why it matters for your FYP |
|---|---|
| **Simple syntax** | Beginner-friendly — no boilerplate like `unittest` |
| **Auto-discovery** | Just name files `test_*.py` — pytest finds them |
| **Rich assertions** | `assert x == y` instead of `self.assertEqual(x, y)` |
| **Coverage reports** | Easy to show "X% code covered" in thesis |
| **Fast feedback** | Run individual tests during development |
| **Industry standard** | Looks good in demo — shows professional practices |

### Hybrid TDD Approach (Timeline-Friendly)

Given your **9-week timeline** and **beginner-friendly** constraints:

#### ✅ Do TDD for:
1. **Database operations** (`test_database.py`) — critical for data integrity
2. **Level gate enforcement** (`test_gates.py`) — research validity depends on this
3. **Scoring logic** (`test_scoring.py`) — pre/post test calculations must be correct
4. **SUS formula** (`test_questionnaires.py`) — validated psychometric scale
5. **API endpoints** — request validation, error responses, status codes
6. **Edge case handling** — empty inputs, invalid data, boundary conditions

#### ⏸️ Skip TDD for:
1. **Streamlit UI pages** — hard to test, change frequently, manual testing is faster
2. **LLM prompts** — non-deterministic output makes assertions fragile
3. **Graph visualization** — visual verification is more practical

---

## ⚠️ MANDATORY TDD WORKFLOW FOR ALL CODE CHANGES

**This is NOT optional.** Every single code change MUST follow this workflow:

### Before Writing Any Code:
1. **Identify the feature/bug fix** — What exactly are you building or fixing?
2. **List ALL edge cases** — Think from every angle (see Edge Case Checklist below)
3. **Write tests FIRST** — Tests must exist BEFORE implementation code
4. **Watch tests fail** — Confirm tests actually test something (red → green pattern)

### Edge Case Checklist (Test ALL of These):
For EVERY function/endpoint, ask:

**Input Validation:**
- [ ] What if input is `None`?
- [ ] What if input is empty string `""`?
- [ ] What if input is empty list `[]` or empty dict `{}`?
- [ ] What if input has special characters? (`<script>`, SQL injection, etc.)
- [ ] What if input exceeds maximum length?
- [ ] What if input is wrong type? (int instead of str, str instead of int)
- [ ] What if required fields are missing?

**Boundary Conditions:**
- [ ] What if value is 0?
- [ ] What if value is negative?
- [ ] What if value is at minimum allowed?
- [ ] What if value is at maximum allowed?
- [ ] What if value exceeds limits?
- [ ] What if list has 1 item? 100 items? 1000 items?

**Database Operations:**
- [ ] What if record doesn't exist? (returns None)
- [ ] What if duplicate entry is attempted?
- [ ] What if foreign key reference is broken?
- [ ] What if database is locked?
- [ ] What if connection fails mid-operation?
- [ ] What if two users modify same data simultaneously?

**API Endpoints:**
- [ ] What if request body is missing?
- [ ] What if required field is missing?
- [ ] What if authentication is missing?
- [ ] What if user doesn't have permission?
- [ ] What if resource doesn't exist? (404)
- [ ] What if method is wrong? (GET vs POST)
- [ ] What if Content-Type is wrong?

**State Machine / Flow:**
- [ ] What if user tries to skip steps?
- [ ] What if user repeats a completed step?
- [ ] What if session expires mid-flow?
- [ ] What if user goes back to previous page?
- [ ] What if two tabs are open simultaneously?

**Error Handling:**
- [ ] Does it fail gracefully?
- [ ] Is error message user-friendly?
- [ ] Is error logged for debugging?
- [ ] Does it rollback database changes?
- [ ] Does it return correct HTTP status code?

**Research Integrity:**
- [ ] Does this affect data collection?
- [ ] Could this corrupt participant data?
- [ ] Is this action logged for analysis?
- [ ] Does this violate study protocol?

### Implementation Phase:
1. **Write minimal code** to pass tests — nothing more
2. **Run tests** — all must pass (green)
3. **Refactor** — clean up code, keep tests passing
4. **Run tests again** — ensure refactoring didn't break anything

### After Implementation:
1. **Run full test suite** — `pytest tests/ -v`
2. **Check coverage** — `pytest tests/ -v --cov=. --cov-report=term-missing`
3. **Test manually** — run the actual app, verify behavior
4. **Document bugs fixed** — see Bug Summary Template below

---

## 📋 BUG SUMMARY TEMPLATE (Use After Every Code Change)

After each testing session, create a quick summary:

```markdown
### Bug Summary — [Date] — [Feature Name]

**Bugs Found & Fixed:**

1. **Bug:** [Description of what was wrong]
   - **Location:** `filename.py:function_name()`, line X
   - **Root Cause:** [Why it happened — e.g., "didn't handle None case"]
   - **Fix:** [What you changed]
   - **Test Added:** `test_filename.py::TestClass::test_specific_case`
   - **Severity:** [Critical / High / Medium / Low]

2. **Bug:** [Next bug...]

**Code Changes Made:**
- Modified `filename.py`:
  - Function `foo()`: Added null check at start
  - Function `bar()`: Changed return type from int to Optional[int]
- Created `new_file.py`:
  - New helper function `validate_input()`

**Tests Added/Updated:**
- `test_filename.py::TestClass::test_new_scenario` — Tests [what]
- `test_filename.py::TestClass::test_edge_case` — Tests [what]

**Test Results:**
```
✅ 42 passed, 0 failed
Coverage: 57% (database.py: 63%, scoring_utils.py: 94%)
```

**Manual Verification:**
- [ ] Tested in browser with valid input
- [ ] Tested in browser with invalid input
- [ ] Verified database state after operation
- [ ] Checked error messages are user-friendly

**Remaining Issues:**
- [ ] [Any known issues not yet fixed, or "None"]

**Next Steps:**
- [ ] [What to do next, or "Continue to next feature"]
```

---

## 🔄 CONTINUOUS TESTING REMINDER

**At the start of EVERY coding session:**
1. Run `pytest tests/ -v` — ensure all existing tests pass
2. If tests fail: fix them FIRST before adding new features
3. If adding new code: write tests FIRST

**At the end of EVERY coding session:**
1. Run `pytest tests/ -v --cov=.` — check coverage didn't drop
2. Run manual test of affected feature
3. Commit tests AND code together — never separate

**Before EVERY git commit:**
1. Run full test suite one more time
2. Ensure no tests are failing
3. Ensure coverage is acceptable (>60% for business logic)

---

### Test Files Structure

```
tests/
├── conftest.py              # Shared fixtures (database connections, sample data)
├── test_database.py         # Database operations (participant lookup, consent, bloom progress)
├── test_gates.py            # Level gate enforcement (cannot skip levels)
├── test_scoring.py          # SUS, NASA-TLX, learning gain calculations
└── test_questionnaires.py   # Questionnaire submission logic (Phase 6)
```

### Setup Commands

```bash
# Install pytest (already in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/test_database.py -v

# Run specific test function
pytest tests/test_scoring.py::TestSUSScoring::test_sus_midrange_score -v
```

### Example Test Pattern

```python
# tests/test_database.py
import pytest
from database import get_participant_by_code, update_consent

def test_get_participant_by_valid_code(db_connection):
    """P01 should be found and return correct data."""
    participant = get_participant_by_code("P01", db_path=os.environ.get('TEST_DB_PATH'))
    
    assert participant is not None
    assert participant['code'] == "P01"
    assert participant['consent_given'] == 0  # Default: no consent yet

def test_get_participant_by_invalid_code(db_connection):
    """Invalid code P99 should return None."""
    participant = get_participant_by_code("P99", db_path=os.environ.get('TEST_DB_PATH'))
    
    assert participant is None
```

### Fixtures Explained (from conftest.py)

| Fixture | Scope | Provides |
|---|---|---|
| `test_database` | session | Fresh test DB file, auto-cleanup |
| `db_connection` | function | SQLite connection, auto-closes |
| `sample_participant` | function | P01 participant dict |
| `sample_test_data` | function | Pre-test result for P01 |

### Coverage Goals by Phase

| Phase | Target | Critical Files |
|---|---|---|
| Phase 3 | 40% | `database.py`, `api.py` (gate checks) |
| Phase 4 | 50% | + `llm_utils.py` (paraphrase logic) |
| Phase 5 | 60% | + `graph_utils.py` (node/edge operations) |
| Phase 6 | 70% | + `scoring_utils.py`, questionnaire logic |
| Phase 7 | 75% | Full regression suite |

### Thesis Benefits

You can include a **Testing Strategy** section:
- "Unit tests covered X% of business logic"
- "Critical paths (gates, scoring) tested before implementation"
- "Automated regression testing prevented data corruption"

### Debugging Test Failures

```bash
# See detailed output
pytest tests/ -v -s

# Stop on first failure
pytest tests/ -x

# Run tests that failed last time
pytest tests/ --lf

# Show local variables in tracebacks
pytest tests/ -l
```

### Test Database Isolation

Tests use a **separate** `test_cms_database.db` file to avoid corrupting your development data. This file is:
- Created fresh at the start of each test session
- Deleted automatically after all tests complete
- Never committed to Git (in `.gitignore`)

Add to `.gitignore`:
```
# Test database
test_cms_database.db
# Coverage reports
htmlcov/
.coverage
```

---
8. FastAPI Routes Reference
Build these routes in `api.py` in this order:
```
POST /login                         # Validate participant code, return participant_id
POST /consent/{participant_id}      # Mark consent_given=1 in DB
GET  /progress/{participant_id}     # Return level statuses dict
POST /test/submit                   # Save pre or post test score
POST /validate/definition           # LLM definition check → VALID or NEEDS_REVISION
POST /nodes/add                     # Add concept node to NetworkX graph + DB
POST /validate/paraphrase           # Sentence-transformer similarity check
POST /edges/add                     # Add edge to graph
POST /validate/edge                 # LLM adversarial challenge → challenge question
POST /edges/defend                  # Save student's defense, mark defended_at
POST /questionnaire/sus             # Save SUS responses + calculate score
POST /questionnaire/nasa            # Save NASA-TLX scores
GET  /export/{participant_id}       # Return all participant data as CSV
```
---
9. LLM Prompt Rules
These are non-negotiable research integrity requirements.
Rule	Why
NEVER give the correct answer in prompts	Core research principle — tests if students can construct knowledge
Always end prompts with "Respond now:"	Reduces LLM preamble, keeps responses under 50 words
Always specify response format	VALID:/NEEDS_REVISION: or Challenge: prefixes make parsing reliable
Log every single call	Response time is a primary research metric (90% must be <10s)
Set timeout=30.0 on httpx calls	LM Studio can hang; 30s timeout prevents app freeze
Max 2 revision cycles per node	After 2 NEEDS_REVISION responses, auto-accept with a note
---
10. Critical UX Rules
These are not optional. They affect research integrity.
Rule	Implementation
Consent must come before everything	`pages/01_consent.py` blocks all other pages until `consent_given=1` in DB
Cannot retake pre-test	Query `test_results` for `test_type='pre'` before rendering; redirect if found
Cannot skip levels by URL	Every page queries API for level status; shows error if locked
Max 2 revision cycles per node	Track `revision_count` in DB; auto-accept on 3rd attempt with a note
Autosave everything	Write to DB on every button click, not just session end
Show AI response time	Display `response_time_ms` from logs; warn if >10s
Level 3 needs 3 defended edges	Count `defended_at IS NOT NULL` in `concept_edges`; gate on 3
---
11. Graph Visualization
```python
# graph_utils.py
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import json

BLOOM_COLORS = {
    1: '#FF6B6B',  # Remember — Red
    2: '#FF9F43',  # Understand — Orange
    3: '#FECA57',  # Apply — Yellow
    4: '#48DBFB',  # Analyze — Blue
    5: '#1DD1A1',  # Evaluate — Green
    6: '#7BED9F',  # Create — Light Green
}

def load_graph(participant_id: int) -> nx.DiGraph:
    path = f'graph_{participant_id}.json'
    try:
        with open(path) as f:
            return nx.node_link_graph(json.load(f))
    except FileNotFoundError:
        return nx.DiGraph()

def save_graph(G: nx.DiGraph, participant_id: int):
    with open(f'graph_{participant_id}.json', 'w') as f:
        json.dump(nx.node_link_data(G), f)

def render_graph_in_streamlit(G: nx.DiGraph):
    net = Network(height='500px', width='100%', directed=True)
    net.from_nx(G)
    net.set_options('''
    var options = {
      "nodes": {"font": {"size": 14}, "color": {"background": "#2E86AB"}},
      "edges": {"arrows": {"to": {"enabled": true}}}
    }''')
    net.save_graph('/tmp/cognimap_graph.html')
    with open('/tmp/cognimap_graph.html', 'r') as f:
        html = f.read()
    components.html(html, height=520)
```
---
12. Testing Checklist
Run these tests manually before each study session. Print this page.

### Infrastructure ✅ COMPLETE
[x] LM Studio server responds in <10 seconds (verify via Local Server tab in LM Studio GUI)
[x] `http://localhost:8000/docs` loads Swagger UI
[x] `http://localhost:8501` loads login screen
[x] `cms_database.db` exists; `SELECT COUNT(*) FROM participants` returns 10

### Level Gate Security ✅ PARTIAL
[ ] Accessing Level 2 URL without completing Level 1 → blocked with error (Phase 3)
[x] Trying to re-take pre-test → returns 400 error (tested)
[x] Entering invalid participant code → error shown, no login

### Core Features ✅ PARTIAL
[x] F1: P01 logs in; P99 is rejected
[x] F2: 18 questions render; score saved correctly; cannot retake
[ ] F3: Level 2 returns 403 if Level 1 not complete (test via curl) — Phase 3
[ ] F4: Concept + definition saves node to graph JSON file — Phase 3
[ ] F5: LLM returns VALID or NEEDS_REVISION prefix in <10s — Phase 3
[ ] F6: All concepts AI-validated unlocks Level 2
[ ] F7: Copy-paste rejected (similarity >0.95); genuine paraphrase accepted (0.85–0.95) — Phase 4
[ ] F8: Graph renders with nodes visible, edges have arrows — Phase 3
[ ] F9: All actions visible in SQLite; CSV export downloads — Phase 7
[ ] F10: SUS score = (sum of scaled responses) × 2.5 — Phase 6
[ ] F11: NASA-TLX 3 scores saved — Phase 6
[ ] F12: All LLM calls in `llm_logs`; `response_time_ms` populated — Phase 3

### Full Session Flow
[ ] Complete flow runs without errors: Login → Consent → Demo → L1 → L2 → L3 → L4 → L5 → L6
[ ] All concept data visible in DB after session
[ ] CSV export works for participant data (nodes, edges, LLM logs)
---
13. Study Session Launch
run.sh (Mac/Linux)
```bash
#!/bin/bash
echo "🚀 Starting CogniMap..."

# Activate virtual environment
source venv/bin/activate

# Backup database before session
mkdir -p backups
cp cms_database.db backups/cms_backup_$(date +%Y%m%d_%H%M).db
echo "✅ Database backed up"

# LM Studio must be started manually via GUI before running this script
echo "⚠️ Ensure LM Studio Local Server is running on port 1234"
sleep 3
echo "✅ LM Studio ready"

# Start FastAPI in background
uvicorn api:app --host 0.0.0.0 --port 8000 &
sleep 2
echo "✅ FastAPI ready at http://localhost:8000"

# Start Streamlit
echo "✅ CogniMap ready at http://localhost:8501"
streamlit run app.py
```
```bash
chmod +x run.sh
./run.sh  # Run before every study session
```
run.bat (Windows)
```batch
@echo off
echo Starting CogniMap...
call venv\Scripts\activate
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
copy cms_database.db backups\cms_backup_%dt:~0,12%.db
REM LM Studio must be started manually via GUI before running this script
echo Ensure LM Studio Local Server is running on port 1234
timeout /t 3
start "" uvicorn api:app --host 0.0.0.0 --port 8000
timeout /t 2
echo CogniMap ready at http://localhost:8501
streamlit run app.py
```
Pre-Session Checklist (Print and Use)
```
□ 1. Laptop charged or plugged in (battery >80%)
□ 2. (venv) visible in terminal prompt
□ 3. LM Studio Local Server running on port 1234 (verify in GUI)
□ 4. http://localhost:8000/docs loads
□ 5. http://localhost:8501 loads login screen
□ 6. backups/ folder has today's timestamp
□ 7. Next participant code ready (e.g. P04 for 4th participant)
□ 8. git status shows "nothing to commit"
□ 9. Physical consent forms printed (backup)
□ 10. Phone timer ready for 20-min tests
```
---
14. Data Backup Strategy
> ⚠️ One corrupted database = lost research data. Prevent this at all costs.
When	What	How
Before every session	Copy DB	`run.sh` does this automatically
Every day	Git commit	`git add cms_database.db && git commit -m "data backup"` to a private `backup` branch
Every week	Full project backup	Copy entire `cognimap-fyp/` folder to Google Drive or external drive
Never commit the database to your `main` branch — create a separate `backup` branch for data.
---
15. Debugging Guide
Problem	First Check	Fix
LM Studio response >10s	Check RAM usage (Activity Monitor / Task Manager)	Close other apps; use Q4_K_M quantized model; lower context length in LM Studio settings
"database is locked" SQLite error	Two connections open simultaneously	Ensure every function calls `conn.close()`
pyvis graph doesn't render	Check `/tmp/cognimap_graph.html` exists	Verify `streamlit.components.v1` import; check pyvis version
Streamlit and FastAPI not talking	Both servers running? httpx installed?	`httpx.get("http://localhost:8000")` in Python shell
sentence-transformers OOM	Not enough RAM	Switch to TF-IDF cosine similarity fallback
ChromaDB too slow on first run	Downloading model (~80MB)	Wait for first download; subsequent calls are fast
Streamlit session state lost	Browser tab refreshed	All critical state must be in DB, not just session_state
---
16. Gemini CLI Usage
Since you are using Gemini CLI as your AI coding assistant, here are optimal prompts for each task type:
When you hit a bug
```
I am building CogniMap, a Python app with Streamlit + FastAPI + SQLite + LM Studio.

Error message:
[PASTE FULL ERROR]

Code that caused it:
[PASTE THE FUNCTION]

Tell me: (1) what this error means in plain English, (2) which line caused it, (3) how to fix it and why.
```
When you need a new feature
```
I am building CogniMap. Here is my current [filename]:
[PASTE CURRENT FILE]

I need to add [DESCRIBE FEATURE EXACTLY].

Constraints:
- Must use my existing SQLite schema (tables: participants, bloom_progress, concept_nodes, concept_edges, llm_logs, test_results, sus_responses, nasa_tlx)
- Must follow the FastAPI + Streamlit pattern already in my code
- Beginner-friendly Python only — no advanced patterns
- Every LLM call must go through call_lmstudio() in llm_utils.py

Write the code, then explain each new function in plain English.
```
When you need code explained
```
Explain this Python code to me line by line as if I am a complete beginner.
For each line: (1) what it does, (2) why it is needed, (3) what breaks if I remove it.

[PASTE CODE]
```
What Gemini CLI cannot help with
Task	Do this instead
Debugging LM Studio speed on your specific hardware	Test manually via LM Studio Local Server tab and monitor response time
Setting the right similarity threshold (0.85–0.95)	Run 20 test paraphrases and measure where the boundary falls
Research design validity	Follow PRD Section 9; consult your supervisor
pyvis rendering bugs	Check github.com/WestHealth/pyvis issues for your exact version
---
17. Definition of Done
The MVP is complete when ALL of the following are true:

### Technical
[ ] F1–F12 all pass manual testing (see Testing Checklist section)
[ ] Full session runs end-to-end without errors for 2 test participants
[ ] Level gates enforced: attempting to skip via URL returns 403
[ ] 90% of logged LLM responses under 10,000ms
[ ] CSV export works for all participant data
[ ] `run.sh` / `run.bat` starts all services in one command
[ ] `.gitignore` excludes all sensitive/generated files

### Research
[ ] 10 participants complete full sessions (minimum N=8)
[ ] Pre and post test scores stored for all participants
[ ] SUS scores stored; mean calculated
[ ] All LLM interaction logs exportable for qualitative analysis
[ ] Zero critical errors during any live session

### Documentation
[ ] README.md with setup instructions (verify: a classmate can follow it)
[ ] All code committed to Git; no real participant names in repo
[ ] Code comments on every non-obvious function
[ ] Thesis Chapters 1–6 drafted
[ ] 10-minute demo rehearsed twice successfully

### Sign-Off
[ ] Supervisor final approval received

---

### Current Progress (as of April 5, 2026 — Evening)

**🆕 CogniMap v2.0: Flask + vis.js Redesign**
- ✅ Phase 1 Complete: Flask foundation + single-page UI
- ✅ TDD Tests: 70 tests created, 67 passing (96%)
- ✅ vis.js Integration: Interactive graph visualization working
- ✅ Auth System: Login, logout, consent, session management
- ✅ Graph CRUD: Node/edge creation, updates, visualization
- ✅ Level Progression: Complete/unlock levels, layer progression
- ⚠️ Known Issue: 3 test failures due to test DB isolation (infrastructure, not code bug)

**Files Created:**
- `app_flask.py` — Flask backend with 20+ API routes
- `templates/index.html` — Single-page app shell
- `static/css/style.css` — Clean, minimal design (237 lines)
- `static/js/app.js` — Client-side logic (369 lines)
- `static/lib/vis-9.1.2/` — vis.js library (from References)

**Test Coverage (v2.0):**
- `test_flask_auth.py`: 21 tests (login, session, auth enforcement)
- `test_flask_consent.py`: 12 tests (consent flow, state management)
- `test_flask_graph.py`: 17 tests (graph CRUD, edge cases)
- `test_flask_progress.py`: 20 tests (progress, level completion)
- **Total:** 70 tests, 67 passed, 3 failed (96% pass rate)

**Legacy System (Streamlit — Still Functional):**
- ✅ Phase 1: Infrastructure (login, database, API, consent)
- ⚠️ Phase 2: Consent (pre/post tests archived for future use)
- ✅ Phase 3-6: All 6 Bloom's levels implemented
- ✅ TDD Infrastructure: 31 passing tests (original suite)

**Archived (Available for Future Use):**
- 📦 Pre/Post Tests: 18 questions, scoring logic (`archive/test_system.py`)
- 📦 SUS/NASA-TLX: Questionnaire forms, scoring utilities (`archive/scoring_utils.py`)
- 📦 Test Suite: `archive/test_scoring.py` (22 tests, 94% coverage)

**Next Steps for v2.0:**
1. Fix test database isolation issue (Flask app should use TEST_DB_PATH)
2. Phase 2: PDF upload + concept extraction pipeline
3. Phase 3: Level 1 UI (click node → define → AI validate)
4. Phase 4: Level 2-6 interfaces
5. Manual testing + polish

---
18. Research Formulas Reference
```python
# Learning Gain (Primary Metric)
from scipy import stats
t_statistic, p_value = stats.ttest_rel(pre_scores, post_scores)
# Success: p < 0.05 OR Cohen's d > 0.5

# Cohen's d (Effect Size)
import numpy as np
differences = np.array(post_scores) - np.array(pre_scores)
cohens_d = differences.mean() / differences.std()
# <0.2=negligible, 0.2-0.5=small, 0.5-0.8=medium, >0.8=large

# SUS Score
def calculate_sus(responses):
    odd_sum = sum(responses[f'q{i}'] - 1 for i in [1,3,5,7,9])
    even_sum = sum(5 - responses[f'q{i}'] for i in [2,4,6,8,10])
    return (odd_sum + even_sum) * 2.5
# Success: score > 68

# LLM Response Time (System Metric)
# Success: 90th percentile of response_time_ms < 10,000
import pandas as pd
df = pd.read_sql("SELECT response_time_ms FROM llm_logs", conn)
p90 = df['response_time_ms'].quantile(0.90)
```
---
19. Scaling Path (For Thesis Context Only — Do Not Build)
Phase	When	What Changes
V1 FYP MVP	Now	Localhost, 10 participants, SQLite, LM Studio
V2 Pilot	Post-graduation	50–200 users, PostgreSQL, Docker, cloud hosting
V2.5 Cloud LLM	When local LLM limits speed	Replace LM Studio with Anthropic Claude API
V3 Multi-Institution	1–2 years	React frontend, FastAPI microservices
V4 Full Product	3+ years	Mobile app, LMS integration (Canvas/Moodle)
Every technology chosen has a clear upgrade path: SQLite→PostgreSQL, LM Studio→Claude API, Streamlit→React, NetworkX→Neo4j.

---

## 📝 Development Log: April 5, 2026

### What Was Built Today
**Phase 1 Infrastructure Fix + Phase 2 Complete**

**Test Database Isolation Fixed:**
- Created `db_wrapper.py` — routes all DB calls through `TEST_DB_PATH`
- Updated 4 Flask test files to import `db_wrapper`
- Enhanced `conftest.py` with full table reset between tests
- **Result: 89/89 tests passing (100%)**

**Phase 2: PDF Upload + Level 1 (Remember):**
- PDF upload UI → concept extraction → graph rendering
- Click node → definition textarea → AI validates
- +570 lines of frontend code (HTML/CSS/JS)
- 19 new TDD tests

**Bug Fixes:**
- Fixed vis.js library path (`/lib/vis-9.1.2/`)
- Reset P01 progress state in production DB

### How to Run
```bash
# Activate virtual environment
.\venv\Scripts\activate

# Start Flask app
python app_flask.py

# Access at:
http://localhost:5000
```

### Testing
```bash
# Run all Flask v2.0 tests
python -m pytest tests/test_flask_*.py -v

# Run with coverage
python -m pytest tests/test_flask_*.py --cov=app_flask --cov-report=term-missing
```

---
AGENTS.md | CogniMap MVP | Version 2.0 | April 8, 2026
Phase 1 Complete: Flask + vis.js Architecture — Git Pushed (`559cdc7`)