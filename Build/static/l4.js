// CogniMap Step 4 — L4 Analyze (Locks §4).
// Drag-only connect (press-hold-drag shows a live ghost arrow) + edge panel
// (8 presets incl. consists of + custom) + mid-line labels + canvas
// click-to-select delete popup (no link list) + Finish gate + n=1 auto-pass
// + §6.2 warning.
(function () {
  let SID = '', UID = 0, pendingFrom = null, pendingTo = null, cacheConcepts = [], cacheLinks = [], currentStage = '', selectedLinkId = null;
  const PRESETS = ["causes","leads to","depends on","includes","contrasts with","applied in","influences","consists of"];
  // UI_ISSUES.txt Problem 1: every link type has its own color.
  const EDGE_COLORS = {
    "causes": "#800000",         // maroon
    "leads to": "#2563eb",       // blue
    "depends on": "#16a34a",     // green
    "includes": "#f97316",       // orange
    "contrasts with": "#dc2626", // red
    "applied in": "#1e3a8a",     // navy
    "influences": "#9333ea",     // purple
    "consists of": "#166534",    // dark green
  };
  const CUSTOM_COLOR = "#9ca3af"; // grey (custom)
  const DIMMED_BLUE = "#5a7fa6";  // dimmed blue (drag ghost arrow)
  function edgeSlug(t) {
    return String(t ?? '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'custom';
  }
  function edgeColor(t) {
    const k = String(t ?? '').toLowerCase().trim();
    return EDGE_COLORS[k] || CUSTOM_COLOR;
  }
  function edgeMarkerId(t, dim) {
    if (dim) return 'cogArrow';
    const k = String(t ?? '').toLowerCase().trim();
    if (EDGE_COLORS[k]) return 'cogArrow-' + edgeSlug(k);
    return 'cogArrow-custom';
  }
  try { window.CogniMapEdgeColors = { EDGE_COLORS, CUSTOM_COLOR, DIMMED_BLUE, edgeColor, edgeSlug, edgeMarkerId }; } catch (_e) { /* expose for L5 */ }

  // UI_ISSUES.txt Problem 1 (free move): persistent node positions so user
  // rearrangements survive repaint + reload. Frontend-only (models frozen):
  // in-memory window.__cognimap_nodePos + localStorage per session SID.
  // Links read positions live, so they adjust automatically when nodes move.
  const POS_MIN_X = -500, POS_MAX_X = 1100, POS_MIN_Y = -500, POS_MAX_Y = 860;
  function posKey() { return 'cognimap-pos-' + (SID || ''); }
  function clampPos(x, y) {
    let nx = Number(x), ny = Number(y);
    if (!isFinite(nx)) nx = 300;
    if (!isFinite(ny)) ny = 168;
    nx = Math.max(POS_MIN_X, Math.min(POS_MAX_X, Math.round(nx)));
    ny = Math.max(POS_MIN_Y, Math.min(POS_MAX_Y, Math.round(ny)));
    return { x: nx, y: ny };
  }
  function loadPositions() {
    // In-memory first (fast path within a page load).
    try {
      if (window.__cognimap_nodePos && window.__cognimap_nodePos._sid === SID) {
        return window.__cognimap_nodePos.map;
      }
    } catch (_e) { /* fall through to storage */ }
    let map = {};
    try {
      const raw = localStorage.getItem(posKey());
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          Object.keys(parsed).forEach(k => {
            const v = parsed[k];
            if (v && isFinite(Number(v.x)) && isFinite(Number(v.y))) {
              map[k] = clampPos(v.x, v.y);
            }
          });
        }
      }
    } catch (_e) { /* storage unavailable — memory only */ }
    try { window.__cognimap_nodePos = { _sid: SID, map }; } catch (_e) { /* ignore */ }
    return map;
  }
  function savePositions(map) {
    map = map || {};
    try { window.__cognimap_nodePos = { _sid: SID, map }; } catch (_e) { /* ignore */ }
    try { localStorage.setItem(posKey(), JSON.stringify(map)); } catch (_e) { /* memory only */ }
  }
  function getSavedPos(id) {
    const m = loadPositions();
    return m[id] || null;
  }
  function setSavedPos(id, x, y) {
    const m = loadPositions();
    m[id] = clampPos(x, y);
    savePositions(m);
  }
  function prunePositions(visibleIds) {
    const m = loadPositions();
    const keep = new Set(visibleIds || []);
    let changed = false;
    Object.keys(m).forEach(k => { if (!keep.has(k)) { delete m[k]; changed = true; } });
    if (changed) savePositions(m);
    return m;
  }
  function markNodeMoved() {
    // Suppress the click that ends a node-move drag so it does NOT open the
    // drawer/panel (mirrors __cognimap_panned for background pan, but with a
    // 300ms window so the queued click reliably sees the flag before it
    // clears — plain clicks never set this flag).
    try {
      window.__cognimap_nodeMoved = true;
      setTimeout(function () { window.__cognimap_nodeMoved = false; }, 300);
    } catch (_e) { /* flag optional */ }
  }
  function wasNodeMoved() {
    try { return !!window.__cognimap_nodeMoved; } catch (_e) { return false; }
  }
  try {
    window.CogniMapNodeMove = {
      wasMoved: wasNodeMoved, markMoved: markNodeMoved,
      getPos: function (id) { try { return getSavedPos(id); } catch (_e) { return null; } },
      reset: function () {
        try { localStorage.removeItem(posKey()); } catch (_e) { /* ignore */ }
        try { window.__cognimap_nodePos = { _sid: SID, map: {} }; } catch (_e) { /* ignore */ }
        try { refresh(); } catch (_e) { /* refresh optional */ }
      }
    };
  } catch (_e) { /* expose optional */ }

  // Fluid animation helpers (snappy + precise): rAF smoothing for drag,
  // FLIP glide for repaints/reset/revert. All disabled under
  // prefers-reduced-motion (instant, as before).
  function prefersReducedMotion() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (_e) { return false; }
  }
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  // Tween a single node + its incident edges from (fx,fy) to (tx,ty).
  // Uses moveNodeLive per frame so edges stay glued. Quiet (no glow).
  function tweenNodeTo(id, fx, fy, tx, ty, durMs) {
    try {
      if (prefersReducedMotion() || !durMs || durMs <= 0) { moveNodeLiveRef(id, tx, ty, true); return null; }
      const start = (window.performance && window.performance.now) ? window.performance.now() : Date.now();
      const tok = { cancelled: false };
      const step = function (now) {
        if (tok.cancelled) return;
        const t = Math.max(0, Math.min(1, ((now || Date.now()) - start) / durMs));
        const k = easeOutCubic(t);
        moveNodeLiveRef(id, fx + (tx - fx) * k, fy + (ty - fy) * k, true);
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      return tok;
    } catch (_e) { return null; }
  }
  // FLIP glide after a full repaint: nodes slide from old centers to new.
  // oldMap: {id:{x,y}} captured before innerHTML. New positions read live.
  function flipGlide(oldMap, durMs) {
    try {
      if (prefersReducedMotion()) return;
      if (!oldMap) return;
      durMs = durMs || 200;
      const svg = document.querySelector('#graph #graphSvg');
      if (!svg) return;
      const jobs = [];
      Object.keys(oldMap).forEach(function (id) {
        let cur = null;
        try {
          const nodes = svg.querySelectorAll('g.gnode[data-node]');
          for (const nn of nodes) {
            if (nn.getAttribute('data-node') === id) {
              const cc = nn.querySelector('circle');
              if (cc) cur = { x: parseFloat(cc.getAttribute('cx')), y: parseFloat(cc.getAttribute('cy')) };
              break;
            }
          }
        } catch (_e) { cur = null; }
        const old = oldMap[id];
        if (!cur || !old || !isFinite(cur.x) || !isFinite(old.x)) return;
        const dx = old.x - cur.x, dy = old.y - cur.y;
        if (Math.hypot(dx, dy) < 1) return;
        // Start at old spot, glide to new (quiet: no dragging glow).
        moveNodeLiveRef(id, old.x, old.y, true);
        jobs.push({ id, fx: old.x, fy: old.y, tx: cur.x, ty: cur.y });
      });
      if (!jobs.length) return;
      const start = (window.performance && window.performance.now) ? window.performance.now() : Date.now();
      const step = function (now) {
        const t = Math.max(0, Math.min(1, ((now || Date.now()) - start) / durMs));
        const k = easeOutCubic(t);
        jobs.forEach(function (j) {
          moveNodeLiveRef(j.id, j.fx + (j.tx - j.fx) * k, j.fy + (j.ty - j.fy) * k, true);
        });
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    } catch (_e) { /* glide optional */ }
  }
  // Forward ref filled once bindNodes defines the real moveNodeLive.
  // Allows paintGraph/reset (defined earlier) to call the live updater.
  let moveNodeLiveRef = function () { /* replaced by bindNodes */ };

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
  function title(id) {
    const c = cacheConcepts.find(x => x.id === id);
    return c ? c.title : id;
  }

  async function refresh() {
    let concepts = [];
    try { concepts = await api('/api/sessions/' + SID + '/concepts' + q()); } catch (e) { return; }
    cacheConcepts = concepts;
    let st = null;
    try { st = await api('/api/sessions/' + SID + '/l4/status' + q()); } catch (e) { return; }
    // Stage-aware frozen UI (Locks §5/§6.3): hide deletes + block drag when
    // graph frozen (L5/done/Phase2). Backend already 400s; UI must not mislead.
    try {
      const sst = await api('/api/sessions/' + SID + '/state' + q());
      currentStage = (sst.session && sst.session.stage) || '';
    } catch (e) { currentStage = ''; }
    // Problem 2: only current stage card visible (L4 card only in L4).
    try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar(currentStage); } catch (e) { /* sidebar optional */ }
    // Problem 1: leaving L4 (or never entering it) must disarm any pending
    // link silently so L1-2/L3 clicks open the drawer, never the edge panel.
    if (!canLink()) { clearLinkArmed(); clearSelection(); }
    cacheLinks = (st.links || []).slice();
    paintGraph(concepts, st);
    paintStatus(st);
    // L5 dim runs on the canvas edges directly (no link list).
    try { if (window.CogniMapL5 && window.CogniMapL5.refresh) window.CogniMapL5.refresh(); }
    catch (e) { /* L5 optional */ }
  }

  function isFrozen() {
    return currentStage === 'L5' || currentStage === 'done' || currentStage === 'Phase2';
  }

  function canLink() {
    // UI_ISSUES.txt Problem 1: linking lives only in L4. Every other stage
    // (steps1-2, L1-2, L3, L5/done/Phase2) silently ignores drag/click-link
    // so the L1-2 drawer keeps working. Backend enforces the same gate.
    return currentStage === 'L4';
  }

  function clearLinkArmed() {
    pendingFrom = pendingTo = null;
    try { window.__cognimap_l4_pending = false; } catch (_e) { /* ignore */ }
    try {
      const ep = document.getElementById('edgePanel');
      if (ep) ep.classList.add('hidden');
    } catch (_e) { /* ignore */ }
  }

  function findLink(lid) {
    return (cacheLinks || []).find(L => L.id === lid) || null;
  }

  function ensureSelectedPanel() {
    let p = document.getElementById('edgeSelectedPanel');
    if (p) return p;
    p = document.createElement('div');
    p.id = 'edgeSelectedPanel';
    p.className = 'hidden';
    p.innerHTML = `<div class="modal-head"><h4 id="edgeSelectedTitle">Link</h4>` +
      `<button class="btn sm" id="edgeSelectedX">x</button></div>` +
      `<div id="edgeSelectedSub" class="muted"></div>` +
      `<div id="edgeSelectedMsg"></div>` +
      `<div class="modal-foot"><button class="btn sm" id="edgeSelectedDelete">Delete link</button></div>`;
    document.body.appendChild(p);
    const x = p.querySelector('#edgeSelectedX');
    if (x) x.onclick = () => clearSelection();
    const del = p.querySelector('#edgeSelectedDelete');
    if (del) del.onclick = () => deleteSelected();
    return p;
  }

  function clearSelection() {
    selectedLinkId = null;
    try {
      const p = document.getElementById('edgeSelectedPanel');
      if (p) p.classList.add('hidden');
    } catch (_e) { /* ignore */ }
    try {
      document.querySelectorAll('#graph g.gedge.selected').forEach(gr => gr.classList.remove('selected'));
    } catch (_e) { /* ignore */ }
  }

  function openSelection(lid) {
    if (!canLink()) return;
    const L = findLink(lid);
    if (!L) return;
    selectedLinkId = lid;
    try {
      document.querySelectorAll('#graph g.gedge[data-link]').forEach(gr => {
        gr.classList.toggle('selected', gr.getAttribute('data-link') === lid);
      });
    } catch (_e) { /* highlight optional */ }
    const p = ensureSelectedPanel();
    try {
      const t = p.querySelector('#edgeSelectedTitle');
      if (t) t.textContent = 'Link selected';
      const s = p.querySelector('#edgeSelectedSub');
      if (s) {
        const dot = `<span class="link-dot" style="background:${edgeColor(L.edge_type)}"></span>`;
        s.innerHTML = `${dot}<span class="mid-label">[${esc(title(L.a_id))}] → [${esc(L.edge_type)}] → [${esc(title(L.b_id))}]</span>`;
      }
      const m = p.querySelector('#edgeSelectedMsg');
      if (m) m.textContent = '';
      p.classList.remove('hidden');
    } catch (_e) { /* popup optional */ }
  }

  async function deleteSelected() {
    if (!selectedLinkId) return;
    if (!canLink()) { clearSelection(); return; }
    const lid = selectedLinkId;
    try {
      const j = await api('/api/sessions/' + SID + '/l4/links/' + lid + q(), { method: 'DELETE' });
      clearSelection();
      paintStatus(j.status); refresh();
    } catch (err) {
      try {
        const p = document.getElementById('edgeSelectedPanel');
        const m = p && p.querySelector('#edgeSelectedMsg');
        if (m) m.textContent = err.message;
        else el('l4status').textContent = err.message;
      } catch (_e) { el('l4status').textContent = err.message; }
    }
  }

  function paintGraph(concepts, st) {
    const g = el('graph');
    if (!g) return;
    // Locks §3/§4 Phase 1: workspace mains-only (subs hidden from math/display).
    // Phase 2 (§7): mixed workspace — mains dimmed/completed + subs active;
    // both clickable because L4 allows sub-sub + sub-main edges.
    // B1 canvas owner (Locks §0+§4): one SVG canvas renders nodes + ordered
    // (from,to,type) edges with mid-line labels + dim/bright. Ordered store
    // kept server-side for display/probe; deletes happen via canvas
    // click-to-select popup (no link list).
    const counted = new Set(st.counted || []);
    const phase = st.phase || 'phase1';
    const visible = phase === 'phase1' ? concepts.filter(c => counted.has(c.id)) : concepts;
    const n = visible.length;
    const CX = 300, CY = 168, R = n <= 1 ? 0 : Math.min(200, 52 + 20 * n);
    // UI_ISSUES.txt Problem 1 (free move): circular layout is the DEFAULT;
    // saved user positions win so rearrangements survive repaint. New ids
    // take the circular slot, old ids keep their saved spot. Prune stale ids.
    const savedMap = loadPositions();
    const pos = {};
    visible.forEach((c, i) => {
      const hit = savedMap[c.id];
      if (hit && isFinite(Number(hit.x)) && isFinite(Number(hit.y))) {
        pos[c.id] = clampPos(hit.x, hit.y);
      } else {
        const a = (-90 + (360 * i) / Math.max(n, 1)) * Math.PI / 180;
        pos[c.id] = { x: Math.round(CX + R * Math.cos(a)), y: Math.round(CY + R * Math.sin(a)) };
      }
    });
    try {
      const merged = {};
      visible.forEach(c => { merged[c.id] = pos[c.id]; });
      savePositions(merged);
    } catch (_e) { /* persistence optional */ }
    const byId = {};
    visible.forEach(c => { byId[c.id] = c; });
    const linkable = canLink();
    const edges = (st.links || []).filter(L => pos[L.a_id] && pos[L.b_id]);
    const edgesSvg = edges.map(L => {
      const A = pos[L.a_id], B = pos[L.b_id];
      // UI_ISSUES.txt Problem 4: arrowhead was hidden under the target node
      // circle (line ran center-to-center, nodes paint after edges with r=30).
      // Shorten to circle edges so marker-end lands outside the node.
      const NODE_R = 30, ARROW_GAP = 4;
      const dx = B.x - A.x, dy = B.y - A.y;
      const dist = Math.hypot(dx, dy) || 1;
      const ux = dx / dist, uy = dy / dist;
      const sx = Math.round(A.x + ux * NODE_R);
      const sy = Math.round(A.y + uy * NODE_R);
      const ex = Math.round(B.x - ux * (NODE_R + ARROW_GAP));
      const ey = Math.round(B.y - uy * (NODE_R + ARROW_GAP));
      const mx = Math.round((sx + ex) / 2), my = Math.round((sy + ey) / 2);
      const dim = (L.bright === false || L.bright === 0) ? ' edge-dim' : '';
      // UI_ISSUES.txt Problem 1: per-type edge color (line + arrowhead +
      // label via CSS [data-etype]; marker picked here, dim stays grey).
      const isDim = !!(L.bright === false || L.bright === 0);
      const markerId = edgeMarkerId(L.edge_type, isDim);
      return `<g class="gedge${dim}" data-link="${esc(L.id)}" data-etype="${esc(String(L.edge_type || '').toLowerCase().trim())}">` +
        `<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" marker-end="url(#${markerId})"/>` +
        `<text class="edge-label" x="${mx}" y="${my}">${esc(L.edge_type)}</text></g>`;
    }).join('');
    const nodesSvg = visible.map(c => {
      const p = pos[c.id];
      const dim = (phase !== 'phase1' && c.kind === 'main') ? ' dimmed' : '';
      const blue = c.source === 'user_added' ? ' blue' : '';
      const short = c.title.length > 18 ? c.title.slice(0, 17) + '…' : c.title;
      // Problem 1: only L4 nodes carry data-l4node (drag-link handle).
      // Other stages keep data-node so drawer/history/probe still work.
      // Linking = press + hold RIGHT mouse button on a concept, drag to
      // another, release. LEFT-drag always moves (never links). Touch:
      // drag one concept onto another to link.
      const l4attr = linkable ? ` data-l4node="${esc(c.id)}"` : '';
      const tip = linkable ? 'Left-drag to move · Right-press-and-hold + drag to another to link' : 'Left-drag to move · click to open';
      return `<g class="gnode${blue}${dim}" data-node="${esc(c.id)}"${l4attr} title="${tip}">` +
        `<circle cx="${p.x}" cy="${p.y}" r="30"/>` +
        `<text class="node-label" x="${p.x}" y="${p.y + 4}">${esc(short)}</text>` +
        `<title>${esc(c.title)}</title></g>`;
    }).join('');
    const svg = n
      ? `<svg id="graphSvg" viewBox="0 0 600 360" width="100%" height="100%" role="img" aria-label="concept graph">` +
        `<defs><marker id="cogArrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#999"/></marker>` +
        `<marker id="cogArrow-causes" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#800000"/></marker>` +
        `<marker id="cogArrow-leads-to" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#2563eb"/></marker>` +
        `<marker id="cogArrow-depends-on" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#16a34a"/></marker>` +
        `<marker id="cogArrow-includes" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#f97316"/></marker>` +
        `<marker id="cogArrow-contrasts-with" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#dc2626"/></marker>` +
        `<marker id="cogArrow-applied-in" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#1e3a8a"/></marker>` +
        `<marker id="cogArrow-influences" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#9333ea"/></marker>` +
        `<marker id="cogArrow-consists-of" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#166534"/></marker>` +
        `<marker id="cogArrow-custom" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#9ca3af"/></marker>` +
        `<marker id="cogArrowBlue" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#5a7fa6"/></marker></defs>` +
        edgesSvg + nodesSvg + `</svg>` +
        `<div class="graph-controls"><button data-zoom="in" title="zoom in">+</button><button data-zoom="out" title="zoom out">−</button><button data-zoom="reset" title="reset view">⟲</button><button data-layout="reset" title="reset node layout">⌂</button></div>`
      : `<div class="graph-empty">No concepts yet</div>`;
    // Fluid: FLIP snapshot before replacing DOM so repaint/reset glides.
    let oldMap = null;
    try {
      const prev = g.querySelectorAll('g.gnode[data-node]');
      if (prev && prev.length) {
        oldMap = {};
        prev.forEach(function (nn) {
          try {
            const id = nn.getAttribute('data-node');
            const cc = nn.querySelector('circle');
            if (id && cc) {
              const cx = parseFloat(cc.getAttribute('cx')), cy = parseFloat(cc.getAttribute('cy'));
              if (isFinite(cx) && isFinite(cy)) oldMap[id] = { x: cx, y: cy };
            }
          } catch (_e) { /* skip */ }
        });
      }
    } catch (_e) { oldMap = null; }
    g.innerHTML = `<div class="graph-canvas">${svg}</div>`;
    bindNodes();
    // Glide surviving nodes from old spots to new (200ms ease-out).
    try { if (oldMap) flipGlide(oldMap, 200); } catch (_e) { /* glide optional */ }
    // Problem 5: standard graph nav — background-drag pan + wheel zoom.
    // ViewBox-based (graph.js owns), node drag stays link (pan skips nodes).
    try {
      const _svg = g.querySelector('#graphSvg');
      if (_svg && window.CogniMapShell && window.CogniMapShell.attachPanZoom) window.CogniMapShell.attachPanZoom(_svg);
    } catch (_e) { /* pan/zoom optional */ }
    // UI_ISSUES.txt Problem 1 (free move): layout reset restores the default
    // circular arrangement (clears saved positions, then repaints).
    try {
      const lb = g.querySelector('[data-layout="reset"]');
      if (lb && !lb._layoutBound) {
        lb._layoutBound = true;
        lb.addEventListener('click', (e) => {
          e.stopPropagation();
          try { localStorage.removeItem(posKey()); } catch (_e) { /* ignore */ }
          try { window.__cognimap_nodePos = { _sid: SID, map: {} }; } catch (_e) { /* ignore */ }
          refresh();
        });
      }
    } catch (_e) { /* layout reset optional */ }
    // Re-apply selection highlight after repaint (no link list to rely on).
    try {
      if (selectedLinkId && canLink()) {
        const sel = g.querySelector(`g.gedge[data-link="${selectedLinkId}"]`);
        if (sel) sel.classList.add('selected');
        else selectedLinkId = null;
      }
    } catch (_e) { /* highlight optional */ }
    // Canvas edges: L4 click selects for delete popup; L5 click probes.
    // Outside L4/L5 (done/Phase2 final map) clicks do nothing.
    g.querySelectorAll('g.gedge[data-link]').forEach(gr => {
      gr.addEventListener('click', (e) => {
        // Problem 5: a background pan ending on an edge must not act.
        try { if (window.__cognimap_panned) return; } catch (_e) { /* fall through */ }
        const lid = gr.getAttribute('data-link');
        if (currentStage === 'L4') {
          e.stopPropagation();
          try { openSelection(lid); } catch (_e) { /* popup optional */ }
          return;
        }
        if (currentStage !== 'L5') return;
        e.stopPropagation();
        try {
          if (window.CogniMapL5 && window.CogniMapL5.openProbe) window.CogniMapL5.openProbe(lid);
        } catch (_e) { /* probe optional */ }
      });
    });
    // Empty-canvas click deselects (nodes/edges stopPropagation above).
    try {
      const _svg = g.querySelector('#graphSvg');
      if (_svg && !_svg._l4deselectBound) {
        _svg._l4deselectBound = true;
        _svg.addEventListener('click', (e) => {
          try { if (window.__cognimap_panned) return; } catch (_e) { /* fall through */ }
          clearSelection();
        });
      }
    } catch (_e) { /* deselect optional */ }
  }

  function bindNodes() {
    const g = el('graph');
    if (!g || g._l4bound) return;
    g._l4bound = true;
    const NODE_R = 30, ARROW_GAP = 4, DRAG_PX = 5;
    let downFrom = null, downCX = 0, downCY = 0;
    // Linking = RIGHT mouse button press-and-hold + drag (left never links).
    // linkWithRight tracks a right-button link gesture vs a left-button move.
    let linkWithRight = false;
    // LEFT-drag moves every [data-node] in every stage (never links).
    let moveId = null, moveOrig = null, moveMoved = false, moveCur = null;

    function svgEl() { try { return g.querySelector('#graphSvg'); } catch (_e) { return null; } }
    // client(px) -> svg units (pan/zoom aware via live viewBox).
    function svgPoint(svg, clientX, clientY) {
      try {
        const rect = svg.getBoundingClientRect();
        if (!rect.width || !rect.height) return null;
        let vx = 0, vy = 0, vw = 600, vh = 360;
        try {
          const vb = svg.viewBox && svg.viewBox.baseVal;
          if (vb && vb.width && vb.height) { vx = vb.x; vy = vb.y; vw = vb.width; vh = vb.height; }
        } catch (_e) { /* fallback to defaults */ }
        return {
          x: vx + (clientX - rect.left) / rect.width * vw,
          y: vy + (clientY - rect.top) / rect.height * vh,
        };
      } catch (_e) { return null; }
    }
    function nodeCenter(id) {
      try {
        const nodes = g.querySelectorAll('g.gnode[data-node]');
        for (const n of nodes) {
          if (n.getAttribute('data-node') === id) {
            const c = n.querySelector('circle');
            if (!c) return null;
            return { x: parseFloat(c.getAttribute('cx')), y: parseFloat(c.getAttribute('cy')) };
          }
        }
      } catch (_e) { /* ignore */ }
      return null;
    }
    function clearHighlight(svg) {
      try { svg.querySelectorAll('g.gnode.drop-target').forEach(n => n.classList.remove('drop-target')); } catch (_e) { /* ignore */ }
    }
    function clearGhost() {
      const svg = svgEl();
      if (svg) {
        const ln = svg.querySelector('#dragGhost');
        if (ln) ln.remove();
        clearHighlight(svg);
      }
    }
    function setHighlight(id) {
      const svg = svgEl();
      if (!svg) return;
      clearHighlight(svg);
      if (!id || id === downFrom) return;
      try {
        const nodes = svg.querySelectorAll('g.gnode[data-node]');
        for (const n of nodes) {
          if (n.getAttribute('data-node') === id) { n.classList.add('drop-target'); break; }
        }
      } catch (_e) { /* ignore */ }
    }
    function ensureGhost(svg) {
      let ln = svg.querySelector('#dragGhost');
      if (ln) return ln;
      const NS = 'http://www.w3.org/2000/svg';
      ln = document.createElementNS(NS, 'line');
      ln.setAttribute('id', 'dragGhost');
      ln.setAttribute('class', 'drag-ghost');
      ln.setAttribute('marker-end', 'url(#cogArrowBlue)');
      svg.appendChild(ln);
      return ln;
    }
    function updateGhost(clientX, clientY, hoverId) {
      const svg = svgEl();
      if (!svg || !downFrom) return;
      const S = nodeCenter(downFrom);
      if (!S) return;
      const P = svgPoint(svg, clientX, clientY);
      if (!P) return;
      let ex = P.x, ey = P.y;
      // Snap the tip to a valid target's edge so the arrow lands on it.
      if (hoverId && hoverId !== downFrom) {
        const T = nodeCenter(hoverId);
        if (T) {
          const dx = T.x - S.x, dy = T.y - S.y;
          const d = Math.hypot(dx, dy) || 1;
          ex = T.x - dx / d * (NODE_R + ARROW_GAP);
          ey = T.y - dy / d * (NODE_R + ARROW_GAP);
        }
      }
      const dx = ex - S.x, dy = ey - S.y;
      const d = Math.hypot(dx, dy) || 1;
      const sx = S.x + dx / d * NODE_R, sy = S.y + dy / d * NODE_R;
      const ln = ensureGhost(svg);
      ln.setAttribute('x1', Math.round(sx));
      ln.setAttribute('y1', Math.round(sy));
      ln.setAttribute('x2', Math.round(ex));
      ln.setAttribute('y2', Math.round(ey));
    }
    function hoverIdFromEvent(e) {
      try {
        const n = e.target && e.target.closest ? e.target.closest('[data-l4node]') : null;
        return n ? n.getAttribute('data-l4node') : null;
      } catch (_e) { return null; }
    }
    // UI_ISSUES.txt Problem 1 (free move): coordinate-based drop target so a
    // moving node following the cursor can't hide the node underneath
    // (e.target would stay the dragged node). Cursor-in-circle wins.
    function dropTargetAt(clientX, clientY, excludeId) {
      try {
        const svg = svgEl();
        if (!svg) return null;
        const P = svgPoint(svg, clientX, clientY);
        if (!P) return hoverIdFromEvent({ target: document.elementFromPoint ? document.elementFromPoint(clientX, clientY) : null });
        let best = null, bestD = Infinity;
        const nodes = svg.querySelectorAll('g.gnode[data-node]');
        // Outside L4 with no freeze there is no link target at all.
        if (!canLink() && !isFrozen()) return null;
        for (const n of nodes) {
          const id = n.getAttribute('data-node');
          if (!id || id === excludeId) continue;
          // L4 links need a linkable endpoint; frozen drops accept any node
          // (to show the frozen notice); moves accept any node.
          if (canLink()) {
            const l4ok = n.hasAttribute('data-l4node');
            if (!l4ok) continue;
          }
          const c = n.querySelector('circle');
          if (!c) continue;
          const cx = parseFloat(c.getAttribute('cx')), cy = parseFloat(c.getAttribute('cy'));
          if (!isFinite(cx) || !isFinite(cy)) continue;
          const d = Math.hypot(P.x - cx, P.y - cy);
          if (d <= NODE_R + 8 && d < bestD) { bestD = d; best = id; }
        }
        return best;
      } catch (_e) { return null; }
    }
    // UI_ISSUES.txt Problem 1 (free move): live node + incident-edge update
    // so links adjust accordingly WHILE dragging (not just on drop).
    function findNodeEl(id) {
      try {
        const svg = svgEl();
        if (!svg) return null;
        const nodes = svg.querySelectorAll('g.gnode[data-node]');
        for (const n of nodes) {
          if (n.getAttribute('data-node') === id) return n;
        }
      } catch (_e) { /* ignore */ }
      return null;
    }
    function moveNodeLive(id, nx, ny, quiet) {
      try {
        const svg = svgEl();
        if (!svg) return;
        const cl = clampPos(nx, ny);
        nx = cl.x; ny = cl.y;
        const node = findNodeEl(id);
        if (node) {
          const circ = node.querySelector('circle');
          if (circ) { circ.setAttribute('cx', nx); circ.setAttribute('cy', ny); }
          const lab = node.querySelector('text.node-label');
          if (lab) { lab.setAttribute('x', nx); lab.setAttribute('y', ny + 4); }
          // Fluid: programmatic glides (repaint/reset/revert) must not leave
          // the white dragging glow stuck — only active drags set it.
          if (!quiet) node.classList.add('dragging');
          else node.classList.remove('dragging');
        }
        moveCur = { x: nx, y: ny };
        // Recompute every incident edge from live DOM centers.
        svg.querySelectorAll('g.gedge[data-link]').forEach(gr => {
          let link = null;
          try { link = findLink(gr.getAttribute('data-link')); } catch (_e) { link = null; }
          if (!link) return;
          if (link.a_id !== id && link.b_id !== id) return;
          const A = (link.a_id === id) ? { x: nx, y: ny } : nodeCenter(link.a_id);
          const B = (link.b_id === id) ? { x: nx, y: ny } : nodeCenter(link.b_id);
          if (!A || !B) return;
          const dx = B.x - A.x, dy = B.y - A.y;
          const dist = Math.hypot(dx, dy) || 1;
          const ux = dx / dist, uy = dy / dist;
          const sx = Math.round(A.x + ux * NODE_R);
          const sy = Math.round(A.y + uy * NODE_R);
          const ex = Math.round(B.x - ux * (NODE_R + ARROW_GAP));
          const ey = Math.round(B.y - uy * (NODE_R + ARROW_GAP));
          const mx = Math.round((sx + ex) / 2), my = Math.round((sy + ey) / 2);
          const ln = gr.querySelector('line');
          if (ln) { ln.setAttribute('x1', sx); ln.setAttribute('y1', sy); ln.setAttribute('x2', ex); ln.setAttribute('y2', ey); }
          const tx = gr.querySelector('text.edge-label');
          if (tx) { tx.setAttribute('x', mx); tx.setAttribute('y', my); }
        });
      } catch (_e) { /* live move optional */ }
    }
    function clearDragging(id) {
      try {
        const svg = svgEl();
        if (!svg) return;
        if (id) {
          const node = findNodeEl(id);
          if (node) node.classList.remove('dragging');
        } else {
          svg.querySelectorAll('g.gnode.dragging').forEach(n => n.classList.remove('dragging'));
        }
      } catch (_e) { /* ignore */ }
    }
    function svgDelta(svg, dxClient, dyClient) {
      try {
        const rect = svg.getBoundingClientRect();
        if (!rect.width || !rect.height) return { dx: 0, dy: 0 };
        let vw = 600, vh = 360;
        try {
          const vb = svg.viewBox && svg.viewBox.baseVal;
          if (vb && vb.width && vb.height) { vw = vb.width; vh = vb.height; }
        } catch (_e) { /* defaults */ }
        return { dx: dxClient * vw / rect.width, dy: dyClient * vh / rect.height };
      } catch (_e) { return { dx: 0, dy: 0 }; }
    }
    // Fluid drag engine (snappy + precise): rAF-coalesced + exponential
    // smoothing (~150ms settle). True cursor pos drives L4 linking (exact);
    // smoothed render drives visuals. Commit on release is exact.
    let dragPendCX = 0, dragPendCY = 0, dragRaf = 0;
    let renderX = 0, renderY = 0, trueX = 0, trueY = 0, lastTickT = 0;
    try { moveNodeLiveRef = moveNodeLive; } catch (_e) { /* forward ref */ }
    function setDraggingActive(on) {
      try { const s = svgEl(); if (s) s.classList.toggle('dragging-active', !!on); } catch (_e) { /* ignore */ }
    }
    function truePosFor(clientX, clientY) {
      const svg = svgEl();
      if (!svg || !moveOrig) return null;
      const d = svgDelta(svg, clientX - downCX, clientY - downCY);
      return clampPos(moveOrig.x + d.dx, moveOrig.y + d.dy);
    }
    function scheduleTick() {
      if (dragRaf) return;
      try { dragRaf = requestAnimationFrame(tickDrag); } catch (_e) { dragRaf = 0; }
    }
    function cancelTick() {
      if (dragRaf) { try { cancelAnimationFrame(dragRaf); } catch (_e) { /* ignore */ } dragRaf = 0; }
    }
    function tickDrag(now) {
      dragRaf = 0;
      if (!moveId || !moveOrig) return;
      const tp = truePosFor(dragPendCX, dragPendCY);
      if (!tp) return;
      trueX = tp.x; trueY = tp.y;
      if (prefersReducedMotion()) {
        renderX = trueX; renderY = trueY;
      } else {
        const t = (typeof now === 'number') ? now : ((window.performance && window.performance.now) ? window.performance.now() : Date.now());
        const dt = Math.max(8, Math.min(64, t - (lastTickT || t) || 16));
        lastTickT = t;
        const k = 1 - Math.exp(-dt / 45);
        renderX += (trueX - renderX) * k;
        renderY += (trueY - renderY) * k;
        if (Math.hypot(trueX - renderX, trueY - renderY) < 0.5) { renderX = trueX; renderY = trueY; }
      }
      try { moveNodeLive(moveId, renderX, renderY); } catch (_e) { /* ignore */ }
      // NOTE: LEFT-drag never shows the link ghost (RIGHT-drag owns linking).
      // Ease the tail even without new mousemove events.
      if (!prefersReducedMotion() && moveId && moveMoved && (Math.hypot(trueX - renderX, trueY - renderY) > 0.5)) scheduleTick();
    }
    function revertGlide(id, fx, fy, tx, ty) {
      try {
        if (prefersReducedMotion()) { moveNodeLive(id, tx, ty); return; }
        tweenNodeTo(id, fx, fy, tx, ty, 150);
      } catch (_e) { /* revert optional */ }
    }
    // No native menu inside the canvas — right-drag is the link gesture.
    g.addEventListener('contextmenu', (e) => {
      try {
        if (e.target && e.target.closest && e.target.closest('#graph, #graphSvg, [data-node], [data-l4node]')) e.preventDefault();
      } catch (_e) { /* ignore */ }
    });
    g.addEventListener('mousedown', (e) => {
      // LEFT (button 0): arm MOVE only — never links, in any stage.
      // RIGHT (button 2, press-and-hold): arm LINK only — ghost + drop on
      // another concept opens the edge panel. The node itself does not move.
      // Touch keeps its own handlers below (drag onto another to link).
      const btn = (e.button !== undefined) ? e.button : 0;
      let n = null;
      try { n = e.target && e.target.closest ? e.target.closest('[data-node]') : null; } catch (_e) { n = null; }
      if (btn === 2) {
        if (!n) return;
        const id = n.getAttribute('data-node');
        if (!id) return;
        if (!(canLink() || isFrozen())) return;
        let ln = null;
        try { ln = e.target && e.target.closest ? e.target.closest('[data-l4node]') : null; } catch (_e) { ln = null; }
        if (ln) downFrom = ln.getAttribute('data-l4node') || id;
        else if (n.hasAttribute && n.hasAttribute('data-l4node')) downFrom = id;
        else return;
        linkWithRight = true;
        downCX = e.clientX; downCY = e.clientY;
        dragPendCX = e.clientX; dragPendCY = e.clientY;
        try { e.preventDefault(); } catch (_e) { /* ignore */ }
        return;
      }
      if (btn !== 0) return;
      if (!n) { downFrom = null; moveId = null; return; }
      const id = n.getAttribute('data-node');
      if (!id) return;
      const C = nodeCenter(id);
      if (!C) return;
      moveId = id; moveOrig = { x: C.x, y: C.y }; moveCur = { x: C.x, y: C.y }; moveMoved = false;
      renderX = C.x; renderY = C.y; trueX = C.x; trueY = C.y; lastTickT = 0;
      dragPendCX = e.clientX; dragPendCY = e.clientY;
      cancelTick();
      downCX = e.clientX; downCY = e.clientY;
      downFrom = null;
      linkWithRight = false;
    });
    window.addEventListener('mousemove', (e) => {
      // RIGHT-link ghost: node stays put, arrow follows the cursor.
      if (linkWithRight && downFrom) {
        if (Math.hypot(e.clientX - downCX, e.clientY - downCY) < DRAG_PX) return;
        if (canLink()) {
          const hid = dropTargetAt(e.clientX, e.clientY, downFrom);
          setHighlight(hid);
          updateGhost(e.clientX, e.clientY, hid);
        } else if (isFrozen()) {
          setHighlight(dropTargetAt(e.clientX, e.clientY, downFrom));
        }
        return;
      }
      // LEFT-move only (never links).
      if (!moveId) return;
      if (Math.hypot(e.clientX - downCX, e.clientY - downCY) < DRAG_PX) return;
      if (!moveMoved) { moveMoved = true; setDraggingActive(true); }
      dragPendCX = e.clientX; dragPendCY = e.clientY;
      // Fluid: coalesce to one smoothed update per frame.
      scheduleTick();
    });
    window.addEventListener('mouseup', (e) => {
      // RIGHT-link release: node never moved — drop on another opens panel.
      if (linkWithRight && downFrom) {
        const linkFrom = downFrom;
        if (canLink()) {
          let target = null;
          try { target = dropTargetAt(e.clientX, e.clientY, linkFrom); } catch (_e) { target = null; }
          if (!target) { try { target = hoverIdFromEvent(e); } catch (_e) { target = null; } }
          if (target && target !== linkFrom) {
            openEdgePanel(linkFrom, target);
            markNodeMoved();
          }
        } else if (isFrozen()) {
          let ft = null;
          try { ft = dropTargetAt(e.clientX, e.clientY, linkFrom); } catch (_e) { ft = null; }
          if (ft && ft !== linkFrom) {
            openEdgePanel(linkFrom, ft); // frozen notice path
            markNodeMoved();
          }
        }
        linkWithRight = false;
        downFrom = null;
        clearGhost();
        // Fall through to LEFT-move cleanup below in case both were armed.
      }
      // LEFT-move release: snap exact + persist. Never links.
      const mid = moveId, wasMoved = moveMoved;
      cancelTick();
      setDraggingActive(false);
      let exact = null;
      if (mid && wasMoved) {
        try { exact = truePosFor(e.clientX, e.clientY); } catch (_e) { exact = null; }
        if (exact) { try { moveNodeLive(mid, exact.x, exact.y); } catch (_e) { /* snap */ } }
      }
      const cur = exact || moveCur;
      if (mid && wasMoved) {
        try {
          if (cur) setSavedPos(mid, cur.x, cur.y);
        } catch (_e) { /* persistence optional */ }
        try { clearDragging(mid); } catch (_e) { /* ignore */ }
        markNodeMoved();
      } else {
        try { clearDragging(mid); } catch (_e) { /* ignore */ }
      }
      moveId = null; moveOrig = null; moveMoved = false; moveCur = null;
      if (!linkWithRight) { downFrom = null; clearGhost(); }
    });
    // Touch (no right button): drag moves; release on another links (L4).
    g.addEventListener('touchstart', (e) => {
      try {
        const t = e.changedTouches && e.changedTouches[0];
        const n = e.target && e.target.closest ? e.target.closest('[data-node]') : null;
        if (n && t) {
          const id = n.getAttribute('data-node');
          const C = nodeCenter(id);
          if (C && id) {
            moveId = id; moveOrig = { x: C.x, y: C.y }; moveCur = { x: C.x, y: C.y }; moveMoved = false;
            renderX = C.x; renderY = C.y; trueX = C.x; trueY = C.y; lastTickT = 0;
            dragPendCX = t.clientX; dragPendCY = t.clientY;
            cancelTick();
            downCX = t.clientX; downCY = t.clientY;
            try {
              const ln = n.hasAttribute && n.hasAttribute('data-l4node') ? n : (e.target.closest ? e.target.closest('[data-l4node]') : null);
              downFrom = (ln && (canLink() || isFrozen())) ? ln.getAttribute('data-l4node') || ln.getAttribute('data-node') : null;
            } catch (_e) { downFrom = null; }
          }
        }
      } catch (_e) { /* ignore */ }
    }, { passive: true });
    window.addEventListener('touchmove', (e) => {
      if (!moveId) return;
      try {
        const t = e.changedTouches && e.changedTouches[0];
        if (!t) return;
        if (Math.hypot(t.clientX - downCX, t.clientY - downCY) < DRAG_PX) return;
        if (!moveMoved) { moveMoved = true; setDraggingActive(true); }
        dragPendCX = t.clientX; dragPendCY = t.clientY;
        scheduleTick();
        // Prevent page scroll while moving a node.
        try { if (e.cancelable) e.preventDefault(); } catch (_e) { /* passive */ }
      } catch (_e) { /* ignore */ }
    }, { passive: false });
    window.addEventListener('touchend', (e) => {
      if (!moveId) return;
      cancelTick();
      setDraggingActive(false);
      try {
        const t = e.changedTouches && e.changedTouches[0];
        const mid = moveId, wasMoved = moveMoved, orig = moveOrig, linkFrom = downFrom;
        let exact = null;
        if (mid && wasMoved && t) {
          try { exact = truePosFor(t.clientX, t.clientY); } catch (_e) { exact = null; }
          if (exact) { try { moveNodeLive(mid, exact.x, exact.y); } catch (_e) { /* snap */ } }
        }
        const cur = exact || moveCur;
        if (mid && wasMoved && linkFrom && canLink() && t) {
          let target = dropTargetAt(t.clientX, t.clientY, linkFrom);
          if (!target && document.elementFromPoint) {
            try {
              const under = document.elementFromPoint(t.clientX, t.clientY);
              const nn = under && under.closest ? under.closest('[data-l4node]') : null;
              if (nn) target = nn.getAttribute('data-l4node');
            } catch (_e) { /* ignore */ }
          }
          if (target && target !== linkFrom) {
            try { if (cur && orig) revertGlide(mid, cur.x, cur.y, orig.x, orig.y); } catch (_e) { /* revert */ }
            try { clearDragging(mid); } catch (_e) { /* ignore */ }
            openEdgePanel(linkFrom, target);
            markNodeMoved();
            moveId = null; moveOrig = null; moveMoved = false; moveCur = null;
            downFrom = null; clearGhost();
            return;
          }
        }
        if (mid && wasMoved && cur) {
          try { setSavedPos(mid, cur.x, cur.y); } catch (_e) { /* ignore */ }
          markNodeMoved();
        }
        try { clearDragging(mid); } catch (_e) { /* ignore */ }
      } catch (_e) { /* ignore */ }
      moveId = null; moveOrig = null; moveMoved = false; moveCur = null;
      downFrom = null; clearGhost();
    });
    // M2 Esc path: disarm armed link, or mirror Cancel when the edge panel
    // is open (Cancel path already clears pending + flag). Also clears the
    // selected-edge delete popup.
    if (!g._l4escbound) {
      g._l4escbound = true;
      document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' && e.key !== 'Esc') return;
        try {
          const ep = document.getElementById('edgePanel');
          if (ep && !ep.classList.contains('hidden')) ep.classList.add('hidden');
        } catch (_e) { /* ignore */ }
        pendingFrom = pendingTo = null;
        try { window.__cognimap_l4_pending = false; } catch (_e) { /* ignore */ }
        // Cancel a mid-drag ghost too (press-hold released via keyboard).
        // UI_ISSUES.txt Problem 1 (free move): Esc also reverts a mid-move.
        try { cancelTick(); setDraggingActive(false); } catch (_e) { /* ignore */ }
        try { downFrom = null; linkWithRight = false; clearGhost(); } catch (_e) { /* ignore */ }
        try {
          if (moveId && moveMoved && moveOrig && moveCur) { revertGlide(moveId, moveCur.x, moveCur.y, moveOrig.x, moveOrig.y); }
          else if (moveId && moveOrig) { try { moveNodeLive(moveId, moveOrig.x, moveOrig.y); } catch (_e) { /* revert */ } }
          clearDragging(moveId);
        } catch (_e) { /* revert optional */ }
        try { moveId = null; moveOrig = null; moveMoved = false; moveCur = null; } catch (_e) { /* ignore */ }
        try { clearSelection(); } catch (_e) { /* ignore */ }
      });
    }
  }

  function openEdgePanel(a, b) {
    // Frozen graph (Locks §5/§6.3): no new links in L5 — probe only.
    if (isFrozen()) {
      el('l4status').textContent = 'Graph frozen for evaluation. Click dimmed links to defend them.';
      return;
    }
    // Problem 1: silently ignore link attempts outside L4 (backend 400s too).
    if (!canLink()) return;
    try { clearSelection(); } catch (_e) { /* one popup at a time */ }
    // B3: arm linking flag (skeleton helper reads it to suppress drawer).
    try { window.__cognimap_l4_pending = true; } catch (_e) { /* ignore */ }
    pendingFrom = a; pendingTo = b;
    el('edgeOpts').innerHTML = PRESETS.map(p =>
      `<label><input type="radio" name="etype" value="${esc(p)}"><span class="edge-dot" style="background:${edgeColor(p)}"></span> ${esc(p)}</label>`).join('') +
      `<label class="edge-custom-hint"><span class="edge-dot" style="background:${CUSTOM_COLOR}"></span> custom: grey — write below</label>`;
    try {
      const t = el('edgeTitle');
      if (t) t.textContent = `Link: ${title(a)} → ${title(b)}`;
      const s = el('edgeSub');
      if (s) s.textContent = 'Choose the relationship type below.';
    } catch (_e) { /* labels optional */ }
    el('edgeCustom').value = '';
    el('edgeMsg').textContent = '';
    el('edgePanel').classList.remove('hidden');
  }

  async function submitEdge() {
    // Problem 1: never POST outside L4 — silently close and disarm.
    if (!canLink()) { clearLinkArmed(); return; }
    const sel = document.querySelector('input[name=etype]:checked');
    const custom = (el('edgeCustom').value || '').trim();
    // Locks §4 Q11 (m1+M3): custom textbox blocks exact preset duplicates
    // case-insensitive (all 8) — pick the preset instead. Preset radio path
    // sends is_preset=True with exact and passes server validate (which allows
    // exact for presets); custom path sends is_preset=False so typing
    // "causes"/"Causes"/"CAUSES" as custom is rejected 400 server-side too.
    let etype = '', is_preset = false;
    if (custom) {
      const low = custom.toLowerCase();
      const dup = PRESETS.find(p => p.toLowerCase() === low);
      if (dup) { el('edgeMsg').textContent = `use preset '${dup}' instead of custom duplicate`; return; }
      etype = custom; is_preset = false;
    } else {
      etype = sel ? sel.value : '';
      is_preset = true;
    }
    if (!etype) { el('edgeMsg').textContent = 'Pick a type or write custom'; return; }
    try {
      const j = await api('/api/sessions/' + SID + '/l4/links' + q(), { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_id: pendingFrom, to_id: pendingTo, edge_type: etype, is_preset }) });
      el('edgePanel').classList.add('hidden');
      pendingFrom = pendingTo = null;
      try { window.__cognimap_l4_pending = false; } catch (_e) { /* ignore */ }
      await refresh();
      if (window.CogniMapL5) CogniMapL5.refresh();
      // G-S4-1: a Phase-2 main soft-exempt (sub side fine, main over 3) keeps
      // its create_link notice — surface it on the status line after the
      // repaint so it survives the refresh overwrite. Additive only.
      const notice = (j && typeof j.notice === 'string') ? j.notice : '';
      if (notice) {
        const ls = el('l4status');
        if (ls) ls.textContent = ls.textContent + ' · ' + notice;
      }
    } catch (err) { el('edgeMsg').textContent = err.message; }
  }

  function paintStatus(st) {
    if (!st) return;
    const n = (st.counted || []).length;
    if (n === 0) {
      // Pre-Confirm empty-counted guard: never render "Level 4 links: 0 ·  · need…".
      el('l4status').textContent = 'No concepts yet — confirm selection to begin Analyze.';
    } else if (n === 1 && st.n1_auto) {
      el('l4status').textContent = 'Single concept — auto-pass (no links to defend). Finish enabled.';
    } else {
      const degs = st.degrees || {};
      el('l4status').textContent = `Level 4 links: ${(st.links || []).length} · ` +
        (st.counted || []).map(id => `${title(id)}:${degs[id] || 0}`).join(' ') +
        (st.finish_enabled ? ' · Finish enabled' : ' · need ≥1 per concept, max 3');
    }
    el('finishBtn').disabled = !st.finish_enabled;
  }

  async function finish() {
    try {
      const j = await api('/api/sessions/' + SID + '/l4/finish' + q(), { method: 'POST' });
      el('l4status').textContent = 'Level 4 Complete! Graph frozen for evaluation.';
      // Keep the L4 stage cache fresh so canvas edge clicks gate correctly:
      // after Finish the session is L5 (or Phase2/done for n=1) — without
      // this the edge handler would keep the stale L4 value and block valid
      // Stage-5 probes (openProbe refetches authoritatively, but the fast
      // path here must not stale-deny).
      try { currentStage = j.stage || currentStage; } catch (_e) { /* ignore */ }
      // Problem 2: stage left L4 — gate sidebar to the returned stage
      // (L5 / Phase2 / done) so only the current card shows.
      try { if (window.CogniMapStage && window.CogniMapStage.refreshSidebar) window.CogniMapStage.refreshSidebar(j.stage); } catch (e) { /* sidebar optional */ }
      refresh();
      if (window.CogniMapL5) CogniMapL5.refresh();
      // M2 (§4/§5 n=1 vacuous): backend advances N=0 straight to
      // Phase2/done — skip the L5 defend modal (zero links) and open the
      // Phase-2 / final path instead.
      if (j.stage === 'Phase2' || j.stage === 'done' || j.l5_n === 0) {
        if (j.stage === 'Phase2') {
          if (window.CogniMapPhase2) window.CogniMapPhase2.open();
          else { const m2 = el('phase2modal'); if (m2) m2.classList.add('open'); }
        } else {
          el('l4status').textContent += ' All learned — final map intact.';
          const d = el('donemodal');
          if (d) d.classList.add('open');
        }
        return;
      }
      const m = el('l5modal');
      if (m) m.classList.add('open');
      void j;
    } catch (err) { el('l4status').textContent = err.message; }
  }

  function init(sid, userId) {
    SID = sid; UID = userId || 0;
    if (el('edgeConfirm')) el('edgeConfirm').onclick = submitEdge;
    if (el('edgeCancel')) el('edgeCancel').onclick = () => {
      el('edgePanel').classList.add('hidden');
      pendingFrom = pendingTo = null;
      try { window.__cognimap_l4_pending = false; } catch (_e) { /* ignore */ }
    };
    if (el('finishBtn')) el('finishBtn').onclick = finish;
    const t = el('toL4Btn');
    if (t) t.onclick = () => { el('l4modal').classList.remove('open'); refresh(); };
    refresh();
  }

  window.CogniMapL4 = { init, refresh };
})();
