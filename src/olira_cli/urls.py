"""Environment -> service URL derivation, shared by auth.py, credentials.py, and ingest.py.

Moved out of auth.py so non-login commands (ingest, validate --check-org) can
derive the correct app-api base URL without importing the login flow, and so
there is exactly one place that knows these hostnames.
"""

from __future__ import annotations

from urllib.parse import urlparse


def default_api_url(env: str = "prod") -> str:
    """Return the app-api base URL for an environment.

    Used when only an API key is present (no credentials file to read
    api_server from) — e.g. OLIRA_API_KEY set on a CI box that never ran
    `olira login`.
    """
    if env == "prod":
        return "https://app-api.prod.olira.ai/app-api"
    if env == "stage":
        return "https://app-api.stage.olira.ai/app-api"
    if env == "local":
        return "http://localhost:8080/app-api"
    return "https://app-api.dev.olira.ai/app-api"


def derive_api_url(env: str) -> str:
    return default_api_url(env)


def default_mcp_url(env: str = "prod") -> str:
    """Return the MCP Patient State server base URL for an environment."""
    if env == "prod":
        return "https://mcp-patient-state.olira.ai"
    if env == "stage":
        return "https://mcp-patient-state.stage.olira.ai"
    if env == "local":
        return "http://localhost:8084"
    return "https://mcp-patient-state.dev.olira.ai"


def derive_console_url(mcp_server_url: str) -> str | None:
    """Infer the Console URL from the MCP server URL."""
    try:
        parsed = urlparse(mcp_server_url)
        host = parsed.netloc or parsed.path
        if "mcp-patient-state.dev.olira.ai" in host:
            return "https://console.dev.olira.ai"
        if "mcp-patient-state.stage.olira.ai" in host:
            return "https://console.stage.olira.ai"
        if "mcp-patient-state.olira.ai" in host and "stage" not in host and "dev" not in host:
            return "https://console.olira.ai"
    except Exception:
        pass
    return None
