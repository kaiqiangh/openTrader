.PHONY: test lint fmt env-validate migrate-up migrate-down migrate-revision

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

env-validate:
	uv run python /Users/kai/Desktop/openTrader/scripts/validate_env.py

migrate-up:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

migrate-revision:
	@if [ -z "$(MSG)" ]; then echo "Usage: make migrate-revision MSG='add_users_table'"; exit 1; fi
	uv run alembic revision -m "$(MSG)"
