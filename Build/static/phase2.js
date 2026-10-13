// CogniMap Step 6 — Phase-2 restricted modal (Locks §7).
// Mains dimmed, subs-only adds, Phase-1 hidden subs preselected,
// ≥1 sub block + ≥2 recommended hint. Confirm merges subs, mains keep links/bright.
(function () {
  let SID = '', UID = 0, mains = [], subs = [];

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

  async function open() {
    // Problem 2: entering Phase2 hides stage cards (modal covers workspace).
    try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('Phase2'); } catch (e) { /* sidebar optional */ }
    let st = null;
    try { st = await api('/api/sessions/' + SID + '/phase2/status' + q()); }
    catch (e) { el('phase2warn').textContent = e.message; el('phase2warn').classList.remove('hidden'); return; }
    mains = st.mains || [];
    // Persisted subs (Phase-1 hidden + already-merged) are locked pre-selected
    // per Locks §7 — never discard, always counted in ceil(subs/3)/Finish/N.
    subs = (st.subs || []).map(s => ({ ...s, _locked: true }));
    render();
    el('phase2modal').classList.add('open');
  }

  function subRowHtml(s) {
    const sid = esc(s.id || s.concept_id);
    const locked = s._locked !== false;
    const check = locked
      ? `<input type="checkbox" data-act="check" checked disabled title="Persisted — always included"> `
      : `<input type="checkbox" data-act="check" checked> `;
    const del = locked ? '' : ` <button class="icon-btn" data-act="del" title="remove new row">x</button>`;
    return `<div class="tree-row sub" data-id="${sid}">${check}` +
      `<span class="tree-title">${esc(s.title)}</span> ` +
      `<button class="icon-btn" data-act="rename" title="rename">✎</button>${del}</div>`;
  }

  function render() {
    // UI_ISSUES.txt Problem 2: subs grouped under each main (context kept),
    // mirroring steps12.js renderTree — not one flat sub list. Mains dimmed
    // (no new mains); persisted subs locked checked-disabled, only new adds
    // checkable (Locks §7 filtered math: unchecked persisted would still count
    // backend-side, so deselect is forbidden in UI).
    // Subs rename via pen (Locks §7 subs add/rename allowed, like steps12.js).
    const mainIds = new Set((mains || []).map(m => m.id));
    const orphans = (subs || []).filter(s => !mainIds.has(s.parent_id));
    let h = '<div class="muted">Mains dimmed (completed) — sub-headings grouped under each main for context.</div>';
    h += '<div style="margin:8px 0"><b>Sub-headings (select ≥1, ≥2 recommended)</b></div>';
    for (const m of (mains || [])) {
      const kids = (subs || []).filter(s => s.parent_id === m.id);
      h += `<div class="tree-main" data-main="${esc(m.id)}">` +
        `<div class="tree-row dimmed"><span class="tree-title"><b>${esc(m.title)}</b> <span class="muted">(completed)</span></span></div>`;
      if (kids.length) {
        h += kids.map(subRowHtml).join('');
      } else {
        h += `<div class="muted" style="margin-left:26px">No sub-headings yet under this main.</div>`;
      }
      h += `<div class="add-line sub" data-addsub="${esc(m.id)}"><span>+ Add Sub-Heading under “${esc(m.title)}”</span></div></div>`;
    }
    if (orphans.length) {
      h += `<div class="tree-main" data-main=""><div class="tree-row dimmed"><span class="tree-title"><b>Other sub-headings</b> <span class="muted">(no matching main)</span></span></div>` +
        orphans.map(subRowHtml).join('') + `</div>`;
    }
    h += `<div class="add-line" id="p2add"><span>+ Add Sub-Heading (choose parent)</span></div>` +
      `<div id="p2form" class="hidden"></div>`;
    el('phase2tree').innerHTML = h;
    el('phase2warn').classList.add('hidden');
    // Rename (pen) + delete-new bindings, mirroring steps12.js:122-129.
    // UI_ISSUES.txt Problem 3: rename also uses the shared floating panel.
    el('phase2tree').querySelectorAll('.tree-row[data-id]').forEach(row => {
      const id = row.getAttribute('data-id');
      const sub = subs.find(s => ((s.id || s.concept_id) === id));
      const rn = row.querySelector('[data-act=rename]');
      if (rn) rn.onclick = (e) => {
        e.stopPropagation();
        if (!sub) return;
        if (window.CogniMapAddHeading && window.CogniMapAddHeading.open) {
          window.CogniMapAddHeading.open({
            title: 'Rename Sub-Heading',
            placeholder: 'Type sub-heading title',
            saveLabel: 'Save',
            initialValue: sub.title,
            onSave(t) { sub.title = t; render(); }
          });
        } else {
          const t = prompt('Rename sub-heading:', sub.title);
          if (t && t.trim()) { sub.title = t.trim(); render(); }
        }
      };
      const dl = row.querySelector('[data-act=del]');
      if (dl) dl.onclick = (e) => {
        e.stopPropagation();
        const ix = subs.indexOf(sub);
        if (ix >= 0) subs.splice(ix, 1);
        render();
      };
    });
    el('phase2tree').querySelectorAll('[data-addsub]').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        showAddForm(btn.getAttribute('data-addsub'));
      };
    });
    const add = el('p2add');
    if (add) add.onclick = () => showAddForm();
  }

  function showAddForm(presetParent) {
    // UI_ISSUES.txt Problem 3: floating centered panel for sub-heading adds
    // (shared #addHeadingModal) replaces the old inline bottom form so typing
    // happens in a clean pretty dialog in the middle, like main-heading adds.
    if (!mains.length) { el('phase2warn').textContent = 'No mains to attach to'; el('phase2warn').classList.remove('hidden'); return; }
    const validPreset = presetParent && mains.some(m => m.id === presetParent) ? presetParent : null;
    const pm = validPreset ? mains.find(m => m.id === validPreset) : null;
    const parents = mains.map(m => ({ id: m.id, title: m.title }));
    if (window.CogniMapAddHeading && window.CogniMapAddHeading.open) {
      window.CogniMapAddHeading.open({
        title: 'Add Sub-Heading',
        subtitle: pm ? `Under “${pm.title}” — pick a parent main below.` : 'Pick a parent main below.',
        placeholder: 'Type new sub-heading title',
        saveLabel: 'Add',
        showParent: true,
        parents,
        presetParent: validPreset,
        onSave(t, pid) {
          if (!pid || !mains.some(m => m.id === pid)) { el('phase2warn').textContent = 'Pick an existing main parent'; el('phase2warn').classList.remove('hidden'); return; }
          const nid = 'u-sub-' + Date.now().toString(36);
          subs.push({ id: nid, concept_id: nid, title: t, kind: 'sub', parent_id: pid, source: 'user_added', explanation_type: 'definition', explanation_text: '', explanation_source: 'user', pages: [], diagram_refs: [], diagram_description: '', _locked: false });
          render();
        }
      });
      return;
    }
    // Fallback when the shared modal is missing: legacy inline form.
    const form = el('p2form');
    if (!form) return;
    // Mains dropdown (no typo-prone prompt(id list)): pick parent explicitly.
    // Per-main "+ Add" preselects that parent; global "+ Add" keeps dropdown free.
    const sel = validPreset;
    form.innerHTML = `<div class="p2-new"><input type="text" id="p2newTitle" placeholder="Sub-heading title"> ` +
      `<select id="p2newParent">` +
      mains.map(m => `<option value="${esc(m.id)}"${m.id === sel ? ' selected' : ''}>${esc(m.title)}</option>`).join('') +
      `</select> <button class="btn sm green-inline" id="p2save">Add</button> ` +
      `<button class="btn sm" id="p2cancel">x</button></div>`;
    form.classList.remove('hidden');
    el('p2save').onclick = () => {
      const t = (el('p2newTitle').value || '').trim();
      const pid = el('p2newParent').value;
      if (!t) { el('phase2warn').textContent = 'Sub-heading title required'; el('phase2warn').classList.remove('hidden'); return; }
      if (!pid || !mains.some(m => m.id === pid)) { el('phase2warn').textContent = 'Pick an existing main parent'; el('phase2warn').classList.remove('hidden'); return; }
      const nid = 'u-sub-' + Date.now().toString(36);
      subs.push({ id: nid, concept_id: nid, title: t, kind: 'sub', parent_id: pid, source: 'user_added', explanation_type: 'definition', explanation_text: '', explanation_source: 'user', pages: [], diagram_refs: [], diagram_description: '', _locked: false });
      render();
    };
    el('p2cancel').onclick = () => { form.classList.add('hidden'); form.innerHTML = ''; };
  }

  function selected() {
    // Locked persisted subs always included (checked-disabled); only new
    // adds respect the checkbox. Backend never discards existing ids, so the
    // UI must not offer deselect — this keeps ceil/Finish/N math consistent.
    const boxes = {};
    document.querySelectorAll('#phase2tree .tree-row[data-id]').forEach(r => {
      const id = r.getAttribute('data-id');
      const box = r.querySelector('[data-act=check]');
      boxes[id] = box ? (box.disabled || box.checked) : true;
    });
    return subs.filter(s => boxes[s.id || s.concept_id] !== false).map(s => {
      return { concept_id: s.id || s.concept_id, title: s.title, kind: 'sub', parent_id: s.parent_id, source: s.source || 'extracted', explanation_type: s.explanation_type, explanation_text: s.explanation_text, explanation_source: s.explanation_source, pages: s.pages, diagram_refs: s.diagram_refs, diagram_description: s.diagram_description };
    }).filter(Boolean);
  }

  async function confirm() {
    const sel = selected();
    if (!sel.length) {
      el('phase2warn').textContent = 'Select at least 1 sub-heading to continue';
      el('phase2warn').classList.remove('hidden');
      return;
    }
    try {
      const j = await api('/api/sessions/' + SID + '/phase2/confirm' + q(), { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subs: sel }) });
      // m2 (Steps_Locks §7 hint): render ≥2-recommended hint inline into
      // #phase2warn (no alert() — blocks demo flow, not styled). Demo: 1-sub
      // Confirm shows inline warning. Keep modal open briefly so the marker
      // sees it, then reload into the new L1-2 sub cycle.
      if (j.hint) {
        el('phase2warn').textContent = j.hint;
        el('phase2warn').classList.remove('hidden');
        setTimeout(() => location.reload(), 1800);
        return;
      }
      el('phase2modal').classList.remove('open');
      // New cycle: refresh all slices (math on subs + new links only).
      location.reload();
    } catch (err) {
      el('phase2warn').textContent = err.message;
      el('phase2warn').classList.remove('hidden');
    }
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    // Problem 4 same root cause: #phase2modal parsed after the old init
    // position. Robust bind + DOMContentLoaded retry + delegated close.
    // UI_ISSUES.txt Problem 1: #phase2Btn reopens the sub-headings list
    // after the popup is cancelled via #phase2X (stage stays Phase2 with
    // the sidebar reopen card visible).
    function bindTrailing() {
      const c = el('phase2Confirm');
      if (c && !c._bound) { c._bound = true; c.onclick = confirm; }
      const x = el('phase2X');
      if (x && !x._bound) { x._bound = true; x.onclick = closeModal; }
      const b = el('phase2Btn');
      if (b && !b._bound) { b._bound = true; b.onclick = open; }
    }
    bindTrailing();
    try { document.addEventListener('DOMContentLoaded', bindTrailing); } catch (e) { /* ignore */ }
    try {
      if (!document._cognimapPhase2Delegated) {
        document._cognimapPhase2Delegated = true;
        document.addEventListener('click', (e) => {
          const t = e.target && e.target.closest ? e.target.closest('#phase2X') : null;
          if (t) { closeModal(); return; }
          const b2 = e.target && e.target.closest ? e.target.closest('#phase2Btn') : null;
          if (b2) { open(); }
        });
      }
    } catch (e) { /* delegation optional */ }
  }

  function closeModal() {
    const m = el('phase2modal');
    if (m) m.classList.remove('open');
    // Keep the Phase2 reopen card visible so the user can return to the
    // sub-headings loop whenever wanted (cancel is safe, never a dead end).
    try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar('Phase2'); } catch (e) { /* sidebar optional */ }
  }

  window.CogniMapPhase2 = { init, open };
})();
