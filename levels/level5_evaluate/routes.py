"""
Level 5: Evaluate — Find injected errors in concept graph.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access

level5_bp = Blueprint("level5_evaluate", __name__, url_prefix="/api/level5")


@level5_bp.route("/status", methods=["GET"])
def level5_status():
    """Return current Level 5 status."""
    participant_id = request.args.get("participant_id", "P01")
    access = check_level_access(participant_id, required_level=5)

    return jsonify({
        "allowed": access["allowed"],
        "status": access["status"],
    })
