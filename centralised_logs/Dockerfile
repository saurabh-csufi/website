# Dockerfile for Centralized Log Collector Service
# Optimized for Google Cloud Run deployment

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cloud Run will set PORT environment variable
ENV PORT=8080

WORKDIR /app

# Install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY log_collector.py .
COPY config.json .

# Expose the port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Use gunicorn for production
# Cloud Run requires the container to listen on $PORT
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 log_collector:app
