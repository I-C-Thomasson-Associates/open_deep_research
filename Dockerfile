FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . .

RUN uv pip install --system .

EXPOSE 2024

CMD ["python", "-m", "langgraph_api.cli", "--host", "0.0.0.0", "--port", "2024", "--no-reload", "--config", "langgraph.json", "--runtime-edition", "inmem", "--n-jobs-per-worker", "1"]
