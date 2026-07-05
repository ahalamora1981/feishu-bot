"""In-memory multi-turn session store, keyed by user_id (or chat_id+user_id).

Stored in plain dicts with a threading lock. Good enough for a single-process
bot; will not survive restarts and is not shared across processes.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Deque, Dict, List, TypedDict


class Message(TypedDict):
    role: str  # "user" | "assistant" | "system"
    content: str


class SessionStore:
    def __init__(self, max_turns: int) -> None:
        # Each "turn" = one user msg + one assistant msg. We keep the last
        # ``max_turns`` turns (so up to 2 * max_turns messages in the deque).
        self._max_turns = max_turns
        self._lock = threading.Lock()
        self._history: Dict[str, Deque[Message]] = defaultdict(
            lambda: deque(maxlen=2 * max_turns)
        )

    def get(self, key: str) -> List[Message]:
        with self._lock:
            return list(self._history[key])

    def append(self, key: str, user_msg: str, assistant_msg: str) -> None:
        with self._lock:
            buf = self._history[key]
            buf.append({"role": "user", "content": user_msg})
            buf.append({"role": "assistant", "content": assistant_msg})

    def clear(self, key: str) -> None:
        with self._lock:
            self._history.pop(key, None)
