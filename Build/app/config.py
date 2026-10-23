"""CogniMap integration config (S1, additive).

Centralises all env handling for LLM / LlamaParse live paths.
Keyless runs stay stub; live APIs behind env flags; supervisor demo never breaks.

S2f (Oct 2026): the archived Gemini + LM Studio paths are REMOVED entirely per
user instruction ("remove gemini api and lm studio api") — the same treatment
as the S2c GLM removal. Removed env names are no longer honoured
(LMSTUDIO_API_KEY / LMSTUDIO_BASE_URL / GOOGLE_API_KEY / GEMINI_API_KEY); the
LLM_MODELS stale-name guard still drops ids from removed providers (glm*,
gemini*, google/gemma-*, nvidia-nemotron-*) so old .env lines cannot 400 the
remaining chain. History: Gemini (S1, 429/503) -> GLM (S2b, removed S2c) ->
Groq (S2c) -> LM Studio (S2d) -> Groq (S2e) -> Gemini + LM Studio removed
(S2f) -> DeepSeek added selectable (S2g).

S2g (Oct 2026): DeepSeek added as a selectable provider per user instruction
("Add this deepseek api and test with it") — an OpenAI-compatible commercial
endpoint (base https://api.deepseek.com, chat/completions), model
deepseek-chat on the same shared transport and prompts (both P2 and P1 text
already contain the word "JSON", satisfying DeepSeek's response_format
restriction that messages mention json for json_object mode).

S2g+ (same session): the DeepSeek chain is pinned to deepseek-flash
(DeepSeek-V4.1-Flash) with thinking explicitly disabled via the extra
thinking {"type": "disabled"} payload field. Probed live: deepseek-flash
THINKS by default (reasoning tokens count inside max_tokens -> empty
content), the effort knob low|high|max does not disable thinking, whereas
thinking {"type": "disabled"} (and reasoning_effort "none") produce clean
runs. The earlier deepseek-chat alias is served by the same flash model with
thinking off server-side; the alias id is now treated as stale so the
chain names what actually serves.

S2h (2026-10-23, grill G-Route): routing moved to a MIXED CHAIN — the
LLM_MODELS list may combine provider ids and every chain link resolves its
provider by model id (qwen/* -> Groq, deepseek-* -> DeepSeek), one attempt
per link, full list -> labelled stub. LLM_PROVIDER is REMOVED (a global
selector contradicts per-activity chain order): free Groq serves every
normal click, paid DeepSeek answers only when Groq stumbles (429/5xx/etc)
or is deliberately promoted via LLM_MODELS reorder. Default chain (G3:
free-first on P1 extract AND P2 verify): qwen/qwen3.8-27b ->
deepseek-flash. A stub on stage then requires BOTH vendors to fail at
once (or no keys); /api/health reports the first KEYED chain link.

Env names locked (Integration_Tracker; S2f purge -> S2g/S2g+ -> S2h chain):
  LLAMA_CLOUD_API_KEY
  GROQ_API_KEY
  GROQ_BASE_URL (default https://api.groq.com/openai/v1)
  DEEPSEEK_API_KEY
  DEEPSEEK_BASE_URL (default https://api.deepseek.com)
  LLM_MODELS=mixed chain (default qwen/qwen3.8-27b,deepseek-flash; G3 free-first)
  LLAMA_TIER (agentic|agentic_plus, default agentic)
S2h purge: LLM_PROVIDER is no longer honoured (chain routes by model id).

Limits (S6, decided here so parse + routes share them):
  MAX_PDF_BYTES = 20 MiB
  PAGE_CAP for agentic_plus escalation hint = 50 pages (manual flag wins)
  LLM_TIMEOUT_S per chain link = 30s (S2b raised it to 60 for GLM thinking;
    S2c reverted — Groq qwen3.8-27b answers in <1s; the value is only a hang
    guard now that the slower local provider is gone too)
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
DEFAULT_DEEPSEEK_MODELS = ["deepseek-flash"]
# S2h (grill G-Route, G3): free-first on EVERY LLM activity — the chain order
# IS the routing policy. Normal clicks are served free (Groq); the paid link
# (DeepSeek flash, thinking off) answers only after an earlier link stumbles,
# or when someone deliberately promotes it by reordering LLM_MODELS.
DEFAULT_LLM_MODELS = DEFAULT_GROQ_MODELS + DEFAULT_DEEPSEEK_MODELS
DEFAULT_LLM_CHAIN = DEFAULT_LLM_MODELS  # backwards-compatible alias
# Stale-id guard (S2h): ids from removed providers (glm*, gemini-*,
# google/gemma-*, nvidia-nemotron-*) and the opaque S2g-era deepseek-chat
# alias are dropped wherever they appear in LLM_MODELS; anything else may
# MIX freely (routing is by id, not by a global provider switch).
_STALE_ID_PREFIXES = ("gemini", "glm", "google/gemma", "nvidia-nemotron",
                      "deepseek-chat")


def model_provider(model: str) -> str | None:
    """Chain link id -> provider name (S2h mixed chain).

    qwen/* ids run on Groq (free tier, LPU-fast); deepseek-* ids run on
    DeepSeek (pay-as-you-go failover) EXCEPT the opaque deepseek-chat alias —
    S2g+ pinned deepseek-flash and the router enforces the pin by id, so the
    config always names what actually serves. Unknown/unroutable ids return
    None — the provider dispatcher raises and the chain advances.
    """
    mid = (model or "").strip().lower()
    if mid == "deepseek-chat":
        return None
    if mid.startswith("qwen/"):
        return "groq"
    if mid.startswith("deepseek-"):
        return "deepseek"
    return None

MAX_PDF_BYTES = int(os.environ.get("MAX_PDF_BYTES", str(20 * 1024 * 1024)))
LLAMA_PAGE_CAP = int(os.environ.get("LLAMA_PAGE_CAP", "50"))
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_S", "30"))
PARSE_TIMEOUT_S = int(os.environ.get("PARSE_TIMEOUT_S", "120"))


def get_llama_key() -> str | None:
    v = (os.environ.get("LLAMA_CLOUD_API_KEY") or "").strip()
    return v or None


def get_groq_key() -> str | None:
    v = (os.environ.get("GROQ_API_KEY") or "").strip()
    return v or None


def get_groq_base_url() -> str:
    raw = (os.environ.get("GROQ_BASE_URL") or "").strip()
    return (raw or "https://api.groq.com/openai/v1").rstrip("/")


def get_deepseek_key() -> str | None:
    v = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    return v or None


def get_deepseek_base_url() -> str:
    raw = (os.environ.get("DEEPSEEK_BASE_URL") or "").strip()
    return (raw or "https://api.deepseek.com").rstrip("/")


def get_llm_models() -> list[str]:
    """The mixed LLM chain, in try-order (S2h; G3 free-first by default)."""
    raw = (os.environ.get("LLM_MODELS") or "").strip()
    if raw:
        out = [m.strip() for m in raw.split(",") if m.strip()]
        # Stale-id guard: removed-provider ids and the opaque deepseek-chat
        # alias would 400 (or silently reroute) a chain link — drop them and
        # fall back to the default when nothing routable remains.
        out = [m for m in out if not m.lower().startswith(_STALE_ID_PREFIXES)]
        if out:
            return out
    return list(DEFAULT_LLM_MODELS)


def get_llama_tier() -> str:
    t = (os.environ.get("LLAMA_TIER") or "agentic").strip().lower()
    if t in ("agentic_plus", "agentic-plus", "agenticplus"):
        return "agentic_plus"
    return "agentic"


def is_llama_live() -> bool:
    return bool(get_llama_key())


def get_llm_key(model: str) -> str | None:
    """Live key for the provider serving `model` (None when not configured).

    S2h: per-LINK resolution by model id — a chain may carry links from both
    providers and each link uses its own key. Keys are never logged.
    """
    provider = model_provider(model)
    if provider == "groq":
        return get_groq_key()
    if provider == "deepseek":
        return get_deepseek_key()
    return None


def is_llm_live() -> bool:
    """True when at least one chain link has its provider key configured."""
    return any(get_llm_key(m) for m in get_llm_models())


def llm_status() -> dict:
    """Additive health payload fragment: {llm: live|stub, llm_model}.

    S2h mixed chain: llm_model reports the first KEYED link — the one a
    normal click would hit next (later paid links only fire after a
    stumble). stub only when every link lacks a key.
    """
    for model in get_llm_models():
        if get_llm_key(model):
            return {"llm": "live", "llm_model": model}
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
