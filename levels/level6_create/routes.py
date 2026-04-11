"""
Level 6: Create — Generate export artifacts demonstrating mastery.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access

level6_bp = Blueprint("level6_create", __name__, url_prefix="/api/level6")


@level6_bp.route("/status", methods=["GET"])
def level6_status():
    """Return current Level 6 status."""
    participant_id = request.args.get("participant_id", "P01")
    access = check_level_access(participant_id, required_level=6)

    return jsonify({
        "allowed": access["allowed"],
        "status": access["status"],
    })
