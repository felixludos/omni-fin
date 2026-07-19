# Omnifin Quickstart

## Prerequisites

- Python 3.11+
- Node.js 18+

## Backend Setup

From repo root:

```bash
python -m pip install -e .
python -m pytest -q
```

## Frontend Setup

From repo root:

```bash
npm install
npm --prefix frontend install
npm run dev
```

## Useful CLI Commands

```bash
fin init-db --db data/omnifin.db
fin normalize cloud_data/extra/export.csv --db data/omnifin.db --output data/normalized.csv --json-plan
fin normalize cloud_data/extra/export.csv --db data/omnifin.db --save
fin tax --db data/omnifin.db --jurisdiction US --year 2026
fin serve --db data/omnifin.db --host 127.0.0.1 --port 8000 --reload
```

## API Endpoints (Current)

- `GET /api/health`
- `GET /api/assets`
- `GET /api/accounts`
- `GET /api/statements`
- `GET /api/transfers`
- `GET /api/reports`

## Notes

- Tax modules are scaffold implementations and currently return warning-first payloads.
- Prefer running tests from the repo root to use installed package resolution.
