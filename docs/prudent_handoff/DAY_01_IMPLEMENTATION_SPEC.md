# Day 01 Implementation Brief: Sovereign Foundations, Ingress & Reverse CRM

> **Document ID**: `HANDOFF-DAY-01`  
> **Source**: `Project Prudent` (Architecture & PRD Engine)  
> **Target Agent**: `Linkedin strategy` Core Engineering Agent  
> **Status**: Verified Production Specification Ready for Implementation

---

## 🎯 Executive Summary for the Builder Agent

This document contains the complete, battle-tested architectural blueprint for Day 01. Your mission in `Linkedin strategy` is to implement these specifications into your production codebase.

### The Scope of Day 01:
1. **SQLite WAL Mode & Migrations**: Configure WAL mode and apply schema for `leads` and `lead_interactions`.
2. **Ubiquitous Ingress Daemon**: Connect to Telegram Bot API via outbound long-polling with 24h cloud buffering.
3. **Real-Time Live Studio Display**: Broadcast newly arrived drafts over Server-Sent Events (SSE) to the Studio UI in <5ms.
4. **LinkedIn Native Scheduler Staging**: Pre-stage posts directly into LinkedIn's native cloud scheduler via Voyager APIs.
5. **Enterprise Reverse CRM**: Deterministic multi-factor ICP scoring and anti-slop contextual DM generation.

---

## 🗄️ 1. Database Configuration & Schema Migrations

### Required Pragmas (Apply to `linkedin_studio.db` on connection):
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000; -- 64MB cache
```

### Schema Migration: Enterprise Reverse CRM Tables
Execute this DDL against `linkedin_studio.db`:
```sql
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_urn TEXT UNIQUE,
    full_name TEXT NOT NULL,
    headline TEXT,
    company TEXT,
    seniority_level TEXT DEFAULT 'Unknown',
    icp_score REAL DEFAULT 0.0,
    lead_status TEXT DEFAULT 'NEW' CHECK(lead_status IN ('NEW', 'ENGAGED', 'DM_DRAFTED', 'DM_SENT', 'CONVERTED', 'ARCHIVED')),
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    post_id INTEGER,
    post_urn TEXT,
    interaction_type TEXT NOT NULL CHECK(interaction_type IN ('COMMENT', 'LIKE', 'REPOST')),
    comment_text TEXT,
    sentiment_label TEXT DEFAULT 'NEUTRAL',
    suggested_dm_reply TEXT,
    interacted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    FOREIGN KEY(post_id) REFERENCES drafts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_icp ON leads(icp_score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(lead_status);
CREATE INDEX IF NOT EXISTS idx_interactions_lead ON lead_interactions(lead_id, interacted_at DESC);
```

---

## 📡 2. Ubiquitous Telegram Ingress & Real-Time Event Bus

### 2.1 The Long-Polling Ingress Daemon:
* Connect outbound to: `https://api.telegram.org/bot<TOKEN>/getUpdates?offset=<LAST_ID+1>&timeout=30`
* **Zero Open Ports**: Do not bind a webhook. The client connects outward.
* **Whitelist Security**: Check `update.message.chat.id == AUTHORIZED_CHAT_ID`. Drop all other IDs silently.
* **Parsing Rules**:
  - `Draft: <text>` -> Set `archetype = 'Draft'`, tags = `['mobile-ingress']`.
  - `Idea: <text>` -> Set `archetype = 'Raw Idea'`, tags = `['idea', 'mobile-ingress']`.
  - `Schedule <target>: <text>` -> Set `archetype = 'Scheduled Post'`, queue for target time.
  - Extract all hashtags (`#tag`) into JSON tags array.
* **Pre-fold Calculation**:
  - Fold triggered at **line 3 OR 140 characters**.
  - Blank lines count as **45 characters**.

### 2.2 Server-Sent Events (SSE) Studio Stream:
* Expose FastAPI endpoint: `GET /api/v1/stream/events`
* Wire standard `text/event-stream` headers.
* When a message is ingested from Telegram, broadcast:
  ```json
  event: draft_ingested
  data: {"draft_id": 1, "title": "...", "raw_content": "...", "is_pre_fold_safe": true}
  ```
* In `studio/frontend/`, open `new EventSource('/api/v1/stream/events')` and animate incoming drafts into the Studio inbox tray in <5ms.

---

## ⏱️ 3. LinkedIn Native Scheduler Protocol (Solving Sleeping Laptop)

When scheduling a post from the Studio:
* **Endpoint**: `POST https://www.linkedin.com/voyager/api/contentcreation/normShares`
* **Headers**: Must include active session `Cookie: li_at=...; JSESSIONID="ajax:...";` and `csrf-token: ajax:...`
* **Payload**:
  ```json
  {
    "author": "urn:li:person:CURRENT_MEMBER_URN",
    "lifecycleState": "SCHEDULED",
    "visibility": "PUBLIC",
    "commentary": {
      "text": "Your post content here...",
      "attributes": []
    },
    "scheduledAt": 1789716600000
  }
  ```
* **Local Fallback (Self-Healing Queue)**:
  - If post is queued locally and machine wakes up after the scheduled slot:
    - *Delay <= 45 mins*: Prompt 1-click launch under the morning grace period.
    - *Delay > 45 mins*: Auto-reschedule to the next peak creator window (e.g. 1:15 PM) to protect algorithmic reach.

---

## 💼 4. Enterprise Reverse CRM: ICP Equation & Anti-Slop DMs

### 4.1 Deterministic ICP Scoring Formula:
$$\text{ICP Score} = \min\Big(100, \max\big(0, (W_s \cdot 0.45) + (W_i \cdot 0.30) + (W_c \cdot 0.15) + (W_q \cdot 0.10)\big)\Big)$$

* **Seniority Weights ($W_s$)**:
  - Founder / Co-Founder / Managing Director: **100 pts**
  - C-Suite (CEO, CTO, CPO, COO): **90 pts**
  - VP / Director / Head of: **75 pts**
  - Senior Practitioner (Staff, Principal, Architect): **50 pts**
  - Student / Intern / Job Seeker: **-40 pts** (hard penalty)
* **Interaction Depth ($W_i$)**:
  - Comment > 15 words: **100 pts** | Comment 5–14 words: **60 pts** | Like/Reaction: **15 pts**
* **Question Multiplier ($W_q$)**:
  - Comment contains `?`: **100 pts** | Otherwise: **0 pts**

### 4.2 Anti-Slop Contextual DM Template:
When generating follow-up outreach, strictly ban em-dashes and generic clichés:
```text
Hi [First Name], saw your question on my recent post about [Topic]. 
Specifically regarding "[Comment Excerpt]...", wanted to share a quick perspective directly. 
[1-to-2 sentence direct insight]. 
Are you testing similar workflows in your stack?
```

---

## 🛑 5. Anti-Slop Verification Gate

Before committing your code in `Linkedin strategy`:
1. **Zero Em-Dashes**: Run regex audit `grep -rn " - "` across your changes. Ban all em-dashes.
2. **Loopback Binding**: Assert backend binds strictly to `127.0.0.1:8000`, never `0.0.0.0`.
3. **Reference Implementations**: Reference tested implementations in `Project Prudent/studio/core/` for guidance:
   - Ingress daemon: `studio/core/ingress.py`
   - Event bus: `studio/core/event_bus.py`
   - CRM engine: `studio/core/crm.py`
   - SQLite engine: `studio/core/database.py`
   - OS Power manager: `studio/core/power.py`
