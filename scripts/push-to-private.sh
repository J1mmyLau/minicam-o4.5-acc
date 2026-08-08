#!/bin/bash
# =============================================================================
# push-to-private.sh — Push current branch to competition private repo
# =============================================================================
#
#   Remote: Phoenix3334/minicpmo45-ascend-private (ssh.github.com:443)
#   Auth:   ~/.ssh/minicpmo45_ascend_private deploy key
#   Proxy:  agent.baidu.com:8891 (when available; fallback: direct SSH)
#
# Usage:   bash scripts/push-to-private.sh [tag-name]
#          bash scripts/push-to-private.sh checkpoint-20260808-rtf-provenance
#
# =============================================================================

set -euo pipefail

PRIVATE_REMOTE="private"
PRIVATE_SSH_URL="ssh.github.com:Phoenix3334/minicpmo45-ascend-private.git"

# ── Step 0: verify we are in the right repo ──────────────────────────────
if [ ! -d .git ]; then
    echo "ERROR: not in a git repository" >&2
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
echo "=== Current branch: $CURRENT_BRANCH ==="
echo ""
echo "Recent commits:"
git log --oneline -5
echo ""

# ── Step 1: ensure private remote exists ────────────────────────────────
if ! git remote get-url "$PRIVATE_REMOTE" >/dev/null 2>&1; then
    echo "Adding remote '$PRIVATE_REMOTE'..."
    git remote add "$PRIVATE_REMOTE" "$PRIVATE_SSH_URL"
else
    CURRENT_URL=$(git remote get-url "$PRIVATE_REMOTE")
    if [ "$CURRENT_URL" != "$PRIVATE_SSH_URL" ]; then
        echo "Fixing '$PRIVATE_REMOTE' URL..."
        git remote set-url "$PRIVATE_REMOTE" "$PRIVATE_SSH_URL"
    fi
fi

echo "Remote '$PRIVATE_REMOTE': $(git remote get-url "$PRIVATE_REMOTE")"
echo ""

# ── Step 2: check for large files (GitHub rejects >100MB) ──────────────
LARGE_FILES=$(git rev-list --objects HEAD | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | \
    awk '$1=="blob" && $2>50000000 {printf "%s %.1fMB\n", $3, $2/1048576}' | head -5)

if [ -n "$LARGE_FILES" ]; then
    echo "ERROR: Large files in history (GitHub rejects >100MB):" >&2
    echo "$LARGE_FILES" >&2
    echo "" >&2
    echo "Run: bash scripts/strip-large-files.sh" >&2
    exit 1
fi

echo "No large files detected."
echo ""

# ── Step 3: push branch ─────────────────────────────────────────────────
echo "=== Pushing branch '$CURRENT_BRANCH' to '$PRIVATE_REMOTE' ==="
GIT_SSH_COMMAND="ssh -o ConnectTimeout=30 -o ServerAliveInterval=30 -o ServerAliveCountMax=10" \
    git push -u "$PRIVATE_REMOTE" "$CURRENT_BRANCH"
echo "Branch pushed."
echo ""

# ── Step 4: push tag if provided ────────────────────────────────────────
TAG_NAME="${1:-}"
if [ -n "$TAG_NAME" ]; then
    echo "=== Pushing tag '$TAG_NAME' ==="
    GIT_SSH_COMMAND="ssh -o ConnectTimeout=30 -o ServerAliveInterval=30 -o ServerAliveCountMax=10" \
        git push "$PRIVATE_REMOTE" "$TAG_NAME"
    echo "Tag pushed."
else
    echo "No tag provided — skip. Usage: $0 [tag-name]"
fi

echo ""
echo "=== Done ==="
echo "Verify: https://github.com/Phoenix3334/minicpmo45-ascend-private/tree/$CURRENT_BRANCH"
