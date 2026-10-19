"""
Agno AgentOS Multi-Model Gateway (BYO-AI / Provider-Agnostic Engine)
====================================================================
Unified interface enabling Inox Hydra to orchestrate across any LLM provider:
- Google Gemini (Gemini 2.5 Flash, Gemini 1.5 Pro, Imagen 3)
- OpenAI (GPT-4o, GPT-4o-mini, DALL-E 3)
- Anthropic Claude (Claude Sonnet 5.5, Opus 5.5, Haiku 5.5)
- Local LLMs via Ollama / vLLM / LocalAI (Llama 3, Mistral, DeepSeek)
- Groq / DeepSeek Cloud APIs (OpenAI-compatible)
- Local Deterministic Intelligence Engine (Zero-egress fallback)

Supports instant credential verification, latency benchmarking, and automated fallback.
"""

import os
import json
import time
import asyncio
import socket
import threading
import contextvars
import urllib.request
import urllib.error
from urllib.parse import quote

from fastapi import HTTPException

try:  # the shared egress chokepoint
    from .. import egress as _egress
except ImportError:
    import egress as _egress
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
        "default_model": "claude-sonnet-5-5",
        "supported_models": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
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


# Providers whose base URL the user may legitimately set, because the whole
# point of them is pointing at something local or self hosted.
CUSTOM_ENDPOINT_PROVIDERS = ("custom_openai", "ollama")


def _is_private_host(hostname):
    import ipaddress

    if not hostname:
        return False
    if hostname in ("localhost", "::1"):
        return True
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _resolve_base_url(provider, requested, prov_meta):
    """
    Decides where this provider's requests are actually sent.

    Every completion carries the user's API key in an Authorization header, so
    whoever controls this URL receives that key. It was a free string written
    straight into settings, which made a single POST to /api/ai/configure
    enough to have the next AI action deliver an OpenAI or Anthropic key to an
    arbitrary host.

    Two rules:

      A named provider always uses its own endpoint. If the provider is
      "openai", the key is an OpenAI key, and there is no legitimate reason to
      send it anywhere but OpenAI. The field is ignored rather than rejected,
      because nothing in the interface offers to set it for these.

      A custom endpoint provider may point anywhere, since that is its purpose,
      but only over https unless the host is local. Sending a bearer token in
      cleartext across a network is not a tradeoff worth offering.
    """
    from urllib.parse import urlsplit

    default = prov_meta.get("default_base_url") or ""
    candidate = (requested or "").strip()

    if provider not in CUSTOM_ENDPOINT_PROVIDERS:
        return default

    if not candidate:
        return default

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return default

    if parts.scheme not in ("http", "https"):
        return default
    if parts.scheme == "http" and not _is_private_host(parts.hostname):
        return default

    return candidate

try:
    from ..secret_settings import seal as _seal_setting, unseal as _unseal_setting
except ImportError:
    from secret_settings import seal as _seal_setting, unseal as _unseal_setting


def _gemini_headers(api_key: str) -> Dict[str, str]:
    """
    Gemini's key travels in a header, never in the URL.

    It used to be ?key=, and every place that records or prints a URL then
    held it: the egress ledger the Local security tab reads, and the requests
    exception printed to the log on any network failure.
    """
    return {"Content-Type": "application/json", "x-goog-api-key": api_key}

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
        # Known by value to the redactor, whatever shape the key has.
        _egress.remember_secret(self.api_key)
        prov_meta = SUPPORTED_PROVIDERS[self.provider]
        self.model = model or prov_meta.get("default_model", "deterministic-heuristics-v2")
        self.base_url = _resolve_base_url(self.provider, base_url, prov_meta).rstrip("/")
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
            # The last four at most. The first four said which provider issued
            # it and, with the last four, left only the middle to guess.
            if mask_key and len(self.api_key) > 12:
                key_display = f"...{self.api_key[-4:]}"
            elif mask_key:
                key_display = "set"
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
        conn = None
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
                    api_key = _unseal_setting("gemini_api_key", gem_row[0])
                    model = "gemini-2.5-flash"
            else:
                provider = rows.get("ai_provider", "local_deterministic")
                api_key = _unseal_setting("ai_api_key", rows.get("ai_api_key", ""))
                model = rows.get("ai_model", "")
                base_url = rows.get("ai_base_url", "")
                verified_at = rows.get("ai_verified_at", "")
                status = rows.get("ai_status", "active")
        except Exception:
            pass
        finally:
            if conn:
                try:
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
            model = SUPPORTED_PROVIDERS["anthropic"]["default_model"]
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
        conn = None
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
                    # Sealed on the way in. The key used to be written here as
                    # typed, into a table the README called an encrypted vault.
                    cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (key, _seal_setting(key, val or "")))

                # Also sync legacy gemini_api_key if provider is gemini
                if config.provider == "gemini":
                    cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES ('gemini_api_key', ?, CURRENT_TIMESTAMP)
                    """, (_seal_setting("gemini_api_key", config.api_key),))
        except Exception as e:
            print(f"[ModelGateway] SQLite save failed: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # A failure belonged to the setup just replaced.
    _record_outcome(None)
    return config


# How long one provider request may take, start to finish.
#
# urlopen's timeout bounds each socket read, not the request, so a provider or
# a proxy that kept the connection alive with a byte every few seconds never
# timed out at all. This is the whole budget, connection to last byte.
PROVIDER_DEADLINE_SECONDS = 40.0

# Longest silence tolerated on one read before giving up early.
_READ_TIMEOUT_SECONDS = 15.0

# The most provider requests in flight at once.
#
# Each request used to run on one of the web server's worker threads for as
# long as it took, so about forty presses of Re-Hook against a stalled
# provider left no thread to serve anything else, Save included. Requests now
# run on their own threads, at most this many, and a request that finds them
# all busy is answered at once rather than queued.
PROVIDER_CONCURRENCY = 3
_provider_slots = threading.BoundedSemaphore(PROVIDER_CONCURRENCY)

# Verify and save has slots of its own, so a check of a new setup is never
# refused because the old one is stalled.
_verify_slots = threading.BoundedSemaphore(2)

# Answers are short JSON. Anything larger than this is not one.
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

_last_failure: Dict[str, Optional[str]] = {"message": None, "at": None}


class ProviderError(HTTPException):
    """
    A configured provider that failed, in words the creator can act on.

    An HTTPException, so a route that lets it through answers with the
    status here and the message as its detail, which the interface prints.
    It used to be swallowed: execute_llm_completion returned "" and every
    caller served its deterministic templates as a success, so a revoked key
    or an empty account looked exactly like a working one.

    The message is redacted on the way in. It quotes what the provider said,
    and a provider can quote the key back.
    """

    def __init__(self, message: str, status_code: int = 502, upstream_status: Optional[int] = None):
        self.message = _egress.redact(message)
        self.upstream_status = upstream_status
        super().__init__(status_code=status_code, detail=self.message)

    def __str__(self) -> str:
        return self.message


def last_provider_failure() -> Dict[str, Optional[str]]:
    """The most recent provider failure and when, or Nones since a success."""
    return dict(_last_failure)


def _record_outcome(failure: Optional[ProviderError]) -> None:
    if failure is None:
        _last_failure.update({"message": None, "at": None})
    else:
        from datetime import datetime
        _last_failure.update({"message": failure.message, "at": datetime.now().isoformat(timespec="seconds")})


def _provider_label(provider: str) -> str:
    if provider == "custom_openai":
        return "Your provider"
    return SUPPORTED_PROVIDERS.get(provider, {}).get("name", provider)


def _refusal(error: "urllib.error.HTTPError", who: str, model: str) -> ProviderError:
    """An HTTP error from the provider, said as what it means."""
    detail = ""
    try:
        body = json.loads(error.read(65536).decode("utf-8", "replace"))
        problem = body.get("error") if isinstance(body, dict) else None
        if isinstance(problem, dict):
            detail = str(problem.get("message") or "")
        elif problem:
            detail = str(problem)
    except Exception:
        pass
    code = error.code
    if code in (401, 403):
        lead = f"{who} refused the key"
    elif code == 404:
        lead = f"{who} did not find the model '{model}'"
    elif code == 429:
        lead = f"{who} is limiting this key, or the account is out of credit"
    elif code >= 500:
        lead = f"{who} had a failure of its own"
    else:
        lead = f"{who} rejected the request"
    text = f"{lead} (HTTP {code})"
    # Redacted before it is cut short, so a key cannot survive as a fragment.
    detail = _egress.redact(detail)[:300]
    text += f": {detail}" if detail else "."
    return ProviderError(text, status_code=502, upstream_status=code)


class _Sockets:
    """
    The sockets one request opens, so the deadline can cut them.

    A socket timeout bounds each read, and a provider or proxy that sends its
    status line or headers a byte at a time never trips it: urlopen kept
    parsing, and the thread held its slot until the connection ended, twenty
    minutes in one test. Shutting the sockets down at the deadline ends that
    read whatever stage the exchange is at.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._held: list = []
        self.cut = False

    def hold(self, sock) -> None:
        with self._lock:
            self._held.append(sock)
            if self.cut:
                self._shut(sock)

    def cut_all(self) -> None:
        with self._lock:
            self.cut = True
            for sock in self._held:
                self._shut(sock)

    @staticmethod
    def _shut(sock) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _opener_holding(sockets: "_Sockets"):
    """An opener, proxies included, whose every new socket is held by `sockets`."""
    import http.client

    def holding(connection_class):
        class Held(connection_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                make = self._create_connection

                def made(*a, **k):
                    sock = make(*a, **k)
                    sockets.hold(sock)
                    return sock

                self._create_connection = made

        return Held

    plain, secure = holding(http.client.HTTPConnection), holding(http.client.HTTPSConnection)

    class PlainHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(plain, req)

    class SecureHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            options = {"context": getattr(self, "_context", None)}
            if getattr(self, "_check_hostname", None) is not None:
                options["check_hostname"] = self._check_hostname
            return self.do_open(secure, req, **options)

    return urllib.request.build_opener(PlainHandler, SecureHandler)


def _post_json(endpoint: str, payload: Dict[str, Any], headers: Dict[str, str],
               stop: float, who: str, model: str, budget: float) -> Any:
    """
    POSTs and reads the whole answer before `stop`, a time.monotonic() value.

    The deadline covers the whole exchange, connection and headers included:
    a timer shuts the request's sockets down when it runs out. Runs on a
    provider thread. Raises ProviderError for anything short of a JSON answer,
    and EgressRefused when model requests are off.
    """
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
    late = ProviderError(
        f"{who} did not finish answering within {int(budget)} seconds. Nothing was changed.", status_code=504
    )
    silent = ProviderError(
        f"{who} stopped answering for {_READ_TIMEOUT_SECONDS:g} seconds. Nothing was changed.", status_code=504
    )
    # Refuses rather than connecting when this category is off. See egress.py.
    _egress.require(endpoint, "model")
    sockets = _Sockets()
    timer = threading.Timer(max(0.0, stop - time.monotonic()), sockets.cut_all)
    timer.daemon = True
    timer.start()
    try:
        read_timeout = max(0.1, min(stop - time.monotonic(), _READ_TIMEOUT_SECONDS))
        with _opener_holding(sockets).open(request, timeout=read_timeout) as response:
            chunks, size = [], 0
            while True:
                if time.monotonic() > stop:
                    raise late
                chunk = response.read1(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_RESPONSE_BYTES:
                    raise ProviderError(f"{who} sent an answer far too large to be one.")
                chunks.append(chunk)
            if sockets.cut:
                raise late
    except urllib.error.HTTPError as error:
        if sockets.cut:
            raise late from None
        raise _refusal(error, who, model) from None
    except (ProviderError, _egress.EgressRefused):
        raise
    except urllib.error.URLError as error:
        if sockets.cut:
            raise late from None
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise ProviderError(
                f"{who} could not be reached within {_READ_TIMEOUT_SECONDS:g} seconds.", status_code=504
            ) from None
        raise ProviderError(f"{who} could not be reached: {error.reason}.") from None
    except (socket.timeout, TimeoutError):
        raise (late if sockets.cut else silent) from None
    except Exception as error:
        if sockets.cut:
            raise late from None
        raise ProviderError(f"{who} could not be reached: {error}.") from None
    finally:
        timer.cancel()
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except ValueError:
        raise ProviderError(f"{who} answered with something that is not JSON.") from None


def _within_deadline(call, budget: float, slots=None):
    """
    Runs call(stop) on a provider thread and waits at most `budget` seconds.

    The caller has an answer by the deadline whatever the connection is
    doing, and the thread's sockets are shut at the same moment, so its slot
    is free again within the budget. `slots` is the pool to draw from: the
    completions' unless given.
    """
    slots = slots or _provider_slots
    if not slots.acquire(blocking=False):
        raise ProviderError(
            "Your provider is still working on earlier requests. Wait for them to finish, then try again.",
            status_code=503,
        )
    outcome: Dict[str, Any] = {}
    finished = threading.Event()
    context = contextvars.copy_context()
    stop = time.monotonic() + budget

    def run():
        try:
            outcome["value"] = context.run(call, stop)
        except BaseException as error:  # handed to the waiting caller
            outcome["error"] = error
        finally:
            slots.release()
            finished.set()

    try:
        threading.Thread(target=run, name="inox-provider", daemon=True).start()
    except BaseException:
        slots.release()
        raise
    if not finished.wait(budget + 2.0):
        raise ProviderError(
            f"Your provider did not finish answering within {int(budget)} seconds. Nothing was changed.",
            status_code=504,
        )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def _request_for(provider: str, base_url: str, api_key: str, model: str, prompt: str,
                 system_prompt: Optional[str], max_tokens: int, temperature: float):
    """The endpoint, body and headers for one completion, per provider family."""
    if provider == "gemini":
        parts = []
        if system_prompt:
            parts.append({"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"})
        parts.append({"text": prompt})
        return (
            f"{base_url}/models/{quote(model, safe='')}:generateContent",
            {"contents": [{"parts": parts}],
             "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}},
            _gemini_headers(api_key),
        )
    if provider in ("openai", "groq", "ollama", "custom_openai"):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return (
            f"{base_url}/chat/completions",
            {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            headers,
        )
    if provider == "anthropic":
        payload = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system_prompt:
            payload["system"] = system_prompt
        return (
            f"{base_url}/messages",
            payload,
            {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
    return None


def _text_of(provider: str, data: Any) -> Optional[str]:
    """The answer's text, or None when the answer has no text where it should."""
    try:
        if provider == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        if provider == "anthropic":
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", "")
            return None
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def verify_ai_connection(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 15.0
) -> Tuple[bool, str, float]:
    """
    Actively tests an AI provider configuration with a test prompt ping.
    Returns: (is_success, status_message, latency_ms)

    `timeout` is the whole budget for the ping, not a per-read limit.
    """
    if provider == "local_deterministic":
        return True, "Local deterministic engine verified (100% zero cloud egress).", 1.2

    provider = provider.lower().strip()
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unsupported provider '{provider}'. Available: {list(SUPPORTED_PROVIDERS.keys())}", 0.0

    prov_meta = SUPPORTED_PROVIDERS[provider]
    model = (model or "").strip() or prov_meta["default_model"]
    # The address the saved setup will use, so the ping tests what is saved.
    # It used to go to whatever was typed, with the key, even when the saved
    # setup then ignored that address.
    base_url = _resolve_base_url(provider, base_url, prov_meta).rstrip("/")
    api_key = api_key or ""
    _egress.remember_secret(api_key)

    if prov_meta["requires_key"] and not api_key:
        return False, f"Provider '{provider}' requires an API key.", 0.0

    built = _request_for(provider, base_url, api_key, model, "Say 'OK' in one word.", None, 5, 0.1)
    if built is None:
        return False, "Provider test routine not implemented.", 0.0
    endpoint, payload, headers = built
    who = prov_meta["name"] if provider != "custom_openai" else "The endpoint"

    start_time = time.time()
    try:
        data = _within_deadline(
            lambda stop: _post_json(endpoint, payload, headers, stop, who, model, timeout), timeout,
            slots=_verify_slots,
        )
    except ProviderError as error:
        return False, error.message, round((time.time() - start_time) * 1000, 1)
    except Exception as error:
        return False, _egress.redact(f"Connection error: {error}"), round((time.time() - start_time) * 1000, 1)

    latency = round((time.time() - start_time) * 1000, 1)
    if _text_of(provider, data) is None:
        return False, f"{who} answered, but not in the shape a {prov_meta['name']} answer has.", latency
    return True, f"Connected to {prov_meta['name']} ({model}) successfully!", latency


def execute_llm_completion(
    config: AIProviderConfig,
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1200,
    temperature: float = 0.7
) -> str:
    """
    Routes prompt completion through the configured AI provider.

    Returns the generated text, or "" when no provider is configured. A
    configured provider that fails raises ProviderError, and one refused by
    egress policy raises EgressRefused. Neither is ever an empty string, which
    callers used to answer with their templates, as a success.
    """
    if config.provider == "local_deterministic" or not config.api_key and config.provider != "ollama":
        return ""

    built = _request_for(config.provider, config.base_url, config.api_key, config.model,
                         prompt, system_prompt, max_tokens, temperature)
    if built is None:
        return ""
    endpoint, payload, headers = built
    who = _provider_label(config.provider)
    budget = PROVIDER_DEADLINE_SECONDS

    try:
        data = _within_deadline(
            lambda stop: _post_json(endpoint, payload, headers, stop, who, config.model, budget), budget
        )
        text = _text_of(config.provider, data)
        if text is None:
            raise ProviderError(f"{who} answered, but with no text in it.")
    except _egress.EgressRefused:
        raise
    except ProviderError as failure:
        print(f"[ModelGateway] {config.provider} request failed: {failure.message}")
        _record_outcome(failure)
        raise
    except Exception as error:
        failure = ProviderError(f"{who} request failed: {error}")
        print(f"[ModelGateway] {config.provider} request failed: {failure.message}")
        _record_outcome(failure)
        raise failure from None

    _record_outcome(None)
    return text.strip()


async def execute_llm_completion_async(
    config: AIProviderConfig,
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1200,
    temperature: float = 0.7
) -> str:
    """
    Non-blocking async completion using httpx.AsyncClient.
    Preserves strict egress category checks and zero-cloud-egress guarantees.
    """
    if config.provider == "local_deterministic" or not config.api_key and config.provider != "ollama":
        return ""

    import httpx

    try:
        if config.provider == "gemini":
            endpoint = f"{config.base_url}/models/{quote(config.model, safe='')}:generateContent"
            parts = []
            if system_prompt:
                parts.append({"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"})
            parts.append({"text": prompt})

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}
            }
            _egress.require(endpoint, "model")
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await asyncio.wait_for(client.post(endpoint, json=payload, headers=_gemini_headers(config.api_key)), PROVIDER_DEADLINE_SECONDS)
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        elif config.provider in ("openai", "groq", "ollama", "custom_openai"):
            endpoint = f"{config.base_url}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": config.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"

            _egress.require(endpoint, "model")
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await asyncio.wait_for(client.post(endpoint, json=payload, headers=headers), PROVIDER_DEADLINE_SECONDS)
                resp.raise_for_status()
                data = resp.json()
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
            _egress.require(endpoint, "model")
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await asyncio.wait_for(client.post(endpoint, json=payload_dict, headers=headers), PROVIDER_DEADLINE_SECONDS)
                resp.raise_for_status()
                data = resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block.get("text", "").strip()

    except _egress.EgressRefused:
        raise
    except Exception as e:
        print(f"[ModelGateway] Error in async LLM completion ({config.provider}): {_egress.redact(e)}")

    return ""


async def _lines_until(response, stop: float):
    """The lines of a streamed answer, ending at `stop` (a time.monotonic() value)."""
    lines = response.aiter_lines().__aiter__()
    while True:
        remaining = stop - time.monotonic()
        if remaining <= 0:
            return
        try:
            line = await asyncio.wait_for(lines.__anext__(), remaining)
        except (StopAsyncIteration, asyncio.TimeoutError):
            return
        yield line


async def stream_llm_completion_async(
    config: AIProviderConfig,
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1200,
    temperature: float = 0.7
):
    """
    Streaming token generator yielding text chunks for real-time SSE UI consumption.

    The stream ends at PROVIDER_DEADLINE_SECONDS from its start, however the
    provider is pacing its bytes.
    """
    if config.provider == "local_deterministic" or not config.api_key and config.provider != "ollama":
        yield ""
        return

    import httpx

    stop = time.monotonic() + PROVIDER_DEADLINE_SECONDS

    if config.provider in ("openai", "groq", "ollama", "custom_openai"):
        endpoint = f"{config.base_url}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        _egress.require(endpoint, "model")
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                async for line in _lines_until(response, stop):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue

    elif config.provider == "gemini":
        endpoint = f"{config.base_url}/models/{quote(config.model, safe='')}:streamGenerateContent?alt=sse"
        parts = []
        if system_prompt:
            parts.append({"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"})
        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}
        }
        _egress.require(endpoint, "model")
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", endpoint, json=payload, headers=_gemini_headers(config.api_key)) as response:
                async for line in _lines_until(response, stop):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:].strip()
                    try:
                        chunk = json.loads(line)
                        candidates = chunk.get("candidates", [])
                        if candidates:
                            c_parts = candidates[0].get("content", {}).get("parts", [])
                            for p in c_parts:
                                text_piece = p.get("text", "")
                                if text_piece:
                                    yield text_piece
                    except Exception:
                        continue

    elif config.provider == "anthropic":
        endpoint = f"{config.base_url}/messages"
        payload = {
            "model": config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01"
        }
        _egress.require(endpoint, "model")
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                async for line in _lines_until(response, stop):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:].strip()
                    try:
                        chunk = json.loads(line)
                        if chunk.get("type") == "content_block_delta":
                            text_piece = chunk.get("delta", {}).get("text", "")
                            if text_piece:
                                yield text_piece
                    except Exception:
                        continue

    else:
        # Fallback to full async completion
        full_text = await execute_llm_completion_async(config, prompt, system_prompt, max_tokens, temperature)
        if full_text:
            yield full_text

