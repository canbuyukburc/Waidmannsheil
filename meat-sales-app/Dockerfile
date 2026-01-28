FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create templates and static directories
RUN mkdir -p templates static

# Make startup script executable
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 5000

# Run the application with initialization
CMD ["/bin/bash", "/app/start.sh"]