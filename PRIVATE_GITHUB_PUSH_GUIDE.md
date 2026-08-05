# Private GitHub Push Guide — F6 Handoff

> **Target**: `git@github.com:Phoenix3334/minicpmo45-ascend-private.git`
> **Generated**: 2026-08-05
> **Audit status**: PRE-PUSH AUDIT COMPLETE (0 BLOCKING_SECRET, all local gates PASS)

---

## Prerequisites

- SSH key registered with GitHub account Phoenix3334
- Network access to github.com
- This repo at HEAD `33ccda1` (branch `perf/f6-decode-to-speak`)

---

## Quick Push (after network is confirmed)

```bash
# Step 0: Verify connectivity
ssh -T git@github.com

# Step 1: Add private remote
git remote add private git@github.com:Phoenix3334/minicpmo45-ascend-private.git

# Step 2: Push branch (ABSOLUTELY NO --force / -f / --mirror / --all)
git push private perf/f6-decode-to-speak

# Step 3: Push tags
git push private f6-candidate-source-bdd4550
git push private f6-handoff-33ccda1

# Step 4: Verify
git ls-remote private
```

---

## What Is Being Pushed

| Item | Value |
|------|-------|
| **Branch** | `perf/f6-decode-to-speak` |
| **HEAD** | `33ccda1` (chore(gitignore): add .env and .env.* patterns) |
| **Frozen source** | `bdd4550` (ancestor of HEAD, tagged `f6-candidate-source-bdd4550`) |
| **Tag 1** | `f6-candidate-source-bdd4550` → commit `bdd4550` |
| **Tag 2** | `f6-handoff-33ccda1` → commit `33ccda1` |
| **Existing tag** | `f6-timing-instrumentation-pass-20260730` (pre-existing, informational) |

---

## What Is NOT Being Pushed

| Excluded | Why |
|----------|-----|
| Model weights (*.gguf except vocab) | .gitignore (`*.gguf`, `/models/*`) |
| Build artifacts (build/, *.so, *.o) | .gitignore (`/build*`, `*.so`, `*.o`) |
| Tarball archives (*.tar.gz) | .gitignore (`*.tar.gz`) |
| .env files | .gitignore (`.env`, `.env.*`) |
| Binary/profiling data | .gitignore (`*.bin`, `*.log`, `*.gcda`) |
| PyTorch checkpoints | .gitignore (`*.pt`, `*.safetensors`, `pt/`) |
| Demo apps | .gitignore (`apps/`) |
| Node modules | .gitignore (`node_modules`) |

---

## Security Audit Summary

| Check | Result |
|-------|--------|
| Secrets in git history | **CLEAN** — 0 real passwords/tokens/keys |
| AWS keys | **CLEAN** — 0 matches |
| GitHub tokens | **CLEAN** — 0 matches |
| Private key files | **CLEAN** — idea-arch.key is a diagram ZIP, not a crypto key |
| .env files tracked | **CLEAN** — submission/config/server.env is a public template |
| Git credentials in config | **CLEAN** |
| Forbidden binaries tracked | **CLEAN** — only intentional vocab gguf files |
| License | MIT (tracked, valid) |

### BLOCKING_SECRET: 0

---

## What the User Sees After Push

The repo at `Phoenix3334/minicpmo45-ascend-private` will contain:

- Full git history from initial commit through `33ccda1`
- Complete source tree (llama.cpp + omni extensions, frozen at bdd4550)
- All documentation (8 top-level docs, audit/, tracking/, evidence/, competition/, vllm-migration/)
- Submission scripts (`submission/`)
- 2 annotated tags for easy checkout
- No model weights, no binaries, no tarballs, no secrets

---

## Delivery Artifacts (NOT in git — share separately)

These are local files for GitHub Releases or direct transfer:

| File | Size | Description |
|------|------|-------------|
| `f6-candidate-source-bdd4550.tar.gz` | 71 MB | Clean git archive of frozen source |
| `f6-competition-handoff-bdd4550-20260805.tar.gz` | 4.2 MB | Documentation + evidence package |
| `vllm-migration-docs-37dc598-20260805.tar.gz` | 53 KB | vLLM migration documentation |
| `PACKAGE_SHA256SUMS` | — | SHA256 hashes of all 3 tarballs |

---

## Emergency Rollback

If anything goes wrong, the remote repo can be reset. But DO NOT force push without explicit authorization.

To remove the branch from remote (only if necessary):
```bash
git push private --delete perf/f6-decode-to-speak
```

To remove tags from remote (only if necessary):
```bash
git push private --delete f6-candidate-source-bdd4550
git push private --delete f6-handoff-33ccda1
```
