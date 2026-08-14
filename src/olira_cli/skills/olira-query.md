---
name: olira-query
description: Query patients, clinical state, cohorts, projects, connected integrations, and the log-type catalog read-only with the Olira CLI — same API key as ingestion, no writes, no prompts.
---

# Olira CLI — Querying

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}).
For the auth-class split, the JSON envelope shape, and the full exit-code
table shared by every olira command, see `AGENTS.md` at the repo root.

## Auth

Same **API key** (`OLIRA_API_KEY=olira_...`) as ingestion — a browser login
is rejected for all of these. Each command needs a specific scope; see the
table below. `patients`/`cohorts` accept `--project <id-or-slug>` (or
`OLIRA_PROJECT`); `state`/`projects`/`integrations`/`log-types` don't
(patient-keyed or org-level).

## Commands

Read-only — same `OLIRA_API_KEY` as `ingest`/`validate`, no writes, no prompts:

| Command | Scope needed | `--project`? |
|---|---|---|
| `olira patients list [--limit N] [--offset N] [--external-system S --external-value V]` / `get <patient_id>` | `api:manage-patients` | yes |
| `olira state <subcommand> <patient_id> ...` — subcommands: `stable`, `modules`, `views`, `view-block`, `recent`, `logs`, `events`, `memories` | `sdk:state-read` | no (patient-keyed) |
| `olira cohorts list` / `get <cohort_id>` / `templates <cohort_id>` | `api:manage-patients` | yes |
| `olira projects list` / `get <id_or_slug>` | `api:manage-projects` (org-wide key) | n/a (no flag exists) |
| `olira integrations catalog` / `list` / `get <id>` / `data-points <id> [--catalog]` | `sdk:integrations` | n/a (org-level) |
| `olira log-types list` / `get <subtype>` | `sdk:event-log` | n/a (org-level) |

`state modules` and `state views` have two forms:
- No second argument → list summaries: `olira state modules <patient_id>`.
- With a type argument → one item's full payload: `olira state modules <patient_id> symptoms`.

## Reading responses

Always pass `--json` and read the `data` field of the final envelope:
- `patients list` → the Olira patient id is `data.patients[].id`; `data.total` and `data.has_more` drive pagination.
- `state logs` → `data.logs[]` (each has `type`, `timestamp`, `payload`); `data.count`.
- Clinical payloads are arbitrary JSON — read them as data, never parse the human-mode prose output.

## Recipes

```bash
# Look up a patient, then ask about their clinical state
olira patients list --external-system epic --external-value MRN-12345 --json
olira state logs <patient_id> --event-types symptom_report --limit 20 --json
olira state stable <patient_id> --json

# Check a connected integration's sync health
olira integrations list --json
olira integrations data-points <integration_id> --json

# Mapping your source field to an Olira log type: browse the catalog,
# then pull one type's full payload JSON Schema before writing the mapping
olira log-types list --json
olira log-types get symptom_report --json
```

## Failure playbook

| Exit code | Likely cause | Next command |
|---|---|---|
| 3 (`AUTH_REQUIRED`) | `OLIRA_API_KEY` unset, or missing the specific scope this command needs (see the scope column above) | `olira keys create --scopes <the one you need>`, then `export OLIRA_API_KEY=...` |
| 4 (`NOT_FOUND`) | The id/slug doesn't exist, or belongs to a different project | Double check the id; for `patients`/`cohorts`, try `--project <id-or-slug>` |
