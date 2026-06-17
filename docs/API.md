# API Document
## Competitor Intelligence Agent — v1.0

---

## 1. Overview

The backend exposes two types of interfaces:

| Type | Base | Purpose |
|------|------|---------|
| **WebSocket** | `ws://localhost:8000/ws` | Real-time agent interaction (main chat loop) |
| **REST** | `http://localhost:8000/api` | Conversation history management (sidebar) |

The WebSocket is the **primary interface** — the entire agent loop, tool call trace, and final response flow through it. REST is used only for loading history on page load and sidebar population.

---

## 2. WebSocket API

### 2.1 Connection

```
ws://localhost:8000/ws?session_id={session_id}&conversation_id={conversation_id}
```

| Query param | Required | Description |
|-------------|----------|-------------|
| `session_id` | ✅ | Anonymous UUID stored in browser `localStorage`. Identifies the device/user. |
| `conversation_id` | ❌ | UUID of an existing conversation. Omit to start a new conversation. |

**On connect:**
- If `conversation_id` is provided, the backend loads the existing conversation from MySQL and holds it in memory for the session.
- If omitted, a new `Conversation` row is created in MySQL. The backend sends a `conversation_created` event with the new `conversation_id`.
- The frontend stores the returned `conversation_id` and uses it for all subsequent messages in this chat.

---

### 2.2 Client → Server Messages

All messages are JSON strings sent over the WebSocket.

#### `user_message` — Send a new chat message

```json
{
  "type": "user_message",
  "content": "Did this competitor launch any new offers today?",
  "urls": [
    "https://competitor.com",
    "https://other-competitor.com"
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✅ | Must be `"user_message"` |
| `content` | string | ✅ | The user's natural-language question |
| `urls` | string[] | ❌ | Zero or more competitor URLs attached to this message |

---

### 2.3 Server → Client Events

All events are JSON strings pushed by the backend over the WebSocket. Each has a `type` field.

---

#### `conversation_created` — New conversation was started

Sent once immediately after connection when no `conversation_id` was provided.

```json
{
  "type": "conversation_created",
  "conversation_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
  "title": "New Conversation"
}
```

---

#### `agent_thinking` — Agent loop started

Sent immediately after the user message is received, before any Groq API calls. Triggers the loading indicator in the UI.

```json
{
  "type": "agent_thinking"
}
```

---

#### `tool_event` — An MCP tool was called and completed

Sent once per tool call, in real-time, as each tool finishes. Multiple `tool_event` frames may arrive before `final_response`.

```json
{
  "type": "tool_event",
  "sequence": 0,
  "tool_name": "fetch-website-pages",
  "tool_input": {
    "url": "https://competitor.com"
  },
  "output_summary": "Found 24 pages on competitor.com",
  "called_at": "2026-06-17T12:00:01.123Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"tool_event"` |
| `sequence` | int | 0-indexed order of this tool call in the current agent turn |
| `tool_name` | string | One of: `fetch-website-pages`, `scrape-one-page`, `scrape-multi-pages` |
| `tool_input` | object | The exact arguments passed to the tool |
| `output_summary` | string | Short human-readable summary of what the tool returned |
| `called_at` | ISO 8601 | Timestamp of when the tool was called |

---

#### `final_response` — Agent has finished; full answer ready

Sent once, after the agent loop exits (no more tool calls). Contains the complete answer and reasoning.

```json
{
  "type": "final_response",
  "message_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "content": "Yes, competitor.com launched a 20% off sale on all electronics starting today...",
  "reasoning": "The user wants to know about new offers on competitor.com. I should first crawl the site to find relevant pages, then scrape the offers/promotions pages specifically...",
  "tool_count": 3,
  "created_at": "2026-06-17T12:00:08.456Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"final_response"` |
| `message_id` | string | UUID of the saved `messages` row |
| `content` | string | The agent's final answer (markdown supported) |
| `reasoning` | string | The model's internal reasoning tokens (from `reasoning_format="parsed"`) |
| `tool_count` | int | Total number of tool calls made this turn |
| `created_at` | ISO 8601 | Timestamp |

---

#### `error` — Something went wrong

```json
{
  "type": "error",
  "code": "SCRAPE_FAILED",
  "message": "Failed to fetch https://competitor.com — connection timed out after 30s",
  "recoverable": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"error"` |
| `code` | string | Machine-readable error code (see §2.4) |
| `message` | string | Human-readable description |
| `recoverable` | bool | If `true`, the user can try again; if `false`, session is broken |

---

### 2.4 WebSocket Error Codes

| Code | Meaning |
|------|---------|
| `SCRAPE_FAILED` | httpx and Playwright both failed on a URL |
| `GROQ_API_ERROR` | Groq API returned a non-200 response |
| `GROQ_RATE_LIMIT` | Groq rate limit hit; retry after delay |
| `DB_WRITE_FAILED` | Failed to persist data to MySQL |
| `INVALID_MESSAGE` | Malformed client message (missing required fields) |
| `TOOL_NOT_FOUND` | Agent requested a tool that doesn't exist |
| `SESSION_NOT_FOUND` | Provided `conversation_id` doesn't exist in DB |

---

### 2.5 Full WebSocket Sequence Diagram

```
Browser                          FastAPI Backend                    Groq API
   │                                    │                               │
   │──── WS Connect (session_id) ──────►│                               │
   │◄─── conversation_created ──────────│                               │
   │                                    │                               │
   │──── user_message ─────────────────►│                               │
   │◄─── agent_thinking ────────────────│                               │
   │                                    │──── chat.completions (turn 1) ►│
   │                                    │◄─── tool_calls: [fetch-pages] ─│
   │                                    │                               │
   │                                    │ [execute fetch-website-pages]  │
   │◄─── tool_event (fetch-pages) ──────│                               │
   │                                    │                               │
   │                                    │──── chat.completions (turn 2) ►│
   │                                    │◄─── tool_calls: [scrape-multi] │
   │                                    │                               │
   │                                    │ [execute scrape-multi-pages]   │
   │◄─── tool_event (scrape-multi) ─────│                               │
   │                                    │                               │
   │                                    │──── chat.completions (turn 3) ►│
   │                                    │◄─── content: "Yes, competitor…"│
   │                                    │     reasoning: "I should..."   │
   │                                    │                               │
   │                                    │ [save to MySQL]               │
   │◄─── final_response ────────────────│                               │
   │                                    │                               │
   │  [typewriter reveal begins]        │                               │
```

---

## 3. REST API

All REST endpoints are prefixed with `/api`. Used by the frontend on page load to populate the sidebar and reload conversation history.

---

### 3.1 `GET /api/conversations`

Returns all conversations for a given session, sorted by most recent.

**Query params:**

| Param | Required | Description |
|-------|----------|-------------|
| `session_id` | ✅ | The anonymous browser UUID |

**Response `200 OK`:**

```json
{
  "conversations": [
    {
      "id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
      "title": "Did competitor launch offers today?",
      "updated_at": "2026-06-17T12:00:08Z",
      "message_count": 6
    },
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "title": "New Conversation",
      "updated_at": "2026-06-16T09:15:00Z",
      "message_count": 2
    }
  ]
}
```

---

### 3.2 `GET /api/conversations/{conversation_id}/messages`

Returns the full message history for a specific conversation. Used when the user clicks a conversation in the sidebar.

**Path params:**

| Param | Required | Description |
|-------|----------|-------------|
| `conversation_id` | ✅ | UUID of the conversation |

**Response `200 OK`:**

```json
{
  "conversation_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
  "title": "Did competitor launch offers today?",
  "messages": [
    {
      "id": "aaa111",
      "role": "user",
      "content": "Did this competitor launch any new offers today?",
      "urls_attached": ["https://competitor.com"],
      "created_at": "2026-06-17T12:00:00Z"
    },
    {
      "id": "bbb222",
      "role": "assistant",
      "content": "Yes, competitor.com launched a 20% off sale...",
      "reasoning": "The user wants to know about new offers...",
      "tool_calls": [
        {
          "id": "tc001",
          "tool_name": "fetch-website-pages",
          "tool_input": {"url": "https://competitor.com"},
          "output_summary": "Found 24 pages",
          "sequence_order": 0,
          "called_at": "2026-06-17T12:00:01Z"
        },
        {
          "id": "tc002",
          "tool_name": "scrape-multi-pages",
          "tool_input": {"urls": ["https://competitor.com/offers", "https://competitor.com/sale"]},
          "output_summary": "Scraped 2 pages, 85KB total",
          "sequence_order": 1,
          "called_at": "2026-06-17T12:00:04Z"
        }
      ],
      "created_at": "2026-06-17T12:00:08Z"
    }
  ]
}
```

---

### 3.3 `DELETE /api/conversations/{conversation_id}`

Deletes a conversation and all its messages, tool calls, and scrape results (cascade).

**Response `200 OK`:**

```json
{ "deleted": true }
```

---

### 3.4 `PATCH /api/conversations/{conversation_id}`

Update conversation title (for future manual renaming, already in schema).

**Request body:**

```json
{ "title": "Competitor summer sale check" }
```

**Response `200 OK`:**

```json
{
  "id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
  "title": "Competitor summer sale check",
  "updated_at": "2026-06-17T12:05:00Z"
}
```

---

## 4. CORS Configuration

Since `index.html` opens as `file://` during development, the backend must allow `null` origin (browsers send `Origin: null` for `file://` requests).

```python
# main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

> ⚠️ `"null"` origin is only safe for localhost dev. Remove or restrict before any public-facing deployment.

---

## 5. FastAPI Route Registration

```python
# main.py (structure preview)
from fastapi import FastAPI
from api.routes import router, ws_router

app = FastAPI(title="Competitor Intelligence Agent", version="1.0.0")

app.add_middleware(CORSMiddleware, ...)

app.include_router(router, prefix="/api")        # REST routes
app.include_router(ws_router)                    # WebSocket route (no prefix)

# On startup: create DB tables
@app.on_event("startup")
async def startup():
    from db.connection import init_db
    await init_db()
```

---

## 6. Health Check

```
GET /health
```

**Response `200 OK`:**

```json
{
  "status": "ok",
  "db": "connected",
  "groq": "reachable"
}
```

Used to confirm the backend is up before the frontend attempts a WebSocket connection.
