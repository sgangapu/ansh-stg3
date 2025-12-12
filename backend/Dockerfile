# Node.js + Python backend for audiobook generation
FROM node:18-slim

# Install Python and required system packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copy Python requirements first (for better Docker caching)
COPY audio_reader_standalone/requirements.txt ./audio_reader_standalone/
COPY audio_reader_standalone/requirements_mongo.txt ./audio_reader_standalone/

# Create Python virtual environment and install dependencies
RUN python3 -m venv /app/audio_reader_standalone/venv && \
    /app/audio_reader_standalone/venv/bin/pip install --upgrade pip && \
    /app/audio_reader_standalone/venv/bin/pip install -r /app/audio_reader_standalone/requirements.txt && \
    /app/audio_reader_standalone/venv/bin/pip install -r /app/audio_reader_standalone/requirements_mongo.txt

# Copy Node.js package files
COPY package*.json ./

# Install Node.js dependencies
RUN npm ci --only=production

# Copy all application code
COPY . .

# Create output directory for generated audiobooks
RUN mkdir -p /app/audio_reader_standalone/output

# Expose port (Railway sets PORT env var automatically)
EXPOSE 5000

# Start the server
CMD ["npm", "start"]
