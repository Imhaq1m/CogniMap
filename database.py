"""
CogniMap Database Module — SQLite schema and helper functions.
Tracks concept nodes, quiz attempts, and Bloom's Taxonomy progress.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

# Database path
DB_DIR = Path(__file__).parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "cognimap.db"

# Test database path (for pytest isolation)
TEST_DB_PATH = os.getenv("TEST_DB_PATH", None)


def get_connection():
    """Get SQLite connection, respecting test database isolation."""
    db_path = TEST_DB_PATH if TEST_DB_PATH else str(DB_PATH)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Concept nodes table (stores verified concepts with layer info)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_nodes (
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
        )
    """)

    # Quiz attempts table (tracks quiz scores per layer)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT DEFAULT 'P01',
            layer INTEGER DEFAULT 1,
            level INTEGER DEFAULT 1,
            score REAL NOT NULL,
            total_questions INTEGER NOT NULL,
            passed INTEGER DEFAULT 0,
            questions_json TEXT,
            responses_json TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)

    # Bloom progress table (tracks level progression per layer)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloom_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT DEFAULT 'P01',
            layer INTEGER DEFAULT 1,
            level INTEGER DEFAULT 1,
            status TEXT DEFAULT 'locked',
            unlocked_at TEXT,
            completed_at TEXT,
            UNIQUE(participant_id, layer, level)
        )
    """)

    # Seed initial data: Layer 1, Level 1 is 'active' for P01
    cursor.execute("""
        INSERT OR IGNORE INTO bloom_progress (participant_id, layer, level, status, unlocked_at)
        VALUES ('P01', 1, 1, 'active', datetime('now'))
    """)

    conn.commit()
    conn.close()
    print(f"[OK] Database initialized at {DB_PATH}")


# =====================================================
# Concept Node Operations
# =====================================================

def save_concept_nodes(concepts: list, participant_id: str = "P01"):
    """Save confirmed concepts to database with layer tracking."""
    conn = get_connection()
    cursor = conn.cursor()

    for concept in concepts:
        # Determine layer and type
        concept_type = concept.get('type', 'main_topic')
        layer = 1 if concept_type == 'main_topic' else 2

        cursor.execute("""
            INSERT OR IGNORE INTO concept_nodes 
            (participant_id, layer, concept_type, name, source, page)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            participant_id,
            layer,
            concept_type,
            concept.get('name', ''),
            concept.get('source', ''),
            concept.get('page')
        ))

    conn.commit()
    conn.close()


def get_concepts_by_layer(layer: int, participant_id: str = "P01"):
    """Get all concepts for a specific layer."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT * FROM concept_nodes 
        WHERE participant_id = ? AND layer = ?
        ORDER BY concept_type, name
    """, (participant_id, layer))
    
    concepts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return concepts


def get_verified_concepts(layer: int, participant_id: str = "P01"):
    """Get verified concepts for a specific layer."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT * FROM concept_nodes
        WHERE participant_id = ? AND layer = ? AND verified = 1
        ORDER BY concept_type, name
    """, (participant_id, layer))

    concepts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return concepts


def verify_concept(concept_id: int, definition: str = None):
    """Mark a concept as verified (passed validation/quiz)."""
    conn = get_connection()
    if definition:
        conn.execute("""
            UPDATE concept_nodes 
            SET verified = 1, definition = ?
            WHERE id = ?
        """, (definition, concept_id))
    else:
        conn.execute("""
            UPDATE concept_nodes 
            SET verified = 1 
            WHERE id = ?
        """, (concept_id,))
    
    conn.commit()
    conn.close()


# =====================================================
# Bloom Progress Operations
# =====================================================

def get_bloom_progress(participant_id: str = "P01"):
    """Get progress for all layers and levels."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT layer, level, status, unlocked_at, completed_at
        FROM bloom_progress 
        WHERE participant_id = ?
        ORDER BY layer, level
    """, (participant_id,))
    
    progress = {}
    for row in cursor.fetchall():
        layer = row['layer']
        level = row['level']
        if layer not in progress:
            progress[layer] = {}
        progress[layer][level] = {
            'status': row['status'],
            'unlocked_at': row['unlocked_at'],
            'completed_at': row['completed_at']
        }
    
    conn.close()
    return progress


def update_bloom_progress(participant_id: str, layer: int, level: int, 
                          status: str, completed: bool = False):
    """Update progress for a specific layer and level."""
    conn = get_connection()
    
    if completed:
        conn.execute("""
            UPDATE bloom_progress 
            SET status = ?, completed_at = datetime('now')
            WHERE participant_id = ? AND layer = ? AND level = ?
        """, (status, participant_id, layer, level))
    else:
        conn.execute("""
            UPDATE bloom_progress 
            SET status = ?, unlocked_at = datetime('now')
            WHERE participant_id = ? AND layer = ? AND level = ?
        """, (status, participant_id, layer, level))
    
    conn.commit()
    conn.close()


def unlock_next_level(participant_id: str, layer: int, current_level: int):
    """Unlock the next level after completing current level."""
    next_level = current_level + 1
    
    # Check if next level exists (max 6 levels)
    if next_level <= 6:
        update_bloom_progress(participant_id, layer, next_level, 'active')
        return True
    else:
        # Level 6 completed → check if layer is complete
        if layer == 1:
            # Unlock Layer 2, Level 1
            update_bloom_progress(participant_id, 2, 1, 'active')
            return True
        return False


# =====================================================
# Initialization
# =====================================================

# Auto-initialize on import
initialize_database()
