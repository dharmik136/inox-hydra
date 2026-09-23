"""
The studio as an MCP client.

Not a server. An agent driving a local studio is thin, because the agent and
the studio are already on the same machine. The inversion is not: a draft
grounded in the creator's own notes, repository and calendar is the one thing
a cloud writing tool structurally cannot do, having never seen their work.

  protocol  newline delimited JSON-RPC to a local MCP server, over stdio
  servers   what is configured, and the separate question of what is allowed
  grounding gathering material, budgeting it, and reporting where it goes
"""

from .grounding import (MAX_GROUNDING_BYTES, as_brief_inputs, egress_report,
                        gather, grounding_provenance)
from .protocol import McpServer
from .servers import (add_server, enabled_servers, list_servers,
                      remove_server, set_enabled)

__all__ = [
    "McpServer",
    "add_server",
    "as_brief_inputs",
    "egress_report",
    "enabled_servers",
    "gather",
    "grounding_provenance",
    "list_servers",
    "remove_server",
    "set_enabled",
    "MAX_GROUNDING_BYTES",
]
