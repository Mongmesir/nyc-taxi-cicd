# NYC Yellow Taxi & Taxi Zones CI/CD Pipeline

Automated batch data ingestion, validation, spatial zone enrichment, and Azure Blob Storage delivery pipeline built with Python and GitHub Actions.

## Data Sources (NYC Open Data REST API)

- **NYC Yellow Taxi Trips (CSV):** `https://data.cityofnewyork.us/resource/4b4i-vvec.csv?$limit=25000&$offset=0`
- **NYC Taxi Zones + Geometry (JSON):** `https://data.cityofnewyork.us/resource/8meu-9t5y.json?$limit=300`

## Project Structure

```text
nyc-taxi-cicd/
├── .github/workflows/
│   └── ci-cd-pipeline.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
├── src/
│   ├── config.py
│   ├── ingest.py
│   ├── transform.py
│   ├── validate.py
│   ├── pipeline.py
│   └── upload_blob.py
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── requirements.txt
└── requirements-dev.txt
```

## Local Usage

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
python -m src.pipeline fixture --output-dir artifacts/local_fixture
python -m src.pipeline live --limit 1000 --offset 0 --output-dir artifacts/local_live
```

## CI/CD Architecture

- **CI (`push` / `pull_request`):** Runs `pytest` unit & integration tests, executes the fixture pipeline, and uploads verified CSV/JSON build artifacts.
- **CD (`schedule: "0 */6 * * *"` / `workflow_dispatch`):** Runs after CI succeeds, ingests live NYC Open Data batches, authenticates to Azure via Entra ID OIDC (`azure/login@v2`), uploads outputs to a private Azure Blob container, and verifies every uploaded blob.
