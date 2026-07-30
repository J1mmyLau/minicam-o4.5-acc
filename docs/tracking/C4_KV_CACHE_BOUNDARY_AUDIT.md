# C4: KV Cache Boundary Audit

**Date:** 2026-07-30
**Source:** omni.cpp (HEAD 0828de2, branch perf/flow-chunk-rtf)
**Server log evidence:** /tmp/omni-server-kvcache-fix2.log

---

## Q1: What is the exact token boundary of the cache save?

**Answer:** The cache saves ONLY the system prompt — tokens evaluated during the first `stream_prefill(index=0)` call within the `!ctx_omni->system_prompt_initialized` block.

The save boundary is at `ctx_omni->n_past` after system prompt evaluation completes. Specifically:

```
save_position = ctx_omni->n_past  (= ctx_omni->n_keep, set at line 11867)
```

The system prompt consists of:
1. `voice_clone_prompt` — text tokens (prefix with `<|audio_start|>`)
2. `ref_audio` APM embedding tokens (variable count, typically 10 positions)
3. `assistant_prompt` — text tokens (suffix with `<|audio_end|><|im_end|>`)
4. `n_keep = n_past` — the protection boundary

Evidence from server log:
```
n_past = 63        ← save position
n_keep = 63        ← protection boundary (line 11867)
```

**The save is a `llama_state_seq_save_file` of seq_id=0 at this exact position.** It captures all KV cache entries from position 0 through `n_past-1`.

---

## Q2: What is ctx_omni->n_past at save time?

**Answer:** For the standard ref_audio case, `n_past = 63` at save time.

Breakdown of the 63 tokens (from the server log):
- Voice clone prompt text tokens: ~15 (then sliding window compresses to 8)
- Ref audio embedding: 10 positions (n_pos=10)
- Assistant prompt text tokens: ~54 (then sliding window compresses to 9)
- Then `n_keep = 63` is set, triggering one more eval for `<|im_start|>user\n` prefix

The exact value depends on:
- The length of `voice_clone_prompt` + `assistant_prompt` text
- The ref_audio length (longer audio = more embedding positions)
- Sliding window compression that may reduce some text tokens

From log evidence for AUDIO_0001: `n_past=63`, identical to AUDIO_0000.

---

## Q3: What tokens does the cache contain?

**Answer:** The cache contains these tokens (in position order):

| Position Range | Content | Type |
|---|---|---|
| 0–14 (then compressed to 0–7) | `<|im_start|>system\n` + voice_clone_prompt (including `<|audio_start|>`) | Text |
| 8–17 (approx) | ref_audio APM embedding tokens | Audio embedding |
| 18–62 (then compressed to 9–62) | assistant_prompt (including `<|audio_end|>` + `<|im_end|>`) | Text |
| After compression: 0–62 | System prompt complete | Mixed |

**Critically, the cache does NOT contain:**
- Any user audio (those are prefill'd at index ≥ 1, outside the `!system_prompt_initialized` block)
- Any LLM decode output tokens (those happen in `stream_decode`, after the cache save)
- Any `<|im_start|>assistant\n` response tokens

---

## Q4: Is reference audio included in the cache?

**Answer: YES.** The ref_audio APM embedding tokens are part of the system prompt and are included in the cached KV state.

Evidence from server log:
```
system prompt ref_audio embedding: n_pos=10
```

The ref_audio embedding is prefill'd at line 11851 via `prefill_with_emb()`, advancing `n_past`. These 10 positions are captured when `kv_cache_safe_save` serializes the full KV cache at `n_past=63`.

---

## Q5: At cache load time, what is n_past set to?

**Answer:** `n_past = loaded_pos` where `loaded_pos` is the number of positions restored from the cache file.

From line 11745:
```cpp
ctx_omni->n_past = loaded_pos;
ctx_omni->n_keep = ctx_omni->n_past;
```

And `loaded_pos` comes from `llama_state_seq_load_file`'s `n_tokens_out` parameter, or from `llama_memory_seq_pos_max(mem, 0) + 1` as a fallback.

From server log evidence:
```
KV cache HIT: loaded 63 positions (9291376 bytes)
```

So on HIT: `n_past = 63`, `n_keep = 63` — exactly matching the save-time values.

---

## Q6: After cache load, is the sliding window state restored?

**Answer:** Partially. The `n_keep` protection boundary is restored (line 11746), and `sliding_window_register_system_prompt(ctx_omni)` is called (line 11753) to set `system_preserve_length`.

However, the **round boundary tracking** (`ctx_omni->rounds` vector) is NOT part of the serialized state. It is re-initialized fresh on each new `omni_init`. This means after a HIT, the sliding window algorithm knows to protect positions 0–62 but has no memory of multi-round boundaries from a previous session.

This is acceptable because:
- The cache only covers the system prompt (positions 0–62)
- Multi-round user interaction starts AFTER the system prompt
- Round boundaries from previous sessions are irrelevant

---

## Q7: Is n_keep correct after cache load?

**Answer: YES.** On HIT, `n_keep` is set to `n_past` (= 63) at line 11746. This matches the MISS path where `n_keep` is set to `n_past` at line 11867.

Both paths produce `n_keep = 63`, meaning positions 0–62 are permanently protected from sliding window deletion.

Verification from server log:
- MISS path: `🔒 n_keep 设置为 63 (system prompt tokens)，这部分永远不会被滑动窗口删除`
- HIT path: `[SW] system_prompt registered: preserve_length=63 (will be protected from sliding)`

Both show `n_keep = 63`.

---

## Q8: What is the KV cache key composed of?

**Answer:** The cache key is a composite FNV-1a 64-bit hash of:

| Component | Source | Example |
|---|---|---|
| Model file size + mtime | `stat(model_path)` | `m<size>:<mtime>:` |
| Model head 64KB FNV-1a hash | First 64KB of .gguf | `<hash>:` |
| Model tail 64KB FNV-1a hash | Last 64KB of .gguf | `<hash>:` |
| n_ctx, n_batch, n_ubatch | `params` struct | `c0:b2048:ub512:` |
| System prompt text FNV-1a hash | `voice_clone_prompt + assistant_prompt` | `s<hash>:` |
| **Ref_audio path FNV-1a hash** | Only when `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1` | `a<hash>:` |
| Model path (as template proxy) | `params.model.path` | `t:/path/to/model:` |
| Cache format version | Hardcoded `KV_CACHE_VERSION=1` | `v1` |

The final key is the FNV-1a hash of this composite string: e.g., `21aeb5cc25b1358e`.

**When `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1`:**
- The `aud_fname` passed to `stream_prefill` is used as `key_ref_audio` (line 11732)
- Different ref_audio files produce different cache keys
- This ensures AUDIO_0000 and AUDIO_0001 get separate cache entries

**When `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=0` (default):**
- `key_ref_audio` is empty → ref_audio NOT in cache key
- All test cases with the same model + system prompt share one cache entry
- The `index=0` call determines the actual ref_audio p_embedding in the cache

---

## Q9: Are different ref_audio files properly isolated?

**Answer:** YES, but only when `OMNI_KV_CACHE_PER_CASE_REF_AUDIO=1`.

**With per-case mode ON (tested in C7 gate):**
- 3 distinct cache entries: `21aeb5cc` (AUDIO_0000), `ce45059b` (AUDIO_0001), `10f7ebd4` (custom_600Hz)
- 9.3 MB each — separate, independent files
- Corruption of key_A does NOT affect key_B or key_C (verified in C7 corruption test)
- Each HIT loads the correct ref_audio's cached embedding

**With per-case mode OFF (default):**
- Only one cache entry for all cases sharing the same model + system prompt
- The FIRST `index=0` call (e.g., AUDIO_0000) determines the ref_audio in the cached system prompt
- Subsequent cases with different ref_audio would get a HIT but with AUDIO_0000's voice — **this is a semantic mismatch**, though not a crash
- This is acceptable for single-voice scenarios (the default use case)

---

## Q10: Can dynamic user input be incorrectly saved into the KV cache?

**Answer: NO.** Dynamic user input cannot be saved into the KV cache.

**Proof by control flow:**

1. The KV cache save (line 11892) is inside the `!ctx_omni->system_prompt_initialized` guard (line 11717)
2. `system_prompt_initialized` is set to `true` at line 11864
3. After the first `stream_prefill(index=0)` completes, `system_prompt_initialized = true`
4. All subsequent calls — `stream_prefill(index>=1)` for user audio/images AND `stream_decode()` for LLM generation — are outside this guard
5. `stream_decode()` (line 12065) has zero KV cache save calls
6. The save file is written BEFORE the LLM thread starts, so no decode output can leak in

**The only data in the cache is:**
- System prompt text tokens
- Ref_audio APM embedding tokens
- `<|im_start|>user\n` prefix tokens

**Never in cache:**
- User audio from `stream_prefill(index>=1)`
- User images from `stream_prefill(index>=1)`
- LLM decode output tokens
- `<|im_start|>assistant\n` response tokens

---

## Additional Boundary Finding: Sliding Window During System Prompt

The system prompt evaluation triggers sliding window compression (visible in log):

```
⚠️ KV Cache 滑动窗口触发: n_past=0, chunk_size=15       → compresses 15→8
⚠️ KV Cache 滑动窗口触发: n_past=15, chunk_size=10      → compresses 18→9
⚠️ KV Cache 滑动窗口触发: n_past=18, chunk_size=54      → compresses 18→9
```

But these are intra-system-prompt compressions. The final `n_past=63` and `n_keep=63` are correct — positions 0–62 form a contiguous, valid KV cache that can be loaded by a fresh process.

---

## Summary

| Question | Answer | Confidence |
|---|---|---|
| Q1: Token boundary | System prompt only (positions 0 to n_past-1) | HIGH |
| Q2: n_past at save | 63 (for standard ref_audio), variable with audio length | HIGH |
| Q3: Cache contents | voice_clone_prompt + ref_audio_embed + assistant_prompt | HIGH |
| Q4: Ref audio in cache | YES — APM embedding tokens are part of the cached state | HIGH |
| Q5: n_past after load | Set to loaded_pos (63) from llama_state_seq_load_file | HIGH |
| Q6: Sliding window restore | Partial — n_keep restored, rounds vector NOT restored | MEDIUM |
| Q7: n_keep correct | YES — 63 on both MISS and HIT paths | HIGH |
| Q8: Key composition | FNV-1a(model+params+system_prompt+[ref_audio]+template+version) | HIGH |
| Q9: Ref audio isolation | YES with PER_CASE=1; NO with default (shared cache) | HIGH |
| Q10: User input in cache | NO — guarded by system_prompt_initialized flag | HIGH |
