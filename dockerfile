FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim as base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project --frozen

COPY . .
RUN uv sync --frozen

FROM base AS runner

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/ranking_service /app/ranking_service

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT []
CMD []