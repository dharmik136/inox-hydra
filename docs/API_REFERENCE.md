# REST API Reference Manual

LinkedIn Studio Enterprise exposes a comprehensive RESTful API on `http://127.0.0.1:8000/api`. Interactive Swagger documentation is accessible at `http://127.0.0.1:8000/docs`.

---

## 1. Analytics Endpoints

### `GET /api/analytics/kpis`
Calculates high-level metrics, growth rates, and true period-over-period percentage deltas.
* **Query Parameters**:
  * `range` (string, optional): `7d`, `14d`, `30d` (default), or `90d`.
* **Response (200 OK)**:
```json
{
  "range": "30d",
  "impressions": 58400,
  "impressions_delta_pct": 14.2,
  "total_engagements": 2980,
  "engagements_delta_pct": 8.6,
  "avg_engagement_rate": 5.1,
  "engagement_rate_delta": 0.4,
  "total_followers": 2412,
  "follower_growth": 148,
  "profile_views": 104,
  "profile_views_delta_pct": 18.2,
  "scheduled_posts_count": 1
}
```

### `GET /api/analytics/overview`
Returns the daily time-series array for charts.
* **Query Parameters**: `range` (`7d`, `14d`, `30d`, `90d`).
* **Response (200 OK)**:
```json
{
  "status": "success",
  "range": "30d",
  "count": 30,
  "series": [
    {
      "date": "2026-08-15",
      "impressions": 1820,
      "reactions": 85,
      "comments": 22,
      "shares": 8,
      "followers": 2264,
      "profile_views": 92
    }
  ]
}
```

### `GET /api/analytics/demographics`
Returns audience distribution across 4 dimensions: `job_title`, `company`, `geography`, and `seniority`.

### `GET /api/analytics/export`
Generates and downloads a complete historical CSV report.

---

## 2. AI Command Engine Endpoints

### `GET /api/ai/status`
Returns current configuration, active mode, and capabilities.
* **Response (200 OK)**:
```json
{
  "provider": "gemini_antigravity",
  "has_api_key": true,
  "model": "gemini-2.5-flash",
  "active_mode": "Gemini 2.5 Flash (Cloud Native)",
  "antigravity_pair_programming": true,
  "capabilities": [
    "10x_viral_hooks",
    "smart_repurpose",
    "algorithmic_audit",
    "antigravity_agent_command",
    "personalized_crm_dm"
  ]
}
```

### `POST /api/ai/settings`
Saves your optional Google Gemini API key to local SQLite.
* **Request Body**:
```json
{
  "gemini_api_key": "AIzaSy..."
}
```

### `POST /api/ai/command`
Executes an instruction using Gemini (if key configured) or the Antigravity Local Engine.
* **Request Body**:
```json
{
  "command": "Draft a punchy post about decoupled state machines",
  "context": "Optional existing draft notes here..."
}
```
* **Response (200 OK)**:
```json
{
  "status": "success",
  "engine": "Gemini 2.5 Flash",
  "output": "𝗭𝗲𝗿𝗼 𝗺𝗮𝗻𝘂𝗮𝗹 𝗶𝗻𝘁𝗲𝗿𝘃𝗲𝗻𝘁𝗶𝗼𝗻.\n\nThat is the single metric that matters..."
}
```

---

## 3. Carousel PDF Generator

### `POST /api/carousel/generate`
Generates a 1080×1080 multi-page PDF ready for LinkedIn Document upload.
* **Request Body**:
```json
{
  "slides": [
    { "title": "Decoupled Architecture", "body": "Why schemas must be decoupled from business logic." },
    { "title": "01. Immutable State", "body": "State transitions should be events, not in-place mutations." },
    { "title": "Summary & Takeaways", "body": "Save this carousel to revisit foundational architecture." }
  ],
  "theme": "dark_slate",
  "author_name": "Dharmik Shingala",
  "author_title": "Content Strategist & Enterprise Systems Practitioner"
}
```
* **Response (200 OK)**: Binary stream (`application/pdf`) with `Content-Disposition: attachment; filename=linkedin_carousel.pdf`.

---

## 4. Leads & CRM Endpoints

### `GET /api/leads`
Lists leads, optionally filtered by status (`New Lead`, `Outreach Sent`, `Connected`, `Meeting Booked`).

### `POST /api/leads`
Creates a new prospect lead in the pipeline.

### `PUT /api/leads/{id}/status`
Updates lead pipeline status and notes.
* **Request Body**:
```json
{
  "status": "Outreach Sent",
  "notes": "Sent personalized DM via LinkedIn on Monday morning"
}
```

### `GET /api/leads/{id}/dm-script`
Generates a personalized direct message script for the prospect.
* **Response (200 OK)**:
```json
{
  "status": "success",
  "lead_name": "Aravind Subramanian",
  "dm_script": "Hi Aravind, noticed your perspective on our recent discussion around enterprise systems. Loved your insights..."
}
```

---

## 5. Post Formatting & Algorithmic Audit

### `POST /api/format/re-hook`
Generates 10 high-converting alternative hooks with mobile fold analysis.

### `POST /api/format/repurpose`
Transforms draft text into 5 distinct LinkedIn frameworks.

### `POST /api/format/algorithm-audit`
Performs real-time 2026 algorithmic distribution safety audit.
* **Response (200 OK)**:
```json
{
  "safety_score": 95,
  "status_label": "Optimal",
  "word_count": 142,
  "estimated_dwell_seconds": 42,
  "penalties": [],
  "recommendations": ["Consider adding 2-3 focused hashtags to aid discovery"],
  "has_outbound_links": false,
  "hashtag_count": 0,
  "mention_count": 0
}
```

### `POST /api/format/bold`, `/italic`, `/monospace`, `/clean`
Transforms text into Unicode mathematical styles or scrubs em-dashes.

---

## 6. Vector Carousel Generator (Swiss Typography)

### `POST /api/v1/carousel/deck/generate`
Generates pure vector SVG slides adhering to 4:5 vertical (1080x1350) or 1:1 square (1080x1080) formats with Swiss typography principles ('Plus Jakarta Sans' headlines, 'Inter' body, 'JetBrains Mono' badges).
* **Request Body**:
```json
{
  "title": "Decoupled Architecture",
  "author_name": "Dharmik Shingala",
  "author_handle": "@dharmikshingala",
  "slides": [
    {
      "slide_number": 1,
      "tag": "FOUNDATION",
      "headline": "Decoupled Architecture",
      "body": "Why schemas must be decoupled from business logic in high-scale systems.",
      "takeaway": "Clean separation ensures longevity"
    }
  ],
  "theme": "dark_slate",
  "aspect_ratio": "4:5"
}
```
* **Response (200 OK)**:
```json
{
  "status": "success",
  "deck_id": "deck_20260918_...",
  "slide_count": 1,
  "aspect_ratio": "4:5",
  "dimensions": { "width": 1080, "height": 1350 },
  "slides": [
    { "slide_number": 1, "svg_content": "<svg ...>...</svg>" }
  ]
}
```

---

## 7. FTS5 Full-Text Documentation Search

### `GET /api/docs/search`
Queries the SQLite FTS5 documentation search index with BM25 ranking and snippet highlighting. Latency is sub-15ms.
* **Query Parameters**:
  * `q` (string, required): Search query (e.g., `rate limiter`, `circuit breaker`).
  * `limit` (int, optional): Max results (default 10).
* **Response (200 OK)**:
```json
{
  "status": "success",
  "query": "rate limiter",
  "count": 4,
  "results": [
    {
      "module_id": "02_SCHEDULE_AND_QUEUE",
      "section_title": "Gaussian Jitter Rate Limiter",
      "snippet": "...implements a Gaussian rate limiter with token bucket...",
      "score": -5.21
    }
  ]
}
```

---

## 8. Inbound CRM Ingestion & Anti-Slop DMs

### `POST /api/v1/crm/interactions/ingest`
Ingests passive commenter interactions from the Chrome extension or manual entry, normalizes profile URLs, executes deterministic 4-factor ICP scoring, and triggers lead pipeline placement.
* **Request Body**:
```json
{
  "lead_name": "Aravind Subramanian",
  "profile_url": "https://www.linkedin.com/in/aravind-subramanian",
  "headline": "VP of Engineering at Enterprise Scale",
  "company": "Enterprise Scale",
  "interaction_type": "COMMENT",
  "comment_text": "Decoupling storage from compute was our biggest leap this year.",
  "post_urn": "urn:li:activity:7123456789012345678"
}
```
* **Response (200 OK)**:
```json
{
  "status": "success",
  "lead_id": 42,
  "icp_score": 85,
  "qualification_tier": "Tier 1 - Executive / Decision Maker",
  "intent_signals": ["TECH_TERMS:decoupling"],
  "variants": [
    {
      "style": "Executive Peer (Direct & Respectful)",
      "text": "Aravind: saw your comment on decoupling storage and compute..."
    }
  ]
}
```

---

## 9. Asymmetric Intelligence Sync (ETag Cached)

### `GET /api/v1/intelligence/bundle/export`
Exports viral hook blueprints and algorithmic rules as a deterministic JSON bundle. Supports HTTP conditional requests with `If-None-Match` and `304 Not Modified`.

### `POST /api/v1/intelligence/bundle/import`
Imports a synchronized intelligence bundle directly for 100% air-gapped workstations.

---

## 10. Rate Limiter & Single-Writer Diagnostics

### `GET /api/v1/rate-limiter/status`
Returns real-time diagnostics for the Gaussian jitter rate limiter, token bucket capacity, and time-to-next-token.

### `POST /api/v1/rate-limiter/acquire`
Attempts to acquire rate-limited permission for passive API/session requests.

---

## 11. Grounding: The Creator's Own Material (MCP)

The studio is an MCP **client**. It reads the creator's notes, repository and
calendar so a draft can be written from their actual record, which is the one
thing a cloud writing tool structurally cannot do.

**These routes execute commands.** Adding a server stores a command line the
studio will run. That is what MCP is rather than an oversight, and it makes
this the largest grant in the API. Four things hold it:

- The access middleware already limits every route to loopback with a matching
  `Host`, an allowed `Origin`, and the session cookie.
- **The extension cannot relay these.** `RELAYABLE_PATHS` in the service worker
  lists three ingest endpoints. A test pins its size, because adding a fourth
  would be a one line change whose consequence nobody would notice.
- A command is a list of arguments, never a string, and never reaches a shell.
  A string is rejected with `422`.
- Adding does not enable. They are separate calls because they are separate
  decisions.

### `GET /api/v1/mcp/servers`
Every configured source and whether it is switched on, plus an `egress` object
computed from the AI provider currently in force.

### `POST /api/v1/mcp/servers`
Registers a source, **switched off**. Body: `name`, `command` (a list), and
optional `cwd`, `env`, `description`. There is no `enabled` field.

### `POST /api/v1/mcp/servers/{name}/enabled`
Body `{"enabled": true|false}`. Returns the state it **achieved**, read back
rather than echoed, so a caller cannot be told a source is on when the write
failed.

### `DELETE /api/v1/mcp/servers/{name}`

### `GET /api/v1/mcp/preview`
What the enabled sources hand over, before a draft uses it: `material`,
`errors` naming any source that failed, `bytes_used` against `bytes_budget`,
and the same `egress` object.

### Notes for an interface built on these

The vanilla page carries this as a Grounding card in Settings.
`paths.get_frontend_dir()` prefers `frontend_next` when it is built, so the
React interface needs its own, and these are the properties that matter rather
than the layout:

- **Never omit the egress line.** The backend computes on every call whether
  material is about to leave the machine. A creator deciding whether to connect
  their notes needs that answer before they connect them, and until this
  existed the backend computed it and told nobody. Style local and remote
  differently; one neutral treatment for both is the interface declining to
  say.
- **Escape everything a source returns.** It is arbitrary text from an
  arbitrary local program, and this is the only place in the studio where such
  text is rendered.
- **Show the command.** The creator is agreeing to run it, and an agreement to
  something invisible is not one.
- **Let the toggle follow the achieved state**, not the click. A toggle left on
  after a failed write says drafts are grounded when they are not.
