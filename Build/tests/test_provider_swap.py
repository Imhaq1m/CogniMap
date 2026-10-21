"""S2c provider-swap tests: Groq qwen/qwen3.8-27b default, Gemini archived.

Keyless CI stays green: nothing here touches the network — the Groq transport
is faked at httpx.Client and chain tests monkeypatch the dispatcher. Covers:
provider gating/defaults, dispatcher routing, Groq request shape + content-only
parsing, HTTP/empty failures -> labelled stub, the archived Gemini path staying
selectable end-to-end, and the P1 list-shape fixes carried over (json_mode=False
for list-shaped output; `source: generated` conflation coerced while user_added
stays rejected). GLM was removed (not archived) in S2c — no provider path
routes it. Isolated DB pattern mirrors tests/test_locks.py:14.
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


def groq_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-not-logged")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)


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


def fake_groq_http(monkeypatch, status=200, payload=None, text="", raise_exc=None):
    """Fake httpx.Client so _groq_generate runs offline; returns captured calls."""
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

def test_provider_default_is_groq_archived_gemini_kept(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)
    assert config.get_llm_provider() == "groq"
    assert config.get_llm_models() == ["qwen/qwen3.8-27b"]
    # Archived Gemini chain still selectable, not deleted.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert config.get_llm_models() == [
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
    ]
    # Explicit LLM_MODELS wins within the provider.
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODELS", "qwen/qwen3.8-27b,qwen/qwen3-32b")
    assert config.get_llm_models() == ["qwen/qwen3.8-27b", "qwen/qwen3-32b"]
    # Migration guard: stale cross-provider names fall back to provider
    # defaults instead of 400-ing every chain link (glm removed in S2c).
    monkeypatch.setenv("LLM_MODELS", "glm-4.7-flash")
    assert config.get_llm_models() == ["qwen/qwen3.8-27b"]
    monkeypatch.setenv("LLM_MODELS", "gemini-3.8-flash,gemini-3.7-flash")
    assert config.get_llm_models() == ["qwen/qwen3.8-27b"]


def test_is_llm_live_provider_gating(monkeypatch):
    for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert config.is_llm_live() is False
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    assert config.is_llm_live() is False  # groq provider needs the Groq key
    monkeypatch.setenv("GROQ_API_KEY", "z")
    assert config.is_llm_live() is True
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


def test_llm_status_reports_groq_first_link(monkeypatch):
    groq_env(monkeypatch)
    assert config.llm_status() == {"llm": "live", "llm_model": "qwen/qwen3.8-27b"}
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert config.llm_status() == {"llm": "stub", "llm_model": "stub"}


# ---- dispatcher routing (both providers + unknown) ----

def test_dispatcher_routes_by_provider(monkeypatch):
    groq_env(monkeypatch)
    seen: list[str] = []
    monkeypatch.setattr(llm, "_groq_generate", lambda *a, **k: seen.append("groq") or "{}")
    monkeypatch.setattr(llm, "_gemini_generate", lambda *a, **k: seen.append("gemini") or "{}")
    assert llm._llm_generate("m", "s", "u", "k", 5) == "{}"
    assert seen == ["groq"]
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    llm._llm_generate("m", "s", "u", "k", 5)
    assert seen == ["groq", "gemini"]
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm._llm_generate("m", "s", "u", "k", 5)


def test_dispatcher_forwards_json_mode(monkeypatch):
    groq_env(monkeypatch)
    seen: list[dict] = []
    monkeypatch.setattr(llm, "_groq_generate", lambda *a, **k: seen.append(k) or "{}")
    llm._llm_generate("m", "s", "u", "k", 5, json_mode=False)
    assert seen == [{"json_mode": False, "max_tokens": None}]
    llm._llm_generate("m", "s", "u", "k", 5, json_mode=False,
                      max_tokens=llm.GROQ_MAX_TOKENS_EXTRACT)
    assert seen[-1] == {"json_mode": False,
                        "max_tokens": llm.GROQ_MAX_TOKENS_EXTRACT}


# ---- Groq transport: request shape, content-only reading, failures ----

def test_groq_generate_request_shape_and_content_only(monkeypatch):
    groq_env(monkeypatch)
    answer = live_json()
    calls = fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {
            "content": answer,
            "reasoning": "any reasoning field (must be ignored)",
        }}]
    })
    out = llm._groq_generate("qwen/qwen3.8-27b", "SYS", "USER", "secret-key", 7)
    assert out == answer  # JSON content only, never any reasoning block
    assert len(calls) == 1
    c = calls[0]
    assert c["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer secret-key"
    assert c["timeout"] == 7.0
    body = c["json"]
    assert body["model"] == "qwen/qwen3.8-27b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == llm.GROQ_MAX_TOKENS
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_groq_base_url_override(monkeypatch):
    groq_env(monkeypatch)
    monkeypatch.setenv("GROQ_BASE_URL", "https://example.test/v1/")  # trailing slash
    calls = fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {"content": "{}"}}]
    })
    llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    assert calls[0]["url"] == "https://example.test/v1/chat/completions"


def test_groq_json_mode_flag_controls_response_format(monkeypatch):
    groq_env(monkeypatch)
    calls = fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {"content": "{}"}}]
    })
    llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5, json_mode=False)
    assert "response_format" not in calls[0]["json"]  # list-shaped calls opt out
    calls2 = fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {"content": "{}"}}]
    })
    llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)  # default stays object
    assert calls2[0]["json"]["response_format"] == {"type": "json_object"}


def test_groq_generate_failures_raise(monkeypatch):
    groq_env(monkeypatch)
    fake_groq_http(monkeypatch, status=429, payload={"error": "quota"},
                   text="rate limited")
    with pytest.raises(RuntimeError, match="429"):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    fake_groq_http(monkeypatch, payload={"choices": [{"message": {"content": ""}}]})
    with pytest.raises(ValueError, match="empty"):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    fake_groq_http(monkeypatch, raise_exc=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)


# ---- end-to-end: Groq 503 -> labelled stub; archived Gemini path live ----

def test_groq_http_503_falls_back_to_labelled_stub(monkeypatch):
    u = mk_user()
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    groq_env(monkeypatch)
    fake_groq_http(monkeypatch, status=503, payload={"error": "busy"},
                   text="unavailable")
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "503" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True  # lenient stub keeps demo alive


# ---- P1 (list-shaped): no object mode; known source conflation coerced ----

def test_p1_chain_list_mode_and_source_coercion(monkeypatch):
    groq_env(monkeypatch)
    row = main_row("m1")
    row["source"] = "generated"  # model conflation -> coerced, never user_added
    calls = fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {
            "content": "```json\n" + json.dumps([row]) + "\n```",
        }}]
    })
    st = llm.extract_concepts_with_status("Some parsed markdown about ML.")
    assert st["mode"] == "live" and st["model"] == "qwen/qwen3.8-27b"
    assert st["fallback_reason"] == ""
    assert "response_format" not in calls[0]["json"]  # P1 must not force object mode
    assert calls[0]["json"]["max_tokens"] == llm.GROQ_MAX_TOKENS_EXTRACT
    assert st["concepts"][0]["source"] == "extracted"  # coerced by the validator


def test_groq_caps_stay_under_free_tier_otpm():
    # qwen3.8-27b free tier: OTPM 1000/min; each request's max_tokens reserves
    # against that budget, so both caps must fit well under 1000.
    assert 0 < llm.GROQ_MAX_TOKENS <= llm.GROQ_MAX_TOKENS_EXTRACT < 1000


def test_p1_empty_list_reason_is_clean(monkeypatch):
    """Placeholder/empty parsed text: live [] is a labelled stub, not an error."""
    groq_env(monkeypatch)
    fake_groq_http(monkeypatch, payload={
        "choices": [{"message": {"content": "[]"}}]
    })
    st = llm.extract_concepts_with_status("")
    assert st["mode"] == "stub"
    assert "no concepts" in st["fallback_reason"]
    assert "validation failed" not in st["fallback_reason"]


def test_validator_coerces_generated_source_only():
    row = main_row("m1")
    row["source"] = "generated"
    out = llm.validate_extract_shape([row])
    assert out[0]["source"] == "extracted"
    bad = main_row("m2")
    bad["source"] = "user_added"
    with pytest.raises(ValueError, match="extracted only"):
        llm.validate_extract_shape([bad])


def test_glm_provider_removed(monkeypatch):
    # S2c user decision: GLM removed from the system (not archived).
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "old-glm-key")
    assert config.get_llm_key() is None
    assert config.is_llm_live() is False


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
