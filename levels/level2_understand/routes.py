"""
Level 2: Understand — Paraphrase definitions, semantic similarity check.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access

level2_bp = Blueprint("level2_understand", __name__, url_prefix="/api/level2")


@level2_bp.route("/validate-paraphrase", methods=["POST"])
def validate_paraphrase():
    """
    Validate a student's paraphrase using semantic similarity.

    Request JSON:
        original: str — original definition
        paraphrase: str — student's paraphrase
        participant_id: str — default 'P01'

    Response JSON:
        result: 'VALID', 'COPY_PASTE', or 'TOO_DIFFERENT'
        similarity: float — cosine similarity score
        feedback: str
    """
    data = request.json or {}
    original = data.get("original", "")
    paraphrase = data.get("paraphrase", "")
    participant_id = data.get("participant_id", "P01")

    if not original or not paraphrase:
        return jsonify({"error": "Original and paraphrase are required"}), 400

    access = check_level_access(participant_id, required_level=2)
    if not access["allowed"]:
        return jsonify({"error": f"Level 2 is {access['status']}"}), 403

    # TODO: Implement sentence-transformers similarity check
    # For now, return placeholder
    return jsonify({
        "result": "VALID",
        "similarity": 0.90,
        "feedback": "Paraphrase validation not yet implemented.",
    })
