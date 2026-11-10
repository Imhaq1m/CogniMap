// CogniMap Print — revision hardcopy (grilled Q1-Q14, browser print only).
// Anytime print + B&W-safe + by-concept dossier. No new API routes:
// builds from existing /state /concepts /links /scenarios /trail.
(function () {
  let SID = '', UID = 0;

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

  // Grilled Q8: B&W-safe provenance tag (no color-only meaning).
  function tagFor(c) {
    const pg = pagesLabel(c.pages);
    if (c.source === 'user_added') return '[Mine — user-defined]';
    if (c.explanation_source === 'extracted') return '[Doc' + (pg ? ' ' + pg : '') + ']';
    return '[AI-grounded' + (pg ? ' ' + pg : '') + ']';
  }

  function latestPassedParaphrase(trail, cid) {
    const rows = (trail || []).filter(t => t.stage === 'L1-2' && t.concept_id === cid);
    if (!rows.length) return '';
    rows.sort((a, b) => (a.id || 0) - (b.id || 0));
    for (let i = rows.length - 1; i >= 0; i--) {
      try {
        const p = JSON.parse(rows[i].payload || '{}');
        if (p.passed && (p.paraphrase || p.user_explanation)) return p.paraphrase || p.user_explanation;
      } catch (e) { /* skip */ }
    }
    return '';
  }

  function scenarioText(scn) {
    const t = ((scn && scn.text) || '').replace(/\s+/g, ' ').trim();
    if (!t) return '(no text)';
    return t.length > 220 ? t.slice(0, 217) + '…' : t;
  }

  function snapshotMapSvg() {
    // Grilled Q7/Q14: image best-effort, list always. Clone live SVG if present.
    try {
      const svg = document.querySelector('#graphSvg');
      if (!svg) return '';
      const clone = svg.cloneNode(true);
      clone.removeAttribute('id');
      clone.setAttribute('width', '100%');
      // Strip interactive-only controls; keep nodes + edges.
      return new XMLSerializer().serializeToString(clone);
    } catch (e) { return ''; }
  }

  function diagramThumb(c) {
    const refs = c.diagram_refs || [];
    let h = '';
    for (const r of refs) {
      const did = r.diagram_id || r.id || '';
      if (!did) continue;
      const src = '/static/diagrams/' + encodeURIComponent(did) + '.png';
      h += '<div class="pp-diag"><img src="' + esc(src) + '" alt="Diagram ' + esc(did) + '" '
        + 'onerror="this.style.display=\'none\'">'
        + '<div class="pp-diag-cap">Fig ' + esc(did)
        + (c.diagram_description ? ' — ' + esc(c.diagram_description) : '') + '</div></div>';
      break; // one thumbnail; description covers the rest
    }
    if (!refs.length && c.diagram_description) {
      h += '<div class="pp-diag"><div class="pp-diag-cap">Diagram: ' + esc(c.diagram_description) + '</div></div>';
    }
    return h;
  }

  async function collect() {
    const [state, concepts, links, scenarios, trail] = await Promise.all([
      api('/api/sessions/' + SID + '/state' + q()),
      api('/api/sessions/' + SID + '/concepts' + q()).catch(() => []),
      api('/api/sessions/' + SID + '/links' + q()).catch(() => []),
      api('/api/sessions/' + SID + '/scenarios' + q()).catch(() => []),
      api('/api/sessions/' + SID + '/trail' + q()).catch(() => []),
    ]);
    const sess = (state && state.session) || {};
    // Stage pct for the header: fetch only the active percentage stage.
    let pctLine = '';
    try {
      const stage = sess.stage || '';
      if (stage === 'L1-2') {
        const s = await api('/api/sessions/' + SID + '/l12/status' + q());
        pctLine = 'Level 1-2 ' + s.completed + '/' + s.total + ' (' + s.pct + '%)';
      } else if (stage === 'L3') {
        const s = await api('/api/sessions/' + SID + '/l3/status' + q());
        pctLine = 'Level 3 ' + s.cleared + '/' + s.total + ' (' + s.pct + '%)';
      } else if (stage === 'L5') {
        const s = await api('/api/sessions/' + SID + '/l5/status' + q());
        pctLine = s.entered ? ('Level 5 ' + s.bright + '/' + s.n + ' (' + s.pct + '%)') : ('Level 5 0/' + (s.n || 0));
      } else {
        pctLine = stage || 'steps1-2';
      }
    } catch (e) { pctLine = (sess.stage || ''); }
    return { sess, concepts, links, scenarios, trail, pctLine };
  }

  function incidentLinks(links, cid) {
    return (links || []).filter(L => L.a_id === cid || L.b_id === cid);
  }

  function linkLabel(L, byId) {
    const a = (byId[L.a_id] && byId[L.a_id].title) || L.a_id || '';
    const b = (byId[L.b_id] && byId[L.b_id].title) || L.b_id || '';
    const t = (L.edge_type || '—').trim() || '—';
    const st = (L.bright === false || L.bright === 0) ? ' ○ pending' : ' ● verified';
    return esc(a) + ' —' + esc(t) + '→ ' + esc(b) + esc(st);
  }

  async function buildPack(opts) {
    const data = await collect();
    const { sess, concepts, links, scenarios, trail, pctLine } = data;
    const byId = {};
    (concepts || []).forEach(c => { byId[c.id] = c; });
    const wsName = sess.name || sess.file || SID;
    const fileLbl = sess.file || '';
    const stage = sess.stage || 'steps1-2';
    const phase = sess.phase || 'phase1';
    const isDone = stage === 'done';
    const dateStr = new Date().toLocaleDateString();
    const draftTag = isDone ? 'FINAL' : 'DRAFT';

    const mains = (concepts || []).filter(c => c.kind === 'main');
    const subsByParent = {};
    (concepts || []).filter(c => c.kind === 'sub').forEach(s => {
      const p = s.parent_id || '';
      (subsByParent[p] = subsByParent[p] || []).push(s);
    });

    function conceptBlock(c) {
      const isBlue = c.source === 'user_added';
      let h = '<section class="pp-concept">';
      h += '<h3 class="pp-ctitle">' + esc(c.title) + ' <span class="pp-tag">' + esc(tagFor(c)) + '</span></h3>';
      if (isBlue) {
        const txt = (c.explanation_text || '').trim();
        h += '<div class="pp-def"><div class="pp-label">Your definition (user-added, not doc-verified)</div>'
          + '<div>' + esc(txt || '— not written yet —') + '</div></div>';
      } else {
        h += '<div class="pp-def"><div class="pp-label">Definition ' + esc(tagFor(c)) + '</div>'
          + '<div>' + esc(c.explanation_text || '—') + '</div></div>';
      }
      if (opts.words && !isBlue) {
        const para = latestPassedParaphrase(trail, c.id);
        if (para) {
          h += '<div class="pp-words"><div class="pp-label">In your words (last passed)</div>'
            + '<div>' + esc(para) + '</div></div>';
        }
      } else if (opts.words && isBlue) {
        // Blue saved text already shown above; no duplicate box.
      }
      if (opts.scenarios) {
        const used = (scenarios || []).filter(s => (s.concept_ids || []).includes(c.id));
        if (used.length) {
          h += '<div class="pp-used"><div class="pp-label">Used in ' + used.length + ' scenario(s)</div><ul>'
            + used.map(s => '<li>' + esc(scenarioText(s)) + '</li>').join('') + '</ul></div>';
        }
      }
      if (opts.links) {
        const inc = incidentLinks(links, c.id);
        if (inc.length) {
          h += '<div class="pp-links"><div class="pp-label">Links (' + inc.length + ')</div><ul>'
            + inc.map(L => '<li>' + linkLabel(L, byId) + '</li>').join('') + '</ul></div>';
        }
      }
      h += diagramThumb(c);
      // Q11: subs nested under parent, same block order recursively.
      const subs = subsByParent[c.id] || [];
      subs.forEach(s => { h += '<div class="pp-sub">' + conceptBlockInner(s) + '</div>'; });
      h += '</section>';
      return h;
    }
    function conceptBlockInner(c) {
      // Sub block without re-nesting (subs have no children by lock).
      const isBlue = c.source === 'user_added';
      let h = '<h4 class="pp-ctitle pp-sub-title">↳ ' + esc(c.title) + ' <span class="pp-tag">' + esc(tagFor(c)) + '</span></h4>';
      if (isBlue) {
        h += '<div class="pp-def"><div class="pp-label">Your definition (user-added)</div>'
          + '<div>' + esc((c.explanation_text || '').trim() || '— not written yet —') + '</div></div>';
      } else {
        h += '<div class="pp-def"><div class="pp-label">Definition ' + esc(tagFor(c)) + '</div>'
          + '<div>' + esc(c.explanation_text || '—') + '</div></div>';
      }
      if (opts.words && !isBlue) {
        const para = latestPassedParaphrase(trail, c.id);
        if (para) h += '<div class="pp-words"><div class="pp-label">In your words (last passed)</div><div>' + esc(para) + '</div></div>';
      }
      if (opts.scenarios) {
        const used = (scenarios || []).filter(s => (s.concept_ids || []).includes(c.id));
        if (used.length) h += '<div class="pp-used"><div class="pp-label">Used in</div><ul>' + used.map(s => '<li>' + esc(scenarioText(s)) + '</li>').join('') + '</ul></div>';
      }
      if (opts.links) {
        const inc = incidentLinks(links, c.id);
        if (inc.length) h += '<div class="pp-links"><div class="pp-label">Links</div><ul>' + inc.map(L => '<li>' + linkLabel(L, byId) + '</li>').join('') + '</ul></div>';
      }
      h += diagramThumb(c);
      return h;
    }

    const svgStr = opts.mapImg ? snapshotMapSvg() : '';
    const mapImgHtml = svgStr
      ? '<div class="pp-mapimg">' + svgStr + '<div class="pp-caption">Workspace shape (illustrative — list below is complete).</div></div>'
      : '<div class="pp-caption">Map image unavailable — list below is complete.</div>';

    let html = '';
    html += '<div class="pp-runhead">CogniMap — ' + esc(wsName) + ' — ' + esc(stage) + ' ' + esc(pctLine) + ' — ' + esc(dateStr) + ' — ' + esc(draftTag) + '</div>';
    html += '<div class="pp-runfoot">Source: ' + esc(fileLbl || wsName) + ' — ' + esc(draftTag) + ' unless done</div>';
    html += '<div class="pp-cover"><h1>CogniMap Study Pack</h1>'
      + '<div class="pp-cover-meta">Workspace: <b>' + esc(wsName) + '</b> · Stage: <b>' + esc(stage) + '</b> (' + esc(phase) + ') · ' + esc(pctLine) + ' · ' + esc(dateStr) + ' · <b>' + esc(draftTag) + '</b></div>'
      + '<div class="pp-cover-meta">Source file: ' + esc(fileLbl || '—') + ' · Concepts: ' + (concepts || []).length + ' · Links: ' + (links || []).length + ' · Scenarios: ' + (scenarios || []).length + '</div>'
      + '<div class="pp-legend">Legend: [Doc p.X] = from your PDF · [AI-grounded] = written from doc scope by AI · [Mine] = you added it (not doc-verified) · ● verified link / ○ pending link · B&amp;W-safe: meaning never color-only.</div>'
      + '<div class="pp-how">How to use: read Definition, recall In-your-words, then check Used-in + Links. Order follows Bloom: what it is (L1-2) → where it applies (L3) → how it connects (L4-5).</div>'
      + '</div>';
    html += '<h2 class="pp-h2">Concept map</h2>' + mapImgHtml;
    if (opts.links) {
      html += '<div class="pp-adj"><div class="pp-label">All links (' + (links || []).length + ')</div>';
      html += (links || []).length
        ? '<ol>' + (links || []).map(L => '<li>' + linkLabel(L, byId) + '</li>').join('') + '</ol>'
        : '<div class="pp-caption">No links yet.</div>';
      html += '</div>';
    }
    html += '<h2 class="pp-h2">Concepts (' + mains.length + ' mains)</h2>';
    html += mains.length ? mains.map(conceptBlock).join('') : '<div class="pp-caption">No concepts confirmed yet — confirm selection in the workspace first.</div>';
    if (opts.scenarios) {
      html += '<h2 class="pp-h2">Scenarios (' + (scenarios || []).length + ')</h2>';
      html += (scenarios || []).length
        ? '<ol class="pp-scnlist">' + (scenarios || []).map(s => {
            const names = (s.concept_ids || []).map(id => (byId[id] && byId[id].title) || id).join(', ');
            return '<li><div>' + esc(scenarioText(s)) + '</div><div class="pp-caption">Concepts: ' + esc(names) + (s.cleared ? ' · cleared' : '') + '</div></li>';
          }).join('') + '</ol>'
        : '<div class="pp-caption">No scenarios yet.</div>';
    }
    html += '<div class="pp-foot">Printed ' + esc(dateStr) + ' from CogniMap workspace “' + esc(wsName) + '” — ' + esc(draftTag) + '. Source: ' + esc(fileLbl || wsName) + '.</div>';
    return { html, wsName, stage, pctLine, dateStr, draftTag };
  }

  function readOpts() {
    return {
      mapImg: el('ppChkMap') ? el('ppChkMap').checked : true,
      words: el('ppChkWords') ? el('ppChkWords').checked : true,
      scenarios: el('ppChkScn') ? el('ppChkScn').checked : true,
      links: el('ppChkLinks') ? el('ppChkLinks').checked : true,
    };
  }

  async function doPrint() {
    const box = el('printPack');
    try {
      if (el('ppMsg')) el('ppMsg').textContent = 'Building pack…';
      const out = await buildPack(readOpts());
      if (box) box.innerHTML = out.html;
      if (el('printmodal')) el('printmodal').classList.add('hidden');
      if (el('ppMsg')) el('ppMsg').textContent = '';
      window.print();
    } catch (e) {
      if (el('ppMsg')) el('ppMsg').textContent = 'Print failed: ' + (e.message || e);
    }
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    const btn = el('printBtn');
    if (btn) btn.onclick = () => {
      const m = el('printmodal');
      if (m) m.classList.remove('hidden');
    };
    const x = el('printX');
    if (x) x.onclick = () => el('printmodal').classList.add('hidden');
    const cancel = el('printCancel');
    if (cancel) cancel.onclick = () => el('printmodal').classList.add('hidden');
    const go = el('printGo');
    if (go) go.onclick = doPrint;
    const m = el('printmodal');
    if (m) m.addEventListener('mousedown', (ev) => { if (ev.target === m) m.classList.add('hidden'); });
    document.addEventListener('keydown', (ev) => {
      try {
        if ((ev.key === 'Escape' || ev.key === 'Esc') && m && !m.classList.contains('hidden')) m.classList.add('hidden');
      } catch (_e) { /* ignore */ }
    });
  }

  window.CogniMapPrint = { init, buildPack: buildPack, collect: collect };
})();
