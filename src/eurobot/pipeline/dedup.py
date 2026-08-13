"""SQLite-based deduplication and macro-release freshness tracking.

Two tables:
  - ``news_seen``: prevents posting the same news item within a cooldown window.
  - ``macro_releases``: tracks when each macro series was last presented to the
    LLM.  A series is presented only on the day it is freshly released; after
    that it is filtered out until the next release.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from eurobot import config

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_seen (
    hash            TEXT PRIMARY KEY,
    first_seen      TIMESTAMP NOT NULL,
    times_posted    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS macro_releases (
    series_key          TEXT PRIMARY KEY,
    latest_obs_period   TEXT,
    release_timestamp   TIMESTAMP,
    first_presented     TIMESTAMP,
    hash                TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# News dedup
# ---------------------------------------------------------------------------

def filter_fresh_news(items: list, cooldown_hours: int | None = None) -> list:
    """Filter out news items already seen within the cooldown window.

    Args:
        items: list of NewsItem objects (from rss_fetcher).
        cooldown_hours: override default from config.
    """
    if cooldown_hours is None:
        cooldown_hours = config.NEWS_COOLDOWN_HOURS
    cutoff = datetime.now() - timedelta(hours=cooldown_hours)
    fresh = []
    with _get_conn() as conn:
        for item in items:
            row = conn.execute(
                "SELECT first_seen FROM news_seen WHERE hash = ?", (item.hash,)
            ).fetchone()
            if row is None or datetime.fromisoformat(row["first_seen"]) < cutoff:
                fresh.append(item)
            # else: item is in cooldown, skip
    logger.info("Dedup: %d/%d news items fresh (cooldown=%dh)",
                len(fresh), len(items), cooldown_hours)
    return fresh


def mark_news_seen(items: list) -> None:
    """Record news items as seen (upsert)."""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        for item in items:
            conn.execute(
                """INSERT INTO news_seen (hash, first_seen, times_posted)
                   VALUES (?, ?, 1)
                   ON CONFLICT(hash) DO UPDATE SET
                     times_posted = times_posted + 1""",
                (item.hash, now),
            )
    logger.info("Dedup: marked %d news items as seen", len(items))


# ---------------------------------------------------------------------------
# Macro release freshness
# ---------------------------------------------------------------------------

def filter_fresh_macro(items: list[dict]) -> list[dict]:
    """Filter macro items to those with a genuinely new release.

    A macro series is "fresh" if:
      1. We have never seen it before, OR
      2. Its latest observation period is newer than what we recorded, OR
      3. The data-value hash changed (revision) and we haven't shown the revision.

    Once presented, the series is filtered out on subsequent runs until the
    next actual release.
    """
    fresh = []
    now_iso = datetime.now().isoformat()
    with _get_conn() as conn:
        for item in items:
            series = item["series"]
            spec = item["spec"]
            tag = item["tag"]

            # Compute current observation signature
            if series is None or series.empty:
                continue
            latest_period = str(series.index[-1].date())
            value_hash = hashlib.sha256(
                series.tail(5).round(4).to_json().encode()
            ).hexdigest()[:16]

            row = conn.execute(
                "SELECT * FROM macro_releases WHERE series_key = ?", (tag,)
            ).fetchone()

            is_fresh = False
            if row is None:
                # Never seen — it's fresh
                is_fresh = True
            elif row["latest_obs_period"] != latest_period:
                # New observation period
                is_fresh = True
            elif row["hash"] != value_hash:
                # Data revision
                is_fresh = True

            if is_fresh:
                fresh.append(item)

    logger.info("Dedup: %d/%d macro series have fresh releases", len(fresh), len(items))
    return fresh


def mark_macro_presented(items: list[dict]) -> None:
    """Record that these macro series were presented to the LLM."""
    now_iso = datetime.now().isoformat()
    with _get_conn() as conn:
        for item in items:
            series = item["series"]
            tag = item["tag"]
            latest_period = str(series.index[-1].date())
            value_hash = hashlib.sha256(
                series.tail(5).round(4).to_json().encode()
            ).hexdigest()[:16]

            conn.execute(
                """INSERT INTO macro_releases
                   (series_key, latest_obs_period, release_timestamp,
                    first_presented, hash)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(series_key) DO UPDATE SET
                     latest_obs_period = excluded.latest_obs_period,
                     release_timestamp = excluded.release_timestamp,
                     first_presented = excluded.first_presented,
                     hash = excluded.hash""",
                (tag, latest_period, now_iso, now_iso, value_hash),
            )
    logger.info("DDedup: marked %d macro series as presented", len(items))
