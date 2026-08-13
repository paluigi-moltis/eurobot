"""Central configuration for eurobot — loads env vars and paths."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
load_dotenv(_BASE_DIR / ".env")

CONFIG_DIR = Path(os.getenv("EUROBOT_CONFIG_DIR", _BASE_DIR / "config"))
DATA_DIR = Path(os.getenv("EUROBOT_DATA_DIR", _BASE_DIR / "data"))
DB_PATH = DATA_DIR / "eurobot.db"
POSTS_DIR = DATA_DIR / "posts"

# Ensure data dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
POSTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# External service configuration
# ---------------------------------------------------------------------------
ZZBOARD_API_TOKEN: str = os.getenv("ZZBOARD_API_TOKEN", "")
ZZBOARD_API_ENDPOINT: str = os.getenv(
    "ZZBOARD_API_ENDPOINT", "https://roll.by.gg8.eu/api/posts"
)

# llm-pycascade TOML config path
CASCADE_CONFIG_PATH: str = str(CONFIG_DIR / "llm-pycascade.toml")

# Dedup / freshness windows (hours)
NEWS_COOLDOWN_HOURS: int = int(os.getenv("NEWS_COOLDOWN_HOURS", "48"))
THEME_COOLDOWN_HOURS: int = int(os.getenv("THEME_COOLDOWN_HOURS", "24"))

# Number of news items / data items to present to LLM
MAX_NEWS_ITEMS: int = int(os.getenv("MAX_NEWS_ITEMS", "15"))
MAX_HISTORY_DAYS: int = int(os.getenv("MAX_HISTORY_DAYS", "90"))  # for chart lookback

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logger with stdout + file handler."""
    log_path = DATA_DIR / "eurobot.log"
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_path)),
        ],
    )
    return logging.getLogger("eurobot")
