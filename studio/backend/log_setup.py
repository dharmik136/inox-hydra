"""
What the studio writes to its log, and what it leaves out.

Every launcher runs uvicorn with its access log on and sends the console to
logs/engine.log, which the diagnostics bundle tails and the creator is asked
to attach to an issue. uvicorn's access line records each request with its
query string, so the log held every Ctrl+K search letter by letter, every
first-message topic and every help search: lead names and the creator's own
typed words, in a file described as safe to publish. The interface polls
every few seconds too, so the same lines grew the file by megabytes a day
until the next launch deleted it, crash and all.

So the access log keeps only what explains a failure:
- the path without its query string, never what was typed;
- a request that failed (status 400 or more) or changed something (any
  method but GET, HEAD and OPTIONS). A successful read, which is nearly all
  of the volume, is not written.

Installed on the logger itself, not a handler, so it holds whichever log
config the launcher gave uvicorn.
"""

import logging

ACCESS_LOGGER = "uvicorn.access"
_READS = ("GET", "HEAD", "OPTIONS")


def path_only(target: str) -> str:
    """A request target without its query string or fragment."""
    text = str(target or "")
    for mark in ("?", "#"):
        if mark in text:
            text = text.split(mark, 1)[0]
    return text


class PrivateAccessLog(logging.Filter):
    """Drops successful reads, and the query string from every line kept."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn's own access record: (client, method, path, http version, status).
        if not isinstance(args, tuple) or len(args) != 5:
            return True
        client, method, target, version, status = args
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = 0
        if str(method).upper() in _READS and 0 < code < 400:
            return False
        record.args = (client, method, path_only(target), version, status)
        return True


def install() -> None:
    """Adds the filter once, however many times the app module is imported."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(existing, PrivateAccessLog) for existing in logger.filters):
        logger.addFilter(PrivateAccessLog())
