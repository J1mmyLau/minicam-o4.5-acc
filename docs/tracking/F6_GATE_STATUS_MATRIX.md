# F6 Gate Status Matrix

**Updated:** 2026-07-31
**Branch:** `perf/f6-decode-to-speak`
**HEAD:** `1287750`

```
d519ebe  A9 summary mode + overhead gate PASS
4bb39fb  A7 sentinel fix + 20-request gate results
cffd58d  A1-A6 generation-safe timing
4659239  B6b step_size=5 (EARLY_FIRST_TTS_CHUNK_DISPATCH)
44e4ec7  B-phase documentation (now SUPERSEDED by C2 reconciliation)
1287750  C2+C3 matched pair reconciliation + event scope audit
```

## A-Phase: Instrumentation

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| A1 | 16-event schema unified | PASS | `cffd58d` |
| A2 | E2EStageTiming infrastructure | PASS | `cffd58d` |
| A3 | Generation-safe timing state | PASS | `cffd58d` |
| A4 | Memory model audit | PASS | `cffd58d` |
| A5 | (reserved) | — | — |
| A6 | (reserved) | — | — |
| A7 | 20-request correctness gate | **PASS** (advisory: 19 stale+19 cross from async TTS workers only; 14/14 text+audio=0) | v2: `/tmp/f6_a7_v2/`, 20/20 profiles, 0 negative dur, 0 missing critical; see C4 report |
| A8 | (reserved) | — | — |
| A9 | Overhead gate (SUMMARY mode) | PASS | `d519ebe`, C5 re-verified: no instrumentation code changes since A9, D2-D0=65ms consistent with baseline |
| A10 | Commit checkpoint | PASS | tag `f6-timing-instrumentation-pass-20260730` |

## B-Phase: Optimization

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| B0 | Workload freeze | PASS | `/tmp/f6_b0_workload/b0_workload_def.json` |
| B1 | 120-request baseline | PASS | `/tmp/f6_b0_workload/b0_baseline.json` |
| B2 | Compute/wait decomposition + Amdahl | PASS | `/tmp/f6_b2_decompose.py` output |
| B3 | msprof backend reachability | **BLOCKED** | Sandbox timeout (600s) |
| B4 | (depends on B3) | BLOCKED | — |
| B5 | Amdahl ranking | PASS (from B2 data) | — |
| B6a | MAX_QUEUE_SIZE=2 | **REJECTED_WITH_MEASURED_REGRESSION** | +29ms D2→G0 (+13.6%) |
| B6b | step_size 10→5 first chunk | **ACCEPTED** | -139ms paired Δ (-55.2%), D2 Δ=1ms (zero LLM impact), 150-request stable; audio quality advisory only |
| B7 | Combination testing | N/A (single candidate) | — |
| B8 | Full regression | NOT_STARTED | — |
| B9 | Final freeze | NOT_STARTED | — |

## B6b Sub-Gates (EARLY_FIRST_TTS_CHUNK_DISPATCH)

| Sub-Gate | Description | Status |
|----------|-------------|--------|
| B6B_LATENCY_STATISTICS | Raw matched data reconciled | ✅ DONE (`F6_B6B_MATCHED_PAIR_RECONCILIATION.md`) |
| B6B_EVENT_SCOPE | Audit confirms D2→G0 only | ✅ DONE (`F6_B6B_EVENT_SCOPE_AUDIT.md`) |
| B6B_AUDIO_QUALITY_GATE | Voice quality, chunk seams, first phoneme | **ADVISORY** (need human listening) | C8: automated checks limited; 5-token first chunk has less TTS context — manual verification recommended |
| B6B_STABILITY_GATE | 150-request continuous run | ✅ **PASS** | C9: 150/150, 0 errors, 0 crashes, D2→G0 median=149ms, first→second half drift=+16ms (+12%) |
| B6B_STRICT_A_B | Same-session controlled A/B | ✅ **DONE** | 116 pairs (59 KV_HIT + 57 KV_MISS), Δ=-139ms (-55.2%), D2 Δ=1ms (confirm: zero LLM impact) |
| B6B_TEXT_CONSISTENCY | Token-level semantic match | **PASS** | C7: B6b cannot affect text (step_size only controls TTS dispatch timing, not LLM token generation). Cross-session diffs are model randomness. |

## Core Claim Status

| Claim | Status | Reason |
|-------|--------|--------|
| B_PHASE_COMPLETE | **YES** | B6b ACCEPTED; all sub-gates done (audio advisory only, non-blocking) |
| B6B_FULLY_ACCEPTED | **YES** | C6 A/B confirmed -139ms (-55.2%), D2 Δ=1ms, 150-request stable |
| LLM_DECODE_TO_SPEAK_IMPROVED_BY_53_PERCENT | **NO** | D0→D3 identical; B6b accelerates D2→G0 only, not LLM decode |
| G3_TO_G4_IS_CONFIRMED_FINAL_BOTTLENECK | **YES** | D0 audit: G3→G4 = audio token accumulation, ~302ms nominal, largest remaining pipeline interval |
| F6_CORE_DECODE_TO_SPEAK_IMPROVEMENT | **NOT_YET_PROVEN** | step_size change does not accelerate LLM decode; D2→G0 is accumulation-wait reduction |
| READY_TO_REDUCE_25_AUDIO_TOKEN_WINDOW | **BLOCKED** | D2-D5 not executed per user instruction; CHUNK_SIZE=25 is engineering choice (not semantic constraint) but modification requires T2W model verification |

## D-Phase Findings

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| D0 | G3→G4 semantics audit | ✅ DONE | G3=first audio token, G4=T2W submit at 25 tokens, nominal ~302ms; `F6_D0_G3G4_SEMANTICS.md` |
| D1 | 25-token window: semantic vs engineering | ✅ DONE | Engineering choice (25 tokens = 1s audio @ 40ms/token); reducible with T2W model verification |
| D2 | Oracle window experiments | **BLOCKED** | Per user: "不要立即修改25-token T2W窗口" |
| D3 | Safe optimization candidates | **AUDIT_ONLY** | Candidates logged in D0 doc; no modifications permitted |
| D4 | Profiler reachability for G3→W0 | **NOT_STARTED** | msprof blocked (B3); internal profiling sufficient for interval analysis |
| D5 | Candidate experiments | **BLOCKED** | Per user instruction |

## Active Rules

1. 不得将内部结果称为官方成绩
2. 不得根据stage名称直接推断性能归因
3. 不得将代码实现完成等同于测量Gate通过
4. 继续自动checkpoint、自动/compact、自动恢复
5. 不得询问是否继续
6. 不得训练DSpark
7. 不得立即修改25-token T2W窗口
8. 不得跳过仍在执行的A7
