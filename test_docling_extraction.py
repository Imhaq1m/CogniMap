"""Test Docling extraction with a sample PDF."""

from concept_extractor_docling import extract_text_and_structure
from pathlib import Path

# Test with an existing PDF
pdf_path = Path("uploads/CSCI 4340 2. Evaluating Model Performance.pdf")

if pdf_path.exists():
    print(f"📄 Testing Docling extraction with: {pdf_path.name}")
    print("=" * 60)
    
    try:
        result = extract_text_and_structure(pdf_path)
        
        print(f"✅ Extraction successful!")
        print(f"📊 Source: {result['source']}")
        print(f"📄 Pages: {result['page_count']}")
        print(f"📑 Headings found: {len(result['headings'])}")
        
        # Show heading hierarchy
        def print_headings(headings, indent=0):
            for h in headings:
                prefix = "  " * indent
                level_icon = "#" * h.get('level', 1)
                print(f"{prefix}{level_icon} {h['name']} (page {h.get('page', '?')})")
                if h.get('concepts'):
                    print(f"{prefix}  Concepts ({len(h['concepts'])}):")
                    for c in h['concepts'][:3]:  # Show first 3
                        print(f"{prefix}    • {c.get('name', 'unnamed')}")
                    if len(h['concepts']) > 3:
                        print(f"{prefix}    ... and {len(h['concepts']) - 3} more")
                
                # Recurse into nested headings
                if h.get('concepts'):
                    # Filter for nested headings (those with 'level' key)
                    nested = [c for c in h['concepts'] if 'level' in c]
                    print_headings(nested, indent + 1)
        
        print("\n📋 Heading Hierarchy:")
        print("-" * 60)
        print_headings(result['headings'])
        
        print(f"\n🔢 Total concepts extracted: {len(result['concepts'])}")
        
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"❌ PDF not found: {pdf_path}")
    print("Available PDFs in uploads/:")
    for p in Path("uploads/").glob("*.pdf"):
        print(f"  • {p.name}")
