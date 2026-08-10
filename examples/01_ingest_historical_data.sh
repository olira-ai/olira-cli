#!/usr/bin/env bash
# Validate, upload, and confirm a small historical ingestion job end-to-end.
#
# Usage:
#   export OLIRA_API_KEY=olira_...   # needs sdk:historical-ingest scope
#   ./01_ingest_historical_data.sh
set -euo pipefail

if [ -z "${OLIRA_API_KEY:-}" ]; then
    echo "Error: OLIRA_API_KEY is not set." >&2
    echo "Create one with: olira keys create --name example --scopes sdk:historical-ingest" >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "Error: this script needs 'jq' (brew install jq / apt-get install jq)." >&2
    exit 1
fi

DATA_FILE="$(mktemp -t olira-example-data).jsonl"
trap 'rm -f "$DATA_FILE"' EXIT

cat > "$DATA_FILE" <<'EOF'
{"type": "patient", "data": {"external_identifiers": [{"system": "example", "value": "example-patient-1"}], "first_name": "Example", "last_name": "Patient"}}
{"type": "log", "data": {"patient_id": "example-patient-1", "event_type": "symptom_report", "timestamp": "2026-01-15T09:00:00Z", "payload": {"symptoms": [{"name": "fatigue", "score": 4}]}}}
EOF

echo "==> Validating $DATA_FILE"
olira validate "$DATA_FILE" --json | jq .

echo
echo "==> Uploading (--watch --timeout 90 bounds how long this call blocks, not the job's real duration)"
set +e
UPLOAD=$(olira ingest upload "$DATA_FILE" --json --watch --timeout 90)
UPLOAD_STATUS=$?
set -e
echo "$UPLOAD" | jq .
if [ "$UPLOAD_STATUS" -ne 0 ] && [ "$UPLOAD_STATUS" -ne 8 ]; then
    echo "==> Upload failed (exit $UPLOAD_STATUS) — see error above" >&2
    exit "$UPLOAD_STATUS"
fi
JOB_ID=$(echo "$UPLOAD" | tail -1 | jq -r '.data.job.job_id // .data.job_id // empty')

if [ -z "$JOB_ID" ]; then
    echo "Error: could not determine job_id from upload output." >&2
    exit 1
fi

STATUS=$(olira ingest status "$JOB_ID" --json | jq -r '.data.job.status')
echo
echo "==> Job $JOB_ID is now: $STATUS"

if [ "$STATUS" = "awaiting_confirmation" ]; then
    echo "==> Confirming (initializing any missing view templates)"
    # --timeout bounds how long THIS call blocks, not the job's real duration
    # (see using-olira-with-agents.md). If it times out (exit 8), that's not
    # a failure — this is the "check back later" fallback the docs describe,
    # not a naive retry with an ever-bigger timeout.
    set +e
    CONFIRM=$(olira ingest confirm "$JOB_ID" --init-templates --json --watch --timeout 90)
    CONFIRM_STATUS=$?
    set -e
    echo "$CONFIRM" | jq .
    if [ "$CONFIRM_STATUS" -eq 8 ]; then
        echo "==> Still running past the watch window — polling status instead of blocking further"
        for _ in $(seq 1 30); do
            sleep 10
            STATUS=$(olira ingest status "$JOB_ID" --json | jq -r '.data.job.status')
            echo "    status: $STATUS"
            case "$STATUS" in
                completed|completed_with_errors|cancelled|failed) break ;;
            esac
        done
    elif [ "$CONFIRM_STATUS" -ne 0 ]; then
        echo "==> Confirm failed (exit $CONFIRM_STATUS) — see error above" >&2
        exit "$CONFIRM_STATUS"
    fi
fi

echo
echo "==> Final status"
olira ingest status "$JOB_ID" --json | jq .
