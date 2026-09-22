"""
Database connections are closed on the way out, including the failing way.
==========================================================================

CPython's refcounting hides this most of the time: when a function raises, the
frame is destroyed, the local connection loses its last reference, and
sqlite3.Connection.__del__ closes it. So a missing try/finally looks harmless
in a quick test.

It stops being harmless the moment anything retains the traceback, which is
exactly what a web framework does while it formats a 500, and what any error
logger does. The traceback holds the frame, the frame holds the connection, and
the connection stays OPEN for as long as the error object lives.

Measured before the fix: five failing ingests with their errors retained held
five open connections. After: zero.

Note what to measure. A closed sqlite3.Connection is still a live Python
object, so counting objects proves nothing. These tests count connections that
still answer a query, which is the only definition of "open" that matters.
"""

import gc
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

GUARDED_MODULES = (
    "studio/backend/leads.py",
    "studio/backend/app.py",
    "studio/backend/linkedin_client.py",
    "studio/backend/crm.py",
    "studio/backend/scheduler.py",
    "studio/backend/intelligence_sync.py",
)


def open_connection_count():
    """
    Connections that still answer a query.

    Counting isinstance(o, sqlite3.Connection) counts closed ones too, which is
    the mistake that makes this bug look either absent or unfixable depending
    on which way you squint.
    """
    gc.collect()
    total = 0
    for obj in gc.get_objects():
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.execute("SELECT 1")
                total += 1
            except Exception:
                pass
    return total


def test_a_failing_ingest_holds_no_open_connection():
    """
    The concrete case: the extension sends a percentage where a float is
    expected, float() raises partway through, and the error is retained.
    """
    from linkedin_client import linkedin_client

    before = open_connection_count()

    retained = []
    for _ in range(5):
        try:
            linkedin_client.ingest_analytics_payload(
                {"viewer_seniority": [{"label": "VP", "percentage": "12%"}]}
            )
        except Exception as err:
            retained.append(err)

    after = open_connection_count()
    assert after <= before, (
        f"{after - before} connections are still open after five failed ingests "
        f"whose errors are still referenced. A traceback keeps the frame alive, "
        f"so refcounting does not close them."
    )


def test_a_failing_lead_write_holds_no_open_connection():
    """leads.py had seven functions and zero try/finally blocks."""
    import leads

    before = open_connection_count()

    retained = []
    for _ in range(5):
        try:
            # A string where a list of dicts is expected, which is what an
            # older export or a hand edited payload produces.
            leads.batch_add_leads("not-a-list-of-leads")
        except Exception as err:
            retained.append(err)

    after = open_connection_count()
    assert after <= before, (
        f"{after - before} connections left open by failed batch writes"
    )


@pytest.mark.parametrize("relative", GUARDED_MODULES)
def test_every_function_that_opens_a_connection_guards_it(relative):
    """
    Structural, so a new route cannot quietly reintroduce the pattern.

    crm.py, scheduler.py and intelligence_sync.py already did this. leads.py
    and sixteen routes in app.py did not, which made them the exception to
    their own codebase's convention rather than a deliberate choice.
    """
    import ast
    import io

    source = io.open(os.path.join(REPO_ROOT, relative), encoding="utf-8").read()
    tree = ast.parse(source)

    unguarded = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        dumped = ast.dump(node)
        if "get_db" not in dumped:
            continue
        if any(isinstance(n, ast.Try) and n.finalbody for n in ast.walk(node)):
            continue
        unguarded.append(f"{node.name} (line {node.lineno})")

    assert not unguarded, (
        f"{relative} opens a database connection without a finally that closes "
        f"it:\n  " + "\n  ".join(unguarded)
        + "\n\nRefcounting hides this until something retains the traceback."
    )
