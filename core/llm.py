"""
Core LLM Module — All LM Studio communication.
Every LLM call goes through this module for consistent logging and error handling.
"""

import os
import httpx
from pathlib import Path
from database import get_connection

# Configuration
LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://localhost:1234/v1/chat/completions")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "gemma-4-26b-a4b-it-heretic-guff")


def call_lmstudio(
    prompt: str,
    feature: str = "unknown",
    participant_id: str = "P01",
    temperature: float = 0.3,
    max_tokens: int = 200,
    timeout: int = 30,
) -> str:
    """
    Call LM Studio API and return response text.
    Logs every call to llm_logs for research analysis.

    Args:
        prompt: The prompt text
        feature: Feature name for logging (e.g. 'definition_validator', 'edge_challenger')
        participant_id: Participant code for research tracking
        temperature: LLM temperature (0.0-1.0)
        max_tokens: Maximum tokens in response
        timeout: HTTP timeout in seconds

    Returns:
        Response text from the LLM

    Raises:
        Exception: On timeout or API error
    """
    import time

    start = time.time()

    try:
        response = httpx.post(
            LMSTUDIO_URL,
            json={
                "model": LMSTUDIO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        response_text = result["choices"][0]["message"]["content"]

        elapsed_ms = int((time.time() - start) * 1000)

        # Log the call for research analysis
        _log_llm_call(participant_id, feature, prompt, response_text, elapsed_ms)

        return response_text

    except httpx.TimeoutException:
        raise Exception(f"LM Studio timed out after {timeout}s")
    except Exception as e:
        raise Exception(f"LM Studio API error: {str(e)}")


def _log_llm_call(
    participant_id: str, feature: str, prompt: str, response: str, response_time_ms: int
):
    """Save LLM call to database for research analysis."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO llm_logs (participant_id, feature, prompt, response, response_time_ms)
               VALUES (?, ?, ?, ?, ?)""",
            (participant_id, feature, prompt, response, response_time_ms),
        )
        conn.commit()
    except Exception:
        # llm_logs table may not exist yet — don't crash the app
        conn.rollback()
    finally:
        conn.close()
