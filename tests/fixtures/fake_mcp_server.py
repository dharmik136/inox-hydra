"""
A real MCP server, small enough to reason about, for the client tests.

Deliberately a subprocess speaking the actual wire format rather than a mock.
A mocked transport would prove the client calls its own functions in order and
nothing about whether it speaks the protocol, which is the only part that can
be wrong in a way a user would notice.

Behaviour is switched by argv so one file covers the awkward cases:

    (none)      a well behaved server with three resources
    noisy       writes a line of garbage to stdout before answering
    empty       handshakes, then offers no resources
    huge        offers one resource far larger than the per resource budget
    slow        never answers, to exercise the request timeout
    refuse      answers initialize with a JSON-RPC error
"""

import json
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"

RESOURCES = [
    {"uri": "notes://migration", "name": "Migration Notes",
     "text": "We moved the ledger to forward only migrations after a rollback "
             "wrote to a newer database on its way to refusing it."},
    {"uri": "notes://review", "name": "Design Review",
     "text": "Argued that reporting what happened beats reporting what was "
             "asked for. The queue pause was the example that convinced us."},
    {"uri": "notes://binary", "name": "A Screenshot",
     "blob": "iVBORw0KGgo="},
]

if MODE == "huge":
    RESOURCES = [{"uri": "notes://long", "name": "Long Document",
                  "text": "word " * 20000}]
if MODE == "empty":
    RESOURCES = []


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue

        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            if MODE == "refuse":
                send({"jsonrpc": "2.0", "id": request_id,
                      "error": {"code": -32600, "message": "not today"}})
                continue
            if MODE == "noisy":
                sys.stdout.write("starting up, this is not JSON\n")
                sys.stdout.flush()
            if MODE == "slow":
                time.sleep(60)
                continue
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"resources": {}},
                "serverInfo": {"name": "fake", "version": "1"},
            }})

        elif method == "notifications/initialized":
            continue

        elif method == "resources/list":
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "resources": [
                    {k: v for k, v in r.items() if k in ("uri", "name")}
                    for r in RESOURCES
                ]
            }})

        elif method == "resources/read":
            uri = (request.get("params") or {}).get("uri")
            match = next((r for r in RESOURCES if r["uri"] == uri), None)
            if match is None:
                send({"jsonrpc": "2.0", "id": request_id,
                      "error": {"code": -32602, "message": "no such resource"}})
                continue
            entry = {"uri": uri}
            if "text" in match:
                entry["text"] = match["text"]
            else:
                entry["blob"] = match["blob"]
            send({"jsonrpc": "2.0", "id": request_id,
                  "result": {"contents": [entry]}})

        elif request_id is not None:
            send({"jsonrpc": "2.0", "id": request_id,
                  "error": {"code": -32601, "message": f"no method {method}"}})


if __name__ == "__main__":
    main()
