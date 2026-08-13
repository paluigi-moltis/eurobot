"""fetchers package — data acquisition from SDMX, Yahoo Finance, and RSS."""

from eurobot.fetchers.sdmx_fetcher import fetch_all_macro
from eurobot.fetchers.market_fetcher import fetch_all_markets, compute_btp_bund_spread

__all__ = ["fetch_all_macro", "fetch_all_markets", "compute_btp_bund_spread"]
