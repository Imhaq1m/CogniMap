"""CogniMap — model-agnostic LLM interfaces (Locks §8) + seed-backed stubs.

Locked signatures (Locks §8 — stubs MUST keep these so a model swap needs no
UI change):
  parse_pdf(file) -> {markdown, figures[]}  # alias to parse.parse_pdf
  extract_concepts(markdown, figures) -> ConceptsJSON
  evaluate_paraphrase(session_id, concept_id, paraphrase)
  generate_scenario(chunk_ids 1-3, context_markdown)
  evaluate_scenario(session_id, scenario_id, selections)
  probe_link(session_id, link_id, why_answer, fail_answer)

Server-side resolution: stubs resolve explanation/scenario/edge from the
session store by owned (session_id, concept/link/scenario_id) — never raw
client text. Route-level ownership (sessions.user_id == requesting user,
see main._owned + store.require_owned_session) runs before every call, so the
session_id arriving here is already an owned session; resolvers below then
scope all reads to that session (multi-session isolation, doc-scope
grounding). Real model implementations MUST repeat the ownership check
first (see Steps_Locks §8).
"""
from __future__ import annotations

import json
import os

from . import store

SEED_PATH = os.path.join(os.path.dirname(__file__), "seed.json")


def load_seed_concepts() -> list[dict]:
    with open(SEED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "concepts" in data:
        return data["concepts"]
    return data if isinstance(data, list) else []


# 1. extract_concepts(markdown, figures) -> ConceptsJSON (§1 shape + Q4)
def extract_concepts(markdown: str, figures: list[dict] | None = None) -> list[dict]:
    """Stub wired to figures (Locks §1 Q4 + §8).

    Demo-blue note (Locks §1 provenance): seed.json c6 is a demo-blue row
    (source=user_added, explanation_text="", explanation_source="user") —
    the correct two-step Confirm shape, included in the stub seed so the
    blue bypass / plausibility-check path demos without keys. A real
    extractor outputs extracted rows only; user_added rows are created at
    Confirm (Phase-1) / Phase-2 Confirm, never by the extractor.

    Starts from seed JSON, then links LlamaParse figures to concepts via
    diagram_refs/diagram_description: a figure attaches to concepts whose
    pages overlap the figure page (doc-scope grounding). Seed rows already
    carry diagram_refs for fig-p5-1/fig-p13-1; this keeps them only when the
    figure id is present in the input, drops stale refs, and fills
    image_path/caption defaults from the figure meta. Guarantees the
    figure→diagram_refs/diagram_description path is exercised (M10).
    """
    _ = markdown
    figs = list(figures or [])
    by_id = {str(f.get("diagram_id", "")): f for f in figs if f.get("diagram_id")}
    seed = load_seed_concepts()
    out: list[dict] = []
    for c in seed:
        d = dict(c)
        refs = list(d.get("diagram_refs") or [])
        # Keep only refs whose figure was actually parsed (no phantom links).
        kept = [r for r in refs if str(r.get("diagram_id", "")) in by_id]
        # If the seed row has no refs but a figure shares a page, attach it
        # (Q4: extractor reads figures + outputs diagram_description).
        if not kept:
            pages = set(d.get("pages") or [])
            for f in figs:
                if f.get("page") in pages:
                    kept.append(
                        {"diagram_id": str(f["diagram_id"]), "page": int(f["page"])}
                    )
                    break
        d["diagram_refs"] = kept
        if kept and not (d.get("diagram_description") or "").strip():
            first = by_id.get(str(kept[0].get("diagram_id", "")), {})
            cap = str(first.get("caption") or "").strip()
            if cap:
                d["diagram_description"] = cap
        # Normalise figure image_path convention for the UI (§0).
        for r in d["diagram_refs"]:
            fid = str(r.get("diagram_id", ""))
            if fid and fid in by_id and not by_id[fid].get("image_path"):
                by_id[fid]["image_path"] = f"/static/diagrams/{fid}.png"
        out.append(d)
    return out


# 2. evaluate_paraphrase(session_id, concept_id, paraphrase) -> {passed,...}
def evaluate_paraphrase(session_id: str, concept_id: str, paraphrase: str,
                        user_id: int | None = None) -> dict:
    """Stub (Locks §8): resolves the concept server-side by owned ids.

    Ownership (§0+§8): when user_id is given, verifies
    sessions.user_id == user_id first (route already gates via _owned;
    this is defense-in-depth so every §8 call verifies, never session_id
    alone). Blue (user_added): bypass LLM — non-empty user text passes with
    plausibility-check feedback, never doc-cited. Extracted: lenient stub —
    non-empty paraphrase passes; the real model grounds against the resolved
    explanation_text/type/pages/diagram_description.
    """
    if user_id is not None:
        store.require_owned_session(session_id, user_id)
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    c = concepts.get((concept_id or "").strip())
    if not c:
        raise KeyError("unknown concept for this session")
    text = (paraphrase or "").strip()
    if c.get("source") == "user_added":
        # Locks §9: blue rows carry user explanation + warning-ack + saved
        # flag, NO accuracy/originality (bypass, no LLM).
        ok = bool(text)
        return {
            "passed": ok,
            "feedback": "Saved — user-defined, plausibility check, not doc-cited."
            if ok else "Write your explanation first.",
            "hint": "" if ok else "State what your concept means in your own words.",
            "warning_ack": "Ensure your self-defined concept is accurate — not verified against source.",
            "user_explanation": text,
            "saved": ok,
        }
    ok = bool(text)
    # m2 (Details L1-2 §4): lenient-but-plausible copy, still tagged as
    # stub-grounded (no signature/UI change — swap model later with no UI change).
    return {
        "passed": ok,  # skeleton leniency: non-empty passes; real model checks grounding
        "accuracy": "Good coverage of the source meaning (stub-grounded check).",
        "originality": "Reads in your own words (stub-grounded check).",
        "feedback": "Nice — captures the core meaning in your own words (stub-grounded, doc scope)."
        if ok else "Explain the concept in your own words, tied to the cited pages (stub-grounded).",
        "hint": "" if ok else "Restate the explanation in your own words, tying to the cited pages (stub-grounded hint).",
    }


# 3. generate_scenario(chunk_ids, context_markdown) -> {scenario_id, text, concept_ids}
# Locks §3+§8: app owns partition, passes exact chunk; LLM verbalizes only.
# (No session scoping needed — chunk + background context are app-supplied.)
def generate_scenario(chunk_ids: list[str], context_markdown: str = "") -> dict:
    _ = context_markdown
    pick = list(chunk_ids or [])[:3]  # cap 3; 2+2 remainder + n=1 exception handled by caller
    return {
        "scenario_id": "stub-scn-1",
        "text": "stub scenario covering: " + ", ".join(pick),
        "concept_ids": pick,
    }


# 4. evaluate_scenario(session_id, scenario_id, selections)
#    -> {results, missed_ids, scenario_cleared} (Locks §3 tier 4 + §8)
def evaluate_scenario(
    session_id: str,
    scenario_id: str,
    selections: list[dict] | None = None,
    user_id: int | None = None,
) -> dict:
    """Stub (Locks §8): resolves scenario + concepts server-side by owned ids.

    Ownership (§0+§8): when user_id is given, verifies sessions.user_id ==
    user_id first. Raw client-supplied required sets are NEVER trusted —
    `required` always resolves from the owned scenario row (legacy
    scenario_concept_ids param removed per §8 MUST NOT trust raw client
    text). results = one entry per submitted selection (tier 1:
    selected-but-not-required fails as "not related"); missed_ids =
    required-but-unselected; cleared = missed empty AND no wrong picks AND
    every required selected+passed. Blue-involved selections resolve user
    text as ground with plausibility feedback. Lock-passed inputs are
    excluded by the caller (main keeps the locked set); the caller's strict
    clear additionally requires locked coverage — see main.api_l3_submit.
    """
    if user_id is not None:
        store.require_owned_session(session_id, user_id)
    rows = {x["id"]: x for x in store.list_scenarios(session_id)}
    scn = rows.get((scenario_id or "").strip())
    if not scn:
        raise KeyError("unknown scenario for this session")
    required = list(scn.get("concept_ids") or [])
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    sels = selections or []
    got = {s.get("concept_id", "") for s in sels}
    missed = [c for c in required if c not in got]
    results = []
    for s in sels:
        cid = s.get("concept_id", "")
        just = (s.get("justification") or "").strip()
        if cid not in required:
            # Tier 1: wrong concept selected → flag + explain why not related.
            results.append(
                {
                    "concept_id": cid,
                    "passed": False,
                    "feedback": f"Concept {cid} is not related to this scenario.",
                    "hint": "Uncheck it, or replace with a concept the scenario facts support.",
                }
            )
            continue
        c = concepts.get(cid) or {}
        blue = c.get("source") == "user_added"
        ok = bool(just)
        if blue:
            # m2: plausible blue copy, still plausibility-tagged (no signature change).
            results.append(
                {
                    "concept_id": cid,
                    "passed": ok,
                    "feedback": "user-defined — plausibility check, not doc-cited."
                    if ok else "Justify how your concept applies to the scenario.",
                    "hint": "" if ok else "Tie your justification to specific scenario facts (stub-grounded hint).",
                }
            )
        else:
            # m2 (Details L3 §4): plausible tier copy, still stub-grounded.
            results.append(
                {
                    "concept_id": cid,
                    "passed": ok,
                    "feedback": "Applies here — justification supported by the scenario facts (stub-grounded)."
                    if ok else "Explain how this concept applies to the scenario facts (stub-grounded).",
                    "hint": "" if ok else "Tie your justification to specific scenario facts (stub-grounded hint).",
                }
            )
    required_ok = all(
        next((r["passed"] for r in results if r["concept_id"] == cid), False)
        for cid in required
    )
    wrong = any(r["concept_id"] not in required for r in results)
    cleared = (not missed) and (not wrong) and required_ok and bool(required)
    return {"results": results, "missed_ids": missed, "scenario_cleared": cleared}


# 5. probe_link(session_id, link_id, why_answer, fail_answer) -> 6-field
#    (Locks §5+§8+§9: per-side feedback+hints)
def probe_link(
    session_id: str,
    link_id: str,
    why_answer: str = "",
    fail_answer: str = "",
    user_id: int | None = None,
) -> dict:
    """Stub (Locks §8): resolves the edge + endpoint explanations by owned ids.

    Ownership (§0+§8): when user_id is given, verifies sessions.user_id ==
    user_id first. Raw client-supplied edge dicts are NEVER trusted (legacy
    link param removed) — edge always resolves from the owned links table.
    Blue-involved links (either endpoint source=user_added) resolve the
    user-supplied text as ground with plausibility feedback, never doc-cited.
    """
    if user_id is not None:
        store.require_owned_session(session_id, user_id)
    links = {x["id"]: x for x in store.list_links(session_id)}
    edge = links.get((link_id or "").strip())
    if not edge:
        raise KeyError("unknown link for this session")
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    a = concepts.get(edge.get("a_id", "")) or {}
    b = concepts.get(edge.get("b_id", "")) or {}
    blue = a.get("source") == "user_added" or b.get("source") == "user_added"
    tag = "user-defined — plausibility check, not doc-cited. " if blue else ""
    why_ok = bool((why_answer or "").strip())
    fail_ok = bool((fail_answer or "").strip())
    # m2 (Details L5 §3): plausible per-side copy, still stub-grounded;
    # blue tag preserved ("not doc-cited") with no signature/UI change.
    return {
        "why_passed": why_ok,
        "why_feedback": f"{tag}Holds — explains what must be true for this link (stub-grounded)."
        if why_ok else f"{tag}State what must be true for this link to hold (stub-grounded).",
        "why_hint": "" if why_ok else "Name the mechanism that makes the link hold (stub-grounded hint).",
        "fail_passed": fail_ok,
        "fail_feedback": f"{tag}Boundary named — says when the link breaks (stub-grounded)."
        if fail_ok else f"{tag}Name a condition where the link breaks (stub-grounded).",
        "fail_hint": "" if fail_ok else "Give a concrete case where the relationship fails (stub-grounded hint).",
    }
