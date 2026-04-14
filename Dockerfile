FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required by OpenCV and MediaPipe.
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# Keep concurrency low to avoid memory spikes on Render free tier.
CMD ["gunicorn", "--workers=1", "--threads=1", "--timeout=180", "--bind=0.0.0.0:10000", "run:app"]
