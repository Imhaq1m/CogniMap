"""
db_wrapper.py — Database wrapper for Flask app that respects TEST_DB_PATH.

This module wraps all database.py functions to automatically pass the
TEST_DB_PATH environment variable when running tests. This ensures
Flask uses the test database during pytest runs instead of the production database.

Usage in Flask app:
    import db_wrapper as db  # Instead of: import database as db

All database function calls work exactly the same, but now respect TEST_DB_PATH.
"""

import os
import database as db_module


def _get_db_path():
    """Get the database path from environment or use default."""
    return os.environ.get('TEST_DB_PATH')


# ==================== Wrapper Functions ====================
# Each function calls the real database function with the correct db_path

def get_participant_by_code(code: str):
    return db_module.get_participant_by_code(code, db_path=_get_db_path())


def get_participant_by_id(participant_id: int):
    return db_module.get_participant_by_id(participant_id, db_path=_get_db_path())


def set_consent_given(participant_id: int):
    return db_module.set_consent_given(participant_id, db_path=_get_db_path())


def get_bloom_progress(participant_id: int, layer: int = 1):
    return db_module.get_bloom_progress(participant_id, layer=layer, db_path=_get_db_path())


def get_current_layer(participant_id: int):
    return db_module.get_current_layer(participant_id, db_path=_get_db_path())


def is_layer_complete(participant_id: int, layer: int):
    return db_module.is_layer_complete(participant_id, layer=layer, db_path=_get_db_path())


def complete_level(participant_id: int, level: int, layer: int = 1):
    return db_module.complete_level(participant_id, level, layer=layer, db_path=_get_db_path())


def unlock_level(participant_id: int, level: int, layer: int = 1):
    return db_module.unlock_level(participant_id, level, layer=layer, db_path=_get_db_path())


def unlock_layer(participant_id: int, layer: int):
    return db_module.unlock_layer(participant_id, layer=layer, db_path=_get_db_path())


def log_audit_action(participant_id: int, action: str, layer: int = None, level: int = None, details: dict = None):
    return db_module.log_audit_action(
        participant_id, action=action, layer=layer, level=level, details=details, db_path=_get_db_path()
    )


def get_audit_logs(participant_id: int):
    return db_module.get_audit_logs(participant_id, db_path=_get_db_path())


def get_concept_nodes(participant_id: int, layer: int = 1):
    return db_module.get_concept_nodes(participant_id, layer=layer, db_path=_get_db_path())


def get_concept_edges(participant_id: int, layer: int = 1):
    return db_module.get_concept_edges(participant_id, layer=layer, db_path=_get_db_path())


def save_concept_node(participant_id: int, concept: str, definition: str, layer: int = 1,
                      source_text: str = None, is_candidate: bool = True,
                      verification_status: str = 'pending', validation_result: str = None,
                      revision_count: int = 0):
    return db_module.save_concept_node(
        participant_id, concept=concept, definition=definition, layer=layer,
        source_text=source_text, is_candidate=is_candidate,
        verification_status=verification_status, validation_result=validation_result,
        revision_count=revision_count, db_path=_get_db_path()
    )


def save_concept_edge(participant_id: int, from_node: str, to_node: str, layer: int = 1,
                      edge_label: str = None, justification: str = None, evidence_text: str = None):
    return db_module.save_concept_edge(
        participant_id, from_node=from_node, to_node=to_node, layer=layer,
        edge_label=edge_label, justification=justification, evidence_text=evidence_text, db_path=_get_db_path()
    )


def update_node_verification(node_id: int, verification_status: str, validation_result: str = None):
    return db_module.update_node_verification(
        node_id, verification_status=verification_status, validation_result=validation_result, db_path=_get_db_path()
    )


def update_node_paraphrase(node_id: int, definition: str, similarity_score: float):
    return db_module.update_node_paraphrase(
        node_id, definition=definition, similarity_score=similarity_score, db_path=_get_db_path()
    )


def get_verified_nodes(participant_id: int, layer: int = 1):
    return db_module.get_verified_nodes(participant_id, layer=layer, db_path=_get_db_path())


def update_edge_challenge(edge_id: int, challenge: str):
    return db_module.update_edge_challenge(edge_id, challenge, db_path=_get_db_path())


def mark_edge_defended(edge_id: int, defense: str):
    return db_module.mark_edge_defended(edge_id, defense, db_path=_get_db_path())


def get_defended_edge_count(participant_id: int, layer: int = 1):
    return db_module.get_defended_edge_count(participant_id, layer=layer, db_path=_get_db_path())


def get_audit_logs(participant_id: int):
    """Get audit logs for a participant."""
    return db_module.get_audit_logs(participant_id, db_path=_get_db_path())


def get_llm_logs(participant_id: int, layer: int = None, level: int = None):
    """Get LLM logs for a participant."""
    return db_module.get_llm_logs(participant_id, layer=layer, level=level, db_path=_get_db_path())


def initialize_database(db_path: str = None):
    """Initialize database — uses TEST_DB_PATH if set, otherwise default."""
    path = db_path or _get_db_path()
    return db_module.initialize_database(db_path=path)


def seed_participants(db_path: str = None):
    """Seed participants — uses TEST_DB_PATH if set, otherwise default."""
    path = db_path or _get_db_path()
    return db_module.seed_participants(db_path=path)


def reset_participant_progress(participant_id: int):
    """Reset all progress, nodes, edges, and logs for a participant."""
    return db_module.reset_participant_progress(participant_id, db_path=_get_db_path())
