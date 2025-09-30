#!/usr/bin/env bash
# git-clean-branches.sh
# List/delete merged branches (local and remote) with safety rails and options.
# Bash 4.2+ compatible.

set -euo pipefail

# Defaults
REMOTE="${REMOTE:-origin}"
BASE="${BASE:-main}"            # baseline branch to compare "merged into"
PROTECT_DEFAULTS="main master develop ${BASE}"
YES=0
DRY_RUN=0
FORCE=0
INCLUDE_UNMERGED=0
PRUNE=0

usage() {
  cat <<'USAGE'
Usage: git-clean-branches.sh [options]

Options:
  -r, --remote <name>     Remote name (default: origin)
  -b, --base <branch>     Baseline branch to check merges into (default: main)
  -y, --yes               Non-interactive: delete without prompting
  -n, --dry-run           Show what would happen; do not delete
  -f, --force             Force delete local branches (-D) even if not merged
  -u, --include-unmerged  Offer to delete local branches not merged into BASE
  -p, --prune             Also prune remote-tracking refs (git remote prune)
  -h, --help              Show this help

Env overrides:
  REMOTE, BASE

Examples:
  ./git-clean-branches.sh
  ./git-clean-branches.sh -b develop -r upstream
  ./git-clean-branches.sh -y -n       # non-interactive dry-run
USAGE
}

say()  { printf '%s\n' "$*" >&2; }
die()  { say "ERROR: $*"; exit 1; }
ask()  { local q="$1"; read -r -p "$q [y/N] " ans || true; [[ "$ans" =~ ^[Yy]$ ]]; }

# Parse args
while (( $# )); do
  case "$1" in
    -r|--remote) REMOTE="${2:-}"; shift 2 ;;
    -b|--base)   BASE="${2:-}";   shift 2 ;;
    -y|--yes)    YES=1; shift ;;
    -n|--dry-run)DRY_RUN=1; shift ;;
    -f|--force)  FORCE=1; shift ;;
    -u|--include-unmerged) INCLUDE_UNMERGED=1; shift ;;
    -p|--prune)  PRUNE=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) usage; die "Unknown option: $1" ;;
  esac
done

# Preconditions
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Not inside a Git repository."
git fetch --all --prune --quiet || true

# Resolve baseline
if ! git show-ref --verify --quiet "refs/heads/${BASE}"; then
  # Try remote branch and create a local tracking branch name only for comparison
  if git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BASE}"; then
    say "Info: local ${BASE} missing; will compare merges against ${REMOTE}/${BASE}"
  else
    die "Baseline ${BASE} not found locally or on ${REMOTE}."
  fi
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
protect=($PROTECT_DEFAULTS "$current_branch")
# Deduplicate protect list
declare -A seen=()
PROTECT=()
for b in "${protect[@]}"; do
  [[ -n "${seen[$b]:-}" ]] || { PROTECT+=("$b"); seen[$b]=1; }
done

is_protected() {
  local b="$1"
  for p in "${PROTECT[@]}"; do
    [[ "$b" == "$p" ]] && return 0
  done
  return 1
}

# Helper: delete local branch
del_local() {
  local b="$1"
  if (( DRY_RUN )); then
    say "[dry-run] git branch $([ $FORCE -eq 1 ] && echo -D || echo -d) $b"
  else
    git branch $([ $FORCE -eq 1 ] && echo -D || echo -d) "$b"
  fi
}

# Helper: delete remote branch
del_remote() {
  local rb="$1"   # short branch name (without remote/)
  if (( DRY_RUN )); then
    say "[dry-run] git push ${REMOTE} --delete ${rb}"
  else
    git push "${REMOTE}" --delete "$rb"
  fi
}

# Determine baseline ref to compare merges
BASE_REF="refs/heads/${BASE}"
if ! git show-ref --verify --quiet "$BASE_REF"; then
  BASE_REF="refs/remotes/${REMOTE}/${BASE}"
fi

say "Remote: ${REMOTE}"
say "Baseline: ${BASE_REF#refs/}"
say "Protected: ${PROTECT[*]}"
say

# 1) Local branches fully merged into BASE
say "Scanning local merged branches..."
mapfile -t merged_local < <(git branch --format='%(refname:short)' --merged "$BASE_REF" | sed 's/^ *//;s/ *$//' | grep -v '^\*$' || true)
# Filter protected
keep_local=()
cand_local=()
for b in "${merged_local[@]}"; do
  if is_protected "$b"; then
    keep_local+=("$b")
  else
    cand_local+=("$b")
  fi
done

if ((${#cand_local[@]})); then
  say "Merged locally into ${BASE}:"
  for b in "${cand_local[@]}"; do say "  - $b"; done
  if (( YES )) || ask "Delete these local branches?"; then
    for b in "${cand_local[@]}"; do del_local "$b"; done
  fi
else
  say "No local branches fully merged into ${BASE} (excluding protected)."
fi
say

# 2) Optionally include local branches not merged (dangerous unless you force)
if (( INCLUDE_UNMERGED )); then
  say "Scanning local NOT-merged branches (may be dangerous)..."
  mapfile -t not_merged < <(git branch --format='%(refname:short)' --no-merged "$BASE_REF" || true)
  nm_filtered=()
  for b in "${not_merged[@]}"; do
    is_protected "$b" || nm_filtered+=("$b")
  done
  if ((${#nm_filtered[@]})); then
    say "Not merged into ${BASE}:"
    for b in "${nm_filtered[@]}"; do say "  - $b"; done
    if (( YES )) || ask "Force delete these local NOT-merged branches?"; then
      FORCE=1
      for b in "${nm_filtered[@]}"; do del_local "$b"; done
    fi
  else
    say "No deletable NOT-merged local branches."
  fi
  say
fi

# 3) Remote branches merged into BASE on the remote
say "Scanning remote merged branches on ${REMOTE}..."
# Use remote-merged against remote base for accuracy
remote_base="refs/remotes/${REMOTE}/${BASE}"
mapfile -t merged_remote < <(git branch -r --merged "$remote_base" --format='%(refname:short)' | sed 's/^.*\///' | sort -u || true)
# Filter protected and skip HEAD symbolic
cand_remote=()
for b in "${merged_remote[@]}"; do
  [[ "$b" == "HEAD" ]] && continue
  is_protected "$b" || cand_remote+=("$b")
done

if ((${#cand_remote[@]})); then
  say "Merged on ${REMOTE} into ${BASE}:"
  for b in "${cand_remote[@]}"; do say "  - $b"; done
  if (( YES )) || ask "Delete these remote branches from ${REMOTE}?"; then
    for b in "${cand_remote[@]}"; do del_remote "$b"; done
  fi
else
  say "No remote branches fully merged into ${BASE} (excluding protected)."
fi
say

# 4) Optionally prune stale remote-tracking refs
if (( PRUNE )); then
  if (( DRY_RUN )); then
    say "[dry-run] git remote prune ${REMOTE}"
  else
    say "Pruning remote-tracking refs for ${REMOTE}..."
    git remote prune "${REMOTE}" || true
  fi
fi

say "Done."

