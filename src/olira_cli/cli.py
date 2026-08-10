"""Entry point for the olira CLI."""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

from olira_cli import _INTERNAL_BUILD, __version__, output
from olira_cli.errors import CliError, CommandResult

_ENV_HELP = "Target environment: dev | stage | prod | local" if _INTERNAL_BUILD else argparse.SUPPRESS
_MCP_HELP = "MCP server URL override (e.g. http://localhost:8084)" if _INTERNAL_BUILD else argparse.SUPPRESS
_CONSOLE_HELP = "Console URL override (e.g. http://localhost:3000)" if _INTERNAL_BUILD else argparse.SUPPRESS
_PORT_HELP = "Callback server port (default: 9100)" if _INTERNAL_BUILD else argparse.SUPPRESS


def _common_parser() -> argparse.ArgumentParser:
    """Flags every subcommand accepts, regardless of position.

    Both the root parser and every subparser carry a copy via parents=[...],
    so `olira --json ingest list` and `olira ingest list --json` both work.
    Child copies default to None (not False) so a root-level True is never
    silently overwritten by a child's default — see _json_flag()/_api_key_flag().
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--json", action="store_true", default=None, help="Machine-readable JSON output")
    p.add_argument(
        "--api-key",
        default=None,
        help="API key overriding OLIRA_API_KEY and the stored login (SDK-backed commands only)",
    )
    return p


def _scan_global_flags(argv: list[str]) -> tuple[bool, str | None]:
    """Find --json / --api-key anywhere in argv, independent of position.

    argparse's subparsers action re-parses the remainder into a *fresh*
    namespace and then merges it over the parent's, so a global flag's
    parent-level value is always clobbered by the subparser's own (unset)
    default for that same dest — regardless of which side the user actually
    passed it on. --json and --api-key are declared on every subparser only
    so --help/usage-checking sees them; their real values come from this
    scan, not from the parsed namespace.
    """
    json_flag = False
    api_key: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--json":
            json_flag = True
        elif tok == "--api-key" and i + 1 < len(argv):
            api_key = argv[i + 1]
            i += 1
        elif tok.startswith("--api-key="):
            api_key = tok.split("=", 1)[1]
        i += 1
    return json_flag, api_key


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()

    parser = argparse.ArgumentParser(
        prog="olira",
        description="Olira CLI — authenticate, manage API keys, configure MCP access, and upload historical patient data.",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"olira {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    login_parser = subparsers.add_parser("login", help="Log in via browser", parents=[common])
    login_parser.add_argument("--env", default=None, help=_ENV_HELP)
    login_parser.add_argument("--mcp-server", help=_MCP_HELP)
    login_parser.add_argument("--console-url", help=_CONSOLE_HELP)
    login_parser.add_argument("--port", type=int, default=9876, help=_PORT_HELP)

    token_parser = subparsers.add_parser("token", help="Print access token to stdout for piping", parents=[common])
    token_parser.add_argument("--quiet", action="store_true", help="Suppress expiry warning to stderr")

    subparsers.add_parser("status", help="Show current login and token expiry", parents=[common])

    subparsers.add_parser("logout", help="Remove stored credentials", parents=[common])

    keys_parser = subparsers.add_parser("keys", help="Manage API keys (org admin only)", parents=[common])
    keys_sub = keys_parser.add_subparsers(dest="keys_command", help="keys subcommands")
    keys_create = keys_sub.add_parser("create", help="Create a new API key", parents=[common])
    keys_create.add_argument(
        "--name",
        default=None,
        help="Key name (skips the interactive prompt).",
    )
    keys_create.add_argument(
        "--scopes",
        nargs="+",
        metavar="SCOPE",
        help=(
            "Scopes to grant (space-separated). Skips the interactive picker. "
            "Valid: mcp:patient-state, sdk:event-log, sdk:patient-token, "
            "api:manage-patients, api:org-config, sdk:state-read, sdk:historical-ingest, "
            "sdk:integrations, sdk:integration-write, api:manage-projects."
        ),
    )
    keys_sub.add_parser("list", help="List API keys for your organization", parents=[common])
    keys_revoke = keys_sub.add_parser("revoke", help="Permanently revoke an API key", parents=[common])
    keys_revoke.add_argument("key", help="Key name or ID to revoke")
    keys_revoke.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    configure_parser = subparsers.add_parser(
        "configure", help="Write MCP client config or agent docs", parents=[common]
    )
    configure_sub = configure_parser.add_subparsers(dest="configure_command", help="configure subcommands")

    configure_cursor = configure_sub.add_parser("cursor", help="Write MCP server entry into mcp.json", parents=[common])
    configure_cursor.add_argument(
        "--dir",
        dest="cursor_dir",
        default=None,
        help="Path to the .cursor directory to write to (skips discovery/prompt).",
    )

    configure_claude = configure_sub.add_parser(
        "claude", help="Write a project-scoped MCP server entry into .mcp.json (Claude Code)", parents=[common]
    )
    configure_claude.add_argument("--env", default=None, help=_ENV_HELP)
    configure_claude.add_argument("--mcp-server", help=_MCP_HELP)
    configure_claude.add_argument(
        "--api-key-env",
        default=None,
        help="Env var name Claude Code should read the bearer token from (default: OLIRA_API_KEY)",
    )
    configure_claude.add_argument(
        "--dir", dest="claude_dir", default=None, help="Directory to write .mcp.json into (default: cwd)"
    )

    configure_codex = configure_sub.add_parser(
        "codex", help="Write a project-scoped MCP server entry into .codex/config.toml", parents=[common]
    )
    configure_codex.add_argument("--env", default=None, help=_ENV_HELP)
    configure_codex.add_argument("--mcp-server", help=_MCP_HELP)
    configure_codex.add_argument(
        "--api-key-env",
        default=None,
        help="Env var name Codex should read the bearer token from (default: OLIRA_API_KEY)",
    )
    configure_codex.add_argument(
        "--dir", dest="codex_dir", default=None, help="Directory to write .codex/config.toml into (default: cwd)"
    )

    configure_agents = configure_sub.add_parser(
        "agents",
        help="Write agent-facing docs (AGENTS.md, Claude skill, Cursor rule)",
        parents=[common],
    )
    configure_agents.add_argument(
        "--target",
        choices=["all", "agents-md", "claude", "codex", "cursor"],
        default="all",
        help="Which agent doc(s) to write (default: all). 'codex' is an alias for 'agents-md' — "
        "Codex CLI reads plain AGENTS.md natively.",
    )
    configure_agents.add_argument(
        "--dir",
        dest="agents_dir",
        default=None,
        help="Directory to write into (default: current directory)",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a .jsonl file before uploading",
        parents=[common],
    )
    validate_parser.add_argument("file", help="Path to the .jsonl file to validate")
    validate_parser.add_argument(
        "--check-org",
        action="store_true",
        help="Also check patient references against live org patients (requires an API key)",
    )
    validate_parser.add_argument(
        "--skip-order-check",
        action="store_true",
        help="Skip the check that patients are declared before logs that reference them",
    )
    validate_parser.add_argument(
        "--project",
        default=None,
        help="Project id or slug to scope --check-org against (org-wide keys only; default: org's default project)",
    )

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Upload and manage historical data ingestion jobs",
        description="Upload a JSONL file of historical patient data and manage the ingestion pipeline. "
        "Subcommands: upload, list, status, confirm, cancel, retry-backfill.",
        parents=[common],
    )
    ingest_sub = ingest_parser.add_subparsers(dest="ingest_command", help="ingest subcommands")

    ingest_upload = ingest_sub.add_parser(
        "upload", help="Upload a .jsonl file and create an ingestion job", parents=[common]
    )
    ingest_upload.add_argument("file", help="Path to the .jsonl file to upload")
    ingest_upload.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the AWAITING_CONFIRMATION review step and run to completion automatically",
    )
    ingest_upload.add_argument(
        "--summary-types",
        nargs="+",
        metavar="TYPE",
        help="View types to generate (e.g. emotional_state_snapshot clinical_note)",
    )
    ingest_upload.add_argument(
        "--idempotency-key",
        default=None,
        help="Idempotency key (auto-generated if omitted)",
    )
    ingest_upload.add_argument(
        "--no-backfill",
        action="store_true",
        help="Skip Stage 5 (AI view generation) after graph replay — data is fully imported but Console views are not populated",
    )
    ingest_upload.add_argument(
        "--watch",
        action="store_true",
        help="Tail job progress until terminal or AWAITING_CONFIRMATION",
    )
    ingest_upload.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Give up watching (exit 8) after this many seconds; the job keeps running server-side",
    )
    ingest_upload.add_argument(
        "--init-templates",
        action="store_true",
        dest="init_templates",
        help="At AWAITING_CONFIRMATION, initialize missing view template slots and confirm (non-interactive)",
    )
    ingest_upload.add_argument(
        "--project",
        default=None,
        help="Project id or slug to upload into (org-wide keys only; default: org's default project)",
    )

    ingest_list = ingest_sub.add_parser("list", help="List ingestion jobs for the org", parents=[common])
    ingest_list.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    ingest_list.add_argument("--page-size", type=int, default=10, dest="page_size", help="Jobs per page (default: 10)")
    ingest_list.add_argument(
        "--status",
        default=None,
        metavar="STATUS",
        help="Filter by status (e.g. failed, completed, completed_with_errors, awaiting_confirmation)",
    )
    ingest_list.add_argument("--project", default=None, help="Project id or slug to scope the listing to")

    ingest_status = ingest_sub.add_parser("status", help="Show status for a single job", parents=[common])
    ingest_status.add_argument("job_id", help="Job ID")
    ingest_status.add_argument(
        "--watch",
        action="store_true",
        help="Tail progress until terminal or AWAITING_CONFIRMATION",
    )
    ingest_status.add_argument("--timeout", type=float, default=None, help="Give up watching after this many seconds")
    ingest_status.add_argument("--project", default=None, help="Project id or slug the job belongs to")

    ingest_confirm = ingest_sub.add_parser("confirm", help="Confirm a job at AWAITING_CONFIRMATION", parents=[common])
    ingest_confirm.add_argument("job_id", help="Job ID")
    ingest_confirm.add_argument(
        "--summary-types",
        nargs="+",
        metavar="TYPE",
        help="Set view types before confirming",
    )
    ingest_confirm.add_argument(
        "--no-backfill",
        action="store_true",
        help="Skip Stage 5 (AI view generation) after graph replay",
    )
    ingest_confirm.add_argument(
        "--watch",
        action="store_true",
        help="Tail progress after confirmation",
    )
    ingest_confirm.add_argument("--timeout", type=float, default=None, help="Give up watching after this many seconds")
    ingest_confirm.add_argument(
        "--init-templates",
        action="store_true",
        dest="init_templates",
        help="Initialize missing view template slots before confirming (non-interactive)",
    )
    ingest_confirm.add_argument("--project", default=None, help="Project id or slug the job belongs to")

    ingest_cancel = ingest_sub.add_parser("cancel", help="Cancel an ingestion job", parents=[common])
    ingest_cancel.add_argument("job_id", help="Job ID")
    ingest_cancel.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    ingest_cancel.add_argument("--project", default=None, help="Project id or slug the job belongs to")

    ingest_retry = ingest_sub.add_parser(
        "retry-backfill",
        help="Retry view backfill on a COMPLETED_WITH_ERRORS job",
        parents=[common],
    )
    ingest_retry.add_argument("job_id", help="Job ID")
    ingest_retry.add_argument(
        "--watch",
        action="store_true",
        help="Tail progress until the backfill completes",
    )
    ingest_retry.add_argument("--timeout", type=float, default=None, help="Give up watching after this many seconds")
    ingest_retry.add_argument("--project", default=None, help="Project id or slug the job belongs to")

    return parser


_VALID_ENVS = {"dev", "stage", "prod", "local"}
_PUBLIC_ENVS = {"dev", "stage", "prod"}


def _command_name(args: argparse.Namespace) -> str:
    command = getattr(args, "command", None) or "help"
    sub = (
        getattr(args, "keys_command", None)
        or getattr(args, "configure_command", None)
        or getattr(args, "ingest_command", None)
    )
    return f"{command}.{sub}" if sub else command


def _dispatch(args: argparse.Namespace) -> CommandResult:
    if args.command == "login":
        return _cmd_login(args)
    if args.command == "token":
        from olira_cli.credentials import cmd_token

        return cmd_token(quiet=args.quiet)
    if args.command == "status":
        from olira_cli.credentials import cmd_status

        return cmd_status()
    if args.command == "logout":
        from olira_cli.credentials import cmd_logout

        return cmd_logout()
    if args.command == "keys":
        return _cmd_keys(args)
    if args.command == "configure":
        return _cmd_configure(args)
    if args.command == "validate":
        from olira_cli.validate import cmd_validate

        return cmd_validate(args)
    if args.command == "ingest":
        return _cmd_ingest(args)
    raise CliError("Unknown command.", code="USAGE", exit_code=2)


def _cmd_login(args: argparse.Namespace) -> CommandResult:
    env = args.env
    if env is None and not args.mcp_server:
        env = "prod"
    if env is not None and env not in _VALID_ENVS:
        raise CliError(f"--env must be one of: {', '.join(sorted(_PUBLIC_ENVS))}", code="USAGE", exit_code=2)
    from olira_cli.auth import run_login

    return run_login(
        env=env,
        mcp_server=args.mcp_server,
        console_url=args.console_url,
        port=args.port,
    )


def _cmd_keys(args: argparse.Namespace) -> CommandResult:
    from olira_cli.api import cmd_keys

    return cmd_keys(args)


def _cmd_configure(args: argparse.Namespace) -> CommandResult:
    sub = getattr(args, "configure_command", None)
    if sub == "agents":
        from olira_cli.agent_docs import cmd_configure_agents

        return cmd_configure_agents(args)
    if sub == "cursor":
        from olira_cli.api import cmd_configure_cursor

        return cmd_configure_cursor(args)
    if sub == "claude":
        from olira_cli.api import cmd_configure_claude

        return cmd_configure_claude(args)
    if sub == "codex":
        from olira_cli.api import cmd_configure_codex

        return cmd_configure_codex(args)
    raise CliError("Usage: olira configure {cursor|claude|codex|agents}", code="USAGE", exit_code=2)


def _cmd_ingest(args: argparse.Namespace) -> CommandResult:
    from olira_cli.ingest import cmd_cancel, cmd_confirm, cmd_list, cmd_retry_backfill, cmd_status, cmd_upload

    dispatch: dict[str, Any] = {
        "upload": cmd_upload,
        "list": cmd_list,
        "status": cmd_status,
        "confirm": cmd_confirm,
        "cancel": cmd_cancel,
        "retry-backfill": cmd_retry_backfill,
    }

    sub = getattr(args, "ingest_command", None)
    if sub is None or sub not in dispatch:
        raise CliError(
            "Usage: olira ingest {upload|list|status|confirm|cancel|retry-backfill}", code="USAGE", exit_code=2
        )

    return dispatch[sub](args)


def _force_line_buffering() -> None:
    """Line-buffer stdout/stderr even when redirected to a file or pipe.

    Python fully buffers non-TTY stdout by default — fine for a one-shot
    command, but it means --watch's NDJSON progress/heartbeat events sit in
    memory and never reach a redirected file until the process exits. That
    silently breaks the "run --watch in the background, tail the log for
    live progress" pattern this CLI is designed around. Not all stdout-like
    objects support reconfigure() (e.g. test harnesses), so this is best-effort.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(line_buffering=True)
            except ValueError:
                pass


def main() -> int:
    _force_line_buffering()
    parser = build_parser()
    args = parser.parse_args()

    json_flag, api_key_flag = _scan_global_flags(sys.argv[1:])
    output.set_mode(json_flag)
    args.api_key = api_key_flag
    command = _command_name(args)

    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0

    try:
        result = _dispatch(args)
        output.emit_success(command, result.data, result.warnings)
        return result.exit_code
    except CliError as e:
        output.emit_error(command, e)
        return e.exit_code
    except KeyboardInterrupt:
        output.emit_error(command, CliError("Interrupted.", code="INTERRUPTED", exit_code=130))
        return 130
    except httpx.HTTPStatusError as e:
        from olira_cli.errors import from_http_error

        err = from_http_error(e)
        output.emit_error(command, err)
        return err.exit_code
    except Exception as e:
        output.emit_error(command, CliError(str(e)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
