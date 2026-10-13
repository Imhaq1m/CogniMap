// CogniMap Step 0 — graph/panel/modal/progress SHELLS only. No logic.
// Slices add: Steps1-2 modal tree, L1-2 drawer, L3 scenarios, L4 drag-connect, L5 probes.
(function () {
  function qs(s) { return document.querySelector(s); }
  window.CogniMapShell = {
    openPanel: function () { var p = qs('#panel'); if (p) p.classList.add('open'); },
    closePanel: function () { var p = qs('#panel'); if (p) p.classList.remove('open'); },
    openModal: function (title) {
      var m = qs('#modal'); if (!m) return;
      m.classList.add('open');
      var t = qs('#modal-title'); if (t && title) t.textContent = title;
    },
    closeModal: function () { var m = qs('#modal'); if (m) m.classList.remove('open'); },
    setProgress: function (label, pct) {
      var el = qs('#progress'); if (!el) return;
      el.textContent = label + ' ' + pct + '%';
    }
  };
  document.addEventListener('click', function (e) {
    // Gated to [data-node] only (Locks §4 drag-conflict fix): empty-canvas
    // clicks must NOT open the panel — L4 drag-connect uses mousedown→mouseup
    // on [data-l4node], and L1-2 drawer opens via l12.js [data-node] handler.
    var n = e.target && e.target.closest ? e.target.closest('[data-node]') : null;
    // B3 stage gate (skeleton owns): never cover the L4 edge panel with an
    // empty drawer during linking (drag pending or edge panel open).
    if (n) {
      // UI_ISSUES.txt Problem 1 (free move): a node-move drag ends in a click
      // — suppress the panel so rearranging never pops the drawer.
      try {
        if (window.__cognimap_nodeMoved) return;
        if (window.CogniMapNodeMove && window.CogniMapNodeMove.wasMoved && window.CogniMapNodeMove.wasMoved()) return;
      } catch (_e) { /* fall through */ }
      try {
        if (window.CogniMapStage && window.CogniMapStage.isLinkingActive()) return;
      } catch (_e) { /* fall through to open */ }
      window.CogniMapShell.openPanel();
    }
  });
  // B3 single stage-gate helper (skeleton owns, Locks §4+§6).
  // Suppress drawer/verify when stage in (L4, L5) except Phase-2 sub flow.
  // Phase-2 sub flow = phase2 + kind==sub in an active L1-2/L3 loop; the
  // restricted modal owns that path, so the L1-2 drawer must stay usable.
  window.CogniMapStage = {
    DRAWER_LOCKED: ['L4', 'L5'],
    shouldSuppressDrawer: function (stage, opts) {
      opts = opts || {};
      if (opts.phase2SubFlow) return false;
      // Explicit Phase-2 sub exception: subs in phase2 stay drawable even
      // when the session stage reads L4/L5 (mixed workspace, §7).
      if (opts.phase === 'phase2' && opts.kind === 'sub') return false;
      return this.DRAWER_LOCKED.indexOf(stage || '') !== -1;
    },
    shouldSuppressVerify: function (stage, opts) {
      opts = opts || {};
      if (opts.phase2SubFlow) return false;
      // Verify lives only in L1-2; late verifies after advance would append
      // L1-2 trail rows post-hoc (B3). Kind-phase match enforces §7 math:
      // phase1 verifies mains, phase2 verifies subs (mains history-only).
      if ((stage || '') !== 'L1-2') return true;
      if (opts.phase === 'phase2' && opts.kind === 'main') return true;
      if (opts.phase === 'phase1' && opts.kind === 'sub') return true;
      return false;
    },
    isLinkingActive: function () {
      // M2 note: __cognimap_l4_pending is armed on first node click (l4.js)
      // and disarmed on second-node panel open, same-node toggle,
      // empty-canvas click, Esc, Cancel, or Confirm — so this cannot stick
      // true and suppress the L1-2 drawer/history (Locks §9 mid-phase review).
      try {
        var ep = document.getElementById('edgePanel');
        if (ep && !ep.classList.contains('hidden')) return true;
      } catch (_e) { /* ignore */ }
      if (window.__cognimap_l4_pending) return true;
      return false;
    }
  };
  // Problem 2 stage-gated sidebar (Q2-a/b): only the current stage card is
  // visible. materialsCard lives only in steps1-2; filesCard (Studying)
  // stays always so file names remain after Confirm. l12card appears after
  // Confirm (stage L1-2), then L3/L4/L5 one-at-a-time. Phase2 shows its own
  // reopen card (UI_ISSUES.txt Problem 1: closing the sub-headings popup
  // must leave a way back); done hides all stage cards (final map).
  window.CogniMapStage.refreshSidebar = function (stage) {
    function show(id, visible) {
      var n = document.getElementById(id);
      if (!n) return;
      n.classList.toggle('hidden', !visible);
    }
    var s = stage || 'steps1-2';
    show('materialsCard', s === 'steps1-2');
    show('filesCard', true);
    show('l12card', s === 'L1-2');
    show('l3card', s === 'L3');
    show('l4card', s === 'L4');
    show('l5card', s === 'L5');
    show('phase2card', s === 'Phase2');
  };
  // Q2-c: #state JSON hidden behind Debug toggle (still rendered for
  // troubleshooting, never user-visible by default).
  document.addEventListener('DOMContentLoaded', function () {
    var t = document.getElementById('debugToggle');
    var st = document.getElementById('state');
    if (t && st) {
      t.onclick = function () { st.classList.toggle('hidden'); };
    }
  });
  // Problem 5: workspace fills middle + standard graph nav (background-drag
  // pan + wheel zoom + +/-/Reset). ViewBox-based so existing node/edge targets
  // ([data-node]/[data-l4node]/gedge) keep working. Pan starts ONLY on empty
  // background (not on nodes) so L4 node-to-node drag-link is preserved.
  // View persists across repaint via window.__cognimap_view.
  var PAN_BASE_W = 600, PAN_BASE_H = 360;
  function panView() {
    if (!window.__cognimap_view) {
      window.__cognimap_view = { vx: 0, vy: 0, vw: PAN_BASE_W, vh: PAN_BASE_H };
    }
    return window.__cognimap_view;
  }
  function applyView(svg) {
    if (!svg) return;
    var v = panView();
    svg.setAttribute('viewBox', v.vx + ' ' + v.vy + ' ' + v.vw + ' ' + v.vh);
  }
  function zoomAt(svg, clientX, clientY, factor) {
    var v = panView();
    var rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    var nvw = Math.min(1200, Math.max(150, v.vw / factor));
    var nvh = nvw * (PAN_BASE_H / PAN_BASE_W);
    var fx = (clientX - rect.left) / rect.width;
    var fy = (clientY - rect.top) / rect.height;
    var px = v.vx + fx * v.vw;
    var py = v.vy + fy * v.vh;
    v.vw = nvw; v.vh = nvh;
    v.vx = px - fx * nvw;
    v.vy = py - fy * nvh;
    applyView(svg);
  }
  window.CogniMapShell.attachPanZoom = function (svg) {
    if (!svg) return;
    applyView(svg);
    if (svg._pzBound) return;
    svg._pzBound = true;
    // Wheel = zoom around cursor (prevent page scroll while over canvas).
    svg.addEventListener('wheel', function (e) {
      e.preventDefault();
      var f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      var r = svg.getBoundingClientRect();
      var cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
      zoomAt(svg, e.clientX || cx, e.clientY || cy, f);
    }, { passive: false });
    // Background-drag pan (node drag stays link).
    var panning = false, sx = 0, sy = 0, vx0 = 0, vy0 = 0, moved = false;
    svg.addEventListener('mousedown', function (e) {
      try {
        if (e.target && e.target.closest &&
          e.target.closest('[data-l4node],[data-node]')) return;
      } catch (_e) { /* fall through to pan */ }
      if (e.button !== 0 && e.button !== undefined) return;
      var v = panView();
      panning = true; moved = false;
      sx = e.clientX; sy = e.clientY; vx0 = v.vx; vy0 = v.vy;
      svg.classList.add('panning');
    });
    window.addEventListener('mousemove', function (e) {
      if (!panning) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      var v = panView();
      var rect = svg.getBoundingClientRect();
      if (rect.width && rect.height) {
        v.vx = vx0 - dx * v.vw / rect.width;
        v.vy = vy0 - dy * v.vh / rect.height;
        applyView(svg);
      }
    });
    window.addEventListener('mouseup', function () {
      if (!panning) return;
      panning = false;
      svg.classList.remove('panning');
      // A real pan (moved) must not trigger an L5 edge-probe click.
      if (moved) {
        window.__cognimap_panned = true;
        setTimeout(function () { window.__cognimap_panned = false; }, 0);
      }
    });
    // Suppress the click that ends a pan (e.g. starting on an edge).
    svg.addEventListener('click', function (e) {
      if (window.__cognimap_panned) {
        e.stopPropagation();
        e.preventDefault();
        window.__cognimap_panned = false;
      }
    }, true);
    // +/-/Reset overlay buttons (bound per canvas, delegation-safe).
    try {
      var box = svg.closest ? svg.closest('.graph-canvas') : null;
      var root = box || document;
      ['in', 'out', 'reset'].forEach(function (k) {
        var b = root.querySelector('[data-zoom="' + k + '"]');
        if (b && !b._pzBound) {
          b._pzBound = true;
          b.addEventListener('click', function (e) {
            e.stopPropagation();
            var v = panView();
            var r = svg.getBoundingClientRect();
            var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
            if (k === 'in') zoomAt(svg, cx, cy, 1.25);
            else if (k === 'out') zoomAt(svg, cx, cy, 1 / 1.25);
            else { v.vx = 0; v.vy = 0; v.vw = PAN_BASE_W; v.vh = PAN_BASE_H; applyView(svg); }
          });
        }
      });
    } catch (_e) { /* buttons optional */ }
  };
  window.CogniMapShell.resetPanZoom = function () {
    window.__cognimap_view = { vx: 0, vy: 0, vw: PAN_BASE_W, vh: PAN_BASE_H };
    var svg = document.getElementById('graphSvg');
    if (svg) applyView(svg);
  };
  // UI_ISSUES.txt Problem 3: shared floating add/rename heading panel.
  // Centered overlay (#addHeadingModal) used by both main-heading adds
  // (steps12.js) and sub-heading adds (steps12.js + phase2.js), replacing
  // bare prompt() + inline bottom forms with one clean pretty dialog.
  // opts: {title, subtitle, placeholder, saveLabel, showParent,
  //   parents:[{id,title}], presetParent, initialValue, onSave(title,parentId)}.
  (function () {
    var _saveCb = null;
    function els() {
      return {
        modal: document.getElementById('addHeadingModal'),
        title: document.getElementById('addHeadingTitle'),
        sub: document.getElementById('addHeadingSub'),
        wrap: document.getElementById('addHeadingParentWrap'),
        parent: document.getElementById('addHeadingParent'),
        input: document.getElementById('addHeadingInput'),
        msg: document.getElementById('addHeadingMsg'),
        save: document.getElementById('addHeadingSave'),
        cancel: document.getElementById('addHeadingCancel'),
        x: document.getElementById('addHeadingX')
      };
    }
    function esc(s) {
      return String(s ?? '').replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }
    function close() {
      var e = els();
      if (e.modal) e.modal.classList.remove('open');
      _saveCb = null;
    }
    function showMsg(t) {
      var e = els();
      if (!e.msg) return;
      if (!t) { e.msg.textContent = ''; e.msg.classList.add('hidden'); return; }
      e.msg.textContent = t;
      e.msg.classList.remove('hidden');
    }
    function bindOnce() {
      var e = els();
      if (!e.modal || e.modal._ahBound) return;
      e.modal._ahBound = true;
      function onSaveClick() {
        var d = els();
        if (!_saveCb) { close(); return; }
        var title = (d.input ? d.input.value : '').trim();
        if (!title) { showMsg('Please type a heading title.'); if (d.input) d.input.focus(); return; }
        var pid = null;
        if (d.wrap && !d.wrap.classList.contains('hidden') && d.parent) pid = d.parent.value || null;
        showMsg('');
        var cb = _saveCb;
        close();
        try { cb(title, pid); } catch (_err) { /* caller handles */ }
      }
      if (e.save) e.save.onclick = function (ev) { if (ev) ev.stopPropagation(); onSaveClick(); };
      function onCancel(ev) { if (ev) ev.stopPropagation(); showMsg(''); close(); }
      if (e.cancel) e.cancel.onclick = onCancel;
      if (e.x) e.x.onclick = onCancel;
      e.modal.addEventListener('mousedown', function (ev) {
        if (ev.target === e.modal) onCancel(ev);
      });
      document.addEventListener('keydown', function (ev) {
        try {
          if (!e.modal.classList.contains('open')) return;
          if (ev.key === 'Escape') { ev.stopPropagation(); onCancel(ev); }
          else if (ev.key === 'Enter' && document.activeElement === els().input) {
            ev.preventDefault();
            onSaveClick();
          }
        } catch (_err) { /* ignore */ }
      });
      if (e.input) e.input.addEventListener('input', function () { showMsg(''); });
    }
    window.CogniMapAddHeading = {
      open: function (opts) {
        opts = opts || {};
        bindOnce();
        var e = els();
        // Fallback to prompt() only when the shared modal is missing
        // (e.g. unit HTML without workspace_page) so adds never dead-end.
        if (!e.modal || !e.input) {
          var fb = null;
          try { fb = prompt(opts.title || 'Heading title:', opts.initialValue || ''); } catch (_err) { fb = null; }
          if (fb && fb.trim() && opts.onSave) opts.onSave(fb.trim(), opts.presetParent || null);
          return;
        }
        // Second fallback bind for late-parsed modal (Problem 4 pattern).
        bindOnce();
        if (e.title) e.title.textContent = opts.title || 'Add heading';
        if (e.sub) {
          if (opts.subtitle) { e.sub.textContent = opts.subtitle; e.sub.classList.remove('hidden'); }
          else { e.sub.textContent = ''; e.sub.classList.add('hidden'); }
        }
        if (e.input) {
          e.input.placeholder = opts.placeholder || 'Type heading title';
          e.input.value = opts.initialValue || '';
        }
        if (e.save) e.save.textContent = opts.saveLabel || 'Add';
        var parents = opts.parents || [];
        if (opts.showParent && parents.length && e.wrap && e.parent) {
          e.wrap.classList.remove('hidden');
          e.parent.innerHTML = parents.map(function (m) {
            var sel = (m.id === opts.presetParent) ? ' selected' : '';
            return '<option value="' + esc(m.id) + '"' + sel + '>' + esc(m.title) + '</option>';
          }).join('');
          if (opts.presetParent) e.parent.value = opts.presetParent;
        } else if (e.wrap) {
          e.wrap.classList.add('hidden');
        }
        showMsg('');
        _saveCb = (typeof opts.onSave === 'function') ? opts.onSave : null;
        e.modal.classList.add('open');
        setTimeout(function () {
          try {
            e.input.focus();
            if (opts.initialValue) e.input.select();
          } catch (_err) { /* focus optional */ }
        }, 0);
      },
      close: close
    };
  })();
})();
