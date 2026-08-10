"""olira configure agents — writes agent-facing docs into a customer repo.

Content lives here as plain string constants (not importlib.resources data
files) so it's compiled straight into the PyInstaller onebinary and never
needs datas-spec plumbing or _MEIPASS handling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from olira_cli import __version__, output
from olira_cli.errors import CliError, CommandResult

_MARKER_BEGIN = "<!-- BEGIN olira-cli (managed by 'olira configure agents', v{version}) -->"
_MARKER_END = "<!-- END olira-cli -->"

_EXIT_CODE_TABLE = """\
| Code | Meaning |
|---|---|
| 0 | Success — including a job that finished `completed_with_errors`; check `data.status` |
| 1 | Unexpected/internal error |
| 2 | Usage error (bad flags/args) |
| 3 | Auth — not authenticated, wrong credential type, or forbidden |
| 4 | Not found — job/key/file does not exist |
| 5 | Validation failed |
| 6 | Wrong state / interaction required — read `error.remediation` for the exact flag to add |
| 7 | Network or server error |
| 8 | `--watch --timeout` exceeded — the job is still running server-side |
| 130 | Interrupted (Ctrl-C) |
"""

_SCOPE_TABLE = """\
| Scope | Grants |
|---|---|
| `sdk:historical-ingest` | Upload/manage bulk historical ingestion jobs (`olira ingest *`) |
| `api:manage-patients` | Create, read, update, soft-delete patients |
| `sdk:event-log` | Log events and upload passive signal Parquet (`send_signals`) |
| `sdk:state-read` | Read patient state, summaries, event logs |
| `sdk:patient-token` | Mint short-lived patient-scoped JWTs |
| `sdk:integrations` | Manage EHR integrations — catalog, connect/disconnect, sync status (control-plane only) |
| `sdk:integration-write` | Honor `write_back` on logged events for EHR write-back |
| `api:manage-projects` | Manage projects (org-wide keys only) |
| `mcp:patient-state` | Query patient state via the MCP server (used by `configure claude`/`configure codex`, not by the CLI's own commands) |
"""

_STATE_MACHINE = """\
```
queued -> validating -> inserting_patients -> inserting_logs
    -> [awaiting_confirmation]   (only if require_confirmation, the default)
    -> confirmed -> replaying -> backfilling
    -> completed | completed_with_errors | cancelled | failed
```

At `awaiting_confirmation`, some patients may be missing view template slots
(`missing_template_slots` on the job, or `error_summary` entries with
`code: "missing_template_slot"`). `olira ingest confirm <job_id>` then needs
exactly one of:
- `--init-templates` — create the missing templates and proceed (recommended)
- `--no-backfill` — skip view generation for this job entirely
- (interactive TTY only) an interactive prompt with the same choices

Without one of these, `confirm` exits 6 with code `CONFIRMATION_REQUIRED`.
"""

_JSONL_SCHEMA = """\
One JSON object per line. Two record types:

```jsonl
{"type": "patient", "data": {"external_identifiers": [{"system": "mrn", "value": "abc123"}], "first_name": "...", "date_of_birth": "1990-01-01"}}
{"type": "log", "data": {"patient_id": "abc123", "event_type": "symptom_report", "timestamp": "2025-01-15T09:00:00Z", ...}}
```

Rules:
- A patient must be declared (a `type: "patient"` line) before any `log` line references its `patient_id`, unless that id already exists in the org.
- `patient_id` must be a pseudonymous identifier — never an email, phone number, or SSN (the validator rejects these).
- `event_type` must be a known type — run `olira validate` to check against the current catalog.
- Always run `olira validate <file>.jsonl --json` before `olira ingest upload` — fix everything in `error.details.errors` first.
"""

_RECIPES = """\
```bash
# 1. Validate before uploading — always do this first
olira validate data.jsonl --json

# 2. Upload. --watch --timeout is a SHORT bound (catches quick jobs) — if it
#    times out (exit 8), the job is still running; that's not a failure.
olira ingest upload data.jsonl --json --watch --timeout 90

# 3. If it paused at AWAITING_CONFIRMATION with missing templates
olira ingest confirm <job_id> --init-templates --json --watch --timeout 90

# 4. If step 2 or 3 timed out, don't re-watch with a bigger number — report
#    progress now and check back later with a plain (non-watching) status call:
olira ingest status <job_id> --json

# 5. Check what's failing across the org
olira ingest list --status failed --json
```
"""

_FAILURE_PLAYBOOK = """\
| Exit code | Likely cause | Next command |
|---|---|---|
| 3 (`AUTH_REQUIRED`) | `OLIRA_API_KEY` unset, or a browser-login-only credential used for an SDK command | Ask the human to run `olira keys create --scopes sdk:historical-ingest`, then `export OLIRA_API_KEY=...` |
| 5 (`VALIDATION_FAILED`) | `olira validate` found errors | Read `error.details.errors`, fix the file, re-run `olira validate` |
| 6 (`PROMPT_REQUIRED`) | A command would have prompted interactively | Read `error.remediation` — it names the exact flag to add |
| 6 (`CONFIRMATION_REQUIRED`) | Job at `awaiting_confirmation` has missing template slots | `olira ingest confirm <job_id> --init-templates` |
| 6 (`JOB_FAILED` / `JOB_CANCELLED`) | Watched job ended non-successfully | `olira ingest status <job_id> --json` for `error_summary` |
| 7 (`NETWORK_ERROR` / `SERVER_ERROR`) | Transient network/5xx | Retry; the watch loop already retries transient errors automatically |
| 8 (`WATCH_TIMEOUT`) | `--timeout` exceeded — normal for a long-running job, NOT a failure | Report the job id and its last-known progress to the user now; check `olira ingest status <job_id> --json` again in a later turn. Do not just retry with a bigger `--timeout` — a bulk historical job can legitimately run for hours, and blocking a turn on it wastes it. |
| any, on `completed_with_errors` | Partial success | Inspect `data.error_summary`; consider `olira ingest retry-backfill <job_id>` |
"""

_GOLDEN_RULES = """\
- Always pass `--json`. Every command emits one JSON envelope on stdout: `{"ok": true|false, "command", "cli_version", "data"|"error"}`.
- Never rely on an interactive prompt. Always pass the flag that answers it up front: `--yes` (destructive confirmations), `--name`/`--scopes` (`keys create`), `--init-templates`/`--no-backfill` (`ingest confirm`), `--dir` (`configure cursor`).
- Always pass a SHORT `--timeout` with `--watch` (e.g. `--timeout 60` to `--timeout 120`). This bounds how long *this one tool call* blocks — it is not a guess at the job's real duration. Ingestion jobs can legitimately run for hours; `--watch` is for catching the common case where a job finishes quickly, not for sitting through a long one. On exit `8` (`WATCH_TIMEOUT`), the job is still running server-side — report progress and check back with a plain `olira ingest status <job_id> --json` in a later turn instead of re-watching with an ever-bigger timeout.
- Never run `olira login` — it opens a browser and will hang or error out headless. If `OLIRA_API_KEY` isn't set, ask the human to create one with `olira keys create`.
- Check `data.status` on ingestion jobs — `completed_with_errors` exits 0 but is a partial success.
"""


def _skill_md(version: str) -> str:
    return f"""---
name: olira
description: Upload and manage historical patient data with the Olira CLI — validate JSONL, upload, watch ingestion jobs, and manage API keys, non-interactively.
---

# Olira CLI

Installed as `olira` (verify with `olira --version`; this doc matches v{version}).

## Auth

- Ingestion and validation (`olira ingest *`, `olira validate --check-org`) need an **API key**, set as `OLIRA_API_KEY=olira_...` (or `--api-key`). A browser login does NOT work for these — the server rejects it.
- Key management (`olira keys *`) and `olira configure cursor` need a **browser login** (`olira login`) instead — an API key does not work for these. Don't run `olira login` yourself; it's interactive. Ask the human if one isn't already available.
- `olira configure claude` / `olira configure codex` write a project-scoped MCP server config (`.mcp.json` / `.codex/config.toml`) for connecting that client directly to the Olira MCP server. Neither needs auth to run — no flags required. Neither writes a secret to disk either: both reference an env var (`OLIRA_API_KEY` by default, override with `--api-key-env`) for the client to read the bearer token from at connect time, since these config files are meant to be committed to git. The human still needs to export that env var with a real API key scoped to `mcp:patient-state` before the MCP connection will actually authenticate.
- Multi-project orgs: pass `--project <id-or-slug>` (or `OLIRA_PROJECT`) on `ingest`/`validate` commands to target a project other than the org default.

### Scopes

{_SCOPE_TABLE}

## Golden rules

{_GOLDEN_RULES}

## JSON envelope and exit codes

{_EXIT_CODE_TABLE}

## Ingestion job state machine

{_STATE_MACHINE}

## JSONL schema

{_JSONL_SCHEMA}

## Recipes

{_RECIPES}

## Failure playbook

{_FAILURE_PLAYBOOK}
"""


def _agents_md_block(version: str) -> str:
    return f"""{_MARKER_BEGIN.format(version=version)}
## Olira CLI

Installed as `olira`. Full reference: `.claude/skills/olira/SKILL.md` (also readable directly).

- Auth: `OLIRA_API_KEY=olira_...` for `ingest`/`validate --check-org`; browser login (`olira login`, human-only) for `keys`/`configure cursor`.
- Always pass `--json`. With `--watch`, pass a SHORT `--timeout` (e.g. `60`-`120`) — it bounds how long *this call* blocks, not the job's real duration. Ingestion can legitimately run for hours; on exit `8` (`WATCH_TIMEOUT`) the job is still running — report progress and re-check with a later, non-watching `status` call instead of re-watching with a bigger timeout.
- Never rely on interactive prompts — pass `--yes`/`--name`/`--scopes`/`--init-templates`/`--no-backfill`/`--dir` up front.

{_EXIT_CODE_TABLE}
{_MARKER_END}
"""


def _cursor_mdc(version: str) -> str:
    return f"""---
description: Using the Olira CLI (olira) for historical data ingestion and API key management
alwaysApply: false
---

# Olira CLI (v{version})

{_GOLDEN_RULES}

{_EXIT_CODE_TABLE}

{_STATE_MACHINE}

{_RECIPES}
"""


def _write_whole_file(path: Path, content: str) -> str:
    existed = path.exists()
    existing = path.read_text(encoding="utf-8") if existed else None
    if existing == content:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "updated" if existed else "created"


def write_marker_block(path: Path, block: str, *, begin_prefix: str, end_marker: str) -> str:
    """Idempotently write `block` into `path`, owning only the text between markers.

    - File doesn't exist: create it containing just the block.
    - File exists, no BEGIN marker found: append the block (existing content untouched).
    - File exists with a BEGIN...END pair: replace only that span.

    Used for files we don't fully own (AGENTS.md, a project's .codex/config.toml)
    where we must not clobber unrelated content.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return "created"

    existing = path.read_text(encoding="utf-8")
    begin_idx = existing.find(begin_prefix)
    if begin_idx == -1:
        new_content = existing.rstrip("\n") + "\n\n" + block
        if new_content == existing:
            return "unchanged"
        path.write_text(new_content, encoding="utf-8")
        return "updated"

    end_idx = existing.find(end_marker, begin_idx)
    if end_idx == -1:
        raise CliError(
            f"{path} has a BEGIN marker but no matching END marker — refusing to overwrite.",
            code="MANAGED_BLOCK_CORRUPT",
        )
    end_idx += len(end_marker)
    new_content = existing[:begin_idx] + block.rstrip("\n") + existing[end_idx:]
    if new_content == existing:
        return "unchanged"
    path.write_text(new_content, encoding="utf-8")
    return "updated"


def write_agent_docs(directory: Path, target: str) -> list[dict[str, str]]:
    """`codex` is an alias for `agents-md`: Codex CLI reads plain AGENTS.md natively
    (no special format, well under its 32 KiB limit), so it needs no separate file."""
    version = __version__
    files: list[dict[str, str]] = []

    if target in ("all", "agents-md", "codex"):
        path = directory / "AGENTS.md"
        begin_prefix = _MARKER_BEGIN.split("v{version}")[0]
        action = write_marker_block(path, _agents_md_block(version), begin_prefix=begin_prefix, end_marker=_MARKER_END)
        files.append({"path": str(path), "action": action})

    if target in ("all", "claude"):
        path = directory / ".claude" / "skills" / "olira" / "SKILL.md"
        action = _write_whole_file(path, _skill_md(version))
        files.append({"path": str(path), "action": action})

    if target in ("all", "cursor"):
        path = directory / ".cursor" / "rules" / "olira.mdc"
        action = _write_whole_file(path, _cursor_mdc(version))
        files.append({"path": str(path), "action": action})

    return files


def cmd_configure_agents(args: Any) -> CommandResult:
    directory = Path(getattr(args, "agents_dir", None) or Path.cwd())
    target = getattr(args, "target", "all")

    files = write_agent_docs(directory, target)

    if not output.json_mode():
        for f in files:
            print(f"  {f['action']:<9} {f['path']}")

    return CommandResult({"files": files})
