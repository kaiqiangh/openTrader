.PHONY: test lint fmt env-validate

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

env-validate:
	uv run python /Users/kai/Desktop/openTrader/scripts/validate_env.py
