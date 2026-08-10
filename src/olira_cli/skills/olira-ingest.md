---
name: olira-ingest
description: Upload and manage historical patient data ingestion jobs with the Olira CLI — validate JSONL, upload, watch/confirm/cancel/retry jobs, non-interactively.
---

# Olira CLI — Historical Ingestion

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}).
For the auth-class split, the JSON envelope shape, and the full exit-code
table shared by every olira command, see `AGENTS.md` at the repo root.
This workflow is for **bulk historical files**; live, ongoing logging from
the codebase itself is the `olira-logging` skill instead.

## Auth

`olira ingest *` / `olira validate --check-org` need an **API key**
(`OLIRA_API_KEY=olira_...`, scope `sdk:historical-ingest`) — a browser login
is rejected. Multi-project orgs: `--project <id-or-slug>` (or
`OLIRA_PROJECT`).

## Golden rules for this workflow

- Always pass a SHORT `--timeout` with `--watch` (60 to 120 seconds). The timeout bounds how long this one call blocks. It is not a guess at the job's real duration — jobs can legitimately run for hours.
- Exit `8` (`WATCH_TIMEOUT`) means the job is STILL RUNNING, not failed. Report progress now; check again later with `olira ingest status <job_id> --json` (no `--watch`). Never retry with a bigger timeout.
- Check `data.status` on every job response. `completed_with_errors` exits 0 but is a partial success — inspect `data.error_summary`.

## Ingestion job state machine

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

(A third option, an interactive prompt, exists for humans at a TTY only —
never rely on it as an agent.) Without one of these flags, `confirm` exits 6
with code `CONFIRMATION_REQUIRED`.

## JSONL schema

One JSON object per line. Two record types:

```jsonl
{"type": "patient", "data": {"external_identifiers": [{"system": "mrn", "value": "abc123"}], "first_name": "Jane", "date_of_birth": "1990-01-01"}}
{"type": "log", "data": {"patient_id": "abc123", "event_type": "symptom_report", "timestamp": "2025-01-15T09:00:00Z", "payload": {"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 6}]}}}
```

Rules:
- A patient must be declared (a `type: "patient"` line) before any `log` line references its `patient_id`, unless that id already exists in the org.
- `patient_id` must be a pseudonymous identifier — never an email, phone number, or SSN (the validator rejects these).
- `event_type` must be a known type — run `olira validate` to check against the current catalog.
- Always run `olira validate <file>.jsonl --json` before `olira ingest upload` — fix everything in `error.details.errors` first.

## Recipes

```bash
# 1. Validate before uploading — always do this first
olira validate data.jsonl --json

# 2. Upload. --watch --timeout is a SHORT bound (catches quick jobs) — if it
#    times out (exit 8), the job is still running; that's not a failure.
#    The job id you need for every later step is data.job.job_id in the
#    final JSON envelope (fallback: data.job_id).
olira ingest upload data.jsonl --json --watch --timeout 90

# 3. If it paused at AWAITING_CONFIRMATION with missing templates
olira ingest confirm <job_id> --init-templates --json --watch --timeout 90

# 4. If step 2 or 3 timed out, don't re-watch with a bigger number — report
#    progress now and check back later with a plain (non-watching) status call:
olira ingest status <job_id> --json

# 5. Check what's failing across the org
olira ingest list --status failed --json
```

## Done checklist

Before reporting the ingestion finished, confirm every item:

- [ ] `olira validate` exited 0 on the final version of the file.
- [ ] The job reached `completed` or `completed_with_errors` (from a `status` call, not assumed).
- [ ] If `completed_with_errors`: `data.error_summary` inspected and reported to the user.
- [ ] If the watch timed out: the job id and last-known progress were reported — a running job is not a finished task.

## Failure playbook

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
