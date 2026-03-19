# Playwright önceden kurulu Python imajı (Chromium uyumluluğu için)
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_HEADLESS=true

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir pip setuptools wheel \
    && pip install --no-cache-dir .

CMD ["python", "-m", "app.main"]
