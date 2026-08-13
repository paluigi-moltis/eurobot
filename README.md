# eurobot

Autonomous euro-area economic reporting pipeline. Collects macro data (SDMX),
market data (Stooq), and news (RSS) three times daily, uses a two-stage LLM
workflow to select and narrate a cohesive theme, and publishes to a zzboard
endpoint.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Container                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│  │  Cron   │─▶│  main.py │─▶│  fetchers (SDMX/Stooq/RSS)│   │
│  │  3×/day │  │          │  └────────────┬─────────────┘   │
│  └─────────┘  │          │               ▼                  │
│               │          │  ┌──────────────────────────┐   │
│               │          │  │  stats (Δ prev + YoY)     │   │
│               │          │  └────────────┬─────────────┘   │
│               │          │               ▼                  │
│               │          │  ┌──────────────────────────┐   │
│               │          │  │  viz (Plotly charts/tables)│  │
│               │          │  └────────────┬─────────────┘   │
│               │          │               ▼                  │
│               │          │  ┌──────────────────────────┐   │
│   llm-pycascade (cascade)│  │  3-stage LLM:             │   │
│   config/ (mounted)      │  │  select → draft → review  │   │
│   .env (env vars)        │  └────────────┬─────────────┘   │
│                          │               ▼                  │
│                          │  ┌──────────────────────────┐   │
│                          │  │  payload → publish        │   │
│                          │  └──────────────────────────┘   │
│  ┌──────────────────┐                                       │
│  │  SQLite (dedup)  │  data/ (mounted)                     │
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/paluigi-moltis/eurobot.git
cd eurobot

# 2. Set up secrets
cp .env.example .env
# Edit .env with your API keys

cp config/llm-pycascade.toml.example config/llm-pycascade.toml
# Edit TOML to add your provider models

# 3. Build and run
docker compose build
docker compose up -d

# 4. Check logs
docker compose logs -f eurobot
```

## Data Sources

### Macro (SDMX via `sdmx1`)
| Series | Source | Description |
|--------|--------|-------------|
| CISS | ECB | Composite Indicator of Systemic Stress |
| EUR/USD | ECB | Daily spot exchange rate |
| M3 | ECB | Broad money aggregate |
| Bund 10Y | ECB | German sovereign yield |
| BTP 10Y | ECB | Italian sovereign yield |
| HICP | Eurostat | Harmonised consumer price index |
| HICP Core | Eurostat | HICP excl. energy & food |
| GDP | Eurostat | Volume, chain-linked, SA |
| Unemployment | Eurostat | EA unemployment rate |
| ESI | DG-ECFIN | Economic Sentiment Indicator |

### Market (Stooq, free)
| Instrument | Symbol | Description |
|------------|--------|-------------|
| FTSE MIB | ftsemib | Italian equity benchmark |
| Brent | cbr.c | Crude oil benchmark |
| EUR/USD | eurusd | Cross-check vs ECB |
| BTP–Bund spread | (computed) | Sovereign stress |

### News (RSS)
Official (ECB, Eurostat), Italian press (ANSA, RAI, Il Sole 24 Ore),
international (Reuters, The Economist, Guardian), think tanks (Bruegel, VoxEU).

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ZZBOARD_API_TOKEN` | — | Bearer token for publishing |
| `ZZBOARD_API_ENDPOINT` | `https://roll.by.gg8.eu/api/posts` | Target endpoint |
| `EUROBOT_CONFIG_DIR` | `/app/config` | llm-pycascade TOML location |
| `EUROBOT_DATA_DIR` | `/app/data` | SQLite DB + audit logs |
| `NEWS_COOLDOWN_HOURS` | 48 | News dedup window |
| `THEME_COOLDOWN_HOURS` | 24 | Same-theme dedup window |
| `MAX_NEWS_ITEMS` | 15 | Max news items to LLM |
| `MAX_HISTORY_DAYS` | 90 | Chart lookback |

## LLM Cascade

The pipeline uses [`llm-pycascade`](https://github.com/paluigi/llm-pycascade) for
resilient multi-provider LLM inference with automatic failover. Configure the
cascade in `config/llm-pycascade.toml` (mounted into the container).

Three LLM stages:
1. **Selection** — pick 3–4 data points + 2–3 news items forming a theme
2. **Drafting** — write 2–3 paragraph narrative with title, summary, tags
3. **Self-review** — verify numeric claims against source data

## Deduplication

- **News**: same item filtered for 48h after posting (SQLite `news_seen`)
- **Macro releases**: presented only on the day of a fresh release; filtered
  out until the next one (SQLite `macro_releases`)
- **Market data**: always fresh (daily Stooq updates)

## Development

```bash
# Local dev with uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python -m eurobot.main

# Run tests
pytest
```

## Schedule

Cron runs 3× daily at 08:00, 13:00, 18:00 UTC inside the container.

## License

MIT
