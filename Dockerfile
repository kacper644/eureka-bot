FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libx11-6 libxkbcommon0 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxi6 libxtst6 libdrm2 libgbm1 libasound2 fonts-liberation wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080"]
