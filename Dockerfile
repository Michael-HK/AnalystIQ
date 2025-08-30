

FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      fontconfig \
      # Dependencies for Playwright Chromium
      libnss3 \
      libatk-bridge2.0-0 \
      libdrm2 \
      libxkbcommon0 \
      libgtk-3-0 \
      libgbm1 \
      libasound2 && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker's layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install chromium

# Download Chart.js for offline use
RUN mkdir -p /app/vendor && \
    curl -fsSL -o /app/vendor/chart.min.js \
      https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js

# Copy the rest of the application code
COPY . .

ENV CHARTJS_SRC=file:///app/vendor/chart.min.js

# Command to run the application
# This runs the main.py script as a module
ENTRYPOINT ["python", "-m", "main"]
CMD ["AAPL"]
