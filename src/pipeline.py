"""CLI entry point orchestrating fixture and live NYC Taxi ingestion pipelines."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import (
    DEFAULT_BATCH_LIMIT,
    DEFAULT_DATASET_ID,
    DEFAULT_ZONES_LIMIT,
    SAMPLE_DATA_DIR,
    TRIPS_ENRICHED_COLUMNS,
    ZONE_SUMMARY_COLUMNS,
    ZONES_LOOKUP_COLUMNS,
)
from src.ingest import fetch_trips_csv, fetch_zones_json
from src.transform import (
    build_zone_summary,
    build_zones_lookup,
    parse_trips_csv,
    transform_trips,
)
from src.validate import validate_enriched_dataset


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Write a list of dictionaries to CSV with deterministic headers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _append_markdown_summary(
    summary_path: Path,
    metadata: dict[str, Any],
    zone_summary: list[dict[str, Any]],
) -> None:
    """Append a concise Markdown report table (for GitHub Actions Job Summary)."""
    lines = [
        f"### NYC Taxi Pipeline Summary (`{metadata['mode']}`)",
        "",
        f"- **Dataset ID:** `{metadata['dataset_id']}` (limit `{metadata['limit']}`, offset `{metadata['offset']}`)",
        f"- **Raw Trips:** {metadata['raw_trip_count']} | **Valid Trips:** {metadata['valid_trip_count']} | **Rejected:** {metadata['rejected_trip_count']}",
        f"- **Zones Loaded:** {metadata['zones_count']} | **Fare Anomalies:** {metadata['anomaly_count']}",
        "",
        "| PU ID | Borough | Pickup Zone | Trips | Avg Fare ($) | Total Revenue ($) | Anomalies |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in zone_summary[:5]:
        lines.append(
            f"| {row['pulocationid']} | {row['pu_borough']} | {row['pu_zone']} "
            f"| {row['trip_count']} | {row['avg_fare']:.2f} | {row['total_revenue']:.2f} | {row['anomaly_count']} |"
        )
    lines.append("")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _execute_pipeline(
    mode: str,
    raw_trips_csv: str,
    raw_zones: list[dict[str, Any]],
    output_dir: Path,
    dataset_id: str,
    limit: int,
    offset: int,
    save_raw: bool,
    summary_markdown: Path | None = None,
) -> dict[str, Any]:
    """Run parsing, validation, transformation, and write output artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if save_raw:
        (output_dir / "raw_trips.csv").write_text(raw_trips_csv, encoding="utf-8")
        (output_dir / "raw_zones.json").write_text(
            json.dumps(raw_zones, indent=2), encoding="utf-8"
        )

    raw_trips = parse_trips_csv(raw_trips_csv)
    zones_lookup = build_zones_lookup(raw_zones)
    enriched_rows, rejected_counts = transform_trips(raw_trips, zones_lookup)
    validate_enriched_dataset(enriched_rows, min_rows=1)
    zone_summary = build_zone_summary(enriched_rows)
    zones_list = sorted(zones_lookup.values(), key=lambda z: z["location_id"])

    _write_csv(output_dir / "trips_enriched.csv", TRIPS_ENRICHED_COLUMNS, enriched_rows)
    _write_csv(output_dir / "zone_summary.csv", ZONE_SUMMARY_COLUMNS, zone_summary)
    _write_csv(output_dir / "zones_lookup.csv", ZONES_LOOKUP_COLUMNS, zones_list)

    anomaly_count = sum(1 for row in enriched_rows if row["is_fare_anomaly"])
    metadata: dict[str, Any] = {
        "mode": mode,
        "dataset_id": dataset_id,
        "limit": limit,
        "offset": offset,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_trip_count": len(raw_trips),
        "valid_trip_count": len(enriched_rows),
        "rejected_trip_count": sum(rejected_counts.values()),
        "rejected_reasons": rejected_counts,
        "zones_count": len(zones_list),
        "unique_pickup_zones": len(zone_summary),
        "anomaly_count": anomaly_count,
        "top_pickup_zones": zone_summary[:5],
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    if summary_markdown is not None:
        _append_markdown_summary(summary_markdown, metadata, zone_summary)

    print(
        f"[{mode}] raw={metadata['raw_trip_count']} valid={metadata['valid_trip_count']} "
        f"rejected={metadata['rejected_trip_count']} zones={metadata['zones_count']} "
        f"anomalies={metadata['anomaly_count']}"
    )
    print("Top 5 Pickup Zones:")
    for item in zone_summary[:5]:
        print(
            f"  - {item['pu_zone']} ({item['pu_borough']}, ID={item['pulocationid']}): "
            f"trips={item['trip_count']}, avg_fare=${item['avg_fare']:.2f}, "
            f"revenue=${item['total_revenue']:.2f}"
        )

    return metadata


def run_fixture_pipeline(
    output_dir: Path,
    sample_dir: Path = SAMPLE_DATA_DIR,
    summary_markdown: Path | None = None,
) -> dict[str, Any]:
    """Run the offline pipeline against bundled sample CSV and JSON fixtures."""
    trips_csv = (sample_dir / "trips_sample.csv").read_text(encoding="utf-8")
    zones_json = json.loads((sample_dir / "zones_sample.json").read_text(encoding="utf-8"))
    return _execute_pipeline(
        mode="fixture",
        raw_trips_csv=trips_csv,
        raw_zones=zones_json,
        output_dir=output_dir,
        dataset_id="fixture-sample",
        limit=0,
        offset=0,
        save_raw=False,
        summary_markdown=summary_markdown,
    )


def run_live_pipeline(
    output_dir: Path,
    dataset_id: str = DEFAULT_DATASET_ID,
    limit: int = DEFAULT_BATCH_LIMIT,
    offset: int = 0,
    summary_markdown: Path | None = None,
) -> dict[str, Any]:
    """Run the live pipeline against NYC Open Data Trips CSV and Zones JSON APIs."""
    trips_csv = fetch_trips_csv(dataset_id=dataset_id, limit=limit, offset=offset)
    zones_json = fetch_zones_json(limit=DEFAULT_ZONES_LIMIT)
    return _execute_pipeline(
        mode="live",
        raw_trips_csv=trips_csv,
        raw_zones=zones_json,
        output_dir=output_dir,
        dataset_id=dataset_id,
        limit=limit,
        offset=offset,
        save_raw=True,
        summary_markdown=summary_markdown,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser for fixture and live pipeline modes."""
    parser = argparse.ArgumentParser(description="NYC Yellow Taxi CI/CD Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode_name in ("fixture", "live"):
        sub = subparsers.add_parser(mode_name)
        sub.add_argument("--output-dir", type=Path, required=True)
        sub.add_argument("--summary-markdown", type=Path, default=None)
        if mode_name == "fixture":
            sub.add_argument("--sample-dir", type=Path, default=SAMPLE_DATA_DIR)
        else:
            sub.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
            sub.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT)
            sub.add_argument("--offset", type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    if args.mode == "fixture":
        run_fixture_pipeline(
            output_dir=args.output_dir,
            sample_dir=args.sample_dir,
            summary_markdown=args.summary_markdown,
        )
    else:
        run_live_pipeline(
            output_dir=args.output_dir,
            dataset_id=args.dataset_id,
            limit=args.limit,
            offset=args.offset,
            summary_markdown=args.summary_markdown,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
