.PHONY: install-backend test-backend init-db dev

install-backend:
	python -m pip install -e backend

test-backend:
	cd backend && python -m pytest

init-db:
	cd backend && fin init-db --db ../data/omnifin.db

dev:
	npm run dev
