# Profiling Data Reproduction Commands

## Baseline (OFF)

```bash
source /usr/local/Ascend/cann-9.1.0-beta.1/set_env.sh
cd /workspace/llama.cpp-omni-operator
msprof --application="./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 0 --omni \
  --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 1 \
  --test-start 4" \
  --output=profiles/decode-speak/ \
  --aic-metrics=PipeUtilization
```

Binary SHA256: 6913c972b30177fd
Model: /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
CANN: 9.1.0-beta.1
Date: 2026-07-28 06:45 UTC
Test case: tc=4 (MEDIUM)

## RoPE F16 ON

```bash
source /usr/local/Ascend/cann-9.1.0-beta.1/set_env.sh
export GGML_CANN_ROPE_FP16=1
cd /workspace/llama.cpp-omni-operator
msprof --application="./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 0 --omni \
  --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 1 \
  --test-start 4" \
  --output=profiles/decode-speak/rope_fp16/ \
  --aic-metrics=PipeUtilization
```

Binary SHA256: 6913c972b30177fd
Date: 2026-07-28 07:06 UTC
Test case: tc=4 (MEDIUM)

## Parsed Summary CSVs

The key outputs (KEPT in git) are in:
- `profiles/decode-speak/*/mindstudio_profiler_output/op_summary*.csv`
- `profiles/decode-speak/*/mindstudio_profiler_output/op_statistic*.csv`
- `profiles/decode-speak/*/mindstudio_profiler_output/api_statistic*.csv`
- `profiles/decode-speak/*/mindstudio_profiler_output/task_time*.csv`

Raw msprof data (device_*, host/*, sqlite/*, *.db) has been moved to artifacts/.
MANIFEST.json contains SHA256 of all original files.
