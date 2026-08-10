"""HTTP calls to the Olira API (keys CRUD, configure cursor) and MCP (validation).

All commands here use the "console" credential class (an Auth0 tenant JWT
from `olira login`) — /organization/* routes reject API keys.
"""

from __future__ import annotations

import pathlib
from typing import Any

from olira_cli import http, output
from olira_cli.credentials import Auth, resolve_auth
from olira_cli.errors import CliError, CommandResult, require_tty

VALID_SCOPES: dict[str, str] = {
    "mcp:patient-state": "Query patient state via the MCP Patient State server",
    "sdk:event-log": "Log health events and upload passive signal Parquet (send_signals) via the Olira SDK",
    "sdk:patient-token": "Mint short-lived, patient-locked JWTs for SDK use",
    "api:manage-patients": "Create, read, update, and deactivate patient records via REST",
    "api:org-config": "Read and update organisation platform configuration via REST",
    "sdk:state-read": "Read patient state — stable data, event modules, summaries, logs, events, memories",
    "sdk:historical-ingest": "Upload and manage bulk historical data ingestion jobs via the Olira SDK",
    "sdk:integrations": "Manage integrations — catalog, connect/disconnect, data-point subscriptions, sync status",
    "sdk:integration-write": "Honor the write_back flag on logged events for EHR write-back",
    "api:manage-projects": "Create, list, rename, and deprecate projects; requires an org-wide key",
}
_DEFAULT_SCOPE = "mcp:patient-state"


def cmd_keys(args: Any) -> CommandResult:
    """Dispatch keys create | list | revoke."""
    auth = resolve_auth("console", getattr(args, "api_key", None))
    if args.keys_command == "create":
        return _keys_create(auth, getattr(args, "name", None), scopes=getattr(args, "scopes", None))
    if args.keys_command == "list":
        return _keys_list(auth)
    if args.keys_command == "revoke":
        return _keys_revoke(auth, args.key, yes=getattr(args, "yes", False))
    raise CliError("Usage: olira keys {create|list|revoke}", code="USAGE", exit_code=2)


def _prompt_scopes() -> list[str] | None:
    """Show an interactive checkbox picker and return the selected scopes.

    Returns None if the user cancels (Ctrl-C / Ctrl-D).
    """
    require_tty("Selecting scopes", "--scopes")
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
        raise CliError("Cancelled.", code="CANCELLED") from None

    return selected


def _prompt_name() -> str:
    """Prompt the user for a key name."""
    require_tty("Naming the key", "--name")
    from InquirerPy import inquirer

    try:
        name: str = inquirer.text(
            message="Key name:",
            validate=lambda v: len(v.strip()) > 0,
            invalid_message="Name cannot be empty.",
        ).execute()
    except (KeyboardInterrupt, EOFError):
        raise CliError("Cancelled.", code="CANCELLED") from None
    return name.strip()


def _keys_create(auth: Auth, name: str | None = None, scopes: list[str] | None = None) -> CommandResult:
    if name is None:
        name = _prompt_name()

    if scopes is not None:
        invalid = [s for s in scopes if s not in VALID_SCOPES]
        if invalid:
            raise CliError(
                f"Unknown scope(s): {invalid}",
                code="INVALID_SCOPES",
                exit_code=5,
                remediation=f"Valid scopes: {', '.join(VALID_SCOPES)}",
            )
        if not scopes:
            raise CliError("At least one scope must be provided.", code="INVALID_SCOPES", exit_code=5)
    else:
        scopes = _prompt_scopes()
        if scopes is None:
            raise CliError("Cancelled.", code="CANCELLED")

    api_base = auth.api_server.rstrip("/")
    url = f"{api_base}/organization/api-keys"
    with http.client() as client:
        r = client.post(
            url,
            json={"name": name, "scopes": scopes},
            headers={"Authorization": f"Bearer {auth.token}"},
        )
        r.raise_for_status()
        data = r.json()
    raw_key = data.get("raw_key") or data.get("rawKey")
    if not raw_key:
        raise CliError("Server did not return a key.", code="SERVER_ERROR", exit_code=7)

    if not output.json_mode():
        print(f"API key created: {raw_key}")
        print("  Copy this key now — it will not be shown again.")
        print(f"  Scopes: {', '.join(scopes)}")

    return CommandResult({"name": name, "scopes": scopes, "raw_key": raw_key})


def _fetch_keys(auth: Auth) -> list[dict[str, Any]]:
    api_base = auth.api_server.rstrip("/")
    with http.client() as client:
        r = client.get(f"{api_base}/organization/api-keys", headers={"Authorization": f"Bearer {auth.token}"})
        r.raise_for_status()
        data = r.json()
    return data.get("data") or data.get("keys") or []


def _render_keys_list(keys: list[dict[str, Any]]) -> None:
    if not keys:
        print("No API keys.")
        return
    rows = []
    for k in keys:
        name = k.get("name") or k.get("display_name") or ""
        created = (k.get("created_at") or "")[:10]
        last_used = (k.get("last_used_at") or "")[:10] if k.get("last_used_at") else "-"
        status = "active" if k.get("is_active", True) else "revoked"
        scopes = ", ".join(k.get("scopes") or [_DEFAULT_SCOPE])
        rows.append([name, created, last_used, status, scopes])
    output.table(["NAME", "CREATED", "LAST USED", "STATUS", "SCOPES"], rows)


def _keys_list(auth: Auth) -> CommandResult:
    keys = _fetch_keys(auth)
    if not output.json_mode():
        _render_keys_list(keys)
    return CommandResult({"keys": keys})


def _keys_revoke(auth: Auth, key_ref: str, *, yes: bool) -> CommandResult:
    keys = _fetch_keys(auth)
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
        raise CliError(f"Key '{key_ref}' not found.", code="NOT_FOUND", exit_code=4)

    if not yes:
        require_tty("Revoking a key", "--yes")
        confirm = input(f'Are you sure you want to revoke "{key_name or key_id}"? This cannot be undone. [y/N]: ')
        if confirm.strip().lower() != "y":
            if not output.json_mode():
                print("Cancelled.")
            return CommandResult({"revoked": False, "key_id": key_id, "key_name": key_name})

    api_base = auth.api_server.rstrip("/")
    with http.client() as client:
        r = client.delete(
            f"{api_base}/organization/api-keys/{key_id}", headers={"Authorization": f"Bearer {auth.token}"}
        )
        r.raise_for_status()

    if not output.json_mode():
        print(f'Key "{key_name or key_id}" revoked.')
    return CommandResult({"revoked": True, "key_id": key_id, "key_name": key_name})


def fetch_member_profile(api_base: str, token: str) -> dict[str, str]:
    """Fetch member profile from the Olira API.

    Calls GET /member/me and GET /organization/me with the given JWT.
    Returns a dict with keys: email, first_name, last_name, org_name.
    Returns an empty dict on any failure so callers (the login flow) can fall back gracefully.
    """
    result: dict[str, str] = {}
    base = api_base.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with http.client(timeout=10.0) as client:
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


def _find_cursor_dir(explicit_dir: str | None) -> pathlib.Path:
    """Return the .cursor directory to use.

    Resolution order:
      1. --dir, if given (created if missing)
      2. .cursor/ in the current working directory (project-level config)
      3. ~/.cursor/ (global config)
      4. Prompt for a path if none exists and we have a TTY
    """
    if explicit_dir:
        p = pathlib.Path(explicit_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    cwd_cursor = pathlib.Path.cwd() / ".cursor"
    if cwd_cursor.is_dir():
        return cwd_cursor

    home_cursor = pathlib.Path.home() / ".cursor"
    if home_cursor.is_dir():
        return home_cursor

    require_tty("Choosing a .cursor directory", "--dir")
    print("No .cursor directory found in the current directory or your home folder.")
    try:
        raw = input("Enter the path to your .cursor directory (or press Enter to create ~/.cursor): ").strip()
    except EOFError:
        raise CliError("Cancelled.", code="CANCELLED") from None
    p = pathlib.Path(raw).expanduser().resolve() if raw else home_cursor
    p.mkdir(parents=True, exist_ok=True)
    return p


def _merge_mcp_server_json(config_path: pathlib.Path, entry: dict[str, Any]) -> str:
    """Merge a single `mcpServers.olira-patient-state` entry into a JSON MCP config file.

    Preserves every other key and every other configured server. Returns
    "created"/"updated"/"unchanged" for the CommandResult data.
    """
    import json

    existed = config_path.exists()
    if existed:
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            config = {}
    else:
        config = {}

    servers = config.get("mcpServers") or {}
    if servers.get("olira-patient-state") == entry:
        return "unchanged"

    servers["olira-patient-state"] = entry
    config["mcpServers"] = servers
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    return "updated" if existed else "created"


def _mcp_server_url(args: Any) -> str:
    """Resolve the MCP server URL from --mcp-server / --env, no auth required."""
    from olira_cli.urls import default_mcp_url

    explicit = getattr(args, "mcp_server", None)
    mcp_server = explicit or default_mcp_url(getattr(args, "env", None) or "prod")
    mcp_server = mcp_server.rstrip("/")
    if not mcp_server.endswith("/mcp"):
        mcp_server += "/mcp"
    return mcp_server


def cmd_configure_cursor(args: Any) -> CommandResult:
    """Write MCP config for Cursor — embeds the current login token directly."""
    auth = resolve_auth("console", getattr(args, "api_key", None))
    cursor_dir = _find_cursor_dir(getattr(args, "cursor_dir", None))

    from olira_cli.credentials import load_credentials

    creds = load_credentials() or {}
    mcp_server = (creds.get("mcp_server") or "").rstrip("/")
    if not mcp_server:
        raise CliError(
            "No MCP server URL on file.", code="SERVER_ERROR", exit_code=7, remediation="Run 'olira login' again."
        )
    if not mcp_server.endswith("/mcp"):
        mcp_server = mcp_server + "/mcp"

    config_path = cursor_dir / "mcp.json"
    action = _merge_mcp_server_json(
        config_path, {"url": mcp_server, "headers": {"Authorization": f"Bearer {auth.token}"}}
    )

    if not output.json_mode():
        print(f"Wrote MCP server config to {config_path}")
        print(f"  Server: {mcp_server}")
        print("")
        print("Token written directly to mcp.json.")
        print("When your token expires, re-run: olira configure cursor")
        print("Tip: for a non-expiring credential, create an API key and use it instead:")
        print('  olira keys create --name "Cursor"')
        print("")
        print("This connects Cursor to Olira's MCP server. To also teach a coding agent")
        print("how to drive the rest of this CLI (ingest, validate, query), run:")
        print("  olira init agent")

    return CommandResult({"config_path": str(config_path), "mcp_server": mcp_server, "action": action})


def cmd_configure_claude(args: Any) -> CommandResult:
    """Write project-scoped MCP config for Claude Code (.mcp.json).

    Unlike `configure cursor`, this never embeds a literal token: Claude Code
    documents .mcp.json as meant to be committed and shared with a team, so
    the Authorization header references an env var instead
    (${OLIRA_API_KEY} by default) — the API key itself is never written to disk.
    """
    api_key_env = getattr(args, "api_key_env", None) or "OLIRA_API_KEY"
    mcp_server = _mcp_server_url(args)
    directory = pathlib.Path(getattr(args, "claude_dir", None) or pathlib.Path.cwd())
    config_path = directory / ".mcp.json"

    action = _merge_mcp_server_json(
        config_path,
        {
            "type": "http",
            "url": mcp_server,
            "headers": {"Authorization": f"Bearer ${{{api_key_env}}}"},
        },
    )

    if not output.json_mode():
        print(f"Wrote MCP server config to {config_path}")
        print(f"  Server: {mcp_server}")
        print("")
        print(f"No token was written. Export {api_key_env} with an API key scoped to")
        print("mcp:patient-state before Claude Code connects to this server:")
        print('  olira keys create --name "Claude Code" --scopes mcp:patient-state')
        print(f"  export {api_key_env}=olira_...")
        print("")
        print("This connects Claude Code to Olira's MCP server. To also teach a coding")
        print("agent how to drive the rest of this CLI (ingest, validate, query), run:")
        print("  olira init agent")

    return CommandResult({"config_path": str(config_path), "mcp_server": mcp_server, "action": action})


def _merge_codex_mcp_block(config_path: pathlib.Path, mcp_server: str, api_key_env: str, version: str) -> str:
    from olira_cli.agent_docs import write_marker_block

    begin = f"# BEGIN olira-cli (managed by 'olira configure codex', v{version})"
    end = "# END olira-cli"
    block = (
        f"{begin}\n"
        "[mcp_servers.olira-patient-state]\n"
        f'url = "{mcp_server}"\n'
        f'bearer_token_env_var = "{api_key_env}"\n'
        f"{end}\n"
    )
    return write_marker_block(config_path, block, begin_prefix=begin, end_marker=end)


def cmd_configure_codex(args: Any) -> CommandResult:
    """Write project-scoped MCP config for Codex CLI (.codex/config.toml).

    Like configure claude, never embeds a literal token — Codex's own schema
    is built around this: `bearer_token_env_var` names an env var for Codex to
    read at connect time, rather than a field that holds a secret directly.
    """
    from olira_cli import __version__

    api_key_env = getattr(args, "api_key_env", None) or "OLIRA_API_KEY"
    mcp_server = _mcp_server_url(args)
    directory = pathlib.Path(getattr(args, "codex_dir", None) or pathlib.Path.cwd())
    config_path = directory / ".codex" / "config.toml"

    action = _merge_codex_mcp_block(config_path, mcp_server, api_key_env, __version__)

    if not output.json_mode():
        print(f"Wrote MCP server config to {config_path}")
        print(f"  Server: {mcp_server}")
        print("")
        print(f"No token was written. Export {api_key_env} with an API key scoped to")
        print("mcp:patient-state before Codex connects to this server:")
        print('  olira keys create --name "Codex" --scopes mcp:patient-state')
        print(f"  export {api_key_env}=olira_...")
        print("")
        print("This connects Codex to Olira's MCP server. To also teach a coding agent")
        print("how to drive the rest of this CLI (ingest, validate, query), run:")
        print("  olira init agent")

    return CommandResult({"config_path": str(config_path), "mcp_server": mcp_server, "action": action})
