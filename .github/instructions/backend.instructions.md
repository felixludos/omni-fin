---
applyTo: "backend/**/*.py"
---
# Omnifin Backend & CLI (fin) Coding Standards

## Stack Specifications
- **Python:** >= 3.11
- **CLI Framework:** Click
- **API Framework:** FastAPI
- **Data Validation:** Pydantic v2
- **Database:** SQLite with SQLAlchemy ORM

## Click CLI (`fin`) Patterns
- All commands must be subcommands of the main group in `omnifin/cli.py`.
- Use explicit type annotations for Click arguments and options.
- CLI commands must operate fully statelessly or write directly to SQLite. They must *never* rely on a running FastAPI instance.
- Wrap complex pipeline executions (e.g., CSV ingest) in a progress bar or clear terminal output using `click.echo`.

## Data Models & Validation
- Inherit from Pydantic's `BaseModel` (v2 syntax).
- For ingest validation, enforce strict schemas for `Asset` and `UniversalEvent`.
- Always use timezone-aware datetimes (`datetime.now(timezone.utc)`).

## FastAPI API Standards
- Use Router-based architecture (`APIRouter`) structured by domain (e.g., `/api/v1/ledger`, `/api/v1/taxes`).
- Always use dependency injection (`Depends`) for database sessions and service layers.
- Match relative proxy pathways: All web endpoints must start with prefix `/api`.