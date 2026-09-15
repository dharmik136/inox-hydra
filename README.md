# Inox Hydra — LinkedIn Studio Enterprise (Local Creator Engine)

> **A 100% self-hosted, air-gapped, privacy-first alternative to $199/month SaaS creator tools (like Taplio Pro), running entirely on your local machine with zero cloud data egress.**

[![Localhost](https://img.shields.io/badge/Localhost-127.0.0.1%3A8000-0ea5e9.svg)](http://127.0.0.1:8000)
[![Database](https://img.shields.io/badge/Database-SQLite%20(WAL%20Mode)-22c55e.svg)](#architecture)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Gemini%202.5%20Flash%20%2B%20Antigravity-a855f7.svg)](#dual-mode-ai-engine)
[![Security](https://img.shields.io/badge/Security-Zero%20Cloud%20Egress-emerald.svg)](#zero-egress-security-guarantee)
[![License](https://img.shields.io/badge/License-Proprietary-slate.svg)](#)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF.svg)](#)

---

## 🌟 Executive Product Overview

**LinkedIn Studio Enterprise** is a high-performance content strategy, analytics intelligence, and lead pipeline operating system engineered for enterprise architects, founders, and content practitioners.

Most commercial creator platforms charge upwards of **$199/month**, store your personal drafts on external cloud databases, and risk account flags through aggressive automated scraping. LinkedIn Studio eliminates third-party SaaS dependencies by running a **strictly local stack** with passive session observation and zero bot footprint.

---

## 🚀 Key Features & Capabilities

| Module | Taplio $199/mo Pro Equivalent | Our Local Implementation | Privacy & Execution Guarantee |
| :--- | :--- | :--- | :--- |
| **Carousel PDF Builder** | AI Document Carousels | Native Python `Pillow` 1080×1080 multi-page PDF generator with 3 curated themes | 100% Local rendering, zero cloud APIs |
| **Post Studio & Simulator** | Post Composer | Real-time mobile feed simulator with mobile cutoff detection (~140 chars) | In-memory instant rendering |
| **10× Viral Re-Hooker** | Hook Generator | 10 high-retention hook archetypes with real-time fold safety analysis | Deterministic scoring + Gemini 2.5 Flash |
| **5-Style Repurposer** | Content Repurposer | Converts raw notes into 5 distinct viral LinkedIn frameworks | Zero cloud LLM token egress required |
| **Algorithm Safety Auditor** | Virality Score | Real-time audit detecting outbound URL reach penalties (-40%), hashtag spam, and dwell time | Local linguistic regex engine |
| **Leads & Engagers CRM** | Lead Database | Pipeline management (*New*, *Outreach Sent*, *Connected*, *Meeting Booked*) with 1-click tailored DMs | Encrypted local SQLite (`linkedin_studio.db`) |
| **Smart Queue & Scheduler** | Auto-Scheduler | Local background thread managing peak engagement time slots (e.g. 5:30 PM IST) | Zero external cron dependencies |
| **AI Command Hub** | AI Copilot | Dual-mode Gemini 2.5 Flash cloud API + Antigravity Deterministic Local Engine | Configurable API key stored in local SQLite |

---

## 🏗️ Repository Architecture

```text
Linkedin strategy/
├── assets/                     # Master 4K visual assets and infographics
│   ├── motadata_to_enterprise_4k_flawless.jpg # Master 4K creative
│   ├── ai_leadership_gestured_4k.jpg
│   └── telemetry_to_enterprise_concept.jpg
├── docs/                       # Comprehensive enterprise documentation
│   ├── GETTING_STARTED.md      # Installation, desktop app launch & quickstart
│   ├── ARCHITECTURE.md         # System design, data flow, WAL mode & security
│   ├── AI_ENGINE.md            # Gemini 2.5 Flash + Antigravity dual-mode specification
│   ├── EXTENSION_AND_SYNC.md   # Chrome MV3 session bridge & anti-detection design
│   ├── ENTERPRISE_USAGE.md     # Feature-by-feature operational guide
│   └── API_REFERENCE.md        # Complete OpenAPI / REST endpoint schemas
├── legacy_connectors/          # Archived standalone scripts & third-party connectors
│   ├── taplio_cli.py
│   └── taplio_mcp_server.py
├── studio/                     # Core application platform
│   ├── backend/                # Modular Python FastAPI services
│   │   ├── app.py              # Main API router, lifespan manager & static server
│   │   ├── database.py         # SQLite connection provider & WAL initialization
│   │   ├── formatters.py       # Mathematical sans-bold & punctuation scrubbers
│   │   ├── carousel_generator.py # 1080x1080 Pillow PDF carousel engine
│   │   ├── repurposer.py       # Dual-Mode AI engine & 10x hook generator
│   │   ├── leads.py            # Relationship CRM & personalized DM builder
│   │   ├── linkedin_client.py  # Passive session bridge & telemetry ingestor
│   │   ├── scheduler.py        # Background thread queue dispatcher
│   │   └── test_studio_backend.py # Comprehensive 6-suite verification test
│   ├── frontend/               # Single-page web studio interface
│   │   ├── index.html          # Semantic application layout & navigation
│   │   ├── styles.css          # Curated dark-slate design system
│   │   └── app.js              # Reactive UI controller & API bridge
│   ├── extension/              # Chrome Extension (Manifest V3)
│   │   ├── manifest.json       # Extension configuration & permissions
│   │   ├── background.js       # Background cookie synchronization & alarms
│   │   ├── content.js          # Passive DOM observer for commenter CRM capture
│   │   ├── popup.html / .js    # Quick status popup
│   │   └── sidepanel.html / .js # Embedded composer & sidepanel injection
│   └── data/                   # Local encrypted database
│       └── linkedin_studio.db  # SQLite database in WAL journal mode
├── launch_studio.bat           # 1-Click native Windows desktop app launcher
├── create_desktop_shortcut.vbs # Generates 'LinkedIn Studio.lnk' on desktop
├── strategy_playbook.md        # Content pillars, positioning & authority framework
└── README.md                   # This document
```

---

## ⚡ Quick Start

### 1. One-Click Desktop App (Windows)
Double-click [`launch_studio.bat`](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/launch_studio.bat) or the **LinkedIn Studio** desktop shortcut.

This automatically:
1. Verifies if the backend daemon is active on port 8000 (starts it minimized if needed).
2. Launches Google Chrome in borderless App Mode (`--app="http://127.0.0.1:8000"`), providing a distraction-free, native desktop experience without address bars or browser tabs.

### 2. Manual CLI Startup
```bash
# Start backend server
python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000

# Open in browser
start http://127.0.0.1:8000
```

### 3. Chrome Extension Setup
1. Open Google Chrome and navigate to `chrome://extensions`.
2. Toggle on **Developer mode** (top right).
3. Click **Load unpacked** and select the [`studio/extension/`](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/studio/extension/) folder.
4. Your active LinkedIn cookies will passively synchronize to `127.0.0.1:8000`, and commenters on your posts will automatically populate your local CRM pipeline.

---

## 🤖 Dual-Mode AI Engine

The studio utilizes a resilient dual-mode architecture:

1. **Live Google Gemini 2.5 Flash**:
   * Activated when you enter an optional `GEMINI_API_KEY` in the AI Command Center or set it as an environment variable.
   * Delivers lightning-fast, high-signal post generation, bespoke 10x hook variations, and personalized CRM outreach scripts.
   * Stored strictly in your local SQLite `settings` table.
2. **Antigravity Deterministic Local Engine**:
   * Operates with 0ms latency even when completely offline with zero API keys.
   * Generates structured archetypes, enforces **proper mathematical sans-bold Unicode**, and **strictly eliminates em-dashes (`—`)**.

---

## 🔒 Zero-Egress Security Guarantee

* **Strict Localhost Binding**: The FastAPI backend binds exclusively to `127.0.0.1`.
* **Zero Telemetry**: No third-party analytics trackers, no tracking pixels, no external SaaS calls.
* **Encrypted Local Storage**: Drafts, prospect leads, analytics, and settings remain on your local NVMe drive.
* **Anti-Bot Passive Extraction**: Avoids monkey-patching `window.fetch` or modifying browser prototypes, making sync completely undetectable.

---

## 📖 Documentation Suite

* [**Enterprise Master Manual**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/ENTERPRISE_USAGE.md): Complete operational guide to all 6 studio modules.
* [**Module 01: Studio & Editor**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/01_STUDIO_AND_EDITOR.md): Topbar telemetry, dynamic fold tracker, 1080×1080 PDF carousels, and 6-dimension algorithmic audit.
* [**Module 02: Schedule & Queue**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/02_SCHEDULE_AND_QUEUE.md): Publishing cadence, peak smart slots, and local background dispatcher.
* [**Module 03: Inbound CRM**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/03_INBOUND_CRM.md): Pipeline lifecycle, column dictionary, search/filter, and 3-style contextual DM generator.
* [**Module 04: Viral Swipe File**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/04_VIRAL_SWIPE_FILE.md): 356 curated blueprints, 13 topic categories, and Agno Framework autonomous inbound roadmap.
* [**Module 05: Creator Analytics**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/05_ANALYTICS.md): Direct LinkedIn session ingestion, growth deltas, Chart.js time-series, and demographics.
* [**Module 06: AI Command Hub**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/modules/06_AI_COMMAND.md): Dual-mode Gemini 2.5 Flash + Antigravity local engine, prompt presets, and direct Studio transfer.
* [**Architecture & Security Blueprint**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/ARCHITECTURE.md): Deep-dive into data flow, SQLite WAL concurrency, and threat model.
* [**Dual-Mode AI Engine Guide**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/AI_ENGINE.md): Gemini 2.5 Flash setup, local prompt engineering, and mathematical bolding standards.
* [**Chrome Extension & Passive Sync**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/EXTENSION_AND_SYNC.md): Manifest V3 token bridge and passive commenter extraction.
* [**Getting Started Guide**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/GETTING_STARTED.md): Step-by-step setup, desktop shortcuts, and initial configuration.
* [**REST API Reference**](file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/docs/API_REFERENCE.md): Full OpenAPI specifications for all 20+ backend endpoints.
* [**Interactive In-App Docs Hub**](http://127.0.0.1:8000): Available directly within the Studio UI under the **Docs & Playbook** tab.
