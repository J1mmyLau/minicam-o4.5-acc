// Omni streaming HTTP server — standalone omni API endpoints
// Based on the old server.cpp omni handlers, adapted for the new llama.cpp APIs

#include "omni.h"
#include "llama.h"
#include "common.h"
#include "log.h"
#include "arg.h"
#include "sampling.h"
#include "session.h"
#include "ws_handler.h"

#include <mutex>
#include <thread>
#include <queue>
#include <condition_variable>
#include <fstream>
#include <string>
#include <chrono>
#include <sstream>
#include <unistd.h>

// ============================================================================
// F6 LIFECYCLE INSTRUMENTATION — provides nanosecond-precision handler events
// to distinguish (A) drain hang, (B) handler/mutex block, (C) context reuse race.
// Events go to stderr (unbuffered) to avoid mixing with server.log.
// ============================================================================
static uint64_t _f6_ns_now() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
static void _f6_event(const char *event, int req_id, const omni_context *ctx) {
    uint64_t ns = _f6_ns_now();
    uint64_t ctx_ptr = reinterpret_cast<uint64_t>(ctx);
    size_t   tid     = std::hash<std::thread::id>{}(std::this_thread::get_id());
    fprintf(stderr, "F6_EVENT|%lu|%s|req=%d|ctx=0x%lx|tid=0x%zx\n",
            ns, event, req_id, ctx_ptr, tid);
}
static void _f6_event_ctx_state(int req_id, const omni_context *ctx) {
    if (!ctx) return;
    uint64_t ns = _f6_ns_now();
    // F6 A1: use atomic counters for lock-free reads of T2W queue depth.
    // queue.size() is UNSAFE without holding t2w_thread_info->mtx.
    // GLOBAL_ prefix on prefill_done and t2w_thread_running: these are
    // file-scope atomics in omni.cpp, NOT per-omni_context fields.
    size_t queued = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->queued_t2w_task_count.load() : (size_t)0;
    size_t active = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->active_t2w_task_count.load() : (size_t)0;
    uint32_t req_gen  = ctx->request_generation.load();
    uint32_t drain_gen = ctx->drain_complete_generation.load();
    int      ctx_state = ctx->context_state.load();
    int      req_state = ctx->request_state.load();
    // F6 R12: per-generation accounting counters
    uint32_t final_dequeued  = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->final_dequeued_generation.load() : (uint32_t)0;
    uint32_t final_completed = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->final_processed_generation.load() : (uint32_t)0;
    uint32_t gen_dequeue   = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->generation_dequeue_count.load() : (uint32_t)0;
    uint32_t gen_complete  = ctx->t2w_thread_info
        ? ctx->t2w_thread_info->generation_complete_count.load() : (uint32_t)0;
    fprintf(stderr, "F6_CTXSTATE|%lu|req=%d|ctx=0x%lx|t2w_joinable=%d|"
            "queued=%zu|active=%zu|need_speek=%d|speek_done=%d|"
            "n_past=%d|llm_gen_done=%d|"
            "req_gen=%u|drain_gen=%u|ctx_state=%d|req_state=%d(%s)|"
            "final_dequeued=%u|final_completed=%u|gen_deq=%u|gen_cmp=%u|"
            "GLOBAL_prefill_done=%d|GLOBAL_t2w_thread_running=%d\n",
            ns, req_id, reinterpret_cast<uint64_t>(ctx),
            ctx->t2w_thread.joinable() ? 1 : 0,
            queued, active,
            ctx->need_speek.load() ? 1 : 0,
            ctx->speek_done.load() ? 1 : 0,
            ctx->n_past,
            ctx->llm_generation_done.load() ? 1 : 0,
            req_gen, drain_gen, ctx_state, req_state, req_state_name((OmniRequestState)req_state),
            final_dequeued, final_completed, gen_dequeue, gen_complete,
            prefill_done.load() ? 1 : 0,
            t2w_thread_running.load() ? 1 : 0);
}

// F6 R10: Request state machine — validates and logs state transitions.
// Returns true if the transition is legal, false if illegal (logged as ERROR).
static bool _f6_transition_req_state(omni_context *ctx, OmniRequestState new_state,
                                      int req_id, const char *label) {
    if (!ctx) {
        fprintf(stderr, "F6_REQSTATE|%lu|req=%d|(null)→%s|label=%s|SKIP_NULL_CTX\n",
                _f6_ns_now(), req_id, req_state_name(new_state), label ? label : "?");
        return false;
    }
    int old_val = ctx->request_state.load(std::memory_order_relaxed);
    OmniRequestState old_state = (OmniRequestState)old_val;

    // Transition validity matrix — sparse: only specific (old→new) pairs allowed.
    bool legal = false;
    switch (old_state) {
    case REQ_IDLE:
        legal = (new_state == REQ_VALIDATING);
        break;
    case REQ_VALIDATING:
        legal = (new_state == REQ_DECODING || new_state == REQ_ERROR);
        break;
    case REQ_DECODING:
        legal = (new_state == REQ_TTS_PENDING || new_state == REQ_DRAINING || new_state == REQ_RESPONDING || new_state == REQ_ERROR);
        break;
    case REQ_TTS_PENDING:
        legal = (new_state == REQ_DRAINING || new_state == REQ_ERROR);
        break;
    case REQ_DRAINING:
        legal = (new_state == REQ_RESPONDING || new_state == REQ_ERROR);
        break;
    case REQ_RESPONDING:
        legal = (new_state == REQ_IDLE);
        break;
    case REQ_ERROR:
        legal = (new_state == REQ_IDLE);
        break;
    default:
        legal = false;
        break;
    }

    ctx->request_state.store((int)new_state, std::memory_order_release);

    uint64_t ns = _f6_ns_now();
    fprintf(stderr, "F6_REQSTATE|%lu|req=%d|%s→%s|label=%s|%s\n",
            ns, req_id,
            req_state_name(old_state), req_state_name(new_state),
            label ? label : "?",
            legal ? "OK" : "ILLEGAL");

    return legal;
}

#include "httplib.h"
#include <nlohmann/json.hpp>

using json = nlohmann::json;

static json format_error_response(const std::string & message, const std::string & type = "invalid_request_error") {
    return json{{"error", {{"message", message}, {"type", type}}}};
}

template<typename T>
static T json_value(const json & body, const std::string & key, const T & default_value) {
    if (body.contains(key)) {
        try {
            return body.at(key).get<T>();
        } catch (...) {
            return default_value;
        }
    }
    return default_value;
}

static void res_ok(httplib::Response & res, const json & data) {
    res.set_content(data.dump(), "application/json");
}

static void res_error(httplib::Response & res, const json & err) {
    res.status = json_value(err, "code", 500);
    res.set_content(err.dump(), "application/json");
}

static bool server_sent_event(httplib::DataSink & sink, const json & ev) {
    std::string str = "data: " + ev.dump() + "\n\n";
    return sink.write(str.data(), str.size());
}

static std::string parent_dir(const std::string & path) {
    const size_t pos = path.find_last_of("/\\");
    return pos == std::string::npos ? "." : path.substr(0, pos);
}

static bool ensure_omni_model_paths_from_llm(common_params & params) {
    if (params.model.path.empty()) {
        return false;
    }
    const std::string root = parent_dir(params.model.path);
    if (root.empty()) {
        return false;
    }
    if (params.vpm_model.empty()) {
        params.vpm_model = root + "/vision/MiniCPM-o-4_5-vision-F16.gguf";
    }
    if (params.apm_model.empty()) {
        params.apm_model = root + "/audio/MiniCPM-o-4_5-audio-F16.gguf";
    }
    if (params.tts_model.empty()) {
        params.tts_model = root + "/tts/MiniCPM-o-4_5-tts-F16.gguf";
    }
    if (params.tts_bin_dir.empty()) {
        params.tts_bin_dir = root + "/tts";
    }
    return true;
}

struct omni_server_state {
    omni_context * octx = nullptr;    // WS backend uses this as shared_octx
    std::mutex octx_mutex;            // protects omni_context lifecycle + prefill/decode entry
    SessionManager session_mgr;       // WS backend session management
    int server_pid = 0;               // F6 R11: port ownership guard — set at startup
    int bound_port = 0;               // F6 R11: port this server bound to
};

int main(int argc, char ** argv) {
    common_params params;

    common_init();

    if (!common_params_parse(argc, argv, params, LLAMA_EXAMPLE_SERVER)) {
        return 1;
    }

    // omni HTTP server is single-session (1:1 duplex), so 1 sequence is enough.
    // common_params defaults n_parallel to -1 ("auto"); each example resolves it
    // itself (see tools/server/server.cpp). Without this, n_seq_max overflows
    // uint32 and trips LLAMA_MAX_SEQ(256) inside llama_context.
    if (params.n_parallel < 0) {
        params.n_parallel = 1;
    }

    llama_backend_init();
    llama_numa_init(params.numa);

    LOG_INF("Omni HTTP server starting...\n");

    // auto-detect omni model paths
    if (!params.vpm_model.empty() || !params.apm_model.empty() || !params.tts_model.empty()) {
        LOG_INF("Using explicit omni model paths from args\n");
    }

    // HTTP server setup
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    httplib::SSLServer svr(params.ssl_file_cert.c_str(), params.ssl_file_key.c_str());
#else
    httplib::Server svr;
#endif

    omni_server_state state;

    // GET /health — includes PID for port ownership verification
    svr.Get("/health", [&](const httplib::Request &, httplib::Response & res) {
        json health = {
            {"status", "ok"},
            {"engine", "comni"},
            {"pid", state.server_pid},
            {"port", state.bound_port},
        };
        res.set_header("X-Engine", "comni");
        res.set_header("X-Server-PID", std::to_string(state.server_pid));
        res_ok(res, health);
    });

    svr.Get("/v1/health", [&](const httplib::Request &, httplib::Response & res) {
        json health = {
            {"status", "ok"},
            {"engine", "comni"},
            {"pid", state.server_pid},
            {"port", state.bound_port},
        };
        res.set_header("X-Engine", "comni");
        res.set_header("X-Server-PID", std::to_string(state.server_pid));
        res_ok(res, health);
    });

    // POST /v1/stream/omni_init
    svr.Post("/v1/stream/omni_init", [&](const httplib::Request & req, httplib::Response & res) {
        _f6_event("OMNI_INIT_HANDLER_ENTER", -1, state.octx);
        try {
        json data = json::parse(req.body);

        if (!data.contains("msg_type") && !data.contains("media_type")) {
            res_error(res, format_error_response("\"msg_type\" or \"media_type\" must be provided"));
            return;
        }

        int media_type = data.value("msg_type", data.value("media_type", 2));
        bool use_tts   = data.value("use_tts", true);
        bool duplex_mode = data.value("duplex_mode", false);
        int tts_gpu_layers = data.value("tts_gpu_layers", 100);
        std::string token2wav_device = data.value("token2wav_device", "gpu:0");
        std::string output_dir = data.value("output_dir", "./tools/omni/output");
        std::string voice_audio = data.value("voice_audio", "");

        // validate key files
        auto check_file = [&](const std::string & role, const std::string & path) -> bool {
            if (path.empty()) return true;
            std::ifstream f(path);
            if (!f.good()) {
                res_error(res, format_error_response(
                    "omni_init missing required model file (" + role + "): " + path));
                return false;
            }
            return true;
        };

        // Keep legacy HTTP aligned with /backend: the LLM path (-m) anchors the
        // fixed MiniCPM-o sub-model layout; request model_dir is ignored.
        if (!ensure_omni_model_paths_from_llm(params)) {
            res_error(res, format_error_response("LLM model path (-m) is required to derive omni model paths"));
            return;
        }

        if (!check_file("LLM",    params.model.path) ||
            !check_file("vision", params.vpm_model)  ||
            !check_file("audio",  params.apm_model)  ||
            (use_tts && !check_file("tts", params.tts_model))) {
            return;
        }

        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            if (state.octx) {
                _f6_event("OMNI_FREE_BEGIN", -1, state.octx);
                omni_free(state.octx);
                _f6_event("OMNI_FREE_END", -1, nullptr);
                state.octx = nullptr;
            }
        }

        _f6_event("OMNI_INIT_BEGIN", -1, nullptr);
        omni_context * octx = omni_init(&params, media_type, use_tts, params.tts_bin_dir, tts_gpu_layers,
                                         token2wav_device, duplex_mode,
                                         /*existing_model=*/nullptr, /*existing_ctx=*/nullptr, output_dir);
        _f6_event("OMNI_INIT_END", -1, octx);
        if (!octx) {
            res_error(res, format_error_response("omni_init failed"));
            return;
        }

        // voice clone / assistant prompt
        if (data.contains("voice_clone_prompt")) octx->omni_voice_clone_prompt = data["voice_clone_prompt"];
        if (data.contains("assistant_prompt")) octx->omni_assistant_prompt = data["assistant_prompt"];
        // K2: propagate voice_audio to ref_audio_path for KV cache key safety.
        // The cache key includes ctx_omni->ref_audio_path unconditionally.
        // Without this propagation, different voice_audio values produce identical
        // cache keys (always falling through to default_ref_audio.wav), causing
        // false cache HITs across different voice clones.
        if (!voice_audio.empty()) octx->ref_audio_path = voice_audio;

        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            state.octx = octx;
        }

        res_ok(res, {{"success", true}});
        } catch (const std::exception & e) {
            LOG_ERR("omni_init exception: %s\n", e.what());
            res_error(res, format_error_response(std::string("omni_init failed: ") + e.what()));
        } catch (...) {
            LOG_ERR("omni_init unknown exception\n");
            res_error(res, format_error_response("omni_init failed: unknown exception"));
        }
    });

    // POST /v1/stream/prefill
    svr.Post("/v1/stream/prefill", [&](const httplib::Request & req, httplib::Response & res) {
        json data = json::parse(req.body);

        if (!data.contains("audio_path_prefix") || !data.at("audio_path_prefix").is_string()) {
            res_error(res, format_error_response("\"audio_path_prefix\" must be provided as string"));
            return;
        }
        if (!data.contains("cnt") || !data.at("cnt").is_number_integer()) {
            res_error(res, format_error_response("\"cnt\" must be provided as integer"));
            return;
        }

        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            if (state.octx == nullptr) {
                res_error(res, format_error_response("omni context not initialized. call /v1/stream/omni_init first"));
                return;
            }
        }

        std::string audio_path = data.at("audio_path_prefix");
        std::string img_path   = data.value("img_path_prefix", "");
        std::string text       = data.value("text", "");
        int cnt                = data.at("cnt");
        int max_slice_nums     = data.value("max_slice_nums", -1);

        bool ok = false;
        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            ok = stream_prefill(state.octx, audio_path, img_path, cnt, max_slice_nums, text);
        }

        if (!ok) {
            res_error(res, format_error_response("stream_prefill failed"));
            return;
        }

        res_ok(res, {{"success", true}, {"audio_path_prefix", audio_path}, {"cnt", cnt}});
    });

    // POST /v1/stream/decode (SSE)
    svr.Post("/v1/stream/decode", [&](const httplib::Request & req, httplib::Response & res) {
        _f6_event("HANDLER_ENTER", -1, state.octx);
        _f6_transition_req_state(state.octx, REQ_VALIDATING, -1, "handler_enter");
        json data = json::parse(req.body);

        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            if (state.octx == nullptr) {
                res_error(res, format_error_response("omni context not initialized. call /v1/stream/omni_init first"));
                return;
            }
        }

        std::string debug_dir = data.value("debug_dir", "./");
        bool stream = data.value("stream", true);
        int round_idx = data.value("round_idx", -1);

        // length_penalty
        if (data.contains("length_penalty") && data.at("length_penalty").is_number()) {
            float lp = data.at("length_penalty").get<float>();
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            if (state.octx != nullptr) {
                state.octx->length_penalty = lp;
            }
        }

        if (!stream) {
            bool ok = false;

            // F6 LIFECYCLE: acquire octx_mutex for stream_decode
            _f6_event("OCTX_LOCK_WAIT_BEGIN", round_idx, state.octx);
            {
                std::lock_guard<std::mutex> lock(state.octx_mutex);
                _f6_event("OCTX_LOCK_ACQUIRED", round_idx, state.octx);
                _f6_event("STREAM_DECODE_BEGIN", round_idx, state.octx);
                _f6_event_ctx_state(round_idx, state.octx);

                // F6 A5: reject if context is not in a reusable state.
                // Attempt recovery if NOT_REUSABLE: the old generation's T2W worker
                // may have finished processing after the drain timed out.
                int ctx_state = state.octx->context_state.load();
                if (ctx_state == CTX_STATE_NOT_REUSABLE) {
                    // F6 A6: Check if old gen's drain quietly completed using
                    // generation-scoped predicate.  active_t2w_task_count is
                    // intentionally excluded — final_processed_generation is set
                    // at dequeue time, not process-complete time.
                    uint32_t req_gen = state.octx->request_generation.load(std::memory_order_relaxed);
                    // F6 R12: Recovery requires full completion (Flow+Vocoder done),
                    // not just dequeue.  final_processed_generation is now set ONLY
                    // after WAV write; active==0 prevents recovery during in-flight
                    // processing.
                    // F6 R13: Use per-generation active check for recovery.
                    uint32_t active_gen = state.octx->t2w_thread_info
                        ? state.octx->t2w_thread_info->active_t2w_generation.load(std::memory_order_relaxed) : 0;
                    bool old_drain_done = state.octx->t2w_thread_info
                        && state.octx->t2w_thread_info->final_processed_generation.load(std::memory_order_acquire) >= req_gen
                        && state.octx->t2w_thread_info->queued_t2w_task_count.load() == 0
                        && (active_gen == 0 || active_gen > req_gen);
                    if (old_drain_done) {
                        uint32_t completed_gen = state.octx->request_generation.load();
                        state.octx->drain_complete_generation.store(completed_gen);
                        state.octx->context_state.store(CTX_STATE_REUSABLE);
                        LOG_INF("Context recovered: old gen %u drain completed, state→REUSABLE\n",
                                completed_gen);
                        _f6_event("RECOVERY_DRAIN_COMPLETE", round_idx, state.octx);
                        // fall through to proceed normally
                    } else {
                        _f6_transition_req_state(state.octx, REQ_ERROR, round_idx, "ctx_not_reusable");
                        LOG_ERR("Context state=NOT_REUSABLE, old drain still pending (queued=%zu) — "
                                "rejecting request\n",
                                state.octx->t2w_thread_info
                                    ? state.octx->t2w_thread_info->queued_t2w_task_count.load() : (size_t)0);
                        _f6_event("HANDLER_RETURN_BUSY", round_idx, state.octx);
                        res_error(res, format_error_response(
                            "Context not ready — previous drain may have timed out, retry later"));
                        _f6_transition_req_state(state.octx, REQ_IDLE, round_idx, "busy_response_sent");
                        return;
                    }
                } else if (ctx_state != CTX_STATE_REUSABLE && ctx_state != CTX_STATE_DRAINING) {
                    _f6_transition_req_state(state.octx, REQ_ERROR, round_idx, "bad_ctx_state");
                    LOG_ERR("Context state=%d (not REUSABLE/DRAINING) — rejecting request\n", ctx_state);
                    _f6_event("HANDLER_RETURN_BUSY", round_idx, state.octx);
                    res_error(res, format_error_response(
                        "Context not ready — previous drain may have timed out, retry later"));
                    _f6_transition_req_state(state.octx, REQ_IDLE, round_idx, "busy_response_sent");
                    return;
                }

                _f6_transition_req_state(state.octx, REQ_DECODING, round_idx, "stream_decode_begin");
                ok = stream_decode(state.octx, debug_dir, round_idx);

                _f6_event("STREAM_DECODE_END", round_idx, state.octx);

                // F6 R10: transition to TTS_PENDING or RESPONDING based on whether
                // T2W drain is needed.  For non-TTS requests or when TTS wasn't
                // active, skip straight to RESPONDING.
                if (state.octx->use_tts) {
                    _f6_transition_req_state(state.octx, REQ_TTS_PENDING, round_idx, "decode_done_tts");
                } else {
                    _f6_transition_req_state(state.octx, REQ_RESPONDING, round_idx, "decode_done_no_tts");
                }

                // F6 R8: Drain T2W audio INSIDE the octx_mutex to prevent a race
                // where request B acquires the lock, increments request_generation,
                // and invalidates request A's drain between OCTX_UNLOCKED and
                // T2W_DRAIN_BEGIN.  The drain holds drain_mtx (not octx_mutex),
                // so stream_decode for the next request is still blocked by the
                // outer lock_guard but the internal CV wait won't deadlock.
                if (state.octx->use_tts) {
                    _f6_transition_req_state(state.octx, REQ_DRAINING, round_idx, "drain_begin");
                    _f6_event("T2W_DRAIN_BEGIN", round_idx, state.octx);
                    _f6_event_ctx_state(round_idx, state.octx);
                    bool drained = omni_duplex_drain_tts_audio(state.octx);
                    _f6_event("T2W_DRAIN_END", round_idx, state.octx);

                    if (!drained) {
                        _f6_transition_req_state(state.octx, REQ_ERROR, round_idx, "drain_failed");
                        LOG_ERR("T2W drain FAILED — context state is stale, "
                                "rejecting request to prevent hang\n");
                        _f6_event("HANDLER_RETURN_DRAIN_FAILED", round_idx, state.octx);
                        res_error(res, format_error_response(
                            "T2W drain timed out — context busy, retry later"));
                        _f6_transition_req_state(state.octx, REQ_IDLE, round_idx, "error_response_sent");
                        return;
                    }
                    _f6_transition_req_state(state.octx, REQ_RESPONDING, round_idx, "drain_complete");
                }
            }
            _f6_event("OCTX_UNLOCKED", round_idx, state.octx);

            if (!ok) {
                _f6_transition_req_state(state.octx, REQ_ERROR, round_idx, "decode_failed");
                res_error(res, format_error_response("stream_decode failed"));
                _f6_transition_req_state(state.octx, REQ_IDLE, round_idx, "error_response_sent");
                return;
            }

            _f6_event("HANDLER_RETURN", round_idx, state.octx);
            res_ok(res, {{"success", true}});
            _f6_transition_req_state(state.octx, REQ_IDLE, round_idx, "response_sent");
            return;
        }

        // SSE streaming
        res.set_chunked_content_provider("text/event-stream",
            [&](size_t, httplib::DataSink & sink) -> bool {
                // reset state
                {
                    std::lock_guard<std::mutex> lock(state.octx->text_mtx);
                    state.octx->text_queue.clear();
                    state.octx->text_done_flag = false;
                    state.octx->text_streaming = true;
                }

                // start decode in background thread
                std::thread worker([&](std::string dd, int ri) {
                    std::lock_guard<std::mutex> lock(state.octx_mutex);
                    (void) stream_decode(state.octx, dd, ri);
                }, debug_dir, round_idx);

                // poll text queue
                while (true) {
                    std::unique_lock<std::mutex> lk(state.octx->text_mtx);
                    state.octx->text_cv.wait_for(lk, std::chrono::milliseconds(200), [&]{
                        return !state.octx->text_queue.empty() || state.octx->text_done_flag;
                    });

                    while (!state.octx->text_queue.empty()) {
                        std::string frag = std::move(state.octx->text_queue.front());
                        state.octx->text_queue.pop_front();
                        lk.unlock();

                        json ev;
                        if (frag == "__IS_LISTEN__") {
                            ev = {{"content", ""}, {"stop", false}, {"is_listen", true}, {"end_of_turn", true}};
                        } else if (frag == "__END_OF_TURN__") {
                            ev = {{"content", ""}, {"stop", true}, {"is_listen", false}, {"end_of_turn", true}};
                        } else {
                            ev = {{"content", frag}, {"stop", false}, {"is_listen", false}, {"end_of_turn", false}};
                        }

                        if (!server_sent_event(sink, ev)) {
                            if (worker.joinable()) worker.join();
                            return false;
                        }
                        lk.lock();
                    }

                    if (state.octx->text_done_flag) break;
                }

                if (worker.joinable()) worker.join();

                // send done
                static const std::string ev_done = "data: [DONE]\n\n";
                sink.write(ev_done.data(), ev_done.size());
                return true;
            });
    });

    // POST /v1/stream/update_session_config
    svr.Post("/v1/stream/update_session_config", [&](const httplib::Request & req, httplib::Response & res) {
        json data = json::parse(req.body);
        int media_type = data.value("media_type", -1);

        {
            std::lock_guard<std::mutex> lock(state.octx_mutex);
            if (state.octx == nullptr) {
                res_error(res, format_error_response("omni context not initialized"));
                return;
            }
            if (media_type > 0) {
                state.octx->media_type = media_type;
            }
        }

        res_ok(res, {{"success", true}});
    });

    //
    // Backend Protocol (WebSocket + HTTP unary)
    //
    svr.WebSocket("/backend", [&](const httplib::Request &, httplib::ws::WebSocket & ws) {
        handle_ws_backend(ws, state.session_mgr, params,
                          /*model*/nullptr, /*ctx*/nullptr,
                          state.octx, state.octx_mutex);
    });

    svr.Post("/sessions/:session_id/close", [&](const httplib::Request & req, httplib::Response & res) {
        std::string session_id = req.path_params.at("session_id");
        LOG_INF("Close session requested: %s\n", session_id.c_str());

        auto * session = state.session_mgr.get(session_id);
        if (!session || session->state != SessionState::ACTIVE) {
            res_error(res, format_error_response("session not found", "not_found"));
            res.status = 404;
            return;
        }

        state.session_mgr.request_transport_close(session_id);

        // close is a completion primitive: do not return until inference
        // threads are stopped and the shared omni_context is safe to reuse.
        {
            std::lock_guard<std::mutex> octx_lock(state.octx_mutex);
            auto * closing = state.session_mgr.get(session_id);
            if (closing && closing->octx) {
                closing->octx->break_event = true;
                {
                    std::lock_guard<std::mutex> lk(closing->octx->text_mtx);
                    closing->octx->text_queue.clear();
                    closing->octx->text_done_flag = true;
                }
                closing->octx->text_cv.notify_all();
                omni_prepare_for_reuse(closing->octx);
            }

            state.session_mgr.close(session_id);
        }

        json resp;
        resp["ok"] = true;
        resp["session_id"] = session_id;
        resp["closed"] = true;
        res_ok(res, resp);
    });

    // F6 R11: set PID and port for ownership verification in health endpoint
    state.server_pid = (int)getpid();
    state.bound_port = params.port;

    // start server
    svr.listen("0.0.0.0", params.port);

    // cleanup
    {
        std::lock_guard<std::mutex> lock(state.octx_mutex);
        if (state.octx) {
            omni_free(state.octx);
            state.octx = nullptr;
        }
    }
    llama_backend_free();

    return 0;
}
