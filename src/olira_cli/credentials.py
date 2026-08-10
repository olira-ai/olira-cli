"""Read/write ~/.olira/credentials.json, and resolve which credential a command should use.

Two credential *classes* exist and are not interchangeable (see
services/app-api/AUTH.md):

- "sdk"     — a raw `olira_{env}_...` API key. Required by every /v1/* route
              (ingest, validate --check-org). A browser-login JWT is rejected
              by these routes, so resolve_auth raises a clear AuthError
              instead of sending a token the server will 401 on.
- "console" — an Auth0 tenant JWT from `olira login`. Required by
              /organization/* and /member/* routes (keys CRUD, configure
              cursor). An API key cannot manage API keys, so the reverse
              substitution is rejected too.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from olira_cli.errors import AuthError, CommandResult

CREDENTIALS_DIR = Path.home() / ".olira"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
CREDENTIALS_MODE = 0o600


def _ensure_dir() -> Path:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    return CREDENTIALS_DIR


def get_credentials_path() -> Path:
    return CREDENTIALS_FILE


def load_credentials() -> dict[str, Any] | None:
    """Load credentials from ~/.olira/credentials.json. Returns None if missing or invalid."""
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        st = CREDENTIALS_FILE.stat()
        if st.st_mode & 0o077 != 0:
            print("Warning: credentials file has overly permissive permissions (should be 600).", file=sys.stderr)
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_credentials(data: dict[str, Any]) -> None:
    """Write credentials to ~/.olira/credentials.json with chmod 600."""
    _ensure_dir()
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(CREDENTIALS_FILE, CREDENTIALS_MODE)
    except OSError:
        pass


def delete_credentials() -> bool:
    """Remove credentials file. Returns True if removed, False if not present."""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        return True
    return False


@dataclass
class Auth:
    token: str
    api_server: str
    source: Literal["flag", "env", "login"]


def resolve_auth(cls: Literal["sdk", "console"], api_key_flag: str | None = None) -> Auth:
    """Resolve the credential a command should use, enforcing the sdk/console split.

    sdk:     --api-key flag > OLIRA_API_KEY env. A credentials-file-only login
             is *not* accepted — /v1/* routes reject anything but an
             `olira_...` key, so we fail fast with the right remediation
             instead of sending a token that will bounce with an opaque 401.
    console: credentials file only (from `olira login`). An API key present
             via flag/env is *not* accepted here either.
    """
    api_key = api_key_flag or os.environ.get("OLIRA_API_KEY")
    creds = load_credentials()

    if cls == "sdk":
        if api_key:
            api_server = (creds or {}).get("api_server") or os.environ.get("OLIRA_API_URL")
            if not api_server:
                from olira_cli.urls import default_api_url

                api_server = default_api_url("prod")
            return Auth(token=api_key, api_server=api_server, source="flag" if api_key_flag else "env")
        if creds and creds.get("access_token"):
            raise AuthError(
                "This command requires an API key, not a browser login.",
                remediation=(
                    "Set OLIRA_API_KEY=olira_... (create one with 'olira keys create --scopes sdk:historical-ingest')."
                ),
            )
        raise AuthError(
            "Not authenticated.",
            remediation="Set OLIRA_API_KEY=olira_... (create one with 'olira keys create').",
        )

    # cls == "console"
    if creds and creds.get("access_token"):
        api_server = creds.get("api_server") or os.environ.get("OLIRA_API_URL")
        if not api_server:
            from olira_cli.urls import default_api_url

            api_server = default_api_url("prod")
        return Auth(token=creds["access_token"], api_server=api_server, source="login")
    if api_key:
        raise AuthError(
            "This command requires browser login, not an API key.",
            remediation="Run 'olira login' (API keys cannot manage API keys or configure clients).",
        )
    raise AuthError("Not logged in.", remediation="Run 'olira login'.")


def resolve_project(args: Any) -> str | None:
    """Resolve --project (or OLIRA_PROJECT) — shared by every /v1/* command that's project-scoped."""
    return getattr(args, "project", None) or os.environ.get("OLIRA_PROJECT")


def sdk_headers(auth: Auth, project: str | None = None) -> dict[str, str]:
    """Bearer + optional X-Olira-Project header for /v1/* requests."""
    headers = {"Authorization": f"Bearer {auth.token}"}
    if project:
        headers["X-Olira-Project"] = project
    return headers


def api_base(auth: Auth) -> str:
    return auth.api_server.rstrip("/")


def cmd_token(quiet: bool = False) -> CommandResult:
    """JSON-aware variant of get_token_stdout, used by cli.py's central dispatch."""
    from olira_cli import output

    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        raise AuthError("Not logged in.", remediation="Run 'olira login'.")
    token = creds["access_token"]
    expired = _is_token_expired(token)
    if expired and not quiet:
        output.warn("Warning: token has expired. Run 'olira login' to refresh.")
    if not output.json_mode():
        print(token, end="")
    return CommandResult({"access_token": token, "expires_at": creds.get("expires_at", ""), "expired": expired})


def _is_token_expired(token: str) -> bool:
    """Return True if JWT exp claim is in the past (with 60s buffer)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        import base64

        payload_b64 = parts[1].replace("-", "+").replace("_", "/")
        payload = json.loads(base64.b64decode(payload_b64 + "==").decode())
        exp = payload.get("exp")
        if exp is None:
            return False
        import time

        return exp < (int(time.time()) + 60)
    except Exception:
        return False


def cmd_status() -> CommandResult:
    """Return current login and token expiry as a CommandResult; renders prose in human mode."""
    from olira_cli import output

    creds = load_credentials()
    if not creds:
        raise AuthError("Not logged in.", remediation="Run 'olira login'.")
    identity = creds.get("identity", "unknown")
    organization = creds.get("organization", "unknown")
    mcp_server = creds.get("mcp_server", "")
    expires_at = creds.get("expires_at", "")
    token = creds.get("access_token", "")
    expired = _is_token_expired(token) if token else True

    if not output.json_mode():
        print(f"Logged in as {identity} ({organization})")
        print(f"MCP Server: {mcp_server}")
        if expires_at:
            print(f"Token expires: {expires_at}" + (" (expired)" if expired else ""))
        else:
            print("Token expiry: unknown")

    return CommandResult(
        {
            "identity": identity,
            "organization": organization,
            "mcp_server": mcp_server,
            "expires_at": expires_at,
            "expired": expired,
        }
    )


def _clear_mcp_json(path: Path) -> bool:
    """Remove the olira-patient-state entry from an mcp.json file.

    Returns True if the file was modified, False otherwise.
    """
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        servers = config.get("mcpServers", {})
        if "olira-patient-state" not in servers:
            return False
        del servers["olira-patient-state"]
        if not servers:
            del config["mcpServers"]
        else:
            config["mcpServers"] = servers
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except (json.JSONDecodeError, OSError, KeyError):
        return False


def cmd_logout() -> CommandResult:
    """Remove stored credentials and wipe the Olira entry from mcp.json files."""
    from olira_cli import output

    removed = delete_credentials()
    if not output.json_mode():
        print("Logged out. Credentials removed." if removed else "Not logged in.")

    cleaned: list[Path] = []

    cwd_mcp = Path.cwd() / ".cursor" / "mcp.json"
    if _clear_mcp_json(cwd_mcp):
        cleaned.append(cwd_mcp)

    home_mcp = Path.home() / ".cursor" / "mcp.json"
    if home_mcp != cwd_mcp and _clear_mcp_json(home_mcp):
        cleaned.append(home_mcp)

    if not output.json_mode():
        for p in cleaned:
            print(f"Removed olira-patient-state from {p}")

    return CommandResult({"removed_credentials": removed, "cleaned_mcp_json": [str(p) for p in cleaned]})
