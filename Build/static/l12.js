// CogniMap Step 2 — L1-2 Remember/Understand drawer (Locks §2, §6).
// Title read-only post-Confirm; blue bypass (no LLM, non-empty saves);
// progress % on mains (Phase 1); 100% → L3 transition modal.
(function () {
  let SID = '', UID = 0, cache = [];

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

  function pagesLabel(pages) {
    const p = pages || [];
    if (!p.length) return '';
    if (p.length === 1) return 'p.' + p[0];
    return 'p.' + Math.min(...p) + '-' + Math.max(...p);
  }

  function explLabel(c) {
    // Locks §1: pages=[] → omit p.X (no trailing comma).
    const pg = pagesLabel(c.pages);
    const inner = pg ? `${c.explanation_type}, ${pg}` : `${c.explanation_type}`;
    const tag = c.explanation_source === 'extracted'
      ? `Original Explanation [${inner}]`
      : `AI-grounded from doc scope [${inner}]`;
    return tag;
  }

  function diagramHtml(c) {
    // Locks §0: screenshots at /static/diagrams/{diagram_id}.png; absent
    // file → description-only (onerror hides the img, no breakage).
    let h = '';
    const refs = c.diagram_refs || [];
    for (const r of refs) {
      const did = r.diagram_id || r.id || '';
      if (!did) continue;
      const src = `/static/diagrams/${encodeURIComponent(did)}.png`;
      h += `<div class="expl-diag"><img src="${esc(src)}" alt="Diagram ${esc(did)}" ` +
        `style="max-width:100%" onerror="this.style.display='none'">` +
        (c.diagram_description ? `<div>Diagram: ${esc(c.diagram_description)}</div>` : '') +
        `</div>`;
      break; // one image branch exercised; description covers the rest
    }
    if (!refs.length && c.diagram_description) {
      h += `<div class="expl-diag">Diagram: ${esc(c.diagram_description)}</div>`;
    }
    return h;
  }

  async function openDrawer(id) {
    // B3 stage gate (wired to skeleton helper): linking clicks (drag pending
    // or edge panel open) must NOT pop the drawer over the edge panel.
    try {
      if (window.CogniMapStage && window.CogniMapStage.isLinkingActive()) return;
    } catch (e) { /* fall through */ }
    cache = await api('/api/sessions/' + SID + '/concepts' + q());
    const c = cache.find(x => x.id === id);
    if (!c) return;
    // Locks §7 (M3): mains dimmed/completed locked in Phase 2 — math on
    // subs only. Verify disabled for kind==main in phase2, history-only.
    // B3: also gate Verify via skeleton helper when stage left L1-2 (L3/L4/L5
    // late verifies would append L1-2 trail after advance). Drawer stays open
    // for §9 history review; only Verify is locked.
    let phase = 'phase1', stage = 'L1-2';
    try {
      const st = await api('/api/sessions/' + SID + '/l12/status' + q());
      phase = st.phase || 'phase1';
    } catch (e) { /* pre-confirm: stay phase1 */ }
    try {
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      stage = (sst.session && sst.session.stage) || stage;
      phase = (sst.session && sst.session.phase) || phase;
    } catch (e) { /* keep phase */ }
    const lockedMain = (phase === 'phase2' && c.kind === 'main');
    let stageLocked = false;
    try {
      if (window.CogniMapStage && window.CogniMapStage.shouldSuppressVerify)
        stageLocked = window.CogniMapStage.shouldSuppressVerify(stage, { phase, kind: c.kind });
    } catch (e) { stageLocked = false; }
    const blue = c.source === 'user_added';
    el('drawerTitle').textContent = c.title;
    el('blueWarn').classList.toggle('hidden', !blue);
    let h = '';
    let savedText = '';
    if (!blue) {
      h += `<div class="expl-tag">${esc(explLabel(c))}</div>`;
      h += `<div class="expl-text">${esc(c.explanation_text)}</div>`;
      h += diagramHtml(c);
    } else {
      // Blue (user_added, Locks §2+§9): no source box; reviewable as
      // name + user explanation + warning-ack + saved flag (no accuracy).
      // Warning lives in #blueWarn; saved text prefilled below for review.
      savedText = (c.explanation_text || '').trim();
      if (savedText) {
        h += `<div class="expl-tag">Your saved explanation [user-defined] ✓ Saved</div>`;
        h += `<div class="expl-text">${esc(c.explanation_text)}</div>`;
        h += diagramHtml(c);
      } else {
        h += `<div class="expl-text muted">No source definition (user-added). Write your own explanation below — saving counts toward progress.</div>`;
      }
    }
    el('drawerExpl').innerHTML = h;
    // Blue saved text stays reviewable: prefill the box for edit/review
    // instead of clearing (M5). Extracted rows start blank each open.
    el('drawerPara').value = blue ? savedText : '';
    if (lockedMain || stageLocked) {
      // Phase-2 mains: completed/locked, history-only (no Verify, no trail).
      // B3: L3/L4/L5 stages lock Verify the same way (drawer stays for history).
      // UI_ISSUES.txt Problem 3: history-only must not look like Stage 1-2 UI —
      // hide the paraphrase input + Verify so the panel reads as history
      // (explanation read-only on top, answers/feedback in histView below).
      const msg = lockedMain
        ? `<div class="muted">Main completed in Phase 1 — history-only in Phase 2 (subs carry progress).</div>`
        : `<div class="muted">L1-2 locked at stage ${esc(stage)} — history-only (complete the current stage to continue).</div>`;
      el('drawerFb').innerHTML = msg;
      el('verifyBtn').disabled = true;
      el('verifyBtn').onclick = () => {
        el('drawerFb').innerHTML = msg;
      };
      el('drawerPara').disabled = true;
      try {
        const _lbl = el('drawerParaLabel') || document.querySelector('label[for="drawerPara"]');
        if (_lbl) _lbl.classList.add('hidden');
      } catch (e) { /* label optional */ }
      el('drawerPara').classList.add('hidden');
      el('verifyBtn').classList.add('hidden');
    } else {
      el('drawerFb').innerHTML = (blue && savedText)
        ? `<div class="fb-ok">✓ Saved — reviewable (warning acknowledged, no LLM grade).</div>` : '';
      el('verifyBtn').disabled = false;
      el('drawerPara').disabled = false;
      el('verifyBtn').onclick = () => verify(c.id);
      try {
        const _lbl = el('drawerParaLabel') || document.querySelector('label[for="drawerPara"]');
        if (_lbl) _lbl.classList.remove('hidden');
      } catch (e) { /* label optional */ }
      el('drawerPara').classList.remove('hidden');
      el('verifyBtn').classList.remove('hidden');
    }
    el('drawerPara').onkeydown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') verify(c.id);
    };
    window.CogniMapShell.openPanel();
    // Locks §9 defaults: stage-aware history on drawer open (mid-phase
    // reviewable). History module fetches /state itself; no-op if user set.
    try {
      if (window.CogniMapHistory && window.CogniMapHistory.ensureDefault)
        window.CogniMapHistory.ensureDefault();
    } catch (e) { /* history optional */ }
  }

  async function verify(id) {
    // B3+M3 guard (wired to skeleton helper): never Verify when stage left
    // L1-2 or kind-phase mismatches (would pollute trail) — history-only.
    // Server enforces the same gate (400); this is the UI mirror.
    try {
      const cc = (cache || []).find(x => x.id === id);
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      const stage = (sst.session && sst.session.stage) || 'L1-2';
      const phase = (sst.session && sst.session.phase) || 'phase1';
      const kind = cc ? cc.kind : undefined;
      if (window.CogniMapStage && window.CogniMapStage.shouldSuppressVerify(stage, { phase, kind })) {
        el('drawerFb').innerHTML = `<div class="muted">L1-2 locked at stage ${esc(stage)} — history-only (complete the current stage to continue).</div>`;
        return;
      }
      if (cc && cc.kind === 'main' && phase === 'phase2') {
        el('drawerFb').innerHTML = `<div class="muted">Main completed in Phase 1 — history-only in Phase 2 (subs carry progress).</div>`;
        return;
      }
    } catch (e) { /* fall through to server verify */ }
    const text = el('drawerPara').value;
    try {
      const j = await api('/api/sessions/' + SID + '/l12/verify' + q(), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept_id: id, paraphrase: text }),
      });
      const ok = j.passed;
      if (j.bypass) {
        // Locks §9: blue rows — user explanation + warning-ack + saved flag,
        // no accuracy/originality.
        el('drawerFb').innerHTML =
          `<div class="${ok ? 'fb-ok' : 'fb-bad'}">${ok ? '✔ Saved' : 'Needs work'}</div>` +
          `<div>${esc(j.feedback || '')}</div>` +
          (j.warning_ack ? `<div class="fb-hint">${esc(j.warning_ack)}</div>` : '') +
          (ok ? `<div class="fb-ok">✓ Saved — reviewable.</div>` : '') +
          (j.hint ? `<div class="fb-hint">Hint: ${esc(j.hint)}</div>` : '');
        // Refresh cached explanation so reopen stays reviewable.
        try {
          cache = await api('/api/sessions/' + SID + '/concepts' + q());
          const c = cache.find(x => x.id === id);
          if (c && (c.explanation_text || '').trim()) openDrawerRefreshOnly(c);
        } catch (e) { /* keep drawer */ }
      } else {
        el('drawerFb').innerHTML =
          `<div class="${ok ? 'fb-ok' : 'fb-bad'}">${ok ? '✔ Correct' : 'Needs work'}</div>` +
          `<div>Accuracy: ${esc(j.accuracy)} · Originality: ${esc(j.originality)}</div>
             <div>${esc(j.feedback)}</div>` +
            (j.warning ? `<div class="fb-hint">${esc(j.warning)}</div>` : '') +
            (j.hint ? `<div class="fb-hint">Hint: ${esc(j.hint)}</div>` : '');
      }
      paintProgress(j.progress);
      if (j.l3_ready) {
        el('l3modal').classList.add('open');
        // Problem 2: stage advanced L1-2 → L3, show only L3 card now.
        try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('L3'); } catch (e) { /* sidebar optional */ }
        // Locks §3+§10: stage just advanced to L3 — refresh L3 slice so
        // Generate Scenario enables without manual reload (mirrors
        // toL4Btn→refresh() in l4.js).
        try { if (window.CogniMapL3 && window.CogniMapL3.refresh) window.CogniMapL3.refresh(); } catch (e) { /* L3 optional */ }
      }
    } catch (err) {
      el('drawerFb').innerHTML = `<div class="fb-bad">${esc(err.message)}</div>`;
    }
  }

  function openDrawerRefreshOnly(c) {
    // Re-render saved blue text inline without clearing the just-typed box.
    const h = `<div class="expl-tag">Your saved explanation [user-defined] ✓ Saved</div>` +
      `<div class="expl-text">${esc(c.explanation_text)}</div>` + diagramHtml(c);
    el('drawerExpl').innerHTML = h;
  }

  function paintProgress(p) {
    if (!p) return;
    const bar = el('progress');
    bar.innerHTML = `Level 1 - 2 [Remember/Understand] ${p.pct}% (${p.completed}/${p.total})` +
      (p.complete ? ` <button class="btn sm green-inline" id="goL3">Continue to Level 3</button>` : '');
    const b = el('goL3');
    if (b) b.onclick = () => {
      el('l3modal').classList.add('open');
      try { if (window.CogniMapL3 && window.CogniMapL3.refresh) window.CogniMapL3.refresh(); } catch (e) { /* L3 optional */ }
    };
  }

  async function init(sid, userId) {
    SID = sid; UID = userId || 0;
    el('graph').addEventListener('click', (e) => {
      // UI_ISSUES.txt Problem 1 (free move): suppress drawer after a move drag.
      try {
        if (window.__cognimap_nodeMoved) { e.stopPropagation(); return; }
        if (window.CogniMapNodeMove && window.CogniMapNodeMove.wasMoved && window.CogniMapNodeMove.wasMoved()) { e.stopPropagation(); return; }
      } catch (_e) { /* fall through */ }
      // B3: linking clicks must not pop the drawer over the L4 edge panel.
      try {
        if (window.CogniMapStage && window.CogniMapStage.isLinkingActive()) {
          e.stopPropagation();
          return;
        }
      } catch (_e) { /* fall through */ }
      const n = e.target.closest('[data-node]');
      if (n) openDrawer(n.getAttribute('data-node'));
    });
    // Problem 4 same root cause as l12guide: #toL3Btn lives in trailing
    // #l3modal after the old init position, so direct bind could miss.
    // Robust bind + DOMContentLoaded retry + delegated fallback (keeps L3 refresh).
    function bindToL3() {
      const t = el('toL3Btn');
      if (t && !t._bound) {
        t._bound = true;
        t.onclick = () => {
          el('l3modal').classList.remove('open');
          // Same pattern as toL4Btn→refresh(): entering L3 must enable Generate.
          try { if (window.CogniMapL3 && window.CogniMapL3.refresh) window.CogniMapL3.refresh(); } catch (e) { /* L3 optional */ }
        };
      }
    }
    bindToL3();
    try { document.addEventListener('DOMContentLoaded', bindToL3); } catch (e) { /* ignore */ }
    try {
      if (!document._cognimapToL3Delegated) {
        document._cognimapToL3Delegated = true;
        document.addEventListener('click', (e) => {
          const t2 = e.target && e.target.closest ? e.target.closest('#toL3Btn') : null;
          if (t2) {
            const m = el('l3modal');
            if (m) m.classList.remove('open');
            try { if (window.CogniMapL3 && window.CogniMapL3.refresh) window.CogniMapL3.refresh(); } catch (_e) { /* L3 optional */ }
          }
        });
      }
    } catch (e) { /* delegation optional */ }
    try { paintProgress(await api('/api/sessions/' + SID + '/l12/status' + q())); } catch (e) { /* empty session */ }
    // Problem 2: gate sidebar on load (L1-2 card only when stage is L1-2;
    // steps1-2 shows materials only even though l12/status returns 0/0).
    try {
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      if (window.CogniMapStage && window.CogniMapStage.refreshSidebar)
        window.CogniMapStage.refreshSidebar(sst.session && sst.session.stage);
    } catch (e) { /* pre-confirm session */ }
  }

  window.CogniMapL12 = { init, openDrawer };
})();
