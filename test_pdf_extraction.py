"""
test_pdf_extraction.py — Test PDF concept extraction using LM Studio directly.

No Flask needed. Just reads the PDF and sends it to LM Studio.

Run with: python test_pdf_extraction.py
Requires: LM Studio running at http://localhost:1234
"""
import PyPDF2
import httpx
import json
import re
import time
from pathlib import Path

LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "gemma-4-e4b-uncensored-hauhaucs-aggressive"

UPLOADS_DIR = Path(__file__).parent / "uploads"
PDF_FILES = list(UPLOADS_DIR.glob("*.pdf"))

if not PDF_FILES:
    print("❌ No PDF found in uploads/")
    exit(1)

PDF_FILE = PDF_FILES[0]


def call_lm(prompt: str) -> str:
    """Send prompt to LM Studio and return response."""
    start = time.time()
    try:
        resp = httpx.post(
            LMSTUDIO_URL,
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=60.0
        )
        elapsed = time.time() - start
        result = resp.json()["choices"][0]["message"]["content"]
        return result, elapsed
    except Exception as e:
        return f"ERROR: {e}", 0


def extract_text(pdf_path: Path) -> str:
    """Extract text from PDF."""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        return "".join([page.extract_text() or "" for page in reader.pages])


def extract_concepts(pdf_text: str) -> list:
    """Extract concepts from PDF text using LM Studio."""
    prompt = f"""You are an educational AI extracting key concepts from a learning document.

Extract the main HEADINGS and their definitions from this text.

RULES:
1. Extract 5-10 key terms that are ESSENTIAL for understanding this topic
2. For each term, provide the exact definition from the text
3. Include the source text snippet (1-2 sentences) that defines each term
4. Focus on broad structural concepts

Respond in JSON format only:
[
  {{
    "concept": "Term1",
    "definition": "Definition from text",
    "source_text": "Exact quote from document"
  }},
  ...
]

TEXT:
{pdf_text[:8000]}

Extract concepts now:"""

    response, elapsed = call_lm(prompt)
    return response, elapsed


def parse_json_response(text: str) -> list:
    """Try to parse JSON from LLM response."""
    # Try to find JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to parse entire response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def main():
    print("=" * 60)
    print("PDF Concept Extraction Test")
    print("=" * 60)

    # Step 1: Check LM Studio
    print("\n[1] Checking LM Studio...")
    try:
        resp = httpx.get(f"{LMSTUDIO_URL}/models", timeout=5)
        models = resp.json().get("data", [])
        model_names = [m.get("id", "?") for m in models]
        print(f"   ✅ LM Studio running — Models: {', '.join(model_names)}")
    except Exception as e:
        print(f"   ❌ Cannot connect to LM Studio at {LMSTUDIO_URL}")
        print(f"      Error: {e}")
        print("   Start LM Studio Local Server first!")
        exit(1)

    # Step 2: Read PDF
    print(f"\n[2] Reading PDF: {PDF_FILE.name}")
    pdf_text = extract_text(PDF_FILE)
    print(f"   ✅ Extracted {len(pdf_text):,} characters ({len(pdf_text.split()):,} words)")
    print(f"   First 200 chars: {pdf_text[:200]}...")

    # Step 3: Extract concepts
    print(f"\n[3] Extracting concepts (sending to LM Studio)...")
    print("   This may take 10-30 seconds...")
    raw_response, elapsed = extract_concepts(pdf_text)

    print(f"   ⏱️ Response time: {elapsed:.1f}s")

    # Step 4: Parse and display results
    print(f"\n[4] Parsing response...")

    concepts = parse_json_response(raw_response)

    if concepts:
        print(f"   ✅ Parsed {len(concepts)} concepts")
        print(f"\n{'─' * 60}")
        for i, c in enumerate(concepts, 1):
            concept = c.get("concept", "?")
            definition = c.get("definition", "")
            source = c.get("source_text", "")
            print(f"\n   {i}. {concept}")
            print(f"      Definition: {definition[:100]}{'...' if len(definition) > 100 else ''}")
            if source:
                print(f"      Source: {source[:80]}{'...' if len(source) > 80 else ''}")
        print(f"\n{'─' * 60}")
    else:
        print(f"   ❌ Failed to parse JSON from response")
        print(f"   Raw response (first 500 chars):")
        print(f"   {raw_response[:500]}")

    # Save raw response for debugging
    output_file = Path(__file__).parent / "test_extraction_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "pdf": PDF_FILE.name,
            "response_time_s": round(elapsed, 1),
            "raw_response": raw_response,
            "parsed_concepts": concepts if concepts else None
        }, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Raw response saved to: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
