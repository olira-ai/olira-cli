---
name: olira-query
description: Query patients, clinical state, cohorts, projects, and EHR integrations read-only with the Olira CLI — same API key as ingestion, no writes, no prompts.
---

# Olira CLI — Querying

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}).
For the auth-class split, the JSON envelope shape, and the full exit-code
table shared by every olira command, see `AGENTS.md` at the repo root.

## Auth

Same **API key** (`OLIRA_API_KEY=olira_...`) as ingestion — a browser login
is rejected for all of these. Each command needs a specific scope; see the
table below. `patients`/`cohorts` accept `--project <id-or-slug>` (or
`OLIRA_PROJECT`); `state`/`projects`/`integrations` don't (patient-keyed or
org-level).

## Commands

Read-only — same `OLIRA_API_KEY` as `ingest`/`validate`, no writes, no prompts:

| Command | Scope needed | `--project`? |
|---|---|---|
| `olira patients list [--limit N] [--offset N] [--external-system S --external-value V]` / `get <patient_id>` | `api:manage-patients` | yes |
| `olira state stable\|modules\|views\|view-block\|recent\|logs\|events\|memories <patient_id> ...` | `sdk:state-read` | no (patient-keyed) |
| `olira cohorts list` / `get <cohort_id>` / `templates <cohort_id>` | `api:manage-patients` | yes |
| `olira projects list` / `get <id_or_slug>` | `api:manage-projects` (org-wide key) | n/a (no flag exists) |
| `olira integrations catalog` / `list` / `get <id>` / `data-points <id> [--catalog]` | `sdk:integrations` | n/a (org-level) |

`state modules`/`state views` list when called with no second positional arg, or fetch one item's full payload when given a type (e.g. `olira state modules <patient_id> symptoms`). Clinical payloads are arbitrary JSON — read `data` in `--json` mode rather than parsing prose.

## Recipes

```bash
# Look up a patient, then ask about their clinical state
olira patients list --external-system epic --external-value MRN-12345 --json
olira state logs <patient_id> --event-types symptom_report --limit 20 --json
olira state stable <patient_id> --json

# Check an EHR integration's sync health
olira integrations list --json
olira integrations data-points <integration_id> --json
```

## Failure playbook

| Exit code | Likely cause | Next command |
|---|---|---|
| 3 (`AUTH_REQUIRED`) | `OLIRA_API_KEY` unset, or missing the specific scope this command needs (see the scope column above) | `olira keys create --scopes <the one you need>`, then `export OLIRA_API_KEY=...` |
| 4 (`NOT_FOUND`) | The id/slug doesn't exist, or belongs to a different project | Double check the id; for `patients`/`cohorts`, try `--project <id-or-slug>` |
