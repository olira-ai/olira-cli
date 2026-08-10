# Using Olira with a coding agent

This CLI is built so a coding agent — Cursor, Claude Code, Codex, or
anything else that can run shell commands — can drive it correctly without
you writing custom integration code. This guide covers the one-time setup
and what to expect once your agent is working with it.

## 1. Install the CLI

```bash
brew install olira-ai/tap/olira
# or: curl -fsSL https://install.olira.ai | sh
olira --version
```

## 2. Create an API key (you do this, not the agent)

Agents can't complete `olira login` — it opens a real browser. Log in
yourself once, then create a long-lived API key for the agent to use:

```bash
olira login
olira keys create --name "my-agent" --scopes sdk:historical-ingest api:manage-patients sdk:state-read sdk:integrations
```

Grant only the scopes your agent actually needs — see
[docs.olira.ai/cli/scopes](https://docs.olira.ai/cli/scopes) for what each
one unlocks. Copy the key; it's shown once.

## 3. Teach your agent how to use the CLI

Run this once, in the repo your agent works in:

```bash
export OLIRA_API_KEY=olira_...
olira init agent
```

This writes `AGENTS.md` plus three focused skills — `olira-ingest`,
`olira-query`, `olira-setup` — as `.claude/skills/<name>/SKILL.md` for Claude
Code and `.agents/skills/<name>/SKILL.md` for Cursor and Codex, the shared
location both of those discover skills from. `AGENTS.md` covers the auth
model, the `--json` envelope, and the full exit-code table; each skill
covers only its own workflow (the ingestion state machine, the read-only
query commands, or key management) so a task only loads what it needs.
Most agents (Claude Code, Cursor, Codex) pick these up automatically; if
yours doesn't, point it at `AGENTS.md` directly.

Make sure `OLIRA_API_KEY` is set wherever your agent actually runs shell
commands (its own terminal session, not just yours) — `export` doesn't
cross into a different process.

## 4. Give your agent a task

Some things to try:

- *"Validate `data.jsonl` and fix any errors it reports."*
- *"Upload `data.jsonl` as a historical ingestion job and confirm it once
  it's ready for review."*
- *"What symptoms has patient `<id>` reported recently?"*
- *"List our connected EHR integrations and tell me if any are failing to
  sync."*
- *"Create an API key called `ci-pipeline` with the event-log scope."* —
  this one should make your agent stop and tell you it needs your help,
  since key management requires a browser login it can't do itself. That's
  the CLI working as intended, not a bug.

## What correct agent behavior looks like

- It passes `--json` on every call and reads `error.code` /
  `error.remediation` instead of guessing from prose.
- It never gets stuck waiting for input — every prompt has a
  non-interactive flag, and the CLI fails fast (exit `6`) naming it if the
  flag is missing.
- With `--watch`, it uses a **short** `--timeout` (60–120s) and, on exit `8`
  (`WATCH_TIMEOUT`), reports progress and checks back later rather than
  re-watching with an ever-bigger timeout. Bulk ingestion jobs can
  legitimately run for hours — no coding agent should block a whole turn
  waiting for one to finish.
- It recognizes when a task needs you (browser login, granting a new
  scope) and asks, rather than trying to work around it.

If your agent isn't doing these things, the fastest fix is usually to
re-run `olira init agent` (it's idempotent) and point the agent at
the file it wrote for its client.

## See also

- [`01_ingest_historical_data.sh`](01_ingest_historical_data.sh),
  [`02_query_patient_data.sh`](02_query_patient_data.sh),
  [`03_integration_health.sh`](03_integration_health.sh) — the same
  workflows above, as plain shell scripts, if you want to see the exact
  commands without an agent in the loop.
- [CLI_DOCUMENTATION.md](../CLI_DOCUMENTATION.md) — full command reference,
  JSON envelope, exit codes, and credential model.
