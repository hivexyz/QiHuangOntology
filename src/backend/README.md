# QiHuang Shield Backend

FastAPI backend project managed by `uv`.

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
UV_CACHE_DIR=../../.uv-cache uv run uvicorn qihuang_shield.app:app --app-dir src --host 127.0.0.1 --port 8000
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
- seed demo tenant / users / rules / policy / ontology / review task into PostgreSQL + Neo4j if the database is empty

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
```
