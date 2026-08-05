# Package Release Report — F6 Handoff Archives

> **Generated**: 2026-08-05T06:18Z
> **Documentation Commit**: 5afde3d
> **Candidate Source Commit**: bdd4550 (frozen, unchanged)

---

## Archive Inventory

| Archive | SHA256 | Entries | Size |
|---------|--------|---------|------|
| `vllm-migration-docs-37dc598-20260805.tar.gz` | `40c0092f65defb11d1d412e1db5195f12cb432935714397ac5a57cd594aaf709` | 14 (10 files + 1 dir + 3 manifests) | 53 KB |
| `f6-competition-handoff-bdd4550-20260805.tar.gz` | `48193f5b765528074eeea92d392ae028be125d5b4ff17a89a431c35b0143c047` | 640 (595 files + 45 dirs) | 4.2 MB |

SHA256SUMS verified: ✅

---

## vllm-migration-docs

| Item | Value |
|------|-------|
| **Package type** | VLLM_EXPERIENCE_MIGRATION_DOCS |
| **Target audience** | vLLM-Omni team |
| **Contents** | 10 markdown docs (migration guide, evidence appendix, component mapping, execution plan V0-V12, risk matrix R26-R40, competition requirements, metric spec, handoff package, experiment templates) |
| **Excluded** | vLLM runtime results, vLLM source, model weights |
| **Status** | `RELEASE_READY` |

---

## f6-competition-handoff

| Item | Value |
|------|-------|
| **Package type** | INTERNAL_COMPETITION_HANDOFF |
| **Target audience** | Judges, reproduction auditors, successor developers, vLLM teammates |
| **Contents** | 8 core docs, 5 audit docs, 7 phase2 docs, 1 phase3 doc, 12 competition docs, 223 f6-s13-closure evidence files, 109 tracking files, 54 experiment reports, 36 submission scripts, 10 vLLM docs, 3 package manifests |
| **Excluded** | profiles/decode-speak/ (368 MB audio), build/ binaries, model weights, official benchmark results, demo video |
| **Status** | `RELEASE_READY` |

---

## Source Delivery

| Method | Status |
|--------|--------|
| git checkout bdd4550 from llama.cpp-omni repo | Primary |
| git bundle (on request) | Alternative |
| Source tarball (on request) | Alternative |

This package does **NOT** contain full candidate source code.

---

## Clean-Room Audit Results

| Check | Result |
|-------|--------|
| Symlinks in archive | 0 (clean) |
| Sensitive tokens/secrets | 0 (clean) |
| Empty files | 11 (.gitkeep × 3 + empty .stdout × 8 — all expected) |
| Shell script syntax (`bash -n`) | All PASS |
| `/workspace/` paths in docs | Present in 20+ historical docs (ORIGINAL_WORKSPACE_PATH — not script dependencies) |
| `/tmp/` paths in docs | Present in reproduction guide + historical references (not hard dependencies) |
| Private paths in submission scripts | check_no_private_paths.py scans for these (tool itself is clean) |

---

## Broken Markdown Links (Expected)

Package renames files (e.g., `F6_README.md` → `core/00_README.md`), so original
inter-document links like `[F6_ARCHITECTURE.md](F6_ARCHITECTURE.md)` will not resolve
in the extracted package. Links within a single file (anchor links) work correctly.
The package README.md serves as the canonical index.

---

## Final Status

```
VLLM_MIGRATION_PACKAGE           = RELEASE_READY
F6_HANDOFF_PACKAGE               = RELEASE_READY
F6_OFFICIAL_SUBMISSION_PACKAGE   = NOT_READY

CANDIDATE_SOURCE_COMMIT          = bdd4550
FINAL_INTERNAL                   = PASS
REPRODUCIBLE_BINARY              = PASS
T6_FROZEN_BINARY_REGRESSION      = PASS (11/11)

CANN_STATIC_CAPABILITY_AUDIT     = PASS
MAIN_LLM_STATIC_PLACEMENT        = PASS
MAIN_LLM_RUNTIME_PLACEMENT       = PARTIAL
MAIN_LLM_CPU_FALLBACK_OBSERVED   = NO
GRAPH_SPLIT_RUNTIME_COUNT        = NOT_MEASURED
STREAM_SYNC_RUNTIME_COST         = NOT_MEASURED
D2H_COST                         = NOT_MEASURED
CPU_PER_CHUNK_CRITICAL_PATH      = TO_MEASURE

OFFICIAL_DAILY_OMNI              = NOT_RUN
OFFICIAL_TTS_SEED                = NOT_RUN
OFFICIAL_VIDEO_MME               = NOT_RUN
OFFICIAL_DEMO_GATE               = NOT_RUN
OFFICIAL_CHUNK_RTF               = NOT_RUN
OFFICIAL_GATES                   = BLOCKED_BY_OFFICIAL_STARTER_KIT
COMPETITION_COMPLETE             = NOT_CLAIMED
```

---

## "official-submission" Name Gate

The name `f6-official-submission-<version>.tar.gz` is reserved for a package that contains:

- [ ] Full candidate source code (or verified git bundle)
- [ ] Official Daily-Omni benchmark results
- [ ] Official TTS-Seed benchmark results
- [ ] Official Video-MME benchmark results
- [ ] Official per-chunk RTF results from official harness
- [ ] Official Demo verification + video
- [ ] Clean-environment reproduction PASS
- [ ] All baseline/candidate symmetry checks PASS

Until all items are checked, this package is named `f6-competition-handoff-*`.

---

## Git Push Security Audit (2026-08-05)

> **Target**: `Phoenix3334/minicpmo45-ascend-private`
> **Push**: **BLOCKED** — private repo requires authentication, none available on this machine.
> **All local audit steps**: COMPLETE.

### Network Diagnosis

| Check | Result |
|-------|--------|
| `GITHUB_HTTPS_NETWORK` | **PASS** — public repos reachable via HTTPS |
| `GITHUB_SSH_22` | **BLOCKED** — timeout |
| `GITHUB_SSH_443` | **CONNECTS** but key `hidevlab-vscode-plugin` not authorized |
| `PRIVATE_REPO_HTTPS` | **AUTH_REQUIRED** — 404 for unauthenticated private repo |
| `PRIVATE_REPO_SSH_443` | **AUTH_REQUIRED** — key not registered with GitHub |

### Audit Results

| Step | Check | Result |
|------|-------|--------|
| 1 | Repo state | PASS — branch perf/f6-decode-to-speak, HEAD 163f1d7, worktree clean |
| 2 | GitHub network | PARTIAL — HTTPS public PASS, SSH/private AUTH_REQUIRED |
| 3a | git history secrets scan | PASS — 0 real secrets |
| 3b | rg working tree secrets | PASS — 0 password/secret/token patterns, 0 AWS keys, 0 GitHub tokens |
| 3c | Private key files | PASS — idea-arch.key is ZIP/JPEG diagram, not crypto key |
| 3c | .env / credential files | PASS — 0 .env files with secrets |
| 4 | .gitignore audit | PASS — .env gap fixed (33ccda1); tarballs/bundles excluded |
| 4 | Tracked binaries | PASS — only 19 intentional vocab gguf files |
| 5 | License | PASS — MIT (tracked, valid) |
| 6 | Git tags | PASS — f6-candidate-source-bdd4550 + f6-handoff-163f1d7 |
| 7-10 | Push | **PRIVATE_REPO_AUTH_REQUIRED** |
| 11 | Doc updates | THIS_FILE + PRIVATE_GITHUB_PUSH_GUIDE.md (4 auth options) |
| 12 | Final output | Below |

### BLOCKING_SECRET Found: 0

### Resolution Paths

See `PRIVATE_GITHUB_PUSH_GUIDE.md` for 4 options:
- **A**: Add authorized SSH key to this machine → push via `ssh.github.com:443`
- **B**: Set up HTTPS PAT credential helper (outside conversation)
- **C**: Push from user's local machine with network + auth
- **D**: Offline `git bundle` → transfer → push from another machine
