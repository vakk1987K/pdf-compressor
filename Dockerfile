FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Ghostscript for PDF compression
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY app.py .

# Temporary working directory
RUN mkdir -p /tmp/pdf_compressor

EXPOSE 10000

# Start Flask with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--timeout", "240", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
