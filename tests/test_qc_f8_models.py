"""
Quality cycle 2026-10, batch F8: no retired Claude model id is offered to a
user or used as a default anywhere, not only where WRITE-14 looked.

README, the docs and studio_cli.py's --model help still named
claude-3-5-sonnet-20241022 and friends, which Anthropic no longer serves, so a
user copying the documented command saved a model that fails every request.
tests/test_qc_f2_models.py holds the gateway, the Prompt tab and the help
article; this holds everything else that a user reads or runs.

Left alone on purpose: CHANGELOG.md (history), the tests that use an old id as
inert fixture data, and the Day 08 demo draft in studio/backend/database.py.
That draft is sample content, not a default, and the demo cleanup recognises
an untouched seeded draft by its exact text; changing the text would leave the
copy 2.5.1 seeded into every install unrecognised and never removed.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RETIRED = re.compile(r"claude-(?:3|2|instant)[\w.-]*")
CURRENT_CLAUDE = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
SEEDED_DEMO = os.path.join("studio", "backend", "database.py")


def _user_facing_files():
    yield os.path.join(REPO_ROOT, "README.md")
    yield os.path.join(REPO_ROOT, "studio_cli.py")
    for top in ("docs", os.path.join("studio", "backend"), os.path.join("studio", "ui", "src"),
                os.path.join("studio", "extension")):
        for folder, dirs, files in os.walk(os.path.join(REPO_ROOT, top)):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__")]
            for name in files:
                if name.endswith((".md", ".py", ".ts", ".tsx", ".js", ".json")):
                    path = os.path.join(folder, name)
                    if os.path.relpath(path, REPO_ROOT) != SEEDED_DEMO:
                        yield path


def test_no_retired_claude_id_is_offered_anywhere_a_user_reads_or_runs():
    found = []
    for path in _user_facing_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                for hit in RETIRED.findall(line):
                    found.append(f"{os.path.relpath(path, REPO_ROOT)}:{number}: {hit}")
    assert not found, "retired Claude model ids:\n" + "\n".join(found)


def test_the_documented_anthropic_commands_use_a_current_model():
    for rel in ("docs/AI_ENGINE.md", "docs/BYO_AI_ARCHITECTURE.md"):
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as handle:
            text = handle.read()
        models = re.findall(r"--provider anthropic [^\n]*--model (\S+)", text)
        assert models and set(models) <= CURRENT_CLAUDE, (rel, models)
