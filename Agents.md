# Agents.md — Coding Agent Guidelines for Omnifin

## 1. Environment & Execution

Always use `uv run` for backend commands. Never use bare `python` or `pytest`.

```bash
# Running the CLI
uv run fin --help
uv run fin init-db --db data/omnifin.db

# Running tests
uv run pytest tests -q

# Linting
uv run ruff check omnifin/

# Installing in editable mode (only when needed)
uv pip install -e .
```

Frontend commands use npm directly:

```bash
npm --prefix frontend install
npm --prefix frontend run build
npm run dev  # from repo root, starts both backend proxy and frontend
```

## 2. Testing Requirements

Every new feature must be accompanied by systematic unit tests using `pytest`.

- Tests live in `tests/`
- Test files are named `test_<module>.py`
- Use `tmp_path` fixture for isolated SQLite databases per test
- Call `clear_global_identity_map()` before/after tests that use domain models (use the `autouse` fixture from `conftest.py`)
- Mock external dependencies (LLM calls, uvicorn) — never require Ollama or a running server in tests
- Run `uv run pytest tests -q --ignore=tests/test_seeding.py` before considering any task complete

When appropriate, also include:
- Manual verification instructions (exact commands to run and expected output)
- CLI usage examples in docstrings or help text

## 3. Documentation Obligations

This file (`Agents.md`) and the guides in `docs/` must always be updated to reflect:

- Changes to CLI commands (new commands, changed options, removed commands)
- Changes to API endpoints
- Changes to build/test/run instructions
- Ongoing progress on milestones (update `docs/IMPLEMENTATION_ROADMAP.md`)
- New conventions or architectural decisions

When completing a phase or significant milestone, update:
- `docs/IMPLEMENTATION_ROADMAP.md` — mark tasks complete, note what's scaffold-only
- `tests/test_plan.md` — update test coverage status
- This file (`Agents.md`) — if execution conventions changed

## 4. Code Conventions

- CLI commands use `click` and live in `omnifin/cli/`
- Domain models use Pydantic v2 and live in `omnifin/models/`
- All data classes use strict typing (no `Any` in public APIs where avoidable)
- Every CLI command must work headless (no server required)
- Commands that mutate data default to preview mode (safe by default)
- The `--db` option defaults to `omnifin.db` on every command

## 5. Monorepo Structure

```
fin/
├── Agents.md                 # This file
├── Makefile                  # Build/dev shortcuts
├── pyproject.toml            # Python package config, entry point: fin
├── omnifin/                  # Installable Python package
│   ├── cli/                  # Click CLI commands
│   ├── core/                 # Database, IDs, registry, errors
│   ├── models/               # Pydantic domain models
│   ├── ingest/               # CSV normalization
│   ├── tax/                  # Tax engines (US/DE)
│   ├── reconcile/            # Reconciliation
│   ├── ai/                   # LLM integration
│   ├── api/                  # FastAPI server
│   └── db/                   # Schema SQL, seeding
├── tests/                    # pytest test suite
├── frontend/                 # Vite + React + TypeScript
├── docs/                     # Guides, roadmaps, schema docs
└── memory-bank/              # Project brief
```

## 6. Current State Summary

See `docs/IMPLEMENTATION_ROADMAP.md` for the full milestone roadmap.

**CLI commands that exist and work:** `fin init-db`, `fin normalize`, `fin tax` (scaffold), `fin serve`
**CLI commands planned:** `fin info`, `fin assets`, `fin statement`, `fin reconcile`, `fin audit`, `fin report undo`

**Domain model:** Fully implemented and well-tested.
**Tax engines:** Scaffold only (no real logic).
**Reconciliation:** Minimal single-statement check, untested.
**AI integration:** Fully implemented, untested.
**Web interface:** 42 API endpoints, 3 frontend views (deferred to separate phase).
