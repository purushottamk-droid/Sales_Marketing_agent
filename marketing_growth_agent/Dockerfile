FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything into a subfolder named marketing_growth_agent, so that
# `from marketing_growth_agent.scripts...` imports resolve correctly.
COPY . ./marketing_growth_agent

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV PYTHONPATH=/app

CMD exec uvicorn marketing_growth_agent.api:api --host 0.0.0.0 --port ${PORT}