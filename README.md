# Multi-Agent AI System

A production-ready, distributed multi-agent AI framework with:
- **Configurable LLM provider per agent** (Ollama/free-local, OpenAI, Anthropic, Groq)
- **Expandable tool system** (file, web, code, office, knowledge — 16 built-in tools)
- **RAG knowledge base** (PDF, DOCX, XLSX, TXT, MD → ChromaDB)
- **LLM chain modes** (Sequential, Parallel, Router)
- **Distributed nodes** across multiple PCs/servers via Redis pub/sub
- **Master web app** (React) with chat, agents, tasks, nodes, knowledge panels
- **Security** (API keys, rate limiting, path sandboxing, privilege levels, secret redaction)
- **Docker Compose** one-command deployment

---

## Architecture Diagrams

### 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MASTER CONTROL PLANE                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                   React Web App (Vite + TailwindCSS)                │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │  │
│   │  │   Chat   │  │  Agents  │  │  Nodes   │  │ Tasks │ Knowledge  │ │  │
│   │  │(SSE+WS)  │  │  CRUD    │  │   Map    │  │ Queue │  Upload    │ │  │
│   │  └──────────┘  └──────────┘  └──────────┘  └────────────────────┘ │  │
│   └───────────────────────────┬──────────────────────────────────────────┘  │
│                               │  WebSocket + REST + SSE streaming           │
│   ┌───────────────────────────▼──────────────────────────────────────────┐  │
│   │                   FastAPI Master Server (:8000)                       │  │
│   │  /api/chat   /api/agents  /api/chains  /api/tasks                   │  │
│   │  /api/nodes  /api/knowledge  /ws/{session_id}                        │  │
│   │  ┌──────────────┐  ┌────────────────┐  ┌──────────────────────────┐ │  │
│   │  │ Rate Limiter  │  │  API Key Auth  │  │   WebSocket Manager      │ │  │
│   │  └──────────────┘  └────────────────┘  └──────────────────────────┘ │  │
│   └───────────────────────────┬──────────────────────────────────────────┘  │
│                               │                                              │
│   ┌───────────────────────────▼──────────────────────────────────────────┐  │
│   │             Redis (:6379) — pub/sub task routing + results            │  │
│   │   Channel: tasks:{node_id}   Channel: tasks:broadcast                │  │
│   │   Channel: results                                                   │  │
│   └────────────────────┬───────────────────────────┬─────────────────────┘  │
└────────────────────────┼───────────────────────────┼────────────────────────┘
                         │                           │
          ┌──────────────▼──────────────┐  ┌─────────▼────────────────┐
          │    NODE  (Laptop / PC)       │  │  NODE  (Server / VPS)    │
          │    python -m node.worker     │  │  python -m node.worker   │
          │  ┌───────────────────────┐   │  │  ┌──────────────────┐   │
          │  │     Orchestrator       │   │  │  │   Orchestrator   │   │
          │  │  ┌─────────────────┐  │   │  │  │  ┌────────────┐  │   │
          │  │  │ Agent A (Ollama) │  │   │  │  │  │Agent C     │  │   │
          │  │  │ FREE / LOCAL    │  │   │  │  │  │(OpenAI)    │  │   │
          │  │  ├─────────────────┤  │   │  │  │  ├────────────┤  │   │
          │  │  │ Agent B (Groq)  │  │   │  │  │  │Agent D     │  │   │
          │  │  │ FAST FREE TIER  │  │   │  │  │  │(Anthropic) │  │   │
          │  │  └─────────────────┘  │   │  │  │  └────────────┘  │   │
          │  └───────────────────────┘   │  │  └──────────────────┘   │
          │  ChromaDB + 16 Tools         │  │  ChromaDB + 16 Tools    │
          └──────────────────────────────┘  └──────────────────────────┘
```

---

### 2. Agent ReAct Loop

```
  User Input
      │
      ▼
 ┌──────────┐     ┌──────────────────────────────────────────┐
 │  Memory  │────▶│            LLM Provider                   │
 │(sliding  │     │  Ollama / OpenAI / Anthropic / Groq       │
 │  window) │     └──────────────┬──────────────┬────────────┘
 └──────────┘                    │               │
                         Tool call(s)?      Plain text?
                                 │               │
                    ┌────────────▼──────┐   ┌────▼──────────┐
                    │  Tool Dispatcher   │   │ Final Answer  │
                    │  ┌─────────────┐  │   └───────────────┘
                    │  │ read_file   │  │
                    │  │ fetch_web   │  │  ← privilege check
                    │  │ exec_python │  │  ← path sandbox
                    │  │ read_excel  │  │  ← secret redaction
                    │  │ query_kb    │  │
                    │  └─────────────┘  │
                    └────────┬──────────┘
                             │ results appended to memory
                             └──────────────────── loop (max N iterations)
```

---

### 3. LLM Chain Modes

```
SEQUENTIAL  (A → B → C)
────────────────────────────────────────────────────────────
Input ──▶ Agent A ──output──▶ Agent B ──output──▶ Agent C ──▶ Final
          researcher            writer             reviewer

PARALLEL  ([A, B, C] run simultaneously, merge)
────────────────────────────────────────────────────────────
          ┌──▶ Agent A (angle 1) ──┐
Input ────┼──▶ Agent B (angle 2) ──┼──▶ MergeAgent ──▶ Final
          └──▶ Agent C (angle 3) ──┘

ROUTER  (router picks best downstream agent)
────────────────────────────────────────────────────────────
Input ──▶ RouterAgent ──"use Agent B"──▶ Agent B ──▶ Final
```

---

### 4. Knowledge RAG Pipeline

```
  Files (PDF, DOCX, XLSX, TXT, MD, CSV, JSON, YAML…)
        │   uploaded via UI  OR  server-side directory
        ▼
  ┌─────────────────────────────────────┐
  │  File Reader (ingestion.py)         │
  │  .pdf → pypdf                       │
  │  .docx → python-docx                │
  │  .xlsx → openpyxl                   │
  │  others → plain text                │
  └──────────────────┬──────────────────┘
                     │ raw text
                     ▼
  ┌─────────────────────────────────────┐
  │  Chunker (1000 chars, 200 overlap)  │
  └──────────────────┬──────────────────┘
                     │ chunks[]
                     ▼
  ┌─────────────────────────────────────┐
  │  ChromaDB PersistentClient          │
  │  cosine similarity index            │
  │  ./data/chroma/                     │
  └──────────────────┬──────────────────┘
              At query time:
                     │ query_knowledge_base(query, n=5)
                     ▼
  ┌─────────────────────────────────────┐
  │  Top-N chunks + similarity scores   │
  │  injected into agent context window │
  └─────────────────────────────────────┘
```

---

### 5. Security Architecture

```
  Incoming HTTP Request
          │
  ┌───────▼──────────────────────┐
  │  Rate Limiter (per IP)        │  60 req/60s — configurable
  │  token-bucket algorithm       │  → 429 if exceeded
  └───────┬──────────────────────┘
          │ OK
  ┌───────▼──────────────────────┐
  │  API Key Auth                 │  X-API-Key header
  │  HMAC constant-time compare  │  → 401 if invalid
  │  (disabled if no keys set)   │  (dev mode: open access)
  └───────┬──────────────────────┘
          │ OK
  ┌───────▼──────────────────────┐
  │  Node Secret Auth             │  X-Node-Secret header
  │  (node registration only)    │  → 403 if wrong
  └───────┬──────────────────────┘
          │ OK (inside agent execution)
  ┌───────▼──────────────────────┐
  │  Privilege Level              │  0=READ_ONLY  1=STANDARD
  │  per-agent tool gating        │  2=ELEVATED  3=ADMIN
  └───────┬──────────────────────┘
  ┌───────▼──────────────────────┐
  │  Path Sandbox                 │  ALLOWED_DIRS env var
  │  resolves symlinks & checks   │  → PermissionError if outside
  └───────┬──────────────────────┘
  ┌───────▼──────────────────────┐
  │  Secret Redactor              │  regex strips API keys,
  │  applied to all LLM output   │  tokens, passwords → [REDACTED]
  └──────────────────────────────┘
```

---

### 6. Directory Layout

```
multi-agent/
├── core/                      Core framework
│   ├── providers/             LLM providers (Ollama/OpenAI/Anthropic/Groq)
│   ├── tools/                 16 built-in tools + registry
│   ├── knowledge/             RAG: ingestion + ChromaDB retrieval
│   ├── security.py            Auth, rate limiting, sandboxing, redaction
│   ├── memory.py              Sliding-window conversation memory
│   ├── agent.py               ReAct agent
│   ├── chain.py               Sequential / Parallel / Router chains
│   └── orchestrator.py        Multi-agent task coordinator
│
├── master/                    Control plane
│   ├── api/                   FastAPI app + routes + WebSocket
│   └── frontend/              React app (Vite + TailwindCSS)
│
├── node/
│   └── worker.py              Distributed node worker (Redis + Orchestrator)
│
├── config/
│   ├── agents.yaml            Agent / chain definitions
│   └── system.yaml            System defaults
│
├── docker-compose.yml         Full stack (redis + ollama + master + node)
├── Dockerfile.master
├── Dockerfile.node
├── requirements.txt
├── setup.sh                   One-command bootstrap
└── .env.example               Environment template
```

---

## Quick Start

### Docker (recommended — one command)

```bash
cp .env.example .env
docker-compose up

# Pull free local model (first time)
docker-compose exec ollama ollama pull llama3.2

# Open UI
open http://localhost:8000
```

### Local (no Docker)

```bash
./setup.sh                          # creates venv, installs deps, starts Redis

source .venv/bin/activate
uvicorn master.api.main:app --reload  # Terminal 1
python -m node.worker                  # Terminal 2
cd master/frontend && npm run dev      # Terminal 3

open http://localhost:5173
```

### Add a second node on another machine

```bash
NODE_ID=node-2 \
MASTER_URL=http://<master-ip>:8000 \
REDIS_URL=redis://<master-ip>:6379 \
python -m node.worker
```

The new node registers itself and appears live in the **Nodes** tab.

---

## Tools Reference (16 built-in)

| Tool | Category | Min Privilege |
|---|---|---|
| `read_file` | File | READ_ONLY |
| `write_file` | File | STANDARD |
| `list_directory` | File | READ_ONLY |
| `search_in_files` | File | READ_ONLY |
| `fetch_webpage` | Web | READ_ONLY |
| `http_request` | Web | STANDARD |
| `execute_python` | Code | ELEVATED |
| `execute_shell` | Code | ELEVATED |
| `read_excel` | Office | READ_ONLY |
| `write_excel` | Office | STANDARD |
| `read_word` | Office | READ_ONLY |
| `write_word` | Office | STANDARD |
| `read_pdf` | Office | READ_ONLY |
| `read_csv` | Office | READ_ONLY |
| `write_csv` | Office | STANDARD |
| `query_knowledge_base` | Knowledge | READ_ONLY |

---

## LLM Providers

| Provider | Cost | Notes |
|---|---|---|
| **Ollama** | **Free** | Fully local, no internet needed, best for privacy |
| **Groq** | Free tier | Ultra-fast cloud inference |
| **OpenAI** | Paid | GPT-4o, highest capability |
| **Anthropic** | Paid | Claude, best for long-context analysis |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MASTER_API_KEYS` | _(open)_ | Comma-separated allowed API keys |
| `NODE_SHARED_SECRET` | _(none)_ | Node ↔ master authentication |
| `ALLOWED_DIRS` | `./workspace` | Colon-separated sandbox paths |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `CHROMA_DIR` | `./data/chroma` | ChromaDB storage dir |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GROQ_API_KEY` | — | Groq API key |
| `MASTER_URL` | `http://localhost:8000` | Master URL (for node workers) |
| `NODE_ID` | _(hostname)_ | Unique node name |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window in seconds |
