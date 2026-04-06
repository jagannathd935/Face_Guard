FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by OpenCV and building some pip packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for faster Docker caching
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port (Render automatically uses PORT env var, but good practice to expose 10000)
EXPOSE 10000

# Set gunicorn to bind to the Render port and use 4 workers
CMD ["gunicorn", "--workers=4", "--bind=0.0.0.0:10000", "run:app"]
