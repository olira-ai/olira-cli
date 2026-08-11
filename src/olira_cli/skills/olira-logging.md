---
name: olira-logging
description: Instrument a codebase to log events to Olira with the Python SDK — discover the right log type from the catalog, shape the payload to its JSON Schema, call client.log(), and verify the round-trip.
---

# Olira CLI — Logging from your own code

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}).
Everything here needs `OLIRA_API_KEY=olira_...` exported in the shell that
runs the CLI, and passed as `api_key=` to the SDK client.

This skill covers **live, ongoing logging**: `client.log(...)` calls in the
codebase so events flow to Olira as they happen. Two adjacent workflows are
different skills:
- **Historical backfill** (a bulk file, or one patient's past history at setup time) → the `olira-ingest` workflow: `olira validate` + `olira ingest upload` for files, or `client.create_ingestion_job(records=...)` from code.
- A data model **too awkward to reshape at every call site** (a vendor system's payloads, many call sites) → Olira supports registering org-native source schemas with server-side mappings. There is no CLI tooling for that yet; ask Olira.

## Step 1 — Find the right log type

Olira has a **closed catalog of log types**, each with a full payload JSON
Schema. Never guess a type or a payload shape. Follow this procedure:

1. Run `olira log-types list --json`. Each entry has `subtype`, `category`, and a `description`.
2. Search the descriptions (not the names) for the kind of data you are logging.
3. Read the matching type's description fully. It contains "Use for: ..." and "Do not use for: ..." sentences.
4. **Redirect rule:** if the description says `Do not use for: <your case> (<other_subtype>)`, your data belongs to `<other_subtype>`. Switch to it and re-read from step 3.
   Example: `symptom_report` says "Do not use for: free-text symptom descriptions (symptom_free_text); mood labels (mood_report)" — so a mood label must be logged as `mood_report`, never `symptom_report`.
5. Run `olira log-types get <subtype> --json` and read `data.payload_schema`: the `required` list, each property's type, and any enums. This schema is the contract your payload must satisfy.

`get` accepts known aliases and resolves them to the canonical subtype.

## Auth & scopes

| Doing what | Scope needed |
|---|---|
| `client.log()` / `log_batch()` / `log_fhir()` | `sdk:event-log` |
| Look up / create patients (`olira patients *`) | `api:manage-patients` |
| Verify by reading logs back (`olira state logs`) | `sdk:state-read` |

One API key can carry all three scopes. If the key is missing a scope, ask
the human to create one — `olira keys create` needs a browser login, so
never run it yourself.

## Step 2 — Complete example (copy and adapt)

```python
import os
from olira import OliraClient

client = OliraClient(api_key=os.environ["OLIRA_API_KEY"])
# Multi-project orgs: add project="<id-or-slug>" to target a specific
# workspace (e.g. a dev project while testing). A project-locked key
# needs no project param. Logs always inherit the patient's project.

# patient_id must be the OLIRA-ASSIGNED id, not your system's identifier.
# Resolve yours first (see "Patient ids" below), or hardcode a known one.
patient_id = "<olira-assigned id>"

client.log(
    log_type="symptom_report",           # the subtype chosen in Step 1
    patient_id=patient_id,
    payload={                            # must satisfy the Step 1 schema
        "instrument": "esas_r",
        "symptoms": [{"name": "pain", "score": 6}],
        "source": "patient_self_report",
    },
    timestamp="2026-01-15T09:00:00Z",    # when it happened (ISO 8601 UTC); omit for "now"
)

client.flush()   # REQUIRED before exit — log() only queues; without flush the event is lost
client.close()
```

Then verify it landed (Step 3):

```bash
olira state logs <patient_id> --event-types <subtype> --limit 5 --json
```

### SDK notes

- `log()` queues the event in memory and returns immediately. A script that
  exits without `flush()` or `close()` **silently loses queued events**.
  Long-running servers may rely on the periodic background flush; scripts,
  jobs, and CI must call `flush()` before exit. This is the most common bug.
- `log()` also accepts `metadata=` (unvalidated, see shaping rules) and
  `trace=` (an `OliraTrace` linking the event to a source object).
- **Bursts:** `client.log_batch([LogSpec(log_type=..., patient_id=..., payload=..., idempotency_key=...), ...])`
  (`from olira import LogSpec`) sends one synchronous request and returns
  `BatchResult(accepted, failed, errors)`.
  Always check `failed` and `errors` — partial failures are reported per item.
  `idempotency_key` (dedup on retry) exists on `LogSpec` only; `log()` does not take it.
  **`log_batch` is for live bursts only — never for historical backfill.**
  Months of past events (a bulk import, or one patient's history at setup
  time) go through the ingestion pipeline instead
  (`client.create_ingestion_job(...)` — see the `olira-ingest` skill),
  which replays rows in chronological order and backfills summary views;
  `log_batch` with old timestamps does neither.
- **Passive sensor streams:** multi-Hz accelerometer/gyroscope/GPS batches
  go through `client.send_signals(patient_id=..., sensor_type=..., source_device=..., records=... | parquet=...)`
  as Parquet — `records=` serialized locally (`pip install olira[signals]`)
  or pre-serialized `parquet=` bytes; same `sdk:event-log` scope — never
  through `log()`/`log_batch()`. Returns a job handle; call `handle.wait()`
  to confirm absorption.
- **Already-FHIR sources:** `client.log_fhir(patient_id=..., resource=...)`
  maps an R4 resource to platform log types server-side. No `log_type`
  choice, no payload shaping.
- **Non-Python stacks:** `POST /v1/logs/batch` with
  `Authorization: Bearer $OLIRA_API_KEY` is the same contract the SDK uses.
- An `AsyncOliraClient` exists with the same methods as `async def`.

### Patient ids

`patient_id` is the **Olira-assigned id**. Your system's own identifier
will fail with a 404. Resolve it first:

```bash
olira patients list --external-system <your-system> --external-value <your-id> --json
```

The Olira id is `data.patients[0].id` in the response. If the patient does
not exist yet, create it with `client.create_patient(...)` and include
`external_identifiers` so future lookups resolve.

## Payload shaping rules

1. **Use only fields the Step 1 schema defines.** Ingest validates every payload against the catalog. Unknown or mis-typed fields cause a 422 rejection; nothing is silently dropped.
2. Include every field in the schema's `required` list.
3. Set `source` (most types define it) to record who asserted the fact. Either a string (`"patient_self_report"`, `"clinician"`, `"ehr_import"`) or a structured object (`{"type": "ehr_import", "source_system": "epic", "reference_id": "..."}`).
4. `extensions` is valid **only where the type's schema defines it** (e.g. per-symptom `extensions` entries on `symptom_report`). Never add an extensions bag to a type that does not declare one.
5. Data with no schema slot goes in **event-level `metadata=`** on the `log()` call — a sibling of the payload, stored but never validated. Rule of thumb: clinical content → `payload` (typed, drives patient state); operational context (your internal ids, versions, routing info) → `metadata`.
6. Timestamps are ISO 8601 UTC strings: `2026-01-15T09:00:00Z`.

## Step 3 — Verify the round-trip

After logging against a test patient:

```bash
olira state logs <patient_id> --event-types <subtype> --limit 5 --json
```

In the response, confirm `data.count` is at least 1 and
`data.logs[0].payload` matches what you sent. Do this once per new call
site. It proves the type choice, payload shape, and patient resolution all
at once — no other check does.

## Done checklist

Before reporting the integration finished, confirm every item:

- [ ] Log type chosen from catalog descriptions (Step 1 procedure), not guessed from the name.
- [ ] Payload contains only schema-defined fields and all `required` ones.
- [ ] `patient_id` is the Olira-assigned id.
- [ ] `flush()` (or `close()`) is called before every exit path of the script.
- [ ] `log_batch` results checked for `failed` / `errors` (if used).
- [ ] Round-trip verified with `olira state logs` (Step 3).

## Failure playbook

| Symptom | Likely cause | Next step |
|---|---|---|
| 422 on log, message names a field or the event type | Payload does not satisfy the catalog schema | Re-run `olira log-types get <subtype> --json`, fix the payload to match, then retry |
| 403 | Key missing `sdk:event-log` | Ask the human for a key with the scope |
| 404 patient | Unknown `patient_id`, or an external id was passed | Resolve via `olira patients list --external-system ... --external-value ...`; create the patient if needed |
| 409 "being processed by a historical ingestion job" | Patient is mid-backfill; logging is temporarily locked | Wait and retry later — this clears on its own |
| Events missing on read-back, no errors anywhere | Script exited before the queue flushed | Add `client.flush()` before exit |
