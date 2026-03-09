"""Olira CLI — authentication and MCP client configuration."""

__version__ = "0.3.2"

# True in all dev/stage/local builds (monorepo editable installs, CodeArtifact dev/stage).
# Flipped to False by CI before the prod PyPI/CodeArtifact build so internal flags
# (--env, --mcp-server, --console-url, --port) are hidden from customer --help output.
_INTERNAL_BUILD: bool = True
