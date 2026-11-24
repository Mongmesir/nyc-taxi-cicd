"""Spatial centroid extraction, trip enrichment, and zone summary aggregation."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from typing import Any

from src.config import ANOMALY_FARE_PER_MILE, ANOMALY_TOTAL_AMOUNT
from src.validate import (
    compute_duration_minutes,
    parse_optional_float,
    parse_required_int,
    validate_trip_row,
)


def _iter_lon_lat_pairs(coords: Any) -> list[tuple[float, float]]:
    """Recursively flatten GeoJSON Polygon/MultiPolygon coordinates into (lon, lat) pairs."""
    if not isinstance(coords, (list, tuple)) or not coords:
        return []
    if isinstance(coords[0], (int, float)) and len(coords) >= 2:
        return [(float(coords[0]), float(coords[1]))]

    pairs: list[tuple[float, float]] = []
    for item in coords:
        pairs.extend(_iter_lon_lat_pairs(item))
    return pairs


def compute_centroid(the_geom: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Return rounded (latitude, longitude) centroid from a GeoJSON geometry object."""
    if not isinstance(the_geom, dict):
        return None, None
    pairs = _iter_lon_lat_pairs(the_geom.get("coordinates"))
    if not pairs:
        return None, None

    avg_lon = sum(lon for lon, _ in pairs) / len(pairs)
    avg_lat = sum(lat for _, lat in pairs) / len(pairs)
    return round(avg_lat, 6), round(avg_lon, 6)


def build_zones_lookup(raw_zones: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Build a lookup map keyed by integer location_id from NYC Open Data JSON."""
    lookup: dict[int, dict[str, Any]] = {}
    for record in raw_zones:
        raw_id = record.get("locationid") or record.get("location_id")
        if raw_id is None:
            continue
        loc_id = parse_required_int(raw_id)
        lat, lon = compute_centroid(record.get("the_geom"))
        lookup[loc_id] = {
            "location_id": loc_id,
            "borough": str(record.get("borough") or "Unknown").strip(),
            "zone": str(record.get("zone") or "Unknown").strip(),
            "centroid_lat": lat,
            "centroid_lon": lon,
        }
    return lookup


def parse_trips_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse raw NYC Yellow Taxi CSV text into normalized-key row dictionaries."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        cleaned = {
            (k.strip().lower() if k else ""): (v.strip() if isinstance(v, str) else v)
            for k, v in raw_row.items()
            if k is not None
        }
        rows.append(cleaned)
    return rows


def _zone_fields(
    loc_id: int,
    zones_lookup: dict[int, dict[str, Any]],
    prefix: str,
) -> dict[str, Any]:
    """Resolve borough, zone name, and centroid for a pickup or dropoff ID."""
    zone = zones_lookup.get(loc_id)
    if zone is None:
        return {
            f"{prefix}_borough": "Unknown",
            f"{prefix}_zone": f"Zone {loc_id}",
            f"{prefix}_lat": None,
            f"{prefix}_lon": None,
        }
    return {
        f"{prefix}_borough": zone["borough"],
        f"{prefix}_zone": zone["zone"],
        f"{prefix}_lat": zone["centroid_lat"],
        f"{prefix}_lon": zone["centroid_lon"],
    }


def transform_trips(
    raw_trips: list[dict[str, Any]],
    zones_lookup: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Validate, enrich with zone metadata, and flag fare anomalies."""
    enriched: list[dict[str, Any]] = []
    rejected_counts: Counter[str] = Counter()

    for row in raw_trips:
        is_valid, reason = validate_trip_row(row)
        if not is_valid:
            rejected_counts[reason] += 1
            continue

        pu_id = parse_required_int(row["pulocationid"])
        do_id = parse_required_int(row["dolocationid"])
        distance = float(row["trip_distance"])
        fare = float(row["fare_amount"])
        total = float(row["total_amount"])
        tip = parse_optional_float(row.get("tip_amount"), 0.0)
        tolls = parse_optional_float(row.get("tolls_amount"), 0.0)
        passengers = int(round(parse_optional_float(row.get("passenger_count"), 1.0)))
        duration_min = round(
            compute_duration_minutes(
                row["tpep_pickup_datetime"],
                row["tpep_dropoff_datetime"],
            ),
            2,
        )
        fare_per_mile = round(fare / distance, 2)
        is_anomaly = (
            fare_per_mile >= ANOMALY_FARE_PER_MILE or total >= ANOMALY_TOTAL_AMOUNT
        )

        record: dict[str, Any] = {
            "vendorid": parse_required_int(row.get("vendorid", 0))
            if str(row.get("vendorid", "")).strip()
            else 0,
            "tpep_pickup_datetime": row["tpep_pickup_datetime"],
            "tpep_dropoff_datetime": row["tpep_dropoff_datetime"],
            "duration_minutes": duration_min,
            "passenger_count": passengers,
            "trip_distance": round(distance, 2),
            "pulocationid": pu_id,
            **_zone_fields(pu_id, zones_lookup, "pu"),
            "dolocationid": do_id,
            **_zone_fields(do_id, zones_lookup, "do"),
            "fare_amount": round(fare, 2),
            "tip_amount": round(tip, 2),
            "tolls_amount": round(tolls, 2),
            "total_amount": round(total, 2),
            "fare_per_mile": fare_per_mile,
            "is_fare_anomaly": is_anomaly,
        }
        enriched.append(record)

    return enriched, dict(rejected_counts)


def build_zone_summary(enriched_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate trip volume, average fare/distance, revenue, and anomalies per pickup zone."""
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched_rows:
        key = (row["pulocationid"], row["pu_borough"], row["pu_zone"])
        grouped[key].append(row)

    summary: list[dict[str, Any]] = []
    for (pu_id, borough, zone_name), items in grouped.items():
        count = len(items)
        total_fare = sum(float(item["fare_amount"]) for item in items)
        total_dist = sum(float(item["trip_distance"]) for item in items)
        total_rev = sum(float(item["total_amount"]) for item in items)
        anomaly_cnt = sum(1 for item in items if item["is_fare_anomaly"])
        summary.append(
            {
                "pulocationid": pu_id,
                "pu_borough": borough,
                "pu_zone": zone_name,
                "trip_count": count,
                "avg_fare": round(total_fare / count, 2),
                "avg_distance": round(total_dist / count, 2),
                "total_revenue": round(total_rev, 2),
                "anomaly_count": anomaly_cnt,
            }
        )

    summary.sort(
        key=lambda item: (-item["trip_count"], -item["total_revenue"], item["pulocationid"])
    )
    return summary
