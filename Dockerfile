# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.9.9 AS uv
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

WORKDIR /opt/yacht_co2

# ARM64 does not have wheels for every locked scientific dependency, so keep
# the compiler in this build stage and out of the runtime image.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Resolve the locked runtime dependencies before copying the source so that
# ordinary code changes retain Docker's dependency layer cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --python /usr/local/bin/python3 --locked --no-dev --extra gui --no-install-project

COPY . .
RUN uv sync \
    --python /usr/local/bin/python3 \
    --locked \
    --no-dev \
    --extra gui \
    --no-editable \
    --compile-bytecode

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/yacht_co2/.venv/bin:$PATH" \
    YACHT_CO2_CONFIG_DIR=/home/renku/.config/yacht_co2

COPY --from=builder /opt/yacht_co2 /opt/yacht_co2

RUN useradd --create-home --uid 1000 --shell /bin/bash renku \
    && mkdir -p /home/renku/work /home/renku/.config/yacht_co2 \
    && chown -R renku:renku /home/renku

USER renku
WORKDIR /home/renku/work

EXPOSE 8080

# NiceGUI automatically uses RENKU_BASE_URL_PATH when Renku injects it.
CMD ["yacht-co2", "gui", "--data-root", "/home/renku/work", "--host", "0.0.0.0", "--port", "8080", "--no-show"]
