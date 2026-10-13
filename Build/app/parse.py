"""CogniMap Step 1 — LlamaParse stub (Locks §0).

Locked parsing: LlamaParse API tier `agentic` (or `agentic_plus` for complex
pages) with `images_to_save: ["screenshot"]`,
`expand: ["text","markdown","items","images_content_metadata"]`.
Cost-optimizer allowed. Real keys deferred — UI builds against this stub + seed.
Pipeline: PDF -> LlamaParse (sentences/pages/figures) -> Extractor LLM (§1).
"""
from __future__ import annotations


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
    }


def parse_pdf(file: str) -> dict:
    """Locked §8 name: parse_pdf(file) -> {markdown, figures[]}.

    Alias to llamaparse_stub (LlamaParse agentic tier stub); real impl swaps
    in the API call with no UI change.
    """
    return llamaparse_stub(file)


# Back-compat: some callers import parse_pdf from parse.
__all__ = ["llamaparse_stub", "parse_pdf"]
