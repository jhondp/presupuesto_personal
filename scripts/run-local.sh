#!/bin/bash

echo "🚀 Starting Personal Finance Platform (Local)"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}Starting Backend (FastAPI)...${NC}"
echo ""

# Start backend in background
cd "$PROJECT_ROOT/api"
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo -e "${GREEN}✓ Backend PID: $BACKEND_PID${NC}"
sleep 3

echo ""
echo -e "${BLUE}Starting Frontend (Static Server)...${NC}"
echo ""

# Start frontend in background
cd "$PROJECT_ROOT/web"
python3 -m http.server 4173 &
FRONTEND_PID=$!

echo -e "${GREEN}✓ Frontend PID: $FRONTEND_PID${NC}"
sleep 2

echo ""
echo -e "${GREEN}=============================================="
echo "✓ Application Started!"
echo "===============================================${NC}"
echo ""
echo -e "Backend:  ${YELLOW}http://localhost:8000${NC}"
echo -e "Frontend: ${YELLOW}http://localhost:4173${NC}"
echo ""
echo "Open http://localhost:4173 in your browser"
echo ""
echo "To stop: press Ctrl+C"
echo ""

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID

echo ""
echo -e "${YELLOW}Application stopped${NC}"
