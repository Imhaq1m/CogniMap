# AGENTS.md — CogniMap MVP
## Universal AI Coding Agent Instructions

> **How to use this file:** This is the brain file for any AI coding agent helping build CogniMap.
> Read this entirely before writing a single line of code. Every section is here for a reason.
> When in doubt, re-read. When stuck, re-read. When tempted to skip a step, re-read.

---

## 1. Project Overview

**CogniMap** is a local-first, AI-powered learning system for a university Final Year Project (FYP) research study. It scaffolds learning through Bloom's Taxonomy levels without automating thinking.

| Field | Value |
|---|---|
| App Name | CogniMap (Cognitive Mastery System) |
| Tagline | "AI that scaffolds learning without automating thinking" |
| Purpose | FYP research study — 10 participants, single study session each |
| Deployment | Localhost only (no cloud, no internet required during sessions) |
| Developer Level | Python learner / vibe-coder — beginner-safe patterns only |
| Primary Language | Python 3.11 |
| Timeline | 9-week build window (Weeks 4–13 of FYP) |
| Budget | $0 — all open-source, all local |

### What CogniMap Does
Students upload a learning document (PDF), then progress through Bloom's Taxonomy levels:
1. **Level 1 — Remember:** Type a concept + own-words definition → AI validates without giving the answer
2. **Level 2 — Understand:** Paraphrase the definition → semantic similarity check detects copy-paste
3. **Level 3 — Apply/Analyze:** Create concept connections + justify them → AI adversarially challenges justifications

Students **cannot skip levels**. Gates are enforced by the FastAPI backend. All interactions are logged for research analysis.

### Why It Exists (Research Context)
- 92% of students use AI tools, but 80–85% of AI-generated content only targets Remember/Understand
- CogniMap forces genuine thinking by using AI to validate *process*, not provide *answers*
- Pre/post tests measure actual learning gain; SUS + NASA-TLX measure usability and cognitive load

---

## 2. Tech Stack

Understand this before touching any file. Every tool was chosen deliberately.

| Layer | Tool | Version | Why |
|---|---|---|---|
| Frontend | Streamlit | 1.32.0 | Python-only, no HTML/CSS needed, renders in browser |
| Backend API | FastAPI | 0.110.0 | Auto API docs, Pydantic validation, enforces state machine |
| LLM Runtime | LM Studio | latest | GUI-based local LLM server, free, works offline, OpenAI-compatible API |
| LLM Model | Gemma 4 E4B Uncensored | — | Fits 8GB RAM, fast, excellent instruction-following |
| Graph Core | NetworkX | 3.2.1 | JSON-serializable, integrates natively with pyvis |
| Graph Visual | pyvis | 0.3.2 | Interactive HTML graphs, embeddable in Streamlit |
| Vector DB | ChromaDB (embedded) | 0.4.24 | No server, pure Python, persists to folder |
| Relational DB | SQLite (built-in) | — | Single file, zero setup, easy backup |
| Embeddings | sentence-transformers | 2.6.1 | all-MiniLM-L6-v2, 80MB, CPU-friendly, offline |
| PDF Reading | PyPDF2 | 3.0.1 | Extract text from student-uploaded documents |
| HTTP Client | httpx | 0.27.0 | Streamlit uses this to call FastAPI |
| Data Export | pandas | 2.2.0 | Export SQLite data to CSV for research analysis |

### Ports (All Localhost)
- `http://localhost:8501` — Streamlit frontend (student-facing)
- `http://localhost:8000` — FastAPI backend (API + business logic)
- `http://localhost:1234` — LM Studio local server

### How Components Talk
```
Student (Browser) → Streamlit app.py
  → httpx HTTP calls → FastAPI api.py
    → LM Studio (LLM calls via REST)
    → SQLite (structured data)
    → NetworkX (graph, persisted as JSON)
    → ChromaDB (PDF embeddings, P1 feature)
```

---

## 3. Project Folder Structure

Create this exact structure before writing feature code. Do not rename files — the rest of this document references them by name.

```
cognimap-fyp/
├── app.py                      # Streamlit frontend entry point
├── api.py                      # FastAPI backend (all routes here)
├── database.py                 # All SQLite operations
├── graph_utils.py              # NetworkX graph operations
├── llm_utils.py                # LM Studio calls + ChromaDB RAG
├── test_system.py              # Pre/post test questions + scoring logic
├── requirements.txt            # Python dependencies (exact versions)
├── .gitignore                  # Excludes venv/, *.db, chroma_db/, *.json
├── README.md                   # Setup instructions (must work for a stranger)
├── run.sh                      # One-command launcher (Mac/Linux)
├── run.bat                     # One-command launcher (Windows)
├── .streamlit/
│   └── config.toml             # Streamlit theme configuration
├── pages/                      # Streamlit multi-page app
│   ├── 01_consent.py           # Digital consent form
│   ├── 02_pretest.py           # 18-question pre-test
│   ├── 03_level1_remember.py   # Concept definition + AI validation
│   ├── 04_level2_understand.py # Paraphrase + semantic similarity
│   ├── 05_level3_apply.py      # Edge creation + adversarial challenge
│   ├── 06_posttest.py          # 18-question post-test
│   └── 07_questionnaires.py    # SUS + NASA-TLX forms
├── tests/                      # Unit tests
│   ├── test_gates.py           # Test level gate enforcement
│   └── test_database.py        # Test SQLite operations
├── backups/                    # Auto-created by run.sh; never commit
└── docs/
    ├── thesis/
    └── diagrams/
```

---

## 4. Environment Setup

Complete these in order. Each step unlocks the next. Estimated time: 3–4 hours on a fresh machine.

### Step 1 — Python 3.11
```bash
python --version  # Must show 3.11.x or 3.12.x
# Download from python.org if needed (3.11 preferred — better wheel support)
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
# 2. Open LM Studio GUI → Search for "gemma-4-e4b-uncensored-hauhaucs-aggressive" → Download the model
# 3. In LM Studio: Go to Local Server tab → Click "Start Server" (keep LM Studio open)
# 4. Test it responds under 10 seconds via API:
curl http://localhost:1234/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"gemma-4-e4b-uncensored-hauhaucs-aggressive","messages":[{"role":"user","content":"Say hello in one sentence"}]}'
```

### Step 4 — requirements.txt
Create this file in the project root exactly as shown:
```
streamlit==1.32.0
fastapi==0.110.0
uvicorn==0.27.1
httpx==0.27.0
pydantic==2.6.0
networkx==3.2.1
pyvis==0.3.2
chromadb==0.4.24
sentence-transformers==2.6.1
PyPDF2==3.0.1
python-multipart==0.0.9
pandas==2.2.0
scipy==1.12.0
```

```bash
pip install -r requirements.txt
# Takes 5–10 minutes — sentence-transformers is large
```

### Step 5 — Streamlit Theme
Create `.streamlit/config.toml`:
```toml
[theme]
primaryColor = '#2E86AB'
backgroundColor = '#FFFFFF'
secondaryBackgroundColor = '#EBF4F8'
textColor = '#1A1A1A'
font = 'sans serif'
```

### Step 6 — Git
```bash
git init
echo "venv/ *.db chroma_db/ *.json __pycache__/ .env backups/" > .gitignore
git add .
git commit -m "Initial project setup"
# Push to a private GitHub repo — do this NOW before writing any code
```

### Step 7 — Verify Everything Works
```bash
# Terminal 1: LM Studio server (start via GUI, then verify)
curl http://localhost:1234/v1/models  # Should return model list

# Terminal 2: FastAPI (creates a blank api.py first)
uvicorn api:app --reload --port 8000
# Visit http://localhost:8000/docs — should show Swagger UI

# Terminal 3: Streamlit (creates a blank app.py first)
streamlit run app.py
# Visit http://localhost:8501 — should show app
```

---

## 5. Database Schema

**database.py owns all SQLite operations.** No other file writes to the database directly — they call functions from database.py.

### Tables

```sql
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,         -- P01 through P10
    consent_given INTEGER DEFAULT 0,   -- 0=no, 1=yes
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bloom_progress (
    participant_id INTEGER,
    level INTEGER,                     -- 1=Remember, 2=Understand, 3=Apply
    status TEXT DEFAULT 'locked',      -- locked | active | complete
    unlocked_at TEXT,
    PRIMARY KEY (participant_id, level)
);

CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    test_type TEXT,                    -- 'pre' or 'post'
    score REAL,                        -- percentage 0-100
    bloom_level_scores TEXT,           -- JSON: {"1": 80, "2": 60, ...}
    taken_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concept_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    concept TEXT NOT NULL,
    definition TEXT NOT NULL,
    validation_result TEXT,            -- 'VALID' or 'NEEDS_REVISION'
    revision_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    from_node TEXT,
    to_node TEXT,
    justification TEXT,
    adversarial_challenge TEXT,        -- The AI's challenge question
    defended_at TEXT                   -- NULL until student defends
);

CREATE TABLE IF NOT EXISTS llm_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER,
    feature TEXT,                      -- e.g. 'definition_validator', 'edge_challenger'
    prompt TEXT,
    response TEXT,
    response_time_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sus_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER UNIQUE,
    q1 INTEGER, q2 INTEGER, q3 INTEGER, q4 INTEGER, q5 INTEGER,
    q6 INTEGER, q7 INTEGER, q8 INTEGER, q9 INTEGER, q10 INTEGER,
    total_score REAL,
    submitted_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nasa_tlx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER UNIQUE,
    mental_demand INTEGER,             -- 1-10 scale
    effort INTEGER,                    -- 1-10 scale
    frustration INTEGER,               -- 1-10 scale
    submitted_at TEXT DEFAULT (datetime('now'))
);
```

### Seed Data (Run Once)
```python
# In database.py — call initialize_database() from api.py startup
def seed_participants():
    """Insert participant codes P01–P10 if not already present."""
    conn = get_connection()
    cursor = conn.cursor()
    for i in range(1, 11):
        code = f"P{i:02d}"  # P01, P02, ..., P10
        cursor.execute(
            "INSERT OR IGNORE INTO participants (code) VALUES (?)", (code,)
        )
        # Initialize all 3 levels as 'locked' for each participant
        participant_id = cursor.execute(
            "SELECT id FROM participants WHERE code = ?", (code,)
        ).fetchone()[0]
        for level in range(1, 4):
            cursor.execute(
                "INSERT OR IGNORE INTO bloom_progress (participant_id, level, status) VALUES (?, ?, ?)",
                (participant_id, level, 'locked' if level > 1 else 'active')
            )
    conn.commit()
    conn.close()
```

---

## 6. Implementation Phases

Build in this order. Do not jump ahead. Each phase has a clear test before moving on.

---

### Phase 1 — Infrastructure (Week 4)
**Goal:** All three servers start. Login works. Database exists.

**Files to create:** `database.py`, `api.py` (skeleton), `app.py` (login page only)

**Build order:**
1. `database.py` — `initialize_database()`, `seed_participants()`, `get_connection()`
2. `api.py` — startup event calls `initialize_database()`, add `POST /login` endpoint
3. `app.py` — login screen with participant code input, stores `participant_id` in `st.session_state`

**Test before moving on:**
- [ ] `uvicorn api:app --reload` starts with no errors
- [ ] `streamlit run app.py` shows login form
- [ ] Entering `P01` logs in; entering `INVALID` shows error
- [ ] SQLite file `cms_database.db` exists with 8 tables and 10 participant rows

---

### Phase 2 — Consent + Pre-Test (Week 5)
**Goal:** Consent is stored. Pre-test runs and scores are saved.

**Files to create:** `test_system.py`, `pages/01_consent.py`, `pages/02_pretest.py`

**Build order:**
1. `test_system.py` — hardcode 18 test questions (3 per Bloom level 1–6), scoring function
2. `api.py` — add `POST /consent/{participant_id}`, `POST /test/submit`
3. `pages/01_consent.py` — show consent text, digital signature input, submit button
4. `pages/02_pretest.py` — render 18 radio-button questions, submit, save score to DB

**Test before moving on:**
- [ ] Consent page blocks access to all other pages until signed
- [ ] Pre-test renders all 18 questions
- [ ] Submitting saves score to `test_results` table with `test_type='pre'`
- [ ] Cannot take pre-test twice (query DB before rendering)

---

### Phase 3 — Level 1: Remember (Week 6)
**Goal:** Students define concepts. AI validates without giving the answer.

**Files to create:** `llm_utils.py`, `graph_utils.py`, `pages/03_level1_remember.py`

**Build order:**
1. `llm_utils.py` — `call_lmstudio(prompt, feature, participant_id)` — calls LM Studio, logs to `llm_logs`, returns response text
2. `graph_utils.py` — `load_graph()`, `save_graph()`, `add_node()`, `render_graph_in_streamlit()`
3. `api.py` — add `POST /validate/definition`, `POST /nodes/add`, `GET /progress/{participant_id}`
4. `pages/03_level1_remember.py` — concept input → definition textarea → submit → show AI feedback
5. Level 1 quiz logic + `POST /quiz/level1/submit` endpoint (gate: ≥70% score → unlock Level 2)

**LLM Prompt for Definition Validator (critical — do not change the NEVER GIVE THE ANSWER rule):**
```python
DEFINITION_VALIDATOR_PROMPT = """You are an educational AI assistant for CogniMap, a learning tool based on Bloom's Taxonomy.

A student is learning from their own uploaded document. They have just typed this definition of a concept in their own words.

Concept: {concept}
Student's Definition: {definition}

Your job is to validate whether this definition shows genuine understanding. You MUST follow these rules:
1. NEVER give the correct definition or the answer — that defeats the learning purpose
2. If valid: respond with "VALID: [one sentence of specific encouragement about what they got right]"
3. If needs revision: respond with "NEEDS_REVISION: [one specific question that guides them to think deeper, without revealing the answer]"
4. Keep your response under 50 words
5. Be encouraging but honest

Respond now:"""
```

**Test before moving on:**
- [ ] Student can enter a concept + definition
- [ ] AI responds with VALID or NEEDS_REVISION in under 10 seconds
- [ ] Response is logged to `llm_logs` with `response_time_ms`
- [ ] Node is saved to NetworkX graph JSON file
- [ ] Graph renders in browser with pyvis
- [ ] Level 1 quiz gate: scoring <70% shows "try again"; ≥70% updates `bloom_progress` Level 2 to 'active'

---

### Phase 4 — Level 2: Understand (Week 7)
**Goal:** Students paraphrase. Semantic similarity detects copy-paste.

**Files to create:** `pages/04_level2_understand.py`

**Build order:**
1. `llm_utils.py` — add `check_paraphrase(original, paraphrase)` using sentence-transformers cosine similarity
2. `api.py` — add `POST /validate/paraphrase`
3. `pages/04_level2_understand.py` — show original definition (read-only), paraphrase textarea, submit

**Similarity Logic:**
```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('all-MiniLM-L6-v2')

def check_paraphrase(original: str, paraphrase: str) -> dict:
    embeddings = model.encode([original, paraphrase])
    similarity = float(util.cos_sim(embeddings[0], embeddings[1]))
    
    if similarity > 0.95:
        return {"result": "COPY_PASTE", "similarity": similarity,
                "feedback": "This is too similar to the original. Use your own words."}
    elif similarity >= 0.85:
        return {"result": "VALID", "similarity": similarity,
                "feedback": "Good paraphrase — you've shown you understand this."}
    else:
        return {"result": "TOO_DIFFERENT", "similarity": similarity,
                "feedback": "This seems off-topic from the original definition. Try again."}
```

**Test before moving on:**
- [ ] Copy-pasting original definition is rejected (similarity >0.95)
- [ ] Genuine paraphrase with similarity 0.85–0.95 is accepted
- [ ] Completely unrelated text is rejected (similarity <0.85)
- [ ] Level 2 quiz gate enforced; Level 3 unlocks on pass

---

### Phase 5 — Level 3: Apply + Adversarial (Week 8)
**Goal:** Students connect concepts. AI challenges their justifications.

**Files to create:** `pages/05_level3_apply.py`

**Build order:**
1. `graph_utils.py` — add `add_edge(from_node, to_node, justification)`, `get_nodes_for_participant()`
2. `api.py` — add `POST /edges/add`, `POST /validate/edge`
3. `pages/05_level3_apply.py` — show existing nodes as dropdowns, justification textarea, submit → show adversarial challenge → student defends

**LLM Prompt for Adversarial Edge Validator:**
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

**Test before moving on:**
- [ ] Student can select two existing nodes from dropdowns
- [ ] AI returns a challenge question (not a confirmation)
- [ ] Student can type a defense; defense saved to `concept_edges.defended_at`
- [ ] 3 defended edges required to complete Level 3

---

### Phase 6 — Post-Test + Questionnaires (Week 9)
**Goal:** Data collection complete. All metrics captured.

**Files to create:** `pages/06_posttest.py`, `pages/07_questionnaires.py`

**Build order:**
1. `pages/06_posttest.py` — same 18 questions, save with `test_type='post'`, show pre vs post comparison
2. `pages/07_questionnaires.py` — SUS 10 items + NASA-TLX 3 items, calculate SUS score, save both

**SUS Score Formula:**
```python
def calculate_sus_score(responses: dict) -> float:
    """responses = {q1: 1-5, q2: 1-5, ..., q10: 1-5}"""
    odd_sum = sum(responses[f'q{i}'] - 1 for i in [1,3,5,7,9])
    even_sum = sum(5 - responses[f'q{i}'] for i in [2,4,6,8,10])
    return (odd_sum + even_sum) * 2.5
    # Success threshold: score > 68
```

**Test before moving on:**
- [ ] Post-test saves with `test_type='post'`
- [ ] Student can see pre vs post score comparison
- [ ] SUS score calculated correctly (check manually against known SUS formula)
- [ ] NASA-TLX 3 scores saved to `nasa_tlx` table

---

### Phase 7 — Polish + Study Readiness (Week 10)
**Goal:** Full session runs end-to-end without errors.

**Tasks:**
- Add sidebar progress tracker to every page (`render_sidebar()` function in app.py)
- Add `run.sh` / `run.bat` launcher scripts
- Add auto-backup of database before each session
- Test full flow: Login → Consent → Pre-test → L1 → L2 → L3 → Post-test → SUS → NASA-TLX → Debrief
- Try to skip levels via URL manipulation — must get blocked
- Add debrief page explaining study purpose
- Implement 2-revision-cycle limit per concept node

**Sidebar Template:**
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

### Phase 8 — P1 Features (Week 11, only if P0 is complete)
**Goal:** Add RAG chat assistant and PDF upload.

> ⚠️ **Do NOT build Phase 8 until all Phase 1–7 tests pass.** These are P1 features. If time is short, skip entirely and document as future work in the thesis.

**Files to modify:** `llm_utils.py`, `api.py`, new page `pages/00_upload.py`

**RAG Fallback Strategy (if ChromaDB is too complex):**
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

## 7. Code Patterns

Always follow these patterns. They exist to prevent common bugs.

### Pattern 1 — Every Database Operation Closes Its Connection
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

### Pattern 2 — Every LLM Call Goes Through call_lmstudio()
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
            "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
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

### Pattern 3 — Level Gate Check in Every FastAPI Route
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

### Pattern 4 — Session State Check on Every Streamlit Page
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

### Pattern 5 — Autosave on Every Button Click
```python
# ✅ Save immediately when student submits — don't wait until end of session
if st.button("Submit Definition"):
    with st.spinner("Validating..."):
        result = httpx.post("http://localhost:8000/validate/definition", json={...}).json()
    # Save happens inside the API route — done before response returns
    st.success("Saved!")
```

### Pattern 6 — Show Response Time to User
```python
# After every LLM call, show timing (this is a research metric)
response_time_s = elapsed_ms / 1000
if response_time_s > 10:
    st.warning(f"⚠️ AI took {response_time_s:.1f}s (over 10s threshold)")
else:
    st.caption(f"AI response time: {response_time_s:.1f}s")
```

---

## 8. FastAPI Routes Reference

Build these routes in `api.py` in this order:

```
POST /login                         # Validate participant code, return participant_id
POST /consent/{participant_id}      # Mark consent_given=1 in DB
GET  /progress/{participant_id}     # Return level statuses dict
POST /test/submit                   # Save pre or post test score
POST /validate/definition           # LLM definition check → VALID or NEEDS_REVISION
POST /nodes/add                     # Add concept node to NetworkX graph + DB
POST /quiz/level1/submit            # Score quiz, unlock Level 2 if ≥70%
POST /validate/paraphrase           # Sentence-transformer similarity check
POST /quiz/level2/submit            # Score quiz, unlock Level 3 if ≥70%
POST /edges/add                     # Add edge to graph
POST /validate/edge                 # LLM adversarial challenge → challenge question
POST /edges/defend                  # Save student's defense, mark defended_at
POST /questionnaire/sus             # Save SUS responses + calculate score
POST /questionnaire/nasa            # Save NASA-TLX scores
GET  /export/{participant_id}       # Return all participant data as CSV
```

---

## 9. LLM Prompt Rules

These are non-negotiable research integrity requirements.

| Rule | Why |
|---|---|
| **NEVER give the correct answer in prompts** | Core research principle — tests if students can construct knowledge |
| **Always end prompts with "Respond now:"** | Reduces LLM preamble, keeps responses under 50 words |
| **Always specify response format** | VALID:/NEEDS_REVISION: or Challenge: prefixes make parsing reliable |
| **Log every single call** | Response time is a primary research metric (90% must be <10s) |
| **Set timeout=30.0 on httpx calls** | LM Studio can hang; 30s timeout prevents app freeze |
| **Max 2 revision cycles per node** | After 2 NEEDS_REVISION responses, auto-accept with a note |

---

## 10. Critical UX Rules

These are not optional. They affect research integrity.

| Rule | Implementation |
|---|---|
| Consent must come before everything | `pages/01_consent.py` blocks all other pages until `consent_given=1` in DB |
| Cannot retake pre-test | Query `test_results` for `test_type='pre'` before rendering; redirect if found |
| Cannot skip levels by URL | Every page queries API for level status; shows error if locked |
| Max 2 revision cycles per node | Track `revision_count` in DB; auto-accept on 3rd attempt with a note |
| Autosave everything | Write to DB on every button click, not just session end |
| Show AI response time | Display `response_time_ms` from logs; warn if >10s |
| Level 3 needs 3 defended edges | Count `defended_at IS NOT NULL` in `concept_edges`; gate on 3 |

---

## 11. Graph Visualization

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

## 12. Testing Checklist

Run these tests manually before each study session. Print this page.

### Infrastructure
- [ ] LM Studio server responds in <10 seconds (verify via Local Server tab in LM Studio GUI)
- [ ] `http://localhost:8000/docs` loads Swagger UI
- [ ] `http://localhost:8501` loads login screen
- [ ] `cms_database.db` exists; `SELECT COUNT(*) FROM participants` returns 10

### Level Gate Security
- [ ] Accessing Level 2 URL without completing Level 1 → blocked with error
- [ ] Trying to re-take pre-test → redirected with message
- [ ] Entering invalid participant code → error shown, no login

### Core Features
- [ ] F1: P01 logs in; P99 is rejected
- [ ] F2: 18 questions render; score saved correctly; cannot retake
- [ ] F3: Level 2 returns 403 if Level 1 not complete (test via curl)
- [ ] F4: Concept + definition saves node to graph JSON file
- [ ] F5: LLM returns VALID or NEEDS_REVISION prefix in <10s
- [ ] F6: Scoring 60% on Level 1 quiz does NOT unlock Level 2
- [ ] F6: Scoring 80% on Level 1 quiz DOES unlock Level 2
- [ ] F7: Copy-paste rejected (similarity >0.95); genuine paraphrase accepted (0.85–0.95)
- [ ] F8: Graph renders with nodes visible, edges have arrows
- [ ] F9: All actions visible in SQLite; CSV export downloads
- [ ] F10: SUS score = (sum of scaled responses) × 2.5
- [ ] F11: NASA-TLX 3 scores saved
- [ ] F12: All LLM calls in `llm_logs`; `response_time_ms` populated

### Full Session Flow
- [ ] Complete flow runs without errors: Login → Consent → Pre-test → L1 → L2 → L3 → Post-test → SUS → NASA-TLX
- [ ] All data visible in DB after session
- [ ] CSV export works for the completed participant

---

## 13. Study Session Launch

### run.sh (Mac/Linux)
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

### run.bat (Windows)
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

### Pre-Session Checklist (Print and Use)
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

## 14. Data Backup Strategy

> ⚠️ One corrupted database = lost research data. Prevent this at all costs.

| When | What | How |
|---|---|---|
| Before every session | Copy DB | `run.sh` does this automatically |
| Every day | Git commit | `git add cms_database.db && git commit -m "data backup"` to a private `backup` branch |
| Every week | Full project backup | Copy entire `cognimap-fyp/` folder to Google Drive or external drive |

Never commit the database to your `main` branch — create a separate `backup` branch for data.

---

## 15. Debugging Guide

| Problem | First Check | Fix |
|---|---|---|
| LM Studio response >10s | Check RAM usage (Activity Monitor / Task Manager) | Close other apps; use Q4_K_M quantized model; lower context length in LM Studio settings |
| "database is locked" SQLite error | Two connections open simultaneously | Ensure every function calls `conn.close()` |
| pyvis graph doesn't render | Check `/tmp/cognimap_graph.html` exists | Verify `streamlit.components.v1` import; check pyvis version |
| Streamlit and FastAPI not talking | Both servers running? httpx installed? | `httpx.get("http://localhost:8000")` in Python shell |
| sentence-transformers OOM | Not enough RAM | Switch to TF-IDF cosine similarity fallback |
| ChromaDB too slow on first run | Downloading model (~80MB) | Wait for first download; subsequent calls are fast |
| Streamlit session state lost | Browser tab refreshed | All critical state must be in DB, not just session_state |

---

## 16. Gemini CLI Usage

Since you are using **Gemini CLI** as your AI coding assistant, here are optimal prompts for each task type:

### When you hit a bug
```
I am building CogniMap, a Python app with Streamlit + FastAPI + SQLite + LM Studio.

Error message:
[PASTE FULL ERROR]

Code that caused it:
[PASTE THE FUNCTION]

Tell me: (1) what this error means in plain English, (2) which line caused it, (3) how to fix it and why.
```

### When you need a new feature
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

### When you need code explained
```
Explain this Python code to me line by line as if I am a complete beginner.
For each line: (1) what it does, (2) why it is needed, (3) what breaks if I remove it.

[PASTE CODE]
```

### What Gemini CLI cannot help with
| Task | Do this instead |
|---|---|
| Debugging LM Studio speed on your specific hardware | Test manually via LM Studio Local Server tab and monitor response time |
| Setting the right similarity threshold (0.85–0.95) | Run 20 test paraphrases and measure where the boundary falls |
| Research design validity | Follow PRD Section 9; consult your supervisor |
| pyvis rendering bugs | Check github.com/WestHealth/pyvis issues for your exact version |

---

## 17. Definition of Done

The MVP is complete when ALL of the following are true:

### Technical
- [ ] F1–F12 all pass manual testing (see Testing Checklist section)
- [ ] Full session runs end-to-end without errors for 2 test participants
- [ ] Level gates enforced: attempting to skip via URL returns 403
- [ ] 90% of logged LLM responses under 10,000ms
- [ ] CSV export works for all participant data
- [ ] `run.sh` / `run.bat` starts all services in one command
- [ ] `.gitignore` excludes all sensitive/generated files

### Research
- [ ] 10 participants complete full sessions (minimum N=8)
- [ ] Pre and post test scores stored for all participants
- [ ] SUS scores stored; mean calculated
- [ ] All LLM interaction logs exportable for qualitative analysis
- [ ] Zero critical errors during any live session

### Documentation
- [ ] README.md with setup instructions (verify: a classmate can follow it)
- [ ] All code committed to Git; no real participant names in repo
- [ ] Code comments on every non-obvious function
- [ ] Thesis Chapters 1–6 drafted
- [ ] 10-minute demo rehearsed twice successfully

### Sign-Off
- [ ] Supervisor final approval received

---

## 18. Research Formulas Reference

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

## 19. Scaling Path (For Thesis Context Only — Do Not Build)

| Phase | When | What Changes |
|---|---|---|
| V1 FYP MVP | Now | Localhost, 10 participants, SQLite, LM Studio |
| V2 Pilot | Post-graduation | 50–200 users, PostgreSQL, Docker, cloud hosting |
| V2.5 Cloud LLM | When local LLM limits speed | Replace LM Studio with Anthropic Claude API |
| V3 Multi-Institution | 1–2 years | React frontend, FastAPI microservices |
| V4 Full Product | 3+ years | Mobile app, LMS integration (Canvas/Moodle) |

Every technology chosen has a clear upgrade path: SQLite→PostgreSQL, LM Studio→Claude API, Streamlit→React, NetworkX→Neo4j.

---

*AGENTS.md | CogniMap MVP | Version 1.0 | March 2026*
*Generated from PRD-CogniMap-MVP.md + TechDesign-CogniMap-MVP.docx*
*Target: Gemini CLI | Vibe-coder level | FYP Weeks 4–13*
