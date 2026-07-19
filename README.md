# Omnifin Seed Repo

Omnifin is a local-first financial ledger and normalization toolkit. This seed
repo implements the foundation discussed in the design conversation:

- an installable Python backend package named `omnifin`
- a CLI entry point named `fin`
- a FastAPI backend server
- a Vite/React frontend
- a root `npm run dev` command that starts both backend and frontend via `concurrently`
- a normalized SQLite schema using strict tables and foreign keys
- high-level Pydantic domain objects with lazy loading, session-scoped identity maps, staged edits, `Report.plan()`, and `Report.save()`
- unit tests covering singleton identity, scalar coercion, graph planning/saving, staged tags/comments, and lazy hydration

## Repository layout

```text
fin/
├── package.json                    # root dev orchestration; npm run dev starts both servers
├── Makefile
├── pyproject.toml                  # installable omnifin package and fin CLI
├── omnifin/
│   ├── api/server.py               # FastAPI app
│   ├── ai/structured.py            # modular local-LLM structured-output wrapper
│   ├── cli/main.py                 # fin commands
│   ├── core/                       # db session, ids, registry, errors
│   ├── db/schema.sql               # SQLite STRICT schema
│   ├── ingest/normalize.py         # generic CSV normalization milestone
│   ├── models/domain.py            # high-level domain layer
│   ├── reconcile/                  # reconciliation scaffold
│   └── tax/                        # US/DE tax engine scaffolds
├── tests/
│   └── test_domain.py
└── frontend/
    ├── package.json
    ├── vite.config.ts              # proxies /api to FastAPI
    └── src/                        # simple dashboard skeleton
```

## Quick start

From the repo root:

```bash
python -m pip install -e .
python -m pytest
```

Then install frontend tooling and start the full stack:

```bash
npm install
npm --prefix frontend install
npm run dev
```

The backend runs on `http://127.0.0.1:8000`; the frontend runs on
`http://127.0.0.1:5173` and proxies `/api` requests to FastAPI.

## CLI examples

```bash
fin init-db --db data/omnifin.db
fin normalize ~/Downloads/activity.csv --db data/omnifin.db --output data/normalized.csv --json-plan
fin normalize ~/Downloads/activity.csv --db data/omnifin.db --save
fin serve --db data/omnifin.db --port 8000
fin tax --db data/omnifin.db --jurisdiction US --year 2026
```

## Domain example

```python
from datetime import UTC, datetime
from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Report, Statement

with DatabaseSession("data/omnifin.db") as session:
    report = Report(_session=session, name="Fidelity import")

    statement = Statement(
        date=datetime(2026, 1, 1, tzinfo=UTC),
        account=Account(name="Fidelity Taxable", type="internal"),
        unit="USD",                 # coerced into Asset("USD")
        balance=100.50,
    )
    statement.add_tags("taxable_2026")
    statement.comment("Validated against source CSV")

    plan = report.plan(statement)   # dry run
    if plan.is_valid:
        report.save(statement)      # atomic commit
```

## Design notes and improvements applied

The seed code makes a few intentional changes relative to the rough SQL sketches:

1. **Reports are provenance records, not cascading parents of core objects.**
   `report_id` is retained as nullable provenance. Deleting a report should not
   silently delete global assets or accounts; cleanup can be implemented as an
   explicit import-rollback workflow later.

2. **Currencies are assets.**
   `Asset("USD")`, `Asset("EUR")`, stocks, ETFs, crypto, and funds all share the
   same asset registry.

3. **Separate junction tables preserve referential integrity.**
   Tags and comments use per-object junction tables rather than polymorphic
   `(object_type, object_id)` references.

4. **The identity map is session scoped.**
   `DatabaseSession` owns the cache, preventing stale object leakage between
   imports. A small global cache remains only for objects created before a
   session is attached.

5. **`Report.plan()` and `Report.save()` share the same graph traversal.**
   The dry run is not a separate guess; it sees the same nested objects,
   dependencies, staged tags/comments, and relation writes that `save()` will use.

6. **Staged edits do not hit SQLite until saved.**
   `add_tags`, `comment`, `add_entities`, and `add_involved` update local state.
   The merged local view is returned immediately, then `Report.save()` flushes the
   junction-table changes.

7. **Lazy placeholders are allowed.**
   `Statement(unit="USD")` creates an `Asset("USD")` placeholder. If it already
   exists in SQLite, accessing non-identity fields can hydrate it; if it does not,
   `Report.save(statement)` inserts it as part of the object graph.

## Current limitations

This is a foundation, not a complete tax engine. The US and German tax modules
are scaffolds, and broker-specific Fidelity/IBKR parsers should be added on top
of the generic CSV normalizer. The next major work items are:

- broker-specific Fidelity activity, Fidelity closed positions, and IBKR Flex parsers
- trade conversion / fee modeling beyond single-leg `Transfer` records
- lot matching, US wash sales, German FIFO, ETF partial exemptions, and Vorabpauschale
- import rollback and audit-log workflows
- generated TypeScript API client from FastAPI OpenAPI
- richer web editing and reconciliation screens
