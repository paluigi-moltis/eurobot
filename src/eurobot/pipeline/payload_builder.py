"""zzboard payload builder — assembles the flat-array JSON structure.

The zzboard schema is flat:
  - ``content_markdown``: prose narrative (from LLM Stage 2/3)
  - ``tables``: array of {title, rows}
  - ``charts``: array of {title, spec}
  - ``links``: array of {label, url, description} — built from selected news
  - ``title``, ``summary``, ``author``, ``tags``: from LLM Stage 2

No block-interleaving or regex tag parsing — the builder simply collects
the flat arrays from the available widgets and selected news.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from eurobot import config

logger = logging.getLogger(__name__)

DEFAULT_AUTHOR = "eurobot"


def assemble_payload(
    title: str,
    summary: str,
    tags: list[str],
    content_markdown: str,
    charts: list[dict],
    tables: list[dict],
    selected_news: list,
) -> dict:
    """Assemble the final zzboard payload.

    Args:
        title: Post title (from LLM).
        summary: One-sentence summary (from LLM).
        tags: Tag list (from LLM).
        content_markdown: Narrative body (from LLM Stage 3).
        charts: List of chart dicts {title, spec}.
        tables: list of table dicts {title, tags, rows}.
        selected_news: List of NewsItem objects for the links array.

    Returns:
        Dict conforming to the zzboard JSON schema.
    """
    # Build links array from selected news items
    links = [
        {
            "label": item.title,
            "url": item.link,
            "description": item.source,
        }
        for item in selected_news
    ]

    payload = {
        "title": title,
        "summary": summary,
        "author": DEFAULT_AUTHOR,
        "content_markdown": content_markdown,
        "tables": [
            {"title": t["title"], "rows": t["rows"]}
            for t in tables
        ],
        "charts": [
            {"title": c["title"], "spec": c["spec"]}
            for c in charts
        ],
        "links": links,
        "tags": tags,
    }

    logger.info(
        "Payload assembled: %d charts, %d tables, %d links, %d chars markdown",
        len(charts), len(tables), len(links), len(content_markdown),
    )
    return payload


def save_payload(payload: dict, posts_dir=None) -> str:
    """Save payload to disk for audit trail.

    Returns the path to the saved file.
    """
    if posts_dir is None:
        posts_dir = config.POSTS_DIR
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = posts_dir / f"post_{timestamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info("Payload saved to %s", path)
    return str(path)
