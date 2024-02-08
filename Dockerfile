# Use Python slim image for smaller size
FROM python:3.11-slim

WORKDIR /app

# Install Chromium and ChromeDriver in one layer, clean up in the same layer
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set display port to avoid crash
ENV DISPLAY=:99

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py .

CMD ["python", "scraper.py"]
