"""Read/write ~/.olira/credentials.json with secure permissions."""

import json
import os
import sys
from pathlib import Path
from typing import Any

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


def get_token_stdout(quiet: bool = False) -> int:
    """Print access token to stdout. Always prints token (even if expired). Returns 0."""
    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        if not quiet:
            print("Not logged in. Run: olira login", file=sys.stderr)
        return 1
    token = creds["access_token"]
    expired = _is_token_expired(token)
    if expired and not quiet:
        print("Warning: token has expired. Run 'olira login' to refresh.", file=sys.stderr)
    print(token, end="")
    return 0


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


def cmd_status() -> int:
    """Print current login and token expiry. Returns 0 if logged in, 1 otherwise."""
    creds = load_credentials()
    if not creds:
        print("Not logged in. Run: olira login")
        return 1
    identity = creds.get("identity", "unknown")
    organization = creds.get("organization", "unknown")
    mcp_server = creds.get("mcp_server", "")
    expires_at = creds.get("expires_at", "")
    token = creds.get("access_token", "")
    expired = _is_token_expired(token) if token else True

    print(f"Logged in as {identity} ({organization})")
    print(f"MCP Server: {mcp_server}")
    if expires_at:
        print(f"Token expires: {expires_at}" + (" (expired)" if expired else ""))
    else:
        print("Token expiry: unknown")
    return 0


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


def cmd_logout() -> int:
    """Remove stored credentials and wipe the Olira entry from mcp.json files."""
    if delete_credentials():
        print("Logged out. Credentials removed.")
    else:
        print("Not logged in.")

    cleaned: list[Path] = []

    cwd_mcp = Path.cwd() / ".cursor" / "mcp.json"
    if _clear_mcp_json(cwd_mcp):
        cleaned.append(cwd_mcp)

    home_mcp = Path.home() / ".cursor" / "mcp.json"
    if home_mcp != cwd_mcp and _clear_mcp_json(home_mcp):
        cleaned.append(home_mcp)

    for p in cleaned:
        print(f"Removed olira-patient-state from {p}")

    return 0
