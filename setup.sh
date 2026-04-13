#!/usr/bin/env bash
# ============================================================
# Multi-Agent AI System — one-command local setup
# Works on macOS, Linux, and WSL2
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }

# ---- Python virtualenv ----
if [ ! -d ".venv" ]; then
  info "Creating Python virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
info "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ---- .env ----
if [ ! -f ".env" ]; then
  cp .env.example .env
  info "Created .env from .env.example — edit it to add API keys"
fi

# ---- Data directories ----
mkdir -p data/chroma workspace

# ---- Ollama (optional) ----
if command -v ollama &>/dev/null; then
  info "Ollama found. Pulling llama3.2 model..."
  ollama pull llama3.2 || warn "Could not pull llama3.2. Run manually: ollama pull llama3.2"
else
  warn "Ollama not found. Install from https://ollama.com to use free local LLMs."
fi

# ---- Redis ----
if command -v redis-server &>/dev/null; then
  info "Redis found."
elif command -v docker &>/dev/null; then
  info "Starting Redis via Docker..."
  docker run -d --name multi-agent-redis -p 6379:6379 redis:7-alpine 2>/dev/null || true
else
  warn "Redis not found. Install Redis or Docker: https://redis.io"
fi

# ---- Frontend ----
if command -v node &>/dev/null; then
  info "Installing frontend dependencies..."
  cd master/frontend && npm install --silent && cd ../..
  info "Frontend ready. Run 'npm run dev' inside master/frontend/ to start dev server."
else
  warn "Node.js not found. Install from https://nodejs.org to build the frontend."
fi

info "=========================================="
info "Setup complete!"
info ""
info "Start the system:"
info "  # Terminal 1 — Master API"
info "  uvicorn master.api.main:app --reload"
info ""
info "  # Terminal 2 — Node worker"
info "  python -m node.worker"
info ""
info "  # Terminal 3 — React UI (dev)"
info "  cd master/frontend && npm run dev"
info ""
info "  # Or use Docker Compose for everything:"
info "  docker-compose up"
info ""
info "Open: http://localhost:5173"
info "=========================================="
