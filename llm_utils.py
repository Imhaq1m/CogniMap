"""
llm_utils.py — All LM Studio LLM interactions for CogniMap

Every LLM call goes through call_lmstudio() which logs to llm_logs table.
All prompts follow the research integrity rules:
- NEVER give the correct answer directly
- Use Socratic questioning to guide thinking
- Keep responses under 50 words
- Log all interactions with timing for research analysis
"""

import httpx
import time
import json
import re
from typing import List, Dict, Optional
from database import get_connection, log_llm_call, log_audit_action

# LM Studio server configuration
LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "gemma-4-e4b-uncensored-hauhaucs-aggressive"

# ==================== Core LLM Function ====================

def call_lmstudio(prompt: str, feature: str, participant_id: int, 
                  layer: int = None, level: int = None, 
                  metadata: dict = None, db_path: str = None) -> str:
    """
    Send a prompt to LM Studio and return the response.
    
    Args:
        prompt: The prompt to send
        feature: Feature name (e.g., 'ner_extraction', 'definition_validator')
        participant_id: Participant ID for logging
        layer: Bloom's layer (1=Main Headings, 2=Subheadings)
        level: Bloom's level (1-6)
        metadata: Additional metadata to log
        db_path: Optional custom database path
    
    Returns:
        LLM response text
    """
    start = time.time()
    
    try:
        response = httpx.post(
            LMSTUDIO_URL,
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            },
            timeout=30.0
        )
        response.raise_for_status()
        
        elapsed_ms = int((time.time() - start) * 1000)
        result = response.json()["choices"][0]["message"]["content"]
        
        # Log every call — this is research data
        log_llm_call(
            participant_id=participant_id,
            layer=layer,
            level=level,
            feature=feature,
            prompt=prompt,
            response=result,
            response_time_ms=elapsed_ms,
            metadata=metadata,
            db_path=db_path
        )
        
        # Warn if response is slow (research metric)
        if elapsed_ms > 10000:
            print(f"⚠️ SLOW RESPONSE: {elapsed_ms}ms (limit: 10,000ms)")
        
        return result
        
    except httpx.TimeoutException:
        log_llm_call(
            participant_id=participant_id,
            layer=layer,
            level=level,
            feature=feature,
            prompt=prompt,
            response="ERROR: Timeout after 30 seconds",
            response_time_ms=30000,
            metadata={"error": "timeout"},
            db_path=db_path
        )
        return "ERROR: LLM response timed out. Please try again."
        
    except httpx.HTTPError as e:
        log_llm_call(
            participant_id=participant_id,
            layer=layer,
            level=level,
            feature=feature,
            prompt=prompt,
            response=f"ERROR: {str(e)}",
            response_time_ms=0,
            metadata={"error": str(e)},
            db_path=db_path
        )
        return f"ERROR: Cannot connect to LM Studio. Is the Local Server running?"


# ==================== Level 1: Remember - Definition Validation ====================

def validate_definition(concept: str, definition: str, participant_id: int, 
                        layer: int = 1, db_path: str = None) -> Dict:
    """
    Validate a student's definition of a concept.

    Args:
        concept: The concept name
        definition: Student's definition in their own words
        participant_id: Participant ID for logging
        layer: Current layer (1 or 2)
        db_path: Optional custom database path

    Returns:
        Dict with 'result' (VALID/NEEDS_REVISION), 'feedback'
    """
    prompt = f"""You are an educational AI assistant for CogniMap, a learning tool based on Bloom's Taxonomy.

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

    response = call_lmstudio(
        prompt=prompt,
        feature="definition_validator",
        participant_id=participant_id,
        layer=layer,
        level=1,
        metadata={"concept": concept},
        db_path=db_path
    )

    # Parse response
    if "VALID:" in response:
        result = "VALID"
        feedback = response.split("VALID:")[1].strip()
    elif "NEEDS_REVISION:" in response:
        result = "NEEDS_REVISION"
        feedback = response.split("NEEDS_REVISION:")[1].strip()
    else:
        # Default to VALID if format unclear
        result = "VALID"
        feedback = response

    return {
        "result": result,
        "feedback": feedback,
        "raw_response": response
    }


# ==================== Level 1: Remember - NER Extraction ====================

def extract_candidate_nodes(pdf_text: str, participant_id: int, layer: int = 1, db_path: str = None) -> List[Dict]:
    """
    Extract candidate concept nodes from PDF text using NER.
    
    Args:
        pdf_text: Full text from uploaded PDF
        participant_id: Participant ID
        layer: Current layer (1 or 2)
        db_path: Optional custom database path
    
    Returns:
        List of dicts with 'concept', 'definition', 'source_text'
    """
    # Prompt for extracting key terms and definitions
    prompt = f"""You are an educational AI extracting key concepts from a learning document.

Extract the main {('HEADINGS' if layer == 1 else 'SUBHEADINGS')} and their definitions from this text.

RULES:
1. Extract 5-10 key terms that are ESSENTIAL for understanding this topic
2. For each term, provide the exact definition from the text
3. Include the source text snippet (1-2 sentences) that defines each term
4. Focus on {('broad structural concepts' if layer == 1 else 'detailed sub-concepts')}

Respond in JSON format only:
[
  {{
    "concept": "Term1",
    "definition": "Definition from text",
    "source_text": "Exact quote from document"
  }},
  ...
]

TEXT:
{pdf_text[:8000]}  # Truncate to avoid token limits

Extract concepts now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="ner_extraction",
        participant_id=participant_id,
        layer=layer,
        level=1,
        metadata={"pdf_length": len(pdf_text)},
        db_path=db_path
    )
    
    # Parse JSON response
    try:
        # Try to extract JSON from response (may have markdown formatting)
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            concepts = json.loads(json_match.group())
        else:
            concepts = json.loads(response)
        
        return [
            {
                "concept": c.get("concept", ""),
                "definition": c.get("definition", ""),
                "source_text": c.get("source_text", "")
            }
            for c in concepts
        ]
    except json.JSONDecodeError:
        # Fallback: return empty list if parsing fails
        log_audit_action(
            participant_id=participant_id,
            layer=layer,
            level=1,
            action="ner_extraction_failed",
            details={"response": response[:500]}
        )
        return []


def generate_level1_quiz(verified_nodes: List[Dict], participant_id: int, layer: int = 1, db_path: str = None) -> List[Dict]:
    """
    Generate MCQ quiz for Level 1 (Remember).
    
    Args:
        verified_nodes: List of verified concept nodes
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        List of quiz questions with options
    """
    if len(verified_nodes) < 3:
        return []
    
    # Prepare concepts for prompt
    concepts_str = "\n".join([
        f"- {n['concept']}: {n['definition']}"
        for n in verified_nodes[:8]  # Limit to 8 concepts
    ])
    
    prompt = f"""You are creating a multiple-choice quiz to test memory of definitions.

CONCEPTS:
{concepts_str}

Generate {min(len(verified_nodes), 5)} multiple-choice questions.

RULES:
1. Each question asks for the definition of a concept
2. Provide 4 options (1 correct, 3 plausible distractors)
3. Distractors should be related but clearly wrong
4. Include the correct answer index (0-3)

Respond in JSON format only:
[
  {{
    "question": "What is the definition of [Concept]?",
    "options": ["Correct definition", "Wrong but plausible", "Another wrong", "Third wrong"],
    "correct_index": 0
  }},
  ...
]

Generate quiz now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="level1_quiz_generation",
        participant_id=participant_id,
        layer=layer,
        level=1,
        db_path=db_path
    )
    
    # Parse JSON response
    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            questions = json.loads(json_match.group())
        else:
            questions = json.loads(response)
        
        return questions
    except json.JSONDecodeError:
        return []


# ==================== Level 2: Understand - Paraphrase Validation ====================

def validate_paraphrase(original: str, paraphrase: str, participant_id: int, 
                        layer: int = 1, db_path: str = None) -> Dict:
    """
    Validate a paraphrase using semantic similarity + LLM evaluation.
    
    Args:
        original: Original definition from source
        paraphrase: Student's paraphrase
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Dict with 'result', 'similarity', 'feedback'
    """
    # First, calculate semantic similarity using sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        embeddings = model.encode([original, paraphrase])
        similarity = float(util.cos_sim(embeddings[0], embeddings[1]))
    except Exception as e:
        # Fallback if sentence-transformers not available
        similarity = 0.5
        print(f"Warning: Could not calculate similarity: {e}")
    
    # LLM evaluates meaning preservation
    prompt = f"""You are evaluating whether a student's paraphrase preserves the meaning of the original definition.

ORIGINAL: {original}

STUDENT'S PARAPHRASE: {paraphrase}

RULES:
1. Check if the paraphrase preserves the CORE MEANING
2. Check if it uses DIFFERENT WORDS (not copy-paste)
3. If valid: respond with "VALID: [brief encouragement]"
4. If too similar (>95% same words): respond with "COPY_PASTE: [hint to use own words]"
5. If meaning is lost: respond with "MEANING_CHANGED: [what aspect changed]"
6. Keep feedback under 30 words

Evaluate now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="paraphrase_validation",
        participant_id=participant_id,
        layer=layer,
        level=2,
        metadata={"similarity_score": similarity},
        db_path=db_path
    )
    
    # Parse response
    if "VALID:" in response:
        result = "VALID"
        feedback = response.split("VALID:")[1].strip()
    elif "COPY_PASTE:" in response:
        result = "COPY_PASTE"
        feedback = response.split("COPY_PASTE:")[1].strip()
    elif "MEANING_CHANGED:" in response:
        result = "MEANING_CHANGED"
        feedback = response.split("MEANING_CHANGED:")[1].strip()
    else:
        result = "NEEDS_REVISION"
        feedback = response
    
    return {
        "result": result,
        "similarity": similarity,
        "feedback": feedback
    }


# ==================== Level 3: Apply - Scenario Generation ====================

def generate_scenario(verified_nodes: List[Dict], participant_id: int, layer: int = 1, db_path: str = None) -> Dict:
    """
    Generate a novel scenario for Level 3 (Apply).
    
    Args:
        verified_nodes: List of verified concept nodes
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Dict with 'scenario_text', 'correct_nodes', 'distractor_nodes'
    """
    concepts_str = "\n".join([n['concept'] for n in verified_nodes[:8]])
    
    prompt = f"""You are creating a problem-solving scenario that tests application of concepts.

AVAILABLE CONCEPTS:
{concepts_str}

Create a NOVEL scenario (not directly from the text) that requires applying 2-3 of these concepts.

RULES:
1. Scenario should be realistic and solvable using only the listed concepts
2. Do NOT make it obvious which concepts apply
3. Include plausible distractors (concepts that seem relevant but aren't)

Respond in JSON format:
{{
  "scenario_text": "Problem description...",
  "correct_concepts": ["Concept1", "Concept2"],
  "distractor_concepts": ["Concept3", "Concept4"]
}}

Generate scenario now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="scenario_generation",
        participant_id=participant_id,
        layer=layer,
        level=3,
        db_path=db_path
    )
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            scenario = json.loads(json_match.group())
        else:
            scenario = json.loads(response)
        
        return {
            "scenario_text": scenario.get("scenario_text", ""),
            "correct_concepts": scenario.get("correct_concepts", []),
            "distractor_concepts": scenario.get("distractor_concepts", [])
        }
    except json.JSONDecodeError:
        return {
            "scenario_text": "Error generating scenario. Please try again.",
            "correct_concepts": [],
            "distractor_concepts": []
        }


def validate_scenario_solution(selected_concepts: List[int], correct_concepts: List[str], 
                               participant_id: int, layer: int = 1, db_path: str = None) -> Dict:
    """
    Validate a scenario solution.
    
    Returns:
        Dict with 'is_correct', 'feedback'
    """
    # Convert to strings for comparison
    selected_set = set(str(c) for c in selected_concepts)
    correct_set = set(str(c) for c in correct_concepts)
    
    is_correct = selected_set == correct_set
    
    if is_correct:
        feedback = "Correct! You've identified the right concepts for this scenario."
    else:
        missing = correct_set - selected_set
        extra = selected_set - correct_set
        feedback_parts = []
        if missing:
            feedback_parts.append(f"Consider also: {', '.join(str(m) for m in missing)}")
        if extra:
            feedback_parts.append(f"Reconsider: {', '.join(str(e) for e in extra)}")
        feedback = " | ".join(feedback_parts)
    
    # Log for research
    log_audit_action(
        participant_id=participant_id,
        layer=layer,
        level=3,
        action="scenario_solution",
        details={
            "selected": selected_concepts,
            "correct": correct_concepts,
            "is_correct": is_correct
        },
        db_path=db_path
    )
    
    return {
        "is_correct": is_correct,
        "feedback": feedback
    }


# ==================== Level 4: Analyze - Adversarial Edge Challenge ====================

def generate_edge_challenge(from_node: str, to_node: str, justification: str, 
                            participant_id: int, layer: int = 1, db_path: str = None) -> str:
    """
    Generate a Socratic challenge for an edge justification.
    
    Args:
        from_node: Source concept
        to_node: Target concept
        justification: Student's justification
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Challenge question string
    """
    prompt = f"""You are a Socratic AI tutor challenging a student's reasoning.

CONCEPT A: {from_node}
CONCEPT B: {to_node}
STUDENT'S JUSTIFICATION: {justification}

RULES:
1. Do NOT confirm or deny if the connection is correct
2. Ask ONE probing question that makes them think harder
3. The question should be specific to their justification
4. Keep your response under 40 words
5. Start with "Challenge: "

Example format: "Challenge: You say X causes Y — but what happens when [specific counterexample]?"

Respond now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="edge_challenge",
        participant_id=participant_id,
        layer=layer,
        level=4,
        db_path=db_path
    )
    
    # Extract challenge (remove any preamble)
    if "Challenge:" in response:
        challenge = response.split("Challenge:")[1].strip()
        return f"Challenge: {challenge}"
    return f"Challenge: {response}"


def validate_edge_analysis(from_node: str, to_node: str, justification: str, 
                           defense: str, participant_id: int, layer: int = 1, db_path: str = None) -> Dict:
    """
    Validate if the student's defense successfully addresses the challenge.
    
    Returns:
        Dict with 'is_validated', 'feedback'
    """
    prompt = f"""You are evaluating whether a student successfully defended their reasoning.

CONCEPT A: {from_node}
CONCEPT B: {to_node}
ORIGINAL JUSTIFICATION: {justification}
STUDENT'S DEFENSE: {defense}

RULES:
1. Check if the defense addresses potential counterarguments
2. Check if the reasoning is logically sound
3. If validated: respond with "VALIDATED: [brief praise]"
4. If needs more work: respond with "NEEDS_MORE_WORK: [what's missing]"
5. Keep feedback under 40 words

Evaluate now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="edge_validation",
        participant_id=participant_id,
        layer=layer,
        level=4,
        db_path=db_path
    )
    
    if "VALIDATED:" in response:
        return {
            "is_validated": True,
            "feedback": response.split("VALIDATED:")[1].strip()
        }
    else:
        return {
            "is_validated": False,
            "feedback": response.split("NEEDS_MORE_WORK:")[1].strip() if "NEEDS_MORE_WORK:" in response else response
        }


# ==================== Level 5: Evaluate - Error Injection ====================

def generate_error_injection(concept_nodes: List[Dict], concept_edges: List[Dict], 
                             participant_id: int, layer: int = 1, db_path: str = None) -> Dict:
    """
    Generate an intentional error for the student to find.
    
    Args:
        concept_nodes: List of verified nodes
        concept_edges: List of validated edges
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Dict with 'error_type', 'target_id', 'original_value', 'injected_value'
    """
    import random
    
    # Decide error type
    error_types = ['wrong_definition', 'wrong_edge']
    error_type = random.choice(error_types)
    
    if error_type == 'wrong_definition' and concept_nodes:
        # Select a random node to modify
        target = random.choice(concept_nodes)
        
        prompt = f"""Generate a subtly WRONG definition for this concept.

CONCEPT: {target['concept']}
CORRECT DEFINITION: {target['definition']}

RULES:
1. Change ONE key aspect to make it incorrect
2. Keep it plausible (not obviously wrong)
3. Keep similar length to original

Respond in JSON:
{{
  "original": "{target['definition']}",
  "injected": "[your wrong definition]"
}}

Generate now:"""

        response = call_lmstudio(
            prompt=prompt,
            feature="error_injection_definition",
            participant_id=participant_id,
            layer=layer,
            level=5,
            db_path=db_path
        )
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            error_data = json.loads(json_match.group()) if json_match else json.loads(response)
            
            return {
                "error_type": "wrong_definition",
                "target_id": target['id'],
                "original_value": target['definition'],
                "injected_value": error_data.get("injected", "")
            }
        except json.JSONDecodeError:
            return None
    
    elif error_type == 'wrong_edge' and concept_edges:
        # Select a random edge to modify
        target = random.choice(concept_edges)
        
        prompt = f"""Generate a subtly WRONG edge label for this connection.

FROM: {target['from_node']}
TO: {target['to_node']}
CORRECT LABEL: {target.get('edge_label', 'Related to')}

RULES:
1. Change the relationship to something plausible but incorrect
2. Keep it short (1-3 words)

Respond in JSON:
{{
  "original": "{target.get('edge_label', 'Related to')}",
  "injected": "[your wrong label]"
}}

Generate now:"""

        response = call_lmstudio(
            prompt=prompt,
            feature="error_injection_edge",
            participant_id=participant_id,
            layer=layer,
            level=5,
            db_path=db_path
        )
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            error_data = json.loads(json_match.group()) if json_match else json.loads(response)
            
            return {
                "error_type": "wrong_edge",
                "target_id": target['id'],
                "original_value": target.get('edge_label', 'Related to'),
                "injected_value": error_data.get("injected", "")
            }
        except json.JSONDecodeError:
            return None
    
    return None


# ==================== Level 6: Create - Export Generation ====================

def generate_export_artifact(verified_nodes: List[Dict], concept_edges: List[Dict], 
                             export_type: str, participant_id: int, layer: int = 1, db_path: str = None) -> str:
    """
    Generate an export artifact (quiz, study guide, or essay outline).
    
    Args:
        verified_nodes: List of verified nodes
        concept_edges: List of validated edges
        export_type: 'quiz', 'study_guide', or 'essay_outline'
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Generated artifact text
    """
    nodes_str = "\n".join([f"- {n['concept']}: {n['definition']}" for n in verified_nodes[:10]])
    edges_str = "\n".join([f"- {e['from_node']} → {e['to_node']}: {e.get('edge_label', 'Related to')}" for e in concept_edges[:10]])
    
    if export_type == 'quiz':
        prompt = f"""Create a practice quiz from these concepts.

CONCEPTS:
{nodes_str}

RELATIONSHIPS:
{edges_str}

Generate a 5-question quiz with:
- 2 definition questions
- 2 application questions
- 1 analysis question

Include answer key at the end.

Format clearly with sections."""

    elif export_type == 'study_guide':
        prompt = f"""Create a study guide from these concepts.

CONCEPTS:
{nodes_str}

RELATIONSHIPS:
{edges_str}

Organize as:
1. Key Terms (alphabetical)
2. Concept Map (describe the graph structure)
3. Common Misconceptions to Avoid
4. Practice Questions

Format clearly with sections."""

    elif export_type == 'essay_outline':
        prompt = f"""Create an essay outline from these concepts.

CONCEPTS:
{nodes_str}

RELATIONSHIPS:
{edges_str}

Create an outline for an essay explaining this topic:
- Introduction (hook + thesis)
- Body Paragraph 1 (main concept)
- Body Paragraph 2 (relationships)
- Body Paragraph 3 (applications)
- Conclusion (summary + implications)

Format clearly with sections."""

    else:
        return "Error: Unknown export type"

    response = call_lmstudio(
        prompt=prompt,
        feature=f"export_generation_{export_type}",
        participant_id=participant_id,
        layer=layer,
        level=6,
        db_path=db_path
    )
    
    return response


def evaluate_export_utility(export_type: str, ai_draft: str, user_edits: Dict, 
                            participant_id: int, layer: int = 1, db_path: str = None) -> float:
    """
    Evaluate the utility of an export artifact after user edits.
    
    Returns:
        Utility score (0-100)
    """
    # Count edits as proxy for engagement
    edit_count = len(user_edits) if user_edits else 0
    
    # LLM evaluates quality
    prompt = f"""Evaluate this {export_type} for educational utility.

AI DRAFT:
{ai_draft[:3000]}

USER EDITS MADE: {edit_count} edits

Rate the utility on these criteria (1-10 each):
1. Clarity: Is it easy to understand?
2. Accuracy: Is the information correct?
3. Usefulness: Would this help someone learn?

Respond in JSON:
{{
  "clarity": 8,
  "accuracy": 9,
  "usefulness": 7,
  "total": 24
}}

Evaluate now:"""

    response = call_lmstudio(
        prompt=prompt,
        feature="export_utility_evaluation",
        participant_id=participant_id,
        layer=layer,
        level=6,
        metadata={"edit_count": edit_count},
        db_path=db_path
    )
    
    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        scores = json.loads(json_match.group()) if json_match else json.loads(response)
        return scores.get("total", 0) / 30 * 100  # Convert to percentage
    except json.JSONDecodeError:
        return 50.0  # Default score


# ==================== Scaffolding Fade-Out ====================

def get_ai_hint(feature: str, level: int, attempt_count: int, 
                participant_id: int, layer: int = 1, db_path: str = None) -> Optional[str]:
    """
    Get an AI hint with scaffolding fade-out.
    
    More hints at Level 1, fewer at Level 3, none at Level 5+.
    
    Args:
        feature: Current feature
        level: Bloom's level (1-6)
        attempt_count: Number of attempts
        participant_id: Participant ID
        layer: Current layer
        db_path: Optional custom database path
    
    Returns:
        Hint string or None if no hints available at this level
    """
    # Scaffolding fade-out: no hints at Level 5+
    if level >= 5:
        return None
    
    # Level 1-2: Full hints available
    # Level 3-4: Reduced hints
    # Level 5-6: No hints (independence)
    
    if level <= 2:
        max_hints = 3
    elif level <= 4:
        max_hints = 2
    else:
        return None
    
    if attempt_count >= max_hints:
        return None  # No more hints
    
    # Generate hint based on feature
    if feature == "definition_validation":
        hint_prompt = "Give a hint about what makes a good definition (without giving the answer)."
    elif feature == "paraphrase_validation":
        hint_prompt = "Give a hint about paraphrasing in your own words."
    elif feature == "scenario_solution":
        hint_prompt = "Give a hint about which concepts might apply here."
    elif feature == "edge_justification":
        hint_prompt = "Give a hint about explaining relationships between concepts."
    else:
        hint_prompt = "Give a general hint to help the student think deeper."
    
    response = call_lmstudio(
        prompt=hint_prompt,
        feature="scaffolding_hint",
        participant_id=participant_id,
        layer=layer,
        level=level,
        metadata={"attempt_count": attempt_count},
        db_path=db_path
    )
    
    return response
