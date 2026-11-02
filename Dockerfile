# One image: the built React app and the FastAPI backend. Build from the repo root:
#   docker build -t invoice-review .
# Run (secrets come from the environment, never from the image):
#   docker run --rm -p 8000:8000 --env-file backend/.env invoice-review

# ---- 1. Build the SPA. VITE_API_BASE_URL=/ means "same origin": the API is served by this image.
FROM node:22-slim AS frontend
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV VITE_API_BASE_URL=/
RUN pnpm build

# ---- 2. Install the backend dependencies exactly as in uv.lock (no dev tools).
FROM python:3.12-slim-bookworm AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev

# ---- 3. Runtime image.
FROM python:3.12-slim-bookworm
# opencv (pulled in by RapidOCR) needs these two system libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
COPY --from=backend-deps /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY backend/app ./app
COPY --from=frontend /build/dist ./static
# SQLite, uploads and reading caches live here (lost when the container is replaced).
RUN mkdir data && chown app:app data
USER app

ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/health', timeout=4)"
# Hosts such as Render and Railway set $PORT. --proxy-headers lets the app see HTTPS behind
# the host's proxy, so the login cookie gets the Secure flag.
CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" \
    --proxy-headers --forwarded-allow-ips "*"
