"""CogniMap Step 0 — frozen data models (Locks §0-§1, §8-§9).

FREEZE NOTICE: models/routes frozen after Step 0 demo passes.
All domain rows carry session_id-only scoping (Locks §0); user_id is
reached via sessions join (no denormalized user_id). Ownership is
enforced via store.require_owned_session (sessions.user_id == requester).
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

Kind = Literal["main", "sub"]
Source = Literal["extracted", "user_added"]
ExplanationType = Literal["definition", "procedure", "framework", "principle"]
ExplanationSource = Literal["extracted", "generated", "user"]  # M6b: blue rows store user text with "user"


class User(BaseModel):
    id: int
    name: str


class Session(BaseModel):
    id: str
    user_id: int
    file: str = ""
    created: str = ""
    # minimal state machine for skeleton; full transitions land in slices
    stage: str = "steps1-2"  # steps1-2 | L1-2 | L3 | L4 | L5 | Phase2 | done
    phase: str = "phase1"  # phase1 | phase2


class DiagramRef(BaseModel):
    diagram_id: str
    page: int


class Concept(BaseModel):
    """Locks §1 extractor shape + session_id-only scoping (§0, no user_id).

    Dual id-key convention (canonical, frozen post-Step 0 — do not rename):
    DB/store use `id`; seed/extract JSON use `concept_id`; Concept aliases
    concept_id→id (populate_by_name); frontend bridges with `||` fallbacks
    (c.concept_id || c.id). Consistent today; schema freeze forbids rename.
    """

    concept_id: str = Field(alias="id", default="")
    session_id: str = ""
    title: str = ""
    kind: Kind = "main"
    parent_id: Optional[str] = None
    source: Source = "extracted"
    explanation_type: ExplanationType = "definition"
    explanation_text: str = ""
    explanation_source: ExplanationSource = "generated"
    pages: list[int] = Field(default_factory=list)
    diagram_refs: list[DiagramRef] = Field(default_factory=list)
    diagram_description: str = ""

    model_config = {"populate_by_name": True}


class Link(BaseModel):
    id: str = ""  # link_id
    session_id: str = ""
    a_id: str = ""
    b_id: str = ""
    edge_type: str = ""
    # L5 visual state; L4 bright by default. Phase 1: all L4 links dim at L5
    # entry; Phase 2: only new Phase-2 links dim (old main-main stay bright,
    # excluded per §5 — overrides Details Level 5 §1 all-dim wording).
    bright: bool = True
    why_answer: str = ""
    fail_answer: str = ""
    why_passed: bool = False
    fail_passed: bool = False


class Scenario(BaseModel):
    id: str = ""  # scenario_id
    session_id: str = ""
    text: str = ""
    concept_ids: list[str] = Field(default_factory=list)
    cleared: bool = False


class Trail(BaseModel):
    """Full-trail history row, never pruned until session end (Locks §9).

    stage includes steps1-2 Confirm event rows (one per confirmed concept)
    plus L1-2 | L3 | L5 attempt rows; event rows allowed, never prune.
    """

    id: int = 0
    session_id: str = ""
    concept_id: Optional[str] = None
    link_id: Optional[str] = None
    scenario_id: Optional[str] = None
    stage: str = ""  # steps1-2 | L1-2 | L3 | L5 (L4 graph-visible only, omitted; done terminal, no trail writes)
    payload: str = "{}"  # JSON string
    created: str = ""
