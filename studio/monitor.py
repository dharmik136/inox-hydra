"""
Inox Hydra Live Data Ingestion Terminal Monitor.
================================================
Monitors data ingestion, bridge heartbeat status, and sync progression in real time.

Usage:
    python -m studio.cli monitor
    python monitor.py
    python monitor.py --once
    python monitor.py --interval 1.5 --limit 8

Strict Invariants:
- Zero em-dashes across all code, docstrings, and strings.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# ANSI color codes
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RED = "\033[31m"
CLEAR_SCREEN = "\033[2J\033[H"


def _format_ago(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "-"
    try:
        norm = iso_str.replace(" ", "T")
        if not norm.endswith("Z") and "+" not in norm:
            norm += "+00:00"
        dt = datetime.datetime.fromisoformat(norm)
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = max(0, int((now - dt).total_seconds()))
        if diff < 10:
            return "just now"
        if diff < 60:
            return f"{diff}s ago"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"
    except Exception:
        return iso_str[:16]


def _truncate(text: Optional[str], width: int) -> str:
    if not text:
        return ""
    clean = " ".join(text.split())
    if len(clean) <= width:
        return clean
    return clean[: width - 3] + "..."


def get_auth_token() -> str:
    """Retrieves API token from security module or token file."""
    try:
        from studio.backend import security
        return security.get_or_create_token()
    except Exception:
        token_path = os.path.expanduser("~/.config/inox-hydra/api_token")
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        return ""


def fetch_stream(host: str, port: int, token: str, limit: int = 10) -> Dict[str, Any]:
    url = f"http://{host}:{port}/api/v1/self/activity-stream?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "X-Inox-Token": token,
            "User-Agent": "InoxHydra-Monitor/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_dashboard(data: Dict[str, Any], is_tty: bool, limit: int = 5) -> None:
    summary = data.get("summary", {})
    creator = data.get("creator") or "Unknown"
    bridge_online = summary.get("bridge_connected", False)
    carrier = summary.get("bridge_carrier") or "Brave"
    last_seen = _format_ago(summary.get("bridge_last_seen"))

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if is_tty:
        sys.stdout.write(CLEAR_SCREEN)

    # Header
    status_indicator = f"{GREEN}● ONLINE{RESET}" if bridge_online else f"{YELLOW}○ IDLE{RESET}"
    title_line = f"{BOLD}INOX HYDRA - INGESTION MONITOR{RESET}  |  {now_str}  |  Creator: {CYAN}@{creator}{RESET}"
    bridge_line = f"Bridge Status: {status_indicator} ({carrier}, last heartbeat: {last_seen})"

    print("=" * 80)
    print(title_line)
    print(bridge_line)
    print("-" * 80)

    # Stat counters
    posts_cnt = summary.get("posts_count", 0)
    comments_cnt = summary.get("comments_count", 0)
    reactions_cnt = summary.get("reactions_count", 0)
    leads_cnt = summary.get("leads_count", 0)

    stats = (
        f"  {BOLD}POSTS:{RESET} {CYAN}{posts_cnt:<6}{RESET} "
        f"|  {BOLD}COMMENTS:{RESET} {GREEN}{comments_cnt:<6}{RESET} "
        f"|  {BOLD}REACTIONS:{RESET} {YELLOW}{reactions_cnt:<6}{RESET} "
        f"|  {BOLD}LEADS:{RESET} {MAGENTA}{leads_cnt:<6}{RESET}"
    )
    print(stats)

    # Sync progression
    sync_chain = summary.get("active_sync_chain")
    if sync_chain and sync_chain.get("active"):
        idx = sync_chain.get("current_index", 0)
        seq = sync_chain.get("sequence", [])
        stage = seq[idx] if idx < len(seq) else "finalizing"
        print(f"  {YELLOW}▶ ACTIVE SYNC SEQUENCE: Step {idx + 1}/{len(seq)} ({stage}){RESET}")
    print("-" * 80)

    # Section 1: Recent Posts
    recent_posts = data.get("recent_posts", [])[:limit]
    print(f"{BOLD}[ RECENT AUTHORED POSTS ({len(recent_posts)}) ]{RESET}")
    if not recent_posts:
        print("  (No authored posts loaded yet)")
    else:
        for p in recent_posts:
            urn = p.get("activity_urn", "").split(":")[-1]
            reacts = p.get("reactions") or 0
            cmts = p.get("comments") or 0
            age = _format_ago(p.get("last_seen_at"))
            excerpt = _truncate(p.get("excerpt"), 45)
            metrics = f"R:{reacts:<3} C:{cmts:<3}"
            print(f"  • {DIM}{urn}{RESET}  {CYAN}{metrics}{RESET}  {excerpt:<48} {DIM}({age}){RESET}")
    print()

    # Section 2: Recent Outbound Comments
    recent_comments = data.get("recent_comments", [])[:limit]
    print(f"{BOLD}[ OUTBOUND COMMENTS ({len(recent_comments)}) ]{RESET}")
    if not recent_comments:
        print("  (No outbound comments recorded yet)")
    else:
        for c in recent_comments:
            author = _truncate(c.get("target_author") or "Unknown", 18)
            text = _truncate(c.get("my_text") or "", 46)
            age = _format_ago(c.get("last_seen_at"))
            print(f"  • to {BOLD}{author:<18}{RESET} : \"{text}\" {DIM}({age}){RESET}")
    print()

    # Section 3: Recent Outbound Reactions
    recent_reactions = data.get("recent_reactions", [])[:limit]
    print(f"{BOLD}[ OUTBOUND REACTIONS ({len(recent_reactions)}) ]{RESET}")
    if not recent_reactions:
        print("  (No outbound reactions recorded yet)")
    else:
        for r in recent_reactions:
            kind = r.get("reaction_kind") or "like"
            author = _truncate(r.get("target_author") or "LinkedIn Post", 28)
            age = _format_ago(r.get("last_seen_at"))
            print(f"  • [{YELLOW}{kind.upper():<9}{RESET}] on {author:<28} {DIM}({age}){RESET}")
    print()

    # Section 4: Recent CRM Leads
    recent_leads = data.get("recent_leads", [])[:limit]
    print(f"{BOLD}[ AUDIENCE LEADS ({len(recent_leads)}) ]{RESET}")
    if not recent_leads:
        print("  (No audience leads identified yet)")
    else:
        for ld in recent_leads:
            name = _truncate(ld.get("name") or "Unknown", 22)
            headline = _truncate(ld.get("headline") or ld.get("company") or "", 36)
            score = ld.get("icp_score", 0.0)
            print(f"  • {BOLD}{name:<22}{RESET} (ICP: {score:<4}) | {headline}")
    print()

    # Section 5: Recent Import Diagnostics
    recent_imports = data.get("recent_imports", [])[:limit]
    print(f"{BOLD}[ RECENT IMPORT PIPELINE JOBS ({len(recent_imports)}) ]{RESET}")
    if not recent_imports:
        print("  (No import jobs on record)")
    else:
        for imp in recent_imports:
            kind = imp.get("kind", "").upper()
            outcome = imp.get("outcome", "unknown")
            items = imp.get("items_seen")
            items_str = f"{items} items" if items is not None else "pending"
            req_ago = _format_ago(imp.get("requested_at"))
            status_color = GREEN if outcome == "completed" else (YELLOW if outcome == "pending" else DIM)
            print(f"  • {kind:<10} [{status_color}{outcome:<10}{RESET}] {items_str:<12} (requested {req_ago})")

    print("=" * 80)
    if is_tty:
        print(f"{DIM}Press Ctrl+C to exit monitor.{RESET}")


def run_monitor(
    host: str = "127.0.0.1",
    port: int = 8000,
    interval: float = 2.0,
    limit: int = 5,
    once: bool = False,
    as_json: bool = False,
) -> int:
    token = get_auth_token()
    is_tty = sys.stdout.isatty() and not as_json

    while True:
        try:
            data = fetch_stream(host, port, token, limit=limit)
            if as_json:
                print(json.dumps(data, indent=2))
            else:
                render_dashboard(data, is_tty=is_tty, limit=limit)
        except urllib.error.URLError as err:
            err_msg = f"Cannot connect to Inox Hydra Studio at {host}:{port}: {err.reason}"
            if is_tty:
                sys.stdout.write(CLEAR_SCREEN)
            print("=" * 80)
            print(f"{RED}STUDIO SERVER OFFLINE OR UNREACHABLE{RESET}")
            print(err_msg)
            print("Ensure the backend server is running: .venv/bin/python -m uvicorn studio.backend.app:app")
            print("=" * 80)
        except KeyboardInterrupt:
            print(f"\n{GREEN}Monitor terminated.{RESET}")
            return 0
        except Exception as exc:
            print(f"Monitor error: {exc}")

        if once:
            return 0

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{GREEN}Monitor terminated.{RESET}")
            return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="monitor",
        description="Inox Hydra real-time ingestion and bridge activity monitor.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Studio host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Studio port (default: 8000)")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds (default: 2.0)")
    parser.add_argument("--limit", type=int, default=5, help="Items per category to display (default: 5)")
    parser.add_argument("--once", action="store_true", help="Print current status once and exit")
    parser.add_argument("--json", action="store_true", help="Output stream as JSON")
    args = parser.parse_args(argv)

    return run_monitor(
        host=args.host,
        port=args.port,
        interval=args.interval,
        limit=args.limit,
        once=args.once,
        as_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
