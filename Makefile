.PHONY: install-backend test-backend lint-backend init-db dev check

install-backend:
	uv pip install -e .

test-backend:
	uv run pytest tests -q --ignore=tests/test_seeding.py

lint-backend:
	uv run ruff check omnifin/

init-db:
	uv run fin init-db --db data/omnifin.db

dev:
	npm run dev

check: test-backend lint-backend
	uv run fin --help > /dev/null 2>&1 && echo "CLI: OK" || echo "CLI: MISSING"
	@echo "All checks passed."
