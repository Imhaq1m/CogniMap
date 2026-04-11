"""
Level 1: Remember — Define concepts in own words, AI validates.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access, call_lmstudio, load_graph_data
from database import verify_concept, get_concepts_by_layer

level1_bp = Blueprint("level1_remember", __name__, url_prefix="/api/level1")

# ---------------------------------------------------------------------------
# LLM Prompts
# ---------------------------------------------------------------------------

DEFINITION_VALIDATOR_PROMPT = """\
You are an educational AI assistant for CogniMap, a learning tool based on Bloom's Taxonomy.

A student is learning from their own uploaded document. They have just typed this definition of a concept in their own words.

Concept: {concept}
Student's Definition: {definition}

Your job is to validate whether this definition shows genuine understanding. You MUST follow these rules:
1. NEVER give the correct definition or the answer — that defeats the learning purpose
2. If valid: respond with "VALID: [one sentence of specific encouragement about what they got right]"
3. If needs revision: respond with "NEEDS_REVISION: [one specific question that guides them to think deeper, without revealing the answer]"
4. Keep your response under 50 words
5. Be encouraging but honest

Respond now:"""

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@level1_bp.route("/validate-definition", methods=["POST"])
def validate_definition():
    """
    Validate a student's definition of a concept.

    Request JSON:
        concept: str — concept name
        definition: str — student's definition
        participant_id: str — default 'P01'

    Response JSON:
        result: 'VALID' or 'NEEDS_REVISION'
        feedback: str — AI response text
        response_time_ms: int
    """
    data = request.json or {}
    concept = data.get("concept", "")
    definition = data.get("definition", "")
    participant_id = data.get("participant_id", "P01")

    if not concept or not definition:
        return jsonify({"error": "Concept and definition are required"}), 400

    # Gate check
    access = check_level_access(participant_id, required_level=1)
    if not access["allowed"]:
        return jsonify({"error": f"Level 1 is {access['status']}"}), 403

    # Call LLM
    prompt = DEFINITION_VALIDATOR_PROMPT.format(concept=concept, definition=definition)
    try:
        response_text = call_lmstudio(
            prompt,
            feature="definition_validator",
            participant_id=participant_id,
            max_tokens=100,
            timeout=30,
        )
    except Exception as e:
        return jsonify({"error": f"AI validation failed: {str(e)}"}), 500

    # Parse result
    result = "VALID" if response_text.startswith("VALID:") else "NEEDS_REVISION"

    return jsonify({
        "result": result,
        "feedback": response_text,
    })
