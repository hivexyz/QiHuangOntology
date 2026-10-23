# QiHuang Shield Backend

FastAPI backend for the QiHuang Shield traditional Chinese medicine ontology
governance and knowledge service platform. The backend separates governance
operations (ingestion, review, validation, publishing) from read-only
knowledge services consumed by downstream applications.

## Storage modes

The backend supports two storage backends:

- `memory` - default local MVP mode
- `database` - PostgreSQL + Neo4j persistence mode

Configuration is loaded from `src/backend/.env` when present.

## Start PostgreSQL + Neo4j locally

```bash
cd src/backend
cp .env.example .env
docker compose up -d
```

Default local ports:

- PostgreSQL: `127.0.0.1:5432`
- Neo4j HTTP: `127.0.0.1:7474`
- Neo4j Bolt: `127.0.0.1:7687`

## Quick start (memory mode)

```bash
cd src/backend
UV_CACHE_DIR=../../.uv-cache uv sync --extra dev
UV_CACHE_DIR=../../.uv-cache uv run uvicorn qihuang_shield.app:app --app-dir src --host 127.0.0.1 --port 8001
```

## Quick start (database mode)

1. Start databases:

```bash
cd src/backend
cp .env.example .env
docker compose up -d
```

2. Install dependencies and run backend:

```bash
cd src/backend
UV_CACHE_DIR=../../.uv-cache uv sync --extra dev
UV_CACHE_DIR=../../.uv-cache uv run uvicorn qihuang_shield.app:app --app-dir src --host 127.0.0.1 --port 8001
```

On first startup with `QHS_STORAGE_BACKEND=database`, the app will:

- auto-create PostgreSQL tables
- auto-create Neo4j uniqueness constraint
- seed demo tenant / users / rules / policy / ontology into PostgreSQL + Neo4j only when `QHS_ENABLE_DEMO_SEED=true`

The default `.env.example` keeps demo seeding disabled. Do not use demo
credentials or default development secrets in a shared or production
environment.

## Core API surfaces

- Governance: `/api/v1/ontology/guideline-imports`,
  `/api/v1/ontology/import-jobs/{import_job_id}/governance`, normalization
  review (including staged normalization review and concept proposals),
  validation, and import-job publishing.
- Knowledge service: `/api/v1/ontology-base/concepts`, assertions, evidence,
  conditions, and `/api/v1/ontology-base/releases`.
- Retrieval: `/api/v1/vector-search/query` and `/api/v1/vector-search/rag-query`.

`kb_versions` is the current source of truth for knowledge releases. The
release read model exposes a stable release identifier, component counts,
validation report, publication state, and derived projection count without
introducing a second version table.

Unresolved mentions can enter a staged Concept Proposal workflow. A proposal
must include its ontology type, standard name, definition, and staged evidence.
Only an approved proposal creates a formal staged concept; the concept becomes
part of the global knowledge store only when the import job is published.

## Development

```bash
cd src/backend
UV_CACHE_DIR=../../.uv-cache uv run uvicorn qihuang_shield.app:app --app-dir src --reload
```

## Quality checks

```bash
cd src/backend
UV_CACHE_DIR=../../.uv-cache uv run ruff check src
UV_CACHE_DIR=../../.uv-cache uv run python -m compileall src
UV_CACHE_DIR=../../.uv-cache uv run pytest -q
UV_CACHE_DIR=../../.uv-cache uv run python scripts/evaluate_golden.py eval/golden_smoke.jsonl
```
