# Omnifin Repository Assessment (2026-06-29)

## Executive Summary

The repository is a strong seed architecture with clean layering and explicit domain modeling, but still in early-product stage for business-critical finance workflows. Core foundations are credible (schema, identity map, CLI/API scaffolding, normalization heuristics), while major functional depth is still missing in tax logic, reconciliation rigor, and API completeness.

## What Is High Quality Today

1. Domain model design is intentional:
   - Session-scoped identity map reduces duplicate object hazards.
   - `Report.plan()` and `Report.save()` share traversal logic, lowering drift risk between dry run and write path.
   - Relation staging for tags/comments/events/entities supports deferred persistence.
2. SQLite schema quality is good for a seed:
   - STRICT tables and foreign keys enabled.
   - Meaningful constraints (e.g., transfer amount > 0, UUID byte length checks).
   - Useful indexes for common transfer/statements reads.
3. Developer ergonomics are solid:
   - Installable backend package with CLI entry point.
   - FastAPI and frontend wiring enable local full-stack iteration.
   - Tests now exercise core API/CLI/domain/normalization paths deterministically.

## Main Risks / Technical Debt

### 1) Functional Coverage Risk
- Tax modules (`tax/us.py`, `tax/de.py`) are explicit scaffolds.
- Reconciliation logic is not yet a mature engine.
- API supports list views only; no robust read-by-id/update workflows.

Impact: High. This limits production usefulness for compliance and audit workflows.

### 2) Documentation Drift
- `docs/schemas.md` does not fully match the current executable schema and naming patterns.

Impact: Medium. New contributors and agents can implement against stale assumptions.

### 3) Data Lifecycle / Migration Maturity
- Migrations are effectively bootstrap-level (`schema_migrations` seeded at version 1).
- No explicit tested strategy for forward migrations and rollback behavior.

Impact: Medium to high as schema evolves.

### 4) Performance Guardrails Missing
- No benchmark or stress tests for large CSV ingest workflows.

Impact: Medium, but high once real account exports scale.

## Testing Quality Assessment

## Prior State
- Tests passed but had quality weaknesses:
  - Shared API DB fixture across session risked hidden test coupling.
  - Some assertions were too broad (status-only, generic exception checks).
  - CLI `serve` behavior was untested.

## Current State
- Test quality improved with deterministic fixtures and stronger assertions.
- Backend suite now validates:
  - API pagination and query validation boundaries.
  - CLI JSON plan/tax payload semantics.
  - CLI serve invocation contract via mocking.
  - Domain invalid-plan and save failure behavior.
  - Normalization fallback/filter/write edge paths.

Current command result: `python -m pytest -q` -> `30 passed`.

## Missing Next (Testing)

1. Property-based tests for parser resilience.
2. Transaction rollback fault-injection tests.
3. Migration compatibility tests across schema versions.
4. Large fixture throughput tests.
5. Tax correctness vectors once business logic is implemented.

## Recommended Next Steps (Priority Order)

1. Implement lot model + US/DE tax correctness core, then add fixture-based tax tests.
2. Add object-by-id API routes with strict error contracts and tests.
3. Introduce migration framework/process (even lightweight) and migration smoke tests.
4. Reconcile and update `docs/schemas.md` against `omnifin/db/schema.sql`.
5. Add ingest performance benchmarks for representative broker exports.

## Guidance For Future AI Agents

- Treat `omnifin/db/schema.sql` and `omnifin/core/registry.py` as the source of truth pair; changes should stay synchronized.
- Keep tests deterministic by using per-test DB files and clearing global identity maps.
- Prefer exact behavior assertions over status-only checks.
- Add tests in the same PR as any new endpoint/CLI/domain relation behavior.
