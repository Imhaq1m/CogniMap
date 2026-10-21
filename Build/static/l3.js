// CogniMap Step 3 — L3 Apply (Locks §3 amended: app partitions 2+2, omission tier,
// lock-passed retry same scenario, strict all-or-nothing, progress on cleared only).
(function () {
  let SID = '', UID = 0, current = null, titles = {}, _pendingL4 = false, _pendingNext = false;

  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function q() { return '?user_id=' + encodeURIComponent(UID); }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const t = await r.text();
    let j = {};
    try { j = JSON.parse(t); } catch (e) { j = { detail: t }; }
    if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
    return j;
  }

  function paint(p) {
    if (!p) return;
    el('l3progress').innerHTML = `Level 3 [Apply] ${p.pct}% (${p.cleared}/${p.total})` +
      (p.complete ? ` <button class="btn sm green-inline" id="goL4">Continue to Level 4</button>` : '');
    const b = el('goL4');
    if (b) b.onclick = () => el('l4modal').classList.add('open');
  }

  async function refresh() {
    try {
      const st = await api('/api/sessions/' + SID + '/state' + q());
      el('genBtn').disabled = (st.session.stage !== 'L3');
      paint(await api('/api/sessions/' + SID + '/l3/status' + q()));
      // Problem 2: only current stage card visible.
      try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar(st.session && st.session.stage); } catch (e) { /* sidebar optional */ }
    } catch (e) { /* pre-confirm session */ }
  }

  function render() {
    el('scnText').innerHTML = `<b>Scenario</b><p>${esc(current.text)}</p>`;
    // Locks §3: pool = all visible-counted, required hidden server-side.
    // The server never sends scenario_concept_ids, so there is nothing here
    // to reveal — render the pool unchecked; tiers 1 (wrong) and 4
    // (omission) stay live.
    const pool = current.pool || [];
    el('scnConcepts').innerHTML = `<b>Concepts</b>` + pool.map(cid => {
      const locked = (current.locked_passed || []).includes(cid);
      return `<div class="scn-row${locked ? ' locked-green' : ''}" data-cid="${esc(cid)}">
        <label><input type="checkbox" data-act="check" ${locked ? 'checked disabled' : ''}>
        ${esc(titles[cid] || cid)}${locked ? ' ✔' : ''}</label>
        <textarea data-act="just" rows="2" placeholder="Justification — why does it apply?" ${locked ? 'disabled' : ''}>${locked ? 'Locked green from earlier pass.' : ''}</textarea>
        <div data-act="res"></div>
      </div>`;
    }).join('');
    el('scnMsg').innerHTML = '';
  }

  async function generate() {
    try {
      const j = await api('/api/sessions/' + SID + '/l3/generate' + q(), { method: 'POST' });
      paint(j.progress);
      if (j.complete) { el('l4modal').classList.add('open'); refresh(); return; }
      current = j;
      const concepts = await api('/api/sessions/' + SID + '/concepts' + q());
      titles = {};
      concepts.forEach(c => { titles[c.id] = c.title; });
      render();
      el('scnmodal').classList.add('open');
    } catch (err) {
      el('l3progress').innerHTML = 'Level 3 [Apply] — ' + esc(err.message);
    }
  }

  // UI issue 1: L3 → L4 handoff (Complete banner → close panel → sidebar swap),
  // deferred until the user closes the scenario panel after l4_ready so the
  // final feedback can be reviewed first.
  function finishToL4() {
    _pendingL4 = false;
    el('l4modal').classList.add('open'); refresh();
    // Problem 2: stage advanced L3 → L4, show only L4 card now.
    try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('L4'); } catch (e) { /* sidebar optional */ }
  }

  async function submit() {
    // Each attempt recomputes the pending handoffs from its own response. If
    // this submit errors out (network/400), armed flags are dropped — the user
    // stays put and re-drives manually; close never force-advances on stale
    // state.
    _pendingL4 = false; _pendingNext = false;
    const rows = [...document.querySelectorAll('#scnConcepts .scn-row')];
    const selections = rows.filter(r => {
      const box = r.querySelector('[data-act=check]');
      return box.checked && !box.disabled;
    }).map(r => ({
      concept_id: r.getAttribute('data-cid'),
      justification: r.querySelector('[data-act=just]').value,
    }));
    try {
      const j = await api('/api/sessions/' + SID + '/l3/submit' + q(), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: current.scenario_id || current.id, selections }),
      });
      const byId = {};
      j.results.forEach(r => { byId[r.concept_id] = r; });
      rows.forEach(r => {
        const cid = r.getAttribute('data-cid');
        const res = byId[cid];
        const box = r.querySelector('[data-act=res]');
        if (!res) return;
        box.innerHTML = res.passed
          ? `<div class="fb-ok">Result: correct ✔${res.locked ? ' (locked)' : ''}</div>`
          : `<div class="fb-bad">Result: needs work</div><div>${esc(res.feedback)}</div>` +
            (res.hint ? `<div class="fb-hint">Hint: ${esc(res.hint)}</div>` : '');
      });
      let msg = '';
      if (j.missed_ids && j.missed_ids.length) {
        const names = j.missed_ids.map(cid => `${esc(titles[cid] || cid)} (${esc(cid)})`);
        msg += `<div class="warn">Required but not selected: ${names.join(', ')} — scenario not cleared.</div>`;
      }
      if (j.scenario_cleared) {
        current.locked_passed = j.locked_passed;
        renderResultsOnly(j);
        // UI issue 1 (+ between-scenarios extension): the panel never closes
        // or replaces itself — on any clear the user reviews the feedback,
        // then closes the panel; the close action itself drives what happens
        // next (finishToL4 on the final clear, generate() mid-run).
        msg += j.l4_ready
          ? `<div class="fb-ok">Scenario cleared (${j.progress.cleared}/${j.progress.total}) — Level 3 complete! 🎉</div>` +
            `<div>Review the feedback above, then close this panel to continue to Level 4.</div>`
          : `<div class="fb-ok">Scenario cleared (${j.progress.cleared}/${j.progress.total}).</div>` +
            `<div>Review the feedback above, then close this panel for the next scenario.</div>`;
      } else {
        current.locked_passed = j.locked_passed; // failed ones stay editable, passed lock green
        renderResultsOnly(j);
      }
      el('scnMsg').innerHTML = msg;
      paint(j.progress);
      // m4 (Locks §3 retry SAME scenario) + between-scenarios extension: no
      // timers anywhere. A failed partial keeps the user on the same scenario
      // (generate re-serves it — active_scenario, main.py). A clear just arms
      // a deferred handoff that the scnX close handler fires; never
      // auto-fire when Level 4 is ready. Demo unchanged (ceil(n/3)).
      if (j.l4_ready) {
        _pendingL4 = true;
      }
      else if (j.scenario_cleared) {
        _pendingNext = true;
      }
    } catch (err) {
      el('scnMsg').innerHTML = `<div class="fb-bad">${esc(err.message)}</div>`;
    }
  }

  // Re-render rows so newly-locked concepts turn green/disabled without losing typed text.
  function renderResultsOnly(j) {
    const byId = {};
    j.results.forEach(r => { byId[r.concept_id] = r; });
    document.querySelectorAll('#scnConcepts .scn-row').forEach(r => {
      const cid = r.getAttribute('data-cid');
      if ((j.locked_passed || []).includes(cid)) {
        r.classList.add('locked-green');
        const box = r.querySelector('[data-act=check]');
        box.checked = true; box.disabled = true;
        const t = r.querySelector('[data-act=just]');
        t.disabled = true;
        if (!t.value) t.value = 'Locked green from earlier pass.';
        const label = r.querySelector('label');
        if (label && !label.textContent.includes('✔')) label.innerHTML += ' ✔';
      }
    });
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    el('genBtn').onclick = generate;
    // m4 + UI issue 1 (+ between-scenarios extension): closing the panel is
    // the user-controlled transition, not a timer — after the final clear it
    // fires the Level 4 handoff; after a mid-run clear it generates/opens the
    // next scenario; otherwise it is just a plain close.
    el('scnX').onclick = () => {
      el('scnmodal').classList.remove('open');
      if (_pendingL4) finishToL4();
      else if (_pendingNext) { _pendingNext = false; generate(); }
    };
    el('scnSubmit').onclick = submit;
    const t = el('toL4Btn');
    if (t) t.onclick = () => el('l4modal').classList.remove('open');
    refresh();
  }

  window.CogniMapL3 = { init, refresh };
})();
