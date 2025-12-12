# Node.js + Python backend for audiobook generation
FROM node:18-slim

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copy Python requirements first for better caching
COPY audio_reader_standalone/requirements.txt ./audio_reader_standalone/
COPY audio_reader_standalone/requirements_mongo.txt ./audio_reader_standalone/

# Create Python virtual environment and install dependencies
RUN python3 -m venv /app/audio_reader_standalone/venv && \
    /app/audio_reader_standalone/venv/bin/pip install --upgrade pip && \
    /app/audio_reader_standalone/venv/bin/pip install -r /app/audio_reader_standalone/requirements.txt && \
    /app/audio_reader_standalone/venv/bin/pip install -r /app/audio_reader_standalone/requirements_mongo.txt

# Copy backend package files
COPY backend/package*.json ./backend/

# Install Node.js dependencies
WORKDIR /app/backend
RUN npm ci --only=production

# Copy all application code
WORKDIR /app
COPY backend/ ./backend/
COPY audio_reader_standalone/ ./audio_reader_standalone/

# Create output directory for generated audiobooks
RUN mkdir -p /app/audio_reader_standalone/output

WORKDIR /app/backend

# Expose port (Railway sets PORT env var)
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:' + (process.env.PORT || 5000) + '/api/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

# Start the server
CMD ["npm", "start"]
