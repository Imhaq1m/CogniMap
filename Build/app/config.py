"""CogniMap integration config (S1, additive).

Centralises all env handling for LLM / LlamaParse live paths.
Keyless runs stay stub; live APIs behind env flags; supervisor demo never breaks.

S2b (Oct 2026): live default switched Gemini -> GLM-4.7-Flash (z.ai free
tier) after Gemini 429/503 availability pain; the Gemini chain is archived,
not deleted — still selectable via LLM_PROVIDER=gemini.

Env names locked (Integration_Tracker; GLM amendment S2b):
  LLAMA_CLOUD_API_KEY
  LLM_PROVIDER=glm (default; gemini = archived path, kept selectable)
  GLM_API_KEY (accept ZAI_API_KEY alias, GLM_API_KEY wins)
  GLM_BASE_URL (default https://api.z.ai/api/paas/v4)
  LLM_MODELS=glm-4.7-flash (default per provider; Gemini triplet archived)
  GOOGLE_API_KEY / GEMINI_API_KEY (archived Gemini path only)
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

DEFAULT_GLM_MODELS = ["glm-4.7-flash"]
# Archived as default Oct 2026 (S2b); selectable via LLM_PROVIDER=gemini.
DEFAULT_GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
DEFAULT_LLM_MODELS = DEFAULT_GLM_MODELS  # backwards-compatible alias

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


def get_glm_key() -> str | None:
    # GLM_API_KEY wins; ZAI_API_KEY accepted alias (z.ai console naming).
    g = (os.environ.get("GLM_API_KEY") or "").strip()
    if g:
        return g
    z = (os.environ.get("ZAI_API_KEY") or "").strip()
    return z or None


def get_glm_base_url() -> str:
    raw = (os.environ.get("GLM_BASE_URL") or "").strip()
    return (raw or "https://api.z.ai/api/paas/v4").rstrip("/")


def get_llm_provider() -> str:
    # S2b default: glm. "gemini" routes to the archived provider path.
    return (os.environ.get("LLM_PROVIDER") or "glm").strip().lower() or "glm"


def get_llm_models() -> list[str]:
    provider = get_llm_provider()
    default = DEFAULT_GEMINI_MODELS if provider == "gemini" else DEFAULT_GLM_MODELS
    raw = (os.environ.get("LLM_MODELS") or "").strip()
    if raw:
        out = [m.strip() for m in raw.split(",") if m.strip()]
        # Migration guard: stale cross-provider names in LLM_MODELS (e.g.
        # Gemini ids left in .env after the S2b swap) would 400 every chain
        # link; drop them and use this provider's defaults instead.
        other = "gemini" if provider == "glm" else "glm"
        out = [m for m in out if not m.startswith(other)]
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
    if provider == "glm":
        return get_glm_key()
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
