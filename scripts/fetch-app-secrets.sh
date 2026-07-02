#!/usr/bin/env bash
# Fetch the application-backend (ADR-0026) secrets from Google Secret Manager and
# print them as KEY=VALUE lines for the docker-compose env. Append to the deploy
# `.env` (gitignored) so the runtime container gets them as environment and never
# contacts GSM itself:
#
#   bash scripts/fetch-app-secrets.sh >> .env
#
# Requires `gcloud auth login` on the host (secret-accessor on project cdsci-infra).
# NEVER commit the output — these are live credentials.
set -euo pipefail
PROJ="${UCCC_GSM_PROJECT:-cdsci-infra}"
get() { gcloud secrets versions access latest --secret="$1" --project="$PROJ"; }
cat <<EOF
UCCC_APP_DB_PASSWORD=$(get uccc-app-db-password)
UCCC_APP_OIDC_CLIENT_ID=$(get cancerdatasci-oauth-client-id)
UCCC_APP_OIDC_CLIENT_SECRET=$(get cancerdatasci-oauth-client-secret)
UCCC_APP_SESSION_SECRET=$(get uccc-app-session-secret)
EOF
