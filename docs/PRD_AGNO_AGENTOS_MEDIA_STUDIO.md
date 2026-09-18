# Product Requirements Document (PRD)
# Inox Hydra: Enterprise Media Studio & Agno AgentOS Integration

**Document Version:** 3.0.0  
**Status:** In Review (Awaiting User Sign-off)  
**Author:** Antigravity AI Engine  
**Governing Standard:** `~/agno-agentos-rulebook-kit` DNA (P1 One-Home / P6 Anti-Pattern Memory / P7 Structure-as-Law)  
**Target Repository:** `dharmik136/inox-hydra` (LinkedIn Studio Enterprise)

---

## 1. Executive Summary & Problem Statement

### 1.1 Context & Background
Inox Hydra is an enterprise-grade LinkedIn creator studio running on a local, air-gapped architecture (`127.0.0.1:8000`). In previous iterations, a synthetic multi-slide carousel generator built with Python Pillow attempted to draw static text boxes onto 1080×1080 canvas slides. 

### 1.2 The Problem
1. **Lousy Carousel Generation**: Programmatic Pillow text rendering produces synthetic, low-fidelity slides that fail LinkedIn audience engagement benchmarks. Real LinkedIn thought leaders do not want automated box-drawing; they design custom multi-page PDF carousels, infographics, or high-definition MP4/WebM videos, which need a proper upload dropzone.
2. **Missing Native Media Uploads**: The post editor previously only provided a plain text box for media URLs, with no drag-and-drop file upload, no MIME validation, and no multi-image or PDF/video preview.
3. **Unorchestrated Image Generation**: AI image generation was absent or lacked structured steering. High-performing LinkedIn imagery requires deliberate parameter tuning (aspect ratios, corporate visual styles, lighting, color palettes) blended with user concept descriptions, executed through multi-stage prompt synthesis and backend rendering with visible real-time progress.
4. **Shallow Agent Utilization**: The Agno multi-agent framework was restricted to a single background CRM enrichment task rather than serving as the foundational intelligence backbone across the studio.

### 1.3 The Solution
1. **Terminate Pillow Carousel Generator**: Fully decommission the canvas carousel builder (`carousel_generator.py` and canvas deck editor).
2. **Unified Enterprise Media Dropzone**: Introduce a drag-and-drop / file-picker media area in the Web UI supporting:
   - Single & Multi-Images (`.png`, `.jpg`, `.jpeg`, `.webp`)
   - Native Multi-Slide Document Carousels (`.pdf` with page count and cover preview)
   - High-Definition Videos (`.mp4`, `.webm`)
3. **Structured AI Image Studio & Multi-Stage Orchestration**:
   - Guided option selectors (Aspect Ratio, Visual Style, Enterprise Color Mood, Lighting).
   - Natural language creative concept textarea.
   - Agentic prompt synthesizer (Agno `ImagePromptSynthesizerAgent`) producing negative constraints, camera specs, and composition rules.
   - Dual-mode generation backend (Gemini Imagen 3 / Pollinations high-res engine fallback / offline sandbox).
   - Live interactive progress bar (`1%` to `100%`) with phased milestones.
   - In-app preview with 1-click attachment to active post draft.
4. **Deep Agno AgentOS Rulebook Kit Integration**:
   - Implement the **P1 / P6 / P7 Structure-as-Law** architecture.
   - Deploy 4 bounded Agno agents across studio workflows:
     - `ImagePromptSynthesizerAgent`: Generative visual prompt engineering.
     - `LinkedInContentCopilotAgent`: Algorithmic post drafting, hook formulation, zero em-dash enforcement.
     - `CRMLeadEnrichmentAgent`: Warm inbound profile analysis and high-signal DM synthesis.
     - `SwipeFileHarvesterAgent`: Reverse-engineered viral post structural analysis.

---

## 2. Architectural Principles: Agno AgentOS DNA Standard

Every agent and workflow in this system adheres to the **P1 / P6 / P7 Structure-as-Law** standard:

```
+-------------------------------------------------------------------------+
|                       AGNO AGENTOS RULEBOOK DNA                         |
+-------------------------------------------------------------------------+
|  P1: One-Home-Per-Fact        | Bounded context per agent. Schema is    |
|                               | single source of truth in Pydantic.     |
+-------------------------------+-----------------------------------------+
|  P6: Anti-Pattern Memory      | Scar tissue rules: "What NOT to do"     |
|                               | explicitly checked before return.       |
+-------------------------------+-----------------------------------------+
|  P7: Structure-as-Law         | Typed Pydantic I/O models, machine gates|
|                               | and verifiable step-by-step recipes.    |
+-------------------------------------------------------------------------+
```

### 2.1 P1: One Home Per Fact (Single Source of Truth)
- **Database Schema**: All post media metadata is persisted in `posts.media_urls` as a JSON array with typed media metadata stored in SQLite `media_assets`.
- **Agent Registry**: A single centralized registry `studio/backend/agno_agentos/registry.py` defines all active agents, their assigned capabilities, system prompts, and output schemas. No duplicate prompt or agent definitions across files.

### 2.2 P6: Anti-Pattern Memory (Scar Tissue & Negative Constraints)
The platform enforces strict negative constraints:
- **NO Pillow synthetic carousels**: Do not draw text on canvas. Accept user-authored PDFs, images, or videos.
- **NO em-dashes (` - `, `–`, `--`)**: Strict zero em-dash compliance on all generated text, hooks, and DMs.
- **NO ungrounded claims or hallucinated metrics**: Ground intelligence on verified input or explicitly flag as inferred.
- **NO blocking generation calls**: Image generation and agent enrichment must run asynchronously with progressive status updates.
- **NO external telemetry egress**: Zero cloud egress of user data; local SQLite persistence on localhost.

### 2.3 P7: Structure-as-Law (Typed Contracts & Machine Gates)
- All agent inputs and outputs are defined as strict Pydantic v2 `BaseModel` classes with explicit type annotations.
- Every generation output is validated through a machine gate (e.g., verifying aspect ratio, checking forbidden vocabulary, checking length boundaries) before display or storage.

---

## 3. Modular Functional Specifications

### Section 1: Carousel Termination & Unified Media Dropzone

#### 1.1 Decommissioning
- Remove `carousel_generator.py` and its Pillow canvas rendering pipeline.
- Remove `mode-carousel-btn` and `carousel-deck-canvas` from `studio/frontend/index.html` and `studio/frontend/app.js`.
- Remove legacy carousel styles from `studio/frontend/styles.css`.

#### 1.2 Unified Media Dropzone (Web UI)
- Located directly below the post writing canvas in the Post Studio.
- Dual ingestion modes:
  1. **Drag-and-Drop Area**: Highlighted dropzone supporting direct drag-and-drop from Windows File Explorer or Mac Finder.
  2. **File Picker Button**: Clickable button allowing file selection.
- Supported Media Types & MIME Validation:
  - **Images**: PNG, JPG, JPEG, WEBP (up to 10MB per image, up to 9 images for multi-image posts).
  - **Carousels (PDF Documents)**: PDF files (up to 100MB). Extracted page count displayed on preview card.
  - **Videos**: MP4, WebM (up to 200MB). Video player preview with duration badge.
- Interactive Preview Bar:
  - Visual card rendering thumbnail, filename, file size, and format badge (`[PDF 12 Pages]`, `[VIDEO 0:45]`, `[IMAGE 1080×1080]`).
  - Single-click `✕ Remove` button to detach media.
  - Live Mobile Feed Simulator reflects the attached media in real time.

#### 1.3 Backend Media Upload API
- **Endpoint**: `POST /api/media/upload` (multipart/form-data)
- **Storage Directory**: `studio/assets/uploads/`
- **Response Contract**:
```json
{
  "status": "success",
  "media_type": "image" | "carousel" | "video",
  "url": "/assets/uploads/7f8a9b2c_infographic.png",
  "filename": "infographic.png",
  "size_bytes": 1048576,
  "dimensions": {"width": 1080, "height": 1080},
  "page_count": null,
  "duration_seconds": null
}
```

---

### Section 2: AI Image Generation Studio & Multi-Stage Orchestration

#### 2.1 UI Ergonomics & Control Hierarchy
Embedded within the Post Studio and accessible via AI Command Hub:
- **Toggle Mode**: `[ 📁 Upload Media ]` | `[ ✨ AI Image Studio ]`
- **Option Selectors**:
  - **Aspect Ratio**:
    - `1:1 Square` (1080×1080 - Best for single-image feed posts)
    - `4:5 Portrait` (1080×1350 - Maximum mobile feed real estate)
    - `16:9 Landscape` (1920×1080 - Ideal for technical diagrams & banner posts)
  - **Enterprise Visual Style**:
    - `Photorealistic Minimalist` (Clean studio photography, shallow depth of field)
    - `Enterprise Blueprint / Tech` (Technical schematic, isometric system architecture)
    - `Editorial Magazine` (Bloomberg/Forbes aesthetic, high-contrast corporate lighting)
    - `3D Glassmorphic / Clay` (Modern SaaS 3D iconographic style, vibrant frosted gradients)
    - `Hand-drawn Architectural Sketch` (Pen & ink with watercolor wash, whiteboard aesthetic)
  - **Color Palette & Tone**:
    - `Enterprise Navy & Cyan`
    - `Dark Obsidian & Electric Indigo`
    - `Minimal Monochrome (B&W)`
    - `Warm Corporate Editorial (Oatmeal & Forest)`
  - **Lighting & Ambience**:
    - `Studio Directional`
    - `Cinematic High Contrast`
    - `Soft Ambient Daylight`
    - `Cyber Neon Accent`
- **User Concept Input**:
  - Multi-line textarea for user's raw idea (e.g., *"A high-throughput distributed database handling 1M transactions per second with real-time stream processing"*).

#### 2.2 Orchestration Pipeline & Workflow
```
[User Options + Concept]
           │
           ▼
[ImagePromptSynthesizerAgent (Agno)] ───► Generates Master Generative Prompt
           │                              (composition, camera, lighting, negative constraints)
           ▼
[Async Task Orchestrator] ───────────────► Returns task_id, initializes progress at 1%
           │
           ├──► 01% - 20%: Prompt Analysis & Semantic Decomposition
           ├──► 21% - 50%: Model Latent Space Initialization & Diffusion
           ├──► 51% - 80%: High-Res Denoising & Surface Detailing
           ├──► 81% - 99%: Upscaling, Aspect Ratio Fitting & Local Asset Persistence
           └──► 100%: Complete! Local URL generated & preview served
```

#### 2.3 Interactive Live Progress Bar
- **UI Element**: Dynamic progress track with real-time percentage counter (`1%... 100%`) and animated shimmer.
- **Status Toast**: Descriptive live updates:
  - `"Synthesizing prompt engineering master blueprint..."`
  - `"Initializing latent diffusion pipeline..."`
  - `"Rendering 4K textures and corporate lighting..."`
  - `"Saving asset to local vault and verifying checksum..."`
- **Backend Endpoints**:
  - `POST /api/image/generate` -> Starts task, returns `task_id`.
  - `GET /api/image/progress/{task_id}` -> Streams/polls current percentage (`0-100`) and stage status.
  - `GET /api/image/result/{task_id}` -> Returns generated asset metadata.

#### 2.4 One-Click Post Attachment
- Once rendering reaches `100%`, the UI presents:
  - High-resolution preview image card.
  - Collapsible "Prompt Used" inspector.
  - **`[ ✍️ Attach to Active Draft ]` Button**: Instantly sets this image as the active draft's media attachment, updating the Mobile Feed Simulator immediately.
  - **`[ 💾 Download Asset ]` Button**: Saves local file to creator's computer.

---

### Section 3: Deep Agno Framework & AgentOS Rulebook Kit Integration

#### 3.1 Agno AgentOS Architecture (`studio/backend/agno_agentos/`)
We organize all agents under a clean, unified Agno AgentOS package:
```
studio/backend/agno_agentos/
├── __init__.py               # Package exports & versioning
├── contracts.py              # Pydantic v2 schemas for all inputs & outputs (P1/P7)
├── scar_tissue.py            # Anti-pattern validators & negative rulebook gates (P6)
├── registry.py               # Central Agent & Workflow Registry (P1 single source of truth)
├── orchestrator.py           # Multi-agent coordinator with dual-mode execution
└── agents/
    ├── __init__.py
    ├── image_prompt_agent.py # ImagePromptSynthesizerAgent
    ├── content_copilot_agent.py # LinkedInContentCopilotAgent (hooks, drafting, formatting)
    ├── crm_enrichment_agent.py  # LeadResearchAgent & IcebreakerAgent
    └── swipe_harvester_agent.py # SwipeFileHarvesterAgent (viral pattern extractor)
```

#### 3.2 Agent Contracts & Capabilities

##### Agent A: `ImagePromptSynthesizerAgent`
- **Role**: Transforms creator concept descriptions and selected styling tags into high-performance image prompts.
- **Input Contract**:
  - `concept: str`
  - `aspect_ratio: str` (`1:1` | `16:9` | `4:5`)
  - `visual_style: str`
  - `color_palette: str`
  - `lighting: str`
- **Output Contract (`SynthesizedImagePrompt`)**:
  - `master_prompt: str` (expanded descriptive prompt)
  - `negative_prompt: str` (e.g. "blurry, distorted text, low quality, cartoonish, watermark")
  - `technical_params: dict` (`width`, `height`, `seed`, `sampler`)
  - `rationale: str`

##### Agent B: `LinkedInContentCopilotAgent`
- **Role**: Assists in crafting viral hooks, re-formatting technical copy for LinkedIn mobile feed dwell time, and enforcing algorithmic safety.
- **Input Contract**:
  - `raw_content: str`
  - `target_audience: str`
  - `post_format: str` (`contrarian_take`, `technical_deep_dive`, `framework_breakdown`, `story_lesson`)
  - `attached_media_type: Optional[str]` (`image`, `carousel`, `video`, `none`)
- **Output Contract (`CopilotDraftResponse`)**:
  - `optimized_content: str` (with pre-fold hook, line breaks, mathematical bold highlights)
  - `hook_variants: List[str]` (5-10 scroll-stopping variations)
  - `dwell_time_score: int` (estimated dwell time in seconds)
  - `fold_safe: bool` (hook under 180 characters)
  - `media_callout: str` (e.g., "Swipe left for the architecture diagram ➡️")

##### Agent C: `CRMLeadEnrichmentAgent` & `IcebreakerAgent`
- **Role**: Ingests commenter/reactor profiles, maps organizational scale, infers tech stack, and synthesizes 3 contextual DM conversation starters.
- **P6 Enforcement**: Strict zero em-dashes, no generic "loved your post" flattery, hyper-specific technical angles.

##### Agent D: `SwipeFileHarvesterAgent`
- **Role**: Analyzes high-engagement posts from the 356-item viral swipe file vault.
- **Output Contract**:
  - `hook_archetype: str` (`curiosity_gap`, `counter_intuitive`, `data_revelation`, `personal_confession`)
  - `structural_blueprint: str`
  - `variable_placeholders: List[str]`

---

## 4. Database Schema Migration

To support persistent media assets and generation tasks without cloud leaks:

### 4.1 `media_assets` Table (New)
```sql
CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    media_type TEXT NOT NULL,          -- 'image', 'carousel', 'video'
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    dimensions TEXT,                   -- '{"width": 1080, "height": 1080}'
    page_count INTEGER,                -- For PDF carousels
    duration_seconds REAL,             -- For MP4/WebM videos
    prompt TEXT,                       -- If generated via AI
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 `generation_tasks` Table (New)
```sql
CREATE TABLE IF NOT EXISTS generation_tasks (
    task_id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',     -- 'pending', 'processing', 'completed', 'failed'
    progress_percent INTEGER DEFAULT 1,
    status_message TEXT,
    result_url TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 `posts` Table Compatibility
Existing column `media_urls` is maintained for full backward compatibility, storing JSON array strings of media URLs (e.g., `'["/assets/uploads/diagram.pdf"]'`).

---

## 5. User Experience & Ergonomics Correlation Matrix

| Touchpoint | Media Dropzone | AI Image Studio | Agno AgentOS |
|---|---|---|---|
| **Post Drafting** | Shows attached media badge & thumbnail in editor. | Accessible via 1-click tab toggle in editor. | Provides real-time hook & media CTA recommendations. |
| **Mobile Feed Simulator** | Dynamically renders image / PDF cover / video player. | Displays generated image in simulator as soon as rendered. | Renders pre-fold hook with glow indicator. |
| **Publishing / Scheduling** | Transmits local media paths to LinkedIn Voyager API. | Generated images stored locally in `assets/generated/`. | Formats post metadata according to LinkedIn algorithm rules. |
| **Error / Offline State** | Graceful drag-and-drop file rejection on invalid MIME. | Seamless fallback to Pollinations / local mock if offline. | Deterministic offline engine runs without API keys. |

---

## 6. Verification & Test Plan

1. **Automated Unit Tests**:
   - `tests/test_media_dropzone.py`: Tests file uploads for image, PDF, and video; verifies MIME rejection for disallowed files; verifies file persistence in `studio/assets/uploads/`.
   - `tests/test_image_studio.py`: Tests prompt synthesis, async task creation, progressive polling (`1%` to `100%`), and image asset saving.
   - `tests/test_agno_agentos.py`: Validates P1/P6/P7 compliance, Pydantic schema validation, scar tissue em-dash scrubbing, and agent registry resolution.
2. **End-to-End Browser Verification**:
   - Test drag-and-drop media upload in Web UI on `http://127.0.0.1:8000`.
   - Test AI Image Studio generation with progress bar animation and 1-click attachment to active post draft.
   - Verify Mobile Feed Simulator accurately displays attached media.
   - Verify that the old Pillow carousel canvas has been completely removed.
3. **Regression Safety**:
   - Ensure all 31 existing pytest tests pass without regression.
