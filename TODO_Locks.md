# CogniMap — Build TODO (tracks Steps_Locks.md §10)
Check off only when demo-on-seed passes. Do not start next slice until current is checked.

> FROZEN (reviewer verified 2026-09-29): `pytest Build/tests` green (30 passed)
> on seed: ownership 404 (`/u/A` vs session of B on HTML + every
> `/api/sessions/{sid}/*` with `?user_id=`), per-file vs last-file reset,
> `ceil(n/3)` + 2+2 runs, wrong-pick (tier 1) + omission (tier 4) cases,
> lock-passed retry, session/id-keyed §8 stubs. Models/routes frozen
> (models.py/store.py schema + main.py routes/state-machine). No schema change after.

## Step 0 — Skeleton SOLO (main agent, freeze before fan-out)
- [x] Models with `session_id` scoping on domain tables (`concept, link, scenario, trail` carry `session_id` only; `user_id` via `sessions` join) + ownership check (`sessions.user_id == route user`) per Locks §0/§8
- [x] SQLite store + `users`/`sessions`/`session_files` tables + owned-session-scoped queries (+ session lifecycle create/list/delete cascade per Locks §0/§6)
- [x] Profile/session picker + routes `/u/{user_id}` + `/u/{user_id}/s/{session_id}` (+ ownership 404 test)
- [x] Workspace graph / sliding panel / modal / progress shells (stubs, no logic)
- [x] Stubs for LLM/parser interfaces per Locks §8 (`parse_pdf(file) -> {markdown, figures[]}`, `extract_concepts(markdown, figures) -> ConceptsJSON`, `evaluate_paraphrase(session_id, concept_id, ...)`, `generate_scenario(chunk_ids 1-3, context_markdown)`, `evaluate_scenario(session_id, scenario_id, ...)`, `probe_link(session_id, link_id, ...)`) + seed JSON demo file (seed round-trips through `parse_pdf` + `extract_concepts` stubs)
- [x] DONE = picker → empty workspace loads on seed, no errors; ownership check test (`/u/A/s/{session_of_B}` blocked); last-file reset test. FREEZE models/routes.

## Step 1 — Steps 1-2 modal (chronological)
- [x] Upload via LlamaParse stub `parse_pdf(file) -> {markdown, figures[]}` + file list (`session_files` per Locks §0) + remove-file reset cascade (`clear_session_data`: last-file deletes scoped concepts/links/scenarios/trail + clears `sessions.file`; files remain → keep data)
- [x] Extracted Concepts modal: mains/subs tree, checkboxes, rename, add lines, delete pre-Confirm, blue `user_added` styling, `source` flag
- [x] Confirm lock warning copy (Locks §6.1, incl. ≥2–3 mains recommended) + Phase-1 ≥1-main guard + merge to workspace (mains only Phase 1 display; Phase-1-added subs persist `user_added`, never discard, hidden from Phase-1 math via kind filter — explicit hidden-flag + Phase-2 restricted-modal preselect path deferred to Step 6 per Locks §7, not claimed here)
- [x] DONE = seed populates modal via `parse_pdf` + `extract_concepts` stubs, Confirm merges mains, 0-main Confirm blocked, history store initialized.

## Step 2 — L1-2 Remember/Understand
- [x] Drawer: title read-only, explanation box [type/pages/diagram], paraphrase box, Verify
- [x] Blue bypass (warning + save non-empty counts, no LLM)
- [x] Eval stub `{passed, accuracy, originality, feedback, hint}` lenient + progress `%` on mains (subs in Phase 2)
- [x] History trail writes L1-2 per Locks §9 + mid-phase reviewable
- [x] DONE = 100% on seed triggers L3 transition modal.

## Step 3 — L3 Apply (sub-agentable after Step 0; Locks §3+§7 win over Details/Order pool wording)
- [x] Generate Scenario (app partitions uncovered → chunks of 3, 2+2 remainder fix, n=1 exception; LLM verbalizes only via `generate_scenario(chunk_ids, context_markdown)` — context may carry mains as background, never chunked/pooled; no repeats; `ceil(n/3)` total)
- [x] Split panel (pool = all visible-counted per Locks §3), checkboxes + justifications, Submit, per-concept pass/hint, omission `missed_ids` → no clear, lock-passed retry same scenario
- [x] Progress on cleared scenarios only (`% = cleared/ceil(n/3)`; failed attempts change nothing; strict all-or-nothing: missed empty AND all passed)
- [x] History writes L3 (one row per `(scenario_id, concept_id)` incl. omission rows per Locks §9) + mid-phase reviewable
- [x] DONE = seed clears in `ceil(n/3)` runs, retry locks passed, wrong-pick + omission cases tested on seed (pool = all visible-counted per Locks §3; strict clear = missed empty AND all passed).

## Step 4 — L4 Analyze (sub-agentable after Step 0; Locks §4 wins — Details omits `consists of`)
- [x] Drag-connect + edge panel (8 presets incl. `consists of` + custom verbatim per Locks §4: `1-24 chars, single line, trim, max 3 words, charset [A-Za-z0-9 space hyphen], no newlines/emoji/arrows, block exact preset duplicates case-insensitive`)
- [x] Ordered store (from,to,type) for display/probe; undirected counting, max3 / >=1 gate, no loops, one-edge-per-pair block ("One link per pair — direction stored for probing."); deleted pair may be re-added; n=1 auto-pass per Locks §4
- [x] Mid-line labels, delete-link + re-pick, Finish enable logic, no % bar
- [x] L4-entry warning per Locks §6.2
- [x] DONE = Finish enables only when all counted concepts >=1 on seed (n=1 auto-pass covered).

## Step 5 — L5 Evaluate (sub-agentable after Step 0)
- [x] Entry dimming, frozen graph, fixed N (Phase 1: entry links; Phase 2: new links only), `Level 5 0%`
- [x] L5-entry frozen warning per Locks §6.3
- [x] Probe modal Why/When + Submit, independent eval stub (6-field: per-side feedback+hints), lock-passed per side, brighten on both-green
- [x] Progress `bright/N` + history writes per link + mid-phase reviewable
- [x] DONE = 100% on seed triggers Phase 2 modal.

## Step 6 — Phase 2 + History (Locks §7 wins — same stages, filtered math, not exact-same pool)
- [x] Restricted modal (mains dimmed, subs-only adds, Phase-1-added subs persist hidden + pre-selected per Locks §7, ≥1 sub required / ≥2 recommended guard), Confirm merges subs, mains keep links/bright; new-edge gate keeps sub total degree ≤3, mains soft-exempt per Locks §7
- [x] Mixed workspace filtered progress (math on subs + new links only per Locks §7; mains display-only never in L3 pool/scenario_ids; only new links dim at L5 entry per Locks §5)
- [x] Sub loop L1-5 reuse + history dropdown (bottom-right, defaults per Locks §9, L4 graph-only omit, no-prune)
- [x] Final interconnected map view intact
- [x] DONE = full seed run Phase1→Phase2→100% with dropdown reviewable mid-phase; 0-sub Confirm blocked (blocking DONE gate, do not relax — prevents L1-2 0/0, L3 0 scenarios, L5 N=0 per Locks §7).

## Integration / Reviewer
- [x] Reviewer sub-agent: each slice vs Locks (counts, lock-passed, Finish gate incl. n=1 auto-pass, second-drag-block regardless of type, history writes per locked `trail(session_id, concept_id?, link_id?, scenario_id?, stage, payload JSON, created)` schema §9 — L3 one row per `(scenario, concept)` incl. omissions; L3 strict 4-tier omission case + `results` selected-only / `missed_ids` unselected-required per §8; L3 `% = cleared/ceil(n/3)` no partial credit; blue rows plausibility-check feedback)
- [x] Seed demo end-to-end without LLM keys / LlamaParse keys
