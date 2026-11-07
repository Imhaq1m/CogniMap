# CogniMap Motion System (MOTION.md)

Source of truth for the "soft vibes" motion + skin pass. Grilled plan v1
(2026-10-28), confirmed by the user. Progress is tracked in the status
table at the bottom; update it per slice, mirroring the UI_ISSUES.txt
RESOLVED pattern. UI_ISSUES.txt itself stays untouched by this work.

## Motion personality

**Smooth & calm** — gentle ease-out, fade + rise, no bounce, no jiggle.
Exits are slightly quicker than entrances. Nothing pops in or vanishes.

**Precision boundary** — cursor-following elements get ZERO easing:

- dragged node position (`cx`/`cy` attributes, set per-frame by the L4
  rAF drag engine — CSS transitions cannot fight this, positions are
  attribute-driven, not transform-driven)
- the right-drag link ghost line (attribute-driven `x1/y1/x2/y2`)
- the true-cursor position used for L4 link drops (exact by design)

Everything around them (hover lift, drop-target glow, labels, dimming)
uses the soft tokens below. The drag engine's own smoothing constants
(45ms exponential settle, `tweenNodeTo`/`flipGlide` durations in l4.js)
are precision machinery, not CSS tokens — intentionally untouched except
where a duration was retuned for calm (noted per slice).

## Tokens (style.css `:root`)

| Token | Value | Used for |
|---|---|---|
| `--dur-fast` | 160ms | hover, press, glow, border/focus changes |
| `--dur-base` | 280ms | modals, drawer, cards, labels, feedback |
| `--dur-slow` | 420ms | signature moments (level-complete reveals) |
| `--dur-exit` | 200ms | all exits (quicker than entrances) |
| `--ease-soft` | cubic-bezier(.22, 1, .36, 1) | entrances |
| `--ease-exit` | cubic-bezier(.4, 0, .68, 1) | exits |
| `--ring` | `0 0 0 3px rgba(47,111,237,.35)` | focus ring |
| `--shadow-card` | soft 1px/3px | cards |
| `--shadow-float` | layered 10px/40px + 2px/10px | modals & floating popups |

`prefers-reduced-motion: reduce` collapses every duration token to 1ms
(single `:root` override), so token-driven transitions go instant without
duplicating rules. Entrance *animations* additionally sit inside
`@media (prefers-reduced-motion: no-preference)` blocks (house pattern).

## Machinery — and one documented deviation

**Deviated from the grilled plan: no `motion.js`.** The plan specified a
JS enter/exit helper, but implementing revealed every overlay toggles a
class (`.open` or `.hidden`) on an element that is permanently in the
DOM. Switching those overlays from `display:none` toggling to
`opacity + visibility + transform` transitions makes enter/exit pure CSS:

- **Zero call-site churn** — all ~37 `classList.add/remove('open')` sites
  across 6 modules keep working untouched (that logic is Locks §-heavy;
  not touching it is a safety win).
- **Race-free by construction** — re-toggling mid-transition retargets
  the running transition smoothly; no JS timers to cancel.
- Exits work (the old `display:none` pattern made every close a vanish).

**Adapted grep-audit** (was "no display:none→flex open without helper"):
there must be **no `display:none`↔`.open{display:flex}` pairs left** for
any overlay — overlays animate via the visibility/opacity system. Grep
for `display:none` next to a modal id: only structural `.hidden` uses
(sidebar cards, `#state`, tree pieces) may remain, and those are
intentionally instant (documented below).

## Intentionally NOT animated

- Sidebar stage-card show/hide (`.hidden` on cards) — structural, would
  smear the stage-swap moment.
- `#state` debug panel, history dropdown `<select>` visibility.
- The modal concept tree rows (`.tree-row`) — re-renders on add/rename
  would flicker-animate while typing flow is delicate; calm > busy.
- `.warn` / `.lock` boxes that are statically visible on page load
  (l4warn/l5warn); dynamic ones animate via their container rules.
- Drag engine internals (see precision boundary).

## Slice plan + status

| Slice | Scope | Status |
|---|---|---|
| 0 | Tokens + overlay system + skin in style.css | DONE (2026-10-28) |
| 1 | All `.open` overlays animate in AND out (10 modals) | DONE (2026-10-28) |
| 2 | Drawer `#panel` soft slide + shadow | DONE (2026-10-28) |
| 3 | Buttons/inputs: hover glow, press scale, focus rings | DONE (2026-10-28) |
| 4 | Feedback + lists entrances (drawer fb, scn results, hist cards, rows) | DONE (2026-10-28) |
| 5 | Graph niceties: soft hover lift, glow pulse drop target, dim/label transitions | DONE (2026-10-28) |
| 6 | Signature moments: slow level-complete reveals + 40ms row cascade | DONE (2026-10-28) |
| 7 | Stage flow (UI_ISSUES #2): traveler glide, breathing current ring, glow crossfades | DONE (2026-10-28) |

### Slice notes

- **Slice 1**: overlays = `#modal #l3modal #l4modal #l5modal #probemodal
  #phase2modal #donemodal #scnmodal #l12guide #addHeadingModal` (backdrop
  fade + box rise). `#edgePanel` + `#edgeSelectedPanel` are
  `.hidden`-toggled and get the same treatment via `:not(.hidden)` states
  (base `.hidden` is overridden to `display:block` so transitions can run;
  `visibility:hidden` keeps them non-interactive).
- **Slice 4**: entrances replay on each render (innerHTML swap recreates
  nodes → CSS animation restarts) — that replay IS the feedback cue.
  **Planned "progress bar width transitions" turned out N/A**: all three
  progress cards are text-only (`textContent`/`innerHTML`), no bars exist.
- **Slice 5**: `cogPulse` scale-pop replaced by `cogGlow` — a gentle
  1.6s stroke-opacity pulse under the existing static glow ring.
  gnode hover/drag lift retuned 120ms → `--dur-base`. The `cogDash`
  marching-ants ghost keeps its own `.6s` cadence (cursor-following
  exempt; decorative cadence, not a duration token).
- **Slice 6**: transition modals (l3/l4/l5/done/l12guide) reveal at
  `--dur-slow` with an 18px rise; `.scn-row`s cascade left-to-right via a
  `--i` index set in l3.js `render()` (40ms steps, `backwards` fill).
- **l4.js retunes**: repaint glide 200→280ms, drop-revert glide 150→220ms
  (calm, still clearly "settling", not floaty).

### Slice 7 notes (stage flow + glow)

- **Traveler** (`.stp-traveler`): glides previous → current marker on
  `--dur-slow` + `--ease-soft`; `left/top/background/box-shadow`
  transition together, so the colour retarget rides the same glide.
  First paint / same-stage re-syncs use `.stp-noanim` (transition:none
  for one frame) — it lands instead of sliding from nowhere. Confirming
  sub-headings sends it BACK to Level 1–2 (grilled "honest rewind").
- **Breathing current ring**: `cogStageBreath` 1.6s cycle — ring radius
  + tint breathe on the current dot; boxed in
  `@media (prefers-reduced-motion: no-preference)` (house pattern), the
  static 3px ring stays for reduced motion.
- **Glow crossfades**: stage change swaps the inline root `--glow` var;
  `#graph::before` wash + `#panel::before` veil transition their
  background-color on `--dur-slow` (a var swap retargets the running
  transition — no fade layer needed), panel halo in the open-shadow on
  box-shadow.
- **Token-driven only**: all of it uses `--dur-fast/--dur-slow` +
  `--ease-soft`; `prefers-reduced-motion: reduce` collapses durations to
  1ms via the single `:root` override — no per-rule work needed.

## Definition of done

- [x] No `display:none`↔`.open{display:flex}` overlay pairs remain.
- [x] No hardcoded durations in style.css outside the token block
      (exceptions: `cogDash .6s`, documented above).
- [x] Every overlay animates in AND out.
- [x] `prefers-reduced-motion: reduce` collapses all of it.
- [x] `node --check` clean on all touched JS.
- [x] Backend test suite stays green (133 passed, 2026-10-28 — suite has
      grown past the 44 noted in UI_ISSUES.txt; CSS/JS-only change).
- [ ] Per-slice click-through feel pass by the user — **pending; the only
      open item.** Everything else is done; go click through a session
      (drawer, each modal, L3 rows cascade, L4 hover/drag, L5 dim) and
      flag anything that feels too slow/fast — token values are the
      single tuning surface.

## Verification

- Syntax: `node --check Build/static/{style-modified js files}` (all JS).
- Tests: `Build/.venv` pytest suite (`Build/tests`, 44 passing at time of
  this change — CSS/JS-only change, no backend code touched).
- Feel: user click-through per slice (subjective by nature — the slices
  are small so any "too much/too little" lands on one reviewable change).
