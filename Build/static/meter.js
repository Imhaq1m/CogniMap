// CogniMap stage progress meter (UI_ISSUES.txt #1) — BAR meter.
// ONE horizontal meter lives at the BOTTOM of the left panel (sidebar):
// the percentage NUMBER renders in the MIDDLE of the bar, the bar fills
// left→right with the CURRENT stage's --stage-accent, and the fraction
// (e.g. 6/11) is a small caption under the bar.
// Stage gating: the meter is visible only on the percentage stages
// (L1-2 / L3 / L5). Each stage module pushes its latest numbers via
// paint(stageKey, {pct, sub}); sync() — hooked from the refreshSidebar
// chokepoint (graph.js) — shows/hides it on every stage change and swaps
// the accent colour, so the meter always mirrors the CURRENT stage only.
// Server twin: _meter_html/_meter_for_stage in main.py render the same
// markup (incl. real initial numbers) for the stage the page opens on —
// keep markup + numbers in sync across the two files.
(function () {
  var ACCENTS = {
    'L1-2': 'var(--stage-l12)',
    'L3': 'var(--stage-l3)',
    'L5': 'var(--stage-l5)'
  };
  var data = {};        // stageKey -> {pct, sub} latest paint from that module
  var curStage = null;  // current session stage, set by sync()

  function clamp(n) {
    n = Number(n);
    if (!isFinite(n)) n = 0;
    return Math.max(0, Math.min(100, n));
  }

  function numHtml(p) { return String(p) + '<i>%</i>'; }

  function ensureBar(m) {
    if (m.querySelector('.cm-bar')) return;
    m.innerHTML = '<div class="cm-bar"><div class="cm-fill" style="width:0%"></div></div>';
  }

  function render(stage) {
    var m = document.getElementById('stageMeter');
    if (!m) return;
    var p = data[stage];
    if (!ACCENTS[stage]) { m.classList.add('hidden'); return; }
    if (!p) {
      // No module data yet (first-load race: refreshSidebar can fire before
      // this stage's first paint). Keep the SERVER-rendered numbers when the
      // page opened on this stage (data-stage attr set by _meter_for_stage);
      // hide on any other stage so the wrong stage's meter never lingers.
      var srv = m.getAttribute('data-stage');
      if (srv === stage && !m.classList.contains('hidden')) return;
      m.classList.add('hidden');
      return;
    }
    var pct = clamp(p.pct);
    try { m.style.setProperty('--stage-accent', ACCENTS[stage]); } catch (e) { /* ignore */ }
    m.setAttribute('data-stage', stage);
    m.classList.remove('hidden');
    m.setAttribute('aria-label', 'Progress ' + pct + '% of 100%');
    // In-place update (structure built once) so the width transition sweeps.
    ensureBar(m);
    var f = m.querySelector('.cm-fill');
    var num = m.querySelector('.cm-num');
    if (!num) {
      num = document.createElement('div');
      num.className = 'cm-num';
      m.querySelector('.cm-bar').appendChild(num);
    }
    f.style.width = pct + '%';
    num.innerHTML = numHtml(pct);
    var subEl = m.querySelector('.cm-sub');
    if (p.sub) {
      if (subEl) subEl.textContent = p.sub;
      else {
        subEl = document.createElement('div');
        subEl.className = 'cm-sub';
        subEl.textContent = p.sub;
        m.appendChild(subEl);
      }
    } else if (subEl) {
      subEl.remove();
    }
  }

  // paint('L3', {pct: 40, sub: '2/5'}) — record + repaint when it IS the
  // current stage (other stages' paints just refresh the stored data).
  function paint(stageKey, payload) {
    if (!stageKey) return;
    data[stageKey] = payload || {};
    if (curStage === stageKey) render(stageKey);
  }

  // sync(stage) — the stage change hook (mirror of CogniMapStageFlow.refresh).
  function sync(stage) {
    curStage = stage || null;
    render(curStage);
  }

  window.CogniMapMeter = { paint: paint, sync: sync };
})();
