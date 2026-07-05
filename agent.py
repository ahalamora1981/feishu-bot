"""Minimal LLM agent: wraps an OpenAI-compatible /chat/completions endpoint.

No tools, no streaming, no agent framework — just a synchronous chat call.
Works with DashScope's OpenAI-compatible mode and any local server that
exposes the same protocol (Ollama, LM Studio, vLLM, etc.).
"""
from __future__ import annotations

import logging
from typing import List

import httpx

import config
from session import Message, SessionStore

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns an unexpected shape."""


class LLMAgent:
    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._client = httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS)

    def chat(self, session_key: str, user_text: str) -> str:
        """Run one turn. Loads history, calls the LLM, stores the new turn."""
        history: List[Message] = self._store.get(session_key)
        messages: List[Message] = [
            {"role": "system", "content": config.SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_text},
        ]

        url = config.LLM_BASE_URL.rstrip("/") + "/chat/completions"
        payload = {
            "model": config.LLM_MODEL,
            "messages": messages,
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            resp = self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise LLMError(f"HTTP error calling LLM: {e}") from e

        if resp.status_code >= 400:
            # DashScope returns useful error bodies; surface them.
            raise LLMError(
                f"LLM returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
            reply: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise LLMError(f"Unexpected LLM response shape: {resp.text[:500]}") from e

        if not reply:
            raise LLMError("LLM returned empty content")

        self._store.append(session_key, user_text, reply)
        log.info(
            "llm ok session=%s prompt_tokens=%s completion_tokens=%s",
            session_key,
            (data.get("usage") or {}).get("prompt_tokens"),
            (data.get("usage") or {}).get("completion_tokens"),
        )
        return reply

    def close(self) -> None:
        self._client.close()
