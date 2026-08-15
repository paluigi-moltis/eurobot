"""Main orchestrator — coordinates the full end-to-end pipeline.

Flow:
  1. Fetch macro (SDMX), market (Yahoo Finance), and news (RSS) data.
  2. Filter for freshness (dedup) and compute statistics (Δ prev + YoY).
  3. Generate Plotly charts and summary tables.
  4. Stage 1 LLM: Select items forming a cohesive theme.
  5. Stage 2 LLM: Draft narrative with title, summary, tags.
  6. Stage 3 LLM: Self-review for numeric accuracy.
  7. Assemble zzboard payload and publish.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys

from eurobot import config
from eurobot.fetchers.sdmx_fetcher import fetch_all_macro
from eurobot.fetchers.market_fetcher import fetch_all_markets, compute_btp_bund_spread
from eurobot.fetchers.rss_fetcher import get_latest_news
from eurobot.stats.compute import compute_stats_for_series
from eurobot.viz.plotly_charts import make_line_chart, make_summary_table, make_delta_bar_chart
from eurobot.pipeline import dedup
from eurobot.pipeline.payload_builder import assemble_payload, save_payload
from eurobot.publish.zzboard_client import publish_payload
from eurobot.llm.cascade_runner import query_llm
from eurobot.llm import prompts

logger = config.setup_logging()


def run() -> int:
    """Execute the full pipeline. Returns exit code (0=success)."""
    logger.info("=" * 60)
    logger.info("eurobot pipeline started")
    logger.info("=" * 60)

    # ── 1. Fetch data ────────────────────────────────────────────────────
    logger.info("STEP 1: Fetching data sources")
    macro_items = fetch_all_macro()
    market_items = fetch_all_markets()
    all_news = get_latest_news(max_items=config.MAX_NEWS_ITEMS)

    # Compute BTP-Bund spread from sovereign yields
    macro_by_tag = {it["tag"]: it for it in macro_items}
    btp = macro_by_tag.get("IT_10Y_YIELD", {}).get("series")
    bund = macro_by_tag.get("DE_10Y_YIELD", {}).get("series")
    if btp is not None and bund is not None:
        spread = compute_btp_bund_spread(btp, bund)
        if spread is not None:
            macro_items.append({
                "tag": "BTP_BUND_SPREAD",
                "title": "BTP–Bund spread",
                "unit": "percentage points",
                "frequency": "D",
                "description": "Italian-German 10-year sovereign yield spread.",
                "series": spread,
                "spec": None,
            })

    # Combine macro + market into a single list
    all_data = macro_items + market_items
    logger.info("Total data items: %d macro + %d market = %d",
                len(macro_items), len(market_items), len(all_data))

    if not all_data and not all_news:
        logger.warning("No data or news collected — nothing to report. Exiting.")
        return 0

    # ── 2. Filter for freshness ──────────────────────────────────────────
    logger.info("STEP 2: Filtering for fresh content")
    fresh_macro = dedup.filter_fresh_macro(macro_items)
    fresh_news = dedup.filter_fresh_news(all_news)

    # Market data is always fresh (daily updates)
    fresh_data = fresh_macro + market_items

    if not fresh_data and not fresh_news:
        logger.info("No fresh content today — nothing to report. Exiting.")
        return 0

    # ── 3. Compute statistics + generate charts/tables ───────────────────
    logger.info("STEP 3: Computing stats and generating visualizations")
    data_summaries: list[str] = []
    all_stats = []
    charts_pool: dict[str, dict] = {}  # tag → chart dict
    tables_pool: dict[str, dict] = {}  # tag → table dict

    for item in fresh_data:
        series = item.get("series")
        if series is None or series.empty:
            continue
        tag = item["tag"]
        title = item["title"]
        freq = item.get("frequency", "M")
        unit = item.get("unit", "")

        stats = compute_stats_for_series(series, tag, title, frequency=freq)
        if stats is None:
            continue
        all_stats.append(stats)

        # Generate both chart and table for this series
        chart = make_line_chart(series, tag, title, y_title=unit)
        table = make_summary_table(stats, tag)
        charts_pool[tag] = chart
        tables_pool[tag] = table

        data_summaries.append(
            f"[DATA_{tag}] {stats.summary} (unit: {unit})"
        )

    # Add a cross-indicator bar chart if we have multiple series
    if len(all_stats) >= 2:
        overview = make_delta_bar_chart(all_stats)
        charts_pool["ALL_DELTA"] = overview
        data_summaries.append(
            f"[DATA_ALL_DELTA] Overview bar chart: Δ vs previous period across {len(all_stats)} indicators"
        )

    news_summaries = [item.to_prompt_line() for item in fresh_news]

    logger.info("Prepared %d data items + %d news items for LLM",
                len(data_summaries), len(news_summaries))

    if not data_summaries and not news_summaries:
        logger.info("Nothing to present to LLM. Exiting.")
        return 0

    # ── 4. Stage 1 — Selection ───────────────────────────────────────────
    logger.info("STEP 4: LLM Stage 1 — Selection")
    sys_prompt, usr_prompt = prompts.build_selection_prompt(
        data_summaries, news_summaries
    )
    raw_response = query_llm(usr_prompt, system_prompt=sys_prompt)
    selected_ids = _parse_json_safe(raw_response, prefer=list)

    if not selected_ids:
        logger.error("Stage 1 returned no valid selections — aborting")
        return 1
    logger.info("Stage 1 selected: %s", selected_ids)

    # Build selected context for Stage 2
    selected_context_parts = []
    selected_news: list = []
    selected_tags: set[str] = set()

    for item_id in selected_ids:
        if item_id.startswith("NEWS_"):
            # Find the matching news item
            for n in fresh_news:
                if n.tag == item_id:
                    selected_news.append(n)
                    selected_context_parts.append(n.to_prompt_line())
                    break
        elif item_id.startswith("DATA_"):
            tag = item_id.replace("DATA_", "")
            selected_tags.add(tag)
            # Find the matching data summary
            for s in data_summaries:
                if s.startswith(f"[{item_id}]"):
                    selected_context_parts.append(s)
                    break

    selected_context = "\n".join(selected_context_parts)

    # ── 5. Stage 2 — Drafting ────────────────────────────────────────────
    logger.info("STEP 5: LLM Stage 2 — Drafting")
    sys_prompt, usr_prompt = prompts.build_drafting_prompt(selected_context)
    raw_response = query_llm(usr_prompt, system_prompt=sys_prompt)
    draft = _parse_json_safe(raw_response, prefer=dict)

    if not draft or "content_markdown" not in draft:
        logger.error("Stage 2 returned invalid draft — aborting")
        return 1

    logger.info("Draft: title='%s', %d chars markdown",
                draft.get("title", "?"), len(draft["content_markdown"]))

    # ── 6. Stage 3 — Self-review ─────────────────────────────────────────
    logger.info("STEP 6: LLM Stage 3 — Self-review")
    source_summaries = "\n".join(
        [s.summary for s in all_stats if s.tag in selected_tags]
    )
    sys_prompt, usr_prompt = prompts.build_review_prompt(
        json.dumps(draft, indent=2), source_summaries
    )
    raw_response = query_llm(usr_prompt, system_prompt=sys_prompt)
    review = _parse_json_safe(raw_response, prefer=dict)

    if review and review.get("approved") is False:
        if review.get("corrected_markdown"):
            logger.warning("Self-review found errors — applying corrections")
            draft["content_markdown"] = review["corrected_markdown"]
        else:
            logger.error("Self-review rejected the draft and it cannot be fixed — aborting")
            return 1
    else:
        logger.info("Self-review approved the draft")

    # ── 7. Assemble charts/tables for selected series ────────────────────
    selected_charts = []
    selected_tables = []
    for tag in selected_tags:
        if tag in charts_pool:
            selected_charts.append(charts_pool[tag])
        if tag in tables_pool:
            selected_tables.append(tables_pool[tag])
    if "ALL_DELTA" in selected_tags:
        # Already added above
        pass

    # ── 8. Assemble payload + publish ────────────────────────────────────
    logger.info("STEP 7: Assembling and publishing payload")
    payload = assemble_payload(
        title=draft.get("title", "Euro-area economic update"),
        summary=draft.get("summary", ""),
        tags=draft.get("tags", []),
        content_markdown=draft["content_markdown"],
        charts=selected_charts,
        tables=selected_tables,
        selected_news=selected_news,
    )

    # Save for audit
    payload_path = save_payload(payload)
    logger.info("Payload saved to %s", payload_path)

    # Publish
    success = publish_payload(payload)
    if success:
        # Mark items as seen/presented only after a successful publish, so a
        # failed run retries the same content at the next scheduled run.
        dedup.mark_news_seen(selected_news)
        dedup.mark_macro_presented(
            [item for item in fresh_data if item["tag"] in selected_tags]
        )
        logger.info("=" * 60)
        logger.info("eurobot pipeline completed successfully")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("Publish failed — payload saved locally for retry")
        return 1


def _parse_json_safe(text: str, prefer: type | None = None) -> list | dict | None:
    """Extract and parse JSON from an LLM response.

    Tolerates reasoning-model ``<think>`` blocks (even with the JSON inside
    them), markdown code fences, and surrounding prose: collects every
    complete JSON value found and returns the last one — models place the
    final answer at the end. If ``prefer`` (list or dict) is given, only
    candidates of that type are considered.
    """
    import re

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r"[\[{]", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
            candidates.append(obj)
        except json.JSONDecodeError:
            continue
    if prefer is not None:
        candidates = [c for c in candidates if isinstance(c, prefer)]
    if candidates:
        return candidates[-1]
    logger.error("Could not parse JSON from LLM response: %s", text[:200])
    return None


if __name__ == "__main__":
    sys.exit(run())
