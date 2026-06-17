# AGENTS.md — Competitor Intelligence Agent

**Before any implementation, read all files in `docs/` first.** They contain the authoritative specs for architecture, API, database, MCP, tools, and UI. The build order and current status are tracked in `docs/TASKS.md`.

## Commands

```bash
uv sync                          # install deps (uv, not pip)
uv run uvicorn main:app --reload --port 8000   # start backend
uv run playwright install chromium             # install Playwright (required for scraper)
```

## Key architecture rules

- **WebSocket** (`ws://localhost:8000/ws`) is primary chat transport; REST (`/api`) only for sidebar history
- Agent loop: Groq `tool_choice="auto"` + `TOOLS` list → if `tool_calls` returned, `dispatch_tool()` → append `role="tool"` results → loop until no more tool calls
- Tool errors: return `isError: true` in result dict, NOT exceptions — LLM must see errors to recover
- `scrape-multi-pages` avoids N LLM roundtrips: parallel with `asyncio.gather`, max 20 URLs
- Never `print()` to stdout in tools (corrupts MCP protocol); use `print(..., file=sys.stderr)`
- DB writes happen in agent loop, not in tool functions
- Model: Groq `openai/gpt-oss-120b`, `reasoning_format="parsed"` (no streaming)
- MCP is **in-process stdio** — tools imported directly, NOT a subprocess
- MCP Sampling and Logging protocols are deprecated — do not implement
- `index.html` frontend is vanilla HTML/CSS/JS, opened as `file://` — no build step
