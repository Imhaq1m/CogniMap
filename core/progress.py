"""
Core Progress Module — Bloom's Taxonomy gate enforcement.
All level access checks and progression logic live here.
"""

from database import get_connection


def check_level_access(participant_id: str, required_level: int, layer: int = 1) -> dict:
    """
    Check if a participant can access a specific level.

    Args:
        participant_id: Participant code (e.g. 'P01')
        required_level: Bloom level (1-6)
        layer: Hierarchy layer (1=Main Topics, 2=Sub-topics)

    Returns:
        dict with 'allowed' (bool) and 'status' (str)

    Raises:
        ValueError: If level is out of range
    """
    if not (1 <= required_level <= 6):
        raise ValueError(f"Level must be 1-6, got {required_level}")

    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT status FROM bloom_progress
               WHERE participant_id = ? AND layer = ? AND level = ?""",
            (participant_id, layer, required_level)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"allowed": False, "status": "not_found"}

    status = row["status"]
    return {"allowed": status in ("active", "complete"), "status": status}


def get_bloom_progress(participant_id: str = "P01") -> dict:
    """
    Get progress for all layers and levels.

    Returns:
        Nested dict: {layer: {level: {status, unlocked_at, completed_at}}}
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """SELECT layer, level, status, unlocked_at, completed_at
               FROM bloom_progress
               WHERE participant_id = ?
               ORDER BY layer, level""",
            (participant_id,)
        )

        progress = {}
        for row in cursor.fetchall():
            layer = row["layer"]
            level = row["level"]
            if layer not in progress:
                progress[layer] = {}
            progress[layer][level] = {
                "status": row["status"],
                "unlocked_at": row["unlocked_at"],
                "completed_at": row["completed_at"],
            }
    finally:
        conn.close()

    return progress


def update_bloom_progress(participant_id: str, layer: int, level: int,
                          status: str, completed: bool = False):
    """Update progress for a specific layer and level."""
    conn = get_connection()
    try:
        if completed:
            conn.execute(
                """UPDATE bloom_progress
                   SET status = ?, completed_at = datetime('now')
                   WHERE participant_id = ? AND layer = ? AND level = ?""",
                (status, participant_id, layer, level)
            )
        else:
            conn.execute(
                """UPDATE bloom_progress
                   SET status = ?, unlocked_at = datetime('now')
                   WHERE participant_id = ? AND layer = ? AND level = ?""",
                (status, participant_id, layer, level)
            )
        conn.commit()
    finally:
        conn.close()


def complete_level(participant_id: str, layer: int, current_level: int) -> bool:
    """
    Mark current level as complete and unlock the next level.

    Args:
        participant_id: Participant code
        layer: Hierarchy layer (1 or 2)
        current_level: Current Bloom level (1-6)

    Returns:
        True if next level was unlocked, False if session is fully complete
    """
    # Mark current as complete
    update_bloom_progress(participant_id, layer, current_level, "complete", completed=True)

    next_level = current_level + 1

    # Check if next level exists (max 6 levels)
    if next_level <= 6:
        update_bloom_progress(participant_id, layer, next_level, "active")
        return True
    else:
        # Level 6 completed → check if layer is complete
        if layer == 1:
            # Unlock Layer 2, Level 1
            update_bloom_progress(participant_id, 2, 1, "active")
            return True
        return False


def get_current_level(participant_id: str, layer: int = 1) -> int:
    """Get the first level that is 'active' for this participant/layer."""
    progress = get_bloom_progress(participant_id)
    layer_progress = progress.get(layer, {})

    for level in range(1, 7):
        if level_progress := layer_progress.get(level):
            if level_progress["status"] == "active":
                return level

    return 7  # All levels complete
