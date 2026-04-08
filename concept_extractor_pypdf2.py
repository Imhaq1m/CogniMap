"""
Concept Extraction Module — Uses LM Studio to extract hierarchical concepts from PDFs.
"""

import json
import httpx
import os
from pathlib import Path
from PyPDF2 import PdfReader

# Configuration
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1/chat/completions")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "gemma-4-e4b-uncensored-hauhaucs-aggressive")

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
CONCEPT_CACHE_DIR = OUTPUT_DIR / "concept_cache"
GRAPH_DATA_PATH = OUTPUT_DIR / "graph_data.json"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CONCEPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using PyPDF2."""
    try:
        reader = PdfReader(str(pdf_path))
        text = ""
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {page_num} ---\n"
                text += page_text
        return text
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def call_lmstudio(prompt: str, timeout: int = 180) -> str:
    """Call LM Studio API and return response text."""
    try:
        response = httpx.post(
            LMSTUDIO_URL,
            json={
                "model": LMSTUDIO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4000
            },
            timeout=timeout
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        raise Exception(f"LM Studio timed out after {timeout}s")
    except Exception as e:
        raise Exception(f"LM Studio API error: {str(e)}")


def build_extraction_prompt(pdf_text: str, filename: str) -> str:
    """Build the prompt for concept extraction."""
    # Truncate if too long (LM Studio context limits)
    max_chars = 12000
    if len(pdf_text) > max_chars:
        pdf_text = pdf_text[:max_chars]
        pdf_text += "\n\n[Text truncated due to length...]"
    
    return f"""You are a concept extraction AI for CogniMap, a learning tool.

Analyze the following PDF text and extract key concepts organized by their main headings and subheadings. Return a JSON object with this exact structure:

{{
  "headings": [
    {{
      "name": "Main Heading 1",
      "source": "{filename}",
      "concepts": [
        {{"name": "Sub-concept 1.1", "source": "{filename}", "page": 3}},
        {{"name": "Sub-concept 1.2", "source": "{filename}", "page": 5}}
      ]
    }}
  ]
}}

Rules:
1. Extract 5-15 key concepts total
2. Group concepts under their main headings (2-5 headings)
3. Include page numbers where each concept appears (estimate from the text markers)
4. Include the source filename
5. Use exact terminology from the PDF
6. Return ONLY valid JSON, no markdown blocks, no explanations
7. Do NOT include the ```json wrapper

PDF Text:
{pdf_text}"""


def extract_json_from_text(text: str) -> dict:
    """Robustly extract JSON from LLM response text."""
    try:
        text = text.strip()
        # Remove markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        # Find the first '{' and last '}' to handle conversational noise
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        return json.loads(text)
    except Exception as e:
        print(f"JSON extraction failed: {e}")
        print(f"Raw text (first 500 chars): {text[:500]}")
        return {"headings": []}


def extract_concepts_from_files(file_list: list, state_manager=None) -> dict:
    """
    Extract hierarchical concepts from a list of PDF files.

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
                f"Starting extraction for {filename}"
            )

        if not pdf_path.exists():
            print(f"Warning: PDF not found: {pdf_path}")
            continue

        # Step 1: Extract text from PDF
        if state_manager:
            state_manager.update(f"📖 Reading text from {filename}...")

        pdf_text = extract_text_from_pdf(pdf_path)

        if not pdf_text.strip():
            print(f"Warning: No text extracted from {filename}")
            continue

        # Step 2: Call LM Studio to extract concepts
        if state_manager:
            state_manager.update(f"🤖 Calling AI to extract concepts from {filename}... (this may take 1-3 minutes)")

        prompt = build_extraction_prompt(pdf_text, filename)
        response_text = call_lmstudio(prompt, timeout=180)
        
        # DEBUG: Save raw LLM response for debugging
        debug_path = OUTPUT_DIR / "llm_response_debug.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(response_text)
        print(f"[DEBUG] Raw LLM response saved to {debug_path}")

        # Step 3: Parse JSON response
        if state_manager:
            state_manager.update(f"🔍 Parsing AI response for {filename}...")

        result = extract_json_from_text(response_text)
        
        # DEBUG: Log parsed result
        print(f"[DEBUG] Parsed result keys: {list(result.keys())}")
        if result.get("headings"):
            print(f"[DEBUG] Found {len(result['headings'])} headings")
        else:
            print(f"[DEBUG] No 'headings' key found in result")

        if result.get("headings"):
            all_headings.extend(result["headings"])
            if state_manager:
                heading_count = len(result["headings"])
                concept_count = sum(len(h.get("concepts", [])) for h in result["headings"])
                state_manager.update(f"✅ Extracted {concept_count} concepts under {heading_count} headings from {filename}")
        else:
            if state_manager:
                state_manager.update(f"⚠️ No concepts found in {filename}")
    
    # Save to cache
    cache_data = {
        "headings": all_headings,
        "source_files": file_list,
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
        "confirmed_at": str(__import__('datetime').datetime.now().isoformat())
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
