#!/usr/bin/env bash
# One-time, idempotent setup for www.clementine-player.org's GITHUB_TOKEN
# Secret Manager secret (replaces the old plaintext env_variables in
# app.yaml). Requires gcloud authenticated with Secret Manager admin rights
# on clementine-web.
#
# Usage: pipe the token in on stdin, so it never touches argv/shell history:
#   echo -n "$YOUR_GITHUB_TOKEN" | tools/setup-www-secrets.sh
set -euo pipefail

PROJECT_ID=clementine-web
SECRET_NAME=GITHUB_TOKEN
SERVICE_ACCOUNT_EMAIL="clementine-web@appspot.gserviceaccount.com"

if [ -t 0 ]; then
  echo "Usage: echo -n \"\$YOUR_GITHUB_TOKEN\" | $0" >&2
  exit 1
fi

gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1 || \
gcloud secrets create "$SECRET_NAME" \
  --project="$PROJECT_ID" --replication-policy=automatic

gcloud secrets versions add "$SECRET_NAME" --project="$PROJECT_ID" --data-file=-

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project="$PROJECT_ID" --role="roles/secretmanager.secretAccessor" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}"

echo "Done. The App Engine default service account (${SERVICE_ACCOUNT_EMAIL}) can now read ${SECRET_NAME}."
