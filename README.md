# Inox Hydra  -  LinkedIn Studio Enterprise (Local Creator Engine)

> **A 100% self-hosted, air-gapped, privacy-first alternative to $199/month SaaS creator tools (like Taplio Pro), running entirely on your local machine with zero cloud data egress.**

[![Localhost](https://img.shields.io/badge/Localhost-127.0.0.1%3A8000-0ea5e9.svg)](http://127.0.0.1:8000)
[![Database](https://img.shields.io/badge/Database-SQLite%20(WAL%20Mode)-22c55e.svg)](#architecture)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-Bring--Your--Own--AI%20(OpenAI%20%7C%20Gemini%20%7C%20Claude%20%7C%20Ollama)-a855f7.svg)](#bring-your-own-ai-byo-ai-multi-model-architecture)
[![Security](https://img.shields.io/badge/Security-Zero%20Cloud%20Egress-emerald.svg)](#zero-egress-security-guarantee)
[![License](https://img.shields.io/badge/License-Proprietary-slate.svg)](#)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF.svg)](#)

---

## 🌟 Executive Product Overview

**LinkedIn Studio Enterprise** is a high-performance content strategy, analytics intelligence, and lead pipeline operating system engineered for enterprise architects, founders, and content practitioners.

Most commercial creator platforms charge upwards of **$199/month**, store your personal drafts on external cloud databases, lock you into proprietary vendor models, and risk account flags through aggressive automated scraping. LinkedIn Studio eliminates third-party SaaS dependencies by running a **strictly local stack** with passive session observation, zero bot footprint, and a pluggable **Bring-Your-Own-AI (BYO-AI)** architecture.

---

## 🚀 Key Features & Capabilities

| Module | Taplio $199/mo Pro Equivalent | Our Local Implementation | Privacy & Execution Guarantee |
| :--- | :--- | :--- | :--- |
| **Native Media Dropzone** | AI Document Carousels | Drag-and-drop native ingestion for multi-page PDF Carousels, 4K Images, and MP4/WebM Videos | 100% Local file ingestion, zero cloud egress |
| **Post Studio & Simulator** | Post Composer | Real-time mobile feed simulator with mobile cutoff detection (~140 chars) | In-memory instant rendering |
| **10× Viral Re-Hooker** | Hook Generator | 10 high-retention hook archetypes with real-time fold safety analysis | Deterministic scoring + BYO-AI (OpenAI / Gemini / Claude / Ollama) |
| **5-Style Repurposer** | Content Repurposer | Converts raw notes into 5 distinct viral LinkedIn frameworks | Zero cloud LLM token egress required |
| **Algorithm Safety Auditor** | Virality Score | Real-time audit detecting outbound URL reach penalties (-40%), hashtag spam, and dwell time | Local linguistic regex engine |
| **Leads & Engagers CRM** | Lead Database | Pipeline management (*New*, *Outreach Sent*, *Connected*, *Meeting Booked*) with 1-click tailored DMs | Encrypted local SQLite (`linkedin_studio.db`) |
| **Smart Queue & Scheduler** | Auto-Scheduler | Local background thread managing peak engagement time slots (e.g. 5:30 PM IST) | Zero external cron dependencies |
| **Bring-Your-Own-AI Hub** | AI Copilot | Multi-model gateway (OpenAI, Gemini, Claude, Groq, Ollama) + Antigravity Local Engine | Verified live connection via CLI or UI; local SQLite encrypted vault |
| **Vector Carousel Engine** | Content Design Studio | 4:5 & 1:1 Swiss vector SVG slides ('Plus Jakarta Sans', 'Inter', 'JetBrains Mono') | Pure vector SVG, zero cloud rendering |
| **FTS5 Playbook Search** | Knowledge Base | SQLite FTS5 BM25 search across 401 strategy & technical sections (<15ms) | Local SQLite virtual table, zero latency |
| **Gaussian Rate Limiter** | Anti-Detection Shield | Human-like Gaussian token bucket pacing with single-writer serialization | Mathematically clamped, passive observer |

---

## 🏗️ Repository Architecture

```text
inox-hydra/
├── studio/                     # The application package
│   ├── __version__.py          # Single source of version truth for every surface
│   ├── cli.py                  # Support toolkit: doctor, backup, restore, export
│   ├── backend/                # FastAPI services
│   │   ├── app.py              # API router, lifespan manager & static server
│   │   ├── paths.py            # Resolves ALL user state, outside the install dir
│   │   ├── migrations.py       # Forward-only schema ledger (PRAGMA user_version)
│   │   ├── database.py         # Frozen schema baseline & WAL configuration
│   │   ├── support.py          # Redacted diagnostics, backup, restore, export
│   │   ├── updates.py          # Opt-in update check, off by default
│   │   ├── vault.py            # DPAPI encryption at rest for session tokens
│   │   ├── ingress.py          # Telegram capture, outbound long-polling only
│   │   ├── crm.py              # Reverse CRM & deterministic ICP scoring
│   │   ├── event_bus.py        # SSE hub with replay buffer
│   │   ├── intelligence_sync.py # ETag-cached CDN sync for hook archetypes
│   │   ├── docs_engine.py      # SQLite FTS5 index over bundled documentation
│   │   └── agno_agentos/       # Multi-agent orchestrator & BYO-AI gateway
│   ├── core/rate_limiter.py    # Gaussian jitter governor & single-writer actor
│   ├── frontend/               # Single-page studio interface (no build step)
│   └── extension/              # Chrome Extension (Manifest V3)
├── tools/                      # Build and release tooling
│   ├── build_portable.py       # Produces the portable Windows ZIP
│   ├── smoke_portable.py       # Boots the artifact with a scrubbed environment
│   ├── verify_package.py       # Builds, installs and boots a wheel in isolation
│   ├── prepare_package.py      # Stages bundled docs into the package
│   └── sync_version.py         # Propagates the version to every surface
├── tests/                      # 260 automated tests
├── docs/                       # Documentation suite and the master plan
├── release/latest.json         # Manifest read by opt-in update checks
├── pyproject.toml              # Packaging metadata and dependencies
├── launch_studio.bat           # 1-click Windows launcher (source checkout)
└── studio_cli.py               # BYO-AI provider configuration
```

> Your drafts, leads, analytics and media are **not** stored here. They live in
> `%LOCALAPPDATA%\InoxHydra`, deliberately outside the application folder, so
> replacing it with a newer version never touches your work. See
> [`docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md`](docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md).

---

## 📦 Install

### Option A: Download and run (recommended, no Python required)

1. Download **`InoxHydra-2.5.0-win64.zip`** from [Releases](https://github.com/dharmik136/inox-hydra/releases/latest).
2. Extract it anywhere. A USB stick is fine.
3. Double-click **`InoxHydra.bat`**.

The studio opens in its own window. No installer, no administrator rights, and
no Python installation: the ZIP embeds its own CPython runtime.

**To upgrade**, delete the folder and extract the newer one. Your data lives in
`%LOCALAPPDATA%\InoxHydra`, so it is untouched, and any database schema changes
are applied automatically on first launch with a timestamped backup taken first.

### Option B: Run from source (developers)

```bash
git clone https://github.com/dharmik136/inox-hydra.git
cd inox-hydra
pip install -r requirements.txt
python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000
```

A source checkout keeps its state in `studio/data/` rather than your user
profile, so each clone is self-contained. Set `INOX_HYDRA_HOME` to override.

---

## 🛠️ Support Toolkit

Everything runs locally, so nobody can see errors on your machine. The CLI is
how you look after your own installation:

```bash
python -m studio.cli doctor --bundle   # health report, safe to post publicly
python -m studio.cli backup            # snapshot database and media
python -m studio.cli restore <zip>     # roll back, snapshots current state first
python -m studio.cli export            # take your content elsewhere, JSON or CSV
python -m studio.cli reset             # fix a broken setup, keeping your content
python -m studio.cli migrate --dry-run # show pending schema migrations
python -m studio.cli update status     # update checks are OFF by default
```

In the portable build these are reachable as `InoxHydra-CLI.bat <command>`.

The diagnostics bundle **redacts your LinkedIn session and any API keys by
allowlist**, so it is safe to attach to a public issue. Open it in a text editor
and confirm for yourself.

**Update checks are opt-in and off by default.** Nothing is sent anywhere unless
you run `update enable`, and even then the check only reads a small version file
and tells you whether a newer release exists. It never installs anything itself.

---

## ⚡ Configuration & CLI Management

### 1. Configure Your AI Provider (Bring-Your-Own-AI)
Inox Hydra is provider-agnostic and never locks you into a single vendor. Configure your preferred model using the CLI:

```bash
# View all supported providers (OpenAI, Gemini, Claude, Ollama, Groq, etc.)
python studio_cli.py ai list-providers

# Configure an AI provider (actively tests and verifies connection before saving)
python studio_cli.py ai configure --provider openai --api-key "sk-..." --model gpt-4o

# Or configure Google Gemini
python studio_cli.py ai configure --provider gemini --api-key "AIzaSy..." --model gemini-2.5-flash

# Or connect a 100% offline local model via Ollama (zero API key required)
python studio_cli.py ai configure --provider ollama --model llama3:latest

# Check status and latency of the active AI configuration
python studio_cli.py ai status
python studio_cli.py ai test

# Reset to 100% offline local deterministic engine anytime
python studio_cli.py ai reset
```

> [!IMPORTANT]
> The CLI performs an **active ping verification**. If an API key is invalid or an endpoint is unreachable, the CLI will reject the configuration, display the exact error code, and leave existing settings untouched.

### 2. Launch Desktop App (Windows)
Double-click [`launch_studio.bat`](launch_studio.bat) or the **LinkedIn Studio** desktop shortcut.

### 3. Manual Server Startup
```bash
# Start backend server
python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000

# Open in browser
start http://127.0.0.1:8000
```

---

## 🤖 Bring-Your-Own-AI (BYO-AI) & Multi-Model Architecture

Inox Hydra is designed as an open, model-agnostic creator studio. You can seamlessly switch between providers:

1. **Google Gemini**:
   * Models: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`, `imagen-3.0-generate-002`.
   * High-speed contextual generation, multi-angle icebreakers, and native Imagen 3 rendering.
2. **OpenAI**:
   * Models: `gpt-4o`, `gpt-4o-mini`, `o3-mini`, `dall-e-3`.
   * State-of-the-art copywriting, viral hook formulation, and DALL-E 3 image generation.
3. **Anthropic Claude**:
   * Models: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`.
   * Long-form practitioner essays, technical nuance, and architecture breakdowns.
4. **Local Offline LLMs (Ollama / vLLM)**:
   * Models: `llama3`, `mistral`, `deepseek-r1`, `qwen2.5`.
   * 100% local hardware inference with zero cloud data egress.
5. **Antigravity Deterministic Local Engine (Zero-Egress Default)**:
   * Operates with 0ms latency when completely offline with zero API keys or dependencies.
   * Generates structured archetypes, enforces **mathematical sans-bold Unicode**, and **strictly eliminates em-dashes (` - `)**.

---

## 🔒 Zero-Egress Security Guarantee

* **Strict Localhost Binding**: The FastAPI backend binds exclusively to `127.0.0.1`.
* **Zero Telemetry**: No third-party analytics trackers, no tracking pixels, no external SaaS calls.
* **Encrypted Local Storage**: Drafts, prospect leads, analytics, and settings remain on your local NVMe drive.
* **Anti-Bot Passive Extraction**: Avoids monkey-patching `window.fetch` or modifying browser prototypes, making sync completely undetectable.

---

## 📖 Documentation Suite

* [**Enterprise Master Manual**](docs/ENTERPRISE_USAGE.md): Complete operational guide to all 6 studio modules.
* [**Module 01: Studio & Editor**](docs/modules/01_STUDIO_AND_EDITOR.md): Topbar telemetry, dynamic fold tracker, 1080×1080 PDF carousels, and 6-dimension algorithmic audit.
* [**Module 02: Schedule & Queue**](docs/modules/02_SCHEDULE_AND_QUEUE.md): Publishing cadence, peak smart slots, and local background dispatcher.
* [**Module 03: Inbound CRM**](docs/modules/03_INBOUND_CRM.md): Pipeline lifecycle, column dictionary, search/filter, and 3-style contextual DM generator.
* [**Module 04: Viral Swipe File**](docs/modules/04_VIRAL_SWIPE_FILE.md): 356 curated blueprints, 13 topic categories, and Agno Framework autonomous inbound roadmap.
* [**Module 05: Creator Analytics**](docs/modules/05_ANALYTICS.md): Direct LinkedIn session ingestion, growth deltas, Chart.js time-series, and demographics.
* [**Module 06: AI Command Hub**](docs/modules/06_AI_COMMAND.md): Dual-mode Gemini 2.5 Flash + Antigravity local engine, prompt presets, and direct Studio transfer.
* [**Architecture & Security Blueprint**](docs/ARCHITECTURE.md): Deep-dive into data flow, SQLite WAL concurrency, and threat model.
* [**Dual-Mode AI Engine Guide**](docs/AI_ENGINE.md): Gemini 2.5 Flash setup, local prompt engineering, and mathematical bolding standards.
* [**Chrome Extension & Passive Sync**](docs/EXTENSION_AND_SYNC.md): Manifest V3 token bridge and passive commenter extraction.
* [**Getting Started Guide**](docs/GETTING_STARTED.md): Step-by-step setup, desktop shortcuts, and initial configuration.
* [**REST API Reference**](docs/API_REFERENCE.md): Full OpenAPI specifications for all 20+ backend endpoints.
* [**Interactive In-App Docs Hub**](http://127.0.0.1:8000): Available directly within the Studio UI under the **Docs & Playbook** tab.
