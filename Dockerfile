FROM python:3.12-slim

RUN apt update && apt install -y --no-install-recommends \
    ffmpeg \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app
RUN chown -R 1000:1000 /app

RUN pip install --no-cache-dir uv
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

RUN playwright install --with-deps chromium-headless-shell \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

COPY atp/ atp/
COPY entrypoint.py .

ENTRYPOINT ["python", "-u", "entrypoint.py"]
