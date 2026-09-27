"""
Numbers the studio shows must be measured, or labelled as what they are.
========================================================================

Audit W15 to W17.

W15. Generated hooks carried predicted_score: 92 if the hook fit the fold, 80
if not. The composer showed it as "SCORE 92", a forecast nobody made.

W16. Swipe templates carry velocity_score and engagement_multiplier values that
were typed in by the template's author. The interface called the first
"VELOCITY", which reads as a rate someone observed. It is an editorial rating,
and is now labelled as one.

W17. The fold limit was 140 in the formatter and 180 in the copilot, so one
draft could be fold-safe on one screen and truncated on another.
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _ui(path):
    with open(os.path.join(UI, path), encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", source)


def test_generated_hooks_carry_no_invented_score():
    import repurposer

    for hook in repurposer.generate_10x_hooks("Most migrations fail because nobody owns the rollback."):
        assert "predicted_score" not in hook, "a hook is given a score that predicts nothing"
    assert "predicted_score" not in _ui("components/HookFilmstrip.tsx")
    assert "predicted_score" not in _ui("lib/api.ts")


def test_a_typed_rating_is_not_called_velocity():
    for path in ("components/HookFilmstrip.tsx", "components/SwipeSurface.tsx"):
        source = _ui(path)
        assert not re.search(r'"VELOCITY"|>\s*VELOCITY\b|\bVELOCITY \{', source), (
            f"{path} labels an author's typed rating as a measured velocity"
        )


def test_every_fold_check_uses_one_limit():
    import fold
    from agno_agentos.scar_tissue import validate_pre_fold_hook
    from agno_agentos.agents import content_copilot_agent
    import ingress

    assert validate_pre_fold_hook("x" * (fold.MOBILE_FOLD_CHARS + 1))[0] is False
    assert validate_pre_fold_hook("x" * fold.MOBILE_FOLD_CHARS)[0] is True
    assert content_copilot_agent.HOOK_FOLD_LIMIT == fold.MOBILE_FOLD_CHARS
    assert ingress.MOBILE_FOLD_CHAR_LIMIT == fold.MOBILE_FOLD_CHARS

    for base, _dirs, files in os.walk(os.path.join(REPO_ROOT, "studio", "backend")):
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as handle:
                text = handle.read()
            assert "max_chars=180" not in text and "180-char fold" not in text, (
                f"{name} carries its own fold limit again"
            )
