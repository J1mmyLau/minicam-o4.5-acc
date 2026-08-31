#include "token2wav-impl.h"
#include "token2wav-profile.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {


bool file_exists(const std::string & path) {
    std::ifstream f(path, std::ios::binary);
    return (bool) f;
}

// pcm转wav
bool write_wav_mono_i16(const std::string & path, const std::vector<float> & wave_bt, int sample_rate) {
    const int16_t num_channels    = 1;
    const int16_t bits_per_sample = 16;
    const int16_t block_align     = num_channels * (bits_per_sample / 8);
    const int32_t byte_rate       = sample_rate * block_align;

    std::vector<int16_t> pcm((size_t) wave_bt.size());
    for (size_t i = 0; i < wave_bt.size(); ++i) {
        float x = wave_bt[i];
        if (!std::isfinite(x)) {
            x = 0.0f;
        }
        x = std::max(-1.0f, std::min(1.0f, x));
        const float y = x * 32767.0f;
        if (y >= 32767.0f) {
            pcm[i] = (int16_t) 32767;
        } else if (y <= -32768.0f) {
            pcm[i] = (int16_t) -32768;
        } else {
            pcm[i] = (int16_t) (y);
        }
    }

    const uint32_t data_bytes = (uint32_t) (pcm.size() * sizeof(int16_t));
    const uint32_t riff_size  = 36u + data_bytes;

    std::ofstream out(path, std::ios::binary);
    if (!out) {
        return false;
    }

    out.write("RIFF", 4);
    out.write(reinterpret_cast<const char *>(&riff_size), 4);
    out.write("WAVE", 4);

    out.write("fmt ", 4);
    const uint32_t fmt_size     = 16;
    const uint16_t audio_format = 1;  // PCM 格式
    out.write(reinterpret_cast<const char *>(&fmt_size), 4);
    out.write(reinterpret_cast<const char *>(&audio_format), 2);
    out.write(reinterpret_cast<const char *>(&num_channels), 2);
    out.write(reinterpret_cast<const char *>(&sample_rate), 4);
    out.write(reinterpret_cast<const char *>(&byte_rate), 4);
    out.write(reinterpret_cast<const char *>(&block_align), 2);
    out.write(reinterpret_cast<const char *>(&bits_per_sample), 2);

    out.write("data", 4);
    out.write(reinterpret_cast<const char *>(&data_bytes), 4);
    out.write(reinterpret_cast<const char *>(pcm.data()), (std::streamsize) data_bytes);
    return true;
}

bool ensure_dir(const std::string & dir) {
    if (dir.empty()) {
        return false;
    }
    std::error_code ec;
    std::filesystem::create_directories(std::filesystem::path(dir), ec);
    return !ec;
}

std::string parent_dir_of(const std::string & path) {
    const auto p = std::filesystem::path(path).parent_path();
    return p.empty() ? std::string() : p.string();
}

bool waves_equal(const std::vector<float> & lhs,
                 const std::vector<float> & rhs) {
    return lhs.size() == rhs.size() &&
           (lhs.empty() ||
            std::memcmp(lhs.data(), rhs.data(),
                        lhs.size() * sizeof(float)) == 0);
}

bool init_session(omni::flow::Token2WavSession & sess,
                  const std::string &             encoder_gguf,
                  const std::string &             flow_matching_gguf,
                  const std::string &             flow_extra_gguf,
                  const std::string &             prompt_cache_gguf,
                  const std::string &             prompt_bundle_dir,
                  const std::string &             vocoder_gguf,
                  const std::string &             device_token2mel,
                  const std::string &             device_vocoder,
                  int                             n_timesteps,
                  float                           temperature,
                  float                           cfg_rate) {
    const std::string coreml_model;
    return prompt_bundle_dir.empty()
        ? sess.init_from_prompt_cache_gguf(
              encoder_gguf, flow_matching_gguf, flow_extra_gguf,
              prompt_cache_gguf, vocoder_gguf, device_token2mel,
              device_vocoder, n_timesteps, temperature, coreml_model,
              cfg_rate)
        : sess.init_from_prompt_bundle(
              encoder_gguf, flow_matching_gguf, flow_extra_gguf,
              prompt_bundle_dir, vocoder_gguf, device_token2mel,
              device_vocoder, n_timesteps, temperature, coreml_model,
              cfg_rate);
}

int run_transaction_smoke(
        const std::string & encoder_gguf,
        const std::string & flow_matching_gguf,
        const std::string & flow_extra_gguf,
        const std::string & prompt_cache_gguf,
        const std::string & prompt_bundle_dir,
        const std::string & vocoder_gguf,
        const std::string & device_token2mel,
        const std::string & device_vocoder,
        int                 n_timesteps,
        float               temperature,
        float               cfg_rate,
        const std::string & invalid_bundle_dir,
        const std::vector<int32_t> & tokens) {
    if (tokens.size() < 2 * (size_t) omni::flow::Token2Mel::kDt) {
        std::fprintf(stderr, "transaction smoke needs at least two token windows\n");
        return 6;
    }

    omni::flow::Token2WavSession control;
    omni::flow::Token2WavSession candidate;
    if (!init_session(control, encoder_gguf, flow_matching_gguf,
                      flow_extra_gguf, prompt_cache_gguf, prompt_bundle_dir,
                      vocoder_gguf, device_token2mel, device_vocoder,
                      n_timesteps, temperature, cfg_rate) ||
        !init_session(candidate, encoder_gguf, flow_matching_gguf,
                      flow_extra_gguf, prompt_cache_gguf, prompt_bundle_dir,
                      vocoder_gguf, device_token2mel, device_vocoder,
                      n_timesteps, temperature, cfg_rate)) {
        std::fprintf(stderr, "transaction smoke session initialization failed\n");
        return 6;
    }

    const size_t dt = (size_t) omni::flow::Token2Mel::kDt;
    std::vector<float> control_first;
    std::vector<float> candidate_first;
    if (!control.feed_window(tokens.data(), (int64_t) dt, false,
                             control_first) ||
        !candidate.feed_window(tokens.data(), (int64_t) dt, false,
                               candidate_first) ||
        !waves_equal(control_first, candidate_first)) {
        std::fprintf(stderr, "transaction smoke first-window replay mismatch\n");
        return 6;
    }

    const int active_nt = candidate.t2w.n_timesteps();
    const float active_temperature = candidate.t2w.temperature();
    const float active_cfg = candidate.t2w.inference_cfg_rate();
    if (!prompt_bundle_dir.empty()) {
        if (!candidate.exercise_prompt_transaction_rollback_for_test(
                prompt_bundle_dir, active_nt, active_temperature,
                active_cfg)) {
            std::fprintf(stderr,
                         "transaction smoke explicit rollback failed\n");
            return 6;
        }
    }
    if (candidate.switch_prompt_bundle(invalid_bundle_dir)) {
        std::fprintf(stderr, "transaction smoke invalid switch unexpectedly succeeded\n");
        return 6;
    }
    if (candidate.t2w.n_timesteps() != active_nt ||
        candidate.t2w.temperature() != active_temperature ||
        candidate.t2w.inference_cfg_rate() != active_cfg) {
        std::fprintf(stderr, "transaction smoke changed active parameters on failure\n");
        return 6;
    }

    std::vector<float> control_second;
    std::vector<float> candidate_second;
    if (!control.feed_window(tokens.data() + dt, (int64_t) dt, false,
                             control_second) ||
        !candidate.feed_window(tokens.data() + dt, (int64_t) dt, false,
                               candidate_second) ||
        !waves_equal(control_second, candidate_second)) {
        std::fprintf(stderr, "transaction smoke continuation mismatch after failure\n");
        return 6;
    }

    omni::flow::Token2WavSession control_pending;
    omni::flow::Token2WavSession candidate_pending;
    if (!init_session(control_pending, encoder_gguf, flow_matching_gguf,
                      flow_extra_gguf, prompt_cache_gguf, prompt_bundle_dir,
                      vocoder_gguf, device_token2mel, device_vocoder,
                      n_timesteps, temperature, cfg_rate) ||
        !init_session(candidate_pending, encoder_gguf, flow_matching_gguf,
                      flow_extra_gguf, prompt_cache_gguf, prompt_bundle_dir,
                      vocoder_gguf, device_token2mel, device_vocoder,
                      n_timesteps, temperature, cfg_rate)) {
        std::fprintf(stderr, "transaction smoke pending-session initialization failed\n");
        return 6;
    }

    const int64_t prefix = omni::flow::Token2Mel::kDt - 1;
    std::vector<float> empty_control;
    std::vector<float> empty_candidate;
    if (!control_pending.feed_tokens(tokens.data(), prefix, false,
                                     empty_control) ||
        !candidate_pending.feed_tokens(tokens.data(), prefix, false,
                                       empty_candidate) ||
        !empty_control.empty() || !empty_candidate.empty() ||
        candidate_pending.switch_prompt_bundle(invalid_bundle_dir)) {
        std::fprintf(stderr, "transaction smoke pending precondition failed\n");
        return 6;
    }

    std::vector<float> pending_control_wave;
    std::vector<float> pending_candidate_wave;
    if (!control_pending.feed_tokens(tokens.data() + prefix, 1, false,
                                     pending_control_wave) ||
        !candidate_pending.feed_tokens(tokens.data() + prefix, 1, false,
                                       pending_candidate_wave) ||
        !waves_equal(pending_control_wave, pending_candidate_wave)) {
        std::fprintf(stderr, "transaction smoke pending tokens were not preserved\n");
        return 6;
    }

    std::printf("[transaction-smoke] PASS invalid_switch=%s n_timesteps=%d temperature=%g cfg=%g\n",
                invalid_bundle_dir.c_str(), active_nt, active_temperature,
                active_cfg);
    return 0;
}

}  // namespace

int main() {
    using clock = std::chrono::steady_clock;
    const auto t_program0 = clock::now();

    // token2wav-example：主要关注初始化和两种送入输出方式即可
    // 目前是使用读取prompt_cache.gguf的方式初始化然后以call的方式来流式输出pcm并转换为wav

    // 默认路径，根据5个gguf和两个输出位置改动；可用环境变量覆盖，便于做纯 T2W profile。
    //   OMNI_T2W_MODEL_DIR  : token2wav-gguf 目录（内含 encoder/flow_*/hifigan2/prompt_cache）
    //   OMNI_T2W_DEVICE     : "cpu" / "gpu" / "gpu:<idx>"（token2mel 设备）
    //   OMNI_VOC_DEVICE : 可选，覆盖 vocoder 设备；macOS 默认走 CPU，避免 Metal vocoder 慢路径
    //   OMNI_T2W_OUT_WAV    : 合并输出 WAV 路径
    //   OMNI_T2W_OUT_CHUNK_DIR : 每个 callback chunk 的输出目录（空串 = 不落盘）
    auto env_or = [](const char * name, const std::string & def) {
        const char * v = std::getenv(name);
        return (v && *v) ? std::string(v) : def;
    };

    std::string model_dir      = env_or("OMNI_T2W_MODEL_DIR", "./tools/omni/convert/gguf/token2wav-gguf");
    std::string encoder_gguf       = model_dir + "/encoder.gguf";
    std::string flow_matching_gguf = model_dir + "/flow_matching.gguf";
    std::string flow_extra_gguf    = model_dir + "/flow_extra.gguf";
    std::string vocoder_gguf       = model_dir + "/hifigan2.gguf";
    std::string prompt_cache_gguf  = model_dir + "/prompt_cache.gguf";
    std::string prompt_bundle_dir  = env_or("OMNI_T2W_PROMPT_BUNDLE_DIR", "");

    std::string out_wav            = env_or("OMNI_T2W_OUT_WAV", "/tmp/token2wav_example_stream.wav");
    std::string out_chunk_wav_dir  = env_or("OMNI_T2W_OUT_CHUNK_DIR", "/tmp/token2wav_example_chunks");

    std::string device_token2mel   = env_or("OMNI_T2W_DEVICE", "gpu");
#if defined(__APPLE__)
    std::string device_vocoder     = env_or("OMNI_VOC_DEVICE", "cpu");
#else
    std::string device_vocoder     = env_or("OMNI_VOC_DEVICE", device_token2mel);
#endif

    int       n_timesteps = std::atoi(env_or("OMNI_T2W_N_TIMESTEPS", "5").c_str());
    float     cfg_rate    = std::atof(env_or("OMNI_T2W_CFG", "0.7").c_str());
    float     temperature = 1.0f;
    const int sr          = omni::flow::Token2Wav::kSampleRate;

    {
        const std::string out_parent = parent_dir_of(out_wav);
        if (!out_parent.empty() && !ensure_dir(out_parent)) {
            std::fprintf(stderr, "failed to create out_wav parent dir: %s\n", out_parent.c_str());
            return 2;
        }
        if (!out_chunk_wav_dir.empty() && !ensure_dir(out_chunk_wav_dir)) {
            std::fprintf(stderr, "failed to create out_chunk_wav_dir: %s\n", out_chunk_wav_dir.c_str());
            return 2;
        }
    }

    if (prompt_bundle_dir.empty() && !file_exists(prompt_cache_gguf)) {
        std::fprintf(stderr, "prompt_cache.gguf not found: %s\n", prompt_cache_gguf.c_str());
        return 2;
    }

    const int repeat = std::max(1, std::atoi(env_or("OMNI_T2W_REPEAT", "1").c_str()));
    const bool transaction_smoke =
        env_or("OMNI_T2W_TRANSACTION_SMOKE", "0") == "1";
    const std::string invalid_bundle_dir = env_or(
        "OMNI_T2W_INVALID_PROMPT_BUNDLE_DIR",
        "/tmp/omni-token2wav-invalid-prompt-bundle");

    // 例子 token
    std::vector<int32_t> tokens_base = {
        1493, 4299, 4218, 2049, 528,  2752, 4850, 4569, 4575, 6372, 2127, 4068, 2312, 4993, 4769, 2300,
        226,  2175, 2160, 2152, 6311, 6065, 4859, 5102, 4615, 6534, 6426, 1763, 2249, 2209, 5938, 1725,
        6048, 3816, 6058, 958,  63,   4460, 5914, 2379, 735,  5319, 4593, 2328, 890,  35,   751,  1483,
        1484, 1483, 2112, 303,  4753, 2301, 5507, 5588, 5261, 5744, 5501, 2341, 2001, 2252, 2344, 1860,
        2031, 414,  4366, 4366, 6059, 5300, 4814, 5092, 5100, 1923, 3054, 4320, 4296, 2148, 4371, 5831,
        5084, 5027, 4946, 4946, 2678, 575,  575,  521,  518,  638,  1367, 2804, 3402, 4299,
    };
    std::vector<int32_t> tokens;
    tokens.reserve(tokens_base.size() * (size_t) repeat);
    for (int r = 0; r < repeat; ++r) {
        tokens.insert(tokens.end(), tokens_base.begin(), tokens_base.end());
    }

    if (transaction_smoke) {
        return run_transaction_smoke(
            encoder_gguf, flow_matching_gguf, flow_extra_gguf,
            prompt_cache_gguf, prompt_bundle_dir, vocoder_gguf,
            device_token2mel, device_vocoder, n_timesteps, temperature,
            cfg_rate, invalid_bundle_dir, tokens);
    }

    omni::flow::Token2WavSession sess;
    // 初始化：加载 encoder/flow/vocoder 模型，导入 prompt_cache用于初始化
    const auto t_init0 = clock::now();
    const bool init_ok = init_session(
        sess, encoder_gguf, flow_matching_gguf, flow_extra_gguf,
        prompt_cache_gguf, prompt_bundle_dir, vocoder_gguf,
        device_token2mel, device_vocoder, n_timesteps, temperature,
        cfg_rate);
    if (!init_ok) {
        std::fprintf(stderr, "%s failed\n",
                     prompt_bundle_dir.empty() ? "init_from_prompt_cache_gguf" : "init_from_prompt_bundle");
        return 3;
    }
    const auto t_init1 = clock::now();

    constexpr int32_t step_valid  = 25;
    constexpr int32_t chunk_total = 28;
    int64_t           pos         = 0;
    const int64_t     n           = (int64_t) tokens.size();

    std::vector<float> wave_all;

    int call_id = 0;
    const auto t_infer0 = clock::now();
    while (pos + chunk_total <= n) {
        // 滑窗规则：每次取 28 个 token（25 主要内容 + 3 lookahead），下一次 pos += 25
        std::vector<int32_t> win(tokens.begin() + pos, tokens.begin() + pos + chunk_total);
        // callback 推流：调用 Token2WavSession::feed_window(callback形式)，一窗推理完成后立刻把音频分块回调
        // 需要注意pcm 指针只在回调执行期间有效
        if (!sess.feed_window(win, false, [&](const float * pcm, int64_t n_samples) {
                wave_all.insert(wave_all.end(), pcm, pcm + n_samples);
                if (!out_chunk_wav_dir.empty()) {
                    const std::string  chunk_path = out_chunk_wav_dir + "/call" + std::to_string(call_id) + ".wav";
                    std::vector<float> tmp(pcm, pcm + n_samples);
                    if (!write_wav_mono_i16(chunk_path, tmp, sr)) {
                        std::fprintf(stderr, "failed to write chunk wav: %s\n", chunk_path.c_str());
                    }
                }
            })) {
            std::fprintf(stderr, "feed_window failed\n");
            return 4;
        }
        pos += step_valid;
        call_id++;
    }

    {
        // final flush：最后一段不足 28 时也要调用一次，然后传is_final=true 把剩下的缓存吐干净
        std::vector<int32_t> tail;
        if (pos < n) {
            tail.assign(tokens.begin() + pos, tokens.end());
        }
        if (!sess.feed_window(tail, true, [&](const float * pcm, int64_t n_samples) {
                wave_all.insert(wave_all.end(), pcm, pcm + n_samples);
                if (!out_chunk_wav_dir.empty()) {
                    const std::string  chunk_path = out_chunk_wav_dir + "/call" + std::to_string(call_id) + ".wav";
                    std::vector<float> tmp(pcm, pcm + n_samples);
                    if (!write_wav_mono_i16(chunk_path, tmp, sr)) {
                        std::fprintf(stderr, "failed to write chunk wav: %s\n", chunk_path.c_str());
                    }
                }
            })) {
            std::fprintf(stderr, "feed_window(final) failed\n");
            return 4;
        }
        call_id++;
    }
    const auto t_infer1 = clock::now();

    const auto t_write0 = clock::now();
    if (!write_wav_mono_i16(out_wav, wave_all, sr)) {
        std::fprintf(stderr, "failed to write wav: %s\n", out_wav.c_str());
        return 5;
    }
    const auto t_write1 = clock::now();

    {
        const double init_ms  = std::chrono::duration<double, std::milli>(t_init1 - t_init0).count();
        const double infer_ms = std::chrono::duration<double, std::milli>(t_infer1 - t_infer0).count();
        const double write_ms = std::chrono::duration<double, std::milli>(t_write1 - t_write0).count();
        const double total_ms = std::chrono::duration<double, std::milli>(clock::now() - t_program0).count();
        std::fprintf(stderr,
                     "[timing-total] init=%.3fms infer=%.3fms write=%.3fms total=%.3fms\n",
                     init_ms, infer_ms, write_ms, total_ms);
    }

    std::printf("[done] out_wav=%s sr=%d total_samples=%zu n_calls=%d\n", out_wav.c_str(), sr, wave_all.size(),
                call_id);
    if (!out_chunk_wav_dir.empty()) {
        std::printf("[done] out_chunk_wav_dir=%s\n", out_chunk_wav_dir.c_str());
    }

    // 汇总 profile 结果（OMNI_T2W_PROFILE=0 时会直接跳过）
    omni::flow::profile::print_summary(stderr);
    return 0;
}


