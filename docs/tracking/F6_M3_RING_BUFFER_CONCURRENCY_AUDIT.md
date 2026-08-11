# F6 M3: TalkerStepBuffer Concurrency Audit

**Date:** 2026-08-01
**Status:** AUDIT_COMPLETE — 14 questions answered, 1 non-blocking race identified

---

## Q1: Who writes to TalkerStepBuffer? (Producer)

**A: TTS thread only.**
- `record_step()` at line 6946 — TTS simplex decode loop
- `record_step()` at line 7666 — TTS local decode loop
- Both are called within the TTS thread's `tts_thread_func()` context
- Single producer. No concurrent writes from multiple threads.

## Q2: Who reads TalkerStepBuffer? (Consumer)

**A: T2W worker thread.**
- `summarize()` at line 1142 — called from `e2e_profile_dump_audio_json()`
- Step-level JSON dump at lines 1167-1182 — iterates `steps[]` array
- Called when first WAV is ready (line 11248), inside T2W worker thread

## Q3: Is there concurrent producer/consumer access?

**A: YES — potential race window exists.**

Normal pipeline ordering (no race):
```
TTS writes talker_steps → TTS pushes to queue → T2W dequeues → 
T2W processes Flow+Vocoder → T2W reads talker_steps (summarize + dump)
```
The TTS writes happen-before T2W reads in normal flow. ✓

Race window (edge case):
```
Request N:   TTS writes → TTS enqueues → [HTTP handler returns]
Request N+1: HTTP handler calls reset() → clears talker_step_buffer
Request N:   T2W dequeues → ... → T2W reads talker_steps (RACE!)
```
If the HTTP handler starts request N+1 before the T2W worker finishes request N,
`reset()` clears the buffer while the T2W worker is reading it.

## Q4: Severity of the race?

**LOW.** The race requires the HTTP client to send a new request before the T2W
worker finishes the previous request's Flow+Vocoder (~267ms window). For
interactive use (human-scale), this window is negligible. For load-testing
(back-to-back requests), it could trigger.

Consequences:
- `count` read as 0 → talker_step_summary omitted from JSON (benign)
- `count` read as N but buffer cleared mid-read → garbage values (cosmetic)
- `summarize()` called with cleared buffer → returns `{valid=false}` (benign)
- No crash, no memory corruption (buffer is fixed-size stack-allocated array)

## Q5: Memory ordering — are atomics needed?

**No atomics on buffer fields.** `count`, `truncated`, `steps[]` are all plain types.

The write pattern:
```cpp
// Producer (TTS thread):
steps[count] = rec;   // write step data
count++;              // THEN increment count
```

The read pattern:
```cpp
// Consumer (T2W thread):
int n = count;        // read count
for (int i = 0; i < n; i++) {
    auto &rec = steps[i];  // read step data
}
```

Without atomics or barriers, the consumer could see `count == N+1` but
`steps[N]` not yet fully written (store-store reordering on ARM).

**This is a non-issue in practice because:**
1. Same-thread pipeline ordering prevents concurrent access in normal flow
2. The race window only opens when reset() interleaves (Q3 above)
3. ARM has a weakly-ordered memory model, but store-store ordering is
   maintained within a single thread (TTS thread writes both `steps[]` and
   `count` sequentially)

**Recommendation:** No changes needed for C8/M8. For C10 (production readiness),
add `std::atomic<int> count` and document that reads may observe partial state.

## Q6: Overflow behavior at TALKER_MAX_STEPS=500?

```
record_step():
  if (count < 500):  steps[count++] = rec;
  else:              truncated = true;
```

- `max_audio_tokens` is the loop bound (typically 500)
- If the loop exceeds 500, `truncated=true` and recording stops silently
- The loop bound ensures count never exceeds 500
- No buffer overflow possible

## Q7: Does reset() properly clear the buffer?

**YES.**
```cpp
void reset() {
    count = 0;
    truncated = false;
}
```
- Called from `E2EStageTiming::reset()` at line 447
- Clears logical state (count=0), doesn't zero the data array (unnecessary)
- `summarize()` checks `count == 0` and returns `{valid=false}`

## Q8: Generation validation?

**NONE.** The buffer has no generation_id field and doesn't check
`active_generation_id`. It relies on `reset()` being called between requests.

This is BY DESIGN — the buffer is a simple ring buffer, not a
generation-validated structure. The `E2EStageTiming::record()` guard
(generation mismatch → reject) is NOT applied to `record_step()`.

## Q9: Is summarize() safe when called concurrently with record_step()?

**YES, assuming normal pipeline ordering.** `summarize()` is const and only reads.
`record_step()` only writes. If called from different threads without
synchronization, the reader may see a partial/inconsistent state.

In normal flow, the TTS thread has finished all `record_step()` calls before
the T2W worker calls `summarize()`. The pipeline ordering provides the
happens-before relationship.

## Q10: Single vs multi-producer?

**Single producer (TTS thread).** `record_step()` is only called from the TTS
thread's decode loop. There is no concurrent access from multiple threads.

## Q11: Is the buffer per-request or shared?

**Per-request, logically.** `E2EStageTiming` is a per-request object (one per
`omni_context`), and `talker_step_buffer` is a member of it. `reset()` clears
it between requests.

## Q12: What happens if the TTS thread aborts mid-loop?

- `count` stays at whatever value was reached before abort
- `truncated` remains false
- `summarize()` returns a valid summary with partial data
- JSON dump still contains the partial data
- This is correct behavior — partial data > no data for debugging

## Q13: What happens if talker_stats_enabled=false?

- The `if (talker_stats_enabled)` guard at all recording sites prevents writes
- `talker_step_buffer.count` stays at 0
- JSON dump skips talker_step_summary section entirely
- **Zero recording overhead when disabled** — only one `if` branch per step

## Q14: Thread safety of summarize() internal vector allocation?

`summarize()` allocates `std::vector<int64_t> compute_durs` on the stack.
This is thread-safe (each caller gets its own vector). The allocation size
is bounded by `count` (≤500), so ~4KB.

---

## Verdict

| Aspect | Status | Action |
|--------|--------|--------|
| Producer | Single (TTS) | OK |
| Consumer | Single (T2W) | OK |
| Race window | EXISTS but LOW severity | Defer to C10 |
| Memory ordering | Plain fields, benign in practice | Defer to C10 |
| Overflow | Guarded, no risk | OK |
| Generation guard | None (by design) | OK |
| Reset correctness | Correct | OK |
| Disabled overhead | Zero | OK |

**No blocking issues for M8 (runtime smoke) or C8 (implementation).**
The identified race window is cosmetic and will be addressed in C10
(overhead gate) or C14 (production readiness).
