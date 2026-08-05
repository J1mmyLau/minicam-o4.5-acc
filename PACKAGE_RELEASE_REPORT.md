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

> **Target**: `git@github.com:Phoenix3334/minicpmo45-ascend-private.git`
> **Push blocked**: No GitHub network connectivity from air-gapped CANN environment.
> **All audit steps that run locally**: COMPLETE.

### Audit Results

| Step | Check | Result |
|------|-------|--------|
| 1 | Repo state | PASS — branch perf/f6-decode-to-speak, HEAD 33ccda1, worktree clean |
| 2 | GitHub auth | BLOCKED_BY_NETWORK — no external connectivity from CANN sandbox |
| 3a | git history secrets scan | PASS — 0 real secrets; all hits are technical terms in documentation (token/key in TTS/NLP context) |
| 3b | rg working tree secrets | PASS — 0 password/secret/token[:=]"value" patterns, 0 AWS keys, 0 GitHub tokens |
| 3c | Private key files | PASS — idea-arch.key is a ZIP/JPEG diagram file, not a crypto key |
| 3c | .env / credential files | PASS — 0 .env files, 0 credentials.json, 0 service-account files |
| 4 | .gitignore audit | PASS (FIXED) — .env/.env.* added; tarballs/bundles/sha256 excluded; models/ build/ *.gguf covered |
| 4 | Tracked binaries check | PASS — only intentional: 19 ggml-vocab-*.gguf (model vocabulary files, not weights) |
| 5 | License | PASS — MIT License (tracked, valid) |
| 6 | Git tags | PASS (2 tags created) — f6-candidate-source-bdd4550 (on bdd4550), f6-handoff-33ccda1 (on 33ccda1) |
| 7-10 | Push + remote verify | NOT_RUN — blocked by network |
| 11 | Doc updates | THIS_FILE + PRIVATE_GITHUB_PUSH_GUIDE.md |
| 12 | Final output | Below |

### BLOCKING_SECRET Found: 0

No secrets, passwords, API keys, tokens, private keys, AWS credentials, GitHub tokens, or environment files with secrets were found in the git history or working tree.

### Pre-Push Checklist (for when network is available)

```bash
# 1. Verify remote exists
git ls-remote git@github.com:Phoenix3334/minicpmo45-ascend-private.git

# 2. Push branch (NO force — absolute prohibition)
git push git@github.com:Phoenix3334/minicpmo45-ascend-private.git perf/f6-decode-to-speak

# 3. Push tags (only these 2)
git push git@github.com:Phoenix3334/minicpmo45-ascend-private.git f6-candidate-source-bdd4550
git push git@github.com:Phoenix3334/minicpmo45-ascend-private.git f6-handoff-33ccda1

# 4. Verify remote
git ls-remote git@github.com:Phoenix3334/minicpmo45-ascend-private.git
```
