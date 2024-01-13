FROM python:3.9

WORKDIR /usr/local/bin

# Install Chromium and ChromeDriver
RUN apt-get update \
    && apt-get install -y chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set display port to avoid crash
ENV DISPLAY=:99

# Install Python dependencies
RUN pip install requests selenium python-dotenv

ADD scraper.py .

CMD ["python", "scraper.py"]

