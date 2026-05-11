"""Entry point for the olira CLI."""

import argparse
import sys
from typing import Any

from olira_cli import _INTERNAL_BUILD

# Flags hidden from customer --help output in prod builds.
# In internal builds (dev/stage/local) they are fully documented.
_ENV_HELP = "Target environment: dev | stage | prod | local" if _INTERNAL_BUILD else argparse.SUPPRESS
_MCP_HELP = "MCP server URL override (e.g. http://localhost:8084)" if _INTERNAL_BUILD else argparse.SUPPRESS
_CONSOLE_HELP = "Console URL override (e.g. http://localhost:3000)" if _INTERNAL_BUILD else argparse.SUPPRESS
_PORT_HELP = "Callback server port (default: 9100)" if _INTERNAL_BUILD else argparse.SUPPRESS


def main() -> int:
    """Main entry point. Dispatches to subcommands."""
    parser = argparse.ArgumentParser(
        prog="olira",
        description="Olira CLI — authenticate, manage API keys, configure MCP access, and upload historical patient data.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # login
    login_parser = subparsers.add_parser("login", help="Log in via browser")
    login_parser.add_argument("--env", default=None, help=_ENV_HELP)
    login_parser.add_argument("--mcp-server", help=_MCP_HELP)
    login_parser.add_argument("--console-url", help=_CONSOLE_HELP)
    login_parser.add_argument("--port", type=int, default=9876, help=_PORT_HELP)

    # token
    token_parser = subparsers.add_parser("token", help="Print access token to stdout for piping")
    token_parser.add_argument("--quiet", action="store_true", help="Suppress expiry warning to stderr")

    # status
    subparsers.add_parser("status", help="Show current login and token expiry")

    # logout
    subparsers.add_parser("logout", help="Remove stored credentials")

    # keys
    keys_parser = subparsers.add_parser("keys", help="Manage API keys (org admin only)")
    keys_sub = keys_parser.add_subparsers(dest="keys_command", help="keys subcommands")
    keys_create = keys_sub.add_parser("create", help="Create a new API key")
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
            "Valid: mcp:patient-state, mcp:integration, sdk:event-log, "
            "sdk:patient-token, api:manage-patients, api:org-config, sdk:state-read, "
            "sdk:historical-ingest."
        ),
    )
    keys_sub.add_parser("list", help="List API keys for your organization")
    keys_revoke = keys_sub.add_parser("revoke", help="Permanently revoke an API key")
    keys_revoke.add_argument("key", help="Key name or ID to revoke")

    # configure
    configure_parser = subparsers.add_parser("configure", help="Write MCP client config")
    configure_parser.add_argument(
        "client",
        choices=["cursor"],
        help="Target client (cursor; claude-code planned)",
    )

    # validate
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a .jsonl file before uploading",
    )
    validate_parser.add_argument("file", help="Path to the .jsonl file to validate")
    validate_parser.add_argument(
        "--check-org",
        action="store_true",
        help="Also check patient references against live org patients (requires login)",
    )
    validate_parser.add_argument(
        "--skip-order-check",
        action="store_true",
        help="Skip the check that patients are declared before logs that reference them",
    )

    # ingest
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Upload and manage historical data ingestion jobs",
        description="Upload a JSONL file of historical patient data and manage the ingestion pipeline. "
        "Subcommands: upload, list, status, confirm, cancel, retry-backfill.",
    )
    ingest_sub = ingest_parser.add_subparsers(dest="ingest_command", help="ingest subcommands")

    # ingest upload
    ingest_upload = ingest_sub.add_parser("upload", help="Upload a .jsonl file and create an ingestion job")
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
        help="AI summary types to generate (e.g. emotional_state_snapshot clinical_note)",
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

    # ingest list
    ingest_list = ingest_sub.add_parser("list", help="List ingestion jobs for the org")
    ingest_list.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    ingest_list.add_argument("--page-size", type=int, default=10, dest="page_size", help="Jobs per page (default: 10)")
    ingest_list.add_argument(
        "--status",
        default=None,
        metavar="STATUS",
        help="Filter by status (e.g. failed, completed, completed_with_errors, awaiting_confirmation)",
    )

    # ingest status
    ingest_status = ingest_sub.add_parser("status", help="Show status for a single job")
    ingest_status.add_argument("job_id", help="Job ID")
    ingest_status.add_argument(
        "--watch",
        action="store_true",
        help="Tail progress until terminal or AWAITING_CONFIRMATION",
    )

    # ingest confirm
    ingest_confirm = ingest_sub.add_parser("confirm", help="Confirm a job at AWAITING_CONFIRMATION")
    ingest_confirm.add_argument("job_id", help="Job ID")
    ingest_confirm.add_argument(
        "--summary-types",
        nargs="+",
        metavar="TYPE",
        help="Set AI summary types before confirming",
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

    # ingest cancel
    ingest_cancel = ingest_sub.add_parser("cancel", help="Cancel an ingestion job")
    ingest_cancel.add_argument("job_id", help="Job ID")
    ingest_cancel.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # ingest retry-backfill
    ingest_retry = ingest_sub.add_parser(
        "retry-backfill",
        help="Retry view backfill on a COMPLETED_WITH_ERRORS job",
    )
    ingest_retry.add_argument("job_id", help="Job ID")
    ingest_retry.add_argument(
        "--watch",
        action="store_true",
        help="Tail progress until the backfill completes",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "login":
        return _cmd_login(args)
    if args.command == "token":
        return _cmd_token(args)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "logout":
        return _cmd_logout(args)
    if args.command == "keys":
        return _cmd_keys(args)
    if args.command == "configure":
        return _cmd_configure(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "ingest":
        return _cmd_ingest(args)

    parser.print_help()
    return 0


_VALID_ENVS = {"dev", "stage", "prod", "local"}
_PUBLIC_ENVS = {"dev", "stage", "prod"}


def _cmd_login(args: argparse.Namespace) -> int:
    env = args.env
    if env is None and not args.mcp_server:
        env = "prod"
    if env is not None and env not in _VALID_ENVS:
        print(
            f"Error: --env must be one of: {', '.join(sorted(_PUBLIC_ENVS))}",
            file=sys.stderr,
        )
        return 1
    from olira_cli.auth import run_login

    return run_login(
        env=env,
        mcp_server=args.mcp_server,
        console_url=args.console_url,
        port=args.port,
    )


def _cmd_token(args: argparse.Namespace) -> int:
    from olira_cli.credentials import get_token_stdout

    return get_token_stdout(quiet=args.quiet)


def _cmd_status(args: argparse.Namespace) -> int:
    from olira_cli.credentials import cmd_status

    return cmd_status()


def _cmd_logout(args: argparse.Namespace) -> int:
    from olira_cli.credentials import cmd_logout

    return cmd_logout()


def _cmd_keys(args: argparse.Namespace) -> int:
    from olira_cli.api import cmd_keys

    return cmd_keys(args)


def _cmd_configure(args: argparse.Namespace) -> int:
    from olira_cli.api import cmd_configure

    return cmd_configure(args.client)


def _cmd_validate(args: argparse.Namespace) -> int:
    from olira_cli.validate import cmd_validate

    return cmd_validate(args)


def _cmd_ingest(args: argparse.Namespace) -> int:
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
        print("Usage: olira ingest {upload|list|status|confirm|cancel|retry-backfill}", file=sys.stderr)
        return 1

    return dispatch[sub](args)


if __name__ == "__main__":
    sys.exit(main())
