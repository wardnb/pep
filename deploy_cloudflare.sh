#!/usr/bin/env bash
# Build the static snapshot and deploy it to Cloudflare Pages.
#
# Prerequisites (one-time):
#   1. A Cloudflare API token with the "Cloudflare Pages: Edit" permission.
#      Create at: https://dash.cloudflare.com/profile/api-tokens
#   2. Your Cloudflare Account ID (Dashboard -> right sidebar, or Workers & Pages).
#
# Then:
#   export CLOUDFLARE_API_TOKEN=xxxxxxxx
#   export CLOUDFLARE_ACCOUNT_ID=xxxxxxxx
#   ./deploy_cloudflare.sh
#
# Optional: CF_PROJECT overrides the Pages project name (default: peptide-rater).
set -e
cd "$(dirname "$0")"

PROJECT="${CF_PROJECT:-peptide-rater}"

echo "==> Seeding database and building static snapshot..."
python3 backend/seed.py --reset
python3 backend/build_static.py

echo "==> Deploying ./dist to Cloudflare Pages project '$PROJECT'..."
# --commit-dirty lets a direct-upload deploy proceed without a git commit.
npx --yes wrangler pages deploy dist \
  --project-name "$PROJECT" \
  --commit-dirty=true

echo "==> Done. The URL is printed above (https://$PROJECT.pages.dev)."
