FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libffi-dev \
    libcairo2 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libjpeg-dev \
    libopenjp2-7-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

ENV PYTHONPATH="/app:$PYTHONPATH"

ENV PORT=8000

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]