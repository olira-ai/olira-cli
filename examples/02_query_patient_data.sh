#!/usr/bin/env bash
# Look up a patient and read their clinical state — read-only, no writes.
#
# Usage:
#   export OLIRA_API_KEY=olira_...   # needs api:manage-patients + sdk:state-read scopes
#   ./02_query_patient_data.sh                 # uses the first patient found in the org
#   PATIENT_ID=<id> ./02_query_patient_data.sh # or target a specific patient
set -euo pipefail

if [ -z "${OLIRA_API_KEY:-}" ]; then
    echo "Error: OLIRA_API_KEY is not set." >&2
    echo "Create one with: olira keys create --name example --scopes api:manage-patients sdk:state-read" >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "Error: this script needs 'jq' (brew install jq / apt-get install jq)." >&2
    exit 1
fi

if [ -z "${PATIENT_ID:-}" ]; then
    echo "==> No PATIENT_ID given — looking up the first patient in the org"
    PATIENT_ID=$(olira patients list --limit 1 --json | jq -r '.data.patients[0].id // empty')
    if [ -z "$PATIENT_ID" ]; then
        echo "Error: no patients found. Run 01_ingest_historical_data.sh first, or set PATIENT_ID=<id>." >&2
        exit 1
    fi
fi

echo "==> Patient: $PATIENT_ID"
olira patients get "$PATIENT_ID" --json | jq .

echo
echo "==> Stable data modules"
olira state stable "$PATIENT_ID" --json | jq .

echo
echo "==> Views"
olira state views "$PATIENT_ID" --json | jq .

echo
echo "==> 5 most recent event logs"
olira state logs "$PATIENT_ID" --limit 5 --json | jq .
