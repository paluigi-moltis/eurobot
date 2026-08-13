"""Prompt templates for the three-stage LLM workflow.

Stage 1 — Selection:    Pick 3–4 data points + 2–3 news items forming a theme.
Stage 2 — Drafting:     Write 2–3 paragraph narrative + title/summary/tags.
Stage 3 — Self-review:  Verify numeric claims against source data.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt — applies to all stages
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert economic analyst specialising in the euro area. \
You write for a professional audience of economists and financial analysts. \
Your tone is precise, analytical, and concise — never sensational. \
You never fabricate data; you only reference figures provided to you. \
Your output must be valid JSON when requested."""


# ---------------------------------------------------------------------------
# Stage 1 — Selection
# ---------------------------------------------------------------------------

SELECTION_SYSTEM = SYSTEM_PROMPT + "\n\n" + """\
STAGE 1 — SELECTION. You are given a list of data summaries and news items. \
Select items that together form a COHESIVE euro-area economic theme for today. \
Prefer fresh macro releases and breaking news that explains market moves."""

SELECTION_USER_TEMPLATE = """\
Here are today's candidate items:

## Data items (charts & tables)

{data_items}

## News items

{news_items}

---

Select 3–4 data items and 2–3 news items that together tell a coherent \
euro-area economic story. Respond with ONLY a JSON array of the IDs you \
selected, in the order they should appear in the narrative. Example:

["DATA_001", "NEWS_002", "DATA_003", "DATA_002", "NEWS_001"]

Note: each [DATA_xxx] represents both a chart and a table for that series. \
You are selecting the series; the presentation format (chart vs table) will be \
chosen in the next stage. Respond with ONLY the JSON array, no explanation."""


# ---------------------------------------------------------------------------
# Stage 2 — Drafting
# ---------------------------------------------------------------------------

DRAFTING_SYSTEM = SYSTEM_PROMPT + "\n\n" + """\
STAGE 2 — DRAFTING. Write a short economic blog post (2–3 paragraphs) for \
economists. Embed the selected data by referencing each series by name. \
You MUST provide title, summary, tags, and content_markdown."""

DRAFTING_USER_TEMPLATE = """\
You have selected the following items for today's post:

{selected_context}

---

Write a 2–3 paragraph blog post for a professional economist audience. \
Rules:
1. Open with the most significant development.
2. Connect the data to the news contextually.
3. Reference each data series by name when discussing it.
4. Use markdown formatting (## subheadings, **bold** for key figures).
5. Do NOT fabricate any numbers — use only the figures in the context above.
6. The post should be ~150–250 words.

Respond with ONLY a JSON object with this exact structure:
{{
  "title": "A concise headline (max 12 words)",
  "summary": "1-sentence summary of the post",
  "tags": ["tag1", "tag2", ...],
  "content_markdown": "The full markdown body"
}}"""


# ---------------------------------------------------------------------------
# Stage 3 — Self-review
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = SYSTEM_PROMPT + "\n\n" + """\
STAGE 3 — SELF-REVIEW. You are a fact-checker. Verify every numeric claim in \
the draft against the provided source data. Flag any discrepancy. If a claim \
is wrong and cannot be corrected, reject the post."""

REVIEW_USER_TEMPLATE = """\
Draft post:
{draft_json}

Source data summaries (ground truth):
{source_summaries}

---

Verify every numeric figure mentioned in the draft against the source data. \
Check that:
1. Every number matches the source exactly (or is a correct arithmetic derivation).
2. No figures are fabricated or attributed to the wrong series.
3. The direction of change (↑/↓) is correct.

Respond with ONLY a JSON object:
{{
  "approved": true | false,
  "errors": ["description of each error found"],
  "corrected_markdown": "the corrected content_markdown, or null if approved"
}}"""


# ---------------------------------------------------------------------------
# Helpers to build prompts from pipeline data
# ---------------------------------------------------------------------------

def build_selection_prompt(
    data_summaries: list[str],
    news_summaries: list[str],
) -> tuple[str, str]:
    """Build (system, user) prompt pair for Stage 1.

    Args:
        data_summaries: One-line summaries, each prefixed with [DATA_xxx].
        news_summaries: One-line summaries, each prefixed with [NEWS_xxx].

    Returns:
        (system_prompt, user_prompt) tuple.
    """
    data_text = "\n".join(data_summaries) if data_summaries else "(none)"
    news_text = "\n".join(news_summaries) if news_summaries else "(none)"
    user = SELECTION_USER_TEMPLATE.format(
        data_items=data_text,
        news_items=news_text,
    )
    return SELECTION_SYSTEM, user


def build_drafting_prompt(selected_context: str) -> tuple[str, str]:
    """Build (system, user) prompt pair for Stage 2."""
    return DRAFTING_SYSTEM, DRAFTING_USER_TEMPLATE.format(
        selected_context=selected_context
    )


def build_review_prompt(
    draft_json: str,
    source_summaries: str,
) -> tuple[str, str]:
    """Build (system, user) prompt pair for Stage 3."""
    return REVIEW_SYSTEM, REVIEW_USER_TEMPLATE.format(
        draft_json=draft_json,
        source_summaries=source_summaries,
    )
