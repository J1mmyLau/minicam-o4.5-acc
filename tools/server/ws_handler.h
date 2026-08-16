#pragma once

#include <string>
#include <string_view>
#include <vector>
#include <functional>
#include <mutex>

struct omni_context;
struct common_params;
struct llama_model;
struct llama_context;
class SessionManager;

namespace httplib {
namespace ws { class WebSocket; }
}

// ============================================================================
// WS /backend handler — main entry point called from server.cpp
// ============================================================================

void handle_ws_backend(httplib::ws::WebSocket & ws,
                       SessionManager & session_mgr,
                       common_params & params_base,
                       llama_model * model,
                       llama_context * ctx,
                       omni_context *& shared_octx,  // server-owned, reused across sessions
                       std::mutex & octx_mutex);

// ============================================================================
// Shared session cleanup helpers — used by both WS handler (cleanup path)
// and HTTP close endpoint (server-omni.cpp) to ensure consistent lifecycle.
// ============================================================================

// Clear KV cache + reset n_past for the given omni_context.
// Safe to call after omni_prepare_for_reuse (threads joined).
void ws_cleanup_kv_cache_for_reuse(omni_context * octx);

// Transition context_state from ACTIVE → DRAINING → REUSABLE.
// Advances T2W generation counters for text-only sessions.
// Call before omni_prepare_for_reuse (first call) and after KV clear (second call).
void ws_finalize_context_reusable(omni_context * octx);

// ============================================================================
// Helpers: base64 audio/JPEG → temp files
// ============================================================================

struct TempMediaFiles {
    std::string audio_path;      // WAV file path (empty if no audio)
    std::string image_path;      // PNG/JPEG file path (empty if no image)
    
    // Write base64 float32 PCM to a temp WAV file
    // Returns empty string on failure
    static std::string write_audio_wav(const std::string & b64, const std::string & temp_dir, int counter);
    
    // Write base64 JPEG/PNG bytes to a temp file
    // Returns empty string on failure
    static std::string write_image_jpeg(const std::string & b64, const std::string & temp_dir, int counter);
    
    // Create a temp file from raw bytes
    static std::string write_temp_file(const std::string & temp_dir, const std::string & prefix,
                                       const std::string & suffix, const void * data, size_t len);
    
    // Clean up temp files
    void cleanup();
};
