# UI Document
## Competitor Intelligence Agent — v1.0

---

## 1. Overview

The entire frontend is a **single `index.html` file** using vanilla HTML, CSS, and JavaScript only. No frameworks, no build step, no npm. It is opened directly as `file://` in the browser and communicates with the FastAPI backend via WebSocket and REST.

**Design direction:** Dark mode, premium feel. Clean chat UI inspired by modern AI chat products (Claude, ChatGPT) but with a dedicated "Thinking" panel that surfaces the agent's internal process transparently.

---

## 2. Layout

```
┌────────────────────────────────────────────────────────────────────┐
│                         index.html                                 │
│  ┌──────────────┬─────────────────────────────────────────────┐   │
│  │              │                                             │   │
│  │   SIDEBAR    │               CHAT WINDOW                  │   │
│  │              │                                             │   │
│  │ [+ New Chat] │  ┌─────────────────────────────────────┐   │   │
│  │              │  │          Message Thread              │   │   │
│  │ ─────────── │  │                                     │   │   │
│  │              │  │  [User bubble]                      │   │   │
│  │ Chat 1       │  │                                     │   │   │
│  │ Chat 2       │  │  [Agent bubble]                     │   │   │
│  │ Chat 3       │  │    [🧠 Thinking ▾] ← always visible  │   │   │
│  │ ...          │  │    ┌─────────────────────────────┐  │   │   │
│  │              │  │    │ THINKING PANEL (collapsible)│  │   │   │
│  │              │  │    │ • Reasoning text             │  │   │   │
│  │              │  │    │ • Tool call 1               │  │   │   │
│  │              │  │    │ • Tool call 2               │  │   │   │
│  │              │  │    └─────────────────────────────┘  │   │   │
│  │              │  │                                     │   │   │
│  │              │  └─────────────────────────────────────┘   │   │
│  │              │                                             │   │
│  │              │  ┌─────────────────────────────────────┐   │   │
│  │              │  │           INPUT AREA                 │   │   │
│  │              │  │  ┌──────────────────────────────┐   │   │   │
│  │              │  │  │  📎 URL chips (+ Add URL btn) │   │   │   │
│  │              │  │  └──────────────────────────────┘   │   │   │
│  │              │  │  ┌──────────────────────────────┐   │   │   │
│  │              │  │  │  Message textarea            │   │   │   │
│  │              │  │  └────────────────────┬─────────┘   │   │   │
│  │              │  │                       │  [Send ▶]   │   │   │
│  │              │  └───────────────────────┴─────────────┘   │   │
│  └──────────────┴─────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Design System

### 3.1 Color Palette

```css
--bg-primary:      #0f1117;   /* Main background — deep near-black */
--bg-secondary:    #1a1d27;   /* Sidebar + input area background */
--bg-surface:      #21253a;   /* Message bubbles, cards */
--bg-surface-alt:  #2a2f47;   /* Thinking panel, hover states */

--accent:          #6c63ff;   /* Primary purple — buttons, active states */
--accent-hover:    #7c74ff;   /* Lighter purple on hover */
--accent-glow:     rgba(108, 99, 255, 0.25); /* Shadow/glow effect */

--text-primary:    #e8eaf0;   /* Main text */
--text-secondary:  #8a90a8;   /* Muted labels, timestamps */
--text-code:       #a8daff;   /* Inline code, tool names */

--border:          #2e3352;   /* Dividers and borders */
--border-light:    #383d5e;   /* Subtle borders */

--user-bubble:     #1e3a5f;   /* User message background (blue tint) */
--agent-bubble:    #21253a;   /* Agent message background */

--thinking-bg:     #161a2e;   /* Thinking panel background */
--thinking-border: #6c63ff44; /* Purple tinted border on thinking panel */

--tool-badge:      #2d3561;   /* Tool call badge background */

--success:         #3ddc84;
--warning:         #ffb347;
--error:           #ff5c5c;

--radius-sm:       6px;
--radius-md:       12px;
--radius-lg:       18px;
--radius-xl:       24px;
```

### 3.2 Typography

```css
/* Font: Inter from Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

--font-sans:  'Inter', system-ui, sans-serif;
--font-mono:  'JetBrains Mono', 'Courier New', monospace;  /* Tool names, code */

--text-xs:    11px;
--text-sm:    13px;
--text-base:  15px;
--text-lg:    17px;
```

---

## 4. Components

### 4.1 Sidebar

- **Width:** 260px, fixed left, non-collapsible in v1
- **Header:** App logo/name ("Competitor Agent") + "New Chat" button (top)
- **Conversation list:** Scrollable, sorted newest first
  - Each item shows: conversation title (truncated to 1 line) + relative time ("2 hours ago")
  - Active conversation is highlighted with `--accent` left border + `--bg-surface-alt` background
  - Hover: subtle background shift
  - Click: load conversation (REST GET + re-render chat window)
- **Delete:** On hover, a ✕ icon appears to the right of each conversation item

```
┌──────────────────────────┐
│  🤖 Competitor Agent      │
│  [+ New Chat]            │
│  ─────────────────────── │
│ ▌ Did competitor launch… │  ← active (purple left border)
│   2 hours ago            │
│                          │
│   Summer sale check      │
│   Yesterday              │
│                          │
│   New Conversation       │
│   Jun 15                 │
└──────────────────────────┘
```

---

### 4.2 Chat Window

- **Area:** Fills remaining width after sidebar; vertically scrollable
- **Auto-scroll:** Always scrolls to bottom when new content arrives
- **Empty state:** When no messages, show a centered welcome prompt with suggested example questions
- **Loading state:** Full-width animated "thinking" bar shown while agent processes

---

### 4.3 Message Bubbles

#### User Message
- Right-aligned (or full-width with left-aligned content — choose one style consistently)
- Background: `--user-bubble`
- Shows: message text + URL chips (if any) below the text
- URL chips: small pill badges showing the domain name + link icon; clickable to open URL

```
┌──────────────────────────────────────────────────────┐
│  Did this competitor launch any new offers today?    │
│                                                      │
│  🔗 competitor.com   🔗 other-site.com               │
│                                      12:00 PM        │
└──────────────────────────────────────────────────────┘
```

#### Agent Message
- Full-width, left-aligned
- Background: `--agent-bubble`
- Content rendered as Markdown (using a lightweight renderer — `marked.js` included inline)
- Below the message content: the **Thinking button**

```
┌──────────────────────────────────────────────────────┐
│  Yes, competitor.com launched a **20% off** sale     │
│  on all electronics starting today, June 17th.       │
│  The offer runs until June 24th and applies to...    │
│                                                      │
│  [🧠 Thinking  ▾]                       12:00 PM    │
└──────────────────────────────────────────────────────┘
```

---

### 4.4 Thinking Button & Panel

This is the signature feature of the UI.

#### The Button
- Label: `🧠 Thinking ▾` (collapsed) / `🧠 Thinking ▴` (expanded)
- Style: small pill button, `--bg-surface-alt` background, `--accent` text color
- **Always present** on every agent message — it never disappears after first click
- **Toggle behavior:** click to expand/collapse the panel; state is independent per message
- Clicking on an already-expanded panel collapses it (and vice versa)

#### The Panel (expanded state)

The panel has two sections:

**Section 1 — Model Reasoning**
- Header: `💭 Reasoning`
- Content: the raw `reasoning` text from the Groq `reasoning_format="parsed"` response
- Font: `--font-mono`, slightly smaller
- Background: `--thinking-bg`
- Left border: 2px solid `--accent`
- Scrollable if very long

**Section 2 — Tool Call Trace**
- Header: `🔧 Tool Calls (N)`
- One card per tool call, in `sequence_order`
- Each card shows:
  - Tool name badge (e.g. `fetch-website-pages`) — styled like a code tag
  - Arrow icon + call number (e.g. `→ Call #1`)
  - Input args as pretty-printed JSON (collapsible)
  - Output summary text

```
┌─────────────────────────────────────────────────────────────┐
│ 🧠 Thinking ▴                                               │
│                                                             │
│ ─── 💭 Reasoning ─────────────────────────────────────────  │
│                                                             │
│  The user wants to know about new offers on competitor.com. │
│  I should first call fetch-website-pages to discover the    │
│  site structure, then identify pages related to sales or    │
│  promotions and scrape those...                             │
│                                                             │
│ ─── 🔧 Tool Calls (2) ────────────────────────────────────  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ `fetch-website-pages`  → Call #1                    │   │
│  │ Input: { "url": "https://competitor.com" }          │   │
│  │ Result: Found 24 pages on competitor.com            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ `scrape-multi-pages`   → Call #2                    │   │
│  │ Input: { "urls": ["…/offers", "…/sale"] }           │   │
│  │ Result: Scraped 2 pages, 241KB total                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Live Tool Events (during loading)
While the agent is still processing, `tool_event` WebSocket frames arrive in real-time. The Thinking panel for the **in-progress** message updates live as each tool finishes — new tool cards append to the panel as they arrive. The user can open the panel during loading to watch the agent work.

---

### 4.5 Input Area

Fixed to the bottom of the chat window. Two-part structure:

**Part 1 — URL Input Row**
- A horizontal row of URL chips + an "Add URL" button
- Each chip: domain favicon (if available) + short domain name + ✕ remove button
- "Add URL" button opens a small inline input field; pressing Enter or clicking "Add" adds the chip
- URL validation: must match `https?://` pattern; invalid URLs show inline error

**Part 2 — Message Textarea + Send Button**
- Auto-expanding textarea (grows as user types, max 6 lines then scrolls)
- Placeholder: `"Ask anything about your competitors…"`
- Send button (▶): right-aligned, accent color; disabled while agent is processing
- Keyboard shortcut: `Enter` to send, `Shift+Enter` for new line

```
┌───────────────────────────────────────────────────────┐
│  🔗 competitor.com ✕    🔗 other.com ✕    [+ Add URL] │
├───────────────────────────────────────────────────────┤
│  Did this competitor launch any new offers today?     │
│                                                       │
│                                                [▶ Send]│
└───────────────────────────────────────────────────────┘
```

---

### 4.6 Loading State

Shown after the user sends a message, until `final_response` arrives.

- The input area is **disabled** (textarea + send button grayed out; "Add URL" hidden)
- A **status bar** appears above the input area showing the current agent status:
  - Initial: `🤔 Agent is thinking…` with a pulsing dot animation
  - After each `tool_event`: updates to `🔧 Calling fetch-website-pages…` then `✅ fetch-website-pages done`
- An in-progress agent message bubble appears with a **typing animation** (three animated dots `···`)
- The Thinking panel on this in-progress bubble updates live as `tool_event` frames arrive

---

## 5. WebSocket Client Logic (JavaScript)

```javascript
// State
let ws = null;
let sessionId = localStorage.getItem('sessionId') || generateUUID();
let conversationId = null;
let currentAgentMessageEl = null;

localStorage.setItem('sessionId', sessionId);

// Connect
function connect(convId = null) {
    const url = `ws://localhost:8000/ws?session_id=${sessionId}`
              + (convId ? `&conversation_id=${convId}` : '');
    ws = new WebSocket(url);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerEvent(data);
    };
}

// Handle incoming events
function handleServerEvent(data) {
    switch (data.type) {
        case 'conversation_created':
            conversationId = data.conversation_id;
            addConversationToSidebar(data);
            break;

        case 'agent_thinking':
            currentAgentMessageEl = renderAgentBubble({ inProgress: true });
            setInputDisabled(true);
            break;

        case 'tool_event':
            appendToolEventToThinkingPanel(currentAgentMessageEl, data);
            updateStatusBar(`🔧 ${data.tool_name} completed`);
            break;

        case 'final_response':
            finalizeAgentBubble(currentAgentMessageEl, data);
            setInputDisabled(false);
            currentAgentMessageEl = null;
            break;

        case 'error':
            showErrorToast(data.message);
            setInputDisabled(false);
            break;
    }
}

// Typewriter reveal
function typewriterReveal(element, text, speedMs = 12) {
    let i = 0;
    const interval = setInterval(() => {
        element.innerHTML = marked.parse(text.slice(0, i));
        i++;
        if (i > text.length) clearInterval(interval);
    }, speedMs);
}
```

---

## 6. Page Load Sequence

```
1. Page loads (file:// or http://localhost:8000)
2. Read sessionId from localStorage (or generate new UUID and store it)
3. GET /api/conversations?session_id=... → populate sidebar
4. If URL has ?conversation_id= query param → load that conversation
   (GET /api/conversations/{id}/messages → render history)
5. Open WebSocket connection (no conversation_id yet for new chat)
6. Wait for user input
```

---

## 7. Markdown Rendering

Agent responses are rendered as Markdown using **`marked.js`** (loaded inline from CDN in `index.html`). Supported elements:
- **Bold**, *italic*, `inline code`
- Bullet lists and numbered lists
- Headings (H2, H3)
- Code blocks (fenced with language hint)
- Horizontal rules

No external renderer needed — one script tag:
```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

---

## 8. Animations & Micro-interactions

| Interaction | Animation |
|-------------|-----------|
| Page load | Sidebar slides in from left (150ms ease-out) |
| New message sent | User bubble fades + slides in from right |
| Agent response | Typewriter character-by-character reveal |
| Thinking panel open | Panel slides down + fades in (200ms) |
| Tool event appended | New tool card fades in (150ms) |
| Loading indicator | Pulsing dot animation on status bar |
| Send button hover | Scale 1.05 + glow shadow |
| Sidebar item hover | Background transition (100ms) |
| URL chip add | Chip pops in with scale animation |
| URL chip remove | Chip fades + collapses out |

---

## 9. Responsive Behavior

The UI targets desktop-first (local dev tool). Minimum supported width: **900px**. No mobile breakpoints in v1. A simple note in the UI footer warns if the viewport is too narrow.

---

## 10. File Structure (Single File)

The entire `index.html` is organized into clearly commented sections:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Meta, title, Google Fonts -->
    <!-- Marked.js CDN -->
    <style>
        /* ═══════════════════════════════════ */
        /* 1. CSS RESET & VARIABLES           */
        /* 2. LAYOUT (sidebar + chat)         */
        /* 3. SIDEBAR COMPONENT               */
        /* 4. CHAT WINDOW                     */
        /* 5. MESSAGE BUBBLES                 */
        /* 6. THINKING BUTTON & PANEL         */
        /* 7. INPUT AREA                      */
        /* 8. LOADING STATE                   */
        /* 9. ANIMATIONS & TRANSITIONS        */
        /* 10. UTILITY CLASSES                */
        /* ═══════════════════════════════════ */
    </style>
</head>
<body>
    <!-- SIDEBAR -->
    <aside id="sidebar"> ... </aside>

    <!-- MAIN CHAT -->
    <main id="chat-main">
        <!-- CHAT WINDOW -->
        <div id="chat-window"> ... </div>

        <!-- STATUS BAR (loading) -->
        <div id="status-bar"> ... </div>

        <!-- INPUT AREA -->
        <div id="input-area">
            <div id="url-chips-row"> ... </div>
            <div id="message-row">
                <textarea id="message-input"> ... </textarea>
                <button id="send-btn"> ... </button>
            </div>
        </div>
    </main>

    <script>
        /* ═══════════════════════════════════ */
        /* 1. CONSTANTS & STATE               */
        /* 2. SESSION MANAGEMENT              */
        /* 3. WEBSOCKET CLIENT                */
        /* 4. EVENT HANDLERS                  */
        /* 5. RENDER FUNCTIONS                */
        /* 6. SIDEBAR FUNCTIONS               */
        /* 7. INPUT AREA FUNCTIONS            */
        /* 8. THINKING PANEL FUNCTIONS        */
        /* 9. TYPEWRITER REVEAL               */
        /* 10. UTILITY FUNCTIONS              */
        /* ═══════════════════════════════════ */
    </script>
</body>
</html>
```
