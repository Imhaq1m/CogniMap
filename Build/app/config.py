"""CogniMap integration config (S1, additive).

Centralises all env handling for LLM / LlamaParse live paths.
Keyless runs stay stub; live APIs behind env flags; supervisor demo never breaks.

Env names locked (Integration_Tracker):
  LLAMA_CLOUD_API_KEY
  LLM_PROVIDER=gemini
  GOOGLE_API_KEY (accept GEMINI_API_KEY alias, GOOGLE_API_KEY wins)
  LLM_MODELS=gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash
  LLAMA_TIER (agentic|agentic_plus, default agentic)

Limits (S6, decided here so parse + routes share them):
  MAX_PDF_BYTES = 20 MiB
  PAGE_CAP for agentic_plus escalation hint = 50 pages (manual flag wins)
  LLM_TIMEOUT_S per chain link = 30s
  PARSE_TIMEOUT_S = 120s

os.environ only, .env via python-dotenv (gitignored). No keys ever logged.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    # dotenv is optional at runtime (hard dep in requirements for prod);
    # os.environ still works without it so keyless CI stays green.
    pass

DEFAULT_LLM_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]

MAX_PDF_BYTES = int(os.environ.get("MAX_PDF_BYTES", str(20 * 1024 * 1024)))
LLAMA_PAGE_CAP = int(os.environ.get("LLAMA_PAGE_CAP", "50"))
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_S", "30"))
PARSE_TIMEOUT_S = int(os.environ.get("PARSE_TIMEOUT_S", "120"))


def get_llama_key() -> str | None:
    v = (os.environ.get("LLAMA_CLOUD_API_KEY") or "").strip()
    return v or None


def get_google_key() -> str | None:
    # GOOGLE_API_KEY wins per google-genai docs; GEMINI_API_KEY accepted alias.
    g = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    if g:
        return g
    gem = (os.environ.get("GEMINI_API_KEY") or "").strip()
    return gem or None


def get_llm_provider() -> str:
    return (os.environ.get("LLM_PROVIDER") or "gemini").strip().lower() or "gemini"


def get_llm_models() -> list[str]:
    raw = (os.environ.get("LLM_MODELS") or "").strip()
    if not raw:
        return list(DEFAULT_LLM_MODELS)
    out = [m.strip() for m in raw.split(",") if m.strip()]
    return out or list(DEFAULT_LLM_MODELS)


def get_llama_tier() -> str:
    t = (os.environ.get("LLAMA_TIER") or "agentic").strip().lower()
    if t in ("agentic_plus", "agentic-plus", "agenticplus"):
        return "agentic_plus"
    return "agentic"


def is_llama_live() -> bool:
    return bool(get_llama_key())


def is_llm_live() -> bool:
    return get_llm_provider() == "gemini" and bool(get_google_key())


def llm_status() -> dict:
    """Additive health payload fragment: {llm: live|stub, llm_model}."""
    models = get_llm_models()
    if is_llm_live():
        return {"llm": "live", "llm_model": models[0] if models else "stub"}
    return {"llm": "stub", "llm_model": "stub"}


def llama_status() -> dict:
    if is_llama_live():
        return {"llama": "live"}
    return {"llama": "stub"}


def upload_root() -> str:
    # Build/uploads/{sid}/{filename} (disk only, no store schema change).
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "uploads"))


def diagram_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "static", "diagrams"))
