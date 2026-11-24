"""Data-contract validation rules for raw trip records and enriched datasets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.config import (
    MAX_DURATION_MIN,
    MAX_FARE_AMOUNT,
    MAX_TRIP_DISTANCE_MI,
    TRIPS_ENRICHED_COLUMNS,
)


def parse_optional_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric string/number to float, returning default when empty."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return float(text)


def parse_required_int(value: Any) -> int:
    """Parse an integer field that may arrive as '161' or '161.0'."""
    if value is None or str(value).strip() == "":
        raise ValueError("missing integer value")
    return int(float(str(value).strip()))


def compute_duration_minutes(pickup_iso: str, dropoff_iso: str) -> float:
    """Compute elapsed trip duration in minutes from ISO-8601 timestamps."""
    pickup_dt = datetime.fromisoformat(str(pickup_iso).strip().replace("Z", "+00:00"))
    dropoff_dt = datetime.fromisoformat(str(dropoff_iso).strip().replace("Z", "+00:00"))
    return (dropoff_dt - pickup_dt).total_seconds() / 60.0


def validate_trip_row(row: dict[str, Any]) -> tuple[bool, str]:
    """Validate one raw NYC trip record against schema and domain rules."""
    try:
        duration_min = compute_duration_minutes(
            row.get("tpep_pickup_datetime", ""),
            row.get("tpep_dropoff_datetime", ""),
        )
    except (TypeError, ValueError):
        return False, "invalid_datetime"

    if duration_min <= 0 or duration_min > MAX_DURATION_MIN:
        return False, "invalid_duration"

    try:
        pu_id = parse_required_int(row.get("pulocationid"))
        do_id = parse_required_int(row.get("dolocationid"))
    except ValueError:
        return False, "invalid_location_id"

    if pu_id < 1 or do_id < 1:
        return False, "invalid_location_id"

    try:
        distance = float(str(row.get("trip_distance", "")).strip())
        fare = float(str(row.get("fare_amount", "")).strip())
        total = float(str(row.get("total_amount", "")).strip())
    except (TypeError, ValueError):
        return False, "invalid_numeric"

    if distance <= 0 or distance > MAX_TRIP_DISTANCE_MI:
        return False, "invalid_distance"
    if fare <= 0 or fare > MAX_FARE_AMOUNT:
        return False, "invalid_fare"
    if total <= 0:
        return False, "invalid_total_amount"

    return True, "ok"


def validate_enriched_dataset(
    rows: list[dict[str, Any]],
    min_rows: int = 1,
) -> None:
    """Verify the enriched trip dataset is non-empty and matches the output contract."""
    if len(rows) < min_rows:
        raise ValueError(
            f"Expected at least {min_rows} valid enriched rows, got {len(rows)}"
        )

    expected = set(TRIPS_ENRICHED_COLUMNS)
    for idx, row in enumerate(rows):
        missing = expected - set(row.keys())
        if missing:
            raise ValueError(
                f"Enriched row {idx} missing required columns: {sorted(missing)}"
            )
