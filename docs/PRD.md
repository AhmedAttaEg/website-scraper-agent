# Product Requirements Document (PRD)
## Competitor Intelligence Agent — v1.0

---

## 1. Overview

A web-based AI agent chat interface that allows a user to monitor competitor websites for offers, discounts, price changes, or any noteworthy updates. The user can attach one or more competitor URLs to their message, and the agent will autonomously crawl and scrape those websites using MCP tools, reason about what it found, and respond with a clear, structured answer.

The system is designed to be a local-first tool during development (backend on `localhost`, `index.html` opened directly in the browser), with a clear migration path to AWS EC2 later.

---

## 2. Problem Statement

Manually checking competitor websites for promotions, price changes, or new offers is time-consuming and error-prone. There is no existing lightweight tool that lets a user simply ask in natural language — *"Did [competitor] launch any new offers today?"* — and get a reliable, AI-driven answer backed by live website data.

---

## 3. Goals

| # | Goal |
|---|------|
| G1 | Let a user ask natural-language questions about competitor websites |
| G2 | Allow the user to attach one or more URLs per message |
| G3 | Have the agent autonomously choose the right scraping tools and execute them |
| G4 | Surface the agent's reasoning and tool usage in a dedicated, togglable panel |
| G5 | Persist conversation history and scraped results in AWS RDS MySQL |
| G6 | Keep the entire UI in a single `index.html` file (no build step, no framework) |

---

## 4. Non-Goals (v1.0)

- No user authentication or multi-user support
- No automated/scheduled competitor checks (cron jobs, alerts)
- No email / Slack / Gmail notifications *(planned for v2)*
- No production deployment *(local only for now; EC2 migration is post-v1)*
- No image or screenshot analysis of competitor pages
- No competitor comparison side-by-side dashboards

---

## 5. Users

**Primary user:** A single business operator or analyst who runs the tool locally on their machine to stay updated on competitor activity. No login required. Sessions are identified by an anonymous session ID stored in `localStorage`.

---

## 6. User Stories

### Core Chat Flow
- **US-01** — As a user, I want to type a natural-language question and attach one or more competitor URLs so the agent can investigate and answer me.
- **US-02** — As a user, I want to see a loading indicator while the agent is working so I know the request is in progress.
- **US-03** — As a user, I want the agent's final answer to appear smoothly (typewriter-style reveal) so it feels responsive even though the response was fully buffered.

### Thinking Panel
- **US-04** — As a user, I want to click a "Thinking" button on any agent message to toggle a panel showing the model's internal reasoning text.
- **US-05** — As a user, I want the Thinking panel to also show every MCP tool that was called (tool name, input arguments, and a summary of the output) so I can trace exactly what the agent did.
- **US-06** — As a user, I want the Thinking button to always remain visible and clickable — it should never disappear after I click it.

### Conversation History
- **US-07** — As a user, I want a sidebar listing all my past conversations so I can revisit them.
- **US-08** — As a user, I want to click a past conversation in the sidebar to reload its full message history.
- **US-09** — As a user, I want to start a new conversation at any time via a "New Chat" button.

### Multi-URL / Multi-question Input
- **US-10** — As a user, I want a dedicated URL input area (separate from my text message) where I can add multiple competitor URLs to a single request.
- **US-11** — As a user, I want to add or remove URLs from the input before submitting.

### Persistence
- **US-12** — As a user, I want my conversation history to be saved so it survives a page refresh or browser restart.
- **US-13** — As a user, I want the raw scraped data from each request to also be saved so the agent (or I) can reference previous scrape results in future questions.

---

## 7. Feature List (v1.0)

### 7.1 Agent Capabilities
| Feature | Description |
|---------|-------------|
| Natural-language understanding | The agent interprets free-form competitor monitoring questions |
| Autonomous tool selection | The agent decides which MCP tools to use and in what order |
| Multi-step tool loop | The agent may call multiple tools (fetch → scrape) until it has enough data |
| Unbounded tool calls | No hard cap on tool calls per request; agent loops until it has an answer |
| Reasoning extraction | Model reasoning tokens (`reasoning_format="parsed"`) are captured and stored |

### 7.2 MCP Tools
| Tool | Purpose |
|------|---------|
| `fetch-website-pages` | Crawl a website's sitemap/homepage links and return a list of `{name, url}` pairs |
| `scrape-one-page` | Fetch and return the full HTML of a single URL (httpx first, Playwright fallback) |
| `scrape-multi-pages` | Batch-scrape multiple URLs in parallel; returns a list of `{url, html}` objects |

### 7.3 UI Components
| Component | Description |
|-----------|-------------|
| Sidebar | Lists all conversations; supports "New Chat" |
| Chat window | Scrollable message thread |
| Message input | Text area for the user's question |
| URL input area | Add/remove multiple competitor URLs per message |
| Send button | Submits the message + URLs |
| Loading state | Animated indicator while agent is processing |
| Thinking button | Per-message toggle for reasoning + tool call trace panel |
| Typewriter reveal | Agent response appears progressively after full response is received |

### 7.4 Persistence
| What | Where |
|------|-------|
| Conversation metadata | `conversations` table (MySQL RDS) |
| All messages (user + agent) | `messages` table |
| Agent reasoning text | `messages` table (`reasoning` column) |
| Tool call traces | `tool_calls` table |
| Scraped page results | `scrape_results` table |

---

## 8. Technical Constraints & Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| LLM | Groq `openai/gpt-oss-120b` | Supports reasoning tokens + tool calling; fast inference |
| Reasoning API | `reasoning_format="parsed"` | Separates reasoning into a dedicated field alongside tool calls |
| Backend framework | FastAPI (Python) | Async-native, WebSocket support, fast |
| Frontend | Single `index.html` (vanilla HTML/CSS/JS) | Zero build step; easy to share and iterate |
| Real-time transport | WebSocket | Supports long-running agent loops; sends intermediate tool events and final answer |
| MCP transport | stdio (in-process Python) | Simplest for v1; agent and MCP server share the same process |
| Primary scraper | httpx + BeautifulSoup | Lightweight; `httpx` already in deps |
| Fallback scraper | Playwright | For JS-rendered sites |
| Database | AWS RDS MySQL (non-Aurora) | Persistent, cloud-hosted; dev phase uses IP-restricted security group |
| Session identity | Anonymous UUID in `localStorage` | No login required |
| Deployment (now) | `localhost` | Backend on `uvicorn`; `index.html` opened as `file://` |
| Deployment (later) | AWS EC2 | Backend moved to EC2; `index.html` served as static file |

---

## 9. Data Flow (High Level)

```
User types message + attaches URLs
        │
        ▼
index.html  ──[WebSocket]──►  FastAPI Backend
                                    │
                              Agent Loop (Groq)
                                    │
                           ┌────────┴────────┐
                           │  MCP Tool Calls  │
                           │  (stdio, Python) │
                           └────────┬────────┘
                                    │
                              Tool results
                              fed back to Groq
                                    │
                              Final answer +
                              reasoning captured
                                    │
                     ┌─────────────┴─────────────┐
                     │                           │
              WebSocket response           MySQL RDS
              (reasoning + tool           (messages,
               chain + answer)            tool_calls,
                     │                  scrape_results)
                     ▼
              index.html renders
              typewriter answer +
              Thinking panel available
```

---

## 10. Success Criteria (v1.0)

- [ ] User can send a message with ≥1 URL and receive a coherent competitor analysis answer
- [ ] Agent correctly uses `fetch-website-pages` → `scrape-*` tool chain autonomously
- [ ] "Thinking" button reveals model reasoning text AND tool call trace on every agent message
- [ ] Conversation history persists across page refreshes
- [ ] Scraped HTML is stored in MySQL for future reference
- [ ] No streaming used; full response arrives then typewriter reveal begins

---

## 11. Future Roadmap (Post v1.0)

| Feature | Version |
|---------|---------|
| Scheduled competitor checks (cron) | v2 |
| Gmail / Slack notifications on detected changes | v2 |
| User-defined alert rules ("notify me if price drops below X") | v2 |
| EC2 deployment with proper domain | v2 |
| Multi-user support with login | v3 |
| Screenshot / visual diff of competitor pages | v3 |
| Competitor comparison dashboard | v3 |
