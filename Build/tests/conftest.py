"""Pytest isolation for Build/tests (S8).

Ensures the temp SQLite DB exists before every test even when multiple
test modules share one COGNIMAP_DB file (import-order deletes would
otherwise leave 'no such table' after the second module's cleanup).
Mirrors the isolated COGNIMAP_DB pattern in test_locks.py:14.

Also makes live integration hermetic: live keys are stripped for every
test EXCEPT test_live* (which need real keys), so stub-assuming tests
(incl. frozen test_locks.py) stay deterministic whether or not the
developer has keys in .env. Keyless CI behaviour is unchanged.
"""
from __future__ import annotations

import os
import tempfile

_DB = os.path.join(tempfile.gettempdir(), f"cognimap_test_{os.getpid()}.db")
os.environ.setdefault("COGNIMAP_DB", _DB)

import pytest

_LIVE_KEYS = ("LLAMA_CLOUD_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
              "GLM_API_KEY", "ZAI_API_KEY")
_SAVED: dict[str, str | None] = {}


@pytest.fixture(autouse=True)
def _ensure_db_and_stub(request):
    from app import store

    store.init_db()
    # Capture live keys lazily on first test setup — by then test-module
    # imports have run config.load_dotenv(), so .env keys are visible.
    if not _SAVED:
        for k in _LIVE_KEYS:
            _SAVED[k] = os.environ.get(k)
    if request.node.name.startswith("test_live"):
        for k, v in _SAVED.items():
            if v is not None:
                os.environ[k] = v
    else:
        for k in _LIVE_KEYS:
            os.environ.pop(k, None)
    yield
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
