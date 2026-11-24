"""Unit tests for NYC trip row and enriched dataset data-contract validation."""

from __future__ import annotations

import pytest

from src.config import TRIPS_ENRICHED_COLUMNS
from src.validate import validate_enriched_dataset, validate_trip_row


def _valid_raw_trip() -> dict[str, str]:
    return {
        "vendorid": "2",
        "tpep_pickup_datetime": "2023-01-01T00:32:10.000",
        "tpep_dropoff_datetime": "2023-01-01T00:40:36.000",
        "passenger_count": "1.0",
        "trip_distance": "1.5",
        "pulocationid": "161",
        "dolocationid": "141",
        "fare_amount": "10.0",
        "total_amount": "15.0",
    }


def test_validate_trip_row_accepts_valid_record() -> None:
    is_valid, reason = validate_trip_row(_valid_raw_trip())
    assert is_valid is True
    assert reason == "ok"


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("fare_amount", "-5.0", "invalid_fare"),
        ("trip_distance", "0.0", "invalid_distance"),
        ("total_amount", "0.0", "invalid_total_amount"),
        ("pulocationid", "0", "invalid_location_id"),
        ("tpep_dropoff_datetime", "2023-01-01T00:30:00.000", "invalid_duration"),
        ("tpep_pickup_datetime", "not-a-timestamp", "invalid_datetime"),
    ],
)
def test_validate_trip_row_rejects_invalid_records(
    field: str,
    value: str,
    expected_reason: str,
) -> None:
    row = _valid_raw_trip()
    row[field] = value
    is_valid, reason = validate_trip_row(row)
    assert is_valid is False
    assert reason == expected_reason


def test_validate_enriched_dataset_enforces_schema_and_non_empty() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        validate_enriched_dataset([], min_rows=1)

    complete_row = {col: "x" for col in TRIPS_ENRICHED_COLUMNS}
    validate_enriched_dataset([complete_row], min_rows=1)

    incomplete_row = dict(complete_row)
    incomplete_row.pop("fare_per_mile")
    with pytest.raises(ValueError, match="missing required columns"):
        validate_enriched_dataset([incomplete_row], min_rows=1)
