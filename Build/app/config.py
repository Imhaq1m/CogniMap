"""CogniMap integration config (S1, additive).

Centralises all env handling for LLM / LlamaParse live paths.
Keyless runs stay stub; live APIs behind env flags; supervisor demo never breaks.

S2c (Oct 2026): live default switched GLM-4.7-Flash -> Groq qwen/qwen3.8-27b
after GLM free-tier rate limits (1302/1305) and 15-30s thinking latency made it
unusable for the demo. Groq is OpenAI-compatible and answers in well under a
second. GLM removed from the system per user request (NOT archived); the Gemini
chain is still archived, not deleted — selectable via LLM_PROVIDER=gemini.

Env names locked (Integration_Tracker; Groq amendment S2c):
  LLAMA_CLOUD_API_KEY
  LLM_PROVIDER=groq (default; gemini = archived path, kept selectable)
  GROQ_API_KEY
  GROQ_BASE_URL (default https://api.groq.com/openai/v1)
  LLM_MODELS=qwen/qwen3.8-27b (default per provider; Gemini triplet archived)
  GOOGLE_API_KEY / GEMINI_API_KEY (archived Gemini path only)
  LLAMA_TIER (agentic|agentic_plus, default agentic)

Limits (S6, decided here so parse + routes share them):
  MAX_PDF_BYTES = 20 MiB
  PAGE_CAP for agentic_plus escalation hint = 50 pages (manual flag wins)
  LLM_TIMEOUT_S per chain link = 30s (S2b raised it to 60 for GLM thinking;
    S2c reverted — Groq qwen3.8-27b answers in <1s, 30s is a hang guard only)
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

DEFAULT_GROQ_MODELS = ["qwen/qwen3.8-27b"]
# Archived as default Oct 2026 (S2b); selectable via LLM_PROVIDER=gemini.
DEFAULT_GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
DEFAULT_LLM_MODELS = DEFAULT_GROQ_MODELS  # backwards-compatible alias

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


def get_groq_key() -> str | None:
    v = (os.environ.get("GROQ_API_KEY") or "").strip()
    return v or None


def get_groq_base_url() -> str:
    raw = (os.environ.get("GROQ_BASE_URL") or "").strip()
    return (raw or "https://api.groq.com/openai/v1").rstrip("/")


def get_llm_provider() -> str:
    # S2c default: groq. "gemini" routes to the archived provider path.
    return (os.environ.get("LLM_PROVIDER") or "groq").strip().lower() or "groq"


def get_llm_models() -> list[str]:
    provider = get_llm_provider()
    default = DEFAULT_GEMINI_MODELS if provider == "gemini" else DEFAULT_GROQ_MODELS
    raw = (os.environ.get("LLM_MODELS") or "").strip()
    if raw:
        out = [m.strip() for m in raw.split(",") if m.strip()]
        # Migration guard: stale cross-provider names in LLM_MODELS (e.g.
        # glm-*/gemini-* left in .env after earlier swaps) would 400 every
        # chain link; drop them and use this provider's defaults instead.
        if provider == "gemini":
            out = [m for m in out if m.lower().startswith("gemini")]
        else:
            out = [m for m in out if not m.lower().startswith(("gemini", "glm"))]
        if out:
            return out
    return list(default)


def get_llama_tier() -> str:
    t = (os.environ.get("LLAMA_TIER") or "agentic").strip().lower()
    if t in ("agentic_plus", "agentic-plus", "agenticplus"):
        return "agentic_plus"
    return "agentic"


def is_llama_live() -> bool:
    return bool(get_llama_key())


def get_llm_key() -> str | None:
    """Provider-appropriate live key (None when not configured)."""
    provider = get_llm_provider()
    if provider == "groq":
        return get_groq_key()
    if provider == "gemini":
        return get_google_key()
    return None


def is_llm_live() -> bool:
    return bool(get_llm_key())


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
