#!/bin/bash
# P7-B: RoPE FP16 paired A/B test
# Compares GGML_CANN_ROPE_FP16=0 (baseline) vs =1 (candidate)
# Paired design: OFF then ON, alternating, to minimize temporal bias
set -euo pipefail

source /usr/local/Ascend/cann-9.1.0-beta.1/set_env.sh 2>/dev/null

BINARY="/workspace/llama.cpp-omni-operator/build/bin/llama-omni-cli"
MODEL="/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf"
TPREFIX="/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/omni_test_case/omni_test_case_"
OUTDIR="/workspace/llama.cpp-omni-operator/profiles/rope_fp16_ab"
TC=4  # MEDIUM — fastest median (35s p50)
NWARM=3
NPAIRS=15

mkdir -p "$OUTDIR"

echo "# RoPE FP16 Paired A/B Test"
echo "## $(date -u +'%Y-%m-%d %H:%M UTC')"
echo "## Binary: $(sha256sum $BINARY | cut -c1-16)"
echo "## Test case: $TC (MEDIUM)"
echo "## Pairs: $NPAIRS (warmup=$NWARM)"
echo ""

# Warmup phase (discarded)
echo "=== WARMUP ($NWARM iterations) ==="
for i in $(seq 1 $NWARM); do
    rm -rf /workspace/llama.cpp-omni-operator/tools/omni/output/round_* 2>/dev/null
    MODE=$(( i % 2 ))  # alternate
    echo "Warmup $i/$NWARM: MODE=$MODE"
    GGML_CANN_ROPE_FP16=$MODE timeout 300 "$BINARY" -m "$MODEL" -ngl 0 --omni \
        --test "$TPREFIX" 1 --test-start "$TC" \
        > /dev/null 2>&1 || true
done

# Measured phase
echo ""
echo "=== MEASURED ($NPAIRS pairs) ==="
echo "pair,backend,decode_to_first_audio_ms,request_to_first_audio_ms,wall_ms,exit_code,wav_count"

for pair in $(seq 1 $NPAIRS); do
    for mode in 0 1; do
        rm -rf /workspace/llama.cpp-omni-operator/tools/omni/output/round_* 2>/dev/null

        T0=$(date +%s%N)
        GGML_CANN_ROPE_FP16=$mode timeout 600 "$BINARY" -m "$MODEL" -ngl 0 --omni \
            --test "$TPREFIX" 1 --test-start "$TC" \
            > "${OUTDIR}/pair${pair}_mode${mode}.stdout" \
            2> "${OUTDIR}/pair${pair}_mode${mode}.stderr"
        rc=$?
        T1=$(date +%s%N)
        wall_ms=$(( (T1 - T0) / 1000000 ))

        # Extract metrics from stderr
        decode_ms=$(grep -oP 'decode_to_first_audio\):\s*\K[0-9]+' "${OUTDIR}/pair${pair}_mode${mode}.stderr" | head -1 || echo "NA")
        request_ms=$(grep -oP 'request_to_first_audio\):\s*\K[0-9]+' "${OUTDIR}/pair${pair}_mode${mode}.stderr" | head -1 || echo "NA")

        # Count WAV files
        wav_count=$(find /workspace/llama.cpp-omni-operator/tools/omni/output/ -name "*.wav" 2>/dev/null | wc -l || echo "0")

        backend=$([ "$mode" = "1" ] && echo "FP16" || echo "F32")
        echo "${pair},${backend},${decode_ms},${request_ms},${wall_ms},${rc},${wav_count}"
    done
    echo "  Pair $pair/$NPAIRS done at $(date +%H:%M)" >&2
done

echo ""
echo "## Done: $(date -u +'%Y-%m-%d %H:%M UTC')"
echo "## Results: $OUTDIR/pairs.csv"
