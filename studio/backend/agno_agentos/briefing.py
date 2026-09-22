"""
Agent Briefing: How This System Talks To A Model.
=================================================

Both generating agents used to hand the model a sentence and hope. The image
agent built a carefully engineered prompt out of style, palette, lighting and
composition rules, then, if a provider happened to be configured, threw all of
it away and used the model's 75 word reply instead. The reply had never been
told what the lighting was, what the aspect ratio was, or that the bottom third
of the frame had to stay empty for the quote compositor. Configuring an AI
provider therefore made the output worse, quietly, and nothing recorded that it
had happened.

This module is the fix. Three ideas, and they apply to every agent here.

  1. A brief, not a sentence.
     The model receives the resolved creative direction in labelled sections:
     who it is, the single objective, the inputs, the hard constraints, and the
     exact shape of an acceptable answer. Nothing that was already decided is
     left for the model to guess at or contradict.

  2. The model fills a slot, it does not replace the scaffold.
     An agent asks for the one part that benefits from language ability, the
     scene description or the hook line, and composes it back into the
     deterministic structure. Lighting, composition and negative space survive,
     because the model was never in a position to drop them.

  3. Every answer is checked before it is used.
     Preamble is stripped, length is enforced, banned tropes and em-dashes are
     caught, and forbidden subjects are rejected. A response that fails goes in
     the bin and the deterministic value stands. Silent acceptance is how a
     model's bad day becomes the product's bad day.

Provenance is recorded either way, so a maintainer looking at an image or a
hook can tell whether a model touched it, and if not, why not.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- A rejected response never degrades output below the deterministic baseline.
- Nothing here raises. Enhancement is an improvement, never a dependency.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from .scar_tissue import scrub_em_dashes, validate_banned_vocabulary


# Openers a model reaches for when it ignores an instruction to return only the
# answer. Cheap to strip, and leaving them in corrupts the composed prompt.
_PREAMBLE_PATTERNS = [
    re.compile(r"^\s*(sure|certainly|of course|absolutely)[,!.]?\s*", re.IGNORECASE),
    re.compile(r"^\s*here (?:is|are)(?: your| the)?[^:\n]{0,40}:\s*", re.IGNORECASE),
    re.compile(r"^\s*(?:final |optimi[sz]ed |enhanced )?prompt\s*:\s*", re.IGNORECASE),
    re.compile(r"^\s*output\s*:\s*", re.IGNORECASE),
    re.compile(r"^\s*```[a-z]*\s*", re.IGNORECASE),
]

_TRAILING_FENCE = re.compile(r"\s*```\s*$")


class Brief:
    """
    A structured directive for a single agent turn.

    Renders to two strings because that is what every provider in the gateway
    accepts: a system prompt establishing the role and the rules, and a user
    prompt carrying this turn's inputs and the required output shape.
    """

    def __init__(
        self,
        role: str,
        objective: str,
        inputs: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        forbidden: Optional[List[str]] = None,
        output_contract: str = "",
    ):
        self.role = role
        self.objective = objective
        self.inputs = inputs or {}
        self.constraints = constraints or []
        self.forbidden = forbidden or []
        self.output_contract = output_contract

    def system_prompt(self) -> str:
        lines = [self.role]
        if self.constraints:
            lines.append("")
            lines.append("Rules you must follow on every response:")
            for rule in self.constraints:
                lines.append(f"- {rule}")
        lines.append("")
        lines.append(
            "Return only what the OUTPUT section asks for. No preamble, no explanation, "
            "no surrounding quotes, no code fences."
        )
        return scrub_em_dashes("\n".join(lines))

    def user_prompt(self) -> str:
        lines = [f"OBJECTIVE: {self.objective}", ""]

        if self.inputs:
            lines.append("INPUTS:")
            for key, value in self.inputs.items():
                if value is None or value == "":
                    continue
                label = key.replace("_", " ").title()
                lines.append(f"  {label}: {value}")
            lines.append("")

        if self.forbidden:
            lines.append("MUST NOT APPEAR IN YOUR ANSWER:")
            for item in self.forbidden:
                lines.append(f"  - {item}")
            lines.append("")

        lines.append(f"OUTPUT: {self.output_contract}")
        return scrub_em_dashes("\n".join(lines))

    def render(self) -> Tuple[str, str]:
        return self.system_prompt(), self.user_prompt()


def strip_preamble(text: str) -> str:
    """Removes the conversational opener a model adds when it ignores the rule."""
    if not text:
        return ""
    cleaned = text.strip()
    for _ in range(3):
        before = cleaned
        for pattern in _PREAMBLE_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
        if cleaned == before:
            break
    cleaned = _TRAILING_FENCE.sub("", cleaned).strip()
    # A model that wrapped its whole answer in quotes meant the content, not
    # the quotes.
    if len(cleaned) > 1 and cleaned[0] in "\"'" and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def validate_response(
    text: Optional[str],
    min_chars: int = 12,
    max_chars: int = 2000,
    forbidden_terms: Optional[List[str]] = None,
    reject_banned_tropes: bool = True,
) -> Tuple[bool, str, str]:
    """
    Decides whether a model's answer is usable.

    Returns (accepted, cleaned_text, reason). On rejection the caller keeps its
    deterministic value, so a bad response costs nothing beyond one wasted call.
    The reason is recorded rather than printed, because "the model said something
    odd" is exactly the kind of thing that should be visible later.
    """
    if not text or not text.strip():
        return False, "", "empty response"

    cleaned = scrub_em_dashes(strip_preamble(text))

    if len(cleaned) < min_chars:
        return False, "", f"too short ({len(cleaned)} chars)"
    if len(cleaned) > max_chars:
        return False, "", f"too long ({len(cleaned)} chars)"

    # A model that starts explaining itself has not followed the contract, and
    # the explanation would end up inside the composed prompt.
    if re.search(r"\b(as an ai|i cannot|i'm unable|note that|please note)\b", cleaned, re.IGNORECASE):
        return False, "", "response contains commentary"

    lowered = cleaned.lower()
    for term in forbidden_terms or []:
        if term.lower() in lowered:
            return False, "", f"contains forbidden term '{term}'"

    if reject_banned_tropes:
        ok, found = validate_banned_vocabulary(cleaned)
        if not ok:
            return False, "", f"contains banned tropes: {', '.join(found)}"

    return True, cleaned, "accepted"


def provenance(source: str, reason: str = "", model: str = "") -> Dict[str, str]:
    """
    Where a piece of generated output came from.

    Carried on the response so a maintainer can tell a deterministic prompt from
    a model assisted one without rerunning anything, and can see why a model
    answer was refused when it was.
    """
    return {"source": source, "reason": reason, "model": model}
