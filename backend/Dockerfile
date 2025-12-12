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

# Copy package files first for better caching
COPY package*.json ./

# Install Node.js dependencies
RUN npm ci --only=production

# Copy Python requirements
COPY ../audio_reader_standalone/requirements.txt ./python_deps/
COPY ../audio_reader_standalone/requirements_mongo.txt ./python_deps/

# Create Python virtual environment and install dependencies
RUN python3 -m venv ../audio_reader_standalone/venv && \
    ../audio_reader_standalone/venv/bin/pip install --upgrade pip && \
    ../audio_reader_standalone/venv/bin/pip install -r ./python_deps/requirements.txt && \
    ../audio_reader_standalone/venv/bin/pip install -r ./python_deps/requirements_mongo.txt

# Copy application code
COPY . .

# Create output directory
RUN mkdir -p ../audio_reader_standalone/output

# Expose port
EXPOSE 5000

# Start the server
CMD ["npm", "start"]
