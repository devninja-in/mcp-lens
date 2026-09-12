FROM python:3.11-slim AS backend

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

COPY src/app/ src/app/

FROM node:20-slim AS frontend

WORKDIR /app/src/frontend

COPY src/frontend/package*.json ./
RUN npm ci --silent

COPY src/frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

COPY src/app/ src/app/
COPY --from=frontend /app/src/frontend/dist static/

EXPOSE 5002

CMD ["uv", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "5002"]
