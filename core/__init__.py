"""
CogniMap Core Module — Shared infrastructure used by all levels.

Usage:
    from core import check_level_access, call_lmstudio, load_graph_data
    from core import extract_concepts_from_files, pipeline_state
"""

# LLM
from core.llm import call_lmstudio, LMSTUDIO_URL, LMSTUDIO_MODEL

# Progress / Gate Enforcement
from core.progress import (
    check_level_access,
    get_bloom_progress,
    update_bloom_progress,
    complete_level,
    get_current_level,
)

# Graph Operations
from core.graph_ops import (
    load_graph_data,
    save_confirmed_concepts,
    get_concepts_for_level,
    add_edge,
    get_defended_edge_count,
    defend_edge,
    update_edge_challenge,
    get_vis_nodes,
    get_vis_edges,
    GRAPH_DATA_PATH,
    OUTPUT_DIR,
)

# PDF / Concept Extraction
from core.extraction import (
    extract_text_from_pdf,
    build_extraction_prompt,
    extract_json_from_text,
    extract_concepts_from_files,
)

# Pipeline State
from core.pipeline_state import pipeline_state, PipelineState
