"""
api.py — FastAPI backend for CogniMap

All business logic and API routes live here.
Level gates are enforced in every route that requires them.
Hierarchical scaffolding: Layer 1 (Main Headings) must be completed before Layer 2 (Subheadings).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

import database as db
import llm_utils as llm
import graph_utils as gu

# Initialize FastAPI app
app = FastAPI(title="CogniMap API", version="2.0.0")

# Enable CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Pydantic Models ====================

class LoginRequest(BaseModel):
    code: str


class NodeVerifyRequest(BaseModel):
    participant_id: int
    layer: int
    node_id: int
    verification_status: str  # 'verified' | 'rejected'
    validation_result: Optional[str] = None


class ParaphraseRequest(BaseModel):
    participant_id: int
    layer: int
    node_id: int
    original: str
    paraphrase: str


class ScenarioSubmitRequest(BaseModel):
    participant_id: int
    layer: int
    scenario_id: int
    selected_nodes: List[int]


class EdgeCreateRequest(BaseModel):
    participant_id: int
    layer: int
    from_node: str
    to_node: str
    edge_label: str
    justification: str
    evidence_text: Optional[str] = None


class EdgeDefendRequest(BaseModel):
    participant_id: int
    layer: int
    edge_id: int
    defense_response: str


class ErrorFlagRequest(BaseModel):
    participant_id: int
    layer: int
    error_id: int
    error_type: str  # 'wrong_node' | 'wrong_edge' | 'wrong_definition'


class ExportCreateRequest(BaseModel):
    participant_id: int
    layer: int
    export_type: str  # 'quiz' | 'study_guide' | 'essay_outline'
    user_edits: Optional[Dict[str, Any]] = None


class QuizSubmitRequest(BaseModel):
    participant_id: int
    layer: int
    level: int
    answers: Dict[int, int]  # question_id -> selected_option_index


class PDFUploadRequest(BaseModel):
    participant_id: int
    layer: int
    pdf_text: str


class LayerUnlockRequest(BaseModel):
    participant_id: int


class TestSubmitRequest(BaseModel):
    participant_id: int
    test_type: str  # 'pre' or 'post'
    answers: dict
    bloom_level_scores: dict


class SUSRequest(BaseModel):
    participant_id: int
    responses: dict  # {q1: 1-5, q2: 1-5, ..., q10: 1-5}


class NASATLXRequest(BaseModel):
    participant_id: int
    mental_demand: int
    effort: int
    frustration: int


# ==================== Startup Event ====================

@app.on_event("startup")
async def startup_event():
    """Initialize database and seed participants on startup."""
    print("Starting CogniMap API...")
    db.initialize_database()
    db.seed_participants()
    print("Database initialized and seeded with P01-P10")


# ==================== Helper Functions ====================

def check_level_access(participant_id: int, level: int, layer: int = 1):
    """Check if participant has access to a level. Raises 403 if locked."""
    status = db.get_level_status(participant_id, level, layer)
    if status == 'locked':
        raise HTTPException(
            status_code=403,
            detail=f"Level {level} (Layer {layer}) is locked. Complete previous levels first."
        )


def check_layer_access(participant_id: int, layer: int):
    """Check if participant has access to a layer. Raises 403 if Layer 1 not complete."""
    if layer == 2:
        if not db.is_layer_complete(participant_id, 1):
            raise HTTPException(
                status_code=403,
                detail="Layer 1 must be completed before accessing Layer 2."
            )


def check_consent_given(participant_id: int):
    """Check if participant has given consent. Raises 403 if not."""
    participant = db.get_participant_by_id(participant_id)
    if not participant or not participant.get('consent_given'):
        raise HTTPException(
            status_code=403,
            detail="Consent must be given before accessing this feature."
        )


# ==================== Authentication Routes ====================

@app.post("/login")
def login(request: LoginRequest):
    """Validate participant code and return participant info."""
    participant = db.get_participant_by_code(request.code.upper())

    if not participant:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid participant code: {request.code}. Please use P01-P10."
        )

    current_layer = db.get_current_layer(participant['id'])
    
    return {
        "participant_id": participant['id'],
        "code": participant['code'],
        "consent_given": participant['consent_given'],
        "current_layer": current_layer
    }


@app.post("/consent/{participant_id}")
def give_consent(participant_id: int):
    """Mark consent as given for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    db.set_consent_given(participant_id)
    db.log_audit_action(participant_id, "consent_given")
    return {"status": "success", "message": "Consent recorded"}


# ==================== Progress Routes ====================

@app.get("/progress/{participant_id}")
def get_progress(participant_id: int, layer: int = None):
    """Get Bloom's Taxonomy progress for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    progress = db.get_bloom_progress(participant_id, layer)
    current_layer = db.get_current_layer(participant_id)
    
    return {
        "progress": progress,
        "current_layer": current_layer
    }


@app.get("/layer/current/{participant_id}")
def get_current_layer(participant_id: int):
    """Get the current active layer for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    current_layer = db.get_current_layer(participant_id)
    layer1_complete = db.is_layer_complete(participant_id, 1)
    
    return {
        "current_layer": current_layer,
        "layer1_complete": layer1_complete
    }


@app.post("/layer/unlock")
def unlock_layer(request: LayerUnlockRequest):
    """Unlock Layer 2 after Layer 1 is complete."""
    check_consent_given(request.participant_id)
    
    if not db.is_layer_complete(request.participant_id, 1):
        raise HTTPException(
            status_code=403,
            detail="Layer 1 must be completed before unlocking Layer 2."
        )
    
    db.unlock_layer(request.participant_id, 2)
    db.log_audit_action(request.participant_id, "layer2_unlocked", level=1)
    
    return {"status": "success", "message": "Layer 2 unlocked!", "layer": 2}


# ==================== Level 1: Remember Routes ====================

@app.post("/pdf/upload")
def upload_pdf(request: PDFUploadRequest):
    """Process uploaded PDF and extract candidate nodes."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 1, request.layer)
    
    # Extract candidate nodes using NER
    candidate_nodes = llm.extract_candidate_nodes(
        pdf_text=request.pdf_text,
        participant_id=request.participant_id,
        layer=request.layer
    )
    
    # Save candidate nodes to database
    node_ids = []
    for node_data in candidate_nodes:
        node_id = db.save_concept_node(
            participant_id=request.participant_id,
            layer=request.layer,
            concept=node_data['concept'],
            definition=node_data['definition'],
            source_text=node_data['source_text'],
            is_candidate=True,
            verification_status='pending'
        )
        node_ids.append(node_id)
    
    db.log_audit_action(
        request.participant_id, "pdf_uploaded", 
        layer=request.layer, level=1,
        details={"node_count": len(node_ids)}
    )
    
    return {
        "status": "success",
        "candidate_nodes": [
            {"id": nid, **cnode} 
            for nid, cnode in zip(node_ids, candidate_nodes)
        ],
        "count": len(node_ids)
    }


@app.post("/nodes/verify")
def verify_node(request: NodeVerifyRequest):
    """Verify or reject a candidate node."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 1, request.layer)
    
    db.update_node_verification(
        node_id=request.node_id,
        verification_status=request.verification_status,
        validation_result=request.validation_result
    )
    
    db.log_audit_action(
        request.participant_id, "node_verified" if request.verification_status == 'verified' else "node_rejected",
        layer=request.layer, level=1,
        details={"node_id": request.node_id}
    )
    
    return {"status": "success", "message": f"Node {request.verification_status}"}


@app.get("/nodes/{participant_id}")
def get_nodes(participant_id: int, layer: int = None, verified_only: bool = False):
    """Get concept nodes for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    if verified_only:
        nodes = db.get_verified_nodes(participant_id, layer)
    else:
        nodes = db.get_concept_nodes(participant_id, layer)
    
    return {"nodes": nodes, "count": len(nodes)}


@app.post("/quiz/level1/generate")
def generate_level1_quiz(participant_id: int, layer: int = 1):
    """Generate Level 1 quiz from verified nodes."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 1, layer)
    
    verified_nodes = db.get_verified_nodes(participant_id, layer)
    
    if len(verified_nodes) < 3:
        raise HTTPException(
            status_code=400,
            detail="Need at least 3 verified nodes to generate a quiz."
        )
    
    questions = llm.generate_level1_quiz(
        verified_nodes=verified_nodes,
        participant_id=participant_id,
        layer=layer
    )
    
    # Store questions in session (for this demo, return them directly)
    return {
        "status": "success",
        "questions": questions,
        "count": len(questions)
    }


@app.post("/quiz/level1/submit")
def submit_level1_quiz(request: QuizSubmitRequest):
    """Submit Level 1 quiz and unlock Level 2 if score >= 80%."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 1, request.layer)
    
    # Calculate score (for demo, assume 1 question = 1 point)
    total_questions = len(request.answers)
    correct_answers = sum(1 for qid, ans in request.answers.items() if ans == 0)  # Simplified
    score = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    
    db.log_audit_action(
        request.participant_id, "level1_quiz_submitted",
        layer=request.layer, level=1,
        details={"score": score, "total": total_questions, "correct": correct_answers}
    )
    
    if score >= 80:
        db.unlock_level(request.participant_id, 2, request.layer)
        return {
            "status": "success",
            "score": score,
            "passed": True,
            "message": f"Score {score}% - Level 1 complete! Level 2 unlocked.",
            "unlocked": 2
        }
    else:
        return {
            "status": "fail",
            "score": score,
            "passed": False,
            "message": f"Score {score}% - Need ≥80% to advance. Try again.",
            "unlocked": None
        }


# ==================== Level 2: Understand Routes ====================

@app.post("/validate/paraphrase")
def validate_paraphrase(request: ParaphraseRequest):
    """Validate paraphrase using semantic similarity."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 2, request.layer)
    
    result = llm.validate_paraphrase(
        original=request.original,
        paraphrase=request.paraphrase,
        participant_id=request.participant_id,
        layer=request.layer
    )
    
    # Update node with paraphrase
    db.update_node_paraphrase(
        node_id=request.node_id,
        definition=request.paraphrase,
        similarity_score=result['similarity']
    )
    
    db.log_audit_action(
        request.participant_id, "paraphrase_validated",
        layer=request.layer, level=2,
        details={"result": result['result'], "similarity": result['similarity']}
    )
    
    return result


@app.post("/quiz/level2/submit")
def submit_level2_quiz(participant_id: int, layer: int = 1, score: float = 0):
    """Submit Level 2 quiz and unlock Level 3 if score >= 80%."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 2, layer)
    
    db.log_audit_action(
        participant_id, "level2_quiz_submitted",
        layer=layer, level=2,
        details={"score": score}
    )
    
    if score >= 80:
        db.unlock_level(participant_id, 3, layer)
        return {
            "status": "success",
            "score": score,
            "passed": True,
            "message": f"Score {score}% - Level 2 complete! Level 3 unlocked.",
            "unlocked": 3
        }
    else:
        return {
            "status": "fail",
            "score": score,
            "passed": False,
            "message": f"Score {score}% - Need ≥80% to advance. Try again.",
            "unlocked": None
        }


# ==================== Level 3: Apply Routes ====================

@app.post("/scenario/generate")
def generate_scenario(participant_id: int, layer: int = 1):
    """Generate a scenario for Level 3."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 3, layer)
    
    verified_nodes = db.get_verified_nodes(participant_id, layer)
    
    if len(verified_nodes) < 3:
        raise HTTPException(
            status_code=400,
            detail="Need at least 3 verified nodes to generate a scenario."
        )
    
    scenario = llm.generate_scenario(
        verified_nodes=verified_nodes,
        participant_id=participant_id,
        layer=layer
    )
    
    # Store scenario (simplified - in production, store in DB)
    scenario_id = 1  # Placeholder
    
    return {
        "status": "success",
        "scenario_id": scenario_id,
        "scenario_text": scenario['scenario_text'],
        "available_nodes": [{'concept': n['concept'], 'id': n['id']} for n in verified_nodes]
    }


@app.post("/scenario/submit")
def submit_scenario(request: ScenarioSubmitRequest):
    """Submit a scenario solution."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 3, request.layer)
    
    # For demo, validate with simplified logic
    # In production, fetch correct_concepts from stored scenario
    result = llm.validate_scenario_solution(
        selected_concepts=request.selected_nodes,
        correct_concepts=[],  # Would fetch from stored scenario
        participant_id=request.participant_id,
        layer=request.layer
    )
    
    db.save_scenario_response(
        participant_id=request.participant_id,
        layer=request.layer,
        scenario_text="",
        selected_nodes=request.selected_nodes,
        is_correct=result['is_correct']
    )
    
    correct_count = db.get_scenario_response_count(
        request.participant_id, request.layer, correct_only=True
    )
    
    db.log_audit_action(
        request.participant_id, "scenario_submitted",
        layer=request.layer, level=3,
        details={"is_correct": result['is_correct'], "correct_count": correct_count}
    )
    
    if correct_count >= 3:
        db.unlock_level(request.participant_id, 4, request.layer)
        return {
            "status": "success",
            "message": "3 consecutive correct solutions! Level 3 complete! Level 4 unlocked.",
            "unlocked": 4
        }
    
    return {
        "status": "submitted",
        "is_correct": result['is_correct'],
        "feedback": result['feedback'],
        "correct_count": correct_count,
        "message": f"Correct solutions: {correct_count}/3"
    }


# ==================== Level 4: Analyze Routes ====================

@app.post("/edges/add")
def add_edge(request: EdgeCreateRequest):
    """Add an edge between concepts."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 4, request.layer)
    
    # Save to database
    edge_id = db.save_concept_edge(
        participant_id=request.participant_id,
        layer=request.layer,
        from_node=request.from_node,
        to_node=request.to_node,
        edge_label=request.edge_label,
        justification=request.justification,
        evidence_text=request.evidence_text
    )
    
    # Also add to graph
    G = gu.load_graph(request.participant_id, request.layer)
    gu.add_edge_to_graph(
        G=G,
        from_node=request.from_node,
        to_node=request.to_node,
        edge_label=request.edge_label,
        justification=request.justification
    )
    gu.save_graph(G, request.participant_id, request.layer)
    
    db.log_audit_action(
        request.participant_id, "edge_created",
        layer=request.layer, level=4,
        details={"edge_id": edge_id}
    )
    
    return {"status": "success", "edge_id": edge_id}


@app.post("/edges/challenge")
def generate_edge_challenge(edge_id: int, participant_id: int, layer: int = 1):
    """Generate an adversarial challenge for an edge."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 4, layer)
    
    edge = db.get_concept_edges(participant_id, layer)
    edge_data = next((e for e in edge if e['id'] == edge_id), None)
    
    if not edge_data:
        raise HTTPException(status_code=404, detail="Edge not found")
    
    challenge = llm.generate_edge_challenge(
        from_node=edge_data['from_node'],
        to_node=edge_data['to_node'],
        justification=edge_data['justification'],
        participant_id=participant_id,
        layer=layer
    )
    
    db.update_edge_challenge(edge_id, challenge)
    
    return {"challenge": challenge}


@app.post("/edges/defend")
def defend_edge(request: EdgeDefendRequest):
    """Submit a defense for an edge."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 4, request.layer)
    
    db.mark_edge_defended(
        edge_id=request.edge_id,
        defense_response=request.defense_response
    )
    
    defended_count = db.get_defended_edge_count(request.participant_id, request.layer)
    
    db.log_audit_action(
        request.participant_id, "edge_defended",
        layer=request.layer, level=4,
        details={"edge_id": request.edge_id, "defended_count": defended_count}
    )
    
    if defended_count >= 5:
        db.unlock_level(request.participant_id, 5, request.layer)
        return {
            "status": "success",
            "message": "5 edges defended! Level 4 complete! Level 5 unlocked.",
            "unlocked": 5
        }
    
    return {
        "status": "success",
        "message": "Edge defense recorded",
        "defended_count": defended_count
    }


# ==================== Level 5: Evaluate Routes ====================

@app.post("/evaluate/inject-error")
def inject_error(participant_id: int, layer: int = 1):
    """Inject an error for the student to find."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 5, layer)
    
    nodes = db.get_verified_nodes(participant_id, layer)
    edges = db.get_concept_edges(participant_id, layer)
    
    error_data = llm.generate_error_injection(
        concept_nodes=nodes,
        concept_edges=edges,
        participant_id=participant_id,
        layer=layer
    )
    
    if not error_data:
        raise HTTPException(status_code=500, detail="Failed to generate error")
    
    error_id = db.inject_error(
        participant_id=participant_id,
        error_type=error_data['error_type'],
        target_id=error_data['target_id'],
        original_value=error_data['original_value'],
        injected_value=error_data['injected_value']
    )
    
    return {
        "status": "success",
        "error_id": error_id,
        "message": "Error injected. Can you find it?"
    }


@app.post("/evaluate/flag-error")
def flag_error(request: ErrorFlagRequest):
    """Flag an injected error as detected."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 5, request.layer)
    
    db.mark_error_detected(request.error_id)
    
    detection_rate = db.get_error_detection_rate(request.participant_id)
    
    db.log_audit_action(
        request.participant_id, "error_flagged",
        layer=request.layer, level=5,
        details={"error_id": request.error_id, "detection_rate": detection_rate}
    )
    
    if detection_rate >= 0.7:
        db.unlock_level(request.participant_id, 6, request.layer)
        return {
            "status": "success",
            "detection_rate": detection_rate,
            "message": "≥70% error detection rate! Level 5 complete! Level 6 unlocked.",
            "unlocked": 6
        }
    
    return {
        "status": "success",
        "detection_rate": detection_rate,
        "message": f"Error detected! Detection rate: {detection_rate*100:.0f}%"
    }


# ==================== Level 6: Create Routes ====================

@app.post("/create/export")
def create_export(request: ExportCreateRequest):
    """Generate an export artifact."""
    check_consent_given(request.participant_id)
    check_level_access(request.participant_id, 6, request.layer)
    
    nodes = db.get_verified_nodes(participant_id, request.layer)
    edges = db.get_concept_edges(participant_id, request.layer)
    
    ai_draft = llm.generate_export_artifact(
        verified_nodes=nodes,
        concept_edges=edges,
        export_type=request.export_type,
        participant_id=participant_id,
        layer=request.layer
    )
    
    artifact_id = db.save_export_artifact(
        participant_id=participant_id,
        export_type=request.export_type,
        ai_draft=ai_draft,
        user_edits=request.user_edits
    )
    
    db.log_audit_action(
        participant_id, "export_created",
        layer=request.layer, level=6,
        details={"artifact_id": artifact_id, "export_type": request.export_type}
    )
    
    return {
        "status": "success",
        "artifact_id": artifact_id,
        "ai_draft": ai_draft
    }


@app.post("/create/evaluate")
def evaluate_export(artifact_id: int, participant_id: int, layer: int = 1, user_edits: Dict = None):
    """Evaluate the utility of an export artifact."""
    check_consent_given(participant_id)
    check_level_access(participant_id, 6, layer)
    
    # Get artifact from DB (simplified)
    utility_score = llm.evaluate_export_utility(
        export_type="quiz",  # Would fetch from artifact
        ai_draft="",
        user_edits=user_edits or {},
        participant_id=participant_id,
        layer=layer
    )
    
    db.log_audit_action(
        participant_id, "export_evaluated",
        layer=layer, level=6,
        details={"artifact_id": artifact_id, "utility_score": utility_score}
    )
    
    if utility_score > 70:
        db.complete_level(participant_id, 6, layer)
        
        # If Layer 1 Level 6 complete, participant can unlock Layer 2
        if layer == 1:
            return {
                "status": "success",
                "utility_score": utility_score,
                "message": "Excellent artifact! Layer 1 complete! You can now unlock Layer 2.",
                "layer1_complete": True
            }
    
    return {
        "status": "success",
        "utility_score": utility_score,
        "message": f"Utility score: {utility_score:.0f}%"
    }


# ==================== Test Routes ====================
# ⚠️ ARCHIVED (April 5, 2026): Pre/post test routes moved to archive/
# These routes will be restored when ready for data collection phase
# To restore: Move archive/test_system.py back to root and uncomment below

# @app.post("/test/submit")
# def submit_test(request: TestSubmitRequest):
#     """Save pre or post test results."""
#     check_consent_given(request.participant_id)
# 
#     if db.has_taken_test(request.participant_id, request.test_type):
#         raise HTTPException(
#             status_code=400,
#             detail=f"You have already taken the {request.test_type}-test."
#         )
# 
#     total_score = sum(request.bloom_level_scores.values()) / len(request.bloom_level_scores)
# 
#     db.save_test_result(
#         request.participant_id,
#         request.test_type,
#         total_score,
#         request.bloom_level_scores
#     )
# 
#     return {"status": "success", "message": f"{request.test_type.title()} test saved"}


# @app.get("/test/{participant_id}/{test_type}")
# def check_test_status(participant_id: int, test_type: str):
#     """Check if participant has taken a test."""
#     has_taken = db.has_taken_test(participant_id, test_type)
#     return {"has_taken": has_taken}


# ==================== Questionnaire Routes ====================
# ⚠️ ARCHIVED (April 5, 2026): SUS/NASA-TLX routes moved to archive/
# These routes will be restored when ready for data collection phase
# To restore: Move archive/scoring_utils.py back to root and uncomment below

# @app.post("/questionnaire/sus")
# def submit_sus(request: SUSRequest):
#     """Save SUS questionnaire responses."""
#     check_consent_given(request.participant_id)
# 
#     odd_sum = sum(request.responses.get(f'q{i}', 0) - 1 for i in [1, 3, 5, 7, 9])
#     even_sum = sum(5 - request.responses.get(f'q{i}', 0) for i in [2, 4, 6, 8, 10])
#     total_score = (odd_sum + even_sum) * 2.5
# 
#     db.save_sus_response(request.participant_id, request.responses, total_score)
# 
#     return {"status": "success", "total_score": total_score}


# @app.post("/questionnaire/nasa")
# def submit_nasa_tlx(request: NASATLXRequest):
#     """Save NASA-TLX responses."""
#     check_consent_given(request.participant_id)
# 
#     db.save_nasa_tlx(
#         request.participant_id,
#         request.mental_demand,
#         request.effort,
#         request.frustration
#     )
# 
#     return {"status": "success"}


# ==================== Graph Routes ====================

@app.get("/graph/{participant_id}")
def get_graph(participant_id: int, layer: int = None):
    """Get graph data for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    if layer is None:
        layer = db.get_current_layer(participant_id)
    
    G = gu.load_graph(participant_id, layer)
    graph_data = gu.get_graph_for_visualization(G)
    
    return {
        "participant_id": participant_id,
        "layer": layer,
        "nodes": graph_data['nodes'],
        "edges": graph_data['edges'],
        "node_count": len(graph_data['nodes']),
        "edge_count": len(graph_data['edges'])
    }


# ==================== Export Routes ====================

@app.get("/export/{participant_id}")
def export_participant_data(participant_id: int):
    """Export all data for a participant."""
    participant = db.get_participant_by_id(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    # Get all data
    nodes = db.get_concept_nodes(participant_id)
    edges = db.get_concept_edges(participant_id)
    progress = db.get_bloom_progress(participant_id)
    
    return {
        "participant": participant,
        "nodes": nodes,
        "edges": edges,
        "progress": progress,
        "status": "success"
    }


# ==================== Health Check ====================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "CogniMap API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
