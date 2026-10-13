"""Reviewer tests for Steps_Locks B1–B6 (gates for TODO Steps 0–3 re-freeze).

Run: `pytest tests` from Build/ (or `pytest Build/tests` from repo root).
Uses an isolated temp SQLite DB (COGNIMAP_DB set before app import).
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

import pytest
from starlette.testclient import TestClient

from app import llm, parse, store
from app import models
from app.main import app

client = TestClient(app)


# ---- helpers ----

def mk_user(prefix="u"):
    return store.get_or_create_user(f"{prefix}-{uuid.uuid4().hex[:6]}")


def mk_session(uid, file=""):
    return store.create_session(uid, file)


def main_row(cid, **kw):
    d = {"concept_id": cid, "title": f"T-{cid}", "kind": "main",
         "parent_id": None, "source": "extracted",
         "explanation_type": "definition", "explanation_text": f"text {cid}",
         "explanation_source": "extracted", "pages": [5],
         "diagram_refs": [], "diagram_description": ""}
    d.update(kw)
    return d


def blue_row(cid):
    return main_row(cid, source="user_added", explanation_text="",
                    explanation_source="user")


FOUR = [main_row("c1"), main_row("c2"), main_row("c3"), blue_row("c4")]


def confirm4(sid, uid):
    return store.confirm_selection(sid, uid, FOUR)


def pass_l12(sid, uid, ids):
    for cid in ids:
        store.record_l12_attempt(sid, uid, cid, f"para {cid}", True, "a", "o", "fb", "")


def start_l3(sid, uid, concepts=None):
    store.confirm_selection(sid, uid, concepts or FOUR)
    # Blue two-step: Confirm stores "", L1-2 save fills it.
    for c in (concepts or FOUR):
        if c.get("source") == "user_added":
            store.set_user_explanation(sid, c["concept_id"], "user note")
    ids = [c["concept_id"] for c in (concepts or FOUR)]
    pass_l12(sid, uid, ids)
    store.set_stage(sid, "L3")
    return ids


# ---- B2: ownership ----

def test_ownership_html_404():
    a = mk_user("htmlA")
    b = mk_user("htmlB")
    s = mk_session(a["id"])
    assert client.get(f"/u/{a['id']}/s/{s['id']}").status_code == 200
    assert client.get(f"/u/{b['id']}/s/{s['id']}").status_code == 404


def test_api_requires_user_id():
    a = mk_user("apiA")
    b = mk_user("apiB")
    s = mk_session(a["id"])
    sid = s["id"]
    assert client.get(f"/api/sessions/{sid}/state").status_code == 404
    assert client.get(f"/api/sessions/{sid}/state",
                      params={"user_id": b["id"]}).status_code == 404
    assert client.get(f"/api/sessions/{sid}/concepts",
                      params={"user_id": b["id"]}).status_code == 404
    assert client.get(f"/api/sessions/{sid}/l3/status",
                      params={"user_id": b["id"]}).status_code == 404
    r = client.get(f"/api/sessions/{sid}/state", params={"user_id": a["id"]})
    assert r.status_code == 200


def test_ownership_every_route_404():
    """B1: every /api/sessions/{sid}/*?user_id= + HTML verifies
    sessions.user_id==requester, never session_id alone (Locks §0+§8+§10)."""
    a = mk_user("ownA")
    b = mk_user("ownB")
    s = mk_session(a["id"], "o.pdf")
    sid = s["id"]
    # Seed minimal data so L4/L5/phase2 routes have rows to gate (not 400).
    store.confirm_selection(sid, a["id"], FOUR)
    # HTML workspace route.
    assert client.get(f"/u/{a['id']}/s/{sid}").status_code == 200
    assert client.get(f"/u/{b['id']}/s/{sid}").status_code == 404
    assert client.get(f"/u/{a['id']}/s/nope").status_code == 404
    gets = [
        "state", "concepts", "links", "scenarios", "trail", "files",
        "l12/status", "l3/status", "l4/status", "l5/status", "phase2/status",
    ]
    for p in gets:
        r0 = client.get(f"/api/sessions/{sid}/{p}")
        assert r0.status_code == 404, p
        rb = client.get(f"/api/sessions/{sid}/{p}", params={"user_id": b["id"]})
        assert rb.status_code == 404, p
        ra = client.get(f"/api/sessions/{sid}/{p}", params={"user_id": a["id"]})
        assert ra.status_code == 200, (p, ra.text)
    posts_missing = [
        ("seed-load", {}),
        ("upload", {"file": "x.pdf"}),
        ("extract", None),
        ("confirm-selection", {"concepts": FOUR}),
        ("l12/verify", {"concept_id": "c1", "paraphrase": "p"}),
        ("l3/generate", None),
        ("l3/submit", {"scenario_id": "nope", "selections": []}),
        ("l4/links", {"from_id": "c1", "to_id": "c2", "edge_type": "causes"}),
        ("l4/finish", None),
        ("l5/probe", {"link_id": "nope", "why_answer": "w", "fail_answer": "f"}),
        ("phase2/confirm", {"subs": []}),
    ]
    for p, body in posts_missing:
        # Missing user_id fails closed (404, never 422/200).
        if body is None:
            r0 = client.post(f"/api/sessions/{sid}/{p}")
        else:
            r0 = client.post(f"/api/sessions/{sid}/{p}", json=body)
        assert r0.status_code == 404, (p, r0.text)
        # Cross-user fails closed (404).
        if body is None:
            rb = client.post(f"/api/sessions/{sid}/{p}", params={"user_id": b["id"]})
        else:
            rb = client.post(f"/api/sessions/{sid}/{p}", params={"user_id": b["id"]},
                             json=body)
        assert rb.status_code == 404, (p, rb.text)
    # DELETE file + DELETE session also gate.
    assert client.delete(f"/api/sessions/{sid}/file",
                         params={"filename": "o.pdf"}).status_code == 404
    assert client.delete(f"/api/sessions/{sid}/file",
                         params={"user_id": b["id"],
                                 "filename": "o.pdf"}).status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}",
                         params={"user_id": b["id"]}).status_code == 404
    # Owner still works.
    assert client.get(f"/api/sessions/{sid}/state",
                      params={"user_id": a["id"]}).status_code == 200


def test_confirm_ownership_mismatch():
    a = mk_user("cfA")
    b = mk_user("cfB")
    s = mk_session(a["id"])
    with pytest.raises(PermissionError):
        store.confirm_selection(s["id"], b["id"], [main_row("m1")])
    r = client.post(f"/api/sessions/{s['id']}/confirm-selection",
                    params={"user_id": b["id"]},
                    json={"concepts": [main_row("m1")]})
    assert r.status_code == 404


# ---- B1: session_files + cascade ----

def test_files_per_file_vs_last_file():
    u = mk_user("fileU")
    s = mk_session(u["id"], "a.pdf")
    sid = s["id"]
    assert [f["filename"] for f in store.list_files(sid)] == ["a.pdf"]
    # Second file via API upload.
    r = client.post(f"/api/sessions/{sid}/upload", params={"user_id": u["id"]},
                    json={"file": "b.pdf"})
    assert r.status_code == 200
    assert sorted(f["filename"] for f in store.list_files(sid)) == ["a.pdf", "b.pdf"]
    # Seed one concept so we can prove data survives a per-file remove.
    store.seed_concepts(sid, u["id"], [main_row("m1")])
    assert len(store.list_concepts(sid)) == 1
    # Remove one file → keep data.
    r = client.delete(f"/api/sessions/{sid}/file",
                      params={"user_id": u["id"], "filename": "a.pdf"})
    assert r.status_code == 200
    body = r.json()
    assert body["reset"] is False
    assert [f["filename"] for f in store.list_files(sid)] == ["b.pdf"]
    assert len(store.list_concepts(sid)) == 1
    assert store.get_session(sid)["file"] == "b.pdf"
    # Remove last file → full wipe.
    r = client.delete(f"/api/sessions/{sid}/file",
                      params={"user_id": u["id"], "filename": "b.pdf"})
    assert r.json()["reset"] is True
    assert store.list_files(sid) == []
    assert store.list_concepts(sid) == []
    st = store.get_session(sid)
    assert st["file"] == "" and st["stage"] == "steps1-2"


# ---- L3 math: ceil + 2+2 + n=1 ----

def test_partition_ceil_and_remainder():
    assert store.partition_chunks(["a"]) == [["a"]]
    assert store.partition_chunks(["a", "b", "c", "d"]) == [["a", "b"], ["c", "d"]]
    got = store.partition_chunks([str(i) for i in range(7)])
    assert got == [["0", "1", "2"], ["3", "4"], ["5", "6"]]
    import math
    for n, total in ((1, 1), (3, 1), (4, 2), (6, 2), (7, 3)):
        ids = [f"x{i}" for i in range(n)]
        assert len(store.partition_chunks(ids)) == math.ceil(n / 3) == total


# ---- B3: hidden required set ----

def test_l3_generate_hides_required():
    u = mk_user("hidU")
    s = mk_session(u["id"], "h.pdf")
    start_l3(s["id"], u["id"])
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]}).json()
    assert "concept_ids" not in g, "required set leaked to client"
    assert g["pool"] == ["c1", "c2", "c3", "c4"]
    assert g["id"] and g["text"]
    # Resume returns the same hidden scenario.
    g2 = client.post(f"/api/sessions/{s['id']}/l3/generate",
                     params={"user_id": u["id"]}).json()
    assert g2["id"] == g["id"] and "concept_ids" not in g2


# ---- B4: strict 4-tier + lock-passed ----

def test_l3_strict_tiers_and_lock_passed():
    u = mk_user("tierU")
    s = mk_session(u["id"], "t.pdf")
    sid = s["id"]
    start_l3(sid, u["id"])
    g = client.post(f"/api/sessions/{sid}/l3/generate",
                    params={"user_id": u["id"]}).json()
    scn = g["id"]
    required = store.list_scenarios(sid)[0]["concept_ids"]
    assert len(required) == 2  # 4 mains → 2+2
    outside = [c for c in g["pool"] if c not in required][0]

    # Omission (tier 4): submit a subset → missed, no clear.
    j = client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                    json={"scenario_id": scn, "selections": [
                        {"concept_id": required[0], "justification": "applies"}]}).json()
    assert j["missed_ids"] and j["scenario_cleared"] is False

    # Wrong pick (tier 1): full required + outsider → flagged, no clear.
    j2 = client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                     json={"scenario_id": scn, "selections": [
                         {"concept_id": required[0], "justification": "j1"},
                         {"concept_id": required[1], "justification": "j2"},
                         {"concept_id": outside, "justification": "j-wrong"}]}).json()
    assert j2["scenario_cleared"] is False
    wrong_rows = [r for r in j2["results"] if r["concept_id"] == outside]
    assert wrong_rows and wrong_rows[0]["passed"] is False
    assert "not related" in wrong_rows[0]["feedback"]

    # Lock-passed retry: drop the wrong pick, resubmit remaining → cleared.
    locked = set(j2["locked_passed"])
    need = [c for c in required if c not in locked]
    j3 = client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                     json={"scenario_id": scn, "selections": [
                         {"concept_id": c, "justification": f"good {c}"} for c in need]}).json()
    assert j3["scenario_cleared"] is True
    assert set(j3["locked_passed"]) >= set(required)


def test_l3_full_run_clears_in_ceil():
    u = mk_user("runU")
    s = mk_session(u["id"], "r.pdf")
    sid = s["id"]
    start_l3(sid, u["id"])
    total = store.l3_status(sid)["total"]
    assert total == 2
    for _ in range(total):
        g = client.post(f"/api/sessions/{sid}/l3/generate",
                        params={"user_id": u["id"]}).json()
        assert g.get("complete") is not True
        req = next(x for x in store.list_scenarios(sid) if not x["cleared"])["concept_ids"]
        j = client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                        json={"scenario_id": g["id"], "selections": [
                            {"concept_id": c, "justification": f"why {c}"} for c in req]}).json()
        assert j["scenario_cleared"] is True
    st = store.l3_status(sid)
    assert st["complete"] and st["cleared"] == total and st["pct"] == 100
    assert store.get_session(sid)["stage"] == "L4"
    # Terminal state: stage has advanced to L4, so generate either reports
    # complete or refuses (Level 3 no longer active) — both are correct.
    r = client.post(f"/api/sessions/{sid}/l3/generate",
                    params={"user_id": u["id"]})
    assert (r.json().get("complete") is True) or (r.status_code == 400)


# ---- B5: session/id-keyed stubs ----

def test_evaluate_paraphrase_session_keyed():
    u = mk_user("epU")
    s = mk_session(u["id"], "e.pdf")
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row("m1"), blue_row("b1")])
    ok = llm.evaluate_paraphrase(sid, "m1", "my own words here")
    assert ok["passed"] is True
    blue = llm.evaluate_paraphrase(sid, "b1", "my note")
    assert blue["passed"] is True and "not doc-cited" in blue["feedback"]
    with pytest.raises(KeyError):
        llm.evaluate_paraphrase(sid, "nope", "x")
    # Server-side grounding: raw client text is never trusted — the stub
    # resolves the stored explanation, so an unknown id cannot pass.
    with pytest.raises(KeyError):
        llm.evaluate_paraphrase("s-does-not-exist", "m1", "x")


def test_evaluate_scenario_session_keyed():
    u = mk_user("esU")
    s = mk_session(u["id"], "e.pdf")
    sid = s["id"]
    start_l3(sid, u["id"])
    scn = store.list_scenarios(sid)
    assert scn == []  # no scenario until generate
    store.set_stage(sid, "L3")
    g = client.post(f"/api/sessions/{sid}/l3/generate",
                    params={"user_id": u["id"]}).json()
    req = next(x for x in store.list_scenarios(sid) if not x["cleared"])["concept_ids"]
    ev = llm.evaluate_scenario(sid, g["id"], [
        {"concept_id": req[0], "justification": "fits"}])
    assert ev["missed_ids"] and ev["scenario_cleared"] is False
    outside = [c for c in ["c1", "c2", "c3", "c4"] if c not in req][0]
    ev2 = llm.evaluate_scenario(sid, g["id"], [
        {"concept_id": req[0], "justification": "fits"},
        {"concept_id": req[1], "justification": "fits"},
        {"concept_id": outside, "justification": "fits"}])
    assert ev2["scenario_cleared"] is False
    assert any(r["concept_id"] == outside and not r["passed"] for r in ev2["results"])
    with pytest.raises(KeyError):
        llm.evaluate_scenario(sid, "scn-nope", [])


def test_probe_link_session_keyed_and_blue_tag():
    u = mk_user("plU")
    s = mk_session(u["id"], "p.pdf")
    sid = s["id"]
    import sqlite3
    con = sqlite3.connect(_DB)
    con.execute(
        "INSERT INTO links (id, session_id, a_id, b_id, edge_type)"
        " VALUES (?,?,?,?,?)", ("l1", sid, "a", "b", "causes"))
    con.commit()
    con.close()
    # Unknown link → KeyError (owned-id resolution).
    with pytest.raises(KeyError):
        llm.probe_link(sid, "l-nope", "w", "f")
    # Blue-involved link carries the plausibility tag.
    store.confirm_selection(sid, u["id"], [main_row("a"), blue_row("b")])
    out = llm.probe_link(sid, "l1", "because", "unless")
    assert set(out) == {"why_passed", "why_feedback", "why_hint",
                        "fail_passed", "fail_feedback", "fail_hint"}
    assert out["why_passed"] and out["fail_passed"]
    assert "not doc-cited" in out["why_feedback"]


# ---- item 8 / B5: blue two-step through the API ----

def test_blue_two_step_via_api():
    u = mk_user("blU")
    s = mk_session(u["id"], "b.pdf")
    sid = s["id"]
    r = client.post(f"/api/sessions/{sid}/confirm-selection",
                    params={"user_id": u["id"]},
                    json={"concepts": [main_row("m1"), blue_row("b1")]})
    assert r.status_code == 200
    rows = {c["id"]: c for c in store.list_concepts(sid)}
    assert rows["b1"]["explanation_text"] == ""
    v = client.post(f"/api/sessions/{sid}/l12/verify", params={"user_id": u["id"]},
                    json={"concept_id": "b1", "paraphrase": "my definition"}).json()
    assert v["passed"] is True and v["bypass"] is True
    rows = {c["id"]: c for c in store.list_concepts(sid)}
    assert rows["b1"]["explanation_text"] == "my definition"


# ---- M1: session_id-only, no denormalized user_id ----

def test_m1_no_denormalized_user_id():
    import sqlite3
    con = sqlite3.connect(_DB)
    for tbl in ("concepts", "links", "scenarios", "trail"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({tbl})").fetchall()]
        assert "user_id" not in cols, f"{tbl} still carries denormalized user_id"
    con.close()
    # Pydantic domain models carry session_id only.
    for cls in (models.Concept, models.Link, models.Scenario, models.Trail):
        assert "user_id" not in cls.model_fields, f"{cls.__name__} still has user_id"
    # user_id resolves via sessions join.
    u = mk_user("m1U")
    s = mk_session(u["id"], "m1.pdf")
    assert store.user_id_for_session(s["id"]) == u["id"]
    # Domain rows store no user_id key.
    store.confirm_selection(s["id"], u["id"], [main_row("m1x")])
    rows = store.list_concepts(s["id"])
    assert rows and "user_id" not in rows[0]
    # Legacy seed_concepts(session_id, user_id, concepts) still works (ignored).
    u2 = mk_user("m1U2")
    s2 = mk_session(u2["id"])
    n = store.seed_concepts(s2["id"], u2["id"], [main_row("zz")])
    assert n == 1
    # New seed_concepts(session_id, concepts) also works.
    s3 = mk_session(u2["id"])
    assert store.seed_concepts(s3["id"], [main_row("yy")]) == 1


# ---- M2: session lifecycle delete cascade + no cross-user reads ----

def test_m2_delete_session_cascade():
    a = mk_user("delA")
    b = mk_user("delB")
    s = mk_session(a["id"], "d.pdf")
    sid = s["id"]
    store.confirm_selection(sid, a["id"], FOUR)
    assert store.list_concepts(sid)
    # Cross-user delete 404s, data survives.
    r = client.delete(f"/api/sessions/{sid}", params={"user_id": b["id"]})
    assert r.status_code == 404
    assert store.get_session(sid) is not None
    # Owner delete cascades everything.
    r = client.delete(f"/api/sessions/{sid}", params={"user_id": a["id"]})
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert store.get_session(sid) is None
    assert store.list_concepts(sid) == []
    assert store.list_trail(sid) == []
    # Missing user_id fails closed.
    s2 = mk_session(a["id"])
    assert client.delete(f"/api/sessions/{s2['id']}").status_code == 404


def test_m2_list_hardened_no_cross_user():
    a = mk_user("lstA")
    b = mk_user("lstB")
    sa = mk_session(a["id"], "a.pdf")
    # Missing user_id → 404 (not 422/200).
    assert client.get("/api/sessions").status_code == 404
    # Unknown user → 404 (not empty list leak).
    assert client.get("/api/sessions", params={"user_id": 999999999}).status_code == 404
    # Each user lists only their own rows.
    la = client.get("/api/sessions", params={"user_id": a["id"]}).json()
    lb = client.get("/api/sessions", params={"user_id": b["id"]}).json()
    assert {x["id"] for x in la} >= {sa["id"]}
    assert all(x["user_id"] == a["id"] for x in la)
    assert all(x["user_id"] == b["id"] for x in lb)
    assert sa["id"] not in {x["id"] for x in lb}


# ---- M3: seed-load gated round-trip ----

def test_m3_seed_load_round_trip_and_gate():
    u = mk_user("seedU")
    s = mk_session(u["id"], "seed-demo.pdf")
    sid = s["id"]
    r = client.post(f"/api/sessions/{sid}/seed-load", params={"user_id": u["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stage"] == "L1-2" and body["mains"] >= 1
    assert store.get_session(sid)["stage"] == "L1-2"
    # Trail init wrote one steps1-2 event row per concept.
    stages = [t["stage"] for t in store.list_trail(sid)]
    assert "steps1-2" in stages
    # Second seed-load blocked (already locked / not empty).
    r2 = client.post(f"/api/sessions/{sid}/seed-load", params={"user_id": u["id"]})
    assert r2.status_code == 400
    # Cross-user seed-load 404s.
    v = mk_user("seedV")
    assert client.post(f"/api/sessions/{sid}/seed-load",
                       params={"user_id": v["id"]}).status_code == 404


# ---- M4: Confirm copy verbatim §6.1 ----

def test_m4_confirm_copy_verbatim():
    u = mk_user("copyU")
    s = mk_session(u["id"])
    html = client.get(f"/u/{u['id']}/s/{s['id']}", params={}).text
    want = "≥2–3 mains recommended (a single main auto-passes Analyze/Evaluate with no links to defend)"
    assert want in html


# ---- M5: blue saved text reviewable ----

def test_m5_blue_drawer_reviewable():
    import os as _os
    js = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "l12.js"),
              encoding="utf-8").read()
    # Drawer prefills saved blue text instead of always clearing.
    assert "el('drawerPara').value = blue ? savedText" in js
    # Reviewable as name + user explanation + warning-ack + saved flag.
    assert "Your saved explanation [user-defined]" in js and "✓ Saved" in js
    assert "blueWarn" in js  # warning-ack toggled
    # API review path: blue verify returns saved text for re-open.
    u = mk_user("m5U")
    s = mk_session(u["id"], "m5.pdf")
    sid = s["id"]
    client.post(f"/api/sessions/{sid}/confirm-selection", params={"user_id": u["id"]},
                json={"concepts": [blue_row("b1")]})
    v = client.post(f"/api/sessions/{sid}/l12/verify", params={"user_id": u["id"]},
                    json={"concept_id": "b1", "paraphrase": "saved note"}).json()
    assert v["user_explanation"] == "saved note"
    rows = {c["id"]: c for c in store.list_concepts(sid)}
    assert rows["b1"]["explanation_text"] == "saved note"


# ---- M6: diagram image branch ----

def test_m6_diagram_image_branch():
    import os as _os
    figs = parse.parse_pdf("x.pdf")["figures"]
    assert figs and all("image_path" in f and "caption" in f for f in figs)
    assert all(f["image_path"].startswith("/static/diagrams/") for f in figs)
    # Static dir + placeholder files exist so the image branch is exercised.
    here = _os.path.join(_os.path.dirname(__file__), "..", "static", "diagrams")
    assert _os.path.isdir(here)
    assert _os.path.exists(_os.path.join(here, "fig-p5-1.png"))
    # l12.js renders the image with description-only fallback.
    js = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "l12.js"),
              encoding="utf-8").read()
    assert "/static/diagrams/" in js and "onerror" in js


# ---- M7: absolute static mount + derived health ----

def test_m7_static_absolute_and_health_derived():
    import os as _os
    from app.main import _current_step
    assert client.get("/api/health").json()["step"] == _current_step() == 6
    # Static mount resolves absolutely (works from repo root, not just Build/).
    found = [r for r in app.routes if getattr(r, "path", "") == "/static"]
    assert found
    # Serve a real static asset + a diagram through the mount.
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/diagrams/fig-p5-1.png").status_code == 200
    src = open(_os.path.join(_os.path.dirname(__file__), "..", "app", "main.py"),
               encoding="utf-8").read()
    assert 'StaticFiles(directory="static")' not in src


# ---- M8: blue trail omits accuracy/originality ----

def test_m8_blue_trail_shape():
    import json as _json
    u = mk_user("m8U")
    s = mk_session(u["id"], "m8.pdf")
    sid = s["id"]
    client.post(f"/api/sessions/{sid}/confirm-selection", params={"user_id": u["id"]},
                json={"concepts": [main_row("m1"), blue_row("b1")]})
    v = client.post(f"/api/sessions/{sid}/l12/verify", params={"user_id": u["id"]},
                    json={"concept_id": "b1", "paraphrase": "my note"}).json()
    assert v["bypass"] is True
    assert "accuracy" not in v and "originality" not in v
    assert v["warning_ack"] and v["user_explanation"] == "my note" and v["saved"] is True
    # Stub itself omits the keys too.
    assert "accuracy" not in llm.evaluate_paraphrase(sid, "b1", "x")
    rows = [t for t in store.list_trail(sid)
            if t["concept_id"] == "b1" and t["stage"] == "L1-2"]
    assert rows
    pay = _json.loads(rows[-1]["payload"])
    assert "accuracy" not in pay and "originality" not in pay
    assert pay["warning_ack"] and pay["user_explanation"] == "my note"
    # Extracted rows still carry accuracy/originality.
    v2 = client.post(f"/api/sessions/{sid}/l12/verify", params={"user_id": u["id"]},
                     json={"concept_id": "m1", "paraphrase": "para"}).json()
    assert "accuracy" in v2 and "originality" in v2


# ---- M10: parse_pdf alias + figures wiring ----

def test_m10_parse_pdf_alias_and_figures_wiring():
    assert hasattr(parse, "parse_pdf")
    a = parse.parse_pdf("demo.pdf")
    b = parse.llamaparse_stub("demo.pdf")
    assert a["markdown"] == b["markdown"] and a["figures"] == b["figures"]
    figs = a["figures"]
    concepts = llm.extract_concepts(a["markdown"], figs)
    fig_ids = {f["diagram_id"] for f in figs}
    for c in concepts:
        for r in (c.get("diagram_refs") or []):
            assert r["diagram_id"] in fig_ids
    c1 = next(c for c in concepts if c["concept_id"] == "c1")
    assert c1["diagram_refs"] and c1["diagram_description"]
    # Empty figures → no phantom refs.
    bare = llm.extract_concepts(a["markdown"], [])
    assert all(not (c.get("diagram_refs") or []) for c in bare)


# ---- MINORs ----

def test_minor_guard_copy_and_labels():
    u = mk_user("gU")
    s = mk_session(u["id"])
    with pytest.raises(ValueError, match="Select at least 1 main heading to continue"):
        store.confirm_selection(s["id"], u["id"], [])
    import os as _os
    js = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "l12.js"),
              encoding="utf-8").read()
    assert "[${c.explanation_type}, ${pagesLabel" not in js  # no trailing-comma shape
    s12 = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "steps12.js"),
               encoding="utf-8").read()
    assert "Select at least 1 main heading to continue" in s12
    req = open(_os.path.join(_os.path.dirname(__file__), "..", "requirements.txt"),
               encoding="utf-8").read()
    assert "pytest" in req


def test_minor_seed_shape_small_seeds():
    import math as _m
    seed = llm.load_seed_concepts()
    mains = [c for c in seed if c["kind"] == "main"]
    assert len(mains) == 6  # default seed: 6 mains → ceil(6/3)=2, partition 3+3
    assert len(store.partition_chunks([m["concept_id"] for m in mains])) == 2
    # Reviewer note: 2+2 remainder (n=4/7) + n=1 exception need small seeds.
    for n, total in ((1, 1), (4, 2), (7, 3)):
        ids = [f"s{i}" for i in range(n)]
        assert len(store.partition_chunks(ids)) == _m.ceil(n / 3) == total
    u = mk_user("smU")
    s = mk_session(u["id"])
    one = [main_row("only")]
    store.confirm_selection(s["id"], u["id"], one)
    assert store.l3_counted_ids(s["id"])[1] == ["only"]
    assert store.l3_status(s["id"])["total"] == 1


# ---- B2: L4/L5/Phase2/history DONE gates (seed demo, no keys) ----

def _seed6(uid, sid):
    rows = [main_row(f"m{i}", title=f"Main {i}") for i in range(6)]
    store.confirm_selection(sid, uid, rows)
    for i in range(6):
        store.record_l12_attempt(sid, uid, f"m{i}", f"para m{i}", True, "a", "o", "fb", "")
    store.set_stage(sid, "L3")
    return [f"m{i}" for i in range(6)]


def test_l4_finish_second_drag_n1():
    import json as _json
    u = mk_user("l4U")
    s = mk_session(u["id"], "l4.pdf")
    sid = s["id"]
    _seed6(u["id"], sid)
    # Clear L3 to reach L4 (stub justifications pass).
    for _ in range(2):
        g = client.post(f"/api/sessions/{sid}/l3/generate",
                        params={"user_id": u["id"]}).json()
        req = next(x for x in store.list_scenarios(sid) if not x["cleared"])["concept_ids"]
        client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": c, "justification": f"why {c}"} for c in req]})
    assert store.get_session(sid)["stage"] == "L4"
    # Finish blocked until every counted concept >=1.
    with pytest.raises(ValueError):
        store.l4_finish(sid, u["id"])
    store.create_link(sid, "m0", "m1", "causes", user_id=u["id"])
    # Second drag same pair regardless of type blocked.
    with pytest.raises(ValueError, match="One link per pair"):
        store.create_link(sid, "m1", "m0", "depends on", user_id=u["id"])
    # Finish still blocked (m2-m5 degree 0).
    with pytest.raises(ValueError):
        store.l4_finish(sid, u["id"])
    # Connect all: ring m0-m1-...-m5-m0 gives every degree >=1.
    for a, b in [("m1", "m2"), ("m2", "m3"), ("m3", "m4"), ("m4", "m5"), ("m5", "m0")]:
        store.create_link(sid, a, b, "leads to", user_id=u["id"])
    out = store.l4_finish(sid, u["id"])
    assert out["stage"] == "L5" and out["l5_n"] == 6
    # Frozen: no new links in L5.
    with pytest.raises(ValueError, match="frozen"):
        store.create_link(sid, "m0", "m2", "causes", user_id=u["id"])
    # n=1 auto-pass: single main → Finish enabled, N=0 → Phase2 directly.
    # State-machine gate: n=1 still requires L4 (no skip from L1-2/L3).
    u2 = mk_user("l4n1")
    s2 = mk_session(u2["id"])
    store.confirm_selection(s2["id"], u2["id"], [main_row("only", title="Solo")])
    st = store.l4_status(s2["id"])
    assert st["finish_enabled"] and st["n1_auto"]
    with pytest.raises(ValueError, match="Level 4 not active"):
        store.l4_finish(s2["id"], u2["id"])
    store.set_stage(s2["id"], "L4")
    out2 = store.l4_finish(s2["id"], u2["id"])
    assert out2["l5_n"] == 0 and out2["stage"] == "Phase2"


def test_l5_bright_n_lock_passed():
    u = mk_user("l5U")
    s = mk_session(u["id"], "l5.pdf")
    sid = s["id"]
    _seed6(u["id"], sid)
    store.set_stage(sid, "L4")
    store.create_link(sid, "m0", "m1", "causes", user_id=u["id"])
    store.create_link(sid, "m2", "m3", "causes", user_id=u["id"])
    # Pre-entry: 0%, never 100% (0/0).
    pre = store.l5_status(sid)
    assert pre["entered"] is False and pre["pct"] == 0 and pre["complete"] is False
    store.set_stage(sid, "L5")
    n = store.l5_enter(sid)
    assert n == 2
    # N fixed at entry (idempotent, never recomputed).
    assert store.l5_enter(sid) == 2
    lid = [L["id"] for L in store.list_links(sid)][0]
    ev = {"why_passed": True, "fail_passed": False, "why_feedback": "g",
          "fail_feedback": "b", "why_hint": "h1", "fail_hint": "h2"}
    link = store.probe_submit(sid, lid, "because", "unless", ev, user_id=u["id"])
    assert link["bright"] is False  # both-green required
    assert link["why_passed"] is True and link["fail_passed"] is False
    # Lock-passed: second submit keeps why green, brightens on both-green.
    ev2 = dict(ev, fail_passed=True)
    link2 = store.probe_submit(sid, lid, "because", "unless fixed", ev2, user_id=u["id"])
    assert link2["bright"] is True
    st = store.l5_status(sid)
    assert st["bright"] == 1 and st["n"] == 2
    # History carries hints (m3).
    import json as _json
    rows = [t for t in store.list_trail(sid) if t["stage"] == "L5"]
    assert rows and "why_hint" in _json.loads(rows[-1]["payload"])
    # Ownership on probe.
    v = mk_user("l5V")
    with pytest.raises(PermissionError):
        store.probe_submit(sid, lid, "w", "f", ev, user_id=v["id"])


def test_phase2_hint_total_and_filtered_math():
    u = mk_user("p2U")
    s = mk_session(u["id"], "p2.pdf")
    sid = s["id"]
    _seed6(u["id"], sid)
    store.set_stage(sid, "Phase2")
    # 1 submitted but 0 total→1 total: hint fires. With a pre-existing sub,
    # submitting 1 more (seen==1, total==2) must NOT hint (m1).
    out1 = store.confirm_phase2(sid, u["id"], [
        {"concept_id": "s1", "title": "Sub 1", "kind": "sub", "parent_id": "m0"}])
    assert out1["subs"] == 1 and "recommended" in out1["hint"]
    # Second session: pre-seed one sub, then confirm with one new sub.
    u2 = mk_user("p2U2")
    s2 = mk_session(u2["id"])
    _seed6(u2["id"], s2["id"])
    store.set_stage(s2["id"], "Phase2")
    store.confirm_phase2(s2["id"], u2["id"], [
        {"concept_id": "s1", "title": "Sub 1", "kind": "sub", "parent_id": "m0"}])
    # Stage reset to L1-2/phase2; force back to Phase2 for a second confirm
    # with one new sub (total becomes 2 → no hint).
    store.set_stage(s2["id"], "Phase2")
    out2 = store.confirm_phase2(s2["id"], u2["id"], [
        {"concept_id": "s1", "title": "Sub 1", "kind": "sub", "parent_id": "m0"},
        {"concept_id": "s2", "title": "Sub 2", "kind": "sub", "parent_id": "m1"}])
    assert out2["subs"] == 2 and out2["hint"] == ""
    # Filtered math: L3 counts subs only, mains never pooled.
    phase, ids = store.l3_counted_ids(s2["id"])
    assert phase == "phase2" and set(ids) == {"s1", "s2"}
    # 0-sub Confirm blocked.
    store.set_stage(s2["id"], "Phase2")
    with pytest.raises(ValueError, match="at least 1 sub"):
        store.confirm_phase2(s2["id"], u2["id"], [])


def test_m3_seed_gated_and_history_trail():
    import json as _json
    a = mk_user("sgA")
    b = mk_user("sgB")
    s = mk_session(a["id"])
    sid = s["id"]
    # Cross-user seed_concepts fails closed.
    with pytest.raises(PermissionError):
        store.seed_concepts(sid, b["id"], [main_row("x")])
    # Owner seed works (test-only path).
    assert store.seed_concepts(sid, a["id"], [main_row("x")]) == 1
    # Trail per-slice writes: confirm → steps1-2 rows; L3 → per-(scenario,concept)
    # incl omissions; L5 → per-link rows.
    u = mk_user("trU")
    s2 = mk_session(u["id"])
    sid2 = s2["id"]
    start_l3(sid2, u["id"])
    assert any(t["stage"] == "steps1-2" for t in store.list_trail(sid2))
    g = client.post(f"/api/sessions/{sid2}/l3/generate",
                    params={"user_id": u["id"]}).json()
    req = next(x for x in store.list_scenarios(sid2) if not x["cleared"])["concept_ids"]
    # Submit subset → omission row written.
    client.post(f"/api/sessions/{sid2}/l3/submit", params={"user_id": u["id"]},
                json={"scenario_id": g["id"], "selections": [
                    {"concept_id": req[0], "justification": "j"}]})
    l3rows = [t for t in store.list_trail(sid2) if t["stage"] == "L3"]
    assert any(_json.loads(t["payload"]).get("omitted") for t in l3rows)
    # Omission feedback names the title (m2), not bare id.
    pays = [_json.loads(t["payload"]) for t in l3rows if _json.loads(t["payload"]).get("omitted")]
    assert pays and "T-" in pays[0]["feedback"]


def test_history_js_full_fields_and_l5_hints():
    import os as _os
    js = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "history.js"),
              encoding="utf-8").read()
    # M1: full L1-2 fields + server-side concept fetch.
    assert "explanation_text" in js and "diagram_description" in js
    assert "accuracy" in js and "originality" in js and "warning_ack" in js
    assert "/api/sessions/' + SID + '/concepts'" in js or '/concepts' in js
    # m3: L5 hints rendered.
    assert "why_hint" in js and "fail_hint" in js
    # M2: n=1 branch skips L5 modal.
    l4 = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "l4.js"),
              encoding="utf-8").read()
    assert "phase2modal" in l4 and "l5_n" in l4
    # M4: dim retry / chain.
    l5 = open(_os.path.join(_os.path.dirname(__file__), "..", "static", "l5.js"),
              encoding="utf-8").read()
    assert "setTimeout" in l5 or "CogniMapL5" in open(
        _os.path.join(_os.path.dirname(__file__), "..", "static", "l4.js"),
        encoding="utf-8").read()
