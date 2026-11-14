FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

COPY pyproject.toml /app/pyproject.toml
COPY packages /app/packages
COPY apps/api /app/apps/api
COPY apps/workers /app/apps/workers
COPY scripts /app/scripts

ENV PYTHONPATH=/app:/app/apps/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
