// CogniMap Step 5 — L5 Evaluate (Locks §5).
// Entry dim + frozen graph + N fixed + probe modal [A]→[type]→[B] Why/When
// + 6-field eval + lock-passed per side + brighten only both-green + bright/N.
(function () {
  let SID = '', UID = 0, currentLink = null, titles = {}, currentStage = '';

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

  async function refresh() {
    try {
      const concepts = await api('/api/sessions/' + SID + '/concepts' + q());
      titles = {};
      concepts.forEach(c => { titles[c.id] = c.title; });
    } catch (e) { /* empty */ }
    let st = null;
    try { st = await api('/api/sessions/' + SID + '/l5/status' + q()); } catch (e) { return; }
    // Fetch stage BEFORE dim so clickability (Stage-5-only) uses the fresh
    // value, not the previous refresh's stale one.
    try {
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      currentStage = (sst.session && sst.session.stage) || '';
    } catch (e) { /* pre-confirm session */ }
    paint(st);
    dimGraph(st);
    // Problem 2: only current stage card visible (L5 card only in L5).
    try {
      if (window.CogniMapStage && window.CogniMapStage.refreshSidebar)
        window.CogniMapStage.refreshSidebar(currentStage);
    } catch (e) { /* pre-confirm session */ }
  }

  function paint(st) {
    // Locks §5: pre-entry (entered==False) always 0%, never 100% (0/0).
    // Backend returns pct:0/complete:False pre-entry; gate here too so a
    // stale/cached payload can't false-positive Phase2 (TODO Step 5 DONE).
    if (!st.entered) {
      el('l5progress').textContent = `Level 5 [Evaluate] 0% (0/${st.n})`;
      return;
    }
    el('l5progress').textContent = `Level 5 [Evaluate] ${st.pct}% (${st.bright}/${st.n})`;
    if (st.complete && st.n > 0) {
      el('l5progress').textContent += ' · complete';
    } else if (st.complete && st.n === 0) {
      el('l5progress').textContent = 'Level 5 [Evaluate] 100% (0/0 auto-pass)';
    }
  }

  function dimGraph(st) {
    // Frozen graph: dim target links (bright=0), keep others bright.
    // Canvas-only (no link list): probe entry is via canvas edge clicks.
    const targets = new Set(st.target_ids || []);
    // Probe activity lives ONLY in Stage 5: outside L5 (L4 linking, done /
    // Phase2 final map) edges are not clickable for defend — clicking
    // must not open the Stage-5 probe modal.
    const canProbe = (currentStage === 'L5') && !!st.entered;
    // B1 canvas: mirror dim/bright on SVG edges (mid-line labels stay readable).
    document.querySelectorAll('#graph g.gedge[data-link]').forEach(gr => {
      const id = gr.getAttribute('data-link');
      const link = (st.links || []).find(L => L.id === id);
      const dim = targets.has(id) && link && !link.bright;
      gr.classList.toggle('edge-dim', !!dim);
      gr.style.cursor = (canProbe && targets.has(id)) ? 'pointer' : 'default';
      // UI_ISSUES.txt Problem 1: keep the arrowhead color in sync with the
      // line (per-type when bright, grey when dimmed). L4 paints markers
      // correctly on full repaint, but probe-brighten only re-dims here.
      try {
        const ln = gr.querySelector('line');
        if (ln) {
          let marker = 'cogArrow';
          if (!dim) {
            const et = (gr.getAttribute('data-etype') || (link && link.edge_type) || '').toLowerCase().trim();
            if (window.CogniMapEdgeColors && window.CogniMapEdgeColors.edgeMarkerId) {
              marker = window.CogniMapEdgeColors.edgeMarkerId(et, false);
            } else {
              const known = {'causes':'causes','leads to':'leads-to','depends on':'depends-on','includes':'includes','contrasts with':'contrasts-with','applied in':'applied-in','influences':'influences','consists of':'consists-of'};
              marker = known[et] ? 'cogArrow-' + known[et] : 'cogArrow-custom';
            }
          }
          ln.setAttribute('marker-end', 'url(#' + marker + ')');
        }
      } catch (_e) { /* marker sync optional */ }
    });
  }

  async function openProbe(lid, st) {
    // Stage-5-only gate: never open the defend modal outside L5 (L4 linking,
    // done/Phase2 final map). Backend POST already 400s outside L5; the UI
    // must not mislead by opening the modal. Stage is refetched fresh so a
    // stale cached value can't open the modal after advancing to done/Phase2.
    try {
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      currentStage = (sst.session && sst.session.stage) || '';
    } catch (_e) { /* fall through to entered check */ }
    if (currentStage && currentStage !== 'L5') return;
    if (!st) {
      try { st = await api('/api/sessions/' + SID + '/l5/status' + q()); }
      catch (_e) { return; }
    }
    if (!st.entered) return;
    const L = (st.links || []).find(x => x.id === lid);
    if (!L) return;
    if (!(st.target_ids || []).includes(lid)) return; // excluded old links stay bright
    currentLink = L;
    el('probeTitle').textContent = `[${titles[L.a_id] || L.a_id}] → [${L.edge_type}] → [${titles[L.b_id] || L.b_id}]`;
    // Lock-passed per side: prefill + lock passed boxes (rewrite failed only).
    el('probeWhy').value = L.why_answer || '';
    el('probeFail').value = L.fail_answer || '';
    el('probeWhy').disabled = !!L.why_passed;
    el('probeFail').disabled = !!L.fail_passed;
    el('probeWhyFb').innerHTML = L.why_passed ? '<div class="fb-ok">Why locked green ✔</div>' : '';
    el('probeFailFb').innerHTML = L.fail_passed ? '<div class="fb-ok">When locked green ✔</div>' : '';
    el('probeMsg').textContent = '';
    el('probemodal').classList.add('open');
  }

  async function submit() {
    if (!currentLink) return;
    const why = el('probeWhy').value;
    const fail = el('probeFail').value;
    try {
      const j = await api('/api/sessions/' + SID + '/l5/probe' + q(), { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ link_id: currentLink.id, why_answer: why, fail_answer: fail }) });
      el('probeWhyFb').innerHTML = `<div class="${j.why_passed ? 'fb-ok' : 'fb-bad'}">${esc(j.why_feedback || '')}</div>` +
        (j.why_hint ? `<div class="fb-hint">Hint: ${esc(j.why_hint)}</div>` : '');
      el('probeFailFb').innerHTML = `<div class="${j.fail_passed ? 'fb-ok' : 'fb-bad'}">${esc(j.fail_feedback || '')}</div>` +
        (j.fail_hint ? `<div class="fb-hint">Hint: ${esc(j.fail_hint)}</div>` : '');
      if (j.why_passed) el('probeWhy').disabled = true;
      if (j.fail_passed) el('probeFail').disabled = true;
      paint(j.progress);
      refresh();
      // Manual-close only: the probe modal never auto-closes so the user has
      // time to read LLM feedback. Close via the × (probeX) top-right.
      // Final transitions (Phase2/done) also wait for an explicit Continue
      // click instead of swapping modals immediately.
      if (j.phase2_ready) {
        el('probeMsg').innerHTML = '<div class="fb-ok">Link bright ✔ — all evaluated. Review the feedback above, then continue.</div><button class="btn primary" id="probeNext">Continue to Sub-Headings</button>';
        const nx = el('probeNext');
        if (nx) nx.onclick = () => {
          el('probemodal').classList.remove('open');
          const m = el('phase2modal');
          // Problem 2: stage L5 → Phase2, hide stage cards (modal covers).
          try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('Phase2'); } catch (e) { /* sidebar optional */ }
          if (m) { if (window.CogniMapPhase2) CogniMapPhase2.open(); else m.classList.add('open'); }
        };
      } else if (j.done) {
        el('probeMsg').innerHTML = '<div class="fb-ok">Link bright ✔ — all learned, final map intact. Review the feedback above, then continue.</div><button class="btn primary" id="probeNext">View final map</button>';
        // Final-done modal (mirrors L3/L4/L5 transition pattern, Details Phase 2 §3).
        const nx2 = el('probeNext');
        if (nx2) nx2.onclick = () => {
          el('probemodal').classList.remove('open');
          // Problem 2: stage → done, hide stage cards (final map).
          try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('done'); } catch (e) { /* sidebar optional */ }
          const d = el('donemodal');
          if (d) d.classList.add('open');
        };
      } else if (j.link && j.link.bright) {
        el('probeMsg').innerHTML = '<div class="fb-ok">Link bright ✔ — review the feedback above, then close with × (top-right) to continue.</div>';
      } else {
        el('probeMsg').innerHTML = '<div class="fb-bad">Rewrite the failed side only — passed side stays green.</div>';
      }
    } catch (err) { el('probeMsg').textContent = err.message; }
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    // Problem 4 same root cause: trailing modals (#l5modal/#probemodal/
    // #donemodal) parsed after the old init position. Robust bind + retry.
    function bindTrailing() {
      const ps = el('probeSubmit');
      if (ps && !ps._bound) { ps._bound = true; ps.onclick = submit; }
      const px = el('probeX');
      if (px && !px._bound) { px._bound = true; px.onclick = () => el('probemodal').classList.remove('open'); }
      const t = el('toL5Btn');
      if (t && !t._bound) { t._bound = true; t.onclick = () => el('l5modal').classList.remove('open'); }
      const d = el('doneOk');
      if (d && !d._bound) { d._bound = true; d.onclick = () => el('donemodal').classList.remove('open'); }
    }
    bindTrailing();
    try { document.addEventListener('DOMContentLoaded', bindTrailing); } catch (e) { /* ignore */ }
    try {
      if (!document._cognimapL5Delegated) {
        document._cognimapL5Delegated = true;
        document.addEventListener('click', (e) => {
          const q = e.target && e.target.closest ? e.target.closest('#toL5Btn,#probeX,#doneOk') : null;
          if (!q) return;
          const id = q.id;
          if (id === 'toL5Btn') { const m = el('l5modal'); if (m) m.classList.remove('open'); }
          if (id === 'probeX') { const m = el('probemodal'); if (m) m.classList.remove('open'); }
          if (id === 'doneOk') { const m = el('donemodal'); if (m) m.classList.remove('open'); }
        });
      }
    } catch (e) { /* delegation optional */ }
    refresh();
  }

  window.CogniMapL5 = { init, refresh, openProbe };
})();
