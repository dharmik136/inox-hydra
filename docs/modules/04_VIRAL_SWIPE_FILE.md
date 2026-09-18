# Module 04: Viral Swipe File & Agno Framework Inbound Roadmap

The **Viral Swipe File** module provides a high-signal repository of reverse-engineered viral post structures, proven hook formulas, and pacing frameworks from top industry practitioners.

---

## 1. Visual Layout & User Interface

Accessed via the sidebar (**Viral Swipe File**, `#tab-inspirations`), the interface provides instant filtering across the vaulted blueprints. Every count shown in the interface is read from `/api/inspirations` at load time and is never hardcoded:

```
+-------------------------------------------------------------------------------------------------------+
| PANEL HEADER: Viral Post Swipe File  |  [Badge: <N> Vaulted Blueprints, read from the API]           |
| Subtitle: Reverse-engineered viral hooks, structures, and pacing vaulted permanently from top creators|
| Search Bar: [🔍 Search blueprints by keyword, author, or topic...                                 ] |
+-------------------------------------------------------------------------------------------------------+
| 13 TOPIC CATEGORY FILTER CHIPS (#insp-topic-chips)                                                   |
| [All (<N>)]  [🤖 AI Agents]  [🏛️ Architecture]  [📡 Observability]  [⚙️ Systems]                     |
| [💼 B2B SaaS (26)]  [👑 Leadership (28)]  [✍️ Content (28)]  [📈 Growth (28)]  [🚀 Solopreneur (28)]    |
| [💻 CTO (29)]  [⚡ Productivity (29)]  [🎯 Consulting (30)]                                            |
+-------------------------------------------------------------------------------------------------------+
| SWIPE FILE GRID (#inspirations-container)                                                             |
|                                                                                                       |
| +--- Blueprint Card -------------------------+  +--- Blueprint Card -------------------------+        |
| | Topic: AI Agents          Author: Eric B.  |  | Topic: Systems Engineering  Author: Dan K.  |        |
| | "I hired an AI PM.                         |  | "EBITDA is an unreliable proxy for spend-  |        |
| | Didn't look at her resume once.            |  | able cash in boutique consulting M&A..."   |        |
| | Here's what I looked at instead..."        |  |                                            |        |
| |                                            |  | [⚡ Inject into Studio]  [📋 Copy Blueprint] |        |
| | [⚡ Inject into Studio]  [📋 Copy Blueprint] |  +--------------------------------------------+        |
| +--------------------------------------------+                                                        |
+-------------------------------------------------------------------------------------------------------+
```

---

## 2. Current Architecture & Accumulation Method

### How Posts Are Accumulated Today:

> **Status note.** This section previously stated that 356 blueprints were mirrored
> into SQLite from `studio/data/taplio_vault_archive_backup.json`. That mirroring
> was never implemented. The `inspirations` table is seeded with a small sample
> set from a literal list in `database.py`, and nothing reads the archive at
> runtime. The interface now reports whatever is actually present rather than a
> figure typed into the markup. See section 5 for the decision this raised.

* **Curated Offline Vault**: A sample set of blueprints is seeded into the local SQLite `inspirations` table at first launch.
* **100% Air-Gapped & Offline**: Unlike cloud tools that query remote APIs on every keystroke, the entire database is loaded into local memory upon startup, ensuring zero latency and zero external network calls.
* **Topic Taxonomies** (counts below describe the intended target shape, not current contents):
  1. **AI Agents**: Practical implementation stories, LLM orchestration patterns, evals, and agent workflows.
  2. **Enterprise Architecture**: Decoupling monoliths, event-driven designs, and bounded contexts.
  3. **Observability**: Distributed tracing, telemetry metrics, and MTTR reduction narratives.
  4. **Systems Engineering**: Zero-downtime migrations, database scaling, and state machine designs.
  5. **B2B SaaS**: Positioning, ARR growth frameworks, and outbound strategy.
  6. **Leadership**: Team empowerment, culture building, and hiring playbooks.
  7. **Content Strategy**: Hook formulas, dwell-time pacing, and audience growth mechanics.
  8. **Growth**: Funnel optimization, creator monetization, and distribution loops.
  9. **Solopreneur**: High-leverage workflows, automation, and boutique consulting.
  10. **CTO**: Technical debt management, executive communication, and vendor evaluations.
  11. **Productivity**: Deep work systems, calendar audits, and asynchronous operations.
  12. **Consulting**: Retainer packaging, advisory pricing, and client discovery.

### Interactivity & Authoring Controls:
* **`⚡ Inject into Studio`**: Copies the blueprint directly into the Studio Editor, allowing you to substitute your own metrics and case studies into a proven narrative skeleton.
* **`📋 Copy Blueprint`**: Copies the full post text to your clipboard.

---

## 3. Current Limitation: Absence of a Live Crawling Engine

Currently, the swipe file relies on historical vault snapshots and offline curated datasets. The local application does not yet include an automated, dynamic scraper or real-time feed-monitoring daemon running on localhost.

---

## 4. Strategic Architecture Plan: Agno Framework Autonomous Inbound Engine

To automate the continuous accumulation of outlier, viral LinkedIn posts, we are designing an automated inbounding pipeline built on the **Agno Framework** (formerly Phidata / Agno agentic framework).

### Proposed Agno Multi-Agent Pipeline Architecture:

```mermaid
graph TD
    subgraph LinkedInEcosystem [LinkedIn Platform]
        CreatorFeeds[High-Performing Creator Feeds]
        HashtagStreams[Topic Streams: #architecture #ai]
    end

    subgraph AgnoEngine [Agno Autonomous Multi-Agent Pipeline]
        HarvesterAgent[1. Agno Harvester Agent<br/>Scheduled Passive Ingestion<br/>via Chrome Session Context]
        FilterAgent[2. Virality Threshold Agent<br/>Filter: Impressions > 25K or Reposts > 50]
        HookClassifier[3. Hook Decomposition Agent<br/>Extract 10 Archetypes & Curiosity Gaps]
        SanitizerAgent[4. Template Abstraction Agent<br/>Strip PII, Extract Skeleton Blueprint]
    end

    subgraph LocalStorage [Local Air-Gapped Storage]
        SQLiteVault[(Local SQLite: swipe_file Table)]
        StudioUI[Studio Swipe File View]
    end

    LinkedInEcosystem --> HarvesterAgent
    HarvesterAgent --> FilterAgent
    FilterAgent --> HookClassifier
    HookClassifier --> SanitizerAgent
    SanitizerAgent --> SQLiteVault
    SQLiteVault --> StudioUI
```

### Key Components of the Planned Agno Pipeline:

1. **Agno Harvester Agent**:
   * Uses an authenticated local browser context (leveraging the existing Chrome Extension session cookies `li_at` and `JSESSIONID`).
   * Runs non-invasive, passive batch polling at scheduled intervals (e.g. daily at 2:00 AM) to avoid triggering LinkedIn bot detection.
2. **Virality & Outlier Gatekeeper Agent**:
   * Analyzes engagement velocity (comments-to-reactions ratio, repost velocity).
   * Discards low-engagement or generic updates, passing only statistically significant outliers (top 1% engagement).
3. **Hook Archetype Classifier Agent**:
   * Automatically inspects the first 140 characters of each post.
   * Labels the post with its underlying hook structure (Contrarian, Concrete Metric, Hard-Won Lesson, Tactical Playbook, etc.).
4. **Template Abstraction Agent**:
   * Strips out company-specific names and private identifiers.
   * Produces a fill-in-the-blank blueprint ready to be injected into the Studio Editor with 1 click.
5. **Direct Persistence into Local SQLite**:
   * Ingests new records directly into the local `swipe_file` table in SQLite, instantly expanding the studio's vaulted collection.
