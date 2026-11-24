"""Unit tests for spatial centroid extraction, zone lookup, enrichment, and summary."""

from __future__ import annotations

from src.transform import (
    build_zone_summary,
    build_zones_lookup,
    compute_centroid,
    transform_trips,
)


def test_compute_centroid_multipolygon() -> None:
    geom = {
        "type": "MultiPolygon",
        "coordinates": [[[[ -74.0, 40.7 ], [ -73.9, 40.7 ], [ -73.9, 40.8 ], [ -74.0, 40.8 ]]]],
    }
    lat, lon = compute_centroid(geom)
    assert lat == 40.75
    assert lon == -73.95


def test_compute_centroid_empty_returns_none() -> None:
    assert compute_centroid(None) == (None, None)
    assert compute_centroid({"type": "MultiPolygon", "coordinates": []}) == (None, None)


def test_build_zones_lookup_uses_locationid_key() -> None:
    raw_zones = [
        {
            "locationid": "161",
            "borough": "Manhattan",
            "zone": "Midtown Center",
            "the_geom": {
                "type": "MultiPolygon",
                "coordinates": [[[[-73.98, 40.75], [-73.97, 40.76]]]],
            },
        }
    ]
    lookup = build_zones_lookup(raw_zones)
    assert 161 in lookup
    assert lookup[161]["zone"] == "Midtown Center"
    assert lookup[161]["borough"] == "Manhattan"
    assert lookup[161]["centroid_lat"] == 40.755
    assert lookup[161]["centroid_lon"] == -73.975


def test_transform_trips_enriches_and_flags_anomaly() -> None:
    zones_lookup = {
        48: {
            "location_id": 48,
            "borough": "Manhattan",
            "zone": "Clinton East",
            "centroid_lat": 40.761,
            "centroid_lon": -73.9915,
        },
        161: {
            "location_id": 161,
            "borough": "Manhattan",
            "zone": "Midtown Center",
            "centroid_lat": 40.758,
            "centroid_lon": -73.977,
        },
    }
    raw_trips = [
        {
            "vendorid": "2",
            "tpep_pickup_datetime": "2023-01-01T00:00:00.000",
            "tpep_dropoff_datetime": "2023-01-01T00:10:00.000",
            "passenger_count": "1.0",
            "trip_distance": "2.0",
            "pulocationid": "161",
            "dolocationid": "48",
            "fare_amount": "12.0",
            "tip_amount": "3.0",
            "tolls_amount": "0.0",
            "total_amount": "17.5",
        },
        {
            "vendorid": "2",
            "tpep_pickup_datetime": "2023-01-01T03:00:00.000",
            "tpep_dropoff_datetime": "2023-01-01T03:08:00.000",
            "passenger_count": "1.0",
            "trip_distance": "0.5",
            "pulocationid": "48",
            "dolocationid": "161",
            "fare_amount": "45.0",
            "tip_amount": "0.0",
            "tolls_amount": "0.0",
            "total_amount": "50.0",
        },
        {
            "vendorid": "2",
            "tpep_pickup_datetime": "2023-01-01T04:00:00.000",
            "tpep_dropoff_datetime": "2023-01-01T04:05:00.000",
            "passenger_count": "1.0",
            "trip_distance": "0.0",
            "pulocationid": "48",
            "dolocationid": "161",
            "fare_amount": "10.0",
            "total_amount": "12.0",
        },
    ]

    enriched, rejected = transform_trips(raw_trips, zones_lookup)
    assert len(enriched) == 2
    assert rejected == {"invalid_distance": 1}

    normal_row, anomaly_row = enriched
    assert normal_row["pu_zone"] == "Midtown Center"
    assert normal_row["do_zone"] == "Clinton East"
    assert normal_row["duration_minutes"] == 10.0
    assert normal_row["is_fare_anomaly"] is False

    assert anomaly_row["fare_per_mile"] == 90.0
    assert anomaly_row["is_fare_anomaly"] is True

    summary = build_zone_summary(enriched)
    assert len(summary) == 2
    by_id = {item["pulocationid"]: item for item in summary}
    assert by_id[48]["anomaly_count"] == 1
    assert by_id[161]["total_revenue"] == 17.5
