#!/usr/bin/env bash
set -euo pipefail

# Default commit message includes timestamp if not provided
msg="${1:-"update: $(date +'%Y-%m-%d %H:%M:%S')"}"

# Ensure we’re inside repo
cd "$(git rev-parse --show-toplevel)"

echo "→ Adding changes..."
git add -A

if git diff --cached --quiet; then
  echo "No changes to commit."
else
  echo "→ Committing..."
  git commit -m "$msg"
fi

echo "→ Pulling latest from origin..."
git pull --rebase

echo "→ Pushing to origin..."
git push

echo "✔ Sync complete."

