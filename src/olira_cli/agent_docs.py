"""olira init agent — writes agent-facing docs into a customer repo.

Content lives here as plain string constants (not importlib.resources data
files) so it's compiled straight into the PyInstaller onebinary and never
needs datas-spec plumbing or _MEIPASS handling.

Three focused skills instead of one monolith: `olira-ingest` (the genuinely
complex workflow — state machine, missing-template-slots, watch/timeout),
`olira-query` (a comparatively simple command reference), and `olira-setup`
(auth model, keys, MCP client configuration). A model-invoked skill loads
only when its description matches the task, so splitting by process means a
"list patients" task doesn't pull the ingestion state machine into context,
and vice versa. Cross-cutting content used by every task regardless of
which skill (if any) gets loaded — the auth-class split, the JSON envelope,
the full exit-code table — stays in the AGENTS.md digest, which most agents
load unconditionally; skills reference it rather than repeat it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from olira_cli import __version__, output
from olira_cli.errors import CliError, CommandResult

_MARKER_BEGIN = "<!-- BEGIN olira-cli (managed by 'olira init agent', v{version}) -->"
_MARKER_END = "<!-- END olira-cli -->"

# Paths superseded by the per-process split — removed on write so upgrading
# doesn't leave a stale monolithic skill alongside the new ones.
_LEGACY_PATHS = (
    ("claude", ("skills", "olira")),
    ("cursor", ("rules", "olira.mdc")),
)

_EXIT_CODE_TABLE = """\
| Code | Meaning |
|---|---|
| 0 | Success — including a job that finished `completed_with_errors`; check `data.status` |
| 1 | Unexpected/internal error |
| 2 | Usage error (bad flags/args) |
| 3 | Auth — not authenticated, wrong credential type, or forbidden |
| 4 | Not found — job/key/patient/cohort/project/integration/file does not exist |
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
| `api:manage-patients` | Create, read, update, soft-delete patients; also needed to query them |
| `sdk:event-log` | Log events and upload passive signal Parquet (`send_signals`) |
| `sdk:state-read` | Read patient state, summaries, event logs (`olira state *`) |
| `sdk:patient-token` | Mint short-lived patient-scoped JWTs |
| `sdk:integrations` | Manage/query EHR integrations — catalog, connect/disconnect, sync status (control-plane only) |
| `sdk:integration-write` | Honor `write_back` on logged events for EHR write-back |
| `api:manage-projects` | Manage/query projects (org-wide keys only) |
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

_QUERY_COMMANDS = """\
Read-only — same `OLIRA_API_KEY` as `ingest`/`validate`, no writes, no prompts:

| Command | Scope needed | `--project`? |
|---|---|---|
| `olira patients list [--limit N] [--offset N] [--external-system S --external-value V]` / `get <patient_id>` | `api:manage-patients` | yes |
| `olira state stable\\|modules\\|views\\|view-block\\|recent\\|logs\\|events\\|memories <patient_id> ...` | `sdk:state-read` | no (patient-keyed) |
| `olira cohorts list` / `get <cohort_id>` / `templates <cohort_id>` | `api:manage-patients` | yes |
| `olira projects list` / `get <id_or_slug>` | `api:manage-projects` (org-wide key) | n/a (no flag exists) |
| `olira integrations catalog` / `list` / `get <id>` / `data-points <id> [--catalog]` | `sdk:integrations` | n/a (org-level) |

`state modules`/`state views` list when called with no second positional arg, or fetch one item's full payload when given a type (e.g. `olira state modules <patient_id> symptoms`). Clinical payloads are arbitrary JSON — read `data` in `--json` mode rather than parsing prose.
"""

_INGEST_RECIPES = """\
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

_QUERY_RECIPES = """\
```bash
# Look up a patient, then ask about their clinical state
olira patients list --external-system epic --external-value MRN-12345 --json
olira state logs <patient_id> --event-types symptom_report --limit 20 --json
olira state stable <patient_id> --json

# Check an EHR integration's sync health
olira integrations list --json
olira integrations data-points <integration_id> --json
```
"""

_INGEST_FAILURE_PLAYBOOK = """\
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

_QUERY_FAILURE_PLAYBOOK = """\
| Exit code | Likely cause | Next command |
|---|---|---|
| 3 (`AUTH_REQUIRED`) | `OLIRA_API_KEY` unset, or missing the specific scope this command needs (see the scope column above) | `olira keys create --scopes <the one you need>`, then `export OLIRA_API_KEY=...` |
| 4 (`NOT_FOUND`) | The id/slug doesn't exist, or belongs to a different project | Double check the id; for `patients`/`cohorts`, try `--project <id-or-slug>` |
"""

_INGEST_GOLDEN_RULES = """\
- Always pass a SHORT `--timeout` with `--watch` (e.g. `--timeout 60` to `--timeout 120`). This bounds how long *this one tool call* blocks — it is not a guess at the job's real duration. Ingestion jobs can legitimately run for hours; `--watch` is for catching the common case where a job finishes quickly, not for sitting through a long one. On exit `8` (`WATCH_TIMEOUT`), the job is still running server-side — report progress and check back with a plain `olira ingest status <job_id> --json` in a later turn instead of re-watching with an ever-bigger timeout.
- Check `data.status` on ingestion jobs — `completed_with_errors` exits 0 but is a partial success.
"""

_SETUP_GOLDEN_RULES = """\
- Never run `olira login` yourself — it opens a real browser and will refuse to run headlessly (exit 6). If `OLIRA_API_KEY` isn't set, ask the human to create one with `olira keys create`, or to log in themselves first if you need `keys *`/`configure cursor` (browser-login-only commands).
- `keys create`/`keys revoke` bypass their interactive prompts with `--name`/`--scopes` and `--yes` respectively — pass them up front rather than relying on a TTY.
"""


def _skill_frontmatter(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---"


def _skill_md_ingest(version: str) -> str:
    return f"""{
        _skill_frontmatter(
            "olira-ingest",
            "Upload and manage historical patient data ingestion jobs with the Olira CLI — "
            "validate JSONL, upload, watch/confirm/cancel/retry jobs, non-interactively.",
        )
    }

# Olira CLI — Historical Ingestion

Installed as `olira` (verify with `olira --version`; this doc matches v{version}).
For the auth-class split, the JSON envelope shape, and the full exit-code
table shared by every olira command, see `AGENTS.md` at the repo root.

## Auth

`olira ingest *` / `olira validate --check-org` need an **API key**
(`OLIRA_API_KEY=olira_...`, scope `sdk:historical-ingest`) — a browser login
is rejected. Multi-project orgs: `--project <id-or-slug>` (or
`OLIRA_PROJECT`).

## Golden rules for this workflow

{_INGEST_GOLDEN_RULES}

## Ingestion job state machine

{_STATE_MACHINE}

## JSONL schema

{_JSONL_SCHEMA}

## Recipes

{_INGEST_RECIPES}

## Failure playbook

{_INGEST_FAILURE_PLAYBOOK}
"""


def _skill_md_query(version: str) -> str:
    return f"""{
        _skill_frontmatter(
            "olira-query",
            "Query patients, clinical state, cohorts, projects, and EHR integrations read-only "
            "with the Olira CLI — same API key as ingestion, no writes, no prompts.",
        )
    }

# Olira CLI — Querying

Installed as `olira` (verify with `olira --version`; this doc matches v{version}).
For the auth-class split, the JSON envelope shape, and the full exit-code
table shared by every olira command, see `AGENTS.md` at the repo root.

## Auth

Same **API key** (`OLIRA_API_KEY=olira_...`) as ingestion — a browser login
is rejected for all of these. Each command needs a specific scope; see the
table below. `patients`/`cohorts` accept `--project <id-or-slug>` (or
`OLIRA_PROJECT`); `state`/`projects`/`integrations` don't (patient-keyed or
org-level).

## Commands

{_QUERY_COMMANDS}

## Recipes

{_QUERY_RECIPES}

## Failure playbook

{_QUERY_FAILURE_PLAYBOOK}
"""


def _skill_md_setup(version: str) -> str:
    return f"""{
        _skill_frontmatter(
            "olira-setup",
            "Authenticate, manage API keys, and configure MCP client access (Cursor, Claude Code, "
            "Codex) with the Olira CLI.",
        )
    }

# Olira CLI — Auth & Setup

Installed as `olira` (verify with `olira --version`; this doc matches v{version}).

## Two credential classes — not interchangeable

- **API key** (`OLIRA_API_KEY=olira_...`) — required by `olira ingest *`, `olira validate --check-org`, and every read-only query command (`patients`/`state`/`cohorts`/`projects`/`integrations`). A browser login is rejected for these.
- **Browser login** (`olira login`) — required by `olira keys *` and `olira configure cursor`. An API key is rejected for these. Never run `olira login` yourself; it opens a real browser and refuses to run headlessly. Ask the human to run it, or to hand you an API key instead.

## Scopes

Grant only what a key needs — least privilege, one scope per capability:

{_SCOPE_TABLE}

## Key management (needs browser login)

```bash
olira keys create --name "my-agent" --scopes sdk:historical-ingest api:manage-patients
olira keys list --json
olira keys revoke <name-or-id> --yes
```

## MCP client configuration

Two independent things, don't confuse them:

- **`olira init agent`** writes the skills you're reading now (`olira-ingest`/`olira-query`/`olira-setup`) plus `AGENTS.md` — teaches an agent to drive the CLI's commands.
- **`olira configure cursor` / `configure claude` / `configure codex`** connect that client's *own* MCP tool access to Olira's MCP server (for querying patient state as a tool, not by shelling out to the CLI). `configure cursor` needs a browser login and embeds the current token; `configure claude`/`configure codex` need no auth to run and never write a secret to disk — both reference an env var (`OLIRA_API_KEY` by default, override with `--api-key-env`) that must be exported wherever that client actually runs, scoped to `mcp:patient-state`.

## Golden rules for this workflow

{_SETUP_GOLDEN_RULES}
"""


def _agents_md_block(version: str) -> str:
    return f"""{_MARKER_BEGIN.format(version=version)}
## Olira CLI

Installed as `olira`. Full reference, split by workflow (also readable
directly): `.claude/skills/olira-ingest/SKILL.md` (historical ingestion),
`.claude/skills/olira-query/SKILL.md` (read-only querying),
`.claude/skills/olira-setup/SKILL.md` (auth, keys, MCP configuration).

- Auth: `OLIRA_API_KEY=olira_...` for `ingest`/`validate --check-org`/`patients`/`state`/`cohorts`/`projects`/`integrations`; browser login (`olira login`, human-only) for `keys`/`configure cursor`.
- Always pass `--json`. With `--watch`, pass a SHORT `--timeout` (e.g. `60`-`120`) — it bounds how long *this call* blocks, not the job's real duration. Ingestion can legitimately run for hours; on exit `8` (`WATCH_TIMEOUT`) the job is still running — report progress and re-check with a later, non-watching `status` call instead of re-watching with a bigger timeout.
- Never rely on interactive prompts — pass `--yes`/`--name`/`--scopes`/`--init-templates`/`--no-backfill`/`--dir` up front.
- Read-only querying: `olira patients`/`state`/`cohorts`/`projects`/`integrations` — no writes, no prompts, same API key as ingestion.

{_EXIT_CODE_TABLE}
{_MARKER_END}
"""


def _cursor_mdc_ingest(version: str) -> str:
    return f"""---
description: Using the Olira CLI for historical patient data ingestion (validate/upload/confirm/watch)
alwaysApply: false
---

# Olira CLI — Historical Ingestion (v{version})

{_INGEST_GOLDEN_RULES}

{_STATE_MACHINE}

{_INGEST_RECIPES}
"""


def _cursor_mdc_query(version: str) -> str:
    return f"""---
description: Using the Olira CLI to query patients, clinical state, cohorts, projects, and EHR integrations
alwaysApply: false
---

# Olira CLI — Querying (v{version})

{_QUERY_COMMANDS}

{_QUERY_RECIPES}
"""


def _cursor_mdc_setup(version: str) -> str:
    return f"""---
description: Using the Olira CLI for auth, API key management, and MCP client configuration
alwaysApply: false
---

# Olira CLI — Auth & Setup (v{version})

{_SETUP_GOLDEN_RULES}

## Scopes

{_SCOPE_TABLE}
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


def _remove_legacy_monolith(directory: Path, client: str) -> dict[str, str] | None:
    """Delete the single-skill artifact a pre-split `olira init agent` wrote, if present.

    Only for `claude` (a directory: `.claude/skills/olira/`) and `cursor` (a
    single file: `.cursor/rules/olira.mdc`) — AGENTS.md has nothing legacy
    to remove since its managed block is rewritten in place either way.
    """
    import shutil

    for legacy_client, parts in _LEGACY_PATHS:
        if legacy_client != client:
            continue
        target = directory / f".{legacy_client}" / Path(*parts)
        if legacy_client == "claude" and target.is_dir():
            shutil.rmtree(target)
            return {"path": str(target), "action": "removed (superseded by per-process skills)"}
        if legacy_client == "cursor" and target.is_file():
            target.unlink()
            return {"path": str(target), "action": "removed (superseded by per-process rules)"}
    return None


def write_agent_docs(directory: Path, *, claude: bool, cursor: bool, codex: bool) -> list[dict[str, str]]:
    """AGENTS.md is always written — it's the shared foundation every client (including Codex,
    which reads it natively, no special format) needs regardless of which flags are passed.
    No flags at all means "set this repo up completely": default to every client.
    """
    version = __version__
    files: list[dict[str, str]] = []

    if not (claude or cursor or codex):
        claude = cursor = codex = True

    path = directory / "AGENTS.md"
    begin_prefix = _MARKER_BEGIN.split("v{version}")[0]
    action = write_marker_block(path, _agents_md_block(version), begin_prefix=begin_prefix, end_marker=_MARKER_END)
    files.append({"path": str(path), "action": action})

    if claude:
        legacy = _remove_legacy_monolith(directory, "claude")
        if legacy:
            files.append(legacy)
        for slug, builder in (
            ("olira-ingest", _skill_md_ingest),
            ("olira-query", _skill_md_query),
            ("olira-setup", _skill_md_setup),
        ):
            path = directory / ".claude" / "skills" / slug / "SKILL.md"
            action = _write_whole_file(path, builder(version))
            files.append({"path": str(path), "action": action})

    if cursor:
        legacy = _remove_legacy_monolith(directory, "cursor")
        if legacy:
            files.append(legacy)
        for slug, builder in (
            ("olira-ingest", _cursor_mdc_ingest),
            ("olira-query", _cursor_mdc_query),
            ("olira-setup", _cursor_mdc_setup),
        ):
            path = directory / ".cursor" / "rules" / f"{slug}.mdc"
            action = _write_whole_file(path, builder(version))
            files.append({"path": str(path), "action": action})

    return files


def cmd_init_agent(args: Any) -> CommandResult:
    directory = Path(getattr(args, "agents_dir", None) or Path.cwd())

    files = write_agent_docs(
        directory,
        claude=getattr(args, "claude", False),
        cursor=getattr(args, "cursor", False),
        codex=getattr(args, "codex", False),
    )

    if not output.json_mode():
        for f in files:
            print(f"  {f['action']:<9} {f['path']}")

    return CommandResult({"files": files})
