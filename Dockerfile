# The app image. Built on the Droplet by `docker compose up --build` (see docs/deploy.md).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cached until uv.lock changes), then the app itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

# Run as a normal user. data/ is the DB volume; .nicegui/ is NiceGUI's scratch folder.
RUN useradd --uid 1000 --no-create-home app \
    && mkdir -p data .nicegui && chown app:app data .nicegui
USER app

EXPOSE 8080
CMD ["python", "-m", "gift_exchange.main"]
