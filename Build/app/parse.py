"""CogniMap Step 1 — LlamaParse (Locks §0) + S1 live path (additive).

Locked parsing: LlamaParse API tier `agentic` (or `agentic_plus` for complex
pages) with `images_to_save: ["screenshot"]`,
`expand: ["text","markdown","items","images_content_metadata"]`.
Cost-optimizer allowed. Real keys deferred — UI builds against this stub + seed.
Pipeline: PDF -> LlamaParse (sentences/pages/figures) -> Extractor LLM (§1).

S1 (Integration_Tracker): live path is additive only.
  parse_pdf(file, pdf_bytes=None) tries live when LLAMA_CLOUD_API_KEY is set,
  else falls back to the frozen stub. Return dict keeps frozen keys and adds
  mode + fallback_reason (additive, no UI break).
  Diagrams: screenshots written to /static/diagrams/{diagram_id}.png when
  present; absent file -> description-only, no breakage (Locks §0).
"""
from __future__ import annotations

import logging
import os
import tempfile

from . import config

log = logging.getLogger("cognimap.parse")

TIER_DEFAULT = "agentic"
IMAGES_TO_SAVE = ["screenshot"]
EXPAND = ["text", "markdown", "items", "images_content_metadata"]


def llamaparse_stub(file_label: str) -> dict:
    """LlamaParse stub (Locks §0 agentic tier, screenshot images).

    Figures carry diagram_id/page/image_path/caption per §8; screenshots
    served by convention at /static/diagrams/{diagram_id}.png (§0), absent
    file → description-only rendering (no breakage).
    """
    label = (file_label or "seed-demo.pdf").strip() or "seed-demo.pdf"
    return {
        "file": label,
        "tier": "agentic",
        "images_to_save": ["screenshot"],
        "expand": ["text", "markdown", "items", "images_content_metadata"],
        "markdown": f"# Parsed stub for {label}\n\nSentences/pages/figures placeholder — extractor fills concepts from seed.",
        "figures": [
            {
                "diagram_id": "fig-p5-1",
                "page": 5,
                "image_path": "/static/diagrams/fig-p5-1.png",
                "caption": "Scatter of labeled points splitting into two loose clusters.",
            },
            {
                "diagram_id": "fig-p13-1",
                "page": 13,
                "image_path": "/static/diagrams/fig-p13-1.png",
                "caption": "Model pipeline stages from inputs to deployment.",
            },
        ],
        "pages": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        "mode": "stub",
        "fallback_reason": "stub-default (no live key)",
    }


def _with_mode(d: dict, mode: str, reason: str = "") -> dict:
    d = dict(d)
    d["mode"] = mode
    d["fallback_reason"] = reason
    # Frozen keys guaranteed.
    d.setdefault("images_to_save", list(IMAGES_TO_SAVE))
    d.setdefault("expand", list(EXPAND))
    d.setdefault("tier", config.get_llama_tier())
    return d


def _save_screenshots(figures: list[dict]) -> None:
    """Write inline screenshot bytes to /static/diagrams/{id}.png when present.

    Figures may carry image_bytes (raw png) or image_base64 from the live
    parse. Absent bytes -> keep image_path convention only (description-only).
    Never raises (no breakage).
    """
    import base64

    try:
        root = config.diagram_root()
        os.makedirs(root, exist_ok=True)
        for f in figures or []:
            did = str(f.get("diagram_id") or "").strip()
            if not did:
                continue
            data: bytes | None = None
            if isinstance(f.get("image_bytes"), (bytes, bytearray)):
                data = bytes(f["image_bytes"])
            elif isinstance(f.get("image_base64"), str) and f["image_base64"].strip():
                try:
                    data = base64.b64decode(f["image_base64"].strip())
                except Exception:
                    data = None
            if data:
                try:
                    with open(os.path.join(root, f"{did}.png"), "wb") as fh:
                        fh.write(data)
                except Exception as e:
                    log.warning("parse: diagram write failed %s: %s", did, e)
            # Normalise convention path for the UI (§0) even when bytes absent.
            if not f.get("image_path"):
                f["image_path"] = f"/static/diagrams/{did}.png"
            # Drop raw bytes before returning (keep JSON-serialisable).
            f.pop("image_bytes", None)
            f.pop("image_base64", None)
    except Exception as e:
        log.warning("parse: screenshot save skipped: %s", e)


def _live_parse_via_llama_cloud(pdf_bytes: bytes, filename: str, tier: str) -> dict:
    """Live parse via llama-cloud SDK (Parse API v2). Raises on any failure."""
    from llama_cloud import LlamaCloud  # type: ignore

    api_key = config.get_llama_key()
    if not api_key:
        raise RuntimeError("no LLAMA_CLOUD_API_KEY")
    # Write bytes to a temp file — SDK uploads from path.
    suffix = ".pdf"
    if filename and "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1][:10]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        client = LlamaCloud(api_key=api_key)
        up = client.files.create(file=tmp_path, purpose="parse")
        file_id = getattr(up, "id", None) or getattr(up, "file_id", None)
        if not file_id and isinstance(up, dict):
            file_id = up.get("id")
        if not file_id:
            raise RuntimeError("upload returned no file id")
        result = client.parsing.parse(
            file_id=file_id,
            tier=tier,
            version="latest",
            expand=list(EXPAND),
            output_options={"images_to_save": list(IMAGES_TO_SAVE)},
        )
        return _convert_llama_cloud_result(result, filename, tier)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _convert_llama_cloud_result(result: object, filename: str, tier: str) -> dict:
    """Best-effort conversion of llama-cloud ParseResult -> {markdown, figures}."""
    import base64

    markdown_parts: list[str] = []
    figures: list[dict] = []
    pages: list[int] = []
    try:
        md = getattr(result, "markdown", None)
        items = getattr(result, "items", None)
        images = getattr(result, "images", None) or getattr(result, "images_content_metadata", None)
        # Markdown pages.
        if md is not None:
            pg = getattr(md, "pages", None)
            if isinstance(pg, list):
                for i, p in enumerate(pg, start=1):
                    pages.append(i)
                    t = getattr(p, "markdown", None) or (p.get("markdown") if isinstance(p, dict) else None) or ""
                    if t:
                        # Page markers ride along the joined markdown: the
                        # extractor (and diagram page-overlap) can only cite
                        # pages it can see in the text.
                        markdown_parts.append(f"<!-- page {i} -->\n{t}")
            elif isinstance(md, str):
                markdown_parts.append(md)
            elif isinstance(md, dict):
                for k in ("markdown", "text"):
                    if md.get(k):
                        markdown_parts.append(str(md[k]))
        # Text fallback.
        if not markdown_parts:
            tx = getattr(result, "text", None)
            if isinstance(tx, str) and tx.strip():
                markdown_parts.append(tx)
        # Figures from images metadata.
        if isinstance(images, list):
            for idx, im in enumerate(images):
                if isinstance(im, dict):
                    page = int(im.get("page") or im.get("page_number") or 1)
                    did = str(im.get("diagram_id") or im.get("image_id") or f"fig-p{page}-{idx+1}")
                    cap = str(im.get("caption") or im.get("alt_text") or "")
                    raw = im.get("image_bytes") or im.get("data")
                    fig: dict = {
                        "diagram_id": did,
                        "page": page,
                        "image_path": f"/static/diagrams/{did}.png",
                        "caption": cap,
                    }
                    if isinstance(raw, str) and raw.strip():
                        fig["image_base64"] = raw.strip()
                    figures.append(fig)
        # Items may carry image refs with page overlap.
        if isinstance(items, list) and not figures:
            for idx, it in enumerate(items):
                d = it if isinstance(it, dict) else getattr(it, "model_dump", lambda: {})()
                if not isinstance(d, dict):
                    continue
                if str(d.get("type") or "").lower() in ("image", "figure", "diagram"):
                    page = int(d.get("page") or 1)
                    did = str(d.get("diagram_id") or f"fig-p{page}-{idx+1}")
                    figures.append(
                        {
                            "diagram_id": did,
                            "page": page,
                            "image_path": f"/static/diagrams/{did}.png",
                            "caption": str(d.get("caption") or d.get("text") or "")[:500],
                        }
                    )
    except Exception as e:
        raise RuntimeError(f"live result conversion failed: {e}")
    markdown = "\n\n".join(markdown_parts).strip()
    if not markdown:
        raise RuntimeError("live parse returned empty markdown")
    if not pages:
        pages = list(range(1, 6))
    return {
        "file": filename,
        "tier": tier,
        "images_to_save": list(IMAGES_TO_SAVE),
        "expand": list(EXPAND),
        "markdown": markdown,
        "figures": figures,
        "pages": pages,
    }


def _live_parse_legacy(pdf_bytes: bytes, filename: str, tier: str) -> dict:
    """Fallback for the legacy `llama-parse` package (LlamaParse reader)."""
    from llama_parse import LlamaParse  # type: ignore

    api_key = config.get_llama_key()
    if not api_key:
        raise RuntimeError("no LLAMA_CLOUD_API_KEY")
    parser = LlamaParse(
        api_key=api_key,
        result_type="markdown",
        tier=tier,  # type: ignore[call-arg]
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        docs = parser.load_data(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    parts = []
    for d in docs or []:
        t = getattr(d, "text", "") or (d.get("text") if isinstance(d, dict) else "")
        if t:
            parts.append(str(t))
    markdown = "\n\n".join(parts).strip()
    if not markdown:
        raise RuntimeError("legacy live parse returned empty markdown")
    return {
        "file": filename,
        "tier": tier,
        "images_to_save": list(IMAGES_TO_SAVE),
        "expand": list(EXPAND),
        "markdown": markdown,
        "figures": [],
        "pages": list(range(1, len(parts) + 1)) or [1],
    }


def parse_pdf(file: str, pdf_bytes: bytes | None = None) -> dict:
    """Locked §8 name: parse_pdf(file) -> {markdown, figures[]}.

    S1 additive: optional pdf_bytes enables the live LlamaParse path.
    Live tries tier LLAMA_TIER (default agentic, agentic_plus for complex);
    any failure (no key, no SDK, network, empty result) falls back to the
    frozen stub with mode=stub + fallback_reason. Never raises for demo.
    """
    label = (file or "seed-demo.pdf").strip() or "seed-demo.pdf"
    tier = config.get_llama_tier()
    if pdf_bytes is not None and len(pdf_bytes) == 0:
        pdf_bytes = None
    if pdf_bytes is not None and len(pdf_bytes) > config.MAX_PDF_BYTES:
        stub = llamaparse_stub(label)
        reason = f"pdf over {config.MAX_PDF_BYTES} bytes — stub fallback"
        log.warning("parse: %s", reason)
        return _with_mode(stub, "stub", reason)
    # Keyless or label-only (frozen /upload + seed-load path): stub, no SDK import.
    if not config.is_llama_live() or pdf_bytes is None:
        stub = llamaparse_stub(label)
        reason = "stub-default (no live key)" if not config.is_llama_live() else "stub (label-only, no bytes)"
        # llamaparse_stub already carries mode/fallback; normalise tier.
        stub["tier"] = tier
        stub["mode"] = "stub"
        stub["fallback_reason"] = reason
        return stub
    # Live attempt.
    try:
        try:
            live = _live_parse_via_llama_cloud(bytes(pdf_bytes), label, tier)
        except ImportError:
            live = _live_parse_legacy(bytes(pdf_bytes), label, tier)
        _save_screenshots(live.get("figures") or [])
        log.info("parse: live ok file=%s tier=%s figs=%d", label, tier, len(live.get("figures") or []))
        return _with_mode(live, "live", "")
    except Exception as e:
        reason = f"live parse failed, stub fallback: {type(e).__name__}: {str(e)[:200]}"
        log.warning("parse: %s", reason)
        stub = llamaparse_stub(label)
        stub["tier"] = tier
        stub["mode"] = "stub"
        stub["fallback_reason"] = reason
        return stub


def parse_status() -> dict:
    """Additive health fragment: {llama: live|stub}."""
    return config.llama_status()


# Back-compat: some callers import parse_pdf from parse.
__all__ = ["llamaparse_stub", "parse_pdf", "parse_status"]
