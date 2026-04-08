import json
from pathlib import Path
from filelock import FileLock
from scripts.validate_graph import run_validation
from collections import deque, defaultdict

# Configuration
INPUT_FILE = Path("output/graph_data.json")
LOCK_FILE = Path("output/graph_data.json.lock")

def compute_study_ranks(concepts: list, relationships: list) -> tuple[dict, set]:
    """
    True topological layering for study ordering.
    - Detects logical cycles (A requires B, B requires A).
    - Returns (ranks, cyclic_node_ids).
    """
    node_ids = {c.get("id") for c in concepts}
    adj = defaultdict(list)
    in_degree = {cid: 0 for cid in node_ids}
    
    for r in relationships:
        if r.get("type") == "PREREQUISITE":
            s, t = r.get("source"), r.get("target")
            if s in node_ids and t in node_ids:
                adj[s].append(t)
                in_degree[t] += 1
                
    queue = deque([cid for cid in node_ids if in_degree[cid] == 0])
    levels = {cid: 0 for cid in node_ids}
    processed = []
    
    while queue:
        u = queue.popleft()
        processed.append(u)
        for v in adj[u]:
            levels[v] = max(levels[v], levels[u] + 1)
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
                
    # Detect Cycles: Nodes with remaining in-degrees are part of a loop
    cyclic_node_ids = set(node_ids) - set(processed)

    ranks = {}
    for c in concepts:
        cid = c.get("id")
        lvl = levels.get(cid, 0)
        comp = c.get("complexity", 1)
        
        if cid in cyclic_node_ids:
            # Shift cyclic nodes to the back (900+) but preserve internal complexity/level order
            ranks[cid] = 900 + (lvl * 10) + comp
        else:
            ranks[cid] = (lvl * 10) + comp
        
    return ranks, cyclic_node_ids

def enrich_graph_data(data, target_node=None, target_edge=None):
    concepts = data.get("concepts", [])
    relationships = data.get("relationships", [])

    # Build map for anchor detection (node -> set of sources)
    node_to_sources = {c['id']: set(c.get('sources', [])) for c in concepts}
    
    # Identify cross-document bridge nodes
    cross_doc_bridges = set()
    for rel in relationships:
        s, t = rel.get("source"), rel.get("target")
        s_src = node_to_sources.get(s, set())
        t_src = node_to_sources.get(t, set())
        # If concepts from different source sets are linked, they are bridge candidates
        if s_src and t_src and not (s_src & t_src):
            cross_doc_bridges.add(s)
            cross_doc_bridges.add(t)

    # Run Automated Validation
    print(f"[Validation] Grounding {'targets' if target_node or target_edge else 'full graph'} against PDFs...")
    val_report = run_validation(data, target_node=target_node, target_edge=target_edge)
    node_val = val_report.get("nodes", {})
    edge_val = val_report.get("edges", {})

    node_degree = {}
    for rel in relationships:
        s, t = rel.get("source"), rel.get("target")
        if s and t:
            node_degree[s] = node_degree.get(s, 0) + 1
            node_degree[t] = node_degree.get(t, 0) + 1
            
            # [QA-17] Enrich Edges with Validation results - Move INSIDE guard
            eid = f"{s}_{t}"
            if eid in edge_val:
                v = edge_val[eid]
                rel["ai_confidence_score"] = v["score"]
                rel["validation_status"] = v["status"]

    # [FIX-C1] Guard total_steps against zero and add cyclic warning
    study_ranks, cyclic_ids = compute_study_ranks(concepts, relationships)
    non_cyclic_count = len(concepts) - len(cyclic_ids)
    if non_cyclic_count == 0 and len(concepts) > 0:
        print("⚠️ All concepts are in prerequisite cycles. No linear study path available.")
    total_steps = max(1, non_cyclic_count)

    for concept in concepts:
        cid = concept.get("id")
        is_manual = concept.get("manually_edited", False)

        concept["degree"] = node_degree.get(cid, 0)
        
        # Enrich Nodes with Validation results
        if cid in node_val:
            v = node_val[cid]
            concept["ai_confidence_score"] = v["score"]
            concept["validation_status"] = v["status"]
        
        # [UX-03] Flag logical loops for the UI with actionable advice
        if cid in cyclic_ids:
            concept["has_logical_loop"] = True
            concept["loop_warning"] = "Circular dependency detected. This concept is part of a loop (e.g. A requires B, which requires A). Please review the PREREQUISITE relationships and break the cycle."
            concept["study_rank_display"] = "Position unavailable — cycle detected"
        else:
            concept["has_logical_loop"] = False
            rank = study_ranks.get(cid, 0)
            # [FIX-C1] Clamp step_num to total_steps to prevent display artifacts
            step_num = min(total_steps, (rank // 10) + 1)
            # [UX-04] Relative position display
            concept["study_rank_display"] = f"Step {step_num} of {total_steps} in study path"

        if not is_manual or "study_rank" not in concept:
            concept["study_rank"] = study_ranks.get(cid, 0)

        if not is_manual or "is_anchor" not in concept:
            node_sources = concept.get("sources", [])
            # Anchor Logic: Multi-source OR Cross-document bridge
            concept["is_anchor"] = (len(node_sources) >= 2) or (cid in cross_doc_bridges)

    return {"concepts": concepts, "relationships": relationships}

def run_build(target_node=None, target_edge=None, skip_lock=False):
    """
    Main entry point for graph enrichment.
    [HIGH] skip_lock parameter allows calling this from app.py while a lock is already held,
    preventing deadlocks on Windows.
    """
    if not INPUT_FILE.exists():
        print(f"[Error] {INPUT_FILE} not found.")
        return False

    def perform_build():
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        enriched_data = enrich_graph_data(data, target_node=target_node, target_edge=target_edge)

        # [QA-16] Atomic write: write to .tmp and replace
        tmp_file = INPUT_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, indent=2)
        tmp_file.replace(INPUT_FILE)
        return True

    try:
        if skip_lock:
            # [CONCURRENCY REVIEW] Lock is already held by the caller (app.py)
            return perform_build()
        else:
            # [CONCURRENCY REVIEW] Standard entry point (CLI or Clear Data), take own lock.
            lock = FileLock(LOCK_FILE)
            with lock:
                return perform_build()
    except Exception as e:
        print(f"[Error] processing graph data: {e}")
        return False

if __name__ == "__main__":
    run_build()
