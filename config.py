"""Load configuration from .env file (stdlib only, no extra dependency)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _load_env(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE per line, ignores comments / blanks."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Existing process env wins (allows overrides at launch time).
        os.environ.setdefault(key, value)


# Load once at import time. Path is relative to the project root (where main.py lives).
_PROJECT_ROOT = Path(__file__).resolve().parent
_load_env(_PROJECT_ROOT / ".env")


def _get(key: str, *, required: bool = True, default: Optional[str] = None) -> str:
    value = os.environ.get(key, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {key}")
    return value  # type: ignore[return-value]


# Feishu
APP_ID: str = _get("APP_ID")
APP_SECRET: str = _get("APP_SECRET")

# LLM (DashScope OpenAI-compatible mode)
LLM_BASE_URL: str = _get("DASHSCOPE_BASE_URL")
LLM_API_KEY: str = _get("DASHSCOPE_API_KEY")
LLM_MODEL: str = _get("DASHSCOPE_MODEL")

# Agent behaviour
SYSTEM_PROMPT: str = os.environ.get(
    "SYSTEM_PROMPT",
    "你是一个友好的飞书机器人助手，回答简洁清晰，使用中文。",
)
MAX_HISTORY_TURNS: int = int(os.environ.get("MAX_HISTORY_TURNS", "20"))
LLM_TIMEOUT_SECONDS: float = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
