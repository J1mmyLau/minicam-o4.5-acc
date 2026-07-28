# NEXT ACTION — Operator Profiling Mission

**After /compact:** Continue from `perf/operator-decode-speak`, HEAD `111a48a`.

---

## State Recovery (first 5 actions after /compact)

1. Read `profiles/STATUS.md` — verify current phase (P10: Candidate E)
2. Read `profiles/HANDOFF.md` — verify commit chain, completed items
3. `git log --oneline -5` + `git status --short` — verify HEAD 111a48a, no surprise modifications
4. Confirm clean binary: no diagnostic code in `ggml-cann.cpp` / `aclnn_ops.cpp`
5. Confirm no background runner (`ps aux | grep llama`)

---

## Immediate Task: Candidate E V0 Profiling Audit

### Objective

Profile `aclrtSetDevice` and related runtime overhead. **Read-only counters first, no behavior change.**

### Step 1: Code Audit

- Audit `aclrtSetDevice` call sites in `ggml/src/ggml-cann/ggml-cann.cpp`
- Map: which functions call `aclrtSetDevice`, how many call sites, redundancy pattern
- Identify: `aclrtSynchronizeStream`, `aclrtMemcpy`, `aclrtMemcpyAsync` call sites
- Document: thread model (which threads call SetDevice, are they per-graph or per-op?)

### Step 2: Implement V0 Counters

- Low-overhead: `std::atomic<uint64_t>` counters, no mutex, no per-call timing
- Counters for: `aclrtSetDevice` (total, same-device redundant), `aclrtSynchronizeStream`, `aclrtMemcpy` (direction), graph launch count
- Gate: `GGML_CANN_RUNTIME_DIAG=1` (default OFF, zero cost when OFF)
- Dump at omni_free or on SIGUSR1

### Step 3: Run Single Diagnostic Run

- 1 run with `GGML_CANN_RUNTIME_DIAG=1`, production ngl=8
- Collect: call counts, redundancy rate, breakdown by callsite
- Compute: estimated host time savings if SetDevice caching were implemented

### Step 4: ROI Decision

| Condition | Action |
|-----------|--------|
| Cumulative SetDevice time < 100ms per run | REJECTED — noise |
| Redundancy rate < 50% | REJECTED — already efficient |
| Savings > 500ms AND redundancy > 80% | IMPLEMENT V1 (thread-local cache) |
| Otherwise | Present data, ask user |

### Step 5: If ROI Proven — V1 Thread-Local Cache

- `thread_local` last_device_id, only call `aclrtSetDevice` on change
- Gate: `GGML_CANN_CACHE_DEVICE_CONTEXT=0` (default OFF)
- A/B: 10+ paired runs with kernel timing as primary metric

---

## Candidate E Implementation Constraints (from user)

- ❌ Do NOT modify code based on call counts alone — profile first
- ❌ Do NOT change default behavior without gate
- ✅ V0: counters only (no behavior change)
- ✅ V1: thread-local cache IF ROI proven
- ✅ If cumulative benefit < measurable → REJECTED_WITH_EVIDENCE

---

## Key Reference Files

| File | Content |
|------|---------|
| `ggml/src/ggml-cann/ggml-cann.cpp` | CANN backend, device context, graph compute |
| `profiles/STATUS.md` | Current phase, gate status |
| `profiles/HANDOFF.md` | Commit chain, completed items |
| `docs/experiments/operator-optimization/OP002_RUNTIME_GRAPH_DIAG.md` | OP002 rejection evidence |
| `docs/experiments/operator-optimization/V0_FUSION_VERDICT.md` | V0 fusion A/B result |
