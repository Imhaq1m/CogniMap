from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import os
import sys
import hashlib
import threading
import time
import io
import contextlib
import shutil
from pathlib import Path
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from filelock import FileLock

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)

# [FIX-A9] BUG-12: Restricted CORS in production
# Driven by env var ALLOWED_ORIGINS; defaults to localhost for safety.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")
CORS(app, origins=allowed_origins)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit (QA-07)

# Project Configuration
ROOT_DIR = Path(__file__).parent
DATA_DIR = (ROOT_DIR / "data").resolve()
OUTPUT_DIR = (ROOT_DIR / "output").resolve()
GRAPH_DATA_PATH = OUTPUT_DIR / "graph_data.json"
GRAPH_LOCK_PATH = OUTPUT_DIR / "graph_data.json.lock"
CHAT_HISTORY_DIR = OUTPUT_DIR / "chat_history"

# Pipeline Persistence Configuration
STATUS_FILE = OUTPUT_DIR / "pipeline_status.json"
STATUS_LOCK_PATH = OUTPUT_DIR / "pipeline_status.lock"

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CHAT_HISTORY_DIR.mkdir(exist_ok=True)

# Ollama Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")


def get_history_path(node_id):
    # Using a hash-based naming convention to avoid OS path length limits and secure filename collisions.
    # [MIGRATION] SHA256 of the ID ensures persistent mapping regardless of student renames in UI.
    node_hash = hashlib.sha256(node_id.encode()).hexdigest()[:12]
    return CHAT_HISTORY_DIR / f"hist_{node_hash}.json"


def get_history_lock_path(node_id):
    # [FIX-A4] Per-node lock file to protect the chat history read-extend-write cycle.
    # [CONCURRENCY REVIEW] Each node gets an independent lock so concurrent chats on different
    # nodes do not block each other, while concurrent requests on the SAME node are serialized.
    node_hash = hashlib.sha256(node_id.encode()).hexdigest()[:12]
    return CHAT_HISTORY_DIR / f"hist_{node_hash}.lock"


def migrate_chat_history(old_id, new_id):
    """
    [MIGRATION] Ensures that when a student renames a concept, their Socratic history follows it.
    This handles the migration between the hash-based files.
    """
    old_path = get_history_path(old_id)
    new_path = get_history_path(new_id)
    if old_path.exists() and old_path != new_path:
        try:
            shutil.move(str(old_path), str(new_path))
            # Also move the lock file if it exists, to keep names consistent.
            old_lock = get_history_lock_path(old_id)
            new_lock = get_history_lock_path(new_id)
            if old_lock.exists() and old_lock != new_lock:
                shutil.move(str(old_lock), str(new_lock))
            return True
        except Exception as e:
            print(f"Error migrating history: {e}")
    return False


# ---------------------------------------------------------------------------
# PipelineState — Buffered pipeline state with ABBA deadlock fix
# ---------------------------------------------------------------------------
class PipelineState:
    def __init__(self, status_file, lock_path):
        self.status_file = status_file
        self.lock_path = lock_path
        # [CONCURRENCY REVIEW] self._lock is a FileLock used as the multi-process guard.
        # It is ONLY held during start() (to serialise the read-check-write cycle across workers)
        # and inside _write_state() itself. It is NEVER held while _mem_lock is already held
        # by any code path OTHER than start() — which uses FileLock reentrancy intentionally.
        # This eliminates the ABBA deadlock: update() and finish() now release _mem_lock BEFORE
        # calling _write_state(), so they never hold _mem_lock → _lock simultaneously.
        self._lock = FileLock(self.lock_path)  # [QA-08] Shared instance for re-entrancy in start()
        self._mem_state = {"running": False, "step": "Idle", "log": [], "error": None}
        self._last_sync = 0
        self._mem_lock = threading.Lock()
        self._init_file()

    def _init_file(self):
        # Reset running status on startup to prevent zombie locks.
        with self._mem_lock:
            if self.status_file.exists():
                try:
                    with open(self.status_file, "r", encoding="utf-8") as f:
                        old = json.load(f)
                        if old.get("running"):
                            old["running"] = False
                            old["step"] = "Restarted"
                            self._mem_state = old
                except Exception:
                    pass
            self._write_state(self._mem_state)

    def _write_state(self, state):
        # [CONCURRENCY REVIEW] self._lock is a FileLock (reentrant for the same instance on the
        # same thread). When called from start(), the lock is already held — this is safe due to
        # reentrancy. When called from update() or finish(), _mem_lock has been RELEASED before
        # this call (FIX-A1), so there is no circular wait.
        with self._lock:
            tmp_file = self.status_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            tmp_file.replace(self.status_file)
            self._last_sync = time.time()

    def _read_state(self):
        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"running": False, "step": "Error", "log": [], "error": None}

    def start(self, step="Starting...", log_line=None):
        # [QA-08] Multi-worker safety: lock the read-check-write cycle.
        # Lock ordering in start(): _lock → _mem_lock → _lock (reentrant via FileLock counter).
        # This is the ONLY path that holds _lock while also holding _mem_lock.
        # update() and finish() do NOT hold _lock while holding _mem_lock (FIX-A1).
        with self._lock:
            disk_state = self._read_state()
            if disk_state.get("running"):
                return False

            with self._mem_lock:
                self._mem_state = {
                    "running": True,
                    "step": step,
                    "log": [log_line] if log_line else [],
                    "error": None,
                    "start_time": time.time()
                }
                # Nested call to _write_state is safe: _lock is already held (reentrant).
                self._write_state(self._mem_state)
            return True

    def update(self, step: str, log_line: str = None, force_sync: bool = False):
        # [FIX-A1] ABBA Deadlock Fix:
        # Old code called _write_state() INSIDE the _mem_lock context, creating the ordering:
        #   _mem_lock → _lock  (from the background thread via update)
        # While start() holds:
        #   _lock → _mem_lock  (from Flask request thread)
        # This caused a classic ABBA deadlock.
        #
        # Fix: copy the state while holding _mem_lock, RELEASE _mem_lock, THEN write to disk.
        # This means _lock and _mem_lock are never held simultaneously in update().
        state_to_write = None
        with self._mem_lock:
            step_changed = step != self._mem_state["step"]
            self._mem_state["step"] = step
            if log_line:
                self._mem_state["log"].append(log_line)
                if len(self._mem_state["log"]) > 150:
                    self._mem_state["log"] = self._mem_state["log"][-150:]

            should_sync = step_changed or force_sync or (time.time() - self._last_sync > 2.0)
            if should_sync:
                # Make a shallow copy BEFORE releasing _mem_lock so the write reflects the
                # exact state at this point in time.
                state_to_write = dict(self._mem_state)
        # _mem_lock is now RELEASED. _write_state() acquires _lock independently. No ABBA.
        if state_to_write is not None:
            self._write_state(state_to_write)

    def finish(self, error: str = None):
        # [FIX-A1] Same pattern: copy state under _mem_lock, release, then write.
        with self._mem_lock:
            self._mem_state["running"] = False
            if error:
                self._mem_state["error"] = error
                self._mem_state["step"] = "Error"
            else:
                self._mem_state["step"] = "Finished"
            state_to_write = dict(self._mem_state)
        # _mem_lock released. Now safe to call _write_state without risk of deadlock.
        self._write_state(state_to_write)

    def get_state(self):
        # Always return current memory state (fast path, no disk I/O).
        with self._mem_lock:
            return dict(self._mem_state)

    @property
    def current_step(self):
        # [FIX for BUG-11] Use _mem_lock to avoid races when _mem_state is replaced entirely
        # (e.g., during start() which assigns a new dict object, not just mutates a key).
        with self._mem_lock:
            return self._mem_state.get("step", "Idle")


pipeline_state = PipelineState(STATUS_FILE, STATUS_LOCK_PATH)


# ---------------------------------------------------------------------------
# Dual-Stream Redirector — captures stdout/stderr for the pipeline dashboard
# ---------------------------------------------------------------------------
class DualLogRedirector(io.TextIOBase):
    def __init__(self, pipeline_state):
        self.pipeline_state = pipeline_state
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def write(self, s):
        if s.strip():
            self.stdout.write(s)
            # current_step is now lock-protected (FIX for BUG-11), avoiding the original
            # comment about "non-locking access." The lock is a threading.Lock (not FileLock)
            # so there is no risk of deadlock with the FileLock in _write_state().
            self.pipeline_state.update(self.pipeline_state.current_step, s.strip())
        return len(s)


from scripts.extract_concepts import run_extraction
from scripts.build_graph import run_build


def run_pipeline_in_background():
    redirector = DualLogRedirector(pipeline_state)
    with contextlib.redirect_stdout(redirector), contextlib.redirect_stderr(redirector):
        try:
            pipeline_state.update("Extracting concepts from PDFs...", force_sync=True)
            # [CONCURRENCY REVIEW] run_extraction implements Merge-on-Write (with lock — FIX-B1).
            # The background thread takes LOCK_FILE at the start of run_extraction to snapshot
            # student data, then releases it during the long Gemini API calls, then re-acquires
            # at the end to write. This allows /api/update requests to proceed during extraction.
            run_extraction()
            pipeline_state.update("Building and enriching graph...", force_sync=True)
            # [CONCURRENCY REVIEW] run_build takes its own GRAPH_LOCK_PATH here.
            # The UI thread is not holding GRAPH_LOCK_PATH during this long-running process,
            # so there is no deadlock risk.
            if not run_build():
                raise Exception("Graph enrichment failed")
            pipeline_state.finish()
        except Exception as e:
            print(f"❌ Critical Pipeline Failure: {str(e)}")
            pipeline_state.finish(error=str(e))


# ---------------------------------------------------------------------------
# UI Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory(ROOT_DIR / "scripts", "template.html")


@app.route('/lib/<path:filename>')
def serve_lib(filename):
    # [QA-01] Path traversal guard
    safe_path = (ROOT_DIR / "lib").resolve()
    target_path = (safe_path / filename).resolve()
    if not str(target_path).startswith(str(safe_path)):
        return "Forbidden", 403
    return send_from_directory(safe_path, filename)


@app.route('/data/<path:filename>')
def serve_pdf(filename):
    # [QA-01] Path traversal guard
    target_path = (DATA_DIR / filename).resolve()
    if not str(target_path).startswith(str(DATA_DIR)):
        return "Forbidden", 403
    return send_from_directory(DATA_DIR, filename)


# ---------------------------------------------------------------------------
# API Endpoints — Pipeline Control
# ---------------------------------------------------------------------------

@app.route('/api/process', methods=['POST'])
def process_data():
    if pipeline_state.start(step="Initializing pipeline...", log_line="▶ Pipeline Started"):
        thread = threading.Thread(target=run_pipeline_in_background, daemon=True)
        thread.start()
        return jsonify({"status": "started"}), 202
    return jsonify({"error": "Pipeline already running"}), 409


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(pipeline_state.get_state())


# ---------------------------------------------------------------------------
# API Endpoints — Graph Data
# ---------------------------------------------------------------------------

@app.route('/api/graph', methods=['GET'])
def get_graph():
    # [QA-09] Acquire lock for consistent reads
    if GRAPH_DATA_PATH.exists():
        with FileLock(GRAPH_LOCK_PATH):
            with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    return jsonify({"concepts": [], "relationships": []})


@app.route('/api/update', methods=['POST'])
def update_graph():
    data = request.json

    # [FIX-A5] Validate that the payload has the expected structure before use.
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request body"}), 400

    update_type = data.get('type')
    item_data = data.get('data')

    # [FIX-A5] Guard item_data type — downstream code calls .get() on it; a non-dict will
    # raise AttributeError which leaks stack trace information via the exception handler.
    if not isinstance(item_data, dict):
        return jsonify({"error": "Invalid data payload: 'data' must be a JSON object"}), 400

    target_node, target_edge = None, None
    if not GRAPH_DATA_PATH.exists():
        return jsonify({"error": "Graph not found"}), 404

    try:
        # [CONCURRENCY REVIEW] Holding the lock here prevents race conditions during manual edits.
        # Nested locks on Windows cause deadlocks; run_build must be told to skip its internal lock.
        with FileLock(GRAPH_LOCK_PATH):
            with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            if update_type == 'node':
                old_id = item_data.get('old_id')
                new_id = item_data.get('id')
                if old_id != new_id:
                    if any(c.get('id') == new_id for c in graph_data.get('concepts', [])):
                        return jsonify({"error": f"Concept ID '{new_id}' already exists"}), 409

                    target_node = new_id
                    # [MIGRATION] Call helper to ensure chat history isn't lost during name change.
                    migrate_chat_history(old_id, new_id)

                    for r in graph_data.get('relationships', []):
                        if r['source'] == old_id:
                            r['source'] = new_id
                        if r['target'] == old_id:
                            r['target'] = new_id

                for c in graph_data.get('concepts', []):
                    if c.get('id') == (old_id if old_id != new_id else new_id):
                        allowed_keys = ['id', 'description', 'mental_model', 'complexity',
                                        'sources', 'page_references']
                        for k in allowed_keys:
                            if k in item_data:
                                c[k] = item_data[k]
                        c['manually_edited'] = True
                        break

            elif update_type == 'edge':
                s = item_data.get('source')
                t = item_data.get('target')
                target_edge = f"{s}_{t}"
                for r in graph_data.get('relationships', []):
                    if r['source'] == s and r['target'] == t:
                        r.update(item_data)
                        break

            # Atomic write
            tmp_path = GRAPH_DATA_PATH.with_suffix('.tmp')
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)
            tmp_path.replace(GRAPH_DATA_PATH)

            # [HIGH] Deadlock Fix: Pass skip_lock=True because we already hold GRAPH_LOCK_PATH.
            if not run_build(target_node=target_node, target_edge=target_edge, skip_lock=True):
                return jsonify({"error": "Enrichment failed"}), 500

        return jsonify({"message": "Success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API Endpoints — Chat & History
# ---------------------------------------------------------------------------

@app.route('/api/chat/history/<path:node_id>', methods=['GET'])
def get_chat_history(node_id):
    history_file = get_history_path(node_id)
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify([])


@app.route('/api/chat/history/<path:node_id>', methods=['DELETE'])
def clear_chat_history(node_id):
    """
    [FIX-A2] Server-side chat history clear, called when the student clicks "Clear Chat."
    The client-side handler previously only cleared the in-memory Map, causing history to
    reappear on page refresh. This endpoint deletes the persistent hist_{hash}.json file.
    [CONCURRENCY REVIEW] Uses the per-node FileLock so a concurrent chat write to the same
    node does not race with the delete.
    """
    history_file = get_history_path(node_id)
    lock_path = get_history_lock_path(node_id)
    try:
        with FileLock(lock_path):
            if history_file.exists():
                history_file.unlink()
        return jsonify({"message": "History cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json

        # [QA-10] Validate history is a list
        incoming_history = data.get('history', [])
        if not isinstance(incoming_history, list):
            return jsonify({"reply": "Error: history must be a list"}), 400

        context = data.get('concept_context', {})
        is_eli5 = data.get('eli5', False)
        node_id = context.get('id', 'global') if context else 'global'

        history_path = get_history_path(node_id)
        lock_path = get_history_lock_path(node_id)

        # [FIX-A4] Protect the read-extend-write cycle with a per-node FileLock.
        # [CONCURRENCY REVIEW] Each node has its own lock file so two concurrent chats on
        # DIFFERENT nodes proceed in parallel, while two concurrent requests on the SAME node
        # are serialized. This prevents race conditions where both requests read the same
        # existing_history, both append their messages, and the last write silently loses one.
        with FileLock(lock_path):
            existing_history = []
            if history_path.exists():
                try:
                    with open(history_path, "r", encoding="utf-8") as f:
                        existing_history = json.load(f)
                except Exception:
                    # Corrupted history file — start fresh rather than failing the request.
                    existing_history = []

            user_message = incoming_history[-1] if incoming_history else {"role": "user", "content": "Hello!"}

            # Socratic Context & ELI5 Mode Shift Handling
            instruction = "You are a Socratic coach. Do NOT give answers."
            if is_eli5:
                instruction += " ELI5 Mode: Explain like I'm five. Use simple analogies and avoid jargon."
                # [FIX-A3] ELI5 accumulation fix:
                # Old code checked if the LAST AI message contained "analogy," which meant a new
                # system notice was appended on EVERY subsequent ELI5 message that didn't happen
                # to produce the word "analogy." Over 10 messages, 10 system notices accumulated.
                #
                # Fix: Check if the history ALREADY contains an ELI5 system notice. If so, skip.
                # This means the notice is inserted exactly once per off→on transition.
                already_in_eli5_mode = any(
                    msg.get("role") == "system" and "ELI5" in msg.get("content", "")
                    for msg in existing_history
                )
                if not already_in_eli5_mode:
                    existing_history.append({
                        "role": "system",
                        "content": "Notice: Switching to ELI5 Mode. Use simple language from now on."
                    })

            context_str = (
                f"FOCUS: {context.get('id')} - {context.get('description')} "
                f"Analogies: {context.get('mental_model')}"
                if context else ""
            )
            system_message = {"role": "system", "content": f"{instruction} {context_str}"}

            full_messages = [system_message] + existing_history[-20:] + [user_message]

            # [FIX-A6] Distinguish Ollama connectivity errors from API errors.
            try:
                response = requests.post(
                    OLLAMA_CHAT_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": full_messages,
                        "stream": False,
                        "options": {"temperature": 0.3}
                    },
                    timeout=90
                )
                # Raise for non-2xx HTTP responses (e.g. Ollama model load failures)
                response.raise_for_status()
            except requests.exceptions.ConnectionError:
                return jsonify({
                    "reply": "⚠️ Cannot connect to the local Ollama server. "
                             "Please ensure Ollama is running (`ollama serve`) and the model "
                             f"'{OLLAMA_MODEL}' is available (`ollama pull {OLLAMA_MODEL}`)."
                }), 503
            except requests.exceptions.Timeout:
                return jsonify({"reply": "⚠️ Ollama timed out. The model may be loading — please try again."}), 504
            except requests.exceptions.HTTPError as e:
                return jsonify({"reply": f"⚠️ Ollama returned an error: {e}"}), 502

            ai_reply = response.json().get('message', {}).get('content', 'Error.')

            updated_history = (
                existing_history + [user_message, {"role": "assistant", "content": ai_reply}]
            )[-100:]

            # Atomic history write inside the lock to prevent concurrent corruption.
            tmp_path = history_path.with_suffix('.tmp')
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(updated_history, f, indent=2)
            tmp_path.replace(history_path)

        return jsonify({"reply": ai_reply.strip(), "history": updated_history})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"}), 500


def extract_json_from_text(text: str) -> dict:
    """Robustly extract JSON from LLM response text, handling markdown blocks."""
    try:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        return json.loads(text)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# API Endpoints — Quiz
# ---------------------------------------------------------------------------

@app.route('/api/quiz', methods=['POST'])
def generate_quiz():
    data = request.json
    subject = data.get('subject')
    context = data.get('context', '')

    if not subject:
        return jsonify({"error": "Missing 'subject' field"}), 400

    prompt = (
        f"Create a challenging MCQ JSON for '{subject}'. Context: {context}. "
        f"Return ONLY a JSON object with keys: question (string), options (object with keys A/B/C/D), "
        f"answer (the correct key letter), explanation (string)."
    )
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=90
        )
        response.raise_for_status()
        res_text = response.json().get('response', '{}')
        parsed = extract_json_from_text(res_text)
        if not parsed:
            raise ValueError("Failed to parse valid JSON from AI response")
        return jsonify(parsed)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to Ollama. Is it running?"}), 503
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"Ollama HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/quiz/result', methods=['POST'])
def save_quiz_result():
    """
    [MIGRATION] Saves student performance to the graph to visualise 'Mastery'.
    Adds 'mastery_score' and 'last_quiz_at' to the concept node.
    """
    data = request.json
    node_id = data.get('node_id')
    score = data.get('score')  # 0.0 to 1.0

    # [QA-02] Input validation
    if not isinstance(node_id, str) or not node_id:
        return jsonify({"error": "Invalid node_id"}), 400
    try:
        score = float(score)
        if not (0.0 <= score <= 1.0):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "Score must be a float between 0.0 and 1.0"}), 400

    if not GRAPH_DATA_PATH.exists():
        return jsonify({"error": "Graph not found"}), 404

    try:
        with FileLock(GRAPH_LOCK_PATH):
            with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            found = False
            for c in graph_data.get('concepts', []):
                if c.get('id') == node_id:
                    c['mastery_score'] = score
                    c['last_quiz_at'] = time.time()
                    found = True
                    break

            if found:
                tmp_path = GRAPH_DATA_PATH.with_suffix('.tmp')
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(graph_data, f, indent=2)
                tmp_path.replace(GRAPH_DATA_PATH)
                return jsonify({"message": "Mastery updated"}), 200
            return jsonify({"error": "Node not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API Endpoints — File Management
# ---------------------------------------------------------------------------

@app.route('/api/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "No file"}), 400
    if file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        file.save(DATA_DIR / filename)
        return jsonify({"message": f"Uploaded {filename}"}), 200
    return jsonify({"error": "PDFs only"}), 400


@app.route('/api/files', methods=['GET'])
def list_files():
    return jsonify({"files": [f.name for f in DATA_DIR.glob("*.pdf")]})


@app.route('/api/delete/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        file_path = (DATA_DIR / filename).resolve()
        if not str(file_path).startswith(str(DATA_DIR.resolve())):
            return jsonify({"error": "Unauthorized"}), 403
        if file_path.exists():
            file_path.unlink()
            stem = file_path.stem
            for ext in [".json", ".meta.json"]:
                p = OUTPUT_DIR / "concept_cache" / f"{stem}{ext}"
                if p.exists():
                    p.unlink()
            return jsonify({"message": "Deleted"}), 200
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/clear', methods=['POST'])
def clear_data():
    if not pipeline_state.start(step="Clearing..."):
        return jsonify({"error": "Busy"}), 409
    try:
        # [QA-03] Acquire lock to prevent races during global cleanup.
        # [CONCURRENCY REVIEW] The lock is held for the full duration of the clear operation.
        # Any concurrent /api/graph or /api/update requests will block until clear completes.
        # This is intentional: a partially cleared graph must not be served.
        with FileLock(GRAPH_LOCK_PATH):
            # 1. Delete PDFs
            for f in DATA_DIR.glob("*.pdf"):
                f.unlink()

            # 2. Delete output files except locks and pipeline_status.json.
            # [FIX-BUG-03] Explicit, clearly-parenthesised intent:
            # - Keep: *.lock files, pipeline_status.json
            # - Explicitly force-delete: graph_data.json (even though it ends in .json — it will
            #   be re-seeded in step 5, so deleting it first is intentional)
            # - Delete: everything else that is a file
            # 2. Delete output files with explicit logic [BUG-03]
            for f in OUTPUT_DIR.iterdir():
                if not f.is_file():
                    continue
                if f.suffix == ".lock":
                    continue  # Keep lock files
                if f.suffix == ".json" and f.name != "graph_data.json":
                    continue  # Keep all other .json files (status, histories, etc)
                
                # Delete graph_data.json and any other non-json files (e.g. .tmp, .txt)
                f.unlink()

            # 3. [QA-05] Explicitly purge concept cache
            cache_dir = OUTPUT_DIR / "concept_cache"
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(exist_ok=True)

            # 4. [UX-06] Clear chat history
            if CHAT_HISTORY_DIR.exists():
                shutil.rmtree(CHAT_HISTORY_DIR)
            CHAT_HISTORY_DIR.mkdir(exist_ok=True)

            # 5. [QA-05] Seed empty graph so run_build doesn't fail
            with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
                json.dump({"concepts": [], "relationships": []}, f, indent=2)

            # [CONCURRENCY REVIEW] Use skip_lock=True because we hold GRAPH_LOCK_PATH.
            if not run_build(skip_lock=True):
                raise Exception("Enrichment failed on empty graph")

        pipeline_state.finish()
        return jsonify({"message": "Cleared"}), 200
    except Exception as e:
        pipeline_state.finish(error=str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(port=5000, debug=debug_mode)
