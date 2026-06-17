# Tools Document
## Competitor Intelligence Agent — v1.0

---

## 1. Overview

The agent has access to three MCP tools. All tools are implemented as Python async functions registered with the MCP server (`mcp/server/scraper_server.py`) and exposed to the Groq LLM as function-calling tool definitions.

### Tool Summary

| Tool | Purpose | Primary use |
|------|---------|------------|
| `fetch-website-pages` | Discover all navigable pages of a website | Always first — gives the agent a map of the site |
| `scrape-one-page` | Fetch and return the full HTML of a single URL | When only one specific page is needed |
| `scrape-multi-pages` | Batch-fetch multiple URLs in parallel | When the agent needs content from several pages at once |

---

### Recommended Tool Chain

```
User attaches URL → agent calls fetch-website-pages
                              │
                    Returns list of [name, url]
                              │
              Agent identifies relevant pages
              (e.g. /offers, /sale, /pricing)
                              │
                    ┌─────────┴──────────┐
                    │                    │
               1 page?              Multiple pages?
                    │                    │
           scrape-one-page     scrape-multi-pages
                    │                    │
              HTML returned       All HTMLs returned
                              │
                    Agent analyses HTML content
                    and answers user question
```

---

## 2. Tool: `fetch-website-pages`

### Purpose
Crawl a website's homepage and sitemap to discover all navigable internal links. Returns a structured list of page names and URLs so the agent knows what pages are available before deciding what to scrape.

### When the agent should call this
- Always as the **first tool call** when the user provides a new URL
- When the agent doesn't know the site structure yet
- When the question is broad (e.g. "any new offers?") and the agent needs to find the right pages first

### Input Schema

```json
{
  "name": "fetch-website-pages",
  "description": "Crawl a website to discover all internal page links. Returns a list of {name, url} pairs representing every navigable page found.",
  "parameters": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The root URL of the website to crawl (e.g. https://competitor.com). Must include scheme (https://)."
      },
      "max_pages": {
        "type": "integer",
        "description": "Maximum number of pages to return. Defaults to 50. Use lower values for large sites.",
        "default": 50
      }
    },
    "required": ["url"]
  }
}
```

### Output Schema

```json
{
  "url": "https://competitor.com",
  "pages_found": 24,
  "pages": [
    { "name": "Home",          "url": "https://competitor.com/" },
    { "name": "Offers",        "url": "https://competitor.com/offers" },
    { "name": "Sale",          "url": "https://competitor.com/sale" },
    { "name": "Pricing",       "url": "https://competitor.com/pricing" },
    { "name": "New Arrivals",  "url": "https://competitor.com/new" }
  ]
}
```

### Implementation Logic (`mcp/tools/fetch_pages.py`)

```
1. Parse the root URL, extract domain
2. Try to fetch /sitemap.xml or /sitemap_index.xml via httpx
   → If found: parse all <loc> entries from XML
3. Also fetch the homepage HTML via httpx
   → Parse all <a href="..."> links with BeautifulSoup
   → Filter: keep only internal links (same domain)
   → Deduplicate
4. Combine sitemap URLs + homepage links, deduplicate
5. For each URL, try to extract a human-readable name:
   → From <title> tag if page is fetched, or
   → From the link's anchor text, or
   → From the URL path segment (e.g. /pricing → "Pricing")
6. Return up to max_pages results
```

### Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Site unreachable (timeout, DNS fail) | Return `{"error": "UNREACHABLE", "message": "..."}` |
| No links found | Return empty `pages` array with `pages_found: 0` |
| Sitemap malformed | Fall back to homepage link extraction only |
| `robots.txt` disallows crawling | Log warning; still attempt (no legal enforcement in dev) |

---

## 3. Tool: `scrape-one-page`

### Purpose
Fetch the full HTML content of a single URL. The agent uses this when it has identified a specific page to read (e.g. the `/offers` page).

### When the agent should call this
- When only **one** page is needed
- For quick spot-checks on a specific URL
- When `scrape-multi-pages` would be overkill (e.g. only one relevant page found)

### Input Schema

```json
{
  "name": "scrape-one-page",
  "description": "Fetch the full HTML content of a single URL. Returns the page's raw HTML so you can analyse its content.",
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
        "default": false
      }
    },
    "required": ["url"]
  }
}
```

### Output Schema

```json
{
  "url": "https://competitor.com/offers",
  "page_title": "Offers & Discounts | Competitor",
  "html": "<!DOCTYPE html><html>...",
  "size_bytes": 142300,
  "rendered_with": "httpx",
  "scraped_at": "2026-06-17T12:00:04Z"
}
```

### Implementation Logic (`mcp/tools/scrape_one.py`)

```
1. Attempt with httpx (async GET, 30s timeout, browser-like headers)
   → If response 200 and content-length > 0: return HTML
   → If response non-200, timeout, or HTML is suspiciously short (<1KB):
     → Fall back to Playwright

2. Playwright fallback (async):
   → Launch headless Chromium
   → Navigate to URL, wait for networkidle
   → page.content() → return full rendered HTML
   → Close browser

3. Extract <title> tag with BeautifulSoup

4. Return {url, page_title, html, size_bytes, rendered_with, scraped_at}
```

### Error Handling

| Situation | Behaviour |
|-----------|-----------|
| httpx timeout (30s) | Auto-fallback to Playwright |
| Playwright timeout (60s) | Return `{"error": "SCRAPE_FAILED", "url": "..."}` |
| HTTP 403/429 | Return error with status code; agent decides whether to retry |
| HTTP redirect → different domain | Follow redirect; note final URL in response |

---

## 4. Tool: `scrape-multi-pages`

### Purpose
Batch-fetch multiple URLs in parallel using `asyncio.gather`. This is the primary scraping tool for most competitor analysis tasks — the agent identifies several relevant pages via `fetch-website-pages` and then fetches them all at once in a single tool call.

### When the agent should call this
- When **2 or more** pages need to be scraped
- After `fetch-website-pages` returns a list and the agent identifies multiple relevant URLs
- **Always prefer this over calling `scrape-one-page` multiple times** — it's faster and uses fewer LLM roundtrips

### Input Schema

```json
{
  "name": "scrape-multi-pages",
  "description": "Fetch the full HTML of multiple URLs in parallel. More efficient than calling scrape-one-page multiple times. Returns a list of results.",
  "parameters": {
    "type": "object",
    "properties": {
      "urls": {
        "type": "array",
        "items": { "type": "string" },
        "description": "List of URLs to scrape in parallel (max 20 per call)",
        "maxItems": 20
      },
      "use_playwright_for_all": {
        "type": "boolean",
        "description": "Force Playwright for all URLs. Use when you know the site is JS-rendered.",
        "default": false
      }
    },
    "required": ["urls"]
  }
}
```

### Output Schema

```json
{
  "total_requested": 3,
  "total_succeeded": 3,
  "total_failed": 0,
  "results": [
    {
      "url": "https://competitor.com/offers",
      "page_title": "Offers & Discounts | Competitor",
      "html": "<!DOCTYPE html>...",
      "size_bytes": 142300,
      "rendered_with": "httpx",
      "scraped_at": "2026-06-17T12:00:04Z",
      "error": null
    },
    {
      "url": "https://competitor.com/sale",
      "page_title": "Summer Sale | Competitor",
      "html": "<!DOCTYPE html>...",
      "size_bytes": 98400,
      "rendered_with": "httpx",
      "scraped_at": "2026-06-17T12:00:04Z",
      "error": null
    },
    {
      "url": "https://competitor.com/pricing",
      "page_title": "Pricing | Competitor",
      "html": "<!DOCTYPE html>...",
      "size_bytes": 61200,
      "rendered_with": "playwright",
      "scraped_at": "2026-06-17T12:00:05Z",
      "error": null
    }
  ]
}
```

### Implementation Logic (`mcp/tools/scrape_multi.py`)

```
1. Validate: at most 20 URLs per call
2. Create async tasks: one scrape_one_page() coroutine per URL
3. asyncio.gather(*tasks, return_exceptions=True)
4. For each result:
   → If exception: record as failed with error message
   → If success: include in results
5. Return combined response
```

### Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Some URLs fail | Return partial results; failed URLs have `"error": "..."` field set |
| All URLs fail | Return with `total_succeeded: 0` and all errors populated |
| > 20 URLs requested | Truncate to first 20; note in response |

---

## 5. MCP Tool Registration (`mcp/server/scraper_server.py`)

The tools are registered with the Groq API as a Python list of tool definition dicts. This list is passed as the `tools` parameter on every Groq API call.

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch-website-pages",
            "description": "...",
            "parameters": { ... }   # As defined in §2
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape-one-page",
            "description": "...",
            "parameters": { ... }   # As defined in §3
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape-multi-pages",
            "description": "...",
            "parameters": { ... }   # As defined in §4
        }
    }
]

TOOL_DISPATCH = {
    "fetch-website-pages": fetch_website_pages,
    "scrape-one-page":     scrape_one_page,
    "scrape-multi-pages":  scrape_multi_pages,
}

async def dispatch_tool(name: str, arguments: dict) -> dict:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        raise ValueError(f"Unknown tool: {name}")
    return await fn(**arguments)
```

---

## 6. Scraping Headers

Both `httpx` and `Playwright` use realistic browser-like headers to avoid bot detection:

```python
SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
```

---

## 7. Agent System Prompt (Tool Usage Instructions)

The system prompt instructs the model on how to use the tools effectively:

```
You are a Competitor Intelligence Agent. Your job is to monitor competitor websites
and answer questions about their offers, discounts, price changes, and promotions.

You have access to three tools:
1. fetch-website-pages: ALWAYS call this first when given a new URL. It maps the site.
2. scrape-one-page: Use for a single specific page.
3. scrape-multi-pages: PREFER this when you need 2+ pages. It's faster.

Tool usage strategy:
- Step 1: fetch-website-pages to discover the site structure
- Step 2: Identify pages most likely to contain offers, pricing, sales, or promotions
  (look for paths containing: /offers, /deals, /sale, /pricing, /promotions, /discount, /new)
- Step 3: scrape-multi-pages on those relevant pages (or scrape-one-page if only one)
- Step 4: Analyse the HTML content and answer the user's question

When analysing HTML:
- Look for price elements, promotional banners, countdown timers, badge labels
- Look for keywords: "sale", "off", "discount", "limited time", "new", "launch", "%"
- Be specific: quote exact percentages, prices, product names, and offer end dates if found
- If nothing notable is found, clearly state that — do not fabricate information

You may call tools as many times as needed until you have a complete answer.
```

---

## 8. Adding New Tools (Future)

To add a new tool:

1. Create `mcp/tools/new_tool.py` with an `async def` function
2. Add the JSON tool definition to `TOOLS` list in `scraper_server.py`
3. Add the function to `TOOL_DISPATCH` dict in `scraper_server.py`
4. Document in this file

No other changes needed — the agent loop and WebSocket handler are tool-agnostic.
