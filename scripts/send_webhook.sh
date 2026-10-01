#!/bin/sh
# Usage: scripts/send_webhook.sh <event_id> <provider_reference> <SUCCESS|FAILED> [base_url]
# Signs the body with WEBHOOK_SECRET (default: dev-webhook-secret) and POSTs it.
set -e
EVENT_ID=$1; REF=$2; STATUS=$3; BASE=${4:-http://localhost:8000}
SECRET=${WEBHOOK_SECRET:-dev-webhook-secret}
BODY=$(printf '{"event_id":"%s","provider_reference":"%s","status":"%s"}' "$EVENT_ID" "$REF" "$STATUS")
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -s -X POST "$BASE/payments/webhook/" -H "Content-Type: application/json" -H "X-Signature: $SIG" -d "$BODY"
echo
