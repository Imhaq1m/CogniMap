"""
CogniMap Concept Extraction Module — Docling Version
Uses Docling for layout-aware PDF extraction with heading hierarchy.
"""

import json
import os
from pathlib import Path
from typing import Optional

from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel

# Configuration
DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
CONCEPT_CACHE_DIR = OUTPUT_DIR / "concept_cache"
GRAPH_DATA_PATH = OUTPUT_DIR / "graph_data.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CONCEPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_text_and_structure(pdf_path: Path) -> dict:
    """
    Extract PDF content using Docling's layout analysis.
    
    Returns:
        dict with 'headings', 'concepts', 'source', 'page_count'
    """
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    doc = result.document
    
    # Extract headings with hierarchy
    headings = _extract_headings(doc)
    
    # Extract concepts under each heading
    concepts = _extract_concepts(doc, headings)
    
    return {
        "headings": headings,
        "concepts": concepts,
        "source": pdf_path.name,
        "page_count": len(doc.pages) if hasattr(doc, 'pages') else 0
    }


def _extract_headings(doc) -> list:
    """
    Extract heading hierarchy from Docling document.
    
    Returns list of heading dicts with level, text, page, children.
    """
    headings = []
    current_heading = None
    
    # Iterate through document items
    for item in doc.texts:
        # Check if item is a heading/section header
        if item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]:
            heading = {
                "level": getattr(item, 'level', 1),  # Default to level 1 if not specified
                "name": item.text.strip(),
                "page": item.page_no + 1 if hasattr(item, 'page_no') else 1,
                "source": "",  # Will be filled later
                "concepts": []
            }
            
            # Build hierarchy: attach to parent if nested
            if current_heading and heading["level"] > current_heading["level"]:
                # This is a sub-heading of current_heading
                current_heading["concepts"].append(heading)
            else:
                # Top-level heading
                headings.append(heading)
                current_heading = heading
    
    return headings


def _extract_concepts(doc, headings: list) -> list:
    """
    Extract text concepts and group them under headings.
    
    Uses Docling's reading order to associate text blocks with nearest heading.
    """
    all_concepts = []
    
    # Flatten headings to get all concept containers
    def flatten_headings(heading_list):
        result = []
        for h in heading_list:
            result.append(h)
            if h.get("concepts"):
                result.extend(flatten_headings(h["concepts"]))
        return result
    
    all_heading_containers = flatten_headings(headings)
    
    # Group text blocks by nearest heading
    current_heading_idx = 0
    
    for item in doc.texts:
        # Skip headings themselves
        if item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]:
            continue
        
        # Only process paragraphs/text blocks
        if item.label in [DocItemLabel.TEXT, DocItemLabel.PARAGRAPH]:
            # Extract key concepts from text (simple keyword extraction)
            text_concepts = _extract_keywords(item.text)
            
            # Associate with current heading
            if all_heading_containers and current_heading_idx < len(all_heading_containers):
                container = all_heading_containers[current_heading_idx]
                for concept in text_concepts:
                    concept_entry = {
                        "name": concept,
                        "source": "",  # Will be filled
                        "page": item.page_no + 1 if hasattr(item, 'page_no') else 1
                    }
                    container["concepts"].append(concept_entry)
                    all_concepts.append(concept_entry)
    
    return all_concepts


def _extract_keywords(text: str) -> list:
    """
    Extract key concepts from text block.
    
    Simple implementation: extracts noun phrases and technical terms.
    In production, this could use LLM or NLP library.
    """
    # Simple keyword extraction
    # Remove common words and extract meaningful terms
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
        'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
        'same', 'so', 'than', 'too', 'very', 's', 't', 'just', 'don', 'now',
        'and', 'but', 'if', 'or', 'because', 'until', 'while', 'about', 'against'
    }
    
    # Split text into sentences
    sentences = text.replace('.', '\n').replace('!', '\n').replace('?', '\n').split('\n')
    
    keywords = []
    for sentence in sentences:
        words = sentence.strip().split()
        # Extract multi-word phrases (2-3 words) that might be concepts
        for i in range(len(words)):
            # Single technical terms (capitalized or long words)
            word = words[i].strip('.,;:()[]{}"\'')
            if word.lower() not in stop_words and (word[0].isupper() or len(word) > 5):
                if word not in keywords:
                    keywords.append(word)
            
            # Two-word phrases
            if i + 1 < len(words):
                phrase = f"{words[i]} {words[i+1]}".strip('.,;:()[]{}"\'')
                if len(phrase) > 10 and phrase.lower() not in [s.lower() for s in keywords]:
                    # Check if phrase contains non-stop words
                    phrase_words = phrase.split()
                    if not all(w.lower() in stop_words for w in phrase_words):
                        keywords.append(phrase)
    
    return keywords[:10]  # Limit to 10 concepts per text block


def extract_concepts_from_files(file_list: list, state_manager=None) -> dict:
    """
    Extract hierarchical concepts from a list of PDF files using Docling.
    
    Args:
        file_list: List of PDF filenames
        state_manager: Optional PipelineState instance for progress tracking
    
    Returns:
        Dictionary with 'headings' key containing tree structure
    """
    all_headings = []
    
    for idx, filename in enumerate(file_list):
        pdf_path = DATA_DIR / filename
        
        if state_manager:
            state_manager.update(
                f"📄 Processing {filename} ({idx+1}/{len(file_list)})...",
                f"Starting Docling extraction for {filename}"
            )
        
        if not pdf_path.exists():
            print(f"Warning: PDF not found: {pdf_path}")
            continue
        
        # Extract text and structure using Docling
        if state_manager:
            state_manager.update(f"📖 Analyzing document structure with Docling...")
        
        try:
            result = extract_text_and_structure(pdf_path)
        except Exception as e:
            print(f"Error extracting from {filename}: {e}")
            if state_manager:
                state_manager.update(f"❌ Error: {str(e)}")
            continue
        
        # Process headings
        headings = result.get("headings", [])
        concepts = result.get("concepts", [])
        
        # Add source info
        for heading in headings:
            heading["source"] = filename
            for concept in heading.get("concepts", []):
                concept["source"] = filename
        
        all_headings.extend(headings)
        
        if state_manager:
            heading_count = len(headings)
            concept_count = len(concepts)
            state_manager.update(
                f"✅ Extracted {concept_count} concepts under {heading_count} headings from {filename}"
            )
    
    # Save to cache
    cache_data = {
        "headings": all_headings,
        "source_files": file_list,
        "extraction_method": "docling",
        "timestamp": str(Path(__file__).parent / "output")
    }
    
    cache_path = OUTPUT_DIR / "extracted_concepts.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)
    
    return {"headings": all_headings}


def save_confirmed_concepts(concepts: list):
    """Save user-confirmed concepts to graph data file."""
    graph_data = {
        "concepts": concepts,
        "relationships": [],
        "confirmed_at": str(__import__('datetime').datetime.now().isoformat()),
        "extraction_method": "docling"
    }
    
    with open(GRAPH_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
    
    return graph_data


def load_graph_data() -> dict:
    """Load confirmed graph data."""
    if not GRAPH_DATA_PATH.exists():
        return {"concepts": [], "relationships": []}
    
    try:
        with open(GRAPH_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"concepts": [], "relationships": []}
