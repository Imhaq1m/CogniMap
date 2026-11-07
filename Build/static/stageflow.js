// CogniMap StageFlow — top-bar stage progress + workspace glow (UI_ISSUES.txt #2).
// Server renders the initial state for _stage_flow() (no flash); this module
// re-syncs to SERVER truth after every stage change (hooked from
// refreshSidebar — the chokepoint every transition funnels through — so
// predicted-stage callers self-correct within one /state fetch) and drives:
//   • marker state classes: completed (solid fill) / current (glow ring) /
//     future (dashed hollow) — grilling Q10
//   • the traveler dot gliding from the previous marker to the current one
//     (--dur-slow glide; "honest rewind" travels BACK on Phase2 confirm — Q11)
//   • the "Cycle 2" chip via the #stageFlow data-phase attribute (pure CSS — Q12)
//   • the root --glow var = current stage colour; the canvas-region + drawer
//     ambient glow crossfades in CSS (Q5-revised/Q6).
(function () {
  let SID = '', UID = 0, inited = false, curStage = '', timer = null;

  function el(id) { return document.getElementById(id); }
  function q() { return '?user_id=' + encodeURIComponent(UID); }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const t = await r.text();
    let j = {};
    try { j = JSON.parse(t); } catch (e) { j = { detail: t }; }
    if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
    return j;
  }

  // Session stage order (models.py enum / flow doc); matches server _STAGE_FLOW.
  const ORDER = ['steps1-2', 'L1-2', 'L3', 'L4', 'L5', 'Phase2', 'done'];
  // Stage -> accent token map (--stage-* family; done shares the Phase2
  // colour exactly like #donemodal's border-top does).
  const GLOWS = {
    'steps1-2': 'var(--stage-steps)',
    'L1-2': 'var(--stage-l12)',
    'L3': 'var(--stage-l3)',
    'L4': 'var(--stage-l4)',
    'L5': 'var(--stage-l5)',
    'Phase2': 'var(--stage-p2)',
    'done': 'var(--stage-p2)'
  };

  function paint(stage, phase) {
    const flow = el('stageFlow');
    if (!flow) return;
    const ci = ORDER.indexOf(stage || 'steps1-2');
    const idx = Math.max(0, ci);
    const p2 = phase === 'phase2';
    flow.setAttribute('data-phase', p2 ? 'phase2' : 'phase1');
    const steps = flow.querySelectorAll('.stp-step');
    steps.forEach((step, i) => {
      // Visited inference mirrors server _stage_flow + grilling Q11: the
      // phase-2 replay keeps every mains-cycle stage + Phase2 filled.
      const visited = p2 ? (i <= ORDER.indexOf('Phase2')) : (i < idx);
      step.className = i === idx ? 'stp-step stp-now'
        : (visited ? 'stp-step stp-done' : 'stp-step');
    });
    const track = flow.querySelector('.stp-track');
    const step = steps[idx];
    const traveler = flow.querySelector('.stp-traveler');
    const dot = step ? step.querySelector('.stp-dot') : null;
    if (track && traveler && dot) {
      // Rect math (dot may live inside stp-step, whose offsetParent differs).
      const trect = track.getBoundingClientRect();
      const drect = dot.getBoundingClientRect();
      const x = drect.left + drect.width / 2 - trect.left;
      const y = drect.top + drect.height / 2 - trect.top;
      const color = GLOWS[stage] || 'var(--accent)';
      if (!inited || curStage === stage) {
        // First paint / same-stage re-sync: land, never glide from nowhere.
        traveler.classList.add('stp-noanim');
      }
      traveler.classList.add('stp-set');
      traveler.style.left = x + 'px';
      traveler.style.top = y + 'px';
      traveler.style.background = color;
      traveler.style.boxShadow = '0 0 0 4px color-mix(in srgb,' + color + ' 40%, transparent)';
      if (traveler.classList.contains('stp-noanim')) {
        void traveler.offsetWidth; // flush once so the NEXT move glides
        traveler.classList.remove('stp-noanim');
      }
    }
    // Workspace ambient glow: one inline root var, consumed by the canvas
    // #graph::before wash + #panel veil/halo. Changing it crossfades there.
    try {
      document.documentElement.style.setProperty('--glow', GLOWS[stage] || 'transparent');
    } catch (e) { /* glow optional */ }
    curStage = stage || '';
    inited = true;
  }

  async function fetchState() {
    if (!SID) return;
    timer = null;
    try {
      const st = await api('/api/sessions/' + SID + '/state' + q());
      const s = (st && st.session) || {};
      paint(s.stage, s.phase);
    } catch (e) { /* keep the last painted state on transient errors */ }
  }

  function refresh() {
    // Debounce: refreshSidebar can be hit back-to-back by several modules.
    if (timer) clearTimeout(timer);
    timer = setTimeout(fetchState, 120);
  }

  window.CogniMapStageFlow = {
    init: function (sessionId, userId) {
      SID = sessionId; UID = userId;
      fetchState();
    },
    refresh: refresh
  };
})();
