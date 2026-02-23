FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gcc \
    g++ \
    util-linux \
    tzdata \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.30 /uv /uvx /usr/local/bin/

ARG SUPERCRONIC_VERSION=v0.2.33
RUN DEB_ARCH="$(dpkg --print-architecture)" \
    && case "${DEB_ARCH}" in \
    "amd64") SUPERCRONIC_ARCH="amd64" ;; \
    "arm64") SUPERCRONIC_ARCH="arm64" ;; \
    *) echo "Unsupported architecture: ${DEB_ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSLo /usr/local/bin/supercronic \
    "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${SUPERCRONIC_ARCH}" \
    && chmod +x /usr/local/bin/supercronic

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY crontab ./crontab

CMD ["uv", "run", "python", "src/main.py"]
