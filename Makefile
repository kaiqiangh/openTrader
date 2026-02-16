.PHONY: test lint fmt env-validate migrate-up migrate-down migrate-revision smoke smoke-full runtime-gate runtime-gate-full mock-workflow

test:
	uv run pytest -v

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

env-validate:
	uv run python scripts/validate_env.py

migrate-up:
	@if uv run alembic upgrade head; then \
		true; \
	else \
		echo "Local migration failed; retrying via Docker Compose internal network..."; \
		docker compose up -d postgres_timescaledb; \
		docker compose run --rm --no-deps \
			-e POSTGRES_HOST=postgres_timescaledb \
			-e POSTGRES_PORT=5432 \
			notification_worker uv run --frozen alembic upgrade head || { \
				echo "Docker fallback migration failed. Check POSTGRES_USER/POSTGRES_PASSWORD alignment with existing postgres volume."; \
				echo "If needed for local reset only: docker compose down -v postgres_timescaledb"; \
				exit 1; \
			}; \
	fi

migrate-down:
	uv run alembic downgrade -1

migrate-revision:
	@if [ -z "$(MSG)" ]; then echo "Usage: make migrate-revision MSG='add_users_table'"; exit 1; fi
	uv run alembic revision -m "$(MSG)"

smoke:
	uv run python scripts/smoke_test.py

smoke-full:
	uv run python scripts/smoke_test.py --with-full-profile

runtime-gate:
	uv run python scripts/runtime_integration_gate.py

runtime-gate-full:
	uv run python scripts/runtime_integration_gate.py --with-full-profile

mock-workflow:
	uv run python scripts/mock_realtime_workflow_test.py
