"""Integration tests for the end-to-end fixture ingestion pipeline."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.pipeline import run_fixture_pipeline, run_live_pipeline


def test_run_fixture_pipeline_produces_expected_outputs(tmp_path: Path) -> None:
    metadata = run_fixture_pipeline(output_dir=tmp_path)

    assert metadata["mode"] == "fixture"
    assert metadata["raw_trip_count"] == 8
    assert metadata["valid_trip_count"] == 6
    assert metadata["rejected_trip_count"] == 2
    assert metadata["zones_count"] == 7
    assert metadata["anomaly_count"] == 1

    expected_files = [
        "trips_enriched.csv",
        "zone_summary.csv",
        "zones_lookup.csv",
        "run_metadata.json",
    ]
    for filename in expected_files:
        assert (tmp_path / filename).is_file()

    with (tmp_path / "trips_enriched.csv").open("r", encoding="utf-8") as handle:
        enriched_rows = list(csv.DictReader(handle))
    assert len(enriched_rows) == 6
    assert enriched_rows[0]["pu_zone"] == "Midtown Center"
    assert enriched_rows[0]["do_zone"] == "Lenox Hill West"

    saved_meta = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert saved_meta["valid_trip_count"] == 6


def test_run_live_pipeline_rejects_unsupported_dataset_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported dataset_id"):
        run_live_pipeline(output_dir=tmp_path, dataset_id="invalid-id")
