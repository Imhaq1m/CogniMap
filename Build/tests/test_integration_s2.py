"""S2 integration tests (Integration_Tracker S2 / S8 ride-along).

Keyless CI stays green: stub + blue-bypass assertions always run; live tests
skip without keys; fallback tests force bad-key/bad-JSON -> stub + mode=stub;
a mocked live chain covers the full seed -> L3 transition without network.
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

import pytest
from starlette.testclient import TestClient

from app import config, llm, store
from app.main import app

client = TestClient(app)


def mk_user(prefix="s2"):
    return store.get_or_create_user(f"{prefix}-{uuid.uuid4().hex[:6]}")


def mk_session(uid, file="seed-demo.pdf"):
    return store.create_session(uid, file)


def main_row(cid="m1", **kw):
    d = {
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
    d.update(kw)
    return d


def blue_row(cid="b1"):
    return main_row(cid, source="user_added", explanation_text="",
                    explanation_source="user")


def force_live(monkeypatch):
    # S2h: free-first mixed chain — first (Groq) link serves mocked-live calls.
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-not-logged")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)  # default mixed chain


def live_json(accuracy="Accurate", originality="Own words",
              feedback="Core meaning captured in your own words.",
              hint="", passed=True):
    return json.dumps({
        "passed": passed,
        "accuracy": accuracy,
        "originality": originality,
        "feedback": feedback,
        "hint": hint,
    })


def live_verifies(sid, uid, concept_ids, paraphrase="my own words"):
    out = []
    for cid in concept_ids:
        r = client.post(
            f"/api/sessions/{sid}/l12/verify",
            params={"user_id": uid},
            json={"concept_id": cid, "paraphrase": paraphrase},
        )
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


# ---- grill locks: rubric + hint policy ----

def test_p2_prompt_rubric_and_hint_policy():
    assert "lenient tutor" in llm.P2_SYSTEM
    assert "missing supporting details" in llm.P2_SYSTEM
    assert "captures the central idea" in llm.P2_SYSTEM
    assert "reserve Partly accurate" in llm.P2_RULES
    assert "accuracy == 'Accurate'" in llm.P2_SYSTEM
    assert "originality == 'Own words'" in llm.P2_SYSTEM
    assert "NEVER states or paraphrases the reference answer" in llm.P2_SYSTEM
    assert "ONE short nudge" in llm.P2_SYSTEM
    assert "no external knowledge" in llm.P2_SYSTEM
    # Balanced but lenient: shared terms are fine; only near-verbatim copying fails.
    assert "Shared technical terms" in llm.P2_SYSTEM
    assert "when in doubt choose 'own words'" in llm.P2_SYSTEM.lower()
    assert "hint is empty on pass" in llm.P2_RULES


# ---- grounding: server-resolved row, only paraphrase is client text ----

def test_grounded_prompt_uses_resolved_fields(monkeypatch):
    u = mk_user("grU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row(
        "m1",
        explanation_text="STORED-EXPLANATION",
        explanation_type="procedure",
        explanation_source="generated",
        pages=[5, 7],
        diagram_description="STORED-DIAGRAM-BRIDGE",
    )])
    force_live(monkeypatch)
    seen: dict = {}

    def fake(model, system, user, api_key, timeout_s):
        seen.update(model=model, system=system, user=user,
                    api_key=api_key, timeout_s=timeout_s)
        return live_json()

    monkeypatch.setattr(llm, "_llm_generate", fake)
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1", "MY-STUDENT-WORDS", user_id=u["id"]
    )
    assert st["mode"] == "live" and st["model"] == "qwen/qwen3.8-27b"
    assert st["evaluation"]["passed"] is True
    assert seen["system"] == llm.P2_SYSTEM
    assert "STORED-EXPLANATION" in seen["user"]
    assert "STORED-DIAGRAM-BRIDGE" in seen["user"]
    assert "REFERENCE_TYPE: procedure" in seen["user"]
    assert "REFERENCE_PAGES: [5, 7]" in seen["user"]
    assert "MY-STUDENT-WORDS" in seen["user"]
    # Keys never enter prompts/log payloads.
    assert "dummy-key-not-logged" not in seen["user"]
    assert "dummy-key-not-logged" not in seen["system"]


def test_s2_ownership_gate_defense_in_depth():
    a = mk_user("ownA")
    b = mk_user("ownB")
    s = mk_session(a["id"])
    store.confirm_selection(s["id"], a["id"], [main_row("m1")])
    with pytest.raises(PermissionError):
        llm.evaluate_paraphrase_with_status(
            s["id"], "m1", "my words", user_id=b["id"]
        )
    with pytest.raises(KeyError):
        llm.evaluate_paraphrase_with_status(
            s["id"], "nope", "my words", user_id=a["id"]
        )


# ---- balanced rubric: both bands gate the pass; model `passed` is ignored ----

@pytest.mark.parametrize("accuracy,originality,expected", [
    ("Accurate", "Own words", True),
    ("Accurate", "Too close to source", False),
    ("Partly accurate", "Own words", False),
    ("Inaccurate", "Own words", False),
])
def test_live_balanced_pass_gate(monkeypatch, accuracy, originality, expected):
    u = mk_user("balU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row("m1")])
    force_live(monkeypatch)
    # Model claims passed=True; the app derives the gate from the bands.
    monkeypatch.setattr(
        llm, "_llm_generate",
        lambda *a, **k: live_json(accuracy=accuracy, originality=originality,
                                  hint="focus on the key idea"),
    )
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "live"
    assert st["evaluation"]["passed"] is expected
    if expected:
        assert st["evaluation"]["hint"] == ""
    else:
        assert st["evaluation"]["hint"]


def test_validate_paraphrase_eval_shape():
    ok = llm.validate_paraphrase_eval_shape({
        "passed": True, "accuracy": "Accurate", "originality": "Own words",
        "feedback": "Good.", "hint": "should be cleared on pass",
    })
    assert ok["passed"] is True and ok["hint"] == ""
    copied = llm.validate_paraphrase_eval_shape({
        "passed": True, "accuracy": "Accurate",
        "originality": "Too close to source", "feedback": "Copied.",
    })
    assert copied["passed"] is False and copied["hint"]
    # Common model punctuation must not force a false fallback.
    period = llm.validate_paraphrase_eval_shape({
        "accuracy": "Accurate.", "originality": "Own words.",
        "feedback": "Good.",
    })
    assert period["passed"] is True
    # Hint guardrail: a hint must not echo the reference answer verbatim.
    long_ref = "REFERENCE-ANSWER-THAT-MUST-NOT-BE-ECHOED"
    guarded = llm.validate_paraphrase_eval_shape({
        "accuracy": "Partly accurate", "originality": "Own words",
        "feedback": "Try again.", "hint": long_ref,
    }, reference=long_ref)
    assert long_ref not in guarded["hint"] and guarded["hint"]
    with pytest.raises(ValueError):
        llm.validate_paraphrase_eval_shape([])
    with pytest.raises(ValueError, match="accuracy"):
        llm.validate_paraphrase_eval_shape({
            "accuracy": "excellent", "originality": "Own words",
            "feedback": "x",
        })
    with pytest.raises(ValueError, match="feedback"):
        llm.validate_paraphrase_eval_shape({
            "accuracy": "Accurate", "originality": "Own words",
        })


# ---- fallback: bad key / bad JSON -> stub + mode=stub, never 502 ----

def test_fallback_bad_key_goes_stub(monkeypatch):
    u = mk_user("fkU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row("m1")])
    force_live(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("401 bad key")

    monkeypatch.setattr(llm, "_llm_generate", boom)
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub" and st["model"] == "stub"
    assert "RuntimeError" in st["fallback_reason"]
    assert st["evaluation"]["passed"] is True  # lenient stub keeps demo alive
    r = client.post(f"/api/sessions/{sid}/l12/verify", params={"user_id": u["id"]},
                    json={"concept_id": "m1", "paraphrase": "my own words"})
    assert r.status_code == 200
    j = r.json()
    assert j["mode"] == "stub" and "stubbed" in j["warning"].lower()


def test_fallback_bad_json_goes_stub(monkeypatch):
    u = mk_user("fjU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row("m1")])
    force_live(monkeypatch)
    monkeypatch.setattr(llm, "_llm_generate", lambda *a, **k: "not-json {{{")
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "stub"
    assert st["fallback_reason"]
    assert st["evaluation"]["passed"] is True


def test_live_fail_is_not_replaced_by_stub(monkeypatch):
    u = mk_user("lfU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row("m1")])
    force_live(monkeypatch)
    monkeypatch.setattr(
        llm, "_llm_generate",
        lambda *a, **k: live_json(
            accuracy="Partly accurate", originality="Own words",
            feedback="Close, but one key idea is missing.",
            hint="Name the key idea the reference explains.",
        ),
    )
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1", "my own words", user_id=u["id"]
    )
    assert st["mode"] == "live"
    assert st["fallback_reason"] == ""
    assert st["evaluation"]["passed"] is False
    assert st["evaluation"]["hint"]
    assert "missing" in st["evaluation"]["feedback"]


# ---- blue bypass: no LLM, plausibility only, no accuracy/originality ----

def test_blue_bypass_never_calls_llm(monkeypatch):
    u = mk_user("blU")
    s = mk_session(u["id"])
    sid = s["id"]
    client.post(f"/api/sessions/{sid}/confirm-selection",
                params={"user_id": u["id"]},
                json={"concepts": [main_row("m1"), blue_row("b1")]})
    force_live(monkeypatch)
    calls: list = []

    def fake(*a, **k):
        calls.append(1)
        return live_json()

    monkeypatch.setattr(llm, "_llm_generate", fake)
    st = llm.evaluate_paraphrase_with_status(
        sid, "b1", "my self-defined meaning", user_id=u["id"]
    )
    assert calls == []
    assert st["mode"] == "bypass" and st["model"] == "rules"
    assert st["evaluation"]["passed"] is True
    assert "accuracy" not in st["evaluation"]
    v = client.post(f"/api/sessions/{sid}/l12/verify",
                    params={"user_id": u["id"]},
                    json={"concept_id": "b1", "paraphrase": "saved note"}).json()
    assert calls == []
    assert v["bypass"] is True and v["mode"] == "bypass"
    assert "accuracy" not in v and "originality" not in v
    assert v["warning_ack"] and v["user_explanation"] == "saved note"
    rows = {c["id"]: c for c in store.list_concepts(sid)}
    assert rows["b1"]["explanation_text"] == "saved note"


# ---- DONE gate: seed 100% still triggers L3, keyless and mocked-live ----

def test_l12_js_shows_stub_warning_additively():
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "l12.js"),
              encoding="utf-8").read()
    assert "j.warning" in js
    # Required locked UI keys still rendered; warning is additive only.
    assert "j.accuracy" in js and "j.originality" in js and "j.feedback" in js
    assert "j.bypass" in js and "warning_ack" in js


def test_seed_100_keyless_triggers_l3(monkeypatch):
    for k in ("LLAMA_CLOUD_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    u = mk_user("seedU")
    s = mk_session(u["id"])
    sid = s["id"]
    mains = [c for c in llm.load_seed_concepts() if c.get("kind") == "main"]
    r = client.post(f"/api/sessions/{sid}/confirm-selection",
                    params={"user_id": u["id"]},
                    json={"concepts": mains})
    assert r.status_code == 200, r.text
    out = live_verifies(sid, u["id"], [c["concept_id"] for c in mains])
    assert len(out) == len(mains)
    for c, v in zip(mains, out):
        if c.get("source") == "user_added":
            assert v["mode"] == "bypass" and v["bypass"] is True
            assert "accuracy" not in v and "originality" not in v
        else:
            assert v["mode"] == "stub"
            assert v["accuracy"] and v["originality"]
            assert "stubbed" in v["warning"].lower()
    last = out[-1]
    assert last["l3_ready"] is True
    assert last["progress"]["pct"] == 100 and last["progress"]["complete"] is True
    assert store.get_session(sid)["stage"] == "L3"
    # Trail (§9): latest L1-2 row per concept, extracted vs blue shapes.
    rows = [t for t in store.list_trail(sid) if t["stage"] == "L1-2"]
    assert len(rows) == len(mains)
    for t in rows:
        pay = json.loads(t["payload"])
        assert "paraphrase" in pay and "feedback" in pay
        if t["concept_id"] == "c6":
            assert pay["warning_ack"] and pay["user_explanation"]
            assert "accuracy" not in pay and "originality" not in pay
        else:
            assert pay["accuracy"] and pay["originality"]
            assert "warning_ack" not in pay


def test_live_style_seed_100_mocked_triggers_l3(monkeypatch):
    u = mk_user("liveU")
    s = mk_session(u["id"])
    sid = s["id"]
    mains = [c for c in llm.load_seed_concepts() if c.get("kind") == "main"]
    client.post(f"/api/sessions/{sid}/confirm-selection",
                params={"user_id": u["id"]},
                json={"concepts": mains})
    force_live(monkeypatch)
    calls: list[str] = []

    def fake(model, *a, **k):
        calls.append(model)
        return live_json()

    monkeypatch.setattr(llm, "_llm_generate", fake)
    out = live_verifies(sid, u["id"], [c["concept_id"] for c in mains])
    extracted = [c for c in mains if c.get("source") != "user_added"]
    assert len(calls) == len(extracted)  # blue c6 never reaches the model
    for c, v in zip(mains, out):
        if c.get("source") == "user_added":
            assert v["mode"] == "bypass"
        else:
            assert v["mode"] == "live" and v["model"] == "qwen/qwen3.8-27b"
    last = out[-1]
    assert last["l3_ready"] is True
    assert last["progress"]["pct"] == 100
    assert store.get_session(sid)["stage"] == "L3"


# ---- live test skips without keys ----

@pytest.mark.skipif(not config.is_llm_live(), reason="no LLM key (keyless CI skip)")
def test_live_paraphrase_shape():
    u = mk_user("realU")
    s = mk_session(u["id"])
    sid = s["id"]
    store.confirm_selection(sid, u["id"], [main_row(
        "m1",
        title="Machine Learning",
        explanation_text="Machine learning lets systems learn patterns from data instead of following fixed rules.",
        pages=[5, 6],
    )])
    st = llm.evaluate_paraphrase_with_status(
        sid, "m1",
        "Machine learning is when a system learns patterns from examples "
        "rather than being programmed with fixed rules.",
        user_id=u["id"],
    )
    assert st["mode"] in ("live", "stub")
    ev = st["evaluation"]
    assert {"passed", "accuracy", "originality", "feedback", "hint"} <= set(ev)
    assert isinstance(ev["passed"], bool)
    if st["mode"] == "live":
        assert ev["accuracy"] and ev["originality"]
