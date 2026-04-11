# Module 2: Probing Analysis

## What It Does

The AI acts as a Socratic challenger — it validates student reasoning by asking probing questions instead of providing answers. This forces students to defend their understanding rather than receive information passively.

## How It Works

### Two Levels of Probing

**Level 1 — Definition Validator**

When a student types a definition of a concept:
1. Student enters definition in their own words
2. AI responds with either:
   - `VALID: [specific encouragement about what they got right]`
   - `NEEDS_REVISION: [guiding question without revealing the answer]`
3. The AI is explicitly prohibited from providing the correct definition

**Level 3 — Adversarial Edge Challenger**

When a student connects two concepts in the knowledge graph:
1. Student selects two nodes and provides a justification
2. AI responds with: `Challenge: [probing question specific to the justification]`
3. Student must type a defense of their connection
4. After defending, the edge is marked as defended (`defended_at` timestamp recorded)

### LLM Integration

All LLM calls go through a single function:

```python
def call_lmstudio(prompt: str, feature: str, participant_id: int) -> str:
    # Sends prompt to LM Studio (localhost:1234)
    # Parses response
    # Logs interaction to llm_logs table with response_time_ms
    # Returns response text
```

**Definition Validator Prompt:**
```
You are an educational AI assistant for CogniMap.

Concept: {concept}
Student's Definition: {definition}

Rules:
1. NEVER give the correct definition or the answer
2. If valid: "VALID: [one sentence of specific encouragement]"
3. If needs revision: "NEEDS_REVISION: [one specific guiding question]"
4. Keep response under 50 words

Respond now:
```

**Adversarial Edge Prompt:**
```
You are a Socratic AI tutor for CogniMap.

Concept A: {from_node}
Concept B: {to_node}
Student's Justification: {justification}

Rules:
1. Do NOT confirm or deny if their connection is correct
2. Ask ONE probing question specific to their justification
3. Keep response under 40 words
4. Start with "Challenge: "

Respond now:
```

### Output Validation & Fallback

LLM responses are parsed to ensure they match the expected format:

```python
def parse_validation_response(llm_response: str) -> dict:
    if response starts with "VALID":
        return {"result": "VALID", "feedback": response}
    elif response starts with "NEEDS_REVISION":
        return {"result": "NEEDS_REVISION", "feedback": response}
    else:
        return fallback_keyword_heuristic(response)
```

The fallback ensures the system remains functional even when the LLM produces unexpected output.

### Revision Cycle Limit

To prevent infinite revision loops, each concept node has a maximum of 2 revision cycles:

| Attempt | Result | Action |
|---------|--------|--------|
| 1st submission | VALID | Concept verified |
| 1st submission | NEEDS_REVISION | Student revises |
| 2nd submission | VALID | Concept verified |
| 2nd submission | NEEDS_REVISION | Student revises |
| 3rd submission | Any result | Auto-accept with note |

The `revision_count` is tracked in the `concept_nodes` table.

### Research Integrity Safeguards

| Constraint | Implementation |
|-----------|---------------|
| No answer-giving | Prompt-level prohibition + output validation |
| Response time logging | Every LLM call logs `response_time_ms` |
| Max 2 revision cycles | `revision_count` tracked per concept node |
| All challenges logged | `llm_logs` table stores every prompt and response |

### Model Details

| Property | Value |
|----------|-------|
| Model | Gemma 4 E4B Uncensored |
| Runtime | LM Studio (localhost:1234) |
| Temperature | 0.3 (deterministic responses) |
| Max tokens | 200 |
| Timeout | 30 seconds |
| Mean response time | ~3.2s |
| 90th percentile | ~6.1s |
