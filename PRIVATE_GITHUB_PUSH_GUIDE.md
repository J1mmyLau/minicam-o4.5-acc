# Private GitHub Push Guide — F6 Handoff

> **Target**: `Phoenix3334/minicpmo45-ascend-private`
> **Generated**: 2026-08-05
> **Audit status**: PRE-PUSH AUDIT COMPLETE (0 BLOCKING_SECRET, all local gates PASS)
> **Network**: HTTPS=PASS, SSH_22=BLOCKED, SSH_443=CONNECTS_BUT_NO_AUTHORIZED_KEY

---

## Network Diagnosis (2026-08-05)

| Check | Result | Detail |
|-------|--------|--------|
| `GITHUB_HTTPS_NETWORK` | **PASS** | `git ls-remote https://github.com/ggml-org/llama.cpp.git` → OK |
| `GITHUB_HTTPS_PUBLIC` | **PASS** | `git ls-remote https://github.com/tc-mb/llama.cpp-omni.git` → OK |
| `GITHUB_SSH_22` | **BLOCKED** | Timeout after 15s |
| `GITHUB_SSH_443` | **NO_AUTH** | Connects to `ssh.github.com:443` but key rejected (Permission denied) |
| `PRIVATE_REPO_HTTPS` | **AUTH_REQUIRED** | `https://github.com/Phoenix3334/minicpmo45-ascend-private.git` → 404 (expected for unauthenticated private repo) |
| `PRIVATE_REPO_SSH_443` | **AUTH_REQUIRED** | SSH connects but key `hidevlab-vscode-plugin` not registered with GitHub |

**Root cause**: The SSH key on this machine (`~/.ssh/id_rsa`, fingerprint `SHA256:2GFTzfmLjaAkocsbFU3fiRjIxk7yoSQnRtaK0ztX93s`) is a VS Code plugin key, NOT registered with the GitHub account `Phoenix3334`. No `gh` CLI, no credential helper with a valid token, no `~/.git-credentials`.

**The machine CAN reach GitHub via HTTPS.** The block is purely authentication for the private repo.

---

## Option A: Add Your SSH Key to This Machine (Recommended)

If you have an SSH key that IS registered with GitHub account Phoenix3334:

```bash
# Copy your key to this machine (outside this conversation)
# Then test:
ssh -T -p 443 git@ssh.github.com

# If successful, push via SSH on port 443:
git remote add private ssh://git@ssh.github.com:443/Phoenix3334/minicpmo45-ascend-private.git
git push private perf/f6-decode-to-speak
git push private f6-candidate-source-bdd4550
git push private f6-handoff-163f1d7
```

## Option B: Set Up HTTPS Token Auth (Outside This Conversation)

```bash
# On this machine, outside this conversation:
git config --global credential.helper store
# Then trigger a git operation to the private repo — you'll be prompted for credentials
# Use a GitHub PAT (classic, with 'repo' scope) as password

# Then push:
git remote add private https://github.com/Phoenix3334/minicpmo45-ascend-private.git
git push private perf/f6-decode-to-speak
git push private f6-candidate-source-bdd4550
git push private f6-handoff-163f1d7
```

## Option C: Push From Your Local Machine

Use the `PRIVATE_GITHUB_PUSH_GUIDE.md` as reference. Push the git repo as-is, then upload tarballs separately as GitHub Releases.

## Option D: Offline Git Bundle (Last Resort)

If no authentication method works from this machine:

```bash
# Create bundle (all commits reachable from HEAD)
git bundle create f6-handoff-163f1d7.bundle HEAD

# Also include the candidate commit explicitly
git bundle create f6-candidate-bdd4550.bundle bdd4550

# Transfer the .bundle file(s) to a machine with GitHub access, then:
git clone f6-handoff-163f1d7.bundle minicpmo45-ascend-private
cd minicpmo45-ascend-private
git remote add origin git@github.com:Phoenix3334/minicpmo45-ascend-private.git
git push -u origin perf/f6-decode-to-speak
git push origin f6-candidate-source-bdd4550
git push origin f6-handoff-163f1d7
```

---

## Current State (Ready to Push)

| Item | Value |
|------|-------|
| **Branch** | `perf/f6-decode-to-speak` |
| **HEAD** | `163f1d7` |
| **Frozen source** | `bdd4550` (ancestor of HEAD) |
| **Tag: candidate** | `f6-candidate-source-bdd4550` → `bdd4550` |
| **Tag: handoff** | `f6-handoff-163f1d7` → `163f1d7` |
| **Security audit** | CLEAN (0 BLOCKING_SECRET) |
| **Worktree** | Clean |

---

## What Must NOT Be Pushed

| Excluded | Mechanism |
|----------|-----------|
| Model weights, build artifacts, tarballs, .env, PyTorch checkpoints | `.gitignore` |
| Secrets, tokens, keys | Verified absent via full audit |

## Constraints (ABSOLUTE)

- ❌ NO `--force` / `-f` / `--mirror` / `--all`
- ❌ NO token in remote URL or scripts
- ❌ NO modifying frozen source `bdd4550`
- ❌ NO pushing to origin (tc-mb/llama.cpp-omni)
