# MCP Reference Guide
## Competitor Intelligence Agent — v1.0

> **Purpose:** This document is the single authoritative reference for every MCP-related
> decision in this project. Any agent or developer implementing the `mcp/` folder MUST
> read this document before writing a single line of code. Following this guide prevents
> hallucinated APIs, wrong transport patterns, and broken tool schemas.

---

## Table of Contents

1. [What is MCP?](#1-what-is-mcp)
2. [Architecture](#2-architecture)
3. [Connection Lifecycle](#3-connection-lifecycle)
4. [All MCP Primitives](#4-all-mcp-primitives)
5. [Transport Mechanisms](#5-transport-mechanisms)
6. [Python MCP SDK](#6-python-mcp-sdk)
7. [Error Handling & Pagination](#7-error-handling--pagination)
8. [Security](#8-security)
9. [Anti-Patterns](#9-anti-patterns)
10. [Applying MCP to This Project](#10-applying-mcp-to-this-project)
11. [Quick Reference Cheat Sheet](#11-quick-reference-cheat-sheet)

---

## 1. What is MCP?

The **Model Context Protocol (MCP)** is an open standard introduced by Anthropic in
November 2024. It provides a universal, standardized interface — often called the
**"USB-C port for AI"** — that allows AI applications to connect to external data sources,
tools, and systems in a consistent way.

### Problem Solved

Before MCP, every AI application required custom integration code for every data source:
an N×M integration problem (N apps × M data sources). MCP reduces this to **N+M**: build a
server once, connect any MCP-compatible client to it.

### Protocol Foundation: JSON-RPC 2.0

All MCP communication is **JSON-RPC 2.0**. Three message types exist:

**Request** (expects a response):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "fetch-website-pages",
    "arguments": { "url": "https://competitor.com" }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{ "type": "text", "text": "{\"pages_found\": 12, \"pages\": [...]}" }],
    "isError": false
  }
}
```

**Notification** (no response expected):
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/tools/list_changed"
}
```

**Key rules:**
- `id` must be unique per session; can be string or integer
- Requests can be batched EXCEPT the `initialize` request
- Servers MUST NOT send responses to notifications
- Both sides can initiate requests (bidirectional)

### Protocol Versions

MCP uses **date-based version strings**:

| Version | Key Changes |
|---------|-------------|
| `2024-11-05` | Initial release: JSON-RPC, tools, resources, prompts, stdio, HTTP+SSE |
| `2025-03-26` | Streamable HTTP transport, OAuth 2.1, tool annotations |
| `2025-06-18` | Structured tool output (`outputSchema`, `structuredContent`) |
| `2026-07-28` | Sampling and Logging **deprecated**; evolution toward stateless design |

---

## 2. Architecture

MCP uses a **three-tier model**: Host → Client(s) → Server(s).

```
+----------------------------------------------------------------+
|                            HOST                                |
|     (Your FastAPI app + agent loop = the HOST in this project) |
|                                                                |
|  +--------------+   +--------------+   +--------------+       |
|  |   Client 1   |   |   Client 2   |   |   Client 3   |       |
|  +------+-------+   +------+-------+   +------+-------+       |
+─────────+──────────────────+──────────────────+───────────────-+
          |                 |                 |
     [Transport]       [Transport]       [Transport]
          |                 |                 |
   +------+-------+  +------+-------+  +------+-------+
   |  MCP Server  |  |  MCP Server  |  |  MCP Server  |
   |  (scraper)   |  |  (database)  |  |  (external)  |
   +--------------+  +--------------+  +--------------+
```

### Component Roles

**Host:**
- The top-level application users interact with (in this project: the FastAPI app)
- Manages the lifecycle of all MCP client instances
- Enforces security policies and user consent
- Coordinates between the AI model (Groq) and MCP servers
- Routes LLM tool call outputs to the correct MCP client/server

**Client:**
- Lives inside the host; one client per server connection
- Maintains exactly **1:1 stateful session** with a specific MCP server
- Handles the protocol lifecycle: initialization, capability negotiation, message routing
- In this project (v1 design): the agent loop **directly calls tool functions** rather than
  going through a true MCP client — this is the intentional in-process stdio pattern

**Server:**
- A lightweight service exposing capabilities (Tools, Resources, Prompts)
- In this project: runs **in the same Python process as FastAPI** (in-process stdio)
- Does not share state with other servers
- In this project's v1 design: the MCP server is the `mcp/server/scraper_server.py` module
  that registers tools and exposes a `dispatch_tool()` function and a `TOOLS` list

> **This Project's v1 Design Note (from `ARCHITECTURE.md`):**
> The agent and tools run in the same Python process. Tools are imported directly.
> The MCP schema is used for the Groq API tool definition only. A true subprocess MCP
> server (with full JSON-RPC transport) is planned for v2.

---

## 3. Connection Lifecycle

### Phase 1: Initialization (MANDATORY — Must Be First)

No other requests can be sent until this three-step handshake completes.

**Step 1 — Client sends `initialize` request:**
```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "roots": { "listChanged": true }
    },
    "clientInfo": {
      "name": "CompetitorAgentClient",
      "version": "1.0.0"
    }
  }
}
```

**Step 2 — Server responds with its capabilities:**
```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "tools": { "listChanged": false }
    },
    "serverInfo": {
      "name": "ScraperServer",
      "version": "1.0.0"
    }
  }
}
```

**Step 3 — Client sends `notifications/initialized` (REQUIRED):**
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

After step 3, the connection enters the **Operation Phase**.

### Phase 2: Capability Negotiation

Both sides declare only the features they support. **Parties MUST NOT use features the
other hasn't declared.**

**Server capabilities:**
| Capability | Sub-fields | Meaning |
|---|---|---|
| `tools` | `listChanged` | Server exposes tools; notifies on changes if `true` |
| `resources` | `subscribe`, `listChanged` | Server exposes resources; supports subscriptions |
| `prompts` | `listChanged` | Server exposes prompts; notifies on changes |
| `completions` | (none) | Server supports argument auto-complete |
| `experimental` | `{}` | Draft/experimental features |

**Client capabilities:**
| Capability | Sub-fields | Meaning |
|---|---|---|
| `roots` | `listChanged` | Client exposes filesystem boundaries; notifies on changes |
| `sampling` | (none) | DEPRECATED — do not implement |
| `experimental` | `{}` | Draft/experimental features |

### Phase 3: Operation

Full bidirectional JSON-RPC exchange. Either side can initiate requests. The client
typically calls tools, reads resources, and gets prompts. The server may send
notifications (e.g., `notifications/tools/list_changed`).

### Phase 4: Shutdown

- **stdio transport:** Close stdin; server should exit cleanly. Kill after timeout if needed.
- **Streamable HTTP:** Client sends `HTTP DELETE` to the MCP endpoint.
- No explicit `shutdown` JSON-RPC method exists — transport closure is sufficient.
- Servers must clean up resources (close DB connections, etc.) on connection close.

### Version Negotiation

- Client sends highest version it supports in `initialize`
- Server responds with the version it will use (must be <= client's offered version)
- If server cannot support client's version, it returns a JSON-RPC error and closes

---

## 4. All MCP Primitives

### 4A. Tools (Active — Use This)

Tools are **executable functions the LLM can invoke** to take actions in the world.
They are the primary primitive used in this project.

**Tool Definition Structure:**
```json
{
  "name": "fetch-website-pages",
  "description": "Crawl a website to discover all internal page links. Returns a list of {name, url} pairs.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The root URL of the website to crawl (e.g. https://competitor.com). Must include scheme (https://)."
      },
      "max_pages": {
        "type": "integer",
        "description": "Maximum number of pages to return. Defaults to 50.",
        "default": 50
      }
    },
    "required": ["url"]
  },
  "annotations": {
    "readOnlyHint": true,
    "destructiveHint": false,
    "idempotentHint": false,
    "openWorldHint": true
  }
}
```

**Tool Annotations** (advisory hints only — NOT security guarantees):
| Annotation | Default | Meaning |
|---|---|---|
| `readOnlyHint` | `false` | Tool doesn't modify external state |
| `destructiveHint` | `true` | Tool may do irreversible operations |
| `idempotentHint` | `false` | Multiple identical calls = same effect |
| `openWorldHint` | `true` | Tool interacts with external systems |
| `title` | none | Human-readable display name for UI |

**Tool Discovery (client to server):**
```json
{ "method": "tools/list", "params": {} }
```
Response:
```json
{
  "result": {
    "tools": [{ "name": "fetch-website-pages" }],
    "nextCursor": null
  }
}
```

**Tool Invocation:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "fetch-website-pages",
    "arguments": { "url": "https://competitor.com", "max_pages": 30 }
  }
}
```

**Successful Tool Response:**
```json
{
  "result": {
    "content": [
      { "type": "text", "text": "{\"url\": \"...\", \"pages_found\": 12, \"pages\": [...]}" }
    ],
    "isError": false
  }
}
```

**Failed Tool Response (tool executed but encountered an error):**
```json
{
  "result": {
    "content": [
      { "type": "text", "text": "Error: UNREACHABLE — could not connect to https://competitor.com" }
    ],
    "isError": true
  }
}
```

> CRITICAL: Tool execution errors use `isError: true` in the **result** object —
> NOT JSON-RPC error codes. This allows the LLM to see the error in its context window
> and potentially recover or retry. See Section 7 for the full distinction.

**Structured Output (new in 2025-06-18):**
Tools can optionally include `structuredContent` alongside the text content:
```json
{
  "result": {
    "content": [{ "type": "text", "text": "Found 12 pages" }],
    "structuredContent": { "pages_found": 12, "pages": [] },
    "isError": false
  }
}
```

---

### 4B. Resources (Active — Available But Not Used in v1)

Resources are **read-only data** exposed by servers to clients/LLMs.

**Resource Object:**
```json
{
  "uri": "scrape://results/latest",
  "name": "Latest Scrape Results",
  "description": "Most recent scraping results stored in database",
  "mimeType": "application/json",
  "size": 4096
}
```

**URI Format:** `[scheme]://[host]/[path]` — schemes are custom-defined by the server.

**Resource Templates (RFC 6570 URI Templates):**
```json
{
  "uriTemplate": "scrape://results/{conversation_id}",
  "name": "Scrape Results by Conversation",
  "mimeType": "application/json"
}
```

**Discovery:**
```
Client → resources/list              (lists concrete resources)
Client → resources/templates/list    (lists URI templates)
```

**Reading:**
```json
{ "method": "resources/read", "params": { "uri": "scrape://results/latest" } }
```
Response:
```json
{
  "result": {
    "contents": [
      {
        "uri": "scrape://results/latest",
        "mimeType": "application/json",
        "text": "{\"results\": []}"
      }
    ]
  }
}
```

Content uses `text` (string) for text data or `blob` (base64-encoded) for binary data.

**Resource Subscriptions (requires `resources.subscribe` capability):**
```
resources/subscribe   → subscribe to a URI
resources/unsubscribe → stop subscription
notifications/resources/updated → server notifies client when resource changes
```

---

### 4C. Prompts (Active — Available But Not Used in v1)

Prompts are **user-controlled reusable templates**. Unlike tools (model-controlled), prompts
are explicitly selected by users (e.g., slash commands in a UI).

**Prompt Definition:**
```json
{
  "name": "analyze_competitor",
  "description": "Generate a structured competitor analysis prompt",
  "arguments": [
    { "name": "competitor_name", "description": "Name of the competitor", "required": true },
    { "name": "focus",           "description": "Focus area (pricing/offers/all)", "required": false }
  ]
}
```

**Getting a Prompt:**
```json
{
  "method": "prompts/get",
  "params": {
    "name": "analyze_competitor",
    "arguments": { "competitor_name": "Acme Corp", "focus": "pricing" }
  }
}
```
Response (structured messages ready for LLM injection):
```json
{
  "result": {
    "description": "Competitor analysis prompt",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "Analyze Acme Corp's pricing strategy. Focus on: pricing."
        }
      }
    ]
  }
}
```

---

### 4D. Sampling — DEPRECATED (Do NOT Implement)

**Status: DEPRECATED as of protocol version 2026-07-28.**

Sampling allowed MCP servers to request LLM completions from the host client.
**Do not implement `sampling/createMessage` in any new code.** Servers that need LLM
reasoning should integrate directly with the LLM API instead.

---

### 4E. Roots (Active — Client to Server Filesystem Boundaries)

Roots define filesystem boundaries that the **client exposes to servers**. Servers request
roots to know which directories they are allowed to access.

**Client declares capability:** `{ "roots": { "listChanged": true } }`

**Server requests roots (server sends, client responds):**
```json
{ "method": "roots/list" }
```
Response:
```json
{
  "result": {
    "roots": [
      { "uri": "file:///home/user/project", "name": "Project Root" }
    ]
  }
}
```

**When client's workspace changes:**
```
Client sends: notifications/roots/list_changed
Server re-fetches: roots/list
```

---

### 4F. Logging — DEPRECATED (Use stderr Instead)

**Status: DEPRECATED as of protocol version 2026-07-28.**

Do NOT use the MCP logging protocol (`notifications/message`, `logging/setLevel`).

**Correct approach for this project (stdio transport):**
```python
import sys
print("Debug message", file=sys.stderr)  # Correct — goes to stderr
# NEVER: print("Debug message")          # WRONG — corrupts stdout protocol stream
```

---

### 4G. Progress Notifications (Active)

For long-running tool operations, servers can send progress updates back to the client.

**Client includes `progressToken` in the tool call request:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "scrape-multi-pages",
    "arguments": { "urls": ["..."] },
    "_meta": { "progressToken": "scrape-batch-001" }
  }
}
```

**Server sends progress notifications during execution:**
```json
{
  "method": "notifications/progress",
  "params": {
    "progressToken": "scrape-batch-001",
    "progress": 2,
    "total": 3,
    "message": "Scraped 2 of 3 pages..."
  }
}
```

Rules: `progress` must monotonically increase; `progressToken` must be unique per active request.

---

### 4H. Completions (Active — Argument Autocomplete)

Servers declare `completions` capability. Used for UI autocomplete of prompt arguments
or resource template parameters. Not used in v1 of this project.

```json
{
  "method": "completion/complete",
  "params": {
    "ref": { "type": "ref/prompt", "name": "analyze_competitor" },
    "argument": { "name": "focus", "value": "pr" }
  }
}
```
Response:
```json
{
  "result": {
    "completion": {
      "values": ["pricing", "promotions", "products"],
      "total": 3,
      "hasMore": false
    }
  }
}
```

`ref.type` is either `"ref/prompt"` or `"ref/resource"`.

---

### 4I. Elicitation (Active — Server Requests User Input)

Allows servers to request additional information from users during operation. Not used in v1.

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "This site requires authentication. Please provide credentials.",
    "requestedSchema": {
      "type": "object",
      "properties": {
        "username": { "type": "string" },
        "password": { "type": "string" }
      },
      "required": ["username", "password"]
    }
  }
}
```
Client response:
```json
{
  "result": {
    "action": "accept",
    "content": { "username": "...", "password": "..." }
  }
}
```

`action` is one of: `"accept"` | `"decline"` | `"cancel"`.

---

## 5. Transport Mechanisms

### 5A. stdio Transport — Used in This Project

**Standard for:** Local, single-process deployments. This is what this project uses in v1.

**How it works:**
- Host launches server as a child subprocess (OR runs tools in-process, as in this project's v1)
- Communication via **stdin/stdout** of the process
- Messages are **newline-delimited JSON** — each complete JSON-RPC message is exactly one line
- Server uses **stderr** for all diagnostic output (never stdout)

> CRITICAL RULE: NEVER write anything to stdout that is not a valid MCP JSON-RPC message.
> Any `print()`, framework startup banner, warning, or debug output written to stdout
> will corrupt the protocol stream and cause catastrophic, hard-to-debug failures.
> Use `sys.stderr` for ALL non-protocol output.

**Python server — FastMCP approach:**
```python
from mcp.server.fastmcp import FastMCP
import sys

mcp = FastMCP("ScraperServer")

@mcp.tool()
async def fetch_website_pages(url: str, max_pages: int = 50) -> dict:
    """Crawl a website to discover all internal page links."""
    # stdout is owned by MCP protocol — no print() calls here
    print("Fetching...", file=sys.stderr)  # OK — stderr only
    return {"url": url, "pages_found": 0, "pages": []}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**Python server — Low-level Server approach:**
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
import asyncio
import json

server = Server("ScraperServer")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="fetch-website-pages",
            description="Crawl a website to discover all internal page links.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url":       {"type": "string"},
                    "max_pages": {"type": "integer", "default": 50}
                },
                "required": ["url"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "fetch-website-pages":
        result = await _fetch_website_pages(arguments["url"], arguments.get("max_pages", 50))
        return [types.TextContent(type="text", text=json.dumps(result))]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

**Python client — connecting to a subprocess server:**
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["mcp/server/scraper_server.py"],
    env={"PYTHONPATH": "."}
)

async def use_mcp_client():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()     # Mandatory first
            tools       = await session.list_tools()
            result      = await session.call_tool(
                "fetch-website-pages",
                {"url": "https://competitor.com"}
            )
            print(result.content[0].text, file=sys.stderr)
```

---

### 5B. Streamable HTTP Transport — (For Reference / v2)

**Standard for:** Remote/network deployments (multiple clients, cloud hosting).

**Architecture:**
- Server runs as an independent HTTP service
- **Single endpoint** (e.g., `/mcp`) handles all protocol traffic
- Supports multiple simultaneous clients

**HTTP methods on the `/mcp` endpoint:**
| Method | Purpose |
|---|---|
| `POST` | Client sends JSON-RPC request or notification |
| `GET` | Client opens SSE stream for server-initiated messages |
| `DELETE` | Client terminates session |

**Session management:** Server may return `Mcp-Session-Id` header in the initialize response.
Client must include this header in all subsequent requests.

**POST response format:** Server can respond with either:
- `Content-Type: application/json` — single JSON-RPC response
- `Content-Type: text/event-stream` — SSE stream of multiple messages

**Security requirements (HTTP transport only):**
- Servers MUST validate the `Origin` header (prevents DNS rebinding attacks)
- Authentication via OAuth 2.1 (Bearer tokens in `Authorization` header)
- TLS required for production

**Python (FastMCP) Streamable HTTP:**
```python
mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

---

### 5C. Legacy HTTP+SSE Transport — DEPRECATED

The original remote transport from `2024-11-05`. Uses two separate endpoints:
- `GET /sse` — SSE stream for server to client messages
- `POST /messages` — client to server messages

**Do not implement this.** Use Streamable HTTP instead for remote deployments.

---

## 6. Python MCP SDK

### Installation

```bash
# With uv (this project's package manager) — RECOMMENDED
uv add mcp

# With pip
pip install mcp
```

### 6A. FastMCP — High-Level API (Recommended)

`FastMCP` is the high-level, decorator-based API. Use this for all new servers.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="ScraperServer",
    version="1.0.0"
)
```

**Tool registration:**
```python
@mcp.tool()
async def scrape_one_page(url: str, use_playwright: bool = False) -> dict:
    """
    Fetch the full HTML content of a single URL.
    Returns the page's raw HTML so you can analyse its content.
    """
    # Function docstring  → tool description (shown to LLM)
    # Type hints          → inputSchema (automatically generated)
    result = await _do_scrape(url, use_playwright)
    return result
```

**Resource registration:**
```python
@mcp.resource("config://scraper-settings")
def get_settings() -> str:
    """Return scraper configuration."""
    return json.dumps({"max_retries": 3, "timeout": 30})

# Dynamic resource template
@mcp.resource("scrape://results/{conversation_id}")
def get_scrape_results(conversation_id: str) -> str:
    """Get scrape results for a conversation."""
    results = db.get_scrape_results(conversation_id)
    return json.dumps(results)
```

**Prompt registration:**
```python
@mcp.prompt()
def analyze_competitor(competitor_name: str, focus: str = "all") -> str:
    """Generate a competitor analysis prompt."""
    return f"Analyze {competitor_name}'s website. Focus area: {focus}."
```

**Starting the server:**
```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
    # For HTTP: mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

**Raising tool errors correctly (FastMCP):**
```python
from mcp.types import McpError
from mcp import ErrorCode

@mcp.tool()
async def scrape_one_page(url: str) -> dict:
    """Fetch the full HTML of a single URL."""
    try:
        result = await _do_scrape(url)
        return result
    except Exception as e:
        # This becomes isError: true in the tool response — LLM sees the error and can recover
        raise McpError(ErrorCode.InternalError, f"SCRAPE_FAILED: {str(e)}")
```

---

### 6B. Low-Level Server API

Use when you need full control over the MCP protocol — required for the `TOOLS` list
and `dispatch_tool()` pattern used in this project's `ARCHITECTURE.md`.

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
import asyncio, json

server = Server("ScraperServer")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Called when client sends tools/list."""
    return [
        types.Tool(
            name="fetch-website-pages",
            description="Crawl a website to discover all internal page links.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url":       {"type": "string"},
                    "max_pages": {"type": "integer", "default": 50}
                },
                "required": ["url"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Called when client sends tools/call."""
    try:
        result = await dispatch_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result))]
    except Exception as e:
        # Return error content — the MCP SDK marks this as isError: true
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

async def run_server():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
```

**Key `mcp.types` classes:**
```python
import mcp.types as types

types.Tool              # Tool definition (name, description, inputSchema)
types.TextContent       # types.TextContent(type="text", text="...")
types.ImageContent      # types.ImageContent(type="image", data="base64...", mimeType="image/png")
types.Resource          # Resource definition
types.Prompt            # Prompt definition
types.PromptArgument    # Prompt argument definition
types.CallToolResult    # Tool call result wrapper
```

---

### 6C. ClientSession API

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async with stdio_client(StdioServerParameters(command="python", args=["server.py"])) as (r, w):
    async with ClientSession(r, w) as session:

        # Mandatory first call — SDK also sends notifications/initialized internally
        init = await session.initialize()
        # init.serverInfo.name      → server name
        # init.capabilities.tools   → tools capability info

        # Discover tools
        tools_result = await session.list_tools()
        # tools_result.tools        → List[types.Tool]
        # tools_result.nextCursor   → Optional[str] for pagination

        # Call a tool
        result = await session.call_tool("fetch-website-pages", {"url": "https://..."})
        # result.content   → List[TextContent | ImageContent | ...]
        # result.isError   → bool

        # List resources
        resources = await session.list_resources()

        # Read a resource
        content = await session.read_resource("config://settings")

        # Get a prompt
        prompt = await session.get_prompt("analyze_competitor", {"competitor_name": "Acme"})

        # Subscribe to resource updates (only if server declared resources.subscribe)
        await session.subscribe_resource("scrape://results/latest")
```

---

## 7. Error Handling & Pagination

### 7A. Protocol Errors vs Tool Errors — CRITICAL DISTINCTION

| Error Type | When Used | Format | LLM Sees It? |
|---|---|---|---|
| **JSON-RPC Error** | Protocol failures (bad JSON, unknown method, invalid params) | `{"error": {"code": -32601, "message": "..."}}` | No — breaks the loop |
| **Tool Error** (`isError: true`) | Tool ran but encountered a problem (scrape failed, site unreachable) | `{"result": {"content": [...], "isError": true}}` | Yes — LLM can recover |

**Standard JSON-RPC error codes:**
| Code | Meaning |
|---|---|
| `-32700` | Parse error (invalid JSON) |
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| `-32000` to `-32099` | Server-defined errors |

**Why this distinction matters:** When a scraping tool fails (network error, anti-bot block),
the LLM needs to see the error message so it can report to the user or try a different
approach. If you use a JSON-RPC error code instead, the error goes to the agent loop as an
exception — the LLM never sees it and the agent loop may crash.

**Correct tool error pattern:**
```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "scrape-one-page":
        try:
            result = await scrape_one_page(arguments["url"])
            return [types.TextContent(type="text", text=json.dumps(result))]
        except ScrapingError as e:
            # Correct: return error content — LLM sees this as a tool result with isError=True
            return [types.TextContent(type="text", text=f"SCRAPE_FAILED: {str(e)}")]
```

### 7B. Cursor-Based Pagination

All list operations support pagination. Treat cursors as **opaque tokens** — never parse,
decode, or modify them.

```python
# Paginate through all tools
all_tools = []
cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    result = await session.list_tools(**params)
    all_tools.extend(result.tools)
    if not result.nextCursor:
        break
    cursor = result.nextCursor
```

Operations that support pagination:
`tools/list`, `resources/list`, `resources/templates/list`, `prompts/list`.

---

## 8. Security

### 8A. Key Threat Model

| Threat | Description | Mitigation |
|---|---|---|
| **Prompt Injection** | Malicious instructions in scraped web content that the LLM executes | Treat tool output as data, not instructions |
| **Tool Poisoning** | Malicious instructions embedded in tool descriptions from an untrusted server | Statically validate tool metadata before injecting into LLM context |
| **Confused Deputy** | Exploiting the server's elevated access through crafted tool arguments | Validate all inputs server-side; enforce path restrictions |
| **Cross-Server Contamination** | One MCP server overriding another server's tools | Server isolation; unique tool namespaces |

### 8B. What Servers Must Do

- Validate ALL inputs (treat client-provided arguments as untrusted)
- Sanitize file paths to prevent path traversal attacks
- Rate-limit tool calls to prevent abuse
- Implement resource limits (memory, concurrent requests)
- Log all tool calls for audit purposes

### 8C. What Clients/Hosts Must Do

- Require user consent before executing tools with side effects
- Validate tool schemas from servers before injecting into LLM context
- **Tool annotations (`readOnlyHint`, `destructiveHint`, etc.) are advisory HINTS —**
  **never use them as security enforcement**
- Isolate MCP server processes from each other

### 8D. Authentication

| Transport | Authentication Method |
|---|---|
| **stdio** | Credentials retrieved from environment variables (e.g., `API_KEY` in `.env`) |
| **Streamable HTTP** | OAuth 2.1 with mandatory PKCE; Bearer tokens in `Authorization` header |

For this project (stdio, local development): API keys are passed via environment variables
(`.env` file loaded by `python-dotenv`). No OAuth needed.

---

## 9. Anti-Patterns

These are wrong patterns that will break the implementation. Avoid all of them.

### AP-1: Writing to stdout in a stdio server

```python
# WRONG — corrupts the MCP protocol stream on stdout
print("Server starting...")
print(f"Fetching {url}...")

# CORRECT — stderr is safe for all diagnostic output
import sys
print("Server starting...", file=sys.stderr)
print(f"Fetching {url}...", file=sys.stderr)
```

This is the #1 most common stdio MCP bug. Any non-MCP output to stdout — including
Python's startup warnings, uvicorn logs, or a single debug `print()` — will corrupt
the entire JSON-RPC protocol stream and cause mysterious parsing failures.

### AP-2: Using JSON-RPC error codes for tool execution failures

```python
# WRONG — LLM never sees this; agent loop receives an exception
raise Exception("Site unreachable")

# CORRECT — LLM sees "SCRAPE_FAILED: Site unreachable" and can recover
return [types.TextContent(type="text", text="SCRAPE_FAILED: Site unreachable")]
```

### AP-3: Sending requests before initialization completes

```python
# WRONG — will be rejected or cause undefined behavior
tools = await session.list_tools()
init  = await session.initialize()  # Too late!

# CORRECT — always initialize first
init  = await session.initialize()
tools = await session.list_tools()
```

### AP-4: Implementing deprecated Sampling or Logging

```python
# WRONG — Sampling is deprecated (2026-07-28), do not implement
@server.create_message()
async def handle_sampling(params): ...

# WRONG — Logging protocol is deprecated
await session.set_log_level("debug")

# CORRECT — log to stderr; integrate directly with LLM API
print("Debug info", file=sys.stderr)
```

### AP-5: Trusting tool annotation hints as security enforcement

```python
# WRONG — annotations are advisory hints from potentially untrusted servers
if tool.annotations.readOnlyHint:
    allow_without_confirmation()  # Server could lie!

# CORRECT — validate independently; require confirmation for sensitive operations
if requires_user_confirmation(tool.name):
    await ask_user_for_confirmation()
```

### AP-6: Calling capabilities the other side hasn't declared

```python
# WRONG — calling subscribe without checking server capability first
await session.subscribe_resource("scrape://results/latest")

# CORRECT — check capability first
if init.capabilities.resources and init.capabilities.resources.subscribe:
    await session.subscribe_resource("scrape://results/latest")
```

### AP-7: Assuming all tools/resources fit in one response (forgetting pagination)

```python
# WRONG — may miss tools if server paginates results
result = await session.list_tools()
tools  = result.tools  # Might only be page 1!

# CORRECT — paginate through all results
tools, cursor = [], None
while True:
    r = await session.list_tools(**({"cursor": cursor} if cursor else {}))
    tools.extend(r.tools)
    if not r.nextCursor:
        break
    cursor = r.nextCursor
```

### AP-8: Parsing or modifying cursor tokens

```python
# WRONG — cursors are opaque tokens; never decode them
import base64
page = json.loads(base64.b64decode(next_cursor))  # Will break when format changes

# CORRECT — pass cursors through as-is
cursor = result.nextCursor
if cursor:
    next_result = await session.list_tools(cursor=cursor)
```

### AP-9: Running `mcp.run()` alongside FastAPI uvicorn in the same process

```python
# WRONG — mcp.run() blocks; cannot run alongside FastAPI uvicorn this way
mcp.run(transport="stdio")   # Blocks forever
uvicorn.run(app, port=8000)  # Never reached

# CORRECT for this project — import tool functions directly (in-process pattern)
from mcp.tools.fetch_pages import fetch_website_pages
from mcp.tools.scrape_one  import scrape_one_page
from mcp.tools.scrape_multi import scrape_multi_pages
```

### AP-10: Forgetting `notifications/initialized` after initialize response

```python
# WRONG — skipping the initialized notification leaves the session in limbo
# (manually calling raw JSON-RPC without going through ClientSession)

# CORRECT — use the Python ClientSession, which handles this automatically
init  = await session.initialize()  # SDK sends notifications/initialized internally
tools = await session.list_tools()  # Now safe
```

---

## 10. Applying MCP to This Project

### 10.1 Tool Mapping

The three project tools map to MCP tool primitives as follows:

| Project Tool | MCP `name` field | Primary Use | Tool Chain Position |
|---|---|---|---|
| `fetch-website-pages` | `fetch-website-pages` | Discover site structure | Always first |
| `scrape-one-page` | `scrape-one-page` | Single page HTML | When only 1 page needed |
| `scrape-multi-pages` | `scrape-multi-pages` | Parallel batch scraping | When 2+ pages needed |

**Full input/output schemas** (must match `docs/TOOLS.md` exactly):

```
fetch-website-pages
  Input:  { url: string (required), max_pages: integer (default: 50) }
  Output: { url: string, pages_found: integer, pages: [{name: string, url: string}] }
  Error:  { error: "UNREACHABLE" | "NO_LINKS", message: string }

scrape-one-page
  Input:  { url: string (required), use_playwright: boolean (default: false) }
  Output: { url: string, page_title: string, html: string, size_bytes: integer,
            rendered_with: "httpx" | "playwright", scraped_at: string (ISO 8601) }
  Error:  { error: "SCRAPE_FAILED", url: string, message: string }

scrape-multi-pages
  Input:  { urls: string[] (required, max 20), use_playwright_for_all: boolean (default: false) }
  Output: { total_requested: integer, total_succeeded: integer, total_failed: integer,
            results: [{url, page_title, html, size_bytes, rendered_with, scraped_at, error}] }
```

---

### 10.2 `mcp/server/scraper_server.py` — Complete Implementation

This is the recommended implementation for this project's v1 in-process design.
It implements the `TOOLS` list + `dispatch_tool()` pattern from `ARCHITECTURE.md`:

```python
# mcp/server/scraper_server.py

"""
MCP Tool Registry for the Competitor Intelligence Agent.

Exports:
  TOOLS           - list of tool definitions in OpenAI/Groq function-calling format
                    passed to every Groq API call as the `tools` parameter
  TOOL_DISPATCH   - dict mapping tool names to async Python functions
  dispatch_tool() - unified async function called by the agent loop

v1 Design: Agent and tools run in the same Python process as FastAPI.
Tools are called directly via dispatch_tool() — no JSON-RPC transport.
The MCP inputSchema/description is used for Groq API tool definitions only.
A true subprocess MCP server is planned for v2.
"""

import json
import sys
from typing import Any

from mcp.tools.fetch_pages import fetch_website_pages
from mcp.tools.scrape_one  import scrape_one_page
from mcp.tools.scrape_multi import scrape_multi_pages


# ─────────────────────────────────────────────────────────────────
# TOOLS — Groq/OpenAI function-calling format
# Passed as the `tools` parameter on every Groq API call.
# ─────────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "fetch-website-pages",
            "description": (
                "Crawl a website to discover all internal page links. "
                "Returns a list of {name, url} pairs representing every navigable page found. "
                "ALWAYS call this first when given a new URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The root URL of the website to crawl (e.g. https://competitor.com). Must include scheme (https://)."
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Maximum number of pages to return. Defaults to 50.",
                        "default": 50
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape-one-page",
            "description": (
                "Fetch the full HTML content of a single URL. "
                "Returns the page's raw HTML so you can analyse its content. "
                "Use when only one specific page is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The exact URL to scrape (e.g. https://competitor.com/offers)"
                    },
                    "use_playwright": {
                        "type": "boolean",
                        "description": "Force Playwright (headless browser) instead of httpx. Use for JavaScript-rendered pages. Defaults to false (auto-fallback).",
                        "default": False
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape-multi-pages",
            "description": (
                "Fetch the full HTML of multiple URLs in parallel. "
                "More efficient than calling scrape-one-page multiple times. "
                "PREFER this when you need 2 or more pages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to scrape in parallel (max 20 per call)",
                        "maxItems": 20
                    },
                    "use_playwright_for_all": {
                        "type": "boolean",
                        "description": "Force Playwright for all URLs. Use when you know the site is JS-rendered.",
                        "default": False
                    }
                },
                "required": ["urls"]
            }
        }
    }
]


# ─────────────────────────────────────────────────────────────────
# TOOL_DISPATCH — Maps tool name to async Python function
# ─────────────────────────────────────────────────────────────────

TOOL_DISPATCH: dict[str, Any] = {
    "fetch-website-pages": fetch_website_pages,
    "scrape-one-page":     scrape_one_page,
    "scrape-multi-pages":  scrape_multi_pages,
}


# ─────────────────────────────────────────────────────────────────
# dispatch_tool() — Entry point called by the agent loop
# ─────────────────────────────────────────────────────────────────

async def dispatch_tool(name: str, arguments: dict) -> dict:
    """
    Dispatch a tool call by name to its implementing function.

    Args:
        name:      Tool name as returned by Groq (e.g. "fetch-website-pages")
        arguments: Arguments dict from the Groq tool_call object

    Returns:
        A dict result from the tool function.
        Error dicts include an "error" key with the error code string.

    Raises:
        ValueError: If the tool name is not recognized.
    """
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        raise ValueError(
            f"Unknown tool: '{name}'. "
            f"Available tools: {list(TOOL_DISPATCH.keys())}"
        )

    print(f"[MCP] Dispatching: {name} args={json.dumps(arguments)}", file=sys.stderr)
    result = await fn(**arguments)
    print(f"[MCP] Completed:   {name}", file=sys.stderr)
    return result
```

---

### 10.3 In-Process Integration with FastAPI and Groq

The v1 design runs tools **in-process** with FastAPI. The agent loop:
1. Receives `tool_calls` from Groq (OpenAI format: `tool_calls[].function.name` + `.arguments`)
2. Calls `dispatch_tool(name, arguments)` directly
3. Appends the result as a `role="tool"` message
4. Sends the updated messages back to Groq in the next call

```python
# agent/agent.py — simplified agent loop showing MCP integration

import json
from mcp.server.scraper_server import TOOLS, dispatch_tool

async def run_agent_turn(messages: list[dict], on_tool_event, db_session) -> dict:
    """
    Run one full agent turn: loop until Groq returns no more tool calls.
    Returns: {"content": str, "reasoning": str, "tool_calls": list}
    """
    current_messages = list(messages)
    all_tool_calls   = []

    while True:
        # Call Groq with TOOLS list (MCP schemas in OpenAI format)
        response = await groq_chat(
            messages=current_messages,
            tools=TOOLS,            # <-- The MCP TOOLS list goes here
        )

        # No more tool calls — agent is done
        if not response["tool_calls"]:
            return {
                "content":    response["content"],
                "reasoning":  response["reasoning"],
                "tool_calls": all_tool_calls
            }

        # Append assistant turn (with tool_calls) to message history
        current_messages.append({
            "role":       "assistant",
            "tool_calls": response["tool_calls"]
        })

        # Execute each tool call via MCP dispatcher
        for tool_call in response["tool_calls"]:
            name      = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"])
            tool_id   = tool_call["id"]

            try:
                result   = await dispatch_tool(name, arguments)
                output   = json.dumps(result)
                is_error = "error" in result
            except ValueError as e:
                output   = str(e)
                is_error = True

            # Stream tool event to UI via WebSocket callback
            await on_tool_event(
                tool_name=name,
                tool_input=arguments,
                output_summary=output[:500],
                is_error=is_error
            )

            all_tool_calls.append({
                "tool_call_id": tool_id,
                "name":         name,
                "arguments":    arguments,
                "result":       result if not is_error else {"error": output},
                "is_error":     is_error
            })

            # Append tool result as role="tool" (Groq/OpenAI format)
            current_messages.append({
                "role":         "tool",
                "tool_call_id": tool_id,
                "content":      output
            })
        # Loop — send updated messages back to Groq
```

---

### 10.4 Handling Tool Errors in the Agent Loop

When a tool call returns an error dict (e.g., site unreachable), the error is serialized
to JSON and returned as the `role="tool"` message. The Groq LLM receives this in its next
call and can:

1. **Report the error to the user:** "I was unable to access that website."
2. **Try a different approach:** Use Playwright instead of httpx
3. **Skip the failed URL:** Continue with successfully scraped pages
4. **Ask for clarification:** Request a different URL

```python
# A failed scrape tool result looks like:
failed_result = {
    "error":   "SCRAPE_FAILED",
    "url":     "https://protected-site.com",
    "message": "Playwright timeout after 60s"
}

# This gets serialized and sent to Groq as:
{
    "role":         "tool",
    "tool_call_id": "call_abc123",
    "content":      '{"error": "SCRAPE_FAILED", "url": "...", "message": "..."}'
}

# Groq sees the full error in context and reasons about it.
# The agent loop does NOT crash because isError: true is a valid tool result.
```

---

### 10.5 Asyncio Considerations

This project is fully async: FastAPI + asyncio, MCP tool functions are async, Groq SDK is
async, SQLAlchemy is async. Follow these rules:

**All tool functions must be `async def`:**
```python
# mcp/tools/fetch_pages.py
async def fetch_website_pages(url: str, max_pages: int = 50) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True, timeout=30)
```

**Use `asyncio.gather()` for parallel scraping:**
```python
# mcp/tools/scrape_multi.py
async def scrape_multi_pages(urls: list[str], use_playwright_for_all: bool = False) -> dict:
    tasks   = [scrape_one_page(url, use_playwright_for_all) for url in urls[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Handle exceptions: isinstance(r, Exception) -> error entry in results
```

**Playwright async API:**
```python
from playwright.async_api import async_playwright

async def playwright_scrape(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60000)
        html    = await page.content()
        await browser.close()
        return html
```

**No blocking calls in async functions:**
- Never use `requests` (sync library) — use `httpx.AsyncClient`
- Never use `time.sleep()` — use `await asyncio.sleep()`
- Never use synchronous file I/O in an async context — use `aiofiles` if needed

**Database access:** Do NOT call the database from tool functions. Tool functions are pure
scraping utilities. Database writes happen in `agent.py` after tool calls complete, using
`db/repository.py`.

---

## 11. Quick Reference Cheat Sheet

### JSON-RPC Method Names

| Primitive | Client sends | Server sends (notifications) |
|---|---|---|
| **Init** | `initialize` | `notifications/initialized` |
| **Tools** | `tools/list`, `tools/call` | `notifications/tools/list_changed` |
| **Resources** | `resources/list`, `resources/templates/list`, `resources/read`, `resources/subscribe`, `resources/unsubscribe` | `notifications/resources/list_changed`, `notifications/resources/updated` |
| **Prompts** | `prompts/list`, `prompts/get` | `notifications/prompts/list_changed` |
| **Roots** | `roots/list` *(server requests, client responds)* | `notifications/roots/list_changed` *(client sends)* |
| **Completions** | `completion/complete` | — |
| **Elicitation** | *(server initiates via `elicitation/create`)* | — |
| **Progress** | — | `notifications/progress` |
| **Logging** | `logging/setLevel` DEPRECATED | `notifications/message` DEPRECATED |
| **Sampling** | `sampling/createMessage` DEPRECATED (server initiates) | — |

### Capability Flags

| Side | Flag | Sub-flags | Purpose |
|---|---|---|---|
| Server | `tools` | `listChanged` | Exposes tools; notifies changes |
| Server | `resources` | `subscribe`, `listChanged` | Exposes resources |
| Server | `prompts` | `listChanged` | Exposes prompts |
| Server | `completions` | — | Supports autocomplete |
| Client | `roots` | `listChanged` | Exposes filesystem boundaries |
| Client | `sampling` | — | DEPRECATED |

### Python SDK Import Cheat Sheet

```python
# Server — FastMCP (recommended)
from mcp.server.fastmcp import FastMCP

# Server — Low-level
from mcp.server       import Server
from mcp.server.stdio import stdio_server

# Types
import mcp.types as types
# types.Tool, types.TextContent, types.ImageContent
# types.Resource, types.Prompt, types.PromptArgument

# Client
from mcp                import ClientSession, StdioServerParameters
from mcp.client.stdio   import stdio_client

# Errors
from mcp.types import McpError
from mcp       import ErrorCode
# ErrorCode.InvalidParams, ErrorCode.InternalError, ErrorCode.MethodNotFound
```

### Error Code Table

| Code | Meaning |
|---|---|
| `-32700` | Parse error — invalid JSON received |
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| Tool errors | Use `isError: true` in result — LLM sees and can recover |

### Transport Comparison

| Feature | stdio | Streamable HTTP | Legacy HTTP+SSE |
|---|---|---|---|
| **Use case** | Local, in-process | Remote, multi-client | Remote (deprecated) |
| **This project** | v1 design | v2 plan | Do not use |
| **Message format** | Newline-delimited JSON | HTTP POST + SSE | Separate endpoints |
| **Auth** | Environment variables | OAuth 2.1 + PKCE | OAuth 2.1 + PKCE |
| **Stdout rule** | NEVER write non-MCP to stdout | N/A | N/A |
| **Sessions** | 1 process = 1 session | `Mcp-Session-Id` header | Per SSE stream |
| **Server startup** | `mcp.run(transport="stdio")` | `mcp.run(transport="streamable-http")` | — |

### Protocol Version History

| Version | Key Change |
|---|---|
| `2024-11-05` | Initial: tools, resources, prompts, stdio, HTTP+SSE |
| `2025-03-26` | Streamable HTTP, OAuth 2.1, tool annotations |
| `2025-06-18` | `outputSchema`, `structuredContent` for tools |
| `2026-07-28` | Sampling DEPRECATED, Logging DEPRECATED |

---

*Last updated: 2026-06-17 | MCP spec through version 2026-07-28*

*See also: [PRD](./PRD.md) · [Architecture](./ARCHITECTURE.md) · [Tools](./TOOLS.md) · [Tasks](./TASKS.md)*
