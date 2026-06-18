# API image: FastAPI + LangGraph agent + local embeddings (CPU torch).
# Build context: knowledge_engine/  (the package dir).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

# Embeddings run via OpenRouter, so no torch / local ML wheels are needed.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the package as /app/knowledge_engine so `import knowledge_engine` works.
COPY . /app/knowledge_engine

EXPOSE 8000
CMD ["uvicorn", "knowledge_engine.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
