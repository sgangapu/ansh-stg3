#!/bin/bash

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Audiobook App - Development Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check for --clean flag
if [ "$1" = "--clean" ]; then
    echo -e "${YELLOW}🧹 Cleaning up database and files...${NC}"
    
    # Clean MongoDB
    docker exec mongodb mongosh audiobooks_db --quiet --eval "db.books.deleteMany({}); db.segments.deleteMany({}); db.segment_timings.deleteMany({}); print('✅ Cleaned MongoDB');" 2>/dev/null
    
    # Clean output directory
    rm -rf backend/audio_reader_standalone/output/* 2>/dev/null
    
    # Clean uploads
    find backend/uploads -name "*.pdf" -delete 2>/dev/null
    
    echo -e "${GREEN}✓ Cleanup complete${NC}\n"
fi

# Check if MongoDB is running
echo -e "${YELLOW}Checking MongoDB...${NC}"
if pgrep -x "mongod" > /dev/null; then
    echo -e "${GREEN}✓ Local MongoDB is running${NC}\n"
else
    echo -e "${YELLOW}Local MongoDB not running. Checking Docker...${NC}"
    if docker info > /dev/null 2>&1; then
        if [ ! "$(docker ps -q -f name=mongodb)" ]; then
            if [ "$(docker ps -aq -f name=mongodb)" ]; then
                echo -e "Starting existing MongoDB container..."
                docker start mongodb
            else
                echo -e "Creating and starting MongoDB container..."
                docker run -d -p 27017:27017 --name mongodb mongo:latest
            fi
            echo -e "${GREEN}✓ MongoDB started via Docker${NC}\n"
        else
            echo -e "${GREEN}✓ MongoDB is running via Docker${NC}\n"
        fi
    else
        echo -e "${RED}MongoDB is not running locally and Docker is not available!${NC}"
        echo -e "${RED}Please start Docker Desktop or install MongoDB locally.${NC}\n"
        exit 1
    fi
fi

# Check if backend dependencies are installed
echo -e "${YELLOW}Checking backend dependencies...${NC}"
if [ ! -d "backend/node_modules" ]; then
    echo -e "Installing backend dependencies..."
    cd backend
    npm install
    cd ..
    echo -e "${GREEN}✓ Backend dependencies installed${NC}\n"
else
    echo -e "${GREEN}✓ Backend dependencies OK${NC}\n"
fi

# Check if frontend dependencies are installed
echo -e "${YELLOW}Checking frontend dependencies...${NC}"
if [ ! -d "frontend/node_modules" ]; then
    echo -e "Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}\n"
else
    echo -e "${GREEN}✓ Frontend dependencies OK${NC}\n"
fi

# Check environment files
echo -e "${YELLOW}Checking environment files...${NC}"
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}Creating backend/.env from template...${NC}"
    cp backend/.env.example backend/.env
    echo -e "${GREEN}✓ Created backend/.env${NC}"
fi

if [ ! -f "backend/audio_reader_standalone/.env" ]; then
    echo -e "${RED}⚠️  backend/audio_reader_standalone/.env not found!${NC}"
    echo -e "Please create it with your API keys:"
    echo -e "  cd backend/audio_reader_standalone"
    echo -e "  cp env_template.txt .env"
    echo -e "  # Then edit .env with your API keys\n"
else
    echo -e "${GREEN}✓ Python .env exists${NC}\n"
fi

# Start servers
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Starting Development Servers${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${GREEN}Backend will run on:  http://localhost:5000${NC}"
echo -e "${GREEN}Frontend will run on: http://localhost:3000${NC}\n"

echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}\n"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping servers...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Servers stopped${NC}"
    exit 0
}

trap cleanup INT TERM

# Start backend
cd backend
npm run dev &
BACKEND_PID=$!
cd ..

# Wait a bit for backend to start
sleep 3

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait for both processes
wait

