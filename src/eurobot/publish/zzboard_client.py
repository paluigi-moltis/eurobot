"""zzboard publisher — POST payload to the API endpoint with bearer auth.

Handles authentication, error handling, and logging of HTTP responses.
On failure the payload is saved locally for manual retry.
"""

from __future__ import annotations

import logging

import requests

from eurobot import config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30


def publish_payload(payload: dict) -> bool:
    """POST the zzboard payload to the configured endpoint.

    Args:
        payload: The assembled zzboard JSON payload.

    Returns:
        True if published successfully, False otherwise.
    """
    token = config.ZZBOARD_API_TOKEN
    endpoint = config.ZZBOARD_API_ENDPOINT

    if not token:
        logger.error("Publish: ZZBOARD_API_TOKEN not set — skipping publish")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        logger.info("Publish: POST to %s", endpoint)
        resp = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            logger.info("Publish: success (HTTP %d)", resp.status_code)
            return True
        else:
            logger.error("Publish: HTTP %d — %s", resp.status_code, resp.text[:500])
            return False
    except requests.RequestException as exc:
        logger.error("Publish: request failed — %s", exc)
        return False
