# ---- Stage 1: build the frontend ----
FROM node:26-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime serving API + built frontend ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir ".[postgres]"

COPY --from=frontend /build/dist ./static

RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

ENV TIDELINE_STATIC_DIR=/app/static \
    TIDELINE_DATABASE_URL=sqlite:////data/tideline.db \
    TIDELINE_CORS_ORIGINS=""

EXPOSE 8000
# $PORT is provided by Render; default to 8000 for local runs
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
