# Inox Hydra: Bring-Your-Own-AI (BYO-AI) Architecture Guide

## Overview

Inox Hydra (LinkedIn Studio Enterprise) is built on an open, provider-agnostic artificial intelligence architecture. While commercial tools lock creators into proprietary black-box models or a single vendor API, Inox Hydra empowers authors to **Bring Your Own AI (BYO-AI)**.

Whether you run cutting-edge frontier models from OpenAI, Google, or Anthropic, high-throughput LPUs from Groq, or 100% offline local inference via Ollama or vLLM, Inox Hydra seamlessly orchestrates your chosen model across all content workflows.

---

## Key Capabilities

1. **Vendor Agnosticism**: No hardcoded dependencies on any single cloud provider.
2. **Active Ping Verification**: The CLI and API actively test connection health and credentials before saving to prevent workflow interruptions.
3. **Graceful Fallback**: If an external API is temporarily unavailable or credentials expire, the system automatically drops down to the local deterministic engine without throwing 500 errors.
4. **Multimodal Routing**: Image generation automatically selects DALL-E 3 (OpenAI), Imagen 3 (Gemini), Pollinations AI (free high-res engine), or local canvas generation.
5. **Zero Cloud Egress Default**: Completely functional out of the box with zero external keys or network calls.

---

## Supported Providers & Models

### 1. OpenAI
* **Provider Key**: `openai`
* **Supported Models**: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o3-mini`
* **Image Model**: DALL-E 3 (`dall-e-3`)
* **Endpoint**: `https://api.openai.com/v1`

### 2. Google Gemini
* **Provider Key**: `gemini`
* **Supported Models**: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`
* **Image Model**: Imagen 3 (`imagen-3.0-generate-002`)
* **Endpoint**: `https://generativelanguage.googleapis.com/v1beta`

### 3. Anthropic Claude
* **Provider Key**: `anthropic`
* **Supported Models**: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`
* **Endpoint**: `https://api.anthropic.com/v1`

### 4. Ollama (Local Hardware LLM)
* **Provider Key**: `ollama`
* **Supported Models**: `llama3:latest`, `mistral:latest`, `deepseek-r1:latest`, `qwen2.5:latest`
* **Endpoint**: `http://localhost:11434/v1`
* **Egress**: 100% Local / Zero Cloud Egress

### 5. Groq LPU Acceleration
* **Provider Key**: `groq`
* **Supported Models**: `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`
* **Endpoint**: `https://api.groq.com/openai/v1`

### 6. Custom OpenAI-Compatible
* **Provider Key**: `custom_openai`
* **Supported Models**: Any model ID (e.g. `vllm-model`, `local-ai`)
* **Endpoint**: Configurable (e.g., `http://localhost:8080/v1`)

### 7. Local Deterministic Engine (Default)
* **Provider Key**: `local_deterministic`
* **Model**: `deterministic-heuristics-v2`
* **Latency**: ~0ms
* **Egress**: Strictly 100% Offline

---

## CLI Configuration Workflow

The unified CLI tool `studio_cli.py` provides complete control over your AI configuration:

### 1. View Supported Providers
```bash
python studio_cli.py ai list-providers
```

### 2. Configure a Cloud Provider
```bash
# Configure OpenAI
python studio_cli.py ai configure --provider openai --api-key "sk-..." --model gpt-4o

# Configure Google Gemini
python studio_cli.py ai configure --provider gemini --api-key "AIzaSy..." --model gemini-2.5-flash

# Configure Anthropic Claude
python studio_cli.py ai configure --provider anthropic --api-key "sk-ant-..." --model claude-3-5-sonnet-20241022
```

### 3. Configure Local Offline Inference
```bash
# Start Ollama locally, then connect Inox Hydra:
python studio_cli.py ai configure --provider ollama --model llama3:latest
```

### 4. Test Active Connection & Latency
```bash
python studio_cli.py ai test
```

### 5. Check Active Configuration
```bash
python studio_cli.py ai status
```

### 6. Reset to Deterministic Engine
```bash
python studio_cli.py ai reset
```

---

## Orchestration Across Workflows

When an AI provider is configured, the `AgnoAgentOSOrchestrator` routes completions through the active model across all core workflows:

1. **LinkedIn Content Copilot (`optimize_content`)**: Synthesizes scroll-stopping hooks and structures drafts for maximum mobile dwell time.
2. **AI Image Studio (`synthesize_image_prompt` & `start_task`)**: Formulates cinematic prompts and routes image rendering to DALL-E 3 or Imagen 3.
3. **CRM Inbound Lead Research & Icebreakers (`enrich_lead`)**: Dissects prospect tech stacks and generates 3 tailored warm outreach angles.
4. **Viral Swipe File Harvester (`analyze_swipe`)**: Deconstructs viral LinkedIn posts into reusable formulas.
5. **Content Repurposer (`repurpose_content`)**: Transforms raw thoughts into 5 proven content frameworks.
