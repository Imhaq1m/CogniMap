"""
CogniMap v3.0 — Flask Application
Thin entry point: registers blueprints, serves UI, manages files/extraction.
All level-specific logic lives in levels/*.py
All shared infrastructure lives in core/*.py
"""

import json
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename

from database import save_concept_nodes
from core import (
    extract_concepts_from_files,
    save_confirmed_concepts,
    load_graph_data,
    pipeline_state,
    get_bloom_progress,
)
from core.graph_ops import DATA_DIR, OUTPUT_DIR
from levels import register_all_levels

# ── App Setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

CORS(app, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Register all level blueprints
register_all_levels(app)

# ── UI Route ───────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve the single-page application."""
    return render_template("index.html")


# ── File Management ────────────────────────────────────────────────────────


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload PDF file to data directory."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "Only PDF files allowed"}), 400

    filename = secure_filename(file.filename)
    file.save(str(DATA_DIR / filename))
    return jsonify({"message": f"Uploaded {filename}", "filename": filename}), 200


@app.route("/api/files", methods=["GET"])
def list_files():
    """List uploaded PDF files."""
    files = [f.name for f in DATA_DIR.glob("*.pdf")]
    return jsonify({"files": sorted(files)}), 200


@app.route("/api/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    """Delete uploaded PDF file."""
    file_path = DATA_DIR / secure_filename(filename)
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    file_path.unlink()
    return jsonify({"message": f"Deleted {filename}"}), 200


# ── Concept Extraction ─────────────────────────────────────────────────────


def _run_extraction_pipeline(file_list):
    """Run extraction in a background thread."""
    try:
        extract_concepts_from_files(file_list, state_manager=pipeline_state)
    except Exception as e:
        print(f"Extraction failed: {e}")
        pipeline_state.finish(error=str(e))
        return
    pipeline_state.finish()


@app.route("/api/extract", methods=["POST"])
def extract_concepts():
    """Trigger concept extraction from uploaded PDFs."""
    data = request.json
    file_list = data.get("files", [])

    if not file_list:
        return jsonify({"error": "No files specified"}), 400

    if pipeline_state.is_running:
        return jsonify({"error": "Extraction already in progress"}), 409

    pipeline_state.start(
        step="Initializing extraction...",
        log_line="Starting concept extraction",
    )
    thread = threading.Thread(target=_run_extraction_pipeline, args=(file_list,), daemon=True)
    thread.start()

    return jsonify({"status": "started"}), 202


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get pipeline status."""
    return jsonify(pipeline_state.get_state()), 200


@app.route("/api/extracted-concepts", methods=["GET"])
def get_extracted_concepts():
    """Get extracted concepts after extraction completes."""
    cache_path = OUTPUT_DIR / "extracted_concepts.json"
    if not cache_path.exists():
        return jsonify({"headings": []}), 200

    with open(cache_path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f)), 200


@app.route("/api/confirm-concepts", methods=["POST"])
def confirm_concepts():
    """Save user-confirmed concepts to graph and database."""
    data = request.json
    concepts = data.get("concepts", [])

    if not concepts:
        return jsonify({"error": "No concepts provided"}), 400

    save_confirmed_concepts(concepts)
    save_concept_nodes(concepts)

    return jsonify({
        "message": f"Confirmed {len(concepts)} concepts",
        "count": len(concepts),
        "main_topics": sum(1 for c in concepts if c.get("type") == "main_topic"),
        "sub_topics": sum(1 for c in concepts if c.get("type") == "sub_topic"),
    }), 200


# ── Graph & Progress ───────────────────────────────────────────────────────


@app.route("/api/graph", methods=["GET"])
def get_graph():
    """Get graph data (confirmed concepts)."""
    return jsonify(load_graph_data()), 200


@app.route("/api/progress", methods=["GET"])
def get_progress():
    """Get user's progress across all layers and levels."""
    participant_id = request.args.get("participant_id", "P01")
    return jsonify(get_bloom_progress(participant_id)), 200


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[START] Starting CogniMap v3.0...")
    print(f"[DATA]  Data directory: {DATA_DIR}")
    print(f"[OUTPUT] Output directory: {OUTPUT_DIR}")
    print("[WEB]   Access at: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
