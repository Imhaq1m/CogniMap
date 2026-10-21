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

S1 live (additive): extract_concepts tries Gemini chain
  gemini-3.8-flash -> gemini-3.7-flash -> gemini-3.6-flash -> stub
behind env flags (LLM_PROVIDER=gemini + GOOGLE_API_KEY). Keyless stays stub.
List return shape frozen; mode/model/fallback_reason travel out-of-band via
extract_concepts_with_status (routes use it for labelling, never 502).
S2 live (additive): evaluate_paraphrase uses the same chain with a balanced
rubric (accuracy + originality both pass; minor omissions allowed; hint is
one nudge, never the answer). Blue user_added rows stay a no-LLM bypass.
Result shape frozen; mode/model/fallback_reason travel out-of-band via
evaluate_paraphrase_with_status.
Prompt texts live in this module for the FYP write-up (S7).
"""
from __future__ import annotations

import json
import logging
import os

from . import config, store

log = logging.getLogger("cognimap.llm")

SEED_PATH = os.path.join(os.path.dirname(__file__), "seed.json")


def load_seed_concepts() -> list[dict]:
    with open(SEED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "concepts" in data:
        return data["concepts"]
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# S1 P1 prompts (S9 draft, model-agnostic JSON-only, stable-prefix-first for
# implicit caching: stable RULES/system first, variable MARKDOWN/FIGURES last).
# ---------------------------------------------------------------------------

P1_SYSTEM = (
    "Extract study concepts from course docs only, no external knowledge. "
    "Synthesize scope-grounded text when missing, mark generated + cite pages. "
    "If partial say partial. "
    "Output JSON list only. Each item MUST have: concept_id (unique string), "
    "title, kind (main|sub), parent_id (null for main, main concept_id for sub), "
    "source (always extracted — never user_added), explanation_type "
    "(definition|procedure|framework|principle), explanation_text (always "
    "non-empty; use only parsed markdown/figures, cite pages), "
    "explanation_source (extracted|generated), pages (list of ints, may be []), "
    "diagram_refs (list of {diagram_id, page} linked via page overlap with "
    "FIGURES_JSON), diagram_description (figure caption bridge, may be empty). "
    "Link figures via page overlap. Never output user_added rows."
)

P1_RULES = (
    "RULES: JSON list only. Fields: concept_id/title/kind:main|sub/parent_id/"
    "source:extracted/explanation_type/explanation_text/explanation_source:"
    "extracted|generated/pages/diagram_refs/diagram_description. "
    "Guardrail: use only parsed markdown/figures, no external knowledge, "
    "cite pages, if partial say partial."
)


def build_p1_user(markdown: str, figures: list[dict] | None) -> str:
    figs = figures or []
    # Truncate markdown to keep demo prompts bounded (full doc still sent when short).
    md = (markdown or "")[:12000]
    try:
        figs_json = json.dumps(
            [
                {
                    "diagram_id": f.get("diagram_id"),
                    "page": f.get("page"),
                    "caption": (f.get("caption") or "")[:300],
                }
                for f in figs
            ][:20]
        )
    except Exception:
        figs_json = "[]"
    return f"{P1_RULES}\n\nMARKDOWN:\n{md}\n\nFIGURES_JSON:\n{figs_json}"


# ---------------------------------------------------------------------------
# S2 P2 prompts (balanced leniency: accuracy + originality both gate the
# pass; minor omissions allowed; hint is one nudge, never the answer).
# Stable-prefix-first for implicit caching: RULES first, REFERENCE next,
# the variable STUDENT_PARAPHRASE last.
# ---------------------------------------------------------------------------

P2_ACCURACY_BANDS = ("Accurate", "Partly accurate", "Inaccurate")
P2_ORIGINALITY_BANDS = ("Own words", "Too close to source")

P2_SYSTEM = (
    "You are a lenient tutor grading a student's paraphrase of one course "
    "concept. Judge meaning over wording. Pass ONLY when BOTH hold: "
    "(1) accuracy is 'Accurate' — the core meaning is correct and nothing "
    "contradicts the reference; minor omissions are allowed; and (2) "
    "originality is 'Own words' — the student restructured the sentence and "
    "explained it in their own phrasing. Shared technical terms and short "
    "stock phrases are expected and do NOT make an answer too close. Mark "
    "'Too close to source' ONLY when the student copies most of the "
    "reference sentence nearly verbatim (same structure and wording "
    "throughout); when in doubt choose 'Own words'. Use only the supplied "
    "REFERENCE; no external knowledge. If the answer is partial, say what is "
    "missing without revealing the answer. Output one JSON object only with: "
    "passed (bool), accuracy (Accurate|Partly accurate|Inaccurate), "
    "originality (Own words|Too close to source), feedback (1-2 sentences), "
    "hint. passed MUST equal (accuracy == 'Accurate' AND originality == 'Own "
    "words'). On pass hint must be \"\". On fail hint is ONE short nudge "
    "that points at the missing idea or asks for own wording and NEVER "
    "states or paraphrases the reference answer."
)

P2_RULES = (
    "RULES: JSON object only. accuracy exactly one of Accurate|Partly "
    "accurate|Inaccurate. originality exactly one of Own words|Too close to "
    "source. Pass only when accuracy=Accurate and originality=Own words. "
    "Minor omissions are okay when the core meaning is right. Be lenient on "
    "originality: technical terms and short stock phrases are fine; only "
    "near-verbatim copying of most of the reference is Too close. feedback "
    "is 1-2 sentences, lenient, and never gives the answer. hint is empty on "
    "pass; on fail it is ONE nudge that never reveals the reference answer. "
    "Ground only in REFERENCE."
)


def _clip(value: object, limit: int) -> str:
    return str(value or "")[:limit]


def build_p2_user(concept: dict, paraphrase: str) -> str:
    """Build P2 user prompt from the server-resolved concept row.

    Grounding (§8): the caller must pass a row fetched by owned
    (session_id, concept_id). The only client-supplied text is the student
    paraphrase being graded.
    """
    pages = concept.get("pages") or []
    try:
        pages_json = json.dumps(pages)
    except Exception:
        pages_json = "[]"
    return (
        f"{P2_RULES}\n\n"
        f"REFERENCE_TITLE: {_clip(concept.get('title'), 300)}\n"
        f"REFERENCE_TYPE: {_clip(concept.get('explanation_type') or 'definition', 80)}\n"
        f"REFERENCE_SOURCE: {_clip(concept.get('explanation_source') or 'generated', 40)}\n"
        f"REFERENCE_PAGES: {_clip(pages_json, 300)}\n"
        f"REFERENCE_DIAGRAM: {_clip(concept.get('diagram_description'), 600)}\n"
        f"REFERENCE_EXPLANATION:\n{_clip(concept.get('explanation_text'), 4000)}\n\n"
        f"STUDENT_PARAPHRASE:\n{_clip(paraphrase, 4000)}"
    )


# ---------------------------------------------------------------------------
# Stub core (frozen behaviour, seed-grounded).
# ---------------------------------------------------------------------------

def _stub_extract_concepts(markdown: str, figures: list[dict] | None = None) -> list[dict]:
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


# ---------------------------------------------------------------------------
# S1 validation (strict shape check on live JSON).
# ---------------------------------------------------------------------------

_VALID_KINDS = {"main", "sub"}
_VALID_EXP_TYPES = {"definition", "procedure", "framework", "principle"}
_VALID_EXP_SRC = {"extracted", "generated"}


def validate_extract_shape(concepts: object) -> list[dict]:
    """Strict shape check (per supervisor-demo decision).

    Rules: list, ids unique non-empty, kind main|sub, parent integrity
    (main parent None, sub parent is a selected main), source MUST be
    extracted (never user_added from the extractor), explanation_text
    non-empty, explanation_source extracted|generated, pages list,
    diagram_refs list of {diagram_id, page}.
    Raises ValueError(reason) on any failure -> caller falls back to stub.
    """
    if not isinstance(concepts, list) or not concepts:
        raise ValueError("live JSON must be a non-empty list")
    seen: set[str] = set()
    mains: set[str] = set()
    for c in concepts:
        if not isinstance(c, dict):
            raise ValueError("live item must be an object")
        cid = str(c.get("concept_id") or c.get("id") or "").strip()
        if not cid:
            raise ValueError("live item missing concept_id")
        if cid in seen:
            raise ValueError(f"duplicate concept id: {cid}")
        seen.add(cid)
        if c.get("kind") not in _VALID_KINDS:
            raise ValueError(f"bad kind for {cid}")
        if c.get("kind") == "main":
            mains.add(cid)
        if not str(c.get("title") or "").strip():
            raise ValueError(f"missing title for {cid}")
        if c.get("source") != "extracted":
            raise ValueError(f"live extractor must output extracted only ({cid})")
        if c.get("explanation_type") not in _VALID_EXP_TYPES:
            raise ValueError(f"bad explanation_type for {cid}")
        if not str(c.get("explanation_text") or "").strip():
            raise ValueError(f"missing explanation_text for {cid}")
        if c.get("explanation_source") not in _VALID_EXP_SRC:
            raise ValueError(f"bad explanation_source for {cid}")
        pages = c.get("pages")
        if not isinstance(pages, list):
            raise ValueError(f"pages must be a list for {cid}")
        refs = c.get("diagram_refs")
        if refs is None:
            c["diagram_refs"] = []
        elif not isinstance(refs, list):
            raise ValueError(f"diagram_refs must be a list for {cid}")
        else:
            for r in refs:
                if not isinstance(r, dict) or not str(r.get("diagram_id") or "").strip():
                    raise ValueError(f"bad diagram_ref for {cid}")
        c.setdefault("diagram_description", "")
        c.setdefault("parent_id", None)
    # Parent integrity (second pass so forward refs work).
    for c in concepts:  # type: ignore[union-attr]
        cid = str(c.get("concept_id") or c.get("id") or "").strip()  # type: ignore[union-attr]
        if c.get("kind") == "sub":  # type: ignore[union-attr]
            parent = c.get("parent_id")  # type: ignore[union-attr]
            if not parent or parent not in mains:
                raise ValueError(f"sub {cid} needs a selected main parent")
        else:
            c["parent_id"] = None  # type: ignore[index]
    if not mains:
        raise ValueError("live JSON needs >=1 main (Confirm guard)")
    return concepts  # type: ignore[return-value]


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        # Remove ```json ... ``` fences.
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _gemini_generate(model: str, system: str, user: str, api_key: str, timeout_s: int) -> str:
    """One Gemini call. Raises on 429/5xx/network so the chain can advance."""
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
    finally:
        try:
            client.close()
        except Exception:
            pass
    _ = timeout_s
    text = getattr(resp, "text", "") or ""
    if not text.strip():
        raise ValueError(f"{model} returned empty response")
    return text


def extract_concepts_with_status(
    markdown: str, figures: list[dict] | None = None
) -> dict:
    """S1 live chain + labelled fallback (additive, never raises).

    Returns {concepts, mode: live|stub, model, fallback_reason}.
    Chain: LLM_MODELS order (default 3.8 -> 3.7 -> 3.6) -> stub.
    On 429/5xx/bad-JSON/validation fail, advance to next link; after all
    fail, seed-grounded stub. Never 502 in demo. Logs fallback_reason
    server-side without keys.
    """
    figs = list(figures or [])
    if not config.is_llm_live():
        concepts = _stub_extract_concepts(markdown, figs)
        reason = "stub-default (no LLM key)"
        log.info("extract: mode=stub reason=%s", reason)
        return {"concepts": concepts, "mode": "stub", "model": "stub", "fallback_reason": reason}
    api_key = config.get_google_key() or ""
    models = config.get_llm_models()
    user_prompt = build_p1_user(markdown, figs)
    last_reason = ""
    for model in models:
        try:
            log.info("extract: trying live model=%s", model)
            raw = _gemini_generate(model, P1_SYSTEM, user_prompt, api_key, config.LLM_TIMEOUT_S)
            cleaned = _strip_code_fences(raw)
            try:
                data = json.loads(cleaned)
            except Exception as e:
                last_reason = f"{model}: bad JSON ({type(e).__name__})"
                log.warning("extract: %s", last_reason)
                continue
            # Accept bare list or {concepts: [...]} wrapper.
            if isinstance(data, dict) and isinstance(data.get("concepts"), list):
                data = data["concepts"]
            try:
                concepts = validate_extract_shape(data)
            except ValueError as e:
                last_reason = f"{model}: validation failed ({e})"
                log.warning("extract: %s", last_reason)
                continue
            log.info("extract: live ok model=%s n=%d", model, len(concepts))
            return {"concepts": concepts, "mode": "live", "model": model, "fallback_reason": ""}
        except Exception as e:
            # 429/5xx/network/auth — advance the chain, never 502.
            last_reason = f"{model}: {type(e).__name__}: {str(e)[:200]}"
            log.warning("extract: %s", last_reason)
            continue
    concepts = _stub_extract_concepts(markdown, figs)
    reason = last_reason or "all live models failed — stub fallback"
    log.warning("extract: mode=stub reason=%s", reason)
    return {"concepts": concepts, "mode": "stub", "model": "stub", "fallback_reason": reason}


# 1. extract_concepts(markdown, figures) -> ConceptsJSON (§1 shape + Q4)
def extract_concepts(markdown: str, figures: list[dict] | None = None) -> list[dict]:
    """Frozen §8 signature: returns list only (labelling out-of-band).

    Live behind env flags; keyless/bad-key/bad-JSON always falls back to the
    seed-grounded stub so the supervisor demo never breaks. Routes needing
    mode/model/warning use extract_concepts_with_status.
    """
    return extract_concepts_with_status(markdown, figures)["concepts"]


def llm_status() -> dict:
    """Additive health fragment: {llm: live|stub, llm_model}."""
    return config.llm_status()


# 2. evaluate_paraphrase(session_id, concept_id, paraphrase) -> {passed,...}
# S2 live: balanced rubric (accuracy + originality), Gemini chain -> stub.
# The frozen §8 function returns the result only; mode/model/fallback_reason
# travel out-of-band via evaluate_paraphrase_with_status (route labelling).

_ACCURACY_ALIASES = {
    "accurate": "Accurate",
    "mostly accurate": "Accurate",
    "accurate with minor omissions": "Accurate",
    "partly accurate": "Partly accurate",
    "partially accurate": "Partly accurate",
    "partial": "Partly accurate",
    "inaccurate": "Inaccurate",
    "incorrect": "Inaccurate",
    "wrong": "Inaccurate",
}
_ORIGINALITY_ALIASES = {
    "own words": "Own words",
    "original": "Own words",
    "original wording": "Own words",
    "paraphrased": "Own words",
    "rephrased": "Own words",
    "too close to source": "Too close to source",
    "close to source": "Too close to source",
    "near verbatim": "Too close to source",
    "near-verbatim": "Too close to source",
    "copied": "Too close to source",
    "verbatim": "Too close to source",
}
_ACCURACY_LABELS = {
    "Accurate": "Accurate — core meaning preserved (minor gaps ok)",
    "Partly accurate": "Partly accurate — key idea missing or unclear",
    "Inaccurate": "Inaccurate — contradicts or misses the core meaning",
}
_ORIGINALITY_LABELS = {
    "Own words": "Own words — clearly rephrased",
    "Too close to source": "Too close to source — near-verbatim",
}


def _normalise_band(value: object, aliases: dict[str, str],
                    allowed: tuple[str, ...], field: str) -> str:
    raw = str(value or "").strip().strip('"').strip("'").rstrip(".").strip()
    key = " ".join(raw.lower().split())
    if key in aliases:
        return aliases[key]
    for band in allowed:
        if key == band.lower():
            return band
    raise ValueError(f"bad {field}: {value!r}")


def validate_paraphrase_eval_shape(data: object, reference: str = "") -> dict:
    """Strict shape + balanced pass gate on live P2 JSON.

    The app owns `passed`: it is derived from the two bands so a model cannot
    pass a near-verbatim answer or a partly-accurate one. A fail hint that
    echoes the reference answer is replaced with a generic nudge (hints must
    never give the answer). Raises ValueError(reason) -> caller advances the
    chain, then falls back to the lenient stub.
    """
    if not isinstance(data, dict):
        raise ValueError("live JSON must be an object")
    accuracy = _normalise_band(
        data.get("accuracy"), _ACCURACY_ALIASES, P2_ACCURACY_BANDS, "accuracy"
    )
    originality = _normalise_band(
        data.get("originality"), _ORIGINALITY_ALIASES, P2_ORIGINALITY_BANDS,
        "originality",
    )
    feedback = data.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("feedback must be a non-empty string")
    hint = data.get("hint")
    if hint is None:
        hint = ""
    if not isinstance(hint, str):
        raise ValueError("hint must be a string")
    passed = accuracy == "Accurate" and originality == "Own words"
    hint = hint.strip()[:300]
    if passed:
        hint = ""
    elif not hint:
        # One generic nudge, never the answer, if the model omitted its hint.
        hint = (
            "Point to the key idea the reference explains, then say it in your "
            "own words."
        )
    ref = (reference or "").strip()
    if not passed and len(ref) >= 24 and ref.lower() in hint.lower():
        # Guardrail: a hint must never be the reference answer verbatim.
        hint = (
            "Point to the key idea the reference explains, then say it in your "
            "own words."
        )
    return {
        "passed": passed,
        "accuracy": _ACCURACY_LABELS[accuracy],
        "originality": _ORIGINALITY_LABELS[originality],
        "feedback": feedback.strip()[:800],
        "hint": hint,
    }


def _stub_evaluate_paraphrase(concept: dict, paraphrase: str) -> dict:
    """Lenient keyless/fallback check (S2 DONE gate: seed still reaches 100%)."""
    _ = concept
    ok = bool((paraphrase or "").strip())
    return {
        "passed": ok,
        "accuracy": "Accurate — core meaning assumed (stub-grounded check)."
        if ok else "Inaccurate — write a paraphrase first (stub-grounded check).",
        "originality": "Own words — not compared to source (stub-grounded check)."
        if ok else "Too close to source — no paraphrase supplied.",
        "feedback": "Nice — captures the core meaning in your own words "
        "(stub-grounded, doc scope)." if ok else
        "Explain the concept in your own words, tied to the cited pages "
        "(stub-grounded).",
        "hint": "" if ok else
        "Restate the explanation in your own words, tying to the cited pages "
        "(stub-grounded hint).",
    }


def _blue_evaluate_paraphrase(paraphrase: str) -> dict:
    """Blue bypass (Locks §2+§9): no LLM, plausibility only, no accuracy."""
    text = (paraphrase or "").strip()
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


def evaluate_paraphrase_with_status(
    session_id: str, concept_id: str, paraphrase: str,
    user_id: int | None = None,
) -> dict:
    """S2 live chain + labelled fallback (additive, never raises for live I/O).

    Returns {evaluation, mode: live|stub|bypass, model, fallback_reason}.
    Grounding (§8): resolves the concept row server-side by owned
    (session_id, concept_id); only the student paraphrase is client text.
    Blue user_added rows never call the LLM (plausibility-only bypass).
    Chain: LLM_MODELS order -> stub on 429/5xx/bad-JSON/validation failure.
    A valid live JSON verdict (even passed=false) is returned as live, never
    silently replaced by the lenient stub.
    """
    if user_id is not None:
        store.require_owned_session(session_id, user_id)
    concepts = {c["id"]: c for c in store.list_concepts(session_id)}
    c = concepts.get((concept_id or "").strip())
    if not c:
        raise KeyError("unknown concept for this session")
    text = (paraphrase or "").strip()

    if c.get("source") == "user_added":
        evaluation = _blue_evaluate_paraphrase(text)
        log.info("paraphrase: mode=bypass concept=%s", concept_id)
        return {"evaluation": evaluation, "mode": "bypass",
                "model": "rules", "fallback_reason": ""}

    if not config.is_llm_live():
        evaluation = _stub_evaluate_paraphrase(c, text)
        reason = "stub-default (no LLM key)"
        log.info("paraphrase: mode=stub reason=%s", reason)
        return {"evaluation": evaluation, "mode": "stub",
                "model": "stub", "fallback_reason": reason}

    if not text:
        # Route rejects empty input; direct callers get an honest fail without
        # spending a model call.
        evaluation = _stub_evaluate_paraphrase(c, text)
        reason = "empty paraphrase (not sent to LLM)"
        log.info("paraphrase: mode=stub reason=%s", reason)
        return {"evaluation": evaluation, "mode": "stub",
                "model": "stub", "fallback_reason": reason}

    api_key = config.get_google_key() or ""
    models = config.get_llm_models()
    user_prompt = build_p2_user(c, text)
    last_reason = ""
    for model in models:
        try:
            log.info("paraphrase: trying live model=%s concept=%s", model, concept_id)
            raw = _gemini_generate(
                model, P2_SYSTEM, user_prompt, api_key, config.LLM_TIMEOUT_S
            )
            data = json.loads(_strip_code_fences(raw))
            evaluation = validate_paraphrase_eval_shape(
                data, reference=str(c.get("explanation_text") or "")
            )
            log.info("paraphrase: live ok model=%s passed=%s",
                     model, evaluation["passed"])
            return {"evaluation": evaluation, "mode": "live",
                    "model": model, "fallback_reason": ""}
        except Exception as e:
            # 429/5xx/network/bad-JSON/validation — advance the chain.
            last_reason = f"{model}: {type(e).__name__}: {str(e)[:200]}"
            log.warning("paraphrase: %s", last_reason)
            continue

    evaluation = _stub_evaluate_paraphrase(c, text)
    reason = last_reason or "all live models failed — stub fallback"
    log.warning("paraphrase: mode=stub reason=%s", reason)
    return {"evaluation": evaluation, "mode": "stub",
            "model": "stub", "fallback_reason": reason}


def evaluate_paraphrase(session_id: str, concept_id: str, paraphrase: str,
                        user_id: int | None = None) -> dict:
    """Frozen §8 signature: returns the evaluation dict only.

    Ownership (§0+§8): when user_id is given, verifies
    sessions.user_id == user_id first (route already gates via _owned;
    defense-in-depth so every §8 call verifies, never session_id alone).
    Blue (user_added): bypass LLM — non-empty user text passes with
    plausibility-check feedback, never doc-cited. Extracted: balanced live
    rubric (accuracy + originality) with lenient stub fallback; routes use
    evaluate_paraphrase_with_status for mode/model/warning labelling.
    """
    return evaluate_paraphrase_with_status(
        session_id, concept_id, paraphrase, user_id=user_id
    )["evaluation"]



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
