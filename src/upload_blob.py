"""Upload pipeline artifacts to Azure Blob Storage and verify uploaded blobs."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def _run_az(az_exe: str, args: list[str]) -> str:
    """Execute an Azure CLI command and return stripped stdout."""
    result = subprocess.run(
        [az_exe, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_upload_manifest(input_dir: Path, run_id: str) -> list[tuple[Path, str]]:
    """Map local pipeline outputs to raw/, processed/, metadata/, and latest/ blob paths."""
    candidates: list[tuple[str, str]] = [
        ("raw_trips.csv", f"raw/{run_id}/raw_trips.csv"),
        ("raw_zones.json", f"raw/{run_id}/raw_zones.json"),
        ("trips_enriched.csv", f"processed/{run_id}/trips_enriched.csv"),
        ("zone_summary.csv", f"processed/{run_id}/zone_summary.csv"),
        ("zones_lookup.csv", f"processed/{run_id}/zones_lookup.csv"),
        ("run_metadata.json", f"metadata/{run_id}/run_metadata.json"),
        ("trips_enriched.csv", "latest/trips_enriched.csv"),
        ("zone_summary.csv", "latest/zone_summary.csv"),
        ("zones_lookup.csv", "latest/zones_lookup.csv"),
        ("run_metadata.json", "latest/run_metadata.json"),
    ]
    manifest: list[tuple[Path, str]] = []
    for filename, blob_name in candidates:
        local_file = input_dir / filename
        if local_file.is_file():
            manifest.append((local_file, blob_name))
    return manifest


def upload_and_verify(
    account: str,
    container: str,
    input_dir: Path,
    run_id: str,
) -> list[str]:
    """Upload pipeline outputs via Entra OIDC login and verify each blob exists."""
    az_exe = shutil.which("az")
    if not az_exe:
        raise RuntimeError("Azure CLI ('az') was not found in PATH")

    manifest = build_upload_manifest(input_dir, run_id)
    if not manifest:
        raise FileNotFoundError(f"No pipeline output files found in {input_dir}")

    uploaded: list[str] = []
    for local_file, blob_name in manifest:
        print(f"Uploading {local_file.name} -> {container}/{blob_name}")
        _run_az(
            az_exe,
            [
                "storage",
                "blob",
                "upload",
                "--account-name",
                account,
                "--container-name",
                container,
                "--name",
                blob_name,
                "--file",
                str(local_file),
                "--auth-mode",
                "login",
                "--overwrite",
                "--only-show-errors",
            ],
        )
        exists_out = _run_az(
            az_exe,
            [
                "storage",
                "blob",
                "exists",
                "--account-name",
                account,
                "--container-name",
                container,
                "--name",
                blob_name,
                "--auth-mode",
                "login",
                "--query",
                "exists",
                "-o",
                "tsv",
                "--only-show-errors",
            ],
        )
        if exists_out.lower() != "true":
            raise RuntimeError(f"Verification failed: blob {blob_name} does not exist")
        uploaded.append(blob_name)

    print(f"Verified {len(uploaded)} blobs in {account}/{container}")
    return uploaded


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for Azure Blob Storage upload."""
    parser = argparse.ArgumentParser(description="Upload NYC Taxi outputs to Azure Blob")
    parser.add_argument("--account", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    upload_and_verify(
        account=args.account,
        container=args.container,
        input_dir=args.input_dir,
        run_id=args.run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
