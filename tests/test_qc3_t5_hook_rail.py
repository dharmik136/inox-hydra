"""
The engineering pack adds to the hook rail; it never evicts the starter forms.
=============================================================================

MAKING.md M-1. `get_templates` orders by `velocity_score DESC`
(intelligence_sync.py). The twelve neutral starter forms carry
`velocity_score = NULL`, which SQLite sorts last in that order, and every one
of the opt-in engineering pack's 36 forms carries a score of 9.8 down. So a
rail asking the server for twelve came back twelve of twelve pack forms: one
click of "Add the engineering pack" replaced the creator's own neutral forms
in the Composer entirely, and Alt+1 then put another author's first-person
claim ("I spent $2,400 on creator SaaS...") over the creator's opening line
with no warning anywhere near it.

This establishes that the server still ranks the pack above the starters, and
then runs the real selection module the rail uses to prove the pack can only
ever take half of the rail, whatever the ranking says.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
import intelligence_sync  # noqa: E402
from database import get_db  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_DIR = os.path.join(REPO_ROOT, "studio", "ui")
RAIL_MODULE = os.path.join(UI_DIR, "src", "lib", "hookRail.ts")
FILMSTRIP = os.path.join(UI_DIR, "src", "components", "HookFilmstrip.tsx")
NODE = shutil.which("node") or shutil.which("node.exe")

client = TestClient(app_module.app, base_url="http://127.0.0.1")


def _esbuild():
    for name in ("esbuild.cmd", "esbuild"):
        candidate = os.path.join(UI_DIR, "node_modules", ".bin", name)
        if os.path.exists(candidate):
            return candidate
    return None


@pytest.fixture
def library():
    """The template library as it was, put back afterwards."""
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM viral_templates")]
    conn.execute("DELETE FROM viral_templates")
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM viral_templates")
    for row in rows:
        columns = ", ".join(row)
        conn.execute(
            f"INSERT INTO viral_templates ({columns}) VALUES ({', '.join('?' for _ in row)})",
            tuple(row.values()),
        )
    conn.commit()
    conn.close()


def _templates(limit=200):
    return client.get(f"/api/v1/intelligence/templates?limit={limit}").json()["templates"]


def test_the_server_still_ranks_the_pack_above_every_starter(library):
    """
    The hazard itself. If this fails the ordering changed, and the selection
    below is guarding against something that no longer happens.
    """
    _templates()  # seeds the starter forms on first read
    starters = _templates()
    assert starters, "a new library holds no hook forms at all"
    assert all(t["velocity_score"] is None for t in starters), "a starter carries a rating nobody measured"

    added = client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True})
    assert added.status_code == 200, added.text

    # What the rail used to ask for: the first twelve, by the server's order.
    first_twelve = _templates(limit=12)
    assert len(first_twelve) == 12
    assert all(t["velocity_score"] is not None for t in first_twelve), (
        "the server no longer sorts every rated pack form above the creator's own forms"
    )


def test_the_whole_library_is_readable_in_one_read(library):
    """The rail now reads the library, not a ranked twelve of it."""
    _templates()
    starters = len(_templates())
    client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True})
    everything = _templates(limit=200)
    assert len(everything) == starters + len(intelligence_sync.ENGINEERING_PACK)
    assert sum(1 for t in everything if t["velocity_score"] is None) == starters


# The probe runs the module the rail imports, against a library shaped like a
# real one: twelve unrated starter forms and the pack's rated forms, in the
# order the server answers with (every rated form first, the unrated last).
PROBE = r"""
import { selectRailTemplates, RAIL_SIZE } from "./hookRail.js";

const pack = Array.from({ length: 36 }, (_, i) => ({
  id: 100 + i,
  hook_text: "pack " + i,
  velocity_score: 9.8 - i * 0.1,
}));
const starters = Array.from({ length: 12 }, (_, i) => ({
  id: i,
  hook_text: "[starter] " + i,
  velocity_score: null,
}));

const withPack = selectRailTemplates([...pack, ...starters]);
const withoutPack = selectRailTemplates([...starters]);
const tinyLibrary = selectRailTemplates([...pack, starters[0], starters[1]]);

console.log(JSON.stringify({
  railSize: RAIL_SIZE,
  withPack: {
    total: withPack.length,
    starters: withPack.filter((p) => !p.fromPack).length,
    fromPack: withPack.filter((p) => p.fromPack).length,
    firstIsStarter: withPack.length > 0 && !withPack[0].fromPack,
    texts: withPack.map((p) => p.item.hook_text),
  },
  withoutPack: {
    total: withoutPack.length,
    starters: withoutPack.filter((p) => !p.fromPack).length,
  },
  tinyLibrary: {
    total: tinyLibrary.length,
    starters: tinyLibrary.filter((p) => !p.fromPack).length,
  },
}));
"""


@pytest.fixture(scope="module")
def rail():
    """Compiles studio/ui/src/lib/hookRail.ts and runs the probe against it."""
    esbuild = _esbuild()
    if not NODE:
        pytest.skip("Node is not installed, cannot execute the hook rail module")
    if not esbuild:
        pytest.skip("studio/ui dependencies are not installed, cannot compile TypeScript")
    with tempfile.TemporaryDirectory() as work:
        build = subprocess.run(
            [esbuild, RAIL_MODULE, "--format=esm", f"--outfile={os.path.join(work, 'hookRail.js')}"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert build.returncode == 0, build.stderr
        with open(os.path.join(work, "probe.mjs"), "w", encoding="utf-8") as handle:
            handle.write(PROBE)
        run = subprocess.run(
            [NODE, "probe.mjs"], capture_output=True, text=True, encoding="utf-8", cwd=work,
        )
        assert run.returncode == 0, run.stderr
        return json.loads(run.stdout)


def test_the_pack_never_takes_more_than_half_the_rail(rail):
    """The defect, stated as the rule that now holds: half the rail is yours."""
    assert rail["withPack"]["total"] == rail["railSize"]
    assert rail["withPack"]["starters"] >= rail["railSize"] / 2, (
        "the pack evicted the creator's own starter forms below half the rail"
    )
    assert rail["withPack"]["fromPack"] > 0, "an installed pack should still reach the rail"


def test_a_library_with_no_pack_fills_the_rail_with_starters(rail):
    """Nothing changes for a creator who never asked for the pack."""
    assert rail["withoutPack"]["total"] == rail["railSize"]
    assert rail["withoutPack"]["starters"] == rail["railSize"]


def test_the_pack_may_fill_what_the_starters_cannot(rail):
    """With only two starter forms in the library, the rail is not left short."""
    assert rail["tinyLibrary"]["total"] == rail["railSize"]
    assert rail["tinyLibrary"]["starters"] == 2


def test_a_pack_form_is_named_on_the_rail_and_the_warning_is_beside_it():
    """
    The warning that these make first-person claims was on the Swipe File
    screen only, while the keystroke that applies one is in the Composer.
    """
    with open(FILMSTRIP, encoding="utf-8") as handle:
        source = handle.read()
    assert "selectRailTemplates" in source, "the rail does not use the selection module"
    assert "fetchHookTemplates(LIBRARY_FETCH_LIMIT)" in source, "the rail still asks for a ranked twelve"
    assert "fromPack" in source
    assert "PACK" in source, "a pack form is not named on its own card"
    assert "first-person claims" in source, "the Composer still carries no warning about pack forms"
