"""
A fake of every image provider's API, on this machine (cycle 2, batch R7).

Not a test module: the R7 tests import it. One HTTP server on 127.0.0.1
(port 18217, or any free port when that one is taken) answers the requests
each provider's code makes, in that provider's shapes, under a path prefix
per provider. The cloud providers are pointed at it by replacing
image_providers.ENDPOINTS; the local web UIs are given its address.

Every request is recorded with its path, query, headers and body, so a test
can see exactly what left the studio and where the key went.

The socket guard is the one sandbox_server.py installs: any connection that
is not to loopback raises before it is made, so nothing here can reach a real
image service whatever the code under test does.
"""

import base64
import io
import json
import random
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT = 18217
GOOD_KEY = "sk-notarealkey-r7-good-0123456789"

_LOOPBACK = ("127.", "::1", "localhost", "0.0.0.0")


def install_socket_guard(monkeypatch):
    """Refuses every connection and name lookup that is not loopback."""
    real_connect = socket.socket.connect
    real_create = socket.create_connection
    real_getaddrinfo = socket.getaddrinfo

    def host_of(address):
        return str(address[0] if isinstance(address, tuple) else address)

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not host_of(address).startswith(_LOOPBACK):
            raise ConnectionRefusedError(f"sandbox: outbound connection to {host_of(address)} refused")
        return real_connect(self, address)

    def guarded_create(address, *a, **k):
        if not host_of(address).startswith(_LOOPBACK):
            raise ConnectionRefusedError(f"sandbox: outbound connection to {host_of(address)} refused")
        return real_create(address, *a, **k)

    def guarded_getaddrinfo(host, *a, **k):
        if host and not str(host).startswith(_LOOPBACK):
            raise socket.gaierror(f"sandbox: name lookup for {host} refused")
        return real_getaddrinfo(host, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


def picture(width=1024, height=1024, fmt="JPEG"):
    """A noisy image, so it is a few tens of KB like a real one."""
    from PIL import Image

    rng = random.Random(width * 7 + height)
    image = Image.frombytes("RGB", (width, height), bytes(rng.getrandbits(8) for _ in range(width * height * 3 // 64)) * 64)
    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=70)
    return buf.getvalue()


class FakeImageServer:
    def __init__(self):
        self.requests = []
        # provider prefix -> (status, body bytes, content type), answered to
        # every request under that prefix instead of the normal answer.
        self.fail = {}
        self.jpeg = picture()
        self.png = picture(fmt="PNG")
        self.server = None

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def url(self, prefix):
        return f"{self.base}/{prefix}"

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, status, body, ctype="application/json"):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                parts = urlsplit(self.path)
                prefix, _, rest = parts.path.lstrip("/").partition("/")
                record = {
                    "method": method, "prefix": prefix, "path": "/" + rest, "query": parse_qs(parts.query),
                    "raw_path": self.path, "headers": dict(self.headers), "body": raw,
                }
                try:
                    record["json"] = json.loads(raw) if raw else None
                except ValueError:
                    record["json"] = None
                fake.requests.append(record)
                if prefix in fake.fail:
                    status, body, ctype = fake.fail[prefix]
                    return self._answer(status, body, ctype)
                answer = fake.route(record)
                return self._answer(*answer)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    # -- the providers' APIs --------------------------------------------------

    def _authorised(self, record, scheme="Bearer "):
        auth = record["headers"].get("Authorization") or record["headers"].get("x-goog-api-key") or ""
        return auth in (scheme + GOOD_KEY, GOOD_KEY)

    def _bad_key(self, record):
        # Echoes the key back, as OpenAI's own refusal does, so a test can
        # prove the studio scrubs it.
        said = record["headers"].get("Authorization") or record["headers"].get("x-goog-api-key") or ""
        return 401, {"error": {"message": f"Incorrect API key provided: {said.split(' ')[-1]}."}}

    def route(self, record):
        prefix, path, method = record["prefix"], record["path"], record["method"]
        b64 = base64.b64encode(self.jpeg).decode()

        if prefix == "pollinations" and path.startswith("/prompt/"):
            return 200, self.jpeg, "image/jpeg"

        if prefix == "openai":
            if not self._authorised(record):
                return self._bad_key(record)
            if method == "GET" and path.startswith("/models/"):
                model = path.split("/models/", 1)[1]
                if model not in ("gpt-image-1", "dall-e-3"):
                    return 404, {"error": {"message": f"The model '{model}' does not exist"}}
                return 200, {"id": model, "object": "model"}
            if path == "/images/generations":
                return 200, {"data": [{"b64_json": b64}]}

        if prefix == "gemini":
            if not self._authorised(record):
                return self._bad_key(record)
            if method == "GET" and path == "/models":
                return 200, {"models": [{"name": "models/imagen-4.0-generate-001"}, {"name": "models/gemini-2.5-flash"}]}
            if method == "GET" and path.startswith("/models/"):
                return 200, {"name": "models/" + path.split("/models/", 1)[1], "displayName": "Imagen 4"}
            if method == "POST" and path.endswith(":predict"):
                return 200, {"predictions": [{"bytesBase64Encoded": b64, "mimeType": "image/jpeg"}]}

        if prefix == "stability":
            if not self._authorised(record):
                return self._bad_key(record)
            if path == "/v1/user/balance":
                return 200, {"credits": 12.5}
            if path.startswith("/v2beta/stable-image/generate/"):
                return 200, self.png, "image/png"

        if prefix == "replicate":
            # The file host takes no key, and is sent none.
            if path == "/files/out.jpg":
                return 200, self.jpeg, "image/jpeg"
            if not self._authorised(record):
                return self._bad_key(record)
            if method == "POST" and path.endswith("/predictions"):
                return 201, {"id": "p1", "status": "processing", "urls": {"get": f"{self.base}/replicate/predictions/p1"}}
            if path == "/predictions/p1":
                return 200, {"id": "p1", "status": "succeeded", "output": [f"{self.base}/replicate/files/out.jpg"]}
            if method == "GET" and path.startswith("/models/"):
                return 200, {"owner": "black-forest-labs", "name": path.rsplit("/", 1)[-1]}

        if prefix == "fal":
            if record["headers"].get("Authorization") != "Key " + GOOD_KEY:
                return self._bad_key(record)
            return 200, {"images": [{"url": "data:image/jpeg;base64," + b64, "width": 1024, "height": 1024}]}

        if prefix == "together":
            if not self._authorised(record):
                return self._bad_key(record)
            if path == "/models":
                return 200, [{"id": "black-forest-labs/FLUX.1-schnell", "type": "image"}, {"id": "meta-llama/x", "type": "chat"}]
            if path == "/images/generations":
                return 200, {"data": [{"b64_json": b64}]}

        if prefix == "a1111":
            if path == "/sdapi/v1/options":
                return 200, {"sd_model_checkpoint": "sdxl_base.safetensors [31e35c80fc]"}
            if path == "/sdapi/v1/sd-models":
                return 200, [{"title": "sdxl_base.safetensors [31e35c80fc]"}, {"title": "dreamshaper_8.safetensors [879db523c3]"}]
            if path == "/sdapi/v1/txt2img":
                return 200, {"images": [base64.b64encode(self.png).decode()]}

        if prefix == "a1111-noapi":
            return 404, {"detail": "Not Found"}

        if prefix == "comfy":
            if path == "/object_info/CheckpointLoaderSimple":
                return 200, {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["sd_xl_base_1.0.safetensors", "flux1-schnell.safetensors"], {}]}}}}
            if path == "/prompt":
                return 200, {"prompt_id": "c1", "number": 1, "node_errors": {}}
            if path == "/history/c1":
                return 200, {"c1": {"status": {"status_str": "success", "completed": True},
                                    "outputs": {"9": {"images": [{"filename": "inox_hydra_00001_.png", "subfolder": "", "type": "output"}]}}}}
            if path == "/view":
                return 200, self.png, "image/png"

        return 404, {"detail": f"fake has no {method} {prefix}{path}"}
