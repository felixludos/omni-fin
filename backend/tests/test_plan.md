# Omnifin Test Plan

## 1. Objectives
The goal is to ensure the reliability and correctness of the Omnifin financial tracking system through a layered testing strategy:
- **Unit Tests**: Validate individual functions and components in isolation.
- **Integration Tests**: Validate the interaction between multiple components (e.g., Ingest -> Model -> DB).
- **API Tests**: Ensure REST endpoints return correct data and handle errors gracefully.
- **CLI Tests**: Verify the `fin` command-line interface behaves as expected.

## 2. Key Features to Validate

### A. Data Ingestion & Normalization (`backend/omnifin/ingest/normalize.py`)
The generic CSV parser relies on several heuristics that must be robustly tested.
- **Number Parsing**:
    - Standard floats (`123.45`)
    - Comma-separated thousands (`1,234.56`)
    - Currency symbols (`$100`, `€50`)
    - Accounting format parentheses for negatives (`(100.00)`)
- **Date Parsing**:
    - ISO format (`2026-01-01`)
    - US format (`01/01/2026`, `01/01/26`)
    - European format (`01.01.2026`)
- **Inference Logic**:
    - `infer_event_type`: Correctly identifying dividends, interest, fees, buys, sells, and transfers.
    - `infer_asset_symbol`: Correctly identifying tickers and fiat currencies (USD, EUR, etc.).
    - `infer_amount`/`infer_quantity`: Correctly picking the right column.
- **End-to-End Normalization**:
    - Processing a sample CSV and verifying the resulting `Report`, `Account`, `Asset`, and `Transfer` objects.

### B. Core Domain & Persistence (`backend/omnifin/models/`, `backend/omnifin/core/db/`)
- **Identity Map**: Ensure scalar coercion works (e.g., `Asset("USD") is Asset("USD")`).
- **Persistence**:
    - `Report.plan()` and `Report.save()` correctly stage and persist nested graphs.
    - Lazy hydration of related objects from the database.
    - Integrity constraints (e.g., missing required fields).

### C. API Layer (`backend/omnifin/api/server.py`)
- **Endpoints**:
    - GET /api/reports: List available reports.
    - GET /api/reports/{id}: Retrieve a specific report.
    - GET /api/assets: List tracked assets.
- **Error Handling**: Return 404 for missing resources, 422 for invalid input.

### D. CLI Interface (`backend/omnifin/cli/main.py`)
- **Commands**:
    - `fin normalize <file>`: Successfully parses a file and (optionally) saves to DB.
    - `fin serve`: Starts the FastAPI server.
- **Arguments**: Validation of required flags and options.

## 3. Test Execution Strategy
- **Framework**: `pytest`
- **Mocks**: Use `unittest.mock` or `pytest-mock` for external dependencies.
- **Database**: Use SQLite in-memory (`:memory:`) for fast, isolated tests.
- **CI/CD**: All tests should run on every commit.