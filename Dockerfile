# prod — образ бота; dev — той самий + ruff і mypy для test/lint.
FROM python:3.12-slim AS prod
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_NO_CACHE=1
WORKDIR /app
COPY pyproject.toml ./
COPY deye ./deye
RUN uv pip install --system .
ENTRYPOINT ["python3", "-m", "deye"]

FROM prod AS dev
RUN uv pip install --system ".[dev]"
