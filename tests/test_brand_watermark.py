"""
Brand watermark: the saved handle has to reach the image.
=========================================================

The defect: the profile lookup was guarded by `apply_brand is None`, but the
request model defaults apply_personal_watermark to False and the checkbox in
the interface always sends a boolean. The guard was never true, so the block
was unreachable. A creator who saved their handle in Settings and ticked the
box got an image stamped with the literal string "@creator", and their saved
position and style were ignored.

One condition was answering two different questions:

    should we stamp?   the request decides, because that is the checkbox the
                       creator just clicked
    what do we stamp?  the saved profile decides, because that is where the
                       handle lives

These tests exercise the real resolution logic out of image_studio against the
four things the interface and API actually send.
"""

import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from database import get_db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGE_STUDIO = os.path.join(REPO_ROOT, "studio", "backend", "image_studio.py")

SAVED_PROFILE = {
    "name": "Test Creator",
    "brand_watermark_enabled": True,
    "brand_watermark_text": "@savedhandle",
    "brand_watermark_position": "top_left",
    "brand_watermark_style": "solid_bar",
}


@pytest.fixture
def saved_creator_profile():
    """A creator who has filled in their brand settings, which is the case."""
    conn = get_db()
    try:
        previous = conn.execute(
            "SELECT value FROM settings WHERE key = 'creator_profile'"
        ).fetchone()
        previous_value = previous["value"] if previous else None

        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
            (json.dumps(SAVED_PROFILE),),
        )
        conn.commit()
    finally:
        conn.close()

    yield

    conn = get_db()
    try:
        if previous_value is None:
            conn.execute("DELETE FROM settings WHERE key = 'creator_profile'")
        else:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
                (previous_value,),
            )
        conn.commit()
    finally:
        conn.close()


def _resolve(options):
    """
    Runs the real watermark resolution block from image_studio.

    Extracted and executed rather than reimplemented, so the test cannot drift
    into asserting behaviour the shipped code does not have.
    """
    source = io.open(IMAGE_STUDIO, encoding="utf-8").read()
    start = source.index('            apply_brand = options.get("apply_personal_watermark")')
    end = source.index("            if apply_brand and apply_personal_brand_watermark", start)
    block = source[start:end]

    dedented = "\n".join(
        line[12:] if line.startswith(" " * 12) else line
        for line in block.splitlines()
    )

    namespace = {
        "options": dict(options),
        "get_db": get_db,
        "json": json,
        "task_id": "test-task",
        "self": type("FakeManager", (), {"_update_task": lambda *a, **k: None})(),
    }
    exec(dedented, namespace)
    return (
        namespace.get("apply_brand"),
        namespace.get("brand_text"),
        namespace.get("brand_pos"),
        namespace.get("brand_style"),
    )


def test_ticking_the_box_uses_the_saved_handle(saved_creator_profile):
    """
    The reported case. The creator saves a handle, ticks the box, leaves the
    text field empty. Before this fix the image said "@creator".
    """
    stamp, text, position, style = _resolve({
        "apply_personal_watermark": True,
        "personal_watermark_text": None,
    })

    assert stamp is True
    assert text == "@savedhandle", (
        "the saved handle did not reach the image; got " + repr(text)
    )
    assert position == "top_left", "the saved position was ignored"
    assert style == "solid_bar", "the saved style was ignored"


def test_typed_text_wins_over_the_saved_handle(saved_creator_profile):
    """A one-off handle typed for this image is not overridden by Settings."""
    _stamp, text, position, _style = _resolve({
        "apply_personal_watermark": True,
        "personal_watermark_text": "@justthisonce",
    })
    assert text == "@justthisonce"
    # Details the request did not carry still come from the profile.
    assert position == "top_left"


def test_unticking_the_box_wins_over_a_saved_enabled_flag(saved_creator_profile):
    """
    The profile says watermarking is enabled. The creator just unticked it for
    this image. The click is the more recent instruction.
    """
    stamp, _text, _position, _style = _resolve({
        "apply_personal_watermark": False,
        "personal_watermark_text": None,
    })
    assert stamp is False, "an explicit False was overridden by the saved profile"


def test_an_api_caller_that_omits_the_field_falls_back_to_the_profile(saved_creator_profile):
    """
    Nothing in the interface omits it, but the field is Optional, so a caller
    that leaves it out should get the creator's saved preference.
    """
    stamp, text, _position, _style = _resolve({})
    assert stamp is True
    assert text == "@savedhandle"


def test_no_saved_handle_means_no_watermark_rather_than_an_invented_one():
    """
    With nothing to stamp, stamp nothing.

    The old code fell back to the literal "@creator", which put a handle this
    studio invented onto the creator's image. The same reasoning as "a fresh
    install belongs to nobody": absence is reported, not filled in.
    """
    conn = get_db()
    try:
        previous = conn.execute(
            "SELECT value FROM settings WHERE key = 'creator_profile'"
        ).fetchone()
        previous_value = previous["value"] if previous else None
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
            (json.dumps({"name": "", "brand_watermark_text": ""}),),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        stamp, text, _position, _style = _resolve({
            "apply_personal_watermark": True,
            "personal_watermark_text": None,
        })
        assert not (text or "").strip(), "a handle was invented from nowhere"
        assert stamp is False, (
            "the watermark was applied with no handle to stamp, which is how "
            "the literal @creator ended up on images"
        )
    finally:
        conn = get_db()
        try:
            if previous_value is None:
                conn.execute("DELETE FROM settings WHERE key = 'creator_profile'")
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('creator_profile', ?)",
                    (previous_value,),
                )
            conn.commit()
        finally:
            conn.close()


def test_the_creator_placeholder_is_gone_from_the_code():
    """
    Structural backstop. The literal must not return as a default, only as the
    comments explaining why it was removed.
    """
    source = io.open(IMAGE_STUDIO, encoding="utf-8").read()
    live = [
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    ]
    offenders = [line.strip() for line in live if '"@creator"' in line]
    assert not offenders, (
        "the invented handle is back in live code: " + str(offenders)
    )
