#include "ggml.h"
#include "llama.h"
#include "tts-condition-graph.h"

#include <thread>
#include <memory>
#include <vector>
#include <string>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <functional>
#include <atomic>

// Windows compatibility: pid_t is not defined on MSVC
#ifdef _WIN32
    typedef int pid_t;
#endif

struct vision_ctx;
struct audition_ctx;
struct audition_audio_f32;

// Forward declaration for C++ Token2Wav
namespace omni {
namespace flow {
class Token2WavSession;
}
}

// =======================================================================
// F6 A1: File-scope GLOBAL atomics in omni.cpp — NOT context-scoped.
// These are declared extern so the server instrumentation can read them
// while still reporting them as GLOBAL_* to prevent misattribution.
// =======================================================================
extern std::atomic<bool> prefill_done;
extern std::atomic<bool> t2w_thread_running;

// 🔧 [Duplex Pipeline] 仅在 duplex_mode=true 时分配；
// 定义在 omni.cpp 的 "===== DUPLEX PIPELINE (Stage 1) =====" 区域，
// omni_context 只持有指针，simplex 路径不受影响。
struct DuplexPipeline;

// 定义在 omni.cpp 的 "===== DUPLEX SESSION (high-level) =====" 区域。
// 封装了 prefill_worker / decode_worker 两条调度线程，
// 让外部只需要 push_frame / wait_next_frame，无需知道 stream_prefill/stream_decode
// 的"index 语义"和并发约束。
struct DuplexSession;

//
// omni ctx
//
struct omni_embed {
    float * embed;
    int n_pos;
};
struct omni_embeds{
    // 🔧 [高清模式] vision_embed 改为二维 vector
    // vision_embed[0] = overview embed (64 tokens * hidden_size)
    // vision_embed[1..n] = slice embeds (各 64 tokens * hidden_size)
    std::vector<std::vector<float>> vision_embed;
    std::vector<float> audio_embed;
    // 用户文本片段（与 audio/image 同为一种 modality 的载体）。
    // 非空时，LLM 线程会用 eval_string 将其作为 user-turn 的一部分投入 KV cache，
    // 不会自动包裹任何 role/special token。
    std::string user_text;
    int index = 0;
    int end_flag = false;
};

struct LLMThreadInfo {
    int MAX_QUEUE_SIZE;
    std::queue<omni_embeds*> queue;
    std::mutex mtx;
    std::condition_variable cv;
    std::chrono::steady_clock::time_point start;
    std::chrono::steady_clock::time_point end;

    LLMThreadInfo(int maxQueueSize) : MAX_QUEUE_SIZE(maxQueueSize) {}
};

// ============================================================================
// P7.3 T2W Drain State Machine
// ============================================================================

// T2W worker lifecycle states
enum T2WDrainState {
    T2W_DRAIN_IDLE = 0,           // No active request
    T2W_DRAIN_RUNNING = 1,        // Processing audio tokens
    T2W_DRAIN_EOS_SIGNALED = 2,   // EOS received, worker draining
    T2W_DRAIN_COMPLETE = 3,       // All output produced, drain finished
    T2W_DRAIN_FAILED = 4,         // Error during processing/drain
};

// Terminal output classification for each request
// Distinguishes "expected no-audio" from silent failures
enum T2WTerminalOutput {
    T2W_TERMINAL_UNKNOWN        = 0,
    T2W_AUDIO_SUCCESS           = 1,  // ≥1 WAV produced
    T2W_VALID_NO_SPEECH         = 2,  // LLM legitimately produced no audio tokens
    T2W_OUTPUT_BLOCKED          = 3,  // WAV write failed (disk full, permissions, etc.)
    T2W_DRAIN_TIMEOUT           = 4,  // Drain did not complete within timeout
    T2W_PIPELINE_FAILURE        = 5,  // feed_window() failed repeatedly
    T2W_GENERATION_FAILURE      = 6,  // Upstream failure (LLM/TTS did not produce)
};

// =======================================================================
// F6 A5: Context lifecycle state machine — generation-based request isolation.
// All cross-request CV predicates MUST check generation, not global bools.
// =======================================================================
enum OmniContextState {
    CTX_STATE_REUSABLE     = 0,  // Idle, ready for next request
    CTX_STATE_ACTIVE       = 1,  // Request in progress (stream_decode running)
    CTX_STATE_DRAINING     = 2,  // T2W drain in progress (outside stream_decode)
    CTX_STATE_NOT_REUSABLE = 3,  // Drain failed or critical error — reject next request
};

// F6 R10: Request state machine — tracks each HTTP request through its lifecycle.
// Separate from OmniContextState (which tracks the omni_context reuse lifecycle).
// Valid transitions:
//   IDLE → VALIDATING → DECODING → TTS_PENDING → DRAINING → RESPONDING → IDLE
//   any non-IDLE state → ERROR → IDLE
enum OmniRequestState {
    REQ_IDLE        = 0,  // No active request
    REQ_VALIDATING  = 1,  // Request received, validating input / context guard
    REQ_DECODING    = 2,  // stream_decode in progress (LLM generating tokens)
    REQ_TTS_PENDING = 3,  // LLM done, TTS producing audio, waiting for is_final
    REQ_DRAINING    = 4,  // T2W drain in progress (waiting for worker to dequeue is_final)
    REQ_RESPONDING  = 5,  // Drain complete, building HTTP response
    REQ_ERROR       = 6,  // Error state — returning error response, then → IDLE
};

// Human-readable names for request state diagnostic logging
static inline const char * req_state_name(OmniRequestState s) {
    switch (s) {
        case REQ_IDLE:        return "IDLE";
        case REQ_VALIDATING:  return "VALIDATING";
        case REQ_DECODING:    return "DECODING";
        case REQ_TTS_PENDING: return "TTS_PENDING";
        case REQ_DRAINING:    return "DRAINING";
        case REQ_RESPONDING:  return "RESPONDING";
        case REQ_ERROR:       return "ERROR";
        default:              return "UNKNOWN";
    }
}

struct E2EStageTiming;  // forward decl for T2WOut::profile_handle (F6 C8)

struct T2WOut {
    std::vector<llama_token> audio_tokens;  // Audio token IDs (25 tokens per chunk)
    bool is_final = false;  // Whether this is the final chunk (turn end)
    bool is_chunk_end = false;  // Whether this is the end of a TTS chunk (flush buffer, but not final)
    int round_idx = -1;  // 🔧 [修复目录同步] 轮次索引，由 TTS 线程设置，T2W 线程使用此值确定输出目录
    uint32_t generation_id = 0;  // F6 W5: generation at TTS submit time for correct W0 attribution
    int request_index = 0;  // F6 W5: request_index at submit time for audio profile file naming
    E2EStageTiming *profile_handle = nullptr;  // F6 C8: request-scoped profile for Flow/Vocoder
    std::chrono::steady_clock::time_point enqueue_time = std::chrono::steady_clock::now();
};

struct T2WThreadInfo {
    int MAX_QUEUE_SIZE;
    std::queue<T2WOut*> queue;
    std::mutex mtx;
    std::condition_variable cv;
    std::chrono::steady_clock::time_point start;
    std::chrono::steady_clock::time_point end;

    // ========================================================================
    // P7.3 Drain State Machine — per-request lifecycle tracking
    // ========================================================================

    // Worker drain state (written by T2W worker, read by main thread)
    std::atomic<int> drain_state{T2W_DRAIN_IDLE};

    // EOS signal from main thread → T2W worker
    std::atomic<bool> eos_received{false};

    // Set by worker after is_final fully processed and all WAVs written
    std::atomic<bool> is_final_processed{false};

    // WAV files written for current request (resets per round)
    std::atomic<int> wav_count{0};

    // Terminal output classification (set after drain)
    std::atomic<int> terminal_output{T2W_TERMINAL_UNKNOWN};

    // Number of feed_window failures in this request
    std::atomic<int> feed_window_errors{0};

    // CV for main thread to wait on drain completion
    std::mutex drain_mtx;
    std::condition_variable drain_cv;

    // F6 A1: atomic counters for lock-free queue depth readout
    // These replace unsafe queue.size() calls in instrumentation paths.
    std::atomic<size_t> queued_t2w_task_count{0};   // items waiting in queue for T2W worker (global)
    std::atomic<size_t> active_t2w_task_count{0};   // items currently being processed (legacy: 0 or 1)

    // ========================================================================
    // F6 A6: Generation-scoped T2W drain protocol (R13: per-generation active)
    //
    // Drain completion for generation N requires:
    //   1. tts_producer_done_generation >= N  (no more tasks will be enqueued)
    //   2. queued_t2w_task_count == 0          (all items dequeued — global,
    //      safe under octx_mutex serialization; per-gen TODO)
    //   3. active_t2w_generation == 0          (worker idle)
    //      OR active_t2w_generation > N        (worker processing LATER gen;
    //      gen N is fully done — do NOT block)
    //   4. final_processed_generation >= N     (is_final fully processed)
    //
    // R13 CORRECTION: active_t2w_task_count (global 0/1) is replaced by
    // active_t2w_generation (per-generation) for drain predicates.
    // active_t2w_task_count is retained for backwards-compat diagnostics only.
    //
    // The heuristic timeout is a SAFETY NET only — the drain predicate above
    // determines actual completion.  Expanding the timeout to "fix" a drain
    // failure is a category error; the drain must satisfy the state predicate.
    // ========================================================================

    // F6 R13: Per-generation active tracking.
    // Set to the maximum generation ID of tasks currently being processed
    // by the T2W worker, or 0 if the worker is idle.
    // Drain predicate for gen N: active_t2w_generation == 0 (worker idle)
    // OR active_t2w_generation > N (worker busy with a later gen).
    // Only block when 0 < active_t2w_generation <= N (worker still on gen N
    // or earlier — gen N not yet fully done).
    std::atomic<uint32_t> active_t2w_generation{0};

    // Set by TTS thread when all text chunks for this generation (including the
    // is_final marker) have been converted to T2W tasks and enqueued.
    std::atomic<uint32_t> tts_producer_done_generation{0};

    // F6 R12: Authoritative completion — set by T2W worker ONLY after the
    // is_final task for this generation has been fully processed:
    //   Flow complete → Vocoder complete → WAV written → bookkeeping done.
    // This is the ONLY field the drain predicate trusts for "is this gen done?".
    // It MUST NOT be set at dequeue time (see final_dequeued_generation below).
    std::atomic<uint32_t> final_processed_generation{0};

    // F6 R12: Diagnostic counter — set at DEQUEUE time when the worker pops
    // the is_final item from the queue.  Exists purely for observability;
    // NEVER used in drain/completion predicates.
    std::atomic<uint32_t> final_dequeued_generation{0};

    // F6 R12: Per-generation item accounting (monotonically increasing).
    // Invariant: enqueue_count == completion_count + cancelled_count.
    // Used to detect leaks and cross-generation contamination.
    std::atomic<uint32_t> generation_enqueue_count{0};   // items TTS has enqueued
    std::atomic<uint32_t> generation_dequeue_count{0};   // items worker has dequeued
    std::atomic<uint32_t> generation_complete_count{0};  // items worker has finished processing
    std::atomic<uint32_t> generation_final_enqueued{0};  // gen of last is_final enqueued by TTS
    std::atomic<uint32_t> generation_final_dequeued{0};  // gen of last is_final dequeued by worker
    std::atomic<uint32_t> generation_final_completed{0}; // gen of last is_final fully processed

    // Set when the is_final task for this generation is enqueued (diagnostic).
    std::atomic<uint32_t> final_enqueued_generation{0};

    // F6 R12: Polling overhead instrumentation.
    // drain_notify_wakes: count of wait_for returns from drain_cv.notify_one()
    // drain_poll_wakes:   count of wait_for returns from timeout expiry (500ms polls)
    // A healthy system should be >90% notify-driven; excessive poll wakes indicate
    // lost notifications or predicate churn.
    std::atomic<uint32_t> drain_notify_wake_count{0};
    std::atomic<uint32_t> drain_poll_wake_count{0};
    // Timestamp (ns) of the last drain predicate satisfaction.
    std::atomic<uint64_t> drain_predicate_satisfied_ns{0};
    // Latency (ns) from predicate satisfaction to wait_for return.
    std::atomic<uint64_t> drain_wake_latency_ns{0};

    T2WThreadInfo(int maxQueueSize) : MAX_QUEUE_SIZE(maxQueueSize) {}
};

// Projector Semantic: 2-layer MLP (LLM hidden states -> TTS embedding)
// forward(x): relu(linear1(x)) -> linear2
// ==================== 滑动窗口配置 ====================
// 🔧 [#39] 基于 Python stream_decoder.py 的 DuplexWindowConfig
struct SlidingWindowConfig {
    // 滑窗模式: "off" / "basic" / "context"
    // - "off": 禁用滑窗
    // - "basic": 基础滑窗（按 cache 长度触发）
    // - "context": 带 context 的滑窗（保留生成文本到 previous）
    std::string mode = "off";
    
    // 基础滑窗参数
    int high_water_tokens = 4000;  // 高水位线：超过此值触发滑窗
    int low_water_tokens = 3500;   // 低水位线：滑窗后保留到此值
    
    // RoPE 参数
    float rope_theta = 10000.0f;   // RoPE base frequency
};

// Unit 历史记录条目
struct UnitEntry {
    int unit_id = -1;              // Unit ID
    int length = 0;                // 该 unit 在 cache 中的长度（tokens 数）
    std::string type;              // 类型: "audio" / "video" / "omni" / "system" / "response"
    std::vector<llama_token> generated_tokens;  // 生成的 tokens
    bool is_listen = false;        // 是否是 listen 状态
    // 🔧 [turn 级滑窗] 该 unit 所属 turn 的 id
    // 一个 turn = 一轮完整的 [用户输入 prefill + 模型 response] 序列
    // 同一 turn 内的 prefill unit 和 response unit 共享同一个 turn_id，
    // turn 结束（TURN_EOS / ended_with_listen 等）时 current_turn_id++，
    // 滑窗时优先把整个最早的已完成 turn 一次性丢掉。
    int turn_id = 0;
};

struct projector_hparams {
    int32_t in_dim  = 4096;  // 输入维度 (LLM hidden size)
    int32_t out_dim = 768;   // 输出维度 (TTS embedding size)
};

struct projector_layer {
    struct ggml_tensor * linear1_weight = nullptr;  // [in_dim, out_dim]
    struct ggml_tensor * linear1_bias   = nullptr;  // [out_dim]
    struct ggml_tensor * linear2_weight = nullptr;  // [out_dim, out_dim]
    struct ggml_tensor * linear2_bias   = nullptr;  // [out_dim]
};

struct projector_model {
    projector_hparams hparams;
    projector_layer layer;
    
    struct ggml_context * ctx_w = nullptr;
    ggml_backend_buffer_t buf_w = nullptr;
    ggml_backend_t backend = nullptr;
    ggml_backend_buffer_type_t buf_type = nullptr;
    bool initialized = false;
};

// ============================================================================
// Audio output callback type
// Called by T2W threads when a chunk of audio is generated.
// samples: float32 PCM, caller retains ownership (copy if you need to keep it)
// n_samples: number of float32 values
// sample_rate: sample rate of the audio (e.g. 24000 for Python T2W)
// is_final: true if this is the last chunk of the current generation
// ============================================================================
using audio_output_cb_t = std::function<void(const float * samples, int n_samples, int sample_rate, bool is_final)>;

// ============================================================================
// E2E Stage Profiler — lightweight monotonic-clock timestamps
// Controlled by OMNI_E2E_PROFILE=1 (default off, zero overhead)
// Timestamps use std::chrono::steady_clock (monotonic, cross-thread safe)
// ============================================================================
enum E2EStage : int {
    STAGE_request_received = 0,
    STAGE_prompt_processing_start,
    STAGE_llm_first_token,
    STAGE_speak_token,
    STAGE_talker_start,
    STAGE_talker_first_audio_token,
    STAGE_talker_token_28,
    STAGE_t2w_submit,
    STAGE_t2w_dequeue,
    STAGE_flow_start,
    STAGE_flow_end,
    STAGE_vocoder_start,
    STAGE_vocoder_end,
    STAGE_wav_ready,
    STAGE_client_first_audio,
    STAGE_request_done,
    // F6: decode→first-speak instrumentation (S9)
    STAGE_decode_loop_begin,           // 16 — D0: decode loop begins after prefill complete
    STAGE_llm_first_decode_step,       // 17 — D1: first autoregressive llama_decode call
    STAGE_tts_wake,                    // 18 — G0: TTS thread wakes from cv.wait
    STAGE_tts_first_decode,            // 19 — G2: first TTS llama_decode call
    // F6 C8: request-scoped Flow/Vocoder decomposition
    STAGE_t2w_preprocess_end,          // 20 — Q2: T2W preprocessing completed, Flow input ready
    STAGE_COUNT
};

// ============================================================================
// F6 Phase 3 (P9): Talker Per-Step Instrumentation
// ============================================================================
// Low-overhead ring buffer for recording per-step Talker decode statistics.
// All fields are non-atomic — accessed only by the TTS thread.
// Enabled via F6_PHASE3_TALKER_STATS=1 (default off, zero overhead).

#define TALKER_MAX_STEPS 500  // matches max_audio_tokens

struct TalkerStepRecord {
    int16_t  step_index;              // 0-based step within current chunk
    int64_t  step_start_ns;           // absolute clock (steady_clock epoch)
    int64_t  step_compute_end_ns;     // after llama_decode returns
    int64_t  step_sample_end_ns;      // after sampling
    int32_t  sampled_token_id;        // absolute audio token ID
    int16_t  token_type;              // 0=audio, 1=EOS, 2=text_eos
    int16_t  is_audio_token;          // 1 if this step produced an audio token
    int16_t  audio_token_count_before; // accumulated before this step
    int16_t  audio_token_count_after;  // accumulated after this step
    int32_t  backend_cpu_op_count;     // CPU backend ops (placeholder)
    int32_t  backend_cann_op_count;    // CANN backend ops (placeholder)
    int16_t  allocation_count;         // allocations this step (placeholder)
    int32_t  allocation_bytes;         // bytes allocated (placeholder)
    int64_t  stream_sync_ns;           // time in stream synchronize
    int64_t  queue_wait_ns;            // time waiting for queue/condition
};

struct TalkerStepSummary {
    int     steps_before_first_audio_token;   // G3 step index (0-based)
    int     steps_G3_to_threshold;            // G3 → A1 (25-token accumulation)
    int64_t first_step_ns;                    // step 0 compute duration
    int64_t steady_step_median_ns;            // p50 of steps 1..N compute
    int64_t steady_step_p95_ns;               // p95 of steps 1..N compute
    int64_t total_talker_compute_ns;          // sum of all step compute
    int64_t total_sampling_ns;                // sum of all sampling durations
    int64_t total_sync_ns;                    // sum of stream sync
    int64_t total_allocation_ns;              // sum of allocation overhead
    int64_t total_wait_ns;                    // sum of queue/CV wait
    int     total_steps;
    int     total_audio_tokens;
    int     total_cpu_ops;
    int     total_cann_ops;
    int     total_allocations;
    int64_t total_allocation_bytes;
    bool    truncated;                        // true if > TALKER_MAX_STEPS
    bool    valid;                            // false if no steps recorded
};

struct TalkerStepBuffer {
    TalkerStepRecord steps[TALKER_MAX_STEPS];
    int count = 0;
    bool truncated = false;
    mutable std::atomic<uint32_t> active_generation{0};
    mutable std::atomic<bool>     finalized{false};
    mutable std::atomic<uint32_t> late_write_rejected{0};
    mutable std::atomic<uint32_t> write_after_finalize{0};
    mutable std::atomic<uint32_t> invalid_generation_write{0};

    bool record_step(const TalkerStepRecord &rec, uint32_t generation) {
        if (finalized.load(std::memory_order_acquire)) {
            write_after_finalize.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        uint32_t current_gen = active_generation.load(std::memory_order_acquire);
        if (generation != current_gen) {
            if (generation < current_gen)
                late_write_rejected.fetch_add(1, std::memory_order_relaxed);
            else
                invalid_generation_write.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        if (count < TALKER_MAX_STEPS) { steps[count++] = rec; }
        else { truncated = true; }
        return true;
    }

    void record_step_unchecked(const TalkerStepRecord &rec) {
        uint32_t gen = active_generation.load(std::memory_order_acquire);
        (void)record_step(rec, gen);
    }

    void reset() {
        active_generation.fetch_add(1, std::memory_order_release);
        finalized.store(false, std::memory_order_relaxed);
        count = 0;
        truncated = false;
    }

    void finalize() const {
        finalized.store(true, std::memory_order_release);
    }

    uint32_t capture_generation() const {
        return active_generation.load(std::memory_order_acquire);
    }

    TalkerStepSummary summarize() const;
};

// Dump mode: controls per-request JSON output vs aggregate-only
enum E2EDumpMode : int {
    E2E_DUMP_DISABLED = 0,  // No timing, zero overhead
    E2E_DUMP_FULL     = 1,  // Per-request e2e_XXXX.json (file I/O overhead ~5%)
    E2E_DUMP_SUMMARY  = 2,  // In-memory aggregate only, no per-request I/O (<1% overhead)
};

struct E2EStageTiming {
    bool enabled = false;
    int dump_mode = E2E_DUMP_DISABLED;  // E2EDumpMode: 0=off, 1=full, 2=summary
    int request_index = 0;
    std::string prompt_id;
    int seed = 0;
    std::atomic<int64_t> timestamps_ns[STAGE_COUNT] = {};  // 0 = not recorded
    int talker_token_count = 0;
    bool no_speech = false;
    int cannerror = 0;
    int crash = 0;

    // F6 Phase 3 (P9): Talker per-step ring buffer
    // Non-atomic — accessed only by TTS thread during decode, read at dump time
    TalkerStepBuffer talker_step_buffer;
    bool talker_stats_enabled = false;  // F6_PHASE3_TALKER_STATS=1

    // Non-atomic — accessed only by the owning thread.
    uint32_t tts_thread_generation = 0;
    uint32_t t2w_thread_generation = 0;
    int      t2w_request_index = 0;  // F6 W5: request_index from T2W queue for audio profile naming
    // Monotonically increasing per-request epoch.
    // Bumped by reset(). Workers snapshot this after their per-request wake-up.
    // record() rejects writes whose generation does not match active_generation_id.
    std::atomic<uint32_t> active_generation_id{0};

    // Counters for stale-write detection (accumulate across requests, never reset).
    std::atomic<uint32_t> stale_write_count{0};
    std::atomic<uint32_t> cross_request_write_count{0};

    // Summary mode: aggregate statistics (non-atomic, only written at dump time from HTTP thread)
    int summary_request_count = 0;
    int64_t summary_stage_latency_sum_ns[STAGE_COUNT] = {};
    int summary_stage_count[STAGE_COUNT] = {};
    int64_t summary_total_decode_ns = 0;  // sum of (D3 - R0) across all requests

    // Accumulate one request's data into summary counters
    void summary_accumulate() {
        summary_request_count++;
        int64_t t0 = t0_ns();
        if (t0 <= 0) return;
        for (int i = 0; i < STAGE_COUNT; i++) {
            int64_t elapsed = elapsed_ms(static_cast<E2EStage>(i), t0);
            if (elapsed >= 0) {
                summary_stage_latency_sum_ns[i] += elapsed * 1'000'000;
                summary_stage_count[i]++;
            }
        }
        // total decode latency (R0 → last recorded stage)
        int64_t t_last = 0;
        for (int i = STAGE_COUNT - 1; i >= 0; i--) {
            t_last = timestamps_ns[i].load(std::memory_order_relaxed);
            if (t_last > 0) break;
        }
        if (t_last > 0 && t0 > 0) {
            summary_total_decode_ns += (t_last - t0);
        }
    }

    // Generation-safe record.
    // Returns true if timestamp was stored, false if generation mismatch (stale).
    // generation_id: the epoch this caller believes is current.
    //   Must be obtained from active_generation_id AFTER the caller's per-request
    //   synchronisation point (e.g. after cv.wait return for worker threads,
    //   or after reset() for the HTTP handler thread).
    bool record(E2EStage stage, uint32_t generation_id) {
        if (!enabled || stage < 0 || stage >= STAGE_COUNT) return false;

        // Acquire: pairs with release in reset() so caller sees cleared timestamps.
        uint32_t current_gen = active_generation_id.load(std::memory_order_acquire);
        if (generation_id != current_gen) {
            stale_write_count.fetch_add(1, std::memory_order_relaxed);
            // If the caller's generation is behind, this is a cross-request late write.
            if (generation_id < current_gen) {
                cross_request_write_count.fetch_add(1, std::memory_order_relaxed);
            }
            // Write sentinel to prevent once-guard (load==0 check) from retrying.
            // Without this, the once-guard would pass on every loop iteration after
            // reset() clears timestamps, causing stale_count to explode (e.g. 400+
            // per request from a single worker retrying 8 stages × 50 iterations).
            // -1 is a sentinel that the once-guard (load==0) treats as "already done".
            // reset() clears all timestamps to 0, overwriting this sentinel for the
            // next valid request.
            timestamps_ns[stage].store(-1, std::memory_order_relaxed);
            return false;
        }

        auto now = std::chrono::steady_clock::now().time_since_epoch();
        // Release: pairs with acquire in elapsed_ms() / t0_ns() so the summary
        // reader sees the complete timestamp after load != 0.
        timestamps_ns[stage].store(
            std::chrono::duration_cast<std::chrono::nanoseconds>(now).count(),
            std::memory_order_release);
        return true;
    }

    // Legacy record without generation guard.
    // Uses the current generation at call time (racy for worker threads).
    // Prefer record(stage, generation_id) when a stable epoch is available.
    void record_unsafe(E2EStage stage) {
        uint32_t gen = active_generation_id.load(std::memory_order_acquire);
        (void)record(stage, gen);
    }

    // Snapshot the active generation for this caller.
    // Call ONCE per request per thread after the thread's synchronisation point.
    uint32_t capture_generation() const {
        return active_generation_id.load(std::memory_order_acquire);
    }

    // Reset all timestamps for a new request.
    // Bumps active_generation_id (release) to invalidate any in-flight record()
    // calls from the previous generation.
    // Must be called at the request boundary (start of stream_decode).
    void reset() {
        // Release: pairs with acquire in record() so late workers see the new generation.
        active_generation_id.fetch_add(1, std::memory_order_release);
        // After releasing the new generation, clear timestamps.
        for (int i = 0; i < STAGE_COUNT; i++) {
            timestamps_ns[i].store(0, std::memory_order_relaxed);
        }
        talker_token_count = 0;
        no_speech = false;
        cannerror = 0;
        crash = 0;
        talker_step_buffer.reset();
    }

    // Returns elapsed ms from stream_decode_start (t0) to given stage, or -1 if not recorded
    int64_t elapsed_ms(E2EStage stage, int64_t t0_ns) const {
        int64_t ts = timestamps_ns[stage].load(std::memory_order_acquire);
        // 0 = not yet recorded (initial state, or cleared by reset()).
        // <0 = sentinel (rejected stale write, or other negative marker).
        if (ts <= 0) return -1;
        return (ts - t0_ns) / 1'000'000;
    }

    // Get t0 reference (request_received timestamp in ns)
    int64_t t0_ns() const {
        return timestamps_ns[STAGE_request_received].load(std::memory_order_acquire);
    }

    const char* stage_name(E2EStage s) const {
        switch (s) {
            case STAGE_request_received:         return "request_received";
            case STAGE_prompt_processing_start:   return "prompt_processing_start";
            case STAGE_llm_first_token:           return "llm_first_token";
            case STAGE_speak_token:               return "speak_token";
            case STAGE_talker_start:              return "talker_start";
            case STAGE_talker_first_audio_token:  return "talker_first_audio_token";
            case STAGE_talker_token_28:           return "talker_token_28";
            case STAGE_t2w_submit:                return "t2w_submit";
            case STAGE_t2w_dequeue:               return "t2w_dequeue";
            case STAGE_flow_start:                return "flow_start";
            case STAGE_flow_end:                  return "flow_end";
            case STAGE_vocoder_start:             return "vocoder_start";
            case STAGE_vocoder_end:               return "vocoder_end";
            case STAGE_wav_ready:                 return "wav_ready";
            case STAGE_client_first_audio:        return "client_first_audio";
            case STAGE_request_done:              return "request_done";
            case STAGE_decode_loop_begin:         return "decode_loop_begin";
            case STAGE_llm_first_decode_step:     return "llm_first_decode_step";
            case STAGE_tts_wake:                  return "tts_wake";
            case STAGE_tts_first_decode:          return "tts_first_decode";
            case STAGE_t2w_preprocess_end:        return "t2w_preprocess_end";
            default: return "unknown";
        }
    }
};

// ============================================================================
// Pipeline Trace — lightweight ring-buffer event recording
// Controlled by OMNI_PIPELINE_TRACE=1 (default off, zero overhead)
// Ring buffer: 8,192 entries × 32 bytes = 256KB, atomic push, no lock
// Dump: per-request CSV at request completion (alongside E2E JSON)
// ============================================================================

enum PipelineEvent : uint8_t {
    PE_DECODE_BEGIN       = 0,  // T2: LLM decode loop entered
    PE_TOKEN_GENERATED    = 1,  // each LLM token produced (counter only)
    PE_FIRST_SPEAK_TOKEN  = 2,  // first speak token detected
    PE_TTS_QUEUE_PUSH     = 3,  // token batch pushed to TTS→T2W queue
    PE_TTS_QUEUE_POP      = 4,  // token batch popped by T2W thread
    PE_T2W_SUBMIT         = 5,  // T2W window submitted for processing
    PE_T2W_COMPLETE       = 6,  // T2W window processing complete
    PE_VOCODER_BEGIN      = 7,  // vocoder started
    PE_VOCODER_COMPLETE   = 8,  // vocoder completed
    PE_FIRST_AUDIO_READY  = 9,  // first WAV file ready
    PE_FIRST_AUDIO_EMIT   = 10, // first audio emitted to client
    PE_THREAD_WAIT_BEGIN  = 11, // thread about to wait on cv/queue
    PE_THREAD_WAIT_END    = 12, // thread woke up from cv/queue
    PE_COUNT
};

struct PipelineTraceEntry {
    int64_t  timestamp_ns;   //  8 bytes — steady_clock monotonic timestamp
    uint32_t sequence_id;    //  4 bytes — global sequence number
    uint32_t data;           //  4 bytes — queue_depth, token_count, or duration_ms
    uint16_t thread_id;      //  2 bytes — hashed thread id
    uint16_t queue_id;       //  2 bytes — queue identifier (0=main, 1=tts, 2=t2w)
    uint8_t  event_type;     //  1 byte  — PipelineEvent enum
    uint8_t  request_id;     //  1 byte  — request index (low byte)
    uint8_t  stage;          //  1 byte  — associated E2EStage context
    uint8_t  reason_code;    //  1 byte  — event-specific reason
    uint8_t  _pad[6];        //  6 bytes — padding (total = 32 bytes)
};

static_assert(sizeof(PipelineTraceEntry) == 32, "PipelineTraceEntry must be 32 bytes");

// Thread wait reason codes (used as reason_code for PE_THREAD_WAIT_BEGIN/END)
enum ThreadWaitReason : uint8_t {
    WAIT_INPUT        = 0,  // waiting for upstream data
    WAIT_QUEUE_EMPTY  = 1,  // waiting for queue to be non-empty
    WAIT_QUEUE_FULL   = 2,  // waiting for queue to have space
    WAIT_CONDVAR      = 3,  // generic condition variable wait
    WAIT_JOIN         = 4,  // waiting for thread to join
    WAIT_NPU          = 5,  // waiting for NPU completion
    WAIT_UNKNOWN      = 99,
};

struct PipelineTraceBuffer {
    static constexpr size_t kMaxEntries = 8192;
    PipelineTraceEntry entries[kMaxEntries] = {};
    std::atomic<uint32_t> write_index{0};
    bool enabled = false;

    void record(PipelineEvent event, uint8_t request_id, uint16_t thread_id,
                uint32_t data = 0, uint16_t queue_id = 0,
                uint8_t stage = 0, uint8_t reason = 0) {
        if (!enabled) return;
        uint32_t idx = write_index.fetch_add(1, std::memory_order_relaxed);
        if (idx >= kMaxEntries) return;  // silent drop — ring buffer full
        auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
        entries[idx] = {
            now_ns, idx, data, thread_id, queue_id,
            (uint8_t)event, request_id, stage, reason,
            {0, 0, 0, 0, 0, 0}
        };
    }

    // Get current count (for dump range check)
    uint32_t count() const {
        uint32_t idx = write_index.load(std::memory_order_relaxed);
        return idx <= kMaxEntries ? idx : kMaxEntries;
    }

    // Reset for next request (called after dump)
    void reset() {
        write_index.store(0, std::memory_order_relaxed);
    }

    // Dump to CSV file
    void dump_csv(const std::string &dir, int request_index) const;
};

extern PipelineTraceBuffer g_pipeline_trace;

// Helper: hash thread id to uint16_t for compact recording
inline uint16_t pipeline_thread_hash() {
    static thread_local uint16_t cached = 0;
    if (cached == 0) {
        std::hash<std::thread::id> hasher;
        cached = (uint16_t)(hasher(std::this_thread::get_id()) & 0xFFFF);
        if (cached == 0) cached = 1;  // reserve 0 for "unknown"
    }
    return cached;
}

const char* pipeline_event_name(PipelineEvent e);

// Environment variable to enable profiling: OMNI_E2E_PROFILE=1
// Output directory for per-request JSON: OMNI_E2E_PROFILE_DIR (default: base_output_dir/e2e_profile)
extern bool g_e2e_profile_enabled;

// Global atomics for flow/vocoder stage timestamps (written by token2wav-impl.cpp, read by omni.cpp)
// These are recorded per-request and consumed by E2EStageTiming::dump.
extern std::atomic<int64_t> g_e2e_flow_start_ns;
extern std::atomic<int64_t> g_e2e_flow_end_ns;
extern std::atomic<int64_t> g_e2e_vocoder_start_ns;
extern std::atomic<int64_t> g_e2e_vocoder_end_ns;

struct omni_context {
    struct vision_ctx * ctx_vision = NULL;
    struct audition_ctx * ctx_audio = NULL;
    
    struct llama_context * ctx_llama = NULL;
    struct llama_model * model = NULL;
    struct common_sampler * ctx_sampler = NULL;
    
    // 🔧 [单双工适配] 是否拥有模型（用于 omni_free 时决定是否释放模型）
    // true: omni_init 内部加载的模型，omni_free 时需要释放
    // false: 外部传入的已有模型（模型复用），omni_free 时不释放
    bool owns_model = true;

    // 🔧 [Length Penalty] 用于调整 EOS token 的采样概率
    // length_penalty > 1.0 会降低 EOS 概率，让模型生成更长的输出
    // length_penalty < 1.0 会增加 EOS 概率，让模型更早结束
    float length_penalty = 1.0f;

    struct llama_context * ctx_tts_llama = NULL;
    struct llama_model * model_tts = NULL;
    struct common_sampler * ctx_tts_sampler = NULL;
    
    // struct TTSContext * ctx_tts = NULL;
    struct vocal_ctx * vocal = NULL;
    std::shared_ptr<std::vector<float>> spk_embeds;
    std::vector<float> audio_emb;
    std::vector<float> omni_emb;    
    int output_audio_round_per_text[5] = {16, 8, 4, 2, 2};
    int output_audio_chunk_size[5] = {5, 10, 20, 40, 40};
    
    struct omni_output *omni_output = NULL;
    int n_past = 0;
    int n_keep = 0;
    
    // ==================== 轮次边界管理（用于智能滑动窗口） ====================
    // 每轮对话开始时的 n_past 位置
    // round_start_positions[i] 表示第 i 轮开始的 n_past 位置
    // 第 i 轮的范围是 [round_start_positions[i], round_start_positions[i+1])
    // 最后一轮的结束位置是当前 n_past
    std::vector<int> round_start_positions;
    
    // 滑动窗口保留的最大上下文长度（不包括 n_keep）
    // 设置为 0 表示使用旧的按比例删除策略
    int max_preserved_context = 2048;
    
    // ==================== 滑动窗口状态 (#39) ====================
    SlidingWindowConfig sliding_window_config;
    
    // Unit 历史管理（用于按 unit 粒度删除）
    std::vector<UnitEntry> unit_history;
    int next_unit_id = 0;
    int pending_unit_id = -1;           // 当前正在处理的 unit ID
    int pending_unit_start_cache_len = 0;  // pending unit 开始时的 cache 长度
    
    // System prompt 保护长度（这部分永远不会被滑窗删除）
    int system_preserve_length = 0;
    
    // RoPE 位置偏移（用于 RoPE 位置重对齐后的 position_ids 计算）
    int position_offset = 0;
    
    // 滑窗统计
    int sliding_event_count = 0;         // 滑窗触发次数
    int total_dropped_tokens = 0;        // 总共丢弃的 token 数
    int total_dropped_units = 0;         // 总共被移除的 UnitEntry 条目数；
                                         //   两种模式语义统一：turn 模式下含"整 turn 丢带走的 + fallback 丢的"，
                                         //   非 turn 模式下就是按 unit 丢的总数
    int total_dropped_turns = 0;         // 总共丢弃的 turn 数（按 turn 粒度）；非 turn 模式恒为 0
    int total_unit_fallbacks = 0;        // 仅 turn 模式：整 turn 丢不动 → 退化按 unit 丢的次数；
                                         //   非 turn 模式恒为 0

    // 🔧 [turn 级滑窗] 当前正在构建的 turn id
    // 每个 UnitEntry 注册时会被打上 current_turn_id，
    // 在 turn 边界（round_start_positions 推进处）会把 current_turn_id++。
    // sliding_window_enforce 先按 turn 丢，当 unit_history 里只剩 turn_id == current_turn_id
    // 的 unit（即只剩当前正在构建、还没收尾的 turn）时，退化为按 unit 丢。
    int current_turn_id = 0;
    
    bool async = false;
    std::thread llm_thread;
    std::thread tts_thread;
    std::thread t2w_thread;
    struct LLMThreadInfo *llm_thread_info = NULL;
    struct TTSThreadInfo *tts_thread_info = NULL;
    struct T2WThreadInfo *t2w_thread_info = NULL;

    // 🔧 [Duplex Pipeline - Stage 1]
    // 仅在 duplex_mode=true && async=true 时由 omni_init / stream_prefill(index=0) 分配。
    // 作用：取代 duplex 路径下的老 llm_thread_func，把"VPM+APM 编码"和
    //      "LLM prefill + autoregressive decode" 拆成两个独立常驻线程，
    //      并通过自有的细粒度锁解耦，为后续阶段的 encoder 并行、
    //      batch 融合打基础。
    // 生命周期：omni_free 中通过 duplex_pipeline_free 销毁。
    // 非 duplex_mode 下始终为 nullptr。
    DuplexPipeline * duplex = NULL;

    // 高层 duplex 会话句柄；由 omni_duplex_session_begin 分配，session_end 销毁。
    // 持有内部 prefill_worker/decode_worker 线程及 frame 队列。
    // omni_free 时若仍存在，会被强制 session_end 释放。
    DuplexSession * duplex_session = NULL;
    
    std::atomic<bool> need_speek{false};
    std::atomic<bool> speek_done{true};
    
    // 预热标志：第一轮对话视为预热（例如音色克隆参考音频），完成后设为 true
    std::atomic<bool> warmup_done{false};
    
    // ==================== 双工模式状态 ====================
    // 当前轮次是否已结束（用于决策是否允许切换到 listen 状态）
    // Python: self.current_turn_ended
    bool current_turn_ended = true;
    
    // 打断事件标志
    // break_event: 打断当前生成，但保持会话活跃（用于双工模式的用户打断）
    //              打断后可继续调用 prefill/decode
    std::atomic<bool> break_event{false};
    
    // session_stop_event: 终止整个会话（预留，目前未使用）
    //                     用于彻底关闭当前会话，需要重新 omni_init
    std::atomic<bool> session_stop_event{false};
    
    // 🔧 [双工模式] 记录当前 decode 是否以 <|listen|> 结束
    // 如果是，则不清理 KV cache，让下一个音频片段可以累积上下文
    std::atomic<bool> ended_with_listen{false};
    
    // [滑窗专用] 记录最近一次 decode 结果是 LISTEN 还是 SPEAK
    // 与 ended_with_listen 不同：不在 stream_decode 开头重置，
    // 只由 decode 的实际输出驱动（LISTEN→true, SPEAK→false）
    std::atomic<bool> slide_last_was_listen{true};
    
    // 🔧 [与 Python 对齐] LLM 生成结束标志
    // 当 LLM 检测到 end token 时设置为 true
    // TTS 线程检查此标志来决定是否添加 text_eos_embed
    std::atomic<bool> llm_generation_done{false};

    // ===================================================================
    // F6 A5: Generation-based request lifecycle (replaces bool-only CV preds)
    // request_generation increments with each stream_decode entry.
    // CV waits use ">= my_gen" so they cannot be satisfied by stale state.
    // ===================================================================
    std::atomic<uint32_t> request_generation{0};          // monotonically increasing per-request id
    std::atomic<uint32_t> prefill_ready_generation{0};    // gen for which prefill is done
    std::atomic<uint32_t> speak_requested_generation{0};  // gen for which speak was requested
    std::atomic<uint32_t> drain_complete_generation{0};   // gen for which T2W drain completed
    std::atomic<int>        context_state{CTX_STATE_REUSABLE};  // lifecycle FSM state
    std::atomic<int>        request_state{REQ_IDLE};           // per-request lifecycle FSM state
    
    // ==================== 双工模式参数 ====================
    // 每个 chunk 最大生成 token 数（用于限制单次 speak 长度，便于及时响应打断）
    // 设置为 0 表示无限制
    int max_new_speak_tokens_per_chunk = 26;
    
    // listen_prob_scale: 调整 <|listen|> token 的采样概率
    // 1.0: Python 默认
    float listen_prob_scale = 1.0f;

    // 会话开局强制 LISTEN 的 chunk 数（与 Python duplex_config.force_listen_count 对齐）
    // 防止 browser 打开 MediaStreamTrack 时的瞬态噪声 + 强 system prompt 组合
    // 导致模型在第一 chunk 就 SPEAK 产生"抢答"。
    // 每次 update_session_config 时重置 force_listen_used=0。
    int force_listen_count = 3;
    int force_listen_used  = 0;

    // TTS 采样温度（与 Python TTSSamplingParams.temperature 对齐，默认 0.8）
    // 通过 /v1/stream/update_session_config 的 "tts_temperature" 字段透传
    float tts_temperature = 0.8f;

    // 是否启用双工模式
    // simplex: 单工模式，用户说完后模型回复，回复完用户再说
    // duplex: 双工模式，模型可以在任意时刻决定听/说切换
    bool duplex_mode = false;
    
    // 系统 prompt 是否已初始化（防止 stream_prefill index=0 被重复调用导致 prompt 重复）
    bool system_prompt_initialized = false;
    
    class AudioInputManager * audio_input_manager = NULL;
    
    // models path and other configs
    struct common_params * params = NULL;
    
    // 当前是以「语音通话」还是「视频通话」模式进入的，0 = 语音，1 = 视频；
    int media_type = 0;
    int use_tts = false;
    std::string tts_bin_dir = "";
    std::string ref_audio_path = "";  // 参考音频路径（用于音色克隆）
    
    // 🔧 [高清/高刷模式] 
    // high_image: 高清模式，max_slice_nums 设置为 2，vision 可以看到更多细节
    // high_refresh: 高刷模式，1秒5帧，第1帧作为主图，后4帧stack合并成一张图
    //               注意：stack 处理在 Python server 层实现，C++ 只是标记
    bool high_image = false;
    bool high_refresh = false;
    
    // 🔧 [多实例支持] 可配置的输出目录，避免多个服务实例冲突
    std::string base_output_dir = "./tools/omni/output";
    
    // 每次会话，是否清除 kv cache（默认开启自动清理 kv cache）
    bool clean_kvcache = true;
    
    std::string omni_voice_clone_prompt = "";
    std::string omni_assistant_prompt = "";
    std::string audio_voice_clone_prompt = "";
    std::string audio_assistant_prompt = "";
    
    // 语言设置 (用于 prompt 生成)
    std::string language = "zh";

    // text_mtx protects only the text streaming state consumed by HTTP/WS
    // readers; broader omni_context lifecycle/prefill changes use server octx_mutex.
    std::mutex text_mtx;
    std::condition_variable text_cv;
    std::deque<std::string> text_queue;
    bool text_streaming = false;
    bool text_done_flag = false;

    // llama inference mutex - 保护 ctx_llama 的推理操作
    std::mutex llama_mtx;
    
    // TTS weights loaded from GGUF file
    // emb_code: (num_audio_tokens=6562, hidden_size=768) - for converting audio token IDs to embeddings
    float * emb_code_weight = nullptr;
    int emb_code_vocab_size = 0;  // num_audio_tokens = 6562
    int emb_code_hidden_size = 0; // hidden_size = 768
    bool emb_code_stored_as_transposed = false; // true if stored as [hidden_size, num_audio_tokens] = [768, 6562]
    
    // emb_text: (vocab_size=152064, hidden_size=768)
    float * emb_text_weight = nullptr;
    int emb_text_vocab_size = 0;
    int emb_text_hidden_size = 0;
    
    // projector_semantic: two-layer MLP (4096 -> 768 -> 768)
    // Legacy float* weights (kept for backward compatibility)
    float * projector_semantic_linear1_weight = nullptr;  // (4096, 768)
    float * projector_semantic_linear1_bias = nullptr;   // (768,)
    float * projector_semantic_linear2_weight = nullptr; // (768, 768)
    float * projector_semantic_linear2_bias = nullptr;  // (768,)
    int projector_semantic_input_dim = 0;  // 4096
    int projector_semantic_output_dim = 0;  // 768
    
    // New ggml-based projector model (精度验证版本)
    struct projector_model projector;
    struct tts_condition_graph_model tts_condition_graph;
    
    // head_code: Linear layer (hidden_size=768 -> num_audio_tokens=6562)
    // Note: num_vq=1, so we only need one head_code layer
    float * head_code_weight = nullptr;  // (768, 6562) - stored as (hidden_size, num_audio_tokens)
    int head_code_hidden_size = 0;  // 768
    int head_code_num_audio_tokens = 0;  // 6562
    
    // TTS condition embeddings (for first audio token re-forward)
    // Used to store the condition embeddings so we can re-forward them for the first audio token
    // This ensures KV cache state matches Python's behavior (past_key_values=None on first forward)
    std::vector<float> tts_condition_embeddings;  // Condition embeddings (n_tokens * n_embd)
    int tts_condition_length = 0;  // Number of tokens in condition
    int tts_condition_n_embd = 0;  // Embedding dimension (768)
    bool tts_condition_saved = false;  // Whether condition has been saved
    
    // 🔧 TTS KV cache 累计位置（用于保持跨 chunk 的上下文连续性）
    // Python TTSStreamingGenerator 使用 text_start_pos 来跟踪位置
    int tts_n_past_accumulated = 0;
    
    // 🔧 [关键修复] TTS 已生成的所有 audio tokens（跨 chunk 累积）
    // Python: self.all_generated_tokens 是类成员变量，跨 chunk 持续累积
    // 用于：1. RAS 重复检测（需要完整历史）2. 正确判断 audio_bos（只有第一个 token 才是）
    std::vector<llama_token> tts_all_generated_tokens;
    
    // 🔧 [与 Python 对齐] TTS audio token buffer（跨 text chunk 累积）
    // Python: self._token_buffer 是类成员变量，用于累积 audio token
    // 只有满足 chunk_size (25) 才会 yield，不足的保留到下一个 text chunk
    std::vector<int32_t> tts_token_buffer;
    
    // Timestamp for stream_decode start (used for WAV file naming)
    std::chrono::high_resolution_clock::time_point stream_decode_start_time;

    // P7.3 P10: request-level clock — set before stream_prefill() by the caller.
    // Measures full user-facing latency from request boundary to first audio.
    // Defaults to epoch (0) if not set; the WAV writer uses this as the
    // authoritative request start when available.
    std::chrono::high_resolution_clock::time_point request_start_time;

    // E2E stage profiling (OMNI_E2E_PROFILE=1)
    E2EStageTiming e2e_stage;
    
    // C++ Token2Wav session for audio synthesis
    std::unique_ptr<omni::flow::Token2WavSession> token2wav_session;
    bool token2wav_initialized = false;
    std::string token2wav_model_dir;  // Directory containing token2wav GGUF models
    bool token2wav_defer_worker_init = false;  // CANN: defer init to worker thread

    // ── P1 FAIL-FAST: CANN availability tracking ──────────────────
    // Populated at omni_init() time. Used by the worker thread to
    // decide whether to fail-fast (exit non-zero) vs silently fall
    // back to CPU when the canonical CANN candidate is unavailable.
    bool cann_registry_available       = false;  // aclInit succeeded, devices registered
    bool cann_backend_init_success     = false;  // ggml_backend_cann_init(device) returned non-null
    bool cann_backend_init_failure     = false;  // ggml_backend_cann_init(device) returned null
    bool cann_requested_but_unavailable = false;  // OMNI_T2W_DEVICE=cann-flow-only but CANN missing
    int  cpu_fallback_count            = 0;      // incremented each time a CANN→CPU fallback occurs
    
    // 🔧 [Python Token2Wav] 使用 Python stepaudio2 库实现的 Token2Wav
    // 设置为 true 时使用 Python 实现（精度更高），false 时使用 C++ 实现
    // macOS 上默认使用 C++ 实现（无 CUDA）
    bool use_python_token2wav = false;
    audio_output_cb_t audio_output_cb = nullptr; // called by T2W threads when a chunk of audio is ready
    std::string python_t2w_script_dir;  // Python Token2Wav 脚本目录
    std::string python_t2w_model_dir;   // Python Token2Wav 模型目录
    
    // Python Token2Wav 服务进程 (通过 popen 启动)
    FILE* python_t2w_stdin = nullptr;   // 写入命令
    FILE* python_t2w_stdout = nullptr;  // 读取响应
    pid_t python_t2w_pid = -1;          // 进程 ID
    bool python_t2w_initialized = false;
    std::string python_t2w_gpu_id;      // GPU ID (如 "0", "1")
    
    // 🔧 Python T2W 独立 GPU 配置
    // C++ LLM+TTS 占用约 22GB，Python T2W 占用约 3.3GB
    // 单卡 24GB 放不下，需要使用独立 GPU
    // 设置为空字符串表示使用与 C++ 相同的 GPU
    std::string python_t2w_dedicated_gpu = "";  // 独立 GPU ID，如 "1"
    
    // Token2Wav sliding window buffer (跨 chunk 保持状态)
    // Python 逻辑: buffer 初始填充 3 个静音 token (4218)
    // 每次取 28 个 tokens (25 main + 3 lookahead)，处理后移动 25 个，保留 3 个重叠
    std::vector<int32_t> token2wav_buffer;
    int token2wav_wav_idx = 0;  // 输出 WAV 文件计数器
    int wav_turn_base = 0;      // 每轮对话结束时 +1000，用于区分不同轮次的 WAV 文件
    
    // 🔧 [单工模式] 当前轮次索引（用于创建 round_000、round_001 等子目录）
    int simplex_round_idx = 0;
    
    // ==================== 特殊 Token ID ====================
    // 在 omni_init 时从词表查找并缓存
    llama_token special_token_speak = -1;        // <|speak|>: 模型开始说话
    llama_token special_token_listen = -1;       // <|listen|>: 模型开始听（双工）
    llama_token special_token_chunk_eos = -1;    // <|chunk_eos|>: 语义 chunk 结束
    llama_token special_token_chunk_tts_eos = -1;// <|chunk_tts_eos|>: TTS chunk 结束
    llama_token special_token_turn_eos = -1;     // <|turn_eos|>: 轮次结束
    llama_token special_token_tts_eos = -1;      // <|tts_eos|>: 旧版 TTS 结束
    llama_token special_token_eos = -1;          // </s>: 序列结束
    llama_token tts_bos_token_id = -1;           // <|tts_bos|>: TTS 开始（用于双工强制继续说话）
    llama_token special_token_unit_end = -1;     // </unit>: unit 结束标记（双工 chunk 边界）
    llama_token special_token_tts_pad = -1;      // <|tts_pad|>: TTS 填充（双工模式下禁止采样）
};

//
// omni embed
//
bool prefill_with_emb(struct omni_context * ctx_omni, struct common_params * params, float* embed, int n_pos, int n_batch, int* n_past);
bool prefill_emb_with_hidden(struct omni_context * ctx_omni, struct common_params * params, float* embed, int n_pos, int n_batch, int* n_past, float *& hidden_states);
bool omni_eval_embed(struct llama_context * ctx_llama, const struct omni_embed * embed, int n_batch, int * n_past);
void omni_embed_free(struct omni_embed * embed);
struct omni_embed * omni_image_embed_make_with_bytes(struct vision_ctx * ctx_vision, int n_threads, const unsigned char * image_bytes, int image_bytes_length);
struct omni_embed * omni_image_embed_make_with_filename(struct vision_ctx * ctx_vision, int n_threads, std::string image_path);
struct omni_embed * omni_audio_embed_make_with_bytes(struct audition_ctx * ctx_audition, int n_threads, audition_audio_f32 * audio);
struct omni_embed * omni_audio_embed_make_with_filename(struct audition_ctx * ctx_audition, int n_threads, std::string audio_path);

//
// omni main
//
struct omni_context * omni_init(struct common_params * params, int media_type, bool use_tts, std::string tts_bin_dir,
                                int tts_gpu_layers = -1, const std::string & token2wav_device = "gpu:0",
                                bool duplex_mode = false,
                                llama_model * existing_model = nullptr, llama_context * existing_ctx = nullptr,
                                const std::string & base_output_dir = "./tools/omni/output");

void omni_free(struct omni_context * ctx_omni);
// Stop/join inference threads and clear queues so the same context can serve a
// new session, without tearing down the loaded model (unlike omni_free).
void omni_prepare_for_reuse(struct omni_context * ctx_omni);

// ANE/CoreML warmup — call once after omni_init to pre-load models into NPU
void omni_warmup_ane(struct omni_context * ctx_omni);

// 检查 TTS 和 T2W 队列是否都为空
bool omni_tts_queues_empty(struct omni_context * ctx_omni);

// 停止所有线程（在 join 之前调用）
void omni_stop_threads(struct omni_context * ctx_omni);

bool stream_prefill(struct omni_context * ctx_omni,
                            std::string aud_fname,
                            std::string img_fname = "",
                            int index = 0,
                            int max_slice_nums = -1,  // -1 表示使用全局设置，>=1 表示本次 prefill 的 slice 数量
                            std::string text = "");   // 用户文本片段：与 audio/image 同为一种 modality，
                                                     // 在 index>=1 的用户输入阶段插入到当前 user turn 中。
                                                     // 不会自动包裹任何 role/special token —— 调用方完全控制其字面值。

bool stream_decode(struct omni_context * ctx_omni,
                        std::string debug_dir,
                        int round_idx = -1);  // round_idx: 由调用方指定的轮次索引，-1 表示使用内部计数

// ============================================================================
// 高层 Duplex Session API（推荐外部调用方使用）
//
// 设计目标：
//   把"prefill 提前 submit + decode 等待 LLM 完成"的 producer/consumer 调度
//   完全收纳到 omni 内部。调用方按业务节奏（例如每秒一次）调 push_frame，
//   通过 wait_next_frame 取本帧的决策与文本。test/server/cli 都可以用同一套接口。
//
// 与底层 stream_prefill/stream_decode 的关系：
//   - omni_duplex_session_begin    内部调一次 stream_prefill(index=0)，初始化
//                                  system prompt + voice clone + 启动 duplex pipeline。
//   - omni_duplex_push_frame       通过 prefill_worker 调 stream_prefill(index>0)。
//   - 内部 decode_worker           每提交一帧 prefill 就触发一次 stream_decode，
//                                  保持 1:1 顺序（与 duplex_llm_thread_func 配合）。
//   - omni_duplex_wait_next_frame  按 push 顺序拿出本帧的 LLM 决策与文本。
//
// 仅在 duplex_mode=true && async=true 下可用；非 duplex 模式请直接使用 stream_*。
// ============================================================================

struct OmniDuplexFrame {
    std::string aud_fname;          // 该帧音频文件路径，空字符串表示无音频
    std::string img_fname;          // 该帧图片文件路径，空字符串表示无图片
    int max_slice_nums = -1;        // 与 stream_prefill 同义；-1 表示用全局
    int64_t user_seq = 0;           // 调用方自定义序号，原样回传到 result
};

struct OmniDuplexFrameResult {
    int64_t  user_seq = 0;          // 与 OmniDuplexFrame.user_seq 一致
    int64_t  frame_id = -1;         // 内部分配的递增 id（1, 2, 3, ...）
    bool     ok = false;            // false = prefill 或 decode 失败
    bool     is_speak = false;      // false = LISTEN，true = SPEAK
    std::string text;               // 该帧 SPEAK 时生成的文本片段（已剔除控制 token）
    int      n_past_after = 0;      // 帧处理完成时的 ctx_llama n_past（调试用）
    double   ms_prefill_submit = 0; // push_frame → prefill_worker 完成提交（不等编码）
    double   ms_decode = 0;         // decode_worker 内部 stream_decode 阻塞时长
    double   ms_total = 0;          // push_frame → 本帧 result 出队的端到端 wall time
};

// 启动一次 duplex 会话。
//   ctx_omni      : 已经 omni_init() + ctx_omni->async = true + duplex_mode = true 的上下文
//   voice_audio   : 用作 voice clone reference 的音频文件路径，可空
//   debug_dir     : 每帧 audio chunk 输出目录（沿用 stream_decode 的语义）
// 失败原因通常是 omni_init 未完成、duplex_mode/async 没开、或 voice_audio prefill 出错。
bool omni_duplex_session_begin(struct omni_context * ctx_omni,
                               const std::string & voice_audio,
                               const std::string & debug_dir = "./");

// 提交一帧到 duplex pipeline。立即返回，不等 LLM 完成。
// 返回值：>=1 表示分配的 frame_id；<0 表示会话未启动或队列异常。
// 当内部 pending 队列已满时会阻塞直到有空位（避免无界增长）。
int64_t omni_duplex_push_frame(struct omni_context * ctx_omni,
                               const OmniDuplexFrame & frame);

// 阻塞拿下一帧的处理结果（按 push 顺序 FIFO）。
//   timeout_ms < 0 : 无限等待
//   timeout_ms = 0 : 非阻塞 try_pop
//   timeout_ms > 0 : 等待至多 N 毫秒
// 返回 false 表示超时或会话已结束且队列已空。
bool omni_duplex_wait_next_frame(struct omni_context * ctx_omni,
                                 OmniDuplexFrameResult * out,
                                 int timeout_ms = -1);

// 结束会话：等所有已 push 但未完成的帧 LLM 完成（drain），停止 worker 线程并释放。
// TTS / token2wav 后台音频生成线程不在此处停止，由 omni_free 负责。
void omni_duplex_session_end(struct omni_context * ctx_omni);

// 阻塞等待 TTS / token2wav 队列彻底空闲（即所有 speak 帧的 audio 文件已写盘）。
// 返回前会要求队列连续 idle_ms 毫秒为空，避免误判中间瞬态 idle。
// 仅在 ctx_omni->async && use_tts 时有意义；其他情况立即返回 true。
//   max_wait_ms : 总超时上限，超时返回 false
//   idle_ms     : 连续空闲达到该时长才算 drain 成功（默认 3s）
bool omni_duplex_drain_tts_audio(struct omni_context * ctx_omni,
                                 int max_wait_ms = 120000,
                                 int idle_ms = 3000);

bool stop_speek(struct omni_context * ctx_omni);

bool clean_kvcache(struct omni_context * ctx_omni);

// TTS 推理函数声明（用于 test_tts_inference.cpp）
bool load_tts_weights_from_gguf(struct omni_context * ctx_omni, const char * tts_model_path);
bool prefill_with_emb_tts(struct omni_context* ctx_omni, common_params* params, float* embed, int n_pos, int n_batch, int* n_past_tts);
// sample_tts_token 参数说明：
// - all_generated_tokens: 跨 chunk 累积的所有 tokens（用于判断是否是整个过程的第一个 token，即 re-forward condition）
// - chunk_generated_tokens: 当前 chunk 内已生成的 tokens（用于 repetition penalty，与 Python generate_chunk 对齐）
// - token_index_in_chunk: 当前 chunk 内的 token 索引（用于判断是否跳过 sampling processors）
// - force_no_eos: 是否强制阻止 EOS token 被采样（用于 min_new_tokens 逻辑，与 Python generate_chunk 对齐）
llama_token sample_tts_token(struct common_sampler * smpl, struct omni_context * ctx_omni, common_params* params, int * n_past_tts, const std::vector<llama_token> * all_generated_tokens = nullptr, const std::vector<llama_token> * chunk_generated_tokens = nullptr, int token_index_in_chunk = 0, bool force_no_eos = false);

// Projector 函数声明（精度验证版本）
bool projector_init(projector_model & model, const std::string & fname, bool use_cuda);
void projector_free(projector_model & model);
std::vector<float> projector_forward(projector_model & model, const float * input_data, int n_tokens);

// ==================== 滑动窗口函数声明 (#39) ====================
// Unit 管理
int sliding_window_register_unit_start(struct omni_context * ctx_omni);
void sliding_window_register_unit_end(struct omni_context * ctx_omni, const std::string & input_type, 
                                      const std::vector<llama_token> & generated_tokens = {}, bool is_listen = false);
void sliding_window_register_system_prompt(struct omni_context * ctx_omni);

// 滑窗执行
bool sliding_window_enforce(struct omni_context * ctx_omni);
bool sliding_window_drop_tokens_from_cache(struct omni_context * ctx_omni, int length);
void sliding_window_reset(struct omni_context * ctx_omni);

// ==================== 高清模式函数声明 ====================
// 设置 vision max_slice_nums 覆盖值，用于高清模式
void vision_set_max_slice_nums(struct vision_ctx * ctx_vision, int max_slice_nums);

// benchmark: serial vs batched vision encoding
void omni_bench_vision(struct vision_ctx * ctx_vision, int n_threads, const char * image_path);