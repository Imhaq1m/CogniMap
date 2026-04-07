"""
app_flask.py — Flask-based single-page app for CogniMap v2.0

Replaces the Streamlit multi-page architecture with a Flask + vis.js single-page design.
Integrates 6 Bloom's Taxonomy levels into an interactive concept graph.
"""

from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
import db_wrapper as db
import llm_utils as llm
import graph_utils as gu
import os
import json
from datetime import datetime
from pathlib import Path

# Initialize Flask app
app = Flask(__name__, 
            static_folder='static',
            template_folder='templates')
app.secret_key = os.urandom(24)  # For session management

# Enable CORS for API endpoints
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
ROOT_DIR = Path(__file__).parent
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ==================== Static File Routes ====================

@app.route('/')
def index():
    """Serve the single-page app."""
    return render_template('index.html')


@app.route('/lib/<path:filename>')
def serve_lib(filename):
    """Serve vis.js and other libraries."""
    return send_from_directory('static/lib', filename)


# ==================== Authentication Routes ====================

@app.route('/api/login', methods=['POST'])
def login():
    """Validate participant code and create session."""
    data = request.json
    code = data.get('code', '').strip().upper()
    
    if not code:
        return jsonify({"error": "Participant code required"}), 400
    
    participant = db.get_participant_by_code(code)
    if not participant:
        return jsonify({"error": f"Invalid code: {code}. Use P01-P10."}), 400
    
    # Store in session
    session['participant_id'] = participant['id']
    session['participant_code'] = participant['code']
    session['consent_given'] = participant['consent_given']
    
    current_layer = db.get_current_layer(participant['id'])
    progress = db.get_bloom_progress(participant['id'], layer=1)
    
    return jsonify({
        "participant_id": participant['id'],
        "code": participant['code'],
        "consent_given": participant['consent_given'],
        "current_layer": current_layer,
        "progress": progress
    })


@app.route('/api/logout', methods=['POST'])
def logout():
    """Clear session."""
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route('/api/reset', methods=['POST'])
def reset_progress():
    """Reset all progress for current participant (nodes, edges, progress, logs)."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    participant_id = session['participant_id']

    # Clear all participant data
    db.reset_participant_progress(participant_id)

    # Reset session consent state
    session['consent_given'] = False

    db.log_audit_action(participant_id, action="progress_reset")

    return jsonify({"status": "success", "message": "Progress reset. Please re-consent."})


@app.route('/api/session', methods=['GET'])
def get_session():
    """Get current session status."""
    if 'participant_id' not in session:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
        "participant_id": session['participant_id'],
        "participant_code": session.get('participant_code'),
        "consent_given": session.get('consent_given', False)
    })


# ==================== Audit Log Routes ====================

@app.route('/api/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get audit logs for current participant."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    participant_id = session['participant_id']
    logs = db.get_audit_logs(participant_id)
    return jsonify(logs)


@app.route('/api/llm-logs', methods=['GET'])
def get_llm_logs():
    """Get LLM logs for current participant."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    participant_id = session['participant_id']
    logs = db.get_llm_logs(participant_id)
    return jsonify(logs)


# ==================== Consent Routes ====================

@app.route('/api/consent', methods=['POST'])
def give_consent():
    """Record consent for current participant."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    participant_id = session['participant_id']
    db.set_consent_given(participant_id)
    session['consent_given'] = True
    
    db.log_audit_action(participant_id, action="consent_given")
    
    return jsonify({"status": "success", "message": "Consent recorded"})


# ==================== Progress Routes ====================

@app.route('/api/progress', methods=['GET'])
def get_progress():
    """Get Bloom's Taxonomy progress for current participant."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    participant_id = session['participant_id']
    layer = request.args.get('layer', 1, type=int)
    
    progress = db.get_bloom_progress(participant_id, layer=layer)
    current_layer = db.get_current_layer(participant_id)
    layer1_complete = db.is_layer_complete(participant_id, 1)
    
    return jsonify({
        "progress": progress,
        "current_layer": current_layer,
        "layer1_complete": layer1_complete
    })


@app.route('/api/level/complete', methods=['POST'])
def complete_level():
    """Mark a level as complete and unlock the next."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    participant_id = session['participant_id']
    layer = data.get('layer', 1)
    level = data.get('level')
    
    if not level:
        return jsonify({"error": "Level required"}), 400
    
    # Mark current level complete
    db.complete_level(participant_id, level, layer=layer)
    
    # Unlock next level if exists
    if level < 6:
        db.unlock_level(participant_id, level + 1, layer=layer)
        next_level = level + 1
    elif layer == 1:
        # Layer 1 complete, unlock Layer 2
        db.unlock_layer(participant_id, 2)
        next_level = 1
    else:
        next_level = None
    
    db.log_audit_action(
        participant_id, 
        action="level_completed",
        layer=layer,
        level=level,
        details={"next_level": next_level}
    )
    
    return jsonify({
        "status": "success",
        "completed": level,
        "next_level": next_level
    })


# ==================== Graph Routes ====================

@app.route('/api/graph', methods=['GET'])
def get_graph():
    """Get graph data for current participant."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    participant_id = session['participant_id']
    layer = request.args.get('layer', 1, type=int)
    
    # Load from database
    nodes = db.get_concept_nodes(participant_id, layer=layer)
    edges = db.get_concept_edges(participant_id, layer=layer)
    
    # Also load from NetworkX if exists
    G = gu.load_graph(participant_id, layer)
    graph_viz = gu.get_graph_for_visualization(G)
    
    return jsonify({
        "nodes": nodes,
        "edges": edges,
        "visualization": graph_viz,
        "node_count": len(nodes),
        "edge_count": len(edges)
    })


@app.route('/api/graph/update', methods=['POST'])
def update_graph():
    """Update graph (add/edit/remove nodes or edges)."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    participant_id = session['participant_id']
    layer = data.get('layer', 1)
    update_type = data.get('type')  # 'node' or 'edge'
    item_data = data.get('data')
    
    if not update_type or not item_data:
        return jsonify({"error": "Invalid request"}), 400
    
    try:
        if update_type == 'node':
            # Add or update node
            node_id = db.save_concept_node(
                participant_id=participant_id,
                layer=layer,
                concept=item_data.get('concept', ''),
                definition=item_data.get('definition', ''),
                validation_result=item_data.get('validation_result'),
                revision_count=item_data.get('revision_count', 0)
            )
            
            # Also update NetworkX graph
            G = gu.load_graph(participant_id, layer)
            gu.add_node_to_graph(
                G,
                concept=item_data.get('concept', ''),
                definition=item_data.get('definition', ''),
                node_id=str(node_id)
            )
            gu.save_graph(G, participant_id, layer)
            
            return jsonify({"status": "success", "node_id": node_id})
        
        elif update_type == 'edge':
            # Add or update edge
            edge_id = db.save_concept_edge(
                participant_id=participant_id,
                layer=layer,
                from_node=item_data.get('from_node', ''),
                to_node=item_data.get('to_node', ''),
                edge_label=item_data.get('edge_label', 'Related to'),
                justification=item_data.get('justification', '')
            )
            
            # Also update NetworkX graph
            G = gu.load_graph(participant_id, layer)
            gu.add_edge_to_graph(
                G,
                from_node=item_data.get('from_node', ''),
                to_node=item_data.get('to_node', ''),
                edge_label=item_data.get('edge_label', 'Related to'),
                justification=item_data.get('justification', '')
            )
            gu.save_graph(G, participant_id, layer)
            
            return jsonify({"status": "success", "edge_id": edge_id})
        
        else:
            return jsonify({"error": "Unknown update type"}), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== Level 1: Remember Routes ====================

@app.route('/api/level1/validate', methods=['POST'])
def validate_definition():
    """Validate a concept definition using AI."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    concept = data.get('concept', '')
    definition = data.get('definition', '')
    node_id = data.get('node_id')
    
    if not concept or not definition:
        return jsonify({"error": "Concept and definition required"}), 400
    
    # Call LLM for validation
    result = llm.validate_definition(
        concept=concept,
        definition=definition,
        participant_id=session['participant_id'],
        layer=data.get('layer', 1)
    )
    
    # Update node in database
    if node_id:
        db.update_node_verification(
            node_id=node_id,
            verification_status='verified' if result.get('result') == 'VALID' else 'pending',
            validation_result=result.get('result')
        )
    
    return jsonify(result)


@app.route('/api/level1/quiz/generate', methods=['POST'])
def generate_level1_quiz():
    """Generate Level 1 quiz from verified nodes."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    participant_id = session['participant_id']
    layer = request.json.get('layer', 1)
    
    verified_nodes = db.get_verified_nodes(participant_id, layer=layer)
    
    if len(verified_nodes) < 3:
        return jsonify({"error": "Need at least 3 verified nodes"}), 400
    
    questions = llm.generate_level1_quiz(verified_nodes, participant_id, layer=layer)
    
    return jsonify({
        "questions": questions,
        "count": len(questions)
    })


@app.route('/api/level1/quiz/submit', methods=['POST'])
def submit_level1_quiz():
    """Submit Level 1 quiz and check gate."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    answers = data.get('answers', {})
    layer = data.get('layer', 1)
    
    # Calculate score
    total = len(answers)
    correct = sum(1 for ans in answers.values() if ans.get('is_correct', False))
    score = (correct / total * 100) if total > 0 else 0
    
    # Check gate (≥80%)
    passed = score >= 80
    
    if passed:
        db.complete_level(session['participant_id'], 1, layer=layer)
        db.unlock_level(session['participant_id'], 2, layer=layer)
    
    return jsonify({
        "score": score,
        "passed": passed,
        "correct": correct,
        "total": total
    })


# ==================== Level 2: Understand Routes ====================

@app.route('/api/level2/validate', methods=['POST'])
def validate_paraphrase():
    """Validate paraphrase using semantic similarity."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    original = data.get('original', '')
    paraphrase = data.get('paraphrase', '')
    node_id = data.get('node_id')
    
    if not original or not paraphrase:
        return jsonify({"error": "Original and paraphrase required"}), 400
    
    result = llm.validate_paraphrase(
        original=original,
        paraphrase=paraphrase,
        participant_id=session['participant_id'],
        layer=data.get('layer', 1)
    )
    
    # Update node with paraphrase
    if node_id and result.get('result') == 'VALID':
        db.update_node_paraphrase(
            node_id=node_id,
            definition=paraphrase,
            similarity_score=result.get('similarity', 0)
        )
    
    return jsonify(result)


# ==================== Level 3: Apply Routes ====================

@app.route('/api/level3/challenge', methods=['POST'])
def generate_edge_challenge():
    """Generate Socratic challenge for edge justification."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    from_node = data.get('from_node', '')
    to_node = data.get('to_node', '')
    justification = data.get('justification', '')
    edge_id = data.get('edge_id')
    
    if not from_node or not to_node or not justification:
        return jsonify({"error": "Edge details required"}), 400
    
    challenge = llm.generate_edge_challenge(
        from_node=from_node,
        to_node=to_node,
        justification=justification,
        participant_id=session['participant_id'],
        layer=data.get('layer', 1)
    )
    
    # Save challenge to edge
    if edge_id:
        db.update_edge_challenge(edge_id, challenge)
    
    return jsonify({"challenge": challenge})


@app.route('/api/level3/defend', methods=['POST'])
def defend_edge():
    """Submit defense for an edge."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.json
    edge_id = data.get('edge_id')
    defense = data.get('defense', '')
    layer = data.get('layer', 1)
    
    if not edge_id or not defense:
        return jsonify({"error": "Edge ID and defense required"}), 400
    
    db.mark_edge_defended(edge_id, defense)
    defended_count = db.get_defended_edge_count(session['participant_id'], layer=layer)
    
    # Check gate (3 defended edges)
    gate_passed = defended_count >= 3
    
    if gate_passed:
        db.complete_level(session['participant_id'], 3, layer=layer)
        db.unlock_level(session['participant_id'], 4, layer=layer)
    
    return jsonify({
        "status": "success",
        "defended_count": defended_count,
        "gate_passed": gate_passed
    })


# ==================== PDF Pipeline Routes ====================

@app.route('/api/pdf/upload', methods=['POST'])
def upload_pdf():
    """Upload PDF and extract concepts."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Save file
    filepath = UPLOAD_DIR / file.filename
    file.save(str(filepath))
    
    # Extract text (simplified - use PyPDF2)
    try:
        import PyPDF2
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''.join([page.extract_text() for page in reader.pages])
    except Exception as e:
        return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500
    
    # Extract concepts using LLM
    layer = request.form.get('layer', 1, type=int)
    candidate_nodes = llm.extract_candidate_nodes(
        pdf_text=text[:8000],  # Truncate to avoid token limits
        participant_id=session['participant_id'],
        layer=layer
    )
    
    # Save to database
    node_ids = []
    for node_data in candidate_nodes:
        node_id = db.save_concept_node(
            participant_id=session['participant_id'],
            layer=layer,
            concept=node_data['concept'],
            definition=node_data['definition'],
            source_text=node_data.get('source_text', ''),
            verification_status='pending'
        )
        node_ids.append(node_id)
    
    return jsonify({
        "status": "success",
        "nodes": [{"id": nid, **node} for nid, node in zip(node_ids, candidate_nodes)],
        "count": len(node_ids)
    })


# ==================== Export Routes ====================

@app.route('/api/export', methods=['GET'])
def export_data():
    """Export participant data as JSON."""
    if 'participant_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    participant_id = session['participant_id']
    
    data = {
        "participant": db.get_participant_by_id(participant_id),
        "nodes": db.get_concept_nodes(participant_id),
        "edges": db.get_concept_edges(participant_id),
        "progress": db.get_bloom_progress(participant_id),
        "llm_logs": db.get_llm_logs(participant_id)
    }
    
    return jsonify(data)


# ==================== Main Entry Point ====================

if __name__ == '__main__':
    # Initialize database on startup
    print("Initializing database...")
    db.initialize_database()
    db.seed_participants()
    print("Database ready!")
    
    # Start Flask server
    print("\n🚀 CogniMap v2.0 starting...")
    print("📍 Access at: http://localhost:5000")
    app.run(debug=True, port=5000, host='0.0.0.0')
