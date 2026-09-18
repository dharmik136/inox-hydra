# Project Prudent  -  Upstream Architectural Handoff for LinkedIn Strategy Builder Agent

> **Source**: `Project Prudent` (Architectural & Product Research Laboratory)  
> **Destination**: `Linkedin strategy` (Production Application Repository)  
> **Target Agent**: LinkedIn Strategy Implementation & Core Engineering Agent

---

## 🎯 What is This Folder?

This directory (`docs/prudent_handoff/`) is the **official upstream contract and handoff bridge** between:
1. **The Project Prudent Agent** (Chief Architect, Product Strategist & PRD Author).
2. **The LinkedIn Strategy Builder Agent** (You: The Core Software Engineer, Frontend/Backend Developer & Runtime Implementer).

### The Golden Separation of Concerns:
* **Project Prudent Agent**: Does the deep research, reverse-engineers platform APIs, calculates unit economics, formulates mathematical models (ICP scoring, mobile fold pacing), writes the PRDs, and establishes the anti-slop constraints.
* **LinkedIn Strategy Agent**: Picks up these implementation briefs, translates them into the production codebase (`studio/frontend/`, `studio/backend/`, Chrome extension), and builds the functional software.

---

## 🧭 Daily Handoff Structure

Every day of the 17-day sprint will have an implementation brief placed in this directory:

```text
Linkedin strategy/docs/prudent_handoff/
├── README_AGENT_INSTRUCTIONS.md       # This file (The operational contract)
├── DAY_01_IMPLEMENTATION_SPEC.md     # Day 01: SQLite WAL, Telegram Ingress, Native Sched, Reverse CRM
├── DAY_02_IMPLEMENTATION_SPEC.md     # Day 02: (Upcoming: Passive Telemetry & Anti-Scraping)
└── ...
```

---

## 📋 How the Builder Agent Should Execute Each Spec:

1. Open `DAY_XX_IMPLEMENTATION_SPEC.md`.
2. Review the **Data Schemas & Pragmas** and apply any migrations to `linkedin_studio.db`.
3. Implement the **Core Logic & Endpoints** as specified in the brief.
4. Verify the **Anti-Slop Guardrails** (Strict Zero Em-Dash rule, 140-char mobile fold line, deterministic math over LLM tokens).
5. Run the provided verification test cases to confirm implementation compliance.

---

## 🔗 Master Upstream Documentation Links (Project Prudent)

For full architectural deep dives, refer to the master repository at:
`c:\Users\remoteadmin\Downloads\Ultimate\THE INDIA STORY\Project Prudent\`
- Master PRD: [`docs/prd/PRD_01_SOVEREIGN_FOUNDATIONS_AND_CAPTURE.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/docs/prd/PRD_01_SOVEREIGN_FOUNDATIONS_AND_CAPTURE.md)
- Decision Log: [`docs/decisions/DECISION_LOG.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/docs/decisions/DECISION_LOG.md)
- Software Philosophies & Latency: [`architecture/SOFTWARE_PHILOSOPHIES_AND_DATA_SOVEREIGNTY.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/architecture/SOFTWARE_PHILOSOPHIES_AND_DATA_SOVEREIGNTY.md)
- LinkedIn Native Scheduling: [`architecture/LINKEDIN_NATIVE_SCHEDULER_SPEC.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/architecture/LINKEDIN_NATIVE_SCHEDULER_SPEC.md)
- Offline Voice Architecture: [`architecture/OFFLINE_VOICE_TRANSCRIPTION_SPEC.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/architecture/OFFLINE_VOICE_TRANSCRIPTION_SPEC.md)
- 18-Year SaaS Taxonomy: [`research/06_SAAS_COMPETITIVE_LANDSCAPE.md`](file:///c:/Users/remoteadmin/Downloads/Ultimate/THE%20INDIA%20STORY/Project%20Prudent/research/06_SAAS_COMPETITIVE_LANDSCAPE.md)
