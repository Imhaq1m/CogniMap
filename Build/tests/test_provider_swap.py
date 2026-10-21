"""S2b provider-swap tests: GLM-4.7-Flash default, Gemini archived.

Keyless CI stays green: nothing here touches the network — the z.ai transport
is faked at httpx.Client and chain tests monkeypatch the dispatcher. Covers:
provider gating/defaults, dispatcher routing, GLM request shape +
reasoning_content parsing, HTTP/empty failures -> labelled stub, and the
archived Gemini path staying selectable end-to-end.
Isolated DB pattern mirrors tests/test_locks.py:14.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid

_DB = os.path.join(tempfile.gettempdir(), f"cognimap_test_{os.getpid()}.db")
os.environ.setdefault("COGNIMAP_DB", _DB)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import pytest

from app import config, llm, store


def mk_user(prefix="pb"):
    return store.get_or_create_user(f"{prefix}-{uuid.uuid4().hex[:6]}")


def mk_session(uid):
    return store.create_session(uid, "seed-demo.pdf")


def main_row(cid="m1"):
    return {
        "concept_id": cid,
        "title": f"T-{cid}",
        "kind": "main",
        "parent_id": None,
        "source": "extracted",
        "explanation_type": "definition",
        "explanation_text": f"stored explanation for {cid}",
        "explanation_source": "extracted",
        "pages": [5],
        "diagram_refs": [],
        "diagram_description": "",
    }


def glm_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "dummy-key-not-logged")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    monkeypatch.delenv("GLM_BASE_URL", raising=False)


def live_json():
    return json.dumps({
        "passed": True, "accuracy": "Accurate", "originality": "Own words",
        "feedback": "Core meaning captured in your own words.", "hint": "",
    })


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def fake_glm_http(monkeypatch, status=200, payload=None, text="", raise_exc=None):
    """Fake httpx.Client so _glm_generate runs offline; returns captured calls."""
    calls: list[dict] = []

    class _Client:
        def __init__(self, timeout=None, **kw):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            calls.append({"url": url, "json": json, "headers": headers,
                          "timeout": self.timeout})
            if raise_exc is not None:
                raise raise_exc
            return _Resp(status, payload, text)

    monkeypatch.setattr(httpx, "Client", _Client)
    return calls


# ---- config: new default + archived models + key gating ----

def test_provider_default_is_glm_archived_gemini_kept(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    assert config.get_llm_provider() == "glm"
    assert config.get_llm_models() == ["glm-4.7-flash"]
    # Archived Gemini chain still selectable, not deleted.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert config.get_llm_models() == [
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
    ]
    # Explicit LLM_MODELS wins within the provider.
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("LLM_MODELS", "glm-4.7-flash,glm-4.6-flash")
    assert config.get_llm_models() == ["glm-4.7-flash", "glm-4.6-flash"]
    # Migration guard: stale cross-provider names fall back to provider
    # defaults instead of 400-ing every chain link.
    monkeypatch.setenv("LLM_MODELS", "gemini-3.8-flash,gemini-3.7-flash")
    assert config.get_llm_models() == ["glm-4.7-flash"]


def test_is_llm_live_provider_gating(monkeypatch):
    for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GLM_API_KEY", "ZAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    assert config.is_llm_live() is False
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    assert config.is_llm_live() is False  # glm provider needs a GLM key
    monkeypatch.setenv("GLM_API_KEY", "z")
    assert config.is_llm_live() is True
    # ZAI_API_KEY alias accepted when GLM_API_KEY is absent.
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "z2")
    assert config.get_llm_key() == "z2"
    # Archived Gemini provider gates on the Google key only.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert config.is_llm_live() is False
    monkeypatch.setenv("GEMINI_API_KEY", "g2")  # alias
    assert config.is_llm_live() is True
    # Unknown provider is never live.
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    assert config.is_llm_live() is False


def test_llm_status_reports_glm_first_link(monkeypatch):
    glm_env(monkeypatch)
    assert config.llm_status() == {"llm": "live", "llm_model": "glm-4.7-flash"}
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    assert config.llm_status() == {"llm": "stub", "llm_model": "stub"}


# ---- dispatcher routing (both providers + unknown) ----

def test_dispatcher_routes_by_provider(monkeypatch):
    glm_env(monkeypatch)
    seen: list[str] = []
    monkeypatch.setattr(llm, "_glm_generate", lambda *a, **k: seen.append("glm") or "{}")
    monkeypatch.setattr(llm, "_gemini_generate", lambda *a, **k: seen.append("gemini") or "{}")
    assert llm._llm_generate("m", "s", "u", "k", 5) == "{}"
    assert seen == ["glm"]
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    llm._llm_generate("m", "s", "u", "k", 5)
    assert seen == ["glm", "gemini"]
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm._llm_generate("m", "s", "u", "k", 5)


# ---- GLM transport: request shape, reasoning_content, failures ----

def test_glm_generate_request_shape_and_reasoning(monkeypatch):
    glm_env(monkeypatch)
    answer = live_json()
    calls = fake_glm_http(monkeypatch, payload={
        "choices": [{"message": {
            "content": answer,
            "reasoning_content": "long compulsory thinking (must be ignored)",
        }}]
    })
    out = llm._glm_generate("glm-4.7-flash", "SYS", "USER", "secret-key", 7)
    assert out == answer  # JSON content only, never the reasoning block
    assert len(calls) == 1
    c = calls[0]
    assert c["url"] == "https://api.z.ai/api/paas/v4/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer secret-key"
    assert c["timeout"] == 7.0
    body = c["json"]
    assert body["model"] == "glm-4.7-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == llm.GLM_MAX_TOKENS
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_glm_base_url_override(monkeypatch):
    glm_env(monkeypatch)
    monkeypatch.setenv("GLM_BASE_URL", "https://example.test/v4/")  # trailing slash
    calls = fake_glm_http(monkeypatch, payload={
        "choices": [{"message": {"content": "{}"}}]
    })
    llm._glm_generate("glm-4.7-flash", "S", "U", "k", 5)
    assert calls[0]["url"] == "https://example.test/v4/chat/completions"


def test_glm_generate_failures_raise(monkeypatch):
    glm_env(monkeypatch)
    fake_glm_http(monkeypatch, status=429, payload={"error": "quota"},
                  text="rate limited")
    with pytest.raises(RuntimeError, match="429"):
        llm._glm_generate("glm-4.7-flash", "S", "U", "k", 5)
    fake_glm_http(monkeypatch, payload={"choices": [{"message": {"content": ""}}]})
    with pytest.raises(ValueError, match="empty"):
        llm._glm_generate("glm-4.7-flash", "S", "U", "k", 5)
    fake_glm_http(monkeypatch, raise_exc=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        llm._glm_generate("glm-4.7-flash", "S", "U", "k", 5)


# ---- end-to-end: GLM 503 -> labelled stub; archived Gemini path live ----

def test_glm_http_503_falls_back_to_labelled_stub(monkeypatch):
    u = mk_user()
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    glm_env(monkeypatch)
    fake_glm_http(monkeypatch, status=503, payload={"error": "busy"},
                  text="unavailable")
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "503" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True  # lenient stub keeps demo alive


def test_gemini_archived_path_still_selectable(monkeypatch):
    u = mk_user("ag")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-google-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    monkeypatch.setattr(llm, "_gemini_generate", lambda *a, **k: live_json())
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "live" and st["model"] == "gemini-3.8-flash"
    assert st["fallback_reason"] == ""
    assert st["evaluation"]["passed"] is True
