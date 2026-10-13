# CogniMap — Grilling Locks Addendum (v1)
Companion to `Steps_Details.md` (frozen v1) + `Steps_Order.md`.
This file overrides/clarifies where ambiguous. If conflict, this file wins for implementation.

## 0. Locked assumptions
- Stack: Python backend `FastAPI` + small JS allowed for graph canvas only (drag-connect, labels, dim/bright). Graph host deferred (FastAPI + Cytoscape.js vanilla preferred, NiceGUI/Dash acceptable).
- Storage: `SQLite` (stdlib, still all-Python). Scoped by `session_id`. JSON seed files allowed for demo/fallback. Rationale: history dropdown + multi-session queries are painful in raw JSON.
- Profiles: lite profiles locked (name-pick, no auth). Tables `users(id, name)` + `sessions(id, user_id, file, created)` + `session_files(session_id, filename, created)` (or `files` JSON fallback; `sessions.file` = primary display label). Domain tables (`concepts/links/scenarios/trail`) carry `session_id` only; `user_id` is reached via `sessions` join (no denormalized `user_id` needed). Routes `/u/{user_id}` list + `/u/{user_id}/s/{session_id}` workspace. Single workspace template reused. Ownership check (locked, anti-IDOR): every workspace route AND every §8 server call MUST verify `sessions.user_id == route/session user_id` (join or ownership lookup), never `session_id` alone — `/u/A/s/{session_of_B}` must 404/block, and LLM resolvers must scope by owned `(session_id, concept/link/scenario_id)`. Session-scoped queries filter by owned `session_id` only after the check.
- File list + reset cascade (locked): sidebar renders the `session_files` list (one row per filename with `x`; Details "File 1" is the single-row instance of this list; `sessions.file` mirrors the primary/first entry as display label). Remove-file deletes its `session_files` row; if files remain, keep session data; removing last file = full reset via `clear_session_data(session_id)` (see §6): delete scoped `concepts/links/trail/scenarios` rows + clear `sessions.file`.
- Session lifecycle (locked): create (picker → new `sessions` row + `session_files` row), list (per `user_id`, ownership-checked), delete session (cascade deletes `session_files` + scoped domain rows). No cross-user reads.
- Parsing: `LlamaParse API`, tier `agentic` (or `agentic_plus` for complex pages) with `images_to_save: ["screenshot"]`, `expand: ["text","markdown","items","images_content_metadata"]`. Cost-optimizer allowed. Diagram screenshots served by convention at `/static/diagrams/{diagram_id}.png`; absent file → description-only rendering (no breakage).
- LLM API is IN SCOPE for build. Model choice deferred. All LLM use goes behind §8 interfaces (model-agnostic). Build UI against stubs + seed JSON.
- Original `Steps_Details.md` stays frozen. This file is the implementation checklist.

## 1. Extraction contract (Steps 1-2, Q4 + Q5-B)
Pipeline: `PDF -> LlamaParse (sentences/pages/figures) -> Extractor LLM (assigns to concepts)`.

Extractor MUST output per concept:
```json
{
  "concept_id": "c1",
  "title": "Machine Learning",
  "kind": "main | sub",
  "parent_id": null,
  "source": "extracted | user_added",
  "explanation_type": "definition | procedure | framework | principle",
  "explanation_text": "...",
  "explanation_source": "extracted | generated",
  "pages": [5, 6],
  "diagram_refs": [{"diagram_id": "fig-p5-1", "page": 5}],
  "diagram_description": "... (may be empty if none)"
}
```
Rules:
- Q4 locked: extractor reads figures + outputs `diagram_description` per concept. LlamaParse alone does NOT link figures to concepts.
- Q5=B locked: always fill `explanation_text`. If no explicit sentence, synthesize scope-grounded text, mark `explanation_source: "generated"`, cite pages. Prompt guardrail: "use only parsed markdown/figures, no external knowledge, cite pages, if partial say partial".
- Why B (do-not-forget):
  1. Slide/diagram demos lack clean definitional sentences — strict copy leaves nulls, broken drawer.
  2. Matches Q4 — diagrams need synthesized bridge.
  3. Concepts are procedures/frameworks/steps scattered across text+diagrams — need synthesis.
  4. Unblocks UX/progress — evaluator always has reference; label generated as `AI-grounded from doc scope` to stay defensible.
- Generalization: `explanation` replaces `definition`. Drawer label shows `Original Explanation [type, p.X]` or `AI-grounded from doc scope [type, p.X-Y]`.
- User rows (two-step, locked): `user_added` concepts are created at Confirm with `explanation_text = ""`, `explanation_source = "user"` (enum widened: `extracted | generated | user`) — there is no explanation input in the Step 2 modal, so no user-supplied text exists yet. The text is filled at L1-2 when the user saves a non-empty explanation (`store.set_user_explanation` writes the row; that save counts toward progress per §2).
- Extraction fallbacks (locked): `pages=[]` → drawer label omits `p.X` (no breakage); missing `explanation_type` → default `definition`; `concept_id` namespaced per session at Confirm (unique within `(session_id, concept_id)`, covers §1 shape vs drawer/history).

## 2. Level 1-2 (Q5 detail)
- Drawer: Concept Title (read-only post-Confirm), Explanation box + pages + diagram image/description if present, Your Paraphrase box, Verify button.
- Blue (user_added): omit source box, show warning "Ensure your self-defined concept is accurate — not verified against source.", bypass LLM eval. Saving non-empty user explanation counts toward progress. Blue text later serves as its own ground for L3/L4/L5 (see §5+§8) with plausibility-check feedback, never doc-cited.
- Eval (extracted): returns `{passed, accuracy, originality, feedback, hint}`. Lenient, hints not answers.
- Progress: `% = completed / total_visible`. Phase 1 total = mains only. Phase 2 total = subs only.

## 3. Level 3 Apply (Q6 + Q7)
- Locked Q6: Phase 1 `conceptCount` = mains only. Phase 2 = subs only. `successfully cleared` = ALL concepts + justifications in that scenario correct. No half credit.
- Total scenarios = `ceil(conceptCount / 3)`. `3` is divisor only, not concepts-per-scenario mandate.
- Locked Q7: `2-3 concepts per scenario, target/cap 3`. App partitions uncovered set into chunks of 3, no repeats until all covered. Remainder rule (locked): if `n % 3 == 1`, merge last 4 into `2+2` (n=4 → 2+2, n=7 → 3+2+2); n=1 → single 1-concept scenario as the only min-2 exception. Total scenarios stays `ceil(n/3)`. Blues included.
- Eval tiers (locked, strict all-or-nothing — Locks wins over Details Level 3 §4 3-tier): (1) wrong concept selected → flag + explain why not related; (2) right concept, wrong justification → guiding hint; (3) right concept + right justification → correct; (4) required scenario concept NOT selected → omission flagged via `missed_ids`, scenario NOT cleared, feedback names the missed concept. Clear only when every `scenario_concept_ids` entry is selected AND every justification passes. No half credit (partial scenarios never count).
- Retry: retry SAME scenario text + same concept set, with hints. Lock-passed: correct ones locked green, rewrite failed only. Clear only when all green together. Pure retry-from-scratch rejected (frustration).
- UI: split panel Scenario left / Concepts checkboxes right, justification field under each checked box, green Submit, per-concept `Result: x/y` + hints.
- Checkbox pool (locked — Locks §3+§7 win over Details Level 3 §2 "subset" / Phase 2 §2 "expanded pool" / Order Step 4): pool = all visible-counted concepts (Phase 1: mains, Phase 2: subs per §7 — never mains+subs mixed). `scenario_concept_ids` = hidden app-partitioned subset for this scenario (never revealed until omission feedback). `context_markdown` passed to `generate_scenario` may include mains as display-only background, but mains are never chunked, never pooled, never in `scenario_concept_ids`. Pool=chunk-only or mains+subs would break `ceil(n/3)` math, the 2+2 remainder partition, and tiers 1/4 (dead code). Strict clear = `missed_ids` empty AND all passed.
- Progress (locked): L3 `% = cleared_scenarios / ceil(n/3)`; a scenario counts only when all-green together (missed empty AND every selected justification passed; lock-passed retry per §3). Failed attempts never increment numerator or denominator (`ceil(n/3)` fixed from counted set; `missed_ids` empty AND all passed required per §3+§8, TODO Step 3 strict). Partial clears never advance %.

## 4. Level 4 Analyze (Q8 + custom Q11 + edits)
- Counting: undirected. Arrow head is visual phrasing only. A-B gives +1 to both for Finish/max checks. Store edges ordered (from, to, type) for display and L5 probing; all Finish/max-3/duplicate checks treat the pair unordered. Defense rationale (locked): one edge per unordered pair regardless of type prevents clique explosion and keeps L5 N tractable for FYP scope; directed semantics are preserved in stored `(from, to, type)` and probed at L5, so `A causes B` vs `B depends on A` remains distinguishable in evaluation even though the second drag is blocked.
- Limits: `>=1 per concept to enable Finish, max 3 per concept`. No self-loops. One edge per unordered pair (no duplicates). Duplicate = same pair second drag regardless of type — blocked with message "One link per pair — direction stored for probing." (reviewer must test second-drag-block regardless of type, e.g. `A causes B` then `B depends on A`).
- Edge panel: presets `causes, leads to, depends on, includes, contrasts with, applied in, influences, consists of, custom` (8 presets + custom, matches Steps_Order §Step 5; Steps_Details §Level 4 §4 omission overridden) + green Confirm. Mid-line label rendering for all.
- Custom (Q11 locked): free-text `1-24 chars, single line, trim, max 3 words, charset [A-Za-z0-9 space hyphen] only, no newlines/emoji/arrows, block exact duplicates of presets case-insensitive (all 8 presets)`. Reason: fits mid-edge label, prevents graph/JSON breakage.
- Finish: dimmed until every visible-counted concept has >=1. Phase 1 counts mains. Phase 2 counts subs (mains already satisfied, ignored). No % bar. n=1 exception (locked): a single counted concept cannot link (self-loops banned, 0 pairs) — L4 auto-passes with Finish enabled and zero links, L5 N=0 auto-completes (vacuous pass, probe skipped, advance to Phase-2 / completion). Confirm copy recommends ≥2–3 mains to avoid this trivial path (see §6.1).
- Edits in L4: delete-link + re-pick type allowed (a deleted pair may be re-added — duplicate block applies only to currently-present pairs, so Finish can always recover after delete). No concept add/delete/rename.

## 5. Level 5 Evaluate (Q9 + Q12)
- Entry: Phase 1: all L4 links dimmed; Phase 2: only new Phase-2 links dim at L5 entry (old main–main links stay bright, excluded — overrides Details Level 5 §1 all-dim wording; this file wins). Sidebar `Level 5 [Evaluate] 0%`, denominator N fixed at entry = links present at entry (Phase 1); in Phase 2, N = new links created in Phase 2 L4 only. Graph structure frozen (no add/delete links/concepts).
- Modal per link: title `[A] → [type] → [B]`, two prompts Why exists / When fails, two text boxes, green Submit.
- Eval: independent per side `{why_passed, why_feedback/hint, fail_passed, fail_feedback/hint}`. Same prompts for custom edges (no difference). Blue-involved links (either endpoint `source=user_added`): resolve the user-supplied text as ground and return distinct feedback "user-defined — plausibility check, not doc-cited" (no page citations for the blue side).
- Retry Q12 locked (mirrors L3): lock-passed per perspective. Passed side stays green, rewrite failed side only. Brighten link only when both green. Progress `bright/N`.

## 6. Edit model + warnings (locked)
- Step 2 modal only: rename any (pen icon), add mains/subs (Phase 1) or subs-only (Phase 2) via hover `+` lines, delete any pre-Confirm via row `x` control, remove file = reset. Deselect (uncheck, excluded from Confirm but row kept) ≠ delete (`x`, row removed). Deleting a main cascades to its subs (confirm prompt, `parent_id` orphans forbidden); deleting a sub removes that row only. `kind`/`parent_id`/`source` integrity enforced at Confirm. `source` flag preserved.
- L1-3: titles read-only, no structural edits. Override (locked): Steps_Details §Level 1-2 §3.1 "editable or viewable" overridden — title read-only post-Confirm; rename only in Step 2 modal.
- L4: delete-link allowed, no concept edits.
- L5: frozen, probe only.
- `clear_session_data(session_id)` (locked): deletes scoped `concepts/links/scenarios/trail` rows for the session + clears `sessions.file` + deletes its `session_files` rows + resets `stage='steps1-2'`, `phase='phase1'`. Invoked by last-file remove; per-file remove (files remain) deletes only that `session_files` row and keeps domain data.
- Heads-up copy to implement:
  1. On Confirm: "Heads up — concepts lock after this. Check names/selection, you can't add/delete later. ≥2–3 mains recommended (a single main auto-passes Analyze/Evaluate with no links to defend)." [Confirm / Back]
  2. On L4 entry: "Each concept needs 1-3 links (one link per pair — direction stored for probing). You can delete/re-pick links, but can't add concepts."
  3. On L5 entry: "Graph frozen for evaluation. Click dimmed links to defend them."

## 7. Phase 2 merge (Q10 locked)
- Mains keep L4 links + L5 bright state. No reset.
- Mixed workspace, filtered progress: show mains (dimmed/completed, locked) + subs (active). All math on subs + new links only.
- L1-2 progress on subs. L3 `ceil(subs/3)` from subs only (mains display-only background context if needed — never in checkbox pool, never in `scenario_concept_ids`, never counted). L4 allows sub-sub + sub-main edges; Finish checks subs >=1. L5 probes new links only; old main-main stay bright excluded (only new Phase-2 links dim at L5 entry per §5).
- Restricted modal: mains dimmed, no new mains, subs add/rename allowed. Confirm merges subs into workspace. Guard (locked, blocking DONE gate): Phase 1 Confirm blocked unless ≥1 main selected (message: "Select at least 1 main heading to continue"; prevents Phase-1 `ceil(0/3)=0` / vacuous Finish / `bright/0`, mirroring Phase-2 0-sub block). Phase 2 Confirm blocked unless ≥1 sub selected (message: "Select at least 1 sub-heading to continue"); exactly 1 sub shows recommendation "≥2 recommended for Apply scenarios" but allows (single-concept exception path per §3). Block prevents zero-division paths (`ceil(0/3)=0`, vacuous L4 Finish, L5 `bright/0`). Phase-2 max-3 gate (locked): each new edge must keep the sub endpoint's total degree (all incident, old+new) ≤3 — block otherwise; the main endpoint is soft-exempt (new sub–main edge allowed even if the main exceeds 3, with notice, to preserve Phase-1 bright state; no hard cap on mains for FYP scope). Reviewer checks the sub side only.
- Phase-1-added subs lifecycle (locked): subs added under mains in Phase 1 Step 2 persist hidden with `source=user_added` (not counted in Phase-1 L1-2/L3/L4/L5 math, not shown in Phase-1 workspace); pre-selected in Phase-2 restricted modal for Confirm. Never discard (would lose user work); carry changes Phase-2 `ceil(subs/3)` / Finish / N counts by inclusion.

## 8. LLM interfaces (model-agnostic, to stub now)
```python
parse_pdf(file) -> {markdown: str, figures: list[{diagram_id: str, page: int, image_path?: str, caption?: str}]}  # LlamaParse stub per §0 (agentic tier, images_to_save screenshot, expand text/markdown/items/images_content_metadata); figures feed extract_concepts for Q4 linking
extract_concepts(markdown, figures: list[{diagram_id: str, page: int, image_path?: str, caption?: str}]) -> ConceptsJSON  # §1 shape; figures carry LlamaParse screenshot/meta per Q4, extractor links them to concepts via diagram_refs/diagram_description; /static/diagrams/{diagram_id}.png per §0
evaluate_paraphrase(session_id, concept_id, paraphrase) -> {passed: bool, accuracy: str, originality: str, feedback: str, hint: str}  # server resolves explanation_text/type/pages/diagram_description from session store by id; no raw client text
generate_scenario(chunk_ids: list[str] 1-3, context_markdown) -> {scenario_id, text, concept_ids: list[str]}  # app owns partition: passes exact chunk; LLM verbalizes text only for those ids and returns them unchanged. 1 allowed only when total n==1 per §3 remainder exception; else 2-3. context_markdown may carry mains as background only — never chunked/pooled (see §3).
evaluate_scenario(session_id, scenario_id, selections: [{concept_id, justification}]) -> {results: [{concept_id, passed: bool, feedback: str, hint: str}], missed_ids: list[str], scenario_cleared: bool}  # results = selected ids only (one entry per submitted selection); missed_ids = required-but-unselected ids; server resolves scenario text + concept explanations server-side by id; cleared = missed empty AND all passed (strict all-or-nothing, §3 tier 4). Blue-involved concepts resolve user text as ground with "user-defined — plausibility check, not doc-cited" feedback.
probe_link(session_id, link_id, why_answer, fail_answer) -> {why_passed: bool, why_feedback: str, why_hint: str, fail_passed: bool, fail_feedback: str, fail_hint: str}  # server resolves link edge + concept explanations by id
```
All prompts must enforce doc-scope grounding + page awareness. Server-side implementations MUST first ownership-check `sessions.user_id == requesting user_id`, then resolve both concepts' explanation_text/type/pages/diagram_description from the session store by owned `(session_id, concept_id)` for doc-scope grounding; `evaluate_scenario` MUST likewise resolve scenario text + concept explanations server-side by owned `(session_id, scenario_id)`; `probe_link` by owned `(session_id, link_id)`. Raw client-supplied explanation/scenario text MUST NOT be trusted (multi-session isolation per §0, doc-scope grounding). Stubs simulate with seed JSON but MUST keep the session/id-keyed signatures. UI builds against stubs/seed JSON; swap model later with no UI change.

## 9. History review (Q13 locked)
- Trail schema (locked, frozen per Step 0): `trail(session_id, concept_id?, link_id?, scenario_id?, stage, payload JSON, created)`; one row per attempt/event, never prune until session end. Reviewable mid-phase. L1-2 payload: paraphrase + accuracy/originality/feedback (extracted) — blue rows instead store user explanation + warning-ack, no accuracy/originality (see M18). L3 payload (locked granularity): one row per `(scenario_id, concept_id)` per attempt — each submitted selection writes its row `{justification, passed, feedback, hint, omitted:false}`, and each required-but-unselected id writes an omission row `{justification:"", passed:false, feedback names missed concept, hint, omitted:true}` (`results` selected-only, `missed_ids` unselected-required per §8). L5 payload: Why/When answers + per-side feedback. Reviewer must verify writes per slice (see TODO Integration).
- Store full trail per `concept_id` + per `link_id`, never prune until session end. Reviewable mid-phase.
- L1-2: `concept name + explanation (text/type/source/pages) + diagram_description/diagram_refs when present + user paraphrase + accuracy/originality/feedback` (extracted). Blue rows: `concept name + user explanation + warning-ack + saved flag` — no accuracy/originality (bypass, no LLM).
- L3: `scenarios involved (selector if multiple) + related concepts + user justifications + feedback`. Concept-panel query rule (locked): filter `trail` by `(session_id, concept_id, stage=L3)`, group rows by `scenario_id` for the scenario selector (one row per scenario×concept per §9 makes this query work).
- L4: omitted from dropdown (graph-visible only).
- L5: `Why/When answers + per-side feedback` per link. Concept panel L5 section lists incident link_ids (links touching this concept) with a link-selector dropdown when >1; each entry shows Why/When answers + per-side feedback. L4 omitted from dropdown everywhere (graph-visible only). Phase 2 mains reviewable for Stages 1,2,3,5 (skip 4). Subs follow Phase 1 rules mid-loop. Mains completed Phase 1 (Order Step 8 "through Phase 2" corrected — Locks wins).
- Dropdown at bottom-right of sliding panel (single stage dropdown; nested selectors inside: stage → scenario selector for L3 rows, stage → incident-link selector for L5 rows — never two competing dropdowns). Defaults: Stage3 shows 1&2, Stage4 shows 3 (+graph for 4), Stage5 shows history (+graph for 4). All stages reviewable mid-phase per §9 (L1-2 fields, L3 selector, L5 incident-link selector).

## 10. Build order (for later, not started)
0. Skeleton SOLO (main agent only): models (with `user_id`/`session_id` scoping) + SQLite store + profile/session picker + graph/panel/modal shells + state machine + stubs for §8 + seed JSON. Freeze before fanning out.
1-6. Chronological vertical slices: Steps1-2 -> L1-2 -> L3 -> L4 -> L5 -> Phase2+History. Each slice done = UI + stub logic + progress/history writes + demo on seed data.
- Sub-agents: allowed only after Step 0 frozen. Fan out L3 (§3) / L4 (§4) / L5 (§5) in parallel to sub-agents with Locks section as spec + shared `concept_id`/`link_id`/`trail` + §8 I/O. Main agent keeps skeleton + integration. Reviewer sub-agent checks each slice against Locks (counts, lock-passed, Finish gate, history writes).
