"""
Agno AgentOS Multi-Model Gateway (BYO-AI / Provider-Agnostic Engine)
====================================================================
Unified interface enabling Inox Hydra to orchestrate across any LLM provider:
- Google Gemini (Gemini 2.5 Flash, Gemini 1.5 Pro, Imagen 3)
- OpenAI (GPT-4o, GPT-4o-mini, DALL-E 3)
- Anthropic Claude (Claude 3.5 Sonnet, Claude 3 Haiku)
- Local LLMs via Ollama / vLLM / LocalAI (Llama 3, Mistral, DeepSeek)
- Groq / DeepSeek Cloud APIs (OpenAI-compatible)
- Local Deterministic Intelligence Engine (Zero-egress fallback)

Supports instant credential verification, latency benchmarking, and automated fallback.
"""

import os
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

try:
    from ..database import get_db, init_db
except ImportError:
    try:
        from database import get_db, init_db
    except ImportError:
        get_db = None
        init_db = None

SUPPORTED_PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "supported_models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "requires_key": True,
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "supports_images": True,
        "image_model": "imagen-3.0-generate-002"
    },
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o",
        "supported_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
        "requires_key": True,
        "default_base_url": "https://api.openai.com/v1",
        "supports_images": True,
        "image_model": "dall-e-3"
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "supported_models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "requires_key": True,
        "default_base_url": "https://api.anthropic.com/v1",
        "supports_images": False
    },
    "ollama": {
        "name": "Ollama (Local Offline LLM)",
        "default_model": "llama3:latest",
        "supported_models": ["llama3:latest", "mistral:latest", "deepseek-r1:latest", "qwen2.5:latest"],
        "requires_key": False,
        "default_base_url": "http://localhost:11434/v1",
        "supports_images": False
    },
    "groq": {
        "name": "Groq LPU Acceleration",
        "default_model": "llama-3.3-70b-versatile",
        "supported_models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "requires_key": True,
        "default_base_url": "https://api.groq.com/openai/v1",
        "supports_images": False
    },
    "custom_openai": {
        "name": "Custom OpenAI-Compatible API (vLLM / OpenRouter / LocalAI)",
        "default_model": "default",
        "supported_models": ["*"],
        "requires_key": False,
        "default_base_url": "http://localhost:8080/v1",
        "supports_images": False
    },
    "local_deterministic": {
        "name": "Inox Hydra Deterministic Engine (100% Zero-Egress Offline)",
        "default_model": "deterministic-heuristics-v2",
        "supported_models": ["deterministic-heuristics-v2"],
        "requires_key": False,
        "default_base_url": None,
        "supports_images": True
    }
}


class AIProviderConfig:
    """Encapsulates active AI provider settings."""
    def __init__(
        self,
        provider: str = "local_deterministic",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        verified_at: Optional[str] = None,
        status: str = "active"
    ):
        self.provider = provider if provider in SUPPORTED_PROVIDERS else "local_deterministic"
        self.api_key = api_key or ""
        prov_meta = SUPPORTED_PROVIDERS[self.provider]
        self.model = model or prov_meta.get("default_model", "deterministic-heuristics-v2")
        self.base_url = (base_url or prov_meta.get("default_base_url") or "").rstrip("/")
        self.verified_at = verified_at
        self.status = status

    @property
    def is_configured(self) -> bool:
        """Returns True if a cloud or local model is actively configured."""
        if self.provider == "local_deterministic":
            return False
        if self.provider == "ollama":
            return True
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def to_dict(self, mask_key: bool = True) -> Dict[str, Any]:
        key_display = ""
        if self.api_key:
            if mask_key and len(self.api_key) > 8:
                key_display = f"{self.api_key[:4]}...{self.api_key[-4:]}"
            elif mask_key:
                key_display = "********"
            else:
                key_display = self.api_key

        return {
            "provider": self.provider,
            "provider_name": SUPPORTED_PROVIDERS.get(self.provider, {}).get("name", self.provider),
            "model": self.model,
            "base_url": self.base_url,
            "api_key_masked": key_display,
            "has_key": bool(self.api_key),
            "verified_at": self.verified_at,
            "status": self.status,
            "supports_images": SUPPORTED_PROVIDERS.get(self.provider, {}).get("supports_images", False)
        }


def get_current_ai_config() -> AIProviderConfig:
    """Reads active AI configuration from SQLite settings table, falling back to env."""
    provider = "local_deterministic"
    api_key = ""
    model = ""
    base_url = ""
    verified_at = ""
    status = "active"

    if get_db:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings WHERE key LIKE 'ai_%'")
            rows = dict(cursor.fetchall())
            if not rows.get("ai_provider"):
                # Check legacy gemini_api_key
                cursor.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'")
                gem_row = cursor.fetchone()
                if gem_row and gem_row[0]:
                    provider = "gemini"
                    api_key = gem_row[0]
                    model = "gemini-2.5-flash"
            else:
                provider = rows.get("ai_provider", "local_deterministic")
                api_key = rows.get("ai_api_key", "")
                model = rows.get("ai_model", "")
                base_url = rows.get("ai_base_url", "")
                verified_at = rows.get("ai_verified_at", "")
                status = rows.get("ai_status", "active")
            conn.close()
        except Exception:
            pass

    # Check environment fallback if not set in DB
    if not api_key:
        env_gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        env_openai = os.environ.get("OPENAI_API_KEY")
        env_anthropic = os.environ.get("ANTHROPIC_API_KEY")
        env_groq = os.environ.get("GROQ_API_KEY")
        if env_openai:
            provider = "openai"
            api_key = env_openai
            model = "gpt-4o"
        elif env_gemini:
            provider = "gemini"
            api_key = env_gemini
            model = "gemini-2.5-flash"
        elif env_anthropic:
            provider = "anthropic"
            api_key = env_anthropic
            model = "claude-3-5-sonnet-20241022"
        elif env_groq:
            provider = "groq"
            api_key = env_groq
            model = "llama-3.3-70b-versatile"

    return AIProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        verified_at=verified_at,
        status=status
    )


def save_ai_config(
    provider: Any,
    api_key: Optional[str] = "",
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> AIProviderConfig:
    """Atomically persists active AI configuration into SQLite settings table."""
    from datetime import datetime
    now_iso = datetime.now().isoformat()

    if isinstance(provider, AIProviderConfig):
        config = provider
        if not config.verified_at:
            config.verified_at = now_iso
    else:
        config = AIProviderConfig(
            provider=str(provider),
            api_key=api_key or "",
            model=model,
            base_url=base_url,
            verified_at=now_iso,
            status="connected" if str(provider) != "local_deterministic" else "active"
        )

    if get_db:
        try:
            conn = get_db()
            with conn:
                cursor = conn.cursor()
                settings = [
                    ("ai_provider", config.provider),
                    ("ai_api_key", config.api_key),
                    ("ai_model", config.model),
                    ("ai_base_url", config.base_url),
                    ("ai_verified_at", config.verified_at or now_iso),
                    ("ai_status", config.status)
                ]
                for key, val in settings:
                    cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (key, val or ""))

                # Also sync legacy gemini_api_key if provider is gemini
                if config.provider == "gemini":
                    cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES ('gemini_api_key', ?, CURRENT_TIMESTAMP)
                    """, (config.api_key,))
            conn.close()
        except Exception as e:
            print(f"[ModelGateway] SQLite save failed: {e}")

    return config


def verify_ai_connection(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 8.0
) -> Tuple[bool, str, float]:
    """
    Actively tests an AI provider configuration with a test prompt ping.
    Returns: (is_success, status_message, latency_ms)
    """
    if provider == "local_deterministic":
        return True, "Local deterministic engine verified (100% zero cloud egress).", 1.2

    provider = provider.lower().strip()
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unsupported provider '{provider}'. Available: {list(SUPPORTED_PROVIDERS.keys())}", 0.0

    prov_meta = SUPPORTED_PROVIDERS[provider]
    model = model or prov_meta["default_model"]
    base_url = (base_url or prov_meta["default_base_url"] or "").rstrip("/")
    api_key = api_key or ""

    if prov_meta["requires_key"] and not api_key:
        return False, f"Provider '{provider}' requires an API key.", 0.0

    start_time = time.time()

    try:
        if provider == "gemini":
            # Test Gemini generateContent
            endpoint = f"{base_url}/models/{model}:generateContent?key={api_key}"
            payload = json.dumps({
                "contents": [{"parts": [{"text": "Say 'OK' in one word."}]}],
                "generationConfig": {"maxOutputTokens": 5, "temperature": 0.1}
            }).encode("utf-8")

            req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = round((time.time() - start_time) * 1000, 1)
                if "candidates" in data:
                    return True, f"Connected to Google Gemini ({model}) successfully!", latency
                return False, "Unexpected Gemini API response structure.", latency

        elif provider in ("openai", "groq", "ollama", "custom_openai"):
            # Test OpenAI-compatible /chat/completions
            endpoint = f"{base_url}/chat/completions"
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "Say 'OK' in one word."}],
                "max_tokens": 5,
                "temperature": 0.1
            }).encode("utf-8")

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = round((time.time() - start_time) * 1000, 1)
                if "choices" in data and len(data["choices"]) > 0:
                    return True, f"Connected to {prov_meta['name']} ({model}) successfully!", latency
                return False, "Received empty choices response.", latency

        elif provider == "anthropic":
            # Test Anthropic messages API
            endpoint = f"{base_url}/messages"
            payload = json.dumps({
                "model": model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "Say 'OK' in one word."}]
            }).encode("utf-8")

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }

            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = round((time.time() - start_time) * 1000, 1)
                if "content" in data:
                    return True, f"Connected to Anthropic Claude ({model}) successfully!", latency
                return False, "Unexpected Anthropic response structure.", latency

        return False, "Provider test routine not implemented.", 0.0

    except urllib.error.HTTPError as e:
        latency = round((time.time() - start_time) * 1000, 1)
        err_msg = f"HTTP {e.code}: {e.reason}"
        try:
            body = json.loads(e.read().decode("utf-8"))
            if "error" in body:
                err_detail = body["error"].get("message") if isinstance(body["error"], dict) else str(body["error"])
                err_msg = f"HTTP {e.code}: {err_detail}"
        except Exception:
            pass
        return False, err_msg, latency

    except urllib.error.URLError as e:
        latency = round((time.time() - start_time) * 1000, 1)
        return False, f"Network unreachable: {e.reason}", latency

    except Exception as e:
        latency = round((time.time() - start_time) * 1000, 1)
        return False, f"Connection error: {str(e)}", latency


def execute_llm_completion(
    config: AIProviderConfig,
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1200,
    temperature: float = 0.7
) -> str:
    """
    Routes prompt completion through the configured AI provider.
    Returns generated text string.
    """
    if config.provider == "local_deterministic" or not config.api_key and config.provider != "ollama":
        return ""

    try:
        if config.provider == "gemini":
            endpoint = f"{config.base_url}/models/{config.model}:generateContent?key={config.api_key}"
            parts = []
            if system_prompt:
                parts.append({"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"})
            parts.append({"text": prompt})

            payload = json.dumps({
                "contents": [{"parts": parts}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}
            }).encode("utf-8")

            req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        elif config.provider in ("openai", "groq", "ollama", "custom_openai"):
            endpoint = f"{config.base_url}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = json.dumps({
                "model": config.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }).encode("utf-8")

            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"

            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()

        elif config.provider == "anthropic":
            endpoint = f"{config.base_url}/messages"
            payload_dict = {
                "model": config.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }
            if system_prompt:
                payload_dict["system"] = system_prompt

            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01"
            }

            req = urllib.request.Request(endpoint, data=json.dumps(payload_dict).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block.get("text", "").strip()

    except Exception as e:
        print(f"[ModelGateway] Error executing LLM completion ({config.provider}): {e}")

    return ""
