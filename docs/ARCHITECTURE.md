# Architecture Document
## Competitor Intelligence Agent — v1.0

---

## 1. System Overview

The system is composed of three main layers:

1. **Frontend** — A single `index.html` file (vanilla HTML/CSS/JS) that opens as a `file://` URL in the browser and communicates with the backend via WebSocket.
2. **Backend** — A FastAPI Python application running on `localhost` that hosts the agent loop, MCP tool server, and REST/WebSocket endpoints.
3. **Database** — AWS RDS MySQL storing conversation history, messages, tool call traces, and scraped results.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User's Browser                             │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                     index.html                              │   │
│   │   ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐  │   │
│   │   │   Sidebar   │  │   Chat Window    │  │  Input Area  │  │   │
│   │   │ (history)   │  │  + Thinking Btn  │  │ Text + URLs  │  │   │
│   │   └─────────────┘  └──────────────────┘  └──────────────┘  │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │  WebSocket (ws://localhost:8000/ws)   │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│                    FastAPI Backend (localhost:8000)                  │
│                              │                                      │
│   ┌───────────────────────────▼────────────────────────────────┐    │
│   │                   WebSocket Handler                         │    │
│   │          (receives message + URLs, sends events)           │    │
│   └───────────────────────────┬────────────────────────────────┘    │
│                               │                                     │
│   ┌───────────────────────────▼────────────────────────────────┐    │
│   │                     Agent Loop                              │    │
│   │   1. Build prompt (system + history + user message)        │    │
│   │   2. Call Groq API (reasoning_format="parsed", tools=[...])│    │
│   │   3. If tool_calls → execute via MCP → append results      │    │
│   │   4. Send tool_event over WebSocket (live trace)           │    │
│   │   5. Loop until no more tool calls                         │    │
│   │   6. Send final_response over WebSocket                    │    │
│   └──────────┬───────────────────────────┬─────────────────────┘    │
│              │                           │                          │
│   ┌──────────▼──────────┐    ┌───────────▼────────────────────┐    │
│   │   Groq API Client   │    │   MCP Tool Server (stdio)       │    │
│   │  openai/gpt-oss-120b│    │                                 │    │
│   │  reasoning_format=  │    │  ┌──────────────────────────┐   │    │
│   │    "parsed"         │    │  │  fetch-website-pages      │   │    │
│   └─────────────────────┘    │  │  scrape-one-page          │   │    │
│                              │  │  scrape-multi-pages       │   │    │
│                              │  └──────────┬───────────────┘   │    │
│                              │             │                    │    │
│                              │  ┌──────────▼───────────────┐   │    │
│                              │  │  httpx + BeautifulSoup   │   │    │
│                              │  │  (primary scraper)       │   │    │
│                              │  │  Playwright (fallback)   │   │    │
│                              │  └──────────────────────────┘   │    │
│                              └────────────────────────────────┘    │
│                                           │                        │
│   ┌───────────────────────────────────────▼────────────────────┐    │
│   │                   Database Layer                            │    │
│   │              SQLAlchemy (async) ORM                        │    │
│   └───────────────────────────────────────┬────────────────────┘    │
└───────────────────────────────────────────┼────────────────────────┘
                                            │
                              ┌─────────────▼──────────────┐
                              │     AWS RDS MySQL           │
                              │  (IP-restricted SG for dev) │
                              │                             │
                              │  conversations              │
                              │  messages                   │
                              │  tool_calls                 │
                              │  scrape_results             │
                              └────────────────────────────┘
```

---

## 2. Component Breakdown

### 2.1 Frontend (`index.html`)

A single HTML file opened as `file://` or optionally served by FastAPI as a static file.

| Component | Responsibility |
|-----------|---------------|
| **Sidebar** | Lists conversations fetched via REST on page load; "New Chat" button |
| **Chat window** | Renders user and agent messages in a scrollable thread |
| **Thinking panel** | Per-message collapsible section: model reasoning text + tool call trace |
| **Thinking button** | Toggles the Thinking panel; always visible, never removed from DOM |
| **Input area** | Two-part: text textarea (question) + dynamic URL chips (add/remove) |
| **Send button** | Sends message via WebSocket; disables during processing |
| **Loading indicator** | Animated spinner/dots shown while agent is processing |
| **Typewriter renderer** | Reveals agent text character-by-character once full response arrives |
| **WebSocket client** | Manages connection lifecycle; handles `tool_event` and `final_response` frames |
| **Session manager** | Generates/reads anonymous UUID from `localStorage`; passes it in every WS message |

**WebSocket event types received from backend:**

| Event type | Payload | UI action |
|------------|---------|-----------|
| `tool_event` | `{tool: str, input: dict, output_summary: str}` | Append entry to Thinking panel live |
| `final_response` | `{content: str, reasoning: str}` | Start typewriter; populate Thinking panel reasoning section |
| `error` | `{message: str}` | Show error toast |

---

### 2.2 Backend (`FastAPI`)

**Entry point:** `main.py` → `uvicorn main:app --reload --port 8000`

| Module | Path | Responsibility |
|--------|------|---------------|
| `main.py` | `/` | FastAPI app init, CORS config, router registration |
| `api/routes.py` | `/` | WebSocket endpoint + REST endpoints (conversations, messages) |
| `agent/agent.py` | `/` | Core agent loop: prompt building, Groq API calls, tool dispatch |
| `agent/groq_client.py` | `/` | Groq SDK wrapper; sets `reasoning_format="parsed"`, handles tool call response |
| `agent/prompts.py` | `/` | System prompt template for the competitor intelligence agent |
| `mcp/server/scraper_server.py` | `/` | MCP server definition (stdio); registers the three tools |
| `mcp/tools/fetch_pages.py` | `/` | `fetch-website-pages` implementation |
| `mcp/tools/scrape_one.py` | `/` | `scrape-one-page` implementation (httpx + BS4 → Playwright) |
| `mcp/tools/scrape_multi.py` | `/` | `scrape-multi-pages` implementation (parallel httpx, asyncio.gather) |
| `db/connection.py` | `/` | SQLAlchemy async engine + session factory (MySQL) |
| `db/models.py` | `/` | ORM models: Conversation, Message, ToolCall, ScrapeResult |
| `db/repository.py` | `/` | CRUD helpers used by the agent loop |

---

### 2.3 MCP Tool Server

The MCP server runs in the **same Python process** as FastAPI using `stdio` transport. The agent loop imports the tool functions directly and registers them with the Groq API as tool definitions (JSON schema). When the model returns a `tool_calls` array, the agent dispatches to the corresponding Python function, captures the result, and sends a `tool_event` over the WebSocket.

> **Note:** This design is intentionally simpler than a true subprocess MCP server. The tools are Python functions wrapped with MCP-compatible schemas. Migrating to a full subprocess MCP server (SSE transport) is a v2 concern.

**Tool execution flow:**

```
Groq returns tool_call(name="scrape-one-page", args={url: "..."})
        │
        ▼
agent.py dispatches → mcp/tools/scrape_one.py::scrape_one_page(url)
        │
        ├── Try: httpx GET → BeautifulSoup parse → return full HTML
        │
        └── Fallback: Playwright async page → page.content() → return HTML
        │
        ▼
result appended to messages as role="tool"
tool_event sent over WebSocket to UI
next Groq call made with updated message history
```

---

### 2.4 Database Layer

- **ORM:** SQLAlchemy (async, `asyncmy` driver for MySQL)
- **Connection:** Single async engine per process, connection pool size 5–10
- **Migrations:** Alembic (optional for v1; tables created with `Base.metadata.create_all` on startup)
- **Host:** AWS RDS MySQL (non-Aurora), port 3306, TLS enabled
- **Security group:** Inbound port 3306 allowed only for developer's current IP during dev phase

---

## 3. Project Directory Structure

```
website-scraper-agent/
│
├── index.html                   # Single-file frontend (vanilla HTML/CSS/JS)
│
├── main.py                      # FastAPI app entry point
│
├── agent/
│   ├── __init__.py
│   ├── agent.py                 # Agent loop (tool dispatch, Groq calls)
│   ├── groq_client.py           # Groq SDK wrapper
│   └── prompts.py               # System prompt
│
├── api/
│   ├── __init__.py
│   └── routes.py                # WebSocket + REST route handlers
│
├── mcp/
│   ├── server/
│   │   └── scraper_server.py    # MCP tool registry + schemas
│   └── tools/
│       ├── fetch_pages.py       # fetch-website-pages
│       ├── scrape_one.py        # scrape-one-page
│       └── scrape_multi.py      # scrape-multi-pages
│
├── db/
│   ├── __init__.py
│   ├── connection.py            # Async SQLAlchemy engine
│   ├── models.py                # ORM table definitions
│   └── repository.py           # CRUD helpers
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md          # ← this file
│   ├── DATABASE.md
│   ├── API.md
│   ├── TOOLS.md
│   ├── UI.md
│   └── TASKS.md
│
├── .env                         # GROQ_API_KEY, DB_URL, etc.
├── .env.example
├── .gitignore
├── pyproject.toml               # uv project config
└── uv.lock
```

---

## 4. Key Architectural Decisions & Rationale

### Why WebSocket instead of REST polling?
The agent loop can take 10–60+ seconds (multiple tool calls, sequential Groq API calls). WebSocket lets the backend push `tool_event` frames to the UI in real-time as each tool completes, so the user sees a live trace of the agent's work rather than staring at a static spinner.

### Why not stream the LLM response?
Groq's `reasoning_format="parsed"` is incompatible with streaming when tools are involved. The `reasoning` field is only available in the final, complete response. We wait for the full response, then simulate streaming on the frontend with a typewriter animation. This gives the same "feels alive" UX without the streaming complexity.

### Why `scrape-multi-pages` instead of calling `scrape-one-page` N times?
Each call to `scrape-one-page` through the LLM tool loop costs a full Groq API roundtrip. For a competitor site with 5 relevant pages, that's 5 extra LLM calls just to collect data. `scrape-multi-pages` runs all fetches in parallel with `asyncio.gather` and returns all results in a single tool call, reducing both latency and token usage significantly.

### Why stdio MCP instead of subprocess?
For v1, the agent and tools are in the same Python process. This avoids the complexity of subprocess management, port allocation, and inter-process communication. The tool functions are imported directly; the MCP schema is used for the Groq API tool definition only. A true MCP subprocess server is planned for v2 when tools become independently deployable.

### Why AWS RDS over local SQLite?
The scrape results can be large (full HTML pages). Cloud storage ensures the data is safe across machine restarts, is accessible from future EC2 instances, and allows straightforward migration when moving to production. The developer's IP is added to the RDS security group for the development phase.

---

## 5. Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key | `gsk_...` |
| `DB_HOST` | RDS endpoint | `mydb.xxxx.us-east-1.rds.amazonaws.com` |
| `DB_PORT` | MySQL port | `3306` |
| `DB_NAME` | Database name | `competitor_agent` |
| `DB_USER` | MySQL username | `admin` |
| `DB_PASSWORD` | MySQL password | `...` |
| `GROQ_MODEL` | Model identifier | `openai/gpt-oss-120b` |
| `BACKEND_PORT` | FastAPI port | `8000` |

---

## 6. Local Development Setup

```bash
# 1. Install dependencies
uv sync

# 2. Copy and fill environment file
cp .env.example .env

# 3. Start backend
uv run uvicorn main:app --reload --port 8000

# 4. Open frontend
# Just open index.html in your browser (file://)
# OR: visit http://localhost:8000 if served as static file
```

---

## 7. Deployment Migration Path (v1 → v2)

| Phase | Backend | Frontend | Database |
|-------|---------|----------|----------|
| **Dev (now)** | `localhost:8000` | `file://index.html` | RDS, dev IP SG |
| **Staging** | EC2 `uvicorn` behind nginx | Served by nginx | RDS, EC2 SG |
| **Production** | EC2 + systemd service | nginx static | RDS, private subnet |
