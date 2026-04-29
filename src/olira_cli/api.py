"""HTTP calls to app-api (keys CRUD) and MCP (validation)."""

import pathlib
import sys
from typing import Any

from olira_cli.credentials import load_credentials

# Canonical scope definitions — mirrors ApiKeyScope in common-models and api-keys.ts in the console.
VALID_SCOPES: dict[str, str] = {
    "mcp:patient-state": "Query patient state via the MCP Patient State server",
    "mcp:integration": "Olira Integration MCP (coming soon)",
    "sdk:event-log": "Log health events on behalf of patients via the Olira SDK",
    "sdk:patient-token": "Mint short-lived, patient-locked JWTs for SDK use",
    "api:manage-patients": "Create, read, update, and deactivate patient records via REST",
    "api:org-config": "Read and update organisation platform configuration via REST",
    "sdk:state-read": "Read patient state — stable data, event modules, summaries, event logs, state transitions, memories",
}
_DEFAULT_SCOPE = "mcp:patient-state"


def _require_creds() -> dict[str, Any] | None:
    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        print("Not logged in. Run: olira login --env <dev|stage|prod>", file=sys.stderr)
        return None
    return creds


def cmd_keys(args: Any) -> int:
    """Dispatch keys create | list | revoke."""
    if args.keys_command == "create":
        return _keys_create(getattr(args, "name", None), scopes=getattr(args, "scopes", None))
    if args.keys_command == "list":
        return _keys_list()
    if args.keys_command == "revoke":
        return _keys_revoke(args.key)
    print("Usage: olira keys {create|list|revoke}", file=sys.stderr)
    return 1


def _prompt_scopes() -> list[str] | None:
    """Show an interactive checkbox picker and return the selected scopes.

    Returns None if the user cancels (Ctrl-C / Ctrl-D).
    """
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    choices = [
        Choice(value=scope, name=f"{scope:<28} {desc}", enabled=(scope == _DEFAULT_SCOPE))
        for scope, desc in VALID_SCOPES.items()
    ]

    try:
        selected: list[str] = inquirer.checkbox(
            message="Select scopes for this API key (space to toggle, enter to confirm):",
            choices=choices,
            instruction="(↑↓ move  space toggle  enter confirm)",
            validate=lambda result: len(result) > 0,
            invalid_message="Select at least one scope.",
            cycle=True,
        ).execute()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return None

    return selected


def _prompt_name() -> str | None:
    """Prompt the user for a key name. Returns None if cancelled."""
    from InquirerPy import inquirer

    try:
        name: str = inquirer.text(
            message="Key name:",
            validate=lambda v: len(v.strip()) > 0,
            invalid_message="Name cannot be empty.",
        ).execute()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return None
    return name.strip()


def _keys_create(name: str | None = None, scopes: list[str] | None = None) -> int:
    creds = _require_creds()
    if not creds:
        return 1

    if name is None:
        name = _prompt_name()
        if name is None:
            return 1

    if scopes is not None:
        # Non-interactive: validate the provided scopes client-side before hitting the API.
        invalid = [s for s in scopes if s not in VALID_SCOPES]
        if invalid:
            print(f"Error: Unknown scope(s): {invalid}", file=sys.stderr)
            print(f"Valid scopes: {', '.join(VALID_SCOPES)}", file=sys.stderr)
            return 1
        if not scopes:
            print("Error: At least one scope must be provided.", file=sys.stderr)
            return 1
    else:
        # Interactive: show the checkbox picker.
        selected = _prompt_scopes()
        if selected is None:
            return 1
        scopes = selected

    import httpx

    api_base = creds["api_server"].rstrip("/")
    url = f"{api_base}/organization/api-keys"
    token = creds["access_token"]
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                url,
                json={"name": name, "scopes": scopes},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json()
            raw_key = data.get("raw_key") or data.get("rawKey")
            if not raw_key:
                print("Error: Server did not return a key.", file=sys.stderr)
                return 1
            print(f"API key created: {raw_key}")
            print("  Copy this key now — it will not be shown again.")
            print(f"  Scopes: {', '.join(scopes)}")
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
            print(f"{'NAME':<20} {'CREATED':<12} {'LAST USED':<12} {'STATUS':<10} {'SCOPES'}")
            print("-" * 80)
            for k in keys:
                name = k.get("name") or k.get("display_name") or ""
                created = (k.get("created_at") or "")[:10]
                last_used = (k.get("last_used_at") or "")[:10] if k.get("last_used_at") else "-"
                status = "active" if k.get("is_active", True) else "revoked"
                scopes = ", ".join(k.get("scopes") or [_DEFAULT_SCOPE])
                print(f"{name:<20} {created:<12} {last_used:<12} {status:<10} {scopes}")
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
