# eurobot

Autonomous euro-area economic reporting pipeline. Collects macro data (SDMX),
market data (Yahoo Finance), and news (RSS) three times daily, uses a
three-stage LLM workflow to select and narrate a cohesive theme, and publishes
to a zzboard endpoint.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Container                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│  │  Cron   │─▶│  main.py │─▶│ fetchers (SDMX/Yahoo/RSS) │   │
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
│  │  SQLite (dedup)  │  /app/data (Docker volume)           │
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

### Macro (SDMX: ECB Data Portal + Eurostat, via `sdmx1`)
| Series | Source | Frequency | Description |
|--------|--------|-----------|-------------|
| CISS | ECB | D | Composite Indicator of Systemic Stress |
| EUR/USD | ECB | D | Daily spot exchange reference rate |
| M3 | ECB | M | Broad money aggregate (stock) |
| DFR | ECB | D | ECB Deposit Facility Rate |
| EA 10Y yield | ECB | M | Euro-area benchmark government yield |
| DE 10Y yield | Eurostat | M | German 10Y yield (Maastricht convergence) |
| IT 10Y yield | Eurostat | M | Italian 10Y yield (Maastricht convergence) |
| BTP–Bund spread | (computed) | M | IT minus DE 10Y — sovereign stress |

### Market (Yahoo Finance chart API, free, no key)
| Instrument | Yahoo symbol | Description |
|------------|--------------|-------------|
| FTSE MIB | `FTSEMIB.MI` | Italian equity benchmark |
| Brent | `BZ=F` | Crude oil futures |
| EUR/USD | `EURUSD=X` | Cross-check vs ECB reference rate |
| BTP–Bund spread | (computed) | From the SDMX sovereign yields above |

### News (RSS, 7 feeds)
Official (ECB Press), international press (The Economist, The Guardian,
DW), Italian press (ANSA, Il Sole 24 Ore), think tanks (Bruegel). Items are
pre-filtered by a euro-area economic relevance keyword list before reaching
the LLM.

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
| `PIPELINE_MAX_ATTEMPTS` | 4 | Initial run + retries (tenacity, exponential backoff) before giving up until the next cron slot |
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
- **Market data**: always fresh (daily Yahoo updates)

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

## Failure handling & retries

The LLM stages and publish are wrapped in a [tenacity](https://tenacity.readthedocs.io/)
retry loop (`PIPELINE_MAX_ATTEMPTS`, default 4 = initial run + 3 retries,
exponential backoff ~10–20s between attempts). Retries **resume from the
last valid step**: stage results are checkpointed, so a failed attempt
re-runs only the broken stage and those after it —

- a crashed/unparseable LLM call re-runs just that stage;
- an unfixable self-review rejection **redrafts** (the selection is kept);
- a failed publish POST is retried with backoff.

If all attempts fail, the run exits non-zero and gives up until the next
scheduled cron run (08:00/13:00/18:00 UTC). That next run is effectively a
retry of the same content, because items are marked as *seen* in the dedup
database **only after a successful publish** — a failed run leaves the
selected news/macro items fresh and re-presented.

The assembled payload of every attempt is kept as an audit JSON in
`/app/data/posts` for manual replay if needed. Fetch/stats stages are not
retried as a block (they are already resilient per series).

## Releases

Images on Docker Hub: `paluugi/eurobot:<tag>` — see
[hub.docker.com/r/paluigi/eurobot/tags](https://hub.docker.com/r/paluigi/eurobot/tags).

| Tag | Notes |
|-----|-------|
| `0.1.2` (latest) | Tenacity retries resuming from the last valid pipeline step; unfixable self-review rejections redraft instead of aborting |
| `0.1.1` | Live E2E fixes: `X-API-Key` auth + `/api/new` endpoint, JSON payload sanitization, robust LLM-response parsing; dedup marked only after successful publish; docs match actual data sources |
| `0.1.0` | Initial implementation |

## License

MIT
