.PHONY: install test lint run db-up db-down migrate
install:
	uv sync --extra dev
test:
	uv run pytest
lint:
	uv run ruff check .
	uv run ruff format --check .
run:
	uv run uvicorn opportunityos.api.main:app --reload
db-up:
	docker compose up -d postgres
db-down:
	docker compose down
migrate:
	uv run alembic upgrade head
