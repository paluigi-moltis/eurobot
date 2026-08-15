FROM python:3.12-slim

LABEL maintainer="Luigi Palumbo"
LABEL description="Autonomous euro-area economic reporting pipeline"
LABEL org.opencontainers.image.title="eurobot"
LABEL org.opencontainers.image.description="Autonomous euro-area economic reporting pipeline: fetches ECB/Eurostat, market and news data, drafts an LLM report and publishes it to a zzboard API"
LABEL org.opencontainers.image.source="https://github.com/paluigi/eurobot"
LABEL org.opencontainers.image.licenses="MIT"

# Install cron and curl (for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY config/ ./config/

# Install dependencies using uv
RUN uv pip install --system --no-cache .

# Create data directories
RUN mkdir -p /app/data/posts

# Copy crontab
COPY crontab /etc/cron.d/eurobot-cron
RUN chmod 0644 /etc/cron.d/eurobot-cron && \
    crontab /etc/cron.d/eurobot-cron && \
    touch /var/log/cron.log

# Environment defaults (overridden by docker-compose env_file)
ENV EUROBOT_CONFIG_DIR=/app/config \
    EUROBOT_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

# Volume mount points
VOLUME ["/app/config", "/app/data"]

# Run cron in foreground
CMD ["cron", "-f"]
