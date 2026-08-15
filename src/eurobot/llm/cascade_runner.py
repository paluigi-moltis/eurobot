"""llm-pycascade runner — resilient LLM inference with automatic failover.

Wraps the ``llm-pycascade`` library.  Loads cascade config from the mounted
TOML file, builds a :class:`Conversation`, runs the cascade, and returns the
text response.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from eurobot import config

logger = logging.getLogger(__name__)

# Attempt import of llm_pycascade — it's a hard dependency.
try:
    from llm_pycascade import AppConfig, init_db, load_config, run_cascade
    from llm_pycascade.models import Conversation, Message, MessageRole
except ImportError as exc:  # pragma: no cover
    logger.error("llm-pycascade not installed: %s", exc)
    raise

# SQLite DB where llm-pycascade logs attempts and tracks provider cooldowns.
CASCADE_DB_PATH = config.DATA_DIR / "cascade.db"

# Cache the loaded AppConfig so we don't re-read TOML on every call.
_app_config: AppConfig | None = None


def _load_config() -> AppConfig:
    """Load the cascade TOML config (cached after first call)."""
    global _app_config
    if _app_config is None:
        config_path = Path(config.CASCADE_CONFIG_PATH)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Cascade config not found: {config_path}. "
                "Mount it at /app/config/llm-pycascade.toml"
            )
        logger.info("Loading cascade config from %s", config_path)
        _app_config = load_config(config_path)
    return _app_config


def query_llm(
    user_prompt: str,
    system_prompt: str = "",
    cascade_name: str = "default",
) -> str:
    """Send a prompt through the llm-pycascade.

    Args:
        user_prompt: The user message content.
        system_prompt: Optional system prompt for role/instructions.
        cascade_name: Named cascade to use (default: "default").

    Returns:
        The text content of the LLM response.

    Raises:
        Exception if all providers in the cascade fail.
    """
    cfg = _load_config()

    messages = []
    if system_prompt:
        messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
    messages.append(Message(role=MessageRole.USER, content=user_prompt))

    conversation = Conversation(messages=messages)

    logger.info("Cascade: running '%s' (system=%s, user=%d chars)",
                cascade_name, bool(system_prompt), len(user_prompt))

    response = asyncio.run(
        _run_cascade(cascade_name, conversation, cfg)
    )

    # Extract text from response content blocks
    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
        elif hasattr(block, "content"):
            text_parts.append(block.content)
    result = "\n".join(text_parts)
    logger.info("Cascade: response received (%d chars)", len(result))
    return result


async def _run_cascade(
    cascade_name: str, conversation: Conversation, cfg: AppConfig):
    """Run one cascade query inside an event loop with its own DB connection."""
    conn = await init_db(str(CASCADE_DB_PATH))
    try:
        return await run_cascade(cascade_name, conversation, cfg, conn)
    finally:
        await conn.close()
