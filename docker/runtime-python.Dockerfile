FROM ghcr.io/astral-sh/uv:python3.13-bookworm

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --all-groups

COPY . /app

RUN useradd -r -s /usr/sbin/nologin -d /app appuser && chown -R appuser:appuser /app /tmp/uv-cache
USER appuser
