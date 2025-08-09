# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps if needed later (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app ./app

# Make sure the sqlite folder exists and is writable
RUN mkdir -p /app/data && chmod -R 777 /app/data

ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL="sqlite:////app/data/app.db"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
