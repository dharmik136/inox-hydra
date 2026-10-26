"""
The interface names a contrast's status the way the engine does.
================================================================

contrast_engine answers "not_enough_data" when a side is short of posts;
the interface's ContrastFinding type said "insufficient_sample", a word the
engine uses only for a confidence field (cycle 4, track 3, batch 0, from the
sections report's defects table). TypeScript could not catch it, because the
Patterns screen cast the status to a string before comparing it, which is
how a wrong name survives a type system.

The names are read out of both files here: every status the engine's
evaluator can answer, and the union the interface declares, must be the
same set, and no screen may cast the status away.
"""

import ast
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENGINE = os.path.join(REPO_ROOT, "studio", "backend", "contrast_engine.py")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")

# Answered only for a feature key the engine does not know, which
# compute_all_contrasts never asks about; it is not a finding's status.
NOT_A_FINDING = {"unknown_feature"}


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# The functions that answer a finding's record: the binary features'
# evaluator, the one it hands every form to since topics became forms
# (cycle 4, decision 7), the verdict both share, and the format evaluator
# (cycle 4, track 5), which hands its two sides to the same verdict.
EVALUATORS = ("evaluate_contrast_for_posts", "evaluate_feature", "_verdict", "evaluate_format_contrast")


def engine_statuses():
    tree = ast.parse(_read(ENGINE))
    evaluators = [node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name in EVALUATORS]
    assert evaluators, "the engine's evaluators were renamed; this test reads nothing"
    found = set()
    for evaluator in evaluators:
        for node in ast.walk(evaluator):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "status" and isinstance(value, ast.Constant):
                        found.add(value.value)
    return found - NOT_A_FINDING


def interface_statuses():
    source = _read(API)
    block = source.split("export interface ContrastFinding {", 1)[1].split("\n}", 1)[0]
    line = next(line for line in block.splitlines() if line.strip().startswith("status:"))
    return set(re.findall(r'"([a-z_]+)"', line))


def test_the_engine_answers_the_three_statuses_the_screens_handle():
    assert engine_statuses() == {"conclusive", "not_enough_data", "different_period"}


def test_the_interface_declares_exactly_the_engines_statuses():
    assert interface_statuses() == engine_statuses(), (
        f"the interface names {sorted(interface_statuses())}, the engine answers {sorted(engine_statuses())}"
    )


def test_no_screen_casts_a_status_to_a_string():
    """The cast is how the wrong name survived the type system."""
    offenders = []
    for name in sorted(os.listdir(COMPONENTS)):
        if not name.endswith(".tsx"):
            continue
        for number, line in enumerate(_read(os.path.join(COMPONENTS, name)).splitlines(), 1):
            if re.search(r"\.status as string", line):
                offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, "a screen casts a status away instead of naming it:\n" + "\n".join(offenders)
