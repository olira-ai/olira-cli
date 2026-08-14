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
_PORT_HELP = "Callback server port (default: 9876)" if _INTERNAL_BUILD else argparse.SUPPRESS


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
        epilog=(
            "Driving this CLI with a coding agent? Run 'olira init agent' first — it writes "
            "agent-specific instructions (auth model, exit codes, recipes, failure playbook) into the "
            "current repo so the agent doesn't have to guess from --help alone."
        ),
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
            "sdk:integrations, sdk:integration-write, api:manage-projects, sdk:actions."
        ),
    )
    keys_sub.add_parser("list", help="List API keys for your organization", parents=[common])
    keys_revoke = keys_sub.add_parser("revoke", help="Permanently revoke an API key", parents=[common])
    keys_revoke.add_argument("key", help="Key name or ID to revoke")
    keys_revoke.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")

    configure_parser = subparsers.add_parser("configure", help="Write MCP client config", parents=[common])
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

    init_parser = subparsers.add_parser("init", help="Set up agent-facing docs in the current repo", parents=[common])
    init_sub = init_parser.add_subparsers(dest="init_command", help="init subcommands")

    init_agent = init_sub.add_parser(
        "agent",
        help="Write AGENTS.md plus per-workflow skills (olira-ingest, olira-logging, olira-query, olira-setup, olira-actions)",
        parents=[common],
    )
    init_agent.add_argument("--claude", action="store_true", help="Write the skills under .claude/skills/")
    init_agent.add_argument(
        "--cursor", action="store_true", help="Write the skills under .agents/skills/ (shared with --codex)"
    )
    init_agent.add_argument(
        "--codex", action="store_true", help="Write the skills under .agents/skills/ (shared with --cursor)"
    )
    init_agent.add_argument(
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

    _build_patients_parser(subparsers, common)
    _build_state_parser(subparsers, common)
    _build_cohorts_parser(subparsers, common)
    _build_projects_parser(subparsers, common)
    _build_integrations_parser(subparsers, common)
    _build_log_types_parser(subparsers, common)
    _build_actions_parser(subparsers, common)

    return parser


def _build_patients_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    patients_parser = subparsers.add_parser("patients", help="Query patients (read-only)", parents=[common])
    patients_sub = patients_parser.add_subparsers(dest="patients_command", help="patients subcommands")

    patients_list = patients_sub.add_parser("list", help="List patients for the org", parents=[common])
    patients_list.add_argument("--limit", type=int, default=100, help="Max results, 1-100 (default: 100)")
    patients_list.add_argument("--offset", type=int, default=0, help="Pagination offset (default: 0)")
    patients_list.add_argument(
        "--external-system", default=None, help="Filter by external identifier system (requires --external-value)"
    )
    patients_list.add_argument(
        "--external-value", default=None, help="Filter by external identifier value (requires --external-system)"
    )
    patients_list.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    patients_get = patients_sub.add_parser("get", help="Get a single patient", parents=[common])
    patients_get.add_argument("patient_id", help="Olira-assigned patient id")
    patients_get.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")


def _build_state_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    state_parser = subparsers.add_parser("state", help="Query a patient's clinical state (read-only)", parents=[common])
    state_sub = state_parser.add_subparsers(dest="state_command", help="state subcommands")

    state_stable = state_sub.add_parser("stable", help="Get stable data modules", parents=[common])
    state_stable.add_argument("patient_id", help="Patient id")
    state_stable.add_argument("--modules", default=None, metavar="TYPES", help="Comma-separated module types to filter")

    state_modules = state_sub.add_parser(
        "modules", help="List event state modules, or get one by type", parents=[common]
    )
    state_modules.add_argument("patient_id", help="Patient id")
    state_modules.add_argument("module_type", nargs="?", default=None, help="Module type (omit to list all)")

    state_views = state_sub.add_parser("views", help="List views, or get one by type", parents=[common])
    state_views.add_argument("patient_id", help="Patient id")
    state_views.add_argument("view_type", nargs="?", default=None, help="View type (omit to list all)")

    state_view_block = state_sub.add_parser("view-block", help="Get a single view block", parents=[common])
    state_view_block.add_argument("patient_id", help="Patient id")
    state_view_block.add_argument("view_type", help="View type")
    state_view_block.add_argument("block_id", help="Block id")

    state_recent = state_sub.add_parser("recent", help="Get recent TEMP entries for a view", parents=[common])
    state_recent.add_argument("patient_id", help="Patient id")
    state_recent.add_argument("view_type", help="View type")
    state_recent.add_argument("--limit", type=int, default=50, help="Max entries, 1-200 (default: 50)")

    state_logs = state_sub.add_parser("logs", help="Get a patient's event logs", parents=[common])
    state_logs.add_argument("patient_id", help="Patient id")
    state_logs.add_argument("--since", default=None, help="ISO 8601 timestamp lower bound")
    state_logs.add_argument(
        "--event-types", default=None, metavar="TYPES", help="Comma-separated event types to filter"
    )
    state_logs.add_argument("--trace-type", default=None)
    state_logs.add_argument("--trace-id", default=None)
    state_logs.add_argument("--limit", type=int, default=50, help="Max results, 1-200 (default: 50)")
    state_logs.add_argument("--offset", type=int, default=0, help="Pagination offset (default: 0)")

    state_events = state_sub.add_parser("events", help="Get a patient's state-update events", parents=[common])
    state_events.add_argument("patient_id", help="Patient id")
    state_events.add_argument("--since", default=None, help="ISO 8601 timestamp lower bound")
    state_events.add_argument("--log-type", default=None)
    state_events.add_argument("--trace-type", default=None)
    state_events.add_argument("--trace-id", default=None)
    state_events.add_argument("--status", default="complete", help="Event status filter (default: complete)")
    state_events.add_argument("--limit", type=int, default=50, help="Max results, 1-200 (default: 50)")

    state_memories = state_sub.add_parser("memories", help="Search a patient's memories", parents=[common])
    state_memories.add_argument("patient_id", help="Patient id")
    state_memories.add_argument("--query", default=None, help="Case-insensitive text search")
    state_memories.add_argument("--limit", type=int, default=100, help="Max results, 1-500 (default: 100)")


def _build_cohorts_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    cohorts_parser = subparsers.add_parser("cohorts", help="Query cohorts (read-only)", parents=[common])
    cohorts_sub = cohorts_parser.add_subparsers(dest="cohorts_command", help="cohorts subcommands")

    cohorts_list = cohorts_sub.add_parser("list", help="List cohorts", parents=[common])
    cohorts_list.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    cohorts_get = cohorts_sub.add_parser("get", help="Get a single cohort", parents=[common])
    cohorts_get.add_argument("cohort_id", help="Cohort id")
    cohorts_get.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    cohorts_templates = cohorts_sub.add_parser(
        "templates", help="List a cohort's assigned summary templates", parents=[common]
    )
    cohorts_templates.add_argument("cohort_id", help="Cohort id")
    cohorts_templates.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")


def _build_projects_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    projects_parser = subparsers.add_parser(
        "projects", help="Query projects (read-only; org-wide key required)", parents=[common]
    )
    projects_sub = projects_parser.add_subparsers(dest="projects_command", help="projects subcommands")

    projects_sub.add_parser("list", help="List projects for the org", parents=[common])

    projects_get = projects_sub.add_parser("get", help="Get a single project", parents=[common])
    projects_get.add_argument("project_id", metavar="id_or_slug", help="Project id or slug")


def _build_integrations_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    integrations_parser = subparsers.add_parser(
        "integrations", help="Query connected integrations (read-only)", parents=[common]
    )
    integrations_sub = integrations_parser.add_subparsers(dest="integrations_command", help="integrations subcommands")

    integrations_sub.add_parser("catalog", help="List available integration providers", parents=[common])
    integrations_sub.add_parser("list", help="List the org's connected integrations", parents=[common])

    integrations_get = integrations_sub.add_parser("get", help="Get a single integration", parents=[common])
    integrations_get.add_argument("integration_id", help="Integration id")

    integrations_dp = integrations_sub.add_parser(
        "data-points", help="List an integration's data points", parents=[common]
    )
    integrations_dp.add_argument("integration_id", help="Integration id")
    integrations_dp.add_argument(
        "--catalog", action="store_true", help="Show available data points instead of subscribed ones"
    )


def _build_log_types_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    log_types_parser = subparsers.add_parser(
        "log-types", help="Discover supported log types and their payload schemas (read-only)", parents=[common]
    )
    log_types_sub = log_types_parser.add_subparsers(dest="log_types_command", help="log-types subcommands")

    log_types_sub.add_parser("list", help="List the platform's log-type catalog", parents=[common])

    log_types_get = log_types_sub.add_parser("get", help="Get one log type's full payload schema", parents=[common])
    log_types_get.add_argument("subtype", help="Log type subtype (or a known alias)")


def _add_digest_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--digest-time-of-day", default=None, metavar="HH:MM", help="Batch time, on a half-hour boundary")
    p.add_argument("--digest-timezone", default=None, metavar="TZ", help="IANA timezone, e.g. America/New_York")
    p.add_argument(
        "--digest-triggers",
        default=None,
        metavar="TRIGGERS",
        help="Comma-separated subset of --triggers to batch (all three --digest-* flags required together)",
    )


def _build_actions_parser(subparsers: Any, common: argparse.ArgumentParser) -> None:
    actions_parser = subparsers.add_parser(
        "actions", help="Manage outbound-action destinations and deliveries", parents=[common]
    )
    actions_sub = actions_parser.add_subparsers(dest="actions_command", help="actions subcommands")

    create = actions_sub.add_parser(
        "create-destination", help="Register a webhook or email destination", parents=[common]
    )
    create.add_argument("--url", default=None, help="Webhook URL (mutually exclusive with --to-email)")
    create.add_argument("--to-email", default=None, help="Email recipient (mutually exclusive with --url)")
    create.add_argument("--subject", default=None, help="Email destinations only")
    create.add_argument("--from-name", default=None, help="Email destinations only")
    create.add_argument(
        "--triggers",
        default=None,
        metavar="TRIGGERS",
        help='Required. Comma-separated triggers, or "*" for all',
    )
    create.add_argument("--description", default=None)
    create.add_argument(
        "--header", action="append", default=None, metavar="KEY=VALUE", help="Static header, repeatable"
    )
    create.add_argument("--rate-limit", type=int, default=None, metavar="N", help="Deliveries/min, 1-6000")
    _add_digest_flags(create)
    create.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    actions_sub.add_parser("list-destinations", help="List action destinations", parents=[common]).add_argument(
        "--project", default=None, help="Project id or slug (org-wide keys only)"
    )

    get_dest = actions_sub.add_parser("get-destination", help="Get a single destination", parents=[common])
    get_dest.add_argument("destination_id", help="Destination id")
    get_dest.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    update = actions_sub.add_parser("update-destination", help="Update a destination", parents=[common])
    update.add_argument("destination_id", help="Destination id")
    update.add_argument("--url", default=None, help="Webhook destinations only")
    update.add_argument("--to-email", default=None, help="Email destinations only")
    update.add_argument("--subject", default=None, help="Email destinations only")
    update.add_argument("--description", default=None)
    update.add_argument("--triggers", default=None, metavar="TRIGGERS", help="Replaces the full subscription list")
    update.add_argument("--status", default=None, choices=["active", "disabled"])
    update.add_argument(
        "--header", action="append", default=None, metavar="KEY=VALUE", help="Static header, repeatable; replaces all"
    )
    _add_digest_flags(update)
    update.add_argument(
        "--clear-digest-schedule", action="store_true", help="Turn off digest batching (back to immediate delivery)"
    )
    update.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    delete = actions_sub.add_parser("delete-destination", help="Disable a destination", parents=[common])
    delete.add_argument("destination_id", help="Destination id")
    delete.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    delete.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    rotate = actions_sub.add_parser(
        "rotate-destination-secret", help="Rotate the signing secret (reveal-once)", parents=[common]
    )
    rotate.add_argument("destination_id", help="Destination id")
    rotate.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    list_deliveries = actions_sub.add_parser(
        "list-deliveries", help="List deliveries (cursor-paginated)", parents=[common]
    )
    list_deliveries.add_argument("--destination-id", default=None)
    list_deliveries.add_argument("--status", default=None)
    list_deliveries.add_argument("--trigger", default=None)
    list_deliveries.add_argument("--cursor", default=None)
    list_deliveries.add_argument("--limit", type=int, default=50, help="Max results, 1-200 (default: 50)")
    list_deliveries.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    get_delivery = actions_sub.add_parser(
        "get-delivery", help="Get one delivery's full attempt history", parents=[common]
    )
    get_delivery.add_argument("delivery_id", help="Delivery id")
    get_delivery.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")

    redeliver = actions_sub.add_parser(
        "redeliver-delivery", help="Resend a delivery's original bytes", parents=[common]
    )
    redeliver.add_argument("delivery_id", help="Delivery id")
    redeliver.add_argument("--project", default=None, help="Project id or slug (org-wide keys only)")


_VALID_ENVS = {"dev", "stage", "prod", "local"}
_PUBLIC_ENVS = {"dev", "stage", "prod"}


def _command_name(args: argparse.Namespace) -> str:
    command = getattr(args, "command", None) or "help"
    sub = (
        getattr(args, "keys_command", None)
        or getattr(args, "configure_command", None)
        or getattr(args, "init_command", None)
        or getattr(args, "ingest_command", None)
        or getattr(args, "patients_command", None)
        or getattr(args, "state_command", None)
        or getattr(args, "cohorts_command", None)
        or getattr(args, "projects_command", None)
        or getattr(args, "integrations_command", None)
        or getattr(args, "log_types_command", None)
        or getattr(args, "actions_command", None)
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
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "validate":
        from olira_cli.validate import cmd_validate

        return cmd_validate(args)
    if args.command == "ingest":
        return _cmd_ingest(args)
    if args.command == "patients":
        return _cmd_patients(args)
    if args.command == "state":
        return _cmd_state(args)
    if args.command == "cohorts":
        return _cmd_cohorts(args)
    if args.command == "projects":
        return _cmd_projects(args)
    if args.command == "integrations":
        return _cmd_integrations(args)
    if args.command == "log-types":
        return _cmd_log_types(args)
    if args.command == "actions":
        return _cmd_actions(args)
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
    if sub == "cursor":
        from olira_cli.api import cmd_configure_cursor

        return cmd_configure_cursor(args)
    if sub == "claude":
        from olira_cli.api import cmd_configure_claude

        return cmd_configure_claude(args)
    if sub == "codex":
        from olira_cli.api import cmd_configure_codex

        return cmd_configure_codex(args)
    raise CliError("Usage: olira configure {cursor|claude|codex}", code="USAGE", exit_code=2)


def _cmd_init(args: argparse.Namespace) -> CommandResult:
    sub = getattr(args, "init_command", None)
    if sub == "agent":
        from olira_cli.agent_docs import cmd_init_agent

        return cmd_init_agent(args)
    raise CliError("Usage: olira init agent", code="USAGE", exit_code=2)


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


def _cmd_patients(args: argparse.Namespace) -> CommandResult:
    from olira_cli.reads import cmd_patients_get, cmd_patients_list

    dispatch = {"list": cmd_patients_list, "get": cmd_patients_get}
    sub = getattr(args, "patients_command", None)
    if sub not in dispatch:
        raise CliError("Usage: olira patients {list|get}", code="USAGE", exit_code=2)
    return dispatch[sub](args)


def _cmd_state(args: argparse.Namespace) -> CommandResult:
    from olira_cli import state

    dispatch = {
        "stable": state.cmd_stable,
        "modules": state.cmd_modules,
        "views": state.cmd_views,
        "view-block": state.cmd_view_block,
        "recent": state.cmd_recent,
        "logs": state.cmd_logs,
        "events": state.cmd_events,
        "memories": state.cmd_memories,
    }
    sub = getattr(args, "state_command", None)
    if sub not in dispatch:
        raise CliError(
            "Usage: olira state {stable|modules|views|view-block|recent|logs|events|memories}",
            code="USAGE",
            exit_code=2,
        )
    return dispatch[sub](args)


def _cmd_cohorts(args: argparse.Namespace) -> CommandResult:
    from olira_cli.reads import cmd_cohorts_get, cmd_cohorts_list, cmd_cohorts_templates

    dispatch = {"list": cmd_cohorts_list, "get": cmd_cohorts_get, "templates": cmd_cohorts_templates}
    sub = getattr(args, "cohorts_command", None)
    if sub not in dispatch:
        raise CliError("Usage: olira cohorts {list|get|templates}", code="USAGE", exit_code=2)
    return dispatch[sub](args)


def _cmd_projects(args: argparse.Namespace) -> CommandResult:
    from olira_cli.reads import cmd_projects_get, cmd_projects_list

    dispatch = {"list": cmd_projects_list, "get": cmd_projects_get}
    sub = getattr(args, "projects_command", None)
    if sub not in dispatch:
        raise CliError("Usage: olira projects {list|get}", code="USAGE", exit_code=2)
    return dispatch[sub](args)


def _cmd_integrations(args: argparse.Namespace) -> CommandResult:
    from olira_cli.reads import (
        cmd_integrations_catalog,
        cmd_integrations_data_points,
        cmd_integrations_get,
        cmd_integrations_list,
    )

    dispatch = {
        "catalog": cmd_integrations_catalog,
        "list": cmd_integrations_list,
        "get": cmd_integrations_get,
        "data-points": cmd_integrations_data_points,
    }
    sub = getattr(args, "integrations_command", None)
    if sub not in dispatch:
        raise CliError("Usage: olira integrations {catalog|list|get|data-points}", code="USAGE", exit_code=2)
    return dispatch[sub](args)


def _cmd_log_types(args: argparse.Namespace) -> CommandResult:
    from olira_cli.reads import cmd_log_types_get, cmd_log_types_list

    dispatch = {
        "list": cmd_log_types_list,
        "get": cmd_log_types_get,
    }
    sub = getattr(args, "log_types_command", None)
    if sub not in dispatch:
        raise CliError("Usage: olira log-types {list|get}", code="USAGE", exit_code=2)
    return dispatch[sub](args)


def _cmd_actions(args: argparse.Namespace) -> CommandResult:
    from olira_cli.actions import (
        cmd_create_destination,
        cmd_delete_destination,
        cmd_get_delivery,
        cmd_get_destination,
        cmd_list_deliveries,
        cmd_list_destinations,
        cmd_redeliver_delivery,
        cmd_rotate_destination_secret,
        cmd_update_destination,
    )

    dispatch: dict[str, Any] = {
        "create-destination": cmd_create_destination,
        "list-destinations": cmd_list_destinations,
        "get-destination": cmd_get_destination,
        "update-destination": cmd_update_destination,
        "delete-destination": cmd_delete_destination,
        "rotate-destination-secret": cmd_rotate_destination_secret,
        "list-deliveries": cmd_list_deliveries,
        "get-delivery": cmd_get_delivery,
        "redeliver-delivery": cmd_redeliver_delivery,
    }
    sub = getattr(args, "actions_command", None)
    if sub not in dispatch:
        raise CliError(
            "Usage: olira actions {create-destination|list-destinations|get-destination|"
            "update-destination|delete-destination|rotate-destination-secret|"
            "list-deliveries|get-delivery|redeliver-delivery}",
            code="USAGE",
            exit_code=2,
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
