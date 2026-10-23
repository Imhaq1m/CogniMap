"""S2f/S2g/S2h provider tests: mixed chain, Groq first link, DeepSeek failover.

Keyless CI stays green: nothing here touches the network — the OpenAI-
compatible transport (both providers share it) is faked at httpx.Client and
chain tests monkeypatch the wrappers. Covers (S2h, grill G-Route): the
free-first mixed default chain, per-link routing BY MODEL ID (qwen/* ->
Groq; deepseek-* -> DeepSeek; anything else raises -> chain advances),
key gating per link (a keyless link is skipped without burning an attempt,
its skip noted in fallback_reason but never clobbering a real failure),
Groq and DeepSeek request shapes + content-only parsing + json_mode flag,
Groq 429 fall-through to the PAID live link (the headline S2h invariant),
HTTP/empty failures -> labelled stub (never 502), and the carried list-shape
fixes (json_mode=False for list-shaped output; `source: generated`/free-
text/missing coerced to extracted while user_added stays rejected). Removal
history mirrors S2c/S2f: glm/gemini/lmstudio have no routing left and their
stale env names + ids cannot 400 or route the chain; LLM_PROVIDER itself was
removed in S2h (chain order replaced the global selector).
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


def clear_links(monkeypatch):
    """No keys, no base URLs, no chain override (G2/G3 asserted defaults)."""
    for k in ("GROQ_API_KEY", "DEEPSEEK_API_KEY", "GROQ_BASE_URL",
              "DEEPSEEK_BASE_URL", "LLM_MODELS"):
        monkeypatch.delenv(k, raising=False)


def groq_env(monkeypatch):
    clear_links(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-not-logged")


def deepseek_env(monkeypatch):
    clear_links(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key-not-logged")


def both_env(monkeypatch):
    groq_env(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key-not-logged")


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


def fake_http(monkeypatch, status=200, payload=None, text="", raise_exc=None,
              responses=None):
    """Fake httpx.Client so the OpenAI-compatible transport runs offline.

    `responses` (S2h) queues per-call outcomes for chain fall-through tests;
    each item is {"status", "payload", "text", "raise_exc"} and is consumed
    in order before the static per-call defaults.
    """
    calls: list[dict] = []
    seq = [dict(r) for r in (responses or [])]

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
            if seq:
                item = seq.pop(0)
                if item.get("raise_exc") is not None:
                    raise item["raise_exc"]
                return _Resp(item.get("status", status),
                             item.get("payload", payload),
                             item.get("text", text))
            if raise_exc is not None:
                raise raise_exc
            return _Resp(status, payload, text)

    monkeypatch.setattr(httpx, "Client", _Client)
    return calls


# ---- config: free-first mixed chain + per-link gating + stale-id guard ----

def test_default_chain_free_first_p2_and_p1_share_one_order(monkeypatch):
    clear_links(monkeypatch)
    # G3: ONE chain serves every LLM activity, free-first (groq -> deepseek).
    assert config.get_llm_models() == ["qwen/qwen3.8-27b", "deepseek-flash"]
    # Explicit LLM_MODELS wins — ids may mix providers (S2h) or reorder.
    monkeypatch.setenv("LLM_MODELS", "deepseek-flash,qwen/qwen3.8-27b")
    assert config.get_llm_models() == ["deepseek-flash", "qwen/qwen3.8-27b"]
    # A single-provider chain is allowed (cheapest demo without failover).
    monkeypatch.setenv("LLM_MODELS", "qwen/qwen3-32b")
    assert config.get_llm_models() == ["qwen/qwen3-32b"]
    # Stale ids from removed providers (glm* S2c / gemini* / gemma* / nemotron
    # S2f) and the opaque deepseek-chat alias (S2g+) are dropped; routable ids
    # around them survive.
    for stale, expected in (
        ("google/gemma-4-26b-a4b-qat", ["qwen/qwen3.8-27b", "deepseek-flash"]),
        ("nvidia-nemotron-3.5-lightning-30b-a3b",
         ["qwen/qwen3.8-27b", "deepseek-flash"]),
        ("gemini-3.8-flash", ["qwen/qwen3.8-27b", "deepseek-flash"]),
        ("glm-4.7-flash", ["qwen/qwen3.8-27b", "deepseek-flash"]),
        ("deepseek-chat", ["qwen/qwen3.8-27b", "deepseek-flash"]),
        ("qwen/qwen3.8-27b,glm-4.7-flash", ["qwen/qwen3.8-27b"]),
        ("deepseek-flash,deepseek-chat", ["deepseek-flash"]),
    ):
        monkeypatch.setenv("LLM_MODELS", stale)
        assert config.get_llm_models() == expected


def test_model_provider_resolution(monkeypatch):
    assert config.model_provider("qwen/qwen3.8-27b") == "groq"
    assert config.model_provider("QWEN/Qwen3-32B") == "groq"  # case-insensitive
    assert config.model_provider("deepseek-flash") == "deepseek"
    assert config.model_provider("deepseek-v4-pro") == "deepseek"
    assert config.model_provider("glm-4.7-flash") is None  # removed: unroutable
    assert config.model_provider("mystery-model") is None
    assert config.model_provider("") is None


def test_llm_provider_env_is_removed(monkeypatch):
    # S2h purge: the global selector no longer exists; a stale env value gats
    # nothing. With no keys on any link the chain is dead regardless.
    clear_links(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    assert not hasattr(config, "get_llm_provider")
    assert config.is_llm_live() is False
    assert config.llm_status() == {"llm": "stub", "llm_model": "stub"}


def test_chain_gating_first_keyed_link_reported(monkeypatch):
    # Gating is per-link now: live iff ANY link has its provider key; health
    # names the first KEYED link (the one a normal click serves).
    clear_links(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    assert config.is_llm_live() is True
    assert config.llm_status() == {"llm": "live", "llm_model": "qwen/qwen3.8-27b"}
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
    assert config.is_llm_live() is True
    # The keyless free link is skipped in the report: first KEYED link wins.
    assert config.llm_status() == {"llm": "live", "llm_model": "deepseek-flash"}
    monkeypatch.setenv("GROQ_API_KEY", "g")
    assert config.llm_status() == {"llm": "live", "llm_model": "qwen/qwen3.8-27b"}
    for k in ("GROQ_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert config.is_llm_live() is False
    assert config.llm_status() == {"llm": "stub", "llm_model": "stub"}
    # Legacy removed-provider keys never gate the chain (S2f carries).
    for key in ("GLM_API_KEY", "LMSTUDIO_API_KEY", "GOOGLE_API_KEY",
                "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "z")
        assert config.is_llm_live() is False


def test_max_tokens_caps_default_shapes(monkeypatch):
    # Cap is chosen by call shape (S2h: identical pacing on both providers).
    clear_links(monkeypatch)
    assert llm._max_tokens(extract=True) == llm.GROQ_MAX_TOKENS_EXTRACT
    assert llm._max_tokens() == llm.GROQ_MAX_TOKENS
    # Parity lock with the named DeepSeek constants (benchmark comparability).
    assert llm.DEEPSEEK_MAX_TOKENS == llm.GROQ_MAX_TOKENS
    assert llm.DEEPSEEK_MAX_TOKENS_EXTRACT == llm.GROQ_MAX_TOKENS_EXTRACT


# ---- dispatcher: routing by model id; unroutable ids raise ----

def test_dispatcher_routes_by_id_and_raises_otherwise(monkeypatch):
    both_env(monkeypatch)
    seen: list[str] = []
    monkeypatch.setattr(llm, "_groq_generate", lambda *a, **k: seen.append("groq") or "{}")
    monkeypatch.setattr(llm, "_deepseek_generate",
                        lambda *a, **k: seen.append("deepseek") or "{}")
    assert llm._llm_generate("qwen/qwen3.8-27b", "s", "u", "k", 5) == "{}"
    llm._llm_generate("deepseek-flash", "s", "u", "k", 5, json_mode=False,
                      max_tokens=llm.GROQ_MAX_TOKENS_EXTRACT)
    assert seen == ["groq", "deepseek"]
    # Unroutable ids (removed providers / unknown) raise ->  the chain
    # advances to the next link (or the labelled stub after all fail).
    for model in ("glm-4.7-flash", "gemini-3.8-flash", "deepseek-chat",
                  "mystery-model"):
        with pytest.raises(ValueError, match="unroutable"):
            llm._llm_generate(model, "s", "u", "k", 5)


def test_dispatcher_forwards_json_mode(monkeypatch):
    groq_env(monkeypatch)
    seen: list[dict] = []
    monkeypatch.setattr(llm, "_groq_generate", lambda *a, **k: seen.append(k) or "{}")
    llm._llm_generate("qwen/qwen3.8-27b", "s", "u", "k", 5, json_mode=False)
    assert seen == [{"json_mode": False, "max_tokens": None}]
    llm._llm_generate("qwen/qwen3.8-27b", "s", "u", "k", 5, json_mode=False,
                      max_tokens=llm.GROQ_MAX_TOKENS_EXTRACT)
    assert seen[-1] == {"json_mode": False,
                        "max_tokens": llm.GROQ_MAX_TOKENS_EXTRACT}


# ---- Groq transport: request shape, content-only reading, failures ----

def test_groq_generate_request_shape_and_content_only(monkeypatch):
    groq_env(monkeypatch)
    answer = live_json()
    calls = fake_http(monkeypatch, payload={
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
    assert "reasoning_effort" not in body  # no removed-provider payload keys
    assert "thinking" not in body  # extra_body stays a DeepSeek-only field
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


def test_groq_generate_failures_raise(monkeypatch):
    groq_env(monkeypatch)
    fake_http(monkeypatch, status=429, payload={"error": "quota"},
              text="rate limited")
    with pytest.raises(RuntimeError, match="429"):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    fake_http(monkeypatch, status=500, payload={"error": "boom"}, text="boom")
    with pytest.raises(RuntimeError, match="500"):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    fake_http(monkeypatch, payload={"choices": [{"message": {"content": ""}}]})
    with pytest.raises(ValueError, match="empty"):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)
    fake_http(monkeypatch, raise_exc=httpx.ConnectError("down"))
    with pytest.raises(httpx.ConnectError):
        llm._groq_generate("qwen/qwen3.8-27b", "S", "U", "k", 5)


# ---- DeepSeek transport (paid failover): shape identical to Groq's ----

def test_deepseek_generate_request_shape_and_content_only(monkeypatch):
    deepseek_env(monkeypatch)
    answer = live_json()
    calls = fake_http(monkeypatch, payload={
        "choices": [{"message": {
            "content": answer,
            "reasoning_content": "any reasoning field (must be ignored)",
        }}]
    })
    out = llm._deepseek_generate("deepseek-flash", "SYS", "USER", "secret-key", 7)
    assert out == answer  # JSON content only, never any reasoning block
    assert len(calls) == 1
    c = calls[0]
    assert c["url"] == "https://api.deepseek.com/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer secret-key"
    assert c["timeout"] == 7.0
    body = c["json"]
    assert body["model"] == "deepseek-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == llm.DEEPSEEK_MAX_TOKENS
    # S2g+ pin: thinking explicitly disabled (effort knobs leave it on).
    assert body["thinking"] == {"type": "disabled"}
    assert "effort" not in body
    assert "reasoning_effort" not in body
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}


# ---- headline S2h invariant: Groq stumble -> PAID link answers live ----

def test_p2_groq_429_falls_through_to_deepseek_live(monkeypatch):
    u = mk_user("mixf")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    both_env(monkeypatch)
    live = {"choices": [{"message": {"content": live_json()}}]}
    calls = fake_http(monkeypatch, responses=[
        {"status": 429, "payload": {"error": "quota"}, "text": "rate limited"},
        {"payload": live},
    ])
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    # The stumble never reaches a stub while the paid link has a key: two
    # HTTP calls, two DIFFERENT vendor endpoints, live on the failover link.
    assert st["mode"] == "live" and st["model"] == "deepseek-flash"
    assert st["fallback_reason"] == ""
    assert st["evaluation"]["passed"] is True
    assert len(calls) == 2
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert calls[0]["json"]["model"] == "qwen/qwen3.8-27b"
    assert calls[1]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[1]["json"]["model"] == "deepseek-flash"
    assert calls[1]["json"]["thinking"] == {"type": "disabled"}


# ---- labelled stub is the last resort: all links fail / keys absent ----

def test_deepseek_http_429_falls_back_to_labelled_stub(monkeypatch):
    u = mk_user("dstub")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    deepseek_env(monkeypatch)
    fake_http(monkeypatch, status=429, payload={"error": "quota"},
              text="rate limited")
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "429" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True


def test_groq_http_503_falls_back_to_labelled_stub(monkeypatch):
    u = mk_user()
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    groq_env(monkeypatch)
    fake_http(monkeypatch, status=503, payload={"error": "busy"},
              text="unavailable")
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "503" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True  # lenient stub keeps demo alive


def test_unkeyed_links_skipped_without_burning_attempts(monkeypatch):
    """A link without a provider key is skipped (no sold attempt, no 401)."""
    u = mk_user("noskip")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    deepseek_env(monkeypatch)  # only the paid link keyed
    def boom(*a, **k):
        raise AssertionError("unkeyed link must never be attempted")
    monkeypatch.setattr(llm, "_groq_generate", boom)
    calls = fake_http(monkeypatch, payload={
        "choices": [{"message": {"content": live_json()}}]
    })
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "live" and st["model"] == "deepseek-flash"
    assert len(calls) == 1  # Groq link skipped silently, DeepSeek served


@pytest.mark.parametrize("stale_key,stale_value", [
    ("LMSTUDIO_API_KEY", "lm-studio"),
    ("GOOGLE_API_KEY", "dummy-google-key"),
    ("GLM_API_KEY", "old-glm-key"),
])
def test_removed_providers_fall_to_labelled_stub(monkeypatch, stale_key,
                                                 stale_value):
    """S2c/S2f carry: removed providers have no routing; their old keys and
    stale env values gate nothing — with zero keyed links the labelled stub
    answers and the demo never 502s."""
    u = mk_user("rmp")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    clear_links(monkeypatch)
    monkeypatch.setenv(stale_key, stale_value)
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "no key on any chain link" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True  # never 502


# ---- P1 (list-shaped): no object mode; known source conflation coerced ----

def test_p1_chain_list_mode_and_source_coercion(monkeypatch):
    groq_env(monkeypatch)
    row = main_row("m1")
    row["source"] = "generated"  # model conflation -> coerced, never user_added
    calls = fake_http(monkeypatch, payload={
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


def test_p1_falls_paid_link_when_groq_stumbles(monkeypatch):
    """P1 burst-stumble (the S2b->S2e note; G4): the paid link answers live."""
    u = mk_user()  # not needed for P1 lighting, chain only
    both_env(monkeypatch)
    row = main_row("m1")
    live_p1 = ["```json\n" + json.dumps([row]) + "\n```"]
    calls = fake_http(monkeypatch, responses=[
        {"status": 429, "payload": {"error": "quota"}, "text": "rate limited"},
        {"payload": {"choices": [{"message": {"content": live_p1[0]}}]}},
    ])
    st = llm.extract_concepts_with_status("Some parsed markdown about ML.")
    assert st["mode"] == "live" and st["model"] == "deepseek-flash"
    assert st["concepts"][0]["source"] == "extracted"
    assert len(calls) == 2
    assert calls[1]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[1]["json"]["thinking"] == {"type": "disabled"}


def test_groq_caps_stay_under_free_tier_pacing():
    # Measured 429 strings quoted OTPM 1000/min with max_tokens reserving
    # against it; the S2e free-plan budget (tpm 8000 prompt+completion) is
    # roomier. Either way both caps fit well under both windows.
    assert 0 < llm.GROQ_MAX_TOKENS <= llm.GROQ_MAX_TOKENS_EXTRACT < 1000
    # DeepSeek is pay-as-you-go — same honest caps for benchmark parity (S2g).
    assert 0 < llm.DEEPSEEK_MAX_TOKENS <= llm.DEEPSEEK_MAX_TOKENS_EXTRACT


def test_p1_empty_list_reason_is_clean(monkeypatch):
    """Placeholder/empty parsed text: live [] is a labelled stub, not an error."""
    groq_env(monkeypatch)
    fake_http(monkeypatch, payload={
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
    # Gemma-4-style conflation (found 2026-10-22, provider-agnostic since):
    # free-text / missing source treated the same lenient way — provenance is
    # always extracted from a live extractor.
    tomorrow = main_row("m2")
    tomorrow["source"] = "Machine Learning"  # section title pasted in
    out = llm.validate_extract_shape([tomorrow])
    assert out[0]["source"] == "extracted"
    omitted = main_row("m3")
    omitted.pop("source")
    out = llm.validate_extract_shape([omitted])
    assert out[0]["source"] == "extracted"
    bad = main_row("m4")
    bad["source"] = "user_added"
    with pytest.raises(ValueError, match="extracted only"):
        llm.validate_extract_shape([bad])


def test_groq_default_path_live_eval(monkeypatch):
    """Default path: Groq eval end-to-end with the wrapper monkeypatched."""
    u = mk_user("agr")
    s = mk_session(u["id"])
    store.confirm_selection(s["id"], u["id"], [main_row("m1")])
    groq_env(monkeypatch)
    monkeypatch.setattr(llm, "_groq_generate", lambda *a, **k: live_json())
    st = llm.evaluate_paraphrase_with_status(
        s["id"], "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "live" and st["model"] == "qwen/qwen3.8-27b"
    assert st["fallback_reason"] == ""
    assert st["evaluation"]["passed"] is True
