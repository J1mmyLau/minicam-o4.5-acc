#!/bin/bash
# =============================================================================
# strip-large-files.sh — Remove large profiling blobs from git history
# =============================================================================
#
# Only run when 'git push' is rejected with:
#   remote: error: GH001: Large files detected.
#
# Requires: pip install git-filter-repo (auto-installed if missing)
#
# SAFETY: Creates a backup branch 'backup-pre-strip-YYYYMMDD' before
#         rewriting history. Original objects stay in backup branch.
#
# Usage:   bash scripts/strip-large-files.sh
#
# =============================================================================

set -euo pipefail

STAMP=$(date +%Y%m%d)
BACKUP_BRANCH="backup-pre-strip-$STAMP"

# ── Step 0: verify we are in the right repo ──────────────────────────────
if [ ! -d .git ]; then
    echo "ERROR: not in a git repository" >&2
    exit 1
fi

# ── Step 1: check for git-filter-repo ────────────────────────────────────
if ! command -v git-filter-repo &>/dev/null; then
    echo "Installing git-filter-repo..."
    pip install git-filter-repo
fi

# ── Step 2: create backup ───────────────────────────────────────────────
echo "Creating backup: $BACKUP_BRANCH"
git branch "$BACKUP_BRANCH"
echo "Backup created at $BACKUP_BRANCH"
echo ""

# ── Step 3: find large paths to strip ────────────────────────────────────
echo "Finding large files in history..."
LARGE_PATHS=$(git rev-list --objects HEAD | \
    git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | \
    awk '$1=="blob" && $2>50000000 {print $3}' | \
    sed 's|/[^/]*$||' | sort -u)

if [ -z "$LARGE_PATHS" ]; then
    echo "No large files found. Nothing to strip."
    git branch -D "$BACKUP_BRANCH"
    exit 0
fi

echo "Will strip:"
echo "$LARGE_PATHS" | sed 's/^/  /'
echo ""

# ── Step 4: rewrite history ──────────────────────────────────────────────
echo "=== Rewriting history (this may take a minute) ==="

# Build filter-repo args: --path <dir> --invert-paths for each directory
FILTER_ARGS=""
while IFS= read -r path; do
    [ -z "$path" ] && continue
    FILTER_ARGS="$FILTER_ARGS --path '$path' --invert-paths"
done <<< "$LARGE_PATHS"

# Use eval because filter-repo needs literal --path --invert-paths args
eval "git filter-repo $FILTER_ARGS --force"

echo ""
echo "History rewritten."
echo ""

# ── Step 5: re-add remotes (filter-repo removes them) ────────────────────
if ! git remote get-url private >/dev/null 2>&1; then
    git remote add private ssh.github.com:Phoenix3334/minicpmo45-ascend-private.git
    echo "Re-added 'private' remote."
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/tc-mb/llama.cpp-omni.git
    echo "Re-added 'origin' remote."
fi

echo ""
echo "=== Done ==="
echo "Backup: $BACKUP_BRANCH (original history preserved)"
echo ""
echo "Next: bash scripts/push-to-private.sh"
echo ""
echo "WARNING: If these commits were already pushed to another remote,"
echo "         force-push will be required. Only do this on private repo."
