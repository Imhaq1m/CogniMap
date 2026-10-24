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

S1 live (additive): extract_concepts tries the mixed LLM chain behind env
flags (S2h, grill G-Route: links routed BY MODEL ID — qwen/* -> free Groq,
deepseek-* -> paid DeepSeek with thinking disabled; free-first default
qwen/qwen3.8-27b -> deepseek-flash; the archived Gemini and LM Studio paths
were removed entirely in S2f and unroutable links raise, falling through to
the next link or the labelled stub). Keyless stays stub.
List return shape frozen; mode/model/fallback_reason travel out-of-band via
extract_concepts_with_status (routes use it for labelling, never 502).
S2 live (additive): evaluate_paraphrase uses the same chain with a balanced
rubric (accuracy + originality both pass; minor omissions allowed; hint is
one nudge, never the answer). Blue user_added rows stay a no-LLM bypass.
Result shape frozen; mode/model/fallback_reason travel out-of-band via
evaluate_paraphrase_with_status.
S3 live (additive): generate_scenario (P3) + evaluate_scenario (P4) join the
chain. P3 verbalizes ONLY the app-partitioned chunk — ids echoed unchanged
(validated) and titles never copied verbatim into the text. P4 grades a
submit in ONE merged call per submit: tier-1 wrong picks, empty
justifications and omissions are rule-based BEFORE the chain (G4/G7 —
retries never re-spend tokens); blue user_added selections JOIN the call as
lanes (G2'/G8, amending the S2h no-LLM carry: ground = the user's own saved
user's own saved explanation, lenient-consistency rubric, "user-defined —
plausibility check, not doc-cited" prefix enforced app-side, never
page-cited). A valid live fail stays live; mode=rules labels pure
rule-based submits; strict clear math stays app-side.
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
    "If partial say partial. Keep the set focused: about 4-8 rows, the most "
    "important terms. explanation_text is ONE short sentence (max ~160 chars). "
    "Output a compact JSON list only, no pretty printing. Each item MUST have: concept_id (unique string), "
    "title, kind (main|sub), parent_id (null for main, main concept_id for sub), "
    "source (always the literal string extracted — never user_added, never "
    "generated — generated text belongs in explanation_source), explanation_type "
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
    # S3 G5 trim (parked decision -> implemented): 12000 -> 8000 chars. An
    # extract drops to ~2.8-3k total tokens inside the Groq tpm window,
    # buying burst headroom now that P3/P4 share the chain; provider-agnostic.
    md = (markdown or "")[:8000]
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
    "(1) accuracy is 'Accurate' — the answer captures the central idea and "
    "nothing contradicts the reference; missing supporting details that the "
    "richer reference happens to include do NOT downgrade the band; and (2) "
    "originality is 'Own words' — the student restructured the sentence and "
    "explained it in their own phrasing. Shared technical terms and short "
    "stock phrases are expected and do NOT make an answer too close. Mark "
    "'Too close to source' ONLY when the student copies most of the "
    "reference sentence nearly verbatim (same structure and wording "
    "throughout); when in doubt choose 'Own words'. Use only the supplied "
    "REFERENCE; no external knowledge. If the answer is partial, say what is "
    "missing without revealing the answer. Output one JSON object only with: "
    "passed (bool), accuracy (Accurate|Partly accurate|Inaccurate), "
    "originality (Own words|Too close to source), feedback (ONE short sentence, "
    "max ~140 chars), "
    "hint. passed MUST equal (accuracy == 'Accurate' AND originality == 'Own "
    "words'). On pass hint must be \"\". On fail hint is ONE short nudge "
    "that points at the missing idea or asks for own wording and NEVER "
    "states or paraphrases the reference answer."
)

P2_RULES = (
    "RULES: JSON object only. accuracy exactly one of Accurate|Partly "
    "accurate|Inaccurate. originality exactly one of Own words|Too close to "
    "source. Pass only when accuracy=Accurate and originality=Own words. "
    "A shorter answer that still captures the central idea is Accurate; "
    "reserve Partly accurate for answers where the central idea itself is "
    "missing or muddled, and Inaccurate for wrong or contradictory answers. "
    "Be lenient on "
    "originality: technical terms and short stock phrases are fine; only "
    "near-verbatim copying of most of the reference is Too close. feedback "
    "is ONE short sentence (max ~140 chars), lenient, and never gives the "
    "answer. hint is empty on pass; on fail it is ONE nudge that never "
    "reveals the reference answer. "
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
# S3 P3/P4 prompts (grill ledger G1-G8, model-agnostic JSON-only).
# Stable-prefix-first for implicit caching: RULES first, then the stable
# SCENARIO/REFERENCE blocks, variable JUSTIFIED justifications last.
# ---------------------------------------------------------------------------

P4_BLUE_PREFIX = "user-defined — plausibility check, not doc-cited"

P3_SYSTEM = (
    "You write Apply-scenarios for a study map. Verbalize ONLY the given "
    "concepts: never invent, add, drop or swap them; echo the chunk ids "
    "back exactly. Ground every sentence in the supplied explanations/"
    "pages/captions (doc scope) — no external knowledge, no page numbers "
    "printed as citations. Describe the situation in fresh words: do NOT "
    "print any supplied concept title verbatim in the text. If grounding "
    "is thin, keep the scenario modest and still doc-grounded. Output one "
    "compact JSON object only, no pretty printing."
)

P3_RULES = (
    'RULES: JSON object only: {"text": string, "concept_ids": [ids]}. '
    "Echo CHUNK_IDS exactly, unchanged, same order. Verbalize only — never "
    "invent/add/drop concepts. Never copy a CHUNK_CONCEPTS title into "
    "text; describe the underlying situation instead. Use only the "
    "supplied explanation fields (doc scope, no external knowledge). "
    "2-3 sentences, <= ~420 chars."
)

P4_SYSTEM = (
    "You grade Apply-scenario submissions. For EACH justified concept "
    "decide independently whether its justification correctly explains how "
    "that concept applies to THIS scenario, grounded in that concept's "
    "REFERENCE (doc scope) — no external knowledge. passed=true only when "
    "the justification applies the concept to the scenario's concrete "
    "facts, not when it merely restates the reference or scenario wording. "
    "For BLUE-flagged rows the ground is the user's own definition — trust "
    "it, do not check it against a document, do not cite pages: passed="
    "true when the justification is consistent with that user text AND "
    "plausibly applies it to the scenario's facts; fail when it "
    "contradicts the user's own definition or never touches the scenario. "
    f"Prefix blue feedback with exactly: {P4_BLUE_PREFIX}. feedback: ONE "
    "short sentence (~140 chars). On fail, hint is ONE short nudge that "
    "never states or paraphrases the reference answer; on pass hint must "
    "be empty. Output one compact JSON object only, no pretty printing: "
    '{"results":[{"concept_id","passed","feedback","hint"}]} — exactly one '
    "entry per JUSTIFIED_CONCEPT, same order."
)

P4_RULES = (
    'RULES: JSON object only: '
    '{"results":[{"concept_id","passed","feedback","hint"}]}. One entry per '
    "JUSTIFIED_CONCEPT, same order, ids unchanged. passed=true only when "
    "the justification ties the concept's core idea to the scenario's "
    "concrete facts; a recital of the REFERENCE or scenario wording that "
    "never applies it to the scenario fails. BLUE rows: the ground is the "
    "user's own definition — consistency with it and plausible contact "
    "with the scenario facts is enough; never cite pages; feedback must "
    f"start with '{P4_BLUE_PREFIX}'. feedback ONE short sentence (~140 "
    "chars). hint empty on pass; on fail ONE nudge that never states or "
    "paraphrases the reference answer. Ground only in SCENARIO + REFERENCE."
)


def _lane_line(concept: dict, concept_id: str) -> str:
    """One grounded P3/P4 REFERENCE lane from a server-resolved store row.

    Store rows carry parsed lists for pages (store.list_concepts json-decodes
    them), so values are normalised defensively in case a raw row slips in.
    """
    c = concept or {}
    pages = c.get("pages")
    if isinstance(pages, str):
        try:
            pages = json.loads(pages)
        except Exception:
            pages = []
    return (
        f"- {concept_id} | {_clip(c.get('title'), 300)} | "
        f"{_clip(c.get('explanation_type') or 'definition', 80)} | "
        f"pages {_clip(json.dumps(pages or []), 120)} | "
        f"{_clip(c.get('explanation_text'), 1000)} | "
        f"{_clip(c.get('diagram_description'), 300)}"
    )


def build_p3_user(chunk_ids: list[str], chunk_rows: list[dict] | None = None,
                  mains_rows: list[dict] | None = None) -> str:
    """P3 user prompt: RULES, then CHUNK_IDS + the app-owned chunk lanes.

    Grounding (§8): every lane is a server-resolved store row passed by the
    route (api_l3_generate) — no client text is involved at all. mains_rows
    (Phase 2) ride along as display-only background; mains are never
    chunked, never pooled, never in concept_ids (Locks §3+§7).
    """
    rows = {str((r or {}).get("id") or ""): r for r in (chunk_rows or [])}
    lines = [
        _lane_line(rows.get(cid) or {}, cid) for cid in (chunk_ids or [])
    ]
    out = (
        f"{P3_RULES}\n\n"
        f"CHUNK_IDS: {json.dumps(list(chunk_ids or []))}\n\n"
        "CHUNK_CONCEPTS (id | title | type | pages | explanation | diagram):\n"
        + "\n".join(lines)
    )
    if mains_rows:
        bg = [
            f"- {_clip(c.get('id'), 60)} | {_clip(c.get('title'), 200)} | "
            f"{_clip(c.get('explanation_text'), 240)}"
            for c in list(mains_rows)[:12]
        ]
        out += (
            "\n\nMAINS_BACKGROUND (display-only background; never part of "
            "concept_ids):\n" + "\n".join(bg)
        )
    return out


def build_p4_user(scenario_text: str, lanes: list[dict]) -> str:
    """P4 user prompt for the ONE merged grading call per submit.

    Grounding (§8): `lanes` are built by the caller from server-resolved
    rows — every lane {concept_id, blue, justification, concept}. The only
    client text in the whole prompt is each lane's justification. Blue lanes
    carry the user's own saved explanation as ground (G2'/G8) with a BLUE
    marker; the model is told not to cite pages for that row.
    """
    ref_lines: list[str] = []
    just_lines: list[str] = []
    for lane in lanes:
        cid = str(lane.get("concept_id", ""))
        c = lane.get("concept") or {}
        if lane.get("blue"):
            pages_field = "pages user-defined"
            blue_note = (
                " [BLUE: user_added — ground is the USER TEXT, not the doc; "
                "never cite pages for this row]"
            )
            text = _clip(c.get("explanation_text"), 4000)
        else:
            pages = c.get("pages")
            if isinstance(pages, str):
                try:
                    pages = json.loads(pages)
                except Exception:
                    pages = []
            pages_field = f"pages {_clip(json.dumps(pages or []), 120)}"
            blue_note = ""
            text = _clip(c.get("explanation_text"), 4000)
        ref_lines.append(
            f"- {cid} | {_clip(c.get('title'), 300)} | "
            f"{_clip(c.get('explanation_type') or 'definition', 80)} | "
            f"{pages_field} | {text} | "
            f"{_clip(c.get('diagram_description'), 300)}{blue_note}"
        )
        just_lines.append(
            f"- concept_id: {cid} | justification: "
            f"{_clip(lane.get('justification'), 1200)}"
        )
    return (
        f"{P4_RULES}\n\n"
        f"SCENARIO:\n{_clip(scenario_text, 1200)}\n\n"
        "REFERENCE_CONCEPTS (id | title | type | pages | explanation | diagram):\n"
        + "\n".join(ref_lines)
        + "\n\nJUSTIFIED_CONCEPTS:\n" + "\n".join(just_lines)
    )


# ---- P3/P4 strict validation (live JSON) ----

def validate_scenario_text_shape(data: object, chunk_ids: list[str]) -> str:
    """Strict P3 shape check (S3 grill G1; supervisor-demo strictness).

    Must be an object (an optional {"scenario": {...}} wrapper tolerated)
    with non-empty text and concept_ids that EQUAL the app-owned chunk
    (same set, same length, no duplicates). Returns the clipped text. The
    app keeps its own chunk order at store time regardless; the echo check
    proves the model verbalized the right chunk and invented nothing.
    Raises ValueError(reason) -> caller advances the chain (never 502).
    """
    if not isinstance(data, dict):
        raise ValueError("live JSON must be an object")
    inner = data.get("scenario")
    if isinstance(inner, dict):
        data = inner
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("missing scenario text")
    ids = data.get("concept_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("concept_ids must be a non-empty list")
    clean = [str(i) for i in ids]
    if any(not i.strip() for i in clean):
        raise ValueError("concept_ids entries must be non-empty strings")
    if len(set(clean)) != len(clean):
        raise ValueError("duplicate concept id in concept_ids")
    chunk = [str(i) for i in (chunk_ids or [])]
    if set(clean) != set(chunk) or len(clean) != len(chunk):
        raise ValueError("concept_ids must equal the app-owned chunk")
    return text.strip()[:2000]


def _as_bool(value: object) -> bool:
    """Model verdict coercion: real bool, or true/false-style strings.

    Unknown string verdicts fail closed (safe direction: the student gets a
    nudge instead of a free pass).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "y", "pass", "passed", "correct"):
            return True
        if v in ("false", "0", "no", "n", "fail", "failed"):
            return False
    return False


_L3_GENERIC_HINT = "Tie your justification to specific scenario facts."
_L3_MISSING_FEEDBACK_FAIL = (
    "Explain how this concept applies to the scenario facts."
)
_L3_MISSING_FEEDBACK_PASS = (
    "Applies here — justification supported by the scenario facts."
)


def _coerced_missing_entry(cid: str) -> dict:
    """Split-stay coercion: a dropped live entry still answers honestly."""
    return {"concept_id": cid, "passed": False,
            "feedback": _L3_MISSING_FEEDBACK_FAIL, "hint": _L3_GENERIC_HINT}


def validate_eval_results_shape(data: object, lane_ids: list[str],
                                grounds: dict[str, str] | None = None) -> list[dict]:
    """Strict P4 shape check + stay-live coercions (S3 grill G3/G6/G8).

    Returns exactly ONE entry per lane id, in lane order. Structural
    garbage raises ValueError -> the caller advances the chain. Per-entry
    problems coerce and stay live (a valid read is never thrown away):
    missing entry -> generic fail + nudge; unknown / duplicated / extra
    ids dropped; string verdicts coerced; pass forces hint ''; failed
    missing hint -> one generic nudge; a fail hint that echoes the
    reference answer is replaced (S2 hint guardrail mirrors here).
    """
    if not isinstance(data, dict):
        raise ValueError("live JSON must be an object")
    raw = data.get("results")
    if not isinstance(raw, list):
        raise ValueError("results must be a list")
    want = [str(cid) for cid in (lane_ids or [])]
    by_id: dict[str, dict] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        cid = str(r.get("concept_id") or "").strip()
        if not cid or cid not in want or cid in by_id:
            continue  # unknown / extra / duplicated ids dropped
        by_id[cid] = r
    out: list[dict] = []
    for cid in want:
        r = by_id.get(cid)
        if r is None:
            out.append(_coerced_missing_entry(cid))
            continue
        passed = _as_bool(r.get("passed"))
        feedback = r.get("feedback")
        if not isinstance(feedback, str) or not feedback.strip():
            feedback = _L3_MISSING_FEEDBACK_PASS if passed else _L3_MISSING_FEEDBACK_FAIL
        else:
            feedback = feedback.strip()[:800]
        hint = r.get("hint")
        hint = hint.strip()[:300] if isinstance(hint, str) else ""
        if passed:
            hint = ""
        elif not hint:
            hint = _L3_GENERIC_HINT
        ref = str((grounds or {}).get(cid) or "").strip()
        if not passed and len(ref) >= 24 and ref.lower() in hint.lower():
            # Guardrail (S2 carry): a hint must never be the reference answer.
            hint = _L3_GENERIC_HINT
        out.append({"concept_id": cid, "passed": passed,
                    "feedback": feedback, "hint": hint})
    return out


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
        src = str(c.get("source") or "").strip().lower()
        if src == "generated":
            # Model conflation (first observed on GLM-4.7-Flash, kept
            # defensive): `source` is row provenance (extracted vs user_added);
            # synthesized text belongs in explanation_source. Coerce this one
            # value; still reject user_added.
            c["source"] = "extracted"
            log.info("extract: source generated -> extracted (%s)", cid)
        elif src == "extracted":
            pass
        elif src == "user_added":
            # Hard guardrail: a live extractor must never mint user-added rows.
            raise ValueError(f"live extractor must output extracted only ({cid})")
        else:
            # Gemma-4 conflation (2026-10-22): the model treats `source` as
            # "the concept's origin text" and puts a section title/copied
            # phrase there (e.g. "Machine Learning") or omits it. Same lenient
            # normalisation as the generated->extracted coercion: provenance
            # is never anything but extracted from a live extractor, so coerce
            # and log — a hard reject would stub-fallback an otherwise
            # perfectly shaped row.
            c["source"] = "extracted"
            log.info("extract: source %r -> extracted (%s)", src[:60], cid)
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


# Groq free-tier pacing (tracker [S2b->S2e]): the per-key windows are rpm 30
# / rpd 1000 / tpm 8000 prompt+completion / tpd 200000 for qwen3.8-27b, and
# the measured 429 strings quoted OTPM 1000 with each request's max_tokens
# reserving against it. Under either reading the completion cap stays well
# below the per-minute budget, so the next demo click (extract -> verify
# inside a minute) is never blocked by our own cap.
GROQ_MAX_TOKENS = 200            # P2: short JSON (feedback + one nudge)
GROQ_MAX_TOKENS_EXTRACT = 850    # P1: list (well under any per-minute window)
# DeepSeek is pay-as-you-go (no free-tier token windows), but the same
# conservative caps keep P2/P1 outputs short and comparable for the
# latency benchmark (S2g) — generation cost does not dominate the demo.
DEEPSEEK_MAX_TOKENS = 200            # P2
DEEPSEEK_MAX_TOKENS_EXTRACT = 850    # P1
# S3 (caps grill): two new call shapes join the chain — P3 verbalizes one
# short scenario OBJECT (~90-130 output tokens; 350 keeps ~2.5x headroom) and
# P4 grades ONE merged object with <=3 entries after the tier-1/empty/
# locked pre-filters (feedback ~140 chars each; 450 is comfortable). Same
# value on both providers (S2h identical pacing).
GROQ_MAX_TOKENS_SCENARIO = 350   # P3
GROQ_MAX_TOKENS_EVAL = 450       # P4
# S2g+ probe (2026-10-23): deepseek-flash thinks by default and the effort
# knob (low|high|max) does NOT turn that off (effort=low still burned ~209
# reasoning tokens; reasoning counts inside max_tokens -> empty content and
# every call stubbed). The working off-switch is the GLM-style field, same
# mechanism as the S2b GLM thinking quirk reading / S2d Gemma reasoning_effort
# finding; reasoning_effort:"none" also worked (measured) but this is the
# documented semantic switch. The old deepseek-chat alias = this same flash
# model with thinking already off server-side.
DEEPSEEK_THINKING_OFF = {"thinking": {"type": "disabled"}}

_MAX_TOKENS_BY_SHAPE = {
    "p1": GROQ_MAX_TOKENS_EXTRACT,
    "p2": GROQ_MAX_TOKENS,
    "p3": GROQ_MAX_TOKENS_SCENARIO,
    "p4": GROQ_MAX_TOKENS_EVAL,
}


def _max_tokens(extract: bool = False, shape: str | None = None) -> int:
    """Output cap by call shape (S2h: identical pacing on both providers).

    `shape` ("p1".."p4") wins when given — the S3 slices use it. The legacy
    boolean keeps the S2 behaviour for existing callers/tests.
    """
    if shape:
        return _MAX_TOKENS_BY_SHAPE.get(shape, GROQ_MAX_TOKENS)
    return _MAX_TOKENS_BY_SHAPE["p1"] if extract else _MAX_TOKENS_BY_SHAPE["p2"]


def _openai_compatible_generate(
    model: str, system: str, user: str, api_key: str, base_url: str,
    timeout_s: int, json_mode: bool = True, max_tokens: int | None = None,
    default_max_tokens: int = GROQ_MAX_TOKENS,
    extra_body: dict | None = None,
) -> str:
    """One OpenAI-compatible chat-completions call (the Groq transport).

    Raw httpx (already a dependency): explicit timeout, no hidden retries.
    Only the JSON `content` is read (any reasoning fields are ignored). Raises
    on HTTP>=400/empty/network so the chain can advance (bad JSON is caught by
    the caller's json.loads).

    json_mode requests JSON-object mode (default; P2 object output) via
    response_format {"type": "json_object"}. P1 always passes json_mode=False:
    object mode nudged a previous provider (S2b GLM) to wrap a top-level
    list, which fails the strict extract validator. P2 feedback is a short
    JSON object, so json_mode stays on for it.

    max_tokens falls back to default_max_tokens (the P2 cap).

    extra_body (S2g+): provider-specific payload fields merged last (e.g.
    DeepSeek's thinking toggle). None (Groq) keeps the S2f-era body
    byte-for-byte unchanged.
    """
    import httpx  # type: ignore

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens or default_max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if extra_body:
        payload.update(extra_body)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=float(timeout_s)) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"{model}: HTTP {resp.status_code} {resp.text[:120]}")
    data = resp.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    message = (choices[0].get("message") if choices else None) or {}
    text = message.get("content") or ""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{model} returned empty response")
    return text


def _groq_generate(model: str, system: str, user: str, api_key: str, timeout_s: int,
                   json_mode: bool = True, max_tokens: int | None = None) -> str:
    """One Groq call (S2e default; free tier, LPU-fast)."""
    return _openai_compatible_generate(
        model, system, user, api_key, config.get_groq_base_url(),
        timeout_s, json_mode=json_mode, max_tokens=max_tokens,
        default_max_tokens=GROQ_MAX_TOKENS,
    )


def _deepseek_generate(model: str, system: str, user: str, api_key: str,
                       timeout_s: int, json_mode: bool = True,
                       max_tokens: int | None = None) -> str:
    """One DeepSeek call (S2h mixed chain: paid failover link — or primary if
    LLM_MODELS reorders; pinned S2g+ to deepseek-flash = DeepSeek-V4.1-Flash,
    pay-as-you-go, OpenAI-compatible).

    Same transport as Groq (plus one extra_body field). DeepSeek's
    response_format {"type": "json_object"} requires the word 'json' in the
    messages — both the P2 system text ("Output one JSON object only") and
    the P1 rules ("RULES: JSON list only") already carry it, so json_mode
    passes through exactly like Groq's.

    Thinking off (S2g+ probe, 2026-10-23): deepseek-flash THINKS by default
    (reasoning tokens count inside max_tokens, leaving content empty -> every
    call would fall to the stub). The model's effort levels (low|high|max)
    do NOT disable it (measured: effort=low still burned ~209 reasoning
    tokens at a 400-cap); the working switches are thinking {"type":
    "disabled"} (GLM-style, wired here) or reasoning_effort "none". The old
    deepseek-chat alias is served by the same flash model with thinking
    already off — the pinned pair below reproduces that explicitly so the
    config names the real served model.
    """
    return _openai_compatible_generate(
        model, system, user, api_key, config.get_deepseek_base_url(),
        timeout_s, json_mode=json_mode, max_tokens=max_tokens,
        default_max_tokens=DEEPSEEK_MAX_TOKENS,
        extra_body=DEEPSEEK_THINKING_OFF,
    )


def _llm_generate(model: str, system: str, user: str, api_key: str, timeout_s: int,
                  json_mode: bool = True, max_tokens: int | None = None) -> str:
    """Router for every live chain link (S2h mixed chain; grill G-Route).

    Links are routed BY MODEL ID, not by a global provider switch:
    qwen/* -> _groq_generate (free tier, LPU-fast; G3 first link),
    deepseek-* -> _deepseek_generate (paid failover, thinking off; G3 last
    link). Unroutable ids raise -> the chain advances to the next link and,
    after all fail, the labelled stub answers (never 502).
    """
    provider = config.model_provider(model)
    if provider == "groq":
        return _groq_generate(model, system, user, api_key, timeout_s,
                              json_mode=json_mode, max_tokens=max_tokens)
    if provider == "deepseek":
        return _deepseek_generate(model, system, user, api_key, timeout_s,
                                  json_mode=json_mode, max_tokens=max_tokens)
    raise ValueError(f"unroutable LLM chain link: {model!r}")


def extract_concepts_with_status(
    markdown: str, figures: list[dict] | None = None
) -> dict:
    """S1 live chain + labelled fallback (additive, never raises).

    Returns {concepts, mode: live|stub, model, fallback_reason}.
    Chain: mixed LLM_MODELS (S2h; free-first by default: qwen -> flash) routed
    BY MODEL ID, one attempt per link -> stub.
    On 429/5xx/bad-JSON/validation fail, advance to next link; after all
    fail, seed-grounded stub. Never 502 in demo. Logs fallback_reason
    server-side without keys.
    """
    figs = list(figures or [])
    if not config.is_llm_live():
        concepts = _stub_extract_concepts(markdown, figs)
        reason = "stub-default (no key on any chain link)"
        log.info("extract: mode=stub reason=%s", reason)
        return {"concepts": concepts, "mode": "stub", "model": "stub", "fallback_reason": reason}
    models = config.get_llm_models()
    user_prompt = build_p1_user(markdown, figs)
    last_reason = ""
    skipped: list[str] = []
    for model in models:
        api_key = config.get_llm_key(model)  # per-link key (never logged)
        if not api_key:
            skipped.append(model)
            log.info("extract: %s: skipped (provider key absent)", model)
            continue
        try:
            log.info("extract: trying live model=%s", model)
            raw = _llm_generate(
                model, P1_SYSTEM, user_prompt, api_key, config.LLM_TIMEOUT_S,
                json_mode=False,  # P1 wants a top-level list, not object mode
                max_tokens=_max_tokens(shape="p1"),  # shape-paced caps
            )
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
            if isinstance(data, list) and not data:
                # Valid-but-empty live result (e.g. placeholder/empty parsed
                # text): a labelled stub keeps the demo moving; not an error.
                last_reason = f"{model}: live returned no concepts (empty list)"
                log.info("extract: %s", last_reason)
                continue
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
    if skipped:
        reason += f" [+ unkeyed links skipped: {', '.join(skipped)}]"
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
# S2 live: balanced rubric (accuracy + originality), provider chain -> stub.
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
    Chain: mixed LLM_MODELS routed BY MODEL ID (S2h; free-first by default:
    qwen -> flash) -> stub on 429/5xx/bad-JSON/validation failure.
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
        reason = "stub-default (no key on any chain link)"
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

    models = config.get_llm_models()
    user_prompt = build_p2_user(c, text)
    last_reason = ""
    skipped: list[str] = []
    for model in models:
        api_key = config.get_llm_key(model)  # per-link key (never logged)
        if not api_key:
            skipped.append(model)
            log.info("paraphrase: %s: skipped (provider key absent)", model)
            continue
        try:
            log.info("paraphrase: trying live model=%s concept=%s", model, concept_id)
            raw = _llm_generate(
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
    if skipped:
        reason += f" [+ unkeyed links skipped: {', '.join(skipped)}]"
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

def _generate_scenario_stub(chunk_ids: list[str], context_markdown: str = "") -> dict:
    """Frozen stub behaviour (keyless + fallback): chunk ids preserved."""
    _ = context_markdown
    pick = list(chunk_ids or [])[:3]  # cap 3; 2+2 remainder + n=1 exception handled by caller
    return {
        "scenario_id": "stub-scn-1",
        "text": "stub scenario covering: " + ", ".join(pick),
        "concept_ids": pick,
    }


def generate_scenario_with_status(
    chunk_ids: list[str],
    context_markdown: str = "",
    chunk_rows: list[dict] | None = None,
    mains_rows: list[dict] | None = None,
) -> dict:
    """S3 live chain + labelled fallback (additive, never raises for I/O).

    Returns {scenario: {scenario_id, text, concept_ids},
             mode: live|stub, model, fallback_reason}.
    App owns the partition (Locks §3+§8): the chunk is app-supplied and the
    live model may only verbalize text for it — validate_scenario_text_shape
    demands an id echo that equals the chunk, else the chain advances and
    the labelled stub answers (never 502). Chain: mixed LLM_MODELS routed BY
    MODEL ID (S2h free-first: qwen -> deepseek-flash), one attempt per link;
    unkeyed links are skipped and noted in fallback_reason without burning
    an attempt. Keys never logged.
    """
    pick = list(chunk_ids or [])[:3]  # cap 3; caller gates 1-3 (store.create_scenario)
    _ = context_markdown  # frozen param; structured rows carry the live ground
    if not config.is_llm_live():
        scn = _generate_scenario_stub(chunk_ids, context_markdown)
        reason = "stub-default (no key on any chain link)"
        log.info("l3 generate: mode=stub reason=%s", reason)
        return {"scenario": scn, "mode": "stub", "model": "stub",
                "fallback_reason": reason}

    user_prompt = build_p3_user(pick, chunk_rows, mains_rows)
    last_reason = ""
    skipped: list[str] = []
    for model in config.get_llm_models():
        api_key = config.get_llm_key(model)  # per-link key (never logged)
        if not api_key:
            skipped.append(model)
            log.info("l3 generate: %s: skipped (provider key absent)", model)
            continue
        try:
            log.info("l3 generate: trying live model=%s chunk=%s", model, pick)
            raw = _llm_generate(
                model, P3_SYSTEM, user_prompt, api_key, config.LLM_TIMEOUT_S,
                json_mode=True,  # object output (P3 is an object, not a list)
                max_tokens=_max_tokens(shape="p3"),
            )
            data = json.loads(_strip_code_fences(raw))
            text = validate_scenario_text_shape(data, pick)
            log.info("l3 generate: live ok model=%s chars=%d", model, len(text))
            return {
                "scenario": {"scenario_id": "", "text": text,
                             "concept_ids": list(pick)},
                "mode": "live", "model": model, "fallback_reason": "",
            }
        except Exception as e:
            # 429/5xx/network/auth/bad-JSON/shape-fail — advance the chain.
            last_reason = f"{model}: {type(e).__name__}: {str(e)[:200]}"
            log.warning("l3 generate: %s", last_reason)
            continue
    scn = _generate_scenario_stub(chunk_ids, context_markdown)
    reason = last_reason or "all live models failed — stub fallback"
    if skipped:
        reason += f" [+ unkeyed links skipped: {', '.join(skipped)}]"
    log.warning("l3 generate: mode=stub reason=%s", reason)
    return {"scenario": scn, "mode": "stub", "model": "stub",
            "fallback_reason": reason}


def generate_scenario(chunk_ids: list[str], context_markdown: str = "") -> dict:
    """Frozen §8 signature: returns the scenario dict only (labelling
    out-of-band via generate_scenario_with_status).

    App owns the partition: the model's verbalized text is stored against
    the APP's chunk ids (the untouched store.create_scenario gate), so a
    misbehaving echo can never corrupt the ceil(n/3) math.
    """
    return generate_scenario_with_status(chunk_ids, context_markdown)["scenario"]


# 4. evaluate_scenario(session_id, scenario_id, selections)
#    -> {results, missed_ids, scenario_cleared} (Locks §3 tier 4 + §8)

# Rule-based lane copies for the LIVE path (honest wording — no
# "(stub-grounded)" tag; that tag stays reserved for the frozen stub engine,
# whose mode=stub label makes it truthful). Tier-1 copy matches the stub.

def _tier1_entry(cid: str) -> dict:
    return {"concept_id": cid, "passed": False,
            "feedback": f"Concept {cid} is not related to this scenario.",
            "hint": "Uncheck it, or replace with a concept the scenario facts support."}


def _empty_just_entry(cid: str, blue: bool) -> dict:
    if blue:
        return {"concept_id": cid, "passed": False,
                "feedback": "Justify how your concept applies to the scenario.",
                "hint": _L3_GENERIC_HINT}
    return {"concept_id": cid, "passed": False,
            "feedback": _L3_MISSING_FEEDBACK_FAIL, "hint": _L3_GENERIC_HINT}


def _stub_lane_entry(cid: str, blue: bool) -> dict:
    """Lenient stub copy for a live lane when the whole chain failed."""
    if blue:
        return {"concept_id": cid, "passed": True,
                "feedback": "user-defined — plausibility check, not doc-cited.",
                "hint": ""}
    return {"concept_id": cid, "passed": True,
            "feedback": _L3_MISSING_FEEDBACK_PASS + " (stub-grounded).",
            "hint": ""}


def _evaluate_scenario_stub(session_id: str, scenario_id: str,
                            selections: list[dict] | None = None) -> dict:
    """Frozen stub behaviour (keyless + fallback), byte-identical output.

    Keyless full-run seed clears still land; keyless CI stays green; copies
    keep the historical stub-grounded wording (their mode=stub label makes
    it truthful).
    """
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


def evaluate_scenario_with_status(
    session_id: str,
    scenario_id: str,
    selections: list[dict] | None = None,
    user_id: int | None = None,
) -> dict:
    """S3 live chain + labelled fallback (additive, never raises for live I/O).

    ONE merged P4 call per submit (the S2e+ rate-limit guardrail; the §8
    signature guarantees the merge). Pre-chain rule-based layers per
    selection: tier-1 wrong picks (selected-but-not-required -> "not
    related", retries never re-spend tokens), empty justifications (never
    sent, G7), locked passes (excluded by the caller). Blue user_added
    selections JOIN the call (G2'/G8, amending the S2h no-LLM carry): the
    lane's ground is the user's own saved explanation, graded leniently for
    consistency with it + plausible contact with the scenario facts, the
    "user-defined — plausibility check, not doc-cited" prefix enforced
    app-side, no page citations. Only extraction-grounded required
    selections reach the model.

    Returns {evaluation: {results, missed_ids, scenario_cleared},
             mode: live|stub|rules, model, fallback_reason}.
    mode=rules labels a submit that needed zero model calls (G4). Keyless ->
    frozen stub engine; a valid live fail stays live (never silently
    swapped); strict clear math stays app-side (missed empty AND no wrong
    picks AND every required selection passed); lock-aware locked coverage
    is the caller's concern (main.api_l3_submit).
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

    if not config.is_llm_live():
        evaluation = _evaluate_scenario_stub(session_id, scenario_id, sels)
        reason = "stub-default (no key on any chain link)"
        log.info("l3 submit: mode=stub reason=%s", reason)
        return {"evaluation": evaluation, "mode": "stub", "model": "stub",
                "fallback_reason": reason}

    # Pre-chain lane split (submission order): tier-1 / empty / live lanes.
    tier1: list[dict] = []
    empty_lanes: list[dict] = []
    lanes: list[dict] = []
    for s in sels:
        cid = str(s.get("concept_id", "")).strip()
        just = (s.get("justification") or "").strip()
        if cid not in required:
            tier1.append(_tier1_entry(cid))
            continue
        c = concepts.get(cid) or {}
        blue = c.get("source") == "user_added"
        if not just:
            empty_lanes.append(_empty_just_entry(cid, blue))
            continue
        lanes.append({"concept_id": cid, "blue": blue,
                      "justification": just, "concept": c})

    def _finish(results: list[dict]) -> dict:
        got = {str(s.get("concept_id", "")) for s in sels}
        missed = [c for c in required if c not in got]
        by_id: dict[str, bool] = {}
        for r in results:
            by_id.setdefault(str(r.get("concept_id", "")), bool(r.get("passed")))
        required_ok = all(by_id.get(cid, False) for cid in required)
        wrong = any(str(r.get("concept_id", "")) not in required for r in results)
        cleared = (not missed) and (not wrong) and required_ok and bool(required)
        return {"results": results, "missed_ids": missed, "scenario_cleared": cleared}

    def _ordered(entries: list[dict]) -> list[dict]:
        # Submission order, mirroring the frozen stub shape (UI maps by id).
        by_cid: dict[str, dict] = {}
        for e in entries:
            by_cid.setdefault(str(e.get("concept_id", "")), e)
        return [by_cid[str(s.get("concept_id", ""))] for s in sels]

    if not lanes:
        log.info("l3 submit: mode=rules (no LLM-graded selections)")
        entries = tier1 + empty_lanes
        return {"evaluation": _finish(_ordered(entries)), "mode": "rules",
                "model": "rules", "fallback_reason": ""}

    grounds = {l["concept_id"]: str((l["concept"] or {}).get("explanation_text") or "")
               for l in lanes}
    blue_ids = {l["concept_id"] for l in lanes if l["blue"]}
    lane_ids = [l["concept_id"] for l in lanes]
    user_prompt = build_p4_user(str(scn.get("text") or ""), lanes)
    last_reason = ""
    skipped: list[str] = []
    for model in config.get_llm_models():
        api_key = config.get_llm_key(model)  # per-link key (never logged)
        if not api_key:
            skipped.append(model)
            log.info("l3 submit: %s: skipped (provider key absent)", model)
            continue
        try:
            log.info("l3 submit: trying live model=%s lanes=%s",
                     model, sorted(lane_ids))
            raw = _llm_generate(
                model, P4_SYSTEM, user_prompt, api_key, config.LLM_TIMEOUT_S,
                json_mode=True, max_tokens=_max_tokens(shape="p4"),
            )
            data = json.loads(_strip_code_fences(raw))
            lane_results = validate_eval_results_shape(data, lane_ids, grounds)
            for r in lane_results:
                if (r["concept_id"] in blue_ids
                        and not r["feedback"].startswith(P4_BLUE_PREFIX)):
                    r["feedback"] = f"{P4_BLUE_PREFIX} {r['feedback']}"[:900]
                    log.info("l3 submit: blue prefix enforced (%s)",
                             r["concept_id"])
            log.info("l3 submit: live ok model=%s passed=%s",
                     model, [r["passed"] for r in lane_results])
            entries = tier1 + empty_lanes + lane_results
            return {"evaluation": _finish(_ordered(entries)), "mode": "live",
                    "model": model, "fallback_reason": ""}
        except Exception as e:
            # 429/5xx/network/auth/bad-JSON/shape-fail — advance the chain.
            last_reason = f"{model}: {type(e).__name__}: {str(e)[:200]}"
            log.warning("l3 submit: %s", last_reason)
            continue

    # Whole chain dead: lenient stub lanes (the pre-agreed demo-safety trade;
    # a VALID LIVE FAIL above always stays live). Labelled, never 502.
    lane_results = [_stub_lane_entry(l["concept_id"], l["blue"]) for l in lanes]
    entries = tier1 + empty_lanes + lane_results
    reason = last_reason or "all live models failed — stub fallback"
    if skipped:
        reason += f" [+ unkeyed links skipped: {', '.join(skipped)}]"
    log.warning("l3 submit: mode=stub reason=%s", reason)
    return {"evaluation": _finish(_ordered(entries)), "mode": "stub",
            "model": "stub", "fallback_reason": reason}


def evaluate_scenario(
    session_id: str,
    scenario_id: str,
    selections: list[dict] | None = None,
    user_id: int | None = None,
) -> dict:
    """Frozen §8 signature: returns the evaluation dict only.

    Ownership (§0+§8): when user_id is given, verifies sessions.user_id ==
    user_id first. Raw client-supplied required sets are NEVER trusted —
    `required` always resolves from the owned scenario row (legacy
    scenario_concept_ids param removed per §8 MUST NOT trust raw client
    text). results = one entry per submitted selection (tier 1 flagged
    rule-based); missed_ids = required-but-unselected; cleared = missed
    empty AND no wrong picks AND every required selected+passed. Blue
    selections grade against the user's own saved text (G2'). Lock-passed
    inputs are excluded by the caller (main keeps the locked set); the
    caller's strict clear additionally requires locked coverage — see
    main.api_l3_submit. Routes need mode/model/warning:
    evaluate_scenario_with_status.
    """
    return evaluate_scenario_with_status(
        session_id, scenario_id, selections, user_id=user_id
    )["evaluation"]


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
