import os
import json
import re
import time
import hashlib
import concurrent.futures
import fitz  # PyMuPDF
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from filelock import FileLock
import datetime
import random
from collections import deque, defaultdict

# Configuration
load_dotenv(override=True)
DATA_DIR = Path("data")
CACHE_DIR = Path("output/concept_cache")
OUTPUT_FILE = Path("output/graph_data.json")
LOCK_FILE = Path("output/graph_data.json.lock")

# Gemini Config
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# Performance Tuning
MAX_WORKERS = 3   # Parallel PDFs
PAGES_PER_CHUNK = 15  # Optimal for coherence


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def extract_json_from_text(text: str) -> dict:
    """Robustly extract JSON from LLM response text, handling markdown blocks."""
    try:
        text = text.strip()
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
    except Exception:
        return {}


def call_gemini_with_retry(client, model, contents, config, max_retries=4):
    """
    Retry wrapper for Gemini API calls with exponential back-off and jitter.
    [FIX-B3] Caps the delay at 60 seconds to prevent invisible multi-minute stalls.
    """
    delay = 5
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(
                code in error_str
                for code in ["429", "500", "503", "rate", "quota", "overloaded"]
            )
            if is_retryable and attempt < max_retries - 1:
                time.sleep(delay + random.uniform(0, 2))
                # [FIX-B3] Cap delay at 60 s to prevent multi-minute invisible stalls.
                # Old code: delay *= 2  (unbounded — could reach 40+ seconds by attempt 4)
                delay = min(delay * 2, 60)
            else:
                raise


def get_pdf_hash(pdf_path: Path) -> str:
    return hashlib.md5(pdf_path.read_bytes()).hexdigest()


def get_cache_paths(pdf_path: Path, cache_dir: Path):
    safe_name = pdf_path.stem
    return (cache_dir / f"{safe_name}.json", cache_dir / f"{safe_name}.meta.json")


def is_cache_valid(pdf_path: Path, cache_dir: Path, current_hash: str = None) -> bool:
    content_path, meta_path = get_cache_paths(pdf_path, cache_dir)
    if not content_path.exists() or not meta_path.exists():
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return False
    check_hash = current_hash or get_pdf_hash(pdf_path)
    return meta.get("hash") == check_hash


def read_cache(pdf_path: Path, cache_dir: Path) -> dict:
    content_path, _ = get_cache_paths(pdf_path, cache_dir)
    with open(content_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_cache_with_hash(pdf_path: Path, cache_dir: Path, content: dict, pdf_hash: str):
    """
    [FIX-B2] Atomic dual-file cache write.

    Old code wrote content_path then meta_path in two independent open() calls with no
    atomicity guarantee. A crash between the two writes left the cache inconsistent:
    - If content written but meta not → is_cache_valid() passes the exist check, reads meta,
      fails the hash check, triggers a redundant (and expensive) API re-extraction.
    - If meta written but content not → read_cache() crashes with FileNotFoundError.

    Fix: Write each file via a .tmp intermediate and rename atomically.
    Write ORDER matters: content FIRST, then meta. This ensures that if meta exists, content
    is always present and complete. If a crash occurs after content but before meta, the next
    run's is_cache_valid() finds no meta and re-extracts cleanly.
    """
    content_path, meta_path = get_cache_paths(pdf_path, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Atomically write content file.
    content_tmp = content_path.with_suffix('.tmp')
    with open(content_tmp, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
    content_tmp.replace(content_path)  # Atomic on POSIX; near-atomic on Windows via NTFS

    # Step 2: Atomically write meta file (the "guard" — only present when content is valid).
    meta_tmp = meta_path.with_suffix('.tmp')
    with open(meta_tmp, "w", encoding="utf-8") as f:
        json.dump({
            "hash": pdf_hash,
            "source": pdf_path.name,
            "cached_at": datetime.datetime.now().isoformat()
        }, f, indent=2)
    meta_tmp.replace(meta_path)


def chunk_pdf_by_pages(pdf_path: Path, pages_per_chunk: int = PAGES_PER_CHUNK) -> list:
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()
    chunks = []
    start = 0
    while start < total_pages:
        end = min(start + pages_per_chunk, total_pages)
        chunks.append({"start_page": start + 1, "end_page": end, "overlap_context": start > 0})
        if total_pages <= pages_per_chunk:
            break
        start += pages_per_chunk - 2
    return chunks


# ---------------------------------------------------------------------------
# PDF Extraction (per-file worker)
# ---------------------------------------------------------------------------

def extract_concepts_from_pdf(pdf_path: Path, api_key: str) -> dict:
    # [QA-12] Create worker-specific client for thread safety.
    client = genai.Client(api_key=api_key)

    # [QA-13] Cache hash once at start to avoid re-reading the file repeatedly.
    pdf_bytes = pdf_path.read_bytes()
    pdf_hash = hashlib.md5(pdf_bytes).hexdigest()

    if is_cache_valid(pdf_path, CACHE_DIR, pdf_hash):
        print(f"  [Cache] Valid hit for {pdf_path.name}")
        return read_cache(pdf_path, CACHE_DIR)

    # Check for partial checkpoint
    checkpoint_file = CACHE_DIR / f"{pdf_path.stem}.checkpoint.json"
    pdf_concepts = {}
    pdf_relationships = []
    start_chunk_idx = 0

    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
                if checkpoint.get("hash") == pdf_hash:
                    pdf_concepts = checkpoint.get("concepts", {})
                    pdf_relationships = checkpoint.get("relationships", [])
                    start_chunk_idx = checkpoint.get("next_chunk", 0)
                    print(f"  [Checkpoint] Resuming {pdf_path.name} from chunk {start_chunk_idx}")
        except Exception:
            pass

    print(f"  [API] Sequential PDF extraction: {pdf_path.name}")
    chunks = chunk_pdf_by_pages(pdf_path)

    gemini_file = client.files.upload(file=pdf_path)
    try:
        # [QA-11] Add timeout to polling to prevent infinite wait on Gemini processing.
        poll_start = time.time()
        while gemini_file.state.name == "PROCESSING":
            if time.time() - poll_start > 180:  # 3 minute timeout
                raise Exception(f"Gemini processing timeout for {pdf_path.name}")
            time.sleep(5)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise Exception(f"Gemini processing failed for {pdf_path.name}")

        failed_chunks = []
        for i in range(start_chunk_idx, len(chunks)):
            chunk = chunks[i]
            print(f"    [Worker] {pdf_path.name} (Chunk {i + 1}/{len(chunks)})...")

            prior_context = ""
            if pdf_concepts and chunk["overlap_context"]:
                ids = list(pdf_concepts.keys())[-20:]
                prior_context = f"Reuse their EXACT names: {', '.join(ids)}"

            prompt = (
                f"Analyze {pdf_path.name} PAGES {chunk['start_page']} to {chunk['end_page']}. "
                f"{prior_context}. Extract exactly 5-10 key computer science concepts and their relationships. "
                "Return a JSON object with this exact structure: "
                "{\"concepts\": [{\"id\": \"Name\", \"description\": \"Definition\", \"type\": \"Core/Intro/Advanced\", \"complexity\": 1-5, \"sources\": [\"Filename.pdf\"], \"page_references\": [page_num]}], "
                "\"relationships\": [{\"source\": \"Name\", \"target\": \"Name\", \"type\": \"PREREQUISITE/HIERARCHICAL\", \"logic\": \"Why?\"}]}"
            )

            chunk_success = False
            for attempt in range(3):
                try:
                    # [FIX] Avoid GenerateContentConfig if it causes 400s; pass config directly
                    response = call_gemini_with_retry(
                        client, model=GEMINI_MODEL, contents=[gemini_file, prompt],
                        config={
                            "temperature": 0.1
                        }
                    )
                    data = extract_json_from_text(response.text)
                    if not data or not data.get("concepts"):
                        raise Exception("No concepts found in JSON response")

                    new_count = 0
                    for c in data.get("concepts", []):
                        cid = c["id"].strip()
                        # [FIX] Ensure sources is always populated for grounding
                        if not c.get("sources"):
                            c["sources"] = [pdf_path.name]

                        if cid not in pdf_concepts:
                            pdf_concepts[cid] = c
                            new_count += 1
                        else:
                            pdf_concepts[cid]["page_references"] = list(set(
                                pdf_concepts[cid].get("page_references", [])
                                + c.get("page_references", [])
                            ))
                    pdf_relationships.extend(data.get("relationships", []))
                    
                    if new_count > 0:
                        print(f"      [Heartbeat] Discovered {new_count} new concepts in chunk {i+1}")

                    # Save Checkpoint
                    with open(checkpoint_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "hash": pdf_hash,
                            "concepts": pdf_concepts,
                            "relationships": pdf_relationships,
                            "next_chunk": i + 1
                        }, f, indent=2)

                    chunk_success = True
                    break
                except Exception as e:
                    print(f"      [Retry {attempt + 1}] Failed: {e}")
                    time.sleep(2)

            if not chunk_success:
                failed_chunks.append(chunk)

        result = {
            "concepts": list(pdf_concepts.values()),
            "relationships": pdf_relationships,
            "partial": len(failed_chunks) > 0
        }
        if not failed_chunks:
            write_cache_with_hash(pdf_path, CACHE_DIR, result, pdf_hash)
            if checkpoint_file.exists():
                checkpoint_file.unlink()
        return result
    finally:
        try:
            client.files.delete(name=gemini_file.name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Global Synthesis & Entity Resolution
# ---------------------------------------------------------------------------

def global_synthesis(concepts_list: list, client) -> dict:
    print(f"[Synthesis] Analyzing {len(concepts_list)} concepts...")
    truncated = False
    if len(concepts_list) > 300:
        print(f"⚠️ [QA-14] Large concept set ({len(concepts_list)}). Truncating synthesis to first 300.")
        truncated = True

    summaries = []
    for c in concepts_list:
        desc = c.get("description", "No description.")[:150]  # Cap description length
        summaries.append(f'- "{c["id"]}": {desc}')

    concept_block = "\n".join(summaries[:300])

    prompt = (
        f"Identify 5-8 high-value cross-topic bridges between these concepts. "
        f"Concepts:\n{concept_block}\n"
        f"Return JSON with a 'bridges' key: a list of relationship objects, each with "
        f"'source', 'target', 'type' (always 'ASSOCIATIVE'), and 'explanation' fields."
    )

    try:
        response = call_gemini_with_retry(
            client, model=GEMINI_MODEL, contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2
            }
        )
        result = extract_json_from_text(response.text)
        result["truncated"] = truncated
        return result
    except Exception as e:
        print(f"[Synthesis] Error: {e}")
        return {"bridges": [], "truncated": truncated}


def resolve_entities(concepts: dict, relationships: list, client) -> tuple:
    """
    Case-insensitive entity resolution via LLM-assisted synonym merging.
    It uses a hierarchical approach by processing in smaller overlapping batches.
    """
    if not concepts:
        return concepts, relationships

    all_ids = list(concepts.keys())
    batch_size = 200
    id_map = {}

    # Process in overlapping batches to catch synonyms across batch boundaries
    for start in range(0, len(all_ids), batch_size - 20):
        batch = all_ids[start:start + batch_size]
        if len(batch) < 2:
            continue

        prompt = (
            f"Identify synonyms or near-duplicate concept names in this list: {json.dumps(batch)}. "
            f"Return JSON with a 'merges' key: a list of objects, each with 'canonical' (the preferred name) "
            f"and 'synonyms' (a list of names to merge into canonical)."
        )
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            )
            merges = extract_json_from_text(response.text).get("merges", [])

            concepts_lower = {k.lower(): k for k in concepts.keys()}

            for m in merges:
                canonical = m.get("canonical")
                if not canonical:
                    continue
                actual_canonical = concepts_lower.get(canonical.lower(), canonical)

                for syn in m.get("synonyms", []):
                    if syn.lower() in concepts_lower:
                        syn_id = concepts_lower[syn.lower()]
                        # Chain mapping: if syn_id was already mapped, redirect the new canonical
                        if syn_id in id_map:
                            id_map[actual_canonical] = id_map[syn_id]
                        else:
                            id_map[syn_id] = actual_canonical
        except Exception:
            continue

    if not id_map:
        return concepts, relationships

    new_concepts = {}
    for cid, concept in concepts.items():
        # Resolve through the chain with cycle detection [QA-15]
        target_id = cid
        visited = set()
        while target_id in id_map and target_id not in visited:
            visited.add(target_id)
            target_id = id_map[target_id]

        if target_id not in new_concepts:
            base = concepts.get(target_id, concept).copy()
            base["id"] = target_id
            new_concepts[target_id] = base
        if cid != target_id:
            t = new_concepts[target_id]
            t["sources"] = list(set(t.get("sources", []) + concept.get("sources", [])))
            t["page_references"] = list(set(
                t.get("page_references", []) + concept.get("page_references", [])
            ))
            # Preserve mastery if merging: keep the higher score to not penalise the student.
            if "mastery_score" in concept and "mastery_score" not in t:
                t["mastery_score"] = concept["mastery_score"]

    new_rels = []
    for rel in relationships:
        s_id, t_id = rel["source"], rel["target"]

        # Follow map chain with cycle detection [QA-15]
        visited_s = set()
        while s_id in id_map and s_id not in visited_s:
            visited_s.add(s_id)
            s_id = id_map[s_id]

        visited_t = set()
        while t_id in id_map and t_id not in visited_t:
            visited_t.add(t_id)
            t_id = id_map[t_id]

        if s_id != t_id:
            rel.update({"source": s_id, "target": t_id})
            new_rels.append(rel)

    return new_concepts, new_rels


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run_extraction():
    if not GEMINI_API_KEY:
        print("[Extraction] No GOOGLE_API_KEY found. Skipping.")
        return
    pdf_files = list(DATA_DIR.glob("*.pdf"))
    if not pdf_files:
        print("[Extraction] No PDF files found in data/. Skipping.")
        return

    # -----------------------------------------------------------------------
    # [FIX-B1] CRITICAL: Lock the read of graph_data.json when loading student data.
    #
    # Old code read OUTPUT_FILE without any FileLock at the start of run_extraction().
    # This created a race window:
    #   1. Student edits a node via /api/update (which acquires the lock, writes the edit,
    #      then releases the lock).
    #   2. run_extraction() reads the file WITHOUT the lock — it may see a partially
    #      written file, or — more likely — it reads BEFORE the edit and misses it entirely.
    #   3. run_extraction() finishes (minutes later), merges the OLD manual_nodes snapshot
    #      (missing the student's latest edit), and writes the file WITH the lock.
    #   4. The student's edit is silently overwritten.
    #
    # Fix: Acquire LOCK_FILE just long enough to snapshot manual_nodes and mastery_data.
    # Release immediately so /api/update requests are not blocked for the full extraction
    # duration (which can be many minutes for large PDFs).
    #
    # [CONCURRENCY REVIEW] The lock is held briefly here (snapshot only), then released.
    # The final write at the end of this function re-acquired the lock. Any /api/update
    # that arrives BETWEEN the snapshot and the final write will be captured by the
    # merge logic below (manual_nodes check). If /api/update arrives AFTER the final
    # write, the student's edit stands on disk and will be read by the next extraction.
    # The one remaining gap (edit arrives after snapshot but before final write) means
    # that specific edit is lost — this is a fundamental TOCTOU issue that cannot be
    # fully eliminated without a full event-sourcing architecture. The lock at least
    # guarantees consistent reads.
    # -----------------------------------------------------------------------
    manual_nodes = {}
    mastery_data = {}

    if OUTPUT_FILE.exists():
        with FileLock(LOCK_FILE):
            try:
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    for c in old_data.get("concepts", []):
                        if c.get("manually_edited"):
                            manual_nodes[c["id"]] = c
                        if "mastery_score" in c:
                            mastery_data[c["id"]] = {
                                "score": c["mastery_score"],
                                "ts": c.get("last_quiz_at")
                            }
            except Exception as e:
                print(f"[Warning] Could not read existing graph for merge: {e}")
    # Lock is released here. Extraction begins.

    master_concepts = {}
    master_relationships = []
    partial_files = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # [QA-12] Client is now created inside extract_concepts_from_pdf for thread safety.
        futures = {
            executor.submit(extract_concepts_from_pdf, pdf, GEMINI_API_KEY): pdf
            for pdf in pdf_files
        }
        for future in concurrent.futures.as_completed(futures):
            pdf = futures[future]
            try:
                data = future.result()
                if data.get("partial"):
                    partial_files.append(pdf.name)
                for c in data.get("concepts", []):
                    cid = c["id"].strip()
                    if cid not in master_concepts:
                        master_concepts[cid] = c
                    else:
                        master_concepts[cid]["sources"] = list(set(
                            master_concepts[cid].get("sources", []) + c.get("sources", [])
                        ))
                        master_concepts[cid]["page_references"] = list(set(
                            master_concepts[cid].get("page_references", [])
                            + c.get("page_references", [])
                        ))
                master_relationships.extend(data.get("relationships", []))
            except Exception as e:
                print(f"[Error] {pdf.name}: {e}")
                partial_files.append(pdf.name)

    # Merge extracted data with manually edited data BEFORE entity resolution.
    # This ensures student edits survive even if the LLM produces different concept names.
    for cid, m_node in manual_nodes.items():
        if cid in master_concepts:
            # Update fresh AI node with student's specific edits, preserving manual fields.
            master_concepts[cid].update(m_node)
        else:
            # Re-insert a manual node that might have been lost in new PDF context.
            master_concepts[cid] = m_node

    # Restore mastery scores after any entity resolution merges.
    for cid, m_val in mastery_data.items():
        if cid in master_concepts:
            master_concepts[cid]["mastery_score"] = m_val["score"]
            master_concepts[cid]["last_quiz_at"] = m_val["ts"]

    client = genai.Client(api_key=GEMINI_API_KEY)
    master_concepts, master_relationships = resolve_entities(
        master_concepts, master_relationships, client
    )
    synthesis_result = global_synthesis(list(master_concepts.values()), client)
    bridges = synthesis_result.get("bridges", [])
    for b in bridges:
        b["synthesized"] = True
    master_relationships.extend(bridges)

    # Emit warnings for UI [UX-08]
    if partial_files:
        print(f"⚠️ Partial extraction for files: {', '.join(partial_files)}")
    if synthesis_result.get("truncated"):
        print("⚠️ Synthesis truncated due to high concept count.")

    # Deduplicate relationships
    unique_rels = {}
    for r in master_relationships:
        s, t = r.get("source", "").strip(), r.get("target", "").strip()
        if s and t and s != t:
            r.update({"source": s, "target": t})
            unique_rels[(s, t, r.get("type", ""))] = r
    final_rels = list(unique_rels.values())

    # BFS for isolated node detection
    if master_concepts:
        adj = defaultdict(set)
        for r in final_rels:
            if r["source"] in master_concepts and r["target"] in master_concepts:
                adj[r["source"]].add(r["target"])
                adj[r["target"]].add(r["source"])

        roots = sorted(master_concepts.values(), key=lambda x: -len(adj.get(x["id"], [])))
        if roots:
            root_id = roots[0]["id"]
            visited, queue = {root_id}, deque([root_id])
            while queue:
                curr = queue.popleft()
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            for cid in master_concepts:
                if cid not in visited:
                    master_concepts[cid].update({
                        "is_isolated": True,
                        "isolation_note": "No connections found."
                    })

    # [CONCURRENCY REVIEW] Standard pipeline lock. This script is intended to run
    # as the ONLY writer during the extraction phase of the background thread.
    # The lock was briefly held above (for the snapshot). It is re-acquired here for the write.
    # Any /api/update that arrived between the snapshot release and now has already written
    # its changes to disk — they will be overwritten by this final write. This TOCTOU window
    # is documented above (FIX-B1). A full fix would require re-reading and re-merging here.
    with FileLock(LOCK_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"concepts": list(master_concepts.values()), "relationships": final_rels},
                f, indent=2
            )


if __name__ == "__main__":
    run_extraction()
