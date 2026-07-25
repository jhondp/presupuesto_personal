#!/bin/bash
set -e

echo "🚀 Personal Finance Platform — Local Setup"
echo "==========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Ask for Supabase credentials
echo -e "${BLUE}Step 1: Supabase Credentials${NC}"
echo "Go to https://supabase.com → Create Project (free tier) → copy these values:"
echo ""

read -p "SUPABASE_URL (https://xxxxx.supabase.co): " SUPABASE_URL
read -p "SUPABASE_ANON_KEY (eyJhbGc...): " SUPABASE_ANON_KEY
read -p "SUPABASE_JWT_SECRET (your-jwt-secret): " SUPABASE_JWT_SECRET

echo ""
echo -e "${YELLOW}⏳ Creating .env file...${NC}"

# Create .env in api/
cat > api/.env << EOF
SUPABASE_URL=$SUPABASE_URL
SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
SUPABASE_JWT_SECRET=$SUPABASE_JWT_SECRET
MAX_EXPORT_ROWS=10000
EOF

echo -e "${GREEN}✓ .env created${NC}"
echo ""

# 2. Setup Python backend
echo -e "${BLUE}Step 2: Python Backend Setup${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}❌ Python 3 not found. Install it first: brew install python@3.12${NC}"
    exit 1
fi

cd api

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⏳ Creating Python venv...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate

echo -e "${YELLOW}⏳ Installing dependencies...${NC}"
pip install -e '.[dev]' -q

echo -e "${GREEN}✓ Backend ready${NC}"
cd ..
echo ""

# 3. Apply migrations
echo -e "${BLUE}Step 3: Supabase Migrations${NC}"
echo -e "${YELLOW}Open Supabase Dashboard → SQL Editor${NC}"
echo "Copy & paste each file IN THIS ORDER:"
echo ""

for i in 1 2 3 4 5 6; do
    file="supabase/migrations/000${i}_*.sql"
    actual_file=$(ls $file 2>/dev/null | head -1)
    if [ -f "$actual_file" ]; then
        echo "  ${YELLOW}→${NC} $actual_file"
    fi
done

echo ""
read -p "Done applying migrations? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "⚠️ Skipping. You'll need to apply them manually before running."
fi

echo ""

# 4. Update web/index.html
echo -e "${BLUE}Step 4: Web Client Configuration${NC}"
echo -e "${YELLOW}⏳ Updating web/index.html...${NC}"

# Escape special characters for sed
ESCAPED_URL=$(echo "$SUPABASE_URL" | sed 's/[&/\]/\\&/g')
ESCAPED_KEY=$(echo "$SUPABASE_ANON_KEY" | sed 's/[&/\]/\\&/g')

sed -i.bak "s|https://YOUR_SUPABASE_URL.supabase.co|$ESCAPED_URL|g" web/index.html
sed -i.bak "s|YOUR_SUPABASE_ANON_KEY|$ESCAPED_KEY|g" web/index.html
sed -i.bak "s|http://localhost:8000|http://localhost:8000|g" web/index.html

# Clean backup
rm -f web/index.html.bak

echo -e "${GREEN}✓ Web config updated${NC}"
echo ""

# 5. Summary & run instructions
echo -e "${GREEN}==========================================="
echo "✓ Setup Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${BLUE}To start the application:${NC}"
echo ""
echo "Terminal 1 (Backend):"
echo "  cd api"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload"
echo ""
echo "Terminal 2 (Frontend):"
echo "  cd web"
echo "  python3 -m http.server 4173"
echo ""
echo -e "${YELLOW}Then open: ${GREEN}http://localhost:4173${NC}"
echo ""
echo "Sign up with email/password → enjoy!"
echo ""
