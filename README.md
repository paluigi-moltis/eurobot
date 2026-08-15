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

## Quick Start (Docker)

The image is published on Docker Hub as [`paluugi/eurobot`](https://hub.docker.com/r/paluigi/eurobot).

```bash
# 1. Clone and configure
git clone https://github.com/paluigi/eurobot.git
cd eurobot

# 2. Set up secrets
cp .env.example .env
# Edit .env with your API keys (GROQ_API_KEY / TOGETHER_API_KEY,
# ZZBOARD_API_TOKEN, ZZBOARD_API_ENDPOINT)

cp config/llm-pycascade.toml.example config/llm-pycascade.toml
# Edit the TOML to pick your cascade providers/models

# 3. Run (pulls the image from Docker Hub)
mkdir -p data/posts
docker compose up -d

# 4. Check logs
docker compose logs -f eurobot

# 5. Trigger a run immediately (without waiting for the cron schedule)
docker compose exec eurobot python -m eurobot.main
```

### Container data layout

| Path | Mount | Contents |
|------|-------|----------|
| `/app/config` | `./config` (bind, read-only) | `llm-pycascade.toml` — required |
| `/app/data` | `eurobot_data` (named Docker volume) | `eurobot.db` (dedup SQLite), `cascade.db` (LLM attempt log), `eurobot.log` |
| `/app/data/posts` | `./data/posts` (bind) | Audit JSON copy of every published payload |

The SQLite databases live in a Docker-managed volume (not a bind mount), so
they survive container recreation. Inspect them with e.g.
`docker compose exec eurobot python -c "import sqlite3; print(sqlite3.connect('/app/data/eurobot.db').execute('select count(*) from news_seen').fetchone())"`.

Build the image locally instead of pulling:

```bash
docker build -t paluugi/eurobot:latest .
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
| `GROQ_API_KEY` | — | Groq API key (used by the default cascade) |
| `TOGETHER_API_KEY` | — | Together AI API key (used by the default cascade) |
| `ZZBOARD_API_TOKEN` | — | API key for publishing (sent as `X-API-Key`) |
| `ZZBOARD_API_ENDPOINT` | `https://roll.by.gg8.eu/api/new` | Target endpoint |
| `EUROBOT_CONFIG_DIR` | `/app/config` | llm-pycascade TOML location |
| `EUROBOT_DATA_DIR` | `/app/data` | SQLite DBs + audit logs |
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
