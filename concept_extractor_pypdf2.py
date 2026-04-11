"""
DEPRECATED — Use `from core import ...` instead.
This file exists for backward compatibility during migration.
Will be removed in a future version.

Migration guide:
    OLD: from concept_extractor_pypdf2 import extract_concepts_from_files
    NEW: from core import extract_concepts_from_files
"""

from core.extraction import (  # noqa: F401
    extract_text_from_pdf,
    build_extraction_prompt,
    extract_json_from_text,
    extract_concepts_from_files,
)
from core.graph_ops import (  # noqa: F401
    save_confirmed_concepts,
    load_graph_data,
    DATA_DIR,
    OUTPUT_DIR,
    GRAPH_DATA_PATH,
)
