# Цілі: prod (типова, бот) і dev (+ ruff, mypy — для test/lint). uv лишається тільки на етапах збирання.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app

# --- залежності в /opt/venv (шар кешується, поки не змінився pyproject.toml) ---
FROM base AS deps
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
ENV UV_NO_CACHE=1
RUN uv venv $VIRTUAL_ENV
COPY pyproject.toml ./
RUN uv pip install -r pyproject.toml

FROM deps AS dev-deps
RUN uv pip install -r pyproject.toml --extra dev

# --- образи ---
FROM base AS dev
COPY --from=dev-deps /opt/venv /opt/venv

FROM base AS prod
COPY --from=deps /opt/venv /opt/venv
COPY deye ./deye
ENTRYPOINT ["python", "-m", "deye"]
