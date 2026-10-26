"""S5 integration tests (Integration_Tracker S5 / S8 ride-along).

Keyless CI stays green: the frozen stub asserts always run; the live chain
is exercised through a routing-faithful mock of _llm_generate (a
chain-shaped model that grades exactly the GRADED_SIDES listed in the
prompt), while transport-level request shapes stay covered in
test_provider_swap.py. Covers the S5 grill ledger (S5-G1..G7):

- P5 probing-analyst prompts (sides graded independently on their own
  content, anti-recital rubric, ~140-char feedback, hints never answers,
  custom edges byte-same prompts), caps p5=400;
- S5-G1: blue-involved links JOIN the one P5 call (ground = the user's own
  saved explanation, G8 consistency rubric, "user-defined — plausibility
  check, not doc-cited" prefix enforced app-side exactly once, no page
  citations) — amends G2''s L5 freeze the same way G2'/G8 amended S3;
- S5-G2: a lock-passed side is NEVER re-graded (excluded from the prompt,
  returns a frozen pass), mirrors the S3 locked-row rule; S5-G7a:
  both-sides-locked resubmit = zero model calls, mode=rules;
- S5-G3: verdicts structural (missing verdict -> chain advance), the rest
  coerces stay-live (string verdicts fail closed, generic feedbacks/
  nudges, pass hint empty, fail hint echoing a ground replaced);
- keyless labels + no leak, whole-chain failure -> lenient labelled stub
  (never 502), unkeyed-link skip in fallback_reason, model labels per
  actually-served link, live fail stays live;
- DONE gate: seed 100% triggers Phase2 with or without keys (keyless run +
  mocked-live run), trail one row per attempt with both answers.
Isolated DB pattern mirrors tests/test_locks.py:14.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid

_DB = os.path.join(tempfile.gettempdir(), f"cognimap_test_s5_{os.getpid()}.db")
os.environ.setdefault("COGNIMAP_DB", _DB)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from starlette.testclient import TestClient

from app import config, llm, store
from app.main import app

client = TestClient(app)


def mk_user(prefix="s5"):
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


def confirm_plus_l12(sid, uid, concepts):
    store.confirm_selection(sid, uid, concepts)
    for c in concepts:
        if c.get("source") == "user_added":
            store.set_user_explanation(sid, c["concept_id"], "user note")
    for c in concepts:
        store.record_l12_attempt(sid, uid, c["concept_id"],
                                 f"para {c['concept_id']}", True, "a", "o",
                                 "fb", "")


def start_l5(sid, uid, concepts, edge_types=None):
    """Confirm + L1-2 passes + link cycle in L4 + Finish -> L5 (N fixed).

    n>=3 closes the cycle (each concept degree 2 <= max 3); n==2 takes ONE
    edge (a 'cycle' would be the same unordered pair -> one-link-per-pair
    block). Every counted concept ends >=1-linked so Finish enables.
    """
    confirm_plus_l12(sid, uid, concepts)
    store.set_stage(sid, "L4")
    ids = [c["concept_id"] for c in concepts]
    types = edge_types or ["causes"] * len(ids)
    if len(ids) >= 3:
        for i in range(len(ids)):
            store.create_link(sid, ids[i], (ids + ids[:1])[i + 1], types[i],
                              user_id=uid)
    elif len(ids) == 2:
        store.create_link(sid, ids[0], ids[1], (types + ["causes"])[0],
                          user_id=uid)
    out = store.l4_finish(sid, uid)
    assert out["l5_n"] == (len(ids) if len(ids) >= 3 else 1)
    return ids


def force_live(monkeypatch, deepseek=False):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-not-logged")
    if deepseek:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key-not-logged")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)  # default mixed chain


def probe_needed(s, uid):
    st = client.get(f"/api/sessions/{s['id']}/l5/status",
                    params={"user_id": uid}).json()
    bright = {L["id"] for L in st["links"] if L["bright"]}
    return next(L["id"] for L in st["links"]
                if L["id"] in set(st["target_ids"]) and L["id"] not in bright)


def submit_probe(s, uid, link_id, why="why answer", fail="fail answer"):
    r = client.post(f"/api/sessions/{s['id']}/l5/probe",
                    params={"user_id": uid},
                    json={"link_id": link_id, "why_answer": why,
                          "fail_answer": fail})
    assert r.status_code == 200, r.text
    return r.json()


# ---- routing-faithful P5 fake ----

_DEFAULT_FB = {"why": "Holds mechanically.", "fail": "Breaks at scale-up."}


def _probe_json(user: str, spec: dict | None = None) -> str:
    """Grade exactly the GRADED_SIDES listed in the prompt (obedient model)."""
    graded = json.loads(user.split("GRADED_SIDES: ")[1].split("\n")[0])
    out = {}
    for side in graded:
        s = (spec or {}).get(side) or {}
        out[f"{side}_passed"] = s.get("passed", True)
        out[f"{side}_feedback"] = s.get("feedback", _DEFAULT_FB[side])
        out[f"{side}_hint"] = s.get("hint", "")
    return json.dumps(out)


def probe_obeying_fake(calls: list[dict], spec: dict | None = None):
    def fake(model, system, user, *a, **k):
        calls.append({"model": model, "system": system, "user": user,
                      "kwargs": k})
        return _probe_json(user, spec)

    return fake


def failing_fake(calls: list[dict], exc=None):
    def fake(model, system, user, *a, **k):
        calls.append({"model": model, "system": system, "user": user,
                      "kwargs": k})
        raise exc or RuntimeError(f"HTTP 429 (fake, {model})")

    return fake


# ---- prompts (S5-G6 rubric bundle) ----

def test_p5_prompt_rubric_locked_wording():
    assert "probe defended links" in llm.P5_SYSTEM
    assert "decide independently whether that answer holds" in llm.P5_SYSTEM
    assert "no external knowledge" in llm.P5_SYSTEM
    # Anti-recital rubric (S3 G6 carry, extended to blue).
    assert "merely restates the EDGE wording" in llm.P5_SYSTEM
    assert "definition or never touches the question" in llm.P5_SYSTEM
    prefix = "user-defined — plausibility check, not doc-cited"
    assert prefix in llm.P5_SYSTEM and prefix in llm.P5_RULES
    assert "the user's own definition" in llm.P5_RULES
    assert "never cite pages" in llm.P5_RULES
    # Feedback/hint policy mirrors P2/P4.
    assert "ONE short (~140 chars) sentence per side" in llm.P5_RULES
    assert "never states or paraphrases the expected answer" in llm.P5_SYSTEM
    assert "Same prompts for custom edges" in llm.P5_RULES
    assert "Grade ONLY the sides listed in GRADED_SIDES" in llm.P5_SYSTEM


def test_build_p5_user_lanes_blue_marker_and_clips():
    edge = {"a_id": "m1", "b_id": "m2", "edge_type": "causes"}
    a = {"id": "m1", "title": "Machine Learning",
         "explanation_type": "definition", "pages": [5, 6],
         "explanation_text": "ML ground", "diagram_description": "D1",
         "source": "extracted"}
    b = {"id": "m2", "title": "Deployment (my map)",
         "explanation_type": "definition", "pages": [],
         "explanation_text": "user note", "diagram_description": "",
         "source": "user_added"}
    out = llm.build_p5_user(edge, a, b, ["why", "fail"], "why text",
                            "fail text")
    assert out.startswith(llm.P5_RULES)  # stable prefix first
    assert "EDGE: m1 -causes-> m2" in out
    assert "- m1 | Machine Learning | definition | pages [5, 6] | ML ground | D1" in out
    # S5-G1: blue endpoint ground = the USER TEXT with no page citation.
    assert ("- m2 | Deployment (my map) | definition | pages user-defined | "
            "user note |  [BLUE: user_added") in out
    assert "[BLUE: user_added" in out and "never cite pages" in out
    assert 'GRADED_SIDES: ["why", "fail"]' in out
    assert "- why: why text" in out and "- fail: fail text" in out
    assert "ANSWERS (grade only these):" in out
    # No store machinery or client ids leak into the prompt.
    assert "user_id" not in out and "session" not in out.lower()
    # Answers clipped at 2000 (P3 text-clip mirror).
    long = llm.build_p5_user(edge, a, b, ["why"], "w" * 3000)
    assert ("w" * 2000) in long and ("w" * 2001) not in long
    # S5-G2: an excluded (locked) side never shows an ANSWERS line.
    fail_only = llm.build_p5_user(edge, a, b, ["fail"], "w", "fail text")
    assert 'GRADED_SIDES: ["fail"]' in fail_only
    assert "- fail: fail text" in fail_only
    assert "- why:" not in fail_only.split("ANSWERS", 1)[1]


# ---- validators (LLM API output validation) ----

def test_validate_probe_eval_shape_accepts():
    grounds = {"why": "ground", "fail": "ground"}
    data = {"why_passed": True, "why_feedback": "Holds.", "why_hint": "",
            "fail_passed": False, "fail_feedback": "Weak.", "fail_hint": "n"}
    out = llm.validate_probe_eval_shape(data, ["why", "fail"], grounds)
    assert out["why"]["passed"] is True and out["why"]["hint"] == ""
    assert out["fail"]["passed"] is False and out["fail"]["hint"] == "n"
    # Optional {"probe": {...}} wrapper tolerated (P3 scenario precedent).
    out = llm.validate_probe_eval_shape({"probe": data}, ["why", "fail"])
    assert out["why"]["passed"] is True
    # S5-G2: grading one side tolerates the other side's keys being absent.
    out = llm.validate_probe_eval_shape(
        {"fail_passed": False, "fail_feedback": "weak", "fail_hint": ""},
        ["fail"])
    assert set(out) == {"fail"}
    # Extra/unknown keys (ungraded sides) tolerated + ignored.
    out = llm.validate_probe_eval_shape(
        {"why_passed": True, "why_feedback": "ok",
         "fail_passed": True, "fail_feedback": "ungraded, ignored",
         "extra": "x"}, ["why"])
    assert set(out) == {"why"}


def test_validate_probe_eval_shape_coercions_and_guardrail():
    ground = "the exact stored endpoint explanation wording for the probe"
    grounds = {"why": ground, "fail": ground}
    # String verdicts coerced (true-style); missing feedback coerced per side.
    out = llm.validate_probe_eval_shape(
        {"why_passed": "true",
         "fail_passed": "false"},
        ["why", "fail"], grounds)
    assert out["why"]["passed"] is True and out["why"]["hint"] == ""
    assert out["why"]["feedback"] == llm._L5_MISSING_FEEDBACK_PASS
    assert out["fail"]["passed"] is False
    assert out["fail"]["feedback"] == llm._L5_MISSING_FEEDBACK_FAIL
    assert out["fail"]["hint"] == llm._L5_GENERIC_HINT_FAIL
    # Numeric verdicts coerce; pass forces hint ''; unknown string fails closed.
    out = llm.validate_probe_eval_shape(
        {"why_passed": 1, "why_feedback": "  ok  ", "why_hint": "noise",
         "fail_passed": "maybe", "fail_feedback": "no",
         "fail_hint": "urn"},
        ["why", "fail"], grounds)
    assert out["why"]["passed"] is True and out["why"]["feedback"] == "ok"
    assert out["why"]["hint"] == ""
    assert out["fail"]["passed"] is False and out["fail"]["hint"] == "urn"
    # G-guardrail: a fail hint echoing the endpoint ground is replaced.
    out = llm.validate_probe_eval_shape(
        {"fail_passed": False, "fail_feedback": "no",
         "fail_hint": "try: the exact stored endpoint explanation wording "
                      "for the probe"},
        ["fail"], grounds)
    assert out["fail"]["hint"] == llm._L5_GENERIC_HINT_FAIL
    # Feedback/hint clips (mirror the P4 coercion housekeeping).
    out = llm.validate_probe_eval_shape(
        {"why_passed": False, "why_feedback": "f" * 900,
         "why_hint": "h" * 400}, ["why"], grounds)
    assert len(out["why"]["feedback"]) == 800
    assert len(out["why"]["hint"]) == 300


def test_validate_probe_eval_shape_structural_raises():
    bads = [
        "nonsense", 5, ["not", "a", "dict"], {"probe": "wrapped no dict"},
        {},                                     # missing both verdicts
        {"why_passed": True},                   # missing fail verdict
        {"why_feedback": "no verdict key"},
    ]
    for bad in bads:
        with pytest.raises(ValueError):
            llm.validate_probe_eval_shape(bad, ["why", "fail"])
    with pytest.raises(ValueError):
        llm.validate_probe_eval_shape({"why_feedback": "no verdict"}, ["why"])
    with pytest.raises(ValueError):
        llm.validate_probe_eval_shape({"fail_passed": True}, [])


# ---- caps (S5-G4) ----

def test_s5_caps():
    assert llm._max_tokens(shape="p5") == llm.GROQ_MAX_TOKENS_PROBE == 400
    assert llm._max_tokens(shape="p4") == llm.GROQ_MAX_TOKENS_EVAL == 450
    assert llm._max_tokens(shape="p3") == llm.GROQ_MAX_TOKENS_SCENARIO
    assert llm._max_tokens(extract=True) == llm.GROQ_MAX_TOKENS_EXTRACT
    assert llm._max_tokens() == llm.GROQ_MAX_TOKENS  # legacy flag intact


# ---- keyless: frozen stub labels + no leak ----

def test_l5_probe_keyless_labels_and_no_leak():
    u = mk_user("proK")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")])
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    assert j["mode"] == "stub" and j["model"] == "stub"
    assert "Demo mode (stubbed)" in j["warning"]
    assert "fallback_reason" not in j  # reason never travels (S7)
    # Six-field shape, locked flow intact (`why_passed` frozen key).
    assert j["why_passed"] is True and j["fail_passed"] is True
    assert "(stub-grounded)" in j["why_feedback"]
    assert j["progress"]["bright"] == 1 and j["progress"]["pct"] == 33  # n=3
    assert j["done"] is False and j["phase2_ready"] is False
    # Trail one row per attempt (§9): both answers + per-side feedback.
    rows = [t for t in store.list_trail(s["id"]) if t["stage"] == "L5"]
    assert len(rows) == 1 and rows[0]["link_id"] == lid
    payload = json.loads(rows[0]["payload"])
    assert payload["why_answer"] == "why answer"
    assert payload["why_passed"] is True
    assert payload["fail_feedback"]


# ---- live (mocked chain): one call, prompt shape, lanes, labels ----

def test_l5_probe_live_one_call_both_sides(monkeypatch):
    u = mk_user("proL")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls))
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    # Labels name the actually-served (first keyed) link.
    assert j["mode"] == "live" and j["model"] == "qwen/qwen3.8-27b"
    assert "fallback_reason" not in j and "warning" not in j
    # ONE P5 call: object mode at the p5 cap, owned lanes only.
    assert len(calls) == 1
    c = calls[0]
    assert c["model"] == "qwen/qwen3.8-27b"
    assert c["system"] == llm.P5_SYSTEM
    assert c["kwargs"].get("json_mode") is True
    assert c["kwargs"].get("max_tokens") == llm.GROQ_MAX_TOKENS_PROBE
    assert 'GRADED_SIDES: ["why", "fail"]' in c["user"]
    assert "- why: why answer" in c["user"] and "- fail: fail answer" in c["user"]
    assert "stored explanation for m0" in c["user"]  # server-resolved ground
    assert "user_id" not in c["user"] and "session" not in c["user"].lower()
    # Model verified both sides -> link bright, progress advances.
    assert j["why_passed"] is True and j["fail_passed"] is True
    assert j["progress"]["bright"] == 1


def test_l5_probe_blue_involved_joins_and_prefix_enforced_once(monkeypatch):
    u = mk_user("proB")
    s = mk_session(u["id"])
    # Blue endpoint in the cycle: m1(m0-b1-m1?) — pick ids so b1 links in.
    start_l5(s["id"], u["id"], [main_row("m0"), blue_row("b1"),
                                main_row("m2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls))
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    p5s = [c for c in calls if c["system"] == llm.P5_SYSTEM]
    assert len(p5s) == 1
    prompt = p5s[0]["user"]
    # S5-G1: the blue lane joined with the USER TEXT as its ground.
    assert "[BLUE: user_added" in prompt
    assert "pages user-defined" in prompt
    assert "user note" in prompt
    # Non-blue endpoint grounded from the doc lanes.
    assert "stored explanation for m0" in prompt
    # G8: feedback WITHOUT the model prefix is enforced app-side exactly once.
    assert j["why_feedback"].startswith(llm.P4_BLUE_PREFIX)
    assert j["why_feedback"].count(llm.P4_BLUE_PREFIX) == 1
    assert j["fail_feedback"].startswith(llm.P4_BLUE_PREFIX)
    assert j["mode"] == "live"


def test_l5_probe_blue_prefix_already_present_not_doubled(monkeypatch):
    u = mk_user("proB2")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), blue_row("b1"),
                                main_row("m2")])
    force_live(monkeypatch)
    already = llm.P4_BLUE_PREFIX + " consistent with your own definition."
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(
        calls, spec={"why": {"feedback": already},
                     "fail": {"feedback": already}}))
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    assert j["why_feedback"] == already  # enforced prefix is idempotent
    assert j["fail_feedback"] == already


def test_l5_probe_custom_edge_same_prompts(monkeypatch):
    u = mk_user("proC")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")],
             edge_types=["causes", "custom rel", "leads to"])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls))
    # The custom edge is in the dict probe: find link with edge_type custom.
    st = client.get(f"/api/sessions/{s['id']}/l5/status",
                    params={"user_id": u["id"]}).json()
    lid = next(L["id"] for L in st["links"] if L["edge_type"] == "custom rel")
    j = submit_probe(s, u["id"], lid)
    c = [c for c in calls if c["system"] == llm.P5_SYSTEM][0]
    # Locks §5: custom edges ride the byte-same prompts — only the label
    # line differs; grading + shape are identical.
    assert "EDGE: " in c["user"] and "custom rel" in c["user"]
    assert 'GRADED_SIDES: ["why", "fail"]' in c["user"]
    assert j["mode"] == "live"


def test_l5_probe_live_fail_stays_live(monkeypatch):
    u = mk_user("proF")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    spec = {"why": {"passed": False, "feedback": "No mechanism named."},
            "fail": {"passed": False, "feedback": "Not a boundary.",
                     "hint": "Give a concrete case."}}
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls, spec))
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    # A valid live fail is a live fail — never replaced by the lenient stub.
    assert j["mode"] == "live" and "warning" not in j
    assert j["why_passed"] is False and j["why_hint"] == (
        llm._L5_GENERIC_HINT_WHY)  # missing hint -> one generic nudge
    assert j["fail_passed"] is False and j["fail_hint"] == "Give a concrete case."
    assert j["progress"]["bright"] == 0 and j["progress"]["pct"] == 0
    rows = [t for t in store.list_trail(s["id"]) if t["stage"] == "L5"]
    assert json.loads(rows[0]["payload"])["why_passed"] is False


def test_l5_probe_chain_advance_groq_429_to_deepseek(monkeypatch):
    u = mk_user("proAdv")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1")])
    assert s["id"] and store.get_session(s["id"])["stage"] == "L5"
    force_live(monkeypatch, deepseek=True)
    calls: list[str] = []

    def flaky(model, system, user, *a, **k):
        calls.append(model)
        if model == "qwen/qwen3.8-27b":
            raise RuntimeError("HTTP 429 quota exceeded")
        return _probe_json(user)

    monkeypatch.setattr(llm, "_llm_generate", flaky)
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    # The stumble never reaches a stub while the paid link is keyed.
    assert j["mode"] == "live" and j["model"] == "deepseek-flash"
    assert "fallback_reason" not in j
    assert calls == ["qwen/qwen3.8-27b", "deepseek-flash"]


def test_l5_probe_all_fail_stub_and_unkeyed_skip(monkeypatch, caplog):
    u = mk_user("proStub")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1")])
    force_live(monkeypatch)  # only the free link keyed
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", failing_fake(calls))
    lid = probe_needed(s, u["id"])
    j = submit_probe(s, u["id"], lid)
    # Both sides dead -> lenient stub lanes answer; demo keeps moving.
    assert j["mode"] == "stub" and j["model"] == "stub"
    assert "Demo mode (stubbed)" in j["warning"]
    assert j["why_passed"] is True and j["fail_passed"] is True
    assert "(stub-grounded)" in j["why_feedback"]
    assert "fallback_reason" not in j
    reason = next(r.getMessage() for r in caplog.records
                  if "l5 probe: mode=stub reason=" in r.getMessage())
    assert "qwen/qwen3.8-27b: RuntimeError" in reason
    assert "unkeyed links skipped: deepseek-flash" in reason
    # One attempt per link; the unkeyed link was skipped, not attempted.
    assert [c["model"] for c in calls] == ["qwen/qwen3.8-27b"]


# ---- S5-G2: locked-side lanes + frozen pass; S5-G7a: rules ----

def test_l5_probe_locked_side_lane_exclusion_and_frozen_pass(monkeypatch):
    u = mk_user("proLK")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    # First attempt passes `why` only.
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls, spec={
        "why": {"passed": True, "feedback": "Mechanism named."},
        "fail": {"passed": False, "feedback": "No boundary.",
                 "hint": "Add a case."}}))
    lid = probe_needed(s, u["id"])
    j1 = submit_probe(s, u["id"], lid)
    assert j1["why_passed"] is True and j1["fail_passed"] is False
    assert j1["progress"]["bright"] == 0  # brighten needs BOTH green
    calls.clear()
    # Retry: the locked why side is excluded from the call (never re-graded).
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(
        calls, spec={"fail": {"passed": True, "feedback": "Case named."}}))
    j2 = submit_probe(s, u["id"], lid, why="rewritten why anyway",
                      fail="rewritten fail answer")
    p5 = [c for c in calls if c["system"] == llm.P5_SYSTEM]
    assert len(p5) == 1
    assert 'GRADED_SIDES: ["fail"]' in p5[0]["user"]
    assert "- fail: rewritten fail answer" in p5[0]["user"]
    assert "- why:" not in p5[0]["user"].split("ANSWERS", 1)[1]
    # The frozen side returns a locked pass; the link brightens only now.
    assert j2["why_passed"] is True
    assert j2["why_feedback"] == llm.P5_LOCKED_FEEDBACK
    assert j2["why_hint"] == ""
    assert j2["fail_passed"] is True and j2["progress"]["bright"] == 1
    # Trail keeps one row per attempt with both answers (route keeps both
    # boxes required; lane exclusion is prompt-side only).
    rows = [t for t in store.list_trail(s["id"]) if t["stage"] == "L5"]
    assert len(rows) == 2
    assert json.loads(rows[-1]["payload"])["why_answer"] == "rewritten why anyway"


def test_l5_probe_both_locked_mode_rules_zero_calls(monkeypatch):
    u = mk_user("proR")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1"),
                                main_row("m2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls))
    lid = probe_needed(s, u["id"])
    submit_probe(s, u["id"], lid)          # both sides pass -> link bright
    assert len(calls) == 1
    calls.clear()
    # S5-G7a: a resubmit of a fully lock-passed link needs zero model calls.
    j = submit_probe(s, u["id"], lid)
    assert j["mode"] == "rules" and j["model"] == "rules"
    assert "fallback_reason" not in j and "warning" not in j
    assert j["why_feedback"] == llm.P5_LOCKED_FEEDBACK
    assert j["fail_passed"] is True and len(calls) == 0
    # Still only one of three links bright — L5 not complete, stage holds.
    assert j["progress"]["bright"] == 1
    assert store.get_session(s["id"])["stage"] == "L5"


# ---- route gates + ownership ----

def test_l5_route_gates_membership_and_answers():
    u = mk_user("gateL5")
    s = mk_session(u["id"])
    sid = s["id"]
    start_l5(sid, u["id"], [main_row("m0"), main_row("m1"), main_row("m2")])
    lid = probe_needed(s, u["id"])
    # Missing answers -> 400 (both boxes required; trail never touched).
    assert client.post(f"/api/sessions/{sid}/l5/probe",
                       params={"user_id": u["id"]},
                       json={"link_id": lid, "why_answer": "  ",
                             "fail_answer": "x"}
                       ).status_code == 400
    assert client.post(f"/api/sessions/{sid}/l5/probe",
                       params={"user_id": u["id"]},
                       json={"link_id": lid, "why_answer": "x",
                             "fail_answer": ""}
                       ).status_code == 400
    # Crafted link ids are not in the entry-fixed target set -> 400, no trail.
    base = len([t for t in store.list_trail(sid) if t["stage"] == "L5"])
    r = client.post(f"/api/sessions/{sid}/l5/probe",
                    params={"user_id": u["id"]},
                    json={"link_id": "l-fake", "why_answer": "w",
                          "fail_answer": "f"})
    assert r.status_code == 400
    assert r.json()["detail"] == "link not in current L5 target set"
    with pytest.raises(KeyError):
        store.probe_submit(sid, "l-fake", "w", "f",
                           {"why_passed": True, "fail_passed": True})
    assert len([t for t in store.list_trail(sid)
                if t["stage"] == "L5"]) == base
    # Stage gate: probing outside L5 (here: rolled back to L4) -> 400.
    store.set_stage(sid, "L4")
    assert client.post(f"/api/sessions/{sid}/l5/probe",
                       params={"user_id": u["id"]},
                       json={"link_id": lid, "why_answer": "w",
                             "fail_answer": "f"}
                       ).status_code == 400


def test_l5_with_status_ownership_and_keyerror():
    u = mk_user("ownL5")
    v = mk_user("ownL5V")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("m0"), main_row("m1")])
    # Defense-in-depth: wrong owner fails closed even on direct calls.
    with pytest.raises(PermissionError):
        llm.probe_link_with_status(s["id"], "l-x", "w", "f", user_id=v["id"])
    with pytest.raises(KeyError):
        llm.probe_link_with_status(s["id"], "l-nope", "w", "f",
                                   user_id=u["id"])
    # Frozen §8 wrapper exit unchanged (keyless stub shape + labels).
    lid = store.list_links(s["id"])[0]["id"]
    ev = llm.probe_link(s["id"], lid, "why", "fail")
    assert set(ev) == {"why_passed", "why_feedback", "why_hint",
                       "fail_passed", "fail_feedback", "fail_hint"}
    assert ev["why_passed"] is True and "(stub-grounded)" in ev["why_feedback"]
    # Empty answers still obey the frozen stub wording (no route 400 here).
    ev = llm.probe_link(s["id"], lid, "", "")
    assert ev["why_passed"] is False and "State what must be true" in ev["why_feedback"]


# ---- full runs (DONE gate, S5-G7) ----

def test_l5_keyless_full_run_seed_phase1_phase2_ready():
    u = mk_user("runK")
    s = mk_session(u["id"])
    mains = [c for c in llm.load_seed_concepts() if c.get("kind") == "main"]
    start_l5(s["id"], u["id"], mains)  # 6 mains incl. blue c6 -> 6 links
    sid = s["id"]
    st = store.l5_status(sid)
    assert st["n"] == 6 and not st["complete"]
    # Six lenient stub probes (both sides pass each time) -> Phase2 modal.
    for _ in range(6):
        lid = probe_needed(s, u["id"])
        j = submit_probe(s, u["id"], lid)
        assert j["mode"] == "stub" and "Demo mode (stubbed)" in j["warning"]
    final = store.l5_status(sid)
    assert final["complete"] and final["bright"] == final["n"] == 6
    assert store.get_session(sid)["stage"] == "Phase2"
    rows = [t for t in store.list_trail(sid) if t["stage"] == "L5"]
    assert len(rows) == 6  # one row per (link) attempt at 6/6


def test_l5_mocked_live_full_run_seed_phase1(monkeypatch):
    u = mk_user("runL")
    s = mk_session(u["id"])
    mains = [c for c in llm.load_seed_concepts() if c.get("kind") == "main"]
    start_l5(s["id"], u["id"], mains)  # 6 mains incl. blue c6
    sid = s["id"]
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", probe_obeying_fake(calls))
    # 6 links, each ONE P5 call, each brightens; after the last -> Phase2.
    phase2_seen = False
    for _ in range(6):
        lid = probe_needed(s, u["id"])
        j = submit_probe(s, u["id"], lid)
        assert j["mode"] == "live" and j["model"] == "qwen/qwen3.8-27b"
        if j["phase2_ready"]:
            phase2_seen = True
    assert phase2_seen
    assert store.l5_status(sid)["complete"]
    assert store.get_session(sid)["stage"] == "Phase2"
    p5_calls = [c for c in calls if c["system"] == llm.P5_SYSTEM]
    assert len(p5_calls) == 6  # ONE call per link, no retries, no batching
    # Blue c6 INVOLVED links graded with the user text as ground (S5-G1).
    assert any("[BLUE: user_added" in c["user"] for c in p5_calls)
    # Trail: one row per attempt; blue-involved feedbacks carry the enforced
    # prefix exactly once.
    rows = [t for t in store.list_trail(sid) if t["stage"] == "L5"]
    assert len(rows) == 6
    blue_feedbacks = [json.loads(t["payload"])
                      for t in rows
                      if json.loads(t["payload"])["why_feedback"].startswith(
                          llm.P4_BLUE_PREFIX)]
    assert blue_feedbacks and all(
        fb["why_feedback"].count(llm.P4_BLUE_PREFIX) == 1
        for fb in blue_feedbacks)


# ---- live tests skip without keys ----

@pytest.mark.skipif(not config.is_llm_live(), reason="no LLM key (keyless CI skip)")
def test_live_l5_probe_shape():
    u = mk_user("liveL5")
    s = mk_session(u["id"])
    start_l5(s["id"], u["id"], [main_row("solo-a", title="Store",
                                         explanation_text=(
                                             "A store learns patterns from "
                                             "past orders instead of "
                                             "hand-written rules."),
                                         pages=[5]),
                                main_row("solo-b", title="Baskets",
                                         explanation_text=(
                                             "Unlabelled baskets can reveal "
                                             "shopper groups through their "
                                             "co-purchase patterns."),
                                         pages=[9])])
    lid = probe_needed(s, u["id"])
    r = client.post(f"/api/sessions/{s['id']}/l5/probe",
                    params={"user_id": u["id"]},
                    json={"link_id": lid,
                          "why_answer": "It can learn patterns from order "
                                        "history, so predictions come from "
                                        "the stored data instead of fixed "
                                        "rules.",
                          "fail_answer": "It fails when orders stop "
                                         "representing shoppers, e.g. "
                                         "seasonal trips outside the "
                                         "loyalty programme."})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] in ("live", "stub")  # 429 bursts degrade to the stub
    assert j["why_passed"] in (True, False) and j["fail_passed"] in (True, False)
    if j["why_passed"] is False:
        assert j["why_hint"].strip()
    if j["fail_passed"] is False:
        assert j["fail_hint"].strip()
