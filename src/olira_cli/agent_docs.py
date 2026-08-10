"""olira init agent — writes agent-facing docs into a customer repo.

Each skill's full SKILL.md content — frontmatter and body — lives as a real
file under `skills/<slug>.md`, loaded via importlib.resources and packaged
as PyInstaller `--add-data` (see .github/workflows/release.yml). Both Claude
Code and Cursor read the identical SKILL.md format (`name` + `description`
frontmatter under `.claude/skills/<slug>/` or `.cursor/skills/<slug>/`), so
one file serves both clients — no per-client content fork.

Focused per-workflow skills instead of one monolith: `olira-ingest` (the
genuinely complex bulk-historical workflow — state machine,
missing-template-slots, watch/timeout), `olira-logging` (instrumenting a
codebase to log live events via the SDK — catalog discovery, payload
shaping, round-trip verification), `olira-query` (a comparatively simple
command reference), and `olira-setup` (auth model, keys, MCP client
configuration). A model-invoked skill loads
only when its description matches the task, so splitting by process means a
"list patients" task doesn't pull the ingestion state machine into context,
and vice versa. Cross-cutting content used by every task regardless of
which skill (if any) gets loaded — the auth-class split, the JSON envelope,
the full exit-code table — stays in the AGENTS.md digest, which most agents
load unconditionally; skills reference it rather than repeat it. AGENTS.md
itself stays a Python string, not a file: it's a managed block merged into
a file we don't fully own, not a whole file we write outright.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from olira_cli import __version__, output
from olira_cli.errors import CliError, CommandResult

_SKILL_SLUGS = ("olira-ingest", "olira-logging", "olira-query", "olira-setup")

_MARKER_BEGIN = "<!-- BEGIN olira-cli (managed by 'olira init agent', v{version}) -->"
_MARKER_END = "<!-- END olira-cli -->"

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


def _load_skill_md(slug: str, version: str) -> str:
    """Read skills/<slug>.md and substitute the {{VERSION}} placeholder.

    A plain sentinel replace, not str.format() — these files are full of JSON
    examples with literal `{`/`}` braces that format() would choke on.
    """
    text = resources.files("olira_cli").joinpath("skills").joinpath(f"{slug}.md").read_text(encoding="utf-8")
    return text.replace("{{VERSION}}", version)


def _agents_md_block(version: str) -> str:
    return f"""{_MARKER_BEGIN.format(version=version)}
## Olira CLI

Installed as `olira`. Full reference, split by workflow (also readable
directly under `.claude/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md`):
`olira-ingest` (bulk historical ingestion), `olira-logging` (instrumenting
code to log live events via the SDK), `olira-query` (read-only querying),
`olira-setup` (auth, keys, MCP configuration).

- Auth: `OLIRA_API_KEY=olira_...` for `ingest`/`validate --check-org`/`patients`/`state`/`cohorts`/`projects`/`integrations`/`log-types`; browser login (`olira login`, human-only) for `keys`/`configure cursor`.
- Always pass `--json`. With `--watch`, pass a SHORT `--timeout` (e.g. `60`-`120`) — it bounds how long *this call* blocks, not the job's real duration. Ingestion can legitimately run for hours; on exit `8` (`WATCH_TIMEOUT`) the job is still running — report progress and re-check with a later, non-watching `status` call instead of re-watching with a bigger timeout.
- Never rely on interactive prompts — pass `--yes`/`--name`/`--scopes`/`--init-templates`/`--no-backfill`/`--dir` up front.
- Read-only querying: `olira patients`/`state`/`cohorts`/`projects`/`integrations`/`log-types` — no writes, no prompts, same API key as ingestion.

{_EXIT_CODE_TABLE}
{_MARKER_END}
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


def write_agent_docs(directory: Path, *, claude: bool, cursor: bool, codex: bool) -> list[dict[str, str]]:
    """AGENTS.md is always written — it's the shared foundation every client needs regardless
    of which flags are passed. No flags at all means "set this repo up completely": default to
    every client.

    Cursor and Codex both discover skills from the shared, vendor-neutral `.agents/skills/`
    directory (Claude Code doesn't — it only reads `.claude/skills/`), so `--cursor` and
    `--codex` write the identical files there; passing either is enough, passing both doesn't
    duplicate anything.
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
        for slug in _SKILL_SLUGS:
            path = directory / ".claude" / "skills" / slug / "SKILL.md"
            action = _write_whole_file(path, _load_skill_md(slug, version))
            files.append({"path": str(path), "action": action})

    if cursor or codex:
        for slug in _SKILL_SLUGS:
            path = directory / ".agents" / "skills" / slug / "SKILL.md"
            action = _write_whole_file(path, _load_skill_md(slug, version))
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
