FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY crypto_signal_agent ./crypto_signal_agent
COPY run_monitor.sh ./run_monitor.sh

RUN pip install --upgrade pip \
    && pip install -e ".[openai]" \
    && mkdir -p /app/data \
    && chmod +x /app/run_monitor.sh

CMD ["python", "-m", "crypto_signal_agent.cli", "monitor-new", "--loop", "--send-alert"]
