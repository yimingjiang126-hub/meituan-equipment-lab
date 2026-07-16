FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY standalone/proxy_server.py .
COPY generators/ ./generators/
COPY utils/ ./utils/

# Create directories for generated images
RUN mkdir -p /app/web/static/images/generated

# Expose port
EXPOSE 8081

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Run the proxy server
CMD ["python", "proxy_server.py"]
