"""Print Study Pack tests (grilled Q1-Q14, browser print only).

Verifies the additive print layer: sidebar button + preview modal with 4
toggles + hidden #printPack + print.js builder + @media print CSS.
No new API routes (frozen shapes unchanged).
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

_DB = os.path.join(tempfile.gettempdir(), f"cognimap_test_{os.getpid()}.db")
for _p in (_DB, _DB + "-journal"):
    try:
        os.remove(_p)
    except OSError:
        pass
os.environ["COGNIMAP_DB"] = _DB
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.testclient import TestClient

from app import store
from app.main import app

client = TestClient(app)


def _mk_user(prefix="prt"):
    return store.get_or_create_user(f"{prefix}-{uuid.uuid4().hex[:6]}")


def _main_row(cid, **kw):
    d = {"concept_id": cid, "title": f"T-{cid}", "kind": "main",
         "parent_id": None, "source": "extracted",
         "explanation_type": "definition", "explanation_text": f"text {cid}",
         "explanation_source": "extracted", "pages": [5],
         "diagram_refs": [], "diagram_description": ""}
    d.update(kw)
    return d


def test_workspace_has_print_layer():
    u = _mk_user()
    s = store.create_session(u["id"], "p.pdf")
    html = client.get(f"/u/{u['id']}/s/{s['id']}").text
    assert 'id="printBtn"' in html
    assert 'id="printmodal"' in html
    assert 'id="printPack"' in html
    assert 'print.js' in html
    for chk in ("ppChkMap", "ppChkWords", "ppChkScn", "ppChkLinks"):
        assert chk in html, chk
    assert "CogniMapPrint.init" in html
    # Preview modal copy: toggles + B&W-safe note.
    assert "Map image" in html and "In-your-words" in html


def test_print_js_builds_from_existing_endpoints():
    p = os.path.join(os.path.dirname(__file__), "..", "static", "print.js")
    js = open(p, encoding="utf-8").read()
    for ep in ("/concepts", "/links", "/scenarios", "/trail", "/state"):
        assert ep in js, ep
    assert "window.print()" in js
    # Best-effort image + list-always fallback (Q7/Q14).
    assert "Map image unavailable" in js
    assert "list below is complete" in js
    # Provenance tags + B&W text state (Q8).
    assert "[Doc" in js and "[Mine" in js and "AI-grounded" in js
    assert "pending" in js and "verified" in js
    # Dossier order + nesting (Q6/Q11).
    assert "Used in" in js and "pp-sub" in js


def test_print_css_bw_and_repeat_header():
    p = os.path.join(os.path.dirname(__file__), "..", "static", "style.css")
    css = open(p, encoding="utf-8").read()
    assert "@media print" in css
    assert "#printPack" in css
    assert "pp-runhead" in css and "pp-runfoot" in css
    # B&W-safe: grayscale + black-on-white in print block.
    assert "grayscale(100%)" in css
    # Screen hides pack; print hides chrome.
    assert "#printPack{display:none}" in css.replace(" ", "").replace("\n", "") or "#printPack{display:none}" in css.replace(" ", "")
    assert ".sidebar" in css and "display:none" in css
    # Blank-page guards: app shell fully hidden in print (no 100vh leftovers),
    # empty pack prints nothing, no avoid-page push to blank sheets.
    print_block = css.split("@media print", 1)[1]
    assert ".layout" in print_block and "display:none" in print_block
    assert "#printPack:empty" in print_block
    assert "100vh" not in print_block
    assert "avoid-page" not in print_block


def test_no_new_print_api_route():
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("/print" in p for p in paths), sorted(paths)
    assert client.get("/api/health").json()["step"] == 6


def test_print_does_not_break_locked_flow():
    u = _mk_user()
    s = store.create_session(u["id"], "p.pdf")
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [_main_row("m1"), _main_row("m2")])
    # Print layer present at L1-2 too (anytime print).
    html = client.get(f"/u/{u['id']}/s/{sid}").text
    assert 'id="printBtn"' in html
    r = client.get(f"/api/sessions/{sid}/concepts", params={"user_id": u["id"]})
    assert r.status_code == 200 and len(r.json()) == 2
