# LinkedIn Studio Enterprise - Complete UI/UX Design System & Architectural Blueprint
**Project Name**: `Linkedin strategy` (Inox Hydra / LinkedIn Studio Enterprise)  
**Document**: `DESIGN.md` / `linkedin_strategy_design.md`  
**Target Audience**: AI Agents, UI/UX Engineers, Product Designers  
**Version**: 2.5 (High-Contrast Editorial & Minimalist Authority Design System)  
**Compliance**: Strict Zero Em-Dash (` - `) Rule; 100% Local Air-Gapped Engine (Port 8000)

---

## 1. Executive Summary & Design Philosophy

LinkedIn Studio Enterprise is an air-gapped, high-performance desktop workstation designed for elite tech executives, enterprise software architects, and engineering leaders. The UI is built entirely using **Vanilla HTML5, CSS3, and JavaScript** without external CSS frameworks (no Tailwind runtime bloat), ensuring instantaneous DOM updates, sub-16ms rendering, and complete sovereign data privacy.

### Core Aesthetic Pillars
1. **Minimalist Authority Editorialism**: Clean, distraction-free surfaces inspired by Swiss typographic design, Bloomberg Terminal precision, and Linear/Vercel modern dark-mode luxury.
2. **Dual Identity Realism**: Real-time dual viewport consisting of an unconstrained authoring canvas alongside a pixel-perfect mobile feed simulator with LinkedIn typographic pacing and fold physics.
3. **Deterministic Visual Feedback**: Every interactive component features subtle micro-animations (0.12s to 0.25s cubic-bezier ease), interactive hover states, reactive telemetry counters, and high-contrast accessibility borders.
4. **Strict Zero Em-Dash Typography**: Strict rejection of em-dashes (` - `) in all code, tooltips, placeholders, and formatted outputs in favor of clean commas, natural punctuation, or spaced hyphens.

---

## 2. Design Tokens & CSS Custom Properties

The system implements a dual-theme token architecture (`[data-theme="light"]` and default/luxury `[data-theme="dark"]`).

### 2.1 Color Palette & Tokens

| Token Variable | Dark Mode (Default Obsidian) | Light Mode (Clean Slate) | Functional Purpose |
| :--- | :--- | :--- | :--- |
| `--bg-canvas` | `#07090E` | `#F8FAFC` | App canvas & workspace background |
| `--bg-surface` | `#0E131F` | `#FFFFFF` | Primary cards, panels, and modal backdrops |
| `--bg-surface-elevated` | `#161D2E` | `#FFFFFF` | Floating bars, status bands, elevated cards |
| `--bg-subtle` | `#121826` | `#F1F5F9` | Input fields, table header rows, chip tracks |
| `--bg-muted` | `#1A2234` | `#E2E8F0` | Hover backgrounds, border fills |
| `--border-light` | `rgba(255, 255, 255, 0.09)` | `#E2E8F0` | Standard card dividers, borders |
| `--border-subtle` | `rgba(255, 255, 255, 0.05)` | `#F1F5F9` | Secondary separator rules, nested containers |
| `--border-active` | `#6366F1` | `#4F46E5` | Active focus rings, selected card outlines |
| `--text-primary` | `#F8FAFC` | `#0F172A` | Primary headlines, post body, active text |
| `--text-secondary` | `#CBD5E1` | `#475569` | Field labels, subheadings, card descriptions |
| `--text-muted` | `#94A3B8` | `#64748B` | Helper captions, timestamps, inactive items |
| `--text-dim` | `#64748B` | `#94A3B8` | Watermark text, character limit markers |
| `--accent-indigo` | `#6366F1` | `#4F46E5` | Primary CTA, active nav indicator, brand links |
| `--accent-indigo-hover` | `#4F46E5` | `#4338CA` | Hover state for primary buttons |
| `--accent-indigo-subtle`| `rgba(99, 102, 241, 0.18)` | `rgba(79, 70, 229, 0.08)` | Selected chip fills, active badge backgrounds |
| `--accent-rose` | `#FB7185` | `#E11D48` | Glowing Fold Line indicator, high-risk flags |
| `--accent-rose-glow` | `rgba(251, 113, 133, 0.30)`| `rgba(225, 29, 72, 0.25)` | Pulsing fold line aura, risk gauges |
| `--accent-emerald` | `#34D399` | `#10B981` | Safe reach score, verified badge, online pulse |
| `--accent-amber` | `#FBBF24` | `#F59E0B` | Moderate risk score, quote author highlight |
| `--accent-cyan` | `#38BDF8` | `#06B6D4` | Verified watermark indicator dot, tech badges |

### 2.2 Typography Hierarchy

- **Display & Headlines (`--font-display`)**: `'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
  - Font weights: 700 (Bold), 800 (ExtraBold)
  - Letter spacing: `-0.015em` to `-0.025em` (tight, authoritative editorial feel)
- **Body & Editor (`--font-sans`)**: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
  - Font weights: 400 (Regular), 500 (Medium), 600 (SemiBold)
  - Line height: `1.8` in editor textarea for optimal breathing room; `1.55` in mobile simulator for accurate LinkedIn line-break estimation
- **Code & Telemetry (`--font-mono`)**: `'JetBrains Mono', monospace`
  - Used for: Character metrics, math formulas, status codes, prompt syntax, token previews

### 2.3 Depth, Elevation & Glassmorphism

- **Box Shadows**:
  - `--shadow-sm`: `0 1px 3px 0 rgba(0, 0, 0, 0.5)`
  - `--shadow-md`: `0 4px 14px -2px rgba(0, 0, 0, 0.6)`
  - `--shadow-lg`: `0 12px 24px -4px rgba(0, 0, 0, 0.7)`
  - `--shadow-float`: `0 24px 40px -6px rgba(0, 0, 0, 0.85)` (used on floating toolbar and modals)
  - `--shadow-glow`: `0 0 24px rgba(99, 102, 241, 0.3)`
- **Glassmorphism**:
  - Backdrop filter: `blur(16px)`
  - Dark glass surface: `rgba(14, 19, 31, 0.85)` with border `rgba(255, 255, 255, 0.09)`
  - Light glass surface: `rgba(255, 255, 255, 0.82)` with border `rgba(226, 232, 240, 0.8)`

---

## 3. Global Application Architecture & Layout

The root DOM structure is organized into a rigid layout grid consisting of:
1. **Collapsed / Expandable Left Navigation Sidebar** (`#global-sidebar`)
2. **Main Application Shell** (`.main-shell`)
   - **Context-Aware Studio Topbar** (`.studio-topbar`)
   - **Active Viewport Container** (Dynamic tab switcher switching between 8 core view containers)
3. **Floating Overlay Layer**:
   - Floating Highlight Action Bar (`#floating-selection-toolbar`)
   - Modal Overlays (`#image-studio-modal`, `#prospect-modal`, `#agno-modal`, `#dm-modal`)
   - Toast Container (`#toast-container`)

```
+----------------------------------------------------------------------------------------------------+
| [LS] SIDEBAR (68px / 240px) | TOPBAR: View Title | Context Metrics | Action Buttons | Theme Toggle  |
|-----------------------------+----------------------------------------------------------------------|
| [1] Post Studio             | [ EDITOR PANE (Flex: 1) ]             | [ SIMULATOR PANE (360px-400px)]|
| [2] Schedule & Queue        | - Hook Variant Carousel Track         | - Phone Frame (Bezel & Notch)  |
| [3] Warm-Lead CRM           | - Editor Card (Draft Dropdown, Tools) | - Feed Card (Avatar, Name)     |
| [4] Viral Swipe File        | - Main Textarea Canvas                | - Paced Text (Above / Below)   |
| [5] Analytics               | - Glowing Red Fold Indicator Line     | - "...see more" Dynamic Toggle |
| [6] AI Command (BYO-AI)     | - Floating Text Selection Action Bar  | - Media Preview (Img/Carousel) |
| [7] Docs & Playbook         | - Pre-Fold Hook Metric Status Bar     | - Social Reaction Bar          |
| [8] Settings & Profile      | - Native Media Dropzone Micro-Dock    | - 6-Dimension Safety Scorecard |
|-----------------------------+---------------------------------------+--------------------------------|
| Footer: Local Shield (100%) | Bottom Status Bar / Telemetry         | Dwell Time & Reach Verdict     |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. Detailed Component Specifications

### 4.1 Global Sidebar (`#global-sidebar`)
- **Dimensions**: Width collapsed is `68px`; expands to `240px` upon clicking the brand logo or toggling `.sidebar.expanded`.
- **Brand Toggle Button (`#brand-toggle`)**:
  - 36px x 36px rounded square (8px border-radius).
  - Background: `linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)`.
  - Content: Bold white typography `"LS"`.
  - Hover Behavior: Scales by `1.05`, emits purple-indigo glow shadow (`var(--shadow-glow)`), cursor pointer.
- **Navigation Buttons (`.nav-link[data-tab="..."]`)**:
  - Standard layout: `flex`, 40px height, centered icons (20x20px SVG), hidden label when collapsed, revealed when expanded.
  - Hover Behavior: Background shifts to `var(--bg-subtle)`, text brightens to `var(--text-primary)`, shifts right by `2px` (`transform: translateX(2px); transition: all 0.15s ease`).
  - Active State (`.nav-link.active`): Background tint `var(--accent-indigo-subtle)`, text color `var(--accent-indigo)`, solid 3px left border line in electric indigo (`border-left: 3px solid var(--accent-indigo)`).
  - Nav Badges (`.sidebar-badge`):
    - `count`: 356 vaulted templates badge (slate pill).
    - `ai`: BYO-AI badge (indigo outline).
    - `pro`: V2.5 badge (gold/amber accent).
    - `new`: Emerald badge (`rgba(16, 185, 129, 0.15)`, text `#34D399`).
- **Sidebar Footer (`.local-shield-indicator`)**:
  - Contains pulsing emerald indicator (`.shield-pulse-dot`) running a 2-second infinite keyframe animation (`0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.6) } 70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0) }`).
  - Text label: `"100% Local Machine"` indicating zero external network egress.

---

### 4.2 Topbar Navigation & Context Engine (`.studio-topbar`)
The topbar dynamically swaps its center telemetry pills and right action buttons based on the active tab:
- **Left**:
  - Primary View Title (`#view-title`): 14px to 16px Plus Jakarta Sans bold.
  - Subtitle (`#view-subtitle`): 11.5px muted gray single-line descriptor.
- **Center (Reactive Telemetry Context Groups)**:
  - **Studio Tab Group (`#topbar-group-studio`)**:
    - `Chars: 0 / 3,000`: JetBrains Mono character odometer.
    - `Pre-Fold: 0 chars`: Pre-fold length vs 180 character mobile cutoff.
    - `Dwell: 0s`: Estimated dwell time calculation based on 220 WPM reading pace.
  - **Analytics Tab Group**: 7D, 14D, 30D, 90D range selector pill buttons.
  - **CRM Tab Group**: Total active pipeline lead counter.
  - **Settings Tab Group**: Local SQLite vault badge and verified creator handle (`@dharmik_systems`).
- **Right Action Buttons**:
  - `🧹 Clean Spacing`: Trims trailing whitespaces, collapses multi-blank lines, strips double hyphens.
  - `💾 Save Draft`: Persists content to local SQLite `posts` table.
  - `⏰ Schedule Post`: Queues post into selected peak smart slot.
  - **Theme Switcher Toggle (`#btn-theme-toggle`)**: 36px circular button with sun/moon icon. Hover turns icon by 15 degrees (`transform: scale(1.08) rotate(15deg); transition: transform 0.2s ease`).

---

### 4.3 Center Editor Pane: Distraction-Free Authoring Stage

#### A. Hook Variant Carousel (`#hook-carousel-container`)
- **Container**: Positioned directly above the editor card, collapsible.
- **Track (`#hook-cards-track`)**: Horizontal flex scroll container with `overflow-x: auto` and hidden scrollbars.
- **Hook Cards (`.hook-card`)**:
  - Width: 260px fixed width, flex-shrink 0.
  - Structure: Category badge (e.g. `[Contrarian Insight]`), italicized hook draft, predicted CTR metric pill (`94% CTR`), and `Apply to Draft` action button.
  - Hover Behavior: Card elevates by `-3px` with subtle glowing border (`border-color: var(--accent-indigo); box-shadow: var(--shadow-md);`).

#### B. Main Editor Card & Header Tools
- **Header**:
  - Left: Draft Selector dropdown (`#draft-selector-select`) with active post titles.
  - Right: Word counter metric pill, `Generate Hooks` button, and `🎨 AI Image Studio` launcher button.
- **Writing Canvas (`#post-editor-input`)**:
  - Full-width textarea with transparent border, auto-expanding vertically.
  - Line height `1.8` with font size `15px` to ensure executive readability.
  - Focused state: subtle background fill (`var(--bg-subtle)`), thin border highlight.

#### C. The Dynamic Glowing Red "See More" Fold Line (`.see-more-fold-line`)
- **Purpose**: Visualizes the exact point where LinkedIn truncates the post on mobile devices (between line 3 and line 5 or ~180-210 characters).
- **Styling**:
  - `position: absolute; left: 12px; right: 12px; height: 0;`
  - `border-top: 1.5px dashed var(--accent-rose);`
  - `box-shadow: 0 0 10px var(--accent-rose-glow);`
  - Tags: Left tag pill `...SEE MORE FOLD` (solid rose background, white text); Right counter badge `PRE-FOLD: X CHARS`.
  - Scroll Synchronization: Smoothly recalculates top coordinate in real-time as text is typed or scrolled (`transition: top 0.08s ease`).

#### D. The Floating Highlight Action Bar (`#floating-selection-toolbar`)
Appears directly above any user-selected text in the textarea (`animation: popIn 0.15s cubic-bezier(0.16, 1, 0.3, 1)`):
- **Container**: Obsidian rounded pill (`#18181B`), elevated float shadow (`var(--shadow-float)`), z-index 100.
- **Buttons & Hover Interactions**:
  1. **`𝗕 Bold` (`#float-bold-btn`)**:
     - Function: Converts ASCII characters `A-Z, a-z, 0-9` to Mathematical Sans-Bold Unicode glyphs (`𝗨𝗻𝗶𝗰𝗼𝗱𝗲`).
     - Hover: Background tint `rgba(255, 255, 255, 0.15)`, text color `#FFFFFF`.
  2. **`𝘐 Italic` (`#float-italic-btn`) [The Italian / Italic Tool]**:
     - Function: Converts characters to Mathematical Sans-Italic Unicode glyphs (`𝘐𝘵𝘢𝘭𝘪𝘤`).
     - Hover: Background tint `rgba(255, 255, 255, 0.15)`, text color `#FFFFFF`.
  3. **`𝙼 Mono` (`#float-mono-btn`)**:
     - Function: Converts text to Monospace Unicode characters (`𝙼𝚘𝚗𝚘`).
     - Hover: Background tint `rgba(255, 255, 255, 0.15)`.
  4. **`S̶ Strike` (`#float-strike-btn`)**:
     - Function: Inserts Unicode combining strikethrough characters (`\u0336`).
     - Hover: Background tint `rgba(255, 255, 255, 0.15)`.
  5. **`🧹 Clean` (`#float-clean-btn`)**:
     - Function: Scrubs any em-dashes (` - `), converts smart quotes, and trims irregular spacing.
     - Hover: Background tint `rgba(255, 255, 255, 0.15)`.
  6. **`⚡ Re-Hook` (`#float-rehook-btn`)**:
     - Styling: Distinct red danger button (`.floating-btn.danger`).
     - Function: Sends selected text to Agno Agent to generate 5 variant hooks.
     - Hover: Background shifts to solid rose accent (`var(--accent-rose)`), text `#FFFFFF`.

#### E. Native Media Dropzone Micro-Dock (`#media-dropzone-container`)
- **Dock Target (`.media-dropzone-target`)**:
  - Dashed border (`1.5px dashed var(--border-light)`), rounded corners (8px).
  - Drag-Over State (`.dragover`): Solid electric indigo border, background tint `var(--accent-indigo-subtle)`, glowing outer ring (`box-shadow: 0 0 0 4px var(--accent-indigo-glow)`), scales by `1.005`.
  - Micro-Buttons inside:
    - `📁 Attach Image / PDF / Video`
    - `📑 Carousel Deck Builder (1080x1080 PDF)`
    - `🎨 AI Image Studio`
- **Attached Media Preview Card (`.media-attached-card`)**:
  - Displays square thumbnail, asset filename, dimensions (e.g. `1080x1080`), file size, and remove button (`✕ Remove`).

---

### 4.4 Right Pane: Real-Time Mobile Feed Simulator & Algorithmic Auditor

#### A. The Realistic Mobile Frame (`.device-frame`)
- **Form Factor**: Pixel-perfect iPhone 15 Pro bezel with rounded corners (36px border radius), dark graphite outer border (4px solid `#27272A`), and top speaker notch cutout.
- **Author Identity Header**:
  - Circular avatar (38px) with gradient fill and initials or profile photo.
  - Active presence dot: Green online dot positioned at bottom right of avatar.
  - Author Name: Bold 13px Plus Jakarta Sans (`Dharmik Shingala`).
  - Professional Headline: 11px muted gray (`AI Systems Engineer & Full-Stack Architect`).
  - Timestamp: `1h • Edited • 🌐`.
- **Real-Time Pacing & The Dynamic "...see more" Cutoff**:
  - Text is automatically divided into `.sim-above-fold` and `.sim-below-fold`.
  - `.sim-see-more-toggle`: Renders `...see more` in muted gray font.
  - Click Interaction: Toggles `.sim-below-fold` display between `none` and `inline`, dynamically animating feed height.
- **Attached Media Live Preview (`.sim-attached-media`)**:
  - For Images: Displays clean image with responsive 1:1, 4:5, or 16:9 aspect ratio and personal brand watermark badge in selected corner.
  - For PDF Carousels: Interactive swipeable slide deck with left/right navigation arrows, slide pagination counter (`1 / 7`), and bottom dot indicators.
- **Social Engagement Mockup Bar**:
  - Reaction icons: Like (👍), Celebrate (👏), Insightful (💡), Love (❤️). Counter: `42`.
  - Action pills: Like, Comment, Repost, Send.

#### B. The 6-Dimension Algorithmic Safety Scorecard (`.algo-safety-card`)
- **SVG Circular Radial Gauge**:
  - Background circle with muted track.
  - Dynamic colored progress ring (Emerald `#34D399` for >=85%, Amber `#FBBF24` for 60-84%, Rose `#FB7185` for <60%).
  - Center numeric indicator (0 to 100) in JetBrains Mono.
- **6 Deterministic Audit Checklist**:
  1. **Outbound Link Egress**: Flags any links in body text (penalty: -40% reach). Recommends link in comments.
  2. **Pre-Fold Hook CTR**: Assesses hook length under 180 characters.
  3. **Engagement-Bait Classifier**: Detects banned algorithmic phrases ("comment below", "like if you agree").
  4. **Hashtag Density**: Verifies optimal tag count (0 to 4 tags maximum; flags >5 tags).
  5. **Pacing & Wall-of-Text**: Flags paragraphs exceeding 3 consecutive lines without whitespace.
  6. **Font & Em-Dash Health**: Strictly ensures zero em-dashes and checks accessibility screen-reader score.
- **Estimated Dwell Time Box**: Calculates predicted reading dwell time (e.g. `~65 sec`) and displays algorithmic verdict (`Expand Feed` vs `Dampen Reach`).

---

### 4.5 Personal Settings & Creator Onboarding Dashboard (`#tab-settings`)

Organized as a responsive 3-column executive command dashboard:

```
+----------------------------------------------------------------------------------------------------+
| SETTINGS & CREATOR BRANDING DASHBOARD                                                              |
|----------------------------------------------------------------------------------------------------|
| COLUMN 1: CREATOR PROFILE        | COLUMN 2: PERSONAL WATERMARK      | COLUMN 3: AI DEFENSE & AUTH |
| - Full Name Input                | - Enable Watermark Toggle         | - Eliminate Provider Toggle |
| - Professional Headline / Bio    | - Watermark Handle Text Field     | - Multi-Ratio Crop Details  |
| - Company / Organization Field   | - 2x2 Interactive Corner Picker   | - LinkedIn Session Bridge   |
| - Target Audience Select         | - 3 Badge Style Preset Chips      |   * li_at Token Field       |
|                                  | - Live Interactive Canvas Preview |   * JSESSIONID Field        |
|                                  |   (Moving Badge + Verified Dot)   |   * Anti-Ban Safeguard Note |
+----------------------------------------------------------------------------------------------------+
```

#### Column 1: Creator Onboarding Profile
- **Fields**: Creator Display Name (`#setting-creator-name`), Professional Headline (`#setting-creator-headline`), Company (`#setting-creator-company`), Default Target Audience dropdown (`#setting-target-audience`).
- **Inputs**: Rounded (6px), subtle background fill, clean border transitions on focus (`border-color: var(--accent-indigo)`).

#### Column 2: Personal Brand Watermark Engine
- **Master Toggle (`#setting-watermark-enabled`)**: iOS-style 44x24px smooth toggle switch.
- **Watermark Text Input (`#setting-watermark-text`)**: Live synced with keystrokes to the preview canvas and topbar badge.
- **2x2 Corner Position Grid Picker (`#settings-corner-picker`)**:
  - 4 buttons: `Top-Left`, `Top-Right`, `Bottom-Left`, `Bottom-Right (Standard)`.
  - Hover: Background shifts to `var(--bg-muted)`, border darkens.
  - Active (`.corner-btn.active`): Indigo subtle background, electric indigo text, active border and inset box-shadow.
- **Badge Styling Presets (`#settings-style-chips`)**:
  1. `Glass Pill` (`glass_pill`): Luxury dark frosted-glass pill with cyan verified dot (`#38BDF8`).
  2. `Minimal Text` (`minimal_text`): Clean typography with soft text shadow, zero pill background.
  3. `Accent Badge` (`accent_badge`): Electric indigo pill (`#4F46E5`) with solid white dot.
- **Live Visual Badge Preview Canvas (`#watermark-live-preview-box`)**:
  - Dark radial gradient canvas with subtle 20px grid lines (`linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px)`).
  - Floating live badge (`#watermark-badge-element`) that dynamically animates to the selected corner (`pos-bottom-right`, `pos-top-left`, etc.) and updates its styling preset and handle text in real-time.

#### Column 3: AI Provider Watermark Elimination & LinkedIn Bridge
- **AI Provider Watermark Elimination Switch (`#setting-eliminate-provider-watermark`)**:
  - Controls oversampling (+12.5% canvas buffer) and bottom Lanczos crop to completely shear off Pollinations/trial AI provider logos.
  - Active Protection Info Box: Outlines the pixel-preservation mechanics.
- **LinkedIn Session Bridge**:
  - Connection status badge (`Connected & Verified` with glowing green pulse dot vs `Disconnected`).
  - Session cookie input fields (`li_at` and `JSESSIONID`) with reveal password toggle buttons (`👁️`).
  - Action buttons: `🔄 Save & Sync Tokens` and `⚡ Verify Connection`.
  - Security Guarantee Note: Outlines zero synthetic browser egress policy and local SQLite vault encryption.

---

### 4.6 Generative AI Image Studio Modal (`#image-studio-modal`)

A high-resolution modal dialog for multi-agent visual generation:
- **Left Column (Guided Architectural Selectors)**:
  - **Aspect Ratio Selector Chips**: `1:1 Square Feed`, `4:5 Portrait Feed`, `16:9 Landscape`.
  - **Visual Style Archetypes**: `📸 Photorealistic Executive`, `📐 Engineering Blueprint`, `📰 Editorial Magazine`, `🧊 3D Isometric Tech`, `✏️ Minimalist Architecture`.
  - **Color Mood & Lighting Selectors**: Dropdown grids (Navy & Cyan, Slate & Emerald, Obsidian Monochrome, Volumetric Studio Softbox, Cyber Rim Lighting).
  - **Creative Concept Textarea**: Concept prompt with `📥 Pull from Draft` button that extracts key metaphors from the active editor text.
  - **Dual Watermark Defense & Brand Compositing Controls**:
    - Toggle 1: `Eliminate AI Provider Watermark [ACTIVE]` (crop discard buffer).
    - Toggle 2: `Apply Personal Brand Watermark [CREATOR BADGE]` (stamps `@dharmik_systems` in chosen corner).
    - Toggle 3: `Format Typographic Quote Overlay` (with optional custom quote and author inputs).
  - **Agno Master Prompt Engineering**: Button `⚡ Synthesize Master Prompt with Agno` that populates a zero em-dash compliant prompt blueprint.
- **Right Column (Interactive Diffusion & Progress Stage)**:
  - Action Button: `🚀 Launch AI Generation`.
  - **Live Interactive Progress Card (`#image-gen-progress-card`)**:
    - Progress phase label (e.g. `Decomposing creative concept into artistic dimensions...`).
    - Percentage odometer (1% to 100%).
    - Animated progress track bar with indigo gradient fill.
  - **Result Preview**: Empty state icon or rendered high-res visual with `✍️ Attach to Active Draft` and `📥 Download` buttons.

---

### 4.7 Warm-Lead CRM Inbox View (`#tab-crm`)
- **4 Key Metric Cards**: Active Prospects, Outreach Sent, Connected, Meetings Booked.
- **Search & Filter Bar**: Real-time search by lead name, company, or status.
- **Prospect Table (`.clean-table`)**:
  - Columns: Prospect Name & Profile, Headline/Company, Inbound Engagement Type (Commented, Liked, Reposted), Status Dropdown, Context Notes, Actions.
  - Hover on Row: Background transitions to `var(--bg-subtle)`.
  - Actions:
    - `✨ Agno Dossier`: Launches autonomous multi-agent deep research modal (`#agno-modal`).
    - `⚡ Generate DM`: Opens Contextual DM Modal (`#dm-modal`) with 3 tailored outreach styles (Value Add, Resource Share, Quick Chat).

---

### 4.8 Viral Post Swipe File View (`#tab-inspirations`)
- **Header**: Search filter input with 300ms debounce and 8 topic filter chips (`All Blueprints (356)`, `Architecture & Frameworks`, `Contrarian Takes`, `Engineering Teardowns`, `Career Growth`, etc.).
- **Swipe Cards Grid**: 3-column responsive grid.
  - Each card features category tag, viral reach metric pill (e.g. `142K Views`), hook title, expandable breakdown, and `Use Blueprint in Editor` button that transfers template into active writing stage.

---

### 4.9 Creator Analytics & Time-Series Chart View (`#tab-analytics`)
- **4 KPI Metric Cards**: Impressions (7D/30D/90D), Avg. Engagement Rate, Profile Visits, Follower Growth.
- **Zero-Dependency Vector Curve Chart Engine (`#analytics-chart-canvas`)**:
  - Rendered entirely on HTML5 2D Canvas with zero external libraries.
  - Smooth cubic bezier spline smoothing with vibrant indigo/cyan linear gradient fill.
  - Dynamic crosshair follower on mousemove.
  - Floating glassmorphic tooltip showing exact date and impression count.

---

## 5. Micro-Interactions, States, and Animations

### 5.1 Hover & Active States Directory

| Component / Element | Default State | Hover State | Active / Focus State |
| :--- | :--- | :--- | :--- |
| **Primary Button (`.btn-primary`)** | Indigo background, white text, 8px radius | Shifts to darker indigo (`#4338CA`), transforms `translateY(-1px)`, elevates shadow | `transform: scale(0.98)`, glow shadow ring |
| **Outline Button (`.btn-outline`)** | Transparent bg, border `var(--border-light)` | Background `var(--bg-subtle)`, border `var(--border-active)`, text `var(--text-primary)` | `transform: scale(0.98)` |
| **Floating Action Button (`.floating-btn`)** | Transparent, text `#D4D4D8` | Background `rgba(255,255,255,0.15)`, text `#FFFFFF` | Immediate text transform insertion |
| **Floating Danger Button (`.floating-btn.danger`)** | Transparent, text `#FB7185` | Background `var(--accent-rose)`, text `#FFFFFF` | Triggers Agno hook variant generator |
| **Nav Link (`.nav-link`)** | Muted text, transparent bg | Background `var(--bg-subtle)`, text `var(--text-primary)`, `translateX(2px)` | Indigo accent bg, solid 3px left border |
| **Corner Grid Button (`.corner-btn`)** | Subtle bg, muted text | Background `var(--bg-muted)`, text `var(--text-primary)` | Indigo text, indigo border, inset ring |
| **Style Chip (`.watermark-chip`)** | Subtle bg, light border | Border `var(--border-active)`, elevates shadow | Indigo highlight border, active title |
| **Media Dropzone (`.media-dropzone-target`)** | Dashed border, subtle bg | Border `var(--accent-indigo)`, soft indigo shadow | Solid border, glowing ring, scales `1.005` |
| **Toggle Switch (`.toggle-switch`)** | Gray pill, white circle at left | Cursor pointer | Circle translates right 20px, bg turns indigo |
| **Theme Toggle (`.theme-toggle-btn`)** | Glass circle | Scales `1.08`, rotates `15deg` | Scales `0.95` |

### 5.2 Keyframe Animations
- `@keyframes popIn`: `0% { opacity: 0; transform: translateY(6px) scale(0.96); } 100% { opacity: 1; transform: translateY(0) scale(1); }`
- `@keyframes fadeIn`: `0% { opacity: 0; transform: translateY(4px); } 100% { opacity: 1; transform: translateY(0); }`
- `@keyframes pulse`: `0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.6); } 70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }`

---

## 6. Recommendations for UI/UX Enhancements

For another agent or engineer improving this system, here are high-impact architectural enhancements:

1. **Monaco / Code-Editor Highlighting Integration**:
   - Provide syntax highlighting for multi-language architecture code blocks directly inside the post editor canvas.
2. **Multi-Slide Carousel Visual Arranger**:
   - Add a drag-and-drop slide thumbnail strip at the bottom of the editor to re-order 1080x1080 carousel pages in real-time.
3. **Split-Screen A/B Variant Comparison**:
   - Introduce a side-by-side comparison mode in the simulator pane allowing creators to preview Hook Variant A vs Hook Variant B simultaneously.
4. **Interactive Fold Line Dragger**:
   - Allow creators to manually drag the glowing fold line up or down to simulate tablet or desktop fold heights in addition to mobile.
5. **Aesthetic Preset Exporter**:
   - Allow exporting creator watermark badges, color palettes, and typography presets as a reusable JSON Brand Kit.

---

*This specification represents the complete, unambiguous design manual for the LinkedIn Studio Enterprise frontend.*
