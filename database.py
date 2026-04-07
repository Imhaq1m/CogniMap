"""
database.py — All SQLite operations for CogniMap

Every function MUST close its connection to prevent "database is locked" errors.

For testing: Pass db_path parameter to use a different database file.
"""

import sqlite3
import json
import os
from datetime import datetime

# Default database path - can be overridden for testing
DEFAULT_DATABASE_PATH = "cms_database.db"


def get_connection(db_path: str = None):
    """
    Get a database connection with row factory for dict-like access.
    
    Args:
        db_path: Optional custom database path. Uses DEFAULT_DATABASE_PATH if not provided.
                 For testing, pass 'test_cms_database.db' or use os.environ.get('TEST_DB_PATH')
    
    Returns:
        sqlite3.Connection with row_factory set for dict-like access
    """
    path = db_path if db_path else DEFAULT_DATABASE_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: str = None):
    """Create all tables if they don't exist."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    # Participants table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            consent_given INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Bloom's Taxonomy progress table - Extended for 6 levels + hierarchical layers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloom_progress (
            participant_id INTEGER,
            layer INTEGER DEFAULT 1,                   -- 1=Main Headings, 2=Subheadings
            level INTEGER,                             -- 1=Remember, 2=Understand, 3=Apply, 4=Analyze, 5=Evaluate, 6=Create
            status TEXT DEFAULT 'locked',              -- locked | active | complete
            unlocked_at TEXT,
            completed_at TEXT,
            PRIMARY KEY (participant_id, layer, level)
        )
    """)
    
    # Test results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            test_type TEXT,
            score REAL,
            bloom_level_scores TEXT,
            taken_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Concept nodes table - Extended with layer, source_text, verification status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            layer INTEGER DEFAULT 1,                   -- 1=Main Headings, 2=Subheadings
            concept TEXT NOT NULL,
            definition TEXT NOT NULL,
            source_text TEXT,                          -- Original text snippet from PDF
            is_candidate INTEGER DEFAULT 1,            -- 1=AI-extracted candidate, 0=Student-created
            verification_status TEXT DEFAULT 'pending',-- pending | verified | rejected
            validation_result TEXT,                    -- VALID | NEEDS_REVISION (for Level 1)
            similarity_score REAL,                     -- For Level 2 paraphrase check
            revision_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Concept edges table - Extended with evidence, defense status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            layer INTEGER DEFAULT 1,                   -- 1=Main Headings, 2=Subheadings
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            edge_label TEXT,                           -- e.g., "Causes", "Related to"
            justification TEXT,
            evidence_text TEXT,                        -- Source text supporting the edge
            adversarial_challenge TEXT,                -- AI's Socratic challenge
            defense_response TEXT,                     -- Student's defense
            defended_at TEXT,                          -- NULL until student defends
            is_validated INTEGER DEFAULT 0,            -- 1=AI validated, 0=pending
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # LLM logs table - Extended with layer and level context
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            layer INTEGER,                             -- 1 or 2
            level INTEGER,                             -- 1-6
            feature TEXT,                              -- e.g., 'ner_extraction', 'definition_validator', 'scenario_generator'
            prompt TEXT,
            response TEXT,
            response_time_ms INTEGER,
            metadata TEXT,                             -- JSON for additional context
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Scenario responses table - For Level 3 (Apply)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenario_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            layer INTEGER DEFAULT 1,
            scenario_text TEXT NOT NULL,
            selected_nodes TEXT,                       -- JSON array of selected concept IDs
            is_correct INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Error injections table - For Level 5 (Evaluate)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS error_injections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            error_type TEXT NOT NULL,                  -- 'wrong_node' | 'wrong_edge' | 'wrong_definition'
            target_id INTEGER NOT NULL,                -- node_id or edge_id
            original_value TEXT,                       -- Original correct value
            injected_value TEXT,                       -- Injected wrong value
            is_detected INTEGER DEFAULT 0,             -- 1=student found it, 0=not found
            detected_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Export artifacts table - For Level 6 (Create)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            export_type TEXT NOT NULL,                 -- 'quiz' | 'study_guide' | 'essay_outline'
            ai_draft TEXT,
            user_edits TEXT,                           -- JSON of user modifications
            utility_score REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Audit logs table - Cross-cutting research logging
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            layer INTEGER,
            level INTEGER,
            action TEXT NOT NULL,                      -- e.g., 'node_verified', 'edge_defended', 'error_flagged'
            details TEXT,                              -- JSON with action-specific data
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sus_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER UNIQUE,
            q1 INTEGER, q2 INTEGER, q3 INTEGER, q4 INTEGER, q5 INTEGER,
            q6 INTEGER, q7 INTEGER, q8 INTEGER, q9 INTEGER, q10 INTEGER,
            total_score REAL,
            submitted_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # NASA-TLX table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nasa_tlx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER UNIQUE,
            mental_demand INTEGER,
            effort INTEGER,
            frustration INTEGER,
            submitted_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.commit()
    conn.close()


def seed_participants(db_path: str = None):
    """Insert participant codes P01–P10 and initialize all 6 levels for 2 layers."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    for i in range(1, 11):
        code = f"P{i:02d}"  # P01, P02, ..., P10
        cursor.execute(
            "INSERT OR IGNORE INTO participants (code) VALUES (?)", (code,)
        )

        # Get the participant_id for this code
        cursor.execute(
            "SELECT id FROM participants WHERE code = ?", (code,)
        )
        row = cursor.fetchone()
        if row:
            participant_id = row['id']
            # Initialize all 6 levels for Layer 1 (Main Headings)
            for level in range(1, 7):
                status = 'active' if level == 1 else 'locked'
                cursor.execute(
                    """INSERT OR IGNORE INTO bloom_progress
                       (participant_id, layer, level, status) VALUES (?, ?, ?, ?)""",
                    (participant_id, 1, level, status)
                )
            # Initialize all 6 levels for Layer 2 (Subheadings) - all locked initially
            for level in range(1, 7):
                cursor.execute(
                    """INSERT OR IGNORE INTO bloom_progress
                       (participant_id, layer, level, status) VALUES (?, ?, ?, ?)""",
                    (participant_id, 2, level, 'locked')
                )

    conn.commit()
    conn.close()


def get_participant_by_code(code: str, db_path: str = None):
    """Get participant by code. Returns dict or None."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participants WHERE code = ?", (code,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_participant_by_id(participant_id: int, db_path: str = None):
    """Get participant by ID. Returns dict or None."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participants WHERE id = ?", (participant_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def set_consent_given(participant_id: int, db_path: str = None):
    """Mark consent as given for a participant."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE participants SET consent_given = 1 WHERE id = ?",
        (participant_id,)
    )
    conn.commit()
    conn.close()


def get_bloom_progress(participant_id: int, layer: int = None, db_path: str = None):
    """
    Get all level statuses for a participant as a dict.
    
    Args:
        participant_id: The participant ID
        layer: Optional layer filter (1=Main Headings, 2=Subheadings). If None, returns all layers.
    
    Returns:
        Dict with format: {"1": {"1": "active", "2": "locked", ...}, "2": {...}} if no layer filter
        Or dict with format: {"1": "active", "2": "locked", ...} if layer is specified
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    if layer is not None:
        cursor.execute(
            "SELECT level, status FROM bloom_progress WHERE participant_id = ? AND layer = ?",
            (participant_id, layer)
        )
        rows = cursor.fetchall()
        conn.close()
        return {str(row['level']): row['status'] for row in rows}
    else:
        cursor.execute(
            "SELECT layer, level, status FROM bloom_progress WHERE participant_id = ?",
            (participant_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        result = {}
        for row in rows:
            layer_key = str(row['layer'])
            if layer_key not in result:
                result[layer_key] = {}
            result[layer_key][str(row['level'])] = row['status']
        return result


def get_level_status(participant_id: int, level: int, layer: int = 1, db_path: str = None):
    """Get status for a specific level and layer."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM bloom_progress WHERE participant_id = ? AND layer = ? AND level = ?",
        (participant_id, layer, level)
    )
    row = cursor.fetchone()
    conn.close()
    return row['status'] if row else 'locked'


def get_current_layer(participant_id: int, db_path: str = None):
    """Get the current active layer (1 or 2) for a participant."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    # Check if Layer 1 Level 6 is complete - if yes, Layer 2 is active
    cursor.execute(
        "SELECT status FROM bloom_progress WHERE participant_id = ? AND layer = 1 AND level = 6",
        (participant_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row['status'] == 'complete':
        return 2
    return 1


def unlock_layer(participant_id: int, layer: int, db_path: str = None):
    """Unlock Layer 1 Level 1 when participant starts, or Layer 2 after Layer 1 complete."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE bloom_progress
           SET status = 'active', unlocked_at = ?
           WHERE participant_id = ? AND layer = ? AND level = 1""",
        (datetime.now().isoformat(), participant_id, layer)
    )
    conn.commit()
    conn.close()


def unlock_level(participant_id: int, level: int, layer: int = 1, db_path: str = None):
    """Unlock a level (set status to 'active')."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE bloom_progress
           SET status = 'active', unlocked_at = ?
           WHERE participant_id = ? AND layer = ? AND level = ?""",
        (datetime.now().isoformat(), participant_id, layer, level)
    )
    conn.commit()
    conn.close()


def complete_level(participant_id: int, level: int, layer: int = 1, db_path: str = None):
    """Mark a level as complete."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE bloom_progress
           SET status = 'complete', completed_at = ?
           WHERE participant_id = ? AND layer = ? AND level = ?""",
        (datetime.now().isoformat(), participant_id, layer, level)
    )
    conn.commit()
    conn.close()


def is_layer_complete(participant_id: int, layer: int, db_path: str = None):
    """Check if all 6 levels in a layer are complete."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT COUNT(*) as count FROM bloom_progress 
           WHERE participant_id = ? AND layer = ? AND level <= 6 AND status = 'complete'""",
        (participant_id, layer)
    )
    row = cursor.fetchone()
    conn.close()
    return row['count'] == 6 if row else False


def save_test_result(participant_id: int, test_type: str, score: float, bloom_level_scores: dict, db_path: str = None):
    """Save a test result (pre or post). Returns the inserted row ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO test_results (participant_id, test_type, score, bloom_level_scores)
           VALUES (?, ?, ?, ?)""",
        (participant_id, test_type, score, json.dumps(bloom_level_scores))
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


def has_taken_test(participant_id: int, test_type: str, db_path: str = None):
    """Check if participant has already taken a test."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as count FROM test_results WHERE participant_id = ? AND test_type = ?",
        (participant_id, test_type)
    )
    row = cursor.fetchone()
    conn.close()
    return row['count'] > 0 if row else False


def log_llm_call(participant_id: int, feature: str, prompt: str, response: str, response_time_ms: int, 
                 layer: int = None, level: int = None, metadata: dict = None, db_path: str = None):
    """Log an LLM call for research purposes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO llm_logs (participant_id, layer, level, feature, prompt, response, response_time_ms, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (participant_id, layer, level, feature, prompt, response, response_time_ms, 
         json.dumps(metadata) if metadata else None)
    )
    conn.commit()
    conn.close()


def save_sus_response(participant_id: int, responses: dict, total_score: float, db_path: str = None):
    """Save SUS questionnaire responses."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR REPLACE INTO sus_responses
           (participant_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, total_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (participant_id,
         responses.get('q1'), responses.get('q2'), responses.get('q3'),
         responses.get('q4'), responses.get('q5'), responses.get('q6'),
         responses.get('q7'), responses.get('q8'), responses.get('q9'),
         responses.get('q10'), total_score)
    )
    conn.commit()
    conn.close()


def save_nasa_tlx(participant_id: int, mental_demand: int, effort: int, frustration: int, db_path: str = None):
    """Save NASA-TLX responses."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR REPLACE INTO nasa_tlx
           (participant_id, mental_demand, effort, frustration)
           VALUES (?, ?, ?, ?)""",
        (participant_id, mental_demand, effort, frustration)
    )
    conn.commit()
    conn.close()


def save_concept_node(participant_id: int, concept: str, definition: str, layer: int = 1,
                      source_text: str = None, is_candidate: bool = True, 
                      verification_status: str = 'pending', validation_result: str = None, 
                      revision_count: int = 0, db_path: str = None):
    """Save a concept node."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO concept_nodes (participant_id, layer, concept, definition, source_text, 
           is_candidate, verification_status, validation_result, revision_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (participant_id, layer, concept, definition, source_text, 
         1 if is_candidate else 0, verification_status, validation_result, revision_count)
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


def update_node_verification(node_id: int, verification_status: str, validation_result: str = None, db_path: str = None):
    """Update a concept node's verification status."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE concept_nodes 
           SET verification_status = ?, validation_result = ?
           WHERE id = ?""",
        (verification_status, validation_result, node_id)
    )
    conn.commit()
    conn.close()


def update_node_paraphrase(node_id: int, definition: str, similarity_score: float, db_path: str = None):
    """Update a concept node's definition and similarity score (Level 2)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE concept_nodes 
           SET definition = ?, similarity_score = ?
           WHERE id = ?""",
        (definition, similarity_score, node_id)
    )
    conn.commit()
    conn.close()


def get_concept_nodes(participant_id: int, layer: int = None, db_path: str = None):
    """Get all concept nodes for a participant, optionally filtered by layer."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if layer is not None:
        cursor.execute(
            "SELECT * FROM concept_nodes WHERE participant_id = ? AND layer = ?",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT * FROM concept_nodes WHERE participant_id = ?",
            (participant_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_verified_nodes(participant_id: int, layer: int = None, db_path: str = None):
    """Get only verified nodes for a participant."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if layer is not None:
        cursor.execute(
            "SELECT * FROM concept_nodes WHERE participant_id = ? AND layer = ? AND verification_status = 'verified'",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT * FROM concept_nodes WHERE participant_id = ? AND verification_status = 'verified'",
            (participant_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==================== Concept Edge Functions ====================

def save_concept_edge(participant_id: int, from_node: str, to_node: str, layer: int = 1,
                      edge_label: str = None, justification: str = None, 
                      evidence_text: str = None, db_path: str = None):
    """Save a concept edge."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO concept_edges (participant_id, layer, from_node, to_node, edge_label, justification, evidence_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (participant_id, layer, from_node, to_node, edge_label, justification, evidence_text)
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


def update_edge_challenge(edge_id: int, adversarial_challenge: str, db_path: str = None):
    """Update an edge with AI's adversarial challenge."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE concept_edges SET adversarial_challenge = ? WHERE id = ?",
        (adversarial_challenge, edge_id)
    )
    conn.commit()
    conn.close()


def mark_edge_defended(edge_id: int, defense_response: str, db_path: str = None):
    """Mark an edge as defended."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE concept_edges SET defense_response = ?, defended_at = ?, is_validated = 1 WHERE id = ?",
        (defense_response, datetime.now().isoformat(), edge_id)
    )
    conn.commit()
    conn.close()


def get_defended_edge_count(participant_id: int, layer: int = None, db_path: str = None):
    """Get count of defended edges for a participant."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if layer is not None:
        cursor.execute(
            "SELECT COUNT(*) as count FROM concept_edges WHERE participant_id = ? AND layer = ? AND defended_at IS NOT NULL",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) as count FROM concept_edges WHERE participant_id = ? AND defended_at IS NOT NULL",
            (participant_id,)
        )
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0


def get_concept_edges(participant_id: int, layer: int = None, db_path: str = None):
    """Get all concept edges for a participant."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if layer is not None:
        cursor.execute(
            "SELECT * FROM concept_edges WHERE participant_id = ? AND layer = ?",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT * FROM concept_edges WHERE participant_id = ?",
            (participant_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==================== Scenario Functions (Level 3 - Apply) ====================

def save_scenario_response(participant_id: int, scenario_text: str, selected_nodes: list, 
                           layer: int = 1, is_correct: bool = False, db_path: str = None):
    """Save a scenario response for Level 3."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO scenario_responses (participant_id, layer, scenario_text, selected_nodes, is_correct, attempts)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (participant_id, layer, scenario_text, json.dumps(selected_nodes), 1 if is_correct else 0)
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


def get_scenario_response_count(participant_id: int, layer: int = 1, correct_only: bool = True, db_path: str = None):
    """Get count of scenario responses, optionally only correct ones."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if correct_only:
        cursor.execute(
            "SELECT COUNT(*) as count FROM scenario_responses WHERE participant_id = ? AND layer = ? AND is_correct = 1",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) as count FROM scenario_responses WHERE participant_id = ? AND layer = ?",
            (participant_id, layer)
        )
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0


# ==================== Error Injection Functions (Level 5 - Evaluate) ====================

def inject_error(participant_id: int, error_type: str, target_id: int, 
                 original_value: str, injected_value: str, db_path: str = None):
    """Inject an error for the student to find."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO error_injections (participant_id, error_type, target_id, original_value, injected_value)
           VALUES (?, ?, ?, ?, ?)""",
        (participant_id, error_type, target_id, original_value, injected_value)
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


def mark_error_detected(error_id: int, db_path: str = None):
    """Mark an injected error as detected by the student."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE error_injections SET is_detected = 1, detected_at = ? WHERE id = ?",
        (datetime.now().isoformat(), error_id)
    )
    conn.commit()
    conn.close()


def get_error_detection_rate(participant_id: int, db_path: str = None):
    """Calculate error detection rate (true positives / total injected errors)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_detected = 1 THEN 1 ELSE 0 END) as detected
           FROM error_injections WHERE participant_id = ?""",
        (participant_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row['total'] > 0:
        return row['detected'] / row['total']
    return 0.0


# ==================== Export Artifact Functions (Level 6 - Create) ====================

def save_export_artifact(participant_id: int, export_type: str, ai_draft: str, 
                         user_edits: dict = None, utility_score: float = None, db_path: str = None):
    """Save an export artifact."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO export_artifacts (participant_id, export_type, ai_draft, user_edits, utility_score)
           VALUES (?, ?, ?, ?, ?)""",
        (participant_id, export_type, ai_draft, json.dumps(user_edits) if user_edits else None, utility_score)
    )
    conn.commit()
    result_id = cursor.lastrowid
    conn.close()
    return result_id


# ==================== Audit Log Functions ====================

def log_audit_action(participant_id: int, action: str, layer: int = None, level: int = None, 
                     details: dict = None, db_path: str = None):
    """Log an audit action for research purposes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO audit_logs (participant_id, layer, level, action, details)
           VALUES (?, ?, ?, ?, ?)""",
        (participant_id, layer, level, action, json.dumps(details) if details else None)
    )
    conn.commit()
    conn.close()


def get_llm_logs(participant_id: int, layer: int = None, level: int = None, db_path: str = None):
    """Get LLM logs for a participant, optionally filtered by layer/level."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    if layer is not None and level is not None:
        cursor.execute(
            "SELECT * FROM llm_logs WHERE participant_id = ? AND layer = ? AND level = ? ORDER BY created_at DESC",
            (participant_id, layer, level)
        )
    elif layer is not None:
        cursor.execute(
            "SELECT * FROM llm_logs WHERE participant_id = ? AND layer = ? ORDER BY created_at DESC",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT * FROM llm_logs WHERE participant_id = ? ORDER BY created_at DESC",
            (participant_id,)
        )
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_audit_logs(participant_id: int, layer: int = None, level: int = None, db_path: str = None):
    """Get audit logs for a participant, optionally filtered by layer/level."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    if layer is not None and level is not None:
        cursor.execute(
            "SELECT * FROM audit_logs WHERE participant_id = ? AND layer = ? AND level = ? ORDER BY timestamp DESC",
            (participant_id, layer, level)
        )
    elif layer is not None:
        cursor.execute(
            "SELECT * FROM audit_logs WHERE participant_id = ? AND layer = ? ORDER BY timestamp DESC",
            (participant_id, layer)
        )
    else:
        cursor.execute(
            "SELECT * FROM audit_logs WHERE participant_id = ? ORDER BY timestamp DESC",
            (participant_id,)
        )
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    # Test initialization
    print("Initializing database...")
    initialize_database()
    seed_participants()
    print("Database initialized and seeded with P01-P10")

    # Verify
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM participants")
    codes = [row['code'] for row in cursor.fetchall()]
    conn.close()
    print(f"Participants: {codes}")


def reset_participant_progress(participant_id: int, db_path: str = None):
    """
    Reset all progress for a participant. Clears nodes, edges, logs, progress, and consent.
    Use this to let participants start fresh without server restart.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Clear concept data
    cursor.execute("DELETE FROM concept_nodes WHERE participant_id = ?", (participant_id,))
    cursor.execute("DELETE FROM concept_edges WHERE participant_id = ?", (participant_id,))

    # Clear logs
    cursor.execute("DELETE FROM llm_logs WHERE participant_id = ?", (participant_id,))
    cursor.execute("DELETE FROM audit_logs WHERE participant_id = ?", (participant_id,))
    cursor.execute("DELETE FROM test_results WHERE participant_id = ?", (participant_id,))

    # Reset bloom progress for all layers and levels
    for layer in [1, 2]:
        for level in range(1, 7):
            status = 'active' if (level == 1 and layer == 1) else 'locked'
            cursor.execute(
                "UPDATE bloom_progress SET status = ?, unlocked_at = NULL, completed_at = NULL WHERE participant_id = ? AND layer = ? AND level = ?",
                (status, participant_id, layer, level)
            )

    # Reset consent
    cursor.execute("UPDATE participants SET consent_given = 0 WHERE id = ?", (participant_id,))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Test initialization
    print("Initializing database...")
    initialize_database()
    seed_participants()
    print("Database initialized and seeded with P01-P10")
    
    # Verify
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM participants")
    codes = [row['code'] for row in cursor.fetchall()]
    conn.close()
    print(f"Participants: {codes}")
