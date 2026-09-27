"""
The Fold Is One Number
======================
The studio's central question about a draft is whether its opening survives
LinkedIn's mobile fold. The backend answers it with fold.MOBILE_FOLD_CHARS,
which a change on main settled at 140 for every check: the audit, the hook
generator, the formatter and the ingress parser. That change guarded the
backend with a test and left the interface alone.

The interface carried its own number, 180, taken from the design blueprint.
So the editor drew the fold at 180 and told the writer the draft fitted, the
mobile preview cut it at 180, and the Audit tab, on the same screen, said the
same opening was over the limit. Two answers to the one question the product
exists to answer.

This reads both files, because the constant lives in TypeScript and Python and
nothing else joins them.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import fold  # noqa: E402

COMPOSER = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "ComposerCanvas.tsx")


def _interface_fold():
    with open(COMPOSER, encoding="utf-8") as handle:
        source = handle.read()
    found = re.findall(r"export const FOLD_CHARS\s*=\s*(\d+)\s*;", source)
    assert len(found) == 1, f"expected one FOLD_CHARS declaration, found {found}"
    return int(found[0])


def test_the_editor_and_the_audit_agree_on_the_fold():
    assert _interface_fold() == fold.MOBILE_FOLD_CHARS, (
        f"the editor draws the fold at {_interface_fold()} and the backend checks against "
        f"{fold.MOBILE_FOLD_CHARS}, so a draft is safe on one screen and cut on the other"
    )


def test_no_other_interface_file_carries_its_own_fold():
    """Every surface imports FOLD_CHARS; a literal would be a second fold."""
    ui = os.path.join(REPO_ROOT, "studio", "ui", "src")
    offenders = []
    for root, _, files in os.walk(ui):
        for name in files:
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    code = line.split("//")[0]
                    if code.strip().startswith("*"):
                        continue
                    if re.search(r"(fold|FOLD)[A-Za-z_]*\s*[=:]\s*(140|180|210)\b", code):
                        if "export const FOLD_CHARS" in code:
                            continue
                        offenders.append(f"{os.path.relpath(path, REPO_ROOT)}:{number}: {line.strip()}")
    assert not offenders, "a surface carries its own fold number:\n" + "\n".join(offenders)
