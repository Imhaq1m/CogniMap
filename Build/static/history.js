// CogniMap Step 6 — History dropdown (Locks §9).
// Single stage dropdown + nested scenario/link selectors, defaults per §9,
// L4 omitted graph-only, no-prune, reviewable mid-phase.
(function () {
  let SID = '', UID = 0, currentConcept = null, trailCache = [];

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

  async function loadTrail() {
    try { trailCache = await api('/api/sessions/' + SID + '/trail' + q()); }
    catch (e) { trailCache = []; }
    return trailCache;
  }

  async function ensureDefault() {
    // Locks §9 defaults (m1 documented mapping + m1 fix):
    // Stage3 → 1&2 (L3 shows L1-2), Stage4 → 3 + graph (L4 shows L3,
    // L4 graph-visible only omitted from dropdown), Stage5 → L5 when incident
    // links have L5 history else L3 (+graph for 4; L5 incident-link selector
    // for links), Phase2 (new sub cycle) → L1-2, done → L5.
    // Fetch /state on drawer open; never override explicit user selection.
    // Mid-phase reviewable (TODO Step 6 DONE). Demo: L5 drawer → Why/When +
    // why_hint/fail_hint visible without manual Stage 5 pick.
    try {
      const sel = el('histStage');
      if (!sel || sel.value) return;
      const st = await api('/api/sessions/' + SID + '/state' + q());
      const stage = (st.session && st.session.stage) || '';
      let def = '';
      if (stage === 'L3') def = 'L1-2';
      else if (stage === 'L4') def = 'L3';
      else if (stage === 'L5') {
        // m1: default L5 to L5 when incident links have L5 rows, else L3.
        // Keeps single dropdown + nested link selector; marker sees Why/When.
        def = 'L3';
        try {
          const [trail, links] = await Promise.all([
            api('/api/sessions/' + SID + '/trail' + q()),
            api('/api/sessions/' + SID + '/links' + q()),
          ]);
          if (currentConcept) {
            const incident = new Set(
              links.filter(L => L.a_id === currentConcept || L.b_id === currentConcept).map(L => L.id)
            );
            const hasL5 = trail.some(t => t.stage === 'L5' && incident.has(t.link_id));
            if (hasL5) def = 'L5';
            else if (incident.size) {
              // Links exist but no probe yet — still show L5 so the
              // incident-link selector + Why/When prompts are one click away?
              // No: keep L3 until first probe, else "No history yet" confuses.
              // Exception: if any L5 row exists at all, prefer L5.
              const anyL5 = trail.some(t => t.stage === 'L5');
              if (anyL5) def = 'L5';
            }
          } else {
            if (trail.some(t => t.stage === 'L5')) def = 'L5';
          }
        } catch (e) { /* fall back to L3 */ }
      }
      else if (stage === 'Phase2') def = 'L1-2';
      else if (stage === 'done') def = 'L5';
      if (def) {
        sel.value = def;
        await onStage();
      }
    } catch (e) { /* pre-confirm session: leave empty */ }
  }

  async function onStage() {
    const stage = el('histStage').value;
    const itemSel = el('histItem');
    const view = el('histView');
    if (!stage) { itemSel.classList.add('hidden'); view.innerHTML = ''; return; }
    // m5 (Locks §9 wins): L4 graph-only, correctly omitted from the dropdown
    // options in main.py — this branch is defensive only (unreachable via UI,
    // reachable only if stage is set programmatically). Keep behaviour;
    // reviewer verifies no L4 option per §9.
    if (stage === 'L4') { view.innerHTML = '<div class="muted">Stage 4 graph-only (see links on canvas).</div>'; itemSel.classList.add('hidden'); return; }
    await loadTrail();
    await ensureConcepts();
    await ensureScenarios();
    await ensureLinks();
    let rows = trailCache.filter(t => t.stage === stage);
    // Concept-panel query: filter by current concept when known.
    if (currentConcept && (stage === 'L3' || stage === 'L1-2')) {
      const mine = rows.filter(t => t.concept_id === currentConcept);
      if (mine.length) rows = mine;
    }
    // UI_ISSUES.txt Problem 2: L1-2 keeps only the latest answer + feedback
    // per concept. Backend replaces on each verify; dedup here too so legacy
    // sessions with multiple rows still show a single latest entry.
    if (stage === 'L1-2') {
      const latestByConcept = {};
      rows.forEach(t => {
        const k = t.concept_id || '';
        if (!latestByConcept[k] || (t.id || 0) > (latestByConcept[k].id || 0))
          latestByConcept[k] = t;
      });
      rows = Object.values(latestByConcept).sort((a, b) => (a.id || 0) - (b.id || 0));
    }
    if (stage === 'L5') {
      // Locks §5 vs §9: target_ids gates PROBING only (l5.js openProbe +
      // probe_submit 400 on excluded old links), never history review.
      // §9 requires Phase-2 mains reviewable for Stages 1,2,3,5 — old
      // Phase-1 main-main probe rows must stay visible after Phase-2.
      // So filter by incident link (all phases), never by current target set.
      // Excluded bright links with history show their cards; truly empty
      // shows "No history yet" via renderRows (no special excluded note).
      try {
        const links = await api('/api/sessions/' + SID + '/links' + q());
        (links || []).forEach(L => { if (L && L.id) linkCache[L.id] = L; });
        if (currentConcept) {
          const incident = new Set(
            links.filter(L => L.a_id === currentConcept || L.b_id === currentConcept).map(L => L.id)
          );
          rows = rows.filter(t => incident.has(t.link_id));
        }
        // No-concept focus: show all L5 rows (both phases); grouped by
        // link_id with the link selector below.
      } catch (e) { /* fall back to all */ }
    }
    if (stage === 'L3') {
      const byScn = {};
      rows.forEach(t => { (byScn[t.scenario_id || ''] = byScn[t.scenario_id || ''] || []).push(t); });
      const ids = Object.keys(byScn);
      if (ids.length > 1) {
        // UI_ISSUES.txt Problem 6: scenario dropdown when the (filtered)
        // concept is involved in multiple scenarios — options show the
        // scenario description, not the bare id (full text on hover).
        itemSel.innerHTML = ids.map(id =>
          `<option value="${esc(id)}" title="${esc(scnText(id))}">${esc(scnLabel(id))}</option>`).join('');
        itemSel.classList.remove('hidden');
        itemSel.value = ids[0];
        itemSel.onchange = () => renderRows(byScn[itemSel.value] || []);
        renderRows(byScn[ids[0]] || []);
      } else {
        itemSel.classList.add('hidden');
        renderRows(rows);
      }
    } else if (stage === 'L5') {
      const byLink = {};
      rows.forEach(t => { (byLink[t.link_id || ''] = byLink[t.link_id || ''] || []).push(t); });
      const ids = Object.keys(byLink);
      if (ids.length > 1) {
        // Same pattern as Stage 3 (Problem 6): dropdown shows the
        // human-readable link (other concept + type), not the bare id
        // (full A → type → B flow on hover).
        itemSel.innerHTML = ids.map(id =>
          `<option value="${esc(id)}" title="${esc(linkFull(id))}">${esc(linkDropdownLabel(id))}</option>`).join('');
        itemSel.classList.remove('hidden');
        itemSel.onchange = () => renderRows(byLink[itemSel.value] || []);
        renderRows(byLink[ids[0]] || []);
      } else {
        itemSel.classList.add('hidden');
        renderRows(rows);
      }
    } else {
      itemSel.classList.add('hidden');
      renderRows(rows);
    }
  }

  let conceptCache = {};
  async function ensureConcepts() {
    // M1 (§9): history needs full concept fields (explanation text/type/
    // source/pages + diagram_refs/description) — resolve server-side by id.
    try {
      const cs = await api('/api/sessions/' + SID + '/concepts' + q());
      conceptCache = {};
      cs.forEach(c => { conceptCache[c.id] = c; });
    } catch (e) { /* pre-confirm: leave empty */ }
    return conceptCache;
  }

  // UI_ISSUES.txt Problem 6: Stage-3 history needs scenario descriptions,
  // not bare ids. Cache id -> text via /scenarios (server owns text; trail
  // rows carry only scenario_id).
  let scenarioCache = {};
  async function ensureScenarios() {
    try {
      const scns = await api('/api/sessions/' + SID + '/scenarios' + q());
      scenarioCache = {};
      (scns || []).forEach(s => { if (s && s.id) scenarioCache[s.id] = s.text || ''; });
    } catch (e) { /* pre-confirm: leave empty, fall back to id */ }
    return scenarioCache;
  }
  function scnText(id) {
    const t = scenarioCache[id || ''];
    return (t && t.trim()) ? t : (id || '');
  }
  function scnLabel(id) {
    // Dropdown option label: description truncated so long scenarios stay
    // readable; falls back to the id when text is unavailable.
    const t = scnText(id).replace(/\s+/g, ' ').trim();
    if (!t || t === id) return id || '(unknown scenario)';
    return t.length > 80 ? t.slice(0, 77) + '…' : t;
  }

  // Stage-5 history needs human-readable link labels, not bare link ids.
  // Cache id -> link via /links (server owns a_id/b_id/edge_type; trail rows
  // carry only link_id). Titles resolve via conceptCache.
  let linkCache = {};
  async function ensureLinks() {
    try {
      const ls = await api('/api/sessions/' + SID + '/links' + q());
      const next = {};
      (ls || []).forEach(L => { if (L && L.id) next[L.id] = L; });
      // Merge (don't wipe) so the L5 target-filter fetch below can seed the
      // cache without an extra round-trip when ensureLinks ran first.
      linkCache = Object.assign({}, linkCache, next);
    } catch (e) { /* pre-confirm: leave empty, fall back to id */ }
    return linkCache;
  }
  function linkFull(id) {
    // Full relationship flow for card headers: [A] → [type] → [B].
    // Falls back to the id when link/concepts are unavailable.
    const L = linkCache[id || ''];
    if (!L) return id || '(unknown link)';
    const a = (conceptCache[L.a_id] || {}).title || L.a_id || '';
    const b = (conceptCache[L.b_id] || {}).title || L.b_id || '';
    const t = (L.edge_type || '').trim() || '—';
    if (!a && !b) return id || '(unknown link)';
    return `${a} → ${t} → ${b}`;
  }
  function linkDropdownLabel(id) {
    // Short other-concept form for the dropdown: direction + linked concept
    // + relationship type (e.g. "→ Retail via applied in"). Full flow stays
    // in the title hover + card header. Truncated like scnLabel.
    const L = linkCache[id || ''];
    const full = linkFull(id).replace(/\s+/g, ' ').trim();
    if (!L || !currentConcept) {
      if (!full || full === id) return id || '(unknown link)';
      return full.length > 80 ? full.slice(0, 77) + '…' : full;
    }
    let other = '', dir = '';
    if (currentConcept === L.a_id) {
      other = (conceptCache[L.b_id] || {}).title || L.b_id || '';
      dir = '→';
    } else if (currentConcept === L.b_id) {
      other = (conceptCache[L.a_id] || {}).title || L.a_id || '';
      dir = '←';
    } else {
      if (!full || full === id) return id || '(unknown link)';
      return full.length > 80 ? full.slice(0, 77) + '…' : full;
    }
    const et = (L.edge_type || '').trim() || '—';
    let short = `${dir} ${other} via ${et}`.replace(/\s+/g, ' ').trim();
    if (!other) return full.length > 80 ? full.slice(0, 77) + '…' : full;
    return short.length > 80 ? short.slice(0, 77) + '…' : short;
  }

  function pagesLabel(pages) {
    const p = pages || [];
    if (!p.length) return '';
    if (p.length === 1) return 'p.' + p[0];
    return 'p.' + Math.min(...p) + '-' + Math.max(...p);
  }

  function renderRows(rows) {
    const view = el('histView');
    if (!rows.length) { view.innerHTML = '<div class="muted">No history yet.</div>'; return; }
    view.innerHTML = rows.map(t => {
      let p = {};
      try { p = JSON.parse(t.payload || '{}'); } catch (e) { p = {}; }
      if (t.stage === 'L1-2') {
        // M1 (§9): extracted = name + explanation_text [type/source/pages]
        // + diagram_refs/diagram_description + paraphrase + accuracy/originality +
        // feedback; blue = name + user explanation + warning_ack + saved.
        const c = conceptCache[t.concept_id] || {};
        const name = c.title || t.concept_id || '';
        if (p.bypass || c.source === 'user_added') {
          return `<div class="hist-card"><div class="hist-card-head"><span class="hist-concept">${esc(name)}</span>` +
            `<span class="hist-badge">Stage 1-2 · user-defined</span></div>` +
            `<div class="hist-sec"><div class="hist-label">Your Explanation</div>` +
            `<div class="hist-val">${esc(p.user_explanation || c.explanation_text || '')}</div></div>` +
            `<div class="hist-sec"><div class="hist-label">Status</div>` +
            `<div class="hist-val">${p.saved ? '✓ Saved' : 'unsaved'} · ${esc(p.warning_ack || 'Ensure your self-defined concept is accurate — not verified against source.')}</div></div>` +
            (p.feedback ? `<div class="hist-sec"><div class="hist-label">Feedback</div><div class="hist-val">${esc(p.feedback)}</div></div>` : '') +
            `</div>`;
        }
        const pg = pagesLabel(c.pages);
        const diag = (c.diagram_refs || []).map(r => r.diagram_id || r.id || '').filter(Boolean).join(', ');
        const explMeta = `${c.explanation_type || ''}${c.explanation_source ? ' · ' + c.explanation_source : ''}${pg ? ' · ' + pg : ''}`;
        return `<div class="hist-card"><div class="hist-card-head"><span class="hist-concept">${esc(name)}</span>` +
          `<span class="hist-badge">Stage 1-2</span></div>` +
          `<div class="hist-sec"><div class="hist-label">Original Explanation${explMeta ? ' · ' + esc(explMeta) : ''}</div>` +
          `<div class="hist-val">${esc(c.explanation_text || '')}</div>` +
          `${diag ? `<div class="hist-meta">Diagrams: ${esc(diag)}</div>` : ''}` +
          `${c.diagram_description ? `<div class="hist-meta">Diagram: ${esc(c.diagram_description)}</div>` : ''}</div>` +
          `<div class="hist-sec"><div class="hist-label">Your Answer</div>` +
          `<div class="hist-val">${esc(p.paraphrase || '')}</div></div>` +
          `<div class="hist-sec"><div class="hist-label">Feedback</div>` +
          `<div class="hist-val">${p.accuracy ? `<div>Accuracy: ${esc(p.accuracy)}</div>` : ''}` +
          `${p.originality ? `<div>Originality: ${esc(p.originality)}</div>` : ''}` +
          `${p.feedback ? `<div>${esc(p.feedback)}</div>` : ''}` +
          `${p.hint ? `<div class="fb-hint">Hint: ${esc(p.hint)}</div>` : ''}</div></div>` +
          `</div>`;
      }
      if (t.stage === 'L3') {
        const c = conceptCache[t.concept_id] || {};
        const cname = c.title || t.concept_id || '';
        // UI_ISSUES.txt Problem 6: show the scenario description instead of
        // the bare scenario id (id kept as hover title for traceability).
        const scnFull = scnText(t.scenario_id || '');
        return `<div class="hist-card"><div class="hist-card-head"><span class="hist-concept">${esc(cname)}</span>` +
          `<span class="hist-badge">Stage 3${p.omitted ? ' · omitted' : ''}</span></div>` +
          `<div class="hist-sec"><div class="hist-label">Scenario</div>` +
          `<div class="hist-val" title="${esc(t.scenario_id || '')}">${esc(scnFull || t.scenario_id || '—')}</div></div>` +
          `<div class="hist-sec"><div class="hist-label">Your Justification</div>` +
          `<div class="hist-val">${esc(p.justification || '—')}</div></div>` +
          `<div class="hist-sec"><div class="hist-label">Feedback</div>` +
          `<div class="hist-val">${esc(p.feedback || '')}` +
          `${p.hint ? `<div class="fb-hint">Hint: ${esc(p.hint)}</div>` : ''}</div></div>` +
          `</div>`;
      }
      if (t.stage === 'L5') {
        // m3 (§9): render per-side why_hint/fail_hint alongside answers + feedback.
        // Header shows the full relationship flow (not the bare link id);
        // id kept as hover title for traceability (mirrors Stage 3 cards).
        const linkName = linkFull(t.link_id || '');
        return `<div class="hist-card"><div class="hist-card-head"><span class="hist-concept" title="${esc(t.link_id || '')}">${esc(linkName)}</span>` +
          `<span class="hist-badge">Stage 5</span></div>` +
          `<div class="hist-sec"><div class="hist-label">Why does this relationship exist?</div>` +
          `<div class="hist-val">${esc(p.why_answer || '—')}</div>` +
          `<div class="hist-val muted">${esc(p.why_feedback || '')}</div>` +
          `${p.why_hint ? `<div class="fb-hint">Hint: ${esc(p.why_hint)}</div>` : ''}</div>` +
          `<div class="hist-sec"><div class="hist-label">When might this relationship fail?</div>` +
          `<div class="hist-val">${esc(p.fail_answer || '—')}</div>` +
          `<div class="hist-val muted">${esc(p.fail_feedback || '')}</div>` +
          `${p.fail_hint ? `<div class="fb-hint">Hint: ${esc(p.fail_hint)}</div>` : ''}</div>` +
          `</div>`;
      }
      return `<div class="hist-card"><div class="hist-card-head"><span class="hist-concept">${esc(t.stage)}</span></div>` +
        `<div class="hist-val">${esc(t.payload || '')}</div></div>`;
    }).join('');
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    const s = el('histStage');
    if (s) s.onchange = onStage;
    // Track current concept for concept-panel query (session,concept,stage)
    // + apply stage-aware default on drawer open (Locks §9).
    document.addEventListener('click', (e) => {
      const n = e.target.closest && e.target.closest('[data-node]');
      if (n) {
        currentConcept = n.getAttribute('data-node');
        ensureDefault();
      }
    });
  }

  window.CogniMapHistory = { init, ensureDefault };
})();
