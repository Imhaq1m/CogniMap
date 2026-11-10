"""CogniMap Steps 0-6 — FastAPI (Step 0 routes FROZEN, Steps 1-6 additive).

FROZEN (Step 0): GET /, /u/{user_id}, /u/{user_id}/s/{session_id},
  /api/health, /api/seed, /api/users, /api/sessions,
  /api/sessions/{sid}/state|concepts|links|scenarios|trail|seed-load|files.
ADDITIVE (Step 1): POST /api/sessions/{sid}/upload|extract|confirm-selection,
  DELETE /api/sessions/{sid}/file.
ADDITIVE (Step 2): GET /api/sessions/{sid}/l12/status,
  POST /api/sessions/{sid}/l12/verify.
ADDITIVE (Step 3): GET /api/sessions/{sid}/l3/status,
  POST /api/sessions/{sid}/l3/generate|submit.
ADDITIVE (Step 4): GET /api/sessions/{sid}/l4/status,
  POST /api/sessions/{sid}/l4/links|finish,
  DELETE /api/sessions/{sid}/l4/links/{link_id}.
ADDITIVE (Step 5): GET /api/sessions/{sid}/l5/status,
  POST /api/sessions/{sid}/l5/probe.
ADDITIVE (Step 6): GET /api/sessions/{sid}/phase2/status,
  POST /api/sessions/{sid}/phase2/confirm.
LIFECYCLE (Locks §0/§6): POST /api/sessions (create),
  GET /api/sessions?user_id= (list, ownership-filtered),
  DELETE /api/sessions/{sid}?user_id= (delete-cascade, ownership-checked).
  UI (UI_ISSUES.txt Problem 3): DELETE /api/users/{user_id} (delete-cascade:
  user + sessions + session_files + concepts/links/scenarios/trail).
Shapes from models.py unchanged (session_id-only, user_id via sessions join).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, parse, store

log = logging.getLogger("cognimap.main")

app = FastAPI(title="CogniMap Steps0-6")
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
_STATIC_DIR = os.path.normpath(_STATIC_DIR)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

store.init_db()


def _sv(name: str) -> str:
    """Cache-busting static URL (mtime-based, per-request stat).

    Browsers cache /static/* aggressively, so CSS/JS edits looked "not
    fixed" until hard-refresh. Query ?v=<mtime> changes only when the file
    actually changes — no manual bump, no restart needed.
    """
    try:
        mtime = int(os.path.getmtime(os.path.join(_STATIC_DIR, name)))
    except OSError:
        mtime = 0
    return f"/static/{name}?v={mtime}"


# Theme system (THEME.md): dark is the default; FIRST visit follows the OS
# (prefers-color-scheme: light), any manual toggle wins and persists in
# localStorage ('cognimap-theme'). Runs in <head> before the stylesheet so
# the data-theme attribute is already set → zero theme flash on load.
# The toggle button is appended into the page's .brand (all three pages
# have one) — markup-free injection keeps page templates untouched.
THEME_SCRIPT = """<script>(function(){
var K='cognimap-theme',d=document.documentElement,t=null;
try{t=localStorage.getItem(K)}catch(e){}
if(t!=='light'&&t!=='dark'){
  try{t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'}catch(e){t='dark'}
}
d.setAttribute('data-theme',t);
function set(v){if(v!=='light'&&v!=='dark')return;d.setAttribute('data-theme',v);try{localStorage.setItem(K,v)}catch(e){}}
function label(){return {dark:'Switch to light theme',light:'Switch to dark theme'}[d.getAttribute('data-theme')]||'Switch theme'}
function glyph(){return {dark:'\\u2600',light:'\\u263e'}[d.getAttribute('data-theme')]||'\\u2600'}
function paint(b){var m=label();b.textContent=glyph();b.title=m;b.setAttribute('aria-label',m)}
function mount(){
  var b=document.createElement('button');
  b.type='button';b.className='theme-toggle';paint(b);
  b.addEventListener('click',function(){set(d.getAttribute('data-theme')==='dark'?'light':'dark');paint(b)});
  var brand=document.querySelector('.brand');
  if(brand){brand.appendChild(b)}
  else{b.classList.add('theme-toggle-float');document.body.appendChild(b)}
}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',mount)}else{mount()}
window.CogniMapTheme={get:function(){return d.getAttribute('data-theme')},set:set};
})();</script>"""


# UI_ISSUES.txt #1 (stage percentages → BAR meter at the sidebar bottom):
# server-side twin of static/meter.js so the pre-init sidebar already shows
# the meter with real numbers for the stage the page opens on. Markup MUST
# stay in sync with meter.js. Visible only for the percentage stages
# (L1-2 / L3 / L5) — other stages render the hidden empty shell.
_METER_ACCENT = {
    "L1-2": "var(--stage-l12)",
    "L3": "var(--stage-l3)",
    "L5": "var(--stage-l5)",
}


def _meter_html(pct: float = 0, sub: str = "", accent: str = "var(--accent)",
                hidden: bool = False, stage: str = "") -> str:
    pct = max(0.0, min(100.0, float(pct or 0)))
    shown = f"{pct:g}"  # int % from the API renders without trailing .0
    cls = "cogmeter" + (" hidden" if hidden else "")
    return (
        f'<div id="stageMeter" class="{cls}" role="img" data-stage="{stage}" '
        f'aria-label="Progress {shown}% of 100%" style="--stage-accent:{accent}">'
        f'<div class="cm-bar"><div class="cm-fill" style="width:{shown}%"></div>'
        f'<div class="cm-num">{shown}<i>%</i></div></div>'
        + (f'<div class="cm-sub">{sub}</div>' if sub else "")
        + "</div>"
    )


def _meter_for_stage(session_id: str, stage: str) -> str:
    """Initial bottom panel meter for the CURRENT stage (fail-soft: any
    status error leaves the 0% shell; meter.js repaints from API truth)."""
    accent = _METER_ACCENT.get(stage or "")
    if not accent:
        return _meter_html(stage=stage or "", hidden=True)
    pct, sub = 0, "0/0"
    try:
        if stage == "L1-2":
            st = store.l12_status(session_id)
            pct = st.get("pct", 0)
            sub = f"{st.get('completed', 0)}/{st.get('total', 0)}"
        elif stage == "L3":
            st = store.l3_status(session_id)
            pct = st.get("pct", 0)
            sub = f"{st.get('cleared', 0)}/{st.get('total', 0)}"
        elif stage == "L5":
            st = store.l5_status(session_id)
            if st.get("entered"):
                if st.get("complete") and not st.get("n"):
                    pct, sub = 100, "0/0 auto-pass"
                else:
                    pct = st.get("pct", 0)
                    sub = f"{st.get('bright', 0)}/{st.get('n', 0)}"
                    if st.get("complete") and st.get("n"):
                        sub += " · complete"
            else:
                sub = f"0/{st.get('n', 0)}"
    except Exception:  # fail-soft; meter.js repaints with API truth
        pct, sub = 0, "0/0"
    return _meter_html(pct, sub, accent, stage=stage)


def _page_head() -> str:
    return (f"{THEME_SCRIPT}"
            """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">"""
            f"""<link rel="stylesheet" href="{_sv('style.css')}">""")


def _mode_badge() -> str:
    """Launch-mode pill (grill 2026-10-29: COGNIMAP_MODE toggle visibility).

    DEMO = stub engine forced via COGNIMAP_MODE=demo (keys ignored);
    LIVE + model = auto mode with keys; STUB = auto mode, keyless.
    Rendered per request so it always reflects the launch environment.
    Inline styles: no stylesheet dependency, theme-agnostic.
    """
    pill = ("display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;"
            "border-radius:999px;letter-spacing:.06em;vertical-align:middle;")
    if config.is_demo_forced():
        return (f' <span style="{pill}background:#7c3aed;color:#fff"'
                ' title="COGNIMAP_MODE=demo: stub engine forced, keys ignored">DEMO</span>')
    st = llm.llm_status()
    if st.get("llm") == "live":
        model = str(st.get("llm_model") or "")
        return (f' <span style="{pill}background:#166534;color:#fff"'
                f' title="live engine serving">LIVE · {model}</span>')
    return (f' <span style="{pill}background:#57534c;color:#fff"'
            ' title="auto mode, no keys: stub engine">STUB</span>')


def _current_step() -> int:
    """Derive implemented slice step from mounted routes (no hardcode).

    Step 6 when Phase-2 routes present, else 5 when L5 present, else 4 when
    L4 present, else 3/2/1/0 as before.
    """
    try:
        paths = set()
        for r in app.routes:
            p = getattr(r, "path", "")
            if p:
                paths.add(p)
        if any("/phase2/" in p for p in paths):
            return 6
        if any("/l5/" in p for p in paths):
            return 5
        if any("/l4/" in p for p in paths):
            return 4
        if any("/l3/" in p for p in paths):
            return 3
        if any("/l12/" in p for p in paths):
            return 2
        if any("confirm-selection" in p for p in paths):
            return 1
        return 0
    except Exception:
        return 6


def _owned(session_id: str, user_id: int | None) -> dict:
    """Anti-IDOR gate (Locks §0+§8): every session-scoped route MUST verify
    sessions.user_id == requesting user_id, never session_id alone."""
    try:
        return store.require_owned_session(session_id, user_id)
    except KeyError:
        raise HTTPException(404, "no such session")
    except PermissionError as e:
        raise HTTPException(404, str(e))


class UserIn(BaseModel):
    name: str


class SessionIn(BaseModel):
    user_id: int
    file: str = ""
    name: str = ""


class RenameIn(BaseModel):
    name: str = ""


class UploadIn(BaseModel):
    file: str = ""


class ConfirmIn(BaseModel):
    concepts: list[dict] = []


class VerifyIn(BaseModel):
    concept_id: str = ""
    paraphrase: str = ""


PAGE_HEAD = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/style.css">"""
# NOTE: PAGE_HEAD kept for compat (unversioned). Pages below use _page_head()
# (mtime-versioned) so browser cache never hides CSS fixes.


def picker_page() -> str:
    # UI_ISSUES.txt Problem 3 (picker-only delete) + centered profiles:
    # profile create + list live in the middle (.main, centered card like
    # normal sites), not the left panel. Sidebar keeps brand + helper only.
    return f"""<!doctype html><html><head>{_page_head()}<title>CogniMap</title></head><body>
<div class="layout"><div class="sidebar"><div class="brand">CogniMap{_mode_badge()}</div>
<div class="card"><h3>Profile (lite name-pick, no auth)</h3>
<p class="muted">Pick a profile in the middle to begin. No login — profiles are by name only.</p></div></div>
<div class="main"><div style="max-width:560px;margin:32px auto">
<h2>Pick a profile to begin</h2>
<div class="card"><h3>New profile</h3>
<input type="text" id="name" placeholder="Your name">
<button class="btn primary" id="go">Continue</button></div>
<div class="card" style="margin-top:12px"><h3>Profiles</h3>
<div id="users"></div></div>
<p>Seed demo: <a href="/api/seed">/api/seed</a> · Health: <a href="/api/health">/api/health</a></p></div></div></div>
<script>
async function refresh() {{
  const r = await fetch('/api/users'); const u = await r.json();
  document.getElementById('users').innerHTML = u.map(x =>
    `<div class="file-row"><span>${{x.name}} (#${{x.id}})</span><span><a href="/u/${{x.id}}">open</a> <button class="icon-btn" data-deluser="${{x.id}}" title="delete profile">x</button></span></div>`).join('') || '<p>No profiles yet.</p>';
  document.querySelectorAll('[data-deluser]').forEach(b => {{
    b.onclick = async () => {{
      if (!confirm('Delete this profile and all its sessions/data?')) return;
      await fetch('/api/users/' + b.getAttribute('data-deluser'), {{method:'DELETE'}});
      refresh();
    }};
  }});
}}
document.getElementById('go').onclick = async () => {{
  const name = document.getElementById('name').value.trim(); if (!name) return;
  const r = await fetch('/api/users', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{name}})}});
  const u = await r.json(); window.location = '/u/' + u.id;
}};
refresh();
</script></body></html>"""


def user_page(user_id: int) -> str:
    # UI_ISSUES.txt Problem 1: session list page is NOT a workspace —
    # no Manage Materials (Select/Extract) and no Level progress here.
    # Those live only in workspace_page() (Problem 2 gates when each appears).
    return f"""<!doctype html><html><head>{_page_head()}<title>CogniMap — user {user_id}</title>
<style>
#delOverlay{{position:fixed;inset:0;background:var(--backdrop);display:none;align-items:center;justify-content:center;z-index:200;padding:16px;box-sizing:border-box}}
#delOverlay.open{{display:flex}}
#delOverlay .modal-box{{animation:cogDelIn var(--dur-base) var(--ease-soft)}}
@keyframes cogDelIn{{from{{opacity:0;transform:translateY(10px) scale(.98)}}to{{opacity:1;transform:none}}}}
#delTitleRow{{display:flex;align-items:center;gap:10px}}
#delIcon{{width:36px;height:36px;flex-shrink:0;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;background:var(--warn-bg);border:1px solid var(--warn-line)}}
#delName{{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}}
#delFoot{{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}}
#delFoot .btn{{width:auto;min-width:96px;margin:0;padding:8px 18px}}
#delConfirm{{background:var(--danger);border-color:var(--danger);color:#fff}}
#delConfirm:hover{{opacity:.9}}
</style></head><body>
<div class="layout"><div class="sidebar"><div class="brand">CogniMap</div>
<div class="card"><h3>Sessions</h3>
<p class="muted">Create or open a session to start learning.</p></div>
</div>
<div class="main"><h2>User #{user_id} — sessions</h2>
<input type="text" id="fname" placeholder="Workspace name e.g. Biology Ch.5" maxlength="100">
<button class="btn primary" id="news">New session</button>
<div id="sessions"></div>
<p><a href="/">← profiles</a></p></div></div>
<div id="delOverlay" role="dialog" aria-modal="true" aria-labelledby="delTitle">
<div class="modal-box" style="width:min(440px,94vw)">
<div id="delTitleRow"><div id="delIcon">🗑</div>
<div style="min-width:0"><h3 id="delTitle" style="margin:0">Delete workspace?</h3>
<div id="delName" class="muted" style="font-size:14px"></div></div></div>
<p class="muted" style="margin:12px 0 0 0">This will permanently delete this workspace and all its data. This can't be undone.</p>
<div id="delFoot"><button class="btn" id="delCancel">Cancel</button><button class="btn" id="delConfirm">Delete</button></div>
</div></div>
<script>
function esc(s) {{ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
let pendingDelId = null;
function openDelModal(sid, label) {{
  pendingDelId = sid;
  document.getElementById('delName').textContent = label || sid;
  document.getElementById('delOverlay').classList.add('open');
  document.getElementById('delCancel').focus();
}}
function closeDelModal() {{
  pendingDelId = null;
  document.getElementById('delOverlay').classList.remove('open');
}}
async function refresh() {{
  const r = await fetch('/api/sessions?user_id={user_id}'); const s = await r.json();
  document.getElementById('sessions').innerHTML = s.map(x => {{
    const label = x.name || x.file || x.id;
    return `<div class="file-row" style="flex-wrap:wrap;gap:8px" data-sid="${{x.id}}">`
      + `<span class="ws-label" style="flex:1;min-width:0" title="${{esc(label)}}">${{esc(label)}} · ${{esc(x.stage)}}</span>`
      + `<a class="btn sm primary ws-open" style="text-decoration:none;flex-shrink:0" title="Open workspace" href="/u/{user_id}/s/${{x.id}}">Open →</a>`
      + `<span class="ws-actions" style="flex-shrink:0"><button class="icon-btn" data-rename="${{x.id}}" title="rename workspace">✎</button>`
      + `<button class="icon-btn" data-delsess="${{x.id}}" title="delete session">x</button></span>`
      + `<div class="ws-rename hidden" style="flex-basis:100%;display:none;gap:6px;margin-top:6px"><input type="text" maxlength="100" value="${{esc(label)}}"><button class="btn sm primary">Save</button><button class="btn sm">Cancel</button></div></div>`;
  }}).join('') || '<p>No sessions yet.</p>';
  document.querySelectorAll('[data-delsess]').forEach(b => {{
    b.onclick = () => {{
      const row = b.closest('.file-row');
      const sid = b.getAttribute('data-delsess');
      const lblEl = row ? row.querySelector('.ws-label') : null;
      openDelModal(sid, lblEl ? lblEl.textContent : sid);
    }};
  }});
  const ov = document.getElementById('delOverlay');
  ov.onclick = (e) => {{ if (e.target === ov) closeDelModal(); }};
  document.getElementById('delCancel').onclick = closeDelModal;
  document.getElementById('delConfirm').onclick = async () => {{
    if (!pendingDelId) return;
    await fetch('/api/sessions/' + pendingDelId + '?user_id={user_id}', {{method:'DELETE'}});
    closeDelModal(); refresh();
  }};
  document.onkeydown = (e) => {{ if (e.key === 'Escape' && ov.classList.contains('open')) closeDelModal(); }};
  document.querySelectorAll('[data-rename]').forEach(b => {{
    b.onclick = () => {{
      const row = b.closest('.file-row');
      // Exclusive edit mode: close any other open rename box first so only
      // one row shows Save/Cancel at a time.
      document.querySelectorAll('.file-row').forEach(r => {{
        if (r !== row) {{
          const ob = r.querySelector('.ws-rename');
          if (ob) {{ ob.classList.add('hidden'); ob.style.display = 'none'; }}
          const oa = r.querySelector('.ws-actions');
          if (oa) oa.style.display = '';
          const oo = r.querySelector('.ws-open');
          if (oo) oo.style.display = '';
        }}
      }});
      const box = row.querySelector('.ws-rename');
      const actions = row.querySelector('.ws-actions');
      const openBtn = row.querySelector('.ws-open');
      const inp = box.querySelector('input');
      // Hide pencil/x + Open button while editing — only input + Save/Cancel visible.
      if (actions) actions.style.display = 'none';
      if (openBtn) openBtn.style.display = 'none';
      box.classList.remove('hidden'); box.style.display = 'flex'; inp.focus(); inp.select();
      box.querySelector('.btn.primary').onclick = async () => {{
        const name = inp.value.trim();
        if (!name) {{ alert('Workspace name required'); return; }}
        if (name.length > 100) {{ alert('Workspace name max 100 chars'); return; }}
        const r2 = await fetch('/api/sessions/' + b.getAttribute('data-rename') + '?user_id={user_id}',
          {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{name}})}});
        if (!r2.ok) {{ alert((await r2.text()).slice(0,300)); return; }}
        refresh();
      }};
      box.querySelectorAll('.btn')[1].onclick = () => {{ box.classList.add('hidden'); box.style.display = 'none'; if (actions) actions.style.display = ''; if (openBtn) openBtn.style.display = ''; }};
      inp.onkeydown = (e) => {{ if (e.key === 'Enter') box.querySelector('.btn.primary').click(); if (e.key === 'Escape') box.querySelectorAll('.btn')[1].click(); }};
    }};
  }});
}}
document.getElementById('news').onclick = async () => {{
  const file = document.getElementById('fname').value.trim() || 'seed-demo.pdf';
  const r = await fetch('/api/sessions', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{user_id:{user_id}, file, name: file}})}});
  const s = await r.json(); window.location = '/u/{user_id}/s/' + s.id;
}};
refresh();
</script></body></html>"""


# UI_ISSUES.txt #2 (grilling Q9): one marker per stage, short existing
# vocabulary: Materials · Level 1–2 · Level 3 · Level 4 · Level 5 ·
# Sub-Headings · Done. Server renders the correct initial state (no flash
# of wrong cards — same pattern as the sidebar gating), JS (stageflow.js)
# keeps it true after every transition. States (grilling Q10): completed =
# solid stage-colour fill, current = fill + glow ring, future = dashed
# hollow. The "Cycle 2" chip rides the Sub-Headings marker (grilling Q12).
_STAGE_FLOW = (
    ("steps1-2", "Materials"),
    ("L1-2", "Level 1–2"),
    ("L3", "Level 3"),
    ("L4", "Level 4"),
    ("L5", "Level 5"),
    ("Phase2", "Sub-Headings"),
    ("done", "Done"),
)


def _stage_flow(user_id: int, session_id: str, stage: str, phase: str, display: str = "") -> str:
    """Top-bar stage flow header (replaces the old workspace h2 heading)."""
    stage = stage or "steps1-2"
    phase = phase or "phase1"
    order = [k for k, _ in _STAGE_FLOW]
    ci = order.index(stage) if stage in order else 0
    steps = []
    for i, (key, label) in enumerate(_STAGE_FLOW):
        # Visited inference (grilling Q11, mirrors stageflow.js): the phase-2
        # pass replays the ladder — all mains-cycle stages + Phase2 itself
        # stay filled; phase 1 fills strictly left of the current marker.
        visited = (i <= 5) if phase == "phase2" else (i < ci)
        if i == ci:
            cls = "stp-step stp-now"
        elif visited:
            cls = "stp-step stp-done"
        else:
            cls = "stp-step"
        chip = '<span class="stp-chip">Cycle 2</span>' if key == "Phase2" else ""
        steps.append(
            f'<div class="{cls}" data-stage="{key}" title="{label}">'
            f'<span class="stp-dot"></span><span class="stp-name">{label}</span>{chip}</div>'
        )
    _label = (display or session_id or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return (
        '<header class="topflow">'
        f'<span class="topflow-id" id="wsTopLabel" title="{_label}">user #{user_id} · {_label}</span>'
        f'<div id="stageFlow" class="stage-flow" data-phase="{phase}" role="group" aria-label="Learning stage progress">'
        f'<div class="stp-track"><div class="stp-traveler"></div>{"".join(steps)}</div>'
        "</div></header>"
    )


def workspace_page(user_id: int, session_id: str) -> str:
    # UI_ISSUES.txt Problem 2: stage-gated sidebar — new session shows ONLY
    # Manage Materials + empty workspace; each stage appears one-at-a-time
    # after the previous completes. Only the current stage card is visible
    # (Q2-b). Manage Materials disappears after Confirm but file names stay
    # in the persistent Studying card (Q2-a). #state JSON hidden behind a
    # Debug toggle (Q2-c). Ids kept (progress/l3progress/l4card/l5card) so
    # existing JS keeps working — visibility toggled via .hidden. The old
    # percentage slots (#progress/#l3progress/#l5progress) now keep only the
    # stage-complete Continue buttons; the percentage lives in the shared
    # BAR meter at the panel bottom (UI_ISSUES.txt #1).
    # Server renders the correct initial visibility per stage (no flash of
    # wrong cards); JS refreshSidebar() keeps it correct after transitions.
    try:
        _s = store.get_session(session_id)
        _stage = (_s or {}).get("stage") or "steps1-2"
        _phase = (_s or {}).get("phase") or "phase1"
        _ws_display = ((_s or {}).get("name") or (_s or {}).get("file") or session_id)
    except Exception:
        _stage = "steps1-2"
        _phase = "phase1"
        _ws_display = session_id
    _ws_esc = str(_ws_display).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    _hid_mat = "" if _stage == "steps1-2" else " hidden"
    _hid_l12 = "" if _stage == "L1-2" else " hidden"
    _hid_l3 = "" if _stage == "L3" else " hidden"
    _hid_l4 = "" if _stage == "L4" else " hidden"
    _hid_l5 = "" if _stage == "L5" else " hidden"
    # UI_ISSUES.txt Problem 1: Phase2 stage had no sidebar card — closing the
    # sub-headings popup (phase2X) left no way to reopen it. Phase2 card with
    # an explicit Continue button gives a persistent reopen path after cancel.
    _hid_p2 = "" if _stage == "Phase2" else " hidden"
    _hid_done = "" if _stage == "done" else " hidden"
    return f"""<!doctype html><html><head>{_page_head()}<title>CogniMap workspace</title></head><body>
<div class="layout workspace"><div class="sidebar"><div class="brand">CogniMap{_mode_badge()}</div>
<div class="card" id="wsCard"><h3>Workspace</h3>
<div class="file-row" id="wsViewRow"><span id="wsName" title="{_ws_esc}">{_ws_esc}</span><button class="icon-btn" id="wsRenameBtn" title="rename workspace">✎</button></div>
<div id="wsRenameBox" class="hidden"><input type="text" id="wsRenameInput" maxlength="100" value="{_ws_esc}"><div id="wsRenameMsg" class="warn hidden"></div><div style="display:flex;gap:6px;margin-top:6px"><button class="btn sm primary" id="wsRenameSave">Save</button><button class="btn sm" id="wsRenameCancel">Cancel</button></div></div></div>
<div class="card{_hid_mat}" id="materialsCard"><h3>Manage Materials</h3>
<button class="btn" id="selBtn">Select Files</button>
<input type="file" id="filePick" accept=".pdf,.md,.txt" style="display:none">
<button class="btn" id="extBtn" disabled>Extract Concepts</button>
<div id="fileWarn" class="warn hidden"></div></div>
<div class="card" id="filesCard"><h3>Studying</h3>
<div id="files"></div></div>
<div class="card" id="printCard"><h3>Print</h3>
<p class="muted stage-desc">Revision hardcopy — anytime, B&amp;W-safe.</p>
<button class="btn" id="printBtn">Print Study Pack</button></div>
<div class="card{_hid_l12}" id="l12card"><h3>Level 1 - 2 [Remember/Understand]</h3>
<p class="muted stage-desc">Remember — retrieve relevant knowledge from memory. Understand — construct meaning: interpret, explain, and summarize ideas.</p>
<div id="progress"></div></div>
<div class="card{_hid_l3}" id="l3card"><h3>Level 3 [Apply]</h3>
<p class="muted stage-desc">Apply — carry out or use a procedure in a given situation.</p>
<button class="btn purple" id="genBtn" disabled>Generate Scenario</button>
<div id="l3progress"></div></div>
<div class="card{_hid_l4}" id="l4card"><h3>Level 4 [Analyze]</h3>
<p class="muted stage-desc">Analyze — break material into its parts and see how the parts relate to one another and to the whole.</p>
<div id="l4rules"><ul><li>Each concept must have at least one connection</li><li>~3 connections per concept recommended (more allowed)</li><li>Select a relationship type for each connection (e.g., causes, depends on, leads to)</li><li>Focus on the most important relationships rather than connecting everything</li><li><b>How to link:</b> press + hold the <b>RIGHT</b> mouse button on a concept, drag to another concept, release. LEFT-drag only moves concepts. On touch screens, drag one concept onto another.</li></ul></div>
<div id="l4warn" class="warn">Each concept needs \u22651 link (one link per pair \u2014 direction stored for probing, ~3 recommended, more allowed). LEFT-drag moves concepts (never links); RIGHT-press-and-hold + drag creates links. You can delete/re-pick links, but can\'t add concepts.</div>
<div id="l4status">Level 4: no links yet</div>
<button class="btn green" id="finishBtn" disabled>Finish</button></div>
<div class="card{_hid_l5}" id="l5card"><h3>Level 5 [Evaluate]</h3>
<p class="muted stage-desc">Evaluate — make judgments based on criteria and standards.</p>
<div id="l5warn" class="warn">Graph frozen for evaluation. Click dimmed links to defend them.</div>
<div id="l5progress"></div></div>
<div class="card{_hid_p2}" id="phase2card"><h3>Sub-Headings Expansion</h3>
<p class="muted stage-desc">Conceptual overview complete — expand into sub-concepts when ready.</p>
<button class="btn primary" id="phase2Btn">Continue to Sub-Headings</button></div>
<div class="card{_hid_done}" id="donecard"><h3>Finished — Continue Study</h3>
<p class="muted stage-desc">Final map complete. Study new material in the same workspace.</p>
<button class="btn primary" id="continueSideBtn">Continue with new material</button><div id="continueSideMsg" class="warn hidden"></div></div>
<!-- UI_ISSUES.txt #1: the stage percentage meter lives at the BOTTOM of the
left panel (margin-top auto pins it; style.css). Server renders real numbers
for the current stage via _meter_for_stage; meter.js repaints on every paint. -->
{_meter_for_stage(session_id, _stage)}
<p><a href="/u/{user_id}">← sessions</a></p></div>
<div class="main">{_stage_flow(user_id, session_id, _stage, _phase, _ws_display)}
<div id="graph">Graph canvas — mains render here after Confirm (Phase 1 mains-only)</div>
<div id="edgePanel" class="hidden"><div class="modal-head"><h4 id="edgeTitle">Type of edges</h4><button class="btn sm" id="edgeCancel">x</button></div><div id="edgeSub" class="muted"></div><div id="edgeOpts"></div>
<input type="text" id="edgeCustom" maxlength="24" placeholder="custom (1-24 chars, max 3 words)">
<div id="edgeMsg"></div><button class="btn green" id="edgeConfirm">Confirm</button></div>
<div class="card" id="debugCard"><button class="btn sm" id="debugToggle">Debug</button><div id="state" class="hidden"></div></div></div></div>
<div id="panel">
<div class="drawer-head"><h3 id="drawerTitle">Concept</h3>
<button class="btn sm" onclick="CogniMapShell.closePanel()">x</button></div>
<div id="blueWarn" class="warn hidden">Ensure your self-defined concept is accurate — not verified against source.</div>
<div id="drawerExpl" class="expl-box"></div>
<label for="drawerPara" id="drawerParaLabel"><b>Your Paraphrase</b></label>
<textarea id="drawerPara" rows="5" placeholder="Explain in your own words (meaning, not rote memorization)"></textarea>
<button class="btn primary" id="verifyBtn">Verify</button>
<div id="drawerFb"></div>
<!-- m5 (Locks §9 wins): L4 graph-only, correctly omitted from the history dropdown. Reviewer verifies no L4 option here. -->
<div id="histBox"><div class="hist-head"><span class="hist-title">History</span><select id="histStage"><option value="">History</option><option value="L1-2">Stage 1-2</option><option value="L3">Stage 3</option><option value="L5">Stage 5</option></select><select id="histItem" class="hidden"></select></div><div id="histView"></div></div>
</div>
<div id="modal"><div class="modal-box modal-wide">
<div class="modal-head"><h3 id="modal-title">Extracted Concepts</h3>
<button class="btn sm" id="modalX">x</button></div>
<div id="warnBox" class="warn hidden"></div>
<div id="tree"></div>
<div class="add-line" id="addMain" title="Add Main Heading"><span>+ Add Main Heading</span></div>
<div class="modal-foot"><button class="btn green" id="confirmSel">Confirm Selection</button></div>
</div></div>
<div id="lockBox" class="lock-overlay hidden"><div class="modal-box lock-box" role="dialog" aria-modal="true" aria-labelledby="lockTitle">
<h3 id="lockTitle" style="margin:0">Heads up</h3>
<p>Heads up — concepts lock after this. Check names/selection, you can't add/delete later. ≥2–3 mains recommended (a single main auto-passes Analyze/Evaluate with no links to defend).</p>
<div class="modal-foot lock-foot"><button class="btn green" id="lockConfirm">Confirm</button>
<button class="btn" id="lockBack">Back</button></div>
</div></div>
<div id="scnmodal"><div class="modal-box modal-wide">
<div class="modal-head"><h3>Scenario</h3><button class="btn sm" id="scnX">x</button></div>
<div class="scn-split"><div class="scn-left" id="scnText"></div>
<div class="scn-right" id="scnConcepts"></div></div>
<div id="scnMsg"></div>
<div class="modal-foot"><button class="btn green" id="scnSubmit">Submit</button></div>
</div></div>
<div id="l4modal"><div class="modal-box">
<h3>Level 3 Complete!</h3>
<p>Application secured. Welcome to <b>Level 4 - Analyze</b>: connect concepts, name each relationship, and build structure.</p>
<button class="btn primary" id="toL4Btn">Continue to Level 4</button>
</div></div>
<script src="{_sv('graph.js')}"></script>
<!-- UI_ISSUES.txt #1: shared ring meter (used by l12/l3/l5 paint fns) must
load BEFORE the modules that call CogniMapMeter.html during init(). -->
<script src="{_sv('meter.js')}"></script>
<script src="{_sv('steps12.js')}"></script>
<script src="{_sv('l12.js')}"></script>
<script src="{_sv('l3.js')}"></script>
<script src="{_sv('l4.js')}"></script>
<script src="{_sv('l5.js')}"></script>
<script src="{_sv('phase2.js')}"></script>
<script src="{_sv('history.js')}"></script>
<script src="{_sv('stageflow.js')}"></script>
<script src="{_sv('print.js')}"></script>
<div id="l3modal"><div class="modal-box">
<h3>Level 1 - 2 Complete!</h3>
<p>Core meanings secured. Welcome to <b>Level 3 - Apply</b>: face real-world scenarios and identify which concepts defend your reasoning.</p>
<button class="btn primary" id="toL3Btn">Continue to Level 3</button>
</div></div>
<div id="l12guide"><div class="modal-box">
<h3>Level 1 - 2: Remember/Understand</h3>
<p>Explain each concept in your own words, focusing on meaning rather than rote memorization. Click a main concept to open its definition panel.</p>
<button class="btn primary" id="l12guideContinue">Continue</button>
</div></div>
<div id="l5modal"><div class="modal-box">
<h3>Level 4 Complete!</h3>
<p>Structure secured. Welcome to <b>Level 5 - Evaluate</b>: defend each relationship from both sides.</p>
<button class="btn primary" id="toL5Btn">Continue to Level 5</button>
</div></div>
<div id="probemodal"><div class="modal-box modal-wide">
<div class="modal-head"><h3 id="probeTitle">Probe</h3><button class="btn sm" id="probeX" title="Close" aria-label="Close">×</button></div>
<label><b>Why does this relationship exist?</b></label>
<textarea id="probeWhy" rows="3"></textarea>
<div id="probeWhyFb"></div>
<label><b>When might this relationship fail?</b></label>
<textarea id="probeFail" rows="3"></textarea>
<div id="probeFailFb"></div>
<div id="probeMsg"></div>
<div class="modal-foot"><button class="btn green" id="probeSubmit">Submit</button></div>
</div></div>
<div id="phase2modal"><div class="modal-box modal-wide">
<div class="modal-head"><h3>You've completed the conceptual overview</h3><button class="btn sm" id="phase2X">x</button></div>
<p>Mastered core topics — now expand into sub-concepts. Mains dimmed (completed); add sub-headings only.</p>
<!-- Transition-only note (§7): stage=Phase2/phase=phase1 window reports mains math; modal covers workspace until Phase-2 Confirm. -->
<div id="phase2warn" class="warn hidden"></div>
<div id="phase2tree"></div>
<div class="modal-foot"><button class="btn green" id="phase2Confirm">Confirm Selection</button></div>
</div></div>
<div id="addHeadingModal"><div class="modal-box add-heading-box">
<div class="modal-head"><h3 id="addHeadingTitle">Add heading</h3><button class="btn sm" id="addHeadingX">x</button></div>
<p class="muted" id="addHeadingSub"></p>
<label class="add-heading-label" id="addHeadingParentWrap">Parent main heading<select id="addHeadingParent"></select></label>
<input type="text" id="addHeadingInput" placeholder="Type heading title" maxlength="120" autocomplete="off">
<div id="addHeadingMsg" class="warn hidden"></div>
<div class="modal-foot add-heading-foot"><button class="btn" id="addHeadingCancel">Cancel</button><button class="btn primary" id="addHeadingSave">Add</button></div>
</div></div>
<div id="donemodal"><div class="modal-box">
<h3>All learned — final map complete!</h3>
<p>Fully robust, interconnected concept map intact (mains + subs, all links bright). Review any stage via the history dropdown.</p>
<div class="modal-foot" style="display:flex;gap:10px;justify-content:flex-end"><button class="btn primary" id="doneOk">View final map</button><button class="btn" id="continueBtn" title="Study new material in the same workspace">Continue with new material</button></div>
<div id="continueMsg" class="warn hidden"></div>
</div></div>
<div id="printmodal" class="hidden"><div class="modal-box">
<div class="modal-head"><h3>Print Study Pack</h3><button class="btn sm" id="printX">x</button></div>
<p class="muted">Revision pack, anytime with status header. B&amp;W-safe, subs nested under mains.</p>
<label><input type="checkbox" id="ppChkMap" checked> Map image (list always prints)</label><br>
<label><input type="checkbox" id="ppChkWords" checked> In-your-words (last passed)</label><br>
<label><input type="checkbox" id="ppChkScn" checked> Scenarios + Used-in</label><br>
<label><input type="checkbox" id="ppChkLinks" checked> Links (per-concept + full list)</label>
<div id="ppMsg" class="muted"></div>
<div class="modal-foot" style="display:flex;gap:10px;justify-content:flex-end"><button class="btn" id="printCancel">Cancel</button><button class="btn primary" id="printGo">Print</button></div>
</div></div>
<div id="printPack" aria-hidden="true"></div>
<!-- Problem 4: init runs AFTER all modal divs so trailing Continue/close bindings (l12guideContinue/toL3Btn/toL5Btn/probe/phase2/doneOk) exist at bind time. src tags stay above; only the init call moved to the end. -->
<!-- m3 frozen post-Step 0 (no schema change): init order is steps12.init(user,session) vs l12/l3/l4/l5/phase2/history.init(session,user). Call sites match; do not unify. -->
<script>CogniMapSteps12.init({user_id}, '{session_id}'); CogniMapL12.init('{session_id}', {user_id}); CogniMapL3.init('{session_id}', {user_id}); CogniMapL4.init('{session_id}', {user_id}); CogniMapL5.init('{session_id}', {user_id}); CogniMapPhase2.init('{session_id}', {user_id}); CogniMapHistory.init('{session_id}', {user_id}); CogniMapStageFlow.init('{session_id}', {user_id}); CogniMapPrint.init('{session_id}', {user_id});
(function() {{
  var SID='{session_id}', UID={user_id};
  function esc(s) {{ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
  function showMsg(t) {{ var m=document.getElementById('wsRenameMsg'); if(!m) return; m.textContent=t||''; m.classList.toggle('hidden', !t); }}
  var btn=document.getElementById('wsRenameBtn'), box=document.getElementById('wsRenameBox'),
      inp=document.getElementById('wsRenameInput'), nm=document.getElementById('wsName');
  if(btn && box && inp) {{
    btn.onclick=function() {{ box.classList.remove('hidden'); showMsg(''); btn.style.display='none'; inp.focus(); inp.select(); }};
    document.getElementById('wsRenameCancel').onclick=function() {{ box.classList.add('hidden'); showMsg(''); btn.style.display=''; }};
    document.getElementById('wsRenameSave').onclick=async function() {{
      var name=inp.value.trim();
      if(!name) {{ showMsg('Workspace name required'); return; }}
      if(name.length>100) {{ showMsg('Workspace name max 100 chars'); return; }}
      try {{
        var r=await fetch('/api/sessions/'+SID+'?user_id='+UID, {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{name}})}});
        if(!r.ok) {{ showMsg((await r.text()).slice(0,300)); return; }}
        var s=await r.json(); var label=s.name || s.file || SID;
        nm.textContent=label; nm.title=label; inp.value=label;
        var top=document.getElementById('wsTopLabel'); if(top) {{ top.textContent='user #'+UID+' · '+label; top.title=label; }}
        try {{ document.title='CogniMap — '+label; }} catch(e) {{}}
        box.classList.add('hidden'); showMsg(''); btn.style.display='';
      }} catch(e) {{ showMsg('Rename failed — try again'); }}
    }};
    inp.onkeydown=function(e) {{ if(e.key==='Enter') document.getElementById('wsRenameSave').click(); if(e.key==='Escape') document.getElementById('wsRenameCancel').click(); }};
  }}
  // Keep the sidebar/top-bar labels in sync with server truth (covers
  // renames made in another tab + backfilled names on old sessions).
  (async function() {{ try {{
    var r=await fetch('/api/sessions/'+SID+'/state?user_id='+UID); if(!r.ok) return;
    var j=await r.json(); var s=(j&&j.session)||{{}}; var label=s.name || s.file || SID; if(!label) return;
    if(nm && nm.textContent!==label) {{ nm.textContent=label; nm.title=label; }}
    if(inp && document.getElementById('wsRenameBox').classList.contains('hidden')) inp.value=label;
    var top=document.getElementById('wsTopLabel'); if(top) {{ top.textContent='user #'+UID+' · '+label; top.title=label; }}
  }} catch(e) {{}} }})();
  // Continuous study (done → new iteration in the same workspace).
  try {{
    var sideBtn=document.getElementById('continueSideBtn'), sideMsg=document.getElementById('continueSideMsg');
    if(sideBtn) sideBtn.onclick=async function() {{
      if(sideMsg) {{ sideMsg.textContent=''; sideMsg.classList.add('hidden'); }}
      sideBtn.disabled=true;
      try {{
        var r=await fetch('/api/sessions/'+SID+'/continue?user_id='+UID, {{method:'POST'}});
        var txt=await r.text(); var j={{}}; try {{ j=JSON.parse(txt); }} catch(e) {{ j={{detail:txt}}; }}
        if(!r.ok) throw new Error(j.detail||('HTTP '+r.status));
        location.reload();
      }} catch(e) {{
        if(sideMsg) {{ sideMsg.textContent=e.message; sideMsg.classList.remove('hidden'); }}
        sideBtn.disabled=false;
      }}
    }};
    var doneOk=document.getElementById('doneOk'), contBtn=document.getElementById('continueBtn'), contMsg=document.getElementById('continueMsg'), doneModal=document.getElementById('donemodal');
    if(doneOk && doneModal) doneOk.onclick=function() {{ doneModal.classList.remove('open'); }};
    if(contBtn) contBtn.onclick=async function() {{
      if(contMsg) {{ contMsg.textContent=''; contMsg.classList.add('hidden'); }}
      contBtn.disabled=true;
      try {{
        var r=await fetch('/api/sessions/'+SID+'/continue?user_id='+UID, {{method:'POST'}});
        var txt=await r.text(); var j={{}}; try {{ j=JSON.parse(txt); }} catch(e) {{ j={{detail:txt}}; }}
        if(!r.ok) throw new Error(j.detail||('HTTP '+r.status));
        location.reload();
      }} catch(e) {{
        if(contMsg) {{ contMsg.textContent=e.message; contMsg.classList.remove('hidden'); }}
        contBtn.disabled=false;
      }}
    }};
  }} catch(e) {{}}
}})();</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def root():
    return picker_page()


@app.get("/u/{user_id}", response_class=HTMLResponse)
def user_home(user_id: int):
    # Locks §0 fail-closed (frozen Step 0): unknown user_id 404s, mirroring
    # api_list_sessions (never render an empty session list for /u/999… —
    # that would enumerate arbitrary ids as 200 while the API 404s).
    if not any(u.get("id") == int(user_id) for u in store.list_users()):
        raise HTTPException(404, "no such user")
    return user_page(user_id)


@app.get("/u/{user_id}/s/{session_id}", response_class=HTMLResponse)
def workspace(user_id: int, session_id: str):
    s = store.get_session(session_id)
    if not s or int(s["user_id"]) != int(user_id):
        raise HTTPException(404, "session not found for user")
    return workspace_page(user_id, session_id)


@app.get("/api/health")
def health():
    # S1 additive: {step, llama: live|stub, llm: live|stub, llm_model}.
    # Frozen keys ok/step kept; extra keys allowed, required keys unchanged.
    # Grill 2026-10-29: + data_mode (demo|auto) — tells demo-forced stubs
    # apart from keyless stubs (both report stub above).
    out: dict = {"ok": True, "step": _current_step()}
    out.update(parse.parse_status())
    out.update(llm.llm_status())
    out["data_mode"] = config.get_data_mode()
    return out


@app.get("/api/seed")
def seed():
    return JSONResponse({"concepts": llm.load_seed_concepts()})


@app.get("/api/users")
def api_list_users():
    return store.list_users()


@app.post("/api/users")
def api_create_user(payload: UserIn):
    try:
        return store.get_or_create_user(payload.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int):
    """Delete user cascade (UI_ISSUES.txt Problem 3): lite profiles, no auth.

    Deletes the user + all their sessions/data (sessions + session_files +
    concepts/links/scenarios/trail via store.delete_user). Missing user 404s.
    S6: also removes Build/uploads/{sid}/ dirs for owned sessions.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(404, "no such user")
    try:
        sids = [s["id"] for s in store.list_sessions(uid)]
    except Exception:
        sids = []
    ok = store.delete_user(uid)
    if not ok:
        raise HTTPException(404, "no such user")
    for sid in sids:
        _remove_uploads_session_dir(sid)
    return {"deleted": True, "user_id": uid}


@app.get("/api/sessions")
def api_list_sessions(user_id: int | None = None):
    """List sessions per user_id, ownership-filtered (Locks §0/§6).

    Lite profiles (name-pick, no auth) cannot authenticate the caller, so
    user_id is a filter, not a credential: the route returns only sessions
    whose sessions.user_id matches, never cross-user rows. Missing/invalid
    user_id fails closed with 404 ( consistent with session-scoped routes).
    """
    if user_id is None:
        raise HTTPException(404, "user_id required")
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(404, "user_id required")
    # Fail closed when the profile does not exist (prevents enumeration
    # of arbitrary ids as empty lists).
    if not any(u.get("id") == uid for u in store.list_users()):
        raise HTTPException(404, "no such user")
    return store.list_sessions(uid)


@app.post("/api/sessions")
def api_create_session(payload: SessionIn):
    # Locks §0 fail-closed (m3): unknown user_id 404s (never FK 500).
    try:
        uid = int(payload.user_id)
    except (TypeError, ValueError):
        raise HTTPException(404, "no such user")
    if not any(u.get("id") == uid for u in store.list_users()):
        raise HTTPException(404, "no such user")
    return store.create_session(uid, payload.file, payload.name)


@app.patch("/api/sessions/{session_id}")
def api_rename_session(session_id: str, payload: RenameIn, user_id: int | None = None):
    """Rename workspace (additive): updates sessions.name only.

    Ownership-checked (§0+§8): sessions.user_id == user_id, else 404.
    Validation: 1-100 chars, single line. File labels / session_files
    untouched. Missing user_id fails closed (404, never 422).
    """
    try:
        return store.rename_session(session_id, user_id, payload.name)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError:
        raise HTTPException(404, "no such session")
    except ValueError as e:
        raise HTTPException(400, str(e))


def _uploads_session_dir(session_id: str) -> str:
    # S1/S6: Build/uploads/{sid}/ (disk only, no store schema change).
    d = os.path.join(config.upload_root(), str(session_id))
    os.makedirs(d, exist_ok=True)
    return d


def _remove_uploads_session_dir(session_id: str) -> None:
    try:
        shutil.rmtree(os.path.join(config.upload_root(), str(session_id)), ignore_errors=True)
    except Exception as e:
        log.warning("uploads cleanup skipped %s: %s", session_id, e)


def _remove_upload_file(session_id: str, filename: str) -> None:
    try:
        p = os.path.join(config.upload_root(), str(session_id), str(filename))
        if os.path.isfile(p):
            os.remove(p)
    except Exception as e:
        log.warning("uploads file cleanup skipped %s/%s: %s", session_id, filename, e)


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str, user_id: int | None = None):
    """Delete session cascade (Locks §0/§6): ownership-checked.

    Deletes session_files + scoped domain rows (concepts/links/scenarios/
    trail) + the sessions row. Cross-user deletes 404 (no leak).
    S6: also removes Build/uploads/{sid}/ from disk.
    """
    try:
        s = store.require_owned_session(session_id, user_id)
    except KeyError:
        raise HTTPException(404, "no such session")
    except PermissionError as e:
        raise HTTPException(404, str(e))
    try:
        ok = store.delete_session(session_id, int(s["user_id"]))
    except PermissionError as e:
        raise HTTPException(404, str(e))
    if not ok:
        raise HTTPException(404, "no such session")
    _remove_uploads_session_dir(session_id)
    return {"deleted": True, "session_id": session_id}


@app.get("/api/sessions/{session_id}/state")
def api_state(session_id: str, user_id: int | None = None):
    s = _owned(session_id, user_id)
    concepts = store.list_concepts(session_id)
    mains = [c for c in concepts if c.get("kind") == "main"]
    subs = [c for c in concepts if c.get("kind") == "sub"]
    return {
        "session": s,
        "counts": {"concepts": len(concepts), "mains": len(mains), "subs": len(subs)},
        "links": len(store.list_links(session_id)),
        "scenarios": len(store.list_scenarios(session_id)),
        "trail": len(store.list_trail(session_id)),
    }


@app.get("/api/sessions/{session_id}/concepts")
def api_concepts(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.list_concepts(session_id)


@app.get("/api/sessions/{session_id}/links")
def api_links(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.list_links(session_id)


@app.get("/api/sessions/{session_id}/scenarios")
def api_scenarios(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.list_scenarios(session_id)


@app.get("/api/sessions/{session_id}/trail")
def api_trail(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.list_trail(session_id)


@app.get("/api/sessions/{session_id}/files")
def api_files(session_id: str, user_id: int | None = None):
    """File list (Locks §0): one row per filename; sessions.file mirrors primary."""
    _owned(session_id, user_id)
    return store.list_files(session_id)


@app.post("/api/sessions/{session_id}/seed-load")
def api_seed_load(session_id: str, user_id: int | None = None):
    """Demo seed via the locked parse→extract→Confirm round-trip (TODO Step 0).

    Gates: session must be in steps1-2 with no concepts yet (empty
    workspace); otherwise 400 — direct seed_concepts would bypass the
    Confirm stage check, ≥1-main guard, parent integrity, trail init and
    stage advance. Demo routes through parse_pdf + extract_concepts stubs
    then confirm_selection so all guards apply.
    """
    s = _owned(session_id, user_id)
    if (s.get("stage") or "") != "steps1-2":
        raise HTTPException(400, "already locked — concepts lock after Confirm")
    if store.list_concepts(session_id):
        raise HTTPException(400, "session not empty — remove files to reset first")
    label = (s.get("file") or "").strip() or "seed-demo.pdf"
    parsed = parse.parse_pdf(label)
    concepts = llm.extract_concepts(parsed.get("markdown", ""), parsed.get("figures"))
    try:
        out = store.confirm_selection(session_id, int(s["user_id"]), concepts)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    return {**out, "session_id": session_id}


# ---- Step 1 slice (additive) ----

@app.post("/api/sessions/{session_id}/upload")
def api_upload(session_id: str, payload: UploadIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    # Locks §6 lock: L1-3 read-only, no structural edits after Confirm.
    # Same gate as confirm_selection/seed-load — extraction after freeze
    # would break the reviewer lock check.
    if (s.get("stage") or "") != "steps1-2":
        raise HTTPException(400, "already locked — concepts lock after Confirm")
    label = (payload.file or "").strip() or "seed-demo.pdf"
    parsed = parse.parse_pdf(label)
    session = store.add_file(session_id, label)
    return {"file": label, "parsed": parsed, "session": session,
            "files": store.list_files(session_id)}


@app.delete("/api/sessions/{session_id}/file")
def api_remove_file(session_id: str, filename: str | None = None,
                     user_id: int | None = None):
    """Per-file remove (Locks §6): ?filename= removes one row and keeps data
    while files remain; removing the last file full-wipes via
    clear_session_data. Legacy callers without ?filename= remove the primary
    label (single-file sessions still full-wipe as before).
    S6: disk copy under Build/uploads/{sid}/ removed as well; last-file reset
    removes the whole session dir."""
    s = _owned(session_id, user_id)
    try:
        out = store.remove_file(session_id, filename, user_id=int(s["user_id"]))
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError:
        raise HTTPException(404, "no such session")
    try:
        if out.get("reset"):
            _remove_uploads_session_dir(session_id)
        elif filename:
            _remove_upload_file(session_id, (filename or "").strip())
    except Exception as e:
        log.warning("uploads cleanup skipped: %s", e)
    return out


@app.post("/api/sessions/{session_id}/upload-pdf")
def api_upload_pdf(session_id: str, user_id: int | None = None,
                   file: UploadFile | None = File(None)):
    """S1 upload bytes (additive): multipart PDF -> Build/uploads/{sid}/{filename}.

    Frozen POST /upload {file: label} unchanged; this endpoint adds real bytes
    for the live LlamaParse path. Disk only, no store.py schema change —
    session_files stays filename-only. Limits: MAX_PDF_BYTES (S6).
    """
    s = _owned(session_id, user_id)
    if (s.get("stage") or "") != "steps1-2":
        raise HTTPException(400, "already locked — concepts lock after Confirm")
    if file is None or not (file.filename or "").strip():
        raise HTTPException(400, "pdf file required (multipart field 'file')")
    filename = os.path.basename((file.filename or "").strip()) or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only .pdf accepted here (labels still via /upload)")
    try:
        data = file.file.read()
    except Exception:
        raise HTTPException(400, "could not read upload")
    if not data:
        raise HTTPException(400, "empty pdf")
    if len(data) > config.MAX_PDF_BYTES:
        raise HTTPException(400, f"pdf over {config.MAX_PDF_BYTES} bytes")
    sdir = _uploads_session_dir(session_id)
    dest = os.path.join(sdir, filename)
    try:
        with open(dest, "wb") as fh:
            fh.write(data)
    except Exception as e:
        raise HTTPException(500, f"could not save upload: {e}")
    # Live parse attempt with bytes (falls back to stub, never 502).
    parsed = parse.parse_pdf(filename, pdf_bytes=data)
    if parsed.get("mode") != "live" and parsed.get("fallback_reason"):
        log.warning("upload-pdf fallback %s: %s", filename, parsed.get("fallback_reason"))
    session = store.add_file(session_id, filename)
    return {"file": filename, "parsed": parsed, "session": session,
            "files": store.list_files(session_id)}


@app.post("/api/sessions/{session_id}/continue")
def api_continue(session_id: str, user_id: int | None = None):
    """Continuous study (Q5/Q8/Q12): done → steps1-2 for a new iteration.
    Preserves the frozen map; next upload/extract/confirm builds the new pool."""
    s = _owned(session_id, user_id)
    try:
        return store.continue_session(session_id, int(s["user_id"]))
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/sessions/{session_id}/extract")
def api_extract(session_id: str, user_id: int | None = None):
    s = _owned(session_id, user_id)
    # Locks §6 lock: extraction is a Steps 1-2 operation only.
    if (s.get("stage") or "") != "steps1-2":
        raise HTTPException(400, "already locked — concepts lock after Confirm")
    cur_iter = store.get_iteration(session_id)
    cur_files = store.list_current_files(session_id)
    if not cur_files and not (s.get("file") or "").strip():
        raise HTTPException(400, "upload a file first (Select Files)")
    # Continuous Q7: merged single extract — filename-order concat of current-
    # iteration files, clipped by the P1 8000-char window in build_p1_user.
    # S1 disk-bytes preference preserved per file; label-only stays stub.
    file_labels = [f.get("filename") for f in cur_files if (f.get("filename") or "").strip()]
    if not file_labels:
        file_labels = [(s.get("file") or "").strip()]
    md_parts: list[str] = []
    all_figs: list[dict] = []
    parsed_file = file_labels[0] if file_labels else (s.get("file") or "")
    parsed_pages: list[int] = []
    parsed_mode = "stub"
    parsed_reason = ""
    for _label in file_labels:
        _pdf_bytes: bytes | None = None
        try:
            _cand = os.path.join(config.upload_root(), str(session_id), str(_label))
            if os.path.isfile(_cand) and os.path.getsize(_cand) <= config.MAX_PDF_BYTES:
                with open(_cand, "rb") as _fh:
                    _pdf_bytes = _fh.read()
        except Exception as e:
            log.warning("extract disk read skipped %s: %s", _label, e)
            _pdf_bytes = None
        _parsed = parse.parse_pdf(_label, pdf_bytes=_pdf_bytes)
        _md = (_parsed.get("markdown") or "").strip()
        if _md:
            md_parts.append(f"<!-- file {_label} -->\n{_md}")
        all_figs.extend(_parsed.get("figures") or [])
        if not parsed_pages and _parsed.get("pages"):
            parsed_pages = list(_parsed.get("pages") or [])
        # Live if any file parsed live; else keep stub reason.
        if _parsed.get("mode") == "live":
            parsed_mode = "live"
            parsed_reason = ""
        elif parsed_mode != "live" and _parsed.get("fallback_reason"):
            parsed_reason = str(_parsed.get("fallback_reason") or "")
    merged_md = "\n\n".join(md_parts)
    parsed = {"file": ", ".join(file_labels), "pages": parsed_pages, "mode": parsed_mode, "fallback_reason": parsed_reason,
              "markdown": merged_md, "figures": all_figs}
    status = llm.extract_concepts_with_status(merged_md, all_figs)
    concepts = status["concepts"]
    mode = status.get("mode") or "stub"
    model = status.get("model") or "stub"
    if status.get("fallback_reason"):
        log.warning("extract fallback %s: %s", parsed.get("file"), status.get("fallback_reason"))
    out: dict = {"concepts": concepts,
                 "parsed": {"file": parsed.get("file"), "pages": parsed.get("pages"),
                            "mode": parsed.get("mode", "stub"),
                            "fallback_reason": parsed.get("fallback_reason", "")},
                 "mode": mode, "model": model}
    if mode == "stub":
        # Grill 2026-10-29: demo-forced wording drops the "connect keys"
        # tail — keys exist in demo mode, so that advice would mislead.
        if config.is_demo_forced():
            out["warning"] = "Demo mode (stubbed) — parse/extract use the seed demo."
        else:
            out["warning"] = "Demo mode (stubbed) — connect keys for live parse/extract."
    return out


@app.post("/api/sessions/{session_id}/confirm-selection")
def api_confirm(session_id: str, payload: ConfirmIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    try:
        return store.confirm_selection(session_id, int(s["user_id"]), payload.concepts)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


# ---- Step 2 slice: L1-2 drawer verify (additive) ----

@app.get("/api/sessions/{session_id}/l12/status")
def api_l12_status(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.l12_status(session_id)


@app.post("/api/sessions/{session_id}/l12/verify")
def api_l12_verify(session_id: str, payload: VerifyIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    # B3 stage gate (Locks §4+§6): L1-2 verifies live only in L1-2. Late
    # verifies after advance (L3/L4/L5/Phase2/done) would append L1-2 trail
    # rows post-hoc — block 400. Phase-2 sub flow stays usable: phase2/L1-2
    # verifies subs (mains history-only, blocked below).
    if (s.get("stage") or "") != "L1-2":
        raise HTTPException(400, "L1-2 not active (stage gate)")
    cid = (payload.concept_id or "").strip()
    text = (payload.paraphrase or "").strip()
    if not text:
        raise HTTPException(400, "write your paraphrase first")
    # Kind-phase match (§7 math) + continuous iteration gate (Q10):
    # phase1 verifies mains, phase2 verifies subs; only current-iteration
    # concepts are verifiable (old frozen rows are history-only).
    _concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    _c = _concepts.get(cid)
    if _c:
        _phase = (s.get("phase") or "phase1")
        if _phase == "phase1" and _c.get("kind") != "main":
            raise HTTPException(400, "Phase 1 verifies mains only (subs hidden for Phase-2)")
        if _phase == "phase2" and _c.get("kind") != "sub":
            raise HTTPException(400, "Main completed in Phase 1 — history-only in Phase 2")
        try:
            _cur_iter = store.get_iteration(session_id)
            _c_iter = int((_c.get("iteration") or 1))
        except Exception:
            _cur_iter, _c_iter = 1, 1
        if _c_iter != _cur_iter:
            raise HTTPException(400, "Concept from a previous iteration — history-only")
    try:
        # Locks §8: session/id-keyed — resolves the explanation server-side
        # by owned (session_id, concept_id), never client text. S2 live path
        # returns mode/model/fallback_reason out-of-band; a valid live fail
        # stays live; only I/O/bad-JSON failures fall back to the lenient stub.
        eval_status = llm.evaluate_paraphrase_with_status(
            session_id, cid, text, user_id=user_id
        )
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError:
        raise HTTPException(400, "unknown concept for this session")
    result = eval_status["evaluation"]
    mode = eval_status.get("mode") or "stub"
    model = eval_status.get("model") or "stub"
    if eval_status.get("fallback_reason"):
        # Server-side only; never log keys (S7).
        log.warning("l12 verify fallback %s: %s", cid,
                    eval_status.get("fallback_reason"))
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    c = concepts.get(cid)
    bypass = bool(c) and c.get("source") == "user_added"
    passed = bool(result.get("passed"))
    if bypass and passed:
        store.set_user_explanation(session_id, cid, text)  # blue text lives on row
    store.record_l12_attempt(
        session_id, int(s["user_id"]), cid, text, passed,
        str(result.get("accuracy", "")), str(result.get("originality", "")),
        str(result.get("feedback", "")), str(result.get("hint", "")), bypass,
    )
    progress = store.l12_status(session_id)
    l3_ready = False
    if progress["complete"] and (s.get("stage") == "L1-2"):
        store.set_stage(session_id, "L3")
        l3_ready = True
    if bypass:
        # Locks §9: blue rows carry user explanation + warning-ack + saved
        # flag, NO accuracy/originality (bypass, no LLM). mode=bypass is an
        # additive label only — the locked blue keys stay unchanged.
        blue_out = {
            "passed": passed,
            "feedback": str(result.get("feedback", "")),
            "hint": str(result.get("hint", "")),
            "warning_ack": "Ensure your self-defined concept is accurate — not verified against source.",
            "user_explanation": text,
            "saved": passed,
            "bypass": True,
            "mode": mode,
            "model": model,
            "progress": progress,
            "l3_ready": l3_ready,
        }
        return blue_out
    out = {**result, "bypass": False, "mode": mode, "model": model,
           "progress": progress, "l3_ready": l3_ready}
    if mode == "stub":
        out["warning"] = "Demo mode (stubbed) — paraphrase check is lenient and not live."
    return out


# ---- Step 3 slice: L3 Apply generate + submit (additive) ----

class L3SubmitIn(BaseModel):
    scenario_id: str = ""
    selections: list[dict] = []  # [{concept_id, justification}]


@app.get("/api/sessions/{session_id}/l3/status")
def api_l3_status(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.l3_status(session_id)


@app.post("/api/sessions/{session_id}/l3/generate")
def api_l3_generate(session_id: str, user_id: int | None = None):
    s = _owned(session_id, user_id)
    if (s.get("stage") or "") != "L3":
        raise HTTPException(400, "Level 3 not active (complete L1-2 first)")
    st = store.l3_status(session_id)
    # Honest 0-total shape (§3): total 0 is not complete — guards (≥1 main /
    # ≥1 sub) make this unreachable, but never mask it as complete:True.
    if (st.get("total") or 0) == 0:
        return {"complete": False, "progress": st}
    if st["complete"] or not st["uncovered"]:
        return {"complete": True, "progress": st}
    existing = store.active_scenario(session_id)
    if existing:
        locked = store.scenario_passed_ids(session_id, existing["id"])
        # Locks §3: pool = all visible-counted; scenario_concept_ids stays
        # server-side hidden (never sent to the client — omission feedback is
        # the only reveal). UI renders pool unchecked.
        return {"id": existing["id"], "scenario_id": existing["id"],
                "text": existing.get("text", ""),
                "locked_passed": locked, "progress": st, "pool": st["counted"]}
    chunk = store.partition_chunks(st["uncovered"])[0]
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    # S3 (G1): server-resolved chunk rows feed the live P3 lanes; the frozen
    # joined string stays the stub's context (keyless behaviour unchanged).
    chunk_rows = [concepts[cid] for cid in chunk if cid in concepts]
    context = "; ".join(
        f"{cid}: {(concepts.get(cid) or {}).get('explanation_text', '')}" for cid in chunk
    )
    # Locks §3+§7 + continuous Q9b: context may carry mains as display-only
    # background in Phase-2 — never chunked/pooled. Continuous: old-iteration
    # mains ride as background too (new-only pool, old as context).
    mains_rows: list[dict] = []
    if st.get("phase") == "phase2":
        mains_rows = [c for c in store.list_concepts(session_id)
                      if c.get("kind") == "main"]
    try:
        _cur_iter_bg = store.get_iteration(session_id)
    except Exception:
        _cur_iter_bg = 1
    if _cur_iter_bg > 1:
        try:
            _old_mains = [c for c in store.list_concepts(session_id)
                          if c.get("kind") == "main" and int(c.get("iteration") or 1) < _cur_iter_bg]
        except Exception:
            _old_mains = []
        # Merge without duplicates (Phase-2 mains already include old mains).
        _seen_bg = {c.get("id") for c in mains_rows}
        for _om in _old_mains:
            if _om.get("id") not in _seen_bg:
                mains_rows.append(_om)
                _seen_bg.add(_om.get("id"))
        mains_bg = "; ".join(
            f"{c['id']}: {c.get('explanation_text','')}" for c in mains_rows)
        if mains_bg:
            context = (context + " | mains background: " + mains_bg) if context else mains_bg
    # S3 live chain (labelled): app owns partition; the model verbalizes only
    # and must echo the chunk ids. fallback_reason logs server-side only (S7).
    gen_status = llm.generate_scenario_with_status(
        chunk, context, chunk_rows=chunk_rows, mains_rows=mains_rows
    )
    gen = gen_status["scenario"]
    if gen_status.get("fallback_reason"):
        log.warning("l3 generate fallback %s: %s", session_id,
                    gen_status.get("fallback_reason"))
    try:
        row = store.create_scenario(session_id, chunk, gen["text"],
                                    user_id=int(s["user_id"]))
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    out = {"id": row["id"], "scenario_id": row["id"], "text": row.get("text", ""),
           "locked_passed": [], "progress": store.l3_status(session_id),
           "pool": st["counted"],
           "mode": gen_status.get("mode") or "stub",
           "model": gen_status.get("model") or "stub"}
    if out["mode"] == "stub":
        out["warning"] = ("Demo mode (stubbed) — scenario text is "
                          "stub-backed and not live.")
    return out


@app.post("/api/sessions/{session_id}/l3/submit")
def api_l3_submit(session_id: str, payload: L3SubmitIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    # State-machine gate (Locks §6+§10): submit lives only in L3. Out-of-order
    # writes (L3 after L4, L5 probe ordering) would corrupt trail counts.
    if (s.get("stage") or "") != "L3":
        raise HTTPException(400, "Level 3 not active (complete L1-2 first)")
    rows = {x["id"]: x for x in store.list_scenarios(session_id)}
    scn = rows.get((payload.scenario_id or "").strip())
    if not scn:
        raise HTTPException(400, "unknown scenario for this session")
    if scn.get("cleared"):
        raise HTTPException(400, "scenario already cleared")
    required = list(scn.get("concept_ids") or [])
    uid = int(s["user_id"])
    # M2 pool discipline (§3): pool = all visible-counted (mains P1 / subs P2).
    # Fabricated ids outside the pool → 400, no trail write. In-pool-but-not-
    # required stays tier-1 "not related" (safe direction, no clear).
    _, _pool_ids = store.l3_counted_ids(session_id)
    _pool = set(_pool_ids)
    # Scenario itself must belong to the current counted set (filtered math
    # §7 — stale-phase scenarios never resume/submit).
    if set(required or []) - _pool:
        raise HTTPException(400, "scenario not in current phase pool")
    sub = {x.get("concept_id", ""): (x.get("justification") or "") for x in (payload.selections or [])}
    for _cid in sub:
        if _cid not in _pool:
            raise HTTPException(400, f"concept {_cid or '(empty)'} outside current pool")
    locked = set(store.scenario_passed_ids(session_id, scn["id"]))
    # Lock-passed: locked stay green without rewrite; everything else goes to
    # the §8 evaluator, which flags tier-1 wrong picks itself (selected but
    # not required → "not related", blocks clear, prevents select-all).
    unlocked_sels = [
        {"concept_id": cid, "justification": sub[cid]}
        for cid in sub if cid not in locked
    ]
    try:
        # S3 live chain (labelled): ONE merged call grades only the live
        # lanes (tier-1/empty/locked stay rule-based; blue joins per G2').
        ev_status = llm.evaluate_scenario_with_status(
            session_id, scn["id"], unlocked_sels, user_id=user_id
        )
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    ev = ev_status["evaluation"]
    if ev_status.get("fallback_reason"):
        # Server-side only; never log keys (S7).
        log.warning("l3 submit fallback %s/%s: %s", session_id, scn["id"],
                    ev_status.get("fallback_reason"))
    newly_passed: set[str] = set()
    results: list[dict] = []
    for r in ev.get("results", []):
        cid = r.get("concept_id", "")
        ok = bool(r.get("passed"))
        store.record_l3_attempt(session_id, uid, scn["id"], cid, sub.get(cid, ""),
                                ok, str(r.get("feedback", "")), str(r.get("hint", "")))
        if ok:
            newly_passed.add(cid)
        results.append({**r, "locked": False})
    # Omission is lock-aware (locked coverage excuses a missing selection);
    # wrong is any submitted id outside the hidden required set.
    submitted = {cid for cid in sub if cid in required}
    wrong = sorted(cid for cid in sub if cid not in required)
    missed = [cid for cid in required if cid not in submitted and cid not in locked]
    for cid in sorted(locked):
        results.append({"concept_id": cid, "passed": True, "locked": True,
                        "feedback": "Locked green from earlier pass.", "hint": ""})
    cmap = {c["id"]: c for c in store.list_concepts(session_id)}
    for cid in missed:  # §3 tier 4: omission flagged, no clear (name title, not bare id)
        title = (cmap.get(cid) or {}).get("title") or cid
        store.record_l3_attempt(session_id, uid, scn["id"], cid, "", False,
                                f"Required concept not selected: {title} ({cid}).", "Check it and defend why it applies.", omitted=True)
    cleared_now = (not missed) and (not wrong) and set(required) <= (locked | newly_passed)
    if cleared_now:
        try:
            store.set_scenario_cleared(session_id, scn["id"], user_id=uid)
        except PermissionError as e:
            raise HTTPException(404, str(e))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
    progress = store.l3_status(session_id)
    l4_ready = False
    if progress["complete"] and (s.get("stage") == "L3"):
        store.set_stage(session_id, "L4")
        l4_ready = True
    out = {"results": results, "missed_ids": missed, "scenario_cleared": cleared_now,
            "locked_passed": sorted(locked | newly_passed), "progress": progress,
            "l4_ready": l4_ready,
            "mode": ev_status.get("mode") or "stub",
            "model": ev_status.get("model") or "stub"}
    if out["mode"] == "stub":
        out["warning"] = ("Demo mode (stubbed) — justification grading is "
                          "lenient and not live.")
    return out


# ---- Step 4 slice: L4 Analyze (additive) ----

class L4CreateIn(BaseModel):
    from_id: str = ""
    to_id: str = ""
    edge_type: str = ""
    # M3 (Locks §4 Q11 radio-vs-custom split): preset-radio sends
    # is_preset=True with an exact preset; custom textbox sends False.
    # Missing flag defaults to custom (False) so direct POST custom
    # duplicate (exact "causes" etc) → 400 with "use preset" message.
    is_preset: bool | None = None


@app.get("/api/sessions/{session_id}/l4/status")
def api_l4_status(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.l4_status(session_id)


@app.post("/api/sessions/{session_id}/l4/links")
def api_l4_create(session_id: str, payload: L4CreateIn, user_id: int | None = None):
    _owned(session_id, user_id)
    # M3: missing is_preset → custom path (strict). Preset-radio must send
    # is_preset=True; custom (incl. direct API custom duplicate) → 400.
    flag = payload.is_preset if payload.is_preset is not None else False
    try:
        return store.create_link(session_id, payload.from_id, payload.to_id, payload.edge_type,
                                 user_id=user_id, is_preset=flag)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/sessions/{session_id}/l4/links/{link_id}")
def api_l4_delete(session_id: str, link_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    try:
        store.delete_link(session_id, link_id, user_id=user_id)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"deleted": True, "status": store.l4_status(session_id)}


@app.post("/api/sessions/{session_id}/l4/finish")
def api_l4_finish(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    try:
        return store.l4_finish(session_id, user_id=user_id)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- Step 5 slice: L5 Evaluate (additive) ----

class L5ProbeIn(BaseModel):
    link_id: str = ""
    why_answer: str = ""
    fail_answer: str = ""


@app.get("/api/sessions/{session_id}/l5/status")
def api_l5_status(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    return store.l5_status(session_id)


@app.post("/api/sessions/{session_id}/l5/probe")
def api_l5_probe(session_id: str, payload: L5ProbeIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    # State-machine gate (Locks §6+§10): probe lives only in L5 (after Finish
    # dims/fixes N). Early probes would write L5 trail before entry.
    if (s.get("stage") or "") != "L5":
        raise HTTPException(400, "Level 5 not active (complete Level 4 first)")
    lid = (payload.link_id or "").strip()
    why = (payload.why_answer or "").strip()
    fail = (payload.fail_answer or "").strip()
    if not lid:
        raise HTTPException(400, "link_id required")
    if not why or not fail:
        raise HTTPException(400, "answer both Why and When to Submit")
    # M1 (§5 N = new links only): membership-gate before eval — excluded
    # Phase-1 links in Phase-2 stay bright, never probed. Fail fast 400 with
    # no trail write / no flag touch (UI also blocks in l5.js:90).
    try:
        _tst = store.l5_status(session_id)
        if lid not in set(_tst.get("target_ids") or []):
            raise HTTPException(400, "link not in current L5 target set")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        # S5 live chain (labelled): ONE P5 call grades only the live lanes
        # (locked sides / empty answers / both-locked stay rule-based; blue
        # joins the call per S5-G1).
        probe = llm.probe_link_with_status(session_id, lid, why, fail,
                                           user_id=user_id)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    ev = probe["evaluation"]
    if probe.get("fallback_reason"):
        # Server-side only; never log keys (S7).
        log.warning("l5 probe fallback %s/%s: %s", session_id, lid,
                    probe.get("fallback_reason"))
    try:
        link = store.probe_submit(session_id, lid, why, fail, ev, user_id=user_id)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    status = store.l5_status(session_id)
    phase2_ready = False
    if status["complete"] and (s.get("stage") == "L5"):
        if status["phase"] == "phase1":
            store.set_stage(session_id, "Phase2")
            phase2_ready = True
        else:
            store.set_stage(session_id, "done")
    out = {**ev, "link": link, "progress": status, "phase2_ready": phase2_ready,
            "done": status["complete"] and status["phase"] == "phase2",
            "mode": probe.get("mode") or "stub",
            "model": probe.get("model") or "stub"}
    if out["mode"] == "stub":
        out["warning"] = ("Demo mode (stubbed) — probing grading is "
                          "lenient and not live.")
    return out


# ---- Step 6 slice: Phase-2 + History (additive) ----

class Phase2ConfirmIn(BaseModel):
    subs: list[dict] = []


@app.get("/api/sessions/{session_id}/phase2/status")
def api_phase2_status(session_id: str, user_id: int | None = None):
    _owned(session_id, user_id)
    s = store.get_session(session_id)
    concepts = store.list_concepts(session_id)
    mains = [c for c in concepts if c.get("kind") == "main"]
    subs = [c for c in concepts if c.get("kind") == "sub"]
    return {"stage": (s or {}).get("stage"), "phase": (s or {}).get("phase"),
            "mains": mains, "subs": subs}


@app.post("/api/sessions/{session_id}/phase2/confirm")
def api_phase2_confirm(session_id: str, payload: Phase2ConfirmIn, user_id: int | None = None):
    s = _owned(session_id, user_id)
    try:
        return store.confirm_phase2(session_id, int(s["user_id"]), payload.subs)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
