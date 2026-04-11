"""
Level 3: Apply — Connect concepts with justifications, AI adversarially challenges.
"""

from flask import Blueprint, request, jsonify

from core import check_level_access, add_edge, call_lmstudio

level3_bp = Blueprint("level3_apply", __name__, url_prefix="/api/level3")

ADVERSARIAL_PROMPT = """\
You are a Socratic AI tutor for CogniMap. A student has connected two concepts in their knowledge graph.

Concept A: {from_node}
Concept B: {to_node}
Student's Justification: {justification}

Your job is to challenge their reasoning to deepen understanding. Rules:
1. Do NOT confirm or deny if their connection is correct
2. Ask ONE probing question that makes them think harder about this connection
3. The question should be specific to their justification — not generic
4. Keep your response under 40 words
5. Start with "Challenge: "

Example format: "Challenge: You say X causes Y — but what happens when [specific counterexample]?"

Respond now:"""


@level3_bp.route("/add-edge", methods=["POST"])
def add_edge_route():
    """
    Add an edge between two concepts and get AI challenge.

    Request JSON:
        from_node: str — source concept name
        to_node: str — target concept name
        justification: str — student's reasoning
        participant_id: str — default 'P01'
    """
    data = request.json or {}
    from_node = data.get("from_node", "")
    to_node = data.get("to_node", "")
    justification = data.get("justification", "")
    participant_id = data.get("participant_id", "P01")

    if not all([from_node, to_node, justification]):
        return jsonify({"error": "from_node, to_node, and justification are required"}), 400

    access = check_level_access(participant_id, required_level=3)
    if not access["allowed"]:
        return jsonify({"error": f"Level 3 is {access['status']}"}), 403

    edge = add_edge(from_node, to_node, justification)

    # Get AI adversarial challenge
    prompt = ADVERSARIAL_PROMPT.format(
        from_node=from_node, to_node=to_node, justification=justification
    )
    try:
        challenge = call_lmstudio(
            prompt,
            feature="edge_challenger",
            participant_id=participant_id,
            max_tokens=100,
            timeout=30,
        )
    except Exception as e:
        challenge = f"Challenge failed: {str(e)}"

    return jsonify({
        "edge": edge,
        "challenge": challenge,
    })
