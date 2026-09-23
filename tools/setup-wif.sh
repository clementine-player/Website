#!/usr/bin/env bash
# Sets up Workload Identity Federation so GitHub Actions can deploy to a GCP
# project without a long-lived service-account key. Run once per project:
#
#   tools/setup-wif.sh clementine-web    <www-or-bio-deploy-sa>@clementine-web.iam.gserviceaccount.com
#   tools/setup-wif.sh clementine-data   <data-deploy-sa>@clementine-data.iam.gserviceaccount.com
#
# Requires gcloud authenticated (`gcloud auth login`) with IAM admin rights
# on the target project. Safe to re-run: the describe-before-create checks
# make this idempotent.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <gcp-project-id> <deploying-service-account-email>" >&2
  exit 1
fi

PROJECT_ID="$1"
SERVICE_ACCOUNT_EMAIL="$2"
REPO=clementine-player/Website

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud iam workload-identity-pools describe github-actions \
  --project="$PROJECT_ID" --location=global >/dev/null 2>&1 || \
gcloud iam workload-identity-pools create github-actions \
  --project="$PROJECT_ID" --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers describe website-repo \
  --project="$PROJECT_ID" --location=global --workload-identity-pool=github-actions >/dev/null 2>&1 || \
gcloud iam workload-identity-pools providers create-oidc website-repo \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool=github-actions \
  --display-name="clementine-player/Website" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID" --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/attribute.repository/${REPO}"

echo "Provider path: projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/providers/website-repo"
