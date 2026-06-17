# Competitor Intelligence Agent
> An AI-powered chat agent that monitors competitor websites for offers, discounts, and price changes using autonomous web scraping and LLM reasoning.

---

## Stack
| Layer | Technology |
|-------|-----------|
| LLM | Groq — `openai/gpt-oss-120b` (`reasoning_format="parsed"`) |
| Backend | Python 3.13 · FastAPI · WebSockets · Uvicorn |
| Agent | Custom agent loop · Groq SDK · MCP tool dispatch (stdio) |
| Scraping | httpx + BeautifulSoup (primary) · Playwright (fallback) |
| Database | AWS RDS MySQL 8.x · SQLAlchemy (async) · asyncmy |
| Frontend | Vanilla HTML · CSS · JavaScript (single `index.html`) |
| Package manager | uv |

---

## Docs
- [PRD](./PRD.md) · [Architecture](./ARCHITECTURE.md) · [Database](./DATABASE.md)
- [API](./API.md) · [Tools](./TOOLS.md) · [UI](./UI.md)

---

## Status Legend
| Symbol | Meaning |
|--------|---------|
| `[]` | Not started |
| `[/]` | In progress |
| `[x]` | Done |
| `[!]` | Blocked |

---
---

# Milestone 1 — Project Foundation
> **Goal:** Establish the full project skeleton — directory structure, dependencies, environment config, and a working database connection — so every subsequent milestone can build on a solid, runnable base.

---

## Atomic Milestone 1.1 — Project Structure & Dependencies
> **Goal:** Set up the directory layout, install all required packages, and verify the project runs without errors.

- [x] **WS 111 — Scaffold Directory Structure**
  > DoD: All directories (`agent/`, `api/`, `mcp/server/`, `mcp/tools/`, `db/`, `docs/`) and `__init__.py` files exist; `main.py` is present at root.

- [x] **WS 112 — Install Core Dependencies**
  > DoD: `pyproject.toml` includes and `uv sync` successfully installs all required packages:
  > - `fastapi`, `uvicorn[standard]`
  > - `groq`
  > - `httpx`, `beautifulsoup4`, `lxml`
  > - `playwright` (with `uv run playwright install chromium`)
  > - `sqlalchemy[asyncio]`, `asyncmy`
  > - `python-dotenv`

- [x] **WS 113 — Configure Environment Variables**
  > DoD:
  > - `.env.example` lists all required vars: `GROQ_API_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `GROQ_MODEL`, `BACKEND_PORT`
  > - `.env` is populated with real values and excluded from git via `.gitignore`
  > - `python-dotenv` loads vars at backend startup without errors

---

## Atomic Milestone 1.2 — Database Setup
> **Goal:** Provision the AWS RDS MySQL instance, connect to it from the backend, and have all four tables auto-created on startup.

- [x] **WS 121 — Provision AWS RDS MySQL Instance**
  > DoD:
  > - RDS MySQL 8.x instance is running in AWS
  > - Database `competitor_agent` is created
  > - Security group allows inbound port 3306 from developer's IP `/32` only
  > - TLS connection is enabled

- [x] **WS 122 — Implement Async DB Connection (`db/connection.py`)**
  > DoD: `create_async_engine` and `AsyncSessionLocal` are configured using env vars; `init_db()` coroutine calls `Base.metadata.create_all()` and connects successfully to RDS without errors.

- [x] **WS 123 — Implement ORM Models (`db/models.py`)**
  > DoD: All four SQLAlchemy models are defined and match the schema in `DATABASE.md`:
  > - `Conversation`, `Message`, `ToolCall`, `ScrapeResult`
  > - Relationships, foreign keys, cascades, and indexes are all in place

- [x] **WS 124 — Implement Repository CRUD Helpers (`db/repository.py`)**
  > DoD: The following async functions exist and execute without error against the live RDS instance:
  > - `create_conversation()`, `get_conversations_by_session()`
  > - `create_message()`, `get_messages_by_conversation()`
  > - `create_tool_call()`, `create_scrape_result()`
  > - `delete_conversation()`, `update_conversation_title()`

- [x] **WS 125 — Verify Tables Auto-Created on Startup**
  > DoD: Running `uv run uvicorn main:app` creates all four tables in RDS if they don't exist; confirmed via MySQL client or AWS RDS console.

---
---

# Milestone 2 — MCP Scraping Tools
> **Goal:** Implement all three MCP tools (`fetch-website-pages`, `scrape-one-page`, `scrape-multi-pages`) as working async Python functions, registered in the MCP tool registry and ready to be dispatched by the agent loop.

---

## Atomic Milestone 2.1 — Scraping Infrastructure
> **Goal:** Build the shared HTTP + browser scraping base that all tools use.

- [] **WS 211 — httpx Async Client with Browser Headers**
  > DoD: A shared `async_scrape(url)` helper exists that uses `httpx.AsyncClient` with realistic browser headers (User-Agent, Accept, etc.), a 30s timeout, and follows redirects; returns `(html: str, final_url: str, status_code: int)`.

- [] **WS 212 — Playwright Headless Fallback**
  > DoD: A `playwright_scrape(url)` async function exists that launches headless Chromium, waits for `networkidle`, and returns the fully rendered HTML; closes the browser after each call.

---

## Atomic Milestone 2.2 — `fetch-website-pages` Tool
> **Goal:** Implement the site-crawling tool that discovers all internal pages of a competitor website.

- [] **WS 221 — Sitemap.xml Parser**
  > DoD: Function attempts to fetch `/sitemap.xml` and `/sitemap_index.xml`; if found, parses all `<loc>` entries and returns a list of URLs.

- [] **WS 222 — Homepage Link Crawler**
  > DoD: Function fetches the root URL, parses all `<a href>` tags with BeautifulSoup, filters to same-domain internal links, and deduplicates results.

- [] **WS 223 — Page Name Extractor**
  > DoD: For each discovered URL, a human-readable name is derived from anchor text, `<title>` tag, or URL path segment (e.g. `/pricing` → `"Pricing"`).

- [] **WS 224 — Register `fetch-website-pages` in MCP Server**
  > DoD: Tool JSON schema matches `TOOLS.md` §2; function is in `TOOL_DISPATCH`; calling `dispatch_tool("fetch-website-pages", {"url": "https://example.com"})` returns a valid `{pages_found, pages}` response.

---

## Atomic Milestone 2.3 — `scrape-one-page` Tool
> **Goal:** Implement single-page scraping with automatic httpx → Playwright fallback.

- [] **WS 231 — Implement `scrape-one-page` Logic**
  > DoD:
  > - Tries httpx first; falls back to Playwright if response is non-200 or HTML < 1KB
  > - Returns `{url, page_title, html, size_bytes, rendered_with, scraped_at}`
  > - `page_title` extracted from `<title>` tag via BeautifulSoup

- [] **WS 232 — Register `scrape-one-page` in MCP Server**
  > DoD: Tool JSON schema matches `TOOLS.md` §3; calling `dispatch_tool("scrape-one-page", {"url": "..."})` returns valid response.

---

## Atomic Milestone 2.4 — `scrape-multi-pages` Tool
> **Goal:** Implement parallel batch scraping to eliminate redundant LLM roundtrips.

- [] **WS 241 — Implement `scrape-multi-pages` with `asyncio.gather`**
  > DoD:
  > - Accepts up to 20 URLs; all scraped concurrently via `asyncio.gather`
  > - Partial failures handled gracefully — failed URLs have `"error"` field; successful ones are returned normally
  > - Returns `{total_requested, total_succeeded, total_failed, results[]}`

- [] **WS 242 — Register `scrape-multi-pages` in MCP Server**
  > DoD: Tool JSON schema matches `TOOLS.md` §4; calling `dispatch_tool("scrape-multi-pages", {"urls": [...]})` returns valid batch response.

---

## Atomic Milestone 2.5 — Tool Registry & Dispatch
> **Goal:** Wire all tools into a single dispatch system the agent loop can call uniformly.

- [] **WS 251 — Implement `TOOLS` List (Groq API Format)**
  > DoD: `TOOLS` list in `scraper_server.py` contains all three tool definitions in OpenAI/Groq function-calling JSON format; list is importable by the agent.

- [] **WS 252 — Implement `dispatch_tool()` Function**
  > DoD: `dispatch_tool(name: str, arguments: dict) -> dict` correctly routes to the matching tool function; raises `ValueError` for unknown tool names.

---
---

# Milestone 3 — Agent Core
> **Goal:** Build the multi-turn agent loop that calls Groq with `reasoning_format="parsed"`, dispatches tool calls, accumulates results, and returns a final answer with reasoning.

---

## Atomic Milestone 3.1 — Groq API Client
> **Goal:** Create a clean wrapper around the Groq SDK configured for reasoning + tool use.

- [] **WS 311 — Implement Groq SDK Wrapper (`agent/groq_client.py`)**
  > DoD: `groq_chat(messages, tools, on_tool_event)` async function calls Groq with `reasoning_format="parsed"`, `tool_choice="auto"`, and the full `TOOLS` list; returns `{content, reasoning, tool_calls}`.

- [] **WS 312 — Validate Reasoning Tokens Are Returned**
  > DoD: A quick test call to Groq confirms `message.reasoning` is populated (non-empty string) on responses that involve thinking; confirmed manually in the terminal.

---

## Atomic Milestone 3.2 — Agent Loop (`agent/agent.py`)
> **Goal:** Implement the full multi-turn loop that keeps calling Groq until no more tool calls are returned.

- [] **WS 321 — Implement Multi-Turn Tool Call Loop**
  > DoD:
  > - Loop starts with `[system, ...history, user_message]`
  > - Each Groq response is checked for `tool_calls`
  > - If tool calls exist: dispatch each via `dispatch_tool()`, append `role="tool"` results, call Groq again
  > - Loop exits when Groq returns a response with no tool calls
  > - No hard cap on iterations

- [] **WS 322 — Implement `on_tool_event` Callback**
  > DoD: After each tool call completes, an `on_tool_event(tool_name, tool_input, output_summary, sequence)` callback is invoked; the WebSocket handler can pass its own callback to stream `tool_event` frames live.

- [] **WS 323 — Persist Agent Turn to Database**
  > DoD: At the end of each agent turn, the following are saved to MySQL:
  > - User message row (`role="user"`, `urls_attached`)
  > - Assistant message row (`role="assistant"`, `content`, `reasoning`)
  > - One `ToolCall` row per tool call
  > - One `ScrapeResult` row per scraped URL

---

## Atomic Milestone 3.3 — System Prompt
> **Goal:** Write a system prompt that reliably guides the model to use the tools correctly.

- [] **WS 331 — Write & Test System Prompt (`agent/prompts.py`)**
  > DoD:
  > - System prompt instructs the agent to: always call `fetch-website-pages` first, prefer `scrape-multi-pages` for 2+ pages, analyze HTML for offers/prices/promotions, and never fabricate data
  > - Tested manually: agent consistently follows the `fetch → scrape → answer` chain without extra prompting

---
---

# Milestone 4 — FastAPI Backend
> **Goal:** Build the full FastAPI application with WebSocket and REST endpoints wired to the agent core and database layer.

---

## Atomic Milestone 4.1 — App Initialization
> **Goal:** Stand up a running FastAPI app with CORS, DB startup, and health check.

- [] **WS 411 — Initialize FastAPI App with CORS (`main.py`)**
  > DoD: `uvicorn main:app --reload` starts without errors; CORS middleware allows `"null"` origin (for `file://`) and `http://localhost:8000`.

- [] **WS 412 — Implement `/health` Endpoint**
  > DoD: `GET /health` returns `{"status": "ok", "db": "connected", "groq": "reachable"}` with 200; DB and Groq reachability are actually checked (not hardcoded).

- [] **WS 413 — Implement Startup DB Initialization**
  > DoD: `@app.on_event("startup")` calls `init_db()` which creates all tables if missing; confirmed on fresh RDS DB.

---

## Atomic Milestone 4.2 — WebSocket Endpoint
> **Goal:** Implement the real-time WebSocket handler that drives the full chat → agent → response loop.

- [] **WS 421 — WebSocket Connection Handler**
  > DoD: `ws://localhost:8000/ws?session_id=&conversation_id=` accepts connections; creates a new conversation in MySQL if no `conversation_id` is given; sends `conversation_created` event.

- [] **WS 422 — Handle `user_message` from Client**
  > DoD: Receives and validates `{type, content, urls}` JSON; rejects malformed messages with `error` event; passes valid messages to the agent loop.

- [] **WS 423 — Stream `tool_event` Frames During Agent Loop**
  > DoD: Each time the agent calls a tool, a `tool_event` JSON frame is pushed over the WebSocket to the client in real-time, before the final response.

- [] **WS 424 — Send `final_response` Frame**
  > DoD: After the agent loop exits, `{type: "final_response", message_id, content, reasoning, tool_count, created_at}` is sent to the client.

- [] **WS 425 — Send `error` Frame on Failure**
  > DoD: Any unhandled exception in the agent loop or tool dispatch sends an `{type: "error", code, message, recoverable}` frame; WebSocket connection remains open after recoverable errors.

---

## Atomic Milestone 4.3 — REST Endpoints
> **Goal:** Implement the REST API used by the frontend sidebar to load and manage conversation history.

- [] **WS 431 — `GET /api/conversations`**
  > DoD: Returns all conversations for a `session_id`, sorted by `updated_at` descending, with `{id, title, updated_at, message_count}` per item.

- [] **WS 432 — `GET /api/conversations/{id}/messages`**
  > DoD: Returns full message history for a conversation including nested `tool_calls` array on assistant messages; matches response shape in `API.md` §3.2.

- [] **WS 433 — `DELETE /api/conversations/{id}`**
  > DoD: Deletes conversation and all cascaded rows (messages, tool_calls, scrape_results) from MySQL; returns `{"deleted": true}`.

- [] **WS 434 — `PATCH /api/conversations/{id}`**
  > DoD: Updates `title` field; returns updated conversation object.

---
---

# Milestone 5 — Frontend (index.html)
> **Goal:** Build the complete single-file UI — sidebar, chat window, Thinking panel, input area, and WebSocket client — matching the spec in `UI.md`.

---

## Atomic Milestone 5.1 — Design System & Layout
> **Goal:** Establish the CSS foundation and two-panel layout before any components are built.

- [] **WS 511 — CSS Variables, Reset & Typography**
  > DoD: All design tokens from `UI.md` §3 are defined as CSS custom properties; Inter font is loaded; base reset applied; no unstyled elements visible.

- [] **WS 512 — Sidebar + Chat Window Layout**
  > DoD: Fixed 260px sidebar on the left; chat window fills remaining width; layout is stable at 900px+ viewport width with no overflow.

---

## Atomic Milestone 5.2 — Sidebar
> **Goal:** Build the fully functional sidebar with conversation list and new-chat capability.

- [] **WS 521 — Conversation List (from REST API)**
  > DoD: On page load, `GET /api/conversations` is called and results render as a scrollable list with title (truncated) and relative timestamp.

- [] **WS 522 — New Chat Button**
  > DoD: Clicking "New Chat" clears the chat window, opens a new WebSocket (no `conversation_id`), and sets a pending state until the first message is sent.

- [] **WS 523 — Load Existing Conversation on Click**
  > DoD: Clicking a sidebar item calls `GET /api/conversations/{id}/messages`, renders the full message history (including Thinking panels with tool traces), and reconnects the WebSocket to that conversation.

- [] **WS 524 — Delete Conversation**
  > DoD: Hovering a sidebar item reveals a ✕ button; clicking it calls `DELETE /api/conversations/{id}` and removes the item from the sidebar with a fade-out animation.

---

## Atomic Milestone 5.3 — Chat Window & Message Bubbles
> **Goal:** Render user and agent messages correctly with all their sub-components.

- [] **WS 531 — User Message Bubble**
  > DoD: Displays message text and URL chips (domain + link icon) in `--user-bubble` style; auto-scrolls chat to bottom on render.

- [] **WS 532 — Agent Message Bubble with Markdown**
  > DoD: Agent response rendered via `marked.js`; supports bold, italic, code, lists, headings; styled within `--agent-bubble` background.

- [] **WS 533 — URL Chips in User Messages**
  > DoD: Each attached URL is shown as a small pill badge showing the domain; chips are clickable (open URL in new tab).

- [] **WS 534 — Empty State / Welcome Screen**
  > DoD: When no messages exist, a centered welcome message with 2–3 suggested example questions is displayed in the chat area.

---

## Atomic Milestone 5.4 — Thinking Button & Panel
> **Goal:** Implement the signature Thinking panel — always visible, toggleable, and live-updating during processing.

- [] **WS 541 — Thinking Toggle Button**
  > DoD:
  > - Button always present on every agent bubble; never removed from DOM
  > - Click toggles panel open/closed; chevron icon rotates to reflect state
  > - State is independent per message (opening one doesn't close others)

- [] **WS 542 — Reasoning Section in Panel**
  > DoD: `💭 Reasoning` section renders the `reasoning` string from `final_response` in monospace font with a left purple border; scrollable if long.

- [] **WS 543 — Tool Call Trace Cards**
  > DoD: `🔧 Tool Calls (N)` section renders one card per tool call showing: tool name badge, call number, pretty-printed input JSON (collapsible), and output summary text.

- [] **WS 544 — Live Tool Event Appending During Loading**
  > DoD: As `tool_event` WebSocket frames arrive, new tool cards append to the in-progress message's Thinking panel in real-time; user can open the panel mid-processing to watch the agent work.

---

## Atomic Milestone 5.5 — Input Area
> **Goal:** Build the two-part input area (URLs + message) with all interactive behaviors.

- [] **WS 551 — URL Chips Row (Add / Remove)**
  > DoD:
  > - "Add URL" button reveals inline input; Enter or click confirms
  > - Invalid URLs show inline error and are not added
  > - Each chip shows domain name + ✕ remove button
  > - Chips animate in (scale) and out (fade + collapse)

- [] **WS 552 — Auto-Expanding Message Textarea**
  > DoD: Textarea grows with content (1–6 lines); exceeds 6 lines → scrolls internally; placeholder text shown when empty.

- [] **WS 553 — Send Button & Keyboard Shortcut**
  > DoD: `Enter` sends; `Shift+Enter` inserts newline; Send button click also sends; both collect `{content, urls}` and send `user_message` over WebSocket.

- [] **WS 554 — Disable Input During Processing**
  > DoD: While agent is processing, textarea and Send button are disabled (grayed, non-interactive); "Add URL" button is hidden; re-enabled on `final_response` or `error`.

---

## Atomic Milestone 5.6 — WebSocket Client
> **Goal:** Implement the complete browser-side WebSocket logic that drives all real-time UI updates.

- [] **WS 561 — Session Management**
  > DoD: On page load, `sessionId` is read from `localStorage` or generated as a new UUID and stored; `conversationId` is managed in memory per active chat.

- [] **WS 562 — WebSocket Connection Lifecycle**
  > DoD: `connect(convId?)` opens a WS connection with correct query params; disconnects cleanly when switching conversations or starting new chat; reconnects on unexpected close.

- [] **WS 563 — Handle All Server Event Types**
  > DoD: `handleServerEvent()` correctly routes all event types: `conversation_created`, `agent_thinking`, `tool_event`, `final_response`, `error` — each triggers the correct UI update.

- [] **WS 564 — Typewriter Reveal Animation**
  > DoD: On `final_response`, the full `content` string is revealed character-by-character at ~12ms/char via `setInterval`; Markdown is re-parsed and re-rendered on each tick.

---

## Atomic Milestone 5.7 — Loading State
> **Goal:** Give the user clear visual feedback that the agent is actively working.

- [] **WS 571 — Status Bar with Live Tool Updates**
  > DoD: Status bar appears above input area showing `🤔 Agent is thinking…` initially; updates to `🔧 Calling [tool-name]…` on each `tool_event`; disappears on `final_response`.

- [] **WS 572 — In-Progress Agent Bubble with Typing Animation**
  > DoD: A placeholder agent bubble with animated `···` dots appears immediately after `agent_thinking` is received; replaced by the real response content when `final_response` arrives.

---
---

# Milestone 6 — Integration & Quality
> **Goal:** Verify the full system works end-to-end with real competitor URLs, and all error paths are handled gracefully.

---

## Atomic Milestone 6.1 — End-to-End Smoke Tests
> **Goal:** Manually verify the complete happy-path flow works from browser to Groq to database.

- [] **WS 611 — Full Chat Flow: Single URL**
  > DoD:
  > - User sends message + 1 URL in the browser
  > - Agent calls `fetch-website-pages` then `scrape-multi-pages`
  > - `tool_event` frames appear live in Thinking panel
  > - Final answer rendered with typewriter effect
  > - All data persisted in MySQL (confirmed via DB client)

- [] **WS 612 — Multi-URL Competitor Check**
  > DoD: User attaches 2+ URLs; agent processes all; response addresses all sites; all scrape results saved in `scrape_results` table.

- [] **WS 613 — Conversation History Persistence**
  > DoD: After a conversation, page refresh shows it in the sidebar; clicking it fully restores the message thread including Thinking panels with tool traces.

- [] **WS 614 — Reasoning Tokens in Thinking Panel**
  > DoD: At least one real agent response confirms `reasoning` is non-empty and displays correctly in the `💭 Reasoning` section of the Thinking panel.

---

## Atomic Milestone 6.2 — Error Handling
> **Goal:** Ensure the system fails gracefully under common failure scenarios.

- [] **WS 621 — Scrape Failure Fallback (httpx → Playwright)**
  > DoD: A URL known to require JS rendering is scraped; httpx attempt fails/returns thin HTML; Playwright takes over and returns full content; `rendered_with: "playwright"` in response.

- [] **WS 622 — Unreachable Website Error**
  > DoD: User provides a non-existent URL; agent receives `SCRAPE_FAILED` error from tool; agent reports to user that the site was unreachable (does not crash or hang).

- [] **WS 623 — Groq API Error Handling**
  > DoD: Simulated Groq API failure (wrong key or rate limit) sends `error` event to frontend with `GROQ_API_ERROR` or `GROQ_RATE_LIMIT` code; error toast shown in UI; input re-enabled.

---
---

# Milestone 7 — Documentation & Handoff
> **Goal:** Ensure the project is fully documented and any developer (or future you) can clone and run it in under 10 minutes.

---

## Atomic Milestone 7.1 — README & Environment
> **Goal:** Write clear setup instructions and finalize the environment template.

- [] **WS 711 — Write README.md**
  > DoD: README includes:
  > - One-paragraph project description
  > - Prerequisites (Python 3.13, uv, Playwright, AWS RDS)
  > - Step-by-step setup instructions (`uv sync`, `.env` setup, Playwright install, `uvicorn` start)
  > - How to open `index.html`
  > - Link to each doc file

- [] **WS 712 — Finalize `.env.example`**
  > DoD: `.env.example` contains all required environment variables with placeholder values and inline comments explaining each one.
