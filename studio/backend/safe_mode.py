"""
Starting with a damaged database.

A crash or a disk fault part way through a write can leave the database file
unreadable. The studio used to raise "database disk image is malformed" while
starting and never serve at all, so the desktop splash said to quit and start
again, which never helps, and the help article that explains recovery was
served by the studio that would not start.

Now the studio starts in safe mode instead. It serves one page, at every
address, that names the problem, says where the file is, lists the backups
newest first with the exact command that restores each, and offers a Restore
button. The API answers 503 with the same explanation, except health, which
still answers so the desktop shell opens the window onto that page, and the
two safe-mode routes. A restore takes a safety copy of the damaged files
first (support.restore_backup), and when the restored database opens, the
studio leaves safe mode without a restart.

Nothing in safe mode reads or writes the damaged file.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
"""

import html
import logging
import os
import threading
from typing import Any, Dict, Optional

try:
    from . import paths, support
except ImportError:  # top-level import mode
    import paths
    import support

_log = logging.getLogger("studio.safe_mode")
_lock = threading.Lock()
_state: Dict[str, Any] = {"active": False, "problem": None, "database": None}

STATE_PATH = "/api/v1/safe-mode"
RESTORE_PATH = "/api/v1/safe-mode/restore"
BACKUPS_SHOWN = 5


def enter(error: BaseException) -> None:
    with _lock:
        _state.update(active=True, problem=str(error) or type(error).__name__, database=paths.get_db_path())
    _log.error("The database at %s could not be opened (%s). Starting in safe mode.", paths.get_db_path(), error)


def leave() -> None:
    with _lock:
        _state.update(active=False, problem=None, database=None)


def is_active() -> bool:
    return bool(_state["active"])


def describe() -> Dict[str, Any]:
    """What the page and the API say: the problem, the file, and what to do."""
    backups = support.restorable_backups()
    newest = backups[0] if backups else None
    if newest:
        next_step = (
            f"Restore your newest backup, {newest['name']} from {newest['modified'].replace('T', ' ')}. "
            "The damaged file is kept in a safety copy first."
        )
    else:
        next_step = (
            "There is no backup to restore. Quit the studio, move the damaged file out of the data folder, "
            "and start the studio again: it starts empty, and the damaged file stays where you put it."
        )
    return {
        "safe_mode": True,
        "code": "database_damaged",
        "problem": _state["problem"],
        "database": _state["database"],
        "message": f"The studio's database file is damaged ({_state['problem']}), so the studio started in "
                   f"safe mode and has not read or changed it. {next_step}",
        "next_step": next_step,
        "backups": [dict(entry, command=support.restore_command(entry["path"]))
                    for entry in backups[:BACKUPS_SHOWN]],
        "doctor": "python -m studio.cli doctor",
    }


def restore(name: str, reopen) -> Dict[str, Any]:
    """
    Restores the named backup from the backups folder, then tries to reopen.

    `reopen` brings the database up as a normal start would and raises if it
    still cannot; on success safe mode ends. Only a file listed as restorable
    can be named, so a request cannot point the restore anywhere else.
    """
    chosen = next((entry for entry in support.restorable_backups() if entry["name"] == name), None)
    if chosen is None:
        raise ValueError("That backup is not in the backups folder, or cannot be restored.")
    result = support.restore_backup(chosen["path"])
    try:
        reopen()
    except Exception as still:
        with _lock:
            _state.update(problem=str(still))
        raise RuntimeError(
            f"{chosen['name']} was restored, but the studio still cannot open the database ({still}). "
            "Try an older backup."
        ) from still
    leave()
    return {"restored_from": chosen["name"], "safety_backup": result.get("safety_backup"),
            "message": f"Restored {chosen['name']}. The studio is running normally again."}


def page() -> str:
    """The one page safe mode serves. Self contained: no script or style from anywhere else."""
    info = describe()
    rows = []
    for entry in info["backups"]:
        rows.append(
            "<li><div><strong>{name}</strong><span>{kind}, {when}</span></div>"
            "<code>{command}</code>"
            "<button type=\"button\" data-name=\"{name}\">Restore this backup</button></li>".format(
                name=html.escape(entry["name"]),
                kind="full backup" if entry["kind"] == "backup" else "database copy",
                when=html.escape(entry["modified"].replace("T", " ")),
                command=html.escape(entry["command"]),
            )
        )
    listing = "<ol>" + "".join(rows) + "</ol>" if rows else "<p>There are no backups in the backups folder.</p>"
    folder = html.escape(os.path.dirname(info["database"] or ""))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inox Hydra: safe mode</title>
<style>
:root {{ --ink: #1d2433; --muted: #5b6475; --line: #d7dbe3; --paper: #ffffff; --accent: #1f5fbf; --warn: #9a3412; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --ink: #e7eaf0; --muted: #a3abba; --line: #343b4a; --paper: #12161f; --accent: #7fb0ff; --warn: #fdba74; }}
}}
body {{ margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 46rem; margin: 0 auto; padding: 2rem 1rem; }}
h1 {{ font-size: 1.5rem; margin: 0 0 1rem; }}
.problem {{ color: var(--warn); }}
ol {{ padding: 0; list-style: none; }}
li {{ border: 1px solid var(--line); border-radius: 8px; padding: 0.75rem 1rem; margin: 0 0 0.75rem; }}
li span {{ color: var(--muted); margin-left: 0.5rem; }}
code {{ display: block; overflow-wrap: anywhere; color: var(--muted); margin: 0.5rem 0; font-size: 0.85rem; }}
button {{ font: inherit; padding: 0.4rem 0.9rem; border-radius: 6px; border: 1px solid var(--accent);
  background: var(--accent); color: var(--paper); cursor: pointer; }}
button[disabled] {{ opacity: 0.6; cursor: wait; }}
#outcome {{ font-weight: 600; }}
</style></head>
<body><main>
<h1>The studio's database is damaged</h1>
<p class="problem">{html.escape(info["problem"] or "")}</p>
<p>The studio started in safe mode and has not read or changed the file. It is in {folder}.</p>
<p>{html.escape(info["next_step"])}</p>
<h2>Backups, best first</h2>
{listing}
<p id="outcome" role="status" aria-live="polite"></p>
<p>From a terminal, <code>{html.escape(info["doctor"])}</code> prints the same restore command.</p>
</main>
<script>
document.querySelectorAll("button[data-name]").forEach(function (button) {{
  button.addEventListener("click", function () {{
    var outcome = document.getElementById("outcome");
    if (!confirm("Restore " + button.dataset.name + "? A safety copy of the damaged files is kept first.")) return;
    button.disabled = true;
    outcome.textContent = "Restoring " + button.dataset.name + "...";
    fetch("{RESTORE_PATH}", {{ method: "POST", credentials: "same-origin",
      headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{ name: button.dataset.name }}) }})
      .then(function (r) {{ return r.json().then(function (body) {{ return {{ ok: r.ok, body: body }}; }}); }})
      .then(function (answer) {{
        var said = answer.body && (answer.body.message || (answer.body.detail && answer.body.detail.message));
        outcome.textContent = said || (answer.ok ? "Restored." : "The restore did not finish.");
        if (answer.ok) setTimeout(function () {{ window.location.replace("/"); }}, 1500);
        else button.disabled = false;
      }})
      .catch(function () {{ outcome.textContent = "The studio did not answer. Run the command shown instead."; button.disabled = false; }});
  }});
}});
</script>
</body></html>"""
