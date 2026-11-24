"""Central configuration, API endpoints, and validation thresholds."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = PROJECT_ROOT / "data" / "sample"

DEFAULT_DATASET_ID = "4b4i-vvec"
TRIPS_URL_TEMPLATE = "https://data.cityofnewyork.us/resource/{dataset_id}.csv"
ZONES_URL = "https://data.cityofnewyork.us/resource/8meu-9t5y.json"

DEFAULT_BATCH_LIMIT = 25000
DEFAULT_ZONES_LIMIT = 300

# Data-contract validation bounds
MAX_FARE_AMOUNT = 1000.0
MAX_TRIP_DISTANCE_MI = 200.0
MAX_DURATION_MIN = 360.0

# Fare anomaly thresholds
ANOMALY_FARE_PER_MILE = 25.0
ANOMALY_TOTAL_AMOUNT = 250.0

TRIPS_ENRICHED_COLUMNS = [
    "vendorid",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "duration_minutes",
    "passenger_count",
    "trip_distance",
    "pulocationid",
    "pu_borough",
    "pu_zone",
    "pu_lat",
    "pu_lon",
    "dolocationid",
    "do_borough",
    "do_zone",
    "do_lat",
    "do_lon",
    "fare_amount",
    "tip_amount",
    "tolls_amount",
    "total_amount",
    "fare_per_mile",
    "is_fare_anomaly",
]

ZONE_SUMMARY_COLUMNS = [
    "pulocationid",
    "pu_borough",
    "pu_zone",
    "trip_count",
    "avg_fare",
    "avg_distance",
    "total_revenue",
    "anomaly_count",
]

ZONES_LOOKUP_COLUMNS = [
    "location_id",
    "borough",
    "zone",
    "centroid_lat",
    "centroid_lon",
]
