# Omnifin Project Brief (Updated 2026-06-29)

## Current Architecture

Omnifin is a dual-interface monorepo:

1. Python backend package (`backend/omnifin`) with:
	 - Click CLI (`fin`)
	 - FastAPI server (`/api/*` endpoints)
	 - SQLite schema and session layer
	 - High-level domain model with identity map and staged relations
2. Vite/TypeScript frontend (`frontend`) consuming `/api`.

## Current Backend Maturity

- Foundation is solid for a seed repo:
	- strict SQLite schema with foreign keys and relation tables.
	- explicit domain-to-SQL mapping in `core/registry.py`.
	- `Report.plan()` and `Report.save()` share the same graph traversal logic.
	- normalization pipeline produces domain objects from unknown CSV shapes.
- Test suite quality improved and currently passing:
	- `30 passed` in `backend/tests`.
	- deterministic API/CLI/domain/normalize coverage with stronger assertions.

## High-Impact Gaps

1. Tax engines are scaffolds only (US/DE warnings, no lot matching).
2. API is list-focused; object retrieval/mutation routes are mostly absent.
3. Reconciliation engine exists as scaffold; no production-grade matching logic yet.
4. No migration lifecycle strategy beyond schema bootstrap.
5. No large-fixture performance guardrails for ingest.

## Agent-Friendly Working Notes

- Keep DB operations explicit and session-bound; avoid introducing hidden global state.
- Preserve identity-map semantics when adding model constructors or coercions.
- When adding new relations, update all of:
	- `core/registry.py` (`MODEL_SPECS`, `RELATION_SPECS`, SQL mappings)
	- schema DDL
	- domain model relation accessors/staging
	- tests for plan/save and relation flushes
- Prefer adding tests alongside each new command/endpoint branch.

## Execution Roadmap

### Phase A (Core Correctness)
1. Implement transaction rollback tests and migration smoke tests.
2. Add API object-by-id routes and 404-path tests.
3. Add relation-heavy integration fixtures (tags/comments/events/entities).

### Phase B (Tax/Reconciliation)
1. Implement lot model and matching primitives.
2. Build US wash-sale and holding-period classification.
3. Build German FIFO + Vorabpauschale + partial exemption rules.
4. Add deterministic fixture-based tax test vectors.

### Phase C (Productization)
1. Add import provenance and rollback workflows.
2. Add benchmark tests for large CSV ingest throughput.
3. Expand frontend views for reconciliation and auditability.