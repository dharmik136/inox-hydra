"""
What A Post Did Is One Number
=============================
The studio's second central question, after the fold, is which of a creator's
posts worked. Six modules answered it, each with its own denominator, settled
rule, tie break and minimum sample, and on one creator's three years they
named six different posts as the best one in the same minute. The same ideas
were written out two to four times: SETTLED_AFTER_HOURS twice, _age_hours
twice and divergently, the qualified cut at 60 in four places, the VIP cut at
80 in two and 75 in another, the seven binary features in full in two files
with different labels, and the notable ratio as 1.25/0.8 in one module and
1.15/0.85 in the next.

results.py now holds each of those once. This test is the guard, in the shape
of test_fold_is_one_number.py: it reads the backend's source and fails if a
second definition appears, because a second definition is how the screens
came to disagree in the first place.
"""

import ast
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

import results  # noqa: E402

# Every module the engine is for. A new one that answers "what worked" belongs
# in this list.
READERS = ("insights.py", "evidence_briefing.py", "contrast_engine.py", "post_summary.py", "crm.py",
           "today.py", os.path.join("routers", "analytics.py"))


def _source(relative):
    with open(os.path.join(BACKEND, relative), encoding="utf-8") as handle:
        return handle.read()


def _python_files():
    for root, _dirs, files in os.walk(BACKEND):
        for name in sorted(files):
            if name.endswith(".py"):
                path = os.path.join(root, name)
                yield os.path.relpath(path, BACKEND), path


def test_one_module_declares_the_settled_rule():
    offenders = []
    for relative, path in _python_files():
        if relative == "results.py":
            continue
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                code = line.split("#")[0]
                if re.search(r"^\s*(SETTLED_AFTER_HOURS|SETTLE_BUCKETS|SETTLED_SHARE)\s*=\s*[^r]", code):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, ("a module declares its own settled rule, so a post is settled on one screen and "
                           "growing on another:\n" + "\n".join(offenders))


def test_one_module_declares_the_tiers_and_the_sample_rules():
    """A number a screen judges by is results.py's, or it is a second rule."""
    named = {
        "the VIP cut": r"^\s*[A-Z_]*VIP[A-Z_]*\s*=\s*(80|75)(\.0)?\b",
        "the qualified cut": r"^\s*[A-Z_]*QUALIFIED[A-Z_]*\s*=\s*(60|50)(\.0)?\b",
        "the nurture cut": r"^\s*[A-Z_]*NURTURE[A-Z_]*\s*=\s*30(\.0)?\b",
        "the minimum sample": r"^\s*(MIN_PER_SIDE|MIN_ARM_SAMPLE_SIZE|MIN_FOR_MEDIAN)\s*=\s*\d",
        "the notable ratio": r"^\s*[A-Z_]*NOTABLE[A-Z_]*\s*=\s*[01]\.\d",
        "the captured share": r"^\s*MIN_CAPTURED_SHARE[A-Z_]*\s*=\s*0\.\d",
    }
    offenders = []
    for relative, path in _python_files():
        if relative == "results.py":
            continue
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                code = line.split("#")[0]
                for what, pattern in named.items():
                    if re.search(pattern, code):
                        offenders.append(f"{relative}:{number} declares {what}: {line.strip()}")
    assert not offenders, ("a module writes out a cut point of its own:\n" + "\n".join(offenders))


def test_the_seven_features_are_written_out_once():
    """
    The feature table, the opening line and its two tests. Written twice, with
    different labels, the creator saw two wordings of the same test.
    """
    definitions = []
    for relative, path in _python_files():
        if relative == "results.py":
            continue
        tree = ast.parse(_source(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Name) and target.id in ("PATTERNS", "BINARY_FEATURES")
                            and not isinstance(node.value, (ast.Attribute, ast.Name))):
                        definitions.append(f"{relative}:{node.lineno}: {target.id}")
            if isinstance(node, ast.FunctionDef) and node.name in (
                    "opening_line", "_opens_with_symbol", "opens_with_symbol",
                    "_has_bold_unicode", "has_bold_unicode", "_age_hours", "age_hours",
                    "different_periods", "qualification_tier", "tier", "engagement_rate", "_rate"):
                if node.name == "_rate" and relative == os.path.join("routers", "analytics.py"):
                    # Kept as the router's own name for the one engine call.
                    continue
                definitions.append(f"{relative}:{node.lineno}: def {node.name}()")
    assert not definitions, ("a second copy of a rule results.py owns:\n" + "\n".join(definitions))


def test_every_reader_reads_the_engine():
    missing = [relative for relative in READERS if "results" not in _source(relative)]
    assert not missing, f"these modules answer what worked without reading the engine: {missing}"


def test_the_engine_imports_no_studio_module():
    """
    results.py is a leaf, like fold.py, so every module can read it and none
    of them can be left out of a cycle.
    """
    tree = ast.parse(_source("results.py"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.level or 0) > 0:
            imported.append(node.module or ".")
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
    studio = [name for name in imported if name in {module[:-3] for module, _ in _python_files()}]
    assert not studio, f"the engine imports studio modules: {studio}"


def test_the_engine_answers_every_question_the_batch_names():
    for name in ("SETTLED_AFTER_HOURS", "MIN_PER_SIDE", "MIN_FOR_MEDIAN", "VIP_SCORE", "QUALIFIED_SCORE",
                 "NURTURE_SCORE", "NOTABLE_HIGH", "NOTABLE_LOW", "MIN_CAPTURED_SHARE_TO_COMPARE",
                 "BINARY_FEATURES", "PAIR_BANDS", "SETTLE_BUCKETS"):
        assert hasattr(results, name), f"results.{name} is gone, so a caller will write its own"
    for name in ("age_hours", "is_settled", "figures", "engagement_rate", "rank", "ranking", "best",
                 "pair", "age_bands", "settle_curve", "settled_after_hours", "tier", "is_qualified",
                 "difference", "spread", "window_complete", "opening_line", "different_periods",
                 "usual_of", "against_usual", "median_of"):
        assert callable(getattr(results, name, None)), f"results.{name}() is gone"


def test_no_module_computes_a_rate_of_its_own():
    """
    An engagement rate is engagements over impressions, which cannot exceed
    100%: one post of 1,417 printed 116.25% because the figures came from two
    different readings and nothing checked.
    """
    offenders = []
    pattern = re.compile(r"(reactions|engagements)[^\n]{0,40}\*\s*100(\.0)?\s*/")
    for relative, path in _python_files():
        if relative == "results.py":
            continue
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if pattern.search(line.split("#")[0]):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, ("a module divides engagements by impressions itself, with no clamp and no check:\n"
                           + "\n".join(offenders))
