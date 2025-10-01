#!/usr/bin/env bash
# pull.sh - Update local repo with latest changes from origin

set -euo pipefail

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Updating branch: $BRANCH"

# Stash local changes if any
if ! git diff-index --quiet HEAD --; then
  echo "Stashing local changes..."
  git stash push -u -m "Auto-stash before pull.sh run"
fi

# Fetch and fast-forward merge from origin
git fetch origin
git pull --ff-only origin "$BRANCH"

# Reapply stash if it exists
if git stash list | grep -q "Auto-stash before pull.sh run"; then
  echo "Re-applying stashed changes..."
  git stash pop
fi

echo "Repository is now up to date with origin/$BRANCH"

