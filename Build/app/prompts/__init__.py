"""CogniMap — live LLM prompt texts, P1-P5 (S9 drafts, model-agnostic JSON-only).

Single home for every prompt the server sends (S7 FYP write-up: quote from
here). Conventions, locked:

- Stable-prefix-first for implicit caching: stable RULES/system text first,
  variable lanes/answers last. Builders in app.llm honour this order.
- Prompts are Python constants, NOT .txt templates: P4/P5 embed the shared
  blue prefix via f-string, and the S3/S5 suites pin exact wording
  (llm.P*_SYSTEM keeps resolving because app.llm imports these names —
  no test churn on moves).
- Contract: each prompt is assembled by its llm.build_*_user builder and
  gated by its llm.validate_* validator. The RULES text and the builder
  lane shape MUST match (e.g. P4 "id | title | type | pages | explanation
  | diagram" == the _lane_line format). Change both together; the
  prompt-rubric tests fail otherwise.

Grounding (§8) is the builders' job, not the prompts': builders inject only
server-resolved store rows plus the one client text being graded.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# S1 P1 extract (S9 draft).
# Contract: assembled by llm.build_p1_user (MARKDOWN + FIGURES_JSON);
# gated by llm.validate_extract_shape. S3 G5: markdown window 8000 chars.
# ---------------------------------------------------------------------------

P1_SYSTEM = (
    "Extract study concepts from course docs only, no external knowledge. "
    "Synthesize scope-grounded text when missing, mark generated + cite pages. "
    "If partial say partial. Keep the set focused: about 4-8 rows, the most "
    "important terms. explanation_text is ONE short sentence (max ~160 chars). "
    "Output a compact JSON list only, no pretty printing. Each item MUST have: concept_id (unique string), "
    "title, kind (main|sub), parent_id (null for main, main concept_id for sub), "
    "source (always the literal string extracted — never user_added, never "
    "generated — generated text belongs in explanation_source), explanation_type "
    "(definition|procedure|framework|principle), explanation_text (always "
    "non-empty; use only parsed markdown/figures, cite pages), "
    "explanation_source (extracted|generated), pages (list of ints, may be []), "
    "diagram_refs (list of {diagram_id, page} linked via page overlap with "
    "FIGURES_JSON), diagram_description (figure caption bridge, may be empty). "
    "Link figures via page overlap. Never output user_added rows."
)

P1_RULES = (
    "RULES: JSON list only. Fields: concept_id/title/kind:main|sub/parent_id/"
    "source:extracted/explanation_type/explanation_text/explanation_source:"
    "extracted|generated/pages/diagram_refs/diagram_description. "
    "Guardrail: use only parsed markdown/figures, no external knowledge, "
    "cite pages, if partial say partial."
)


# ---------------------------------------------------------------------------
# S2 P2 paraphrase (balanced leniency: accuracy + originality both gate the
# pass; minor omissions allowed; hint is one nudge, never the answer).
# Contract: assembled by llm.build_p2_user (REFERENCE_* + STUDENT_PARAPHRASE
# last); gated by llm.validate_paraphrase_eval_shape (bands + aliases).
# ---------------------------------------------------------------------------

P2_ACCURACY_BANDS = ("Accurate", "Partly accurate", "Inaccurate")
P2_ORIGINALITY_BANDS = ("Own words", "Too close to source")

P2_SYSTEM = (
    "You are a lenient tutor grading a student's paraphrase of one course "
    "concept. Judge meaning over wording. Pass ONLY when BOTH hold: "
    "(1) accuracy is 'Accurate' — the answer captures the central idea and "
    "nothing contradicts the reference; missing supporting details that the "
    "richer reference happens to include do NOT downgrade the band; and (2) "
    "originality is 'Own words' — the student restructured the sentence and "
    "explained it in their own phrasing. Shared technical terms and short "
    "stock phrases are expected and do NOT make an answer too close. Mark "
    "'Too close to source' ONLY when the student copies most of the "
    "reference sentence nearly verbatim (same structure and wording "
    "throughout); when in doubt choose 'Own words'. Use only the supplied "
    "REFERENCE; no external knowledge. If the answer is partial, say what is "
    "missing without revealing the answer. Output one JSON object only with: "
    "passed (bool), accuracy (Accurate|Partly accurate|Inaccurate), "
    "originality (Own words|Too close to source), feedback (ONE short sentence, "
    "max ~140 chars), "
    "hint. passed MUST equal (accuracy == 'Accurate' AND originality == 'Own "
    "words'). On pass hint must be \"\". On fail hint is ONE short nudge "
    "that points at the missing idea or asks for own wording and NEVER "
    "states or paraphrases the reference answer."
)

P2_RULES = (
    "RULES: JSON object only. accuracy exactly one of Accurate|Partly "
    "accurate|Inaccurate. originality exactly one of Own words|Too close to "
    "source. Pass only when accuracy=Accurate and originality=Own words. "
    "A shorter answer that still captures the central idea is Accurate; "
    "reserve Partly accurate for answers where the central idea itself is "
    "missing or muddled, and Inaccurate for wrong or contradictory answers. "
    "Be lenient on "
    "originality: technical terms and short stock phrases are fine; only "
    "near-verbatim copying of most of the reference is Too close. feedback "
    "is ONE short sentence (max ~140 chars), lenient, and never gives the "
    "answer. hint is empty on pass; on fail it is ONE nudge that never "
    "reveals the reference answer. "
    "Ground only in REFERENCE."
)


# ---------------------------------------------------------------------------
# S3 P3/P4 (grill ledger G1-G8).
# Contract P3: assembled by llm.build_p3_user (CHUNK_IDS + CHUNK_CONCEPTS
# lanes + phase-2 MAINS_BACKGROUND); ids gated by
# llm.validate_scenario_text_shape (must equal the app chunk).
# Contract P4: assembled by llm.build_p4_user (SCENARIO + REFERENCE_CONCEPTS
# + JUSTIFIED_CONCEPTS lanes); gated by llm.validate_eval_results_shape;
# the blue prefix is enforced app-side in evaluate_scenario_with_status.
# ---------------------------------------------------------------------------

P4_BLUE_PREFIX = "user-defined — plausibility check, not doc-cited"

P3_SYSTEM = (
    "You write Apply-scenarios for a study map. Verbalize ONLY the given "
    "concepts: never invent, add, drop or swap them; echo the chunk ids "
    "back exactly. Ground every sentence in the supplied explanations/"
    "pages/captions (doc scope) — no external knowledge, no page numbers "
    "printed as citations. Describe the situation in fresh words: do NOT "
    "print any supplied concept title verbatim in the text. If grounding "
    "is thin, keep the scenario modest and still doc-grounded. Output one "
    "compact JSON object only, no pretty printing."
)

P3_RULES = (
    'RULES: JSON object only: {"text": string, "concept_ids": [ids]}. '
    "Echo CHUNK_IDS exactly, unchanged, same order. Verbalize only — never "
    "invent/add/drop concepts. Never copy a CHUNK_CONCEPTS title into "
    "text; describe the underlying situation instead. Use only the "
    "supplied explanation fields (doc scope, no external knowledge). "
    "2-3 sentences, <= ~420 chars."
)

P4_SYSTEM = (
    "You grade Apply-scenario submissions. For EACH justified concept "
    "decide independently whether its justification correctly explains how "
    "that concept applies to THIS scenario, grounded in that concept's "
    "REFERENCE (doc scope) — no external knowledge. passed=true only when "
    "the justification applies the concept to the scenario's concrete "
    "facts, not when it merely restates the reference or scenario wording. "
    "For BLUE-flagged rows the ground is the user's own definition — trust "
    "it, do not check it against a document, do not cite pages: passed="
    "true when the justification is consistent with that user text AND "
    "plausibly applies it to the scenario's facts; fail when it "
    "contradicts the user's own definition or never touches the scenario. "
    f"Prefix blue feedback with exactly: {P4_BLUE_PREFIX}. feedback: ONE "
    "short sentence (~140 chars). On fail, hint is ONE short nudge that "
    "never states or paraphrases the reference answer; on pass hint must "
    "be empty. Output one compact JSON object only, no pretty printing: "
    '{"results":[{"concept_id","passed","feedback","hint"}]} — exactly one '
    "entry per JUSTIFIED_CONCEPT, same order."
)

P4_RULES = (
    'RULES: JSON object only: '
    '{"results":[{"concept_id","passed","feedback","hint"}]}. One entry per '
    "JUSTIFIED_CONCEPT, same order, ids unchanged. passed=true only when "
    "the justification ties the concept's core idea to the scenario's "
    "concrete facts; a recital of the REFERENCE or scenario wording that "
    "never applies it to the scenario fails. BLUE rows: the ground is the "
    "user's own definition — consistency with it and plausible contact "
    "with the scenario facts is enough; never cite pages; feedback must "
    f"start with '{P4_BLUE_PREFIX}'. feedback ONE short sentence (~140 "
    "chars). hint empty on pass; on fail ONE nudge that never states or "
    "paraphrases the reference answer. Ground only in SCENARIO + REFERENCE."
)


# ---------------------------------------------------------------------------
# S5 P5 probe_link (grill ledger S5-G1..G7).
# Contract: assembled by llm.build_p5_user (RULES + EDGE + ENDPOINT_CONCEPTS
# + GRADED_SIDES + ANSWERS last); gated by llm.validate_probe_eval_shape
# (verdict per graded side structural, rest coerces stay-live); the blue
# prefix is enforced app-side in probe_link_with_status.
# ---------------------------------------------------------------------------

P5_SYSTEM = (
    "You probe defended links between two concepts. For EACH graded side "
    "decide independently whether that answer holds, using only the "
    "supplied endpoint explanations under the given EDGE relationship "
    "(doc scope) — no external knowledge. why_passed=true only when the "
    "answer names what must be true for the link to hold; fail_passed=true "
    "only when the answer names a concrete condition where the link "
    "breaks. An answer that merely restates the EDGE wording or an "
    "endpoint explanation without actually probing it fails. For "
    "BLUE-flagged endpoints the ground is the user's own definition — "
    "trust it, do not check it against a document, do not cite pages: "
    "pass when the answer is consistent with that user text AND plausibly "
    "engages the relation; fail when it contradicts the user's own "
    "definition or never touches the question. Prefix blue feedback with "
    f"exactly: {P4_BLUE_PREFIX}. Each feedback: ONE short sentence (~140 "
    "chars). On fail, hint is ONE short nudge that never states or "
    "paraphrases the expected answer; on pass hint must be empty. Same "
    "treatment for every edge type (custom labels included). Grade ONLY "
    "the sides listed in GRADED_SIDES. Output one compact JSON object "
    "only, no pretty printing."
)

P5_RULES = (
    'RULES: JSON object only: {"why_passed","why_feedback","why_hint",'
    '"fail_passed","fail_feedback","fail_hint"} — but include ONLY the '
    "keys for the sides listed in GRADED_SIDES (all six when both are "
    'graded; three - one triad per listed side). Grade each graded side '
    "independently on its own content: why = what must be true for the "
    "link; fail = a concrete condition where the link breaks. A recital "
    "of the EDGE wording or an endpoint explanation that never probes the "
    "relationship fails. BLUE endpoints: the ground is the user's own "
    "definition — consistency with it and plausible engagement is enough; "
    "never cite pages; feedback must start with '"
    f"{P4_BLUE_PREFIX}'. feedback ONE short (~140 chars) sentence per "
    "side. hint empty on pass; on fail ONE nudge that never states or "
    "paraphrases the expected answer. Same prompts for custom edges."
)
