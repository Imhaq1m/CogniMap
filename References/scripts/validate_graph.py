import json
import fitz  # PyMuPDF
import re
from pathlib import Path

# Configuration
GRAPH_DATA = Path("output/graph_data.json")
DATA_DIR = Path("data")

def run_validation(graph_data=None, target_node=None, target_edge=None):
    """
    Modular validation engine for CogniMap.
    Returns a structured report of node and edge trust scores.
    Supports targeted validation for performance on manual edits.
    """
    if graph_data is None:
        if not GRAPH_DATA.exists(): return {"nodes": {}, "edges": {}}
        try:
            with open(GRAPH_DATA, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
        except Exception:
            return {"nodes": {}, "edges": {}}

    concepts = graph_data.get("concepts", [])
    relationships = graph_data.get("relationships", [])
    
    node_validity = {}
    edge_validity = {}

    # Caches - Local to this run to ensure fresh state and memory safety
    doc_cache = {}
    page_text_cache = {} # (pdf_name, page_num) -> text

    def get_doc(pdf_name):
        pdf_path = DATA_DIR / pdf_name
        if not pdf_path.exists(): return None
        if pdf_name not in doc_cache:
            try:
                doc_cache[pdf_name] = fitz.open(str(pdf_path))
            except Exception:
                return None
        return doc_cache[pdf_name]

    def get_page_text(pdf_name, page_num):
        cache_key = (pdf_name, page_num)
        if cache_key in page_text_cache:
            return page_text_cache[cache_key]
        
        # Memory safety: [QA-19] Lower limit to 200 pages
        if len(page_text_cache) > 200:
            page_text_cache.clear()

        doc = get_doc(pdf_name)
        if doc and 0 <= page_num < len(doc):
            text = doc[page_num].get_text().lower()
            page_text_cache[cache_key] = text
            return text
        return ""

    def word_match(target, text):
        """
        [MIGRATION] Improved grounding engine.
        Tier 1: Literal whole-word match.
        Tier 2: Semantic/Staged match with word boundary safety.
        """
        if not target or not text: return False
        target_lower = target.lower()
        
        # Tier 1: Strict word match
        pattern = rf"\b{re.escape(target_lower)}\b"
        if re.search(pattern, text): return True
        
        # [QA-18] Tier 2: Staged match with boundary enforcement
        target_clean = re.sub(r'[^a-z0-9]', '', target_lower)
        if len(target_clean) < 6: return False # Short concepts must match Tier 1
        
        # We check if the cleaned target appears as a "word" in cleaned text.
        # This is hard with just regex if we want to avoid substring matches in long words.
        # Strategy: Match target_clean if it is surrounded by non-alphanumeric or starts/ends.
        text_clean = re.sub(r'[^a-z0-9]', ' ', text) # Replace separators with space
        pattern_clean = rf"\b{re.escape(target_clean)}\b"
        if re.search(pattern_clean, text_clean):
            return True
            
        return False

    # [CONCURRENCY REVIEW] Resource safety: ensure all doc handles are closed even on error.
    try:
        # 1. Validate Nodes (Grounding)
        for c in concepts:
            cid = c.get("id")
            if not cid: continue
            
            # Performance Optimization: Skip already verified nodes unless targeted
            if not target_node and not target_edge:
                if c.get("validation_status") == "verified" and not c.get("manually_edited"):
                    node_validity[cid] = {"score": c.get("ai_confidence_score", 1.0), "status": "verified"}
                    continue

            # Skip if targeted and this isn't the target
            if target_node and cid != target_node:
                continue

            score = 0.4 # Default uncited score
            status = "uncited"
            
            refs = c.get("page_references", [])
            # [FIX] Handle mixed-type references (int from new extractor, string from old/manual)
            normalized_refs = []
            sources = c.get("sources", [])
            primary_source = sources[0] if sources else None
            
            for r_raw in (refs if isinstance(refs, list) else [refs]):
                if isinstance(r_raw, int) and primary_source:
                    normalized_refs.append(f"{primary_source}:{r_raw}")
                elif isinstance(r_raw, str):
                    normalized_refs.append(r_raw)
            
            if not normalized_refs and c.get("source_ref"):
                normalized_refs = [c["source_ref"]]

            if normalized_refs:
                best_score = 0.0
                best_status = "uncited"
                
                for ref in normalized_refs:
                    if ":" in ref:
                        try:
                            pdf_name, page_str = ref.rsplit(":", 1)
                            page_num = int(page_str) - 1
                            page_text = get_page_text(pdf_name, page_num)
                            
                            if page_text:
                                if word_match(cid, page_text):
                                    current_score = 1.0
                                    current_status = "verified"
                                else:
                                    # Fallback to loose containment if Tier 2 word_match failed
                                    if cid.lower() in page_text:
                                        current_score = 0.6
                                        current_status = "partial_match"
                                    else:
                                        current_score = 0.3
                                        current_status = "not_found_on_page"
                            else:
                                current_score = 0.3
                                current_status = "invalid_ref"
                        except Exception:
                            current_score = 0.2
                            current_status = "error"
                    else:
                        current_score = 0.4
                        current_status = "malformed_ref"
                    
                    if current_score > best_score:
                        best_score = current_score
                        best_status = current_status
                
                score = best_score
                status = best_status
            elif c.get("is_anchor"):
                score = 0.6 
                status = "anchor_unverified"

            node_validity[cid] = {"score": score, "status": status}

        # 2. Validate Edges (Link Integrity)
        for r in relationships:
            s, t = r.get("source"), r.get("target")
            if not s or not t: continue
            eid = f"{s}_{t}"
            
            # Performance Optimization: Skip already verified edges unless targeted
            if not target_node and not target_edge:
                if r.get("validation_status") == "verified":
                    edge_validity[eid] = {"score": r.get("ai_confidence_score", 1.0), "status": "verified"}
                    continue

            # Skip if targeted and this isn't the target
            if target_edge and eid != target_edge:
                continue

            is_synthesized = r.get("synthesized", False)
            
            if is_synthesized:
                s_data = next((c for c in concepts if c['id'] == s), {})
                t_data = next((c for c in concepts if c['id'] == t), {})
                s_sources = set(s_data.get("sources", []))
                t_sources = set(t_data.get("sources", []))
                
                if s_sources & t_sources:
                    edge_validity[eid] = {"score": 0.8, "status": "synthesized_strong"}
                else:
                    edge_validity[eid] = {"score": 0.6, "status": "synthesized"}
                continue

            refs = r.get("page_references", [])
            if not refs and r.get("source_ref"):
                refs = [r["source_ref"]]

            if refs:
                best_score = 0.0
                best_status = "uncited"

                for ref in refs:
                    if ":" in ref:
                        try:
                            pdf_name, page_str = ref.rsplit(":", 1)
                            page_num = int(page_str) - 1
                            
                            found_s, found_t = False, False
                            # Look in a 3-page window for the relationship evidence
                            for p in range(page_num - 1, page_num + 2):
                                text = get_page_text(pdf_name, p)
                                if not text: continue
                                if word_match(s, text): found_s = True
                                if word_match(t, text): found_t = True
                            
                            if found_s and found_t:
                                current_score = 1.0
                                current_status = "verified"
                            elif found_s or found_t:
                                current_score = 0.5
                                current_status = "partial_grounding"
                            else:
                                current_score = 0.3
                                current_status = "not_found_nearby"
                        except Exception:
                            current_score = 0.2
                            current_status = "error"
                    
                    if current_score > best_score:
                        best_score = current_score
                        best_status = current_status
                
                edge_validity[eid] = {"score": best_score, "status": best_status}
            else:
                edge_validity[eid] = {"score": 0.4, "status": "uncited"}
    finally:
        # [CONCURRENCY REVIEW] Ensure all files are closed regardless of logic success.
        for doc in doc_cache.values():
            try:
                doc.close()
            except: pass
        doc_cache.clear()
        page_text_cache.clear()

    return {"nodes": node_validity, "edges": edge_validity}
