"""
Level 4: Analyze — Build complete concept graph, defend edges.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access, get_defended_edge_count

level4_bp = Blueprint("level4_analyze", __name__, url_prefix="/api/level4")


@level4_bp.route("/status", methods=["GET"])
def level4_status():
    """Return current Level 4 status."""
    participant_id = request.args.get("participant_id", "P01")
    access = check_level_access(participant_id, required_level=4)

    defended = get_defended_edge_count()

    return jsonify({
        "allowed": access["allowed"],
        "status": access["status"],
        "defended_edges": defended,
        "required": 5,
    })
