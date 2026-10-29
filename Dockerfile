FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Install system fonts for graphic card rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies globally
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose default port
EXPOSE 7860

CMD ["python", "app.py"]
