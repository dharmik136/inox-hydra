"""
Exporting again into a vault never costs the creator what they wrote.
=====================================================================

Two ways it did:

  - write_vault wrote every generated path without asking whether the file was
    its own. A note the creator made by hand, People/Mei Lin.md about someone
    met offline, was replaced wholesale the first time a lead called Mei Lin
    was captured.
  - People notes were named by display name with " (2)" handed out in database
    order, and "Your notes" travelled with the file path. Deleting one Rahul
    Sharma moved the other's note, and the creator's notes about the CTO,
    onto the intern.

Now each note is keyed to a stable id in the manifest and keeps its path, a
name the creator's own note uses is never handed out, and a generated note the
creator edited is left exactly as it is.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import obsidian_export, paths  # noqa: E402

POST_URN = "urn:li:activity:7383000000000000001"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_vault_ids_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from studio.backend.database import init_db

    init_db()
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
        "VALUES (?, 'Flour waste, measured.', '2026-10-01T08:00:00+00:00', '2026-10-01', '2026-10-01')",
        (POST_URN,),
    )
    conn.commit()
    conn.close()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _lead(lead_id, name, headline, created_at):
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(
        "INSERT INTO leads (id, name, full_name, headline, status, created_at) VALUES (?, ?, ?, ?, 'New Lead', ?)",
        (lead_id, name, name, headline, created_at),
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text) VALUES (?, ?, 'COMMENT', ?)",
        (lead_id, POST_URN, f"A comment from {headline}."),
    )
    conn.commit()
    conn.close()


def _forget(lead_id):
    from studio.backend.crm import reverse_crm

    assert reverse_crm.purge_lead(lead_id)["lead_deleted"]


def _read(root, relative):
    with open(os.path.join(root, relative), encoding="utf-8") as handle:
        return handle.read()


def _add_your_notes(root, relative, text):
    with open(os.path.join(root, relative), "a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _people(root):
    return {
        name: _read(root, f"People/{name}")
        for name in os.listdir(os.path.join(root, "People"))
    }


def test_a_note_the_creator_wrote_is_never_overwritten(home, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    mine = os.path.join(root, "People", "Mei Lin.md")
    os.makedirs(os.path.dirname(mine), exist_ok=True)
    with open(mine, "w", encoding="utf-8") as handle:
        handle.write("# Mei Lin\n\nMet Mei at the Ahmedabad bakers meetup. Owes me a sourdough starter.\n")
    with open(mine, "rb") as handle:
        before = handle.read()

    _lead("lead-mei", "Mei Lin", "Owner at Lin Bakes", "2026-10-02 10:00:00")
    result = obsidian_export.export_obsidian_vault(root)

    with open(mine, "rb") as handle:
        assert handle.read() == before, "the creator's own note was overwritten"
    generated = [n for n, text in _people(root).items() if "Owner at Lin Bakes" in text]
    assert generated and generated[0] != "Mei Lin.md", generated
    assert result["renamed"] == [{"wanted": "People/Mei Lin.md", "written": f"People/{generated[0]}"}], result["renamed"]

    # And on the export after that, both are still where they were.
    obsidian_export.export_obsidian_vault(root)
    with open(mine, "rb") as handle:
        assert handle.read() == before
    assert "Owner at Lin Bakes" in _read(root, f"People/{generated[0]}")


def test_the_command_line_says_when_it_named_around_your_note(home, tmp_path, capsys):
    from studio import cli

    root = str(tmp_path / "vault")
    assert cli.main(["export", "--format", "obsidian", "--output", root]) == 0
    os.makedirs(os.path.join(root, "People"), exist_ok=True)
    with open(os.path.join(root, "People", "Mei Lin.md"), "w", encoding="utf-8") as handle:
        handle.write("Mine.\n")
    _lead("lead-mei", "Mei Lin", "Owner at Lin Bakes", "2026-10-02 10:00:00")
    capsys.readouterr()

    assert cli.main(["export", "--format", "obsidian", "--output", root]) == 0
    said = capsys.readouterr().out
    assert "People/Mei Lin.md is a note of yours, so this one was written to People/Mei Lin (2).md." in said, said


def test_your_notes_stay_with_the_person_when_a_namesake_is_forgotten(home, tmp_path):
    _lead("lead-rahul-cto", "Rahul Sharma", "CTO at DoughOps", "2026-10-01 09:00:00")
    _lead("lead-rahul-intern", "Rahul Sharma", "Intern at Bake School", "2026-10-02 09:00:00")
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]

    notes = _people(root)
    cto = next(n for n, t in notes.items() if "CTO at DoughOps" in t)
    intern = next(n for n, t in notes.items() if "Intern at Bake School" in t)
    _add_your_notes(root, f"People/{cto}", "Talked to Rahul (CTO) on 12 Oct: budget approved.")
    _add_your_notes(root, f"People/{intern}", "Intern, met at the school fair.")

    _forget("lead-rahul-cto" if cto == "Rahul Sharma.md" else "lead-rahul-intern")
    survivor = intern if cto == "Rahul Sharma.md" else cto
    obsidian_export.export_obsidian_vault(root)

    for name, text in _people(root).items():
        if "CTO at DoughOps" in text:
            assert "Intern, met at" not in text, f"{name} carries another person's notes"
        if "Intern at Bake School" in text:
            assert "budget approved" not in text, f"{name} carries the forgotten person's notes:\n{text}"
    survivor_text = _read(root, f"People/{survivor}")
    own = "budget approved" if survivor == cto else "Intern, met at"
    assert own in survivor_text, "the surviving person lost their own notes"


def test_a_new_namesake_does_not_take_an_existing_persons_note(home, tmp_path):
    # The trailing full stop is dropped from the note name, so both people
    # want "Arjun Berg.md", and the newcomer sorts first.
    _lead("lead-arjun-b", "Arjun Berg.", "Baker at North", "2026-10-03 09:00:00")
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    _add_your_notes(root, "People/Arjun Berg.md", "Arjun from North, call Friday.")

    _lead("lead-arjun-a", "Arjun Berg", "Baker at South", "2026-09-01 09:00:00")
    obsidian_export.export_obsidian_vault(root)

    text = _read(root, "People/Arjun Berg.md")
    assert "Baker at North" in text and "call Friday" in text, text


def test_a_generated_note_the_creator_edited_is_left_as_it_is(home, tmp_path):
    _lead("lead-grace", "Grace Hopper", "Engineer", "2026-10-01 09:00:00")
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    path = os.path.join(root, "People", "Grace Hopper.md")
    text = _read(root, "People/Grace Hopper.md").replace("\nEngineer\n", "\nRear Admiral, and my mentor\n")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)

    result = obsidian_export.export_obsidian_vault(root)
    assert _read(root, "People/Grace Hopper.md") == text, "an edited note was overwritten"
    assert result["kept_edited"] == ["People/Grace Hopper.md"], result
    fresh = [n for n, t in _people(root).items() if n != "Grace Hopper.md" and "\nEngineer\n" in t]
    assert fresh, "the refreshed note was not written beside the edited one"


def test_a_forgotten_persons_note_keeps_only_what_the_creator_wrote(home, tmp_path):
    """Forgetting someone removes their captured record from the vault too."""
    _lead("lead-asha", "Asha Rao", "Founder at Crumb Co", "2026-10-01 09:00:00")
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    _add_your_notes(root, "People/Asha Rao.md", "Wants the flour sheet.")

    _forget("lead-asha")
    obsidian_export.export_obsidian_vault(root)

    text = _read(root, "People/Asha Rao.md")
    assert "Wants the flour sheet." in text
    assert "Founder at Crumb Co" not in text and "A comment from" not in text, text
    manifest = json.loads(_read(root, obsidian_export.MANIFEST))
    assert "People/Asha Rao.md" not in manifest["files"], "the export still claims a note that is now the creator's"
