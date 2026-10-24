"""S3 integration tests (Integration_Tracker S3 / S8 ride-along).

Keyless CI stays green: frozen stub asserts always run; the live chain is
exercised through a routing-faithful mock of _llm_generate (a chain-shaped
model: P3 echoes CHUNK_IDS from the prompt, P4 grades every JUSTIFIED
lane), while transport-level request shapes stay covered in
test_provider_swap.py. Covers the S3 grill ledger (G1-G8):

- P3 verbalize-only prompts (titles never printed), id-echo validation,
  MAINS_BACKGROUND Phase-2 lanes, caps p3=350 / p4=450, P1 trim 12000->8000;
- P4 ONE merged call per submit with tier-1 wrong picks / empty
  justifications pre-filtered (zero LLM spend anywhere a rule can decide),
  blue user_added lanes joining the call (G2'/G8: ground = the user's own
  saved explanation, "user-defined — plausibility check, not doc-cited"
  prefix enforced app-side exactly once, no page citations);
- mode=rules for pure rule-based submits, live fail stays live, whole-chain
  failure -> lenient labelled stub (never 502), unkeyed-link skip in
  fallback_reason, model labels per actually-served link;
- strict clear math + lock-passed retry (locked rows never re-graded),
  keyless seed clears in ceil(n/3), Phase-2 full run with mains background;
- ownership + stage gates; live skipif smoke when real keys exist.
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

SCENARIO_TEXT = (
    "A small grocery chain wants dependable predictions from its loyalty-"
    "card history, so the team teaches a system with months of labelled "
    "purchases, then explores unlabelled baskets to find shopper groups; "
    "the running system keeps adapting as new receipts arrive."
)


def mk_user(prefix="s3"):
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


def start_l3(sid, uid, concepts):
    """Confirm + blue two-step fills + L1-2 passes, then stage -> L3."""
    store.confirm_selection(sid, uid, concepts)
    for c in concepts:
        if c.get("source") == "user_added":
            store.set_user_explanation(sid, c["concept_id"], "user note")
    for c in concepts:
        store.record_l12_attempt(sid, uid, c["concept_id"],
                                 f"para {c['concept_id']}", True, "a", "o",
                                 "fb", "")
    store.set_stage(sid, "L3")
    return [c["concept_id"] for c in concepts]


def force_live(monkeypatch, deepseek=False):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key-not-logged")
    if deepseek:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key-not-logged")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)  # default mixed chain


SCN_CTX = "CHUNK_CONCEPTS (id | title | type | pages | explanation | diagram):"


def p3_from_prompt(user: str) -> str:
    """A routing-faithful P3 fake: echo CHUNK_IDS verbatim out of the prompt."""
    chunk = json.loads(user.split("CHUNK_IDS: ")[1].split("\n")[0])
    return json.dumps({"text": SCENARIO_TEXT, "concept_ids": chunk})


def p4_pass_from_prompt(user: str) -> str:
    """A routing-faithful P4 fake: grades every JUSTIFIED lane passed=true.

    Blue feedback arrives WITHOUT the prefix so the app-side enforcement is
    genuinely exercised.
    """
    results = []
    lanes = user.split("JUSTIFIED_CONCEPTS:\n")[1].splitlines()
    for line in lanes:
        line = line.strip()
        if not line.startswith("- concept_id: "):
            continue
        cid = line.split("|")[0].replace("- concept_id: ", "").strip()
        results.append({"concept_id": cid, "passed": True,
                        "feedback": "Applies to the scenario facts.",
                        "hint": ""})
    return json.dumps({"results": results})


def obeying_fake(calls: list[dict], p4_results: list[dict] | None = None):
    """Mock llm._llm_generate: an obedient mixed-chain model (G1/G3/G8)."""
    fixed = list(p4_results or [])

    def fake(model, system, user, *a, **k):
        calls.append({"model": model, "system": system, "user": user,
                      "kwargs": k})
        if system == llm.P3_SYSTEM:
            return p3_from_prompt(user)
        if fixed:
            r = list(fixed)
            fixed.clear()
        else:
            r = p4_results if p4_results is not None else None
        if r is not None:
            return json.dumps({"results": r})
        return p4_pass_from_prompt(user)

    return fake


def failing_fake(calls: list[dict], exc=None):
    def fake(model, system, user, *a, **k):
        if calls is None:
            raise AssertionError("no LLM call was expected")
        calls.append({"model": model, "system": system, "user": user,
                      "kwargs": k})
        raise exc or RuntimeError(f"HTTP 429 (fake, {model})")
    return fake


# ---- prompts (S9 draft as implemented) ----

def test_p3_prompt_rubric_locked_wording():
    assert "Verbalize ONLY the given concepts" in llm.P3_SYSTEM
    assert "echo the chunk ids" in llm.P3_SYSTEM
    assert "no external knowledge" in llm.P3_SYSTEM
    # G1: titles never printed verbatim; describe the situation instead.
    assert "do NOT print any supplied concept title verbatim" in llm.P3_SYSTEM
    assert '{"text": string, "concept_ids": [ids]}' in llm.P3_RULES
    assert "Echo CHUNK_IDS exactly" in llm.P3_RULES
    assert "never invent/add/drop concepts" in llm.P3_RULES
    assert "<= ~420 chars" in llm.P3_RULES


def test_p4_prompt_rubric_locked_wording():
    # G3/G6: trust the model verdict within the anti-recital rubric.
    assert "a recital of the REFERENCE or scenario wording" in llm.P4_RULES
    assert "never applies it to the scenario" in llm.P4_RULES
    assert "no external knowledge" in llm.P4_SYSTEM
    # G2'/G8: blue ground = the user's own definition, lenient, no pages.
    assert "the user's own definition" in llm.P4_SYSTEM
    assert "do not cite pages" in llm.P4_SYSTEM
    prefix = "user-defined — plausibility check, not doc-cited"
    assert prefix in llm.P4_SYSTEM and prefix in llm.P4_RULES
    # Hint policy mirrors P2.
    assert "never states or paraphrases the reference answer" in llm.P4_SYSTEM
    assert "on pass hint must" in llm.P4_SYSTEM
    assert "ONE short sentence (~140 chars)" in llm.P4_SYSTEM
    assert '{"results":[{"concept_id","passed","feedback","hint"}]}' in llm.P4_RULES


def test_build_p3_user_fields_and_mains_background():
    chunk = ["c1", "c2"]
    rows = [
        {"id": "c1", "title": "Machine Learning", "explanation_type": "definition",
         "pages": [5, 6], "explanation_text": "ML text", "diagram_description": "D1"},
        {"id": "c2", "title": "Applications", "explanation_type": "definition",
         "pages": [9], "explanation_text": "App text", "diagram_description": ""},
    ]
    mains = [{"id": "m0", "title": "Main flow", "explanation_text": "mains bg"}]
    out = llm.build_p3_user(chunk, rows, mains)
    assert out.startswith(llm.P3_RULES)  # stable prefix first
    assert 'CHUNK_IDS: ["c1", "c2"]' in out
    assert "- c1 | Machine Learning | definition | pages [5, 6] | ML text | D1" in out
    assert "- c2 | Applications | definition | pages [9] | App text | " in out
    assert "MAINS_BACKGROUND (display-only" in out
    assert "mains bg" in out
    # Without mains_rows the block is absent (Phase-1 shape).
    assert "MAINS_BACKGROUND" not in llm.build_p3_user(chunk, rows)
    # Bounded: never any pretty-printed store rows or client text.
    assert "diagram_refs" not in out.split("\n\n", 1)[1]


def test_build_p4_user_lanes_blue_marker_and_clips():
    scn = "scenario text"
    lanes = [
        {"concept_id": "c1", "blue": False,
         "concept": {"title": "Machine Learning", "explanation_type": "definition",
                     "pages": [5, 6], "explanation_text": "ML ground",
                     "diagram_description": "D"},
         "justification": "just one"},
        {"concept_id": "c4", "blue": True,
         "concept": {"title": "Deployment (my map)", "explanation_type": "definition",
                     "pages": [], "explanation_text": "user note",
                     "diagram_description": ""},
         "justification": "j" * 1300},
    ]
    out = llm.build_p4_user(scn, lanes)
    assert out.startswith(llm.P4_RULES)
    assert "SCENARIO:\nscenario text" in out
    assert "- c1 | Machine Learning | definition | pages [5, 6] | ML ground | D" in out
    # G2': blue ground is the user's own text; pages field is user-defined.
    assert ("- c4 | Deployment (my map) | definition | pages user-defined | "
            "user note |  [BLUE: user_added") in out
    assert "[BLUE: user_added" in out and "never cite pages for this row" in out
    assert "concept_id: c1 | justification: just one" in out
    assert "concept_id: c4 | justification: " + ("j" * 1200) in out
    assert ("j" * 1201) not in out  # justification clipped at 1200


# ---- validators (LLM API output validation) ----

def test_validate_scenario_text_shape_accepts():
    chunk = ["c1", "c2"]
    text = llm.validate_scenario_text_shape(
        {"text": "  A grounded situation.  ", "concept_ids": ["c2", "c1"]},
        chunk)
    assert text == "A grounded situation."
    # Optional {"scenario": {...}} wrapper tolerated (S1 wrapper precedent).
    text = llm.validate_scenario_text_shape(
        {"scenario": {"text": "wrapped", "concept_ids": ["c1", "c2"]}}, chunk)
    assert text == "wrapped"


def test_validate_scenario_text_shape_rejects():
    chunk = ["c1", "c2"]
    bads = [
        "not a dict",
        {"text": "", "concept_ids": ["c1", "c2"]},
        {"text": "ok"},                                   # ids missing
        {"text": "ok", "concept_ids": []},
        {"text": "ok", "concept_ids": ["c1"]},            # fewer
        {"text": "ok", "concept_ids": ["c1", "c2", "c3"]},  # extra
        {"text": "ok", "concept_ids": ["c1", "c1"]},      # dup
        {"text": "ok", "concept_ids": ["c1", "c9"]},      # invented
        {"text": "ok", "concept_ids": ["c1", ""], "": 0},  # blank id
    ]
    for bad in bads:
        with pytest.raises(ValueError):
            llm.validate_scenario_text_shape(bad, chunk)


def test_validate_eval_results_shape_full():
    lanes = ["c1", "b4"]
    grounds = {"c1": "stored explanation for c1 extras-long"}
    data = {"results": [
        {"concept_id": "c1", "passed": True, "feedback": "Applies.", "hint": ""},
        {"concept_id": "b4", "passed": False, "feedback": "Off-scenario.",
         "hint": ""},
    ]}
    out = llm.validate_eval_results_shape(data, lanes, grounds)
    assert [r["concept_id"] for r in out] == lanes
    assert out[0]["passed"] is True and out[0]["hint"] == ""
    assert out[1]["passed"] is False


def test_validate_eval_results_shape_coercions_and_guardrail():
    grounds = {"c1": "the exact stored reference explanation wording here"}
    # Missing entries (empty results envelope) -> generic fail + nudge,
    # stays live (no raise). A dict with NO results list at all is garbage
    # and must advance the chain (structural test below).
    out = llm.validate_eval_results_shape({"results": []}, ["c1", "c2"], grounds)
    assert out[0] == {"concept_id": "c1", "passed": False,
                      "feedback": "Explain how this concept applies to the "
                                  "scenario facts.",
                      "hint": "Tie your justification to specific scenario facts."}
    # Unknown / extra / duplicated ids dropped; string verdicts coerced.
    data = {"results": [
        {"concept_id": "cX", "passed": True, "feedback": "x", "hint": ""},
        {"concept_id": "c1", "passed": "true", "feedback": "  ok  ", "hint": "n"},
        {"concept_id": "c2", "passed": "false", "feedback": "bad", "hint": ""},
    ]}
    out = llm.validate_eval_results_shape(data, ["c1", "c2"], grounds)
    assert out[0]["passed"] is True and out[0]["feedback"] == "ok"
    assert out[1]["passed"] is False
    assert out[1]["hint"] == "Tie your justification to specific scenario facts."
    # Empty feedback coerced per verdict; pass hint "".
    out = llm.validate_eval_results_shape(
        {"results": [{"concept_id": "c1", "passed": True, "feedback": "",
                      "hint": "noise"},
                     {"concept_id": "c2", "passed": False, "feedback": "",
                      "hint": ""}]},
        ["c1", "c2"], grounds)
    assert out[0]["feedback"] == ("Applies here — justification supported by "
                                  "the scenario facts.")
    assert out[0]["hint"] == ""
    assert out[1]["hint"] == "Tie your justification to specific scenario facts."
    # G6 hint guardrail: a fail hint that echoes the ground answer is replaced.
    out = llm.validate_eval_results_shape(
        {"results": [{"concept_id": "c1", "passed": False, "feedback": "no",
                      "hint": "try: the exact stored reference explanation "
                              "wording here"}]},
        ["c1"], grounds)
    assert out[0]["hint"] == "Tie your justification to specific scenario facts."
    # Blue user-text guardrail mirrors the same behaviour via grounds.
    out = llm.validate_eval_results_shape(
        {"results": [{"concept_id": "c1", "passed": False, "feedback": "no",
                      "hint": "echo " + grounds["c1"]}]},
        ["c1"], grounds)
    assert out[0]["hint"] == "Tie your justification to specific scenario facts."
    # Text clip 2000 on P3.
    assert len(llm.validate_scenario_text_shape(
        {"text": "t" * 3000, "concept_ids": ["c1"]}, ["c1"])) == 2000


def test_validate_eval_results_shape_structural_raises():
    for bad in ("nonsense", 5, ["not", "a", "dict"],
                {"results": "not a list"}, {"results": {}}, {}):
        with pytest.raises(ValueError):
            llm.validate_eval_results_shape(bad, ["c1"])


# ---- caps + P1 trim (G5) ----

def test_s3_caps_and_p1_trim():
    assert llm._max_tokens(shape="p3") == llm.GROQ_MAX_TOKENS_SCENARIO == 350
    assert llm._max_tokens(shape="p4") == llm.GROQ_MAX_TOKENS_EVAL == 450
    assert llm._max_tokens(shape="p1") == llm.GROQ_MAX_TOKENS_EXTRACT
    assert llm._max_tokens(shape="p2") == llm.GROQ_MAX_TOKENS
    # Legacy flag stays compatible (provider-swap test untouched).
    assert llm._max_tokens(extract=True) == llm.GROQ_MAX_TOKENS_EXTRACT
    assert llm._max_tokens() == llm.GROQ_MAX_TOKENS
    prompt = llm.build_p1_user("X" * 9000, [])
    assert ("X" * 8000) in prompt and ("X" * 8001) not in prompt  # G5 trim


# ---- generate: keyless + live mocked + chain semantics ----

def test_l3_generate_keyless_labels_and_no_leak():
    u = mk_user("genK")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]})
    assert g.status_code == 200
    g = g.json()
    assert g["mode"] == "stub" and g["model"] == "stub"
    assert "Demo mode (stubbed)" in g["warning"]
    assert "concept_ids" not in g, "required set leaked to client"
    assert g["text"].startswith("stub scenario covering:")
    assert sorted(g["pool"]) == ["c1", "c2"]
    g2 = client.post(f"/api/sessions/{s['id']}/l3/generate",
                     params={"user_id": u["id"]}).json()
    assert g2["id"] == g["id"] and g2["text"] == g["text"]  # active resume


def test_l3_generate_live_mocked(monkeypatch):
    u = mk_user("genL")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]}).json()
    # Labels name the first KEYED link; ids never leak; the APP's chunk stored.
    assert g["mode"] == "live" and g["model"] == "qwen/qwen3.8-27b"
    assert "fallback_reason" not in g
    assert "warning" not in g
    assert "concept_ids" not in g
    assert g["text"] == SCENARIO_TEXT
    assert "T-c1" not in g["text"] and "T-c2" not in g["text"]  # G1 in practice
    store_row = store.list_scenarios(s["id"])[0]
    assert store_row["concept_ids"] == ["c1", "c2"]
    assert store_row["text"] == SCENARIO_TEXT
    # One object-mode call at the P3 cap, server-resolved rows only.
    assert len(calls) == 1
    c = calls[0]
    assert c["model"] == "qwen/qwen3.8-27b"
    assert c["system"] == llm.P3_SYSTEM
    assert c["kwargs"].get("json_mode") is True
    assert c["kwargs"].get("max_tokens") == llm.GROQ_MAX_TOKENS_SCENARIO
    assert "CHUNK_IDS: [\"c1\", \"c2\"]" in c["user"]
    assert "stored explanation for c1" in c["user"]
    assert "user_id" not in c["user"] and "session" not in c["user"].lower()


def test_l3_generate_chain_advance_groq_429_to_deepseek(monkeypatch):
    u = mk_user("genAdv")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1")])
    force_live(monkeypatch, deepseek=True)
    calls: list[dict] = []

    def flaky(model, system, user, *a, **k):
        calls.append(model)
        if model == "qwen/qwen3.8-27b":
            raise RuntimeError("HTTP 429 quota exceeded")
        return p3_from_prompt(user)

    monkeypatch.setattr(llm, "_llm_generate", flaky)
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]}).json()
    # The stumble never reaches a stub while the paid link is keyed: same
    # submit, second vendor, mode=live, chain-echo-validated.
    assert g["mode"] == "live" and g["model"] == "deepseek-flash"
    assert "fallback_reason" not in g
    assert calls == ["qwen/qwen3.8-27b", "deepseek-flash"]


def test_l3_generate_all_fail_stub_and_unkeyed_skip(monkeypatch, caplog):
    u = mk_user("genStub")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1")])
    force_live(monkeypatch)  # only the free link keyed
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", failing_fake(calls))
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]}).json()
    assert g["mode"] == "stub" and g["model"] == "stub"
    assert "Demo mode (stubbed)" in g["warning"]
    assert g["text"].startswith("stub scenario covering: c1")
    assert g["progress"]["total"] == 1
    # fallback_reason travels to NOBODY (S7): mode/model/warning only; the
    # reason is a server-side log line with no vendor keys.
    assert "fallback_reason" not in g
    reason = next(r.getMessage() for r in caplog.records
                  if "l3 generate: mode=stub reason=" in r.getMessage())
    assert "qwen/qwen3.8-27b: RuntimeError" in reason
    # One attempt per link; the unkeyed link was skipped, not attempted.
    assert [c["model"] for c in calls] == ["qwen/qwen3.8-27b"]
    assert "unkeyed links skipped: deepseek-flash" in reason


# ---- submit: keyless + pre-chain rules + live merged call ----

def _gen_first(s, uid):
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": uid})
    assert g.status_code == 200, g.text
    return g.json()


def test_l3_submit_keyless_labels_and_tiers_unchanged():
    u = mk_user("subK")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    g = _gen_first(s, u["id"])
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "why c1"}]})
    j = j.json()
    assert j["mode"] == "stub" and j["model"] == "stub"
    assert "Demo mode (stubbed)" in j["warning"]
    assert j["missed_ids"] == ["c2"] and j["scenario_cleared"] is False
    row = next(r for r in j["results"] if r["concept_id"] == "c1")
    assert row["passed"] is True and "(stub-grounded)" in row["feedback"]


def test_l3_submit_live_one_merged_call_and_tier1_rule_based(monkeypatch):
    u = mk_user("subL")
    s = mk_session(u["id"])
    ids = start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2"),
                                      main_row("c3"), blue_row("c4")])
    assert len(ids) == 4  # n=4 -> 2+2 remainder: [c1, c2] then [c3, c4]
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    g = _gen_first(s, u["id"])
    assert len(calls) == 1  # P3 done
    pool = set(g["pool"])
    wrong_pick = next(cid for cid in pool if cid not in ("c1", "c2"))
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "why one"},
                        {"concept_id": "c2", "justification": "why two"},
                        {"concept_id": wrong_pick, "justification": "unrelated"},
                    ]})
    assert j.status_code == 200, j.text
    j = j.json()
    # EXACTLY one merged P4 call — even with three rows submitted.
    p4 = [c for c in calls if c["system"] == llm.P4_SYSTEM]
    assert len(p4) == 1
    assert p4[0]["kwargs"].get("json_mode") is True
    assert p4[0]["kwargs"].get("max_tokens") == llm.GROQ_MAX_TOKENS_EVAL
    # Tier-1 wrong pick (blue or not) never reaches the model (G4/G-carries).
    assert f"concept_id: {wrong_pick}" not in p4[0]["user"]
    assert "concept_id: c1" in p4[0]["user"] and "concept_id: c2" in p4[0]["user"]
    # Results merge: two live entries + one rule-based tier-1 flag.
    assert j["mode"] == "live" and j["model"] == "qwen/qwen3.8-27b"
    assert j["scenario_cleared"] is False  # wrong pick blocks clear
    row = next(r for r in j["results"] if r["concept_id"] == wrong_pick)
    assert row["passed"] is False and "not related" in row["feedback"]
    assert j["missed_ids"] == []


def test_l3_submit_blue_lane_joins_and_prefix_enforced_once(monkeypatch):
    u = mk_user("subB")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2"),
                                main_row("c3"), blue_row("c4")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    # Reach the second chunk [c3, c4] by clearing [c1, c2] first.
    g = _gen_first(s, u["id"])
    client.post(f"/api/sessions/{s['id']}/l3/submit", params={"user_id": u["id"]},
                json={"scenario_id": g["id"], "selections": [
                    {"concept_id": "c1", "justification": "why one"},
                    {"concept_id": "c2", "justification": "why two"}]})
    g2 = _gen_first(s, u["id"])
    assert g2["id"] != g["id"]
    req = next(x for x in store.list_scenarios(s["id"])
               if not x["cleared"])["concept_ids"]
    assert req == ["c3", "c4"]  # blue c4 in the chunk (Locks §3: Blues included)
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g2["id"], "selections": [
                        {"concept_id": "c3", "justification": "plain"},
                        {"concept_id": "c4", "justification": "justifies it"},
                    ]})
    j = j.json()
    p4 = [c for c in calls if c["system"] == llm.P4_SYSTEM]
    assert len(p4) == 2  # ONE merged call per submit: chunk1 then the blue chunk2
    merged = p4[-1]
    # G2': the BLUE lane joined the single call, grounded in the USER TEXT.
    assert "concept_id: c4" in merged["user"]
    assert "user note" in merged["user"]          # user's saved explanation
    assert "[BLUE: user_added" in merged["user"]  # rubric marker
    # G8: the blue lane's pages field is user-defined — no page citation.
    c4_line = next(l for l in merged["user"].splitlines() if l.startswith("- c4 "))
    assert "user-defined" in c4_line and "pages [5]" not in c4_line
    # The mock returned no prefix — the app enforces it exactly once (G8).
    row = next(r for r in j["results"] if r["concept_id"] == "c4")
    assert row["feedback"] == (
        llm.P4_BLUE_PREFIX + " Applies to the scenario facts.")
    assert j["mode"] == "live" and j["scenario_cleared"] is True
    assert j["locked_passed"] == ["c3", "c4"]
    # Strict clear + advance.
    st = store.l3_status(s["id"])
    assert st["complete"] and st["cleared"] == 2 and st["pct"] == 100


def test_l3_submit_blue_prefix_already_present_not_doubled(monkeypatch):
    u = mk_user("subB2")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    already = llm.P4_BLUE_PREFIX + " coherent with your own definition."
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(
        [], p4_results=[{"concept_id": "c1", "passed": True,
                         "feedback": already, "hint": ""}]))
    g = _gen_first(s, u["id"])
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "mine"}]})
    row = next(r for r in j.json()["results"] if r["concept_id"] == "c1")
    assert row["feedback"] == already  # enforced prefix is idempotent


def test_l3_submit_tier1_only_zero_calls_mode_rules(monkeypatch):
    u = mk_user("subR")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2"),
                                main_row("c3"), blue_row("c4")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    g = _gen_first(s, u["id"])  # required [c1, c2]
    calls.clear()
    # Pure tier-1 submit: only wrong picks (incl. blue c4) — no omissions due
    # to... actually required ids ARE missed too; still zero LLM calls.
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c3", "justification": "why"},
                        {"concept_id": "c4", "justification": "why blue"},
                    ]})
    j = j.json()
    # G4: zero spend — mode=rules, model=rules.
    assert j["mode"] == "rules" and j["model"] == "rules"
    assert "fallback_reason" not in j
    assert len(calls) == 0, "no LLM call may happen on a pure rule-based submit"
    assert j["missed_ids"] == ["c1", "c2"]
    assert j["scenario_cleared"] is False
    by = {r["concept_id"]: r for r in j["results"]}
    assert by["c4"]["passed"] is False and "not related" in by["c4"]["feedback"]
    assert by["c3"]["passed"] is False and "not related" in by["c3"]["feedback"]
    # Trail written for every decision point (reviewer gate §9): two tier-1
    # flags + two omission flags, with no LLM call at all.
    rows = [t for t in store.list_trail(s["id"]) if t["stage"] == "L3"]
    assert len(rows) == 4
    by_c = {t["concept_id"]: json.loads(t["payload"]) for t in rows}
    assert by_c["c4"]["feedback"].startswith("Concept c4 is not related")
    assert by_c["c1"]["omitted"] is True and by_c["c2"]["omitted"] is True


def test_l3_submit_empty_justifications_prefiltered(monkeypatch):
    u = mk_user("subE")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    g = _gen_first(s, u["id"])
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "   "},
                        {"concept_id": "c2", "justification": "good why"},
                    ]})
    j = j.json()
    p4 = [c for c in calls if c["system"] == llm.P4_SYSTEM]
    assert len(p4) == 1  # the empty lane never rode the call (G7)
    assert "concept_id: c1" not in p4[0]["user"]
    assert "concept_id: c2 " in p4[0]["user"]
    row1 = next(r for r in j["results"] if r["concept_id"] == "c1")
    assert row1["passed"] is False
    # Live rule copy is honest — no "(stub-grounded)" tag under mode=live.
    assert row1["feedback"] == "Explain how this concept applies to the scenario facts."
    assert "(stub-grounded)" not in row1["feedback"]
    assert row1["hint"] == "Tie your justification to specific scenario facts."
    assert j["mode"] == "live" and j["scenario_cleared"] is False


def test_l3_submit_live_fail_stays_live(monkeypatch):
    u = mk_user("subF")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(
        [], p4_results=[
            {"concept_id": "c1", "passed": False,
             "feedback": "Doesn't tie to the story.", "hint": "It misses the point."},
            {"concept_id": "c2", "passed": False, "feedback": "No facts named."},
        ]))
    g = _gen_first(s, u["id"])
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "why one"},
                        {"concept_id": "c2", "justification": "why two"},
                    ]}).json()
    # A valid live fail is a live fail — never replaced by the lenient stub.
    assert j["mode"] == "live" and "warning" not in j
    by = {r["concept_id"]: r for r in j["results"]}
    assert by["c1"]["passed"] is False and by["c1"]["hint"] == "It misses the point."
    assert by["c2"]["hint"] == "Tie your justification to specific scenario facts."
    assert j["scenario_cleared"] is False
    st = store.l3_status(s["id"])
    assert st["cleared"] == 0 and st["pct"] == 0  # failed attempts never advance


def test_l3_submit_chain_dead_lenient_stub_clears(monkeypatch, caplog):
    u = mk_user("subD")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", failing_fake(calls))
    g = _gen_first(s, u["id"])  # generate also stubbed + labelled
    assert g["mode"] == "stub"
    calls.clear()
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "c1", "justification": "why one"},
                        {"concept_id": "c2", "justification": "why two"},
                    ]}).json()
    # Both links dead -> lenient stub lanes answer; demo keeps moving (D).
    assert j["mode"] == "stub" and j["model"] == "stub"
    assert "Demo mode (stubbed)" in j["warning"]
    assert "fallback_reason" not in j  # reason never travels (S7)
    by = {r["concept_id"]: r for r in j["results"]}
    assert by["c1"]["passed"] is True and by["c2"]["passed"] is True
    assert j["scenario_cleared"] is True  # ceil math intact via the stub
    assert store.l3_status(s["id"])["cleared"] == 1
    reason = next(r.getMessage() for r in caplog.records
                  if "l3 submit: mode=stub reason=" in r.getMessage())
    assert "qwen/qwen3.8-27b: RuntimeError" in reason
    assert "unkeyed links skipped: deepseek-flash" in reason


def test_l3_lock_passed_retry_live_locked_never_regraded(monkeypatch):
    u = mk_user("subLK")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls, p4_results=[
        {"concept_id": "c1", "passed": True, "feedback": "Good.", "hint": ""},
        {"concept_id": "c2", "passed": False,
         "feedback": "No fact named.", "hint": "Name a fact."}
    ]))
    g = _gen_first(s, u["id"])
    j1 = client.post(f"/api/sessions/{s['id']}/l3/submit",
                     params={"user_id": u["id"]},
                     json={"scenario_id": g["id"], "selections": [
                         {"concept_id": "c1", "justification": "why one"},
                         {"concept_id": "c2", "justification": "why two"},
                     ]}).json()
    assert j1["locked_passed"] == ["c1"]
    calls.clear()
    fixed = [{"concept_id": "c2", "passed": True, "feedback": "Fixed.", "hint": ""}]
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(
        calls, p4_results=list(fixed)))
    j2 = client.post(f"/api/sessions/{s['id']}/l3/submit",
                     params={"user_id": u["id"]},
                     json={"scenario_id": g["id"], "selections": [
                         {"concept_id": "c1", "justification": "editing the text ..."},
                         {"concept_id": "c2", "justification": "why two fixed"},
                     ]}).json()
    p4 = [c for c in calls if c["system"] == llm.P4_SYSTEM]
    assert len(p4) == 1
    # Route excludes locked c1 — retry never re-spend the token (G-rule).
    assert "concept_id: c1" not in p4[0]["user"]
    assert j2["scenario_cleared"] is True
    locked_row = next(r for r in j2["results"] if r["concept_id"] == "c1")
    assert locked_row["passed"] is True and locked_row["locked"] is True
    assert "Locked green from earlier pass." in locked_row["feedback"]


# ---- full runs (DONE gate) ----

def test_l3_mocked_live_full_run_seed_phase1(monkeypatch):
    u = mk_user("runL")
    s = mk_session(u["id"])
    mains = [c for c in llm.load_seed_concepts() if c.get("kind") == "main"]
    ids = start_l3(s["id"], u["id"], mains)  # 6 mains incl. blue c6
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    sid = s["id"]
    for _ in range(2):  # ceil(6/3) = 2 scenarios
        g = _gen_first(s, u["id"])
        assert g["mode"] == "live"
        req = next(x for x in store.list_scenarios(sid)
                   if not x["cleared"])["concept_ids"]
        j = client.post(f"/api/sessions/{sid}/l3/submit",
                        params={"user_id": u["id"]},
                        json={"scenario_id": g["id"],
                              "selections": [{"concept_id": c,
                                              "justification": f"why {c}"}
                                             for c in req]})
        assert j.status_code == 200, j.text
        j = j.json()
        assert j["mode"] == "live" and j["scenario_cleared"] is True
    st = store.l3_status(sid)
    assert st["complete"] and st["cleared"] == 2 and st["pct"] == 100
    assert store.get_session(sid)["stage"] == "L4"
    p3_calls = [c for c in calls if c["system"] == llm.P3_SYSTEM]
    p4_calls = [c for c in calls if c["system"] == llm.P4_SYSTEM]
    assert len(p3_calls) == 2 and len(p4_calls) == 2
    # The blue c6 lane JOINED the merged call for its chunk (G2') and the
    # enforced prefix carried into the stored response rows.
    assert any("concept_id: c6" in c["user"] and "[BLUE: user_added" in c["user"]
               for c in p4_calls)
    l3rows = [t for t in store.list_trail(sid) if t["stage"] == "L3"]
    assert len(l3rows) == 6  # one row per (scenario, concept)
    blue_rows = [json.loads(t["payload"]) for t in l3rows
                 if t["concept_id"] == "c6"]
    assert blue_rows and blue_rows[0]["feedback"].startswith(llm.P4_BLUE_PREFIX)


def test_l3_mocked_live_full_run_phase2_mains_background(monkeypatch):
    u = mk_user("runP2")
    s = mk_session(u["id"])
    sid = s["id"]
    mains = [main_row(f"m{i}", title=f"Main {i}") for i in range(6)]
    store.confirm_selection(sid, u["id"], mains)
    for i in range(6):
        store.record_l12_attempt(sid, u["id"], f"m{i}", f"para m{i}", True,
                                 "a", "o", "fb", "")
    store.set_stage(sid, "Phase2")
    store.confirm_phase2(sid, u["id"], [
        {"concept_id": f"s{i}", "title": f"Sub {i}", "kind": "sub",
         "parent_id": "m0"} for i in range(6)])
    store.set_stage(sid, "L3")
    assert store.l3_counted_ids(sid) == ("phase2", [f"s{i}" for i in range(6)])
    force_live(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(llm, "_llm_generate", obeying_fake(calls))
    for _ in range(2):  # ceil(6/3) from subs only
        g = _gen_first(s, u["id"])
        req = next(x for x in store.list_scenarios(sid)
                   if not x["cleared"])["concept_ids"]
        j = client.post(f"/api/sessions/{sid}/l3/submit",
                        params={"user_id": u["id"]},
                        json={"scenario_id": g["id"],
                              "selections": [{"concept_id": c,
                                              "justification": f"why {c}"}
                                             for c in req]})
        assert j.status_code == 200, j.text
        assert j.json()["scenario_cleared"] is True
    # Phase-2 lock: mains ride along display-only, never in any chunk lane.
    p3 = [c for c in calls if c["system"] == llm.P3_SYSTEM]
    assert len(p3) == 2
    assert "MAINS_BACKGROUND (display-only" in p3[0]["user"]
    assert "stored explanation for m0" in p3[0]["user"]
    assert "CHUNK_IDS: [\"s0\", \"s1\", \"s2\"]" in p3[0]["user"]
    assert all("CHUNK_IDS:" in c["user"] and "m0" not in
               json.loads(c["user"].split("CHUNK_IDS: ")[1].split("\n")[0])
               for c in p3)  # mains never enter scenario_concept_ids (§3+§7)
    assert store.l3_status(sid)["complete"]


# ---- frozen §8 function + ownership/stage gates ----

def test_l3_with_status_ownership_and_keyerror():
    u = mk_user("ownL3")
    v = mk_user("ownL3V")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("c1"), main_row("c2")])
    chunk = ["c1", "c2"]
    # Defense-in-depth: wrong owner fails closed even on direct calls.
    with pytest.raises(PermissionError):
        llm.evaluate_scenario_with_status(s["id"], "scn-x", [],
                                          user_id=v["id"])
    with pytest.raises(KeyError):
        llm.evaluate_scenario_with_status(s["id"], "scn-nope", [],
                                          user_id=u["id"])
    # Frozen wrapper exit unchanged (keyless stub shape).
    with pytest.raises(KeyError):
        llm.evaluate_scenario(s["id"], "scn-nope", [])
    # Ownership reaches generate lanes too: the chunk is app-supplied.
    st = llm.generate_scenario_with_status(chunk)
    assert st["mode"] == "stub" and "concept_ids" in st["scenario"]


def test_l3_route_stage_gates_and_unknown_scenario():
    u = mk_user("gateL3")
    s = mk_session(u["id"])
    sid = s["id"]
    concepts = [main_row("c1"), main_row("c2")]
    store.confirm_selection(sid, u["id"], concepts)  # single Confirm — concepts lock
    # Stage gate: no generate/submit before L1-2 completes.
    assert client.post(f"/api/sessions/{sid}/l3/generate",
                       params={"user_id": u["id"]}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/l3/submit",
                       params={"user_id": u["id"]},
                       json={"scenario_id": "nope", "selections": []}
                       ).status_code == 400
    for c in concepts:
        store.record_l12_attempt(sid, u["id"], c["concept_id"],
                                 f"para {c['concept_id']}", True, "a", "o",
                                 "fb", "")
    store.set_stage(sid, "L3")
    g = _gen_first(s, u["id"])
    req = store.list_scenarios(sid)[0]["concept_ids"]
    client.post(f"/api/sessions/{sid}/l3/submit", params={"user_id": u["id"]},
                json={"scenario_id": g["id"],
                      "selections": [{"concept_id": c, "justification": "why"}
                                     for c in req]})
    # Cleared scenario cannot resubmit; unknown scenario 400s.
    assert client.post(f"/api/sessions/{sid}/l3/submit",
                       params={"user_id": u["id"]},
                       json={"scenario_id": g["id"], "selections": []}
                       ).status_code == 400
    assert client.post(f"/api/sessions/{sid}/l3/submit",
                       params={"user_id": u["id"]},
                       json={"scenario_id": "scn-nope", "selections": []}
                       ).status_code == 400


# ---- live tests skip without keys ----

@pytest.mark.skipif(not config.is_llm_live(), reason="no LLM key (keyless CI skip)")
def test_live_l3_generate_and_submit_shape():
    u = mk_user("liveL3")
    s = mk_session(u["id"])
    start_l3(s["id"], u["id"], [main_row("solo", title="Machine Learning",
                                         explanation_text=(
                                             "Machine learning lets systems "
                                             "learn patterns from data "
                                             "instead of fixed rules."),
                                         pages=[5, 6])])
    g = client.post(f"/api/sessions/{s['id']}/l3/generate",
                    params={"user_id": u["id"]})
    assert g.status_code == 200, g.text
    g = g.json()
    assert g["mode"] in ("live", "stub")  # 429 bursts degrade to the stub
    assert "concept_ids" not in g and g["text"].strip()
    if g["mode"] == "live":
        assert store.list_scenarios(s["id"])[0]["concept_ids"] == ["solo"]
    j = client.post(f"/api/sessions/{s['id']}/l3/submit",
                    params={"user_id": u["id"]},
                    json={"scenario_id": g["id"], "selections": [
                        {"concept_id": "solo",
                         "justification": "The store learns from past orders "
                                          "instead of using hand-written rules."}
                    ]})
    assert j.status_code == 200, j.text
    j = j.json()
    assert j["mode"] in ("live", "stub")
    row = next(r for r in j["results"] if r["concept_id"] == "solo")
    assert row["passed"] in (True, False)
    if row["passed"] is False:
        assert row["hint"].strip()
    assert j["scenario_cleared"] in (True, False)
