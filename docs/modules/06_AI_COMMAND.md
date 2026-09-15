# Module 06: AI Command Hub & Dual-Mode Intelligence Manual

The **AI Command Hub** is the centralized content generation and intelligence console for LinkedIn Studio Enterprise. It features a hybrid **Dual-Mode AI Architecture** pairing Google's flagship Gemini models with a 100% offline, deterministic local engine.

---

## 1. Visual Architecture & Layout Overview

Accessed via the sidebar (**AI Command**, `#tab-ai-command`), the console provides an author-first generative workflow:

```
+-------------------------------------------------------------------------------------------------------+
| PANEL HEADER: ✨ Gemini & Antigravity AI Command Hub                                                  |
| Subtitle: Dual-mode local content generation, hook formulation, and CRM scripting                    |
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

## 2. Dual-Mode Operational Engine

The backend router (`studio/backend/repurposer.py`) manages an automatic fallback hierarchy between two operating modes:

```mermaid
graph TD
    InputCmd[User Prompt / Command] --> Router[AI Engine Dispatcher]
    Router --> KeyCheck{Gemini API Key Configured?}

    KeyCheck -->|Yes: Key Found| ModeA[Mode A: Google Gemini 2.5 Flash<br/>Cloud Native API<br/>Dynamic Contextual Generation]
    KeyCheck -->|No: Offline / Missing| ModeB[Mode B: Antigravity Local Engine<br/>Deterministic Pattern Synthesizer<br/>100% Offline / Zero Egress]

    ModeA --> Sanitizer[Strict Sanitization Layer<br/>• Scrub All Em-Dashes (—, –)<br/>• Mathematical Sans-Bold Mapping<br/>• Mobile Dwell-Time Pacing]
    ModeB --> Sanitizer

    Sanitizer --> OutputConsole[Output Console & Studio Transfer]
```

### Mode A: Google Gemini 2.5 Flash (Cloud Native)
* **Model Identifier**: `gemini-2.5-flash`
* **Configuration**: Configured by saving your Gemini API key in local SQLite via `POST /api/ai/settings`.
* **Nature**: Live, dynamic, state-of-the-art multimodal reasoning.
* **Capabilities**:
  * Formulates highly original, non-templated hooks based on custom technical scenarios.
  * Ingests dense architectural documents or meeting notes and synthesizes nuanced executive perspectives.
  * Adapts tone across contrarian, empathetic, tactical, or visionary storytelling.

### Mode B: Antigravity Local Deterministic Engine (Offline Fallback & Demo Mode)
* **Nature**: 100% local, in-memory Python pattern synthesizer with zero external network connectivity.
* **Current Implementation (Active Demo / Fallback)**:
  * When no Gemini API key is configured (or during offline network disconnects), the studio automatically falls back to deterministic rule-based synthesis.
  * Uses structured archetypes:
    * **10 Hook Templates**: Contrarian, concrete metric, hard-won lesson, tactical playbook, etc.
    * **5 Repurposing Frameworks**: Contrarian, 3-step breakdown, hard truth, razor of leverage, practitioner narrative.
    * **3 Outreach DM Scripts**: Value add, resource share, quick chat.
* **Key Characteristic**: Predictable, instantaneous (0ms latency), and completely private, but relies on structured patterns rather than free-form conversational understanding.

---

## 3. UI Controls & Generation Workflows

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

## 4. Strict Linguistic Formatting Standards

Both Mode A and Mode B pass through a mandatory sanitization pipeline before returning output:

1. **Strict Zero Em-Dash Enforcement**:
   * Em-dashes (`—`) and en-dashes (`–`) are intercepted and replaced with clean commas or periods.
2. **Mathematical Sans-Bold Headers**:
   * Key opening sentences and section labels are converted to Mathematical Sans-Bold Unicode characters (`𝗧𝗲𝘅𝘁`) for cross-platform rendering.
3. **Pacing**:
   * Output is formatted with clean double line breaks between short 1-to-2 sentence thoughts to prevent mobile wall-of-text penalties.

---

## 5. Strategic AI Engine Roadmap

Future development milestones planned for the AI Command Hub:

1. **Local Open-Weights Engine (Ollama / Small LLM)**:
   * Integrating support for lightweight local models (e.g. Llama 3 8B, Gemma 2 9B, or Qwen 2.5) running via Ollama on localhost for true semantic offline generation without any cloud API keys.
2. **Streaming WebSocket Responses**:
   * Token-by-token streaming response delivery for real-time visual feedback.
3. **Multi-Turn Chat History**:
   * Conversational refinement enabling users to ask for follow-up tweaks (e.g. *"make line 2 more punchy"* or *"expand the 3rd principle"*).
