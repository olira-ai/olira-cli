"""Entry point for the olira CLI."""

import argparse
import sys

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
        description="Olira CLI — authenticate and configure MCP access.",
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
            "sdk:patient-token, api:manage-patients, api:org-config, sdk:state-read."
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

    parser.print_help()
    return 0


_VALID_ENVS = {"dev", "stage", "prod", "local"}
_PUBLIC_ENVS = {"dev", "stage", "prod"}


def _cmd_login(args: argparse.Namespace) -> int:
    env = args.env
    # Customers (prod build) get no --env flag; default to prod.
    # Internal builds require --env or explicit URLs.
    if env is None and not args.mcp_server:
        if _INTERNAL_BUILD:
            print(
                "Error: --env is required. Use --env dev, --env stage, --env prod, or --env local.",
                file=sys.stderr,
            )
            return 1
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


if __name__ == "__main__":
    sys.exit(main())
