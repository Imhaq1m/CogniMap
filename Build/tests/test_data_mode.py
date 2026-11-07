"""COGNIMAP_MODE demo toggle (grill 2026-10-29).

Pins: demo forces the stub engine even with live keys present; auto (default,
unset, or any other value) keeps today's key-detection behaviour unchanged.
Shared DB, per-boot, no data machinery — one test module, no fixtures dir.

NOTE: test names must NOT start with test_live (conftest restores real keys
for those); fake keys below are inert strings, never sent anywhere because
demo mode never reaches the transport.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault(
    "COGNIMAP_DB", os.path.join(tempfile.gettempdir(), f"cognimap_test_{os.getpid()}.db")
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app import config, llm, parse  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

_FAKE_KEYS = {
    "GROQ_API_KEY": "fake-groq",
    "DEEPSEEK_API_KEY": "fake-deepseek",
    "LLAMA_CLOUD_API_KEY": "fake-llama",
}


def _set_keys(monkeypatch):
    for k, v in _FAKE_KEYS.items():
        monkeypatch.setenv(k, v)


def _clear_keys(monkeypatch):
    for k in _FAKE_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_auto_default_is_key_detection(monkeypatch):
    # Unset / garbage values fall back to auto: keys decide, as before.
    monkeypatch.delenv("COGNIMAP_MODE", raising=False)
    _set_keys(monkeypatch)
    assert config.get_data_mode() == "auto"
    assert config.is_demo_forced() is False
    assert config.is_llm_live() is True
    assert config.is_llama_live() is True
    assert config.llm_status() == {"llm": "live", "llm_model": "qwen/qwen3.8-27b"}
    monkeypatch.setenv("COGNIMAP_MODE", "banana")
    assert config.get_data_mode() == "auto"


def test_demo_forces_stub_with_keys(monkeypatch):
    monkeypatch.setenv("COGNIMAP_MODE", "demo")
    _set_keys(monkeypatch)
    assert config.get_data_mode() == "demo"
    assert config.is_demo_forced() is True
    assert config.is_llm_live() is False
    assert config.is_llama_live() is False
    assert config.llm_status() == {"llm": "stub", "llm_model": "stub"}
    assert config.llama_status() == {"llama": "stub"}
    assert config.stub_default_reason() == "demo-forced (COGNIMAP_MODE=demo)"


def test_demo_extract_uses_seed_without_network(monkeypatch):
    # The whole point: keys present, demo on, extract answers from seed.json
    # and the transport is never touched.
    monkeypatch.setenv("COGNIMAP_MODE", "demo")
    _set_keys(monkeypatch)
    monkeypatch.setattr(
        llm, "_llm_generate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("live transport hit in demo")),
    )
    st = llm.extract_concepts_with_status("any markdown", [])
    assert st["mode"] == "stub"
    assert st["fallback_reason"] == "demo-forced (COGNIMAP_MODE=demo)"
    # Stub reshapes the seed (drops refs for figures not in the input), so
    # compare against the stub transform, not the raw JSON.
    assert st["concepts"] == llm._stub_extract_concepts("any markdown", [])
    assert [c["concept_id"] for c in st["concepts"]] == [
        c["concept_id"] for c in llm.load_seed_concepts()
    ]
    parsed = parse.parse_pdf("seed-demo.pdf", pdf_bytes=None)
    assert parsed["mode"] == "stub"
    assert parsed["fallback_reason"] == "demo-forced (COGNIMAP_MODE=demo)"


def test_demo_health_and_badge(monkeypatch):
    monkeypatch.setenv("COGNIMAP_MODE", "demo")
    _set_keys(monkeypatch)
    h = client.get("/api/health").json()
    assert h["data_mode"] == "demo"
    assert h["llm"] == "stub" and h["llama"] == "stub"
    picker = client.get("/").text
    assert ">DEMO</span>" in picker
    assert "connect keys" not in picker  # badge only; no key advice on pages


def test_demo_extract_warning_drops_key_advice(monkeypatch):
    # Seed a session through the real pipeline, then extract in demo mode:
    # warning must not tell the presenter to "connect keys" they already have.
    monkeypatch.setenv("COGNIMAP_MODE", "demo")
    _set_keys(monkeypatch)
    uid = client.post("/api/users", json={"name": "demo-mode-user"}).json()["id"]
    sid = client.post(
        "/api/sessions", json={"user_id": uid, "file": "seed-demo.pdf"}
    ).json()["id"]
    r = client.post(f"/api/sessions/{sid}/extract?user_id={uid}")
    body = r.json()
    assert body["mode"] == "stub"
    assert "connect keys" not in body.get("warning", "")
    assert "seed demo" in body.get("warning", "")


def test_auto_keyless_unchanged(monkeypatch):
    # Default boot with no keys and no knob: identical to before the toggle.
    monkeypatch.delenv("COGNIMAP_MODE", raising=False)
    _clear_keys(monkeypatch)
    assert config.get_data_mode() == "auto"
    assert config.stub_default_reason() == "stub-default (no key on any chain link)"
    h = client.get("/api/health").json()
    assert h["data_mode"] == "auto"
    assert h["llm"] == "stub"
    picker = client.get("/").text
    assert ">STUB</span>" in picker
