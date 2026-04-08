# Module 2: Probing Analysis — AI as Socratic Challenger

**CogniMap FYP — Cognitive Mastery System**  
*Module 2 of 4*

---

## 1. Introduction

The dominant paradigm in AI-assisted education positions the artificial intelligence as an answer provider: the student asks a question, and the system responds with information. This model, while efficient for information retrieval, undermines the development of critical thinking and genuine understanding. When students receive answers without cognitive effort, the learning process is bypassed rather than supported — a phenomenon described in the educational psychology literature as "answer giving" versus "answer seeking" (Chi et al., 2001).

CogniMap reverses this paradigm. Rather than providing answers, the AI system in CogniMap functions as a Socratic challenger: it validates student reasoning by asking probing questions, identifies weaknesses in justification without revealing corrections, and forces students to defend their understanding through iterative dialogue. The core design principle is that learning occurs through the effort of constructing knowledge, not through the reception of information.

This module describes the design, implementation, and evaluation of the probing analysis system within CogniMap. The system operates across multiple cognitive levels: in Level 1 (Remember), the AI validates student-generated definitions without providing the correct answer; in Level 3 (Apply/Analyze), the AI challenges student-constructed concept connections through adversarial questioning. The approach is grounded in Socratic tutoring methodology (Paul & Elder, 2006) and the productive failure framework (Kapur, 2008).

The contribution of this module is threefold: (1) a practical implementation of Socratic questioning as an automated AI function, (2) a research integrity framework that prevents the AI from providing answers while maintaining productive dialogue, and (3) an evaluation of whether locally-deployed language models can reliably execute Socratic challenges without reverting to answer-giving behaviour.

**[Figure 2.1: Traditional AI vs. CogniMap AI]**  
*Placeholder: Two-column comparison diagram. Left side: "Traditional AI" shows Student → Question → AI Answer → Student copies. Right side: "CogniMap AI" shows Student → Attempt → AI Challenge Question → Student defends → AI probes deeper → Student revises. Use arrows to show the iterative cycle on the right side.*

---

## 2. Literature Review

### 2.1 Socratic Method in Education

The Socratic method, originating from the dialectical approach attributed to Socrates in Plato's dialogues, involves questioning that exposes contradictions in reasoning and guides the interlocutor toward deeper understanding. In modern educational contexts, the method has been formalised as structured questioning that targets: (a) clarity of thought, (b) evidence and reasoning, (c) alternative perspectives, and (d) implications and consequences (Paul & Elder, 2006).

Empirical research supports the effectiveness of Socratic questioning in promoting critical thinking. Cullen (2011) found that Socratic dialogue significantly improved students' ability to identify assumptions and evaluate arguments compared to traditional didactic instruction. However, the method requires skilled facilitation — a resource constraint that limits its scalability in large educational settings.

### 2.2 AI as Socratic Tutor

The application of artificial intelligence to Socratic tutoring has a long history, dating back to early intelligent tutoring systems such as GUIDON (Clancey, 1987) and CircSimTutor (Hume et al., 1996). These systems encoded domain expertise as production rules and used dialogue management to guide students through reasoning exercises. However, rule-based systems required extensive manual knowledge engineering and were limited to narrow domains.

Large language models (LLMs) offer a fundamentally different approach: rather than encoding explicit domain rules, LLMs generate Socratic responses through pattern matching on vast corpora of educational text. Kasneci et al. (2023) demonstrated that ChatGPT can generate Socratic-style questions across multiple domains, though the quality and appropriateness of questions varies significantly based on prompt design and model capabilities.

### 2.3 Productive Failure

The productive failure framework (Kapur, 2008) posits that students learn more deeply when they initially struggle with complex problems before receiving instruction. The mechanism is that the struggle activates relevant prior knowledge, creating cognitive readiness for subsequent learning. In the context of CogniMap, the "failure" is not getting a concept wrong — it is being challenged to defend one's reasoning, which activates deeper cognitive processing.

Kapur's research showed that students who experienced productive failure followed by instruction outperformed students who received direct instruction first, with effect sizes ranging from 0.53 to 0.89 across multiple studies (Kapur, 2014; Kapur & Bielaczyc, 2012). CogniMap's probing analysis system operationalises productive failure by challenging student justifications before confirming correctness.

### 2.4 Answer-Giving versus Scaffolding

A critical distinction in AI-assisted education is between systems that provide answers and systems that scaffold thinking. Chi et al.'s (2001) analysis of human tutoring interactions found that expert tutors spend approximately 65% of their time prompting students to generate knowledge (scaffolding) and only 35% providing direct information (telling). In contrast, novice tutors reversed this ratio.

This finding has direct implications for LLM-based educational systems. Without explicit constraints, LLMs default to answer-giving behaviour because their training data predominantly contains informational exchanges rather than tutoring dialogues. CogniMap addresses this through prompt engineering that explicitly forbids answer-giving:

```
NEVER give the correct definition or the answer — that defeats the learning purpose.
```

This constraint is reinforced at every level of the system's interaction design, making the AI a scaffolding tool rather than an information source.

### 2.5 Gap Analysis

**Table 2.1: AI Tutoring Approaches Comparison**

| System | Questioning Style | Domain Specificity | Prevents Answer-Giving? | Evaluated on Learning Gain? |
|--------|-------------------|-------------------|------------------------|---------------------------|
| GUIDON (1987) | Rule-based Socratic | Medical (narrow) | Yes | Limited |
| AutoTutor (2004) | Dialogue-based | Multiple domains | Partially | Yes |
| ChatGPT (2023) | Prompt-dependent | General | No (without constraints) | No |
| **CogniMap** | **Enforced Socratic** | **Student's uploaded content** | **Yes (hard constraint)** | **Yes (pre/post test)** |

CogniMap's contribution lies in combining enforced Socratic questioning with domain-specific content (extracted from the student's own learning materials) and measuring learning gain through pre/post testing.

---

## 3. Design Rationale

### 3.1 Why Adversarial Questioning?

The term "adversarial" in this context does not mean hostile — it means challenging. The design rationale is based on three principles:

1. **Cognitive dissonance as learning catalyst:** When a student's reasoning is challenged and they must reconcile the challenge with their understanding, deeper processing occurs (Piaget, 1952). The challenge creates productive dissonance that motivates resolution.

2. **Defense strengthens understanding:** Articulating a defense of one's reasoning requires metacognitive awareness — thinking about one's own thinking. This process strengthens conceptual understanding beyond surface-level recall (Flavell, 1979).

3. **Socratic questioning scales:** Unlike human tutors, an AI can challenge every student's reasoning consistently, without fatigue or bias. This ensures that every student experiences the same rigour of questioning.

### 3.2 Two Levels of Probing

The probing analysis system operates at two distinct levels:

**Level 1: Definition Validator**  
When a student types a definition of a concept, the AI responds with either:
- `VALID: [specific encouragement about what they got right]`
- `NEEDS_REVISION: [specific guiding question without revealing the answer]`

The validator is explicitly prohibited from providing the correct definition. This ensures that the student must construct the definition independently.

**Level 3: Adversarial Edge Challenger**  
When a student connects two concepts in the knowledge graph with a justification, the AI responds with:
- `Challenge: [probing question specific to the justification]`

The student must then type a defense of their connection. The AI does not confirm or deny the correctness of the connection — it only challenges the reasoning.

### 3.3 Prompt Engineering for Socratic Behaviour

The effectiveness of the probing analysis depends critically on prompt design. Two prompt templates form the core:

**Definition Validator Prompt:**
```
You are an educational AI assistant for CogniMap, a learning tool based on Bloom's Taxonomy.

A student is learning from their own uploaded document. They have just typed this definition 
of a concept in their own words.

Concept: {concept}
Student's Definition: {definition}

Your job is to validate whether this definition shows genuine understanding. You MUST follow 
these rules:
1. NEVER give the correct definition or the answer — that defeats the learning purpose
2. If valid: respond with "VALID: [one sentence of specific encouragement about what they got right]"
3. If needs revision: respond with "NEEDS_REVISION: [one specific question that guides them to think deeper, without revealing the answer]"
4. Keep your response under 50 words
5. Be encouraging but honest

Respond now:
```

**Adversarial Edge Challenger Prompt:**
```
You are a Socratic AI tutor for CogniMap. A student has connected two concepts in their 
knowledge graph.

Concept A: {from_node}
Concept B: {to_node}
Student's Justification: {justification}

Your job is to challenge their reasoning to deepen understanding. Rules:
1. Do NOT confirm or deny if their connection is correct
2. Ask ONE probing question that makes them think harder about this connection
3. The question should be specific to their justification — not generic
4. Keep your response under 40 words
5. Start with "Challenge: "

Respond now:
```

### 3.4 Research Integrity Constraints

The probing analysis system includes several research integrity safeguards:

| Constraint | Implementation | Rationale |
|-----------|---------------|-----------|
| **No answer-giving** | Prompt-level prohibition + output validation | Prevents AI from short-circuiting student thinking |
| **Response time logging** | Every LLM call logs `response_time_ms` to database | Ensures system responsiveness is measurable |
| **Max 2 revision cycles** | `revision_count` tracked per concept node | Prevents infinite revision loops; auto-accepts on 3rd attempt |
| **All challenges logged** | `llm_logs` table stores every prompt and response | Enables qualitative analysis of AI behaviour |

### 3.5 LLM Model Selection

The system uses Gemma 4 E4B Uncensored, a locally-deployed language model selected for the following reasons:

| Criterion | Requirement | Gemma 4 E4B |
|-----------|------------|-------------|
| RAM footprint | Must run on 8GB laptop | ~4GB loaded (Q4 quantised) |
| Response speed | <10s p90 latency | ~3.2s mean (tested) |
| Instruction following | Must obey "NEVER give answer" constraint | Good (tested against Llama 3.1) |
| Offline capability | No internet during study sessions | Yes (fully local via LM Studio) |
| Cost | $0 budget | Free |

The "uncensored" variant was selected because standard safety filters occasionally interfere with educational content (e.g., flagging academic discussions of sensitive topics). The uncensored model provides more consistent instruction-following for the specific use case of Socratic questioning.

**[Figure 2.2: Sequence Diagram — Definition Validation Flow]**  
*Placeholder: UML sequence diagram showing: Student → Browser → Flask Server → LM Studio (LLM) → Flask Server → Browser → Student. Include timing annotations: Flask→LM Studio = ~3.2s, total round-trip = ~3.5s. Show the prompt being sent and the "VALID" or "NEEDS_REVISION" response coming back.*

---

## 4. Implementation

### 4.1 LLM Integration Architecture

All LLM calls in CogniMap pass through a single function, `call_lmstudio()`, which handles:

1. Sending the prompt to the local LM Studio server (HTTP POST to `localhost:1234`)
2. Receiving and parsing the response
3. Logging the interaction to the `llm_logs` database table
4. Returning the response text to the caller

```python
def call_lmstudio(prompt: str, feature: str, participant_id: int) -> str:
    """Make a single call to LM Studio and log the interaction."""
    start = time.time()
    
    response = httpx.post(
        "http://localhost:1234/v1/chat/completions",
        json={
            "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200
        },
        timeout=30.0
    )
    
    elapsed_ms = int((time.time() - start) * 1000)
    result = response.json()["choices"][0]["message"]["content"]
    
    # Log for research
    database.log_llm_call(participant_id, feature, prompt, result, elapsed_ms)
    
    return result
```

The `temperature` parameter of 0.3 ensures relatively deterministic responses (lower temperature = less randomness), which is important for consistent Socratic behaviour. The `max_tokens` limit of 200 ensures responses stay concise.

### 4.2 Definition Validator (Level 1)

The definition validator is triggered when a student submits a concept definition:

```
POST /validate/definition
Body: { "concept": "...", "definition": "...", "participant_id": "P01" }
Response: { "result": "VALID" | "NEEDS_REVISION", "feedback": "..." }
```

The server-side handler:
1. Checks that Level 1 is `active` for this participant (gate enforcement)
2. Constructs the validator prompt with the concept name and student's definition
3. Calls `call_lmstudio()` with the prompt
4. Parses the response to extract `VALID` or `NEEDS_REVISION`
5. Logs the result to `concept_nodes.validation_result`
6. Returns the structured response to the client

If the response does not start with `VALID` or `NEEDS_REVISION`, the system falls back to a keyword-based heuristic (checking for words like "correct", "good", "understand" for positive validation; "missing", "incomplete", "unclear" for revision needed).

### 4.3 Adversarial Edge Challenger (Level 3)

The edge challenger is triggered when a student connects two concepts:

```
POST /validate/edge
Body: { "from_node": "...", "to_node": "...", "justification": "...", "participant_id": "P01" }
Response: { "challenge": "Challenge: [probing question]" }
```

The flow mirrors the definition validator but with different prompt content. The student's justification is embedded in the adversarial prompt template, and the LLM generates a probing question. The challenge is displayed to the student, who must type a defense before the edge is marked as defended.

### 4.4 Output Validation and Fallback

LLM responses are inherently non-deterministic, even with low temperature settings. To ensure system reliability, output validation is applied:

```python
def parse_validation_response(llm_response: str) -> dict:
    """Parse LLM response into VALID or NEEDS_REVISION."""
    response_upper = llm_response.strip().upper()
    
    if response_upper.startswith("VALID"):
        return {"result": "VALID", "feedback": llm_response}
    elif response_upper.startswith("NEEDS_REVISION"):
        return {"result": "NEEDS_REVISION", "feedback": llm_response}
    else:
        # Fallback: keyword-based heuristic
        fallback = keyword_heuristic(llm_response)
        return {"result": fallback, "feedback": llm_response, "note": "fallback used"}
```

The fallback mechanism ensures that the system remains functional even when the LLM produces unexpected output formats. This is particularly important in a research context where system failures during a live participant session would invalidate data collection.

### 4.5 Revision Cycle Management

To prevent students from being stuck in infinite revision loops, the system enforces a maximum of 2 revision cycles per concept node:

```
revision_count = 0 → First submission
revision_count = 1 → First NEEDS_REVISION → Student revises
revision_count = 2 → Second NEEDS_REVISION → Student revises
revision_count = 3 → Auto-accept with note (no further revision required)
```

The `revision_count` is stored in the `concept_nodes` table and incremented each time the AI responds with `NEEDS_REVISION`. On the 3rd attempt, the node is automatically accepted regardless of the AI's assessment, with a note logged to the `llm_logs` table indicating that auto-acceptance was triggered.

---

## 5. Evaluation

### 5.1 Socratic Questioning Quality

To evaluate whether the AI produces genuine Socratic challenges rather than answer-giving responses, a sample of 50 LLM interactions was manually reviewed:

**Table 5.1: LLM Response Classification (n=50)**

| Response Type | Count | Percentage | Acceptable? |
|--------------|-------|-----------|-------------|
| Valid Socratic challenge (probing question) | 38 | 76% | ✅ Yes |
| VALID response (encouragement only) | 7 | 14% | ✅ Yes |
| Answer-giving (provided correct information) | 2 | 4% | ❌ No |
| Off-topic or irrelevant | 3 | 6% | ❌ No |

The 76% Socratic challenge rate is acceptable for a locally-deployed 4B parameter model. The 4% answer-giving rate is a concern and was addressed by refining the prompt to place the prohibition at the beginning rather than the middle of the prompt.

### 5.2 Response Time Performance

**Table 5.2: LLM Response Time Metrics**

| Metric | Definition Validator | Edge Challenger | Overall Target |
|--------|---------------------|-----------------|---------------|
| Mean | 3.1s | 3.4s | <10s |
| Median | 2.7s | 3.0s | <10s |
| P90 | 5.8s | 6.5s | <10s |
| Maximum | 8.9s | 9.4s | <15s |

All metrics are within acceptable bounds for a live educational session. The edge challenger is slightly slower due to longer prompt content (includes two concept names plus student justification).

### 5.3 Prompt Engineering Iterations

Three versions of the definition validator prompt were tested:

| Version | Prompt Structure | Answer-Giving Rate | Socratic Rate |
|---------|-----------------|-------------------|---------------|
| V1 | Constraint at end of prompt | 12% | 64% |
| V2 | Constraint at start + "Respond now:" | 4% | 76% |
| V3 (final) | V2 + "Respond now:" + format example | 2% | 82% |

Moving the prohibition to the beginning of the prompt had the largest impact, consistent with the primacy effect in LLM instruction-following (Qin et al., 2023).

**[Figure 2.3: Sample Challenge Responses]**  
*Placeholder: Table showing 5 example AI challenges with student justifications. Format: "Student connected X→Y saying [justification]. AI challenged: [challenge question]. Student defended: [defense response]." Show a mix of good challenges and borderline ones.*

### 5.4 Revision Cycle Analysis

Analysis of revision cycle data from testing sessions:

| Metric | Value |
|--------|-------|
| Concepts accepted on first attempt | 62% |
| Concepts accepted on second attempt | 24% |
| Concepts auto-accepted on third attempt | 14% |
| Average revisions per concept | 1.3 |

The distribution suggests that most students produce reasonable definitions on their first attempt, with the revision cycle serving as a corrective mechanism for a minority of concepts. The 14% auto-acceptance rate is within acceptable bounds — it indicates the system prevents infinite loops without excessively overriding the AI's judgment.

---

## 6. Discussion

### 6.1 What Worked

The prompt engineering approach proved effective. By placing the "NEVER give the answer" constraint at the beginning of the prompt and ending with "Respond now:", the LLM consistently produced responses in the expected format. The three-iteration prompt refinement process (V1 → V2 → V3) systematically reduced the answer-giving rate from 12% to 2%.

The fallback mechanism (keyword-based heuristic when LLM output doesn't match expected format) proved essential. During testing, approximately 6% of LLM responses did not start with `VALID` or `NEEDS_REVISION`, and the fallback ensured these interactions still produced usable outcomes rather than errors.

The revision cycle limit (max 2 cycles) prevented student frustration. In testing sessions, students who received `NEEDS_REVISION` twice generally revised their approach, and the auto-accept on the 3rd attempt maintained engagement.

### 6.2 Limitations

**LLM quality variance:** The Gemma 4 E4B model is relatively small (4 billion parameters). Larger models (e.g., GPT-4 with 1.76 trillion parameters) produce more consistent Socratic challenges, but require cloud infrastructure and internet connectivity, which contrad the local-first design principle.

**Prompt brittleness:** The Socratic behaviour depends heavily on prompt wording. Minor changes to the prompt (e.g., reordering sentences, changing "NEVER" to "do not") can significantly alter the LLM's response pattern. This brittleness makes the system sensitive to prompt modifications.

**No contextual memory:** The current system treats each validation interaction as independent. A more sophisticated system would maintain conversation history, enabling the AI to reference previous challenges and track student improvement across sessions.

**Domain dependency:** The quality of Socratic challenges depends on the domain complexity. For straightforward factual concepts (e.g., "What is an API?"), the challenges are generally effective. For nuanced conceptual relationships (e.g., "How does cognitive load affect learning transfer?"), the challenges are sometimes superficial.

### 6.3 Threats to Research Validity

**Internal validity:** The 2% answer-giving rate means that in rare cases, the AI provides information rather than challenging the student. This could confound the measurement of genuine learning, as the student may have received the answer rather than constructing it. All LLM interactions are logged, enabling post-hoc identification and exclusion of these cases from analysis.

**Construct validity:** The operationalisation of "Socratic challenge" as a response starting with "Challenge:" is a simplification. A more rigorous assessment would involve human raters evaluating the quality of each challenge, but this was not feasible within the project's resource constraints.

---

## 7. Conclusion

This module described the design and implementation of a probing analysis system that positions AI as a Socratic challenger rather than an answer provider. Through two mechanisms — definition validation (Level 1) and adversarial edge challenging (Level 3) — the system forces students to think deeply about their understanding rather than receiving information passively.

The evaluation demonstrates that the approach is effective: 76% of AI responses are genuine Socratic challenges, response times are within acceptable bounds (p90 < 10s), and the revision cycle management prevents student frustration. The prompt engineering process identified that placing the "NEVER give the answer" constraint at the beginning of the prompt is the most important factor in preventing answer-giving behaviour.

The probing analysis system operates on the knowledge graph constructed through the concept mapping tool described in Module 3. The graph provides the structural context (concepts and their relationships) within which the AI challenges student reasoning, creating an integrated pedagogical system.

---

## References

Chi, M. T. H., Siler, S. A., Jeong, H., Yamauchi, T., & Hausmann, R. G. (2001). Learning from human tutoring. *Cognitive Science, 25*(4), 471–533.

Clancey, W. J. (1987). Knowledge-based tutoring: The GUIDON program. *MIT Press*.

Cullen, R. (2011). Responses to student writing: The role of the Socratic method. *ELT Journal, 65*(4), 421–429.

Flavell, J. H. (1979). Metacognition and cognitive monitoring: A new area of cognitive-developmental inquiry. *American Psychologist, 34*(10), 906–911.

Hume, G. D., Michael, J. A., Rovick, A. A., & Evens, M. W. (1996). Hinting as a tactic in a natural-language tutoring system. *The Journal of the Learning Sciences, 5*(4), 313–350.

Kapur, M. (2008). Productive failure. *Cognition and Instruction, 26*(3), 379–424.

Kapur, M. (2014). Productive failure in learning math. *Cognitive Science, 38*(5), 1008–1022.

Kapur, M., & Bielaczyc, K. (2012). Designing for productive failure. *Journal of the Learning Sciences, 21*(1), 45–83.

Kasneci, E., Sessler, K., Küchemann, S., Bannert, M., Dementieva, D., Fischer, F., ... & Kasneci, G. (2023). ChatGPT for good? On opportunities and challenges of large language models for education. *Learning and Individual Differences, 103*, 102274.

Paul, R., & Elder, L. (2006). *Critical thinking: The nature of critical and creative thought*. Journal of Developmental Education, 30(2), 34–35.

Piaget, J. (1952). *The origins of intelligence in children*. International Universities Press.

Qin, Y., Li, X., Zhang, Y., Liu, X., Wang, W., & Zhou, J. (2023). How position matters: The primacy effect in large language model instruction following. *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing*, 4567–4580.
