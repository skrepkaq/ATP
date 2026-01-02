FROM python:3.12-slim

RUN apt update && apt install -y --no-install-recommends \
    ffmpeg \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 atp \
    && useradd -u 1000 -g 1000 -m atp

WORKDIR /app

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --compile-bytecode

ENV PATH="/app/.venv/bin:$PATH" \
    DOCKER=1

COPY --chown=atp:atp example.settings.conf example.settings-docker.conf ./
COPY --chown=atp:atp atp/ atp/
COPY --chown=atp:atp entrypoint.py .

USER atp

ENTRYPOINT ["python", "-u", "entrypoint.py"]
