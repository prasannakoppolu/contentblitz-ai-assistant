# ---- Stage 1: build the React UI ----
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python API serving the built UI ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    CONTENTBLITZ_OUTPUT_DIR=/data/outputs \
    CONTENTBLITZ_MEMORY=sqlite CONTENTBLITZ_MEMORY_PATH=/data/contentblitz_memory.sqlite
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/
COPY config/ config/
COPY --from=ui /ui/dist frontend/dist
RUN useradd -m appuser && mkdir -p /data/outputs && chown -R appuser /data /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
