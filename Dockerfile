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
    YACHT_CO2_CONFIG_DIR=/home/renku/.config/yacht_co2 \
    YACHT_CO2_USER_CONFIG_DIR=/home/renku/work/.config/yacht_co2 \
    YACHT_CO2_DATA_ROOT=/home/renku/work \
    YACHT_CO2_HOST=0.0.0.0 \
    YACHT_CO2_PORT=8080

COPY --from=builder /opt/yacht_co2 /opt/yacht_co2

RUN useradd --create-home --uid 1000 --shell /bin/bash renku \
    && mkdir -p /home/renku/work /home/renku/.config/yacht_co2 \
    && chown -R renku:renku /home/renku

USER renku
WORKDIR /home/renku/work

EXPOSE 8080

# Python's standard library keeps this check dependency-free in the slim image.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=2)"

# NiceGUI automatically uses RENKU_BASE_URL_PATH when Renku injects it.
CMD ["python", "-m", "yacht_co2.container"]
