# Phase 0 Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bootstrap Phase 0 foundations for the ARD-defined trading system: repo structure, Python/Go toolchains, `.env` contract, CI skeleton, ADR baseline, and developer onboarding commands.

**Architecture:** Create a deterministic monorepo skeleton with service boundaries matching the ARD so future phases can be implemented incrementally without structural churn. Keep runtime dependencies minimal, enforce typed/linted code paths, and establish shared contracts first (`.env`, CI gates, directories). All steps follow TDD where meaningful for scripts and config validation.

**Tech Stack:** Python 3.13+, Go, FastAPI, Docker Compose, PostgreSQL + TimescaleDB, RabbitMQ, Redis, Celery, GitHub Actions.

---

### Task 1: Create Monorepo Service Skeleton

**Files:**
- Create: `services/.gitkeep`
- Create: `services/api/.gitkeep`
- Create: `services/market_ingestion/.gitkeep`
- Create: `services/integrity_service/.gitkeep`
- Create: `services/agent_orchestrator/.gitkeep`
- Create: `services/llm_gateway/.gitkeep`
- Create: `services/simulation_execution/.gitkeep`
- Create: `services/real_execution_go/.gitkeep`
- Create: `services/oms/.gitkeep`
- Create: `services/news_ingestion/.gitkeep`
- Create: `services/news_summarizer/.gitkeep`
- Create: `services/workers/.gitkeep`
- Test: `tests/test_repo_layout.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

REQUIRED_DIRS = [
    "services/api",
    "services/market_ingestion",
    "services/integrity_service",
    "services/agent_orchestrator",
    "services/llm_gateway",
    "services/simulation_execution",
    "services/real_execution_go",
    "services/oms",
    "services/news_ingestion",
    "services/news_summarizer",
    "services/workers",
]


def test_required_service_directories_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [d for d in REQUIRED_DIRS if not (root / d).exists()]
    assert not missing, f"Missing directories: {missing}"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repo_layout.py::test_required_service_directories_exist -v`
Expected: FAIL with missing directory list.

**Step 3: Write minimal implementation**

```bash
mkdir -p services/{api,market_ingestion,integrity_service,agent_orchestrator,llm_gateway,simulation_execution,real_execution_go,oms,news_ingestion,news_summarizer,workers}
touch services/.gitkeep
find services -mindepth 1 -maxdepth 1 -type d -exec touch {}/.gitkeep \;
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repo_layout.py::test_required_service_directories_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services tests/test_repo_layout.py
git commit -m "chore: bootstrap service directory skeleton"
```

### Task 2: Add Python 3.13 Tooling Baseline

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `tests/test_python_baseline.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_pyproject_declares_python_313() -> None:
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "requires-python = \">=3.13\"" in content


def test_python_version_file_exists() -> None:
    assert Path(".python-version").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_python_baseline.py -v`
Expected: FAIL because files do not exist.

**Step 3: Write minimal implementation**

```toml
[project]
name = "open-trader"
version = "0.1.0"
description = "LLM-based multi-exchange crypto trading platform"
requires-python = ">=3.13"
dependencies = []

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py313"
```

`.python-version`
```txt
3.13
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_python_baseline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml .python-version tests/test_python_baseline.py
git commit -m "chore: add python 3.13 project baseline"
```

### Task 3: Add Go Module for Real Execution Service

**Files:**
- Create: `services/real_execution_go/go.mod`
- Create: `services/real_execution_go/main.go`
- Create: `tests/test_go_baseline.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_go_module_exists() -> None:
    assert Path("services/real_execution_go/go.mod").exists()


def test_go_main_exists() -> None:
    assert Path("services/real_execution_go/main.go").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_go_baseline.py -v`
Expected: FAIL because files do not exist.

**Step 3: Write minimal implementation**

`go.mod`
```go
module open-trader/real_execution_go

go 1.22
```

`main.go`
```go
package main

import "fmt"

func main() {
	fmt.Println("real_execution_go bootstrap")
}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_go_baseline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/real_execution_go/go.mod services/real_execution_go/main.go tests/test_go_baseline.py
git commit -m "chore: bootstrap go module for real execution service"
```

### Task 4: Add `.env` Contract and Validator Script

**Files:**
- Create: `.env.example`
- Create: `scripts/validate_env.py`
- Create: `tests/test_env_contract.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_env_example_exists() -> None:
    assert Path(".env.example").exists()


def test_env_validator_exists() -> None:
    assert Path("scripts/validate_env.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_env_contract.py -v`
Expected: FAIL because files do not exist.

**Step 3: Write minimal implementation**

`.env.example`
```dotenv
APP_ENV=development
APP_NAME=open-trader
LOG_LEVEL=INFO

API_HOST=0.0.0.0
API_PORT=8000

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=open_trader
POSTGRES_USER=open_trader
POSTGRES_PASSWORD=change_me

REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

OPENAI_API_KEY=
ANTHROPIC_API_KEY=

ENCRYPTION_KEY_BASE64=
JWT_SECRET_KEY=
```

`scripts/validate_env.py`
```python
from __future__ import annotations

import os
import sys

REQUIRED_KEYS = [
    "APP_ENV",
    "API_HOST",
    "API_PORT",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_URL",
    "ENCRYPTION_KEY_BASE64",
    "JWT_SECRET_KEY",
]


def main() -> int:
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        print(f"Missing required env keys: {', '.join(missing)}")
        return 1
    print("Environment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_env_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add .env.example scripts/validate_env.py tests/test_env_contract.py
git commit -m "chore: add env contract and validation script"
```

### Task 5: Add CI Skeleton

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_ci_skeleton.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_ci_workflow_exists() -> None:
    assert Path(".github/workflows/ci.yml").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ci_skeleton.py -v`
Expected: FAIL because workflow file does not exist.

**Step 3: Write minimal implementation**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  python-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Run tests
        run: uv run pytest
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ci_skeleton.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_ci_skeleton.py
git commit -m "chore: add initial ci workflow"
```

### Task 6: Add ADR Baseline

**Files:**
- Create: `docs/adr/0001-architecture-baseline.md`
- Create: `tests/test_adr_baseline.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_adr_exists() -> None:
    assert Path("docs/adr/0001-architecture-baseline.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adr_baseline.py -v`
Expected: FAIL because ADR file does not exist.

**Step 3: Write minimal implementation**

```markdown
# ADR-0001: Architecture Baseline

## Status
Accepted

## Context
This repository follows `docs/ARD_Consolidated.md` as architecture source of truth.

## Decision
Adopt Python 3.13+, Go for performance-critical execution services, RabbitMQ, Redis, PostgreSQL + TimescaleDB, Docker Compose, and `.env`-based configuration.

## Consequences
All future implementation tasks must conform to this stack unless superseded by a new ADR.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adr_baseline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/adr/0001-architecture-baseline.md tests/test_adr_baseline.py
git commit -m "docs: add architecture baseline adr"
```

### Task 7: Add Developer Onboarding Commands

**Files:**
- Create: `Makefile`
- Modify: `README.md`
- Create: `tests/test_onboarding_docs.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_makefile_exists() -> None:
    assert Path("Makefile").exists()


def test_readme_has_bootstrap_section() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "## Development Bootstrap" in readme
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_docs.py -v`
Expected: FAIL because `Makefile` and section do not exist.

**Step 3: Write minimal implementation**

`Makefile`
```make
.PHONY: test lint fmt env-validate

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

env-validate:
	uv run python scripts/validate_env.py
```

`README.md` add section:
```markdown
## Development Bootstrap

1. Install `uv`
2. Create `.env` from `.env.example`
3. Run `make env-validate`
4. Run `make test`
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_onboarding_docs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add Makefile README.md tests/test_onboarding_docs.py
git commit -m "docs: add development bootstrap guide and make targets"
```

