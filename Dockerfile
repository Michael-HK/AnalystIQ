

FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for PDF generation
#RUN apt-get update && apt-get install -y --no-install-recommends \
#    wkhtmltopdf \
#    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl fontconfig \
      libfreetype6 libjpeg-turbo8 libpng16-16 libx11-6 libxext6 libxrender1 \
      python3 python3-pip python3-venv \
      wkhtmltopdf && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker's layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/vendor && \
    curl -fsSL -o /app/vendor/chart.min.js \
      https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js 
      #&& \
    # Optional: verify size/hash for integrity (example SHA256 shown as placeholder)
#    echo "EXPECTED_SHA256  /app/vendor/chart.min.js" > /app/vendor/SHA256SUMS && \
#    # TODO: replace EXPECTED_SHA256 with the real hash if you want strict verification
#    true

# Copy the rest of the application code
COPY . .

ENV CHARTJS_SRC=file:///app/vendor/chart.min.js

# Command to run the application
# This runs the main.py script as a module
ENTRYPOINT ["python", "-m", "main"]
CMD ["AAPL"]
