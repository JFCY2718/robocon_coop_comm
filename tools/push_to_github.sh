#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <github_repo_url>"
  echo "Example: $0 git@github.com:YOUR_NAME/robocon_coop_comm.git"
  exit 1
fi

REPO_URL="$1"

if [ ! -d .git ]; then
  git init
fi

git add .
git commit -m "Initial R1/R2 coop communication project" || true
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi
git push -u origin main
