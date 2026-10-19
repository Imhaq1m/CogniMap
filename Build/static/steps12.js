// CogniMap Step 1 — Extracted Concepts modal (Locks §1, §6).
// Tree + checkboxes + rename (pen) + add lines + delete pre-Confirm +
// blue user_added styling + source flag + Confirm lock warning (§6.1).
// Workspace merge shows mains only (Phase 1). No logic beyond Step 1.
(function () {
  let UID = 0, SID = '', pending = [], confirmed = false;
  let _ctr = 0;

  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function uid(p) { return p + '-' + Date.now().toString(36) + (_ctr++); }
  function q() { return '?user_id=' + encodeURIComponent(UID); }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const t = await r.text();
    let j = {};
    try { j = JSON.parse(t); } catch (e) { j = { detail: t }; }
    if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
    return j;
  }

  async function refreshFiles() {
    const st = await api('/api/sessions/' + SID + '/state' + q());
    // Locks §0 file list: one row per filename; sessions.file mirrors primary.
    let files = [];
    try { files = await api('/api/sessions/' + SID + '/files' + q()); }
    catch (e) {
      const f = (st.session && st.session.file) || '';
      files = f ? [{ filename: f }] : [];
    }
    el('files').innerHTML = files.length
      ? files.map(f =>
        `<div class="file-row"><span>${esc(f.filename)}</span>` +
        `<button class="icon-btn" data-rmfile="${esc(f.filename)}" title="remove file">x</button></div>`).join('')
      : '<p>No file yet.</p>';
    // Locks §6 L1-3 read-only: upload/extract live only in steps1-2.
    // Backend 400s post-lock; UI mirrors so Confirm greys them out.
    const locked = !st.session || (st.session.stage || '') !== 'steps1-2';
    el('extBtn').disabled = !files.length || locked;
    if (el('selBtn')) el('selBtn').disabled = locked;
    // Problem 2 stage gate: only current sidebar card visible (materials in
    // steps1-2 only; filesCard always for persistent names post-lock).
    try {
      if (window.CogniMapStage && window.CogniMapStage.refreshSidebar)
        window.CogniMapStage.refreshSidebar(st.session && st.session.stage);
    } catch (e) { /* sidebar optional */ }
    el('files').querySelectorAll('[data-rmfile]').forEach(btn => {
      btn.onclick = async () => {
        const name = btn.getAttribute('data-rmfile');
        // Locks §6: per-file remove keeps data while files remain;
        // removing the last file full-wipes (clear_session_data).
        const j = await api('/api/sessions/' + SID + '/file?filename=' + encodeURIComponent(name) + '&user_id=' + encodeURIComponent(UID), { method: 'DELETE' });
        if (j && j.reset) {
          // Locks §0+§6 reset cascade: backend wiped concepts/links/trail +
          // stage→steps1-2, but l3progress/l4status/l5progress slices would
          // show stale % — full reload like phase2.js does.
          pending = []; confirmed = false;
          location.reload();
          return;
        }
        refreshFiles(); refreshState();
      };
    });
    renderGraph(st.counts ? await api('/api/sessions/' + SID + '/concepts' + q()) : []);
  }

  async function refreshState() {
    const st = await api('/api/sessions/' + SID + '/state' + q());
    // Q2-c: still rendered but hidden behind Debug toggle (never visible).
    el('state').innerHTML = '<pre>' + esc(JSON.stringify(st, null, 2)) + '</pre>';
  }

  function renderGraph(concepts) {
    // M1 single paint owner (Locks §7): L4 owns the canvas (SVG nodes + ordered
    // edges + mixed-workspace dim). Steps12 never paints over it — delegate to
    // L4 when available so Phase-2 file-refreshes can't clobber subs/mains.
    // Pre-Confirm fallback (L4 status 404/empty) keeps mains-only chips.
    try {
      if (window.CogniMapL4 && window.CogniMapL4.refresh) {
        window.CogniMapL4.refresh();
        return;
      }
    } catch (e) { /* fall through to fallback */ }
    // store rows use lowercase keys: kind/title/source
    const list = (concepts || []).filter(c => c.kind === 'main');
    const g = el('graph');
    if (!list.length) { g.textContent = 'Graph canvas — mains render here after Confirm (Phase 1 mains-only)'; return; }
    g.innerHTML = '<div class="graph-nodes">' + list.map(c =>
      `<span class="gnode${c.source === 'user_added' ? ' blue' : ''}" data-node="${esc(c.id)}" title="Open definition panel">${esc(c.title)}</span>`).join('') + '</div>';
  }

  function rowHtml(c, isSub) {
    const blue = c.source === 'user_added' ? ' row-user' : ' row-extracted';
    // Locks §6: Deselect (uncheck, excluded from Confirm but row kept) ≠ Delete.
    // Both mains and subs respect the checkbox (Steps_Details: each main and
    // sub has a checkbox to select/deselect). Unchecked main excluded from
    // Confirm (row kept); unchecked sub excluded from Confirm (row kept).
    // Orphan guard in selectedPayload(): subs of unselected mains are still
    // excluded (parent_id orphans forbidden per §6). §7 never-discard applies
    // post-Confirm (confirmed subs persist hidden via kind-filter, preselected
    // in Phase-2) — not a pre-Confirm forced-check.
    return `<div class="tree-row${isSub ? ' sub' : ''}${blue}" data-id="${esc(c.concept_id || c.id)}">
      <input type="checkbox" data-act="check" ${c._checked === false ? '' : 'checked'}>
      <span class="tree-title" data-act="title">${esc(c.title)}</span>
      <button class="icon-btn" data-act="rename" title="rename">✎</button>
      <button class="icon-btn" data-act="del" title="delete pre-Confirm">x</button>
    </div>`;
  }

  function renderTree() {
    const mains = pending.filter(c => c.kind === 'main');
    let h = '';
    for (const m of mains) {
      h += `<div class="tree-main" data-main="${esc(m.concept_id || m.id)}">` + rowHtml(m, false);
      const subs = pending.filter(c => c.kind === 'sub' && c.parent_id === (m.concept_id || m.id));
      for (const s of subs) h += rowHtml(s, true);
      h += `<div class="add-line sub" data-addsub="${esc(m.concept_id || m.id)}"><span>+ Add Sub-Heading</span></div></div>`;
    }
    el('tree').innerHTML = h || '<p>No concepts — extract or add a main heading.</p>';
  }

  function findId(id) { return pending.find(c => (c.concept_id || c.id) === id); }

  // UI_ISSUES.txt Problem 3: floating centered panel for add/rename.
  // Shared #addHeadingModal (graph.js CogniMapAddHeading) replaces bare
  // prompt() so typing happens in a clean pretty dialog in the middle.
  function mainParents(preset) {
    return pending.filter(c => c.kind === 'main')
      .map(m => ({ id: (m.concept_id || m.id), title: m.title }));
  }
  function openHeadingDialog(opts) {
    if (window.CogniMapAddHeading && window.CogniMapAddHeading.open) {
      window.CogniMapAddHeading.open(opts);
      return;
    }
    const fb = prompt(opts.title + ':', opts.initialValue || '');
    if (fb && fb.trim() && opts.onSave) opts.onSave(fb.trim(), opts.presetParent || null);
  }

  function bindTree() {
    el('tree').onclick = (e) => {
      const btn = e.target.closest('[data-act]');
      const add = e.target.closest('[data-addsub]');
      if (add) {
        const pid = add.getAttribute('data-addsub');
        const pm = pending.find(c => (c.concept_id || c.id) === pid);
        openHeadingDialog({
          title: 'Add Sub-Heading',
          subtitle: pm ? `Under “${pm.title}” — pick a parent main below.` : 'Pick a parent main below.',
          placeholder: 'Type new sub-heading title',
          saveLabel: 'Add',
          showParent: true,
          parents: mainParents(pid),
          presetParent: pid,
          onSave(t, parentId) {
            pending.push({ concept_id: uid('u-sub'), title: t, kind: 'sub', parent_id: parentId || pid, source: 'user_added', explanation_type: 'definition', explanation_text: '', explanation_source: 'user', pages: [], diagram_refs: [], diagram_description: '' });
            renderTree();
          }
        });
        return;
      }
      if (!btn) return;
      const row = e.target.closest('.tree-row');
      const c = findId(row.getAttribute('data-id'));
      if (!c) return;
      const act = btn.getAttribute('data-act');
      if (act === 'check') c._checked = btn.checked;
      // Locks §6: deleting a main cascades to its subs (confirm prompt,
      // parent_id orphans forbidden); deleting a sub removes that row only.
      // Deselect (uncheck, row kept) ≠ delete (x, row removed).
      if (act === 'del') {
        const cid = row.getAttribute('data-id');
        if (c.kind === 'main') {
          const kids = pending.filter(x => x.kind === 'sub' && (x.parent_id === cid));
          if (!confirm(`Delete main heading "${c.title}" and its ${kids.length} sub-heading(s)?`)) return;
          const kill = new Set([cid, ...kids.map(k => (k.concept_id || k.id))]);
          pending = pending.filter(x => !kill.has(x.concept_id || x.id));
        } else {
          pending = pending.filter(x => x !== c);
        }
      }
      if (act === 'rename') {
        openHeadingDialog({
          title: c.kind === 'sub' ? 'Rename Sub-Heading' : 'Rename Main Heading',
          placeholder: 'Type heading title',
          saveLabel: 'Save',
          initialValue: c.title,
          onSave(t) { c.title = t; renderTree(); }
        });
        return;
      }
      if (act === 'title' && e.detail === 2) {
        openHeadingDialog({
          title: c.kind === 'sub' ? 'Rename Sub-Heading' : 'Rename Main Heading',
          placeholder: 'Type heading title',
          saveLabel: 'Save',
          initialValue: c.title,
          onSave(t) { c.title = t; renderTree(); }
        });
        return;
      }
      renderTree();
    };
    el('addMain').onclick = () => {
      openHeadingDialog({
        title: 'Add Main Heading',
        subtitle: 'Type the new main heading below.',
        placeholder: 'Type new main heading title',
        saveLabel: 'Add',
        onSave(t) {
          pending.push({ concept_id: uid('u-main'), title: t, kind: 'main', parent_id: null, source: 'user_added', explanation_type: 'definition', explanation_text: '', explanation_source: 'user', pages: [], diagram_refs: [], diagram_description: '' });
          renderTree();
        }
      });
    };
  }

  function selectedPayload() {
    // Locks §6 (Deselect ≠ Delete) + §1/§6 parent integrity: mains respect the
    // checkbox (unchecked main excluded, row kept); subs respect the checkbox
    // too (unchecked sub excluded, row kept). Orphan guard: subs of unselected
    // mains are excluded (parent_id orphans forbidden per §6). §7 kind-filter
    // hides confirmed subs from Phase-1 math; it does not force-select them
    // pre-Confirm.
    const checkedMains = new Set(
      pending.filter(c => (c.kind || 'main') !== 'sub' && c._checked !== false)
        .map(c => (c.concept_id || c.id))
    );
    return pending.filter(c => {
      if ((c.kind || 'main') === 'sub') return c._checked !== false && checkedMains.has(c.parent_id);
      return c._checked !== false;
    }).map(c => {
      const o = { ...c }; delete o._checked; return o;
    });
  }

  function showFileWarn(msg) {
    // Major 3 (Locks §0/§6): warnBox lives inside closed #modal pre-Confirm,
    // so upload/extract failures were invisible. Mirror them to the sidebar
    // #fileWarn toast (always visible); keep modal warnBox for Confirm path.
    try {
      const f = el('fileWarn');
      if (f) { f.textContent = msg; f.classList.remove('hidden'); }
    } catch (e) { /* sidebar optional */ }
    try {
      const w = el('warnBox');
      if (w) { w.textContent = msg; w.classList.remove('hidden'); }
    } catch (e) { /* modal optional */ }
  }
  function clearFileWarn() {
    try {
      const f = el('fileWarn');
      if (f) { f.textContent = ''; f.classList.add('hidden'); }
    } catch (e) { /* ignore */ }
  }

  async function doUpload(label) {
    const name = (label || '').trim() || 'lecture.pdf';
    try {
      await api('/api/sessions/' + SID + '/upload' + q(), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: name }) });
      clearFileWarn();
    } catch (e) {
      showFileWarn(e.message);
      throw e;
    }
    refreshFiles(); refreshState();
  }

  async function doUploadBytes(fileObj) {
    // S1 additive: real PDF bytes -> POST /upload-pdf multipart (disk +
    // live parse). Falls back to label-only /upload on any failure so the
    // frozen stub path never breaks. session_files stays filename-only.
    const name = (fileObj && fileObj.name) || 'upload.pdf';
    try {
      const fd = new FormData();
      fd.append('file', fileObj, name);
      const r = await fetch('/api/sessions/' + SID + '/upload-pdf' + q(), { method: 'POST', body: fd });
      const t = await r.text();
      let j = {};
      try { j = JSON.parse(t); } catch (e) { j = { detail: t }; }
      if (!r.ok) throw new Error(j.detail || ('HTTP ' + r.status));
      clearFileWarn();
    } catch (e) {
      // Fallback: label-only frozen route (keyless demo, non-PDF, no multipart).
      await doUpload(name);
      return;
    }
    refreshFiles(); refreshState();
  }

  async function init(userId, sessionId) {
    UID = userId; SID = sessionId;
    // Q2-c backup binding (graph.js also binds on DOMContentLoaded).
    try {
      const _dt = el('debugToggle'), _st = el('state');
      if (_dt && _st && !_dt._bound) { _dt._bound = true; _dt.onclick = () => _st.classList.toggle('hidden'); }
    } catch (e) { /* debug optional */ }
    // Details Step 1 "Select Files" UX (§0/§8 stub-compliant): file picker
    // sends just the filename to the same stub endpoint (zero schema change).
    // Prompt kept as fallback when picker unavailable/cancelled.
    const picker = el('filePick');
    if (picker) {
      picker.onchange = async () => {
        const f = picker.files && picker.files[0];
        if (!f) return;
        try {
          if (f.name && f.name.toLowerCase().endsWith('.pdf') && f.size > 0) { await doUploadBytes(f); }
          else { await doUpload(f.name); }
        } catch (e) {
          // doUpload already mirrored to sidebar #fileWarn + modal warnBox.
        }
        picker.value = '';
      };
    }
    el('selBtn').onclick = async () => {
      if (picker) { picker.click(); return; }
      const label = prompt('File label (LlamaParse stub, no real upload):', 'lecture.pdf');
      if (label === null) return;
      try { await doUpload(label); } catch (e) { /* mirrored to sidebar toast */ }
    };
    el('extBtn').onclick = async () => {
      try {
        el('warnBox').classList.add('hidden');
        clearFileWarn();
        const j = await api('/api/sessions/' + SID + '/extract' + q(), { method: 'POST' });
        pending = (j.concepts || []).map(c => ({ ...c, _checked: true }));
        confirmed = false;
        el('lockBox').classList.add('hidden');
        renderTree();
        // S7: stub banner (additive, locked flows unchanged) — extra keys only.
        try {
          if ((j.mode || 'stub') === 'stub') {
            el('warnBox').textContent = j.warning || 'Demo mode — stubbed, not live.';
            el('warnBox').classList.remove('hidden');
          }
        } catch (e) { /* banner optional */ }
        window.CogniMapShell.openModal('Extracted Concepts');
      } catch (err) {
        // Pre-Confirm the modal is closed, so mirror to the sidebar toast.
        showFileWarn(err.message);
      }
    };
    el('modalX').onclick = () => window.CogniMapShell.closeModal();
    el('confirmSel').onclick = () => {
      const sel = selectedPayload();
      if (!sel.some(c => c.kind === 'main')) {
        el('warnBox').textContent = 'Select at least 1 main heading to continue';
        el('warnBox').classList.remove('hidden');
        return;
      }
      el('warnBox').classList.add('hidden');
      el('lockBox').classList.remove('hidden');
    };
    el('lockBack').onclick = () => el('lockBox').classList.add('hidden');
    // Problem 4: Continue only closes (Q4-a, no refresh). Robust binding so it
    // always closes even if init ever runs before #l12guide parses (old order):
    // direct bind + DOMContentLoaded retry + delegated fallback + re-bind on show.
    function bindL12Guide() {
      const _gc = el('l12guideContinue');
      const _g = el('l12guide');
      if (_gc && _g && !_gc._bound) {
        _gc._bound = true;
        _gc.onclick = () => _g.classList.remove('open');
      }
    }
    try {
      if (!document._cognimapL12guideDelegated) {
        document._cognimapL12guideDelegated = true;
        document.addEventListener('click', (e) => {
          const t = e.target && e.target.closest ? e.target.closest('#l12guideContinue') : null;
          if (t) {
            const _g2 = el('l12guide');
            if (_g2) _g2.classList.remove('open');
          }
        });
      }
    } catch (e) { /* delegation optional */ }
    try { document.addEventListener('DOMContentLoaded', bindL12Guide); } catch (e) { /* ignore */ }
    el('lockConfirm').onclick = async () => {
      try {
        const j = await api('/api/sessions/' + SID + '/confirm-selection' + q(), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ concepts: selectedPayload() }) });
        confirmed = true;
        el('lockBox').classList.add('hidden');
        window.CogniMapShell.closeModal();
        const concepts = await api('/api/sessions/' + SID + '/concepts' + q());
        renderGraph(concepts); refreshFiles(); refreshState();
        // L1-2 guide (Steps_Details L1-2 §1 + Order Step 3): Remember/Understand
        // modal with Continue immediately after Confirm, before mains-only graph work.
        try { bindL12Guide(); } catch (e) { /* binding optional */ }
        const g = el('l12guide');
        if (g) g.classList.add('open');
      } catch (err) {
        el('warnBox').textContent = err.message;
        el('warnBox').classList.remove('hidden');
      }
    };
    bindL12Guide();
    bindTree(); refreshFiles(); refreshState();
  }

  window.CogniMapSteps12 = { init };
})();
