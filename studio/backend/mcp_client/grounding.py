"""
Grounding a draft in the creator's own material, and being honest about where it goes.
======================================================================================

The competitor problem, stated plainly: every cloud writing tool produces
posts that read generic, and no amount of model quality fixes it, because the
tool has never seen the creator's work. It cannot cite the migration they ran
last month or the argument they had in a design review, because it was not
there. A local-first studio can be, which is the one structural advantage this
product has and the reason MCP is worth building here.

So this module gathers material from configured MCP servers and hands it to
the agent as labelled inputs on a Brief.

The part that matters more than the feature
-------------------------------------------
This bundle describes itself to every user as "held entirely on your own
machine. No cloud account, no data egress." Grounding puts that claim under
real pressure: the material gathered here is pasted into a prompt, and if the
configured provider is a hosted one, the creator's private notes leave the
machine and land in someone else's logs.

That is not a reason to refuse to build it. It is a reason to refuse to build
it quietly. Three rules follow, and they are the substance of this file:

  1. Nothing is connected by default, and nothing is gathered without the
     creator having enabled that specific server. Absence of a preference is
     not consent.

  2. Whether the material is about to leave the machine is computed and
     reported, every time, from the provider actually configured. A local
     model means no egress and the studio says so; a hosted one means egress
     and the studio says that instead. The creator is never left to infer it.

  3. What was gathered is returned alongside what was sent, so the interface
     can show the creator the material before it is used rather than after.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Nothing here raises. A server that is down produces no grounding, and the
  draft is written without it exactly as it is today.
- Grounding never silently becomes egress. The report is not optional.
"""

import json
from typing import Any, Dict, List, Optional

try:
    from .protocol import McpServer
    from .servers import enabled_servers
except ImportError:  # pragma: no cover - direct script use
    from protocol import McpServer
    from servers import enabled_servers

# Providers that run on the creator's own machine. Material sent to these
# never leaves it, so grounding carries no disclosure cost.
#
# Kept as a deny-by-default list rather than a check for "localhost" in a URL:
# a base URL pointing at a loopback port that tunnels somewhere else would pass
# a naive string test, and being wrong in that direction means telling someone
# their notes stayed home when they did not.
LOCAL_PROVIDERS = frozenset({"local_deterministic", "ollama", "llamacpp", "lmstudio"})

# What the whole grounding block may occupy. A prompt is a fixed budget shared
# with the creator's own draft and the agent's instructions, and material that
# crowds those out makes the output worse rather than better, which is the
# opposite of the point.
MAX_GROUNDING_BYTES = 6 * 1024

# Per resource, so one long document cannot consume the entire budget and
# leave nothing from any other source.
MAX_PER_RESOURCE_BYTES = 1500


def _summarise(text: str, limit: int = MAX_PER_RESOURCE_BYTES) -> str:
    """Trims to a budget on a whitespace boundary, and says that it did."""
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut + " [trimmed]"


def egress_report(provider: str) -> Dict[str, Any]:
    """
    Whether grounding this draft would send the creator's material off the
    machine, and to whom.

    Computed from the provider in force rather than stored, because the
    provider can change between one draft and the next and a cached answer
    would be a claim about the wrong configuration.
    """
    name = str(provider or "local_deterministic").strip().lower()
    local = name in LOCAL_PROVIDERS
    return {
        "provider": name,
        "leaves_this_machine": not local,
        "summary": (
            f"Grounding stays on this machine. {name} runs locally."
            if local else
            f"Grounding material will be sent to {name}, which is a hosted "
            f"service. Anything gathered here leaves your machine as part of "
            f"the prompt."
        ),
    }


def gather(provider: str = "local_deterministic",
           limit_per_server: int = 3) -> Dict[str, Any]:
    """
    Collects grounding material from every enabled server.

    Returns the material, its provenance, and the egress report. Never raises:
    a server that fails to start contributes nothing and is named in `errors`
    so the creator can see which one, rather than wondering why their post
    reads generic again.
    """
    report = egress_report(provider)
    gathered: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []
    budget = MAX_GROUNDING_BYTES

    for definition in enabled_servers():
        name = definition.get("name") or "unnamed"
        command = definition.get("command") or []

        if budget <= 0:
            break

        server = McpServer(
            name=name,
            command=command,
            cwd=definition.get("cwd"),
            env=definition.get("env") or {},
        )

        try:
            if not server.start():
                errors.append({"server": name, "error": "did not start"})
                continue

            resources = server.list_resources()
            if not resources:
                errors.append({"server": name, "error": "offered nothing"})
                continue

            taken = 0
            for resource in resources:
                if taken >= limit_per_server or budget <= 0:
                    break
                uri = resource.get("uri")
                text = server.read_resource(uri)
                if not text:
                    continue
                body = _summarise(text, min(MAX_PER_RESOURCE_BYTES, budget))
                if not body:
                    continue
                gathered.append({
                    "server": name,
                    "uri": str(uri),
                    "title": str(resource.get("name") or resource.get("title") or uri),
                    "text": body,
                })
                budget -= len(body)
                taken += 1
        finally:
            server.stop()

    return {
        "material": gathered,
        "errors": errors,
        "egress": report,
        "bytes_used": MAX_GROUNDING_BYTES - budget,
        "bytes_budget": MAX_GROUNDING_BYTES,
    }


def as_brief_inputs(gathered: Dict[str, Any]) -> Dict[str, str]:
    """
    Shapes gathered material into labelled Brief inputs.

    One input per source rather than a single blob, because Brief renders
    inputs as titled sections and a model given "Grounding: <6kb of text>"
    treats it as background noise, while a model given "Engineering Notes:
    <text>" treats it as a thing to draw on.
    """
    material = gathered.get("material") or []
    inputs: Dict[str, str] = {}

    for index, item in enumerate(material, start=1):
        title = str(item.get("title") or "").strip()
        # Brief turns the key into a section label, so the key has to read as
        # English rather than as a URI.
        label = "".join(ch if ch.isalnum() or ch == " " else " " for ch in title)
        label = "_".join(label.split()).lower()[:40]
        if not label:
            label = f"source_{index}"
        if label in inputs:
            label = f"{label}_{index}"
        inputs[label] = item["text"]

    return inputs


def grounding_provenance(gathered: Dict[str, Any]) -> Dict[str, Any]:
    """
    What grounded this draft, recorded so a post can be explained later.

    The same reasoning as briefing.provenance: a maintainer or a creator
    looking at an old post should be able to tell what informed it, and
    whether anything left the machine to produce it.
    """
    material = gathered.get("material") or []
    return {
        "grounded": bool(material),
        "sources": [
            {"server": item.get("server"), "uri": item.get("uri")}
            for item in material
        ],
        "source_count": len(material),
        "left_this_machine": bool(gathered.get("egress", {}).get("leaves_this_machine")),
        "provider": gathered.get("egress", {}).get("provider"),
        "errors": gathered.get("errors") or [],
    }
