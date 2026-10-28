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
               below it, which is then never sent again. allowed_updates is
               remembered, as Telegram remembers it, and only those kinds
               of update are delivered
  sendMessage  records the chat, the text and any inline keyboard, and
               answers with a message
  answerCallbackQuery
               answers a button press once, with an optional notice; a
               press answered twice, or never pressed, is refused as
               Telegram refuses it
  editMessageText, editMessageReplyMarkup
               change a message the bot sent, as the phone then shows it;
               an edit that changes nothing is refused ("message is not
               modified"), as Telegram refuses it
  getFile      a file a test added with `add_file`: its size and the path
               it is served at; an unknown file_id is refused as Telegram
               refuses it
  /file/bot<token>/<path>
               the file's bytes, as api.telegram.org serves a file a bot
               may download; recorded as a call to "file"

A press of an inline button is a callback_query update, pushed with
`press` (any data, from any chat) or `press_button` (a button the phone
shows now, by its label).

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
    def __init__(self, token: str, max_wait: float = 0.3, remembered_updates: Optional[List[str]] = None):
        self.token = token
        self.max_wait = max_wait
        self._updates: List[Dict[str, Any]] = []
        self._next_update = 1
        self.sent: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self.blocked_chats = set()
        # The kinds of update a bot asked for last, which Telegram keeps until
        # it is asked again: None is every kind, as for a bot never asked.
        self.allowed_updates: Optional[List[str]] = remembered_updates
        # Each message the bot sent, as the phone shows it now: its chat, its
        # text and its inline keyboard, changed by an edit.
        self.messages: Dict[int, Dict[str, Any]] = {}
        # Each button press pushed, by its query id: whether it was answered.
        self._queries: Dict[str, Dict[str, Any]] = {}
        self.answered: List[Dict[str, Any]] = []
        self.edits: List[Dict[str, Any]] = []
        self._plans: Dict[str, List[tuple]] = {}
        # Files the phone sent, by file_id: their bytes and the path getFile names.
        self.files: Dict[str, Dict[str, Any]] = {}
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
            body = {"message_id": update_id, "date": int(time.time()), "chat": {"id": int(chat_id), "type": "private"},
                    **message}
            if text is not None:
                body["text"] = text
            self._updates.append({"update_id": update_id, "message": body})
            self._cond.notify_all()
        return update_id

    def add_file(self, file_id: str, data: bytes, file_path: Optional[str] = None,
                 file_size: Optional[int] = None) -> None:
        """A file the phone sent, which getFile then names and the file address serves."""
        with self._cond:
            self.files[file_id] = {"data": bytes(data), "file_path": file_path or f"files/{file_id}.bin",
                                   "file_size": len(data) if file_size is None else file_size}

    def press(self, chat_id: Any, data: str, message_id: Optional[int] = None, from_id: Any = None) -> int:
        """
        A press of an inline button: a callback_query update with the
        button's data, from a chat (and a person, the chat's own by default),
        on a message the bot sent (the newest to that chat by default).
        """
        with self._cond:
            if message_id is None:
                mine = [m for m, held in self.messages.items() if held["chat_id"] == str(chat_id)]
                message_id = mine[-1] if mine else 1
            held = self.messages.get(message_id) or {"text": ""}
            update_id = self._next_update
            self._next_update += 1
            query_id = f"q{update_id}"
            self._queries[query_id] = {"answered": False}
            self._updates.append({"update_id": update_id, "callback_query": {
                "id": query_id,
                "from": {"id": int(from_id if from_id is not None else chat_id), "is_bot": False,
                         "first_name": "Someone"},
                "message": {"message_id": message_id, "chat": {"id": int(chat_id), "type": "private"},
                            "text": held.get("text") or ""},
                "chat_instance": "fake-instance",
                "data": data,
            }})
            self._cond.notify_all()
        return update_id

    def buttons(self, message_id: int) -> List[Dict[str, Any]]:
        """The buttons a message shows now, each {text, callback_data}, in order."""
        with self._cond:
            markup = (self.messages.get(message_id) or {}).get("reply_markup") or {}
        return [button for row in (markup.get("inline_keyboard") or []) for button in row]

    def press_button(self, label: str, chat_id: Any, message_id: Optional[int] = None) -> int:
        """Presses the button labelled `label` on the newest message to the chat that shows one now."""
        with self._cond:
            ids = [message_id] if message_id is not None else sorted(
                (m for m, held in self.messages.items() if held["chat_id"] == str(chat_id)), reverse=True)
        for found in ids:
            for button in self.buttons(found):
                if button.get("text") == label:
                    return self.press(chat_id, button["callback_data"], message_id=found)
        raise AssertionError(f"no message to chat {chat_id} shows a button labelled {label!r}")

    def message(self, message_id: int) -> Dict[str, Any]:
        """A message as the phone shows it now."""
        with self._cond:
            return dict(self.messages.get(message_id) or {})

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
        if len(parts) >= 3 and parts[0] == "file" and parts[1].startswith("bot"):
            return self._serve_file(handler, parts[1][3:], "/".join(parts[2:]))
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
        if method == "answerCallbackQuery":
            return self._answer_callback_query(handler, params)
        if method in ("editMessageText", "editMessageReplyMarkup"):
            return self._edit(handler, method, params)
        if method == "getFile":
            return self._get_file(handler, params)
        return self._answer(handler, 404, {"ok": False, "error_code": 404, "description": "Not Found"})

    def _get_file(self, handler, params: Dict[str, Any]) -> None:
        file_id = str(params.get("file_id") or "")
        with self._cond:
            held = self.files.get(file_id)
        if held is None:
            return self._answer(handler, 400, {"ok": False, "error_code": 400,
                                               "description": "Bad Request: invalid file_id"})
        return self._answer(handler, 200, {"ok": True, "result": {
            "file_id": file_id, "file_unique_id": f"u{file_id}", "file_size": held["file_size"],
            "file_path": held["file_path"]}})

    def _serve_file(self, handler, token: str, file_path: str) -> None:
        with self._cond:
            self.calls.append({"method": "file", "params": {"file_path": file_path}, "at": time.monotonic()})
            planned = self._plans.get("file") or []
            failure = planned.pop(0) if planned else None
            held = next((f for f in self.files.values() if f["file_path"] == file_path), None)
            self._cond.notify_all()
        if token != self.token:
            return self._answer(handler, 401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        if failure and failure[0] == "status":
            return self._answer(handler, failure[1], {"ok": False, "error_code": failure[1],
                                                      "description": failure[2]})
        if held is None:
            return self._answer(handler, 404, {"ok": False, "error_code": 404, "description": "Not Found"})
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(len(held["data"])))
        handler.end_headers()
        handler.wfile.write(held["data"])

    def _get_updates(self, handler, params: Dict[str, Any]) -> None:
        offset = int(params.get("offset") or 0)
        wait = min(float(params.get("timeout") or 0), self.max_wait)
        deadline = time.monotonic() + wait
        asked = params.get("allowed_updates")
        with self._cond:
            if asked is not None:
                # Kept until the bot asks again; an empty list is every kind.
                kinds = json.loads(asked) if isinstance(asked, str) else list(asked)
                self.allowed_updates = list(kinds) or None
            # Every update below the offset is confirmed, and gone for good.
            self._updates = [u for u in self._updates if u["update_id"] >= offset]
            # An update of a kind the bot did not ask for is never delivered.
            if self.allowed_updates is not None:
                self._updates = [u for u in self._updates
                                 if any(kind in u for kind in self.allowed_updates)]
            while not self._updates and time.monotonic() < deadline:
                self._cond.wait(min(deadline - time.monotonic(), 0.05))
            result = list(self._updates)
        return self._answer(handler, 200, {"ok": True, "result": result})

    def _answer_callback_query(self, handler, params: Dict[str, Any]) -> None:
        query_id = str(params.get("callback_query_id") or "")
        with self._cond:
            query = self._queries.get(query_id)
            if query is None or query["answered"]:
                return self._answer(handler, 400, {
                    "ok": False, "error_code": 400,
                    "description": "Bad Request: query is too old and response timeout expired or query ID is invalid"})
            query["answered"] = True
            self.answered.append({"callback_query_id": query_id, "text": params.get("text"),
                                  "params": dict(params)})
            self._cond.notify_all()
        return self._answer(handler, 200, {"ok": True, "result": True})

    def _edit(self, handler, method: str, params: Dict[str, Any]) -> None:
        chat = str(params.get("chat_id") or "")
        if chat in self.blocked_chats:
            return self._answer(handler, 403, {"ok": False, "error_code": 403,
                                               "description": "Forbidden: bot was blocked by the user"})
        try:
            message_id = int(params.get("message_id") or 0)
        except (TypeError, ValueError):
            message_id = 0
        with self._cond:
            held = self.messages.get(message_id)
            if held is None or held["chat_id"] != chat:
                return self._answer(handler, 400, {"ok": False, "error_code": 400,
                                                   "description": "Bad Request: message to edit not found"})
            text = params.get("text") if method == "editMessageText" else held["text"]
            # No reply_markup in an edit takes the buttons away.
            markup = params.get("reply_markup") or None
            if isinstance(markup, str):
                markup = json.loads(markup) or None
            if text == held["text"] and markup == held.get("reply_markup"):
                return self._answer(handler, 400, {
                    "ok": False, "error_code": 400,
                    "description": ("Bad Request: message is not modified: specified new message content and "
                                    "reply markup are exactly the same as a current content and reply markup of "
                                    "the message")})
            held["text"], held["reply_markup"] = text, markup
            self.edits.append({"method": method, "message_id": message_id, "chat_id": chat, "text": text,
                               "reply_markup": markup})
            self._cond.notify_all()
            shown = {"message_id": message_id, "chat": {"id": int(chat)}, "text": text}
        return self._answer(handler, 200, {"ok": True, "result": shown})

    def _send_message(self, handler, params: Dict[str, Any]) -> None:
        chat = str(params.get("chat_id") or "")
        if chat in self.blocked_chats:
            return self._answer(handler, 403, {"ok": False, "error_code": 403,
                                               "description": "Forbidden: bot was blocked by the user"})
        if not chat.lstrip("-").isdigit():
            return self._answer(handler, 400, {"ok": False, "error_code": 400,
                                               "description": "Bad Request: chat not found"})
        markup = params.get("reply_markup") or None
        if isinstance(markup, str):
            markup = json.loads(markup) or None
        with self._cond:
            message_id = len(self.sent) + 1
            self.sent.append({"chat_id": chat, "text": params.get("text"), "params": dict(params),
                              "message_id": message_id, "reply_markup": markup})
            self.messages[message_id] = {"chat_id": chat, "text": params.get("text"), "reply_markup": markup}
            self._cond.notify_all()
        return self._answer(handler, 200, {"ok": True, "result": {"message_id": message_id,
                                                                  "chat": {"id": int(chat)},
                                                                  "text": params.get("text")}})
