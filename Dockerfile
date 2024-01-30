FROM python:3.11

WORKDIR /usr/local/bin

# Install Chromium and ChromeDriver
RUN apt-get update \
    && apt-get install -y chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set display port to avoid crash
ENV DISPLAY=:99

# Install Python dependencies
ADD requirements.txt .
RUN pip install -r requirements.txt

ADD scraper.py .

CMD ["python", "scraper.py"]

