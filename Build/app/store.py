"""CogniMap Step 0 — SQLite store (stdlib sqlite3, all-Python).

Tables: users(id, name) + sessions(id, user_id, file, created, stage, phase)
+ session_files(session_id, filename, created)
+ concepts/links/scenarios/trail — session_id ONLY (Locks §0, no
denormalized user_id; user_id reached via sessions join).
Session-scoped queries only after require_owned_session; no cross-session
or cross-user reads.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("COGNIMAP_DB", os.path.join(os.path.dirname(__file__), "cognimap.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    con = connect()
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            file TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'steps1-2',
            phase TEXT NOT NULL DEFAULT 'phase1',
            l5_n INTEGER,
            l5_phase TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS session_files (
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            created TEXT NOT NULL,
            PRIMARY KEY (session_id, filename)
        );
        CREATE TABLE IF NOT EXISTS concepts (
            id TEXT NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('main','sub')),
            parent_id TEXT,
            source TEXT NOT NULL CHECK (source IN ('extracted','user_added')),
            explanation_type TEXT NOT NULL DEFAULT 'definition',
            explanation_text TEXT NOT NULL DEFAULT '',
            explanation_source TEXT NOT NULL DEFAULT 'generated',
            pages TEXT NOT NULL DEFAULT '[]',
            diagram_refs TEXT NOT NULL DEFAULT '[]',
            diagram_description TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (session_id, id)
        );
        CREATE TABLE IF NOT EXISTS links (
            id TEXT NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            a_id TEXT NOT NULL,
            b_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT '',
            bright INTEGER NOT NULL DEFAULT 1,
            why_answer TEXT NOT NULL DEFAULT '',
            fail_answer TEXT NOT NULL DEFAULT '',
            why_passed INTEGER NOT NULL DEFAULT 0,
            fail_passed INTEGER NOT NULL DEFAULT 0,
            phase TEXT NOT NULL DEFAULT 'phase1',
            PRIMARY KEY (session_id, id)
        );
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT NOT NULL,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            text TEXT NOT NULL DEFAULT '',
            concept_ids TEXT NOT NULL DEFAULT '[]',
            cleared INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (session_id, id)
        );
        CREATE TABLE IF NOT EXISTS trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            concept_id TEXT,
            link_id TEXT,
            scenario_id TEXT,
            stage TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            created TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_concepts_session ON concepts(session_id);
        CREATE INDEX IF NOT EXISTS idx_links_session ON links(session_id);
        CREATE INDEX IF NOT EXISTS idx_scenarios_session ON scenarios(session_id);
        CREATE INDEX IF NOT EXISTS idx_trail_session ON trail(session_id);
        CREATE INDEX IF NOT EXISTS idx_trail_lookup ON trail(session_id, concept_id, stage);
        CREATE INDEX IF NOT EXISTS idx_session_files_session ON session_files(session_id);
        """
    )
    con.commit()
    # M1 migration (Locks §0): drop denormalized user_id from domain tables
    # created before the session_id-only freeze. Fresh DBs already lack it.
    for _tbl in ("concepts", "links", "scenarios", "trail"):
        try:
            _cols = {r[1] for r in con.execute(f"PRAGMA table_info({_tbl})").fetchall()}
        except Exception:
            continue
        if "user_id" in _cols:
            try:
                con.execute(f"ALTER TABLE {_tbl} DROP COLUMN user_id")
            except Exception:
                pass
    try:
        con.commit()
    except Exception:
        pass
    # Backfill (existing DBs created before session_files): one row per
    # sessions.file label where no session_files row exists yet.
    try:
        for r in con.execute(
            "SELECT id, file, created FROM sessions WHERE file IS NOT NULL AND file != ''"
        ).fetchall():
            con.execute(
                "INSERT OR IGNORE INTO session_files (session_id, filename, created)"
                " VALUES (?,?,?)",
                (r["id"], r["file"], r["created"]),
            )
        con.commit()
    except Exception:
        pass
    # L4/L5 migration: links.phase (phase at creation) + sessions.l5_n/l5_phase
    # (N fixed at L5 entry per Locks §5). Fresh DBs get them on next CREATE;
    # existing DBs ALTER here.
    try:
        _lcols = {rr[1] for rr in con.execute("PRAGMA table_info(links)").fetchall()}
        if "phase" not in _lcols:
            con.execute("ALTER TABLE links ADD COLUMN phase TEXT NOT NULL DEFAULT 'phase1'")
            con.commit()
    except Exception:
        pass
    try:
        _scols = {rr[1] for rr in con.execute("PRAGMA table_info(sessions)").fetchall()}
        if "l5_n" not in _scols:
            con.execute("ALTER TABLE sessions ADD COLUMN l5_n INTEGER")
            con.commit()
    except Exception:
        pass
    try:
        _scols2 = {rr[1] for rr in con.execute("PRAGMA table_info(sessions)").fetchall()}
        if "l5_phase" not in _scols2:
            con.execute("ALTER TABLE sessions ADD COLUMN l5_phase TEXT NOT NULL DEFAULT ''")
            con.commit()
    except Exception:
        pass
    con.close()


# ---- users (lite name-pick, no auth) ----

def get_or_create_user(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT id, name FROM users WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        con.close()
        return dict(row)
    cur.execute("INSERT INTO users (name) VALUES (?)", (name,))
    uid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": uid, "name": name}


def list_users() -> list[dict]:
    con = connect()
    rows = con.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---- sessions ----

def create_session(user_id: int, file: str = "") -> dict:
    sid = "s-" + uuid.uuid4().hex[:8]
    now = _now()
    con = connect()
    con.execute(
        "INSERT INTO sessions (id, user_id, file, created, stage, phase) VALUES (?,?,?,?,?,?)",
        (sid, user_id, file or "", now, "steps1-2", "phase1"),
    )
    if (file or "").strip():
        con.execute(
            "INSERT OR IGNORE INTO session_files (session_id, filename, created)"
            " VALUES (?,?,?)",
            (sid, (file or "").strip(), now),
        )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    con.close()
    return dict(row)


def list_sessions(user_id: int) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY created", (user_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    con = connect()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def require_owned_session(session_id: str, user_id: int | None) -> dict:
    """Ownership gate (Locks §0+§8): sessions.user_id MUST equal requesting user.

    Raises KeyError("no such session") when missing, PermissionError when the
    session belongs to another user. Callers map both to 404 (never leak
    existence across users). user_id=None always fails closed.
    """
    if user_id is None:
        raise PermissionError("user_id required")
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise PermissionError("user_id required")
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if int(s["user_id"]) != uid:
        raise PermissionError("session not found for user")
    return s


# ---- session files (Locks §0 file list + §6 reset cascade) ----

def list_files(session_id: str) -> list[dict]:
    con = connect()
    try:
        rows = con.execute(
            "SELECT session_id, filename, created FROM session_files"
            " WHERE session_id = ? ORDER BY created, filename",
            (session_id,),
        ).fetchall()
        out = [dict(r) for r in rows]
        con.close()
        return out
    except Exception:
        # Pre-migration DB without the table: fall back to sessions.file label.
        try:
            row = con.execute("SELECT file FROM sessions WHERE id = ?", (session_id,)).fetchone()
        finally:
            con.close()
        if row and (row["file"] or "").strip():
            return [{"session_id": session_id, "filename": row["file"], "created": ""}]
        return []


def add_file(session_id: str, filename: str) -> dict:
    """Upload path: insert session_files row; sessions.file mirrors primary."""
    label = (filename or "").strip() or "seed-demo.pdf"
    con = connect()
    con.execute(
        "INSERT OR IGNORE INTO session_files (session_id, filename, created)"
        " VALUES (?,?,?)",
        (session_id, label, _now()),
    )
    row = con.execute("SELECT file FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is not None and not (row["file"] or "").strip():
        con.execute("UPDATE sessions SET file = ? WHERE id = ?", (label, session_id))
    con.commit()
    out = con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    con.close()
    return dict(out) if out else {}


def remove_file(session_id: str, filename: str | None = None,
                user_id: int | None = None) -> dict:
    """Per-file remove (Locks §6): delete one session_files row, keep data while
    files remain; removing the last file invokes clear_session_data (full wipe
    + sessions.file cleared + stage/phase reset). Returns
    {"session": ..., "files": [...], "reset": bool}.

    Ownership (§0+§8, anti-IDOR): verifies sessions.user_id == user_id first
    (never session_id alone) — mirrors delete_session. user_id=None fails
    closed. Destructive when it wipes, so store-level gate, not route-only.
    """
    require_owned_session(session_id, user_id)
    files = list_files(session_id)
    if not files:
        # Nothing tracked (legacy single-label session): full reset preserves
        # old behaviour for callers that never uploaded via session_files.
        cleared = clear_session_data(session_id, user_id)
        return {"session": cleared, "files": [], "reset": True}
    target = (filename or "").strip() if filename else None
    if target is None:
        # No filename given: legacy callers mean "remove the primary label".
        s = get_session(session_id)
        target = ((s or {}).get("file") or "").strip() or files[0]["filename"]
    con = connect()
    con.execute(
        "DELETE FROM session_files WHERE session_id = ? AND filename = ?",
        (session_id, target),
    )
    con.commit()
    con.close()
    remaining = list_files(session_id)
    if remaining:
        # Files remain: keep all domain data, mirror primary display label.
        con = connect()
        con.execute(
            "UPDATE sessions SET file = ? WHERE id = ?", (remaining[0]["filename"], session_id)
        )
        con.commit()
        con.close()
        return {"session": get_session(session_id), "files": remaining, "reset": False}
    cleared = clear_session_data(session_id, user_id)
    return {"session": cleared, "files": [], "reset": True}


# ---- session-scoped reads (skeleton; writes land in slices) ----

def list_concepts(session_id: str) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT * FROM concepts WHERE session_id = ? ORDER BY kind, id", (session_id,)
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["pages"] = json.loads(d.get("pages") or "[]")
        d["diagram_refs"] = json.loads(d.get("diagram_refs") or "[]")
        out.append(d)
    return out


def list_links(session_id: str) -> list[dict]:
    con = connect()
    try:
        # Deterministic demo order (TODO seed, #linkList, history grouping):
        # insertion order via rowid (ids are random l-xxxx, so ORDER BY id
        # would flap; mirrors list_trail ORDER BY id / list_concepts kind,id).
        rows = con.execute("SELECT * FROM links WHERE session_id = ? ORDER BY rowid", (session_id,)).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        # M3: normalize ints to bools on read (frozen shape keeps ints in DB).
        d["bright"] = bool(d.get("bright"))
        d["why_passed"] = bool(d.get("why_passed"))
        d["fail_passed"] = bool(d.get("fail_passed"))
        if "phase" not in d or not d.get("phase"):
            d["phase"] = "phase1"
        out.append(d)
    return out


def list_scenarios(session_id: str) -> list[dict]:
    con = connect()
    # Deterministic demo order: insertion order via rowid (ids are random
    # scn-xxxx; mirrors list_links ORDER BY rowid, list_trail ORDER BY id).
    rows = con.execute("SELECT * FROM scenarios WHERE session_id = ? ORDER BY rowid", (session_id,)).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["concept_ids"] = json.loads(d.get("concept_ids") or "[]")
        d["cleared"] = bool(d.get("cleared"))
        out.append(d)
    return out


def list_trail(session_id: str) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT * FROM trail WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---- Step 1 slice: upload / reset / confirm (additive, frozen shapes kept) ----

def set_session_file(session_id: str, file_label: str) -> dict | None:
    """Legacy single-label setter — routes through session_files (Locks §0).

    Kept for backward compat; new code should call add_file directly.
    """
    return add_file(session_id, file_label)


def set_stage(session_id: str, stage: str) -> None:
    con = connect()
    con.execute("UPDATE sessions SET stage = ? WHERE id = ?", (stage, session_id))
    con.commit()
    con.close()


def clear_session_data(session_id: str, user_id: int | None = None) -> dict | None:
    """Remove-file reset (Locks §6): reset file + wipe concepts/links/scenarios/trail
    + delete session_files rows.

    Ownership (§0+§8, anti-IDOR): verifies sessions.user_id == user_id first
    (never session_id alone) — mirrors delete_session. user_id=None fails
    closed. Destructive wipe, so store-level gate, not route-only.
    """
    require_owned_session(session_id, user_id)
    con = connect()
    con.execute("DELETE FROM concepts WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM links WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM scenarios WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM trail WHERE session_id = ?", (session_id,))
    try:
        con.execute("DELETE FROM session_files WHERE session_id = ?", (session_id,))
    except Exception:
        pass
    con.execute(
        "UPDATE sessions SET file = '', stage = 'steps1-2', phase = 'phase1', l5_n = NULL, l5_phase = '' WHERE id = ?",
        (session_id,),
    )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def confirm_selection(session_id: str, user_id: int, concepts: list[dict]) -> dict:
    """Validate + persist Confirm Selection. Enforces Step-2-only lock:
    callable only from stage steps1-2; afterwards titles lock (L1-3 read-only).

    Ownership via sessions join (Locks §0, no denormalized user_id):
    user_id param is ownership context only, verified against
    sessions.user_id, never persisted to domain rows.
    Phase-1 subs persist (never discard) but are excluded from Phase-1 math
    via kind filter (m3: kind-filter IS the hidden mechanism — renderGraph
    mains-only + l12_status/l3_counted_ids kind checks; no explicit
    hidden-flag column, no migration post-freeze; Phase-2 restricted-modal
    preselect lands in Step 6 per §7, see TODO Step 6).
    Locks §6 Deselect ≠ Delete applies to mains and subs: unchecked rows are
    excluded from Confirm (row kept in UI), not stored. Parent-integrity still
    enforced: sub needs a selected main parent, orphans forbidden; subs of
    unselected mains excluded.
    """
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if int(s.get("user_id")) != int(user_id):
        # Anti-IDOR (Locks §0+§8): Confirm is an ownership-checked write —
        # the caller must own the session, never session_id alone.
        raise PermissionError("session not found for user")
    if s.get("stage") != "steps1-2":
        raise ValueError("already locked — concepts lock after Confirm")
    items = concepts or []
    mains = [c for c in items if (c.get("kind") or "main") == "main"]
    if not mains:
        raise ValueError("Select at least 1 main heading to continue")
    main_ids = {(c.get("concept_id") or c.get("id") or "").strip() for c in mains}
    if "" in main_ids:
        raise ValueError("main heading missing id")
    # M1 (Locks §1/§6): reject duplicate ids at Confirm — INSERT OR REPLACE
    # would silently collapse dupes and corrupt counts.
    seen: set[str] = set()
    for c in items:
        _cid = ((c.get("concept_id") or c.get("id")) or "").strip()
        if _cid:
            if _cid in seen:
                raise ValueError(f"duplicate concept id: {_cid}")
            seen.add(_cid)
    cleaned: list[dict] = []
    for c in items:
        cid = (c.get("concept_id") or c.get("id") or "").strip()
        title = (c.get("title") or "").strip()
        if not cid or not title:
            raise ValueError("concept id/title required")
        kind = c.get("kind") or "main"
        if kind not in ("main", "sub"):
            raise ValueError(f"bad kind for {cid}")
        source = c.get("source") or "extracted"
        if source not in ("extracted", "user_added"):
            raise ValueError(f"bad source for {cid}")
        parent = c.get("parent_id")
        if kind == "sub":
            if not parent or parent not in main_ids:
                raise ValueError(f"sub {cid} needs a selected main parent")
        else:
            parent = None
        # Locks §1 two-step (M2): user_added created at Confirm with
        # explanation_text="" / explanation_source="user" — no explanation
        # input exists in the Step-2 modal, so never trust client text here.
        # Text is filled later at L1-2 via set_user_explanation (that save
        # counts toward progress).
        if source == "user_added":
            _exp_text = ""
            _exp_src = "user"
        else:
            _exp_text = c.get("explanation_text") or ""
            _exp_src = c.get("explanation_source") or "generated"
        cleaned.append(
            {
                "concept_id": cid,
                "title": title,
                "kind": kind,
                "parent_id": parent,
                "source": source,
                "explanation_type": c.get("explanation_type") or "definition",
                "explanation_text": _exp_text,
                "explanation_source": _exp_src,
                "pages": c.get("pages") or [],
                "diagram_refs": c.get("diagram_refs") or [],
                "diagram_description": c.get("diagram_description") or "",
            }
        )
    n = seed_concepts(session_id, user_id, cleaned)
    # history store initialized: one trail row per confirmed concept
    # (Locks §9 steps1-2 event rows allowed, never prune).
    con = connect()
    for c in cleaned:
        con.execute(
            "INSERT INTO trail (session_id, concept_id, stage, payload, created)"
            " VALUES (?,?,?,?,?)",
            (
                session_id,
                c["concept_id"],
                "steps1-2",
                json.dumps(
                    {"event": "confirmed", "title": c["title"],
                     "kind": c["kind"], "source": c["source"]}
                ),
                _now(),
            ),
        )
    con.execute("UPDATE sessions SET stage = 'L1-2' WHERE id = ?", (session_id,))
    con.commit()
    con.close()
    nm = sum(1 for c in cleaned if c["kind"] == "main")
    ns = sum(1 for c in cleaned if c["kind"] == "sub")
    return {"loaded": n, "mains": nm, "subs": ns, "stage": "L1-2"}


# ---- Step 2 slice: L1-2 attempts + progress (additive) ----

def record_l12_attempt(
    session_id: str,
    user_id: int,
    concept_id: str,
    paraphrase: str,
    passed: bool,
    accuracy: str = "",
    originality: str = "",
    feedback: str = "",
    hint: str = "",
    bypass: bool = False,
) -> None:
    """L1-2 trail write (Locks §9): extracted rows carry paraphrase +
    accuracy/originality/feedback; blue bypass rows carry user explanation +
    warning-ack + saved flag, NO accuracy/originality. user_id param is
    ownership context only (sessions join), never persisted (Locks §0).
    UI_ISSUES.txt Problem 2: keep only the latest L1-2 answer per concept —
    earlier L1-2 rows for the same (session_id, concept_id) are replaced so
    history shows a single latest answer + feedback (steps1-2 confirm rows
    use a different stage and are never touched; L3/L5 keep full per-attempt
    trail for lock-passed)."""
    # Defense-in-depth (§0/§8 uniformity): every mutating store fn verifies
    # sessions.user_id == user_id, never session_id alone. Route-gated today.
    require_owned_session(session_id, user_id)
    if bypass:
        payload = {
            "paraphrase": paraphrase,
            "user_explanation": paraphrase,
            "passed": bool(passed),
            "feedback": feedback,
            "hint": hint,
            "bypass": True,
            "warning_ack": "Ensure your self-defined concept is accurate — not verified against source.",
            "saved": bool(passed),
        }
    else:
        payload = {
            "paraphrase": paraphrase,
            "passed": bool(passed),
            "accuracy": accuracy,
            "originality": originality,
            "feedback": feedback,
            "hint": hint,
            "bypass": False,
        }
    con = connect()
    # UI_ISSUES.txt Problem 2: replace — delete prior L1-2 rows for this
    # concept so only the latest answer + feedback is stored.
    con.execute(
        "DELETE FROM trail WHERE session_id = ? AND concept_id = ? AND stage = 'L1-2'",
        (session_id, concept_id),
    )
    con.execute(
        "INSERT INTO trail (session_id, concept_id, stage, payload, created)"
        " VALUES (?,?,?,?,?)",
        (session_id, concept_id, "L1-2", json.dumps(payload), _now()),
    )
    con.commit()
    con.close()


def set_user_explanation(session_id: str, concept_id: str, text: str) -> None:
    """M6b: blue (user_added) L1-2 save writes user text back to the concept row."""
    con = connect()
    con.execute(
        "UPDATE concepts SET explanation_text = ?, explanation_source = 'user'"
        " WHERE session_id = ? AND id = ? AND source = 'user_added'",
        (text, session_id, concept_id),
    )
    con.commit()
    con.close()


def l12_status(session_id: str) -> dict:
    """Progress `% = completed / total_visible` (Locks §2).
    Phase 1 total = mains only; Phase 2 total = subs only.
    m3: kind-filter IS the hidden mechanism for Phase-1 subs — /concepts still
    lists subs in Phase-1 (hidden only via renderGraph mains-only + this kind
    filter); no explicit hidden-flag column, no migration post-freeze.
    Transition-only note (§7): between P1-L5-complete (stage=Phase2, phase
    still phase1) and P2-confirm, this reports mains math. Cosmetic — the
    Phase-2 modal covers the workspace until confirm_phase2 flips phase."""
    s = get_session(session_id)
    phase = (s or {}).get("phase") or "phase1"
    concepts = list_concepts(session_id)
    visible = [c for c in concepts if c.get("kind") == ("main" if phase == "phase1" else "sub")]
    total = len(visible)
    con = connect()
    rows = con.execute(
        "SELECT concept_id, payload FROM trail WHERE session_id = ? AND stage = 'L1-2'",
        (session_id,),
    ).fetchall()
    con.close()
    done: set[str] = set()
    for r in rows:
        try:
            if json.loads(r["payload"] or "{}").get("passed"):
                done.add(r["concept_id"])
        except (ValueError, TypeError):
            continue
    visible_ids = {c["id"] for c in visible}
    completed = len(done & visible_ids)
    pct = round(100 * completed / total) if total else 0
    return {
        "phase": phase,
        "total": total,
        "completed": completed,
        "pct": pct,
        "complete": bool(total) and completed >= total,
        "completed_ids": sorted(done & visible_ids),
    }


# ---- Step 3 slice: L3 Apply partition + scenarios + lock-passed (additive) ----

def partition_chunks(ids: list[str]) -> list[list[str]]:
    """Locks §3 remainder rule: chunks of 3; n%3==1 → merge last 4 into 2+2;
    n==1 → single 1-concept exception. Count == ceil(n/3)."""
    ids = list(ids or [])
    n = len(ids)
    if n <= 1:
        return [ids] if ids else []
    if n % 3 == 1:
        out, i = [], 0
        while i < n - 4:
            out.append(ids[i : i + 3])
            i += 3
        out.append(ids[i : i + 2])
        out.append(ids[i + 2 : i + 4])
        return out
    return [ids[i : i + 3] for i in range(0, n, 3)]


def l3_counted_ids(session_id: str) -> tuple[str, list[str]]:
    """Phase-aware counted ids: Phase 1 = mains only, Phase 2 = subs only (Locks §3).
    m3: kind-filter IS the hidden mechanism (no explicit hidden flag); mains
    display-only never pooled in Phase-2, subs hidden from Phase-1 math here.
    Transition-only note (§7): stage=Phase2/phase=phase1 window reports mains
    math until confirm_phase2 flips phase; modal covers workspace meanwhile."""
    s = get_session(session_id)
    phase = (s or {}).get("phase") or "phase1"
    concepts = list_concepts(session_id)
    kind = "main" if phase == "phase1" else "sub"
    ids = sorted(c["id"] for c in concepts if c.get("kind") == kind)
    return phase, ids


def l3_status(session_id: str) -> dict:
    import math

    phase, ids = l3_counted_ids(session_id)
    n = len(ids)
    total = math.ceil(n / 3) if n else 0
    allowed = set(ids)
    # Filtered math (Locks §7): mains display-only never counted in Phase 2.
    # Only scenarios whose concept_ids ⊆ current counted set contribute.
    scenarios = [x for x in list_scenarios(session_id)
                 if set(x.get("concept_ids") or []) <= allowed]
    cleared_scns = [x for x in scenarios if x.get("cleared")]
    cleared = len(cleared_scns)
    covered = {cid for x in cleared_scns for cid in (x.get("concept_ids") or [])}
    uncovered = [i for i in ids if i not in covered]
    pct = round(100 * cleared / total) if total else 0
    return {
        "phase": phase,
        "counted": ids,
        "total": total,
        "cleared": cleared,
        "pct": pct,
        "complete": bool(total) and cleared >= total,
        "uncovered": uncovered,
    }


def active_scenario(session_id: str) -> dict | None:
    # Filtered to current counted set (Phase-2 mains scenarios never resume).
    _, ids = l3_counted_ids(session_id)
    allowed = set(ids)
    for x in list_scenarios(session_id):
        if not x.get("cleared") and set(x.get("concept_ids") or []) <= allowed:
            return x
    return None


def create_scenario(
    session_id: str,
    concept_ids: list[str],
    text: str = "",
    user_id: int | None = None,
) -> dict:
    """Create scenario (Locks §3+§6+§8: app owns partition, pool=counted).

    Ownership: verifies sessions.user_id == user_id first (never session_id
    alone) — defense-in-depth, mirrors delete_session. user_id=None fails
    closed.
    Partition gate: stage must be L3 and chunk must satisfy
    chunk ⊆ l3_counted_ids (current phase pool), 1–3 ids, with the 1-concept
    exception only when total n==1 (else 2–3 per §3 remainder rule).
    Crafted chunks outside the counted set would break ceil(n/3)+2+2 math.
    """
    require_owned_session(session_id, user_id)
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if (s.get("stage") or "") != "L3":
        raise ValueError("Level 3 not active (complete L1-2 first)")
    chunk = list(concept_ids or [])
    if not chunk or len(chunk) > 3:
        raise ValueError("scenario chunk must be 1-3 concepts (app-partitioned)")
    _, counted = l3_counted_ids(session_id)
    allowed = set(counted)
    if set(chunk) - allowed:
        raise ValueError("scenario chunk outside current counted pool")
    if len(chunk) == 1 and len(counted) != 1:
        raise ValueError("1-concept scenario allowed only when total n==1")
    if len(set(chunk)) != len(chunk):
        raise ValueError("duplicate concept in scenario chunk")
    sid = "scn-" + uuid.uuid4().hex[:6]
    con = connect()
    con.execute(
        "INSERT INTO scenarios (id, session_id, text, concept_ids, cleared)"
        " VALUES (?,?,?,?,0)",
        (sid, session_id, text, json.dumps(list(concept_ids or []))),
    )
    con.commit()
    row = con.execute(
        "SELECT * FROM scenarios WHERE session_id = ? AND id = ?", (session_id, sid)
    ).fetchone()
    con.close()
    d = dict(row)
    d["concept_ids"] = json.loads(d.get("concept_ids") or "[]")
    return d


def set_scenario_cleared(session_id: str, scenario_id: str,
                         user_id: int | None = None) -> None:
    """Mark scenario cleared (Locks §3 strict clear, §0+§8 ownership).

    Ownership: verifies sessions.user_id == user_id first. Validates the
    scenario belongs to the current counted pool (filtered math §7 — stale
    phase scenarios never clear) and the session is in L3.
    """
    require_owned_session(session_id, user_id)
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if (s.get("stage") or "") != "L3":
        raise ValueError("Level 3 not active (complete L1-2 first)")
    con = connect()
    row = con.execute(
        "SELECT concept_ids FROM scenarios WHERE session_id = ? AND id = ?",
        (session_id, scenario_id),
    ).fetchone()
    if not row:
        con.close()
        raise KeyError("unknown scenario for this session")
    try:
        cids = json.loads(row["concept_ids"] or "[]")
    except (ValueError, TypeError):
        cids = []
    con.close()
    _, counted = l3_counted_ids(session_id)
    if set(cids or []) - set(counted):
        raise ValueError("scenario not in current phase pool")
    con = connect()
    con.execute(
        "UPDATE scenarios SET cleared = 1 WHERE session_id = ? AND id = ?",
        (session_id, scenario_id),
    )
    con.commit()
    con.close()


def record_l3_attempt(
    session_id: str,
    user_id: int,
    scenario_id: str,
    concept_id: str | None,
    justification: str,
    passed: bool,
    feedback: str = "",
    hint: str = "",
    omitted: bool = False,
) -> None:
    """L3 trail write (session_id-only per §0; user_id ownership-only)."""
    # Defense-in-depth (§0/§8 uniformity): verify ownership here too.
    require_owned_session(session_id, user_id)
    con = connect()
    con.execute(
        "INSERT INTO trail (session_id, concept_id, scenario_id, stage, payload, created)"
        " VALUES (?,?,?,?,?,?)",
        (
            session_id,
            concept_id,
            scenario_id,
            "L3",
            json.dumps(
                {
                    "justification": justification,
                    "passed": bool(passed),
                    "feedback": feedback,
                    "hint": hint,
                    "omitted": bool(omitted),
                }
            ),
            _now(),
        ),
    )
    con.commit()
    con.close()


def scenario_passed_ids(session_id: str, scenario_id: str) -> list[str]:
    """Lock-passed set: concept_ids with a passed L3 trail row for this scenario."""
    con = connect()
    rows = con.execute(
        "SELECT concept_id, payload FROM trail"
        " WHERE session_id = ? AND stage = 'L3' AND scenario_id = ?",
        (session_id, scenario_id),
    ).fetchall()
    con.close()
    out: set[str] = set()
    for r in rows:
        try:
            if json.loads(r["payload"] or "{}").get("passed") and r["concept_id"]:
                out.add(r["concept_id"])
        except (ValueError, TypeError):
            continue
    return sorted(out)


def seed_concepts(
    session_id: str,
    user_id_or_concepts: int | list[dict],
    concepts: list[dict] | None = None,
) -> int:
    """Step 0 helper: load concepts into a session for demo (session_id-only
    per §0; user_id ownership-only, never persisted).

    Accepts legacy seed_concepts(session_id, user_id, concepts) and new
    seed_concepts(session_id, concepts). Prefer confirm_selection /
    confirm_phase2 for validated writes (Confirm guards: stage lock,
    ≥1-main/sub, parent integrity, trail init).

    M3 gate (§0/§6/§8): the 3-arg form verifies sessions.user_id==user_id
    (never session_id alone). The 2-arg form is test-only; prod routes must
    go through confirm_selection / confirm_phase2 / seed-load.
    """
    if concepts is None and isinstance(user_id_or_concepts, list):
        items = user_id_or_concepts
    else:
        # Legacy 3-arg form: ownership-check first (fail closed).
        try:
            require_owned_session(session_id, user_id_or_concepts)  # type: ignore[arg-type]
        except (KeyError, PermissionError):
            # confirm_selection pre-validates and calls with the owner id,
            # so a failure here is a real IDOR attempt — re-raise.
            raise PermissionError("session not found for user")
        items = concepts or []
    con = connect()
    n = 0
    for c in items:
        con.execute(
            """INSERT OR REPLACE INTO concepts
               (id, session_id, title, kind, parent_id, source,
                explanation_type, explanation_text, explanation_source,
                pages, diagram_refs, diagram_description)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c.get("concept_id") or c.get("id"),
                session_id,
                c.get("title", ""),
                c.get("kind", "main"),
                c.get("parent_id"),
                c.get("source", "extracted"),
                c.get("explanation_type", "definition"),
                c.get("explanation_text", ""),
                c.get("explanation_source", "generated"),
                json.dumps(c.get("pages", [])),
                json.dumps(c.get("diagram_refs", [])),
                c.get("diagram_description", ""),
            ),
        )
        n += 1
    con.commit()
    con.close()
    return n


def delete_session(session_id: str, user_id: int) -> bool:
    """Session lifecycle delete (Locks §0/§6): ownership-checked cascade.

    Verifies sessions.user_id == user_id (join-free ownership check on the
    sessions row), then deletes session_files + scoped domain rows
    (concepts/links/scenarios/trail) + the sessions row itself.
    Returns True when a session was deleted, False when missing.
    Raises PermissionError on cross-user delete (mapped to 404).
    """
    s = get_session(session_id)
    if not s:
        return False
    if int(s.get("user_id")) != int(user_id):
        raise PermissionError("session not found for user")
    con = connect()
    con.execute("DELETE FROM concepts WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM links WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM scenarios WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM trail WHERE session_id = ?", (session_id,))
    try:
        con.execute("DELETE FROM session_files WHERE session_id = ?", (session_id,))
    except Exception:
        pass
    con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    con.commit()
    con.close()
    return True


def user_id_for_session(session_id: str) -> int | None:
    """Resolve user_id via sessions join (Locks §0, no denormalized user_id).

    Domain tables carry session_id only; ownership always resolves through
    the sessions row. Returns None when the session does not exist.
    """
    s = get_session(session_id)
    return int(s["user_id"]) if s else None


def delete_user(user_id: int) -> bool:
    """User delete cascade (UI_ISSUES.txt Problem 3): lite profiles, no auth.

    Deletes all sessions owned by the user (each via delete_session cascade:
    session_files + concepts/links/scenarios/trail + sessions row) then the
    users row itself. FK ON DELETE CASCADE also covers sessions/domain rows
    as backstop. Returns True when a user was deleted, False when missing.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    con = connect()
    row = con.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
    con.close()
    if not row:
        return False
    for s in list_sessions(uid):
        try:
            delete_session(s["id"], uid)
        except PermissionError:
            continue
    con = connect()
    con.execute("DELETE FROM users WHERE id = ?", (uid,))
    con.commit()
    con.close()
    return True


# ---- Step 4 slice: L4 Analyze links (Locks §4) ----

L4_PRESETS = ["causes", "leads to", "depends on", "includes",
              "contrasts with", "applied in", "influences", "consists of"]

_L4_CHARSET_RE = None


def _l4_charset_ok(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9 \-]+", s))


def validate_edge_type(edge_type: str, is_preset: bool | None = None) -> str:
    """Locks §4 Q11 custom validation + preset allow (M3 radio-vs-custom split).

    Rules: trim, 1-24 chars, single line, max 3 words,
    charset [A-Za-z0-9 space hyphen], no newlines/emoji/arrows,
    block exact preset duplicates case-insensitive (pick the preset instead).
    Returns cleaned type or raises ValueError.

    M3 (is_preset flag): preset-radio path sends is_preset=True with an exact
    preset (case-sensitive) and passes; custom path sends is_preset=False and
    rejects ALL 8 presets case-insensitive (exact "causes" as custom → 400).
    Legacy is_preset=None keeps exact-allow for direct store.create_link calls
    (tests use "causes" as preset); API layer defaults missing flag to custom
    (False) so direct POST {"edge_type":"causes"} without flag is rejected.
    """
    t = (edge_type or "").strip()
    if not t or len(t) > 24:
        raise ValueError("edge type must be 1-24 chars")
    if "\n" in t or "\r" in t:
        raise ValueError("edge type must be a single line")
    if len(t.split()) > 3:
        raise ValueError("edge type max 3 words")
    if not _l4_charset_ok(t):
        raise ValueError("edge type charset [A-Za-z0-9 space hyphen] only")
    # Locks §4 Q11 (m1): presets allowed via radio path (exact match passes
    # here); custom duplicates blocked case-insensitive for ALL 8 presets.
    low = t.lower()
    preset_lows = {p.lower(): p for p in L4_PRESETS}
    if is_preset is True:
        # Preset-radio path: must be an exact preset (case-sensitive).
        if t not in L4_PRESETS:
            # Not an exact preset — fall through to custom duplicate check so
            # a radio-path typo still gets the helpful "use preset" message.
            if low in preset_lows:
                raise ValueError(f"use preset '{preset_lows[low]}' instead of custom duplicate")
            return t
        return t
    if is_preset is False:
        # Custom path (incl. API missing-flag → custom): block ALL 8
        # case-insensitive, exact included. Demo: causes/Causes/CAUSES → 400.
        if low in preset_lows:
            raise ValueError(f"use preset '{preset_lows[low]}' instead of custom duplicate")
        return t
    # Legacy None (direct store calls, preset-compatible): exact-allow, block
    # only case-variants. Backend keeps exact-allow for the preset radio
    # (create_link tests use "causes" as preset); the custom textbox path is
    # blocked client-side in l4.js submitEdge + server-side when is_preset=False.
    if low in preset_lows and t != preset_lows[low]:
        raise ValueError(f"use preset '{preset_lows[low]}' instead of custom duplicate")
    return t


def _link_degrees(session_id: str) -> dict[str, int]:
    degs: dict[str, int] = {}
    for L in list_links(session_id):
        for cid in (L.get("a_id"), L.get("b_id")):
            if cid:
                degs[cid] = degs.get(cid, 0) + 1
    return degs


def l4_status(session_id: str) -> dict:
    """Finish gate (Locks §4): undirected counting, >=1 to enable Finish,
    max-3, n=1 auto-pass. Deleted pairs re-addable (only present pairs block)."""
    phase, counted = l3_counted_ids(session_id)
    links = list_links(session_id)
    degs = _link_degrees(session_id)
    per = {cid: degs.get(cid, 0) for cid in counted}
    n = len(counted)
    if n == 1:
        finish = True
        auto = True
    elif n == 0:
        finish = False
        auto = False
    else:
        finish = all(per.get(cid, 0) >= 1 for cid in counted)
        auto = False
    return {
        "phase": phase,
        "counted": counted,
        "degrees": per,
        "links": links,
        "finish_enabled": finish,
        "n1_auto": auto,
        "presets": L4_PRESETS,
        "warning": "Each concept needs 1-3 links (one link per pair — direction stored for probing). You can delete/re-pick links, but can't add concepts.",
    }


def create_link(session_id: str, from_id: str, to_id: str, edge_type: str,
                user_id: int | None = None, is_preset: bool | None = None) -> dict:
    """Ordered store (from,to,type) for display/probe; undirected counting.

    Gates: no loops, one-edge-per-pair (unordered, currently-present only),
    max-3 per concept (Phase 2: sub side ≤3, mains soft-exempt).
    Ownership (§0+§8): when user_id is given, verifies sessions.user_id ==
    user_id first (routes already gate; defense-in-depth).
    M3 (Locks §4 Q11): is_preset=True = preset-radio path (exact preset
    required); is_preset=False = custom path (blocks all 8 case-insensitive);
    None = legacy preset-compatible (exact-allow, for direct store tests).
    API defaults missing flag to False (custom) so direct POST custom
    duplicate → 400.
    """
    import uuid as _uuid
    if user_id is not None:
        require_owned_session(session_id, user_id)
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if (s.get("stage") or "") == "L5":
        raise ValueError("Graph frozen for evaluation. Click dimmed links to defend them.")
    if (s.get("stage") or "") != "L4":
        raise ValueError("Level 4 not active (complete L3 first)")
    phase = (s.get("phase") or "phase1")
    f = (from_id or "").strip()
    t = (to_id or "").strip()
    if not f or not t:
        raise ValueError("from/to required")
    if f == t:
        raise ValueError("No self-loops — connect two different concepts")
    etype = validate_edge_type(edge_type, is_preset=is_preset)
    concepts = {c["id"]: c for c in list_concepts(session_id)}
    if f not in concepts or t not in concepts:
        raise KeyError("unknown concept for this session")
    # Phase scoping: P1 mains-only; P2 sub-sub or sub-main (no new main-main).
    if phase == "phase1":
        if concepts[f].get("kind") != "main" or concepts[t].get("kind") != "main":
            raise ValueError("Phase 1 links connect mains only")
    else:
        kf = concepts[f].get("kind")
        kt = concepts[t].get("kind")
        if kf != "sub" and kt != "sub":
            raise ValueError("Phase 2 links need a sub endpoint (sub-sub or sub-main)")
    # One-edge-per-pair (unordered, present pairs only → deleted re-addable).
    for L in list_links(session_id):
        a, b = L.get("a_id"), L.get("b_id")
        if {a, b} == {f, t}:
            raise ValueError("One link per pair — direction stored for probing.")
    degs = _link_degrees(session_id)
    notice = ""
    if phase == "phase1":
        if degs.get(f, 0) >= 3 or degs.get(t, 0) >= 3:
            raise ValueError("Max 3 links per concept — pick the most important")
    else:
        # Sub side hard cap; mains soft-exempt (preserve Phase-1 bright state).
        for cid in (f, t):
            if concepts[cid].get("kind") == "sub" and degs.get(cid, 0) >= 3:
                raise ValueError("Max 3 links per sub — pick the most important")
        if degs.get(f, 0) >= 3 or degs.get(t, 0) >= 3:
            notice = "Main over 3 links (soft-exempt to preserve Phase-1 state)"
    lid = "l-" + _uuid.uuid4().hex[:6]
    con = connect()
    try:
        has_phase = "phase" in {r[1] for r in con.execute("PRAGMA table_info(links)").fetchall()}
    except Exception:
        has_phase = False
    if has_phase:
        con.execute(
            "INSERT INTO links (id, session_id, a_id, b_id, edge_type, bright, phase)"
            " VALUES (?,?,?,?,?,1,?)",
            (lid, session_id, f, t, etype, phase),
        )
    else:
        con.execute(
            "INSERT INTO links (id, session_id, a_id, b_id, edge_type, bright)"
            " VALUES (?,?,?,?,?,1)",
            (lid, session_id, f, t, etype),
        )
    con.commit()
    con.close()
    out = next((x for x in list_links(session_id) if x["id"] == lid), {})
    if notice:
        out["notice"] = notice
    return out


def delete_link(session_id: str, link_id: str, user_id: int | None = None) -> bool:
    if user_id is not None:
        require_owned_session(session_id, user_id)
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if (s.get("stage") or "") == "L5":
        raise ValueError("Graph frozen for evaluation. Click dimmed links to defend them.")
    if (s.get("stage") or "") != "L4":
        raise ValueError("Level 4 not active")
    # Locks §7 (M4): mains keep links/bright, no reset — in Phase 2, old
    # Phase-1 main-main links stay bright/excluded and must not be deleted.
    # Only Phase-2 (new) links are deletable in Phase-2 L4.
    if (s.get("phase") or "phase1") == "phase2":
        _chk = connect()
        _row = _chk.execute(
            "SELECT phase FROM links WHERE session_id = ? AND id = ?",
            (session_id, link_id),
        ).fetchone()
        _chk.close()
        if _row is None:
            raise KeyError("unknown link for this session")
        if (_row["phase"] or "phase1") != "phase2":
            raise ValueError("Phase-1 links locked in Phase 2 (mains keep links/bright)")
    con = connect()
    cur = con.execute(
        "DELETE FROM links WHERE session_id = ? AND id = ?", (session_id, link_id)
    )
    n = cur.rowcount
    con.commit()
    con.close()
    if not n:
        raise KeyError("unknown link for this session")
    return True


def l4_finish(session_id: str, user_id: int | None = None) -> dict:
    """Finish gate → freeze to L5 (dims + fixes N). n=1 auto-pass with 0 links."""
    if user_id is not None:
        require_owned_session(session_id, user_id)
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    # State-machine gate (Locks §6+§10): Finish lives only in L4. n=1 still
    # requires L4 (auto-pass with 0 links, not a skip from L3/L1-2).
    if (s.get("stage") or "") != "L4":
        raise ValueError("Level 4 not active (complete L3 first)")
    st = l4_status(session_id)
    if not st["finish_enabled"]:
        raise ValueError("Each concept needs at least 1 link to Finish")
    set_stage(session_id, "L5")
    n = l5_enter(session_id)
    # n=1 vacuous path: N=0 auto-completes → advance immediately.
    if n == 0:
        s = get_session(session_id)
        phase = (s or {}).get("phase") or "phase1"
        if phase == "phase1":
            set_stage(session_id, "Phase2")
        else:
            set_stage(session_id, "done")
    return {"stage": get_session(session_id).get("stage"), "l5_n": n,
            "warning": "Graph frozen for evaluation. Click dimmed links to defend them."}


# ---- Step 5 slice: L5 Evaluate (Locks §5) ----

def l5_enter(session_id: str) -> int:
    """Entry dimming + N fixed at entry. P1: all dim; P2: new (phase2) only,
    old main-main stay bright excluded. Idempotent (N fixed, never recomputed)."""
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    phase = (s.get("phase") or "phase1")
    # N already fixed for this phase → keep (frozen graph anyway).
    if s.get("l5_n") is not None and (s.get("l5_phase") or "") == phase:
        return int(s["l5_n"])
    links = list_links(session_id)
    if phase == "phase1":
        target_ids = [L["id"] for L in links]
    else:
        target_ids = [L["id"] for L in links if (L.get("phase") or "phase1") == "phase2"]
    con = connect()
    if target_ids:
        con.execute(
            f"UPDATE links SET bright = 0 WHERE session_id = ? AND id IN ({','.join('?' * len(target_ids))})",
            (session_id, *target_ids),
        )
        if phase == "phase2":
            # Old links stay bright excluded.
            con.execute(
                "UPDATE links SET bright = 1 WHERE session_id = ? AND phase != 'phase2'",
                (session_id,),
            )
    con.execute(
        "UPDATE sessions SET l5_n = ?, l5_phase = ? WHERE id = ?",
        (len(target_ids), phase, session_id),
    )
    con.commit()
    con.close()
    return len(target_ids)


def l5_status(session_id: str) -> dict:
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    phase = (s.get("phase") or "phase1")
    links = list_links(session_id)
    if phase == "phase1":
        target = links
    else:
        target = [L for L in links if (L.get("phase") or "phase1") == "phase2"]
    n = s.get("l5_n")
    if n is None:
        # Pre-entry (Locks §5): Level 5 0%, N fixed at entry only.
        # Never report 100% (0/0) or bright/N before Finish dims + fixes N.
        n = len(target)
        bright = 0
        entered = False
        pct = 0
        complete = False
    else:
        n = int(n)
        bright = sum(1 for L in target if L.get("bright"))
        entered = True
        if n == 0:
            # Vacuous n=1 auto-pass (l4_finish with 0 links): entered + N=0.
            pct = 100
            complete = True
        else:
            pct = round(100 * bright / n)
            complete = bright >= n
    return {
        "phase": phase,
        "entered": entered,
        "n": n,
        "bright": bright,
        "pct": pct,
        "complete": complete,
        "links": links,
        "target_ids": [L["id"] for L in target],
        "warning": "Graph frozen for evaluation. Click dimmed links to defend them.",
    }


def record_l5_attempt(session_id: str, link_id: str, why_answer: str, fail_answer: str,
                      why_passed: bool, fail_passed: bool, why_feedback: str = "",
                      fail_feedback: str = "", why_hint: str = "", fail_hint: str = "") -> None:
    con = connect()
    con.execute(
        "INSERT INTO trail (session_id, link_id, stage, payload, created)"
        " VALUES (?,?,?,?,?)",
        (session_id, link_id, "L5", json.dumps({
            "why_answer": why_answer, "fail_answer": fail_answer,
            "why_passed": bool(why_passed), "fail_passed": bool(fail_passed),
            "why_feedback": why_feedback, "fail_feedback": fail_feedback,
            "why_hint": why_hint, "fail_hint": fail_hint,
        }), _now()),
    )
    con.commit()
    con.close()


def probe_submit(session_id: str, link_id: str, why_answer: str, fail_answer: str,
                 ev: dict, user_id: int | None = None) -> dict:
    """Lock-passed per side (OR with stored flags); brighten only both-green."""
    if user_id is not None:
        require_owned_session(session_id, user_id)
    _s = get_session(session_id)
    if not _s:
        raise KeyError("no such session")
    # State-machine gate (Locks §6+§10): probe lives only in L5 (after
    # l5_enter dims/fixes N). Out-of-order probes would write L5 trail early.
    if (_s.get("stage") or "") != "L5":
        raise ValueError("Level 5 not active (complete Level 4 first)")
    why_ok = bool(ev.get("why_passed"))
    fail_ok = bool(ev.get("fail_passed"))
    con = connect()
    row = con.execute(
        "SELECT * FROM links WHERE session_id = ? AND id = ?", (session_id, link_id)
    ).fetchone()
    if not row:
        con.close()
        raise KeyError("unknown link for this session")
    d = dict(row)
    # M1 (§5 target-membership gate): Phase 1 target = all entry links;
    # Phase 2 target = phase='phase2' links only (old main-main stay bright,
    # excluded). Frozen graph makes current == entry-fixed, so phase filter
    # IS the entry-fixed set (N fixed at l5_enter, no add/delete in L5).
    # Crafted probes of excluded links → 400, no trail write, no flag touch.
    _phase = (_s.get("phase") or "phase1")
    _lphase = (d.get("phase") or "phase1")
    if _phase == "phase2" and _lphase != "phase2":
        con.close()
        raise ValueError("Link excluded from Phase-2 evaluation (old Phase-1 link stays bright)")
    new_why = bool(d.get("why_passed")) or why_ok
    new_fail = bool(d.get("fail_passed")) or fail_ok
    bright = 1 if (new_why and new_fail) else 0
    con.execute(
        "UPDATE links SET why_answer = ?, fail_answer = ?, why_passed = ?, fail_passed = ?, bright = ?"
        " WHERE session_id = ? AND id = ?",
        (why_answer or d.get("why_answer") or "", fail_answer or d.get("fail_answer") or "",
         int(new_why), int(new_fail), bright, session_id, link_id),
    )
    con.commit()
    con.close()
    record_l5_attempt(session_id, link_id, why_answer, fail_answer, why_ok, fail_ok,
                      str(ev.get("why_feedback", "")), str(ev.get("fail_feedback", "")),
                      str(ev.get("why_hint", "")), str(ev.get("fail_hint", "")))
    return next((x for x in list_links(session_id) if x["id"] == link_id), {})


# ---- Step 6 slice: Phase-2 merge (Locks §7) ----

def set_phase(session_id: str, phase: str) -> None:
    con = connect()
    con.execute("UPDATE sessions SET phase = ? WHERE id = ?", (phase, session_id))
    con.commit()
    con.close()


def confirm_phase2(session_id: str, user_id: int, subs: list[dict]) -> dict:
    """Restricted modal Confirm: subs-only adds, mains dimmed (no new mains).
    Merges subs, mains keep links/bright. Guard ≥1 sub; =1 hint ≥2 recommended."""
    s = get_session(session_id)
    if not s:
        raise KeyError("no such session")
    if int(s.get("user_id")) != int(user_id):
        raise PermissionError("session not found for user")
    if (s.get("stage") or "") != "Phase2":
        raise ValueError("Phase 2 not active (complete Level 5 first)")
    items = subs or []
    if not items:
        raise ValueError("Select at least 1 sub-heading to continue")
    concepts = {c["id"]: c for c in list_concepts(session_id)}
    mains_ids = {c["id"] for c in concepts.values() if c.get("kind") == "main"}
    if not mains_ids:
        raise ValueError("No mains to attach subs to")
    # No new mains allowed.
    for c in items:
        if (c.get("kind") or "sub") == "main":
            raise ValueError("Phase 2 adds sub-headings only (mains dimmed)")
    seen: set[str] = set()
    cleaned: list[dict] = []
    for c in items:
        cid = ((c.get("concept_id") or c.get("id")) or "").strip()
        title = (c.get("title") or "").strip()
        if not cid or not title:
            raise ValueError("sub id/title required")
        if cid in seen:
            raise ValueError(f"duplicate concept id: {cid}")
        seen.add(cid)
        parent = c.get("parent_id")
        if not parent or parent not in mains_ids:
            raise ValueError(f"sub {cid} needs an existing main parent")
        source = c.get("source") or "extracted"
        if source not in ("extracted", "user_added"):
            raise ValueError(f"bad source for {cid}")
        # Locks §1 two-step (M2, Phase-2 same): user_added subs start ""/"user".
        if source == "user_added":
            _p2_text, _p2_src = "", "user"
        else:
            _p2_text = c.get("explanation_text") or ""
            _p2_src = c.get("explanation_source") or "generated"
        cleaned.append({
            "concept_id": cid, "title": title, "kind": "sub", "parent_id": parent,
            "source": source,
            "explanation_type": c.get("explanation_type") or "definition",
            "explanation_text": _p2_text,
            "explanation_source": _p2_src,
            "pages": c.get("pages") or [], "diagram_refs": c.get("diagram_refs") or [],
            "diagram_description": c.get("diagram_description") or "",
        })
    # Merge: insert new ids, UPDATE title for existing SUB ids only
    # (Locks §7 subs add/rename allowed; §1 id-namespace integrity).
    # A sub id colliding with a kind==main id is rejected — otherwise a
    # crafted Phase-2 Confirm would rename a frozen Phase-1 main.
    for c in cleaned:
        _cid = c["concept_id"]
        if _cid in concepts and (concepts[_cid].get("kind") or "") == "main":
            raise ValueError(f"sub id collides with main: {_cid}")
    existing = set(concepts.keys())
    to_insert = [c for c in cleaned if c["concept_id"] not in existing]
    to_rename = [c for c in cleaned
                 if c["concept_id"] in existing
                 and (concepts[c["concept_id"]].get("kind") or "") == "sub"]
    if to_rename:
        _uc = connect()
        for c in to_rename:
            _old = (concepts.get(c["concept_id"]) or {}).get("title") or ""
            _uc.execute(
                "UPDATE concepts SET title = ? WHERE session_id = ? AND id = ?",
                (c["title"], session_id, c["concept_id"]),
            )
            # §9 auditability: renames write an event row (never prune).
            # Steps1-2 event rows allowed; keeps per-concept history complete.
            if _old != c["title"]:
                _uc.execute(
                    "INSERT INTO trail (session_id, concept_id, stage, payload, created)"
                    " VALUES (?,?,?,?,?)",
                    (
                        session_id,
                        c["concept_id"],
                        "steps1-2",
                        json.dumps(
                            {
                                "event": "phase2-renamed",
                                "title": c["title"],
                                "old_title": _old,
                                "kind": "sub",
                            }
                        ),
                        _now(),
                    ),
                )
        _uc.commit()
        _uc.close()
    if to_insert:
        seed_concepts(session_id, [c for c in to_insert])
    # Trail init for newly merged subs.
    con = connect()
    for c in to_insert:
        con.execute(
            "INSERT INTO trail (session_id, concept_id, stage, payload, created)"
            " VALUES (?,?,?,?,?)",
            (session_id, c["concept_id"], "steps1-2",
             json.dumps({"event": "phase2-confirmed", "title": c["title"],
                         "kind": "sub", "source": c["source"]}), _now()),
        )
    # New cycle: phase2, L1-2, N reset (fixed at next L5 entry).
    con.execute(
        "UPDATE sessions SET phase = 'phase2', stage = 'L1-2', l5_n = NULL, l5_phase = '' WHERE id = ?",
        (session_id,),
    )
    con.commit()
    con.close()
    all_subs = [c for c in list_concepts(session_id) if c.get("kind") == "sub"]
    # §7: exactly 1 sub total → ≥2 recommended but allow. Use total after
    # merge (persisted hidden subs count), not just submitted seen.
    hint = ""
    if len(all_subs) == 1:
        hint = "≥2 recommended for Apply scenarios"
    return {"merged": len(to_insert), "subs": len(all_subs), "stage": "L1-2",
            "phase": "phase2", "hint": hint}
