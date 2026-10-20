"""
Image providers: which service turns the image prompt into pixels.

The creator chooses one in the Prompt tab, beside their AI provider, the same
way they bring their own model for writing: a free public generator, a cloud
account of their own, or a web UI they run on this computer. Each choice says
before it is saved what leaves this machine, to whom, and on whose account.

Rules this module keeps:

  One provider, no silent chain. The old worker tried OpenAI, then Gemini,
  then Pollinations, then drew a grey placeholder and called it "complete and
  verified". A creator who chose their own account must not have the prompt
  passed to a third party because their account failed, and a failure must
  read as one. So the chosen provider is the only one asked, and its failure
  is the task's failure, in a sentence.

  The free public generator stays the default. With nothing chosen and no AI
  provider whose key can make images, Generate uses image.pollinations.ai, as
  the owner decided (PRD cycle 2, section 3). With an OpenAI or Gemini AI
  provider and nothing chosen here, that provider's key makes the image, as it
  did before this setting existed; the Prompt tab says which applies.

  Keys like the AI key (WRITE-04). Sealed at rest (secret_settings), sent in a
  header and never in a URL, registered with the redactor, shown as its last
  four characters at most, never returned, and scrubbed from every error.

  A named cloud provider always uses its own endpoint. Only the local web UIs
  take an address, because that is their purpose, and it must be http on this
  computer or the local network, or https anywhere. ENDPOINTS is a module
  attribute so the tests can point the cloud providers at a fake server on
  this machine; nothing the interface sends can change it.
"""

import base64
import io
import random
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlsplit

import requests

try:
    from . import egress as _egress
    from .database import get_db
    from .secret_settings import seal as _seal, unseal as _unseal
except ImportError:
    import egress as _egress
    from database import get_db
    from secret_settings import seal as _seal, unseal as _unseal


# Where each cloud provider's API lives. Fixed: see the module docstring.
ENDPOINTS: Dict[str, str] = {
    "pollinations": "https://image.pollinations.ai",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "stability": "https://api.stability.ai",
    "replicate": "https://api.replicate.com/v1",
    "fal": "https://fal.run",
    "together": "https://api.together.xyz/v1",
}

# Seconds. A cloud render takes 5 to 60 s; a web UI on a laptop GPU, or on a
# CPU, can take minutes, and giving up early would waste the render.
CLOUD_TIMEOUT = 120
LOCAL_TIMEOUT = 600
CHECK_TIMEOUT = 15

# A finished image is a few MB. Anything bigger than this is not one.
MAX_IMAGE_BYTES = 40 * 1024 * 1024

DEFAULT_PROVIDER = "pollinations"

_PROMPT_SENT = "The image prompt built from your description, and the image size"
_PROMPT_AND_NEGATIVE = "The image prompt built from your description, the things to avoid, and the image size"

# The catalogue the Prompt tab draws. "sends", "to" and "account" are shown to
# the creator before they save, so they are written as sentences for them.
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "pollinations": {
        "name": "Free public generator (image.pollinations.ai)",
        "kind": "public",
        "needs_key": False,
        "needs_url": False,
        "default_model": "flux",
        "models": ["flux", "turbo"],
        "sends": _PROMPT_SENT + ", inside the web address of the request.",
        "to": "image.pollinations.ai, a free public service run by a third party.",
        "account": "No account or key. Treat the prompt as public: it travels in the address, which services keep in their logs. The studio crops off the service's mark.",
        "check": "none",
    },
    "openai": {
        "name": "OpenAI Images",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "gpt-image-1",
        "models": ["gpt-image-1", "dall-e-3"],
        "sends": _PROMPT_SENT + ", with your key.",
        "to": "api.openai.com (OpenAI).",
        "account": "Your OpenAI account, billed per image.",
        # What Generate used with an OpenAI AI key before this setting existed.
        # A creator who has not chosen here keeps it (R7 review).
        "legacy_model": "dall-e-3",
        "model_notes": {
            "gpt-image-1": "Newer. OpenAI asks you to verify your organisation before it works, and prices it differently from dall-e-3.",
            "dall-e-3": "The model the studio used with an OpenAI key before this setting existed.",
        },
        "key_hint": "Create a key in your OpenAI account, under API keys.",
        "check": "key",
    },
    "gemini": {
        "name": "Google Imagen (Gemini API)",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "imagen-4.0-generate-001",
        "models": [
            "imagen-4.0-generate-001",
            "imagen-4.0-fast-generate-001",
            "imagen-4.0-ultra-generate-001",
            "imagen-3.0-generate-002",
        ],
        "sends": _PROMPT_SENT + ", with your key.",
        "to": "generativelanguage.googleapis.com (Google).",
        "account": "Your Google AI Studio key. Imagen needs billing turned on for that key.",
        "legacy_model": "imagen-3.0-generate-002",
        "model_notes": {
            "imagen-4.0-generate-001": "Newer, and priced differently from Imagen 3.",
            "imagen-4.0-fast-generate-001": "Newer, faster and cheaper than Imagen 4, with less detail.",
            "imagen-4.0-ultra-generate-001": "Newer, and the most expensive Imagen model.",
            "imagen-3.0-generate-002": "The model the studio used with a Gemini key before this setting existed.",
        },
        "key_hint": "Create a key in Google AI Studio.",
        "check": "key",
    },
    "stability": {
        "name": "Stability AI",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "stable-image-core",
        "models": ["stable-image-core", "stable-image-ultra", "sd3.5-large", "sd3.5-medium"],
        "sends": _PROMPT_AND_NEGATIVE + ", with your key.",
        "to": "api.stability.ai (Stability AI).",
        "account": "Your Stability AI account, which spends credits per image.",
        "key_hint": "Create a key in your Stability AI account settings.",
        "check": "key",
    },
    "replicate": {
        "name": "Replicate (FLUX and other models)",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "black-forest-labs/flux-schnell",
        "models": [
            "black-forest-labs/flux-schnell",
            "black-forest-labs/flux-dev",
            "black-forest-labs/flux-1.1-pro",
        ],
        "sends": _PROMPT_SENT + ", with your key.",
        "to": "api.replicate.com (Replicate). The finished image is then downloaded from Replicate's file host.",
        "account": "Your Replicate account, billed per image. The model is any official model, written owner/name.",
        "key_hint": "Create a token in your Replicate account settings.",
        "check": "key",
    },
    "fal": {
        "name": "fal.ai (FLUX)",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "fal-ai/flux/schnell",
        "models": ["fal-ai/flux/schnell", "fal-ai/flux/dev", "fal-ai/flux-pro/v1.1"],
        "sends": _PROMPT_SENT + ", with your key.",
        "to": "fal.run (fal.ai). The image comes back in the same answer.",
        "account": "Your fal.ai account, billed per image.",
        "key_hint": "Create a key in your fal.ai dashboard.",
        # fal has no check that does not make, and bill, an image.
        "check": "none",
    },
    "together": {
        "name": "Together AI (FLUX)",
        "kind": "cloud",
        "needs_key": True,
        "needs_url": False,
        "default_model": "black-forest-labs/FLUX.1-schnell",
        "models": [
            "black-forest-labs/FLUX.1-schnell",
            "black-forest-labs/FLUX.1-schnell-Free",
            "black-forest-labs/FLUX.1.1-pro",
        ],
        "sends": _PROMPT_SENT + ", with your key.",
        "to": "api.together.xyz (Together AI).",
        "account": "Your Together AI account, billed per image.",
        "key_hint": "Create a key in your Together AI settings.",
        "check": "key",
    },
    "automatic1111": {
        "name": "AUTOMATIC1111 or Forge web UI",
        "kind": "local",
        "needs_key": False,
        "needs_url": True,
        "default_url": "http://127.0.0.1:7860",
        "default_model": "",
        "models": [],
        "sends": _PROMPT_AND_NEGATIVE + ".",
        "to": "the web UI at the address you enter.",
        "account": "Your own machine and models. Start the web UI with the --api option.",
        "check": "url",
    },
    "comfyui": {
        "name": "ComfyUI",
        "kind": "local",
        "needs_key": False,
        "needs_url": True,
        "default_url": "http://127.0.0.1:8188",
        "default_model": "",
        "models": [],
        "sends": _PROMPT_AND_NEGATIVE + ", as a basic text-to-image workflow.",
        "to": "ComfyUI at the address you enter.",
        "account": "Your own machine and models. The studio uses a checkpoint from ComfyUI's models/checkpoints folder.",
        "check": "url",
    },
    "off": {
        "name": "Off",
        "kind": "off",
        "needs_key": False,
        "needs_url": False,
        "default_model": "",
        "models": [],
        "sends": "Nothing. Generate is turned off.",
        "to": "Nobody.",
        "account": "Uploading your own images still works.",
        "check": "none",
    },
}

# Settings rows. Named ai_image_* so `reset --keep-data`, which clears every
# ai_ setting as provider setup, clears these too.
_K_PROVIDER = "ai_image_provider"
_K_KEY = "ai_image_api_key"
_K_MODEL = "ai_image_model"
_K_URL = "ai_image_base_url"
_K_VERIFIED = "ai_image_verified_at"
_K_CHECK = "ai_image_check"
_K_KEY_FROM = "ai_image_key_from"
_ALL_KEYS = (_K_PROVIDER, _K_KEY, _K_MODEL, _K_URL, _K_VERIFIED, _K_CHECK, _K_KEY_FROM)

# Providers whose key can be the AI provider's own, when that is the same
# company. The AI settings' ids for them match these.
_SHARES_AI_KEY = ("openai", "gemini")

_MODEL_NAME = re.compile(r"^[A-Za-z0-9._/:\- ()\[\]]{1,200}$")


class ImageProviderError(Exception):
    """A provider that failed, in a sentence the creator can act on. Redacted."""

    def __init__(self, message: str, refused: bool = False):
        super().__init__(_egress.redact(message))
        self.refused = refused


def _ai_config():
    try:
        from .agno_agentos.model_gateway import get_current_ai_config
    except ImportError:
        from agno_agentos.model_gateway import get_current_ai_config
    return get_current_ai_config()


class ImageProviderConfig:
    """The provider Generate will use, and how it was chosen."""

    def __init__(self, provider: str, model: str = "", api_key: str = "", base_url: str = "",
                 source: str = "default", key_from: str = "", verified_at: str = "", check: str = ""):
        self.provider = provider if provider in PROVIDERS else DEFAULT_PROVIDER
        meta = PROVIDERS[self.provider]
        self.model = (model or "").strip() or meta.get("default_model", "")
        self.api_key = (api_key or "").strip()
        _egress.remember_secret(self.api_key)
        self.base_url = (base_url or meta.get("default_url", "")).rstrip("/") if meta["needs_url"] else ""
        self.source = source
        self.key_from = key_from
        self.verified_at = verified_at
        self.check = check

    @property
    def meta(self) -> Dict[str, Any]:
        return PROVIDERS[self.provider]

    @property
    def name(self) -> str:
        return self.meta["name"]

    def not_ready(self) -> Optional[str]:
        """Why Generate cannot use this setup, or None when it can."""
        if self.provider == "off":
            return "Image generation is off. Choose an image provider in the Prompt tab."
        if self.meta["needs_key"] and not self.api_key:
            if self.key_from == "ai_provider":
                return (f"{self.name} was set to use your AI provider's key, and that key is gone. "
                        "Enter a key for it in the Prompt tab.")
            return f"{self.name} needs a key. Enter one in the Prompt tab."
        return None

    def to_public(self) -> Dict[str, Any]:
        """What the interface may see. The key never, its last four at most."""
        masked = ""
        if self.api_key:
            masked = f"...{self.api_key[-4:]}" if len(self.api_key) > 12 else "set"
        return {
            "provider": self.provider,
            "name": self.name,
            "kind": self.meta["kind"],
            "model": self.model,
            "base_url": self.base_url,
            "source": self.source,
            "has_key": bool(self.api_key),
            "api_key_masked": masked,
            "key_from": self.key_from,
            "verified_at": self.verified_at,
            "check": self.check,
            "ready": self.not_ready() is None,
            "not_ready": self.not_ready(),
            "disclosure": disclosure(self.provider, self.base_url),
        }


def _read_settings() -> Dict[str, str]:
    conn = None
    try:
        conn = get_db()
        rows = conn.execute(
            f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * len(_ALL_KEYS))})", _ALL_KEYS
        ).fetchall()
        return {row[0]: _unseal(row[0], row[1]) for row in rows}
    except Exception:
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def current_config() -> ImageProviderConfig:
    """The setup Generate uses now, for the active profile."""
    saved = _read_settings()
    chosen = saved.get(_K_PROVIDER, "")
    if chosen in PROVIDERS:
        key = saved.get(_K_KEY, "")
        key_from = saved.get(_K_KEY_FROM, "") or ("own" if key else "")
        if key_from == "ai_provider":
            ai = _ai_config()
            key = ai.api_key if ai.provider == chosen else ""
        return ImageProviderConfig(
            chosen, saved.get(_K_MODEL, ""), key, saved.get(_K_URL, ""),
            source="chosen", key_from=key_from,
            verified_at=saved.get(_K_VERIFIED, ""), check=saved.get(_K_CHECK, ""),
        )

    # Nothing chosen: the AI provider's key when it can make images, as before
    # this setting existed; otherwise the free public generator.
    ai = _ai_config()
    if ai.provider in _SHARES_AI_KEY and ai.api_key:
        # The model it used then, not the newest: a newer model is priced
        # differently and gpt-image-1 needs organisation verification, so
        # moving a creator onto it unasked would change their bill and could
        # break Generate (R7 review). Choosing a model here changes it.
        legacy = PROVIDERS[ai.provider].get("legacy_model", "")
        return ImageProviderConfig(ai.provider, legacy, ai.api_key, source="ai_provider", key_from="ai_provider")
    return ImageProviderConfig(DEFAULT_PROVIDER, source="default")


def _where(base_url: str) -> Tuple[str, bool]:
    """Where a local web UI is, in words, and whether that is off this machine."""
    import ipaddress

    host = urlsplit(base_url).hostname or ""
    if _egress.on_this_machine(base_url):
        return "this computer", False
    try:
        if ipaddress.ip_address(host).is_private:
            return f"another computer on your network ({host})", True
    except ValueError:
        # A name with no dot, or one of the local-only suffixes, is resolved
        # on the network rather than on the internet.
        if "." not in host or host.endswith((".local", ".lan", ".home.arpa")):
            return f"another computer on your network ({host})", True
    return f"a server on the internet ({host})", True


def disclosure(provider: str, base_url: str = "") -> Dict[str, Any]:
    """What leaves this machine when Generate runs with this provider."""
    meta = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
    to = meta["to"]
    leaves = meta["kind"] in ("public", "cloud")
    if meta["kind"] == "local" and base_url:
        where, leaves = _where(base_url)
        to = f"{meta['name']} at {base_url}, on {where}."
    return {"sends": meta["sends"], "to": to, "account": meta["account"], "leaves": leaves}


def catalogue() -> List[Dict[str, Any]]:
    """Every provider the Prompt tab offers, with what each would send."""
    listed = []
    for provider_id, meta in PROVIDERS.items():
        listed.append({
            "id": provider_id,
            "name": meta["name"],
            "kind": meta["kind"],
            "needs_key": meta["needs_key"],
            "needs_url": meta["needs_url"],
            "default_url": meta.get("default_url", ""),
            "default_model": meta["default_model"],
            "models": list(meta["models"]),
            "key_hint": meta.get("key_hint", ""),
            # Said beside the model field: what each model needs or costs.
            "model_notes": dict(meta.get("model_notes", {})),
            "checks": meta["check"] != "none",
            "shares_ai_key": provider_id in _SHARES_AI_KEY,
            "disclosure": disclosure(provider_id, meta.get("default_url", "")),
        })
    return listed


# ---------------------------------------------------------------------------
# HTTP, through the chokepoint
# ---------------------------------------------------------------------------

def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc.rsplit("@", 1)[-1]
    except ValueError:
        return ""


# How many redirects within one address a request may follow.
_MAX_SAME_ORIGIN_REDIRECTS = 3


def _origin(url: str) -> Tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.netloc.rsplit("@", 1)[-1].lower()


def _send(method: str, url: str, config: ImageProviderConfig, timeout: float, **kwargs) -> requests.Response:
    """
    One request to the provider, through the egress guard.

    A local web UI on this computer is not egress (egress.on_this_machine).
    Everything else, a web UI on another machine included, is the image
    category and can be refused, which raises EgressRefused before a socket
    opens.

    Redirects are never followed to another address. requests follows them by
    default, and the guard is asked about the first address only, so a web UI
    on 127.0.0.1 that answered 307 had the prompt re-sent to whatever host its
    Location named, under INOX_NO_EGRESS, while the Prompt tab said it stays
    on this computer (R7 review). A cloud provider's redirect would have
    carried the key in its header the same way. A redirect within the same
    scheme, host and port goes nowhere new, so it is followed, a few times at
    most.
    """
    if not (config.meta["kind"] == "local" and _egress.on_this_machine(url)):
        _egress.require(url, "image")
    origin = _origin(url)
    try:
        for _hop in range(_MAX_SAME_ORIGIN_REDIRECTS + 1):
            if method == "GET":
                response = requests.get(url, timeout=timeout, allow_redirects=False, **kwargs)
            else:
                response = requests.post(url, timeout=timeout, allow_redirects=False, **kwargs)
            if not 300 <= response.status_code < 400:
                return response
            location = response.headers.get("Location") or ""
            target = urljoin(url, location)
            if not location or _origin(target) != origin:
                where = _origin(target)[1] if location else "nowhere"
                raise ImageProviderError(
                    f"{config.name} answered with a redirect to {where} (HTTP {response.status_code}). "
                    "The studio does not follow a redirect to another address, so nothing was sent there."
                )
            url = target
            if response.status_code in (301, 302, 303):
                # What browsers and requests do: the next request is a GET
                # with no body.
                method = "GET"
                kwargs = {k: v for k, v in kwargs.items() if k not in ("json", "data", "files")}
        raise ImageProviderError(f"{config.name} kept redirecting, so the studio stopped.")
    except requests.Timeout:
        raise ImageProviderError(f"{config.name} did not answer within {int(timeout)} seconds.")
    except requests.ConnectionError as error:
        if config.meta["kind"] == "local":
            hint = " with the --api option" if config.provider == "automatic1111" else ""
            raise ImageProviderError(
                f"Nothing answered at {config.base_url}. Start {config.name}{hint}, then try again."
            )
        raise ImageProviderError(f"Could not reach {_host(url)}: {_short(error)}")
    except requests.RequestException as error:
        raise ImageProviderError(f"The request to {config.name} failed: {_short(error)}")


def _short(error: Any) -> str:
    text = _egress.redact(error)
    # The commonest failure offline, which otherwise reads as a library repr.
    if "NameResolutionError" in text or "Failed to resolve" in text or "Name or service not known" in text:
        return "its name could not be looked up. Check that this computer is online."
    # requests nests the reason several layers deep; the last clause says it.
    for marker in ("Caused by ", "Failed to establish a new connection: "):
        if marker in text:
            text = text.rsplit(marker, 1)[-1]
    return text.strip(" ()'\"")[:200]


def _detail(response: requests.Response) -> str:
    """The provider's own reason, from the shapes their error bodies take."""
    try:
        body = response.json()
    except ValueError:
        return _egress.redact(response.text or "")[:200].strip()
    said: Any = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            said = error.get("message")
        elif isinstance(error, str):
            said = error
        if not said:
            said = body.get("message") or body.get("detail") or body.get("errors") or body.get("name")
    if isinstance(said, list):
        said = "; ".join(str(item.get("msg", item) if isinstance(item, dict) else item) for item in said)
    return _egress.redact(said or "")[:200].strip()


def _refusal(response: requests.Response, config: ImageProviderConfig) -> ImageProviderError:
    status = response.status_code
    detail = _detail(response)
    said = f" It said: {detail}" if detail else ""
    if status in (401, 403):
        return ImageProviderError(f"{config.name} refused the key (HTTP {status}). Check the key in the Prompt tab.{said}")
    if status == 402:
        return ImageProviderError(f"{config.name} says the account has no credit left (HTTP 402).{said}")
    if status == 404:
        return ImageProviderError(f"{config.name} does not offer the model '{config.model}' (HTTP 404).{said}")
    if status == 429:
        return ImageProviderError(f"{config.name} is limiting requests from this key (HTTP 429). Wait a minute and try again.{said}")
    if status >= 500:
        return ImageProviderError(f"{config.name} had a problem of its own (HTTP {status}). Try again later.{said}")
    return ImageProviderError(f"{config.name} refused the request (HTTP {status}).{said}")


def _json(response: requests.Response, config: ImageProviderConfig) -> Any:
    try:
        return response.json()
    except ValueError:
        raise ImageProviderError(f"{config.name} answered with something that is not JSON.")


def _image(data: Optional[bytes], config: ImageProviderConfig) -> bytes:
    """The bytes, if they are an image. A provider's error page is not one."""
    if not data:
        raise ImageProviderError(f"{config.name} returned no image.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageProviderError(f"{config.name} returned {len(data) // (1024 * 1024)} MB, which is not an image this studio keeps.")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except Exception:
        raise ImageProviderError(f"{config.name} returned something that is not an image.")
    return data


def _b64(value: Any, config: ImageProviderConfig) -> bytes:
    text = str(value or "")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=False)
    except Exception:
        raise ImageProviderError(f"{config.name} returned an image this studio could not read.")


def _download(url: str, base: str, config: ImageProviderConfig) -> bytes:
    """
    A finished image a provider links to.

    https only, or the provider's own address (a fake one in the tests, a web
    UI on the network). Anything else in an answer is not followed.
    """
    if not isinstance(url, str) or not url:
        raise ImageProviderError(f"{config.name} returned no image.")
    if url.startswith("data:"):
        return _b64(url, config)
    parts, own = urlsplit(url), urlsplit(base)
    if parts.scheme != "https" and (parts.scheme, parts.netloc) != (own.scheme, own.netloc):
        raise ImageProviderError(f"{config.name} linked the image at an address this studio does not follow.")
    response = _send("GET", url, config, CLOUD_TIMEOUT)
    if response.status_code != 200:
        raise ImageProviderError(f"The image {config.name} made could not be downloaded (HTTP {response.status_code}).")
    return response.content


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------

def _shape(width: int, height: int) -> str:
    """"square", "landscape" or "portrait", from the size the prompt asks for."""
    if width > height * 1.2:
        return "landscape"
    if height > width * 1.1:
        return "portrait"
    return "square"


# The size a self-hosted model renders at, per shape. Multiples of 64 near a
# megapixel, which suits SDXL and FLUX and still works for SD 1.5.
_LOCAL_SIZE = {"square": (1024, 1024), "landscape": (1344, 768), "portrait": (896, 1120)}


# ---------------------------------------------------------------------------
# Generation, one function per provider
# ---------------------------------------------------------------------------

def _pollinations(config, prompt, negative, width, height, eliminate_watermark):
    try:
        from .quote_renderer import remove_watermark_crop
    except ImportError:
        from quote_renderer import remove_watermark_crop

    if eliminate_watermark:
        # Taller than asked, so the service's mark lands in a strip the crop
        # then discards.
        req_w, req_h = {"landscape": (1080, 688), "portrait": (768, 1080), "square": (768, 864)}[_shape(width, height)]
    else:
        req_w, req_h = width, height
    seed = random.randint(1, 999999)
    encoded = quote((prompt or "Abstract architectural concept").strip()[:450])
    url = (f"{ENDPOINTS['pollinations']}/prompt/{encoded}"
           f"?width={req_w}&height={req_h}&seed={seed}&nologo=true&model={quote(config.model)}")
    response = _send("GET", url, config, CLOUD_TIMEOUT)
    if response.status_code != 200:
        raise _refusal(response, config)
    data = _image(response.content, config)
    if eliminate_watermark:
        data, _ = remove_watermark_crop(data, width, height)
    return data


def _openai(config, prompt, negative, width, height, eliminate_watermark):
    shape = _shape(width, height)
    if config.model.startswith("dall-e"):
        size = {"square": "1024x1024", "landscape": "1792x1024", "portrait": "1024x1792"}[shape]
    else:
        size = {"square": "1024x1024", "landscape": "1536x1024", "portrait": "1024x1536"}[shape]
    payload: Dict[str, Any] = {"model": config.model, "prompt": prompt[:4000], "n": 1, "size": size}
    if config.model.startswith("dall-e"):
        # gpt-image models always answer in base64 and refuse this field.
        payload["response_format"] = "b64_json"
    base = ENDPOINTS["openai"]
    response = _send("POST", f"{base}/images/generations", config, CLOUD_TIMEOUT,
                     headers={"Authorization": f"Bearer {config.api_key}"}, json=payload)
    if response.status_code != 200:
        raise _refusal(response, config)
    items = (_json(response, config) or {}).get("data") or []
    if not items:
        raise ImageProviderError(f"{config.name} returned no image.")
    if items[0].get("b64_json"):
        return _b64(items[0]["b64_json"], config)
    return _download(items[0].get("url"), base, config)


def _gemini(config, prompt, negative, width, height, eliminate_watermark):
    ratio = {"square": "1:1", "landscape": "16:9", "portrait": "3:4"}[_shape(width, height)]
    payload = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1, "aspectRatio": ratio}}
    response = _send("POST", f"{ENDPOINTS['gemini']}/models/{config.model}:predict", config, CLOUD_TIMEOUT,
                     headers={"x-goog-api-key": config.api_key}, json=payload)
    if response.status_code != 200:
        raise _refusal(response, config)
    predictions = (_json(response, config) or {}).get("predictions") or []
    encoded = predictions[0].get("bytesBase64Encoded") if predictions else None
    if not encoded:
        raise ImageProviderError(f"{config.name} returned no image. Its safety filter may have declined the prompt.")
    return _b64(encoded, config)


_STABILITY_ROUTES = {
    "stable-image-core": ("core", None),
    "stable-image-ultra": ("ultra", None),
    "sd3.5-large": ("sd3", "sd3.5-large"),
    "sd3.5-medium": ("sd3", "sd3.5-medium"),
}


def _stability(config, prompt, negative, width, height, eliminate_watermark):
    route, model_field = _STABILITY_ROUTES[config.model]
    fields = {
        "prompt": prompt[:10000],
        "aspect_ratio": {"square": "1:1", "landscape": "16:9", "portrait": "4:5"}[_shape(width, height)],
        "output_format": "jpeg",
    }
    if negative:
        fields["negative_prompt"] = negative[:10000]
    if model_field:
        fields["model"] = model_field
    response = _send(
        "POST", f"{ENDPOINTS['stability']}/v2beta/stable-image/generate/{route}", config, CLOUD_TIMEOUT,
        headers={"Authorization": f"Bearer {config.api_key}", "Accept": "image/*"},
        # The API takes multipart form data only; an empty file part makes
        # requests send it that way.
        files={"none": ("", b"")}, data=fields,
    )
    if response.status_code != 200:
        raise _refusal(response, config)
    return response.content


def _replicate(config, prompt, negative, width, height, eliminate_watermark):
    base = ENDPOINTS["replicate"]
    headers = {"Authorization": f"Bearer {config.api_key}"}
    payload = {"input": {
        "prompt": prompt,
        "aspect_ratio": {"square": "1:1", "landscape": "16:9", "portrait": "4:5"}[_shape(width, height)],
        "output_format": "jpg",
    }}
    response = _send("POST", f"{base}/models/{config.model}/predictions", config, CLOUD_TIMEOUT,
                     headers={**headers, "Prefer": "wait=60"}, json=payload)
    if response.status_code not in (200, 201):
        raise _refusal(response, config)
    prediction = _json(response, config) or {}

    deadline = time.time() + CLOUD_TIMEOUT
    while prediction.get("status") in ("starting", "processing") and time.time() < deadline:
        poll = (prediction.get("urls") or {}).get("get") or ""
        # Polled only at Replicate's own address, with the key.
        if _host(poll) != _host(base):
            break
        time.sleep(2)
        response = _send("GET", poll, config, CHECK_TIMEOUT, headers=headers)
        if response.status_code != 200:
            raise _refusal(response, config)
        prediction = _json(response, config) or {}

    status = prediction.get("status")
    if status != "succeeded":
        reason = _egress.redact(prediction.get("error") or "")[:200]
        if status in ("starting", "processing"):
            raise ImageProviderError(f"{config.name} had not finished after {CLOUD_TIMEOUT} seconds.")
        raise ImageProviderError(f"{config.name} did not make the image ({status or 'no status'}).{' ' + reason if reason else ''}")
    output = prediction.get("output")
    if isinstance(output, list):
        output = output[0] if output else None
    return _download(output, base, config)


def _fal(config, prompt, negative, width, height, eliminate_watermark):
    base = ENDPOINTS["fal"]
    payload = {
        "prompt": prompt,
        "image_size": {"square": "square_hd", "landscape": "landscape_16_9", "portrait": "portrait_4_3"}[_shape(width, height)],
        "num_images": 1,
        # The image comes back in this answer instead of from a second host.
        "sync_mode": True,
    }
    response = _send("POST", f"{base}/{config.model}", config, CLOUD_TIMEOUT,
                     headers={"Authorization": f"Key {config.api_key}"}, json=payload)
    if response.status_code != 200:
        raise _refusal(response, config)
    images = (_json(response, config) or {}).get("images") or []
    if not images:
        raise ImageProviderError(f"{config.name} returned no image.")
    return _download(images[0].get("url"), base, config)


def _together(config, prompt, negative, width, height, eliminate_watermark):
    base = ENDPOINTS["together"]
    gen_w, gen_h = _LOCAL_SIZE[_shape(width, height)]
    payload: Dict[str, Any] = {
        "model": config.model, "prompt": prompt, "width": gen_w, "height": gen_h,
        "n": 1, "response_format": "b64_json",
    }
    if "schnell" in config.model.lower():
        payload["steps"] = 4
    response = _send("POST", f"{base}/images/generations", config, CLOUD_TIMEOUT,
                     headers={"Authorization": f"Bearer {config.api_key}"}, json=payload)
    if response.status_code != 200:
        raise _refusal(response, config)
    items = (_json(response, config) or {}).get("data") or []
    if not items:
        raise ImageProviderError(f"{config.name} returned no image.")
    if items[0].get("b64_json"):
        return _b64(items[0]["b64_json"], config)
    return _download(items[0].get("url"), base, config)


def _automatic1111(config, prompt, negative, width, height, eliminate_watermark):
    gen_w, gen_h = _LOCAL_SIZE[_shape(width, height)]
    payload: Dict[str, Any] = {
        "prompt": prompt, "negative_prompt": negative or "", "width": gen_w, "height": gen_h, "steps": 25,
    }
    if config.model:
        payload["override_settings"] = {"sd_model_checkpoint": config.model}
        payload["override_settings_restore_afterwards"] = True
    response = _send("POST", f"{config.base_url}/sdapi/v1/txt2img", config, LOCAL_TIMEOUT, json=payload)
    if response.status_code == 404:
        raise ImageProviderError(f"The web UI at {config.base_url} answered, but its API is off. Start it with the --api option.")
    if response.status_code != 200:
        raise _refusal(response, config)
    images = (_json(response, config) or {}).get("images") or []
    if not images:
        raise ImageProviderError(f"{config.name} returned no image.")
    return _b64(images[0], config)


def _comfy_workflow(prompt: str, negative: str, checkpoint: str, width: int, height: int) -> Dict[str, Any]:
    """ComfyUI's own default text-to-image graph, with the prompt filled in."""
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": random.randint(1, 2 ** 32 - 1), "steps": 25, "cfg": 7, "sampler_name": "euler",
            "scheduler": "normal", "denoise": 1, "model": ["4", 0], "positive": ["6", 0],
            "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "", "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "inox_hydra", "images": ["8", 0]}},
    }


def _comfy_checkpoints(config) -> List[str]:
    response = _send("GET", f"{config.base_url}/object_info/CheckpointLoaderSimple", config, CHECK_TIMEOUT)
    if response.status_code != 200:
        raise _refusal(response, config)
    info = (_json(response, config) or {}).get("CheckpointLoaderSimple") or {}
    spec = ((info.get("input") or {}).get("required") or {}).get("ckpt_name") or []
    # Older ComfyUI: [[names], {...}]. Newer: ["COMBO", {"options": [names]}].
    if spec and isinstance(spec[0], list):
        return [str(name) for name in spec[0]]
    if len(spec) > 1 and isinstance(spec[1], dict):
        return [str(name) for name in spec[1].get("options") or []]
    return []


def _comfyui(config, prompt, negative, width, height, eliminate_watermark):
    checkpoint = config.model
    if not checkpoint:
        names = _comfy_checkpoints(config)
        if not names:
            raise ImageProviderError("ComfyUI has no checkpoint in its models/checkpoints folder.")
        checkpoint = names[0]
    gen_w, gen_h = _LOCAL_SIZE[_shape(width, height)]
    graph = _comfy_workflow(prompt, negative, checkpoint, gen_w, gen_h)
    response = _send("POST", f"{config.base_url}/prompt", config, CHECK_TIMEOUT,
                     json={"prompt": graph, "client_id": uuid.uuid4().hex})
    if response.status_code != 200:
        raise _refusal(response, config)
    prompt_id = (_json(response, config) or {}).get("prompt_id")
    if not prompt_id:
        raise ImageProviderError("ComfyUI did not queue the workflow.")

    deadline = time.time() + LOCAL_TIMEOUT
    while time.time() < deadline:
        response = _send("GET", f"{config.base_url}/history/{prompt_id}", config, CHECK_TIMEOUT)
        entry = (_json(response, config) or {}).get(prompt_id) if response.status_code == 200 else None
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ImageProviderError("ComfyUI stopped the workflow with an error. Its own window says why.")
            for output in (entry.get("outputs") or {}).values():
                for image in output.get("images") or []:
                    view = _send("GET", f"{config.base_url}/view", config, CHECK_TIMEOUT, params={
                        "filename": image.get("filename", ""),
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    })
                    if view.status_code != 200:
                        raise _refusal(view, config)
                    return view.content
            if status.get("completed"):
                raise ImageProviderError("ComfyUI finished the workflow without an image.")
        time.sleep(1)
    raise ImageProviderError(f"ComfyUI had not finished after {LOCAL_TIMEOUT} seconds.")


_GENERATORS = {
    "pollinations": _pollinations,
    "openai": _openai,
    "gemini": _gemini,
    "stability": _stability,
    "replicate": _replicate,
    "fal": _fal,
    "together": _together,
    "automatic1111": _automatic1111,
    "comfyui": _comfyui,
}


def generate(config: ImageProviderConfig, prompt: str, negative: str, width: int, height: int,
             eliminate_watermark: bool = True) -> bytes:
    """
    The image, as bytes the caller can open with Pillow.

    Raises ImageProviderError with a sentence on every failure, a refusal by
    the egress guard included (refused=True). Never returns an empty result.
    """
    reason = config.not_ready()
    if reason:
        raise ImageProviderError(reason)
    try:
        data = _GENERATORS[config.provider](config, prompt, negative, width, height, eliminate_watermark)
    except _egress.EgressRefused as refusal:
        raise ImageProviderError(f"Nothing was sent to {config.name}: {refusal}", refused=True)
    except ImageProviderError:
        raise
    except Exception as error:
        raise ImageProviderError(f"{config.name} failed: {_short(error)}")
    return _image(data, config)


# ---------------------------------------------------------------------------
# Checking and saving a setup
# ---------------------------------------------------------------------------

def _check_url(provider: str, base_url: str) -> str:
    """The address a local web UI may be reached at, or ImageProviderError."""
    meta = PROVIDERS[provider]
    candidate = (base_url or meta.get("default_url", "")).strip().rstrip("/")
    try:
        parts = urlsplit(candidate)
    except ValueError:
        parts = None
    if not parts or parts.scheme not in ("http", "https") or not parts.hostname:
        raise ImageProviderError(f"Enter the web address {meta['name']} shows when it starts, such as {meta['default_url']}.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ImageProviderError("Enter the address without a name, password or anything after a ? or #.")
    if parts.scheme == "http":
        where, leaves = _where(candidate)
        if leaves and not where.startswith("another computer on your network"):
            raise ImageProviderError("An address on the internet needs https, so the prompt is not sent in the clear.")
    return candidate


def _verify(config: ImageProviderConfig) -> Tuple[str, List[str], str]:
    """
    Asks the provider whether this setup works, without making an image.

    Returns (message, models it lists, model to save). Raises
    ImageProviderError when it does not.
    """
    name, model = config.name, config.model
    if config.provider == "openai":
        response = _send("GET", f"{ENDPOINTS['openai']}/models/{quote(model, safe='')}", config, CHECK_TIMEOUT,
                         headers={"Authorization": f"Bearer {config.api_key}"})
        if response.status_code == 404:
            raise ImageProviderError(f"The key works, but OpenAI does not offer the model '{model}' to it.")
        if response.status_code != 200:
            raise _refusal(response, config)
        return f"OpenAI accepted the key. Model: {model}.", [], model

    if config.provider == "gemini":
        headers = {"x-goog-api-key": config.api_key}
        response = _send("GET", f"{ENDPOINTS['gemini']}/models/{quote(model, safe='')}", config, CHECK_TIMEOUT, headers=headers)
        if response.status_code == 404:
            raise ImageProviderError(f"The key works, but Google does not offer the model '{model}' to it.")
        if response.status_code != 200:
            raise _refusal(response, config)
        label = (_json(response, config) or {}).get("displayName") or model
        models: List[str] = []
        listing = _send("GET", f"{ENDPOINTS['gemini']}/models", config, CHECK_TIMEOUT, headers=headers,
                        params={"pageSize": 1000})
        if listing.status_code == 200:
            models = [str(item.get("name", "")).replace("models/", "", 1)
                      for item in (_json(listing, config) or {}).get("models") or []
                      if "imagen" in str(item.get("name", ""))]
        return f"Google accepted the key. Model: {label}.", models, model

    if config.provider == "stability":
        if model not in _STABILITY_ROUTES:
            raise ImageProviderError(f"Choose one of the Stability AI models: {', '.join(_STABILITY_ROUTES)}.")
        response = _send("GET", f"{ENDPOINTS['stability']}/v1/user/balance", config, CHECK_TIMEOUT,
                         headers={"Authorization": f"Bearer {config.api_key}"})
        if response.status_code != 200:
            raise _refusal(response, config)
        credits = (_json(response, config) or {}).get("credits")
        left = f" Credits left: {credits:g}." if isinstance(credits, (int, float)) else ""
        return f"Stability AI accepted the key. Model: {model}.{left}", list(_STABILITY_ROUTES), model

    if config.provider == "replicate":
        if model.count("/") != 1 or ":" in model:
            raise ImageProviderError("Write the Replicate model as owner/name, such as black-forest-labs/flux-schnell.")
        response = _send("GET", f"{ENDPOINTS['replicate']}/models/{model}", config, CHECK_TIMEOUT,
                         headers={"Authorization": f"Bearer {config.api_key}"})
        if response.status_code == 404:
            raise ImageProviderError(f"The token works, but Replicate has no model '{model}'.")
        if response.status_code != 200:
            raise _refusal(response, config)
        return f"Replicate accepted the token. Model: {model}.", [], model

    if config.provider == "together":
        response = _send("GET", f"{ENDPOINTS['together']}/models", config, CHECK_TIMEOUT,
                         headers={"Authorization": f"Bearer {config.api_key}"})
        if response.status_code != 200:
            raise _refusal(response, config)
        listed = _json(response, config)
        listed = listed.get("data", []) if isinstance(listed, dict) else listed or []
        models = [str(item.get("id")) for item in listed if isinstance(item, dict) and item.get("type") == "image"]
        if models and model not in models:
            raise ImageProviderError(f"The key works, but Together lists no image model '{model}'. It lists: {', '.join(models[:8])}.")
        return f"Together AI accepted the key. Model: {model}.", models, model

    if config.provider == "automatic1111":
        response = _send("GET", f"{config.base_url}/sdapi/v1/options", config, CHECK_TIMEOUT)
        if response.status_code == 404:
            raise ImageProviderError(f"The web UI at {config.base_url} answered, but its API is off. Start it with the --api option.")
        if response.status_code != 200:
            raise _refusal(response, config)
        loaded = str((_json(response, config) or {}).get("sd_model_checkpoint") or "")
        listing = _send("GET", f"{config.base_url}/sdapi/v1/sd-models", config, CHECK_TIMEOUT)
        models = [str(item.get("title")) for item in (_json(listing, config) if listing.status_code == 200 else []) or []
                  if isinstance(item, dict) and item.get("title")]
        if model and models and model not in models:
            raise ImageProviderError(f"The web UI has no model '{model}'. It has: {', '.join(models[:8])}.")
        chosen = model or loaded
        return (f"{name} answered at {config.base_url}. Model: {chosen or 'the one loaded in the web UI'}.",
                models, model)

    if config.provider == "comfyui":
        models = _comfy_checkpoints(config)
        if not models:
            raise ImageProviderError("ComfyUI answered, but has no checkpoint in its models/checkpoints folder.")
        if model and model not in models:
            raise ImageProviderError(f"ComfyUI has no checkpoint '{model}'. It has: {', '.join(models[:8])}.")
        chosen = model or models[0]
        return f"ComfyUI answered at {config.base_url}. Model: {chosen}.", models, chosen

    raise ImageProviderError(f"{name} has no check.")


def _not_checked_message(config: ImageProviderConfig) -> str:
    if config.provider == "pollinations":
        return "Saved. The free public generator needs no account, so there is nothing to check."
    if config.provider == "off":
        return "Saved. Generate is off, and nothing is sent anywhere to make an image."
    return (f"Saved, not checked: {config.name} has no way to check a key without making an image, "
            "which it bills. The first Generate checks it.")


def save(provider: str, api_key: str = "", model: str = "", base_url: str = "") -> Dict[str, Any]:
    """
    Checks a setup and, when it works, makes it the profile's image provider.

    Raises ImageProviderError, having written nothing, when it does not. A
    blank key keeps the key already saved for this provider, or uses the AI
    provider's key when that is the same company; a key typed here is never
    written over the AI settings.
    """
    from datetime import datetime

    if provider not in PROVIDERS:
        raise ImageProviderError(f"There is no image provider called '{provider}'.")
    meta = PROVIDERS[provider]
    key = (api_key or "").strip()
    key_from = "own" if key else ""

    if meta["needs_key"] and not key:
        saved = current_config()
        ai = _ai_config()
        if saved.provider == provider and saved.source == "chosen" and saved.key_from == "own" and saved.api_key:
            key, key_from = saved.api_key, "own"
        elif provider in _SHARES_AI_KEY and ai.provider == provider and ai.api_key:
            key, key_from = "", "ai_provider"
        else:
            raise ImageProviderError(f"Enter your {meta['name']} key.")
    if not meta["needs_key"]:
        key, key_from = "", ""

    model = (model or "").strip()
    if not model:
        # An empty model field keeps the model already in use with this
        # provider, chosen here or carried over from the AI provider; only a
        # model the creator picks changes it.
        in_use = current_config()
        if in_use.provider == provider and in_use.source in ("chosen", "ai_provider"):
            model = in_use.model
    # The model goes into the request path at some providers, so it is a name
    # and nothing that could walk that path somewhere else.
    if model and (not _MODEL_NAME.match(model) or ".." in model):
        raise ImageProviderError("A model name has only letters, digits, spaces and the signs . _ - / : ( ) [ ].")

    url = _check_url(provider, base_url) if meta["needs_url"] else ""
    config = ImageProviderConfig(provider, model, key, url, source="chosen", key_from=key_from)
    if key_from == "ai_provider":
        config.api_key = _ai_config().api_key

    models: List[str] = list(meta["models"])
    verified_at = ""
    if meta["check"] == "none":
        message = _not_checked_message(config)
        saved_model = config.model
    else:
        try:
            message, listed, saved_model = _verify(config)
        except _egress.EgressRefused as refusal:
            raise ImageProviderError(f"Not checked, and not saved: {refusal}", refused=True)
        if listed:
            models = listed
        verified_at = datetime.now().isoformat(timespec="seconds")

    conn = get_db()
    try:
        with conn:
            for setting, value in (
                (_K_PROVIDER, provider), (_K_KEY, key if key_from == "own" else ""),
                (_K_MODEL, saved_model), (_K_URL, url), (_K_VERIFIED, verified_at),
                (_K_CHECK, message), (_K_KEY_FROM, key_from),
            ):
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (setting, _seal(setting, value)),
                )
    finally:
        conn.close()

    return {"message": message, "models": models, "config": current_config().to_public()}
