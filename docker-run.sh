#!/bin/bash

# Docker build and run script for Cropwatch

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🐳 Building Cropwatch Docker image...${NC}"

# Build the Docker image
docker build -t cropwatch:latest .

echo -e "${GREEN}✅ Build completed successfully!${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  No .env file found. Creating from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}📝 Please edit .env file with your actual tokens before running.${NC}"
fi

echo -e "${GREEN}🚀 Starting Cropwatch application...${NC}"

# Run with docker-compose
docker-compose up -d

echo -e "${GREEN}✅ Application is starting!${NC}"
echo -e "${GREEN}🌐 Access the app at: http://localhost:8000${NC}"
echo -e "${YELLOW}📋 To view logs: docker-compose logs -f${NC}"
echo -e "${YELLOW}🛑 To stop: docker-compose down${NC}"