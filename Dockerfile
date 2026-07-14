# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install .

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEB_CONCURRENCY=1

RUN groupadd --gid 10001 opportunityos && \
    useradd --uid 10001 --gid opportunityos --create-home opportunityos

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/container-entrypoint.sh ./scripts/container-entrypoint.sh

RUN chmod 0555 ./scripts/container-entrypoint.sh && \
    chown -R opportunityos:opportunityos /app

USER opportunityos

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=4 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

ENTRYPOINT ["/app/scripts/container-entrypoint.sh"]
