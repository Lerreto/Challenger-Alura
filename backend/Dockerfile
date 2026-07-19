FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app --home /home/app app

COPY --from=uv /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev

COPY --chown=app:app documents /app/seed-documents
RUN mkdir -p /app/storage/documents /app/storage/data /home/app/.cache/huggingface \
    && chown -R app:app /app/storage /home/app

USER app

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=4s --start-period=120s --retries=5 \
  CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3)" || exit 1

CMD [".venv/bin/uvicorn", "nebula_rag.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
