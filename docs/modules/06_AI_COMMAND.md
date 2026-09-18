# Module 06: Bring-Your-Own-AI (BYO-AI) Command Hub & Multi-Model Architecture

The **AI Command Hub** is the centralized intelligence console for LinkedIn Studio Enterprise. Unlike rigid legacy tools locked to a single vendor, Inox Hydra features a production-grade **Bring-Your-Own-AI (BYO-AI)** multi-model gateway. Creators, executives, and enterprise teams can route intelligence through Google Gemini, OpenAI (GPT-4o, DALL-E 3), Anthropic Claude, Groq LPU, self-hosted Ollama/vLLM, custom OpenAI-compatible proxies, or run 100% air-gapped on the local deterministic engine.

---

## 1. Visual Architecture & Layout Overview

Accessed via the sidebar (**AI Command**, `#tab-ai-command`), the console provides an author-first generative workflow:

```
+-------------------------------------------------------------------------------------------------------+
| PANEL HEADER: ✨ Multi-Model AI Command Hub                                                          |
| Subtitle: Bring-Your-Own-AI generation (OpenAI, Gemini, Claude, Ollama, Groq) + offline fallback      |
+-------------------------------------------------------------------------------------------------------+
| 1. QUICK PROMPT PRESET CHIPS (#ai-quick-cmd)                                                          |
| [Contrarian Systems Post]      [10x Hooks Generator]      [Repurpose Notes]                           |
+-------------------------------------------------------------------------------------------------------+
| 2. PROMPT INPUT AREA (#ai-command-prompt)                                                             |
| [ Type your instruction, topic, or raw notes here...                                                ] |
|                                                                                                       |
| Toolbar Row:                                                                                          |
| [📎 Attach Current Draft]                                                 [Execute Command Button]    |
+-------------------------------------------------------------------------------------------------------+
| 3. OUTPUT & TRANSFER CONSOLE (#ai-command-output)                                                     |
| [ Output:                                                                                           ] |
| [ Generated high-converting post draft or hooks appear here...                                      ] |
|                                                                                                       |
| Action Buttons:                                                                                       |
| [📋 Copy to Clipboard]                                                    [✍️ Load into Studio]        |
+-------------------------------------------------------------------------------------------------------+
```

---

## 2. Multi-Model Gateway Architecture

The multi-model router (`studio/backend/agno_agentos/model_gateway.py` and `studio/backend/repurposer.py`) dynamically resolves the user's active, verified AI provider:

```mermaid
graph TD
    InputCmd[User Prompt / Command / Orchestrator Task] --> Router[BYO-AI Multi-Model Gateway]
    Router --> ProviderCheck{Active Verified Provider in SQLite / Env?}

    ProviderCheck -->|OpenAI| ModeOpenAI[OpenAI: GPT-4o, GPT-4o-mini, DALL-E 3<br/>Direct HTTPS API]
    ProviderCheck -->|Gemini| ModeGemini[Google Gemini 2.5 Flash<br/>Direct HTTPS API]
    ProviderCheck -->|Anthropic| ModeClaude[Anthropic: Claude 3.5 Sonnet<br/>Direct HTTPS API]
    ProviderCheck -->|Ollama| ModeOllama[Local Ollama: Llama 3, Mistral, DeepSeek<br/>100% Localhost Zero-Egress]
    ProviderCheck -->|Groq| ModeGroq[Groq LPU: Llama 3.3 70B, Mixtral<br/>Sub-500ms Token Generation]
    ProviderCheck -->|Custom OpenAI| ModeCustom[Custom OpenAI-Compatible<br/>vLLM / LM Studio / Enterprise Proxy]
    ProviderCheck -->|None / Offline| ModeLocal[Antigravity Local Engine<br/>Deterministic Pattern Synthesizer<br/>100% Offline / Zero Cloud Egress]

    ModeOpenAI --> Sanitizer[Strict Sanitization Layer<br/>• Scrub All Em-Dashes ( - , –)<br/>• Mathematical Sans-Bold Mapping<br/>• Mobile Dwell-Time Pacing]
    ModeGemini --> Sanitizer
    ModeClaude --> Sanitizer
    ModeOllama --> Sanitizer
    ModeGroq --> Sanitizer
    ModeCustom --> Sanitizer
    ModeLocal --> Sanitizer

    Sanitizer --> OutputConsole[Output Console & Studio Transfer / Orchestrator Dispatch]
```

### Supported Providers Registry

| Provider Identifier | Default Model | Verification Endpoint | Image Capabilities | Typical Latency |
| :--- | :--- | :--- | :--- | :--- |
| **`openai`** | `gpt-4o` | `api.openai.com/v1/models` | DALL-E 3 HD (1024x1024, 1792x1024) | 1,200ms - 2,500ms |
| **`gemini`** | `Gemini 2.5 Flash` (`gemini-2.5-flash`) | `generativelanguage.googleapis.com` | Imagen 3 via Gemini API | 800ms - 1,800ms |
| **`anthropic`** | `claude-3-5-sonnet-20241022` | `api.anthropic.com/v1/messages` | Multi-prompt enhancement | 1,400ms - 3,000ms |
| **`ollama`** | `llama3` | `http://localhost:11434/api/tags` | Local canvas generation | 500ms - 4,000ms (HW-dependent) |
| **`groq`** | `llama-3.3-70b-versatile` | `api.groq.com/openai/v1/models` | Fast prompt enrichment | 250ms - 600ms |
| **`custom_openai`** | User-defined | User-defined `/v1/models` | Compatible endpoints | Variable |
| **`local_deterministic`** | `Antigravity Local Engine` (`antigravity-local`) | Instantaneous local ping | In-memory SVG/Canvas | **0ms (Zero egress)** |

---

## 3. CLI Configuration & Active Verification Ping

Users configure their AI directly through the unified `studio_cli.py` interface. 

> [!IMPORTANT]
> **Strict Verification Gate**: The CLI never blind-saves unverified credentials. When a user runs `ai configure`, the CLI performs a live HTTP handshake with the provider's API.
> * **If verified**: Latency is measured, the key is securely saved to local SQLite (`studio/data/linkedin_studio.db`), and all studio workflows immediately recall the new provider.
> * **If verification fails** (e.g. invalid API key, network unreachable): The CLI outputs the exact error code (e.g. `HTTP 401 Unauthorized`) and **aborts without modifying previous settings**.

### CLI Command Reference

```bash
# List all supported AI providers and their default models
python studio_cli.py ai list-providers

# Configure OpenAI (live ping test executed before saving)
python studio_cli.py ai configure --provider openai --api-key sk-proj-xxxxxxxx

# Configure Google Gemini
python studio_cli.py ai configure --provider gemini --api-key AIzaSyxxxxxxxx

# Configure Anthropic Claude
python studio_cli.py ai configure --provider anthropic --api-key sk-ant-xxxxxxxx

# Configure Local Ollama (100% private on localhost)
python studio_cli.py ai configure --provider ollama --base-url http://localhost:11434/v1 --model llama3

# Configure Groq LPU (ultra-fast inference)
python studio_cli.py ai configure --provider groq --api-key gsk_xxxxxxxx

# Test current active AI connection and benchmark latency
python studio_cli.py ai test

# Inspect current provider status and masked API keys
python studio_cli.py ai status

# Reset AI to 100% local deterministic offline engine
python studio_cli.py ai reset
```

---

## 4. Orchestration Workflows Powered by BYO-AI

Every generative and autonomous component in LinkedIn Studio dynamically queries `get_current_ai_config()`:

1. **Content Copilot (`ContentCopilotAgent`)**:
   * Generates viral, scroll-stopping hooks and post outlines using the active LLM.
   * Auto-falls back to 10 high-performing deterministic hook archetypes if offline.
2. **AI Image Studio (`image_studio.py`)**:
   * If `openai` is configured: Generates broadcast-quality images via **DALL-E 3**.
   * If `gemini` is configured: Generates images via **Imagen 3**.
   * Cloud fallback: High-speed aesthetic generation via **Pollinations AI**.
   * Air-gapped fallback: Procedural in-memory SVG/HTML5 canvas compositor.
3. **CRM Lead Research & Icebreakers (`IcebreakerAgent`)**:
   * Synthesizes personalized DM outreach scripts analyzing lead pain points, seniority, and industry.
4. **Viral Swipe File Harvester (`SwipeFileHarvesterAgent`)**:
   * Reverse-engineers top-performing industry posts into actionable author templates.
5. **Content Repurposer (`repurposer.py`)**:
   * Transmutes raw meeting notes, whitepapers, or code commits into 5 distinct LinkedIn post formats.

---

## 5. UI Controls & Generation Workflows

### 1. Quick Command Preset Chips
Clicking any preset chip instantly injects optimized prompt instructions into the textarea:
* **`Contrarian Systems Post`**:
  `"Draft a punchy contrarian LinkedIn post on Enterprise Observability vs reactive fire-drills. Use sans-bold for key lines and no em-dashes."`
* **`10x Hooks Generator`**:
  `"Generate 10 scroll-stopping hooks for scaling data infrastructure with zero downtime."`
* **`Repurpose Notes`**:
  `"Repurpose my notes into 5 distinct high-performing LinkedIn frameworks with clean whitespace."`

### 2. `📎 Attach Current Draft` (Context Bridge)
* Copies the active text from the Studio writing canvas (`#post-editor-input`) and appends it to your prompt as context:
  ```text
  Context from current draft:
  """
  [Your draft content]
  """
  ```
* Allows you to quickly re-hook, expand, or summarize what you have already written without manual copy-pasting.

### 3. `✍️ Load into Studio` (Direct Transfer)
* Copies the generated response directly into the main Studio editor textarea (`#post-editor-input`).
* Automatically switches the UI tab to **Studio & Editor**, triggering the live mobile simulator and the 6-dimension algorithmic audit instantly.

---

## 6. Strict Linguistic Formatting Standards

Every response generated across all models passes through our mandatory zero-compromise post-processing pipeline:

1. **Strict Zero Em-Dash Enforcement**:
   * Em-dashes (` - `) and en-dashes (`–`) are intercepted and replaced with clean commas or periods.
2. **Mathematical Sans-Bold Headers**:
   * Key opening sentences and section labels are converted to Mathematical Sans-Bold Unicode characters (`𝗧𝗲𝘅𝘁`) for cross-platform rendering.
3. **Mobile Dwell-Time Pacing**:
   * Output is formatted with clean double line breaks between short 1-to-2 sentence thoughts to prevent mobile wall-of-text penalties.
