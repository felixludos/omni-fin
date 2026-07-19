# Omnifin Backend Test Plan (Updated 2026-07-19)

## 1. Current Test Suite Status
- Command: `uv run pytest tests -q --ignore=tests/test_seeding.py`
- Result: `83 passed`
- Seeding tests (`test_seeding.py`): 43 tests — **all fail** because `cloud_data/seed_data/*.yaml` files are gitignored and not present on this checkout. These tests need either: (a) seed YAML files committed to the repo, or (b) `@pytest.mark.skipif` guards for missing files.
- Scope covered:
  - API endpoint behavior and parameter validation.
  - CLI command behavior (`init-db`, `normalize`, `tax`, `serve`).
  - Domain identity map behavior, plan/save integrity, relation staging.
  - Normalization parsing/inference and CSV output writing.

## 2. What Is Covered Well

### A. API Layer (`omnifin/api/server.py`)
- Endpoints covered: `/api/health`, `/api/assets`, `/api/accounts`, `/api/statements`, `/api/transfers`, `/api/reports`.
- Query validation covered:
  - `limit` lower bound and upper bound.
  - `offset` lower bound.
- Pagination behavior covered with deterministic seeded data and strict assertions.

### B. CLI Layer (`omnifin/cli/main.py`)
- Command success paths covered for:
  - `init-db`
  - `normalize` (plain output, JSON plan output, CSV output, save flow)
  - `tax` (US/DE JSON payload shape)
  - `serve` (uvicorn invocation arguments and DB env propagation via mocking)

### C. Domain Layer (`omnifin/models/domain.py`)
- Identity map singleton behavior for natural keys and UUID keys.
- `Report.plan()` and `Report.save()` on nested object graphs.
- Lazy hydration from persisted rows.
- Required field enforcement in plan and save paths.
- Staged tag/comment relation plan counts and persistence.

### D. Ingest Normalization (`omnifin/ingest/normalize.py`)
- `parse_number`, `parse_date`, key/value discovery helpers.
- Event/asset inference heuristics.
- Fallback logic: amount -> quantity -> minimum safe transfer amount.
- Optional filtering for non-taxable rows.
- CSV writing of normalized rows.

## 3. Known Gaps / Risk Areas (Prioritized)

### High Priority
- No property-based tests for parser robustness under messy real-world CSV inputs.
- No tests for concurrent write/read behavior or transaction rollback semantics under partial failures.
- No API tests for future entity-by-id routes (not implemented yet).

### Medium Priority
- No contract tests for DB schema migrations over multiple versions.
- Tax modules are scaffold-only and have no behavioral correctness tests beyond payload shape.
- No performance regression tests for large CSV files.

### Low Priority
- No snapshot/golden-file tests for normalized output stability.
- No mutation testing to measure assertion quality.

## 4. Next Testing Iterations

1. Add fuzz/property tests for normalization helpers and row-level coercion.
2. Add transaction failure simulation tests for `Report.save()` rollback behavior.
3. Add benchmark-style tests for normalization throughput on large CSV fixtures.
4. Expand tax tests once lot matching and jurisdiction logic are implemented.
5. Add CI quality gates for test runtime, linting, and coverage threshold.

## 5. Testing Conventions For New Contributors/Agents
- Keep tests deterministic: use per-test DB files and clear global identity maps.
- Avoid broad exception assertions; assert exact exception type and key message content.
- Prefer behavior assertions (specific payload shape/values) over generic status-only checks.
- For CLI server commands, mock `uvicorn.run` to avoid blocking test execution.