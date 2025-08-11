FROM mcr.microsoft.com/playwright/python:v1.47.2-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080"]
