# CogniMap Theme System (THEME.md)

Source of truth for the "learner view" reskin: type/spacing scale, Bloom
stage colours, user-added blue reservation, and the dark/light theme pair.
Grilled session 2026-10-28, confirmed by the user. Progress is tracked in
the status table at the bottom, mirroring the MOTION.md / UI_ISSUES.txt
RESOLVED pattern.

## Grilled decisions (what "easier to see, remember, and focus" means)

1. **Scope: whole app** (`Build/static/style.css` — layout untouched).
2. **Sizing complaint** = no shared scale. Fix: a small type ladder +
   4pt spacing rhythm consumed via tokens.
3. **Memory complaint** = colours had no meaning system. Fix: Bloom stage
   colour rows the flow diagram uses (1 blue→slate, 2 teal-family green,
   3 green, 4 purple, 5 amber, 6 red, 7 teal-green) appear as *stage
   chrome*: a 4px left border on the matching sidebar card, a 3px border
   on its progress well, and a 3px top border on that level's transition
   modal. Same colour = same stage = memory cue.
4. **Blue is RESERVED** for user-added concepts ("blue = mine"). Step 1
   therefore shifts to slate in the stage accents — it does NOT get blue.
5. **9 edge-type colours stay** (grilled "both coexist") but their colour
   is now per-type single tokens (line + label + arrowhead share it) and
   theme-adjusted: dark = brightened canvas tones, light = the original
   saturated hues. The old four-value drift (line vs label vs marker) is
   gone.
6. **Dark/light**: dark stays the default heritage look; light base is
   the flow-doc off-white `#f7f7f2` with WCAG-AA body ink. Toggle (sun/moon)
   beside the brand on every page; `localStorage('cognimap-theme')`
   persists; FIRST visit follows the OS (`prefers-color-scheme: light`);
   manual choice wins afterwards.

## Where the theme lives

- `:root` in style.css = dark defaults; `html[data-theme="light"]` block
  overrides the same token names. Rules consume tokens ONLY, so flipping
  the attribute reskins HTML **and** inline SVG (graph nodes/edges,
  arrowhead markers via inline `fill:var(...)` from l4.js) with zero JS
  re-render.
- `main.py` `_page_head()` injects one inline script on all three pages:
  sets `data-theme` before the stylesheet link (no flash), exposes
  `window.CogniMapTheme.get/set`, and injects the `.theme-toggle` button
  into the page's `.brand` (floats top-right as `.theme-toggle-float`
  where no brand exists). Page templates stay untouched.

## Tokens

| Group | Names |
|---|---|
| Surfaces | `--bg --field --inset --panel --sidebar --card --softcard --modal --chip --row --btn` |
| Ink/lines | `--ink --muted --icon --line --line-soft --line-strong` |
| Accents | `--accent --green --purple --danger --link --ube(soft/ink)` |
| Feedback | `--ok --bad --hint --tint-ink` |
| Helper fills | `--warn-bg/line --lock-bg/line --scn-locked --add-line --canvas --backdrop(strong) --node-bg/line/active --edge-dim --edge-label-ink --edge-select-glow` |
| Edge types ×9 | `--edge-causes --edge-leads-to --edge-depends-on --edge-includes --edge-contrasts --edge-applied-in --edge-influences --edge-consists --edge-custom` + `--edge-default --edge-ghost` |
| Bloom stages | `--stage-steps --stage-l12 --stage-l3 --stage-l4 --stage-l5 --stage-p2` |
| Type scale | `--fs-caption:12 --fs-body:14 --fs-title:16 --fs-header:20 --fs-brand:24 --fs-node:13 (px)` |
| Spacing (4pt) | `--sp-1:4 --sp-2:8 --sp-3:12 --sp-4:16 --sp-5:20 --sp-6:24` |

Graph labels rose 11px → `--fs-node` 13px (grilled readability target);
brand/al h3/h2/btn/inputs/captions ride the ladder. Micro-insets below
4pt (2px icon-btn) are a documented half-step.

## Panel text scale (UI_ISSUES.txt #1, grilled 2026-10-28)

The SAME type-token names are re-scoped inside the two reading panels —
`.sidebar` + `#panel` (style.css, "UI_ISSUES.txt #1" block): caption
12→15, body 14→17, title 16→20 (~20-25% uniform, hierarchy kept; the
panels carry an explicit base font-size so rule-less elements inherit
the bump too). The GLOBAL scale keeps its old values: modals, picker and
user pages stay at the original sizes (scope = "everything textual
inside those panels" only). Panel widths unchanged — larger text wraps
or scrolls internally. The top-bar stage flow uses the global caption
size on purpose (it is chrome, not panel reading text).

## Stage flow + glow (UI_ISSUES.txt #2, grilled 2026-10-28)

- `.topflow` in the workspace replaces the old `Workspace — user …` h2
  (picker/user pages keep theirs). 7 dot markers with short existing
  vocabulary (Materials · Level 1–2 · … · Sub-Headings · Done), each
  wearing its `--stage-*` accent — the SAME colour memory cue as the
  sidebar cards (`done` shares the p2 family like `#donemodal`).
- States: completed = solid accent fill, current = accent fill + glowing
  ring, future = dashed hollow circle + muted name; dots-only under 900px
  (native `title` tooltips). Ordering/labels: `_STAGE_FLOW` in main.py,
  mirrored in stageflow.js `ORDER`.
- Workspace ambient glow: one root `--glow` var (inline, set by
  stageflow.js to the current stage's token). Consumed by `#graph::before`
  (blurred wash behind the canvas region) and `#panel` (`::before` veil +
  open-state halo in the slide shadow). Fallback `transparent` ⇒ zero
  glow pre-init and on pages without the flow; sidebar + top bar stay
  neutral by design (grilled: glow lives in the workspace only).

Deliberately NOT themed: `cognimap-flow.html` (design reference doc, own
stylesheet — accepts the step-1-blue divergence), motion tokens and
reduced-motion behaviour (MOTION.md unaffected), and node/edge geometry.

## Slice plan + status

| Slice | Scope | Status |
|---|---|---|
| 0 | Token architecture (surfaces, ink, accents, stages, types) in style.css | DONE (2026-10-28) |
| 1 | Type + spacing scale applied across components | DONE (2026-10-28) |
| 2 | Stage chrome (sidebar cards, progress wells, transition modals) | DONE (2026-10-28) |
| 3 | Dark/light token pair + WCAG-AA light palette | DONE (2026-10-28) |
| 4 | Theme script + toggle injection in `_page_head()` (main.py) | DONE (2026-10-28) |
| 5 | l4.js edge colours → tokens (CONTS/dots/markers) | DONE (2026-10-28) |
| 6 | Theme.md + UI_ISSUES.txt entry | DONE (2026-10-28) |

## Definition of done

- [x] No component rule in style.css hardcodes a surface/ink/type-colour
      hex (only: white text on saturated fills, `#111` for `--add-line`
      text + edge-label stroke, and intentional id selectors remain).
- [x] Whole app flips on `data-theme` change without JS re-render (SVG
      edges/arrowheads consume the same tokens).
- [x] Toggle present on all three pages; persists; OS on first load.
- [x] Blue reserved: user-added rows/nodes keep the blue family; no
      stage accent uses blue (step 1 = slate).
- [x] `node --check` clean (l4.js), `py_compile` clean (main.py).
- [x] Backend tests green: 133 passed (2026-10-28) — pages not asserted
      by tests, CSS/JS-only + head-script change.
- [ ] User feel pass: click a session in BOTH themes, check stage borders,
      graph labels at 13px, long tree/modal text — flag any discomfort.

## Verification

- Syntax: `node --check Build/static/l4.js`; `python3 -m py_compile Build/app/main.py`.
- Tests: `Build/.venv/bin/python -m pytest Build/tests -q` → 133 passed.
- Theme flip: manually set `document.documentElement.setAttribute('data-theme','light')`
  in a running workspace — everything should follow live.
