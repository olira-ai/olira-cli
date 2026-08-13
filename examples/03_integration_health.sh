#!/usr/bin/env bash
# Check every connected integration for failing data-point syncs.
#
# Usage:
#   export OLIRA_API_KEY=olira_...   # needs sdk:integrations scope
#   ./03_integration_health.sh
set -euo pipefail

if [ -z "${OLIRA_API_KEY:-}" ]; then
    echo "Error: OLIRA_API_KEY is not set." >&2
    echo "Create one with: olira keys create --name example --scopes sdk:integrations" >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "Error: this script needs 'jq' (brew install jq / apt-get install jq)." >&2
    exit 1
fi

echo "==> Connected integrations"
INTEGRATIONS=$(olira integrations list --json)
echo "$INTEGRATIONS" | jq .

COUNT=$(echo "$INTEGRATIONS" | jq '.data.data | length')
if [ "$COUNT" -eq 0 ]; then
    echo "No integrations connected."
    exit 0
fi

FAILING_TOTAL=0
for ID in $(echo "$INTEGRATIONS" | jq -r '.data.data[].id'); do
    echo
    echo "==> Integration $ID — data points"
    DP=$(olira integrations data-points "$ID" --json)
    echo "$DP" | jq .

    FAILING=$(echo "$DP" | jq '[.data.data[] | select(.status == "failure")] | length')
    if [ "$FAILING" -gt 0 ]; then
        echo "!! $FAILING data point(s) failing sync on integration $ID" >&2
        FAILING_TOTAL=$((FAILING_TOTAL + FAILING))
    fi
done

echo
if [ "$FAILING_TOTAL" -gt 0 ]; then
    echo "==> $FAILING_TOTAL data point(s) failing sync across $COUNT integration(s)."
    exit 1
fi
echo "==> All data points healthy across $COUNT integration(s)."
