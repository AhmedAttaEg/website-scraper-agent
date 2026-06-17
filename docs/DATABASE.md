# Database Document
## Competitor Intelligence Agent — v1.0

---

## 1. Overview

- **Engine:** MySQL 8.x (AWS RDS, non-Aurora)
- **ORM:** SQLAlchemy (async) with `asyncmy` driver
- **Database name:** `competitor_agent`
- **Character set:** `utf8mb4` (supports full Unicode + emoji in scraped content)
- **Collation:** `utf8mb4_unicode_ci`

---

## 2. Entity Relationship Diagram

```
┌──────────────────────┐
│     conversations    │
│──────────────────────│
│ id (PK, UUID)        │◄──────────────────────────────────┐
│ session_id           │                                   │
│ title                │                                   │
│ created_at           │                                   │
│ updated_at           │                                   │
└──────────┬───────────┘                                   │
           │ 1                                             │
           │                                               │
           │ N                                             │
┌──────────▼───────────┐         ┌─────────────────────┐  │
│       messages       │         │    scrape_results   │  │
│──────────────────────│         │─────────────────────│  │
│ id (PK, UUID)        │    ┌───►│ id (PK, UUID)       │  │
│ conversation_id (FK) │    │    │ conversation_id (FK)├──┘
│ role                 │    │    │ message_id (FK)     │
│ content              │    │    │ url                 │
│ reasoning            │    │    │ page_title          │
│ urls_attached        │    │    │ raw_html            │
│ created_at           │    │    │ scraped_at          │
└──────────┬───────────┘    │    └─────────────────────┘
           │ 1              │
           │                │
           │ N              │
┌──────────▼───────────┐    │
│      tool_calls      │    │
│──────────────────────│    │
│ id (PK, UUID)        │    │
│ message_id (FK)      │    │
│ conversation_id (FK) ├────┘
│ tool_name            │
│ tool_input           │
│ tool_output_summary  │
│ sequence_order       │
│ called_at            │
└──────────────────────┘
```

---

## 3. Table Definitions

### 3.1 `conversations`

Represents one chat session. A new conversation is created when the user clicks "New Chat" or starts the app with no existing session.

```sql
CREATE TABLE conversations (
    id           CHAR(36)      NOT NULL DEFAULT (UUID()),
    session_id   VARCHAR(64)   NOT NULL,               -- Anonymous browser UUID
    title        VARCHAR(255)  NOT NULL DEFAULT 'New Conversation',
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_session_id (session_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Column notes:**
- `id` — UUID primary key, generated at the application layer (Python `uuid4()`)
- `session_id` — The anonymous UUID stored in the browser's `localStorage`; used to scope conversations to a device/browser
- `title` — Auto-generated from the first user message (first ~60 characters); editable in v2
- `updated_at` — Auto-updated on any change; used to sort the sidebar "most recent first"

---

### 3.2 `messages`

Every turn in the conversation — user messages, agent responses, and system messages.

```sql
CREATE TABLE messages (
    id                  CHAR(36)        NOT NULL DEFAULT (UUID()),
    conversation_id     CHAR(36)        NOT NULL,
    role                ENUM('user','assistant','system','tool')
                                        NOT NULL,
    content             LONGTEXT,                       -- Final response text (agent) or user text
    reasoning           LONGTEXT,                       -- Model reasoning tokens (assistant only)
    urls_attached       JSON,                           -- Array of URL strings attached by user (user role only)
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_messages_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Column notes:**
- `role` — Mirrors the OpenAI/Groq message role convention
- `content` — `LONGTEXT` to handle large HTML summaries in tool messages
- `reasoning` — The `message.reasoning` field from Groq's `reasoning_format="parsed"` response; stored only for `assistant` role messages
- `urls_attached` — JSON array like `["https://competitor.com", "https://other.com"]`; stored only for `user` role messages

---

### 3.3 `tool_calls`

Records every MCP tool invocation made by the agent during a single agent response turn. One agent message may have many tool calls.

```sql
CREATE TABLE tool_calls (
    id                   CHAR(36)       NOT NULL DEFAULT (UUID()),
    message_id           CHAR(36)       NOT NULL,       -- The assistant message this belongs to
    conversation_id      CHAR(36)       NOT NULL,
    tool_name            VARCHAR(100)   NOT NULL,       -- e.g. "fetch-website-pages"
    tool_input           JSON           NOT NULL,       -- Full input args as JSON
    tool_output_summary  TEXT,                          -- Short human-readable summary of what was returned
    sequence_order       TINYINT UNSIGNED NOT NULL DEFAULT 0, -- Order within the agent turn
    called_at            DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_tool_calls_message
        FOREIGN KEY (message_id) REFERENCES messages(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_tool_calls_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        ON DELETE CASCADE,
    INDEX idx_message_id (message_id),
    INDEX idx_conversation_id (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Column notes:**
- `tool_input` — The exact JSON arguments passed to the tool, e.g. `{"url": "https://competitor.com/offers"}`
- `tool_output_summary` — A short extracted summary (not the full HTML). For `scrape-one-page` this might be: `"Scraped 142KB HTML from competitor.com/offers"`. The full HTML is stored in `scrape_results`.
- `sequence_order` — The order in which tools were called during one agent turn (0-indexed). Allows the UI to replay the tool chain in order.

---

### 3.4 `scrape_results`

Stores the raw HTML output from scraping tools. Kept separate from `tool_calls` because the payloads can be very large (100KB–1MB per page).

```sql
CREATE TABLE scrape_results (
    id                  CHAR(36)        NOT NULL DEFAULT (UUID()),
    conversation_id     CHAR(36)        NOT NULL,
    message_id          CHAR(36)        NOT NULL,       -- The assistant message that triggered this scrape
    tool_call_id        CHAR(36),                       -- Optional link to the specific tool_call row
    url                 TEXT            NOT NULL,
    page_title          VARCHAR(500),                   -- <title> tag extracted from HTML
    raw_html            LONGTEXT        NOT NULL,       -- Full HTML content of the page
    scraped_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_scrape_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_scrape_message
        FOREIGN KEY (message_id) REFERENCES messages(id)
        ON DELETE CASCADE,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_message_id (message_id),
    INDEX idx_scraped_at (scraped_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Column notes:**
- `raw_html` — Full HTML of the page. `LONGTEXT` supports up to ~4GB; typical pages are 50KB–500KB.
- `page_title` — Extracted from the `<title>` tag of the scraped HTML for quick identification.
- `tool_call_id` — Optional FK to `tool_calls.id` for traceability between the scrape result and the tool call event shown in the UI.

---

## 4. Indexes Summary

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| `conversations` | `idx_session_id` | `session_id` | Fetch all conversations for a browser session |
| `conversations` | `idx_updated_at` | `updated_at` | Sort sidebar by most recent |
| `messages` | `idx_conversation_id` | `conversation_id` | Load full message history |
| `messages` | `idx_created_at` | `created_at` | Order messages chronologically |
| `tool_calls` | `idx_message_id` | `message_id` | Load tool trace for one agent message |
| `scrape_results` | `idx_conversation_id` | `conversation_id` | Query all scrapes for a session |
| `scrape_results` | `idx_message_id` | `message_id` | Load scrapes for one agent turn |

---

## 5. Data Volume Estimates (Dev Phase)

| Table | Est. rows/day | Row size | Notes |
|-------|--------------|----------|-------|
| `conversations` | 5–20 | ~200 bytes | One per "New Chat" |
| `messages` | 20–100 | 1–50 KB | Agent responses can be long |
| `tool_calls` | 50–300 | ~500 bytes | Multiple per agent response |
| `scrape_results` | 20–150 | 50–500 KB | Full HTML pages; largest table |

---

## 6. Migration Strategy

### Development (v1)
Tables are created automatically on backend startup using SQLAlchemy's `Base.metadata.create_all(engine)`. No migration files needed.

### Staging/Production (v2+)
Alembic will be introduced to manage schema migrations. The `alembic/` directory will be added to the project at that point.

---

## 7. RDS Configuration (Dev Phase)

| Setting | Value |
|---------|-------|
| Engine version | MySQL 8.0.x |
| Instance class | `db.t3.micro` (free tier eligible) |
| Storage | 20 GB gp2 (auto-scaling enabled) |
| Multi-AZ | No (dev only) |
| Publicly accessible | Yes (protected by security group) |
| Security group inbound | Port 3306, source = developer's IP `/32` |
| Backup retention | 7 days |
| Encryption at rest | Enabled |

---

## 8. SQLAlchemy ORM Models (Python Preview)

```python
# db/models.py

import uuid
from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, Enum, ForeignKey, SmallInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversations"

    id:              Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id:      Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title:           Mapped[str] = mapped_column(String(255), default="New Conversation")
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages:        Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete")

class Message(Base):
    __tablename__ = "messages"

    id:                  Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id:     Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role:                Mapped[str] = mapped_column(Enum("user", "assistant", "system", "tool"), nullable=False)
    content:             Mapped[str | None] = mapped_column(Text(length=4294967295))   # LONGTEXT
    reasoning:           Mapped[str | None] = mapped_column(Text(length=4294967295))   # LONGTEXT
    urls_attached:       Mapped[dict | None] = mapped_column(JSON)
    created_at:          Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation:        Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    tool_calls:          Mapped[list["ToolCall"]] = relationship("ToolCall", back_populates="message", cascade="all, delete")
    scrape_results:      Mapped[list["ScrapeResult"]] = relationship("ScrapeResult", back_populates="message", cascade="all, delete")

class ToolCall(Base):
    __tablename__ = "tool_calls"

    id:                   Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id:           Mapped[str] = mapped_column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    conversation_id:      Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    tool_name:            Mapped[str] = mapped_column(String(100), nullable=False)
    tool_input:           Mapped[dict] = mapped_column(JSON, nullable=False)
    tool_output_summary:  Mapped[str | None] = mapped_column(Text)
    sequence_order:       Mapped[int] = mapped_column(SmallInteger, default=0)
    called_at:            Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    message:              Mapped["Message"] = relationship("Message", back_populates="tool_calls")

class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id:               Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id:  Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    message_id:       Mapped[str] = mapped_column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    tool_call_id:     Mapped[str | None] = mapped_column(String(36))
    url:              Mapped[str] = mapped_column(Text, nullable=False)
    page_title:       Mapped[str | None] = mapped_column(String(500))
    raw_html:         Mapped[str] = mapped_column(Text(length=4294967295), nullable=False)   # LONGTEXT
    scraped_at:       Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    message:          Mapped["Message"] = relationship("Message", back_populates="scrape_results")
```
