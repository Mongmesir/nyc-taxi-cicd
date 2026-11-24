"""HTTP ingestion helpers for NYC Open Data Yellow Taxi and Taxi Zones APIs."""

from __future__ import annotations

import time
from typing import Any

import requests

from src.config import (
    DEFAULT_BATCH_LIMIT,
    DEFAULT_DATASET_ID,
    DEFAULT_ZONES_LIMIT,
    TRIPS_URL_TEMPLATE,
    ZONES_URL,
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def fetch_with_retry(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 60,
    max_retries: int = 4,
    backoff_seconds: float = 2.0,
) -> requests.Response:
    """Perform a GET request with exponential backoff for transient HTTP errors."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(
                    f"Retryable HTTP {response.status_code} from {url}",
                    response=response,
                )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(backoff_seconds * (2**attempt))

    raise RuntimeError(
        f"Failed to fetch {url} after {max_retries} attempts: {last_error}"
    ) from last_error


def fetch_trips_csv(
    dataset_id: str = DEFAULT_DATASET_ID,
    limit: int = DEFAULT_BATCH_LIMIT,
    offset: int = 0,
) -> str:
    """Fetch a paginated CSV batch of NYC Yellow Taxi trips."""
    url = TRIPS_URL_TEMPLATE.format(dataset_id=dataset_id)
    response = fetch_with_retry(url, params={"$limit": limit, "$offset": offset})
    return response.text


def fetch_zones_json(limit: int = DEFAULT_ZONES_LIMIT) -> list[dict[str, Any]]:
    """Fetch NYC TLC Taxi Zones polygon records as JSON."""
    response = fetch_with_retry(ZONES_URL, params={"$limit": limit})
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Expected list JSON response from Taxi Zones endpoint")
    return payload
