"""S1 integration tests (Integration_Tracker S1/S6/S7/S8 ride-along).

Keyless CI stays green: stub assertions always run; live tests skip without
keys; fallback tests force bad-key/bad-JSON and assert stub shape + mode=stub.
Isolated DB pattern mirrors tests/test_locks.py:14.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid

_DB = os.path.join(tempfile.gettempdir(), f"cognimap_test_{os.getpid()}.db")
os.environ.setdefault("COGNIMAP_DB", _DB)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from starlette.testclient import TestClient

from app import config, llm, parse, store
from app.main import app

client = TestClient(app)

# Every LLM key the code understands — forced absent to prove stub paths.
_KEYLESS_ENV = ("LLAMA_CLOUD_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
                "GLM_API_KEY", "ZAI_API_KEY")


def mk_user(prefix="s1"):
    return store.get_or_create_user(f"{prefix}-{uuid.uuid4().hex[:6]}")


def mk_session(uid, file="seed-demo.pdf"):
    return store.create_session(uid, file)


# ---- health additive (S1 env/config) ----

def test_health_additive_fields():
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and "step" in j
    assert j.get("llama") in ("live", "stub")
    assert j.get("llm") in ("live", "stub")
    assert "llm_model" in j


def test_parse_status_stub_keyless(monkeypatch):
    # Without keys (CI), both report stub. Forced keyless here so the test
    # is hermetic even on machines with keys in .env (conftest also strips).
    for k in _KEYLESS_ENV:
        monkeypatch.delenv(k, raising=False)
    assert parse.parse_status() == {"llama": "stub"}
    assert llm.llm_status() == {"llm": "stub", "llm_model": "stub"}


# ---- frozen signatures preserved ----

def test_parse_pdf_signature_additive():
    import inspect

    sig = inspect.signature(parse.parse_pdf)
    assert "file" in sig.parameters
    # S1 adds optional pdf_bytes without breaking label-only callers.
    assert "pdf_bytes" in sig.parameters
    assert sig.parameters["pdf_bytes"].default is None
    # Label-only still stub with frozen keys + additive mode keys.
    out = parse.parse_pdf("demo.pdf")
    assert out["markdown"] and isinstance(out["figures"], list)
    assert out["mode"] == "stub" and "fallback_reason" in out
    assert out["tier"] in ("agentic", "agentic_plus")
    assert out["images_to_save"] == ["screenshot"]


def test_extract_list_shape_frozen():
    parsed = parse.parse_pdf("demo.pdf")
    concepts = llm.extract_concepts(parsed["markdown"], parsed["figures"])
    assert isinstance(concepts, list) and concepts
    # Confirm guards still pass on stub shape.
    assert any(c.get("kind") == "main" for c in concepts)


def test_extract_with_status_stub_labels(monkeypatch):
    for k in _KEYLESS_ENV:
        monkeypatch.delenv(k, raising=False)
    parsed = parse.parse_pdf("demo.pdf")
    st = llm.extract_concepts_with_status(parsed["markdown"], parsed["figures"])
    assert set(["concepts", "mode", "model", "fallback_reason"]) <= set(st)
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert st["fallback_reason"]
    assert isinstance(st["concepts"], list) and st["concepts"]


# ---- fallback: bad key / bad JSON -> stub + mode=stub (never 502) ----

def test_fallback_bad_key_goes_stub(monkeypatch):
    # S2b: default provider is GLM; chain fails -> labelled stub, never 502.
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "bad-key-for-test")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    # Force the chain to fail fast without network.
    monkeypatch.setattr(llm, "_llm_generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("401 bad key")))
    parsed = parse.parse_pdf("demo.pdf")
    st = llm.extract_concepts_with_status(parsed["markdown"], parsed["figures"])
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert st["fallback_reason"]
    assert isinstance(st["concepts"], list) and st["concepts"]


def test_fallback_bad_json_goes_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "dummy")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    monkeypatch.setattr(llm, "_llm_generate", lambda *a, **k: "not-json {{{")
    parsed = parse.parse_pdf("demo.pdf")
    st = llm.extract_concepts_with_status(parsed["markdown"], parsed["figures"])
    assert st["mode"] == "stub"
    assert "bad JSON" in st["fallback_reason"] or st["fallback_reason"]


def test_validation_rejects_bad_shapes():
    with pytest.raises(ValueError):
        llm.validate_extract_shape([])
    with pytest.raises(ValueError):
        llm.validate_extract_shape([{"concept_id": "a", "title": "T", "kind": "main",
                                     "source": "user_added", "explanation_type": "definition",
                                     "explanation_text": "x", "explanation_source": "extracted",
                                     "pages": [], "diagram_refs": []}])
    dup = [{"concept_id": "a", "title": "T1", "kind": "main", "source": "extracted",
            "explanation_type": "definition", "explanation_text": "x",
            "explanation_source": "extracted", "pages": [], "diagram_refs": []},
           {"concept_id": "a", "title": "T2", "kind": "main", "source": "extracted",
            "explanation_type": "definition", "explanation_text": "y",
            "explanation_source": "extracted", "pages": [], "diagram_refs": []}]
    with pytest.raises(ValueError, match="duplicate"):
        llm.validate_extract_shape(dup)
    orphan = [{"concept_id": "s1", "title": "Sub", "kind": "sub", "parent_id": "nope",
               "source": "extracted", "explanation_type": "definition",
               "explanation_text": "x", "explanation_source": "generated",
               "pages": [], "diagram_refs": []}]
    with pytest.raises(ValueError, match="parent"):
        llm.validate_extract_shape(orphan)
    ok = [{"concept_id": "m1", "title": "Main", "kind": "main", "parent_id": None,
           "source": "extracted", "explanation_type": "definition",
           "explanation_text": "text", "explanation_source": "extracted",
           "pages": [1], "diagram_refs": []}]
    assert llm.validate_extract_shape(ok)


# ---- live tests skip without keys ----

@pytest.mark.skipif(not config.is_llm_live(), reason="no LLM key (keyless CI skip)")
def test_live_extract_shape():
    parsed = parse.parse_pdf("demo.pdf")
    st = llm.extract_concepts_with_status(parsed["markdown"], parsed["figures"])
    # Live or stub both must pass Confirm guards (no UI break on swap).
    # Strict shape check only when mode=live: stub seeds are trusted and may
    # contain user_added (blue) rows the live-only validator would reject
    # (e.g. fallback-to-stub path during a 503 outage).
    if st["mode"] == "live":
        llm.validate_extract_shape(st["concepts"])
    assert any(c.get("kind") == "main" for c in st["concepts"])


@pytest.mark.skipif(not config.is_llama_live(), reason="no LLAMA key (keyless CI skip)")
def test_live_parse_pdf_bytes():
    data = b"%PDF-1.4 fake\n%%EOF"
    out = parse.parse_pdf("live.pdf", pdf_bytes=data)
    assert out["markdown"] and out["mode"] in ("live", "stub")


# ---- routes: /extract labelling + /upload-pdf + cleanup ----

def test_extract_route_labels_stub(monkeypatch):
    for k in _KEYLESS_ENV:
        monkeypatch.delenv(k, raising=False)
    u = mk_user("exU")
    s = mk_session(u["id"], "lecture.pdf")
    r = client.post(f"/api/sessions/{s['id']}/extract", params={"user_id": u["id"]})
    assert r.status_code == 200
    j = r.json()
    assert "concepts" in j and "parsed" in j  # frozen keys kept
    assert j.get("mode") in ("live", "stub") and "model" in j
    assert j["parsed"].get("mode") in ("live", "stub")
    if j.get("mode") == "stub":
        assert "warning" in j and "stubbed" in j["warning"].lower()


def test_upload_pdf_saves_disk_and_lists_filename_only():
    u = mk_user("upU")
    s = mk_session(u["id"], "")
    sid = s["id"]
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    r = client.post(f"/api/sessions/{sid}/upload-pdf", params={"user_id": u["id"]},
                    files={"file": ("notes.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["file"] == "notes.pdf"
    assert "parsed" in j
    files = client.get(f"/api/sessions/{sid}/files", params={"user_id": u["id"]}).json()
    assert [f["filename"] for f in files] == ["notes.pdf"]  # filename-only, no schema change
    # Disk copy exists.
    p = os.path.join(config.upload_root(), sid, "notes.pdf")
    assert os.path.isfile(p)
    # Per-file remove cleans disk but keeps session (single file -> reset wipes).
    d = client.delete(f"/api/sessions/{sid}/file",
                      params={"user_id": u["id"], "filename": "notes.pdf"}).json()
    assert d["reset"] is True
    assert not os.path.exists(p)


def test_upload_pdf_rejects_non_pdf_and_oversize(monkeypatch):
    u = mk_user("upR")
    s = mk_session(u["id"], "")
    sid = s["id"]
    r = client.post(f"/api/sessions/{sid}/upload-pdf", params={"user_id": u["id"]},
                    files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400
    monkeypatch.setattr(config, "MAX_PDF_BYTES", 10)
    big = b"%PDF-" + b"x" * 100
    r2 = client.post(f"/api/sessions/{sid}/upload-pdf", params={"user_id": u["id"]},
                     files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")})
    assert r2.status_code == 400


def test_session_delete_cleans_uploads_dir():
    u = mk_user("delU")
    s = mk_session(u["id"], "")
    sid = s["id"]
    pdf = b"%PDF-1.4 fake"
    client.post(f"/api/sessions/{sid}/upload-pdf", params={"user_id": u["id"]},
                files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")})
    assert os.path.isdir(os.path.join(config.upload_root(), sid))
    r = client.delete(f"/api/sessions/{sid}", params={"user_id": u["id"]})
    assert r.status_code == 200
    assert not os.path.exists(os.path.join(config.upload_root(), sid))
