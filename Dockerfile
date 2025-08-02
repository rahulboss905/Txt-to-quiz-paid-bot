# Use official Python base image
FROM python:3.9-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT=10000

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create health check script
RUN echo '#!/bin/bash\ncurl -f http://localhost:$PORT/health || exit 1' > /healthcheck.sh && \
    chmod +x /healthcheck.sh

# Set health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD /healthcheck.sh

# Set entrypoint command
CMD ["python", "main.py"]
