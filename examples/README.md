# Olira CLI — Examples

Runnable shell scripts that demonstrate the CLI's main workflows, plus a
guide to driving the CLI with a coding agent instead of by hand. Each script
is self-contained — set `OLIRA_API_KEY` and run it directly.

## Setup

```bash
export OLIRA_API_KEY=olira_...   # create one with: olira keys create
chmod +x *.sh                    # if not already executable
./01_ingest_historical_data.sh
```

Every script needs [`jq`](https://jqlang.org/) (`brew install jq` /
`apt-get install jq`) — the CLI's own output is already machine-readable
(`--json`); these scripts just show how to parse it.

## Examples

| File | What it shows | Required scope(s) |
|---|---|---|
| `01_ingest_historical_data.sh` | Validate → upload → (if needed) confirm a small JSONL file end-to-end, using `--watch --timeout` correctly | `sdk:historical-ingest` |
| `02_query_patient_data.sh` | Look up a patient and read their stable data, views, and recent logs — entirely read-only | `api:manage-patients`, `sdk:state-read` |
| `03_integration_health.sh` | List connected integrations and flag any data point with a failing sync | `sdk:integrations` |
| `using-olira-with-agents.md` | Guide: setting up Cursor, Claude Code, Codex, or any other coding agent to drive this CLI on your behalf | — |

## Notes

- `01_ingest_historical_data.sh` creates a throwaway 2-line JSONL file in a
  temp directory and cleans it up on exit — the ingested data (one example
  patient) is real in whatever org the key belongs to. Use a dev/test org
  if you don't want it in production data.
- `02_query_patient_data.sh` looks up the first patient in the org if
  `PATIENT_ID` isn't set — run `01_ingest_historical_data.sh` first if the
  org has no patients yet.
- `03_integration_health.sh` exits `1` if any data point is failing sync, so
  it's safe to use as a CI/cron health check.
- Full command reference: [docs.olira.ai/cli](https://docs.olira.ai/cli).
  Local copy: [`CLI_DOCUMENTATION.md`](../CLI_DOCUMENTATION.md).
