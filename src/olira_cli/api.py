"""HTTP calls to app-api (keys CRUD) and MCP (validation)."""

import pathlib
import sys
from typing import Any

from olira_cli.credentials import load_credentials


def _require_creds() -> dict[str, Any] | None:
    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        print("Not logged in. Run: olira login --env <dev|stage|prod>", file=sys.stderr)
        return None
    return creds


def cmd_keys(args: Any) -> int:
    """Dispatch keys create | list | revoke."""
    if args.keys_command == "create":
        return _keys_create(args.name)
    if args.keys_command == "list":
        return _keys_list()
    if args.keys_command == "revoke":
        return _keys_revoke(args.key)
    print("Usage: olira keys {create|list|revoke}", file=sys.stderr)
    return 1


def _keys_create(name: str) -> int:
    creds = _require_creds()
    if not creds:
        return 1
    import httpx

    api_base = creds["api_server"].rstrip("/")
    url = f"{api_base}/organization/api-keys"
    token = creds["access_token"]
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json={"name": name}, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            data = r.json()
            raw_key = data.get("raw_key") or data.get("rawKey")
            if not raw_key:
                print("Error: Server did not return a key.", file=sys.stderr)
                return 1
            print(f"API Key created: {raw_key}")
            print("  Copy this key now — it will not be shown again.")
            return 0
    except httpx.HTTPStatusError as e:
        msg = e.response.json().get("message") or e.response.json().get("detail") or str(e)
        print(f"Error: {msg}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _keys_list() -> int:
    creds = _require_creds()
    if not creds:
        return 1
    import httpx

    api_base = creds["api_server"].rstrip("/")
    url = f"{api_base}/organization/api-keys"
    token = creds["access_token"]
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            data = r.json()
            keys = data.get("data") or data.get("keys") or []
            if not keys:
                print("No API keys.")
                return 0
            print(f"{'NAME':<20} {'CREATED':<12} {'LAST USED':<12} {'STATUS':<10}")
            print("-" * 56)
            for k in keys:
                name = k.get("name") or k.get("display_name") or ""
                created = (k.get("created_at") or "")[:10]
                last_used = (k.get("last_used_at") or "")[:10] if k.get("last_used_at") else "-"
                status = "active" if k.get("is_active", True) else "revoked"
                print(f"{name:<20} {created:<12} {last_used:<12} {status:<10}")
            return 0
    except httpx.HTTPStatusError as e:
        msg = e.response.json().get("message") or e.response.json().get("detail") or str(e)
        print(f"Error: {msg}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _keys_revoke(key_ref: str) -> int:
    creds = _require_creds()
    if not creds:
        return 1
    import httpx

    api_base = creds["api_server"].rstrip("/")
    token = creds["access_token"]
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{api_base}/organization/api-keys", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        data = r.json()
        keys = data.get("data") or data.get("keys") or []
        key_id = None
        key_name = None
        for k in keys:
            kid = str(k.get("id") or k.get("_id") or "")
            name = k.get("name") or k.get("display_name") or ""
            if kid == key_ref or name == key_ref:
                key_id = kid
                key_name = name
                break
        if not key_id:
            print(f"Error: Key '{key_ref}' not found.", file=sys.stderr)
            return 1
    try:
        confirm = input(f'Are you sure you want to revoke "{key_name or key_id}"? This cannot be undone. [y/N]: ')
        if confirm.strip().lower() != "y":
            print("Cancelled.")
            return 0
    except EOFError:
        return 1
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.delete(
                f"{api_base}/organization/api-keys/{key_id}", headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
        print(f'Key "{key_name or key_id}" revoked.')
        return 0
    except httpx.HTTPStatusError as e:
        msg = e.response.json().get("message") or e.response.json().get("detail") or str(e)
        print(f"Error: {msg}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def fetch_member_profile(api_base: str, token: str) -> dict[str, str]:
    """Fetch member profile from app-api.

    Calls GET /member/me and GET /organization/me with the given JWT.
    Returns a dict with keys: email, first_name, last_name, org_name.
    Returns an empty dict on any failure so callers can fall back gracefully.
    """
    import httpx

    result: dict[str, str] = {}
    base = api_base.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            member_r = client.get(f"{base}/member/me", headers=headers)
            if member_r.status_code == 200:
                body = member_r.json()
                m = body.get("data") or body
                result["email"] = m.get("email") or ""
                result["first_name"] = m.get("first_name") or m.get("firstName") or ""
                result["last_name"] = m.get("last_name") or m.get("lastName") or ""

            org_r = client.get(f"{base}/organization/me", headers=headers)
            if org_r.status_code == 200:
                body = org_r.json()
                o = body.get("data") or body
                result["org_name"] = o.get("name") or ""
    except Exception:
        pass
    return result


def _find_cursor_dir() -> pathlib.Path | None:
    """Return the .cursor directory to use, or None if the user cancels.

    Resolution order:
      1. .cursor/ in the current working directory (project-level config)
      2. ~/.cursor/ (global config)
      3. Prompt the user for a path if neither exists
    """
    cwd_cursor = pathlib.Path.cwd() / ".cursor"
    if cwd_cursor.is_dir():
        return cwd_cursor

    home_cursor = pathlib.Path.home() / ".cursor"
    if home_cursor.is_dir():
        return home_cursor

    print("No .cursor directory found in the current directory or your home folder.")
    try:
        raw = input("Enter the path to your .cursor directory (or press Enter to create ~/.cursor): ").strip()
    except EOFError:
        return None
    if raw:
        p = pathlib.Path(raw).expanduser().resolve()
    else:
        p = home_cursor
    p.mkdir(parents=True, exist_ok=True)
    return p


def cmd_configure(client: str) -> int:
    """Write MCP config for the given client (e.g. cursor)."""
    import json

    if client != "cursor":
        print("Only 'cursor' is supported for now.", file=sys.stderr)
        return 1
    creds = _require_creds()
    if not creds:
        return 1

    cursor_dir = _find_cursor_dir()
    if cursor_dir is None:
        print("Cancelled.", file=sys.stderr)
        return 1

    mcp_server = creds["mcp_server"].rstrip("/")
    if not mcp_server.endswith("/mcp"):
        mcp_server = mcp_server + "/mcp"

    config_path = pathlib.Path(cursor_dir) / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    token = creds.get("access_token", "")

    servers = config.get("mcpServers") or {}
    servers["olira-patient-state"] = {
        "url": mcp_server,
        "headers": {
            "Authorization": f"Bearer {token}",
        },
    }
    config["mcpServers"] = servers
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Wrote MCP server config to {config_path}")
    print(f"  Server: {mcp_server}")
    print("")
    print("Token written directly to mcp.json.")
    print("When your token expires, re-run: olira configure cursor")
    print("Tip: for a non-expiring credential, create an API key and use it instead:")
    print('  olira keys create --name "Cursor"')
    return 0
