"""
A fake Telegram Bot API on loopback, for the suite.
===================================================

The real ingress is driven against this over HTTP, through
telegram_bot.API_BASE, so the worker's own loop, its egress check, its
offsets, its parsing and its replies all run as they do against
api.telegram.org. Nothing here reaches the network: it listens on 127.0.0.1
and answers from memory.

What it does, as the Bot API does:

  getUpdates   long polling: waits up to the request's timeout (capped by
               `max_wait`) for an update; an offset confirms every update
               below it, which is then never sent again
  sendMessage  records the chat and the text and answers with a message

And the failures a real bot meets, planned per method with `plan`:

  ("429", n)            Too Many Requests, with parameters.retry_after n
  ("drop",)             the connection closed before any answer
  ("status", code, why) an error answer, such as 409 for a second poller
  blocked chats         403 "Forbidden: bot was blocked by the user"
  another token         401 "Unauthorized"

Strict Invariants:
- Zero em-dashes.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit


class FakeTelegram:
    def __init__(self, token: str, max_wait: float = 0.3):
        self.token = token
        self.max_wait = max_wait
        self._updates: List[Dict[str, Any]] = []
        self._next_update = 1
        self.sent: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self.blocked_chats = set()
        self._plans: Dict[str, List[tuple]] = {}
        self._cond = threading.Condition()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- what a test does ---------------------------------------------------

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "FakeTelegram":
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                fake._serve(self)

            def do_POST(self):
                fake._serve(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        with self._cond:
            self._cond.notify_all()
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def push(self, chat_id: Any, text: Optional[str] = None, **message: Any) -> int:
        """A message the phone sends: queued as an update until an offset confirms it."""
        with self._cond:
            update_id = self._next_update
            self._next_update += 1
            body = {"message_id": update_id, "chat": {"id": int(chat_id), "type": "private"}, **message}
            if text is not None:
                body["text"] = text
            self._updates.append({"update_id": update_id, "message": body})
            self._cond.notify_all()
        return update_id

    def plan(self, method: str, *failures: tuple) -> None:
        """The next calls of `method` fail as planned, in order; then it answers normally."""
        with self._cond:
            self._plans.setdefault(method, []).extend(failures)

    def waiting(self) -> List[int]:
        """Update ids not yet confirmed by an offset."""
        with self._cond:
            return [u["update_id"] for u in self._updates]

    def wait_for(self, predicate, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while not predicate():
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 0.05))
        return True

    def wait_for_sent(self, count: int, timeout: float = 8.0) -> List[Dict[str, Any]]:
        self.wait_for(lambda: len(self.sent) >= count, timeout)
        with self._cond:
            return list(self.sent)

    def calls_of(self, method: str) -> List[Dict[str, Any]]:
        with self._cond:
            return [c for c in self.calls if c["method"] == method]

    # -- the Bot API ---------------------------------------------------------

    def _params(self, handler) -> Dict[str, Any]:
        query = {k: v[-1] for k, v in parse_qs(urlsplit(handler.path).query).items()}
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        if raw:
            kind = handler.headers.get("Content-Type", "")
            if "json" in kind:
                query.update(json.loads(raw.decode("utf-8")))
            else:
                query.update({k: v[-1] for k, v in parse_qs(raw.decode("utf-8")).items()})
        return query

    def _answer(self, handler, status: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def _serve(self, handler) -> None:
        parts = urlsplit(handler.path).path.strip("/").split("/")
        if len(parts) != 2 or not parts[0].startswith("bot"):
            return self._answer(handler, 404, {"ok": False, "error_code": 404, "description": "Not Found"})
        token, method = parts[0][3:], parts[1]
        params = self._params(handler)
        with self._cond:
            self.calls.append({"method": method, "params": dict(params), "at": time.monotonic()})
            planned = self._plans.get(method) or []
            failure = planned.pop(0) if planned else None
            self._cond.notify_all()
        if token != self.token:
            return self._answer(handler, 401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        if failure:
            if failure[0] == "drop":
                # The connection ends with no answer at all, as a network fault does.
                try:
                    handler.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                handler.close_connection = True
                return
            if failure[0] == "429":
                return self._answer(handler, 429, {"ok": False, "error_code": 429,
                                                   "description": f"Too Many Requests: retry after {failure[1]}",
                                                   "parameters": {"retry_after": failure[1]}})
            if failure[0] == "status":
                return self._answer(handler, failure[1], {"ok": False, "error_code": failure[1],
                                                          "description": failure[2]})
        if method == "getUpdates":
            return self._get_updates(handler, params)
        if method == "sendMessage":
            return self._send_message(handler, params)
        return self._answer(handler, 404, {"ok": False, "error_code": 404, "description": "Not Found"})

    def _get_updates(self, handler, params: Dict[str, Any]) -> None:
        offset = int(params.get("offset") or 0)
        wait = min(float(params.get("timeout") or 0), self.max_wait)
        deadline = time.monotonic() + wait
        with self._cond:
            # Every update below the offset is confirmed, and gone for good.
            self._updates = [u for u in self._updates if u["update_id"] >= offset]
            while not self._updates and time.monotonic() < deadline:
                self._cond.wait(min(deadline - time.monotonic(), 0.05))
            result = list(self._updates)
        return self._answer(handler, 200, {"ok": True, "result": result})

    def _send_message(self, handler, params: Dict[str, Any]) -> None:
        chat = str(params.get("chat_id") or "")
        if chat in self.blocked_chats:
            return self._answer(handler, 403, {"ok": False, "error_code": 403,
                                               "description": "Forbidden: bot was blocked by the user"})
        if not chat.lstrip("-").isdigit():
            return self._answer(handler, 400, {"ok": False, "error_code": 400,
                                               "description": "Bad Request: chat not found"})
        with self._cond:
            self.sent.append({"chat_id": chat, "text": params.get("text"), "params": dict(params)})
            message_id = len(self.sent)
            self._cond.notify_all()
        return self._answer(handler, 200, {"ok": True, "result": {"message_id": message_id,
                                                                  "chat": {"id": int(chat)},
                                                                  "text": params.get("text")}})
